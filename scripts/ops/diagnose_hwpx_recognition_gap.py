"""M1 — XML 인지 정확도 진단 batch.

corpus 문서를 parser_engine + B동 v2(xml_deep_structure_analyzer)로
정밀 진단해서 "왜 라벨 미인지인가"를 정량화한다.

원칙 (CLAUDE.md):
- read-only (writer 미호출, 원본 미수정)
- B동 진단 호출 (기존 자재만 호출, 신규 도구 작성 0)
- AI 미호출 (진단만 — §10 자동 입력 정책과 무관)
- 운영 corpus DB 직접 쓰기 금지 (R2)
"""

from __future__ import annotations

import json
import sqlite3
import sys
import time
import zipfile
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts/hwpx"))


def _read_section_xmls(hwpx_path: Path) -> list[str]:
    """HWPX 안의 Contents/section*.xml 추출."""
    out: list[str] = []
    try:
        with zipfile.ZipFile(str(hwpx_path)) as z:
            for name in z.namelist():
                low = name.lower()
                if low.startswith("contents/section") and low.endswith(".xml"):
                    try:
                        out.append(z.read(name).decode("utf-8", "ignore"))
                    except Exception:  # ruff: ignore[blind-except]
                        pass
    except Exception:  # ruff: ignore[blind-except]
        pass
    return out


def _paragraph_xml_chunks(section_xml: str) -> list[str]:
    """간단 paragraph 분할 — <hp:p ...> ~ </hp:p> 또는 <p ...> ~ </p>."""
    import re

    chunks: list[str] = []
    for pat in (r"<hp:p[\s>][\s\S]*?</hp:p>", r"<p[\s>][\s\S]*?</p>"):
        chunks.extend(re.findall(pat, section_xml))
    return chunks[:200]  # 한 문서당 진단 paragraph 상한


def _cell_xml_chunks(section_xml: str) -> list[str]:
    import re

    return re.findall(r"<hp:tc[\s>][\s\S]*?</hp:tc>", section_xml)[:200]


def _build_parser_stats(result) -> dict[str, int]:
    return {
        "sectionCount": len(result.sections or []),
        "tableCount": len(result.tables or []),
        "blockCount": len(result.blocks or []),
        "objectCount": len(result.objects or []),
        "scheduleCount": len(result.schedules or []),
        "slotCount": len(result.inputSlotCandidates or []),
        "binDataCount": len(result.binData or []),
        "warningCount": len(result.warnings or []),
        "errorCount": len(result.errors or []),
    }


def _record_flag(flag_counts: Counter, severity_counts: Counter, f: dict | None) -> int:
    if not f:
        return 0
    flag_counts[f["reason_code"]] += 1
    severity_counts[f["severity"]] += 1
    return 1


def _scan_section_diagnostics(section_xmls: list[str], an) -> tuple[Counter, Counter, int]:
    flag_counts: Counter = Counter()
    severity_counts: Counter = Counter()
    diag_total = 0
    for sec_xml in section_xmls:
        # paragraph 단위 — run boundary + style resolution
        for p_xml in _paragraph_xml_chunks(sec_xml):
            for fn in (an.analyze_run_boundary, an.analyze_style_resolution):
                diag_total += _record_flag(flag_counts, severity_counts, fn(p_xml))
        # cell 단위
        for c_xml in _cell_xml_chunks(sec_xml):
            for fn in (an.analyze_cell_internal_paragraph, an.analyze_merged_cell_geometry):
                diag_total += _record_flag(flag_counts, severity_counts, fn(c_xml))
        # element 단위 — section 전체
        for fn in (an.analyze_checkbox_or_shape, an.analyze_object_anchor):
            diag_total += _record_flag(flag_counts, severity_counts, fn(sec_xml))
    return flag_counts, severity_counts, diag_total


def _classify_recognition(parser_stats: dict[str, int]) -> str:
    if parser_stats["slotCount"] != 0:
        return "HAS_LABELS"
    if parser_stats["tableCount"] == 0:
        return "NO_TABLE"
    if parser_stats["objectCount"] > 0:
        return "OBJECT_HEAVY"
    if parser_stats["scheduleCount"] > 0:
        return "SCHEDULE_ONLY"
    if parser_stats["blockCount"] == 0:
        return "EMPTY_OR_BROKEN"
    return "TABLE_BUT_NO_SLOT"


def diagnose_one(file_path: Path) -> dict:
    """단일 문서 진단 — parser_engine + B동 v2 통합 호출."""
    from scripts.hwpx.parser.parser_engine import parse_hwpx_v2
    from scripts.hwpx.recognition_corpus import (
        xml_deep_structure_analyzer as an,
    )

    rec_start = time.time()
    try:
        result = parse_hwpx_v2(file_path)
    except Exception as e:  # ruff: ignore[blind-except]
        return {"status": "PARSE_ERROR", "error": str(e)[:200]}
    rec_ms = int((time.time() - rec_start) * 1000)

    # parser-level 통계
    parser_stats = _build_parser_stats(result)

    # B동 진단 — section XML 단위
    diag_start = time.time()
    section_xmls = _read_section_xmls(file_path)
    flag_counts, severity_counts, diag_total = _scan_section_diagnostics(section_xmls, an)
    diag_ms = int((time.time() - diag_start) * 1000)

    # 라벨 미인지 분류
    recognition_class = _classify_recognition(parser_stats)

    return {
        "status": "OK",
        "recognitionMs": rec_ms,
        "diagnoseMs": diag_ms,
        "parserStats": parser_stats,
        "recognitionClass": recognition_class,
        "diagFlags": dict(flag_counts),
        "diagSeverity": dict(severity_counts),
        "diagTotal": diag_total,
        "sectionXmlCount": len(section_xmls),
    }


def run_batch(limit: int, only_form: bool, only_no_label: bool, report_jsonl: Path) -> dict:
    corpus_path = PROJECT_ROOT / "data/recognition_corpus/corpus.sqlite3"
    conn = sqlite3.connect(str(corpus_path))
    if only_form:
        rows = conn.execute(
            "SELECT d.document_id, d.source_path "
            "FROM hwpx_documents d "
            "JOIN document_classifications c "
            "  ON c.document_id = d.document_id "
            "WHERE d.inventory_status='FOUND' "
            "  AND c.document_type='fillable_form' "
            "ORDER BY d.first_seen_at LIMIT ?",
            (limit,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT document_id, source_path FROM hwpx_documents "
            "WHERE inventory_status='FOUND' "
            "ORDER BY first_seen_at LIMIT ?",
            (limit,),
        ).fetchall()
    conn.close()

    report_jsonl.parent.mkdir(parents=True, exist_ok=True)

    stats = {
        "total": 0,
        "byClass": Counter(),
        "byFlag": Counter(),
        "bySeverity": Counter(),
        "totalFlags": 0,
        "elapsedSec": 0.0,
        "parseErrors": 0,
    }

    start = time.time()
    with report_jsonl.open("w", encoding="utf-8") as f:
        for i, (doc_id, source_path) in enumerate(rows):
            file_path = PROJECT_ROOT / source_path
            if not file_path.is_file():
                continue
            stats["total"] += 1
            res = diagnose_one(file_path)
            if res.get("status") == "PARSE_ERROR":
                stats["parseErrors"] += 1
                continue
            if only_no_label and res["parserStats"]["slotCount"] > 0:
                # label 있는 문서 skip (no_label만 분석 모드)
                continue
            stats["byClass"][res["recognitionClass"]] += 1
            for code, count in res["diagFlags"].items():
                stats["byFlag"][code] += count
            for sev, count in res["diagSeverity"].items():
                stats["bySeverity"][sev] += count
            stats["totalFlags"] += res["diagTotal"]

            rec = {"idx": i, "docId": doc_id, "src": source_path, **res}
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
    stats["elapsedSec"] = round(time.time() - start, 2)

    stats["byClass"] = dict(stats["byClass"])
    stats["byFlag"] = dict(stats["byFlag"])
    stats["bySeverity"] = dict(stats["bySeverity"])
    return {"summary": stats, "reportJsonl": str(report_jsonl)}


def main():
    limit = 1000
    only_form = "--form" in sys.argv
    only_no_label = "--no-label-only" in sys.argv
    for a in sys.argv[1:]:
        if a.isdigit():
            limit = int(a)
            break

    suffix = "_form" if only_form else ""
    out = PROJECT_ROOT / f"data/drafts/hwpx_diagnose_report{suffix}.jsonl"
    report = run_batch(limit, only_form, only_no_label, out)
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
