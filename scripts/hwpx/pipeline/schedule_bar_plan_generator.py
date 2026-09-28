"""HWPX-SCHEDULE-BAR-PLAN-GENERATOR-01

BarPlanCandidate → fill_schedule_bars edit plan 변환 공정.

이번 공정은 plan 생성까지만 수행한다.
apply_edit_plan / fill_schedule_bars 실행 금지.
write_package 호출 금지.
원본 fixture 수정 없음.
reports 산출물은 커밋 제외.
"""
from __future__ import annotations

from ..parser.parser_contract import (
    ScheduleBarEditPlan,
    ScheduleBarEditPlanItem,
    ScheduleBarPlanCandidate,
    ScheduleBarPlanDecision,
)
from .schedule_bar_color_policy import resolve_bar_color

# ── decision 정책 ──────────────────────────────────────────────────────────────
_AUTO_ALLOWED_CONFLICTS = frozenset({
    "no_conflict",
    "replaces_existing_empty_template",
})
_REVIEW_CONFLICTS = frozenset({
    "overlaps_existing_bar",
    "extends_existing_bar",
    "unknown",
})
_FAIL_CONFLICTS = frozenset({
    "outside_axis_range",
})


def decide_bar_plan_action(candidate: ScheduleBarPlanCandidate) -> ScheduleBarPlanDecision:
    """BarPlanCandidate의 conflict와 reviewRequired 기반으로 action을 결정한다."""
    conflict = candidate.conflict or "unknown"
    col_ok = candidate.colStart >= 0 and candidate.colEnd >= candidate.colStart
    row_ok = candidate.row >= 0

    if not col_ok or not row_ok:
        return ScheduleBarPlanDecision(
            action="FAIL",
            reason=f"invalid_coords: row={candidate.row} colStart={candidate.colStart} colEnd={candidate.colEnd}",
            confidence=0.0,
        )

    if conflict in _FAIL_CONFLICTS:
        return ScheduleBarPlanDecision(
            action="FAIL",
            reason=f"conflict={conflict}",
            confidence=0.0,
        )

    if candidate.reviewRequired:
        return ScheduleBarPlanDecision(
            action="REVIEW_REQUIRED",
            reason=candidate.reviewRequiredReason or f"conflict={conflict}",
            confidence=candidate.confidence,
        )

    if conflict in _AUTO_ALLOWED_CONFLICTS:
        return ScheduleBarPlanDecision(
            action="AUTO_PLAN_ALLOWED",
            reason=f"conflict={conflict}",
            confidence=candidate.confidence,
        )

    if conflict in _REVIEW_CONFLICTS:
        return ScheduleBarPlanDecision(
            action="REVIEW_REQUIRED",
            reason=f"conflict={conflict}",
            confidence=candidate.confidence,
        )

    return ScheduleBarPlanDecision(
        action="REVIEW_REQUIRED",
        reason=f"unknown_conflict={conflict}",
        confidence=candidate.confidence * 0.7,
    )


def _resolve_color(candidate: ScheduleBarPlanCandidate, action: str) -> str:
    """후보의 색상 결정. 후보에 색상이 있으면 우선 사용."""
    return resolve_bar_color(
        explicit_color=candidate.color or None,
        action=action,
    )


def _resolve_text_at(candidate: ScheduleBarPlanCandidate) -> str:
    """text_at 결정."""
    if not candidate.text:
        return "none"
    return candidate.textAt or "center"


def _resolve_overwrite(candidate: ScheduleBarPlanCandidate) -> bool:
    """overwrite 결정. 기본 False."""
    if candidate.conflict in _AUTO_ALLOWED_CONFLICTS:
        return False
    return False  # 항상 False — 실행 시 사용자 확인 후 변경


def _resolve_preserve_text(candidate: ScheduleBarPlanCandidate) -> bool:
    """preserve_text 결정. 기본 True."""
    return True


def convert_candidate_to_edit_plan_item(
    candidate: ScheduleBarPlanCandidate,
    table_index: int = 0,
) -> ScheduleBarEditPlanItem:
    """BarPlanCandidate를 ScheduleBarEditPlanItem으로 변환한다."""
    decision = decide_bar_plan_action(candidate)
    color = _resolve_color(candidate, decision.action)
    text_at = _resolve_text_at(candidate)
    overwrite = _resolve_overwrite(candidate)
    preserve_text = _resolve_preserve_text(candidate)

    review_required = decision.action != "AUTO_PLAN_ALLOWED"
    review_reason = decision.reason if review_required else None

    return ScheduleBarEditPlanItem(
        table=table_index,
        tableId=candidate.tableId,
        taskRow=candidate.row,
        startCol=candidate.colStart,
        endCol=candidate.colEnd,
        color=color,
        text=candidate.text or "",
        textAt=text_at,
        shrinkToFit=bool(candidate.text),
        preserveText=preserve_text,
        overwrite=overwrite,
        conflict=candidate.conflict or "unknown",
        confidence=decision.confidence,
        sourceCandidateId=f"{candidate.tableId}_r{candidate.row}",
        reviewRequired=review_required,
        reviewRequiredReason=review_reason,
        evidence=list(candidate.evidence or []),
    )


def build_fill_schedule_bars_plan(
    candidate: ScheduleBarPlanCandidate,
    table_index: int = 0,
) -> ScheduleBarEditPlan:
    """단일 후보로부터 ScheduleBarEditPlan을 생성한다."""
    item = convert_candidate_to_edit_plan_item(candidate, table_index)
    decision = decide_bar_plan_action(candidate)

    auto = 1 if decision.action == "AUTO_PLAN_ALLOWED" else 0
    review = 1 if decision.action == "REVIEW_REQUIRED" else 0
    fail = 1 if decision.action == "FAIL" else 0
    skip = 1 if decision.action == "SKIP" else 0

    return ScheduleBarEditPlan(
        tableId=candidate.tableId,
        items=[item],
        autoAllowedCount=auto,
        reviewRequiredCount=review,
        skipCount=skip,
        failCount=fail,
        warnings=list(candidate.warnings or []),
    )


def build_fill_schedule_bars_plan_from_candidates(
    candidates: list[ScheduleBarPlanCandidate],
    table_index: int = 0,
) -> ScheduleBarEditPlan:
    """후보 목록으로부터 통합 ScheduleBarEditPlan을 생성한다."""
    if not candidates:
        return ScheduleBarEditPlan(warnings=["no_candidates"])

    table_id = candidates[0].tableId
    items: list[ScheduleBarEditPlanItem] = []
    auto_count = review_count = fail_count = skip_count = 0
    all_warnings: list[str] = []

    for cand in candidates:
        item = convert_candidate_to_edit_plan_item(cand, table_index)
        items.append(item)
        d = decide_bar_plan_action(cand)
        if d.action == "AUTO_PLAN_ALLOWED":
            auto_count += 1
        elif d.action == "REVIEW_REQUIRED":
            review_count += 1
        elif d.action == "FAIL":
            fail_count += 1
        elif d.action == "SKIP":
            skip_count += 1
        all_warnings.extend(cand.warnings or [])

    return ScheduleBarEditPlan(
        tableId=table_id,
        items=items,
        autoAllowedCount=auto_count,
        reviewRequiredCount=review_count,
        skipCount=skip_count,
        failCount=fail_count,
        warnings=list(dict.fromkeys(all_warnings)),
    )


def validate_schedule_bar_plan(plan: ScheduleBarEditPlan) -> dict:
    """plan 유효성 검사. PASS / WARN / FAIL 반환."""
    issues: list[str] = []
    warnings: list[str] = []

    for item in plan.items:
        if item.startCol < 0 or item.endCol < 0:
            issues.append(f"row={item.taskRow}: invalid col range ({item.startCol},{item.endCol})")
        if item.startCol > item.endCol:
            issues.append(f"row={item.taskRow}: startCol({item.startCol}) > endCol({item.endCol})")
        if item.taskRow < 0:
            issues.append(f"invalid taskRow={item.taskRow}")
        if item.reviewRequired:
            warnings.append(f"row={item.taskRow}: reviewRequired — {item.reviewRequiredReason}")

    if issues:
        return {"status": "FAIL", "issues": issues, "warnings": warnings}
    if warnings:
        return {"status": "WARN", "issues": [], "warnings": warnings}
    return {"status": "PASS", "issues": [], "warnings": []}


def summarize_schedule_bar_plan(plan: ScheduleBarEditPlan) -> dict:
    """plan 요약 정보를 반환한다."""
    auto_items = [i for i in plan.items if not i.reviewRequired and i.startCol >= 0]
    review_items = [i for i in plan.items if i.reviewRequired]
    fail_items = [i for i in plan.items if i.startCol < 0]

    sample = auto_items[0].to_fill_plan_dict() if auto_items else None

    return {
        "tableId": plan.tableId,
        "totalItems": len(plan.items),
        "autoAllowed": len(auto_items),
        "reviewRequired": len(review_items),
        "failed": len(fail_items),
        "sampleEditPlan": sample,
        "warnings": plan.warnings,
    }
