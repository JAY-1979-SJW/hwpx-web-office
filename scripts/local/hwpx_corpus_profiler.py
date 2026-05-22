"""
HWPX-CORPUS-PROFILER-LOCAL-INVENTORY-01

로컬 HWPX 문서를 read-only로 전수 조사하여 Reader/Parser/Schedule Classifier 개선용
자재 데이터를 만든다.

원칙:
- 원본 수정 없음 (open만 사용)
- write_package / apply_edit_plan / repair_for_server 호출 없음
- 실패 파일이 있어도 전체 스캔은 중단되지 않음
- 절대경로는 pathHash로 익명화, relativePath는 root 기준 상대값만 노출
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
import traceback
import unicodedata
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET


NS_HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
NS_HH = "http://www.hancom.co.kr/hwpml/2011/head"
NS_HS = "http://www.hancom.co.kr/hwpml/2011/section"
NS_OPF = "http://www.idpf.org/2007/opf/"
NS_OCF = "urn:oasis:names:tc:opendocument:xmlns:container"


SCHEDULE_FILENAME_KEYWORDS = ("공정표", "예정공정", "일정표", "공정관리", "schedule", "gantt")
SCHEDULE_HEADER_KEYWORDS = (
    "공종", "작업명", "공사명", "시작일", "착수일", "종료일", "완료일", "준공일",
    "기간", "공기", "진행률", "진도율", "예정", "실적", "task", "start", "end", "duration",
)
DATE_HEADER_PATTERNS = [
    re.compile(r"^\d{4}[-./]\d{1,2}[-./]\d{1,2}"),
    re.compile(r"^\d{4}[-./]\d{1,2}$"),   # 연-월 형식 (2026-01)
    re.compile(r"^\d{1,2}[-./]\d{1,2}"),
    re.compile(r"^\d{1,2}월"),
    re.compile(r"^\d{1,2}주차?"),
    re.compile(r"^Q[1-4]"),
    re.compile(r"^\d{4}년"),
]
NUMERIC_HEADER_PATTERNS = [
    re.compile(r"^[+-]?\d+(?:\.\d+)?$"),
    re.compile(r"^\d+%$"),
]

# 헤더 사전 추정용 필드 매핑 (정규화된 헤더 텍스트 일부 매칭 기준)
FIELD_HINTS: list[tuple[str, tuple[str, ...]]] = [
    ("projectName",   ("공사명", "사업명", "프로젝트명")),
    ("siteName",      ("현장명", "현장",)),
    ("contractorName",("시공사", "도급사", "수급인", "업체명", "회사명", "상호")),
    ("reportDate",    ("작성일", "보고일", "제출일")),
    ("receiptNumber", ("접수번호", "접수번", "문서번호", "접수")),
    ("number",        ("번호",)),
    ("trade",         ("공종", "공정", "trade")),
    ("taskName",      ("작업명", "task", "내용", "항목")),
    ("startDate",     ("시작일", "착수일", "착공일", "start")),
    ("endDate",       ("종료일", "완료일", "준공일", "end")),
    ("durationDays",  ("기간", "공기", "duration")),
    ("responsiblePerson",("담당자", "책임자", "성명", "지정자")),
    ("progressRate",  ("진행률", "진도율", "달성률", "progress")),
    ("materialStatus",("자재", "재료", "material")),
    ("inspectionStatus",("검측", "검사", "inspection")),
    ("remarks",       ("비고", "참고", "remark", "note")),
    ("quantity",      ("수량", "량")),
    ("unit",          ("단위", "unit")),
    ("spec",          ("규격", "사양", "spec")),
    ("amount",        ("금액", "단가", "amount", "price")),
    ("gasName",       ("가스명", "가스종류", "gas")),
    ("pressure",      ("압력", "설계압력", "최고허용압력")),
    ("material",      ("재질", "배관재질")),
    ("nominalDiameter",("호칭지름", "호칭경", "관경")),
    ("length",        ("연장", "길이", "length")),
    ("location",      ("위치", "장소", "구간")),
]

# 양식 표 식별용 라벨 키워드 (form_table / metadata_table)
FORM_LABEL_KEYWORDS = (
    "공사명", "현장명", "사업명", "시공사", "감리자",
    "접수번호", "접수일", "발신", "수신", "문서번호", "보고일",
    "작성자", "작성일", "승인자", "검토자", "제출일", "수신처",
)
METADATA_LABEL_KEYWORDS = (
    "공사명", "현장명", "사업명", "접수번호", "작성일", "신청인",
    "시공사", "발주처", "주소", "전화번호", "위치", "착공일", "준공일",
)
STAMP_KEYWORDS = ("직인", "서명", "날인", "결재", "승인", "인장", "검토", "확인인")
PAGE_MARKER_RE = re.compile(
    r"[(\[]\s*\d+\s*쪽\s*(중\s*제\s*\d+\s*쪽)?\s*[)\]]"
    r"|제\s*\d+\s*쪽"
    r"|\d+\s*/\s*\d+\s*쪽"
)
LEGAL_FORM_KEYWORDS = ("별지", "시행규칙", "시행령", "[별표", "서식]", "법률 시행")


@dataclass
class CorpusContext:
    root: Path
    out_dir: Path
    anonymize: bool
    max_files: int
    fail_fast: bool
    include_hidden: bool

    file_records: list[dict[str, Any]] = field(default_factory=list)
    package_records: list[dict[str, Any]] = field(default_factory=list)
    parse_records: list[dict[str, Any]] = field(default_factory=list)
    table_records: list[dict[str, Any]] = field(default_factory=list)
    schedule_records: list[dict[str, Any]] = field(default_factory=list)
    failure_records: list[dict[str, Any]] = field(default_factory=list)
    fixture_records: list[dict[str, Any]] = field(default_factory=list)
    header_counter: dict[str, Counter] = field(default_factory=lambda: defaultdict(Counter))
    header_files: dict[str, set] = field(default_factory=lambda: defaultdict(set))
    header_tables: dict[str, set] = field(default_factory=lambda: defaultdict(set))
    header_col_positions: dict[str, Counter] = field(default_factory=lambda: defaultdict(Counter))


# ── ID/path helpers ────────────────────────────────────────────────────────────

def make_file_id(path_hash: str, index: int) -> str:
    return f"f{index:05d}_{path_hash[:10]}"


def path_hash(path: Path) -> str:
    raw = str(path.resolve()).encode("utf-8", errors="replace")
    return hashlib.sha256(raw).hexdigest()


def rel_path(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve())).replace("\\", "/")
    except ValueError:
        return path.name


# ── inventory / discovery ─────────────────────────────────────────────────────

def discover_hwpx(root: Path, include_hidden: bool, max_files: int) -> list[Path]:
    if not root.exists():
        return []
    files = []
    for p in root.rglob("*.hwpx"):
        try:
            if not include_hidden and any(part.startswith(".") for part in p.parts):
                continue
            if not p.is_file():
                continue
        except OSError:
            continue
        files.append(p)
    files.sort()
    if max_files and max_files > 0:
        files = files[:max_files]
    return files


# ── package structure inspection ───────────────────────────────────────────────

def inspect_package(zf: zipfile.ZipFile) -> dict[str, Any]:
    names = zf.namelist()
    has_mimetype = "mimetype" in names
    mt_value = ""
    mt_compress = -1
    if has_mimetype:
        try:
            mt_value = zf.read("mimetype").decode("ascii", errors="replace").strip()
            mt_compress = zf.getinfo("mimetype").compress_type
        except Exception:
            pass
    has_content_hpf = "Contents/content.hpf" in names
    has_container = "META-INF/container.xml" in names
    has_header = "Contents/header.xml" in names
    section_files = [n for n in names if re.match(r"Contents/section\d+\.xml$", n)]

    manifest_count = 0
    spine_count = 0
    char_pr_count = 0
    para_pr_count = 0
    border_fill_count = 0
    xml_decode_ok = True
    warnings: list[str] = []

    if has_content_hpf:
        try:
            opf = ET.fromstring(zf.read("Contents/content.hpf"))
            manifest_count = len(opf.findall(f".//{{{NS_OPF}}}item"))
            spine_count = len(opf.findall(f".//{{{NS_OPF}}}itemref"))
        except Exception as exc:
            warnings.append(f"content.hpf parse failed: {exc}")
            xml_decode_ok = False

    if has_header:
        try:
            header = ET.fromstring(zf.read("Contents/header.xml"))
            char_pr_count = sum(1 for _ in header.iter(f"{{{NS_HH}}}charPr"))
            para_pr_count = sum(1 for _ in header.iter(f"{{{NS_HH}}}paraPr"))
            border_fill_count = sum(1 for _ in header.iter(f"{{{NS_HH}}}borderFill"))
        except Exception as exc:
            warnings.append(f"header.xml parse failed: {exc}")
            xml_decode_ok = False

    for n in names:
        if n.endswith((".xml", ".hpf", ".rdf")):
            try:
                zf.read(n).decode("utf-8")
            except UnicodeDecodeError:
                warnings.append(f"non-utf8 entry: {n}")
                xml_decode_ok = False

    if has_mimetype and mt_compress != 0:
        warnings.append(f"mimetype not ZIP_STORED (compress_type={mt_compress})")
    if mt_value and mt_value not in ("application/hwp+zip", "application/owpml"):
        warnings.append(f"unexpected mimetype: {mt_value!r}")

    return {
        "entryCount": len(names),
        "hasMimetype": has_mimetype,
        "mimetypeValue": mt_value,
        "mimetypeCompressType": mt_compress,
        "hasContentHpf": has_content_hpf,
        "hasContainerXml": has_container,
        "hasHeaderXml": has_header,
        "sectionFileCount": len(section_files),
        "sectionFiles": section_files,
        "manifestItemCount": manifest_count,
        "spineItemrefCount": spine_count,
        "headerCharPrCount": char_pr_count,
        "headerParaPrCount": para_pr_count,
        "headerBorderFillCount": border_fill_count,
        "xmlDecodeOk": xml_decode_ok,
        "warnings": warnings,
    }


# ── parse / tables / scheduling ───────────────────────────────────────────────

def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def normalize_header(text: str) -> str:
    """헤더 텍스트 정규화: NFKC, 공백 압축, 한글 사이 공백 제거."""
    if not text:
        return ""
    t = unicodedata.normalize("NFKC", text)
    # 괄호·콜론·줄바꿈 등 실무 문서 잡음 제거
    t = re.sub(r"[\r\n\t]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    # 한글(가-힣) 사이에 끼인 공백 제거: "공 사 명" → "공사명"
    # 단, 영문·숫자·단위가 섞인 경우는 건드리지 않음
    t = re.sub(r"(?<=[가-힣]) (?=[가-힣])", "", t)
    return t


def guess_field(normalized: str) -> tuple[str, float]:
    """헤더 텍스트에서 의미 필드 추정. (필드명, 신뢰도)."""
    if not normalized:
        return "unknown", 0.0
    lowered = normalized.lower()
    for field_name, hints in FIELD_HINTS:
        for h in hints:
            if h in normalized or h.lower() in lowered:
                # 정확히 헤더가 hint 자체이면 신뢰도 0.95, 포함이면 0.75
                if normalized == h or lowered == h.lower():
                    return field_name, 0.95
                return field_name, 0.75
    return "unknown", 0.0


def is_date_like(text: str) -> bool:
    if not text:
        return False
    norm = normalize_header(text)
    return any(p.search(norm) for p in DATE_HEADER_PATTERNS)


def is_numeric_like(text: str) -> bool:
    if not text:
        return False
    norm = normalize_header(text).replace(",", "")
    return any(p.match(norm) for p in NUMERIC_HEADER_PATTERNS)


def parse_section_xml(raw: bytes) -> ET.Element | None:
    try:
        return ET.fromstring(raw)
    except ET.ParseError:
        return None


def collect_paragraphs(section_root: ET.Element) -> list[str]:
    paragraphs = []
    for p in section_root.iter(f"{{{NS_HP}}}p"):
        texts = [t.text or "" for t in p.iter(f"{{{NS_HP}}}t") if t.text]
        if texts:
            paragraphs.append("".join(texts))
    return paragraphs


def collect_tables(section_root: ET.Element) -> list[ET.Element]:
    return list(section_root.iter(f"{{{NS_HP}}}tbl"))


def table_rows_cells(table: ET.Element) -> list[list[ET.Element]]:
    rows = [c for c in table if c.tag == f"{{{NS_HP}}}tr"]
    return [[c for c in row if c.tag == f"{{{NS_HP}}}tc"] for row in rows]


def cell_text(cell: ET.Element) -> str:
    parts = []
    for elem in cell.iter():
        if elem.tag == f"{{{NS_HP}}}tbl":  # nested table: skip subtree text
            continue
        if elem.tag == f"{{{NS_HP}}}t" and elem.text:
            parts.append(elem.text)
    return "".join(parts)


def cell_has_nested_table(cell: ET.Element) -> bool:
    return any(elem.tag == f"{{{NS_HP}}}tbl" for elem in cell.iter())


def cell_span(cell: ET.Element) -> tuple[int, int]:
    """colspan, rowspan from <hp:cellSpan> direct child."""
    for child in cell:
        if child.tag == f"{{{NS_HP}}}cellSpan":
            try:
                return int(child.attrib.get("colSpan", "1")), int(child.attrib.get("rowSpan", "1"))
            except ValueError:
                return 1, 1
    return 1, 1


def detect_header_rows(table_grid: list[list[ET.Element]]) -> list[int]:
    """첫 row(s)이 header인지 추정. 병합 제목행 + 실제 헤더행 패턴도 감지."""
    candidates = []
    check_up_to = min(3, len(table_grid))
    for i in range(check_up_to):
        row = table_grid[i]
        if not row:
            continue
        texts = [normalize_header(cell_text(c)) for c in row]
        non_empty = [t for t in texts if t]
        if not non_empty:
            continue
        avg_len = sum(len(t) for t in non_empty) / len(non_empty)
        col_count = len(row)

        # 첫 행이 병합된 제목행(1~2개 셀, 텍스트 길다)이면 건너뜀
        if i == 0 and len(non_empty) <= 2 and avg_len > 15:
            continue
        # 평균 12자 이내 + 비어있지 않은 셀 50% 이상 → 헤더로 추정
        if avg_len <= 14 and len(non_empty) >= max(1, col_count // 2):
            candidates.append(i)
            break  # 첫 유효 헤더행만
    return candidates


def _collect_all_cell_texts(grid: list[list[ET.Element]]) -> list[str]:
    """모든 셀의 정규화 텍스트 (중첩표 포함 원문, 빈 셀 제외)."""
    texts = []
    for row in grid:
        for cell in row:
            t = normalize_header(cell_text(cell))
            if t:
                texts.append(t)
    return texts


def _compute_table_scores(
    grid: list[list[ET.Element]],
) -> dict[str, float]:
    """표 분류에 사용할 점수 벡터를 반환."""
    row_count = len(grid)
    col_count = max((len(r) for r in grid), default=0)
    total_cells = sum(len(r) for r in grid)
    if total_cells == 0:
        return {
            "text_cell_ratio": 0.0, "merge_ratio": 0.0, "page_marker_score": 0.0,
            "stamp_score": 0.0, "label_value_pair_score": 0.0, "metadata_score": 0.0,
            "legal_form_score": 0.0, "approval_stamp_score": 0.0,
            "nested_table_count": 0, "max_col_span": 1, "max_row_span": 1,
            "row_count": row_count, "col_count": col_count, "total_cells": 0,
        }

    text_cells = 0
    merged_cells = 0
    nested_table_count = 0
    max_col_span = 1
    max_row_span = 1
    page_marker_hits = 0
    stamp_hits = 0
    metadata_hits = 0
    legal_form_hits = 0
    all_texts: list[str] = []

    for row in grid:
        for cell in row:
            t = normalize_header(cell_text(cell))
            raw_t = cell_text(cell)
            if t:
                text_cells += 1
                all_texts.append(t)
            cs, rs = cell_span(cell)
            if cs > 1 or rs > 1:
                merged_cells += 1
            max_col_span = max(max_col_span, cs)
            max_row_span = max(max_row_span, rs)
            if cell_has_nested_table(cell):
                nested_table_count += 1
            if raw_t and PAGE_MARKER_RE.search(raw_t):
                page_marker_hits += 1
            if t and any(kw in t for kw in STAMP_KEYWORDS):
                stamp_hits += 1
            if t and any(kw in t for kw in METADATA_LABEL_KEYWORDS):
                metadata_hits += 1
            if raw_t and any(kw in raw_t for kw in LEGAL_FORM_KEYWORDS):
                legal_form_hits += 1

    # label-value-pair score: 2-col 표에서 왼쪽 셀이 짧은 라벨인 비율
    lvp_score = 0.0
    if col_count == 2 and row_count >= 2:
        label_rows = 0
        for row in grid:
            if len(row) >= 1:
                lt = normalize_header(cell_text(row[0]))
                if lt and len(lt) <= 12:
                    label_rows += 1
        lvp_score = label_rows / row_count if row_count else 0.0

    return {
        "text_cell_ratio": text_cells / total_cells,
        "merge_ratio": merged_cells / total_cells,
        "page_marker_score": page_marker_hits / total_cells,
        "stamp_score": stamp_hits / total_cells,
        "label_value_pair_score": lvp_score,
        "metadata_score": metadata_hits / total_cells,
        "legal_form_score": legal_form_hits / total_cells,
        "approval_stamp_score": stamp_hits / total_cells,
        "nested_table_count": nested_table_count,
        "max_col_span": max_col_span,
        "max_row_span": max_row_span,
        "row_count": row_count,
        "col_count": col_count,
        "total_cells": total_cells,
    }


def classify_table_layout(
    grid: list[list[ET.Element]],
    header_texts: list[str],
    paragraphs_around: list[str],
) -> tuple[str, float, list[str]]:
    """layoutGuess + confidence + classificationEvidence."""
    if not grid:
        return "unknown", 0.0, ["empty grid"]

    scores = _compute_table_scores(grid)
    row_count = scores["row_count"]
    col_count = scores["col_count"]
    total_cells = scores["total_cells"]

    norm_headers = [normalize_header(t) for t in header_texts]
    header_text_blob = " ".join(norm_headers)
    schedule_hits = sum(1 for kw in SCHEDULE_HEADER_KEYWORDS if kw in header_text_blob)
    date_header_cols = sum(1 for t in norm_headers if is_date_like(t))

    evidence: list[str] = []

    # ── 1. page_marker_table ─────────────────────────────────────────────────
    if scores["page_marker_score"] > 0:
        evidence.append(f"page marker pattern in cells (score={scores['page_marker_score']:.2f})")
        return "page_marker_table", min(0.7 + scores["page_marker_score"], 0.95), evidence

    # ── 2. stamp_or_approval_table ───────────────────────────────────────────
    if scores["stamp_score"] >= 0.15 or (
        scores["stamp_score"] > 0 and total_cells <= 12
    ):
        conf = min(0.6 + scores["stamp_score"] * 2, 0.92)
        evidence.append(f"stamp/approval keywords (score={scores['stamp_score']:.2f})")
        return "stamp_or_approval_table", conf, evidence

    # ── 3. layout_noise: 단일 셀 또는 텍스트 덩어리 ─────────────────────────
    if total_cells == 1:
        evidence.append("single-cell table")
        return "layout_noise", 0.7, evidence

    # ── 4. gantt_like_table ──────────────────────────────────────────────────
    if date_header_cols >= 3 and col_count >= 5:
        conf = min(0.6 + 0.05 * date_header_cols, 0.95)
        evidence.append(f"date header cols={date_header_cols}, col_count={col_count}")
        return "gantt_like_table", conf, evidence

    # ── 5. schedule variants ─────────────────────────────────────────────────
    if schedule_hits >= 3 and row_count >= 2:
        layout = "vertical_schedule" if row_count > col_count else "horizontal_schedule"
        evidence.append(f"schedule_hits={schedule_hits}, row={row_count}, col={col_count}")
        return layout, 0.75, evidence
    if date_header_cols >= 1 and schedule_hits >= 1:
        evidence.append(f"date_cols={date_header_cols}, schedule_hits={schedule_hits}")
        return "horizontal_schedule", 0.65, evidence

    # ── 6. metadata_table: 문서 기본정보 표 ─────────────────────────────────
    if scores["metadata_score"] >= 0.15:
        evidence.append(f"metadata labels (score={scores['metadata_score']:.2f})")
        return "metadata_table", min(0.55 + scores["metadata_score"], 0.90), evidence

    # ── 7. form_table: 라벨/값 반복 양식 ────────────────────────────────────
    form_score = 0
    for row in grid:
        for c in row:
            t = normalize_header(cell_text(c))
            if any(kw in t for kw in FORM_LABEL_KEYWORDS):
                form_score += 1
    if form_score >= 2 and row_count <= 8:
        conf = min(0.6 + 0.05 * form_score, 0.92)
        evidence.append(f"form label hits={form_score}, row_count={row_count}")
        return "form_table", conf, evidence

    # ── 8. legal_complex_table: 법령서식 복합표 ─────────────────────────────
    if scores["legal_form_score"] > 0 and scores["merge_ratio"] >= 0.4:
        evidence.append(
            f"legal form keywords (score={scores['legal_form_score']:.2f}), "
            f"merge_ratio={scores['merge_ratio']:.2f}"
        )
        return "legal_complex_table", 0.60, evidence

    # ── 9. nested_container_table ────────────────────────────────────────────
    if scores["nested_table_count"] >= 1:
        evidence.append(f"nested_tables={scores['nested_table_count']}")
        return "nested_container_table", 0.65, evidence

    # ── 10. vertical_table / horizontal_table ────────────────────────────────
    if col_count <= 2 and row_count >= 4:
        evidence.append(f"col_count={col_count}, row_count={row_count}")
        return "vertical_table", 0.50, evidence
    if row_count <= 2 and col_count >= 3:
        evidence.append(f"row_count={row_count}, col_count={col_count}")
        return "horizontal_table", 0.50, evidence

    # ── 11. label-value-pair vertical_table ─────────────────────────────────
    if scores["label_value_pair_score"] >= 0.6 and row_count >= 3:
        evidence.append(f"label-value pair score={scores['label_value_pair_score']:.2f}")
        return "vertical_table", 0.55, evidence

    evidence.append(
        f"no pattern matched: row={row_count} col={col_count} "
        f"merge={scores['merge_ratio']:.2f} text={scores['text_cell_ratio']:.2f}"
    )
    return "unknown", 0.3, evidence


def detect_schedule_candidate(
    file_id: str,
    file_name: str,
    paragraphs: list[str],
    tables_info: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    candidates = []
    name_hit = any(kw in file_name for kw in SCHEDULE_FILENAME_KEYWORDS)
    body_blob = " ".join(paragraphs[:50])
    body_hit = any(kw in body_blob for kw in SCHEDULE_FILENAME_KEYWORDS)
    for t in tables_info:
        layout = t.get("layoutGuess", "unknown")
        if layout in ("gantt_like_table", "vertical_schedule", "horizontal_schedule", "calendar_like_table"):
            cand_type = {
                "gantt_like_table": "gantt_bar_schedule",
                "vertical_schedule": "vertical_schedule",
                "horizontal_schedule": "horizontal_schedule",
                "calendar_like_table": "calendar_schedule",
            }[layout]
            conf = float(t.get("confidence", 0.0))
            if name_hit:
                conf = min(conf + 0.1, 1.0)
            if body_hit:
                conf = min(conf + 0.05, 1.0)
            gate = "PARSE_ONLY"
            if conf >= 0.85:
                gate = "AUTO_EDIT_PLAN_ALLOWED"
            elif conf >= 0.60:
                gate = "REVIEW_REQUIRED"
            evidence = []
            if name_hit:
                evidence.append("filename_keyword")
            if body_hit:
                evidence.append("body_keyword")
            evidence.append(f"layout={layout}")
            candidates.append({
                "fileId": file_id,
                "candidateType": cand_type,
                "confidence": round(conf, 3),
                "evidence": evidence,
                "tableId": t.get("tableId"),
                "timeAxisCandidate": t.get("dateHeaderCandidates", []),
                "taskColumnCandidate": t.get("headerTexts", [])[:1],
                "inputSlotCandidateCount": t.get("emptyCellCount", 0),
                "autoEditGate": gate,
            })
    return candidates


# ── per-file processing ────────────────────────────────────────────────────────

def process_file(ctx: CorpusContext, index: int, path: Path) -> None:
    ph = path_hash(path)
    file_id = make_file_id(ph, index)
    rel = rel_path(path, ctx.root)
    try:
        stat = path.stat()
        size = stat.st_size
        mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
    except OSError as exc:
        ctx.failure_records.append({
            "fileId": file_id, "stage": "FILE_DISCOVERY",
            "errorType": exc.__class__.__name__, "errorMessage": str(exc),
            "tracebackShort": "", "recoverable": False, "suggestedFix": "check file access",
            "fixturePriority": "low",
        })
        return

    record = {
        "fileId": file_id,
        "relativePath": rel,
        "pathHash": ph,
        "fileName": path.name,
        "sizeBytes": size,
        "modifiedTime": mtime,
        "zipOpenOk": False,
        "entryCount": 0,
        "hasMimetype": False,
        "mimetypeValue": "",
        "mimetypeCompressType": -1,
        "hasContentHpf": False,
        "hasContainerXml": False,
        "hasHeaderXml": False,
        "sectionFileCount": 0,
        "status": "UNKNOWN",
        "errorMessage": "",
    }
    ctx.file_records.append(record)

    try:
        with zipfile.ZipFile(path) as zf:
            record["zipOpenOk"] = True
            pkg = inspect_package(zf)
            record["entryCount"] = pkg["entryCount"]
            record["hasMimetype"] = pkg["hasMimetype"]
            record["mimetypeValue"] = pkg["mimetypeValue"]
            record["mimetypeCompressType"] = pkg["mimetypeCompressType"]
            record["hasContentHpf"] = pkg["hasContentHpf"]
            record["hasContainerXml"] = pkg["hasContainerXml"]
            record["hasHeaderXml"] = pkg["hasHeaderXml"]
            record["sectionFileCount"] = pkg["sectionFileCount"]
            ctx.package_records.append({"fileId": file_id, **{k: v for k, v in pkg.items() if k != "sectionFiles"}})

            # parse summary
            try:
                _parse_and_catalog(ctx, file_id, path.name, zf, pkg)
                record["status"] = "PASS"
            except Exception as exc:
                tb = traceback.format_exc(limit=3)
                ctx.failure_records.append({
                    "fileId": file_id, "stage": "SECTION_PARSE",
                    "errorType": exc.__class__.__name__, "errorMessage": str(exc),
                    "tracebackShort": tb[-400:], "recoverable": True,
                    "suggestedFix": "harden parse_summary path", "fixturePriority": "medium",
                })
                record["status"] = "PARTIAL"
                record["errorMessage"] = f"parse: {exc}"
    except zipfile.BadZipFile as exc:
        record["status"] = "FAIL"
        record["errorMessage"] = f"BadZipFile: {exc}"
        ctx.failure_records.append({
            "fileId": file_id, "stage": "ZIP_OPEN",
            "errorType": "BadZipFile", "errorMessage": str(exc),
            "tracebackShort": "", "recoverable": False, "suggestedFix": "re-export from Hancom",
            "fixturePriority": "high",
        })
    except Exception as exc:
        record["status"] = "FAIL"
        record["errorMessage"] = str(exc)
        tb = traceback.format_exc(limit=3)
        ctx.failure_records.append({
            "fileId": file_id, "stage": "PACKAGE_STRUCTURE",
            "errorType": exc.__class__.__name__, "errorMessage": str(exc),
            "tracebackShort": tb[-400:], "recoverable": False,
            "suggestedFix": "check package structure", "fixturePriority": "medium",
        })
        if ctx.fail_fast:
            raise


def _parse_and_catalog(
    ctx: CorpusContext,
    file_id: str,
    file_name: str,
    zf: zipfile.ZipFile,
    pkg: dict[str, Any],
) -> None:
    section_entries = pkg.get("sectionFiles", []) or []
    paragraph_count = 0
    table_count = 0
    image_count = 0
    drawing_count = 0
    total_cells = 0
    merged_cells = 0
    empty_cells = 0
    max_rows = 0
    max_cols = 0
    has_schedule_keyword = False
    has_date_axis = False
    has_gantt = False
    parser_warnings: list[str] = []
    title_candidate = ""
    tables_for_schedule: list[dict[str, Any]] = []
    paragraphs_for_schedule: list[str] = []

    for sec_idx, sec_name in enumerate(section_entries):
        try:
            raw = zf.read(sec_name)
        except Exception as exc:
            parser_warnings.append(f"section read failed {sec_name}: {exc}")
            continue
        root = parse_section_xml(raw)
        if root is None:
            parser_warnings.append(f"section parse failed {sec_name}")
            ctx.failure_records.append({
                "fileId": file_id, "stage": "XML_DECODE",
                "errorType": "ParseError", "errorMessage": f"section {sec_name}",
                "tracebackShort": "", "recoverable": True,
                "suggestedFix": "investigate non-utf8 or malformed XML",
                "fixturePriority": "high",
            })
            continue

        paragraphs = collect_paragraphs(root)
        paragraph_count += len(paragraphs)
        if not title_candidate and paragraphs:
            title_candidate = paragraphs[0][:120]
        paragraphs_for_schedule.extend(paragraphs)
        image_count += sum(1 for _ in root.iter(f"{{{NS_HP}}}pic"))
        drawing_count += sum(1 for _ in root.iter(f"{{{NS_HP}}}rect"))
        drawing_count += sum(1 for _ in root.iter(f"{{{NS_HP}}}line"))

        tables = collect_tables(root)
        for tbl_idx, tbl in enumerate(tables):
            table_count += 1
            grid = table_rows_cells(tbl)
            rows = len(grid)
            cols = max((len(r) for r in grid), default=0)
            max_rows = max(max_rows, rows)
            max_cols = max(max_cols, cols)

            cells_total_local = 0
            empty_local = 0
            merged_local = 0
            for row in grid:
                for cell in row:
                    cells_total_local += 1
                    if not cell_text(cell).strip():
                        empty_local += 1
                    cs, rs = cell_span(cell)
                    if cs > 1 or rs > 1:
                        merged_local += 1
            total_cells += cells_total_local
            empty_cells += empty_local
            merged_cells += merged_local

            tbl_scores = _compute_table_scores(grid)
            nested_count = tbl_scores["nested_table_count"]

            header_rows = detect_header_rows(grid)
            header_texts: list[str] = []
            if header_rows:
                first_header_row = grid[header_rows[0]]
                for col_idx, cell in enumerate(first_header_row):
                    norm = normalize_header(cell_text(cell))
                    if norm:
                        header_texts.append(norm)
                        ctx.header_counter[norm][file_id] += 1
                        ctx.header_files[norm].add(file_id)
                        ctx.header_tables[norm].add(f"{file_id}:t{tbl_idx}")
                        ctx.header_col_positions[norm][col_idx] += 1

            date_headers = [t for t in header_texts if is_date_like(t)]
            numeric_headers = [t for t in header_texts if is_numeric_like(t)]
            if date_headers:
                has_date_axis = True
            schedule_hits = sum(1 for kw in SCHEDULE_HEADER_KEYWORDS if kw in " ".join(header_texts))
            if schedule_hits >= 2:
                has_schedule_keyword = True

            layout, conf, evidence = classify_table_layout(grid, header_texts, paragraphs[:5])
            if layout == "gantt_like_table":
                has_gantt = True

            first_rows_preview = []
            for r in grid[:3]:
                first_rows_preview.append([normalize_header(cell_text(c))[:40] for c in r])
            left_col_preview = [normalize_header(cell_text(r[0]))[:40] for r in grid[:10] if r]

            table_id = f"{file_id}:s{sec_idx}:t{tbl_idx}"
            text_cell_count = sum(
                1 for row in grid for c in row if normalize_header(cell_text(c))
            )
            table_record = {
                "fileId": file_id,
                "tableId": table_id,
                "sectionIndex": sec_idx,
                "blockIndex": tbl_idx,
                "tableIndex": tbl_idx,
                "rowCount": rows,
                "colCount": cols,
                "cellCount": cells_total_local,
                "mergedCellCount": merged_local,
                "emptyCellCount": empty_local,
                "hasMergedCells": merged_local > 0,
                "maxColSpan": tbl_scores["max_col_span"],
                "maxRowSpan": tbl_scores["max_row_span"],
                "hasNestedTables": nested_count > 0,
                "nestedTableCount": nested_count,
                "textCellRatio": round(tbl_scores["text_cell_ratio"], 3),
                "denseCellRatio": round(
                    text_cell_count / cells_total_local if cells_total_local else 0.0, 3
                ),
                "labelValuePairScore": round(tbl_scores["label_value_pair_score"], 3),
                "dateAxisScore": round(
                    len(date_headers) / max(cols, 1), 3
                ),
                "approvalStampScore": round(tbl_scores["approval_stamp_score"], 3),
                "pageMarkerScore": round(tbl_scores["page_marker_score"], 3),
                "headerRowCandidates": header_rows,
                "headerTexts": header_texts,
                "firstRowsPreview": first_rows_preview,
                "leftColumnPreview": left_col_preview,
                "dateHeaderCandidates": date_headers,
                "numericHeaderCandidates": numeric_headers,
                "layoutGuess": layout,
                "confidence": round(conf, 3),
                "classificationEvidence": evidence,
                "warnings": [],
            }
            ctx.table_records.append(table_record)
            tables_for_schedule.append(table_record)

    parse_record = {
        "fileId": file_id,
        "documentTitleCandidate": title_candidate,
        "paragraphCount": paragraph_count,
        "blockCount": paragraph_count + table_count,
        "tableCount": table_count,
        "imageCount": image_count,
        "drawingCount": drawing_count,
        "totalCellCount": total_cells,
        "mergedCellCount": merged_cells,
        "emptyCellCount": empty_cells,
        "maxTableRows": max_rows,
        "maxTableCols": max_cols,
        "hasScheduleKeyword": has_schedule_keyword,
        "hasDateAxisCandidate": has_date_axis,
        "hasGanttCandidate": has_gantt,
        "parserStatus": "PASS" if not parser_warnings else "PARTIAL",
        "parserWarnings": parser_warnings,
    }
    ctx.parse_records.append(parse_record)

    # schedule candidates per file
    sch = detect_schedule_candidate(file_id, file_name, paragraphs_for_schedule, tables_for_schedule)
    ctx.schedule_records.extend(sch)


# ── fixture candidate selection ───────────────────────────────────────────────

def select_fixture_candidates(ctx: CorpusContext) -> None:
    by_file_parse = {p["fileId"]: p for p in ctx.parse_records}
    by_file_inv = {f["fileId"]: f for f in ctx.file_records}
    tables_by_file: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for t in ctx.table_records:
        tables_by_file[t["fileId"]].append(t)

    used = set()

    def add(fid: str, category: str, reason: str, confidence: float):
        if fid in used or fid not in by_file_inv:
            return
        used.add(fid)
        inv = by_file_inv[fid]
        ctx.fixture_records.append({
            "fileId": fid,
            "category": category,
            "reason": reason,
            "confidence": round(confidence, 3),
            "pathHash": inv["pathHash"],
            "relativePath": inv["relativePath"] if not ctx.anonymize else inv["pathHash"][:16],
            "copyRecommended": True,
        })

    # 1. simple_form_table
    for fid, tables in tables_by_file.items():
        if any(t["layoutGuess"] == "form_table" and t["rowCount"] <= 6 for t in tables):
            add(fid, "simple_form_table", "form_table with <=6 rows detected", 0.85)
            break

    # 2. vertical_schedule  3. horizontal_schedule  4. gantt_bar_schedule  5. calendar
    for category, layout in (
        ("vertical_schedule", "vertical_schedule"),
        ("horizontal_schedule", "horizontal_schedule"),
        ("gantt_bar_schedule", "gantt_like_table"),
        ("calendar_schedule", "calendar_like_table"),
    ):
        for fid, tables in tables_by_file.items():
            if fid in used:
                continue
            if any(t["layoutGuess"] == layout for t in tables):
                add(fid, category, f"table layout {layout}", 0.8)
                break

    # 6. merged_cell_complex
    for fid, parse in by_file_parse.items():
        if fid in used:
            continue
        if parse.get("mergedCellCount", 0) >= 5:
            add(fid, "merged_cell_complex", f"merged_cell={parse['mergedCellCount']}", 0.7)
            break

    # 7. many_tables_document
    for fid, parse in sorted(by_file_parse.items(), key=lambda kv: kv[1].get("tableCount", 0), reverse=True):
        if fid in used:
            continue
        if parse.get("tableCount", 0) >= 5:
            add(fid, "many_tables_document", f"table_count={parse['tableCount']}", 0.65)
            break

    # 8. parse_failure_high_priority
    failure_by_file: dict[str, list[dict]] = defaultdict(list)
    for f in ctx.failure_records:
        failure_by_file[f["fileId"]].append(f)
    for fid, fails in failure_by_file.items():
        if fid in used:
            continue
        high = [f for f in fails if f.get("fixturePriority") == "high"]
        if high:
            add(fid, "parse_failure_high_priority", f"failures={len(fails)}", 0.95)
            break

    # 9. hancom_compatibility_edge_case
    for fid, pkg in ((p["fileId"], p) for p in ctx.package_records):
        if fid in used:
            continue
        if pkg.get("warnings"):
            add(fid, "hancom_compatibility_edge_case", f"warnings={pkg['warnings']}", 0.6)
            break


# ── report writers ────────────────────────────────────────────────────────────

def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            row = {k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v) for k, v in r.items()}
            w.writerow(row)


def write_reports(ctx: CorpusContext) -> dict[str, Path]:
    out = ctx.out_dir
    paths = {}

    inv_fields = ["fileId", "relativePath", "pathHash", "fileName", "sizeBytes", "modifiedTime",
                  "zipOpenOk", "entryCount", "hasMimetype", "mimetypeValue", "mimetypeCompressType",
                  "hasContentHpf", "hasContainerXml", "hasHeaderXml", "sectionFileCount",
                  "status", "errorMessage"]
    if ctx.anonymize:
        inv_rows = [{**r, "relativePath": ""} for r in ctx.file_records]
    else:
        inv_rows = ctx.file_records
    _write_csv(out / "inventory.csv", inv_rows, inv_fields)
    _write_jsonl(out / "inventory.jsonl", inv_rows)
    paths["inventory_csv"] = out / "inventory.csv"
    paths["inventory_jsonl"] = out / "inventory.jsonl"

    _write_jsonl(out / "package_summary.jsonl", ctx.package_records)
    paths["package_summary"] = out / "package_summary.jsonl"

    parse_fields = ["fileId", "documentTitleCandidate", "paragraphCount", "blockCount",
                    "tableCount", "imageCount", "drawingCount", "totalCellCount",
                    "mergedCellCount", "emptyCellCount", "maxTableRows", "maxTableCols",
                    "hasScheduleKeyword", "hasDateAxisCandidate", "hasGanttCandidate",
                    "parserStatus", "parserWarnings"]
    _write_csv(out / "parse_summary.csv", ctx.parse_records, parse_fields)
    _write_jsonl(out / "parse_summary.jsonl", ctx.parse_records)
    paths["parse_summary"] = out / "parse_summary.jsonl"

    _write_jsonl(out / "table_catalog.jsonl", ctx.table_records)
    paths["table_catalog"] = out / "table_catalog.jsonl"

    # header dictionary
    header_rows = []
    for norm, fid_counter in ctx.header_counter.items():
        total = sum(fid_counter.values())
        files = ctx.header_files[norm]
        tables = ctx.header_tables[norm]
        col_positions = ctx.header_col_positions[norm]
        field_name, conf = guess_field(norm)
        # 자주 같이 등장하는 헤더 패턴으로 documentTypeHints 후보
        type_hints = []
        if field_name in ("startDate", "endDate", "durationDays", "trade", "taskName"):
            type_hints.append("schedule_document")
        if field_name in ("projectName", "siteName", "contractorName"):
            type_hints.append("form_document")
        if field_name in ("quantity", "unit", "spec", "amount"):
            type_hints.append("bill_of_materials")
        header_rows.append({
            "normalizedHeader": norm,
            "originalSamples": norm,
            "count": total,
            "fileCount": len(files),
            "tableCount": len(tables),
            "commonColIndexes": [idx for idx, _ in col_positions.most_common(3)],
            "guessedField": field_name,
            "fieldConfidence": round(conf, 3),
            "documentTypeHints": type_hints,
        })
    header_rows.sort(key=lambda r: r["count"], reverse=True)
    _write_csv(out / "header_dictionary.csv", header_rows,
               ["normalizedHeader", "originalSamples", "count", "fileCount", "tableCount",
                "commonColIndexes", "guessedField", "fieldConfidence", "documentTypeHints"])
    paths["header_dictionary"] = out / "header_dictionary.csv"

    _write_jsonl(out / "schedule_candidates.jsonl", ctx.schedule_records)
    paths["schedule_candidates"] = out / "schedule_candidates.jsonl"

    _write_jsonl(out / "parse_failures.jsonl", ctx.failure_records)
    paths["parse_failures"] = out / "parse_failures.jsonl"

    (out / "fixture_candidates.json").write_text(
        json.dumps(ctx.fixture_records, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    paths["fixture_candidates"] = out / "fixture_candidates.json"

    # summary.md
    summary = _build_summary_md(ctx, header_rows)
    (out / "summary.md").write_text(summary, encoding="utf-8")
    paths["summary"] = out / "summary.md"

    return paths


def _build_summary_md(ctx: CorpusContext, header_rows: list[dict[str, Any]]) -> str:
    total = len(ctx.file_records)
    zip_ok = sum(1 for r in ctx.file_records if r["zipOpenOk"])
    pkg_xml_ok = sum(1 for p in ctx.package_records if p.get("xmlDecodeOk"))
    table_docs = sum(1 for p in ctx.parse_records if p.get("tableCount", 0) > 0)
    total_tables = sum(p.get("tableCount", 0) for p in ctx.parse_records)
    total_cells = sum(p.get("totalCellCount", 0) for p in ctx.parse_records)
    merged_docs = sum(1 for p in ctx.parse_records if p.get("mergedCellCount", 0) > 0)
    schedule_count = len(ctx.schedule_records)

    layout_counter: Counter = Counter(t.get("layoutGuess", "unknown") for t in ctx.table_records)
    failure_counter: Counter = Counter(f.get("errorType", "Unknown") for f in ctx.failure_records)

    out_lines = []
    out_lines.append("# HWPX Corpus Profiler — Smoke Scan Summary")
    out_lines.append("")
    out_lines.append(f"- 스캔 root: `{ctx.root if not ctx.anonymize else '(anonymized)'}`")
    out_lines.append(f"- 총 HWPX 발견: {total}")
    out_lines.append(f"- ZIP 정상: {zip_ok}, 실패: {total - zip_ok}")
    out_lines.append(f"- XML 디코드 정상 패키지: {pkg_xml_ok}")
    out_lines.append(f"- 표 포함 문서: {table_docs}")
    out_lines.append(f"- 총 표 수: {total_tables}")
    out_lines.append(f"- 총 셀 수: {total_cells}")
    out_lines.append(f"- 병합셀 포함 문서: {merged_docs}")
    out_lines.append(f"- 공정표 후보 record: {schedule_count}")
    out_lines.append("")
    out_lines.append("## 표 레이아웃 유형 분포")
    for layout, cnt in layout_counter.most_common():
        out_lines.append(f"- {layout}: {cnt}")
    out_lines.append("")
    out_lines.append("## 가장 자주 나온 헤더 TOP 50")
    for r in header_rows[:50]:
        out_lines.append(f"- `{r['normalizedHeader']}` × {r['count']} (files={r['fileCount']}, "
                         f"guess={r['guessedField']}@{r['fieldConfidence']})")
    out_lines.append("")
    out_lines.append("## 실패 유형 TOP 20")
    for et, cnt in failure_counter.most_common(20):
        out_lines.append(f"- {et}: {cnt}")
    out_lines.append("")
    out_lines.append("## fixture 후보")
    for f in ctx.fixture_records:
        out_lines.append(f"- [{f['category']}] {f['fileId']} — {f['reason']} (conf={f['confidence']})")
    out_lines.append("")
    out_lines.append("## 다음 파서 개선 우선순위")
    priorities = []
    if failure_counter:
        priorities.append("실패 케이스 fixture 격리 후 파서 케이스별 보강")
    if layout_counter.get("unknown", 0) > 0:
        priorities.append(f"unknown layout 분류 보강 ({layout_counter['unknown']}건)")
    if any(p.get("hasGanttCandidate") for p in ctx.parse_records):
        priorities.append("gantt-like 표 시간축/막대 인식 정확도")
    if not priorities:
        priorities.append("nested table 처리 정확도 (현 profiler에서 중첩 스킵)")
    for i, p in enumerate(priorities, 1):
        out_lines.append(f"{i}. {p}")
    return "\n".join(out_lines) + "\n"


# ── CLI entry ─────────────────────────────────────────────────────────────────

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="HWPX corpus profiler (read-only)")
    p.add_argument("--root", required=True, help="scan root directory")
    p.add_argument("--out", required=True, help="report output directory")
    p.add_argument("--max-files", type=int, default=0, help="0 = no limit")
    p.add_argument("--anonymize-paths", dest="anonymize", action="store_true", default=True)
    p.add_argument("--no-anonymize-paths", dest="anonymize", action="store_false")
    p.add_argument("--fail-fast", action="store_true", default=False)
    p.add_argument("--include-hidden", action="store_true", default=False)
    p.add_argument("--copy-fixtures", action="store_true", default=False,
                   help="reserved; not used in this stage")
    return p.parse_args(argv)


def run_profiler(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.copy_fixtures:
        print("[warn] --copy-fixtures requested but disabled in this stage", file=sys.stderr)
    ctx = CorpusContext(
        root=root,
        out_dir=out_dir,
        anonymize=args.anonymize,
        max_files=args.max_files,
        fail_fast=args.fail_fast,
        include_hidden=args.include_hidden,
    )
    files = discover_hwpx(root, args.include_hidden, args.max_files)
    if not files:
        # 빈 폴더도 정상 시나리오 — 빈 리포트 생성
        select_fixture_candidates(ctx)
        paths = write_reports(ctx)
        return {"status": "PASS", "scanned": 0, "reports": {k: str(v) for k, v in paths.items()}}

    for i, p in enumerate(files):
        try:
            process_file(ctx, i, p)
        except Exception as exc:
            tb = traceback.format_exc(limit=3)
            ctx.failure_records.append({
                "fileId": f"unknown_{i}", "stage": "FILE_DISCOVERY",
                "errorType": exc.__class__.__name__, "errorMessage": str(exc),
                "tracebackShort": tb[-400:], "recoverable": False,
                "suggestedFix": "investigate", "fixturePriority": "high",
            })
            if args.fail_fast:
                raise

    select_fixture_candidates(ctx)
    paths = write_reports(ctx)
    return {
        "status": "PASS",
        "scanned": len(files),
        "zip_ok": sum(1 for r in ctx.file_records if r["zipOpenOk"]),
        "tables": sum(p.get("tableCount", 0) for p in ctx.parse_records),
        "failures": len(ctx.failure_records),
        "reports": {k: str(v) for k, v in paths.items()},
    }


def main() -> int:
    args = parse_args()
    result = run_profiler(args)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
