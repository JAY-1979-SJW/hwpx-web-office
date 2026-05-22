"""HWPX-SCHEDULE-STATUS-COLOR-POLICY-01 — 색상 정책 테스트.

apply_edit_plan / fill_schedule_bars 호출 없음 (read-only 정책 검증만).
원본 fixture 수정 없음.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]


# ── T01: import ──────────────────────────────────────────────────────────────

def test_color_policy_importable():
    from scripts.hwpx.pipeline.schedule_bar_color_policy import (
        get_color,
        get_entry,
        get_status_from_conflict,
        get_color_from_conflict,
        get_status_from_action,
        get_color_from_action,
        resolve_bar_color,
        is_auto_allowed_color,
        all_statuses,
        to_policy_dict,
    )
    assert callable(get_color)
    assert callable(resolve_bar_color)


# ── T02: 전체 상태 코드 8개 존재 ─────────────────────────────────────────────

def test_all_statuses_count():
    from scripts.hwpx.pipeline.schedule_bar_color_policy import all_statuses
    statuses = all_statuses()
    assert len(statuses) == 8
    for s in ("PLANNED", "IN_PROGRESS", "DONE", "DELAYED", "REVIEW", "BLOCKED", "TEMPLATE", "UNKNOWN"):
        assert s in statuses, f"missing status: {s}"


# ── T03: DONE 색상 = 92D050 ───────────────────────────────────────────────────

def test_done_color():
    from scripts.hwpx.pipeline.schedule_bar_color_policy import get_color
    assert get_color("DONE") == "92D050"


# ── T04: PLANNED 색상 = D9EAF7 ───────────────────────────────────────────────

def test_planned_color():
    from scripts.hwpx.pipeline.schedule_bar_color_policy import get_color
    assert get_color("PLANNED") == "D9EAF7"


# ── T05: IN_PROGRESS 색상 = FFF2CC ───────────────────────────────────────────

def test_in_progress_color():
    from scripts.hwpx.pipeline.schedule_bar_color_policy import get_color
    assert get_color("IN_PROGRESS") == "FFF2CC"


# ── T06: DELAYED 색상 = F4CCCC ───────────────────────────────────────────────

def test_delayed_color():
    from scripts.hwpx.pipeline.schedule_bar_color_policy import get_color
    assert get_color("DELAYED") == "F4CCCC"


# ── T07: REVIEW 색상 = FFE599 ────────────────────────────────────────────────

def test_review_color():
    from scripts.hwpx.pipeline.schedule_bar_color_policy import get_color
    assert get_color("REVIEW") == "FFE599"


# ── T08: BLOCKED 색상 = EA9999 ───────────────────────────────────────────────

def test_blocked_color():
    from scripts.hwpx.pipeline.schedule_bar_color_policy import get_color
    assert get_color("BLOCKED") == "EA9999"


# ── T09: TEMPLATE 색상 = D9D9D9 ──────────────────────────────────────────────

def test_template_color():
    from scripts.hwpx.pipeline.schedule_bar_color_policy import get_color
    assert get_color("TEMPLATE") == "D9D9D9"


# ── T10: 미정의 상태 → UNKNOWN 색상 반환 ─────────────────────────────────────

def test_unknown_status_fallback():
    from scripts.hwpx.pipeline.schedule_bar_color_policy import get_color
    result = get_color("NO_SUCH_STATUS")
    assert len(result) == 6


# ── T11: conflict → status 매핑 ──────────────────────────────────────────────

@pytest.mark.parametrize("conflict,expected_status", [
    ("no_conflict", "DONE"),
    ("replaces_existing_empty_template", "DONE"),
    ("overlaps_existing_bar", "REVIEW"),
    ("extends_existing_bar", "REVIEW"),
    ("unknown", "REVIEW"),
    ("outside_axis_range", "BLOCKED"),
])
def test_conflict_to_status(conflict, expected_status):
    from scripts.hwpx.pipeline.schedule_bar_color_policy import get_status_from_conflict
    assert get_status_from_conflict(conflict) == expected_status


# ── T12: conflict → color 직접 반환 ──────────────────────────────────────────

def test_conflict_to_color_no_conflict():
    from scripts.hwpx.pipeline.schedule_bar_color_policy import get_color_from_conflict
    assert get_color_from_conflict("no_conflict") == "92D050"


def test_conflict_to_color_overlaps():
    from scripts.hwpx.pipeline.schedule_bar_color_policy import get_color_from_conflict
    assert get_color_from_conflict("overlaps_existing_bar") == "FFE599"


# ── T13: action → status 매핑 ────────────────────────────────────────────────

@pytest.mark.parametrize("action,expected_status", [
    ("AUTO_PLAN_ALLOWED", "DONE"),
    ("REVIEW_REQUIRED", "REVIEW"),
    ("FAIL", "BLOCKED"),
])
def test_action_to_status(action, expected_status):
    from scripts.hwpx.pipeline.schedule_bar_color_policy import get_status_from_action
    assert get_status_from_action(action) == expected_status


# ── T14: resolve_bar_color — explicit 우선 ───────────────────────────────────

def test_resolve_explicit_color_priority():
    from scripts.hwpx.pipeline.schedule_bar_color_policy import resolve_bar_color
    result = resolve_bar_color(
        explicit_color="AABBCC",
        status="DELAYED",
        conflict="overlaps_existing_bar",
        action="REVIEW_REQUIRED",
    )
    assert result == "AABBCC"


# ── T15: resolve_bar_color — status 우선 (explicit 없을 때) ──────────────────

def test_resolve_status_priority():
    from scripts.hwpx.pipeline.schedule_bar_color_policy import resolve_bar_color
    result = resolve_bar_color(status="DELAYED", action="DONE")
    assert result == "F4CCCC"  # DELAYED


# ── T16: resolve_bar_color — conflict 우선 (status 없을 때) ──────────────────

def test_resolve_conflict_priority():
    from scripts.hwpx.pipeline.schedule_bar_color_policy import resolve_bar_color
    result = resolve_bar_color(conflict="no_conflict", action="REVIEW_REQUIRED")
    assert result == "92D050"  # no_conflict → DONE


# ── T17: resolve_bar_color — action 폴백 ─────────────────────────────────────

def test_resolve_action_fallback():
    from scripts.hwpx.pipeline.schedule_bar_color_policy import resolve_bar_color
    result = resolve_bar_color(action="AUTO_PLAN_ALLOWED")
    assert result == "92D050"


# ── T18: resolve_bar_color — 기본값 (모두 None) ───────────────────────────────

def test_resolve_default_fallback():
    from scripts.hwpx.pipeline.schedule_bar_color_policy import resolve_bar_color
    result = resolve_bar_color()
    assert result == "92D050"


# ── T19: autoAllowed 정책 ────────────────────────────────────────────────────

def test_auto_allowed_colors():
    from scripts.hwpx.pipeline.schedule_bar_color_policy import is_auto_allowed_color, _POLICY_TABLE
    for entry in _POLICY_TABLE:
        result = is_auto_allowed_color(entry.hex)
        assert result == entry.autoAllowed, f"autoAllowed mismatch for {entry.status}"


# ── T20: DELAYED / REVIEW / BLOCKED는 autoAllowed=False ──────────────────────

def test_non_auto_statuses():
    from scripts.hwpx.pipeline.schedule_bar_color_policy import get_entry
    for status in ("DELAYED", "REVIEW", "BLOCKED", "UNKNOWN"):
        entry = get_entry(status)
        assert entry is not None
        assert not entry.autoAllowed, f"{status} should not be autoAllowed"


# ── T21: to_policy_dict JSON 직렬화 ──────────────────────────────────────────

def test_policy_dict_json_serializable():
    from scripts.hwpx.pipeline.schedule_bar_color_policy import to_policy_dict
    d = to_policy_dict()
    json_str = json.dumps(d, ensure_ascii=False)
    assert "DONE" in json_str
    assert "92D050" in json_str
    assert "conflictMapping" in json_str
    assert "actionMapping" in json_str


# ── T22: plan_generator가 color_policy를 사용한다 ────────────────────────────

def test_plan_generator_uses_color_policy():
    import re
    src_path = PROJECT_ROOT / "scripts" / "hwpx" / "pipeline" / "schedule_bar_plan_generator.py"
    src = src_path.read_text(encoding="utf-8")
    assert "schedule_bar_color_policy" in src, "plan_generator must import color_policy"
    assert "resolve_bar_color" in src


# ── T23: plan_generator에 임시 색상 상수 없음 ────────────────────────────────

def test_no_hardcoded_color_constants_in_generator():
    import re
    src_path = PROJECT_ROOT / "scripts" / "hwpx" / "pipeline" / "schedule_bar_plan_generator.py"
    src = src_path.read_text(encoding="utf-8")
    # _DEFAULT_COLOR, _REVIEW_COLOR, _CONFLICT_COLOR, _STATE_COLORS 없어야 함
    assert "_DEFAULT_COLOR" not in src
    assert "_REVIEW_COLOR" not in src
    assert "_CONFLICT_COLOR" not in src
    assert "_STATE_COLORS" not in src


# ── T24: 회귀 — plan_generator 기존 기능 유지 ────────────────────────────────

def test_plan_generator_still_decides_action():
    import sys
    sys.path.insert(0, str(PROJECT_ROOT))
    from scripts.hwpx.pipeline.schedule_bar_plan_generator import decide_bar_plan_action
    from scripts.hwpx.parser.parser_contract import ScheduleBarPlanCandidate

    cand = ScheduleBarPlanCandidate(
        row=2, colStart=2, colEnd=4,
        conflict="no_conflict", existingBarType="",
        reviewRequired=False, reviewRequiredReason="",
        confidence=0.9,
    )
    decision = decide_bar_plan_action(cand)
    assert decision.action == "AUTO_PLAN_ALLOWED"
