"""HWPX-AI-AUTO-FILL-PROPOSAL-CONTRACT-01 — review item builder.

AI proposal + target resolution + confidence 분류를 합쳐
운영동(fill_review)이 이해할 수 있는 review item 형태로 변환한다.

본 모듈은 fill_review production을 import하지 않는다. 운영동 schema는
read-only로 mirror된다.
"""
from __future__ import annotations

from . import (
    ai_proposal_contract as apc,
    target_resolver as tr,
    confidence_policy as cp,
)
# 주의: format_normalizer는 도구로만 제공. 자동 호출 금지 — AI가 판단·호출.


def build_review_items_from_proposals(
    proposals: list,
    recognition_result: dict,
    *,
    conflict_labels: set[str] | None = None,
    request_id: str | None = None,
) -> dict:
    """AI proposal 리스트 → 운영동 형식 review item + 부가 메타.

    Args:
        proposals: AI 후보 리스트
        recognition_result: 운영동에서 받은 인식 결과 (read-only)
        conflict_labels: 충돌 라벨 집합 (B동/사람 검수 결과)
        request_id: 추적용

    Returns:
        {
          requestId, reviewItems, rejectedProposals,
          holdProposals, autoApproveEnabled, summary
        }
    """
    envelope_result = apc.validate_proposal_batch(proposals)
    accepted = envelope_result["accepted"]
    rejected = list(envelope_result["rejected"])

    review_items: list[dict] = []
    holds: list[dict] = []

    conflicts = conflict_labels or set()

    for proposal in accepted:
        resolution = tr.resolve_target(proposal, recognition_result)
        label = proposal.get("label") or ""
        norm = resolution["normalizedLabel"]
        has_conflict = norm in conflicts
        classification = cp.classify(
            confidence=float(proposal.get("confidence") or 0.0),
            target_status=resolution["status"],
            has_conflict=has_conflict,
        )
        decision = classification["decision"]

        if decision == "AUTO_REJECT":
            rejected.append({
                "proposalId": proposal.get("proposalId"),
                "errors": [classification["reason"]],
            })
            continue
        if decision == "HOLD":
            holds.append({
                "proposalId": proposal.get("proposalId"),
                "normalizedLabel": norm,
                "reason": classification["reason"],
                "candidates": resolution["candidates"],
            })
            continue

        value_redacted = apc.redact_proposal_value(proposal.get("value"))
        review_items.append({
            "reviewItemId": f"ai-{proposal.get('proposalId')}",
            "label": label,
            "normalizedLabel": norm,
            "semanticType": proposal.get("semanticType"),
            "target": resolution["target"],
            "proposedValueHash": value_redacted["valueHash"],
            "redactedPreview": value_redacted["redactedPreview"],
            "containsSensitive": value_redacted["containsSensitive"],
            "confidence": float(proposal.get("confidence") or 0.0),
            "tier": classification["tier"],
            "policyDecision": classification["decision"],
            "policyReason": classification["reason"],
            "decisionSource": "AI_ASSISTED",
            "evidence": proposal.get("evidence"),
            "modelId": proposal.get("modelId"),
        })

    summary = {
        "totalSubmitted": len(proposals or []),
        "acceptedReadyForReview": len(review_items),
        "holds": len(holds),
        "rejected": len(rejected),
        "autoApproveEnabled": cp.AUTO_APPROVE_ENABLED,
    }
    return {
        "requestId": request_id,
        "reviewItems": review_items,
        "holdProposals": holds,
        "rejectedProposals": rejected,
        "autoApproveEnabled": cp.AUTO_APPROVE_ENABLED,
        "summary": summary,
    }
