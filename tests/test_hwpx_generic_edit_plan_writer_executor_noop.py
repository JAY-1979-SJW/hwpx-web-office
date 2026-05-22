"""HWPX-EDIT-PLAN-WRITER-EXECUTOR-NO-OP-MODE-01 테스트.

WriterCallPlan → no-op executor 시뮬레이션 검증.
실 writer 호출 없음, output 미생성, 원본 무수정.
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
def executor():
    from hwpx.pipeline import generic_edit_plan_writer_executor_noop as e
    return e


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
        plan_id="plan-exe-text",
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


def _build_writer_call_plan(contract, dry_run, review_gate, adapter,
                                parsed_metadata, created_by="ai"):
    t_id, cell = _first_text_cell(parsed_metadata)
    plan = _set_cell_text_plan(contract, t_id, cell, created_by=created_by)
    dr = dry_run.dry_run_edit_plan(plan, parsed_metadata)
    gate = review_gate.apply_review_decisions(dr, [])
    wcp = adapter.build_writer_call_plan(plan, dr, gate)
    return plan, wcp


# ── T01: READY_FOR_WRITER + valid call → PASS ────────────────────────────────

def test_ready_for_writer_passes_noop_executor(contract, dry_run, review_gate,
                                                     adapter, executor, parsed_metadata):
    _, wcp = _build_writer_call_plan(contract, dry_run, review_gate, adapter, parsed_metadata)
    assert wcp.readyForWriter is True
    res = executor.execute_writer_call_plan_noop(wcp)
    assert res.verdict == "PASS_NOOP_EXECUTOR_READY"
    assert res.readyForExecution is True
    assert len(res.simulatedCalls) == 1
    sc = res.simulatedCalls[0]
    assert sc.simulationStatus == "SIMULATED_OK"
    assert sc.writerMethod == "writer.set_cell_text"
    assert sc.operationId == "op-text-1"


# ── T02: readyForWriter=False → BLOCKED_NOT_READY_FOR_WRITER ─────────────────

def test_not_ready_for_writer_blocks(contract, executor):
    fake_wcp = {
        "planId": "p-1",
        "verdict": "BLOCKED_NOT_READY",
        "readyForWriter": False,
        "writerCalls": [],
        "blockedOps": ["op-x"],
    }
    res = executor.execute_writer_call_plan_noop(fake_wcp)
    assert res.verdict == "BLOCKED_NOT_READY_FOR_WRITER"
    assert res.readyForExecution is False
    assert any(f.code == "ADAPTER_NOT_READY" for f in res.safetyFindings)
    assert any(s.operationId == "op-x" for s in res.skippedCalls)


# ── T03: writerCalls=[] → BLOCKED_NO_CALLS ────────────────────────────────────

def test_empty_writer_calls_blocks(executor):
    fake_wcp = {
        "planId": "p-empty",
        "verdict": "READY_FOR_WRITER",
        "readyForWriter": True,
        "writerCalls": [],
        "blockedOps": [],
    }
    res = executor.execute_writer_call_plan_noop(fake_wcp)
    assert res.verdict == "BLOCKED_NO_CALLS"
    assert res.readyForExecution is False
    assert any(f.code == "NO_WRITER_CALLS" for f in res.safetyFindings)


# ── T04: writerMethod whitelist 외 → BLOCKED_UNSAFE_WRITER_METHOD ────────────

def test_unsafe_writer_method_blocks(executor):
    fake_wcp = {
        "planId": "p-bad",
        "verdict": "READY_FOR_WRITER",
        "readyForWriter": True,
        "writerCalls": [{
            "commandId": "c-1",
            "operationId": "op-1",
            "operationType": "setCellText",
            "writerMethod": "writer.delete_everything",
            "target": {"tableId": "t", "row": 0, "col": 0},
            "value": "x",
            "expectedBefore": "y",
            "preserveStyle": True,
            "riskLevel": "low",
            "approvedBy": "ai",
            "sourceDocumentHash": "sha:1",
        }],
        "blockedOps": [],
    }
    res = executor.execute_writer_call_plan_noop(fake_wcp)
    assert res.verdict == "BLOCKED_UNSAFE_WRITER_METHOD"
    assert any(f.code == "WRITER_METHOD_NOT_WHITELISTED" for f in res.safetyFindings)
    assert res.simulatedCalls == []


# ── T05: expectedBefore 누락 → BLOCKED_EXPECTED_BEFORE_MISSING ───────────────

def test_missing_expected_before_blocks(executor):
    fake_wcp = {
        "planId": "p-noexp",
        "verdict": "READY_FOR_WRITER",
        "readyForWriter": True,
        "writerCalls": [{
            "commandId": "c-1",
            "operationId": "op-1",
            "operationType": "setCellText",
            "writerMethod": "writer.set_cell_text",
            "target": {"tableId": "t", "row": 0, "col": 0},
            "value": "x",
            # expectedBefore key 누락
            "preserveStyle": True,
            "riskLevel": "low",
            "approvedBy": "ai",
            "sourceDocumentHash": "sha:1",
        }],
        "blockedOps": [],
    }
    res = executor.execute_writer_call_plan_noop(fake_wcp)
    assert res.verdict == "BLOCKED_EXPECTED_BEFORE_MISSING"
    assert any(f.code == "EXPECTED_BEFORE_MISSING" for f in res.safetyFindings)


# ── T06: sourceDocumentHash 누락 → BLOCKED_SOURCE_HASH_MISSING ───────────────

def test_missing_source_hash_blocks(executor):
    fake_wcp = {
        "planId": "p-nohash",
        "verdict": "READY_FOR_WRITER",
        "readyForWriter": True,
        "writerCalls": [{
            "commandId": "c-1",
            "operationId": "op-1",
            "operationType": "setCellText",
            "writerMethod": "writer.set_cell_text",
            "target": {"tableId": "t", "row": 0, "col": 0},
            "value": "x",
            "expectedBefore": "y",
            "preserveStyle": True,
            "riskLevel": "low",
            "approvedBy": "ai",
            "sourceDocumentHash": "",
        }],
        "blockedOps": [],
    }
    res = executor.execute_writer_call_plan_noop(fake_wcp)
    assert res.verdict == "BLOCKED_SOURCE_HASH_MISSING"
    assert any(f.code == "SOURCE_HASH_MISSING" for f in res.safetyFindings)


# ── T07: 불변식 ──────────────────────────────────────────────────────────────

def test_executor_invariants_writer_output_original(contract, dry_run, review_gate,
                                                          adapter, executor,
                                                          parsed_metadata, tmp_path):
    sha_before = hashlib.sha256(METADATA_FORM.read_bytes()).hexdigest()
    mtime_before = METADATA_FORM.stat().st_mtime
    files_before = sorted(p.name for p in tmp_path.iterdir())

    _, wcp = _build_writer_call_plan(contract, dry_run, review_gate, adapter, parsed_metadata)
    res = executor.execute_writer_call_plan_noop(wcp)

    assert hashlib.sha256(METADATA_FORM.read_bytes()).hexdigest() == sha_before
    assert METADATA_FORM.stat().st_mtime == mtime_before
    assert sorted(p.name for p in tmp_path.iterdir()) == files_before
    assert res.writerCalled is False
    assert res.outputCreated is False
    assert res.originalUnmodified is True


# ── T08: 임시 폴더 output 미생성 (T07에서 함께 검증됨, 명시적 단독 케이스) ──

def test_executor_creates_no_output_files(contract, dry_run, review_gate,
                                                adapter, executor, parsed_metadata,
                                                tmp_path):
    before = sorted(p.name for p in tmp_path.iterdir())
    _, wcp = _build_writer_call_plan(contract, dry_run, review_gate, adapter, parsed_metadata)
    executor.execute_writer_call_plan_noop(wcp)
    assert sorted(p.name for p in tmp_path.iterdir()) == before


# ── T09: 원본 sha256/mtime 무변경 (반복 호출 시 누적) ───────────────────────

def test_executor_repeated_invocations_dont_modify_source(contract, dry_run,
                                                                  review_gate, adapter,
                                                                  executor, parsed_metadata):
    sha_before = hashlib.sha256(METADATA_FORM.read_bytes()).hexdigest()
    mtime_before = METADATA_FORM.stat().st_mtime
    for _ in range(3):
        _, wcp = _build_writer_call_plan(contract, dry_run, review_gate, adapter, parsed_metadata)
        executor.execute_writer_call_plan_noop(wcp)
    assert hashlib.sha256(METADATA_FORM.read_bytes()).hexdigest() == sha_before
    assert METADATA_FORM.stat().st_mtime == mtime_before


# ── T10: createdBy manual/ai/system 동일 결과 ────────────────────────────────

@pytest.mark.parametrize("cb", ["manual", "ai", "system"])
def test_created_by_does_not_change_executor_result(contract, dry_run, review_gate,
                                                          adapter, executor,
                                                          parsed_metadata, cb):
    _, wcp = _build_writer_call_plan(contract, dry_run, review_gate, adapter,
                                          parsed_metadata, created_by=cb)
    res = executor.execute_writer_call_plan_noop(wcp)
    assert res.verdict == "PASS_NOOP_EXECUTOR_READY"
    assert res.readyForExecution is True
    assert len(res.simulatedCalls) == 1


# ── T11: 결과 직렬화 ─────────────────────────────────────────────────────────

def test_executor_result_to_dict_has_expected_keys(contract, dry_run, review_gate,
                                                         adapter, executor, parsed_metadata):
    _, wcp = _build_writer_call_plan(contract, dry_run, review_gate, adapter, parsed_metadata)
    d = executor.execute_writer_call_plan_noop(wcp).to_dict()
    for k in ("executorId", "planId", "verdict", "readyForExecution",
              "simulatedCalls", "skippedCalls", "safetyFindings",
              "readbackRequired", "writerCalled", "outputCreated",
              "originalUnmodified"):
        assert k in d


# ── T12: review-required op → readbackRequired=True ─────────────────────────

def test_readback_required_for_review_required_op(contract, dry_run, review_gate,
                                                         adapter, executor, parsed_metadata):
    t_id, cell = _first_text_cell(parsed_metadata)
    plan = contract.empty_plan_skeleton("plan-rb", "sha256:abc", "ai",
                                            "2026-05-18T00:00:00Z")
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
    dr = dry_run.dry_run_edit_plan(plan, parsed_metadata)
    gate = review_gate.apply_review_decisions(dr, [{
        "decisionId": "d-1", "planId": plan["planId"], "operationId": "op-fill-1",
        "reviewer": "alice", "decision": "APPROVE", "reason": "ok",
        "decidedAt": "2026-05-18T03:00:00Z",
    }])
    wcp = adapter.build_writer_call_plan(plan, dr, gate)
    res = executor.execute_writer_call_plan_noop(wcp)
    assert res.verdict == "PASS_NOOP_EXECUTOR_READY"
    assert res.readbackRequired is True
    assert res.simulatedCalls[0].note == "readback_recommended"
