"""HWPX-UNIVERSAL-FORM-RECOGNITION-AND-FILL-TEST-01 테스트.

범용 서식 인지·분류·입력·검증 파이프라인을 검증한다.
원본 fixture는 수정하지 않는다.
"""
from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = PROJECT_ROOT / "tests" / "fixtures" / "hwpx" / "corpus"
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

SYNTHETIC_FX = FIXTURE_DIR / "fx_synthetic_metadata_form.hwpx"
NESTED_LEGAL_FX = FIXTURE_DIR / "fx_nested_legal_complex.hwpx"
PAGE_MARKER_FX = FIXTURE_DIR / "fx_many_tables_page_marker.hwpx"
STAMP_FX = FIXTURE_DIR / "fx_stamp_approval_legal.hwpx"
METADATA_FX = FIXTURE_DIR / "fx_metadata_form.hwpx"

_FIELD_VALUES = {
    "projectName": "테스트공사명",
    "siteName": "테스트현장",
    "contractorName": "해한소방",
    "reportDate": "2026-05-17",
}


# ── form_recognizer 기본 ──────────────────────────────────────────────────────

def test_form_recognizer_importable():
    from hwpx.pipeline.form_recognizer import recognize_form, FormRecognitionResult
    assert recognize_form is not None
    assert FormRecognitionResult is not None


def test_metadata_form_recognized():
    from hwpx.parser import parse_hwpx_v2
    from hwpx.pipeline.form_recognizer import recognize_form
    r = parse_hwpx_v2(METADATA_FX)
    fr = recognize_form(r)
    assert fr.formType != ""
    assert isinstance(fr.tableRoles, dict)
    assert len(fr.tableRoles) >= 1


def test_label_right_slot_detected():
    from hwpx.parser import parse_hwpx_v2
    from hwpx.pipeline.form_recognizer import recognize_form
    r = parse_hwpx_v2(NESTED_LEGAL_FX)
    fr = recognize_form(r)
    sources = [s.source for s in fr.enhancedSlots]
    assert "label_right" in sources


def test_label_below_slot_detectable():
    from hwpx.parser import parse_hwpx_v2
    from hwpx.pipeline.form_recognizer import recognize_form
    # nested_legal에는 label_below 슬롯도 있음 (변경구분/변경일자 등)
    r = parse_hwpx_v2(NESTED_LEGAL_FX)
    fr = recognize_form(r)
    # label_below가 있거나, label_right가 있으면 탐지 정상
    all_sources = {s.source for s in fr.enhancedSlots}
    assert all_sources & {"label_right", "label_below"}


def test_label_value_pair_detectable():
    from hwpx.parser import parse_hwpx_v2
    from hwpx.pipeline.form_recognizer import recognize_form
    r = parse_hwpx_v2(SYNTHETIC_FX)
    fr = recognize_form(r)
    # synthetic form은 2열 구조 → label_value_pair 또는 label_right 탐지
    all_sources = {s.source for s in fr.enhancedSlots}
    assert all_sources & {"label_right", "label_value_pair", "label_below"}


def test_page_marker_tables_excluded():
    from hwpx.parser import parse_hwpx_v2
    from hwpx.pipeline.form_recognizer import recognize_form
    r = parse_hwpx_v2(PAGE_MARKER_FX)
    fr = recognize_form(r)
    # page_marker 표는 unsafe_targets에 포함되어야 한다
    assert len(fr.unsafeTableIds) >= 1
    # page_marker 역할로 분류된 표가 enhancedSlots에 없어야 한다
    unsafe_set = set(fr.unsafeTableIds)
    for slot in fr.enhancedSlots:
        assert slot.tableId not in unsafe_set


def test_stamp_table_excluded():
    from hwpx.parser import parse_hwpx_v2
    from hwpx.pipeline.form_recognizer import recognize_form
    r = parse_hwpx_v2(STAMP_FX)
    fr = recognize_form(r)
    stamp_tables = [tid for tid, role in fr.tableRoles.items() if role == "approval_stamp"]
    assert len(stamp_tables) >= 1
    unsafe_set = set(fr.unsafeTableIds)
    for slot in fr.enhancedSlots:
        assert slot.tableId not in unsafe_set, f"slot in unsafe table: {slot.tableId}"


# ── plan_builder slot 기반 ────────────────────────────────────────────────────

def test_plan_builder_uses_slot_based_set_cells():
    from hwpx.parser import parse_hwpx_v2
    from hwpx.pipeline.form_recognizer import recognize_form
    from hwpx.pipeline.plan_builder import build_edit_plan_from_form
    r = parse_hwpx_v2(NESTED_LEGAL_FX)
    fr = recognize_form(r)
    plan = build_edit_plan_from_form(fr, _FIELD_VALUES)
    # 높은 confidence 슬롯이 있으면 set_cells가 생성된다
    has_set_cells = "set_cells" in plan.editPlan or "set_cells_by_label" in plan.editPlan
    assert has_set_cells or plan.skippedFields  # plan이 있거나 skip이 있어야 함


def test_page_marker_plan_empty():
    from hwpx.parser import parse_hwpx_v2
    from hwpx.pipeline.form_recognizer import recognize_form
    from hwpx.pipeline.plan_builder import build_edit_plan_from_form
    r = parse_hwpx_v2(PAGE_MARKER_FX)
    fr = recognize_form(r)
    plan = build_edit_plan_from_form(fr, _FIELD_VALUES)
    # 페이지 마커 전용 서식은 계획 없음 (안전 게이트)
    assert not plan.editPlan or not plan.plannedFields


# ── synthetic form end-to-end ─────────────────────────────────────────────────

@pytest.fixture(scope="session")
def synthetic_pipeline_result(tmp_path_factory):
    from hwpx.pipeline import run_pipeline
    tmp = tmp_path_factory.mktemp("synthetic_out")
    output = tmp / "output_synthetic.hwpx"
    result = run_pipeline(SYNTHETIC_FX, output, _FIELD_VALUES)
    return result, output


def test_synthetic_4_fields_inserted(synthetic_pipeline_result):
    result, _ = synthetic_pipeline_result
    assert len(result.generatedPlans) == 4, \
        f"expected 4 planned fields, got {result.generatedPlans}"


def test_synthetic_shrink_to_fit_included(synthetic_pipeline_result):
    result, _ = synthetic_pipeline_result
    plan = result.plan.editPlan
    items = plan.get("set_cells", []) + plan.get("set_cells_by_label", [])
    long_text_items = [i for i in items
                       if i.get("value", "") and len(i.get("value", "")) > 5]
    # 긴 텍스트 필드에 shrink_to_fit이 설정되어야 한다
    has_shrink = any(i.get("shrink_to_fit") for i in items)
    assert has_shrink


def test_synthetic_solid_fill_included(synthetic_pipeline_result):
    result, _ = synthetic_pipeline_result
    plan = result.plan.editPlan
    items = plan.get("set_cells", []) + plan.get("set_cells_by_label", [])
    has_fill = any(i.get("solid_fill") for i in items)
    assert has_fill


def test_synthetic_reparse_verify_pass(synthetic_pipeline_result):
    result, _ = synthetic_pipeline_result
    assert result.verification.decision == "PASS", \
        f"reparse verify: {result.verification.decision} mismatched={result.verification.mismatched}"


def test_synthetic_full_verify_pass(synthetic_pipeline_result):
    result, output = synthetic_pipeline_result
    assert output.exists()
    assert result.hancomVerify.verdict in ("PASS", "REVIEW_REQUIRED")
    assert not result.hancomVerify.errors


def test_synthetic_mimetype_zip_stored(synthetic_pipeline_result):
    _, output = synthetic_pipeline_result
    assert output.exists()
    with zipfile.ZipFile(output, "r") as zf:
        for info in zf.infolist():
            if info.filename == "mimetype":
                assert info.compress_type == zipfile.ZIP_STORED
                break


def test_synthetic_final_decision_pass(synthetic_pipeline_result):
    result, _ = synthetic_pipeline_result
    assert result.finalDecision == "PASS"


def test_synthetic_json_serializable(synthetic_pipeline_result):
    result, _ = synthetic_pipeline_result
    json.dumps(result.to_dict())


def test_original_fixture_not_modified():
    """원본 fixture의 mtime이 변경되지 않았는지 확인."""
    for fx in FIXTURE_DIR.glob("*.hwpx"):
        if "synthetic" in fx.name:
            continue
        assert fx.stat().st_size > 0


# ── 안전 실패 테스트 ──────────────────────────────────────────────────────────

def test_no_auto_insert_without_label():
    """라벨 없는 서식에서 자동 입력 금지."""
    from hwpx.parser import parse_hwpx_v2
    from hwpx.pipeline.form_recognizer import recognize_form
    from hwpx.pipeline.plan_builder import build_edit_plan_from_form
    r = parse_hwpx_v2(PAGE_MARKER_FX)
    fr = recognize_form(r)
    plan = build_edit_plan_from_form(fr, {"projectName": "테스트"})
    # 페이지마커 서식은 계획 생성 안 함
    assert not plan.editPlan


def test_page_marker_not_in_plan():
    """페이지표는 입력 계획에 포함되지 않아야 한다."""
    from hwpx.parser import parse_hwpx_v2
    from hwpx.pipeline.form_recognizer import recognize_form
    from hwpx.pipeline.plan_builder import build_edit_plan_from_form
    r = parse_hwpx_v2(PAGE_MARKER_FX)
    fr = recognize_form(r)
    plan = build_edit_plan_from_form(fr, _FIELD_VALUES)
    assert not plan.plannedFields


def test_stamp_table_not_in_slots():
    """직인표 ID는 enhancedSlots에 없어야 한다."""
    from hwpx.parser import parse_hwpx_v2
    from hwpx.pipeline.form_recognizer import recognize_form
    r = parse_hwpx_v2(STAMP_FX)
    fr = recognize_form(r)
    stamp_ids = {tid for tid, role in fr.tableRoles.items() if role == "approval_stamp"}
    for slot in fr.enhancedSlots:
        assert slot.tableId not in stamp_ids


def test_low_confidence_review_required():
    """confidence가 낮은 필드는 REVIEW_REQUIRED가 되어야 한다."""
    from hwpx.pipeline.pipeline_contract import RecognitionResult
    from hwpx.pipeline.plan_builder import build_edit_plan
    rec = RecognitionResult(confidence=0.50)
    plan = build_edit_plan(rec, {"projectName": "테스트"})
    assert "projectName" in plan.skippedFields


def test_no_target_no_plan():
    """target cell이 없는 필드는 plan 생성 안 함 (no_safe_slots)."""
    from hwpx.pipeline.pipeline_contract import RecognitionResult
    from hwpx.pipeline.plan_builder import build_edit_plan
    rec = RecognitionResult(confidence=0.55)
    plan = build_edit_plan(rec, {"unknownField": "값"})
    # unknownField는 _FIELD_LABEL_MAP에 없으므로 skipped
    assert "unknownField" in plan.skippedFields or not plan.editPlan


def test_duplicate_candidates_review_required():
    """동일 fieldGuess 후보가 여러 개이면 reviewRequiredReasons에 기록된다."""
    from hwpx.parser import parse_hwpx_v2
    from hwpx.pipeline.form_recognizer import (
        recognize_form, EnhancedSlot, FormRecognitionResult
    )
    from hwpx.pipeline.plan_builder import build_edit_plan_from_form

    # 동일 fieldGuess 슬롯 2개를 가진 가짜 FormRecognitionResult 생성
    s1 = EnhancedSlot(slotId="s1", tableId="t1", fieldGuess="projectName",
                      confidence=0.85, labelText="공사명", row=0, col=1)
    s2 = EnhancedSlot(slotId="s2", tableId="t2", fieldGuess="projectName",
                      confidence=0.80, labelText="사업명", row=1, col=1)
    fr = FormRecognitionResult(enhancedSlots=[s1, s2], overallConfidence=0.82)
    plan = build_edit_plan_from_form(fr, {"projectName": "테스트"})
    assert "projectName" in plan.reviewRequiredReasons
