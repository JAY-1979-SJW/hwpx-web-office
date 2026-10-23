"""요청 121 4차 — 서명 칸 안 날짜, 이름 칸+서명 칸 완화, 구분기호 칸, 라벨 길이·라벨 사전, 서명 문단 불변 시험."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
for _p in (_ROOT / "scripts", _ROOT / "scripts" / "hwpx"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from hwpx.parser.cell_kind import (  # noqa: E402
    NAME_NEXT_TO_SIGN,
    SIGN_CELL_DATE,
    has_notice_exception,
    name_next_to_sign,
    sign_paragraphs,
    slot_block_reason,
)
from hwpx.parser.input_slot_detector import (  # noqa: E402
    _label_length,
    detect_input_slots,
)
from hwpx.parser.parser_contract import CellInfo, TableInfo  # noqa: E402
from hwpx.parser.slot_modes import (  # noqa: E402
    APPEND,
    REPLACE,
    SEPARATOR,
    detect_placeholder_slots,
    detect_same_cell_slots,
    detect_separator_slots,
    separator_text,
)
from hwpx.pipeline.form_recognizer import _notice_exception_ok  # noqa: E402
from hwpx.pipeline.plan_builder import _final_cell_text  # noqa: E402
from hwpx.pipeline.reparse_verifier import sign_paragraph_changes  # noqa: E402


def _cell(r, c, text="", col_span=1, height=1500, paragraphs=None) -> CellInfo:
    return CellInfo(
        row=r,
        col=c,
        visualRow=r,
        visualCol=c,
        colSpan=col_span,
        text="\n".join(paragraphs) if paragraphs else text,
        normalizedText=("".join(paragraphs) if paragraphs else text).replace(" ", ""),
        cellHeight=height,
        paragraphs=list(paragraphs or []),
    )


def _table(*cells: CellInfo) -> TableInfo:
    return TableInfo(tableId="t0", cells=list(cells))


# ── 서명 칸 안 날짜 ─────────────────────────────────────────────────────────


def test_sign_cell_date_is_replace_slot_when_date_has_own_paragraph():
    t = _table(_cell(0, 0, paragraphs=["위와 같이 신청합니다.", "      년      월      일", "신청인  (인)"], col_span=4))
    slots = detect_placeholder_slots(t)
    assert [s.writeMode for s in slots] == [REPLACE]
    assert SIGN_CELL_DATE in slots[0].evidence
    assert has_notice_exception(slots[0].evidence)


def test_sign_cell_date_blocked_when_date_shares_paragraph_with_sign():
    t = _table(_cell(0, 0, paragraphs=["위와 같이 신청합니다.", "   년   월   일  신청인 (인)"], col_span=4))
    assert detect_placeholder_slots(t) == []


def test_sign_cell_date_blocked_when_two_dates():
    t = _table(_cell(0, 0, paragraphs=["   년   월   일", "   년   월   일", "신청인 (인)"], col_span=4))
    assert detect_placeholder_slots(t) == []


# ── 이름 칸 + 따로 있는 서명 칸 ─────────────────────────────────────────────


def _name_table(sign_in_same_cell: bool):
    sign = "(인)"
    if sign_in_same_cell:
        return _table(_cell(0, 0, "성명"), _cell(0, 1, sign))
    return _table(_cell(0, 0, "성명"), _cell(0, 1, ""), _cell(0, 2, sign))


def test_name_slot_next_to_separate_sign_cell_is_allowed_and_marked():
    t = _name_table(False)
    slots = detect_input_slots([t])
    assert len(slots) == 1
    assert NAME_NEXT_TO_SIGN in slots[0].evidence
    assert name_next_to_sign(t, slots[0]) is not None
    assert slot_block_reason(t, slots[0]) == ""


def test_non_name_label_next_to_sign_cell_stays_blocked():
    t = _table(_cell(0, 0, "비고"), _cell(0, 1, ""), _cell(0, 2, "(인)"))
    assert detect_input_slots([t]) == []


def test_sign_marker_in_same_cell_gives_no_name_slot():
    assert detect_input_slots([_name_table(True)]) == []


def test_notice_exception_only_for_legal_notice_role():
    assert _notice_exception_ok("legal_notice", [NAME_NEXT_TO_SIGN])
    assert _notice_exception_ok("legal_notice", [SIGN_CELL_DATE])
    assert not _notice_exception_ok("legal_notice", ["label_right"])
    assert not _notice_exception_ok("approval_stamp", [SIGN_CELL_DATE])
    assert not _notice_exception_ok("page_marker", [NAME_NEXT_TO_SIGN])


# ── 구분기호 칸 ─────────────────────────────────────────────────────────────


def test_separator_text_keeps_symbol():
    assert separator_text("-", "123-45-67890") == "123-45-67890"
    assert separator_text("~", "2026.01.01 ~ 2026.12.31") == "2026.01.01 ~ 2026.12.31"
    assert separator_text("-", "1234567890") == "123-45-67890"
    assert separator_text("-", "1101111234567") == "110111-1234567"
    assert separator_text("~", "2026.01.01") == "2026.01.01 ~"
    assert separator_text("-", "서울") == "서울 -"


def test_separator_cell_with_left_label_is_slot():
    t = _table(_cell(0, 0, "기간"), _cell(0, 1, "~"))
    slots = detect_separator_slots(t)
    assert [(s.writeMode, s.labelText, s.cellText) for s in slots] == [(SEPARATOR, "기간", "~")]


def test_separator_between_value_cells_is_not_slot():
    t = _table(_cell(0, 0, "기간"), _cell(0, 1, "2026.01.01"), _cell(0, 2, "~"), _cell(0, 3, "2026.12.31"))
    assert detect_separator_slots(t) == []


def test_separator_chain_is_not_slot():
    t = _table(_cell(0, 0, "번호"), _cell(0, 1, "-"), _cell(0, 2, "-"))
    assert detect_separator_slots(t) == []


def test_plan_final_text_for_separator_slot():
    slot = detect_separator_slots(_table(_cell(0, 0, "기간"), _cell(0, 1, "~")))[0]
    assert _final_cell_text(slot, "2026.01.01 ~ 2026.12.31") == "2026.01.01 ~ 2026.12.31"
    assert _final_cell_text(slot, "2026.01.01") == "2026.01.01 ~"


# ── 라벨 길이·라벨 사전 ─────────────────────────────────────────────────────


def test_label_length_excludes_bracket_descriptions():
    assert _label_length("건축주(법인은 법인명과 대표자 성명을 함께 적습니다)") == 3
    assert _label_length("공사개요[해당 항목을 모두 선택해 주십시오]") == 4
    assert _label_length("가" * 21) == 21


def _label_zone(spacer_between: bool):
    rows = [_cell(0, 0, "사업자등록번호", col_span=4)]
    if spacer_between:
        rows.append(_cell(1, 0, "", col_span=4, height=100))
    rows.append(_cell(2 if spacer_between else 1, 0, "", col_span=4))
    return _table(*rows)


def test_known_label_keeps_append_only_when_blank_below_is_past_spacer():
    kept = [s for s in detect_same_cell_slots(_label_zone(True)) if s.labelText == "사업자등록번호"]
    assert [s.writeMode for s in kept] == [APPEND]
    assert "사업자등록번호" not in {s.labelText for s in detect_same_cell_slots(_label_zone(False))}


# ── 서명 문단 불변 ──────────────────────────────────────────────────────────


class _Doc:
    def __init__(self, *cells):
        self.tables = [_table(*cells)]


def test_sign_paragraphs_and_invariance():
    paras = ["위와 같이 신청합니다.", "      년      월      일", "신청인 (인)"]
    before = _Doc(_cell(0, 0, paragraphs=paras, col_span=4))
    assert sign_paragraphs(before.tables[0].cells[0]) == ["신청인 (인)"]
    same = _Doc(_cell(0, 0, paragraphs=["위와 같이 신청합니다.", "2026년 5월 1일", "신청인 (인)"], col_span=4))
    assert sign_paragraph_changes(before, same) == []
    broken = _Doc(_cell(0, 0, paragraphs=["위와 같이 신청합니다.", "2026년 5월 1일", "신청인"], col_span=4))
    assert sign_paragraph_changes(before, broken) == ["t0:r0c0"]
    gone = _Doc()
    gone.tables = [_table()]
    assert sign_paragraph_changes(before, gone) == ["t0:r0c0"]


def test_sign_invariance_ignores_nested_table_concatenation():
    """안쪽 표가 있는 칸의 첫 문단은 안쪽 칸 글자가 이어 붙은 것이라, 안쪽 칸을 써도 서명 문단 변경으로 보면 안 된다."""
    inner = ["소속: ", "발생기관명직인 ", "직인"]
    concat_before = "소속: 발생기관명직인 직인"
    concat_after = "소속: @000 발생기관명직인 직인"
    b = _cell(0, 0, paragraphs=[concat_before, *inner], col_span=2)
    a = _cell(0, 0, paragraphs=[concat_after, "소속: @000 ", "발생기관명직인 ", "직인"], col_span=2)
    b.hasNestedTable = a.hasNestedTable = True
    assert sign_paragraph_changes(_Doc(b), _Doc(a)) == []
    c = _cell(0, 0, paragraphs=[concat_after, "소속: @000 ", "발생기관명직인 "], col_span=2)
    c.hasNestedTable = True
    assert sign_paragraph_changes(_Doc(b), _Doc(c)) == ["t0:r0c0"]
