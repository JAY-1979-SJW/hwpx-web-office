"""HWPX Parser V2 — input slot detector (HWPX-INPUT-SLOT-DETECTOR-01).

표 구조 분석 결과에서 입력칸 후보를 탐지한다.
source 분류:
  label_right / label_below / label_value_pair / merged_input_cell /
  blank_after_known_header / metadata_form_slot / data_table_append_slot /
  status_cell / schedule_range / manual_candidate

unsafe source (filter_unsafe_slots에서 제외):
  page_marker_table / stamp_or_approval_table / legal_notice_table /
  layout_noise / unknown_low_confidence
"""

from __future__ import annotations

import re

from .parser_contract import CellInfo, InputSlotCandidate, TableInfo

_AUTO_EDIT_THRESHOLD = 0.90
_REVIEW_REQUIRED_THRESHOLD = 0.70

_FIELD_HINTS: list[tuple[str, tuple[str, ...]]] = [
    ("projectName", ("공사명", "사업명", "프로젝트명")),
    ("siteName", ("현장명", "현장", "사업위치", "사업장소재지")),
    ("contractorName", ("시공사", "도급사", "수급인", "업체명", "회사명", "상호")),
    ("reportDate", ("작성일", "보고일", "제출일", "신고일자")),
    ("receiptNumber", ("접수번호", "접수번", "문서번호", "접수")),
    ("startDate", ("시작일", "착수일", "착공일")),
    ("endDate", ("종료일", "완료일", "준공일")),
    ("completionDate", ("준공일", "완공일")),
    ("responsiblePerson", ("담당자", "책임자", "성명")),
    ("inspector", ("검사자", "검토자", "감리원")),
    ("remarks", ("비고", "참고", "특이사항")),
    ("quantity", ("수량",)),
    ("amount", ("금액", "단가")),
    ("materialName", ("품명", "자재명", "품목")),
    ("spec", ("규격", "사양")),
    ("unit", ("단위",)),
    ("status", ("상태", "진행상태", "검측상태", "자재상태", "승인상태", "완료여부")),
    ("progressRate", ("진행률", "공정률")),
]

_STATUS_FIELD_HINTS: list[tuple[str, tuple[str, ...]]] = [
    ("progressRate", ("진행률", "공정률")),
    ("inspectionStatus", ("검측상태",)),
    ("materialStatus", ("자재상태",)),
    ("approvalStatus", ("승인상태",)),
    ("completedFlag", ("완료여부",)),
    ("status", ("상태", "진행상태")),
]

_DATA_TABLE_HEADERS = (
    "품명",
    "자재명",
    "수량",
    "단위",
    "규격",
    "단가",
    "금액",
    "번호",
    "비고",
    "spec",
    "qty",
)

_UNSAFE_LAYOUTS = frozenset({
    "stamp_or_approval_table",
    "page_marker_table",
    "layout_noise",
})

# 개별 탐지기에서 제외할 레이아웃.
# M2 (2026-05-19): page_marker_table을 제외 — 별지 양식이 (앞쪽)/(뒤쪽)
# 페이지 마커 때문에 page_marker_table로 잘못 분류되는 경우가 많아 form
# 입력 라벨이 차단되던 문제 해소. stamp/layout_noise는 계속 차단.
_IGNORE_LAYOUTS = frozenset({
    "stamp_or_approval_table",
    "layout_noise",
})

_LEGAL_PATTERN = re.compile(
    r"(처리절차|첨부서류|별지\s*제\d+호|쪽번호|210mm|297mm|작성요령|유의사항)"
)

# detect_input_slots에서 새 탐지기(blank_after_known_header, metadata_form 등)를
# 추가로 실행할 안전한 레이아웃 목록
_SAFE_EXTENDED_LAYOUTS = frozenset({
    "nested_container_table",
    "horizontal_table",
    "form_table",
    "basic_info",
    "data_table",
})


# ── 내부 유틸 ──────────────────────────────────────────────────────────────────


def _guess_field(text: str) -> str:
    for field_name, hints in _FIELD_HINTS:
        for h in hints:
            if h in text:
                return field_name
    return "unknown"


def _guess_status_field(text: str) -> str:
    for field_name, hints in _STATUS_FIELD_HINTS:
        for h in hints:
            if h in text:
                return field_name
    return "unknown"


def _is_layout_unsafe(table: TableInfo) -> bool:
    """layoutGuess 기반 빠른 unsafe 판정 (개별 탐지기에서 사용)."""
    return getattr(table, "layoutGuess", "") in _IGNORE_LAYOUTS


def _is_unsafe_table(table: TableInfo) -> tuple[bool, str]:
    """텍스트 패턴 포함 전체 unsafe 판정 (detect_input_slots 외부에서 사용)."""
    layout = getattr(table, "layoutGuess", "")
    if layout in _UNSAFE_LAYOUTS:
        return True, layout
    for cell in getattr(table, "cells", []):
        t = getattr(cell, "normalizedText", "") or ""
        if any(k in t for k in ("직인", "결재", "서명", "인감")):
            return True, "stamp_keyword"
        if any(k in t.lower() for k in ("쪽", "페이지", "page")) and len(t) <= 10:
            return True, "page_marker_keyword"
        if _LEGAL_PATTERN.search(t):
            return True, "legal_notice_pattern"
    return False, ""


def _make_slot(  # ruff: ignore[too-many-arguments] -- 8곳 호출부(동일 파일, 위치 인자), 슬롯 생성자 성격상 번들링 실익 낮아 보류
    slot_id: str,
    table: TableInfo,
    source: str,
    target: CellInfo,
    label_text: str,
    field_guess: str,
    confidence: float,
    evidence: list[str],
    *,
    table_role: str = "unknown",
    unsafe_reason: str | None = None,
) -> InputSlotCandidate:
    review = confidence < _REVIEW_REQUIRED_THRESHOLD
    review_reason = None
    if confidence < _REVIEW_REQUIRED_THRESHOLD:
        review_reason = "low_confidence"
    elif source == "merged_input_cell":
        review = True
        review_reason = "merged_cell_review"
    elif source == "data_table_append_slot":
        review = True
        review_reason = "append_slot_requires_review"
    return InputSlotCandidate(
        slotId=slot_id,
        tableId=getattr(table, "tableId", ""),
        tableRole=table_role,
        source=source,
        labelText=label_text,
        fieldGuess=field_guess,
        row=target.row,
        col=target.col,
        visualRow=getattr(target, "visualRow", target.row),
        visualCol=getattr(target, "visualCol", target.col),
        rowSpan=getattr(target, "rowSpan", 1),
        colSpan=getattr(target, "colSpan", 1),
        confidence=round(confidence, 2),
        autoEditAllowed=confidence >= _AUTO_EDIT_THRESHOLD and not review,
        reviewRequired=review,
        reviewRequiredReason=review_reason,
        unsafeReason=unsafe_reason,
        evidence=evidence,
    )


# ── 공개 탐지 함수 ────────────────────────────────────────────────────────────


def detect_label_right_slots(table: TableInfo) -> list[InputSlotCandidate]:
    """같은 행에서 라벨 오른쪽 빈 셀을 입력칸 후보로 탐지."""
    if _is_layout_unsafe(table):
        return []

    slots: list[InputSlotCandidate] = []
    cell_map = {(c.row, c.col): c for c in table.cells}
    tid = getattr(table, "tableId", "")

    for cell in table.cells:
        if not cell.normalizedText:
            continue
        if not getattr(cell, "isLikelyLabel", False) and len(cell.normalizedText) > 20:
            continue
        right = cell_map.get((cell.row, cell.col + getattr(cell, "colSpan", 1)))
        if not right or right.normalizedText or getattr(right, "isCoveredByMerge", False):
            continue
        field_guess = _guess_field(cell.normalizedText)
        conf = 0.88 if field_guess != "unknown" else 0.65
        evidence = [
            f"label='{cell.normalizedText}'",
            "right_cell_empty",
            f"fieldGuess={field_guess}",
        ]
        slots.append(
            _make_slot(
                f"slot_{tid}_r{cell.row}c{right.col}_lr",
                table,
                "label_right",
                right,
                cell.normalizedText,
                field_guess,
                conf,
                evidence,
            )
        )
    return slots


def detect_label_below_slots(table: TableInfo) -> list[InputSlotCandidate]:
    """라벨 아래 빈 셀을 입력칸 후보로 탐지."""
    if _is_layout_unsafe(table):
        return []

    slots: list[InputSlotCandidate] = []
    cell_map = {(c.row, c.col): c for c in table.cells}
    tid = getattr(table, "tableId", "")

    for cell in table.cells:
        if not cell.normalizedText or len(cell.normalizedText) > 20:
            continue
        below = cell_map.get((cell.row + getattr(cell, "rowSpan", 1), cell.col))
        if not below or below.normalizedText or getattr(below, "isCoveredByMerge", False):
            continue
        field_guess = _guess_field(cell.normalizedText)
        conf = 0.75 if field_guess != "unknown" else 0.55
        slots.append(
            _make_slot(
                f"slot_{tid}_r{below.row}c{below.col}_lb",
                table,
                "label_below",
                below,
                cell.normalizedText,
                field_guess,
                conf,
                [f"label='{cell.normalizedText}'", "below_cell_empty"],
            )
        )
    return slots


def detect_label_value_pair_slots(table: TableInfo) -> list[InputSlotCandidate]:
    """2열/4열 양식에서 라벨-값 쌍 패턴으로 입력칸을 탐지한다."""
    if _is_layout_unsafe(table):
        return []

    cols = getattr(table, "colCount", 0)
    if cols not in (2, 4):
        return []

    cells = table.cells
    tid = getattr(table, "tableId", "")
    cell_map = {(c.row, c.col): c for c in cells}
    slots: list[InputSlotCandidate] = []
    seen: set[tuple] = set()

    for cell in cells:
        if not getattr(cell, "normalizedText", ""):
            continue
        if getattr(cell, "isCoveredByMerge", False):
            continue
        col = getattr(cell, "col", 0)
        row = getattr(cell, "row", 0)
        if col % 2 != 0:
            continue
        right = cell_map.get((row, col + 1))
        if (
            not right
            or getattr(right, "normalizedText", "")
            or getattr(right, "isCoveredByMerge", False)
        ):
            continue
        key = (row, col + 1)
        if key in seen:
            continue
        seen.add(key)
        fg = _guess_field(cell.normalizedText)
        conf = 0.82 if fg != "unknown" else 0.60
        if conf < 0.70:
            continue
        slots.append(
            _make_slot(
                f"slot_{tid}_r{row}c{col + 1}_pair",
                table,
                "label_value_pair",
                right,
                cell.normalizedText,
                fg,
                conf,
                [
                    f"label='{cell.normalizedText}'",
                    "label_value_pair_pattern",
                    f"col_pair={col}/{col + 1}",
                ],
            )
        )
    return slots


def detect_merged_input_cells(table: TableInfo) -> list[InputSlotCandidate]:
    """라벨 옆/아래의 병합된 대형 입력칸을 탐지한다."""
    if _is_layout_unsafe(table):
        return []

    cells = table.cells
    tid = getattr(table, "tableId", "")
    cell_map = {(c.row, c.col): c for c in cells}
    slots: list[InputSlotCandidate] = []

    for cell in cells:
        text = getattr(cell, "normalizedText", "") or ""
        if not text or len(text) > 20:
            continue
        fg = _guess_field(text)
        if fg == "unknown":
            continue
        row, col = cell.row, cell.col
        right = cell_map.get((row, col + getattr(cell, "colSpan", 1)))
        if (
            right
            and getattr(right, "isMergedOrigin", False)
            and not getattr(right, "normalizedText", "")
        ):
            span = getattr(right, "colSpan", 1) * getattr(right, "rowSpan", 1)
            if span >= 2:
                slots.append(
                    _make_slot(
                        f"slot_{tid}_r{right.row}c{right.col}_merged",
                        table,
                        "merged_input_cell",
                        right,
                        text,
                        fg,
                        0.75,
                        [f"label='{text}'", "merged_right_cell_empty", f"span={span}"],
                    )
                )
    return slots


def detect_blank_after_known_header_slots(table: TableInfo) -> list[InputSlotCandidate]:
    """known header 텍스트 다음에 오는 빈칸을 탐지한다."""
    if _is_layout_unsafe(table):
        return []

    cells = table.cells
    tid = getattr(table, "tableId", "")
    cell_map = {(c.row, c.col): c for c in cells}
    slots: list[InputSlotCandidate] = []
    seen: set[tuple] = set()

    for cell in cells:
        text = getattr(cell, "normalizedText", "") or ""
        fg = _guess_field(text)
        if fg == "unknown":
            continue
        row, col = cell.row, cell.col
        # 오른쪽 다음 칸 확인
        right = cell_map.get((row, col + getattr(cell, "colSpan", 1)))
        if (
            right
            and not getattr(right, "normalizedText", "")
            and not getattr(right, "isCoveredByMerge", False)
        ):
            key = (right.row, right.col)
            if key not in seen:
                seen.add(key)
                slots.append(
                    _make_slot(
                        f"slot_{tid}_r{right.row}c{right.col}_bkh",
                        table,
                        "blank_after_known_header",
                        right,
                        text,
                        fg,
                        0.85,
                        [f"known_header='{text}'", "blank_right", f"fieldGuess={fg}"],
                    )
                )
        # 아래 칸 확인
        below = cell_map.get((row + getattr(cell, "rowSpan", 1), col))
        if (
            below
            and not getattr(below, "normalizedText", "")
            and not getattr(below, "isCoveredByMerge", False)
        ):
            key = (below.row, below.col)
            if key not in seen:
                seen.add(key)
                slots.append(
                    _make_slot(
                        f"slot_{tid}_r{below.row}c{below.col}_bkh",
                        table,
                        "blank_after_known_header",
                        below,
                        text,
                        fg,
                        0.78,
                        [f"known_header='{text}'", "blank_below", f"fieldGuess={fg}"],
                    )
                )
    return slots


def detect_metadata_form_slots(table: TableInfo) -> list[InputSlotCandidate]:
    """metadata/form 계열 표에서 기본 입력칸을 탐지한다.

    기본정보표, 신청서 헤더 등 구조화된 양식 입력칸을 찾는다.
    """
    if _is_layout_unsafe(table):
        return []

    layout = getattr(table, "layoutGuess", "")
    cells = table.cells
    tid = getattr(table, "tableId", "")

    # 라벨 셀 수 계산
    known_label_count = sum(
        1 for c in cells if _guess_field(getattr(c, "normalizedText", "") or "") != "unknown"
    )
    # metadata table이 아니면 known label이 3개 이상일 때만 처리
    is_metadata = layout in ("nested_container_table", "horizontal_table", "form_table")
    if not is_metadata and known_label_count < 3:
        return []

    cell_map = {(c.row, c.col): c for c in cells}
    slots: list[InputSlotCandidate] = []
    seen: set[tuple] = set()

    for cell in cells:
        text = getattr(cell, "normalizedText", "") or ""
        fg = _guess_field(text)
        if fg == "unknown":
            continue
        row, col = cell.row, cell.col
        # 오른쪽 빈칸
        right = cell_map.get((row, col + getattr(cell, "colSpan", 1)))
        if (
            right
            and not getattr(right, "normalizedText", "")
            and not getattr(right, "isCoveredByMerge", False)
        ):
            key = (right.row, right.col)
            if key not in seen:
                seen.add(key)
                conf = 0.90 if is_metadata else 0.82
                slots.append(
                    _make_slot(
                        f"slot_{tid}_r{right.row}c{right.col}_mf",
                        table,
                        "metadata_form_slot",
                        right,
                        text,
                        fg,
                        conf,
                        [f"label='{text}'", f"layout={layout}", "metadata_form_right_empty"],
                        table_role="basic_info",
                    )
                )
    return slots


def detect_data_table_append_slots(table: TableInfo) -> list[InputSlotCandidate]:
    """반복 데이터표의 추가 행 위치를 탐지한다.

    header row가 있고 마지막 행이 비어 있으면 append slot으로 반환한다.
    실제 append 실행은 하지 않고 후보만 산출한다.
    """
    if _is_layout_unsafe(table):
        return []

    cells = table.cells
    if not cells:
        return []

    tid = getattr(table, "tableId", "")
    rows_count = getattr(table, "rowCount", 0)
    if rows_count < 2:
        return []

    # header row 확인: 상단 행에 data table header 키워드가 있어야 한다
    row0_cells = [c for c in cells if c.row == 0]
    header_texts = " ".join(getattr(c, "normalizedText", "") or "" for c in row0_cells)
    has_data_header = any(kw in header_texts for kw in _DATA_TABLE_HEADERS)
    if not has_data_header:
        return []

    # 마지막 행 확인
    max_row = max(getattr(c, "row", 0) for c in cells)
    last_row_cells = [c for c in cells if c.row == max_row]
    last_row_empty = all(not getattr(c, "normalizedText", "") for c in last_row_cells)

    if not last_row_empty:
        # 빈 행이 없으면 마지막 다음 행을 append 대상으로 표시
        target_row_idx = max_row + 1
        # 헤더 맵 구성
        header_map = {
            getattr(c, "col", i): getattr(c, "normalizedText", "") or ""
            for i, c in enumerate(row0_cells)
        }
        slot = InputSlotCandidate(
            slotId=f"slot_{tid}_append_r{target_row_idx}",
            tableId=tid,
            tableRole="data_table",
            source="data_table_append_slot",
            labelText="",
            fieldGuess="appendRow",
            row=target_row_idx,
            col=0,
            visualRow=target_row_idx,
            visualCol=0,
            confidence=0.72,
            autoEditAllowed=False,
            reviewRequired=True,
            reviewRequiredReason="append_slot_requires_review",
            evidence=[
                f"data_header='{header_texts[:40]}'",
                f"insert_after_row={max_row}",
                f"header_map={list(header_map.values())[:5]}",
            ],
        )
        return [slot]

    # 빈 마지막 행이 있으면 그 행의 첫 번째 셀을 target으로
    if last_row_cells:
        first = last_row_cells[0]
        slot = InputSlotCandidate(
            slotId=f"slot_{tid}_append_r{max_row}",
            tableId=tid,
            tableRole="data_table",
            source="data_table_append_slot",
            labelText="",
            fieldGuess="appendRow",
            row=first.row,
            col=first.col,
            visualRow=getattr(first, "visualRow", first.row),
            visualCol=getattr(first, "visualCol", first.col),
            confidence=0.72,
            autoEditAllowed=False,
            reviewRequired=True,
            reviewRequiredReason="append_slot_requires_review",
            evidence=[
                f"data_header='{header_texts[:40]}'",
                "last_row_empty",
            ],
        )
        return [slot]
    return []


def detect_status_cells(table: TableInfo) -> list[InputSlotCandidate]:
    """상태값 셀(진행률, 검측상태, 자재상태 등)을 탐지한다."""
    if _is_layout_unsafe(table):
        return []

    cells = table.cells
    tid = getattr(table, "tableId", "")
    cell_map = {(c.row, c.col): c for c in cells}
    slots: list[InputSlotCandidate] = []

    for cell in cells:
        text = getattr(cell, "normalizedText", "") or ""
        fg = _guess_status_field(text)
        if fg == "unknown":
            continue
        row, col = cell.row, cell.col
        right = cell_map.get((row, col + getattr(cell, "colSpan", 1)))
        if right and not getattr(right, "normalizedText", ""):
            slots.append(
                _make_slot(
                    f"slot_{tid}_r{right.row}c{right.col}_sc",
                    table,
                    "status_cell",
                    right,
                    text,
                    fg,
                    0.78,
                    [f"status_label='{text}'", "status_cell_empty", f"fieldGuess={fg}"],
                )
            )
    return slots


def filter_unsafe_slots(
    slots: list[InputSlotCandidate],
    table: TableInfo,
) -> list[InputSlotCandidate]:
    """unsafe table에서 생성된 slot을 제거한다.

    unsafeReason이 있거나 tableRole이 unsafe인 slot을 autoEditAllowed=False로 마킹하고
    reviewRequired=True로 설정한다. 완전 제거보다 마킹 방식을 사용한다.
    """
    unsafe, reason = _is_unsafe_table(table)
    if not unsafe:
        return slots
    result = []
    for slot in slots:
        slot.autoEditAllowed = False
        slot.reviewRequired = True
        slot.unsafeReason = reason or "unsafe_table"
        if slot.reviewRequiredReason is None:
            slot.reviewRequiredReason = "unsafe_table"
        result.append(slot)
    return result


def score_slot(slot: InputSlotCandidate, table: TableInfo) -> InputSlotCandidate:
    """slot confidence를 표 구조 증거로 재계산한다.

    기준:
    - known label match: +0.30 (이미 반영됨)
    - target empty: +0.20 (이미 반영됨)
    - safe table role: +0.20
    - layout evidence: +0.15
    - style/input-like cell: +0.10
    - duplicate field 후보: -0.20
    - target not empty: -0.20
    - unsafe table: autoEditAllowed=False
    """
    conf = slot.confidence
    layout = getattr(table, "layoutGuess", "")
    role = getattr(slot, "tableRole", "unknown")

    if role in ("basic_info", "data_table"):
        conf = min(conf + 0.10, 0.98)
    if layout in ("nested_container_table", "horizontal_table"):
        conf = min(conf + 0.05, 0.98)

    unsafe, reason = _is_unsafe_table(table)
    if unsafe:
        slot.autoEditAllowed = False
        slot.reviewRequired = True
        slot.unsafeReason = reason or "unsafe_table"

    slot.confidence = round(conf, 2)
    slot.autoEditAllowed = conf >= _AUTO_EDIT_THRESHOLD and not slot.reviewRequired
    if conf < _REVIEW_REQUIRED_THRESHOLD and not slot.reviewRequiredReason:
        slot.reviewRequired = True
        slot.reviewRequiredReason = "low_confidence_after_scoring"
    return slot


# ── 통합 탐지 ────────────────────────────────────────────────────────────────


def detect_input_slots(
    tables: list[TableInfo],
    *,
    table_roles: dict[str, str] | None = None,
) -> list[InputSlotCandidate]:
    """전체 표 목록에서 입력칸 후보를 탐지한다.

    table_roles가 제공되면 각 표의 역할로 slot의 tableRole을 보강한다.
    중복 좌표 제거 후 score_slot으로 재점수화한다.
    """
    roles = table_roles or {}
    all_slots: list[InputSlotCandidate] = []
    seen: set[tuple] = set()

    for table in tables:
        tid = getattr(table, "tableId", "")
        table_role = roles.get(tid, getattr(table, "layoutGuess", "unknown"))

        # layout-based skip (구버전과 동일 기준 — text 패턴은 enhance_input_slots에서 처리)
        if _is_layout_unsafe(table):
            continue

        candidate_slots: list[InputSlotCandidate] = []
        # 기본 탐지: 모든 안전한 표
        candidate_slots.extend(detect_label_right_slots(table))
        candidate_slots.extend(detect_label_below_slots(table))
        candidate_slots.extend(detect_label_value_pair_slots(table))
        candidate_slots.extend(detect_merged_input_cells(table))
        # 확장 탐지: 안전한 레이아웃 또는 명시적 역할이 있는 표만 추가 실행
        layout = getattr(table, "layoutGuess", "")
        is_extended = layout in _SAFE_EXTENDED_LAYOUTS or table_role in ("basic_info", "data_table")
        if is_extended:
            candidate_slots.extend(detect_blank_after_known_header_slots(table))
            candidate_slots.extend(detect_metadata_form_slots(table))
            candidate_slots.extend(detect_data_table_append_slots(table))
            candidate_slots.extend(detect_status_cells(table))

        for slot in candidate_slots:
            key = (slot.tableId, slot.row, slot.col)
            if key in seen:
                continue
            seen.add(key)
            if slot.tableRole == "unknown" and table_role != "unknown":
                slot.tableRole = table_role
            score_slot(slot, table)
            all_slots.append(slot)

    return all_slots
