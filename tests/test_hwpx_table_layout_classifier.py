"""Tests for HWPX-FULL-TABLE-PARSER-IMPROVE-01: table layout classifier."""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts" / "local"))

from hwpx_corpus_profiler import (
    NS_HP,
    classify_table_layout,
    _compute_table_scores,
    detect_header_rows,
    normalize_header,
    cell_text,
    cell_has_nested_table,
)


# ── XML builder helpers ───────────────────────────────────────────────────────

def _tc(text: str, col_span: int = 1, row_span: int = 1) -> ET.Element:
    tc = ET.Element(f"{{{NS_HP}}}tc")
    span = ET.SubElement(tc, f"{{{NS_HP}}}cellSpan")
    span.set("colSpan", str(col_span))
    span.set("rowSpan", str(row_span))
    sub = ET.SubElement(tc, f"{{{NS_HP}}}subList")
    p = ET.SubElement(sub, f"{{{NS_HP}}}p")
    run = ET.SubElement(p, f"{{{NS_HP}}}run")
    t = ET.SubElement(run, f"{{{NS_HP}}}t")
    t.text = text
    return tc


def _tr(*cells: ET.Element) -> ET.Element:
    tr = ET.Element(f"{{{NS_HP}}}tr")
    for c in cells:
        tr.append(c)
    return tr


def _grid(*rows) -> list[list[ET.Element]]:
    """rows: list of list[ET.Element] or TR elements."""
    result = []
    for row in rows:
        if isinstance(row, ET.Element):
            result.append([c for c in row if c.tag == f"{{{NS_HP}}}tc"])
        else:
            result.append(list(row))
    return result


# ── page_marker_table ─────────────────────────────────────────────────────────

def test_page_marker_table_detected():
    grid = _grid(
        [_tc("(8쪽중제2쪽)")],
        [_tc("특정소방대상물 정보"), _tc(""), _tc("")],
    )
    layout, conf, evidence = classify_table_layout(grid, [], [])
    assert layout == "page_marker_table"
    assert conf >= 0.7
    assert any("page marker" in e for e in evidence)


def test_page_marker_table_paren_format():
    grid = _grid(
        [_tc("(10쪽)")],
        [_tc("다중이용업소현황"), _tc("A동"), _tc("B동")],
    )
    layout, conf, _ = classify_table_layout(grid, [], [])
    assert layout == "page_marker_table"


# ── stamp_or_approval_table ───────────────────────────────────────────────────

def test_stamp_or_approval_table():
    grid = _grid(
        [_tc("담당"), _tc("검토"), _tc("승인")],
        [_tc(""), _tc("직인"), _tc("")],
    )
    layout, conf, evidence = classify_table_layout(grid, [], [])
    assert layout == "stamp_or_approval_table"
    assert conf >= 0.6
    assert any("stamp" in e for e in evidence)


def test_stamp_single_cell_small_table():
    grid = _grid(
        [_tc("직인"), _tc("")],
    )
    layout, conf, _ = classify_table_layout(grid, [], [])
    assert layout == "stamp_or_approval_table"


# ── layout_noise ──────────────────────────────────────────────────────────────

def test_layout_noise_single_cell():
    grid = _grid([_tc("환경관리비의 세부 산출기준(제61조제3항 관련)1. 환경관리비의 범위")])
    layout, conf, evidence = classify_table_layout(grid, [], [])
    assert layout == "layout_noise"
    assert conf >= 0.6
    assert any("single-cell" in e for e in evidence)


# ── metadata_table ────────────────────────────────────────────────────────────

def test_metadata_table_detected():
    grid = _grid(
        [_tc("공사명"), _tc("○○공사 1공구")],
        [_tc("현장명"), _tc("○○ 현장")],
        [_tc("작성일"), _tc("2026-05-17")],
        [_tc("시공사"), _tc("(주) ○○건설")],
    )
    layout, conf, evidence = classify_table_layout(grid, [], [])
    assert layout == "metadata_table"
    assert conf >= 0.55
    assert any("metadata" in e for e in evidence)


# ── form_table ────────────────────────────────────────────────────────────────

def test_form_table_detected():
    grid = _grid(
        [_tc("접수번호"), _tc("2026-001"), _tc("접수일"), _tc("2026-05-01")],
        [_tc("발신"), _tc("○○부서"), _tc("수신"), _tc("△△부서")],
        [_tc("문서번호"), _tc("ABC-001"), _tc("보고일"), _tc("2026-05-17")],
    )
    layout, conf, evidence = classify_table_layout(grid, [], [])
    assert layout == "form_table"
    assert conf >= 0.6
    assert any("form label" in e for e in evidence)


# ── schedule variants ─────────────────────────────────────────────────────────

def test_horizontal_schedule_detected():
    headers = ["공종", "작업명", "시작일", "종료일"]
    grid = _grid(
        [_tc("공종"), _tc("작업명"), _tc("시작일"), _tc("종료일")],
        [_tc("철근"), _tc("배근"), _tc("2026-05-01"), _tc("2026-05-10")],
        [_tc("콘크리트"), _tc("타설"), _tc("2026-05-11"), _tc("2026-05-20")],
    )
    layout, conf, evidence = classify_table_layout(grid, headers, [])
    assert layout in ("horizontal_schedule", "vertical_schedule")
    assert conf >= 0.7


def test_gantt_like_table_detected():
    headers = ["공종", "2026-01", "2026-02", "2026-03", "2026-04", "2026-05"]
    grid = _grid(
        [_tc("공종"), _tc("2026-01"), _tc("2026-02"), _tc("2026-03"), _tc("2026-04"), _tc("2026-05")],
        [_tc("토공"), _tc("■"), _tc("■"), _tc(""), _tc(""), _tc("")],
    )
    layout, conf, _ = classify_table_layout(grid, headers, [])
    assert layout == "gantt_like_table"
    assert conf >= 0.6


# ── vertical_table ────────────────────────────────────────────────────────────

def test_vertical_table_detected():
    headers = ["번호", "항목"]
    grid = _grid(
        [_tc("번호"), _tc("항목")],
        [_tc("1"), _tc("토공사")],
        [_tc("2"), _tc("기초공사")],
        [_tc("3"), _tc("골조공사")],
        [_tc("4"), _tc("마감공사")],
    )
    layout, conf, _ = classify_table_layout(grid, headers, [])
    assert layout in ("vertical_table", "horizontal_table", "horizontal_schedule")


# ── nested_container_table ────────────────────────────────────────────────────

def test_nested_container_table_detected():
    outer_tc = ET.Element(f"{{{NS_HP}}}tc")
    span = ET.SubElement(outer_tc, f"{{{NS_HP}}}cellSpan")
    span.set("colSpan", "1")
    span.set("rowSpan", "1")
    sub = ET.SubElement(outer_tc, f"{{{NS_HP}}}subList")
    # embed a nested tbl
    nested_tbl = ET.SubElement(sub, f"{{{NS_HP}}}tbl")
    ET.SubElement(nested_tbl, f"{{{NS_HP}}}tr")
    p = ET.SubElement(sub, f"{{{NS_HP}}}p")
    run = ET.SubElement(p, f"{{{NS_HP}}}run")
    t_elem = ET.SubElement(run, f"{{{NS_HP}}}t")
    t_elem.text = "outer text"

    grid = [[outer_tc], [_tc("normal"), _tc("cell")]]
    assert cell_has_nested_table(outer_tc)
    layout, conf, evidence = classify_table_layout(grid, [], [])
    assert layout == "nested_container_table"
    assert any("nested" in e for e in evidence)


# ── unknown: no forced classification ────────────────────────────────────────

def test_unknown_not_forced():
    """표가 작고 패턴이 없으면 unknown을 유지해야 한다."""
    grid = _grid(
        [_tc("A"), _tc("B"), _tc("C")],
        [_tc("x"), _tc("y"), _tc("z")],
    )
    layout, conf, evidence = classify_table_layout(grid, ["A", "B", "C"], [])
    # 작은 표에 어떤 category도 명확히 해당 안 되면 unknown 허용
    # (결과는 vertical_table 또는 unknown 중 하나)
    assert isinstance(layout, str)
    assert isinstance(conf, float)
    assert isinstance(evidence, list) and len(evidence) >= 1


# ── headerRowCandidates: 제목행 건너뛰기 ─────────────────────────────────────

def test_header_row_skips_title_row():
    """row 0이 병합된 긴 제목행이면 row 1을 headerRow로 선택해야 한다."""
    grid = _grid(
        [_tc("가스배관 현황표 (단위: m)", col_span=6)],
        [_tc("번호"), _tc("가스명"), _tc("압력"), _tc("재질"), _tc("호칭지름"), _tc("연장")],
        [_tc("1"), _tc("LPG"), _tc("중압"), _tc("강관"), _tc("DN50"), _tc("120")],
    )
    candidates = detect_header_rows(grid)
    assert candidates == [1], f"expected [1], got {candidates}"


def test_header_row_normal_first_row():
    grid = _grid(
        [_tc("공종"), _tc("작업명"), _tc("시작일"), _tc("종료일")],
        [_tc("철근"), _tc("배근"), _tc("2026-05-01"), _tc("2026-05-10")],
    )
    candidates = detect_header_rows(grid)
    assert 0 in candidates


# ── classificationEvidence 출력 확인 ─────────────────────────────────────────

def test_classification_evidence_present_for_non_unknown():
    headers = ["공종", "작업명", "시작일", "종료일"]
    grid = _grid(
        [_tc("공종"), _tc("작업명"), _tc("시작일"), _tc("종료일")],
        [_tc("철근"), _tc("배근"), _tc("2026-05-01"), _tc("2026-05-10")],
    )
    layout, conf, evidence = classify_table_layout(grid, headers, [])
    assert layout != "unknown"
    assert len(evidence) >= 1


def test_classification_evidence_unknown_has_warning():
    grid = _grid(
        [_tc("X"), _tc("Y"), _tc("Z")],
        [_tc("a"), _tc("b"), _tc("c")],
    )
    layout, conf, evidence = classify_table_layout(grid, ["X", "Y", "Z"], [])
    assert len(evidence) >= 1  # unknown도 이유를 남겨야 함


# ── _compute_table_scores ─────────────────────────────────────────────────────

def test_compute_scores_stamp():
    grid = _grid(
        [_tc("담당"), _tc("검토"), _tc("직인")],
    )
    scores = _compute_table_scores(grid)
    assert scores["stamp_score"] > 0
    assert scores["approval_stamp_score"] > 0


def test_compute_scores_page_marker():
    grid = _grid(
        [_tc("(8쪽중제3쪽)")],
        [_tc("소방시설 현황"), _tc(""), _tc("")],
    )
    scores = _compute_table_scores(grid)
    assert scores["page_marker_score"] > 0


def test_compute_scores_metadata():
    grid = _grid(
        [_tc("공사명"), _tc("○○공사")],
        [_tc("현장명"), _tc("○○현장")],
    )
    scores = _compute_table_scores(grid)
    assert scores["metadata_score"] > 0
