"""HWPX-GENERIC-EDIT-PLAN-CONTRACT-01

AI 작업대와 수동 브라우저 작업대가 공통으로 사용하는
HWPX Generic Edit Plan 계약 모듈 (read-only 설계).

이 모듈은 실제 writer 실행을 하지 않는다.
편집 명령 스키마, 안전 게이트, 감사 로그 기준을 정의하고
plan dict가 계약을 만족하는지 검증한다.

검증 결과 verdict:
- PASS_AUTO_ALLOWED       : 모든 안전 조건 충족, 자동 실행 가능
- REVIEW_REQUIRED         : schema는 valid, 사람 검토 필요
- BLOCKED_INVALID_PLAN    : schema 결함 (구조/필드 누락)
- BLOCKED_UNSAFE          : 금지 operationType / 위험 등급으로 차단
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SCHEMA_VERSION = "edit_plan_v1"

# ── 허용 operationType (1차 지원) ─────────────────────────────────────────────
ALLOWED_OPERATION_TYPES: frozenset[str] = frozenset({
    "setCellText",
    "setParagraphText",
    "setCellFillColor",
    "setCellHorizontalAlign",
    "setCellVerticalAlign",
    "setCellTextStyle",
    "appendParagraph",
    "replaceTextRun",
})

# ── 명시적 금지 operationType (이번 공정 범위 밖) ─────────────────────────────
BLOCKED_OPERATION_TYPES: frozenset[str] = frozenset({
    "moveObject",
    "deleteObject",
    "editShapeText",
    "editNestedTableCell",
    "mergeCells",
    "splitCells",
    "insertImage",
    "replaceImage",
    "deleteTable",
    "structuralRewrite",
})

# ── 사람 검토 필수 operationType (자동 실행 금지) ─────────────────────────────
REVIEW_REQUIRED_OPERATION_TYPES: frozenset[str] = frozenset({
    "setCellFillColor",
    "setCellTextStyle",
    "appendParagraph",
})

# ── 작업자 출처 ───────────────────────────────────────────────────────────────
ALLOWED_CREATED_BY: frozenset[str] = frozenset({"manual", "ai", "system"})

# ── 위험 등급 ─────────────────────────────────────────────────────────────────
ALLOWED_RISK_LEVELS: frozenset[str] = frozenset({"low", "medium", "high"})

# ── 필수 EditPlan 최상위 키 ───────────────────────────────────────────────────
REQUIRED_PLAN_FIELDS: tuple[str, ...] = (
    "planId",
    "schemaVersion",
    "sourceDocumentHash",
    "createdBy",
    "createdAt",
    "operations",
    "safety",
)

# ── 필수 Operation 키 ─────────────────────────────────────────────────────────
REQUIRED_OPERATION_FIELDS: tuple[str, ...] = (
    "operationId",
    "operationType",
    "target",
    "preserveStyle",
    "riskLevel",
    "requiresReview",
    "reason",
)

# ── 필수 Target 키 (operationType별로 일부 키만 요구) ─────────────────────────
# 표 셀 대상: tableId, row, col 필수
_CELL_OPS: frozenset[str] = frozenset({
    "setCellText",
    "setCellFillColor",
    "setCellHorizontalAlign",
    "setCellVerticalAlign",
    "setCellTextStyle",
})
# 단락 대상: paragraphIndex 필수
_PARAGRAPH_OPS: frozenset[str] = frozenset({
    "setParagraphText",
    "appendParagraph",
    "replaceTextRun",
})

# ── 필수 Safety 키 ────────────────────────────────────────────────────────────
REQUIRED_SAFETY_FIELDS: tuple[str, ...] = (
    "originalHashRequired",
    "expectedBeforeRequired",
    "noImplicitOverwrite",
    "preserveUnknownXml",
    "reviewRequiredOnConflict",
)


# ──────────────────────────────────────────────────────────────────────────────
# Dataclass 표현 (직렬화는 dict로, 정식 IO는 dict 단위)
# ──────────────────────────────────────────────────────────────────────────────


@dataclass
class Target:
    tableId: str | None = None
    row: int | None = None
    col: int | None = None
    visualRow: int | None = None
    visualCol: int | None = None
    paragraphIndex: int | None = None
    runIndex: int | None = None
    objectId: str | None = None
    sectionIndex: int | None = None


@dataclass
class Operation:
    operationId: str = ""
    operationType: str = ""
    target: dict = field(default_factory=dict)
    value: Any = None
    preserveStyle: bool = True
    expectedBefore: Any = None
    riskLevel: str = "low"
    requiresReview: bool = False
    reason: str = ""


@dataclass
class Safety:
    originalHashRequired: bool = True
    expectedBeforeRequired: bool = True
    noImplicitOverwrite: bool = True
    preserveUnknownXml: bool = True
    reviewRequiredOnConflict: bool = True
    allowedWithoutReview: list[str] = field(default_factory=list)
    blockedOperations: list[str] = field(default_factory=lambda: sorted(BLOCKED_OPERATION_TYPES))


@dataclass
class AuditTrailEntry:
    actor: str = "system"  # manual/ai/system
    action: str = ""
    at: str = ""
    note: str = ""


@dataclass
class ValidationIssue:
    code: str
    detail: str
    operationId: str | None = None


@dataclass
class ValidationResult:
    verdict: str = "BLOCKED_INVALID_PLAN"
    issues: list[ValidationIssue] = field(default_factory=list)
    autoAllowedOps: list[str] = field(default_factory=list)
    reviewRequiredOps: list[str] = field(default_factory=list)
    blockedOps: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "issues": [
                {"code": i.code, "detail": i.detail, "operationId": i.operationId}
                for i in self.issues
            ],
            "autoAllowedOps": self.autoAllowedOps,
            "reviewRequiredOps": self.reviewRequiredOps,
            "blockedOps": self.blockedOps,
        }


# ──────────────────────────────────────────────────────────────────────────────
# 검증 로직
# ──────────────────────────────────────────────────────────────────────────────


def _missing_fields(d: dict, required: tuple[str, ...]) -> list[str]:
    return [k for k in required if k not in d]


def _validate_target(op_type: str, target: dict) -> list[str]:
    """operationType에 따라 target 필수 키를 검증, 누락된 키 목록을 반환."""
    if not isinstance(target, dict):
        return ["target_must_be_object"]
    missing: list[str] = []
    if op_type in _CELL_OPS:
        missing.extend(f"target.{k}" for k in ("tableId", "row", "col") if k not in target or target[k] is None)
    elif op_type in _PARAGRAPH_OPS and (
        target.get("paragraphIndex") is None
        and target.get("paragraphKey") is None
        and target.get("tableId") is None
    ):
        missing.append("target.paragraphIndex_or_paragraphKey_or_tableId")
    return missing


def _validate_operation(op: dict, idx: int) -> tuple[list[ValidationIssue], str]:
    """operation 1건 검증. (issues, bucket) — bucket은 auto/review/blocked."""
    op_id = op.get("operationId") if isinstance(op, dict) else None

    if not isinstance(op, dict):
        return [ValidationIssue("OP_NOT_OBJECT", f"operations[{idx}] is not an object")], "blocked"

    missing = _missing_fields(op, REQUIRED_OPERATION_FIELDS)
    issues: list[ValidationIssue] = [ValidationIssue("OP_MISSING_FIELD", f"operations[{idx}].{k}", op_id) for k in missing]

    op_type = op.get("operationType", "")
    if op_type in BLOCKED_OPERATION_TYPES:
        issues.append(
            ValidationIssue(
                "OP_BLOCKED_TYPE",
                f"operationType={op_type!r} is explicitly blocked in this contract phase",
                op_id,
            )
        )
        return issues, "blocked"

    if op_type not in ALLOWED_OPERATION_TYPES:
        issues.append(
            ValidationIssue(
                "OP_UNKNOWN_TYPE",
                f"operationType={op_type!r} is not in ALLOWED_OPERATION_TYPES",
                op_id,
            )
        )
        return issues, "blocked"

    # target 검증
    target = op.get("target", {})
    issues.extend(ValidationIssue("OP_TARGET_MISSING", t_miss, op_id) for t_miss in _validate_target(op_type, target))

    # riskLevel
    risk = op.get("riskLevel", "")
    if risk not in ALLOWED_RISK_LEVELS:
        issues.append(
            ValidationIssue(
                "OP_RISK_LEVEL_INVALID",
                f"riskLevel={risk!r}",
                op_id,
            )
        )

    # expectedBefore 강제: overwrite 성격 ops는 expectedBefore 필수
    overwrite_ops = {
        "setCellText",
        "setParagraphText",
        "setCellFillColor",
        "setCellHorizontalAlign",
        "setCellVerticalAlign",
        "setCellTextStyle",
        "replaceTextRun",
    }
    if op_type in overwrite_ops and "expectedBefore" not in op:
        issues.append(
            ValidationIssue(
                "OP_EXPECTED_BEFORE_MISSING",
                f"expectedBefore is required for operationType={op_type!r}",
                op_id,
            )
        )

    # 버킷 분류
    if issues:
        return issues, "blocked"

    bucket = (
        "review"
        if (
            op_type in REVIEW_REQUIRED_OPERATION_TYPES
            or op.get("requiresReview") is True
            or risk == "high"
        )
        else "auto"
    )
    return [], bucket


def _validate_top_level_fields(plan: dict) -> list[ValidationIssue]:
    issues = [
        ValidationIssue("PLAN_MISSING_FIELD", k)
        for k in _missing_fields(plan, REQUIRED_PLAN_FIELDS)
    ]
    if plan.get("schemaVersion") != SCHEMA_VERSION:
        issues.append(
            ValidationIssue(
                "SCHEMA_VERSION_MISMATCH",
                f"expected={SCHEMA_VERSION!r}, got={plan.get('schemaVersion')!r}",
            )
        )
    cb = plan.get("createdBy", "")
    if cb not in ALLOWED_CREATED_BY:
        issues.append(
            ValidationIssue(
                "PLAN_CREATED_BY_INVALID",
                f"createdBy={cb!r} not in {sorted(ALLOWED_CREATED_BY)}",
            )
        )
    return issues


def _validate_safety_field(plan: dict) -> list[ValidationIssue]:
    safety = plan.get("safety", {})
    if not isinstance(safety, dict):
        return [ValidationIssue("SAFETY_NOT_OBJECT", "safety must be a dict")]
    issues = [
        ValidationIssue("SAFETY_MISSING_FIELD", k)
        for k in _missing_fields(safety, REQUIRED_SAFETY_FIELDS)
    ]
    if safety.get("originalHashRequired") is True and not plan.get("sourceDocumentHash"):
        issues.append(
            ValidationIssue(
                "SOURCE_DOC_HASH_REQUIRED",
                "safety.originalHashRequired=true but sourceDocumentHash empty",
            )
        )
    return issues


def _classify_operations(
    ops: list,
) -> tuple[list[ValidationIssue], list[str], list[str], list[str]]:
    issues: list[ValidationIssue] = []
    blocked_op_ids: list[str] = []
    review_op_ids: list[str] = []
    auto_op_ids: list[str] = []
    for i, op in enumerate(ops):
        op_issues, bucket = _validate_operation(op, i)
        op_id = op.get("operationId", f"op[{i}]") if isinstance(op, dict) else f"op[{i}]"
        issues.extend(op_issues)
        if bucket == "blocked":
            blocked_op_ids.append(op_id)
        elif bucket == "review":
            review_op_ids.append(op_id)
        else:
            auto_op_ids.append(op_id)
    return issues, blocked_op_ids, review_op_ids, auto_op_ids


_PLAN_LEVEL_INVALID_CODES = {
    "PLAN_MISSING_FIELD",
    "SCHEMA_VERSION_MISMATCH",
    "PLAN_CREATED_BY_INVALID",
    "SAFETY_NOT_OBJECT",
    "SAFETY_MISSING_FIELD",
    "SOURCE_DOC_HASH_REQUIRED",
    "OPS_NOT_LIST",
    "OPS_EMPTY",
    "PLAN_NOT_OBJECT",
}


def _determine_plan_verdict(
    issues: list[ValidationIssue], blocked_op_ids: list[str], review_op_ids: list[str]
) -> str:
    plan_level_invalid = any(i.code in _PLAN_LEVEL_INVALID_CODES for i in issues)
    if plan_level_invalid:
        return "BLOCKED_INVALID_PLAN"
    if blocked_op_ids:
        return "BLOCKED_UNSAFE"
    if review_op_ids:
        return "REVIEW_REQUIRED"
    return "PASS_AUTO_ALLOWED"


def validate_edit_plan(plan: dict) -> ValidationResult:
    """EditPlan dict가 계약을 만족하는지 검증."""
    result = ValidationResult()

    if not isinstance(plan, dict):
        result.issues.append(ValidationIssue("PLAN_NOT_OBJECT", "plan must be a dict"))
        result.verdict = "BLOCKED_INVALID_PLAN"
        return result

    result.issues.extend(_validate_top_level_fields(plan))
    result.issues.extend(_validate_safety_field(plan))

    ops = plan.get("operations", [])
    if not isinstance(ops, list):
        result.issues.append(ValidationIssue("OPS_NOT_LIST", "operations must be a list"))
        result.verdict = "BLOCKED_INVALID_PLAN"
        return result
    if len(ops) == 0:
        result.issues.append(ValidationIssue("OPS_EMPTY", "operations must not be empty"))

    op_issues, blocked_op_ids, review_op_ids, auto_op_ids = _classify_operations(ops)
    result.issues.extend(op_issues)
    result.autoAllowedOps = auto_op_ids
    result.reviewRequiredOps = review_op_ids
    result.blockedOps = blocked_op_ids

    result.verdict = _determine_plan_verdict(result.issues, blocked_op_ids, review_op_ids)
    return result


def default_safety() -> dict:
    """안전 기본값 (manual/AI 양쪽 모두 같은 기본값으로 시작)."""
    return {
        "originalHashRequired": True,
        "expectedBeforeRequired": True,
        "noImplicitOverwrite": True,
        "preserveUnknownXml": True,
        "reviewRequiredOnConflict": True,
        "allowedWithoutReview": [],
        "blockedOperations": sorted(BLOCKED_OPERATION_TYPES),
    }


def empty_plan_skeleton(
    plan_id: str, source_doc_hash: str, created_by: str, created_at: str
) -> dict:
    """빈 EditPlan skeleton dict 생성 (manual UI / AI 모두 동일 출발점)."""
    return {
        "planId": plan_id,
        "schemaVersion": SCHEMA_VERSION,
        "sourceDocumentHash": source_doc_hash,
        "createdBy": created_by,
        "createdAt": created_at,
        "operations": [],
        "safety": default_safety(),
        "auditTrail": [],
    }
