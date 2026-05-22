"""HWPX-SCHEDULE-CONFLICT-REVIEW-GATE-01

REVIEW_REQUIRED 공정표 막대 후보를 검토 목록으로 변환하고,
승인된 후보만 fill_schedule_bars 실행 대상으로 통과시키는 게이트 공정.

이번 공정에서:
- apply_edit_plan 호출 금지 (게이트 판정만 수행)
- fill_schedule_bars 실행 금지 (to_fill_plan_dict 반환만 허용)
- write_package 호출 금지
- 원본 fixture 수정 없음
- reports 산출물은 커밋 제외
"""
from __future__ import annotations

import uuid

from ..parser.parser_contract import (
    ScheduleBarEditPlan,
    ScheduleBarEditPlanItem,
    ScheduleBarGateOutput,
    ScheduleBarReviewDecision,
    ScheduleBarReviewItem,
    ScheduleBarReviewList,
)

# ── verdict 정책 ────────────────────────────────────────────────────────────────
_VALID_VERDICTS = frozenset({"APPROVED", "REJECTED", "DEFERRED", "PENDING"})

# REVIEW_REQUIRED 후보를 AUTO_APPROVED로 처리할 수 있는 conflict 타입
# (보수적 기준: 빈 템플릿 교체는 REVIEW 없이 자동 통과 가능하나
#  이 게이트에서는 일단 사람 검토 원칙 유지)
_AUTO_APPROVE_CONFLICTS: frozenset[str] = frozenset()


def _make_item_id(table_id: str, row: int, col_start: int) -> str:
    return f"{table_id}_r{row}_c{col_start}"


def build_review_list(plan: ScheduleBarEditPlan) -> ScheduleBarReviewList:
    """ScheduleBarEditPlan에서 REVIEW_REQUIRED 항목을 분리해 ScheduleBarReviewList를 반환."""
    review_items: list[ScheduleBarReviewItem] = []
    auto_items: list[ScheduleBarEditPlanItem] = []
    fail_items: list[ScheduleBarEditPlanItem] = []

    for item in plan.items:
        if item.startCol < 0 or item.taskRow < 0:
            fail_items.append(item)
        elif item.reviewRequired:
            review_items.append(ScheduleBarReviewItem(
                itemId=_make_item_id(item.tableId, item.taskRow, item.startCol),
                tableId=item.tableId,
                taskRow=item.taskRow,
                taskName=item.sourceCandidateId or "",
                startCol=item.startCol,
                endCol=item.endCol,
                color=item.color,
                text=item.text,
                conflict=item.conflict,
                reviewRequiredReason=item.reviewRequiredReason or "",
                existingBarType=item.conflict,
                confidence=item.confidence,
                evidence=list(item.evidence or []),
            ))
        else:
            auto_items.append(item)

    return ScheduleBarReviewList(
        tableId=plan.tableId,
        items=review_items,
        autoAllowedItems=auto_items,
        failedItems=fail_items,
        warnings=list(plan.warnings or []),
    )


def build_review_list_from_plans(plans: list[ScheduleBarEditPlan]) -> list[ScheduleBarReviewList]:
    """복수 plan에서 각각 ScheduleBarReviewList를 생성한다."""
    return [build_review_list(p) for p in plans]


def apply_review_decisions(
    review_list: ScheduleBarReviewList,
    decisions: list[ScheduleBarReviewDecision],
) -> ScheduleBarGateOutput:
    """검토 결정(decisions)을 review_list에 적용해 ScheduleBarGateOutput을 반환.

    decisions에 없는 항목은 PENDING으로 처리한다.
    """
    decision_map = {d.itemId: d for d in decisions}

    approved: list[ScheduleBarEditPlanItem] = list(review_list.autoAllowedItems)
    rejected: list[ScheduleBarReviewItem] = []
    deferred: list[ScheduleBarReviewItem] = []
    pending: list[ScheduleBarReviewItem] = []
    warnings = list(review_list.warnings or [])

    for item in review_list.items:
        decision = decision_map.get(item.itemId)
        if decision is None:
            pending.append(item)
            warnings.append(f"no_decision_for_item:{item.itemId}")
            continue

        verdict = decision.verdict
        if verdict not in _VALID_VERDICTS:
            warnings.append(f"invalid_verdict:{item.itemId}:{verdict}")
            pending.append(item)
            continue

        if verdict == "APPROVED":
            approved.append(_review_item_to_plan_item(item))
        elif verdict == "REJECTED":
            rejected.append(item)
        elif verdict == "DEFERRED":
            deferred.append(item)
        else:
            pending.append(item)

    return ScheduleBarGateOutput(
        tableId=review_list.tableId,
        approvedItems=approved,
        rejectedItems=rejected,
        deferredItems=deferred,
        pendingItems=pending,
        warnings=warnings,
    )


def _review_item_to_plan_item(item: ScheduleBarReviewItem) -> ScheduleBarEditPlanItem:
    """ScheduleBarReviewItem을 ScheduleBarEditPlanItem으로 변환 (승인 후 실행 대상)."""
    return ScheduleBarEditPlanItem(
        table=0,
        tableId=item.tableId,
        taskRow=item.taskRow,
        startCol=item.startCol,
        endCol=item.endCol,
        color=item.color,
        text=item.text,
        textAt="center",
        shrinkToFit=bool(item.text),
        preserveText=False,
        overwrite=True,
        conflict=item.conflict,
        confidence=item.confidence,
        sourceCandidateId=item.itemId,
        reviewRequired=False,
        reviewRequiredReason=None,
        evidence=list(item.evidence or []),
    )


def gate_all_approved(review_list: ScheduleBarReviewList) -> ScheduleBarGateOutput:
    """모든 REVIEW_REQUIRED 후보를 APPROVED로 처리한다. (테스트/스모크용)"""
    decisions = [
        ScheduleBarReviewDecision(
            itemId=item.itemId,
            verdict="APPROVED",
            reason="bulk_approve_for_test",
        )
        for item in review_list.items
    ]
    return apply_review_decisions(review_list, decisions)


def gate_all_rejected(review_list: ScheduleBarReviewList) -> ScheduleBarGateOutput:
    """모든 REVIEW_REQUIRED 후보를 REJECTED로 처리한다. (테스트/스모크용)"""
    decisions = [
        ScheduleBarReviewDecision(
            itemId=item.itemId,
            verdict="REJECTED",
            reason="bulk_reject_for_test",
        )
        for item in review_list.items
    ]
    return apply_review_decisions(review_list, decisions)


def validate_gate_output(output: ScheduleBarGateOutput) -> dict:
    """gate output 유효성 검사."""
    issues: list[str] = []
    warnings: list[str] = list(output.warnings or [])

    for item in output.approvedItems:
        if item.startCol < 0 or item.endCol < 0:
            issues.append(f"approved_item_invalid_col: row={item.taskRow}")
        if item.startCol > item.endCol:
            issues.append(f"approved_item_col_reversed: row={item.taskRow}")

    if output.pendingItems:
        warnings.append(f"pending_items_remain: {len(output.pendingItems)}")

    if issues:
        return {"status": "FAIL", "issues": issues, "warnings": warnings}
    if warnings:
        return {"status": "WARN", "issues": [], "warnings": warnings}
    return {"status": "PASS", "issues": [], "warnings": []}


def summarize_gate_output(output: ScheduleBarGateOutput) -> dict:
    """gate output 요약."""
    return {
        "tableId": output.tableId,
        "approvedCount": len(output.approvedItems),
        "rejectedCount": len(output.rejectedItems),
        "deferredCount": len(output.deferredItems),
        "pendingCount": len(output.pendingItems),
        "executableCount": len([i for i in output.approvedItems if i.startCol >= 0]),
        "warnings": output.warnings,
    }
