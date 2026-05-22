"""HWPX-SCHEDULE-BAR-PLAN-GENERATOR-01 — BarPlanCandidate → edit plan 변환 테스트.

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


def _make_candidate(
    table_id="tbl0", row=2, col_start=2, col_end=4,
    conflict="no_conflict", review_required=False,
    review_reason=None, color=None, text="", text_at=None,
    confidence=0.95, existing_bar_type="",
):
    from scripts.hwpx.parser.parser_contract import ScheduleBarPlanCandidate
    return ScheduleBarPlanCandidate(
        tableId=table_id,
        row=row,
        taskName="테스트공종",
        colStart=col_start,
        colEnd=col_end,
        axisUnit="month",
        startLabel="5월",
        endLabel="7월",
        color=color,
        text=text,
        textAt=text_at,
        confidence=confidence,
        source="test",
        existingBarType=existing_bar_type,
        conflict=conflict,
        reviewRequired=review_required,
        reviewRequiredReason=review_reason,
        evidence=[],
        warnings=[],
    )


# ── T01: import ────────────────────────────────────────────────────────────────

def test_plan_generator_importable():
    from scripts.hwpx.pipeline.schedule_bar_plan_generator import (
        decide_bar_plan_action,
        convert_candidate_to_edit_plan_item,
        build_fill_schedule_bars_plan,
        build_fill_schedule_bars_plan_from_candidates,
        validate_schedule_bar_plan,
        summarize_schedule_bar_plan,
    )
    assert callable(decide_bar_plan_action)
    assert callable(build_fill_schedule_bars_plan)


# ── T02: empty_template → AUTO_PLAN_ALLOWED ────────────────────────────────────

def test_empty_template_candidate_auto_allowed():
    from scripts.hwpx.pipeline.schedule_bar_plan_generator import decide_bar_plan_action
    cand = _make_candidate(conflict="replaces_existing_empty_template", review_required=False)
    decision = decide_bar_plan_action(cand)
    assert decision.action == "AUTO_PLAN_ALLOWED"


# ── T03: text_full → REVIEW_REQUIRED ──────────────────────────────────────────

def test_text_full_candidate_review_required():
    from scripts.hwpx.pipeline.schedule_bar_plan_generator import decide_bar_plan_action
    cand = _make_candidate(
        conflict="overlaps_existing_bar",
        review_required=True,
        review_reason="overlaps_existing_bar",
        existing_bar_type="text_full",
    )
    decision = decide_bar_plan_action(cand)
    assert decision.action == "REVIEW_REQUIRED"


# ── T04: text_partial → REVIEW_REQUIRED ───────────────────────────────────────

def test_text_partial_candidate_review_required():
    from scripts.hwpx.pipeline.schedule_bar_plan_generator import decide_bar_plan_action
    cand = _make_candidate(
        conflict="extends_existing_bar",
        review_required=True,
        existing_bar_type="text_partial",
    )
    decision = decide_bar_plan_action(cand)
    assert decision.action == "REVIEW_REQUIRED"


# ── T05: outside_axis_range → FAIL ────────────────────────────────────────────

def test_outside_axis_range_fail():
    from scripts.hwpx.pipeline.schedule_bar_plan_generator import decide_bar_plan_action
    cand = _make_candidate(
        col_start=-1, col_end=-1,
        conflict="outside_axis_range",
    )
    decision = decide_bar_plan_action(cand)
    assert decision.action in ("FAIL", "REVIEW_REQUIRED")


# ── T06: candidate → fill_schedule_bars item 변환 ──────────────────────────────

def test_convert_candidate_to_edit_plan_item():
    from scripts.hwpx.pipeline.schedule_bar_plan_generator import convert_candidate_to_edit_plan_item
    cand = _make_candidate(text="배관공사", color="92D050")
    item = convert_candidate_to_edit_plan_item(cand, table_index=0)
    d = item.to_fill_plan_dict()
    assert d["task_row"] == cand.row
    assert d["start_col"] == cand.colStart
    assert d["end_col"] == cand.colEnd
    assert d["color"] == "92D050"
    assert "text" in d
    assert "text_at" in d
    assert "shrink_to_fit" in d


# ── T07: plan JSON 직렬화 ──────────────────────────────────────────────────────

def test_plan_json_serializable():
    from scripts.hwpx.pipeline.schedule_bar_plan_generator import build_fill_schedule_bars_plan
    cand = _make_candidate(conflict="no_conflict", text="배관공사")
    plan = build_fill_schedule_bars_plan(cand, table_index=0)
    d = plan.to_dict()
    json_str = json.dumps(d, ensure_ascii=False)
    assert "fill_schedule_bars" in json_str


# ── T08: default color 적용 ───────────────────────────────────────────────────

def test_default_color_applied():
    from scripts.hwpx.pipeline.schedule_bar_plan_generator import convert_candidate_to_edit_plan_item
    cand = _make_candidate(color=None, conflict="no_conflict")
    item = convert_candidate_to_edit_plan_item(cand)
    assert item.color == "92D050"


# ── T09: REVIEW_REQUIRED → review color ───────────────────────────────────────

def test_review_required_color():
    from scripts.hwpx.pipeline.schedule_bar_plan_generator import convert_candidate_to_edit_plan_item
    cand = _make_candidate(
        color=None,
        conflict="overlaps_existing_bar",
        review_required=True,
    )
    item = convert_candidate_to_edit_plan_item(cand)
    assert item.color == "FFE599"  # REVIEW 상태 색상 (color_policy: REVIEW=FFE599)


# ── T10: overwrite=false 기본 ─────────────────────────────────────────────────

def test_overwrite_false_default():
    from scripts.hwpx.pipeline.schedule_bar_plan_generator import convert_candidate_to_edit_plan_item
    cand = _make_candidate()
    item = convert_candidate_to_edit_plan_item(cand)
    assert item.overwrite is False


# ── T11: preserve_text=true 기본 ─────────────────────────────────────────────

def test_preserve_text_true_default():
    from scripts.hwpx.pipeline.schedule_bar_plan_generator import convert_candidate_to_edit_plan_item
    cand = _make_candidate()
    item = convert_candidate_to_edit_plan_item(cand)
    assert item.preserveText is True


# ── T12: multiple candidates plan ────────────────────────────────────────────

def test_multiple_candidates_plan():
    from scripts.hwpx.pipeline.schedule_bar_plan_generator import build_fill_schedule_bars_plan_from_candidates
    candidates = [
        _make_candidate(row=2, conflict="no_conflict"),
        _make_candidate(row=3, conflict="replaces_existing_empty_template"),
        _make_candidate(row=4, conflict="overlaps_existing_bar", review_required=True),
    ]
    plan = build_fill_schedule_bars_plan_from_candidates(candidates)
    assert len(plan.items) == 3
    assert plan.autoAllowedCount == 2
    assert plan.reviewRequiredCount == 1


# ── T13: validate PASS ────────────────────────────────────────────────────────

def test_validate_schedule_bar_plan_pass():
    from scripts.hwpx.pipeline.schedule_bar_plan_generator import (
        build_fill_schedule_bars_plan_from_candidates,
        validate_schedule_bar_plan,
    )
    candidates = [_make_candidate(row=2), _make_candidate(row=3)]
    plan = build_fill_schedule_bars_plan_from_candidates(candidates)
    result = validate_schedule_bar_plan(plan)
    assert result["status"] in ("PASS", "WARN")
    assert isinstance(result["issues"], list)


# ── T14: fixture별 plan decision 검증 ────────────────────────────────────────

@pytest.mark.parametrize("fx_path,expected_action", [
    (FX_EMPTY, "AUTO_PLAN_ALLOWED"),
    (FX_BASIC, "REVIEW_REQUIRED"),
])
def test_fixture_plan_decision(fx_path, expected_action):
    from scripts.hwpx.parser.schedule_detector import (
        generate_empty_template_bar_candidates,
        build_schedule_bar_plan_candidate,
    )
    from scripts.hwpx.parser.parser_contract import ScheduleBarRangeRequest
    from scripts.hwpx.pipeline.schedule_bar_plan_generator import decide_bar_plan_action

    result = _parse(fx_path)
    s = _gantt(result)
    assert s is not None

    if expected_action == "AUTO_PLAN_ALLOWED":
        candidates = generate_empty_template_bar_candidates(s)
        assert candidates
        decision = decide_bar_plan_action(candidates[0])
        assert decision.action == "AUTO_PLAN_ALLOWED"
    else:
        req = ScheduleBarRangeRequest(
            taskName="배관공사",
            startDate="2026-05-01",
            endDate="2026-07-31",
        )
        cand = build_schedule_bar_plan_candidate(s, req)
        decision = decide_bar_plan_action(cand)
        assert decision.action in ("REVIEW_REQUIRED", "AUTO_PLAN_ALLOWED", "FAIL")


# ── T15: apply_edit_plan 호출 없음 ────────────────────────────────────────────

def test_apply_edit_plan_not_called():
    import re
    src_path = Path(__file__).parents[1] / "scripts" / "hwpx" / "pipeline" / "schedule_bar_plan_generator.py"
    src = src_path.read_text(encoding="utf-8")
    pat = re.compile(r"(?<!#)\bapply_edit_plan\s*\(")
    assert not pat.search(src), "apply_edit_plan call found in plan generator"


# ── T16: 원본 fixture 수정 없음 ───────────────────────────────────────────────

@pytest.mark.parametrize("fx_path", [FX_BASIC, FX_EMPTY, FX_PARTIAL])
def test_fixture_not_modified(fx_path):
    from scripts.hwpx.parser.schedule_detector import generate_empty_template_bar_candidates
    from scripts.hwpx.pipeline.schedule_bar_plan_generator import build_fill_schedule_bars_plan_from_candidates

    mtime_before = fx_path.stat().st_mtime
    result = _parse(fx_path)
    s = _gantt(result)
    if s:
        candidates = generate_empty_template_bar_candidates(s)
        build_fill_schedule_bars_plan_from_candidates(candidates)
    mtime_after = fx_path.stat().st_mtime
    assert mtime_before == mtime_after, f"fixture was modified: {fx_path.name}"
