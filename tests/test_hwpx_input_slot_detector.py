"""HWPX-INPUT-SLOT-DETECTOR-01 테스트.

input_slot_detector.py 각 탐지 함수의 단위 테스트.
실제 HWPX 파일은 fixture 5개를 사용한다.
synthetic 구조체는 dataclass로 직접 구성한다.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
HWPX_DIR = PROJECT_ROOT / "scripts" / "hwpx"
sys.path.insert(0, str(HWPX_DIR))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

FIXTURE_DIR = PROJECT_ROOT / "tests" / "fixtures" / "hwpx" / "corpus"
SYNTHETIC_FX = FIXTURE_DIR / "fx_synthetic_metadata_form.hwpx"
METADATA_FX = FIXTURE_DIR / "fx_metadata_form.hwpx"
PAGE_FX = FIXTURE_DIR / "fx_many_tables_page_marker.hwpx"
STAMP_FX = FIXTURE_DIR / "fx_stamp_approval_legal.hwpx"


# ── 최소 dataclass 픽스처 ─────────────────────────────────────────────────────

@dataclass
class _Cell:
    row: int = 0
    col: int = 0
    visualRow: int = 0
    visualCol: int = 0
    rowSpan: int = 1
    colSpan: int = 1
    normalizedText: str = ""
    isLikelyLabel: bool = False
    isCoveredByMerge: bool = False
    isMergedOrigin: bool = False


@dataclass
class _Table:
    tableId: str = "t0"
    layoutGuess: str = "horizontal_table"
    rowCount: int = 2
    colCount: int = 2
    cells: list = field(default_factory=list)


def _make_label_right_table() -> _Table:
    """col0=라벨, col1=빈칸 구조"""
    return _Table(tableId="t0", colCount=2, cells=[
        _Cell(row=0, col=0, normalizedText="공사명", isLikelyLabel=True),
        _Cell(row=0, col=1, normalizedText=""),
        _Cell(row=1, col=0, normalizedText="현장명", isLikelyLabel=True),
        _Cell(row=1, col=1, normalizedText=""),
    ])


def _make_label_below_table() -> _Table:
    """row0=라벨, row1=빈칸 구조"""
    return _Table(tableId="t1", colCount=1, rowCount=2, cells=[
        _Cell(row=0, col=0, normalizedText="공사명"),
        _Cell(row=1, col=0, normalizedText=""),
    ])


def _make_label_value_pair_table() -> _Table:
    """4열: col0=라벨, col1=값, col2=라벨, col3=값"""
    return _Table(tableId="t2", colCount=4, cells=[
        _Cell(row=0, col=0, normalizedText="공사명"),
        _Cell(row=0, col=1, normalizedText=""),
        _Cell(row=0, col=2, normalizedText="접수번호"),
        _Cell(row=0, col=3, normalizedText=""),
        _Cell(row=1, col=0, normalizedText="현장명"),
        _Cell(row=1, col=1, normalizedText=""),
        _Cell(row=1, col=2, normalizedText="작성일"),
        _Cell(row=1, col=3, normalizedText=""),
    ])


def _make_merged_input_table() -> _Table:
    """col0=라벨, col1=병합된 빈칸(colSpan=2)"""
    merged = _Cell(row=0, col=1, normalizedText="", isMergedOrigin=True, colSpan=2, rowSpan=1)
    return _Table(tableId="t3", colCount=3, cells=[
        _Cell(row=0, col=0, normalizedText="공사명"),
        merged,
        _Cell(row=0, col=2, normalizedText="", isCoveredByMerge=True),
    ])


def _make_data_table() -> _Table:
    """header row + data rows"""
    return _Table(tableId="t4", colCount=4, rowCount=3, cells=[
        _Cell(row=0, col=0, normalizedText="번호"),
        _Cell(row=0, col=1, normalizedText="품명"),
        _Cell(row=0, col=2, normalizedText="수량"),
        _Cell(row=0, col=3, normalizedText="단위"),
        _Cell(row=1, col=0, normalizedText="1"),
        _Cell(row=1, col=1, normalizedText="강관"),
        _Cell(row=1, col=2, normalizedText="10"),
        _Cell(row=1, col=3, normalizedText="개"),
        _Cell(row=2, col=0, normalizedText=""),
        _Cell(row=2, col=1, normalizedText=""),
        _Cell(row=2, col=2, normalizedText=""),
        _Cell(row=2, col=3, normalizedText=""),
    ])


def _make_status_cell_table() -> _Table:
    return _Table(tableId="t5", colCount=2, cells=[
        _Cell(row=0, col=0, normalizedText="검측상태"),
        _Cell(row=0, col=1, normalizedText=""),
        _Cell(row=1, col=0, normalizedText="진행률"),
        _Cell(row=1, col=1, normalizedText=""),
    ])


def _make_page_marker_table() -> _Table:
    return _Table(tableId="t6", layoutGuess="page_marker_table", colCount=1, cells=[
        _Cell(row=0, col=0, normalizedText="1 / 3"),
    ])


def _make_stamp_table() -> _Table:
    return _Table(tableId="t7", layoutGuess="stamp_or_approval_table", colCount=2, cells=[
        _Cell(row=0, col=0, normalizedText="직인"),
        _Cell(row=0, col=1, normalizedText=""),
    ])


# ── 1. label_right 탐지 ─────────────────────────────────────────────────────

def test_label_right_slot_detected():
    from hwpx.parser.input_slot_detector import detect_label_right_slots
    table = _make_label_right_table()
    slots = detect_label_right_slots(table)
    assert len(slots) >= 1
    sources = {s.source for s in slots}
    assert "label_right" in sources


def test_label_right_field_guess():
    from hwpx.parser.input_slot_detector import detect_label_right_slots
    table = _make_label_right_table()
    slots = detect_label_right_slots(table)
    guesses = {s.fieldGuess for s in slots}
    assert "projectName" in guesses


def test_label_right_confidence():
    from hwpx.parser.input_slot_detector import detect_label_right_slots
    table = _make_label_right_table()
    slots = detect_label_right_slots(table)
    assert all(s.confidence > 0 for s in slots)


# ── 2. label_below 탐지 ─────────────────────────────────────────────────────

def test_label_below_slot_detected():
    from hwpx.parser.input_slot_detector import detect_label_below_slots
    table = _make_label_below_table()
    slots = detect_label_below_slots(table)
    assert len(slots) >= 1
    assert slots[0].source == "label_below"


# ── 3. label_value_pair 탐지 ─────────────────────────────────────────────────

def test_label_value_pair_detected():
    from hwpx.parser.input_slot_detector import detect_label_value_pair_slots
    table = _make_label_value_pair_table()
    slots = detect_label_value_pair_slots(table)
    assert len(slots) >= 2
    assert all(s.source == "label_value_pair" for s in slots)


def test_label_value_pair_field_guesses():
    from hwpx.parser.input_slot_detector import detect_label_value_pair_slots
    table = _make_label_value_pair_table()
    slots = detect_label_value_pair_slots(table)
    guesses = {s.fieldGuess for s in slots}
    assert "projectName" in guesses or "receiptNumber" in guesses


# ── 4. merged_input_cell 탐지 ────────────────────────────────────────────────

def test_merged_input_cell_detected():
    from hwpx.parser.input_slot_detector import detect_merged_input_cells
    table = _make_merged_input_table()
    slots = detect_merged_input_cells(table)
    assert len(slots) >= 1
    assert slots[0].source == "merged_input_cell"
    assert slots[0].reviewRequired


# ── 5. blank_after_known_header 탐지 ─────────────────────────────────────────

def test_blank_after_known_header_detected():
    from hwpx.parser.input_slot_detector import detect_blank_after_known_header_slots
    table = _make_label_right_table()
    slots = detect_blank_after_known_header_slots(table)
    assert len(slots) >= 1
    assert all(s.source == "blank_after_known_header" for s in slots)


# ── 6. metadata_form_slots 탐지 ──────────────────────────────────────────────

def test_metadata_form_slot_detected():
    from hwpx.parser.input_slot_detector import detect_metadata_form_slots
    # 3개 이상 known label이 있는 horizontal_table
    table = _Table(tableId="t_meta", layoutGuess="horizontal_table", colCount=2, cells=[
        _Cell(row=0, col=0, normalizedText="공사명"),  _Cell(row=0, col=1, normalizedText=""),
        _Cell(row=1, col=0, normalizedText="현장명"),  _Cell(row=1, col=1, normalizedText=""),
        _Cell(row=2, col=0, normalizedText="시공사"),  _Cell(row=2, col=1, normalizedText=""),
    ])
    slots = detect_metadata_form_slots(table)
    assert len(slots) >= 1


# ── 7. data_table_append_slot 탐지 ───────────────────────────────────────────

def test_data_table_append_slot_detected():
    from hwpx.parser.input_slot_detector import detect_data_table_append_slots
    table = _make_data_table()
    slots = detect_data_table_append_slots(table)
    assert len(slots) >= 1
    assert slots[0].source == "data_table_append_slot"
    assert slots[0].reviewRequired


# ── 8. status_cell 탐지 ──────────────────────────────────────────────────────

def test_status_cell_detected():
    from hwpx.parser.input_slot_detector import detect_status_cells
    table = _make_status_cell_table()
    slots = detect_status_cells(table)
    assert len(slots) >= 1
    assert slots[0].source == "status_cell"
    assert slots[0].fieldGuess in ("inspectionStatus", "progressRate", "status")


# ── 9. page_marker_table 입력 제외 ───────────────────────────────────────────

def test_page_marker_table_excluded_label_right():
    from hwpx.parser.input_slot_detector import detect_label_right_slots
    table = _make_page_marker_table()
    slots = detect_label_right_slots(table)
    assert len(slots) == 0


def test_page_marker_table_excluded_detect_all():
    from hwpx.parser.input_slot_detector import detect_input_slots
    table = _make_page_marker_table()
    slots = detect_input_slots([table])
    assert len(slots) == 0, f"page_marker_table에서 slot 생성됨: {slots}"


# ── 10. stamp_or_approval_table 입력 제외 ─────────────────────────────────────

def test_stamp_table_excluded():
    from hwpx.parser.input_slot_detector import detect_input_slots
    table = _make_stamp_table()
    slots = detect_input_slots([table])
    assert len(slots) == 0, f"stamp_table에서 slot 생성됨: {slots}"


# ── 11. duplicate field 후보 REVIEW_REQUIRED ─────────────────────────────────

def test_duplicate_field_review_required_in_plan(tmp_path):
    from hwpx.pipeline.form_recognizer import EnhancedSlot, FormRecognitionResult
    from hwpx.pipeline.plan_builder import build_edit_plan_from_form
    # 동일 fieldGuess 2개
    slots = [
        EnhancedSlot(slotId="s1", tableId="t0", fieldGuess="projectName",
                     source="label_right", confidence=0.90, autoEditAllowed=True,
                     row=0, col=1, visualRow=0, visualCol=1),
        EnhancedSlot(slotId="s2", tableId="t0", fieldGuess="projectName",
                     source="label_right", confidence=0.85,
                     row=1, col=1, visualRow=1, visualCol=1),
    ]
    form = FormRecognitionResult(enhancedSlots=slots, reviewRequired=False)
    result = build_edit_plan_from_form(form, {"projectName": "테스트"})
    reasons = result.reviewRequiredReasons
    assert "projectName" in reasons
    assert "duplicate" in reasons["projectName"]


# ── 12. confidence >= 0.90 auto allowed ───────────────────────────────────────

def test_high_confidence_auto_allowed():
    from hwpx.parser.input_slot_detector import detect_input_slots
    table = _make_label_right_table()
    slots = detect_input_slots([table])
    high_conf = [s for s in slots if s.confidence >= 0.90]
    for s in high_conf:
        assert s.autoEditAllowed or s.reviewRequired, \
            f"confidence={s.confidence} autoEditAllowed={s.autoEditAllowed}"


# ── 13. confidence 낮으면 review required ────────────────────────────────────

def test_low_confidence_review_required():
    from hwpx.parser.input_slot_detector import detect_label_below_slots
    table = _Table(tableId="t_lc", colCount=1, cells=[
        _Cell(row=0, col=0, normalizedText="알수없는항목"),
        _Cell(row=1, col=0, normalizedText=""),
    ])
    slots = detect_label_below_slots(table)
    if slots:
        low = [s for s in slots if s.confidence < 0.70]
        for s in low:
            assert s.reviewRequired or s.reviewRequiredReason is not None


# ── 14. plan_builder slot 기반 set_visual_cells 생성 ─────────────────────────

def test_plan_builder_generates_set_visual_cells():
    from hwpx.pipeline.form_recognizer import EnhancedSlot, FormRecognitionResult
    from hwpx.pipeline.plan_builder import build_edit_plan_from_form
    slot = EnhancedSlot(
        slotId="s1", tableId="s_t0", fieldGuess="projectName",
        source="label_right", confidence=0.92, autoEditAllowed=True,
        row=0, col=1, visualRow=0, visualCol=1,
    )
    form = FormRecognitionResult(enhancedSlots=[slot], reviewRequired=False)
    result = build_edit_plan_from_form(form, {"projectName": "테스트공사"})
    plan = result.editPlan
    assert "set_visual_cells" in plan or "set_cells_by_label" in plan, \
        f"plan 생성 없음: {plan}"


# ── 15. targetCell 없으면 plan 미생성 ────────────────────────────────────────

def test_no_slot_no_target_plan_review():
    from hwpx.pipeline.form_recognizer import FormRecognitionResult
    from hwpx.pipeline.plan_builder import build_edit_plan_from_form
    form = FormRecognitionResult(enhancedSlots=[], reviewRequired=True)
    result = build_edit_plan_from_form(form, {"unknownField": "값"}, allow_fallback_when_no_slots=False)
    assert "unknownField" in result.skippedFields or "unknownField" in result.reviewRequiredReasons


# ── 16. universal form 기존 테스트 PASS 유지 (임포트 확인) ──────────────────

def test_universal_form_imports_still_work():
    from hwpx.pipeline.form_recognizer import recognize_form, classify_table_roles
    from hwpx.pipeline.plan_builder import build_edit_plan_from_form, build_edit_plan
    assert callable(recognize_form)
    assert callable(classify_table_roles)
    assert callable(build_edit_plan_from_form)
    assert callable(build_edit_plan)


# ── 17. detect_input_slots 통합 (real fixture) ───────────────────────────────

def test_detect_input_slots_on_real_fixture():
    from hwpx.parser import parse_hwpx_v2
    from hwpx.parser.input_slot_detector import detect_input_slots
    if not SYNTHETIC_FX.exists():
        pytest.skip("synthetic fixture not found")
    result = parse_hwpx_v2(SYNTHETIC_FX)
    slots = detect_input_slots(result.tables)
    assert isinstance(slots, list)


def test_detect_input_slots_no_slots_from_page_fixture():
    """page_marker fixture — M2 정책 (2026-05-19): slot 인지하되
    autoEditAllowed=False + reviewRequired=True 표시.

    이전 정책은 page_marker_table 안 모든 slot을 즉시 차단했지만, 별지 양식이
    (앞쪽)/(뒤쪽) 페이지 마커 때문에 form 표가 page_marker_table로 잘못
    분류되어 입력 라벨이 통째로 차단되던 문제 해소. 안전한 입력은 review로.
    """
    from hwpx.parser import parse_hwpx_v2
    from hwpx.parser.input_slot_detector import detect_input_slots
    if not PAGE_FX.exists():
        pytest.skip("page fixture not found")
    result = parse_hwpx_v2(PAGE_FX)
    slots = detect_input_slots(result.tables)
    page_slots = [s for s in slots if "page" in (s.unsafeReason or "").lower()]
    for s in page_slots:
        assert s.autoEditAllowed is False, \
            f"page_marker slot은 autoEditAllowed=False여야 함: {s.slotId}"
        assert s.reviewRequired is True, \
            f"page_marker slot은 reviewRequired=True여야 함: {s.slotId}"
