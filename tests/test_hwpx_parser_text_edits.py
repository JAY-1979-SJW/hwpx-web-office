"""요청 121 3차 — 칸 글자 일부만 고치는 입력칸(한 칸 여러 값 inline · '( )' 자리표시 replace) 시험."""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
for _p in (_ROOT / "scripts", _ROOT / "scripts" / "hwpx"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from hwpx.parser.parser_contract import CellInfo, TableInfo
from hwpx.parser.slot_modes import (
    DATE_PATTERN,
    INLINE,
    PAREN_PATTERN,
    REPLACE,
    detect_inline_slots,
    detect_placeholder_slots,
)
from hwpx.pipeline.plan_builder import (
    format_blank_date,
    merge_edit_item,
    text_edit_for,
)
from hwpx_cell_text_edits import apply_edit, apply_edits

_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"


def _cell(r: int, c: int, text: str = "", col_span: int = 1, paragraphs: list[str] | None = None) -> CellInfo:
    return CellInfo(
        row=r,
        col=c,
        visualRow=r,
        visualCol=c,
        colSpan=col_span,
        text=text,
        normalizedText=" ".join(text.split()),
        paragraphs=paragraphs if paragraphs is not None else [text],
        cellHeight=1500,
    )


def _table(*cells: CellInfo) -> TableInfo:
    return TableInfo(tableId="t0", cells=list(cells))


# ── 순수 편집 ─────────────────────────────────────────────────────────────────


def test_after_edit_inserts_value_after_anchor_only():
    out = apply_edit("착공(예정): 준공(예정):", {"kind": "after", "anchor": "착공(예정):", "value": "2026"})
    assert out == "착공(예정): 2026 준공(예정):"


def test_after_edit_ignores_space_and_nfkc_differences():
    edit = {"kind": "after", "anchor": "도급액(① 하도급 부분):", "value": "V"}
    assert apply_edit("도급액(1 하도급부분):하도급(예정)금액:", edit) == "도급액(1 하도급부분): V하도급(예정)금액:"
    assert apply_edit("도급액(① 하도급 부분):", edit) == "도급액(① 하도급 부분): V"


def test_replace_edit_and_missing_anchor():
    assert apply_edit("( )", {"kind": "replace", "pattern": PAREN_PATTERN, "value": "(홍)"}) == "(홍)"
    assert apply_edit("공사명", {"kind": "after", "anchor": "현장명:", "value": "x"}) is None
    assert apply_edits("a: b:", [{"kind": "after", "anchor": "a:", "value": "1"}, {"kind": "after", "anchor": "z:", "value": "2"}]) is None


# ── 엔진: 칸의 다른 줄·표시가 그대로 남는다 ───────────────────────────────────


def test_engine_edits_only_matching_paragraph_node():
    from hwpx.hwpx_table_ops import apply_cell_text_edits

    cell = ET.fromstring(
        f'<tc xmlns:hp="{_NS}"><hp:subList>'
        "<hp:p><hp:run><hp:t>착공(예정):</hp:t></hp:run></hp:p>"
        "<hp:p><hp:run><hp:t>준공(예정):</hp:t></hp:run></hp:p>"
        "</hp:subList></tc>"
    )
    edits = [{"kind": "after", "anchor": "준공(예정):", "value": "2027"}]
    assert apply_cell_text_edits(cell, edits) is not None
    texts = [t.text for t in cell.iter(f"{{{_NS}}}t")]
    assert texts == ["착공(예정):", "준공(예정): 2027"]
    assert apply_cell_text_edits(cell, [{"kind": "after", "anchor": "없는라벨:", "value": "x"}]) is None


# ── 탐지 ──────────────────────────────────────────────────────────────────────


def test_inline_slots_one_per_colon_label():
    t = _table(
        _cell(0, 0, "구분"),
        _cell(0, 1, "착공(예정):준공(예정):", col_span=3, paragraphs=["착공(예정):", "준공(예정):"]),
        _cell(1, 0, "비고"),
        _cell(1, 1, "내용", col_span=3),
    )
    slots = detect_inline_slots(t)
    assert [s.writeMode for s in slots] == [INLINE, INLINE]
    assert [s.anchorText for s in slots] == ["착공(예정):", "준공(예정):"]
    assert len({s.slotId for s in slots}) == 2


def test_inline_skips_notice_cell_and_sign_text():
    long_para = "연락처: " + "발주자 담당자의 전자우편 또는 전화번호를 적습니다 " * 3
    notice = _table(_cell(0, 0, long_para, col_span=4, paragraphs=[long_para]))
    assert detect_inline_slots(notice) == []
    sign = _table(_cell(0, 0, "성명: (서명 또는 인)", col_span=4))
    assert detect_inline_slots(sign) == []


def test_placeholder_paren_and_blank_date():
    t = _table(
        _cell(0, 0, "대표자"),
        _cell(0, 1, "( )"),
        _cell(1, 0, "작성일"),
        _cell(1, 1, "    년   월   일", col_span=2),
        _cell(2, 0, "생년월일"),
        _cell(2, 1, "법인등록번호(개인인 경우 생년월일)", col_span=2),
    )
    slots = detect_placeholder_slots(t)
    by = {(s.visualRow, s.visualCol): s for s in slots}
    assert set(by) == {(0, 1), (1, 1)}  # 라벨 글자 속 '생년월일' 은 자리표시가 아니다
    assert by[(0, 1)].writeMode == REPLACE and by[(0, 1)].anchorText == PAREN_PATTERN
    assert by[(0, 1)].labelText == "대표자"
    assert by[(1, 1)].anchorText == DATE_PATTERN


def test_placeholder_skips_sign_text_cell():
    t = _table(_cell(0, 0, "신청인"), _cell(0, 1, "( ) (서명 또는 인)", col_span=3))
    assert detect_placeholder_slots(t) == []


# ── 계획 ──────────────────────────────────────────────────────────────────────


def test_blank_date_format():
    assert format_blank_date("2026-10-23") == "2026년 10월 23일"
    assert format_blank_date("내일") == "내일"


def test_plan_merges_edits_of_same_cell_and_recomputes_value():
    t = _table(_cell(0, 0, "구분"), _cell(0, 1, "착공(예정):준공(예정):", col_span=3, paragraphs=["착공(예정):", "준공(예정):"]))
    s1, s2 = detect_inline_slots(t)
    items: list[dict] = []
    bases: dict = {}
    for slot, val in ((s1, "A"), (s2, "B")):
        edit = text_edit_for(slot, val)
        item = {"table": 0, "visual_row": 0, "visual_col": 1, "value": "", "text_edits": [edit]}
        assert merge_edit_item(items, bases, item, slot.cellText)
    assert len(items) == 1 and len(items[0]["text_edits"]) == 2
    assert items[0]["value"] == "착공(예정): A준공(예정): B"


def test_plan_rejects_edit_on_cell_already_fully_overwritten():
    items = [{"table": 0, "visual_row": 0, "visual_col": 1, "value": "x"}]
    item = {"table": 0, "visual_row": 0, "visual_col": 1, "value": "y", "text_edits": [{"kind": "after", "anchor": "a:", "value": "1"}]}
    assert merge_edit_item(items, {}, item, "a:") is False
