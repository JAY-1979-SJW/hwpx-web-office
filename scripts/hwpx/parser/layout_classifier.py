"""HWPX Parser V2 — layout classifier.

TableInfo를 받아 layoutGuess / confidence / evidence를 반환하는 wrapper.
실질 로직은 기존 corpus profiler의 classify_table_layout을 재사용한다.
분류 결과와 profiler 결과가 일치해야 한다.
"""
from __future__ import annotations

import sys
from pathlib import Path

from .parser_contract import TableInfo

# corpus profiler를 직접 import하여 분류 로직 재사용
_PROFILER_PATH = Path(__file__).resolve().parents[3] / "scripts" / "local"
if str(_PROFILER_PATH) not in sys.path:
    sys.path.insert(0, str(_PROFILER_PATH))

import xml.etree.ElementTree as ET
import unicodedata
import re

# profiler 모듈에서 핵심 분류 함수만 가져옴
try:
    from hwpx_corpus_profiler import (  # type: ignore
        classify_table_layout as _profiler_classify,
        normalize_header as _normalize_header,
    )
    _PROFILER_AVAILABLE = True
except ImportError:
    _PROFILER_AVAILABLE = False


SUPPORTED_LAYOUTS = (
    "metadata_table", "form_table", "vertical_table", "horizontal_table",
    "gantt_like_table", "calendar_like_table", "legal_complex_table",
    "stamp_or_approval_table", "page_marker_table", "nested_container_table",
    "layout_noise", "unknown",
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
    """TableInfo를 받아 (layoutGuess, confidence, evidence)를 반환."""
    if not _PROFILER_AVAILABLE:
        return _fallback_classify(table_info)

    # profiler classify_table_layout은 (grid, header_texts, paragraphs) 형태
    # TableInfo에서 mock grid를 구성해 호출
    # 이번 skeleton에서는 cells 기반으로 간이 grid를 재구성
    if not table_info.cells:
        return "unknown", 0.0, ["empty table"]

    # row×col grid를 ET.Element mock으로 재구성하는 대신
    # cells normalizedText 기반 간이 분류 적용
    # 완전한 grid 재구성은 HWPX-BLOCK-TABLE-ORDER-PARSER-01에서 구현
    return _fallback_classify(table_info)


def enrich_table_layout(table_info: TableInfo) -> TableInfo:
    """TableInfo에 layoutGuess/confidence/evidence를 채워 반환."""
    layout, conf, evidence = classify_table_layout(table_info)
    table_info.layoutGuess = layout
    table_info.confidence = conf
    table_info.classificationEvidence = evidence if evidence else ["fallback_classifier"]
    return table_info
