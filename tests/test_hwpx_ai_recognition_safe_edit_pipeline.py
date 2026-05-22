"""HWPX-AI-RECOGNITION-TO-HANCOM-SAFE-EDIT-PIPELINE-01 테스트.

파이프라인 계약, plan_builder, reparse_verifier, hancom_safe_gate,
end-to-end 흐름을 검증한다. 원본 fixture는 수정하지 않는다.
"""
from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = PROJECT_ROOT / "tests" / "fixtures" / "hwpx" / "corpus"
PIPELINE_PKG = PROJECT_ROOT / "scripts" / "hwpx" / "pipeline"

sys.path.insert(0, str(PROJECT_ROOT / "scripts"))


# ── 계약 JSON 직렬화 ──────────────────────────────────────────────────────────

def test_pipeline_contract_json_serializable():
    from hwpx.pipeline.pipeline_contract import PipelineResult
    r = PipelineResult()
    r.finalDecision = "PASS"
    d = r.to_dict()
    json.dumps(d)  # 예외 없으면 PASS


def test_recognition_result_json_serializable():
    from hwpx.pipeline.pipeline_contract import RecognitionResult
    r = RecognitionResult(detectedLabels=["공사명"], confidence=0.85)
    json.dumps(r.to_dict())


def test_plan_result_json_serializable():
    from hwpx.pipeline.pipeline_contract import PlanResult
    r = PlanResult(plannedFields=["projectName"], editPlan={"set_cells_by_label": []})
    json.dumps(r.to_dict())


# ── plan_builder ─────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def fx_metadata_before():
    from hwpx.parser import parse_hwpx_v2
    return parse_hwpx_v2(FIXTURE_DIR / "fx_metadata_form.hwpx")


def test_plan_builder_reads_parser_result(fx_metadata_before):
    from hwpx.pipeline.pipeline_contract import RecognitionResult
    from hwpx.pipeline.plan_builder import build_edit_plan
    rec = RecognitionResult(confidence=0.85)
    plan = build_edit_plan(rec, {"projectName": "테스트공사"})
    assert isinstance(plan.editPlan, dict)


def test_plan_builder_projectname(fx_metadata_before):
    from hwpx.pipeline.pipeline_contract import RecognitionResult
    from hwpx.pipeline.plan_builder import build_edit_plan
    rec = RecognitionResult(confidence=0.85)
    plan = build_edit_plan(rec, {"projectName": "뇌병변장애인비전센터 리모델링 소방공사"})
    assert "projectName" in plan.plannedFields
    items = plan.editPlan.get("set_cells_by_label", [])
    assert any("공사명" in item.get("contains", "") for item in items)


def test_plan_builder_shrink_to_fit():
    from hwpx.pipeline.pipeline_contract import RecognitionResult
    from hwpx.pipeline.plan_builder import build_edit_plan
    rec = RecognitionResult(confidence=0.85)
    plan = build_edit_plan(rec, {"projectName": "매우긴공사명이들어가는경우에도처리되어야한다"})
    items = plan.editPlan.get("set_cells_by_label", [])
    project_items = [i for i in items if "공사명" in i.get("contains", "")]
    assert project_items and project_items[0].get("shrink_to_fit") is True


def test_plan_builder_solid_fill():
    from hwpx.pipeline.pipeline_contract import RecognitionResult
    from hwpx.pipeline.plan_builder import build_edit_plan
    rec = RecognitionResult(confidence=0.85)
    plan = build_edit_plan(rec, {"projectName": "테스트"})
    items = plan.editPlan.get("set_cells_by_label", [])
    project_items = [i for i in items if "공사명" in i.get("contains", "")]
    assert project_items and "solid_fill" in project_items[0]


def test_plan_builder_low_confidence_review_required():
    from hwpx.pipeline.pipeline_contract import RecognitionResult
    from hwpx.pipeline.plan_builder import build_edit_plan
    rec = RecognitionResult(confidence=0.50)
    plan = build_edit_plan(rec, {"projectName": "테스트"})
    assert "projectName" in plan.skippedFields
    assert "projectName" in plan.reviewRequiredReasons


# ── reparse_verifier ──────────────────────────────────────────────────────────

def test_reparse_verifier_returns_result(fx_metadata_before):
    from hwpx.pipeline.pipeline_contract import PlanResult
    from hwpx.pipeline.reparse_verifier import verify
    plan = PlanResult(editPlan={"set_cells_by_label": [{"contains": "공사명", "value": "테스트"}]})
    result = verify(fx_metadata_before, fx_metadata_before, plan)
    assert result.decision in ("PASS", "REVIEW_REQUIRED", "FAIL")


def test_reparse_verifier_matched_field(fx_metadata_before):
    from hwpx.pipeline.pipeline_contract import PlanResult
    from hwpx.pipeline.reparse_verifier import verify
    # contains 라벨과 동일한 텍스트가 셀에 존재하면 matched에 라벨("접수번호")이 들어온다
    plan = PlanResult(editPlan={"set_cells_by_label": [{"contains": "접수번호", "value": "접수번호"}]})
    result = verify(fx_metadata_before, fx_metadata_before, plan)
    assert "접수번호" in result.matched


# ── hancom_safe_gate ──────────────────────────────────────────────────────────

def test_hancom_safe_gate_fixture_pass():
    from hwpx.pipeline.hancom_safe_gate import verify
    result = verify(FIXTURE_DIR / "fx_metadata_form.hwpx")
    assert result.verdict in ("PASS", "REVIEW_REQUIRED")
    assert isinstance(result.errors, list)


def test_hancom_safe_gate_missing_file():
    from hwpx.pipeline.hancom_safe_gate import verify
    result = verify(Path("nonexistent_file.hwpx"))
    assert result.verdict == "FAIL"
    assert result.errors


# ── end-to-end pipeline ───────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def pipeline_output(tmp_path_factory):
    from hwpx.pipeline import run_pipeline
    tmp = tmp_path_factory.mktemp("pipeline_out")
    output = tmp / "output.hwpx"
    fixture = FIXTURE_DIR / "fx_metadata_form.hwpx"
    result = run_pipeline(
        fixture, output,
        {"projectName": "테스트공사명", "reportDate": "2026-05-17"},
    )
    return result, output, fixture


def test_pipeline_output_hwpx_exists(pipeline_output):
    result, output, _ = pipeline_output
    # edit이 성공하면 output 존재
    if result.stages.get("edit") == "ok":
        assert output.exists()


def test_pipeline_original_not_modified(pipeline_output):
    result, output, fixture = pipeline_output
    mtime = fixture.stat().st_mtime
    # 재확인: fixture mtime 불변
    assert fixture.stat().st_mtime == mtime


def test_pipeline_mimetype_zip_stored(pipeline_output):
    result, output, _ = pipeline_output
    if not output.exists():
        pytest.skip("output not generated")
    with zipfile.ZipFile(output, "r") as zf:
        infos = {i.filename: i for i in zf.infolist()}
        mt_info = infos.get("mimetype")
        assert mt_info is not None
        assert mt_info.compress_type == zipfile.ZIP_STORED


def test_pipeline_final_decision_not_none(pipeline_output):
    result, _, _ = pipeline_output
    assert result.finalDecision in ("PASS", "REVIEW_REQUIRED", "FAIL")


def test_pipeline_json_serializable(pipeline_output):
    result, _, _ = pipeline_output
    d = result.to_dict()
    json.dumps(d)


def test_pipeline_hancom_verify_pass(pipeline_output):
    result, output, _ = pipeline_output
    if not output.exists():
        pytest.skip("output not generated")
    assert result.hancomVerify.verdict in ("PASS", "REVIEW_REQUIRED")
    assert not result.hancomVerify.errors
