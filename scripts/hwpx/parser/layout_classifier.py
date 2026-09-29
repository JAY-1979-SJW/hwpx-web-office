"""HWPX Parser V2 — layout classifier.

TableInfo를 받아 layoutGuess / confidence / evidence를 반환하는 wrapper.
실질 로직은 기존 corpus profiler의 classify_table_layout을 재사용한다.
분류 결과와 profiler 결과가 일치해야 한다.
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from .parser_contract import CellInfo, TableInfo

# corpus profiler를 직접 import하여 분류 로직 재사용
_PROFILER_PATH = Path(__file__).resolve().parents[3] / "scripts" / "local"
if str(_PROFILER_PATH) not in sys.path:
    sys.path.insert(0, str(_PROFILER_PATH))


# profiler 모듈에서 핵심 분류 함수만 가져옴
try:
    from hwpx_corpus_profiler import (  # type: ignore
        classify_table_layout as _profiler_classify,
    )

    _PROFILER_AVAILABLE = True
except ImportError:
    _PROFILER_AVAILABLE = False


_NS_HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
_TAG_TC = f"{{{_NS_HP}}}tc"
_TAG_T = f"{{{_NS_HP}}}t"
_TAG_CELL_SPAN = f"{{{_NS_HP}}}cellSpan"
_TAG_TBL = f"{{{_NS_HP}}}tbl"


def _mock_cell_element(cell: CellInfo) -> ET.Element:
    """CellInfo를 profiler의 cell_text/cell_span/cell_has_nested_table이
    기대하는 최소 hp:tc 구조로 되돌려 넣는다. 원본 XML을 다시 파싱하지
    않고, table_parser가 이미 뽑아둔 값(text/colSpan/rowSpan/hasNestedTable)
    만 최소 골격에 채운다."""
    tc = ET.Element(_TAG_TC)
    span = ET.SubElement(tc, _TAG_CELL_SPAN)
    span.set("colSpan", str(cell.colSpan))
    span.set("rowSpan", str(cell.rowSpan))
    if cell.text:
        t = ET.SubElement(tc, _TAG_T)
        t.text = cell.text
    if cell.hasNestedTable:
        ET.SubElement(tc, _TAG_TBL)
    return tc


def _mock_grid(table_info: TableInfo) -> list[list[ET.Element]]:
    """TableInfo.cells(행 순서 없이 평면 목록)를 row×col 격자로 되돌린다.
    table_parser._parse_table_element가 실제 hp:tr/hp:tc 순서 그대로
    cell.row/cell.col을 매겼으므로, 그 순서로 재구성하면 원본 grid와
    같은 모양이 된다."""
    by_row: dict[int, list[CellInfo]] = {}
    for c in table_info.cells:
        by_row.setdefault(c.row, []).append(c)
    return [
        [_mock_cell_element(c) for c in sorted(by_row[ri], key=lambda c: c.col)]
        for ri in sorted(by_row)
    ]


SUPPORTED_LAYOUTS = (
    "metadata_table",
    "form_table",
    "vertical_table",
    "horizontal_table",
    "gantt_like_table",
    "calendar_like_table",
    "legal_complex_table",
    "stamp_or_approval_table",
    "page_marker_table",
    "nested_container_table",
    "layout_noise",
    "unknown",
)


# profiler 미사용 fallback 분류기
def _fallback_classify(table_info: TableInfo) -> tuple[str, float, list[str]]:
    cells = table_info.cells
    if not cells:
        return "unknown", 0.0, ["empty table"]

    total = len(cells)
    text_count = sum(1 for c in cells if c.normalizedText)
    text_ratio = text_count / total if total else 0.0

    if table_info.hasNestedTables:
        return "nested_container_table", 0.7, ["has_nested_tables"]

    if any("쪽" in c.text for c in cells if c.text):
        return "page_marker_table", 0.85, ["page_marker_text_detected"]

    merged_count = sum(1 for c in cells if c.isMergedOrigin)
    merge_ratio = merged_count / total if total else 0.0

    if text_ratio < 0.2:
        return "layout_noise", 0.75, [f"text_ratio={text_ratio:.2f}"]

    evidence = [f"text_ratio={text_ratio:.2f}", f"merge_ratio={merge_ratio:.2f}"]
    return "unknown", 0.3, evidence


def classify_table_layout(table_info: TableInfo) -> tuple[str, float, list[str]]:
    """TableInfo를 받아 (layoutGuess, confidence, evidence)를 반환.

    2026-09-29 이전에는 profiler import에는 성공하면서도 실제로는 한
    번도 호출하지 않고 항상 _fallback_classify만 써서, 표 분류가 거의
    항상 unknown(신뢰도 0.3)으로 나오는 문제가 있었다(python-hwpx
    교차검증 중 실측으로 발견). CellInfo를 profiler가 기대하는 hp:tc
    grid로 재구성해 실제 분류기를 호출하도록 고쳤다. profiler 호출이
    예외를 내거나 사용 불가능하면 fallback으로 내려간다.
    """
    if not table_info.cells:
        return "unknown", 0.0, ["empty table"]

    # 중첩 표(hasNestedTables)는 profiler보다 먼저 처리한다. profiler는
    # "표 안에 진짜 채울 필드가 있는 중첩 표"와 "법령 문구가 많은 일반
    # 표"를 구분하지 못해, 법령 조항이 섞인 중첩 표를 legal_complex_table
    # 로 분류해버리면 그 안의 실제 입력칸까지 통째로 배제된다(2026-09-29,
    # fx_nested_legal_complex.hwpx 실측으로 발견 — 11개 슬롯이 0개가 됨).
    # 중첩 표는 안쪽 셀 내용으로 판단하는 nested_container_table 이
    # 더 안전하다.
    if table_info.hasNestedTables:
        return "nested_container_table", 0.7, ["has_nested_tables"]

    if not _PROFILER_AVAILABLE:
        return _fallback_classify(table_info)

    try:
        grid = _mock_grid(table_info)
        layout, conf, evidence = _profiler_classify(grid, table_info.headerTexts, [])
    except Exception:  # ruff: ignore[blind-except] - profiler 호출 실패 시 fallback으로 계속
        return _fallback_classify(table_info)
    return layout, conf, evidence


def enrich_table_layout(table_info: TableInfo) -> TableInfo:
    """TableInfo에 layoutGuess/confidence/evidence를 채워 반환."""
    layout, conf, evidence = classify_table_layout(table_info)
    table_info.layoutGuess = layout
    table_info.confidence = conf
    table_info.classificationEvidence = evidence if evidence else ["fallback_classifier"]
    return table_info
