"""요청 121 2차 — 쓰는 방식이 다른 입력칸(선택 상자·머리글 아래 반복 행·같은 칸 이어쓰기) 규칙 시험."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
for _p in (_ROOT / "scripts", _ROOT / "scripts" / "hwpx"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from hwpx.parser.parser_contract import CellInfo, TableInfo  # noqa: E402
from hwpx.parser.slot_modes import (  # noqa: E402
    APPEND,
    CHOICE,
    UNIT,
    choice_options,
    detect_choice_slots,
    detect_group_header_slots,
    detect_same_cell_slots,
    mark_choice,
    unit_of,
)


def _cell(r: int, c: int, text: str = "", col_span: int = 1, height: int = 1500) -> CellInfo:
    return CellInfo(
        row=r, col=c, visualRow=r, visualCol=c, colSpan=col_span, text=text, normalizedText=text.replace(" ", ""), cellHeight=height
    )


def _table(*cells: CellInfo) -> TableInfo:
    return TableInfo(tableId="t0", cells=list(cells))


def test_choice_options_and_mark():
    assert choice_options("[  ] 일괄  [  ] 개별") == ["일괄", "개별"]
    assert mark_choice("[  ] 일괄  [  ] 개별", "개별") == "[  ] 일괄  [√] 개별"
    assert mark_choice("□ 대상 □ 비대상", "대상") == "☑ 대상 □ 비대상"
    assert mark_choice("[ ] 일괄", "없음") is None
    assert choice_options("일반 글자") == []


def test_unit_of_distinguishes_blank_unit_and_text():
    assert unit_of(_cell(0, 0, "")) == ""
    assert unit_of(_cell(0, 0, "%")) == "%"
    assert unit_of(_cell(0, 0, "공사명")) is None


def test_choice_cell_is_choice_slot():
    t = _table(_cell(0, 0, "대상여부"), _cell(0, 1, "□ 대상 □ 비대상", col_span=3))
    slots = detect_choice_slots(t)
    assert [s.writeMode for s in slots] == [CHOICE]
    assert slots[0].labelText == "대상여부"


def test_group_header_unit_cell_is_unit_slot():
    t = _table(
        _cell(0, 0, "공종"),
        _cell(0, 1, "요율"),
        _cell(0, 2, "금액"),
        _cell(1, 0, ""),
        _cell(1, 1, "%"),
        _cell(1, 2, ""),
    )
    slots = {(s.visualRow, s.visualCol): s for s in detect_group_header_slots(t)}
    assert slots[(1, 1)].writeMode == UNIT
    assert slots[(1, 1)].cellText == "%"
    assert slots[(1, 1)].labelText == "요율"


def _wide_table(*extra: CellInfo) -> TableInfo:
    return _table(
        _cell(0, 0, "건축주", col_span=8),
        _cell(1, 0, "주소", col_span=8),
        _cell(2, 0, "", col_span=8, height=300),  # 얇은 간격 행: 값칸이 아니다
        _cell(3, 0, "비고", col_span=4),
        _cell(3, 4, "", col_span=4),
        *extra,
    )


def test_same_cell_append_for_label_only_wide_cell():
    slots = {s.labelText: s for s in detect_same_cell_slots(_wide_table())}
    assert slots["건축주"].writeMode == APPEND
    assert slots["주소"].writeMode == APPEND
    assert "비고" not in slots  # 같은 행에 빈 칸이 있으면 값칸은 그쪽


def test_same_cell_skips_headings_and_tables_without_blanks():
    heading = _table(
        _cell(0, 0, "1. 공사개요", col_span=8),
        _cell(1, 0, "(3쪽중제1쪽)", col_span=8),
        _cell(2, 0, "비고", col_span=4),
        _cell(2, 4, "", col_span=4),
    )
    labels = {s.labelText for s in detect_same_cell_slots(heading)}
    assert labels.isdisjoint({"1. 공사개요", "(3쪽중제1쪽)"})
    no_blank = _table(*(_cell(r, c, f"분류{r}{c}", col_span=2) for r in range(3) for c in range(0, 8, 2)))
    assert detect_same_cell_slots(no_blank) == []


def test_same_cell_skips_column_header_with_blanks_below():
    t = _table(
        _cell(0, 0, "구분", col_span=4),
        _cell(0, 4, "내용", col_span=4),
        _cell(1, 0, "", col_span=4),
        _cell(1, 4, "", col_span=4),
    )
    assert detect_same_cell_slots(t) == []


def test_set_cell_text_drops_inline_marks_and_their_tail():
    """<hp:t>[  ]<hp:fwSpace/>건축설비</hp:t> 를 덮어쓸 때 fwSpace 뒤 글자가 남아 중복되면 안 된다 (요청 121 2차)."""
    import xml.etree.ElementTree as ET

    from hwpx.hwpx_table_ops import set_cell_single_text

    ns = "http://www.hancom.co.kr/hwpml/2011/paragraph"
    cell = ET.fromstring(
        f'<tc xmlns:hp="{ns}"><hp:subList><hp:p><hp:run><hp:t>[  ]<hp:fwSpace/>건축설비</hp:t></hp:run></hp:p></hp:subList></tc>'
    )
    set_cell_single_text(cell, "[√] 건축설비")
    node = cell.find(f".//{{{ns}}}t")
    assert node is not None
    assert node.text == "[√] 건축설비"
    assert len(node) == 0
