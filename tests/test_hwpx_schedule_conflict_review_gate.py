"""HWPX-SCHEDULE-CONFLICT-REVIEW-GATE-01 — 충돌 검토 게이트 테스트.

원본 fixture 수정 없음 (read-only).
apply_edit_plan / fill_schedule_bars / write_package 호출 없음.
게이트 판정 로직만 검증한다.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]

FIXTURE_DIR = PROJECT_ROOT / "tests" / "fixtures" / "hwpx" / "gantt"
FX_BASIC = FIXTURE_DIR / "fx_gantt_like_basic.hwpx"
FX_EMPTY = FIXTURE_DIR / "fx_gantt_like_template_empty.hwpx"
FX_PARTIAL = FIXTURE_DIR / "fx_gantt_like_partial_filled.hwpx"


def _parse(path: Path):
    import sys
    sys.path.insert(0, str(PROJECT_ROOT))
    from scripts.hwpx.parser.parser_engine import parse_hwpx_v2
    return parse_hwpx_v2(path)


def _gantt(result):
    return next((s for s in result.schedules if len(s.taskRows) >= 5), None)


def _make_review_plan_item(
    row: int = 2, col_start: int = 2, col_end: int = 4,
    review_required: bool = True, conflict: str = "overlaps_existing_bar",
    table_id: str = "tbl0",
):
    from scripts.hwpx.parser.parser_contract import ScheduleBarEditPlanItem
    return ScheduleBarEditPlanItem(
        table=0, tableId=table_id, taskRow=row,
        startCol=col_start, endCol=col_end,
        color="92D050", text="배관공사", textAt="center",
        shrinkToFit=True, preserveText=True, overwrite=False,
        conflict=conflict, confidence=0.7,
        sourceCandidateId=f"{table_id}_r{row}",
        reviewRequired=review_required,
        reviewRequiredReason=f"conflict={conflict}",
        evidence=[],
    )


def _make_auto_plan_item(row: int = 3, col_start: int = 2, col_end: int = 4):
    return _make_review_plan_item(row=row, review_required=False, conflict="no_conflict")


def _make_edit_plan(items):
    from scripts.hwpx.parser.parser_contract import ScheduleBarEditPlan
    auto = sum(1 for i in items if not i.reviewRequired)
    review = sum(1 for i in items if i.reviewRequired)
    return ScheduleBarEditPlan(
        tableId="tbl0", items=items,
        autoAllowedCount=auto, reviewRequiredCount=review,
    )


# ── T01: import ──────────────────────────────────────────────────────────────

def test_conflict_review_gate_importable():
    from scripts.hwpx.pipeline.conflict_review_gate import (
        build_review_list,
        apply_review_decisions,
        gate_all_approved,
        gate_all_rejected,
        validate_gate_output,
        summarize_gate_output,
    )
    assert callable(build_review_list)
    assert callable(apply_review_decisions)


# ── T02: REVIEW_REQUIRED → review list 분리 ───────────────────────────────────

def test_review_required_items_separated():
    from scripts.hwpx.pipeline.conflict_review_gate import build_review_list
    items = [_make_review_plan_item(), _make_auto_plan_item()]
    plan = _make_edit_plan(items)
    rl = build_review_list(plan)
    assert len(rl.items) == 1
    assert len(rl.autoAllowedItems) == 1


# ── T03: AUTO_PLAN_ALLOWED → autoAllowedItems ─────────────────────────────────

def test_auto_allowed_items_in_auto_list():
    from scripts.hwpx.pipeline.conflict_review_gate import build_review_list
    items = [_make_auto_plan_item(row=2), _make_auto_plan_item(row=3)]
    plan = _make_edit_plan(items)
    rl = build_review_list(plan)
    assert len(rl.items) == 0
    assert len(rl.autoAllowedItems) == 2


# ── T04: invalid coords → failedItems ────────────────────────────────────────

def test_invalid_coords_in_failed_items():
    from scripts.hwpx.pipeline.conflict_review_gate import build_review_list
    bad = _make_review_plan_item(col_start=-1, col_end=-1)
    plan = _make_edit_plan([bad])
    rl = build_review_list(plan)
    assert len(rl.failedItems) == 1
    assert len(rl.items) == 0


# ── T05: APPROVED 결정 → approvedItems ────────────────────────────────────────

def test_approved_decision_moves_to_approved():
    from scripts.hwpx.pipeline.conflict_review_gate import build_review_list, apply_review_decisions
    from scripts.hwpx.parser.parser_contract import ScheduleBarReviewDecision
    plan = _make_edit_plan([_make_review_plan_item()])
    rl = build_review_list(plan)
    item_id = rl.items[0].itemId
    decisions = [ScheduleBarReviewDecision(itemId=item_id, verdict="APPROVED")]
    output = apply_review_decisions(rl, decisions)
    assert len(output.approvedItems) == 1
    assert len(output.rejectedItems) == 0


# ── T06: REJECTED 결정 → rejectedItems ────────────────────────────────────────

def test_rejected_decision_moves_to_rejected():
    from scripts.hwpx.pipeline.conflict_review_gate import build_review_list, apply_review_decisions
    from scripts.hwpx.parser.parser_contract import ScheduleBarReviewDecision
    plan = _make_edit_plan([_make_review_plan_item()])
    rl = build_review_list(plan)
    item_id = rl.items[0].itemId
    decisions = [ScheduleBarReviewDecision(itemId=item_id, verdict="REJECTED")]
    output = apply_review_decisions(rl, decisions)
    assert len(output.rejectedItems) == 1
    assert len(output.approvedItems) == 0


# ── T07: DEFERRED 결정 → deferredItems ───────────────────────────────────────

def test_deferred_decision_moves_to_deferred():
    from scripts.hwpx.pipeline.conflict_review_gate import build_review_list, apply_review_decisions
    from scripts.hwpx.parser.parser_contract import ScheduleBarReviewDecision
    plan = _make_edit_plan([_make_review_plan_item()])
    rl = build_review_list(plan)
    item_id = rl.items[0].itemId
    decisions = [ScheduleBarReviewDecision(itemId=item_id, verdict="DEFERRED")]
    output = apply_review_decisions(rl, decisions)
    assert len(output.deferredItems) == 1


# ── T08: 결정 없음 → pendingItems ────────────────────────────────────────────

def test_no_decision_moves_to_pending():
    from scripts.hwpx.pipeline.conflict_review_gate import build_review_list, apply_review_decisions
    plan = _make_edit_plan([_make_review_plan_item()])
    rl = build_review_list(plan)
    output = apply_review_decisions(rl, [])
    assert len(output.pendingItems) == 1
    assert len(output.approvedItems) == 0


# ── T09: AUTO item은 decisions 없이도 approved에 포함 ─────────────────────────

def test_auto_items_always_in_approved():
    from scripts.hwpx.pipeline.conflict_review_gate import build_review_list, apply_review_decisions
    items = [_make_auto_plan_item(row=2), _make_review_plan_item(row=3)]
    plan = _make_edit_plan(items)
    rl = build_review_list(plan)
    output = apply_review_decisions(rl, [])
    assert len(output.approvedItems) == 1  # auto item
    assert len(output.pendingItems) == 1   # review item without decision


# ── T10: gate_all_approved ────────────────────────────────────────────────────

def test_gate_all_approved():
    from scripts.hwpx.pipeline.conflict_review_gate import build_review_list, gate_all_approved
    items = [_make_review_plan_item(row=2), _make_review_plan_item(row=3)]
    plan = _make_edit_plan(items)
    rl = build_review_list(plan)
    output = gate_all_approved(rl)
    assert len(output.approvedItems) == 2
    assert len(output.pendingItems) == 0


# ── T11: gate_all_rejected ────────────────────────────────────────────────────

def test_gate_all_rejected():
    from scripts.hwpx.pipeline.conflict_review_gate import build_review_list, gate_all_rejected
    items = [_make_review_plan_item(row=2), _make_review_plan_item(row=3)]
    plan = _make_edit_plan(items)
    rl = build_review_list(plan)
    output = gate_all_rejected(rl)
    assert len(output.rejectedItems) == 2
    assert len(output.approvedItems) == 0


# ── T12: to_fill_plan_dict approved만 포함 ───────────────────────────────────

def test_to_fill_plan_dict_approved_only():
    from scripts.hwpx.pipeline.conflict_review_gate import build_review_list, apply_review_decisions
    from scripts.hwpx.parser.parser_contract import ScheduleBarReviewDecision
    items = [_make_review_plan_item(row=2), _make_review_plan_item(row=3)]
    plan = _make_edit_plan(items)
    rl = build_review_list(plan)
    item_id_0 = rl.items[0].itemId
    decisions = [ScheduleBarReviewDecision(itemId=item_id_0, verdict="APPROVED")]
    output = apply_review_decisions(rl, decisions)
    fill_dict = output.to_fill_plan_dict()
    assert "fill_schedule_bars" in fill_dict
    assert len(fill_dict["fill_schedule_bars"]) == 1


# ── T13: gate output JSON 직렬화 ─────────────────────────────────────────────

def test_gate_output_json_serializable():
    from scripts.hwpx.pipeline.conflict_review_gate import build_review_list, gate_all_approved
    plan = _make_edit_plan([_make_review_plan_item(), _make_auto_plan_item()])
    rl = build_review_list(plan)
    output = gate_all_approved(rl)
    d = output.to_dict()
    json_str = json.dumps(d, ensure_ascii=False)
    assert "fill_schedule_bars" in json_str
    assert "approvedCount" in json_str


# ── T14: validate_gate_output PASS ───────────────────────────────────────────

def test_validate_gate_output_pass():
    from scripts.hwpx.pipeline.conflict_review_gate import (
        build_review_list, gate_all_approved, validate_gate_output,
    )
    plan = _make_edit_plan([_make_auto_plan_item()])
    rl = build_review_list(plan)
    output = gate_all_approved(rl)
    result = validate_gate_output(output)
    assert result["status"] in ("PASS", "WARN")


# ── T15: fixture(basic) → REVIEW_REQUIRED → review list 생성 ─────────────────

def test_basic_fixture_produces_review_list():
    from scripts.hwpx.parser.parser_contract import ScheduleBarRangeRequest
    from scripts.hwpx.parser.schedule_detector import build_schedule_bar_plan_candidate
    from scripts.hwpx.pipeline.schedule_bar_plan_generator import build_fill_schedule_bars_plan
    from scripts.hwpx.pipeline.conflict_review_gate import build_review_list

    result = _parse(FX_BASIC)
    s = _gantt(result)
    assert s is not None
    t = next(t for t in result.tables if t.tableId == s.tableId)

    req = ScheduleBarRangeRequest(
        taskName="배관공사", startDate="2026-05-01", endDate="2026-07-31",
    )
    cand = build_schedule_bar_plan_candidate(s, req)
    plan = build_fill_schedule_bars_plan(cand, table_index=t.tableIndex)
    rl = build_review_list(plan)

    # basic fixture는 기존 막대 있으므로 review item 있거나 auto item만 있어야 함
    total = len(rl.items) + len(rl.autoAllowedItems) + len(rl.failedItems)
    assert total >= 1


# ── T16: apply_edit_plan / fill_schedule_bars 호출 없음 ───────────────────────

def test_no_apply_or_fill_calls_in_gate():
    import re
    src_path = PROJECT_ROOT / "scripts" / "hwpx" / "pipeline" / "conflict_review_gate.py"
    src = src_path.read_text(encoding="utf-8")
    apply_pat = re.compile(r"(?<!#)\bapply_edit_plan\s*\(")
    fill_pat = re.compile(r"(?<!#)\bfill_schedule_bars\s*\(")
    assert not apply_pat.search(src), "apply_edit_plan call found in gate"
    assert not fill_pat.search(src), "fill_schedule_bars call found in gate"
