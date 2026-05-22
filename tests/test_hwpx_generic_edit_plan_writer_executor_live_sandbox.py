"""HWPX-EDIT-PLAN-WRITER-EXECUTOR-LIVE-MODE-SANDBOX-01 테스트.

Sandbox 사본에 한해 첫 실 writer 호출을 허용하는 live executor 검증.
원본 fixture 무수정 유지가 모든 테스트의 절대 조건.
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
        generic_edit_plan_writer_executor_live_sandbox as live,
    )
    return {"contract": c, "dry_run": d, "gate": g, "adapter": a, "live": live}


@pytest.fixture(scope="module")
def parsed_metadata():
    from hwpx.parser import parse_hwpx_v2
    return parse_hwpx_v2(METADATA_FORM)


def _find_cell_with_text(parsed, text_match: str):
    for t in parsed.tables:
        for c in t.cells:
            if c.normalizedText == text_match:
                return t.tableId, c
    return None, None


def _build_setcelltext_plan(stages, t_id, cell, value="사본수정테스트",
                                expected=None, source_hash="sha256:metaform",
                                created_by="ai"):
    c = stages["contract"]
    plan = c.empty_plan_skeleton(
        plan_id="plan-live-test",
        source_doc_hash=source_hash,
        created_by=created_by,
        created_at="2026-05-18T00:00:00Z",
    )
    plan["operations"] = [{
        "operationId": "op-text-1",
        "operationType": "setCellText",
        "target": {"tableId": t_id, "row": cell.row, "col": cell.col},
        "value": value,
        "preserveStyle": True,
        "expectedBefore": expected if expected is not None else cell.normalizedText,
        "riskLevel": "low",
        "requiresReview": False,
        "reason": "sandbox first live",
    }]
    return plan


def _build_wcp(stages, plan, parsed, decisions=None):
    dr = stages["dry_run"].dry_run_edit_plan(plan, parsed)
    gate = stages["gate"].apply_review_decisions(dr, decisions or [])
    wcp = stages["adapter"].build_writer_call_plan(plan, dr, gate)
    return wcp


# ── T01: 정상 sandbox live ────────────────────────────────────────────────────

def test_setcelltext_sandbox_live_applies_successfully(stages, parsed_metadata,
                                                            tmp_path):
    t_id, cell = _find_cell_with_text(parsed_metadata, "교육기관대행갱신신청서")
    assert t_id is not None
    plan = _build_setcelltext_plan(stages, t_id, cell, value="사본테스트값")
    wcp = _build_wcp(stages, plan, parsed_metadata)
    assert wcp.readyForWriter is True

    output = tmp_path / "sandbox.hwpx"
    sha_before = hashlib.sha256(METADATA_FORM.read_bytes()).hexdigest()
    mtime_before = METADATA_FORM.stat().st_mtime

    res = stages["live"].execute_writer_call_plan_live_sandbox(
        wcp, METADATA_FORM, output,
    )
    assert res.verdict == "PASS_LIVE_SANDBOX_APPLIED", res.to_dict()
    assert res.writerCalled is True
    assert res.outputCreated is True
    assert output.exists()
    assert res.originalUnmodified is True
    assert hashlib.sha256(METADATA_FORM.read_bytes()).hexdigest() == sha_before
    assert METADATA_FORM.stat().st_mtime == mtime_before
    assert len(res.appliedCalls) == 1
    assert res.readback.targetCellsVerified == 1
    assert res.readback.divergences == []


# ── T02: sandbox output은 reports 또는 tmp 등 사본 경로에만 생성 ─────────────

def test_output_path_is_under_sandbox(stages, parsed_metadata, tmp_path):
    t_id, cell = _find_cell_with_text(parsed_metadata, "교육기관대행갱신신청서")
    plan = _build_setcelltext_plan(stages, t_id, cell, value="격리경로")
    wcp = _build_wcp(stages, plan, parsed_metadata)
    output = tmp_path / "isolated" / "out.hwpx"
    res = stages["live"].execute_writer_call_plan_live_sandbox(wcp, METADATA_FORM, output)
    assert res.outputPath.endswith("out.hwpx")
    assert str(METADATA_FORM).replace("\\", "/") not in res.outputPath


# ── T03: readback 대상 셀 텍스트 변경 확인 ────────────────────────────────────

def test_readback_target_cell_text_changed(stages, parsed_metadata, tmp_path):
    from hwpx.parser import parse_hwpx_v2
    t_id, cell = _find_cell_with_text(parsed_metadata, "교육기관대행갱신신청서")
    plan = _build_setcelltext_plan(stages, t_id, cell, value="검증된변경값")
    wcp = _build_wcp(stages, plan, parsed_metadata)
    output = tmp_path / "rb.hwpx"
    res = stages["live"].execute_writer_call_plan_live_sandbox(wcp, METADATA_FORM, output)
    assert res.verdict == "PASS_LIVE_SANDBOX_APPLIED"
    reread = parse_hwpx_v2(output)
    found = None
    for t in reread.tables:
        for c in t.cells:
            if t.tableId == t_id and c.row == cell.row and c.col == cell.col:
                found = c; break
        if found: break
    assert found is not None
    assert "검증된변경값" in found.normalizedText


# ── T04: 대상 외 구조 보존 확인 (cellCount/tableCount/object/binData) ────────

def test_readback_preserves_unrelated_structure(stages, parsed_metadata, tmp_path):
    t_id, cell = _find_cell_with_text(parsed_metadata, "교육기관대행갱신신청서")
    plan = _build_setcelltext_plan(stages, t_id, cell, value="구조보존검증")
    wcp = _build_wcp(stages, plan, parsed_metadata)
    output = tmp_path / "structure.hwpx"
    res = stages["live"].execute_writer_call_plan_live_sandbox(wcp, METADATA_FORM, output)
    assert res.verdict == "PASS_LIVE_SANDBOX_APPLIED"
    rb = res.readback
    assert rb.tableCountPreserved
    assert rb.cellCountPreserved
    assert rb.rowSpanSumPreserved
    assert rb.colSpanSumPreserved
    assert rb.objectCountPreserved
    assert rb.binDataCountPreserved
    assert rb.untouchedCellNormalizedTextPreserved


def test_readback_preserves_formatting_counts(stages, parsed_metadata, tmp_path):
    t_id, cell = _find_cell_with_text(parsed_metadata, "교육기관대행갱신신청서")
    plan = _build_setcelltext_plan(stages, t_id, cell, value="서식보존검증")
    wcp = _build_wcp(stages, plan, parsed_metadata)
    output = tmp_path / "fmt.hwpx"
    res = stages["live"].execute_writer_call_plan_live_sandbox(wcp, METADATA_FORM, output)
    rb = res.readback
    assert rb.horizontalAlignCountPreserved
    assert rb.verticalAlignCountPreserved
    assert rb.fontNameCountPreserved
    assert rb.fontSizeCountPreserved
    assert rb.textColorCountPreserved


# ── T05: review-required op은 이번 live mode에서 차단 ────────────────────────

def test_review_required_op_is_blocked_in_live_mode(stages, parsed_metadata, tmp_path):
    t_id, cell = _find_cell_with_text(parsed_metadata, "교육기관대행갱신신청서")
    c = stages["contract"]
    plan = c.empty_plan_skeleton("plan-live-fill", "sha256:abc", "ai", "now")
    plan["operations"] = [{
        "operationId": "op-fill",
        "operationType": "setCellFillColor",
        "target": {"tableId": t_id, "row": cell.row, "col": cell.col},
        "value": "#FFFF00",
        "preserveStyle": True,
        "expectedBefore": cell.fillColor,
        "riskLevel": "low",
        "requiresReview": False,
        "reason": "highlight",
    }]
    wcp = _build_wcp(stages, plan, parsed_metadata, decisions=[{
        "decisionId": "d-1", "planId": plan["planId"], "operationId": "op-fill",
        "reviewer": "alice", "decision": "APPROVE", "reason": "ok",
        "decidedAt": "2026-05-18T01:00:00Z",
    }])
    assert wcp.readyForWriter is True
    output = tmp_path / "fill.hwpx"
    sha_before = hashlib.sha256(METADATA_FORM.read_bytes()).hexdigest()
    res = stages["live"].execute_writer_call_plan_live_sandbox(wcp, METADATA_FORM, output)
    assert res.verdict == "BLOCKED_UNSUPPORTED_LIVE_OPERATION"
    assert res.writerCalled is False
    assert res.outputCreated is False
    assert any(f.code == "UNSUPPORTED_LIVE_OPERATION" for f in res.safetyFindings)
    assert hashlib.sha256(METADATA_FORM.read_bytes()).hexdigest() == sha_before


# ── T06: blocked op (moveObject) 차단 ─────────────────────────────────────────

def test_blocked_op_never_reaches_live(stages, parsed_metadata, tmp_path):
    c = stages["contract"]
    plan = c.empty_plan_skeleton("plan-blk", "sha256:abc", "ai", "now")
    plan["operations"] = [{
        "operationId": "op-move",
        "operationType": "moveObject",
        "target": {"objectId": "obj-x"},
        "value": None,
        "preserveStyle": True,
        "expectedBefore": None,
        "riskLevel": "high",
        "requiresReview": True,
        "reason": "ai move",
    }]
    wcp = _build_wcp(stages, plan, parsed_metadata)
    assert wcp.readyForWriter is False   # adapter가 이미 차단
    output = tmp_path / "blk.hwpx"
    sha_before = hashlib.sha256(METADATA_FORM.read_bytes()).hexdigest()
    res = stages["live"].execute_writer_call_plan_live_sandbox(wcp, METADATA_FORM, output)
    assert res.verdict == "BLOCKED_NOT_READY_FOR_WRITER"
    assert res.writerCalled is False
    assert not output.exists()
    assert hashlib.sha256(METADATA_FORM.read_bytes()).hexdigest() == sha_before


# ── T07: sourceDocumentHash 누락 → 차단 (writer 호출 전) ─────────────────────

def test_missing_source_hash_blocks_live(stages, parsed_metadata, tmp_path):
    # WriterCallSpec에 sourceDocumentHash가 빈 문자열이도록 위조 wcp dict 작성
    fake_wcp = {
        "planId": "p-x",
        "verdict": "READY_FOR_WRITER",
        "readyForWriter": True,
        "writerCalls": [{
            "commandId": "c-1",
            "operationId": "op-1",
            "operationType": "setCellText",
            "writerMethod": "writer.set_cell_text",
            "target": {"tableId": "t_s0_000", "row": 1, "col": 0},
            "value": "x",
            "expectedBefore": "y",
            "preserveStyle": True,
            "riskLevel": "low",
            "approvedBy": "ai",
            "sourceDocumentHash": "",
        }],
        "blockedOps": [],
    }
    output = tmp_path / "nh.hwpx"
    sha_before = hashlib.sha256(METADATA_FORM.read_bytes()).hexdigest()
    res = stages["live"].execute_writer_call_plan_live_sandbox(fake_wcp, METADATA_FORM, output)
    assert res.verdict == "BLOCKED_SOURCE_HASH_MISSING"
    assert res.writerCalled is False
    assert not output.exists()
    assert hashlib.sha256(METADATA_FORM.read_bytes()).hexdigest() == sha_before


# ── T08: expectedBefore 누락 → 차단 ──────────────────────────────────────────

def test_missing_expected_before_blocks_live(stages, parsed_metadata, tmp_path):
    fake_wcp = {
        "planId": "p-y",
        "verdict": "READY_FOR_WRITER",
        "readyForWriter": True,
        "writerCalls": [{
            "commandId": "c-1",
            "operationId": "op-1",
            "operationType": "setCellText",
            "writerMethod": "writer.set_cell_text",
            "target": {"tableId": "t_s0_000", "row": 1, "col": 0},
            "value": "x",
            # expectedBefore 키 자체 없음
            "preserveStyle": True,
            "riskLevel": "low",
            "approvedBy": "ai",
            "sourceDocumentHash": "sha:1",
        }],
        "blockedOps": [],
    }
    output = tmp_path / "noexp.hwpx"
    sha_before = hashlib.sha256(METADATA_FORM.read_bytes()).hexdigest()
    res = stages["live"].execute_writer_call_plan_live_sandbox(fake_wcp, METADATA_FORM, output)
    assert res.verdict == "BLOCKED_EXPECTED_BEFORE_MISSING"
    assert not output.exists()
    assert hashlib.sha256(METADATA_FORM.read_bytes()).hexdigest() == sha_before


# ── T09: output == source 경로 → 즉시 차단 ──────────────────────────────────

def test_output_path_equal_to_source_is_refused(stages, parsed_metadata):
    t_id, cell = _find_cell_with_text(parsed_metadata, "교육기관대행갱신신청서")
    plan = _build_setcelltext_plan(stages, t_id, cell, value="자가덮어쓰기시도")
    wcp = _build_wcp(stages, plan, parsed_metadata)
    sha_before = hashlib.sha256(METADATA_FORM.read_bytes()).hexdigest()
    res = stages["live"].execute_writer_call_plan_live_sandbox(
        wcp, METADATA_FORM, METADATA_FORM,
    )
    assert res.verdict == "BLOCKED_UNSAFE_OUTPUT_PATH"
    assert res.writerCalled is False
    assert any(f.code == "OUTPUT_OVERWRITES_SOURCE" for f in res.safetyFindings)
    assert hashlib.sha256(METADATA_FORM.read_bytes()).hexdigest() == sha_before


# ── T10: writer method whitelist 위조 → 차단 ─────────────────────────────────

def test_unsafe_writer_method_blocks(stages, tmp_path):
    fake_wcp = {
        "planId": "p-z",
        "verdict": "READY_FOR_WRITER",
        "readyForWriter": True,
        "writerCalls": [{
            "commandId": "c-1",
            "operationId": "op-1",
            "operationType": "setCellText",
            "writerMethod": "writer.delete_everything",   # 위조
            "target": {"tableId": "t_s0_000", "row": 1, "col": 0},
            "value": "x",
            "expectedBefore": "y",
            "preserveStyle": True,
            "riskLevel": "low",
            "approvedBy": "ai",
            "sourceDocumentHash": "sha:1",
        }],
        "blockedOps": [],
    }
    output = tmp_path / "bad.hwpx"
    sha_before = hashlib.sha256(METADATA_FORM.read_bytes()).hexdigest()
    res = stages["live"].execute_writer_call_plan_live_sandbox(fake_wcp, METADATA_FORM, output)
    assert res.verdict == "BLOCKED_UNSAFE_WRITER_METHOD"
    assert not output.exists()
    assert hashlib.sha256(METADATA_FORM.read_bytes()).hexdigest() == sha_before


# ── T11: manual/ai/system parity ─────────────────────────────────────────────

@pytest.mark.parametrize("cb", ["manual", "ai", "system"])
def test_created_by_does_not_change_live_result(stages, parsed_metadata, tmp_path, cb):
    t_id, cell = _find_cell_with_text(parsed_metadata, "교육기관대행갱신신청서")
    plan = _build_setcelltext_plan(stages, t_id, cell, value="동등성검증", created_by=cb)
    wcp = _build_wcp(stages, plan, parsed_metadata)
    output = tmp_path / f"parity_{cb}.hwpx"
    res = stages["live"].execute_writer_call_plan_live_sandbox(wcp, METADATA_FORM, output)
    assert res.verdict == "PASS_LIVE_SANDBOX_APPLIED"
    assert res.readback.targetCellsVerified == 1


# ── T12: pipeline integration 회귀 유지 (스모크) ────────────────────────────

def test_pipeline_integration_still_passes_smoke(parsed_metadata):
    """live sandbox 도입이 5단계 파이프라인 통합 흐름을 깨지 않는다."""
    from hwpx.pipeline import (
        generic_edit_plan_contract as c,
        generic_edit_plan_dry_run as d,
        generic_edit_plan_review_gate as g,
        generic_edit_plan_writer_adapter as a,
        generic_edit_plan_writer_executor_noop as e,
    )
    t_id, cell = _find_cell_with_text(parsed_metadata, "교육기관대행갱신신청서")
    plan = c.empty_plan_skeleton("plan-itg-smoke", "sha:1", "ai", "now")
    plan["operations"] = [{
        "operationId": "op-1", "operationType": "setCellText",
        "target": {"tableId": t_id, "row": cell.row, "col": cell.col},
        "value": "smoke", "preserveStyle": True,
        "expectedBefore": cell.normalizedText, "riskLevel": "low",
        "requiresReview": False, "reason": "smoke",
    }]
    dr = d.dry_run_edit_plan(plan, parsed_metadata)
    gate = g.apply_review_decisions(dr, [])
    wcp = a.build_writer_call_plan(plan, dr, gate)
    exe = e.execute_writer_call_plan_noop(wcp)
    assert exe.verdict == "PASS_NOOP_EXECUTOR_READY"


# ── T13: 결과 직렬화 ─────────────────────────────────────────────────────────

# ── EXPAND-ALIGN-01: setCellHorizontalAlign / setCellVerticalAlign 확장 ──────

def _align_plan(stages, op_type, t_id, cell, value, expected,
                  created_by="ai", plan_id="plan-align"):
    c = stages["contract"]
    plan = c.empty_plan_skeleton(
        plan_id=plan_id, source_doc_hash="sha256:metaform",
        created_by=created_by, created_at="2026-05-18T00:00:00Z",
    )
    plan["operations"] = [{
        "operationId": f"op-{op_type}",
        "operationType": op_type,
        "target": {"tableId": t_id, "row": cell.row, "col": cell.col},
        "value": value,
        "preserveStyle": True,
        "expectedBefore": expected,
        "riskLevel": "low",
        "requiresReview": False,
        "reason": "align test",
    }]
    return plan


def test_set_cell_horizontal_align_sandbox_live(stages, parsed_metadata, tmp_path):
    from hwpx.parser import parse_hwpx_v2
    t_id, cell = _find_cell_with_text(parsed_metadata, "교육기관대행갱신신청서")
    plan = _align_plan(stages, "setCellHorizontalAlign", t_id, cell,
                          value="RIGHT", expected=cell.horizontalAlign)
    wcp = _build_wcp(stages, plan, parsed_metadata)
    assert wcp.readyForWriter is True

    output = tmp_path / "halign.hwpx"
    sha_before = hashlib.sha256(METADATA_FORM.read_bytes()).hexdigest()
    mtime_before = METADATA_FORM.stat().st_mtime
    res = stages["live"].execute_writer_call_plan_live_sandbox(
        wcp, METADATA_FORM, output,
    )
    assert res.verdict == "PASS_LIVE_SANDBOX_APPLIED", res.to_dict()
    assert res.writerCalled is True
    assert output.exists()
    assert res.readback.targetCellsVerified == 1
    assert res.readback.divergences == []
    # 원본 무수정
    assert hashlib.sha256(METADATA_FORM.read_bytes()).hexdigest() == sha_before
    assert METADATA_FORM.stat().st_mtime == mtime_before
    # readback: 대상 셀의 horizontalAlign이 실제로 RIGHT로 바뀌었는지
    reread = parse_hwpx_v2(output)
    for t in reread.tables:
        for c2 in t.cells:
            if t.tableId == t_id and c2.row == cell.row and c2.col == cell.col:
                assert c2.horizontalAlign.upper() == "RIGHT"
                # verticalAlign 등 다른 속성은 보존
                assert c2.verticalAlign == cell.verticalAlign
                return


def test_set_cell_vertical_align_sandbox_live(stages, parsed_metadata, tmp_path):
    from hwpx.parser import parse_hwpx_v2
    t_id, cell = _find_cell_with_text(parsed_metadata, "교육기관대행갱신신청서")
    plan = _align_plan(stages, "setCellVerticalAlign", t_id, cell,
                          value="BOTTOM", expected=cell.verticalAlign)
    wcp = _build_wcp(stages, plan, parsed_metadata)
    output = tmp_path / "valign.hwpx"
    sha_before = hashlib.sha256(METADATA_FORM.read_bytes()).hexdigest()
    res = stages["live"].execute_writer_call_plan_live_sandbox(
        wcp, METADATA_FORM, output,
    )
    assert res.verdict == "PASS_LIVE_SANDBOX_APPLIED", res.to_dict()
    assert res.readback.targetCellsVerified == 1
    assert res.readback.divergences == []
    assert hashlib.sha256(METADATA_FORM.read_bytes()).hexdigest() == sha_before
    reread = parse_hwpx_v2(output)
    for t in reread.tables:
        for c2 in t.cells:
            if t.tableId == t_id and c2.row == cell.row and c2.col == cell.col:
                assert c2.verticalAlign.upper() == "BOTTOM"
                assert c2.horizontalAlign == cell.horizontalAlign
                # 다른 셀 텍스트는 그대로
                return


def test_invalid_horizontal_align_value_blocked(stages, parsed_metadata, tmp_path):
    t_id, cell = _find_cell_with_text(parsed_metadata, "교육기관대행갱신신청서")
    plan = _align_plan(stages, "setCellHorizontalAlign", t_id, cell,
                          value="SLANTED", expected=cell.horizontalAlign,
                          plan_id="plan-bad-h")
    wcp = _build_wcp(stages, plan, parsed_metadata)
    output = tmp_path / "bad_h.hwpx"
    sha_before = hashlib.sha256(METADATA_FORM.read_bytes()).hexdigest()
    res = stages["live"].execute_writer_call_plan_live_sandbox(
        wcp, METADATA_FORM, output,
    )
    assert res.verdict == "BLOCKED_INVALID_ALIGN_VALUE"
    assert res.writerCalled is False
    assert not output.exists()
    assert any(f.code == "INVALID_ALIGN_VALUE" for f in res.safetyFindings)
    # 원본 무수정
    assert hashlib.sha256(METADATA_FORM.read_bytes()).hexdigest() == sha_before


def test_invalid_vertical_align_value_blocked(stages, parsed_metadata, tmp_path):
    t_id, cell = _find_cell_with_text(parsed_metadata, "교육기관대행갱신신청서")
    plan = _align_plan(stages, "setCellVerticalAlign", t_id, cell,
                          value="FLOATING", expected=cell.verticalAlign,
                          plan_id="plan-bad-v")
    wcp = _build_wcp(stages, plan, parsed_metadata)
    output = tmp_path / "bad_v.hwpx"
    sha_before = hashlib.sha256(METADATA_FORM.read_bytes()).hexdigest()
    res = stages["live"].execute_writer_call_plan_live_sandbox(
        wcp, METADATA_FORM, output,
    )
    assert res.verdict == "BLOCKED_INVALID_ALIGN_VALUE"
    assert res.writerCalled is False
    assert not output.exists()
    assert hashlib.sha256(METADATA_FORM.read_bytes()).hexdigest() == sha_before


def test_halign_lowercase_value_accepted(stages, parsed_metadata, tmp_path):
    """입력값 'right'도 정규화하여 RIGHT로 수용."""
    t_id, cell = _find_cell_with_text(parsed_metadata, "교육기관대행갱신신청서")
    plan = _align_plan(stages, "setCellHorizontalAlign", t_id, cell,
                          value="right", expected=cell.horizontalAlign,
                          plan_id="plan-lower")
    wcp = _build_wcp(stages, plan, parsed_metadata)
    output = tmp_path / "lower.hwpx"
    res = stages["live"].execute_writer_call_plan_live_sandbox(
        wcp, METADATA_FORM, output,
    )
    assert res.verdict == "PASS_LIVE_SANDBOX_APPLIED"


def test_align_preserves_non_target_structure_and_format(stages, parsed_metadata, tmp_path):
    t_id, cell = _find_cell_with_text(parsed_metadata, "교육기관대행갱신신청서")
    plan = _align_plan(stages, "setCellHorizontalAlign", t_id, cell,
                          value="CENTER", expected=cell.horizontalAlign,
                          plan_id="plan-preserve")
    wcp = _build_wcp(stages, plan, parsed_metadata)
    output = tmp_path / "preserve.hwpx"
    res = stages["live"].execute_writer_call_plan_live_sandbox(
        wcp, METADATA_FORM, output,
    )
    rb = res.readback
    assert rb.tableCountPreserved
    assert rb.cellCountPreserved
    assert rb.rowSpanSumPreserved
    assert rb.colSpanSumPreserved
    assert rb.objectCountPreserved
    assert rb.binDataCountPreserved
    assert rb.untouchedCellNormalizedTextPreserved
    assert rb.fontNameCountPreserved
    assert rb.fontSizeCountPreserved
    assert rb.textColorCountPreserved


def test_setcellfillcolor_remains_unsupported_in_live(stages, parsed_metadata, tmp_path):
    """확장 후에도 setCellFillColor는 sandbox live에서 차단되어야 한다."""
    t_id, cell = _find_cell_with_text(parsed_metadata, "교육기관대행갱신신청서")
    c = stages["contract"]
    plan = c.empty_plan_skeleton("plan-still-fill", "sha256:abc", "ai", "now")
    plan["operations"] = [{
        "operationId": "op-fill",
        "operationType": "setCellFillColor",
        "target": {"tableId": t_id, "row": cell.row, "col": cell.col},
        "value": "#FFFF00",
        "preserveStyle": True,
        "expectedBefore": cell.fillColor,
        "riskLevel": "low",
        "requiresReview": False,
        "reason": "still review",
    }]
    wcp = _build_wcp(stages, plan, parsed_metadata, decisions=[{
        "decisionId": "d-1", "planId": plan["planId"], "operationId": "op-fill",
        "reviewer": "alice", "decision": "APPROVE", "reason": "ok",
        "decidedAt": "2026-05-18T00:00:00Z",
    }])
    output = tmp_path / "still_fill.hwpx"
    sha_before = hashlib.sha256(METADATA_FORM.read_bytes()).hexdigest()
    res = stages["live"].execute_writer_call_plan_live_sandbox(
        wcp, METADATA_FORM, output,
    )
    assert res.verdict == "BLOCKED_UNSUPPORTED_LIVE_OPERATION"
    assert not output.exists()
    assert hashlib.sha256(METADATA_FORM.read_bytes()).hexdigest() == sha_before


def test_allowed_live_operation_types_set_contains_cell_three(stages):
    """ALLOWED_LIVE_OPERATION_TYPES는 최소 cell text + align 2종을 포함한다.

    HWPX-EDIT-PLAN-WRITER-LIVE-EXPAND-PARAGRAPH-TEXT-01 이후 paragraph ops도 추가될 수 있다.
    """
    live = stages["live"]
    assert {"setCellText", "setCellHorizontalAlign",
              "setCellVerticalAlign"}.issubset(live.ALLOWED_LIVE_OPERATION_TYPES)


def test_live_result_to_dict_has_expected_keys(stages, parsed_metadata, tmp_path):
    t_id, cell = _find_cell_with_text(parsed_metadata, "교육기관대행갱신신청서")
    plan = _build_setcelltext_plan(stages, t_id, cell, value="직렬화")
    wcp = _build_wcp(stages, plan, parsed_metadata)
    output = tmp_path / "ser.hwpx"
    d = stages["live"].execute_writer_call_plan_live_sandbox(wcp, METADATA_FORM, output).to_dict()
    for k in ("executorId", "planId", "verdict", "outputPath",
              "writerCalled", "outputCreated", "originalUnmodified",
              "appliedCalls", "skippedCalls", "readback",
              "safetyFindings", "sourceSha256Before", "sourceSha256After"):
        assert k in d
