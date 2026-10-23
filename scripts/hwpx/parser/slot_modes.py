"""HWPX Parser V2 — 칸 안에 쓰는 방식이 다른 입력칸 탐지 (요청 121 2차).

기존 탐지기는 '라벨 옆/아래의 빈 칸'만 입력칸으로 본다. 법정 서식에는 그 밖에 세 가지가 있다.

- group_header : 머리글(병합 머리 포함) 아래로 같은 열에 빈 칸이 줄지어 있는 표(반복 행).
                 머리글 경로 '하도급내용 > 요율' 을 라벨로 삼는다. 단위만 적힌 칸('%', '원')도 빈 칸으로 본다.
- same_cell    : 라벨 글자 뒤 같은 칸에 값을 이어 쓰는 서식('건축주' 칸에 '건축주 홍길동').
- choice       : '[  ] 일괄  [  ] 개별', '□ 대상' 처럼 칸 안의 선택 상자.
- inline       : 한 칸 안에 '도급액: / 하도급금액: / 하도급률:' 처럼 라벨이 줄지어 있고 값 자리가 라벨 뒤인 칸(3차).
- replace      : '(      )' · '    년   월   일' 처럼 칸 안의 자리표시 글자를 값으로 바꾸는 칸(3차).

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
INLINE = "inline"
REPLACE = "replace"
EDIT_MODES = (INLINE, REPLACE)  # 칸 전체를 덮지 않고 글자 일부만 고치는 방식(hwpx_cell_text_edits)

# 자리표시 글자 — 엔진(hwpx_cell_text_edits)이 칸 글자에서 이 정규식으로 자리를 찾는다
PAREN_PATTERN = r"\(\s*\)"
DATE_PATTERN = r"년\s*월\s*일"

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


def slot_key(slot: object) -> tuple:
    """슬롯 중복 판정 키. 글자 일부만 고치는 슬롯은 한 칸에 여러 개일 수 있어 고칠 자리까지 키에 넣는다."""
    key = (getattr(slot, "tableId", ""), getattr(slot, "row", 0), getattr(slot, "col", 0))
    if getattr(slot, "writeMode", SET) in EDIT_MODES:
        return (*key, getattr(slot, "anchorText", ""))
    return key


def _slot(
    table: TableInfo,
    target: CellInfo,
    source: str,
    label: str,
    conf: float,
    mode: str,
    evidence: list[str],
    *,
    anchor: str = "",
    template: str = "{v}",
    suffix: str = "",
) -> InputSlotCandidate:
    from .input_slot_detector import _guess_field  # 같은 패키지의 라벨→필드 추정 재사용

    tid = getattr(table, "tableId", "")
    return InputSlotCandidate(
        slotId=f"slot_{tid}_r{target.row}c{target.col}_{source}{suffix}",
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
        anchorText=anchor,
        valueTemplate=template,
        cellRawText=(getattr(target, "text", "") or "") if mode in EDIT_MODES else "",
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
    # 머리글 줄 — 같은 줄이 라벨 글자뿐(3칸 이상)이고 바로 아래 줄에 값칸이 있으면, 아래 첫 칸이 '대표사' 같은 글자여도 열 머리글이다
    own = by_row.get(row, [])
    if len(own) >= 3 and all(unit_of(x) is None for x in own):
        for r in range(r0, r0 + _HEADER_LOOKAHEAD):
            if any(unit_of(x) is not None and not is_spacer_cell(x, by_row.get(r, []), n_cols) for x in by_row.get(r, [])):
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


# ── 글자 일부만 고치는 칸 (3차) ───────────────────────────────────────────────

_LEAD_RE = re.compile(r"^[\s(（\[\-·ㆍ•※]+")
_TAIL_BLANK_RE = re.compile(r"^[\s)）\]]*$")
_MAX_ANCHOR = 24
_MAX_PARAS = 6
_MAX_PARA_LEN = 60
# 여는 글자는 숫자(연도) 뒤가 아니어야 한다 — 이미 채워진 '2026년 10월' 같은 글자는 자리표시가 아니다
_BLANK_DATE_RE = re.compile(r"(?<![가-힣\d\s])\s*" + DATE_PATTERN)
_BLANK_DATE_LABEL_RE = re.compile(r"^\s*" + DATE_PATTERN + r"\s*$")


def is_blank_date_label(text: str | None) -> bool:
    """'년 월 일' 만 적힌 글자 — 날짜를 쓸 자리표시이지 아래 칸의 라벨이 아니다."""
    return bool(_BLANK_DATE_LABEL_RE.match(text or ""))


def _nearest_label(cell: CellInfo, pos: dict[tuple[int, int], CellInfo], default: str) -> str:
    """칸의 왼쪽(없으면 위쪽)에서 가장 가까운 라벨 글자."""
    row, col = grid_of(cell)
    for c in range(col - 1, -1, -1):
        left = pos.get((row, c))
        if left is not None and left is not cell and _is_label_like(left):
            return left.normalizedText.strip()
    for r in range(row - 1, max(row - 1 - _MAX_HEADER_ROWS, -1), -1):
        up = pos.get((r, col))
        if up is not None and up is not cell and _is_label_like(up):
            return up.normalizedText.strip()
    return default


def _colon_anchors(cell: CellInfo) -> list[str]:
    """줄(문단)마다 '라벨:' 로 끝나 값 자리가 비어 있는 라벨 글자. 한 줄에 콜론이 둘 이상이면 건너뛴다."""
    out: list[str] = []
    for para in getattr(cell, "paragraphs", None) or []:
        if len(re.findall(r"[:：]", para)) != 1:
            continue
        head, _colon, tail = re.split(r"([:：])", para, maxsplit=1)
        if not _TAIL_BLANK_RE.match(tail):
            continue  # 콜론 뒤에 이미 글자가 있다 — 값 자리가 아니다
        label = _LEAD_RE.sub("", head).strip()
        if not label or len(label) > _MAX_ANCHOR or is_value_like(label) or cell_kind(label):
            continue
        out.append(f"{label}:")
    return out


def detect_inline_slots(table: TableInfo) -> list[InputSlotCandidate]:
    """한 칸 안에 '라벨:' 이 줄지어 있고 값 자리가 라벨 뒤인 칸 — 라벨마다 슬롯 1개(같은 칸에 여러 개 가능).

    옆·아래에 따로 값칸이 있는 라벨 칸은 그쪽이 값칸이므로 제외한다. 선택 상자·서명 문구가 든 칸도 제외한다.
    """
    pos = _position_map(table)
    by_row: dict[int, list[CellInfo]] = {}
    for c in table.cells:
        if not getattr(c, "isCoveredByMerge", False):
            by_row.setdefault(grid_of(c)[0], []).append(c)
    n_cols = _grid_width(table)
    slots: list[InputSlotCandidate] = []
    for cell in table.cells:
        if getattr(cell, "isCoveredByMerge", False) or getattr(cell, "hasNestedTable", False):
            continue
        text = (getattr(cell, "normalizedText", "") or "").strip()
        if not text or choice_options(text) or _SIGN_TEXT_RE.search(text):
            continue
        anchors = _colon_anchors(cell)
        if not anchors or len(set(anchors)) != len(anchors):
            continue
        paras = [p.strip() for p in (getattr(cell, "paragraphs", None) or []) if p.strip()]
        if len(paras) > _MAX_PARAS or any(len(p) > _MAX_PARA_LEN for p in paras):
            continue  # 작성방법·안내문 칸 — 라벨 줄이 아니라 설명 문장이 든 칸
        row, col = grid_of(cell)
        span = getattr(cell, "colSpan", 1) or 1
        right = pos.get((row, col + span))
        below = pos.get((row + (getattr(cell, "rowSpan", 1) or 1), col))
        if right is not None and unit_of(right) is not None:
            continue  # 옆에 비어 있는 값칸이 따로 있다
        if len(anchors) == 1 and below is not None and unit_of(below) is not None and not is_spacer_cell(below, by_row.get(grid_of(below)[0], []), n_cols):
            # 아래 빈 칸은 라벨 1개짜리 칸의 값칸일 수 있다 — 단 그 칸의 왼쪽에 자기 라벨이 있으면 그 라벨의 값칸이다
            below_left = pos.get((grid_of(below)[0], grid_of(below)[1] - 1))
            if below_left is None or not (getattr(below_left, "normalizedText", "") or "").strip():
                continue
        for i, anchor in enumerate(anchors):
            label = anchor.rstrip(":").strip()
            slots.append(_slot(table, cell, "inline", label, 0.88, INLINE, ["colon_label_blank_after"], anchor=anchor, suffix=f"_i{i}"))
    return slots


def detect_placeholder_slots(table: TableInfo) -> list[InputSlotCandidate]:
    """'(      )' · '    년   월   일' — 칸 안의 자리표시 글자를 값으로 바꾸는 칸.

    서명·날인 문구가 같이 든 칸(신청 문장·결재 줄)은 칸 단위로 막는다.
    """
    pos = _position_map(table)
    slots: list[InputSlotCandidate] = []
    for cell in table.cells:
        if getattr(cell, "isCoveredByMerge", False) or getattr(cell, "hasNestedTable", False):
            continue
        norm = (getattr(cell, "normalizedText", "") or "").strip()
        raw = getattr(cell, "text", "") or ""
        if not norm or _SIGN_TEXT_RE.search(norm):
            continue
        if re.fullmatch(PAREN_PATTERN, norm):
            label = _nearest_label(cell, pos, "")
            if not label:
                continue
            slots.append(_slot(table, cell, "placeholder", label, 0.85, REPLACE, ["empty_parentheses"], anchor=PAREN_PATTERN, template="({v})"))
        elif _BLANK_DATE_RE.search(raw):
            label = _nearest_label(cell, pos, "일자")
            slots.append(_slot(table, cell, "placeholder", label, 0.85, REPLACE, ["blank_date"], anchor=DATE_PATTERN))
    return slots
