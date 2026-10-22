"""HWPX Parser V2 — 칸 종류 판정 (요청 121).

표 전체를 제외하던 규칙(법령 문구·서명·쪽 표시가 표 어디든 있으면 표 통째 제외)을
칸/행 단위 차단으로 바꾸기 위한 공용 판정. 입력칸 탐지기(input_slot_detector)와
표 역할 분류(form_recognizer)가 같은 규칙을 쓴다.

종류: sign(서명·인) / notice(안내문·처리절차 등) / office(관청 기재 칸) / page(쪽 표시)
"""

from __future__ import annotations

import re

SIGN = "sign"
NOTICE = "notice"
OFFICE = "office"
PAGE = "page"

_SIGN_RE = re.compile(r"\(\s*인\s*\)|\(\s*서명|서명|날인|직인|인감|도장|결재|\(\s*인$|^인$")
_PURE_SIGN_RE = re.compile(r"^[\s(（]*(서명\s*(또는|및|/)?\s*인|서명|인|날인|직인|인감)[\s)）]*$")
# '… 성명 (서명 또는 인)' '… 수급인 (서명 또는 인) 귀하' 처럼 서명 표시로 끝나는 칸 — 길이와 무관하게 서명줄이다.
_TRAILING_SIGN_RE = re.compile(r"[(（]\s*(서명\s*(또는|및|/)?\s*(인|날인)|인)\s*[)）]\s*(귀하|귀중|앞)?\s*$")
_NOTICE_RE = re.compile(
    r"처리\s*절차|첨부\s*서류|별지\s*제\s*\d+\s*호|쪽\s*번호|210\s*mm|297\s*mm|작성\s*요령|유의\s*사항|^※"
)
_OFFICE_RE = re.compile(
    r"접수\s*번호|접수\s*일|접수\s*연월일|처리\s*기간|발급\s*번호|발급\s*일|발급\s*연월일|교부\s*번호|교부\s*일"
)
_PAGE_RE = re.compile(r"[(（]?\s*(앞|뒤)\s*쪽\s*[)）]?|쪽\s*번호|^\s*\d+\s*[/-]\s*\d+\s*$|^page\b|페이지")

# 서명·안내 같은 '종류 판정'은 짧은 칸 글자에만 적용한다. 긴 문장 속의 '서명' 이라는 낱말은
# 설명문이지 서명칸이 아니다(안내문 종류는 길이와 무관하게 판정).
_SHORT = 20


def cell_kind(text: str | None) -> str:
    """칸 글자 → sign/notice/office/page, 해당 없으면 ''."""
    t = (text or "").strip()
    if not t:
        return ""
    if _NOTICE_RE.search(t):
        return NOTICE
    if len(t) <= 12 and _PAGE_RE.search(t):
        return PAGE
    if _TRAILING_SIGN_RE.search(t):
        return SIGN
    if len(t) <= _SHORT:
        if _SIGN_RE.search(t):
            return SIGN
        if _OFFICE_RE.search(t):
            return OFFICE
    return ""


# '100%' '2026-10-23' '1,000' 처럼 값 모양뿐인 글자는 라벨이 아니다 (값칸을 라벨로 잘못 읽은 것).
_VALUE_LIKE_RE = re.compile(r"^[\s\d.,%/~:\-]+$")


def is_value_like(text: str | None) -> bool:
    t = (text or "").strip()
    return bool(t) and bool(_VALUE_LIKE_RE.match(t)) and any(ch.isdigit() for ch in t)


def _is_title_label(table, label: str) -> bool:
    """표 폭의 60% 이상을 가로지르는 '…서/증/표/장/부' 로 끝나는 칸 — 서식 제목이지 항목 라벨이 아니다.

    같은 폭이어도 '허가(신고)번호' 처럼 항목명이면 라벨(값칸이 아래에 있음)이므로 막지 않는다.
    """
    if label[-1:] not in "서증표장부":
        return False
    n_cols = max((grid_of(c)[1] + (getattr(c, "colSpan", 1) or 1) for c in _cells_of(table)), default=0)
    if n_cols < 4:
        return False
    for c in _cells_of(table):
        if (getattr(c, "normalizedText", "") or "").strip() == label and (getattr(c, "colSpan", 1) or 1) * 10 >= n_cols * 6:
            return True
    return False


def is_pure_sign_marker(text: str | None) -> bool:
    """'(인)' '(서명 또는 인)' 처럼 서명 표시만 있는 칸."""
    return bool(_PURE_SIGN_RE.match((text or "").strip()))


def _cells_of(table) -> list:
    return list(getattr(table, "cells", []) or [])


def table_exclusion(table) -> str:
    """표 전체를 입력 대상에서 뺄지: 'page'/'stamp'/'notice'/''.

    표 어딘가에 서명·쪽 글자가 있다는 이유만으로는 빼지 않는다(그런 칸은 slot_block_reason 이
    칸 단위로 막는다). 표 자체가 쪽 표시·결재란·안내문 묶음일 때만 뺀다.
    """
    cells = _cells_of(table)
    texts = [(getattr(c, "normalizedText", "") or "") for c in cells]
    nonempty = [t for t in texts if t]
    if not nonempty:
        return ""
    kinds = [cell_kind(t) for t in nonempty]
    n = len(nonempty)
    if len(cells) <= 4 and kinds.count(PAGE) >= 1:
        return "page"
    if len(cells) <= 12 and (kinds.count(SIGN) >= 1) and kinds.count(SIGN) * 2 >= n - 1:
        return "stamp"
    if any(re.search(r"처리\s*절차", t) for t in nonempty):
        return "notice"
    if kinds.count(NOTICE) * 2 >= n:
        return "notice"
    return ""


_THIN_ROW_HEIGHT = 700  # HWPUNIT. 이보다 낮은 행은 글자를 쓸 자리가 아니라 구역 사이 간격이다


def is_spacer_cell(cell, row_cells: list, n_cols: int) -> bool:
    """구역 사이 간격용 얇은 빈 행 — 글자가 없고, 행에 칸이 하나뿐이며 표 폭 대부분을 덮고, 높이가 낮다."""
    if (getattr(cell, "normalizedText", "") or "").strip() or n_cols <= 0:
        return False
    height = getattr(cell, "cellHeight", 0) or 0
    span = getattr(cell, "colSpan", 1) or 1
    return 0 < height < _THIN_ROW_HEIGHT and len(row_cells) == 1 and span * 10 >= n_cols * 8


def slot_block_reason(table, slot, cells_by_row: dict | None = None) -> str:
    """입력칸 후보 1개를 칸 단위로 막을 사유. 막지 않으면 ''.

    - 라벨이 서명/안내문/관청기재/쪽 표시이면 그 오른쪽·아래 칸은 입력칸이 아니다.
    - 같은 행에 안내문 칸이 있으면 그 행의 칸은 입력칸이 아니다.
    - 바로 옆(왼쪽·오른쪽)이 '(인)' 같은 서명 표시만 있는 칸이면 서명/날인 자리로 보고 막는다.
    """
    kind = cell_kind(getattr(slot, "labelText", ""))
    if kind:
        return f"label_{kind}"
    label = (getattr(slot, "labelText", "") or "").strip()
    if is_value_like(label):
        return "label_is_value"
    if label and _is_title_label(table, label):
        return "title_label"
    row, col = grid_of(slot)
    span = getattr(slot, "colSpan", 1) or 1
    mode = getattr(slot, "writeMode", "set")
    if cells_by_row is None:
        cells_by_row = rows_index(table)
    n_cols = max((grid_of(c)[1] + (getattr(c, "colSpan", 1) or 1) for c in _cells_of(table)), default=0)
    for c in cells_by_row.get(row, []):
        if grid_of(c) == (row, col) and is_spacer_cell(c, cells_by_row.get(row, []), n_cols):
            return "spacer_row"
    for c in cells_by_row.get(row, []):
        if grid_of(c) == (row, col) and getattr(c, "hasNestedTable", False):
            # 안쪽 표를 품은 칸은 쓴 글자가 안쪽 표의 첫 칸으로 들어가 라벨을 덮어쓴다
            return "nested_table_cell"
        t = getattr(c, "normalizedText", "") or ""
        if not t:
            continue
        if cell_kind(t) == NOTICE:
            return "row_notice"
        c_col = grid_of(c)[1]
        c_span = getattr(c, "colSpan", 1) or 1
        # 글자가 이미 있는 칸(이어 쓰기·선택 상자)은 도장 찍는 빈 자리가 아니라서 서명 표시 옆이어도 막지 않는다
        if mode in ("set", "unit") and is_pure_sign_marker(t) and (c_col + c_span == col or c_col == col + span):
            return "next_to_sign_marker"
    return ""


def grid_of(cell) -> tuple[int, int]:
    """편집기(hp:cellAddr)와 같은 격자 주소. col + colSpan 으로 이웃 칸을 찾을 수 있는 좌표계.

    visualRow/visualCol 이 기본값 (0, 0) 인데 row/col 이 0 이 아니면 격자 주소가 채워지지
    않은 셀(손으로 만든 셀 등)이므로 row/col 을 쓴다. 파서가 만든 셀은 (0, 0) 이면 첫 칸뿐이다.
    """
    row, col = getattr(cell, "row", 0), getattr(cell, "col", 0)
    v_row, v_col = getattr(cell, "visualRow", 0), getattr(cell, "visualCol", 0)
    if (v_row, v_col) == (0, 0) and (row, col) != (0, 0):
        return row, col
    return v_row, v_col


def rows_index(table) -> dict[int, list]:
    out: dict[int, list] = {}
    for c in _cells_of(table):
        out.setdefault(grid_of(c)[0], []).append(c)
    return out
