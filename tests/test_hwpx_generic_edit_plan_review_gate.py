"""HWPX-EDIT-PLAN-REVIEW-GATE-01 테스트.

REVIEW_REQUIRED operation에 대한 사람 승인/반려/보류 게이트 검증.
writer 호출 없음, output HWPX 미생성, 원본 무수정.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

METADATA_FORM = PROJECT_ROOT / "tests/fixtures/hwpx/corpus/fx_metadata_form.hwpx"


@pytest.fixture(scope="module")
def contract():
    from hwpx.pipeline import generic_edit_plan_contract as c
    return c


@pytest.fixture(scope="module")
def dry_run():
    from hwpx.pipeline import generic_edit_plan_dry_run as d
    return d


@pytest.fixture(scope="module")
def review_gate():
    from hwpx.pipeline import generic_edit_plan_review_gate as g
    return g


@pytest.fixture(scope="module")
def parsed_metadata():
    from hwpx.parser import parse_hwpx_v2
    return parse_hwpx_v2(METADATA_FORM)


def _first_text_cell(parsed):
    for t in parsed.tables:
        for c in t.cells:
            if c.normalizedText:
                return t.tableId, c
    return None, None


def _make_decision(plan_id, op_id, decision, reviewer="reviewer-1",
                     reason="checked", dec_id=None, decided_at="2026-05-18T01:00:00Z"):
    return {
        "decisionId": dec_id or f"dec-{op_id}",
        "planId": plan_id,
        "operationId": op_id,
        "reviewer": reviewer,
        "decision": decision,
        "reason": reason,
        "decidedAt": decided_at,
    }


def _make_fill_color_plan(contract, t_id, cell, created_by="ai"):
    plan = contract.empty_plan_skeleton(
        plan_id="plan-rg-1",
        source_doc_hash="sha256:abc",
        created_by=created_by,
        created_at="2026-05-18T00:00:00Z",
    )
    plan["operations"] = [{
        "operationId": "op-fill-1",
        "operationType": "setCellFillColor",
        "target": {"tableId": t_id, "row": cell.row, "col": cell.col},
        "value": "#FFFF00",
        "preserveStyle": True,
        "expectedBefore": cell.fillColor,
        "riskLevel": "low",
        "requiresReview": False,
        "reason": "highlight",
    }]
    return plan


def _make_blocked_plan(contract):
    plan = contract.empty_plan_skeleton(
        plan_id="plan-rg-blk",
        source_doc_hash="sha256:abc",
        created_by="ai",
        created_at="2026-05-18T00:00:00Z",
    )
    plan["operations"] = [{
        "operationId": "op-move-1",
        "operationType": "moveObject",
        "target": {"objectId": "obj-x"},
        "value": None,
        "preserveStyle": True,
        "expectedBefore": None,
        "riskLevel": "high",
        "requiresReview": True,
        "reason": "ai move",
    }]
    return plan


# ── T01: APPROVE → approvedOps + READY_AFTER_REVIEW ───────────────────────────

def test_review_approve_moves_to_approved(contract, dry_run, review_gate, parsed_metadata):
    t_id, cell = _first_text_cell(parsed_metadata)
    plan = _make_fill_color_plan(contract, t_id, cell)
    dr = dry_run.dry_run_edit_plan(plan, parsed_metadata)
    assert "op-fill-1" in dr.reviewRequiredOps

    res = review_gate.apply_review_decisions(
        dr, [_make_decision(plan["planId"], "op-fill-1", "APPROVE")],
    )
    assert res.gateVerdict == "READY_AFTER_REVIEW"
    assert res.approvedOps == ["op-fill-1"]
    assert res.rejectedOps == []
    assert res.heldOps == []
    assert res.pendingOps == []


# ── T02: REJECT → REJECTED_BY_REVIEW ──────────────────────────────────────────

def test_review_reject_moves_to_rejected(contract, dry_run, review_gate, parsed_metadata):
    t_id, cell = _first_text_cell(parsed_metadata)
    plan = _make_fill_color_plan(contract, t_id, cell)
    dr = dry_run.dry_run_edit_plan(plan, parsed_metadata)
    res = review_gate.apply_review_decisions(
        dr, [_make_decision(plan["planId"], "op-fill-1", "REJECT", reason="not now")],
    )
    assert res.gateVerdict == "REJECTED_BY_REVIEW"
    assert res.rejectedOps == ["op-fill-1"]
    assert res.approvedOps == []


# ── T03: HOLD → HELD_FOR_REVIEW ───────────────────────────────────────────────

def test_review_hold_moves_to_held(contract, dry_run, review_gate, parsed_metadata):
    t_id, cell = _first_text_cell(parsed_metadata)
    plan = _make_fill_color_plan(contract, t_id, cell)
    dr = dry_run.dry_run_edit_plan(plan, parsed_metadata)
    res = review_gate.apply_review_decisions(
        dr, [_make_decision(plan["planId"], "op-fill-1", "HOLD", reason="check tomorrow")],
    )
    assert res.gateVerdict == "HELD_FOR_REVIEW"
    assert res.heldOps == ["op-fill-1"]


# ── T04: blocked op은 APPROVE해도 blocked 유지 ────────────────────────────────

def test_blocked_op_cannot_be_approved(contract, dry_run, review_gate, parsed_metadata):
    plan = _make_blocked_plan(contract)
    dr = dry_run.dry_run_edit_plan(plan, parsed_metadata)
    assert "op-move-1" in dr.blockedOps

    res = review_gate.apply_review_decisions(
        dr, [_make_decision(plan["planId"], "op-move-1", "APPROVE",
                              reason="please allow")],
    )
    # decision은 부적합으로 거부, blocked 우회 불가
    assert res.gateVerdict == "BLOCKED_INVALID_DECISIONS"
    assert any(f.code == "DECISION_ON_BLOCKED_OP" for f in res.findings)
    assert "op-move-1" not in res.approvedOps
    assert "op-move-1" in res.blockedOps


# ── T05: 필수 필드 누락 → BLOCKED_INVALID_DECISIONS ───────────────────────────

@pytest.mark.parametrize("missing_field", [
    "decisionId", "planId", "operationId",
    "reviewer", "decision", "reason", "decidedAt",
])
def test_missing_decision_field_blocks(contract, dry_run, review_gate,
                                            parsed_metadata, missing_field):
    t_id, cell = _first_text_cell(parsed_metadata)
    plan = _make_fill_color_plan(contract, t_id, cell)
    dr = dry_run.dry_run_edit_plan(plan, parsed_metadata)
    d = _make_decision(plan["planId"], "op-fill-1", "APPROVE")
    d[missing_field] = ""
    res = review_gate.apply_review_decisions(dr, [d])
    assert res.gateVerdict == "BLOCKED_INVALID_DECISIONS"
    assert any(f.code == "DECISION_MISSING_FIELD" and f.detail.endswith(missing_field)
                for f in res.findings)


def test_invalid_decision_value_blocks(contract, dry_run, review_gate, parsed_metadata):
    t_id, cell = _first_text_cell(parsed_metadata)
    plan = _make_fill_color_plan(contract, t_id, cell)
    dr = dry_run.dry_run_edit_plan(plan, parsed_metadata)
    d = _make_decision(plan["planId"], "op-fill-1", "MAYBE_LATER")
    res = review_gate.apply_review_decisions(dr, [d])
    assert res.gateVerdict == "BLOCKED_INVALID_DECISIONS"
    assert any(f.code == "DECISION_VALUE_INVALID" for f in res.findings)


# ── T06: operationId 불일치 / planId 불일치 ───────────────────────────────────

def test_unknown_operation_id_blocks(contract, dry_run, review_gate, parsed_metadata):
    t_id, cell = _first_text_cell(parsed_metadata)
    plan = _make_fill_color_plan(contract, t_id, cell)
    dr = dry_run.dry_run_edit_plan(plan, parsed_metadata)
    d = _make_decision(plan["planId"], "op-does-not-exist", "APPROVE")
    res = review_gate.apply_review_decisions(dr, [d])
    assert res.gateVerdict == "BLOCKED_INVALID_DECISIONS"
    assert any(f.code == "DECISION_UNKNOWN_OP" for f in res.findings)


def test_plan_id_mismatch_blocks(contract, dry_run, review_gate, parsed_metadata):
    t_id, cell = _first_text_cell(parsed_metadata)
    plan = _make_fill_color_plan(contract, t_id, cell)
    dr = dry_run.dry_run_edit_plan(plan, parsed_metadata)
    d = _make_decision("plan-different", "op-fill-1", "APPROVE")
    res = review_gate.apply_review_decisions(dr, [d])
    assert res.gateVerdict == "BLOCKED_INVALID_DECISIONS"
    assert any(f.code == "DECISION_PLAN_ID_MISMATCH" for f in res.findings)


# ── T07: 모든 review op 승인 → READY_AFTER_REVIEW ─────────────────────────────

def test_all_reviews_approved_ready(contract, dry_run, review_gate, parsed_metadata):
    t_id, cell = _first_text_cell(parsed_metadata)
    plan = contract.empty_plan_skeleton("plan-multi", "sha:abc", "ai",
                                           "2026-05-18T00:00:00Z")
    plan["operations"] = [
        {
            "operationId": "op-fill-A",
            "operationType": "setCellFillColor",
            "target": {"tableId": t_id, "row": cell.row, "col": cell.col},
            "value": "#FFFF00",
            "preserveStyle": True,
            "expectedBefore": cell.fillColor,
            "riskLevel": "low",
            "requiresReview": False,
            "reason": "highlight A",
        },
        {
            "operationId": "op-fill-B",
            "operationType": "setCellTextStyle",
            "target": {"tableId": t_id, "row": cell.row, "col": cell.col},
            "value": {"bold": True},
            "preserveStyle": True,
            "expectedBefore": {"bold": cell.bold, "italic": cell.italic,
                                "underline": cell.underline,
                                "textColor": cell.textColor},
            "riskLevel": "low",
            "requiresReview": False,
            "reason": "bold B",
        },
    ]
    dr = dry_run.dry_run_edit_plan(plan, parsed_metadata)
    assert set(dr.reviewRequiredOps) == {"op-fill-A", "op-fill-B"}

    res = review_gate.apply_review_decisions(dr, [
        _make_decision(plan["planId"], "op-fill-A", "APPROVE"),
        _make_decision(plan["planId"], "op-fill-B", "APPROVE"),
    ])
    assert res.gateVerdict == "READY_AFTER_REVIEW"
    assert set(res.approvedOps) == {"op-fill-A", "op-fill-B"}


# ── T08: 일부 HOLD → HELD_FOR_REVIEW ──────────────────────────────────────────

def test_partial_hold_results_in_held(contract, dry_run, review_gate, parsed_metadata):
    t_id, cell = _first_text_cell(parsed_metadata)
    plan = contract.empty_plan_skeleton("plan-hold", "sha:abc", "ai", "t")
    plan["operations"] = [
        {**_make_fill_color_plan(contract, t_id, cell)["operations"][0],
          "operationId": "op-A"},
        {**_make_fill_color_plan(contract, t_id, cell)["operations"][0],
          "operationId": "op-B"},
    ]
    dr = dry_run.dry_run_edit_plan(plan, parsed_metadata)
    res = review_gate.apply_review_decisions(dr, [
        _make_decision(plan["planId"], "op-A", "APPROVE"),
        _make_decision(plan["planId"], "op-B", "HOLD"),
    ])
    assert res.gateVerdict == "HELD_FOR_REVIEW"
    assert res.heldOps == ["op-B"]


# ── T09: 일부 REJECT → REJECTED_BY_REVIEW ─────────────────────────────────────

def test_partial_reject_results_in_rejected(contract, dry_run, review_gate, parsed_metadata):
    t_id, cell = _first_text_cell(parsed_metadata)
    plan = contract.empty_plan_skeleton("plan-rej", "sha:abc", "ai", "t")
    plan["operations"] = [
        {**_make_fill_color_plan(contract, t_id, cell)["operations"][0],
          "operationId": "op-A"},
        {**_make_fill_color_plan(contract, t_id, cell)["operations"][0],
          "operationId": "op-B"},
    ]
    dr = dry_run.dry_run_edit_plan(plan, parsed_metadata)
    res = review_gate.apply_review_decisions(dr, [
        _make_decision(plan["planId"], "op-A", "APPROVE"),
        _make_decision(plan["planId"], "op-B", "REJECT"),
    ])
    assert res.gateVerdict == "REJECTED_BY_REVIEW"
    assert res.rejectedOps == ["op-B"]


# ── T10: createdBy manual/ai/system 동일 결과 ─────────────────────────────────

@pytest.mark.parametrize("cb", ["manual", "ai", "system"])
def test_created_by_does_not_change_gate_result(contract, dry_run, review_gate,
                                                     parsed_metadata, cb):
    t_id, cell = _first_text_cell(parsed_metadata)
    plan = _make_fill_color_plan(contract, t_id, cell, created_by=cb)
    dr = dry_run.dry_run_edit_plan(plan, parsed_metadata)
    res = review_gate.apply_review_decisions(
        dr, [_make_decision(plan["planId"], "op-fill-1", "APPROVE")],
    )
    assert res.gateVerdict == "READY_AFTER_REVIEW"
    assert res.approvedOps == ["op-fill-1"]


# ── T11: writer/output/원본 불변식 ────────────────────────────────────────────

def test_review_gate_does_not_touch_files(contract, dry_run, review_gate,
                                                parsed_metadata, tmp_path):
    sha_before = hashlib.sha256(METADATA_FORM.read_bytes()).hexdigest()
    mtime_before = METADATA_FORM.stat().st_mtime
    files_before = sorted(p.name for p in tmp_path.iterdir())

    t_id, cell = _first_text_cell(parsed_metadata)
    plan = _make_fill_color_plan(contract, t_id, cell)
    dr = dry_run.dry_run_edit_plan(plan, parsed_metadata)
    res = review_gate.apply_review_decisions(
        dr, [_make_decision(plan["planId"], "op-fill-1", "APPROVE")],
    )

    sha_after = hashlib.sha256(METADATA_FORM.read_bytes()).hexdigest()
    mtime_after = METADATA_FORM.stat().st_mtime
    files_after = sorted(p.name for p in tmp_path.iterdir())

    assert sha_before == sha_after
    assert mtime_before == mtime_after
    assert files_before == files_after
    assert res.writerCalled is False
    assert res.outputCreated is False
    assert res.originalUnmodified is True


# ── T12: pending → PENDING_REVIEW + audit log ─────────────────────────────────

def test_missing_decision_results_in_pending(contract, dry_run, review_gate, parsed_metadata):
    t_id, cell = _first_text_cell(parsed_metadata)
    plan = _make_fill_color_plan(contract, t_id, cell)
    dr = dry_run.dry_run_edit_plan(plan, parsed_metadata)
    res = review_gate.apply_review_decisions(dr, [])
    assert res.gateVerdict == "PENDING_REVIEW"
    assert res.pendingOps == ["op-fill-1"]
    # audit log entry 존재
    audit_for_op = [a for a in res.auditLog if a.operationId == "op-fill-1"]
    assert len(audit_for_op) == 1
    assert audit_for_op[0].bucketBefore == "review"
    assert audit_for_op[0].bucketAfter == "pending"


# ── T13: audit log에 reviewer/reason/decidedAt 보존 ───────────────────────────

def test_audit_log_preserves_decision_metadata(contract, dry_run, review_gate, parsed_metadata):
    t_id, cell = _first_text_cell(parsed_metadata)
    plan = _make_fill_color_plan(contract, t_id, cell)
    dr = dry_run.dry_run_edit_plan(plan, parsed_metadata)
    res = review_gate.apply_review_decisions(dr, [
        _make_decision(plan["planId"], "op-fill-1", "APPROVE",
                          reviewer="alice", reason="ok by site mgr",
                          decided_at="2026-05-18T02:30:00Z"),
    ])
    log = [a for a in res.auditLog if a.operationId == "op-fill-1"][0]
    assert log.reviewer == "alice"
    assert log.reason == "ok by site mgr"
    assert log.decidedAt == "2026-05-18T02:30:00Z"
    assert log.decision == "APPROVE"
    assert log.bucketBefore == "review"
    assert log.bucketAfter == "approved"
    # 원 decision 원문도 보존
    assert any(d["operationId"] == "op-fill-1" for d in res.originalDecisions)


# ── T14: 중복 decisionId / 중복 operationId 차단 ──────────────────────────────

def test_duplicate_decision_for_op_blocks(contract, dry_run, review_gate, parsed_metadata):
    t_id, cell = _first_text_cell(parsed_metadata)
    plan = _make_fill_color_plan(contract, t_id, cell)
    dr = dry_run.dry_run_edit_plan(plan, parsed_metadata)
    res = review_gate.apply_review_decisions(dr, [
        _make_decision(plan["planId"], "op-fill-1", "APPROVE", dec_id="d-1"),
        _make_decision(plan["planId"], "op-fill-1", "REJECT", dec_id="d-2"),
    ])
    assert res.gateVerdict == "BLOCKED_INVALID_DECISIONS"
    assert any(f.code == "DECISION_DUPLICATE_OP" for f in res.findings)


def test_duplicate_decision_id_blocks(contract, dry_run, review_gate, parsed_metadata):
    t_id, cell = _first_text_cell(parsed_metadata)
    plan = contract.empty_plan_skeleton("plan-dup-id", "sha:abc", "ai", "t")
    plan["operations"] = [
        {**_make_fill_color_plan(contract, t_id, cell)["operations"][0],
          "operationId": "op-A"},
        {**_make_fill_color_plan(contract, t_id, cell)["operations"][0],
          "operationId": "op-B"},
    ]
    dr = dry_run.dry_run_edit_plan(plan, parsed_metadata)
    res = review_gate.apply_review_decisions(dr, [
        _make_decision(plan["planId"], "op-A", "APPROVE", dec_id="d-same"),
        _make_decision(plan["planId"], "op-B", "APPROVE", dec_id="d-same"),
    ])
    assert res.gateVerdict == "BLOCKED_INVALID_DECISIONS"
    assert any(f.code == "DECISION_DUPLICATE_ID" for f in res.findings)
