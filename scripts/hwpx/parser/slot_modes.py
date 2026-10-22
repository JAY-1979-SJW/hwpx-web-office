"""HWPX Parser V2 — 칸 안에 쓰는 방식이 다른 입력칸 탐지 (요청 121 2차).

기존 탐지기는 '라벨 옆/아래의 빈 칸'만 입력칸으로 본다. 법정 서식에는 그 밖에 세 가지가 있다.

- group_header : 머리글(병합 머리 포함) 아래로 같은 열에 빈 칸이 줄지어 있는 표(반복 행).
                 머리글 경로 '하도급내용 > 요율' 을 라벨로 삼는다. 단위만 적힌 칸('%', '원')도 빈 칸으로 본다.
- same_cell    : 라벨 글자 뒤 같은 칸에 값을 이어 쓰는 서식('건축주' 칸에 '건축주 홍길동').
- choice       : '[  ] 일괄  [  ] 개별', '□ 대상' 처럼 칸 안의 선택 상자.

쓰는 방식(writeMode)과 칸에 원래 있던 글자(cellText)를 슬롯에 실어, 계획 단계가 칸 전체 글자를 만든다.
"""

from __future__ import annotations

import re

from .cell_kind import cell_kind, grid_of, is_spacer_cell, is_value_like
from .parser_contract import CellInfo, InputSlotCandidate, TableInfo

SET = "set"
APPEND = "append"
UNIT = "unit"
CHOICE = "choice"

# '[  ]' '[ ]' '( )' 대신 □ ☐ 만 상자로 본다. '( )' 는 빈 괄호 자리 표시와 구분되지 않는다.
_BOX_RE = re.compile(r"(\[\s*\]|□|☐)\s*([^\[\]□☐]{1,30}?)(?=\s*(?:\[\s*\]|□|☐|$))")
_UNIT_ONLY_RE = re.compile(
    r"^[\s(（]*(%|원|천원|백만원|만원|억원|개|명|호|일|월|년|㎡|㎥|m²|m³|mm|cm|km|m|kg|t|건|식|회|세대|대|㎏)[\s)）]*$"
)
_SIGN_TEXT_RE = re.compile(r"서명|\(\s*인\s*\)|또는\s*인|날인|직인")
_MAX_LABEL = 20
# 번호 붙은 제목('1. 공사개요', '가. 하도급계약', '- 전문공사'), 쪽 표시('(3쪽중제1쪽)'), 번호 머리 열 이름('4보증금')은 쓸 자리가 아니다.
_HEADING_RE = re.compile(r"^\s*(?:\d+\s*[.)．]|\d+(?=[가-힣A-Za-z])|[가-하]\s*[.)．]|[-·ㆍ•※]|\(\s*\d+\s*쪽)")
_MAX_HEADER_ROWS = 12
_HEADER_LOOKAHEAD = 4


# ── 선택 상자 ────────────────────────────────────────────────────────────────


def choice_options(text: str | None) -> list[str]:
    """'[  ] 일괄  [  ] 개별' → ['일괄', '개별']. 상자가 없으면 []."""
    out: list[str] = []
    for m in _BOX_RE.finditer(text or ""):
        label = m.group(2).strip()
        if label:
            out.append(label)
    return out


def mark_choice(text: str, label: str) -> str | None:
    """칸 글자 안에서 label 앞의 빈 상자 하나를 체크 표시로 바꾼 글자. 찾지 못하면 None."""
    for m in _BOX_RE.finditer(text or ""):
        if m.group(2).strip() != label:
            continue
        box = m.group(1)
        mark = "[√]" if box.startswith("[") else "☑"
        return text[: m.start(1)] + mark + text[m.end(1) :]
    return None


# ── 칸 분류 보조 ─────────────────────────────────────────────────────────────


def unit_of(cell: CellInfo) -> str | None:
    """빈 칸이면 '', 단위만 있으면 그 글자, 그 밖의 글자가 있으면 None."""
    t = (getattr(cell, "normalizedText", "") or "").strip()
    if not t:
        return ""
    if _UNIT_ONLY_RE.match(t):
        return t
    return None


def _is_label_like(cell: CellInfo | None) -> bool:
    if cell is None:
        return False
    t = (getattr(cell, "normalizedText", "") or "").strip()
    if not t or len(t) > _MAX_LABEL or is_value_like(t) or cell_kind(t):
        return False
    return unit_of(cell) is None


def _grid_width(table: TableInfo) -> int:
    return max((grid_of(c)[1] + (getattr(c, "colSpan", 1) or 1) for c in table.cells), default=0)


def _position_map(table: TableInfo) -> dict[tuple[int, int], CellInfo]:
    """격자 위치 → 그 위치를 덮는 칸 (병합된 모든 위치 포함)."""
    pos: dict[tuple[int, int], CellInfo] = {}
    for c in table.cells:
        r0, c0 = grid_of(c)
        for dr in range(getattr(c, "rowSpan", 1) or 1):
            for dc in range(getattr(c, "colSpan", 1) or 1):
                pos.setdefault((r0 + dr, c0 + dc), c)
    return pos


def _slot(table: TableInfo, target: CellInfo, source: str, label: str, conf: float, mode: str, evidence: list[str]) -> InputSlotCandidate:
    from .input_slot_detector import _guess_field  # 같은 패키지의 라벨→필드 추정 재사용

    tid = getattr(table, "tableId", "")
    return InputSlotCandidate(
        slotId=f"slot_{tid}_r{target.row}c{target.col}_{source}",
        tableId=tid,
        source=source,
        labelText=label,
        fieldGuess=_guess_field(label),
        row=target.row,
        col=target.col,
        visualRow=getattr(target, "visualRow", target.row),
        visualCol=getattr(target, "visualCol", target.col),
        rowSpan=getattr(target, "rowSpan", 1),
        colSpan=getattr(target, "colSpan", 1),
        confidence=conf,
        evidence=evidence,
        writeMode=mode,
        cellText=(getattr(target, "normalizedText", "") or "").strip(),
    )


# ── 탐지기 ───────────────────────────────────────────────────────────────────


def detect_group_header_slots(table: TableInfo) -> list[InputSlotCandidate]:
    """머리글 아래 같은 열의 빈 칸(또는 단위만 있는 칸) — 반복 행·병합 머리 경로."""
    cells = [c for c in table.cells if not getattr(c, "isCoveredByMerge", False)]
    if not cells:
        return []
    pos = _position_map(table)
    n_cols = _grid_width(table)
    header_row_labels: dict[int, int] = {}
    for c in cells:
        if _is_label_like(c):
            header_row_labels[grid_of(c)[0]] = header_row_labels.get(grid_of(c)[0], 0) + 1
    by_row: dict[int, list[CellInfo]] = {}
    for c in cells:
        by_row.setdefault(grid_of(c)[0], []).append(c)

    slots: list[InputSlotCandidate] = []
    for cell in cells:
        unit = unit_of(cell)
        if unit is None or getattr(cell, "hasNestedTable", False):
            continue
        row, col = grid_of(cell)
        header = None
        for r in range(row - 1, max(row - 1 - _MAX_HEADER_ROWS, -1), -1):
            above = pos.get((r, col))
            if above is None:
                continue
            if unit_of(above) is not None:
                continue  # 빈 칸·단위 칸은 건너뛰고 머리글을 계속 찾는다
            header = above
            break
        if header is None or not _is_label_like(header):
            continue
        h_span = getattr(header, "colSpan", 1) or 1
        if n_cols >= 4 and h_span * 10 >= n_cols * 6:
            continue  # 표 폭 대부분을 가로지르는 띠는 제목이지 열 머리글이 아니다
        h_row = grid_of(header)[0]
        row_has_label = any(
            _is_label_like(x) and grid_of(x)[1] + (getattr(x, "colSpan", 1) or 1) <= col for x in by_row.get(row, [])
        )
        if not row_has_label and header_row_labels.get(h_row, 0) < 3:
            continue
        group = None
        for r in range(h_row - 1, max(h_row - 4, -1), -1):
            up = pos.get((r, col))
            if up is not None and up is not header and _is_label_like(up) and (getattr(up, "colSpan", 1) or 1) > h_span:
                group = up
                break
        path = f"{group.normalizedText.strip()} > {header.normalizedText.strip()}" if group else header.normalizedText.strip()
        slots.append(
            _slot(
                table,
                cell,
                "group_header",
                path,
                0.80,
                UNIT if unit else SET,
                [f"header='{header.normalizedText.strip()}'", "column_below_header", f"unit='{unit}'" if unit else "blank"],
            )
        )
    return slots


def detect_choice_slots(table: TableInfo) -> list[InputSlotCandidate]:
    """칸 안에 □/[  ] 선택 상자가 있는 칸."""
    by_row: dict[int, list[CellInfo]] = {}
    for c in table.cells:
        by_row.setdefault(grid_of(c)[0], []).append(c)
    slots: list[InputSlotCandidate] = []
    for cell in table.cells:
        if getattr(cell, "isCoveredByMerge", False) or getattr(cell, "hasNestedTable", False):
            continue
        text = (getattr(cell, "normalizedText", "") or "").strip()
        options = choice_options(text)
        if not options or _SIGN_TEXT_RE.search(text):
            continue  # 서명·날인 문구가 같이 든 칸(신청 문장 등)은 서명칸이므로 선택 칸으로 쓰지 않는다
        row, col = grid_of(cell)
        left = [x for x in by_row.get(row, []) if grid_of(x)[1] + (getattr(x, "colSpan", 1) or 1) <= col and _is_label_like(x)]
        label = max(left, key=lambda x: grid_of(x)[1]).normalizedText.strip() if left else "선택"
        slots.append(_slot(table, cell, "choice", label, 0.85, CHOICE, [f"options={options}"]))
    return slots


def _is_column_header(cell: CellInfo, pos: dict[tuple[int, int], CellInfo], by_row: dict[int, list[CellInfo]], n_cols: int) -> bool:
    """같은 열 아래쪽(가까운 몇 줄 안)에 실제 빈 칸이 줄지어 있으면 이 칸은 열 머리글이다."""
    row, col = grid_of(cell)
    r0 = row + (getattr(cell, "rowSpan", 1) or 1)
    for r in range(r0, r0 + _HEADER_LOOKAHEAD):
        below = pos.get((r, col))
        if below is None or unit_of(below) is None:
            continue
        if is_spacer_cell(below, by_row.get(grid_of(below)[0], []), n_cols):
            continue
        return True
    return False


def detect_same_cell_slots(table: TableInfo) -> list[InputSlotCandidate]:
    """라벨 글자만 있는 넓은 칸 — 라벨 뒤 같은 칸에 값을 이어 쓰는 서식.

    오탐을 줄이려고 세 조건을 모두 요구한다: 같은 행에 빈 칸이 없고(옆 값칸이 따로 없음),
    바로 아래도 빈 칸이 아니며(아래 값칸이 따로 없음), 칸이 표 폭의 10% 이상이다(쓸 자리가 있음).
    """
    n_cols = _grid_width(table)
    if n_cols < 4:
        return []
    blanks = sum(1 for c in table.cells if unit_of(c) == "")
    if blanks * 10 < len(table.cells):
        return []  # 빈 칸이 거의 없는 표는 분류표·안내표다 — 쓸 자리가 없다
    pos = _position_map(table)
    by_row: dict[int, list[CellInfo]] = {}
    for c in table.cells:
        if not getattr(c, "isCoveredByMerge", False):
            by_row.setdefault(grid_of(c)[0], []).append(c)
    slots: list[InputSlotCandidate] = []
    for cell in table.cells:
        if getattr(cell, "isCoveredByMerge", False) or getattr(cell, "hasNestedTable", False):
            continue
        if not _is_label_like(cell) or choice_options(cell.normalizedText):
            continue
        if _HEADING_RE.match(cell.normalizedText):
            continue
        span = getattr(cell, "colSpan", 1) or 1
        if span * 10 < n_cols:
            continue
        row, col = grid_of(cell)
        if any(unit_of(x) is not None or choice_options(x.normalizedText) for x in by_row.get(row, [])):
            continue  # 같은 행에 빈 칸·단위 칸·선택 상자가 있으면 값칸은 그쪽이다
        below = pos.get((row + (getattr(cell, "rowSpan", 1) or 1), col))
        if below is not None and unit_of(below) is not None and not is_spacer_cell(below, by_row.get(grid_of(below)[0], []), n_cols):
            continue
        if _is_column_header(cell, pos, by_row, n_cols):
            continue
        text = cell.normalizedText.strip()
        slots.append(_slot(table, cell, "same_cell", text, 0.90, APPEND, ["label_only_wide_cell", "no_blank_in_row"]))
    return slots
