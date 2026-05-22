"""HWPX-EDIT-PLAN-WRITER-ADAPTER-DRY-RUN-01

Review Gate를 통과한 READY_AFTER_REVIEW 결과(+ dry-run + plan)를 받아
실제 HWPX writer에 넘길 호출 인자 패키지(WriterCallPlan)를 dry-run으로 산출한다.

이 모듈은 writer를 호출하지 않으며 output HWPX를 생성하지 않는다.
원본 파일은 절대 수정되지 않는다. WriterCallSpec dict를 만들어 반환할 뿐이다.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from . import generic_edit_plan_contract as contract


# operation → writer method whitelist
OPERATION_TO_WRITER_METHOD: dict[str, str] = {
    "setCellText": "writer.set_cell_text",
    "setParagraphText": "writer.set_paragraph_text",
    "setCellHorizontalAlign": "writer.set_cell_horizontal_align",
    "setCellVerticalAlign": "writer.set_cell_vertical_align",
    "replaceTextRun": "writer.replace_text_run",
    "setCellFillColor": "writer.set_cell_fill_color",
    "setCellTextStyle": "writer.set_cell_text_style",
    "appendParagraph": "writer.append_paragraph",
}

# expectedBefore가 반드시 있어야 변환 가능한 overwrite 성격 ops
_OVERWRITE_OPS: frozenset[str] = frozenset({
    "setCellText", "setParagraphText",
    "setCellHorizontalAlign", "setCellVerticalAlign",
    "setCellFillColor", "setCellTextStyle", "replaceTextRun",
})

# review-required ops은 반드시 approvedOps에 있어야 변환 허용
_REVIEW_REQUIRED_OPS: frozenset[str] = contract.REVIEW_REQUIRED_OPERATION_TYPES


# ── 결과 dataclass ────────────────────────────────────────────────────────────

@dataclass
class WriterCallSpec:
    commandId: str
    planId: str
    operationId: str
    operationType: str
    writerMethod: str
    target: dict
    value: Any
    expectedBefore: Any
    preserveStyle: bool
    riskLevel: str
    approvedBy: str
    sourceDocumentHash: str

    def to_dict(self) -> dict:
        return {
            "commandId": self.commandId,
            "planId": self.planId,
            "operationId": self.operationId,
            "operationType": self.operationType,
            "writerMethod": self.writerMethod,
            "target": self.target,
            "value": self.value,
            "expectedBefore": self.expectedBefore,
            "preserveStyle": self.preserveStyle,
            "riskLevel": self.riskLevel,
            "approvedBy": self.approvedBy,
            "sourceDocumentHash": self.sourceDocumentHash,
        }


@dataclass
class SkippedOp:
    operationId: str
    operationType: str
    reason: str

    def to_dict(self) -> dict:
        return {
            "operationId": self.operationId,
            "operationType": self.operationType,
            "reason": self.reason,
        }


@dataclass
class AdapterFinding:
    code: str
    detail: str
    operationId: str | None = None

    def to_dict(self) -> dict:
        return {"code": self.code, "detail": self.detail,
                "operationId": self.operationId}


@dataclass
class WriterCallPlan:
    adapterId: str = ""
    planId: str = ""
    verdict: str = "BLOCKED_NOT_READY"
    readyForWriter: bool = False
    writerCalls: list[WriterCallSpec] = field(default_factory=list)
    skippedOps: list[SkippedOp] = field(default_factory=list)
    blockedOps: list[str] = field(default_factory=list)
    safetyFindings: list[AdapterFinding] = field(default_factory=list)
    writerCalled: bool = False
    outputCreated: bool = False
    originalUnmodified: bool = True

    def to_dict(self) -> dict:
        return {
            "adapterId": self.adapterId,
            "planId": self.planId,
            "verdict": self.verdict,
            "readyForWriter": self.readyForWriter,
            "writerCalls": [w.to_dict() for w in self.writerCalls],
            "skippedOps": [s.to_dict() for s in self.skippedOps],
            "blockedOps": self.blockedOps,
            "safetyFindings": [f.to_dict() for f in self.safetyFindings],
            "writerCalled": self.writerCalled,
            "outputCreated": self.outputCreated,
            "originalUnmodified": self.originalUnmodified,
        }


# ── 헬퍼 ──────────────────────────────────────────────────────────────────────

def _as_dict(obj) -> dict:
    if obj is None:
        return {}
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if isinstance(obj, dict):
        return obj
    return {}


def _reviewer_for_op(gate_dict: dict, op_id: str) -> str | None:
    for entry in gate_dict.get("auditLog", []) or []:
        if entry.get("operationId") == op_id and entry.get("decision") == "APPROVE":
            return entry.get("reviewer")
    return None


# ── 메인 함수 ────────────────────────────────────────────────────────────────

def build_writer_call_plan(plan: dict, dry_run_result,
                              review_gate_result=None) -> WriterCallPlan:
    """plan + dry-run + review gate 결과에서 writer 호출 인자 dry-run 산출.

    writer는 호출되지 않고 output 파일도 만들어지지 않는다.
    """
    plan = plan if isinstance(plan, dict) else {}
    dr = _as_dict(dry_run_result)
    gate = _as_dict(review_gate_result)

    plan_id = plan.get("planId", "") or dr.get("planId", "")
    source_hash = plan.get("sourceDocumentHash", "")
    created_by = plan.get("createdBy", "system")

    result = WriterCallPlan(
        adapterId=str(uuid.uuid4()),
        planId=plan_id,
        blockedOps=list(dr.get("blockedOps", []) or []),
    )

    # 1) dry-run이 blocked면 즉시 차단
    dr_verdict = dr.get("verdict", "")
    if dr_verdict in ("BLOCKED_INVALID_PLAN", "BLOCKED_UNSAFE"):
        result.verdict = "BLOCKED_NOT_READY"
        result.safetyFindings.append(AdapterFinding(
            "DRY_RUN_BLOCKED",
            f"dry-run verdict={dr_verdict!r}; writer adapter refuses to convert",
        ))
        return result

    auto_ops = set(dr.get("autoAllowedOps", []) or [])
    review_ops = set(dr.get("reviewRequiredOps", []) or [])

    # 2) review 필요 op이 있으면 게이트 통과 검사
    has_review_ops = bool(review_ops)
    gate_verdict = gate.get("gateVerdict", "")
    approved_ops = set(gate.get("approvedOps", []) or [])

    if has_review_ops:
        if gate_verdict != "READY_AFTER_REVIEW":
            result.verdict = "BLOCKED_NOT_READY"
            result.safetyFindings.append(AdapterFinding(
                "GATE_NOT_READY",
                f"reviewRequiredOps={sorted(review_ops)} but "
                f"gateVerdict={gate_verdict!r} (need READY_AFTER_REVIEW)",
            ))
            # review op은 skipped로 기록
            for op_id in sorted(review_ops):
                result.skippedOps.append(SkippedOp(
                    operationId=op_id, operationType="",
                    reason=f"gateVerdict={gate_verdict!r}",
                ))
            return result
        # gate가 READY_AFTER_REVIEW면 review op은 반드시 approvedOps에 모두 있어야 한다
        missing = review_ops - approved_ops
        if missing:
            result.verdict = "BLOCKED_NOT_READY"
            result.safetyFindings.append(AdapterFinding(
                "REVIEW_OPS_NOT_FULLY_APPROVED",
                f"missing approvals={sorted(missing)}",
            ))
            return result

    # 3) 변환 후보 = autoAllowedOps ∪ approvedOps (게이트가 있을 때만 approvedOps 사용)
    allowed_for_writer = set(auto_ops)
    if has_review_ops:
        allowed_for_writer |= approved_ops

    # 4) operation 단위 변환
    operations = plan.get("operations", []) or []
    blocked_set = set(result.blockedOps)
    for op in operations:
        if not isinstance(op, dict):
            continue
        op_id = op.get("operationId", "")
        op_type = op.get("operationType", "")

        # 4-1) 차단 op은 절대 변환 금지 (우회 시도 포함)
        if op_id in blocked_set or op_type in contract.BLOCKED_OPERATION_TYPES:
            result.safetyFindings.append(AdapterFinding(
                "BLOCKED_OP_REFUSED",
                f"operationType={op_type!r} is blocked; cannot become writer call",
                op_id,
            ))
            result.skippedOps.append(SkippedOp(
                operationId=op_id, operationType=op_type,
                reason="blocked_or_not_allowlisted",
            ))
            continue

        # 4-2) writer method whitelist
        writer_method = OPERATION_TO_WRITER_METHOD.get(op_type)
        if writer_method is None:
            result.safetyFindings.append(AdapterFinding(
                "WRITER_METHOD_NOT_WHITELISTED",
                f"no writer mapping for operationType={op_type!r}",
                op_id,
            ))
            result.skippedOps.append(SkippedOp(
                operationId=op_id, operationType=op_type,
                reason="no_writer_method_mapping",
            ))
            continue

        # 4-3) 허용 버킷에 있는 op만 진행
        if op_id not in allowed_for_writer:
            result.skippedOps.append(SkippedOp(
                operationId=op_id, operationType=op_type,
                reason="not_in_auto_or_approved",
            ))
            continue

        # 4-4) review-required op은 반드시 approvedOps에 있어야 함
        if op_type in _REVIEW_REQUIRED_OPS and op_id not in approved_ops:
            result.skippedOps.append(SkippedOp(
                operationId=op_id, operationType=op_type,
                reason="review_required_but_not_approved",
            ))
            result.safetyFindings.append(AdapterFinding(
                "REVIEW_REQUIRED_NOT_APPROVED",
                f"operationType={op_type!r} requires explicit approval",
                op_id,
            ))
            continue

        # 4-5) expectedBefore 강제
        if op_type in _OVERWRITE_OPS and "expectedBefore" not in op:
            result.skippedOps.append(SkippedOp(
                operationId=op_id, operationType=op_type,
                reason="expectedBefore_missing",
            ))
            result.safetyFindings.append(AdapterFinding(
                "EXPECTED_BEFORE_REQUIRED",
                f"expectedBefore key required for {op_type!r}", op_id,
            ))
            continue

        # 4-6) approvedBy 결정
        if op_id in auto_ops:
            approved_by = created_by   # auto-allowed는 plan.createdBy 책임
        else:
            reviewer = _reviewer_for_op(gate, op_id)
            if not reviewer:
                result.skippedOps.append(SkippedOp(
                    operationId=op_id, operationType=op_type,
                    reason="reviewer_not_recorded_in_audit_log",
                ))
                continue
            approved_by = reviewer

        # 4-7) WriterCallSpec 생성
        result.writerCalls.append(WriterCallSpec(
            commandId=str(uuid.uuid4()),
            planId=plan_id,
            operationId=op_id,
            operationType=op_type,
            writerMethod=writer_method,
            target=dict(op.get("target") or {}),
            value=op.get("value"),
            expectedBefore=op.get("expectedBefore"),
            preserveStyle=bool(op.get("preserveStyle", True)),
            riskLevel=op.get("riskLevel", "low"),
            approvedBy=approved_by,
            sourceDocumentHash=source_hash,
        ))

    # 5) 최종 verdict
    if result.writerCalls and not result.blockedOps:
        result.verdict = "READY_FOR_WRITER"
        result.readyForWriter = True
    elif result.writerCalls and result.blockedOps:
        # 일부 변환 + 차단 잔존 → 보수적으로 NOT_READY
        result.verdict = "BLOCKED_NOT_READY"
        result.readyForWriter = False
    else:
        result.verdict = "BLOCKED_NOT_READY"
        result.readyForWriter = False

    # 불변식
    result.writerCalled = False
    result.outputCreated = False
    result.originalUnmodified = True
    return result
