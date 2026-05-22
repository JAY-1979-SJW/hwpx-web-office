"""HWPX-EDIT-PLAN-WRITER-ADAPTER-DRY-RUN-01 테스트.

WriterCallPlan dry-run 산출 검증. 실제 writer 호출 없음, output 미생성, 원본 무수정.
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
def adapter():
    from hwpx.pipeline import generic_edit_plan_writer_adapter as a
    return a


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


def _set_cell_text_plan(contract, t_id, cell, created_by="ai"):
    plan = contract.empty_plan_skeleton(
        plan_id="plan-wa-text",
        source_doc_hash="sha256:abc",
        created_by=created_by,
        created_at="2026-05-18T00:00:00Z",
    )
    plan["operations"] = [{
        "operationId": "op-text-1",
        "operationType": "setCellText",
        "target": {"tableId": t_id, "row": cell.row, "col": cell.col},
        "value": "NEW",
        "preserveStyle": True,
        "expectedBefore": cell.normalizedText or cell.text,
        "riskLevel": "low",
        "requiresReview": False,
        "reason": "test",
    }]
    return plan


def _fill_color_plan(contract, t_id, cell, created_by="ai"):
    plan = contract.empty_plan_skeleton(
        plan_id="plan-wa-fill",
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


def _blocked_plan(contract):
    plan = contract.empty_plan_skeleton(
        plan_id="plan-wa-blk",
        source_doc_hash="sha256:abc",
        created_by="ai",
        created_at="2026-05-18T00:00:00Z",
    )
    plan["operations"] = [{
        "operationId": "op-move",
        "operationType": "moveObject",
        "target": {"objectId": "obj-x"},
        "value": None,
        "preserveStyle": True,
        "expectedBefore": None,
        "riskLevel": "high",
        "requiresReview": True,
        "reason": "ai-move",
    }]
    return plan


def _decision(plan_id, op_id, decision, reviewer="alice"):
    return {
        "decisionId": f"d-{op_id}",
        "planId": plan_id,
        "operationId": op_id,
        "reviewer": reviewer,
        "decision": decision,
        "reason": "ok",
        "decidedAt": "2026-05-18T03:00:00Z",
    }


# ── T01: PASS_AUTO_ALLOWED setCellText → writer call ─────────────────────────

def test_auto_set_cell_text_becomes_writer_call(contract, dry_run, review_gate,
                                                     adapter, parsed_metadata):
    t_id, cell = _first_text_cell(parsed_metadata)
    plan = _set_cell_text_plan(contract, t_id, cell)
    dr = dry_run.dry_run_edit_plan(plan, parsed_metadata)
    gate = review_gate.apply_review_decisions(dr, [])  # review op 없음
    res = adapter.build_writer_call_plan(plan, dr, gate)
    assert res.verdict == "READY_FOR_WRITER"
    assert res.readyForWriter is True
    assert len(res.writerCalls) == 1
    wc = res.writerCalls[0]
    assert wc.operationId == "op-text-1"
    assert wc.operationType == "setCellText"
    assert wc.writerMethod == "writer.set_cell_text"
    assert wc.target["tableId"] == t_id
    assert wc.expectedBefore == (cell.normalizedText or cell.text)
    assert wc.value == "NEW"
    assert wc.approvedBy == "ai"
    assert wc.sourceDocumentHash == "sha256:abc"


# ── T02: READY_AFTER_REVIEW approved fillColor → writer call ─────────────────

def test_approved_fill_color_becomes_writer_call(contract, dry_run, review_gate,
                                                       adapter, parsed_metadata):
    t_id, cell = _first_text_cell(parsed_metadata)
    plan = _fill_color_plan(contract, t_id, cell)
    dr = dry_run.dry_run_edit_plan(plan, parsed_metadata)
    gate = review_gate.apply_review_decisions(
        dr, [_decision(plan["planId"], "op-fill-1", "APPROVE", reviewer="bob")],
    )
    assert gate.gateVerdict == "READY_AFTER_REVIEW"
    res = adapter.build_writer_call_plan(plan, dr, gate)
    assert res.verdict == "READY_FOR_WRITER"
    assert len(res.writerCalls) == 1
    wc = res.writerCalls[0]
    assert wc.writerMethod == "writer.set_cell_fill_color"
    assert wc.approvedBy == "bob"


# ── T03..T06: REJECTED / HELD / PENDING / BLOCKED → writer call 0 ────────────

def test_rejected_review_produces_no_writer_calls(contract, dry_run, review_gate,
                                                        adapter, parsed_metadata):
    t_id, cell = _first_text_cell(parsed_metadata)
    plan = _fill_color_plan(contract, t_id, cell)
    dr = dry_run.dry_run_edit_plan(plan, parsed_metadata)
    gate = review_gate.apply_review_decisions(
        dr, [_decision(plan["planId"], "op-fill-1", "REJECT")],
    )
    res = adapter.build_writer_call_plan(plan, dr, gate)
    assert res.readyForWriter is False
    assert res.writerCalls == []
    assert any(f.code == "GATE_NOT_READY" for f in res.safetyFindings)


def test_held_review_produces_no_writer_calls(contract, dry_run, review_gate,
                                                    adapter, parsed_metadata):
    t_id, cell = _first_text_cell(parsed_metadata)
    plan = _fill_color_plan(contract, t_id, cell)
    dr = dry_run.dry_run_edit_plan(plan, parsed_metadata)
    gate = review_gate.apply_review_decisions(
        dr, [_decision(plan["planId"], "op-fill-1", "HOLD")],
    )
    res = adapter.build_writer_call_plan(plan, dr, gate)
    assert res.readyForWriter is False
    assert res.writerCalls == []


def test_pending_review_produces_no_writer_calls(contract, dry_run, review_gate,
                                                       adapter, parsed_metadata):
    t_id, cell = _first_text_cell(parsed_metadata)
    plan = _fill_color_plan(contract, t_id, cell)
    dr = dry_run.dry_run_edit_plan(plan, parsed_metadata)
    gate = review_gate.apply_review_decisions(dr, [])  # 결정 누락
    assert gate.gateVerdict == "PENDING_REVIEW"
    res = adapter.build_writer_call_plan(plan, dr, gate)
    assert res.readyForWriter is False
    assert res.writerCalls == []


def test_blocked_dry_run_produces_no_writer_calls(contract, dry_run, review_gate,
                                                        adapter, parsed_metadata):
    plan = _blocked_plan(contract)
    dr = dry_run.dry_run_edit_plan(plan, parsed_metadata)
    assert dr.verdict == "BLOCKED_UNSAFE"
    # gate는 호출 안 해도 됨 (혹은 빈 결정으로 호출)
    gate = review_gate.apply_review_decisions(dr, [])
    res = adapter.build_writer_call_plan(plan, dr, gate)
    assert res.readyForWriter is False
    assert res.writerCalls == []
    assert any(f.code == "DRY_RUN_BLOCKED" for f in res.safetyFindings)


# ── T07: blocked op 승인 우회 시도 → 변환 차단 ───────────────────────────────

def test_attempted_bypass_of_blocked_op_is_refused(contract, dry_run, review_gate,
                                                        adapter, parsed_metadata):
    plan = _blocked_plan(contract)
    dr = dry_run.dry_run_edit_plan(plan, parsed_metadata)
    # 게이트는 blocked op APPROVE를 거부하지만, 만약 누군가 우회를 시도해서
    # gate.approvedOps에 직접 op-move를 끼워넣는다 해도 adapter는 거부해야 한다.
    fake_gate = {
        "gateVerdict": "READY_AFTER_REVIEW",
        "approvedOps": ["op-move"],
        "auditLog": [{"operationId": "op-move", "reviewer": "evil",
                       "decision": "APPROVE"}],
    }
    res = adapter.build_writer_call_plan(plan, dr, fake_gate)
    assert res.readyForWriter is False
    assert res.writerCalls == []
    assert "op-move" in res.blockedOps
    # 차단 사유가 명확히 기록돼야 한다
    assert any(f.code == "DRY_RUN_BLOCKED" for f in res.safetyFindings)


# ── T08: writer method whitelist 검증 ────────────────────────────────────────

def test_writer_method_whitelist_is_complete(contract, adapter):
    expected_keys = contract.ALLOWED_OPERATION_TYPES
    assert set(adapter.OPERATION_TO_WRITER_METHOD.keys()) == set(expected_keys)
    for method in adapter.OPERATION_TO_WRITER_METHOD.values():
        assert method.startswith("writer.")


def test_writer_method_unknown_op_is_skipped(contract, dry_run, review_gate,
                                                  adapter, parsed_metadata, monkeypatch):
    """매핑에 없는 op_type은 변환 거부 (whitelist 외 차단)."""
    # contract에는 있지만 adapter 매핑에서 일시 제거해 본다
    monkeypatch.setitem(adapter.OPERATION_TO_WRITER_METHOD, "setCellText", None)
    monkeypatch.delitem(adapter.OPERATION_TO_WRITER_METHOD, "setCellText")
    t_id, cell = _first_text_cell(parsed_metadata)
    plan = _set_cell_text_plan(contract, t_id, cell)
    dr = dry_run.dry_run_edit_plan(plan, parsed_metadata)
    gate = review_gate.apply_review_decisions(dr, [])
    res = adapter.build_writer_call_plan(plan, dr, gate)
    assert res.writerCalls == []
    assert any(f.code == "WRITER_METHOD_NOT_WHITELISTED" for f in res.safetyFindings)


# ── T09: 불변식 (writer/output/원본) ─────────────────────────────────────────

def test_adapter_does_not_touch_files(contract, dry_run, review_gate, adapter,
                                            parsed_metadata, tmp_path):
    sha_before = hashlib.sha256(METADATA_FORM.read_bytes()).hexdigest()
    mtime_before = METADATA_FORM.stat().st_mtime
    files_before = sorted(p.name for p in tmp_path.iterdir())

    t_id, cell = _first_text_cell(parsed_metadata)
    plan = _set_cell_text_plan(contract, t_id, cell)
    dr = dry_run.dry_run_edit_plan(plan, parsed_metadata)
    gate = review_gate.apply_review_decisions(dr, [])
    res = adapter.build_writer_call_plan(plan, dr, gate)

    assert hashlib.sha256(METADATA_FORM.read_bytes()).hexdigest() == sha_before
    assert METADATA_FORM.stat().st_mtime == mtime_before
    assert sorted(p.name for p in tmp_path.iterdir()) == files_before
    assert res.writerCalled is False
    assert res.outputCreated is False
    assert res.originalUnmodified is True


# ── T10: createdBy manual/ai/system → 동일 call spec ─────────────────────────

@pytest.mark.parametrize("cb", ["manual", "ai", "system"])
def test_created_by_does_not_change_writer_call(contract, dry_run, review_gate,
                                                     adapter, parsed_metadata, cb):
    t_id, cell = _first_text_cell(parsed_metadata)
    plan = _set_cell_text_plan(contract, t_id, cell, created_by=cb)
    dr = dry_run.dry_run_edit_plan(plan, parsed_metadata)
    gate = review_gate.apply_review_decisions(dr, [])
    res = adapter.build_writer_call_plan(plan, dr, gate)
    assert res.readyForWriter is True
    assert len(res.writerCalls) == 1
    wc = res.writerCalls[0]
    assert wc.operationType == "setCellText"
    assert wc.writerMethod == "writer.set_cell_text"
    assert wc.approvedBy == cb   # auto-allowed면 plan.createdBy를 책임자로


# ── T11: 결과 직렬화 ─────────────────────────────────────────────────────────

def test_writer_call_plan_to_dict_has_expected_keys(contract, dry_run, review_gate,
                                                          adapter, parsed_metadata):
    t_id, cell = _first_text_cell(parsed_metadata)
    plan = _set_cell_text_plan(contract, t_id, cell)
    dr = dry_run.dry_run_edit_plan(plan, parsed_metadata)
    gate = review_gate.apply_review_decisions(dr, [])
    d = adapter.build_writer_call_plan(plan, dr, gate).to_dict()
    for k in ("adapterId", "planId", "verdict", "readyForWriter",
              "writerCalls", "skippedOps", "blockedOps", "safetyFindings",
              "writerCalled", "outputCreated", "originalUnmodified"):
        assert k in d


# ── T12: expectedBefore 누락 변환 차단 (이중 방어) ───────────────────────────

def test_missing_expected_before_skipped_even_if_allowlisted(contract, dry_run,
                                                                    review_gate, adapter,
                                                                    parsed_metadata):
    """contract가 차단하기 전이라 가정하고 adapter 단계에서도 한번 더 막는지 검증."""
    t_id, cell = _first_text_cell(parsed_metadata)
    plan = _set_cell_text_plan(contract, t_id, cell)
    dr = dry_run.dry_run_edit_plan(plan, parsed_metadata)
    gate = review_gate.apply_review_decisions(dr, [])
    # plan에서 expectedBefore 키 자체를 제거해 본다
    plan["operations"][0].pop("expectedBefore", None)
    res = adapter.build_writer_call_plan(plan, dr, gate)
    assert any(s.reason == "expectedBefore_missing" for s in res.skippedOps)
    assert res.writerCalls == []
