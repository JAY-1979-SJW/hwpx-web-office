"""HWPX Pipeline — plan_builder.

FormRecognitionResult + 입력 데이터 → edit plan 생성.
slot 기반 set_cells를 우선하고, fallback으로 set_cells_by_label을 사용.
규칙 기반 skeleton. LLM 연결은 HWPX-LLM-PLANNER-REVIEW-GATE-01에서 진행.
"""
from __future__ import annotations

from .pipeline_contract import PlanResult, RecognitionResult

_AUTO_THRESHOLD = 0.90
_REVIEW_SUGGESTED = 0.70

# 필드명 → set_cells_by_label contains 매핑 (fallback용)
_FIELD_LABEL_MAP: dict[str, list[str]] = {
    "projectName":       ["공사명", "사업명", "프로젝트명"],
    "siteName":          ["현장명", "현장", "사업위치"],
    "contractorName":    ["시공사", "도급사", "수급인", "업체명", "회사명", "상호"],
    "reportDate":        ["작성일", "보고일", "제출일", "신고일자"],
    "receiptNumber":     ["접수번호", "접수번", "문서번호"],
    "startDate":         ["착수일", "착공일", "시작일"],
    "endDate":           ["종료일", "완료일", "준공일"],
    "completionDate":    ["준공일", "완공일"],
    "inspector":         ["담당자", "검사자", "검토자", "감리원", "책임자"],
    "responsiblePerson": ["담당자", "책임자", "성명"],
    "remarks":           ["비고", "참고", "특이사항"],
    "materialName":      ["품명", "자재명"],
    "quantity":          ["수량"],
    "spec":              ["규격", "사양"],
}

_LONG_TEXT_FIELDS = {"projectName", "siteName", "contractorName", "remarks", "materialName"}
_HIGHLIGHT_COLOR = "D9EAF7"
_HIGHLIGHT_FIELDS = {"projectName", "siteName", "contractorName", "reportDate"}


def build_edit_plan_from_form(
    form_recognition,
    field_values: dict[str, str],
    *,
    allow_fallback_when_no_slots: bool = False,
) -> PlanResult:
    """FormRecognitionResult 기반으로 edit plan을 생성한다.

    우선순위:
    1. confidence >= 0.90인 EnhancedSlot → set_cells (좌표 기반)
    2. confidence >= 0.70인 EnhancedSlot → set_cells_by_label
    3. fallback: _FIELD_LABEL_MAP → set_cells_by_label
    4. 불명확하면 REVIEW_REQUIRED
    """
    set_cells: list[dict] = []
    set_cells_by_label: list[dict] = []
    planned: list[str] = []
    skipped: list[str] = []
    review_reasons: dict[str, str] = {}

    # 안전 슬롯이 없고 reviewRequired=True면 fallback 사용 금지
    slots_all = getattr(form_recognition, "enhancedSlots", []) or []
    form_review_required = getattr(form_recognition, "reviewRequired", False)
    no_safe_slots = not any(getattr(s, "confidence", 0) >= _REVIEW_SUGGESTED for s in slots_all)
    if form_review_required and no_safe_slots and not allow_fallback_when_no_slots:
        for field_name in field_values:
            skipped.append(field_name)
            review_reasons[field_name] = "no_safe_slots_form_review_required"
        return PlanResult(editPlan={}, plannedFields=[], skippedFields=skipped,
                          reviewRequiredReasons=review_reasons)

    # 슬롯을 fieldGuess 별로 best 선택
    slots = getattr(form_recognition, "enhancedSlots", []) or []
    best_slots: dict[str, object] = {}
    for slot in slots:
        fg = getattr(slot, "fieldGuess", "unknown")
        if fg == "unknown":
            continue
        existing = best_slots.get(fg)
        if existing is None or getattr(slot, "confidence", 0) > getattr(existing, "confidence", 0):
            best_slots[fg] = slot

    # 동일 fieldGuess 후보가 여러 개면 REVIEW_REQUIRED 기록
    field_counts: dict[str, int] = {}
    for slot in slots:
        fg = getattr(slot, "fieldGuess", "unknown")
        if fg != "unknown":
            field_counts[fg] = field_counts.get(fg, 0) + 1

    for field_name, value in field_values.items():
        if not value:
            skipped.append(field_name)
            review_reasons[field_name] = "empty_value"
            continue

        # 중복 후보 확인
        if field_counts.get(field_name, 0) > 1:
            review_reasons[field_name] = "duplicate_candidates"

        slot = best_slots.get(field_name)

        if slot:
            conf = getattr(slot, "confidence", 0.0)
            if conf < _REVIEW_SUGGESTED:
                skipped.append(field_name)
                review_reasons[field_name] = f"low_confidence={conf:.2f}"
                continue

            table_id = getattr(slot, "tableId", "")
            row = getattr(slot, "row", 0)
            col = getattr(slot, "col", 0)
            label_text = getattr(slot, "labelText", "")

            if conf >= _AUTO_THRESHOLD and field_counts.get(field_name, 1) == 1:
                # visual 좌표 기반 set_visual_cells (가장 정확)
                v_row = getattr(slot, "visualRow", row)
                v_col = getattr(slot, "visualCol", col)
                item: dict = {
                    "table": int(table_id.split("_t")[-1]) if "_t" in str(table_id) else 0,
                    "visual_row": v_row,
                    "visual_col": v_col,
                    "value": value,
                    "vertical_align": "CENTER",
                }
                if field_name in _LONG_TEXT_FIELDS:
                    item["shrink_to_fit"] = True
                if field_name in _HIGHLIGHT_FIELDS:
                    item["solid_fill"] = {"color": _HIGHLIGHT_COLOR}
                set_cells.append(item)
            else:
                # label 기반 set_cells_by_label
                label = label_text or (_FIELD_LABEL_MAP.get(field_name, [""])[0])
                if not label:
                    skipped.append(field_name)
                    review_reasons[field_name] = "no_label_found"
                    continue
                item = {
                    "contains": label,
                    "value": value,
                    "vertical_align": "CENTER",
                }
                if field_name in _LONG_TEXT_FIELDS:
                    item["shrink_to_fit"] = True
                if field_name in _HIGHLIGHT_FIELDS:
                    item["solid_fill"] = {"color": _HIGHLIGHT_COLOR}
                set_cells_by_label.append(item)
                if conf < _AUTO_THRESHOLD:
                    review_reasons[field_name] = f"review_suggested_conf={conf:.2f}"

            planned.append(field_name)

        else:
            # fallback: _FIELD_LABEL_MAP
            labels = _FIELD_LABEL_MAP.get(field_name, [])
            if not labels:
                skipped.append(field_name)
                review_reasons[field_name] = "no_slot_no_label"
                continue
            # fallback confidence=0.70 수준 → label 기반만 생성
            item = {
                "contains": labels[0],
                "value": value,
                "vertical_align": "CENTER",
            }
            if field_name in _LONG_TEXT_FIELDS:
                item["shrink_to_fit"] = True
            if field_name in _HIGHLIGHT_FIELDS:
                item["solid_fill"] = {"color": _HIGHLIGHT_COLOR}
            set_cells_by_label.append(item)
            review_reasons[field_name] = "fallback_label_map"
            planned.append(field_name)

    edit_plan: dict = {}
    if set_cells:
        edit_plan["set_visual_cells"] = set_cells
    if set_cells_by_label:
        edit_plan["set_cells_by_label"] = set_cells_by_label

    return PlanResult(
        editPlan=edit_plan,
        plannedFields=planned,
        skippedFields=skipped,
        reviewRequiredReasons=review_reasons,
    )


def build_edit_plan(
    recognition: RecognitionResult,
    field_values: dict[str, str],
) -> PlanResult:
    """구버전 호환 API. RecognitionResult 기반 plan 생성."""
    set_cells_by_label: list[dict] = []
    planned: list[str] = []
    skipped: list[str] = []
    review_reasons: dict[str, str] = {}

    for field_name, value in field_values.items():
        if not value:
            skipped.append(field_name)
            review_reasons[field_name] = "empty_value"
            continue

        slot = recognition.slotMap.get(field_name)
        conf = slot.confidence if (slot and hasattr(slot, "confidence")) else recognition.confidence

        if conf < _REVIEW_SUGGESTED:
            skipped.append(field_name)
            review_reasons[field_name] = f"low_confidence={conf:.2f}"
            continue

        slot_label = getattr(slot, "labelText", None) if slot else None
        label = slot_label or (_FIELD_LABEL_MAP.get(field_name, [""])[0])
        if not label:
            skipped.append(field_name)
            review_reasons[field_name] = "no_label_found"
            continue

        item: dict = {"contains": label, "value": value, "vertical_align": "CENTER"}
        if field_name in _LONG_TEXT_FIELDS:
            item["shrink_to_fit"] = True
        if field_name in _HIGHLIGHT_FIELDS:
            item["solid_fill"] = {"color": _HIGHLIGHT_COLOR}
        if conf < _AUTO_THRESHOLD:
            review_reasons[field_name] = f"review_suggested_conf={conf:.2f}"

        set_cells_by_label.append(item)
        planned.append(field_name)

    edit_plan: dict = {}
    if set_cells_by_label:
        edit_plan["set_cells_by_label"] = set_cells_by_label

    return PlanResult(
        editPlan=edit_plan,
        plannedFields=planned,
        skippedFields=skipped,
        reviewRequiredReasons=review_reasons,
    )
