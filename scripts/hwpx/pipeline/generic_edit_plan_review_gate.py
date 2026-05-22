"""HWPX-EDIT-PLAN-REVIEW-GATE-01

dry-run 결과의 REVIEW_REQUIRED 항목에 대해 사람 승인/반려/보류 결정을 적용한다.

이 모듈은 writer를 호출하지 않으며 output HWPX를 만들지 않는다. 원본 파일도
수정하지 않는다. dry-run result + decisions만 받아서 게이트 통과 분류를 한다.

승인 후 verdict:
- READY_AFTER_REVIEW       : 모든 review op이 APPROVE, blocked 없음, 실행 후보 확정
- HELD_FOR_REVIEW          : 1건 이상 HOLD
- REJECTED_BY_REVIEW       : 1건 이상 REJECT (terminal)
- PENDING_REVIEW           : 결정 누락 (review op 중 일부에 decision 없음)
- BLOCKED_UNSAFE           : dry-run에서 blocked인 항목 남아 있음 / blocked op 승인 시도
- BLOCKED_INVALID_DECISIONS: decision 자체에 결함 (필수 필드 누락, planId 불일치 등)
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

# 결정 값 ----------------------------------------------------------------------
DECISION_APPROVE = "APPROVE"
DECISION_REJECT = "REJECT"
DECISION_HOLD = "HOLD"
ALLOWED_DECISIONS: frozenset[str] = frozenset({
    DECISION_APPROVE, DECISION_REJECT, DECISION_HOLD,
})

REQUIRED_DECISION_FIELDS: tuple[str, ...] = (
    "decisionId", "planId", "operationId",
    "reviewer", "decision", "reason", "decidedAt",
)


# ── dataclass 정의 ───────────────────────────────────────────────────────────

@dataclass
class ReviewDecision:
    decisionId: str = ""
    planId: str = ""
    operationId: str = ""
    reviewer: str = ""
    decision: str = ""
    reason: str = ""
    decidedAt: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "ReviewDecision":
        return cls(
            decisionId=d.get("decisionId", ""),
            planId=d.get("planId", ""),
            operationId=d.get("operationId", ""),
            reviewer=d.get("reviewer", ""),
            decision=d.get("decision", ""),
            reason=d.get("reason", ""),
            decidedAt=d.get("decidedAt", ""),
        )

    def to_dict(self) -> dict:
        return {
            "decisionId": self.decisionId,
            "planId": self.planId,
            "operationId": self.operationId,
            "reviewer": self.reviewer,
            "decision": self.decision,
            "reason": self.reason,
            "decidedAt": self.decidedAt,
        }


@dataclass
class GateFinding:
    code: str
    detail: str
    operationId: str | None = None
    decisionId: str | None = None

    def to_dict(self) -> dict:
        return {"code": self.code, "detail": self.detail,
                "operationId": self.operationId, "decisionId": self.decisionId}


@dataclass
class AuditLogEntry:
    operationId: str
    bucketBefore: str
    bucketAfter: str
    decisionId: str | None
    reviewer: str | None
    decision: str | None
    reason: str | None
    decidedAt: str | None

    def to_dict(self) -> dict:
        return {
            "operationId": self.operationId,
            "bucketBefore": self.bucketBefore,
            "bucketAfter": self.bucketAfter,
            "decisionId": self.decisionId,
            "reviewer": self.reviewer,
            "decision": self.decision,
            "reason": self.reason,
            "decidedAt": self.decidedAt,
        }


@dataclass
class ReviewGateResult:
    gateId: str = ""
    planId: str = ""
    gateVerdict: str = "PENDING_REVIEW"
    autoAllowedOps: list[str] = field(default_factory=list)
    approvedOps: list[str] = field(default_factory=list)
    rejectedOps: list[str] = field(default_factory=list)
    heldOps: list[str] = field(default_factory=list)
    pendingOps: list[str] = field(default_factory=list)
    blockedOps: list[str] = field(default_factory=list)
    findings: list[GateFinding] = field(default_factory=list)
    auditLog: list[AuditLogEntry] = field(default_factory=list)
    originalDecisions: list[dict] = field(default_factory=list)
    writerCalled: bool = False
    outputCreated: bool = False
    originalUnmodified: bool = True

    def to_dict(self) -> dict:
        return {
            "gateId": self.gateId,
            "planId": self.planId,
            "gateVerdict": self.gateVerdict,
            "autoAllowedOps": self.autoAllowedOps,
            "approvedOps": self.approvedOps,
            "rejectedOps": self.rejectedOps,
            "heldOps": self.heldOps,
            "pendingOps": self.pendingOps,
            "blockedOps": self.blockedOps,
            "findings": [f.to_dict() for f in self.findings],
            "auditLog": [a.to_dict() for a in self.auditLog],
            "originalDecisions": self.originalDecisions,
            "writerCalled": self.writerCalled,
            "outputCreated": self.outputCreated,
            "originalUnmodified": self.originalUnmodified,
        }


# ── 검증 헬퍼 ─────────────────────────────────────────────────────────────────

def _validate_decision(d: dict) -> list[GateFinding]:
    findings: list[GateFinding] = []
    if not isinstance(d, dict):
        return [GateFinding("DECISION_NOT_OBJECT", "decision must be a dict")]
    dec_id = d.get("decisionId")
    op_id = d.get("operationId")
    for k in REQUIRED_DECISION_FIELDS:
        v = d.get(k)
        if v is None or (isinstance(v, str) and not v.strip()):
            findings.append(GateFinding(
                "DECISION_MISSING_FIELD", f"decision.{k}", op_id, dec_id,
            ))
    dec = d.get("decision", "")
    if dec and dec not in ALLOWED_DECISIONS:
        findings.append(GateFinding(
            "DECISION_VALUE_INVALID",
            f"decision={dec!r} not in {sorted(ALLOWED_DECISIONS)}",
            op_id, dec_id,
        ))
    return findings


# ── 메인 게이트 함수 ──────────────────────────────────────────────────────────

def apply_review_decisions(dry_run_result, decisions: list[dict]) -> ReviewGateResult:
    """dry-run result와 review decisions를 받아 게이트 통과 분류를 산출.

    dry_run_result: DryRunResult 또는 dict
    decisions: list[ReviewDecision dict]
    """
    # 입력 정규화
    if hasattr(dry_run_result, "to_dict"):
        dr = dry_run_result.to_dict()
    else:
        dr = dict(dry_run_result or {})

    plan_id = dr.get("planId", "")
    auto_ops = list(dr.get("autoAllowedOps", []) or [])
    review_ops = list(dr.get("reviewRequiredOps", []) or [])
    blocked_ops = list(dr.get("blockedOps", []) or [])
    dr_verdict = dr.get("verdict", "")

    result = ReviewGateResult(
        gateId=str(uuid.uuid4()),
        planId=plan_id,
        autoAllowedOps=sorted(auto_ops),
        blockedOps=sorted(blocked_ops),
        originalDecisions=[dict(d) for d in (decisions or []) if isinstance(d, dict)],
    )

    # dry-run이 BLOCKED_INVALID_PLAN이면 게이트는 그 상태를 보존
    if dr_verdict == "BLOCKED_INVALID_PLAN":
        result.gateVerdict = "BLOCKED_UNSAFE"
        result.findings.append(GateFinding(
            "DRY_RUN_INVALID_PLAN",
            "dry-run verdict was BLOCKED_INVALID_PLAN; review gate cannot rescue",
        ))
        return result

    # 각 decision 사전 검증
    valid_decisions: dict[str, dict] = {}   # operationId → decision dict
    seen_invalid = False
    seen_decision_ids: set[str] = set()
    for d in (decisions or []):
        d_findings = _validate_decision(d)
        if d_findings:
            seen_invalid = True
            result.findings.extend(d_findings)
            continue
        if d["planId"] != plan_id:
            seen_invalid = True
            result.findings.append(GateFinding(
                "DECISION_PLAN_ID_MISMATCH",
                f"decision.planId={d['planId']!r} vs plan={plan_id!r}",
                d.get("operationId"), d.get("decisionId"),
            ))
            continue
        if d["operationId"] in valid_decisions:
            seen_invalid = True
            result.findings.append(GateFinding(
                "DECISION_DUPLICATE_OP",
                f"duplicate decision for operationId={d['operationId']!r}",
                d["operationId"], d.get("decisionId"),
            ))
            continue
        if d["decisionId"] in seen_decision_ids:
            seen_invalid = True
            result.findings.append(GateFinding(
                "DECISION_DUPLICATE_ID",
                f"duplicate decisionId={d['decisionId']!r}",
                d["operationId"], d["decisionId"],
            ))
            continue
        seen_decision_ids.add(d["decisionId"])
        valid_decisions[d["operationId"]] = d

    # operationId가 dry-run에 존재하지 않거나 blocked인 경우 차단
    known_op_ids = set(auto_ops) | set(review_ops) | set(blocked_ops)
    blocked_op_set = set(blocked_ops)
    for op_id, d in list(valid_decisions.items()):
        if op_id not in known_op_ids:
            seen_invalid = True
            result.findings.append(GateFinding(
                "DECISION_UNKNOWN_OP",
                f"operationId={op_id!r} not present in dry-run buckets",
                op_id, d.get("decisionId"),
            ))
            valid_decisions.pop(op_id)
            continue
        if op_id in blocked_op_set:
            # blocked op는 어떤 decision으로도 승인되지 않는다
            seen_invalid = True
            result.findings.append(GateFinding(
                "DECISION_ON_BLOCKED_OP",
                f"blocked operationId={op_id!r} cannot be reviewed/approved",
                op_id, d.get("decisionId"),
            ))
            valid_decisions.pop(op_id)
            continue
        if op_id in set(auto_ops):
            # 이미 auto이므로 review decision 적용 불필요 (informational)
            result.findings.append(GateFinding(
                "DECISION_ON_AUTO_OP_IGNORED",
                f"operationId={op_id!r} is already auto-allowed; "
                "decision ignored without effect",
                op_id, d.get("decisionId"),
            ))
            valid_decisions.pop(op_id)

    # decision invalid가 있으면 BLOCKED_INVALID_DECISIONS로 단정
    if seen_invalid:
        result.gateVerdict = "BLOCKED_INVALID_DECISIONS"
        return result

    # review op에 대해 분류 + audit log 작성
    approved: list[str] = []
    rejected: list[str] = []
    held: list[str] = []
    pending: list[str] = []
    for op_id in sorted(review_ops):
        d = valid_decisions.get(op_id)
        if d is None:
            pending.append(op_id)
            result.auditLog.append(AuditLogEntry(
                operationId=op_id, bucketBefore="review", bucketAfter="pending",
                decisionId=None, reviewer=None, decision=None,
                reason=None, decidedAt=None,
            ))
            continue
        verdict = d["decision"]
        if verdict == DECISION_APPROVE:
            approved.append(op_id); bucket_after = "approved"
        elif verdict == DECISION_REJECT:
            rejected.append(op_id); bucket_after = "rejected"
        else:
            held.append(op_id); bucket_after = "held"
        result.auditLog.append(AuditLogEntry(
            operationId=op_id, bucketBefore="review", bucketAfter=bucket_after,
            decisionId=d["decisionId"], reviewer=d["reviewer"],
            decision=verdict, reason=d["reason"], decidedAt=d["decidedAt"],
        ))

    result.approvedOps = sorted(approved)
    result.rejectedOps = sorted(rejected)
    result.heldOps = sorted(held)
    result.pendingOps = sorted(pending)

    # 최종 verdict 산정
    if blocked_ops:
        result.gateVerdict = "BLOCKED_UNSAFE"
    elif rejected:
        result.gateVerdict = "REJECTED_BY_REVIEW"
    elif held:
        result.gateVerdict = "HELD_FOR_REVIEW"
    elif pending:
        result.gateVerdict = "PENDING_REVIEW"
    else:
        # 모든 review가 APPROVE이거나 review op이 애초에 없는 경우
        result.gateVerdict = "READY_AFTER_REVIEW"

    # 불변식
    result.writerCalled = False
    result.outputCreated = False
    result.originalUnmodified = True
    return result
