"""HWPX Pipeline — plan_builder.

FormRecognitionResult + 입력 데이터 → edit plan 생성.
slot 기반 set_cells를 우선하고, fallback으로 set_cells_by_label을 사용.
규칙 기반 skeleton. LLM 연결은 HWPX-LLM-PLANNER-REVIEW-GATE-01에서 진행.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..hwpx_cell_text_edits import (  # 편집 엔진(L4)의 순수 글자 편집 — 계획과 편집기가 같은 함수를 쓴다
    AFTER,
    REPLACE,
    apply_edit,
    apply_edits,
)
from ..parser.slot_modes import DATE_PATTERN, EDIT_MODES, INLINE, mark_choice
from ..parser.table_parser import (
    _normalize as normalize_text,  # 칸 글자를 읽을 때 쓰는 것과 같은 정규화
)
from .pipeline_contract import PlanResult, RecognitionResult

_AUTO_THRESHOLD = 0.90
_REVIEW_SUGGESTED = 0.70

# 필드명 → set_cells_by_label contains 매핑 (fallback용)
_FIELD_LABEL_MAP: dict[str, list[str]] = {
    "projectName": ["공사명", "사업명", "프로젝트명"],
    "siteName": ["현장명", "현장", "사업위치"],
    "contractorName": ["시공사", "도급사", "수급인", "업체명", "회사명", "상호"],
    "reportDate": ["작성일", "보고일", "제출일", "신고일자"],
    "receiptNumber": ["접수번호", "접수번", "문서번호"],
    "startDate": ["착수일", "착공일", "시작일"],
    "endDate": ["종료일", "완료일", "준공일"],
    "completionDate": ["준공일", "완공일"],
    "inspector": ["담당자", "검사자", "검토자", "감리원", "책임자"],
    "responsiblePerson": ["담당자", "책임자", "성명"],
    "remarks": ["비고", "참고", "특이사항"],
    "materialName": ["품명", "자재명"],
    "quantity": ["수량"],
    "spec": ["규격", "사양"],
}

_LONG_TEXT_FIELDS = {"projectName", "siteName", "contractorName", "remarks", "materialName"}
_HIGHLIGHT_COLOR = "D9EAF7"
_HIGHLIGHT_FIELDS = {"projectName", "siteName", "contractorName", "reportDate"}


def _apply_field_flags(item: dict, field_name: str) -> None:
    if field_name in _LONG_TEXT_FIELDS:
        item["shrink_to_fit"] = True
    if field_name in _HIGHLIGHT_FIELDS:
        item["solid_fill"] = {"color": _HIGHLIGHT_COLOR}


def _table_index_of(slot: object, table_id: str) -> int:
    """편집기 table_index. tableId 는 't_s0_001' 꼴이라 예전의 '_t' 분리는 늘 0 을 돌려줬다."""
    ordinal = getattr(slot, "tableOrdinal", -1)
    if isinstance(ordinal, int) and ordinal >= 0:
        return ordinal
    m = re.fullmatch(r"t_s\d+_(\d+)", str(table_id))
    return int(m.group(1)) if m else 0


_DATE_RE = re.compile(r"(\d{4})\D+(\d{1,2})\D+(\d{1,2})")


def format_blank_date(value: str) -> str:
    """'2026-10-23' 같은 날짜를 '    년  월  일' 자리에 들어갈 '2026년 10월 23일' 로. 날짜 꼴이 아니면 그대로."""
    m = _DATE_RE.search(value or "")
    if not m:
        return value
    return f"{m.group(1)}년 {int(m.group(2))}월 {int(m.group(3))}일"


def edit_base(slot: object) -> str:
    """편집 전 칸 글자 — 원문(공백 그대로)이 있으면 원문, 없으면 정규화된 칸 글자."""
    return getattr(slot, "cellRawText", "") or getattr(slot, "cellText", "") or ""


def text_edit_for(slot: object, value: str) -> dict | None:
    """글자 일부만 고치는 칸(inline·replace)의 편집 1건. 그런 칸이 아니면 None."""
    mode = getattr(slot, "writeMode", "set")
    anchor = getattr(slot, "anchorText", "") or ""
    if mode not in EDIT_MODES or not anchor:
        return None
    if mode == INLINE:
        return {"kind": AFTER, "anchor": anchor, "value": value}
    if anchor == DATE_PATTERN:
        value = format_blank_date(value)
    template = getattr(slot, "valueTemplate", "{v}") or "{v}"
    return {"kind": REPLACE, "pattern": anchor, "value": template.replace("{v}", value)}


def merge_edit_item(items: list[dict], bases: dict, item: dict, base: str) -> bool:
    """글자 일부 편집 항목을 계획에 넣는다. 같은 칸의 앞선 편집이 있으면 편집을 합치고 예상 글자를 다시 계산한다.

    같은 칸을 칸 전체 덮어쓰기 항목이 이미 쓰고 있거나, 합친 편집이 맞지 않으면 False(넣지 않음).
    """
    key = (item["table"], item["visual_row"], item["visual_col"])
    prior = next((i for i in items if (i["table"], i["visual_row"], i["visual_col"]) == key), None)
    if prior is None:
        bases[key] = base
        items.append(item)
        return True
    if key not in bases:
        return False
    edits = list(prior["text_edits"]) + list(item["text_edits"])
    final = apply_edits(base, edits)
    if final is None:
        return False
    prior["text_edits"] = edits
    prior["value"] = normalize_text(final)
    return True


def _final_cell_text(slot: object, value: str) -> str | None:
    """writeMode 별로 칸에 들어갈 최종 글자. 만들 수 없으면 None(선택 항목을 찾지 못함 등)."""
    mode = getattr(slot, "writeMode", "set")
    base = getattr(slot, "cellText", "") or ""
    if mode == "append":
        return f"{base} {value}".strip()
    if mode == "unit":
        return f"{value}{base}"
    if mode == "choice":
        return mark_choice(base, value)
    return value


def _build_slot_item(
    slot: object,
    field_name: str,
    value: str,
    conf: float,
    field_counts: dict[str, int],
) -> tuple[dict | None, str | None]:
    """(item, dest) 반환. dest는 'visual'/'label'/None(생성 실패)."""
    table_id = getattr(slot, "tableId", "")
    row = getattr(slot, "row", 0)
    col = getattr(slot, "col", 0)
    label_text = getattr(slot, "labelText", "")

    mode = getattr(slot, "writeMode", "set")
    if mode in EDIT_MODES:
        edit = text_edit_for(slot, value)
        final = apply_edit(edit_base(slot), edit) if edit else None
        if final is None:
            return None, None
        edit_item = {
            "table": _table_index_of(slot, table_id),
            "visual_row": getattr(slot, "visualRow", row),
            "visual_col": getattr(slot, "visualCol", col),
            "value": normalize_text(final),
            "text_edits": [edit],
        }
        return edit_item, "visual"
    if mode != "set":
        # 칸 안에 이어 쓰거나 상자를 체크하는 칸은 옆 칸 라벨 경로(set_cells_by_label)로는 쓸 수 없다 — 항상 칸 주소로 쓴다
        final = _final_cell_text(slot, value)
        if final is None:
            return None, None
        value = final
    if mode != "set" or (conf >= _AUTO_THRESHOLD and field_counts.get(field_name, 1) == 1):
        v_row = getattr(slot, "visualRow", row)
        v_col = getattr(slot, "visualCol", col)
        item: dict = {
            "table": _table_index_of(slot, table_id),
            "visual_row": v_row,
            "visual_col": v_col,
            "value": value,
            "vertical_align": "CENTER",
        }
        _apply_field_flags(item, field_name)
        return item, "visual"

    label = label_text or (_FIELD_LABEL_MAP.get(field_name, [""])[0])
    if not label:
        return None, None
    item = {"contains": label, "value": value, "vertical_align": "CENTER"}
    _apply_field_flags(item, field_name)
    return item, "label"


@dataclass
class _PlanAccumulator:
    set_cells: list[dict] = field(default_factory=list)
    set_cells_by_label: list[dict] = field(default_factory=list)
    planned: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    review_reasons: dict[str, str] = field(default_factory=dict)
    edit_bases: dict = field(default_factory=dict)


def _process_slotted_field(
    field_name: str,
    value: str,
    slot: object,
    field_counts: dict[str, int],
    acc: _PlanAccumulator,
) -> None:
    conf = getattr(slot, "confidence", 0.0)
    if conf < _REVIEW_SUGGESTED:
        acc.skipped.append(field_name)
        acc.review_reasons[field_name] = f"low_confidence={conf:.2f}"
        return

    item, dest = _build_slot_item(slot, field_name, value, conf, field_counts)
    if dest is None:
        acc.skipped.append(field_name)
        acc.review_reasons[field_name] = "no_label_found"
        return
    if item is None:
        return
    if dest == "visual" and item.get("text_edits"):
        if not merge_edit_item(acc.set_cells, acc.edit_bases, item, edit_base(slot)):
            acc.skipped.append(field_name)
            acc.review_reasons[field_name] = "cell_edit_conflict"
            return
    elif dest == "visual":
        acc.set_cells.append(item)
    else:
        acc.set_cells_by_label.append(item)
        if conf < _AUTO_THRESHOLD:
            acc.review_reasons[field_name] = f"review_suggested_conf={conf:.2f}"
    acc.planned.append(field_name)


def _process_fallback_field(field_name: str, value: str, acc: _PlanAccumulator) -> None:
    labels = _FIELD_LABEL_MAP.get(field_name, [])
    if not labels:
        acc.skipped.append(field_name)
        acc.review_reasons[field_name] = "no_slot_no_label"
        return
    item = {"contains": labels[0], "value": value, "vertical_align": "CENTER"}
    _apply_field_flags(item, field_name)
    acc.set_cells_by_label.append(item)
    acc.review_reasons[field_name] = "fallback_label_map"
    acc.planned.append(field_name)


def _best_slots_by_field_guess(slots: list[object]) -> dict[str, object]:
    best_slots: dict[str, object] = {}
    for slot in slots:
        fg = getattr(slot, "fieldGuess", "unknown")
        if fg == "unknown":
            continue
        existing = best_slots.get(fg)
        if existing is None or getattr(slot, "confidence", 0) > getattr(existing, "confidence", 0):
            best_slots[fg] = slot
    return best_slots


def _field_guess_counts(slots: list[object]) -> dict[str, int]:
    field_counts: dict[str, int] = {}
    for slot in slots:
        fg = getattr(slot, "fieldGuess", "unknown")
        if fg != "unknown":
            field_counts[fg] = field_counts.get(fg, 0) + 1
    return field_counts


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
    acc = _PlanAccumulator()

    # 요청받은 필드 중 하나도 안전 슬롯이 없으면 fallback 사용 금지.
    #
    # 2026-09-29: 원래는 form_recognition.reviewRequired(문서 전체 기준 —
    # 요청받은 필드와 무관한 슬롯도 포함해 계산됨)로 판단했다. 이 때문에
    # layout_classifier.py의 표 분류 정확도를 고친 뒤 실측
    # (fx_many_tables_page_marker.hwpx)에서 실제 버그가 드러남 — 문서
    # 어딘가(예: 설비 점검표)에 믿을 만한 슬롯이 생기자 reviewRequired가
    # False로 바뀌면서, 그 문서와 전혀 무관한 요청 필드(공사명 등)까지
    # _FIELD_LABEL_MAP 추측값으로 채워버렸다. "안전 슬롯 여부"는 지금
    # 요청받은 필드에 한정해서 판단해야 한다 — 요청받지 않은 필드의
    # 확신도는 이 요청이 "라벨 없는 서식"에 대한 것인지 판단하는 근거가
    # 될 수 없다.
    slots_all = getattr(form_recognition, "enhancedSlots", []) or []
    requested_fields = set(field_values)
    no_safe_slots = not any(
        getattr(s, "confidence", 0) >= _REVIEW_SUGGESTED
        and getattr(s, "fieldGuess", "unknown") in requested_fields
        for s in slots_all
    )
    if no_safe_slots and not allow_fallback_when_no_slots:
        for field_name in field_values:
            acc.skipped.append(field_name)
            acc.review_reasons[field_name] = "no_safe_slots_for_requested_fields"
        return PlanResult(
            editPlan={},
            plannedFields=[],
            skippedFields=acc.skipped,
            reviewRequiredReasons=acc.review_reasons,
        )

    slots = getattr(form_recognition, "enhancedSlots", []) or []
    best_slots = _best_slots_by_field_guess(slots)
    field_counts = _field_guess_counts(slots)

    for field_name, value in field_values.items():
        if not value:
            acc.skipped.append(field_name)
            acc.review_reasons[field_name] = "empty_value"
            continue

        # 중복 후보 확인
        if field_counts.get(field_name, 0) > 1:
            acc.review_reasons[field_name] = "duplicate_candidates"

        slot = best_slots.get(field_name)

        if slot:
            _process_slotted_field(field_name, value, slot, field_counts, acc)
        else:
            _process_fallback_field(field_name, value, acc)

    edit_plan: dict = {}
    if acc.set_cells:
        edit_plan["set_visual_cells"] = acc.set_cells
    if acc.set_cells_by_label:
        edit_plan["set_cells_by_label"] = acc.set_cells_by_label

    return PlanResult(
        editPlan=edit_plan,
        plannedFields=acc.planned,
        skippedFields=acc.skipped,
        reviewRequiredReasons=acc.review_reasons,
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
