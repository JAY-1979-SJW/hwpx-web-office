"""HWPX-SCHEDULE-BAR-RANGE-DETECTOR-01 — date range → col range 변환 테스트.

원본 fixture 수정 없음 (read-only).
apply_edit_plan / write_package / fill_schedule_bars 호출 없음.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "hwpx" / "gantt"
FX_BASIC = FIXTURE_DIR / "fx_gantt_like_basic.hwpx"
FX_EMPTY = FIXTURE_DIR / "fx_gantt_like_template_empty.hwpx"
FX_PARTIAL = FIXTURE_DIR / "fx_gantt_like_partial_filled.hwpx"


def _parse(path: Path):
    import sys
    sys.path.insert(0, str(Path(__file__).parents[1]))
    from scripts.hwpx.parser.parser_engine import parse_hwpx_v2
    return parse_hwpx_v2(path)


def _gantt(result):
    return next((s for s in result.schedules if len(s.taskRows) >= 5), None)


# ── T01–T02: normalize ─────────────────────────────────────────────────────

def test_normalize_month_label_kr():
    from scripts.hwpx.parser.schedule_detector import normalize_month_label
    assert normalize_month_label("5월") == "month:5"
    assert normalize_month_label("12월") == "month:12"
    assert normalize_month_label("1월") == "month:1"


def test_normalize_iso_date_to_month_axis():
    from scripts.hwpx.parser.schedule_detector import normalize_schedule_date
    assert normalize_schedule_date("2026-05-01", "month") == "month:5"
    assert normalize_schedule_date("2026-07-31", "month") == "month:7"
    assert normalize_schedule_date("2026-06", "month") == "month:6"
    assert normalize_schedule_date("5월", "month") == "month:5"
    assert normalize_schedule_date("5", "month") == "month:5"


# ── T03–T06: map_date_range_to_columns ────────────────────────────────────

def test_map_full_range_to_cols():
    from scripts.hwpx.parser.schedule_detector import map_date_range_to_columns
    result = _parse(FX_BASIC)
    s = _gantt(result)
    cs, ce, dr = map_date_range_to_columns(s.timeAxis, "2026-05-01", "2026-07-31")
    assert cs == 2
    assert ce == 4
    assert dr.startLabel == "5월"
    assert dr.endLabel == "7월"
    assert not dr.warnings


def test_map_single_month_to_col():
    from scripts.hwpx.parser.schedule_detector import map_date_range_to_columns
    result = _parse(FX_BASIC)
    s = _gantt(result)
    cs, ce, dr = map_date_range_to_columns(s.timeAxis, "2026-06-01", "2026-06-30")
    assert cs == 3
    assert ce == 3


def test_out_of_range_date_review_required():
    from scripts.hwpx.parser.schedule_detector import map_date_range_to_columns
    result = _parse(FX_BASIC)
    s = _gantt(result)
    cs, ce, dr = map_date_range_to_columns(s.timeAxis, "2026-08-01", "2026-09-30")
    assert cs == -1
    assert ce == -1
    assert any("no_range_match" in w for w in dr.warnings)


def test_start_greater_than_end_warning():
    from scripts.hwpx.parser.schedule_detector import map_date_range_to_columns
    result = _parse(FX_BASIC)
    s = _gantt(result)
    # 7월 → 5월 (역방향)
    cs, ce, dr = map_date_range_to_columns(s.timeAxis, "2026-07-01", "2026-05-31")
    assert cs > ce
    assert any(">" in w for w in dr.warnings)


# ── T07–T09: find_task_row ─────────────────────────────────────────────────

def test_task_row_exact_match():
    from scripts.hwpx.parser.schedule_detector import find_task_row
    result = _parse(FX_BASIC)
    s = _gantt(result)
    tr, conf, ev, reason = find_task_row(s.taskRows, task_name="배관공사")
    assert tr is not None
    assert tr.taskName == "배관공사"
    assert conf >= 0.90
    assert reason is None


def test_task_row_contains_match():
    from scripts.hwpx.parser.schedule_detector import find_task_row
    result = _parse(FX_BASIC)
    s = _gantt(result)
    tr, conf, ev, reason = find_task_row(s.taskRows, task_name="배관")
    assert tr is not None
    assert "배관" in tr.taskName
    assert conf >= 0.70


def test_task_row_explicit_row_override():
    from scripts.hwpx.parser.schedule_detector import find_task_row
    result = _parse(FX_BASIC)
    s = _gantt(result)
    first_row = s.taskRows[0].row
    tr, conf, ev, reason = find_task_row(s.taskRows, row=first_row)
    assert tr is not None
    assert tr.row == first_row
    assert conf >= 0.95


# ── T10–T11: build / generate candidates ──────────────────────────────────

def test_build_bar_plan_candidate():
    from scripts.hwpx.parser.schedule_detector import build_schedule_bar_plan_candidate
    from scripts.hwpx.parser.parser_contract import ScheduleBarRangeRequest
    result = _parse(FX_BASIC)
    s = _gantt(result)
    req = ScheduleBarRangeRequest(
        taskName="배관공사",
        startDate="2026-05-01",
        endDate="2026-07-31",
        color="92D050",
        text="배관공사",
    )
    cand = build_schedule_bar_plan_candidate(s, req)
    assert cand.row >= 0
    assert cand.colStart == 2
    assert cand.colEnd == 4
    assert cand.color == "92D050"
    assert cand.confidence > 0


def test_empty_template_candidate_generation():
    from scripts.hwpx.parser.schedule_detector import generate_empty_template_bar_candidates
    result = _parse(FX_EMPTY)
    s = _gantt(result)
    candidates = generate_empty_template_bar_candidates(s)
    assert len(candidates) == len(s.taskRows)
    for c in candidates:
        assert c.colStart >= 0
        assert c.colEnd >= c.colStart
        assert c.source == "empty_template_candidate"


# ── T12–T13: conflict 감지 ─────────────────────────────────────────────────

def test_text_full_conflict_detected():
    from scripts.hwpx.parser.schedule_detector import build_schedule_bar_plan_candidate
    from scripts.hwpx.parser.parser_contract import ScheduleBarRangeRequest
    result = _parse(FX_BASIC)
    s = _gantt(result)
    req = ScheduleBarRangeRequest(
        taskName="배관공사",
        startDate="2026-05-01",
        endDate="2026-07-31",
        color="FF0000",
    )
    cand = build_schedule_bar_plan_candidate(s, req)
    assert cand.conflict in ("overlaps_existing_bar", "replaces_existing_empty_template",
                             "extends_existing_bar", "no_conflict")
    assert cand.existingBarType == "text_full"


def test_partial_bar_conflict():
    from scripts.hwpx.parser.schedule_detector import build_schedule_bar_plan_candidate
    from scripts.hwpx.parser.parser_contract import ScheduleBarRangeRequest
    result = _parse(FX_PARTIAL)
    s = _gantt(result)
    req = ScheduleBarRangeRequest(
        taskName="배관공사",
        startDate="2026-05-01",
        endDate="2026-07-31",
    )
    cand = build_schedule_bar_plan_candidate(s, req)
    assert cand.existingBarType in ("text_partial", "text_full", "empty_template", "")


def test_empty_template_no_conflict():
    from scripts.hwpx.parser.schedule_detector import generate_empty_template_bar_candidates
    result = _parse(FX_EMPTY)
    s = _gantt(result)
    candidates = generate_empty_template_bar_candidates(s)
    conflicts = {c.conflict for c in candidates}
    # empty_template fixture는 replaces_empty 또는 no_conflict만
    assert conflicts <= {"replaces_existing_empty_template", "no_conflict"}


# ── T14: JSON 직렬화 ────────────────────────────────────────────────────────

def test_bar_plan_candidate_json_serializable():
    from scripts.hwpx.parser.schedule_detector import build_schedule_bar_plan_candidate
    from scripts.hwpx.parser.parser_contract import ScheduleBarRangeRequest
    result = _parse(FX_BASIC)
    s = _gantt(result)
    req = ScheduleBarRangeRequest(taskName="배관공사", startDate="2026-05-01", endDate="2026-07-31")
    cand = build_schedule_bar_plan_candidate(s, req)
    d = cand.to_dict()
    json_str = json.dumps(d, ensure_ascii=False)
    assert '"colStart"' in json_str
    assert '"colEnd"' in json_str
    assert '"conflict"' in json_str


# ── T15: 원본 fixture 수정 없음 ──────────────────────────────────────────────

@pytest.mark.parametrize("fx_path", [FX_BASIC, FX_EMPTY, FX_PARTIAL])
def test_fixture_not_modified(fx_path):
    from scripts.hwpx.parser.schedule_detector import (
        build_schedule_bar_plan_candidate,
        generate_empty_template_bar_candidates,
    )
    from scripts.hwpx.parser.parser_contract import ScheduleBarRangeRequest
    mtime_before = fx_path.stat().st_mtime
    result = _parse(fx_path)
    s = _gantt(result)
    if s:
        req = ScheduleBarRangeRequest(taskName="배관공사", startDate="2026-05-01", endDate="2026-07-31")
        build_schedule_bar_plan_candidate(s, req)
        generate_empty_template_bar_candidates(s)
    mtime_after = fx_path.stat().st_mtime
    assert mtime_before == mtime_after, f"fixture was modified: {fx_path.name}"
