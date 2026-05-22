"""HWPX-EDIT-PLAN-PIPELINE-INTEGRATION-AUDIT-01

5단계 파이프라인 통합 감사:
  contract → dry-run → review gate → writer adapter → executor no-op

writer 호출 0, output 생성 0, 원본 수정 0 불변식을 종단까지 보장.
planId / operationId / expectedBefore / sourceDocumentHash 일관성 보장.
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
def stages():
    from hwpx.pipeline import (
        generic_edit_plan_contract as c,
        generic_edit_plan_dry_run as d,
        generic_edit_plan_review_gate as g,
        generic_edit_plan_writer_adapter as a,
        generic_edit_plan_writer_executor_noop as e,
    )
    return {"contract": c, "dry_run": d, "gate": g, "adapter": a, "executor": e}


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


def _make_plan(stages, ops, created_by="ai", plan_id="plan-itg",
                 source_hash="sha256:abc"):
    c = stages["contract"]
    plan = c.empty_plan_skeleton(
        plan_id=plan_id, source_doc_hash=source_hash,
        created_by=created_by, created_at="2026-05-18T10:00:00Z",
    )
    plan["operations"] = ops
    return plan


def _set_cell_text_op(t_id, cell, op_id="op-text",
                         expected=None, value="NEW"):
    return {
        "operationId": op_id,
        "operationType": "setCellText",
        "target": {"tableId": t_id, "row": cell.row, "col": cell.col},
        "value": value,
        "preserveStyle": True,
        "expectedBefore": expected if expected is not None
                            else (cell.normalizedText or cell.text),
        "riskLevel": "low",
        "requiresReview": False,
        "reason": "test",
    }


def _set_fill_color_op(t_id, cell, op_id="op-fill", value="#FFFF00"):
    return {
        "operationId": op_id,
        "operationType": "setCellFillColor",
        "target": {"tableId": t_id, "row": cell.row, "col": cell.col},
        "value": value,
        "preserveStyle": True,
        "expectedBefore": cell.fillColor,
        "riskLevel": "low",
        "requiresReview": False,
        "reason": "highlight",
    }


def _move_object_op(op_id="op-move"):
    return {
        "operationId": op_id,
        "operationType": "moveObject",
        "target": {"objectId": "obj-x"},
        "value": None,
        "preserveStyle": True,
        "expectedBefore": None,
        "riskLevel": "high",
        "requiresReview": True,
        "reason": "ai move",
    }


def _decision(plan_id, op_id, decision, reviewer="alice"):
    return {
        "decisionId": f"d-{op_id}",
        "planId": plan_id,
        "operationId": op_id,
        "reviewer": reviewer,
        "decision": decision,
        "reason": "ok",
        "decidedAt": "2026-05-18T11:00:00Z",
    }


def _run_pipeline(stages, plan, decisions, parsed):
    """5단계를 한 번에 실행하여 dr / gate / adapter / executor 결과 반환."""
    dr = stages["dry_run"].dry_run_edit_plan(plan, parsed)
    gate = stages["gate"].apply_review_decisions(dr, decisions)
    wcp = stages["adapter"].build_writer_call_plan(plan, dr, gate)
    exe = stages["executor"].execute_writer_call_plan_noop(wcp)
    return {"dr": dr, "gate": gate, "wcp": wcp, "exe": exe}


# ── T01: AUTO 경로 ────────────────────────────────────────────────────────────

def test_auto_path_pipeline_passes_end_to_end(stages, parsed_metadata):
    t_id, cell = _first_text_cell(parsed_metadata)
    plan = _make_plan(stages, [_set_cell_text_op(t_id, cell)])
    r = _run_pipeline(stages, plan, [], parsed_metadata)
    assert r["dr"].verdict == "PASS_AUTO_ALLOWED"
    # gate는 review op 없으면 READY_AFTER_REVIEW (vacuously true)
    assert r["gate"].gateVerdict == "READY_AFTER_REVIEW"
    assert r["wcp"].verdict == "READY_FOR_WRITER"
    assert r["exe"].verdict == "PASS_NOOP_EXECUTOR_READY"
    assert r["exe"].readyForExecution is True


# ── T02: REVIEW 승인 경로 ─────────────────────────────────────────────────────

def test_review_approve_path_passes_end_to_end(stages, parsed_metadata):
    t_id, cell = _first_text_cell(parsed_metadata)
    plan = _make_plan(stages, [_set_fill_color_op(t_id, cell)])
    r = _run_pipeline(stages, plan,
                         [_decision(plan["planId"], "op-fill", "APPROVE")],
                         parsed_metadata)
    assert r["dr"].verdict == "REVIEW_REQUIRED"
    assert r["gate"].gateVerdict == "READY_AFTER_REVIEW"
    assert r["wcp"].verdict == "READY_FOR_WRITER"
    assert r["exe"].verdict == "PASS_NOOP_EXECUTOR_READY"
    # readback 권장 flag 전달
    assert r["exe"].readbackRequired is True


# ── T03: REVIEW 반려 경로 ─────────────────────────────────────────────────────

def test_review_reject_path_blocks_writer(stages, parsed_metadata):
    t_id, cell = _first_text_cell(parsed_metadata)
    plan = _make_plan(stages, [_set_fill_color_op(t_id, cell)])
    r = _run_pipeline(stages, plan,
                         [_decision(plan["planId"], "op-fill", "REJECT")],
                         parsed_metadata)
    assert r["gate"].gateVerdict == "REJECTED_BY_REVIEW"
    assert r["wcp"].readyForWriter is False
    assert r["wcp"].writerCalls == []
    assert r["exe"].verdict == "BLOCKED_NOT_READY_FOR_WRITER"
    assert r["exe"].readyForExecution is False


# ── T04: REVIEW 보류 경로 ─────────────────────────────────────────────────────

def test_review_hold_path_blocks_writer(stages, parsed_metadata):
    t_id, cell = _first_text_cell(parsed_metadata)
    plan = _make_plan(stages, [_set_fill_color_op(t_id, cell)])
    r = _run_pipeline(stages, plan,
                         [_decision(plan["planId"], "op-fill", "HOLD")],
                         parsed_metadata)
    assert r["gate"].gateVerdict == "HELD_FOR_REVIEW"
    assert r["wcp"].readyForWriter is False
    assert r["exe"].verdict == "BLOCKED_NOT_READY_FOR_WRITER"


# ── T05: BLOCKED 경로 — 모든 단계에서 차단, 우회 불가 ─────────────────────────

def test_blocked_op_cannot_be_bypassed_anywhere(stages, parsed_metadata):
    plan = _make_plan(stages, [_move_object_op()])
    r = _run_pipeline(stages, plan, [], parsed_metadata)
    assert r["dr"].verdict == "BLOCKED_UNSAFE"
    assert "op-move" in r["dr"].blockedOps
    # 게이트에서 APPROVE 시도해도 BLOCKED_INVALID_DECISIONS
    r2 = _run_pipeline(stages, plan,
                          [_decision(plan["planId"], "op-move", "APPROVE")],
                          parsed_metadata)
    assert r2["gate"].gateVerdict == "BLOCKED_INVALID_DECISIONS"
    assert "op-move" not in r2["gate"].approvedOps
    # 위조된 gate dict로 직접 adapter를 호출해도 거부
    fake_gate = {
        "gateVerdict": "READY_AFTER_REVIEW",
        "approvedOps": ["op-move"],
        "auditLog": [{"operationId": "op-move", "reviewer": "evil",
                       "decision": "APPROVE"}],
    }
    wcp = stages["adapter"].build_writer_call_plan(plan, r["dr"], fake_gate)
    exe = stages["executor"].execute_writer_call_plan_noop(wcp)
    assert wcp.writerCalls == []
    assert exe.verdict == "BLOCKED_NOT_READY_FOR_WRITER"


# ── T06: expectedBefore mismatch는 단일 단계가 아니라도 자동 통과 안 됨 ──────

def test_expected_before_mismatch_demotes_through_pipeline(stages, parsed_metadata):
    t_id, cell = _first_text_cell(parsed_metadata)
    op = _set_cell_text_op(t_id, cell, expected="WRONG_PREVIOUS_VALUE")
    plan = _make_plan(stages, [op])
    # 결정 없음 → review op으로 강등 → PENDING_REVIEW → adapter/executor 차단
    r = _run_pipeline(stages, plan, [], parsed_metadata)
    assert r["dr"].verdict == "REVIEW_REQUIRED"
    assert r["gate"].gateVerdict == "PENDING_REVIEW"
    assert r["wcp"].readyForWriter is False
    assert r["exe"].verdict == "BLOCKED_NOT_READY_FOR_WRITER"


# ── T07: sourceDocumentHash 누락 → 어디에서든 차단 ────────────────────────────

def test_source_document_hash_missing_blocks_pipeline(stages, parsed_metadata):
    t_id, cell = _first_text_cell(parsed_metadata)
    plan = _make_plan(stages, [_set_cell_text_op(t_id, cell)], source_hash="")
    r = _run_pipeline(stages, plan, [], parsed_metadata)
    # contract 단계에서 BLOCKED_INVALID_PLAN
    assert r["dr"].verdict == "BLOCKED_INVALID_PLAN"
    assert r["wcp"].readyForWriter is False
    assert r["exe"].verdict == "BLOCKED_NOT_READY_FOR_WRITER"


# ── T08: manual / ai / system 동등성 ──────────────────────────────────────────

@pytest.mark.parametrize("cb", ["manual", "ai", "system"])
def test_pipeline_is_identical_across_created_by(stages, parsed_metadata, cb):
    t_id, cell = _first_text_cell(parsed_metadata)
    plan = _make_plan(stages, [_set_cell_text_op(t_id, cell)], created_by=cb)
    r = _run_pipeline(stages, plan, [], parsed_metadata)
    assert r["dr"].verdict == "PASS_AUTO_ALLOWED"
    assert r["wcp"].verdict == "READY_FOR_WRITER"
    assert r["exe"].verdict == "PASS_NOOP_EXECUTOR_READY"
    # createdBy만 approvedBy에 반영, 그 외 동일
    assert r["wcp"].writerCalls[0].approvedBy == cb


def test_parity_across_created_by_buckets(stages, parsed_metadata):
    t_id, cell = _first_text_cell(parsed_metadata)
    op = _set_cell_text_op(t_id, cell)
    r_m = _run_pipeline(stages, _make_plan(stages, [op], created_by="manual"),
                            [], parsed_metadata)
    r_a = _run_pipeline(stages, _make_plan(stages, [op], created_by="ai"),
                            [], parsed_metadata)
    r_s = _run_pipeline(stages, _make_plan(stages, [op], created_by="system"),
                            [], parsed_metadata)
    # 버킷 동일
    assert r_m["dr"].autoAllowedOps == r_a["dr"].autoAllowedOps == r_s["dr"].autoAllowedOps
    assert r_m["wcp"].readyForWriter == r_a["wcp"].readyForWriter == r_s["wcp"].readyForWriter
    assert r_m["exe"].verdict == r_a["exe"].verdict == r_s["exe"].verdict


# ── T09: writer/output/원본 불변식 종단 검증 ─────────────────────────────────

def test_pipeline_never_touches_writer_or_output_or_source(stages, parsed_metadata,
                                                                  tmp_path):
    sha_before = hashlib.sha256(METADATA_FORM.read_bytes()).hexdigest()
    mtime_before = METADATA_FORM.stat().st_mtime
    files_before = sorted(p.name for p in tmp_path.iterdir())

    t_id, cell = _first_text_cell(parsed_metadata)
    # 다양한 경로를 모두 실행해본다
    scenarios = [
        ([_set_cell_text_op(t_id, cell)], []),  # AUTO
        ([_set_fill_color_op(t_id, cell)],
            [_decision("plan-itg", "op-fill", "APPROVE")]),
        ([_set_fill_color_op(t_id, cell)],
            [_decision("plan-itg", "op-fill", "REJECT")]),
        ([_move_object_op()], []),
    ]
    for ops, decisions in scenarios:
        plan = _make_plan(stages, ops)
        r = _run_pipeline(stages, plan, decisions, parsed_metadata)
        assert r["exe"].writerCalled is False
        assert r["exe"].outputCreated is False
        assert r["exe"].originalUnmodified is True
        assert r["wcp"].writerCalled is False
        assert r["wcp"].outputCreated is False
        assert r["wcp"].originalUnmodified is True
        assert r["gate"].writerCalled is False
        assert r["gate"].outputCreated is False
        assert r["gate"].originalUnmodified is True

    assert hashlib.sha256(METADATA_FORM.read_bytes()).hexdigest() == sha_before
    assert METADATA_FORM.stat().st_mtime == mtime_before
    assert sorted(p.name for p in tmp_path.iterdir()) == files_before


# ── T10: to_dict / audit trail 일관성 ────────────────────────────────────────

def test_result_chain_to_dict_serializable(stages, parsed_metadata):
    t_id, cell = _first_text_cell(parsed_metadata)
    plan = _make_plan(stages, [_set_fill_color_op(t_id, cell)])
    r = _run_pipeline(stages, plan,
                         [_decision(plan["planId"], "op-fill", "APPROVE",
                                       reviewer="bob")],
                         parsed_metadata)
    # 각 단계 to_dict 가능 + 핵심 키 보존
    dr_d = r["dr"].to_dict()
    gate_d = r["gate"].to_dict()
    wcp_d = r["wcp"].to_dict()
    exe_d = r["exe"].to_dict()
    assert dr_d["planId"] == gate_d["planId"] == wcp_d["planId"] == exe_d["planId"]
    # gate audit log이 단일 entry로 APPROVE 보존
    log = [a for a in gate_d["auditLog"] if a["operationId"] == "op-fill"][0]
    assert log["decision"] == "APPROVE"
    assert log["reviewer"] == "bob"
    # adapter writerCall에 approvedBy=reviewer로 전파
    wc = wcp_d["writerCalls"][0]
    assert wc["approvedBy"] == "bob"
    # executor simulatedCall에 동일 commandId/operationId 전달
    sc = exe_d["simulatedCalls"][0]
    assert sc["commandId"] == wc["commandId"]
    assert sc["operationId"] == "op-fill"


# ── T11: planId / operationId / expectedBefore / sourceHash 일관성 ───────────

def test_invariant_keys_preserved_across_stages_auto(stages, parsed_metadata):
    t_id, cell = _first_text_cell(parsed_metadata)
    plan = _make_plan(stages, [_set_cell_text_op(t_id, cell, op_id="op-A")],
                         plan_id="plan-INV", source_hash="sha256:specific")
    r = _run_pipeline(stages, plan, [], parsed_metadata)

    assert r["dr"].planId == "plan-INV"
    assert r["gate"].planId == "plan-INV"
    assert r["wcp"].planId == "plan-INV"
    assert r["exe"].planId == "plan-INV"

    assert "op-A" in r["dr"].autoAllowedOps
    assert "op-A" in r["wcp"].to_dict()["writerCalls"][0]["operationId"]
    wc = r["wcp"].writerCalls[0]
    assert wc.expectedBefore == (cell.normalizedText or cell.text)
    assert wc.sourceDocumentHash == "sha256:specific"
    # executor에도 그대로 전달
    sc = r["exe"].simulatedCalls[0]
    assert sc.operationId == "op-A"
    assert sc.expectedBefore == wc.expectedBefore


def test_invariant_keys_preserved_through_review_approval(stages, parsed_metadata):
    t_id, cell = _first_text_cell(parsed_metadata)
    plan = _make_plan(stages, [_set_fill_color_op(t_id, cell, op_id="op-F")],
                         plan_id="plan-RV", source_hash="sha256:rv")
    r = _run_pipeline(stages, plan,
                         [_decision("plan-RV", "op-F", "APPROVE")],
                         parsed_metadata)
    wc = r["wcp"].writerCalls[0]
    sc = r["exe"].simulatedCalls[0]
    assert wc.operationId == "op-F"
    assert sc.operationId == "op-F"
    assert wc.sourceDocumentHash == "sha256:rv"
    assert sc.expectedBefore == wc.expectedBefore  # 변조 없음
