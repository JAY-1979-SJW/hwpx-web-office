"""HWPX Pipeline — Universal Form Recognizer.

ParserV2Result를 받아 서식 유형·표 역할·입력칸을 판단한다.
규칙 기반 skeleton. LLM 연결은 HWPX-LLM-PLANNER-REVIEW-GATE-01에서 진행.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# ── 상수 ──────────────────────────────────────────────────────────────────────

_KNOWN_FIELD_HINTS: dict[str, tuple[str, ...]] = {
    "projectName":    ("공사명", "사업명", "프로젝트명"),
    "siteName":       ("현장명", "현장", "사업위치", "사업장소재지"),
    "contractorName": ("시공사", "도급사", "수급인", "업체명", "회사명", "상호"),
    "reportDate":     ("작성일", "보고일", "제출일", "신고일자"),
    "receiptNumber":  ("접수번호", "접수번", "문서번호"),
    "startDate":      ("착수일", "착공일", "시작일"),
    "endDate":        ("종료일", "완료일", "준공일"),
    "completionDate": ("준공일", "완공일"),
    "inspector":      ("담당자", "검사자", "검토자", "감리원", "책임자"),
    "materialName":   ("품명", "자재명", "품목"),
    "quantity":       ("수량",),
    "unit":           ("단위",),
    "spec":           ("규격", "사양"),
    "status":         ("상태", "진행상태"),
    "remarks":        ("비고", "참고", "특이사항"),
}

# 입력 금지 표 탐지 패턴
_UNSAFE_TABLE_KEYWORDS = ("직인", "결재", "서명", "인감")
_UNSAFE_TEXT_PATTERNS = re.compile(r"(처리절차|첨부서류|별지\s*제\d+호|쪽번호|210mm)")
_PAGE_MARKER_KEYWORDS = ("쪽", "페이지", "page")

# formType 분류 키워드
_FORM_TYPE_HINTS: dict[str, tuple[str, ...]] = {
    "application_form":         ("신청서", "신고서", "접수번호", "신청인"),
    "inspection_form":          ("검측요청서", "감리일지", "검사요청", "착공계"),
    "material_inspection_form": ("품명", "규격", "수량", "단가", "자재"),
    "schedule_form":            ("공정표", "일정표", "공정계획"),
    "contract_form":            ("도급계약", "계약금액", "수급인", "도급인"),
    "agreement_form":           ("협약서", "합의서", "각서"),
    "legal_form":               ("별지", "서식", "처리기간", "처리절차"),
}


# ── 결과 dataclass ────────────────────────────────────────────────────────────

@dataclass
class EnhancedSlot:
    slotId: str = ""
    tableId: str = ""
    tableRole: str = "unknown"
    fieldGuess: str = "unknown"
    source: str = "label_right"
    labelText: str = ""
    row: int = 0
    col: int = 0
    visualRow: int = 0
    visualCol: int = 0
    rowSpan: int = 1
    colSpan: int = 1
    confidence: float = 0.0
    autoEditAllowed: bool = False
    reviewRequired: bool = False
    reviewRequiredReason: str | None = None
    unsafeReason: str | None = None
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "slotId": self.slotId,
            "tableId": self.tableId,
            "tableRole": self.tableRole,
            "fieldGuess": self.fieldGuess,
            "source": self.source,
            "labelText": self.labelText,
            "targetCell": {
                "tableId": self.tableId,
                "row": self.row,
                "col": self.col,
                "visualRow": self.visualRow,
                "visualCol": self.visualCol,
                "rowSpan": self.rowSpan,
                "colSpan": self.colSpan,
            },
            "confidence": self.confidence,
            "autoEditAllowed": self.autoEditAllowed,
            "reviewRequired": self.reviewRequired,
            "reviewRequiredReason": self.reviewRequiredReason,
            "unsafeReason": self.unsafeReason,
            "evidence": self.evidence,
        }


@dataclass
class FormRecognitionResult:
    formType: str = "unknown_form"
    formTypeConfidence: float = 0.0
    tableRoles: dict[str, str] = field(default_factory=dict)   # tableId → role
    enhancedSlots: list[EnhancedSlot] = field(default_factory=list)
    unsafeTableIds: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    overallConfidence: float = 0.0
    reviewRequired: bool = False

    def to_dict(self) -> dict:
        return {
            "formType": self.formType,
            "formTypeConfidence": self.formTypeConfidence,
            "tableRoles": self.tableRoles,
            "enhancedSlots": [s.to_dict() for s in self.enhancedSlots],
            "unsafeTableIds": self.unsafeTableIds,
            "evidence": self.evidence,
            "overallConfidence": self.overallConfidence,
            "reviewRequired": self.reviewRequired,
        }


# ── 헬퍼 함수 ─────────────────────────────────────────────────────────────────

def _guess_field(text: str) -> str:
    for fname, hints in _KNOWN_FIELD_HINTS.items():
        for h in hints:
            if h in text:
                return fname
    return "unknown"


def _is_unsafe_table(table) -> bool:
    """직인/페이지/법령 안내표면 True."""
    layout = getattr(table, "layoutGuess", "")
    if layout in ("stamp_or_approval_table", "page_marker_table"):
        return True
    for cell in getattr(table, "cells", []):
        t = getattr(cell, "normalizedText", "") or ""
        if any(k in t for k in _UNSAFE_TABLE_KEYWORDS):
            return True
        if any(k in t.lower() for k in _PAGE_MARKER_KEYWORDS):
            return True
        if _UNSAFE_TEXT_PATTERNS.search(t):
            return True
    return False


def classify_table_roles(tables: list) -> dict[str, str]:
    """표 목록에서 각 표의 역할을 분류한다."""
    roles: dict[str, str] = {}
    for tbl in tables:
        tid = getattr(tbl, "tableId", "")
        layout = getattr(tbl, "layoutGuess", "")

        if layout == "stamp_or_approval_table":
            roles[tid] = "approval_stamp"
            continue
        if layout == "page_marker_table":
            roles[tid] = "page_marker"
            continue
        if layout == "nested_container_table":
            # 내부 셀을 보고 기본정보표 여부 판단
            cells = getattr(tbl, "cells", [])
            known_label_count = sum(
                1 for c in cells
                if _guess_field(getattr(c, "normalizedText", "") or "") != "unknown"
            )
            if known_label_count >= 2:
                roles[tid] = "basic_info"
            else:
                roles[tid] = "unknown"
            continue

        cells = getattr(tbl, "cells", [])
        if not cells:
            roles[tid] = "unknown"
            continue

        # 텍스트 비율
        total = len(cells)
        text_count = sum(1 for c in cells if getattr(c, "normalizedText", ""))
        text_ratio = text_count / total if total else 0

        # 알려진 라벨 수
        known_label_count = sum(
            1 for c in cells
            if _guess_field(getattr(c, "normalizedText", "") or "") != "unknown"
        )
        # 빈칸 비율
        empty_count = sum(1 for c in cells if not getattr(c, "normalizedText", ""))
        empty_ratio = empty_count / total if total else 0

        # 법령 안내 패턴
        all_text = " ".join(getattr(c, "normalizedText", "") or "" for c in cells)
        if _UNSAFE_TEXT_PATTERNS.search(all_text):
            roles[tid] = "legal_notice"
        elif any(k in all_text for k in _UNSAFE_TABLE_KEYWORDS):
            roles[tid] = "approval_stamp"
        elif any(k.lower() in all_text.lower() for k in _PAGE_MARKER_KEYWORDS) and total <= 4:
            roles[tid] = "page_marker"
        elif known_label_count >= 2 and empty_ratio >= 0.2:
            roles[tid] = "basic_info"
        elif layout in ("gantt_like_table", "calendar_like_table"):
            roles[tid] = "schedule_grid"
        elif layout == "horizontal_table" and empty_ratio >= 0.3:
            roles[tid] = "data_table"
        else:
            roles[tid] = "unknown"

    return roles


def classify_form_type(parser_result) -> tuple[str, float, list[str]]:
    """문서 전체 텍스트와 표 구조로 서식 유형을 분류한다."""
    full_text = getattr(getattr(parser_result, "document", None), "fullText", "") or ""
    candidates = getattr(parser_result, "inputSlotCandidates", []) or []

    scores: dict[str, int] = {k: 0 for k in _FORM_TYPE_HINTS}
    evidence: list[str] = []

    for ftype, hints in _FORM_TYPE_HINTS.items():
        for h in hints:
            if h in full_text:
                scores[ftype] += 2

    for slot in candidates:
        fg = getattr(slot, "fieldGuess", "unknown")
        if fg in ("projectName", "siteName", "contractorName", "reportDate"):
            scores["inspection_form"] += 1
            scores["application_form"] += 1
        if fg in ("materialName", "quantity", "unit", "spec"):
            scores["material_inspection_form"] += 2
        if fg == "receiptNumber":
            scores["application_form"] += 2

    best = max(scores, key=lambda k: scores[k])
    best_score = scores[best]

    if best_score == 0:
        return "unknown_form", 0.3, ["no_type_signal"]

    total_score = sum(scores.values()) or 1
    conf = min(0.95, best_score / total_score + 0.3)
    evidence.append(f"top_type={best} score={best_score}")
    return best, round(conf, 2), evidence


def _detect_label_value_pair_slots(table, table_role: str) -> list[EnhancedSlot]:
    """2열/4열 라벨-값 반복 구조에서 입력칸을 탐지한다."""
    if table_role in ("approval_stamp", "page_marker", "legal_notice"):
        return []
    cells = getattr(table, "cells", [])
    tid = getattr(table, "tableId", "")
    cols = getattr(table, "colCount", 0)
    if cols not in (2, 4):
        return []

    cell_map = {(c.row, c.col): c for c in cells}
    slots: list[EnhancedSlot] = []
    seen_pairs: set[tuple] = set()

    for cell in cells:
        if not getattr(cell, "normalizedText", ""):
            continue
        if getattr(cell, "isCoveredByMerge", False):
            continue
        col = getattr(cell, "col", 0)
        row = getattr(cell, "row", 0)
        # 짝수 열이 라벨, 홀수 열이 값인 패턴
        if col % 2 != 0:
            continue
        value_col = col + 1
        right = cell_map.get((row, value_col))
        if right and not getattr(right, "normalizedText", "") and not getattr(right, "isCoveredByMerge", False):
            key = (row, value_col)
            if key in seen_pairs:
                continue
            seen_pairs.add(key)
            fg = _guess_field(cell.normalizedText)
            conf = 0.80 if fg != "unknown" else 0.60
            if conf < 0.70:
                continue
            slot = EnhancedSlot(
                slotId=f"slot_{tid}_r{row}c{value_col}_pair",
                tableId=tid,
                tableRole=table_role,
                fieldGuess=fg,
                source="label_value_pair",
                labelText=cell.normalizedText,
                row=right.row, col=right.col,
                visualRow=getattr(right, "visualRow", right.row),
                visualCol=getattr(right, "visualCol", right.col),
                confidence=conf,
                autoEditAllowed=conf >= 0.90,
                evidence=[
                    f"label='{cell.normalizedText}'",
                    "label_value_pair_pattern",
                    f"col_pair={col}/{value_col}",
                    f"tableRole={table_role}",
                ],
            )
            slots.append(slot)
    return slots


def _detect_merged_input_slots(table, table_role: str) -> list[EnhancedSlot]:
    """라벨 옆/아래의 병합된 대형 입력칸을 탐지한다."""
    if table_role in ("approval_stamp", "page_marker", "legal_notice"):
        return []
    cells = getattr(table, "cells", [])
    tid = getattr(table, "tableId", "")
    cell_map = {(c.row, c.col): c for c in cells}
    slots: list[EnhancedSlot] = []

    for cell in cells:
        text = getattr(cell, "normalizedText", "") or ""
        if not text or len(text) > 20:
            continue
        fg = _guess_field(text)
        if fg == "unknown":
            continue
        row, col = cell.row, cell.col
        # 오른쪽 병합 셀
        right = cell_map.get((row, col + getattr(cell, "colSpan", 1)))
        if right and getattr(right, "isMergedOrigin", False) and not getattr(right, "normalizedText", ""):
            span = getattr(right, "colSpan", 1) * getattr(right, "rowSpan", 1)
            if span >= 2:
                slots.append(EnhancedSlot(
                    slotId=f"slot_{tid}_r{right.row}c{right.col}_merged",
                    tableId=tid, tableRole=table_role,
                    fieldGuess=fg, source="merged_input_cell",
                    labelText=text,
                    row=right.row, col=right.col,
                    visualRow=getattr(right, "visualRow", right.row),
                    visualCol=getattr(right, "visualCol", right.col),
                    confidence=0.75,
                    autoEditAllowed=False,
                    reviewRequiredReason="merged_cell_review",
                    evidence=[f"label='{text}'", "merged_right_cell_empty", f"span={span}"],
                ))
    return slots


def enhance_input_slots(parser_result, table_roles: dict[str, str]) -> list[EnhancedSlot]:
    """Parser V2의 inputSlotCandidates를 보강하고 새 규칙을 추가한다.

    지원 source: label_right, label_below, label_value_pair, merged_input_cell,
    blank_after_known_header, metadata_form_slot, data_table_append_slot, status_cell
    """
    from ..parser.input_slot_detector import detect_input_slots

    enhanced: list[EnhancedSlot] = []
    seen_targets: set[tuple] = set()
    unsafe_tables = {tid for tid, role in table_roles.items()
                     if role in ("approval_stamp", "page_marker", "legal_notice")}

    # ── 기존 슬롯 보강 ───────────────────────────────────────────────────────
    for slot in getattr(parser_result, "inputSlotCandidates", []) or []:
        tid = getattr(slot, "tableId", "")
        if tid in unsafe_tables:
            continue
        row, col = getattr(slot, "row", 0), getattr(slot, "col", 0)
        key = (tid, row, col)
        if key in seen_targets:
            continue
        seen_targets.add(key)

        role = table_roles.get(tid, "unknown")
        conf = getattr(slot, "confidence", 0.0)
        if role == "basic_info" and conf < 0.85:
            conf = min(conf + 0.10, 0.93)

        fg = getattr(slot, "fieldGuess", "unknown")
        evidence = list(getattr(slot, "evidence", []))
        evidence.append(f"tableRole={role}")

        review = getattr(slot, "reviewRequired", conf < 0.70)
        es = EnhancedSlot(
            slotId=getattr(slot, "slotId", f"slot_{tid}_r{row}c{col}"),
            tableId=tid, tableRole=role,
            fieldGuess=fg,
            source=getattr(slot, "source", "label_right"),
            labelText=getattr(slot, "labelText", ""),
            row=row, col=col,
            visualRow=getattr(slot, "visualRow", row),
            visualCol=getattr(slot, "visualCol", col),
            rowSpan=getattr(slot, "rowSpan", 1),
            colSpan=getattr(slot, "colSpan", 1),
            confidence=round(conf, 2),
            autoEditAllowed=conf >= 0.90 and not review,
            reviewRequired=review,
            reviewRequiredReason=getattr(slot, "reviewRequiredReason", None) or (
                "low_confidence" if conf < 0.70 else None
            ),
            unsafeReason=getattr(slot, "unsafeReason", None),
            evidence=evidence,
        )
        enhanced.append(es)

    # ── input_slot_detector 기반 추가 슬롯 ──────────────────────────────────
    tables = getattr(parser_result, "tables", []) or []
    new_slots = detect_input_slots(tables, table_roles=table_roles)
    for slot in new_slots:
        if slot.tableId in unsafe_tables:
            continue
        key = (slot.tableId, slot.row, slot.col)
        if key in seen_targets:
            continue
        seen_targets.add(key)
        role = table_roles.get(slot.tableId, slot.tableRole)
        conf = slot.confidence
        review = slot.reviewRequired or conf < 0.70
        enhanced.append(EnhancedSlot(
            slotId=slot.slotId,
            tableId=slot.tableId,
            tableRole=role,
            fieldGuess=slot.fieldGuess,
            source=slot.source,
            labelText=slot.labelText,
            row=slot.row, col=slot.col,
            visualRow=slot.visualRow, visualCol=slot.visualCol,
            rowSpan=slot.rowSpan, colSpan=slot.colSpan,
            confidence=conf,
            autoEditAllowed=conf >= 0.90 and not review,
            reviewRequired=review,
            reviewRequiredReason=slot.reviewRequiredReason,
            unsafeReason=slot.unsafeReason,
            evidence=slot.evidence,
        ))

    return enhanced


def recognize_form(parser_result) -> FormRecognitionResult:
    """ParserV2Result를 받아 FormRecognitionResult를 반환한다."""
    tables = getattr(parser_result, "tables", []) or []

    # 1. 표 역할 분류
    table_roles = classify_table_roles(tables)

    # 2. 안전 제외 표 목록
    unsafe_ids = [tid for tid, role in table_roles.items()
                  if role in ("approval_stamp", "page_marker", "legal_notice")]

    # 3. 서식 유형 분류
    ftype, ftype_conf, ftype_evidence = classify_form_type(parser_result)

    # 4. 입력칸 보강
    slots = enhance_input_slots(parser_result, table_roles)
    safe_slots = [s for s in slots if s.tableId not in unsafe_ids]

    # 5. 전체 confidence
    if safe_slots:
        overall_conf = round(
            sum(s.confidence for s in safe_slots) / len(safe_slots), 2
        )
    else:
        overall_conf = 0.0

    evidence = ftype_evidence + [
        f"tables={len(tables)}",
        f"safe_slots={len(safe_slots)}",
        f"unsafe_tables={len(unsafe_ids)}",
    ]

    return FormRecognitionResult(
        formType=ftype,
        formTypeConfidence=ftype_conf,
        tableRoles=table_roles,
        enhancedSlots=safe_slots,
        unsafeTableIds=unsafe_ids,
        evidence=evidence,
        overallConfidence=overall_conf,
        reviewRequired=overall_conf < 0.70 or not safe_slots,
    )
