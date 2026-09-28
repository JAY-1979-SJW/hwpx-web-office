"""HWPX-EDIT-PLAN-WRITER-EXECUTOR-NO-OP-MODE-01

WriterCallPlan을 입력받아 writer 실행 직전 단계의 executor를 no-op으로 시뮬레이션한다.

이 모듈은 절대로 실제 writer를 호출하지 않으며 output HWPX를 만들지 않는다.
원본 파일도 수정하지 않는다. WriterCallPlan을 한 번 더 검증해
"이 시점이면 실제 writer를 호출해도 안전한가?" 만 판정한다.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from . import generic_edit_plan_contract as contract
from . import generic_edit_plan_writer_adapter as adapter

# expectedBefore가 반드시 있어야 하는 op type (adapter와 일관)
_OVERWRITE_OPS: frozenset[str] = frozenset({
    "setCellText",
    "setParagraphText",
    "setCellHorizontalAlign",
    "setCellVerticalAlign",
    "setCellFillColor",
    "setCellTextStyle",
    "replaceTextRun",
})

# readback이 권장되는 op (review-required + high risk)
_READBACK_RECOMMENDED_TYPES: frozenset[str] = contract.REVIEW_REQUIRED_OPERATION_TYPES


# ── dataclass ────────────────────────────────────────────────────────────────


@dataclass
class SimulatedCall:
    commandId: str
    operationId: str
    writerMethod: str
    target: dict
    value: Any
    expectedBefore: Any
    simulationStatus: str = "SIMULATED_OK"
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "commandId": self.commandId,
            "operationId": self.operationId,
            "writerMethod": self.writerMethod,
            "target": self.target,
            "value": self.value,
            "expectedBefore": self.expectedBefore,
            "simulationStatus": self.simulationStatus,
            "note": self.note,
        }


@dataclass
class SkippedCall:
    commandId: str
    operationId: str
    writerMethod: str
    reason: str

    def to_dict(self) -> dict:
        return {
            "commandId": self.commandId,
            "operationId": self.operationId,
            "writerMethod": self.writerMethod,
            "reason": self.reason,
        }


@dataclass
class ExecutorFinding:
    code: str
    detail: str
    operationId: str | None = None
    commandId: str | None = None

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "detail": self.detail,
            "operationId": self.operationId,
            "commandId": self.commandId,
        }


@dataclass
class WriterExecutorNoOpResult:
    executorId: str = ""
    planId: str = ""
    verdict: str = "BLOCKED_NOT_READY_FOR_WRITER"
    readyForExecution: bool = False
    simulatedCalls: list[SimulatedCall] = field(default_factory=list)
    skippedCalls: list[SkippedCall] = field(default_factory=list)
    safetyFindings: list[ExecutorFinding] = field(default_factory=list)
    readbackRequired: bool = False
    writerCalled: bool = False
    outputCreated: bool = False
    originalUnmodified: bool = True

    def to_dict(self) -> dict:
        return {
            "executorId": self.executorId,
            "planId": self.planId,
            "verdict": self.verdict,
            "readyForExecution": self.readyForExecution,
            "simulatedCalls": [c.to_dict() for c in self.simulatedCalls],
            "skippedCalls": [s.to_dict() for s in self.skippedCalls],
            "safetyFindings": [f.to_dict() for f in self.safetyFindings],
            "readbackRequired": self.readbackRequired,
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


def _call_to_dict(c) -> dict:
    if hasattr(c, "to_dict"):
        return c.to_dict()
    if isinstance(c, dict):
        return c
    return {}


# ── 메인 함수 ────────────────────────────────────────────────────────────────


def _validate_one_call(c: dict, valid_methods: set, result, fatal_codes: set) -> None:
    cmd_id = c.get("commandId", "")
    op_id = c.get("operationId", "")
    method = c.get("writerMethod", "")
    op_type = c.get("operationType", "")

    # 3-1) writerMethod whitelist 재검증
    if method not in valid_methods:
        result.skippedCalls.append(
            SkippedCall(
                commandId=cmd_id,
                operationId=op_id,
                writerMethod=method,
                reason="writer_method_not_whitelisted",
            )
        )
        result.safetyFindings.append(
            ExecutorFinding(
                "WRITER_METHOD_NOT_WHITELISTED",
                f"writerMethod={method!r} not in adapter allowlist",
                op_id,
                cmd_id,
            )
        )
        fatal_codes.add("BLOCKED_UNSAFE_WRITER_METHOD")
        return

    # 3-2) expectedBefore 재검증 (overwrite op)
    if op_type in _OVERWRITE_OPS and "expectedBefore" not in c:
        result.skippedCalls.append(
            SkippedCall(
                commandId=cmd_id,
                operationId=op_id,
                writerMethod=method,
                reason="expected_before_missing",
            )
        )
        result.safetyFindings.append(
            ExecutorFinding(
                "EXPECTED_BEFORE_MISSING",
                f"expectedBefore key required for operationType={op_type!r}",
                op_id,
                cmd_id,
            )
        )
        fatal_codes.add("BLOCKED_EXPECTED_BEFORE_MISSING")
        return

    # 3-3) sourceDocumentHash 재검증
    src_hash = c.get("sourceDocumentHash", "")
    if not src_hash:
        result.skippedCalls.append(
            SkippedCall(
                commandId=cmd_id,
                operationId=op_id,
                writerMethod=method,
                reason="source_document_hash_missing",
            )
        )
        result.safetyFindings.append(
            ExecutorFinding(
                "SOURCE_HASH_MISSING",
                "sourceDocumentHash empty; refusing to simulate writer call",
                op_id,
                cmd_id,
            )
        )
        fatal_codes.add("BLOCKED_SOURCE_HASH_MISSING")
        return

    # 3-4) 통과 → simulated call 기록
    note = ""
    if op_type in _READBACK_RECOMMENDED_TYPES:
        result.readbackRequired = True
        note = "readback_recommended"
    result.simulatedCalls.append(
        SimulatedCall(
            commandId=cmd_id,
            operationId=op_id,
            writerMethod=method,
            target=dict(c.get("target") or {}),
            value=c.get("value"),
            expectedBefore=c.get("expectedBefore"),
            simulationStatus="SIMULATED_OK",
            note=note,
        )
    )


def execute_writer_call_plan_noop(writer_call_plan) -> WriterExecutorNoOpResult:
    """WriterCallPlan을 입력받아 no-op으로 시뮬레이션한다.

    실제 writer는 호출되지 않으며 output 파일도 만들어지지 않는다.
    """
    wcp = _as_dict(writer_call_plan)
    plan_id = wcp.get("planId", "")
    result = WriterExecutorNoOpResult(
        executorId=str(uuid.uuid4()),
        planId=plan_id,
    )

    # 1) adapter 결과가 ready가 아니면 즉시 차단
    if not wcp.get("readyForWriter") or wcp.get("verdict") != "READY_FOR_WRITER":
        result.verdict = "BLOCKED_NOT_READY_FOR_WRITER"
        result.safetyFindings.append(
            ExecutorFinding(
                "ADAPTER_NOT_READY",
                f"writer adapter verdict={wcp.get('verdict')!r} "
                f"readyForWriter={wcp.get('readyForWriter')}",
            )
        )
        # adapter가 blocked로 표시한 op은 그대로 보고
        for op_id in wcp.get("blockedOps", []) or []:
            result.skippedCalls.append(
                SkippedCall(
                    commandId="",
                    operationId=op_id,
                    writerMethod="",
                    reason="adapter_blocked",
                )
            )
        return result

    calls = wcp.get("writerCalls", []) or []

    # 2) calls 0
    if not calls:
        result.verdict = "BLOCKED_NO_CALLS"
        result.safetyFindings.append(
            ExecutorFinding(
                "NO_WRITER_CALLS",
                "writerCalls is empty",
            )
        )
        return result

    # 3) 각 call 재검증
    valid_methods = set(adapter.OPERATION_TO_WRITER_METHOD.values())
    fatal_codes: set[str] = set()

    for raw in calls:
        _validate_one_call(_call_to_dict(raw), valid_methods, result, fatal_codes)

    # 4) verdict 산정 (fatal code 우선)
    priority = (
        "BLOCKED_UNSAFE_WRITER_METHOD",
        "BLOCKED_EXPECTED_BEFORE_MISSING",
        "BLOCKED_SOURCE_HASH_MISSING",
    )
    for code in priority:
        if code in fatal_codes:
            result.verdict = code
            result.readyForExecution = False
            break
    else:
        if not result.simulatedCalls:
            result.verdict = "BLOCKED_NO_CALLS"
            result.readyForExecution = False
        else:
            result.verdict = "PASS_NOOP_EXECUTOR_READY"
            result.readyForExecution = True

    # 5) 불변식
    result.writerCalled = False
    result.outputCreated = False
    result.originalUnmodified = True
    return result
