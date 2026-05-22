"""HWPX-EDIT-PLAN-EXECUTOR-DRY-RUN-01 테스트.

writer 호출 없이 plan만으로 예상 변경/분류를 산출하는 dry-run 실행기 검증.
원본 파일 / output HWPX 모두 미생성/미수정.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

GANTT_BASIC = PROJECT_ROOT / "tests/fixtures/hwpx/gantt/fx_gantt_like_basic.hwpx"
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
def parsed_metadata():
    from hwpx.parser import parse_hwpx_v2
    return parse_hwpx_v2(METADATA_FORM)


def _first_text_cell(parsed):
    for t in parsed.tables:
        for c in t.cells:
            if c.normalizedText:
                return t.tableId, c
    return None, None


def _make_setcelltext_plan(contract, t_id, row, col, expected, value="NEW",
                              created_by="ai"):
    plan = contract.empty_plan_skeleton(
        plan_id="plan-dry-1",
        source_doc_hash="sha256:abc",
        created_by=created_by,
        created_at="2026-05-18T00:00:00Z",
    )
    plan["operations"] = [{
        "operationId": "op-1",
        "operationType": "setCellText",
        "target": {"tableId": t_id, "row": row, "col": col},
        "value": value,
        "preserveStyle": True,
        "expectedBefore": expected,
        "riskLevel": "low",
        "requiresReview": False,
        "reason": "test",
    }]
    return plan


# ── T01: valid setCellText dry-run PASS_AUTO_ALLOWED ──────────────────────────

def test_valid_setcelltext_dry_run_passes(contract, dry_run, parsed_metadata):
    t_id, cell = _first_text_cell(parsed_metadata)
    assert cell is not None
    plan = _make_setcelltext_plan(contract, t_id, cell.row, cell.col,
                                    expected=cell.normalizedText or cell.text)
    res = dry_run.dry_run_edit_plan(plan, parsed_metadata)
    assert res.verdict == "PASS_AUTO_ALLOWED", res.to_dict()
    assert res.autoExecutable is True
    assert "op-1" in res.autoAllowedOps
    assert res.blockedOps == []
    assert res.reviewRequiredOps == []


# ── T02: expectedChanges 산출 (before/after) ──────────────────────────────────

def test_expected_changes_emitted_when_before_matches(contract, dry_run, parsed_metadata):
    t_id, cell = _first_text_cell(parsed_metadata)
    plan = _make_setcelltext_plan(contract, t_id, cell.row, cell.col,
                                    expected=cell.normalizedText or cell.text,
                                    value="REPLACEMENT")
    res = dry_run.dry_run_edit_plan(plan, parsed_metadata)
    assert len(res.expectedChanges) == 1
    chg = res.expectedChanges[0]
    assert chg.operationId == "op-1"
    assert chg.before == (cell.normalizedText or cell.text)
    assert chg.after == "REPLACEMENT"


# ── T03: expectedBefore 불일치 → review로 강등 ────────────────────────────────

def test_expected_before_mismatch_demotes_to_review(contract, dry_run, parsed_metadata):
    t_id, cell = _first_text_cell(parsed_metadata)
    plan = _make_setcelltext_plan(contract, t_id, cell.row, cell.col,
                                    expected="WRONG_PREVIOUS_VALUE")
    res = dry_run.dry_run_edit_plan(plan, parsed_metadata)
    assert res.verdict == "REVIEW_REQUIRED"
    assert "op-1" in res.reviewRequiredOps
    assert "op-1" not in res.autoAllowedOps
    assert any(f.code == "EXPECTED_BEFORE_MISMATCH" for f in res.safetyFindings)


# ── T04: setCellFillColor는 항상 REVIEW_REQUIRED ──────────────────────────────

def test_set_cell_fill_color_dry_run_review_required(contract, dry_run, parsed_metadata):
    t_id, cell = _first_text_cell(parsed_metadata)
    plan = contract.empty_plan_skeleton("p-fill", "sha:1", "ai", "now")
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
    res = dry_run.dry_run_edit_plan(plan, parsed_metadata)
    assert res.verdict == "REVIEW_REQUIRED"
    assert "op-fill" in res.reviewRequiredOps
    assert res.autoExecutable is False


# ── T05: blocked operation은 BLOCKED_UNSAFE ──────────────────────────────────

def test_blocked_operation_dry_run_blocks(contract, dry_run, parsed_metadata):
    plan = contract.empty_plan_skeleton("p-blk", "sha:1", "ai", "now")
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
    res = dry_run.dry_run_edit_plan(plan, parsed_metadata)
    assert res.verdict == "BLOCKED_UNSAFE"
    assert "op-move" in res.blockedOps
    assert res.autoExecutable is False
    # blocked는 expectedChanges에 포함되지 않아야 함
    assert all(c.operationId != "op-move" for c in res.expectedChanges)


# ── T06: unknown operation은 BLOCKED_INVALID_PLAN ─────────────────────────────

def test_unknown_operation_dry_run_blocked_invalid(contract, dry_run, parsed_metadata):
    plan = contract.empty_plan_skeleton("p-unk", "sha:1", "ai", "now")
    plan["operations"] = [{
        "operationId": "op-zzz",
        "operationType": "setCellMagicGlow",
        "target": {"tableId": "t", "row": 0, "col": 0},
        "value": None,
        "preserveStyle": True,
        "expectedBefore": None,
        "riskLevel": "low",
        "requiresReview": False,
        "reason": "?",
    }]
    res = dry_run.dry_run_edit_plan(plan, parsed_metadata)
    # contract가 OP_UNKNOWN_TYPE → blocked로 분류 → dry-run에서도 그대로
    assert res.verdict in ("BLOCKED_UNSAFE", "BLOCKED_INVALID_PLAN")
    assert res.autoExecutable is False


# ── T07: manual/ai/system 동등성 ─────────────────────────────────────────────

@pytest.mark.parametrize("cb", ["manual", "ai", "system"])
def test_created_by_does_not_change_dry_run_result(contract, dry_run,
                                                       parsed_metadata, cb):
    t_id, cell = _first_text_cell(parsed_metadata)
    plan = _make_setcelltext_plan(contract, t_id, cell.row, cell.col,
                                    expected=cell.normalizedText or cell.text,
                                    created_by=cb)
    res = dry_run.dry_run_edit_plan(plan, parsed_metadata)
    assert res.verdict == "PASS_AUTO_ALLOWED"
    assert res.autoExecutable is True


def test_manual_and_ai_produce_identical_buckets(contract, dry_run, parsed_metadata):
    t_id, cell = _first_text_cell(parsed_metadata)
    base = _make_setcelltext_plan(contract, t_id, cell.row, cell.col,
                                    expected=cell.normalizedText or cell.text)
    r_manual = dry_run.dry_run_edit_plan({**base, "createdBy": "manual"}, parsed_metadata)
    r_ai = dry_run.dry_run_edit_plan({**base, "createdBy": "ai"}, parsed_metadata)
    r_sys = dry_run.dry_run_edit_plan({**base, "createdBy": "system"}, parsed_metadata)
    assert r_manual.autoAllowedOps == r_ai.autoAllowedOps == r_sys.autoAllowedOps
    assert r_manual.reviewRequiredOps == r_ai.reviewRequiredOps == r_sys.reviewRequiredOps
    assert r_manual.blockedOps == r_ai.blockedOps == r_sys.blockedOps


# ── T08: 존재하지 않는 셀 target → BLOCKED ────────────────────────────────────

def test_target_not_found_demotes_to_blocked(contract, dry_run, parsed_metadata):
    plan = _make_setcelltext_plan(contract, "t_nonexistent_999", 99, 99,
                                    expected="x")
    res = dry_run.dry_run_edit_plan(plan, parsed_metadata)
    assert "op-1" in res.blockedOps
    assert any(f.code == "TARGET_CELL_NOT_FOUND" for f in res.safetyFindings)
    assert res.autoExecutable is False


# ── T09: 원본 파일 무수정 ─────────────────────────────────────────────────────

def test_original_file_unmodified_after_dry_run(contract, dry_run, parsed_metadata):
    sha_before = hashlib.sha256(METADATA_FORM.read_bytes()).hexdigest()
    mtime_before = METADATA_FORM.stat().st_mtime
    t_id, cell = _first_text_cell(parsed_metadata)
    plan = _make_setcelltext_plan(contract, t_id, cell.row, cell.col,
                                    expected=cell.normalizedText or cell.text)
    res = dry_run.dry_run_edit_plan(plan, parsed_metadata)
    sha_after = hashlib.sha256(METADATA_FORM.read_bytes()).hexdigest()
    mtime_after = METADATA_FORM.stat().st_mtime
    assert sha_before == sha_after, "원본 파일이 수정됨"
    assert mtime_before == mtime_after, "원본 mtime이 변경됨"
    assert res.originalUnmodified is True
    assert res.writerCalled is False
    assert res.outputCreated is False


# ── T10: output 미생성 (output 폴더 미증가) ───────────────────────────────────

def test_no_output_files_created(contract, dry_run, parsed_metadata, tmp_path):
    """dry-run 호출 전후 tmp 경로의 파일 수가 변하지 않아야 한다."""
    before = sorted(p.name for p in tmp_path.iterdir())
    t_id, cell = _first_text_cell(parsed_metadata)
    plan = _make_setcelltext_plan(contract, t_id, cell.row, cell.col,
                                    expected=cell.normalizedText or cell.text)
    dry_run.dry_run_edit_plan(plan, parsed_metadata)
    after = sorted(p.name for p in tmp_path.iterdir())
    assert before == after


# ── T11: sourceDocumentHash 매칭 ─────────────────────────────────────────────

def test_source_document_hash_match_flag(contract, dry_run, parsed_metadata):
    t_id, cell = _first_text_cell(parsed_metadata)
    plan = _make_setcelltext_plan(contract, t_id, cell.row, cell.col,
                                    expected=cell.normalizedText or cell.text)
    plan["sourceDocumentHash"] = "sha256:expected"
    # matched
    r_ok = dry_run.dry_run_edit_plan(plan, parsed_metadata,
                                       source_document_hash="sha256:expected")
    assert r_ok.sourceDocumentHashMatched is True
    assert r_ok.autoExecutable is True
    # mismatched → 일치 안 함 → autoExecutable False
    r_mis = dry_run.dry_run_edit_plan(plan, parsed_metadata,
                                        source_document_hash="sha256:DIFFERENT")
    assert r_mis.sourceDocumentHashMatched is False
    assert r_mis.autoExecutable is False
    assert any(f.code == "SOURCE_HASH_MISMATCH" for f in r_mis.safetyFindings)


# ── T12: 결과 직렬화 ─────────────────────────────────────────────────────────

def test_dry_run_result_to_dict_has_expected_keys(contract, dry_run, parsed_metadata):
    t_id, cell = _first_text_cell(parsed_metadata)
    plan = _make_setcelltext_plan(contract, t_id, cell.row, cell.col,
                                    expected=cell.normalizedText or cell.text)
    res = dry_run.dry_run_edit_plan(plan, parsed_metadata)
    d = res.to_dict()
    for k in ("dryRunId", "planId", "schemaVersion", "verdict",
              "autoExecutable", "autoAllowedOps", "reviewRequiredOps",
              "blockedOps", "expectedChanges", "safetyFindings",
              "sourceDocumentHashMatched", "originalUnmodified",
              "writerCalled", "outputCreated"):
        assert k in d
    assert d["schemaVersion"] == "edit_plan_v1"
