"""HWPX-GENERIC-EDIT-PLAN-CONTRACT-01 테스트.

EditPlan 계약 모듈의 schema/safety/operation 분류 검증.
실제 writer 실행 없음. dict 단위 계약 테스트만.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))


@pytest.fixture
def contract():
    from hwpx.pipeline import generic_edit_plan_contract as c
    return c


def _make_plan(contract, ops, **plan_overrides) -> dict:
    plan = contract.empty_plan_skeleton(
        plan_id="plan-001",
        source_doc_hash="sha256:abc",
        created_by="ai",
        created_at="2026-05-18T00:00:00Z",
    )
    plan["operations"] = ops
    plan.update(plan_overrides)
    return plan


def _set_cell_text_op(contract, **overrides) -> dict:
    op = {
        "operationId": "op-1",
        "operationType": "setCellText",
        "target": {"tableId": "t_s0_000", "row": 1, "col": 2},
        "value": "New value",
        "preserveStyle": True,
        "expectedBefore": "Old value",
        "riskLevel": "low",
        "requiresReview": False,
        "reason": "user typed correction",
    }
    op.update(overrides)
    return op


# ── T01: SchemaVersion 고정 ───────────────────────────────────────────────────

def test_schema_version_is_v1(contract):
    assert contract.SCHEMA_VERSION == "edit_plan_v1"


def test_skeleton_uses_pinned_schema_version(contract):
    plan = contract.empty_plan_skeleton("p", "sha:1", "manual", "now")
    assert plan["schemaVersion"] == contract.SCHEMA_VERSION


def test_schema_version_mismatch_blocks(contract):
    plan = _make_plan(contract, [_set_cell_text_op(contract)], schemaVersion="edit_plan_v999")
    result = contract.validate_edit_plan(plan)
    assert result.verdict == "BLOCKED_INVALID_PLAN"
    assert any(i.code == "SCHEMA_VERSION_MISMATCH" for i in result.issues)


# ── T02: setCellText 정상 ─────────────────────────────────────────────────────

def test_valid_set_cell_text_plan_passes_auto(contract):
    plan = _make_plan(contract, [_set_cell_text_op(contract)])
    result = contract.validate_edit_plan(plan)
    assert result.verdict == "PASS_AUTO_ALLOWED", result.to_dict()
    assert "op-1" in result.autoAllowedOps
    assert result.blockedOps == []


# ── T03: setCellFillColor는 review 필요 ───────────────────────────────────────

def test_set_cell_fill_color_requires_review(contract):
    op = _set_cell_text_op(contract,
        operationId="op-fill",
        operationType="setCellFillColor",
        value="#FFFF00",
        expectedBefore=None,
    )
    plan = _make_plan(contract, [op])
    result = contract.validate_edit_plan(plan)
    assert result.verdict == "REVIEW_REQUIRED", result.to_dict()
    assert "op-fill" in result.reviewRequiredOps


# ── T04: expectedBefore 누락 차단 ─────────────────────────────────────────────

def test_overwrite_op_without_expected_before_is_blocked(contract):
    op = _set_cell_text_op(contract)
    del op["expectedBefore"]
    plan = _make_plan(contract, [op])
    result = contract.validate_edit_plan(plan)
    assert result.verdict == "BLOCKED_UNSAFE"
    assert any(i.code == "OP_EXPECTED_BEFORE_MISSING" for i in result.issues)


# ── T05: 금지 operationType ───────────────────────────────────────────────────

@pytest.mark.parametrize("blocked_type", [
    "moveObject", "deleteObject", "editShapeText", "editNestedTableCell",
    "mergeCells", "splitCells", "insertImage", "replaceImage",
    "deleteTable", "structuralRewrite",
])
def test_blocked_operation_types_are_blocked(contract, blocked_type):
    op = _set_cell_text_op(contract, operationType=blocked_type, expectedBefore=None)
    plan = _make_plan(contract, [op])
    result = contract.validate_edit_plan(plan)
    assert result.verdict == "BLOCKED_UNSAFE"
    assert any(i.code == "OP_BLOCKED_TYPE" for i in result.issues)


def test_nested_table_direct_edit_is_blocked(contract):
    op = _set_cell_text_op(contract, operationType="editNestedTableCell")
    plan = _make_plan(contract, [op])
    result = contract.validate_edit_plan(plan)
    assert result.verdict == "BLOCKED_UNSAFE"


def test_object_edit_is_blocked(contract):
    for op_type in ("moveObject", "deleteObject", "editShapeText"):
        op = _set_cell_text_op(contract, operationType=op_type)
        plan = _make_plan(contract, [op])
        result = contract.validate_edit_plan(plan)
        assert result.verdict == "BLOCKED_UNSAFE", f"{op_type} should be blocked"


# ── T06: 알 수 없는 operationType ─────────────────────────────────────────────

def test_unknown_operation_type_is_blocked(contract):
    op = _set_cell_text_op(contract, operationType="setCellMagicGlow")
    plan = _make_plan(contract, [op])
    result = contract.validate_edit_plan(plan)
    assert result.verdict == "BLOCKED_UNSAFE"
    assert any(i.code == "OP_UNKNOWN_TYPE" for i in result.issues)


# ── T07: createdBy manual / ai 모두 동일 schema ──────────────────────────────

def test_manual_created_by_plan_passes(contract):
    plan = _make_plan(contract, [_set_cell_text_op(contract)], createdBy="manual")
    result = contract.validate_edit_plan(plan)
    assert result.verdict == "PASS_AUTO_ALLOWED"


def test_ai_created_by_plan_passes(contract):
    plan = _make_plan(contract, [_set_cell_text_op(contract)], createdBy="ai")
    result = contract.validate_edit_plan(plan)
    assert result.verdict == "PASS_AUTO_ALLOWED"


def test_system_created_by_plan_passes(contract):
    plan = _make_plan(contract, [_set_cell_text_op(contract)], createdBy="system")
    result = contract.validate_edit_plan(plan)
    assert result.verdict == "PASS_AUTO_ALLOWED"


def test_unknown_created_by_blocks(contract):
    plan = _make_plan(contract, [_set_cell_text_op(contract)], createdBy="hacker")
    result = contract.validate_edit_plan(plan)
    assert result.verdict == "BLOCKED_INVALID_PLAN"
    assert any(i.code == "PLAN_CREATED_BY_INVALID" for i in result.issues)


def test_executor_treats_manual_and_ai_identically(contract):
    """동일 plan body는 createdBy만 달라도 같은 verdict가 나와야 한다."""
    base = [_set_cell_text_op(contract)]
    r_manual = contract.validate_edit_plan(_make_plan(contract, base, createdBy="manual"))
    r_ai = contract.validate_edit_plan(_make_plan(contract, base, createdBy="ai"))
    r_sys = contract.validate_edit_plan(_make_plan(contract, base, createdBy="system"))
    assert r_manual.verdict == r_ai.verdict == r_sys.verdict == "PASS_AUTO_ALLOWED"
    assert r_manual.autoAllowedOps == r_ai.autoAllowedOps == r_sys.autoAllowedOps


# ── T08: reviewRequired 분류 검증 ─────────────────────────────────────────────

def test_review_required_when_op_has_requires_review_flag(contract):
    op = _set_cell_text_op(contract, requiresReview=True)
    plan = _make_plan(contract, [op])
    result = contract.validate_edit_plan(plan)
    assert result.verdict == "REVIEW_REQUIRED"


def test_review_required_when_risk_level_high(contract):
    op = _set_cell_text_op(contract, riskLevel="high")
    plan = _make_plan(contract, [op])
    result = contract.validate_edit_plan(plan)
    assert result.verdict == "REVIEW_REQUIRED"


def test_review_required_operations_constant_includes_style_changes(contract):
    expected = {"setCellFillColor", "setCellTextStyle", "appendParagraph"}
    assert expected.issubset(contract.REVIEW_REQUIRED_OPERATION_TYPES)


# ── T09: target 검증 ─────────────────────────────────────────────────────────

def test_cell_op_missing_target_table_blocks(contract):
    op = _set_cell_text_op(contract, target={"row": 0, "col": 0})
    plan = _make_plan(contract, [op])
    result = contract.validate_edit_plan(plan)
    assert result.verdict == "BLOCKED_UNSAFE"
    assert any(i.code == "OP_TARGET_MISSING" for i in result.issues)


def test_paragraph_op_requires_paragraph_index_or_table(contract):
    op = {
        "operationId": "op-p",
        "operationType": "appendParagraph",
        "target": {},
        "value": "new paragraph",
        "preserveStyle": True,
        "expectedBefore": None,
        "riskLevel": "low",
        "requiresReview": False,
        "reason": "manual append",
    }
    plan = _make_plan(contract, [op])
    result = contract.validate_edit_plan(plan)
    assert result.verdict == "BLOCKED_UNSAFE"
    assert any(i.code == "OP_TARGET_MISSING" for i in result.issues)


# ── T10: safety / sourceDocumentHash ──────────────────────────────────────────

def test_source_doc_hash_required_when_safety_demands(contract):
    plan = _make_plan(contract, [_set_cell_text_op(contract)], sourceDocumentHash="")
    result = contract.validate_edit_plan(plan)
    assert result.verdict == "BLOCKED_INVALID_PLAN"
    assert any(i.code == "SOURCE_DOC_HASH_REQUIRED" for i in result.issues)


def test_safety_missing_field_blocks(contract):
    plan = _make_plan(contract, [_set_cell_text_op(contract)])
    del plan["safety"]["noImplicitOverwrite"]
    result = contract.validate_edit_plan(plan)
    assert result.verdict == "BLOCKED_INVALID_PLAN"
    assert any(i.code == "SAFETY_MISSING_FIELD" for i in result.issues)


def test_default_safety_includes_blocked_operations(contract):
    s = contract.default_safety()
    assert "moveObject" in s["blockedOperations"]
    assert "deleteTable" in s["blockedOperations"]


# ── T11: 빈/이상한 operations ─────────────────────────────────────────────────

def test_empty_operations_blocks(contract):
    plan = _make_plan(contract, [])
    result = contract.validate_edit_plan(plan)
    assert result.verdict == "BLOCKED_INVALID_PLAN"
    assert any(i.code == "OPS_EMPTY" for i in result.issues)


def test_operations_not_list_blocks(contract):
    plan = _make_plan(contract, [_set_cell_text_op(contract)])
    plan["operations"] = "not a list"
    result = contract.validate_edit_plan(plan)
    assert result.verdict == "BLOCKED_INVALID_PLAN"
    assert any(i.code == "OPS_NOT_LIST" for i in result.issues)


# ── T12: 분류 일관성 ─────────────────────────────────────────────────────────

def test_blocked_and_review_classification_does_not_overlap(contract):
    block_set = contract.BLOCKED_OPERATION_TYPES
    allow_set = contract.ALLOWED_OPERATION_TYPES
    assert block_set.isdisjoint(allow_set), "허용/금지 set이 겹치면 안 됨"
