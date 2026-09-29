"""
HWPX-RECOGNITION-CORPUS-PROFILING-PREFLIGHT-01

실제 HWPX 후보 문서들을 read-only로 스캔/프로파일링하여
corpus DB ingest 가능 여부를 사전 분류한다.

절대 금지:
- 원본 HWPX 수정 없음
- writer 호출 없음
- corpus.sqlite3 생성/수정 없음
- AI API / OCR 호출 없음
- 절대경로 보고서 저장 없음
- 원본 파일명 그대로 저장 없음
- 개인정보 원문 출력 없음
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

NS_HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
NS_HH = "http://www.hancom.co.kr/hwpml/2011/head"
NS_OPF = "http://www.idpf.org/2007/opf/"

STATUS_READY = "READY_FOR_CORPUS_INGEST"
STATUS_BROKEN_ZIP = "BROKEN_ZIP"
STATUS_MISSING_XML = "MISSING_REQUIRED_XML"
STATUS_UNSUPPORTED = "UNSUPPORTED_STRUCTURE"
STATUS_EMPTY = "EMPTY_DOCUMENT"
STATUS_PII = "PII_REVIEW_REQUIRED"
STATUS_LARGE = "LARGE_DOCUMENT_REVIEW_REQUIRED"
STATUS_DUPLICATE = "DUPLICATE_CANDIDATE"
STATUS_UNKNOWN = "UNKNOWN_REVIEW_REQUIRED"

# 대용량 문서 기준: 섹션×표 합산 기준
LARGE_THRESHOLD_CELLS = 5000
LARGE_THRESHOLD_PARAGRAPHS = 3000

# PII 탐지 패턴 (보고서 포함 여부 체크용 — 원문 저장 금지)
_PII_PATTERNS = [
    re.compile(r"\d{2,3}-\d{3,4}-\d{4}"),  # 전화번호
    re.compile(r"\d{3}-\d{2}-\d{5}"),  # 사업자번호
    re.compile(r"\d{6}-[1-4]\d{6}"),  # 주민번호 패턴
    re.compile(r"[가-힣]{2,4}\s*\d{3}-\d{3,4}-\d{4}"),  # 이름+전화
]


# 파일명 PII 마스킹: sha256(절대경로) 기반
def mask_filename(path: Path) -> str:
    h = hashlib.sha256(str(path.resolve()).encode("utf-8", errors="replace")).hexdigest()
    return f"file_{h[:12]}.hwpx"


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    try:
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
    except OSError:
        h.update(str(path).encode())
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Profile record
# ---------------------------------------------------------------------------


@dataclass
class ProfileRecord:
    fileHash: str = ""
    maskedFileName: str = ""
    fileSize: int = 0
    sectionCount: int = 0
    tableCount: int = 0
    cellCount: int = 0
    paragraphCount: int = 0
    objectCount: int = 0
    labelCandidateCount: int = 0
    status: str = STATUS_UNKNOWN
    blockedReason: str = ""
    warnings: list[str] = field(default_factory=list)
    profiledAt: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "fileHash": self.fileHash,
            "maskedFileName": self.maskedFileName,
            "fileSize": self.fileSize,
            "sectionCount": self.sectionCount,
            "tableCount": self.tableCount,
            "cellCount": self.cellCount,
            "paragraphCount": self.paragraphCount,
            "objectCount": self.objectCount,
            "labelCandidateCount": self.labelCandidateCount,
            "status": self.status,
            "blockedReason": self.blockedReason,
            "warnings": self.warnings,
            "profiledAt": self.profiledAt,
        }


# ---------------------------------------------------------------------------
# Core profiling logic
# ---------------------------------------------------------------------------


def _count_paragraphs(section_root: ET.Element) -> int:
    return sum(1 for _ in section_root.iter(f"{{{NS_HP}}}p"))


def _count_tables_cells(section_root: ET.Element) -> tuple[int, int]:
    tables = list(section_root.iter(f"{{{NS_HP}}}tbl"))
    cells = sum(sum(1 for _ in tbl.iter(f"{{{NS_HP}}}tc")) for tbl in tables)
    return len(tables), cells


def _count_objects(section_root: ET.Element) -> int:
    count = 0
    for tag in (f"{{{NS_HP}}}pic", f"{{{NS_HP}}}ole", f"{{{NS_HP}}}gso"):
        count += sum(1 for _ in section_root.iter(tag))
    return count


def _count_label_candidates(section_root: ET.Element) -> int:
    """표 안의 짧은 텍스트 셀(형식 라벨 후보) 수."""
    count = 0
    for tc in section_root.iter(f"{{{NS_HP}}}tc"):
        texts = [t.text or "" for t in tc.iter(f"{{{NS_HP}}}t") if t.text]
        joined = "".join(texts).strip()
        if 1 <= len(joined) <= 15:
            count += 1
    return count


def _has_pii_in_content(section_root: ET.Element) -> bool:
    all_text = " ".join(t.text for t in section_root.iter(f"{{{NS_HP}}}t") if t.text)
    return any(p.search(all_text) for p in _PII_PATTERNS)


def _parse_all_sections(
    zf: zipfile.ZipFile, section_files: list[str]
) -> tuple[int, int, int, int, int, bool, list[str]]:
    """섹션들을 파싱해 합산 카운트와 PII 발견 여부를 반환.

    (total_paragraphs, total_tables, total_cells, total_objects,
    total_labels, pii_found, parse_errors) 반환.
    """
    total_paragraphs = 0
    total_tables = 0
    total_cells = 0
    total_objects = 0
    total_labels = 0
    pii_found = False
    parse_errors: list[str] = []

    for sec_name in section_files:
        try:
            raw = zf.read(sec_name)
            root = ET.fromstring(raw)
        except ET.ParseError as exc:
            parse_errors.append(f"{sec_name}: XML parse error: {exc}")
            continue
        except (KeyError, zipfile.BadZipFile, OSError) as exc:
            parse_errors.append(f"{sec_name}: read error: {exc}")
            continue

        total_paragraphs += _count_paragraphs(root)
        t, c = _count_tables_cells(root)
        total_tables += t
        total_cells += c
        total_objects += _count_objects(root)
        total_labels += _count_label_candidates(root)
        if not pii_found:
            try:
                pii_found = _has_pii_in_content(root)
            except Exception as exc:  # ruff: ignore[blind-except] — fail-safe: 탐지 자체가
                # 실패하면 "PII 없음"이 아니라 "있을 수 있음"으로 간주해
                # 사람 검토로 보낸다(무음이면 PII 유출을 놓칠 수 있음).
                pii_found = True
                parse_errors.append(f"{sec_name}: pii_check_failed: {exc}")

    return (
        total_paragraphs,
        total_tables,
        total_cells,
        total_objects,
        total_labels,
        pii_found,
        parse_errors,
    )


def _classify_profile(
    total_paragraphs: int,
    total_tables: int,
    pii_found: bool,
    total_cells: int,
    has_parse_errors: bool,
) -> tuple[str, str]:
    """집계값으로 (status, blockedReason)을 정한다."""
    if has_parse_errors and total_paragraphs == 0 and total_tables == 0:
        return STATUS_UNSUPPORTED, "all sections failed to parse"

    if total_paragraphs == 0 and total_tables == 0:
        return STATUS_EMPTY, "no paragraphs and no tables"

    if pii_found:
        return STATUS_PII, "PII pattern detected in content"

    if total_cells > LARGE_THRESHOLD_CELLS or total_paragraphs > LARGE_THRESHOLD_PARAGRAPHS:
        return (
            STATUS_LARGE,
            f"large document: cells={total_cells}, paragraphs={total_paragraphs}",
        )

    return STATUS_READY, ""


def profile_one(path: Path) -> ProfileRecord:
    now = datetime.now(tz=UTC).isoformat()
    rec = ProfileRecord(
        fileHash=file_hash(path),
        maskedFileName=mask_filename(path),
        profiledAt=now,
    )
    try:
        rec.fileSize = path.stat().st_size
    except OSError as exc:
        rec.status = STATUS_UNKNOWN
        rec.blockedReason = f"stat failed: {exc}"
        return rec

    # ZIP open
    try:
        zf = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError) as exc:
        rec.status = STATUS_BROKEN_ZIP
        rec.blockedReason = str(exc)
        return rec

    with zf:
        names = zf.namelist()

        # required XML check
        has_hpf = "Contents/content.hpf" in names
        section_files = [n for n in names if re.match(r"Contents/section\d+\.xml$", n)]
        if not has_hpf or not section_files:
            rec.status = STATUS_MISSING_XML
            missing = []
            if not has_hpf:
                missing.append("Contents/content.hpf")
            if not section_files:
                missing.append("Contents/section*.xml")
            rec.blockedReason = f"missing: {', '.join(missing)}"
            return rec

        rec.sectionCount = len(section_files)

        (
            total_paragraphs,
            total_tables,
            total_cells,
            total_objects,
            total_labels,
            pii_found,
            parse_errors,
        ) = _parse_all_sections(zf, section_files)

        rec.paragraphCount = total_paragraphs
        rec.tableCount = total_tables
        rec.cellCount = total_cells
        rec.objectCount = total_objects
        rec.labelCandidateCount = total_labels

        if parse_errors:
            rec.warnings.extend(parse_errors[:5])

        rec.status, rec.blockedReason = _classify_profile(
            total_paragraphs, total_tables, pii_found, total_cells, bool(parse_errors)
        )
        return rec


# ---------------------------------------------------------------------------
# Batch profiling
# ---------------------------------------------------------------------------


def discover_files(
    input_dir: Path,
    pattern: str = "*.hwpx",
    limit: int = 0,
) -> list[Path]:
    files = [p for p in input_dir.rglob("*") if fnmatch.fnmatch(p.name, pattern) and p.is_file()]
    files.sort()
    if limit and limit > 0:
        files = files[:limit]
    return files


def profile_all(
    input_dir: Path,
    output_dir: Path,
    pattern: str = "*.hwpx",
    limit: int = 0,
    dry_run: bool = False,
    mask_pii: bool = True,
) -> dict[str, Any]:
    files = discover_files(input_dir, pattern, limit)

    records: list[ProfileRecord] = []
    seen_hashes: dict[str, str] = {}

    for path in files:
        rec = profile_one(path)
        # duplicate detection
        if rec.status == STATUS_READY and rec.fileHash in seen_hashes:
            rec.status = STATUS_DUPLICATE
            rec.blockedReason = f"duplicate of {seen_hashes[rec.fileHash]}"
        elif rec.fileHash and rec.status == STATUS_READY:
            seen_hashes[rec.fileHash] = rec.maskedFileName
        records.append(rec)

    summary = _build_summary(records, input_dir)

    if not dry_run:
        _write_reports(output_dir, records, summary)

    return summary


def _build_summary(records: list[ProfileRecord], input_dir: Path) -> dict[str, Any]:
    from collections import Counter

    status_counts: Counter = Counter(r.status for r in records)
    return {
        "total": len(records),
        "inputDirMasked": f"dir_{hashlib.sha256(str(input_dir.resolve()).encode()).hexdigest()[:12]}",
        STATUS_READY: status_counts.get(STATUS_READY, 0),
        STATUS_BROKEN_ZIP: status_counts.get(STATUS_BROKEN_ZIP, 0),
        STATUS_MISSING_XML: status_counts.get(STATUS_MISSING_XML, 0),
        STATUS_UNSUPPORTED: status_counts.get(STATUS_UNSUPPORTED, 0),
        STATUS_EMPTY: status_counts.get(STATUS_EMPTY, 0),
        STATUS_PII: status_counts.get(STATUS_PII, 0),
        STATUS_LARGE: status_counts.get(STATUS_LARGE, 0),
        STATUS_DUPLICATE: status_counts.get(STATUS_DUPLICATE, 0),
        STATUS_UNKNOWN: status_counts.get(STATUS_UNKNOWN, 0),
        "profiledAt": datetime.now(tz=UTC).isoformat(),
    }


def _build_markdown(summary: dict[str, Any], records: list[ProfileRecord]) -> str:
    lines = [
        "# HWPX Corpus Candidates Profiling Report",
        "",
        f"- Total scanned: {summary['total']}",
        f"- READY_FOR_CORPUS_INGEST: {summary.get(STATUS_READY, 0)}",
        f"- BROKEN_ZIP: {summary.get(STATUS_BROKEN_ZIP, 0)}",
        f"- MISSING_REQUIRED_XML: {summary.get(STATUS_MISSING_XML, 0)}",
        f"- UNSUPPORTED_STRUCTURE: {summary.get(STATUS_UNSUPPORTED, 0)}",
        f"- EMPTY_DOCUMENT: {summary.get(STATUS_EMPTY, 0)}",
        f"- PII_REVIEW_REQUIRED: {summary.get(STATUS_PII, 0)}",
        f"- LARGE_DOCUMENT_REVIEW_REQUIRED: {summary.get(STATUS_LARGE, 0)}",
        f"- DUPLICATE_CANDIDATE: {summary.get(STATUS_DUPLICATE, 0)}",
        f"- UNKNOWN_REVIEW_REQUIRED: {summary.get(STATUS_UNKNOWN, 0)}",
        f"- profiledAt: {summary.get('profiledAt', '')}",
        "",
    ]
    blocked = [r for r in records if r.status != STATUS_READY]
    if blocked:
        lines.append("## Blocked / Review Required")
        for r in blocked[:50]:
            lines.append(f"- [{r.status}] {r.maskedFileName}: {r.blockedReason}")
        lines.append("")
    return "\n".join(lines)


def _write_reports(
    output_dir: Path,
    records: list[ProfileRecord],
    summary: dict[str, Any],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    (output_dir / "profile_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    all_dicts = [r.to_dict() for r in records]
    (output_dir / "profile_candidates.json").write_text(
        json.dumps(
            [d for d in all_dicts if d["status"] == STATUS_READY],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (output_dir / "profile_blocked.json").write_text(
        json.dumps(
            [d for d in all_dicts if d["status"] != STATUS_READY],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    audit_entry = {
        "event": "PROFILING_PREFLIGHT_RUN",
        "summary": summary,
        "profiledAt": summary.get("profiledAt"),
    }
    (output_dir / "profile_audit.json").write_text(
        json.dumps(audit_entry, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    md = _build_markdown(summary, records)
    (output_dir / "profile_summary.md").write_text(md, encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="HWPX corpus candidate profiler (read-only)")
    p.add_argument("--input-dir", required=True, help="root directory to scan for HWPX files")
    p.add_argument("--output-dir", required=True, help="directory for report output")
    p.add_argument("--limit", type=int, default=0, help="max files to scan (0=no limit)")
    p.add_argument(
        "--dry-run", action="store_true", default=False, help="scan only, do not write output files"
    )
    p.add_argument(
        "--mask-pii",
        action="store_true",
        default=True,
        help="mask filenames and paths in output (default: on)",
    )
    p.add_argument("--no-mask-pii", dest="mask_pii", action="store_false")
    p.add_argument(
        "--include-pattern",
        default="*.hwpx",
        help="glob pattern for file discovery (default: *.hwpx)",
    )
    p.add_argument(
        "--json",
        dest="output_json",
        action="store_true",
        default=False,
        help="print summary JSON to stdout",
    )
    p.add_argument(
        "--markdown",
        dest="output_markdown",
        action="store_true",
        default=False,
        help="print summary markdown to stdout",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    summary = profile_all(
        input_dir=Path(args.input_dir),
        output_dir=Path(args.output_dir),
        pattern=args.include_pattern,
        limit=args.limit,
        dry_run=args.dry_run,
        mask_pii=args.mask_pii,
    )
    if args.output_json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    elif args.output_markdown:
        records: list[ProfileRecord] = []  # markdown from summary only
        print(_build_markdown(summary, records))
    else:
        ready = summary.get(STATUS_READY, 0)
        total = summary.get("total", 0)
        print(f"profiling complete: {ready}/{total} READY_FOR_CORPUS_INGEST")
    return 0


if __name__ == "__main__":
    sys.exit(main())
