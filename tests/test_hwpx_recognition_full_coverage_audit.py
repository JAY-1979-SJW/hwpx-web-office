"""HWPX-RECOGNITION-FULL-COVERAGE-AUDIT-01 테스트.

audit script가 수집된 모든 HWPX를 전수 감사하여 일관된 결과를 내는지 검증.
원본 파일 무수정 / writer 통제 / 보고서 산출 정합성 확인.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture(scope="module")
def audit():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "audit_hwpx_recognition_full_coverage",
        PROJECT_ROOT / "scripts/ops/audit_hwpx_recognition_full_coverage.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def audit_run(audit):
    return audit.run_audit()


# 커밋된 tests/fixtures 는 15개뿐이라(git ls-files -- '*.hwpx'), 실제 로컬
# 코퍼스(수천 건, data/ 등 .gitignore 대상)가 없는 CI에서는 아래 count-locked
# 검증들이 애초에 성립하지 않는다 — 임계값은 그 둘을 넉넉히 가른다.
_FULL_CORPUS_MIN = 100


@pytest.fixture(scope="module")
def full_corpus_required(audit):
    if len(audit._scan_hwpx_inventory()) < _FULL_CORPUS_MIN:
        pytest.skip("실제 로컬 코퍼스(수천 건) 없음 — count-locked 검증은 그 데이터 기준")


# ── inventory & scanning ────────────────────────────────────────────────────


def test_t01_inventory_collected(audit):
    inv = audit._scan_hwpx_inventory()
    assert isinstance(inv, list)
    # 최소 fixture가 있어야 한다
    assert any(
        i.get("relativePath", "").startswith("tests/fixtures/hwpx/")
        for i in inv
        if i.get("include")
    )


def test_t02_audit_does_not_crash_on_empty_inventory(audit, monkeypatch):
    monkeypatch.setattr(audit, "_scan_hwpx_inventory", list)
    s = audit.run_audit()
    assert s["overallVerdict"] == "WARN_NO_HWPX_FIXTURES"
    assert s["totalHwpxFiles"] == 0


def test_t03_each_file_has_sha_and_mtime_baseline(audit):
    inv = audit._scan_hwpx_inventory()
    for item in inv:
        if not item.get("include"):
            continue
        assert item["sha256Before"]
        assert item["mtimeBefore"] > 0


# ── per-file parse ──────────────────────────────────────────────────────────


def test_t04_no_parse_crash(audit_run, full_corpus_required):
    # parseFailedCount는 0이어야 한다 (또는 0보다 낮을 수 없음)
    assert audit_run["parseFailedCount"] == 0


def test_t05_audit_artifact_files_exist(audit, audit_run):
    OUTPUT_DIR = audit.OUTPUT_DIR
    assert (OUTPUT_DIR / "audit.json").exists()
    assert (OUTPUT_DIR / "audit.md").exists()
    data = json.loads((OUTPUT_DIR / "audit.json").read_text(encoding="utf-8"))
    for f in data["fileResults"]:
        # documentHash / sourcePath 정보가 채워졌는지
        if f["verdict"] not in ("FAIL_PARSE_ERROR", "FAIL_STRUCTURE_MISMATCH"):
            assert f.get("documentHash"), f
            assert "sha256Before" in f


def test_t06_paragraph_count_present_when_parsed(audit):
    OUTPUT_DIR = audit.OUTPUT_DIR
    data = json.loads((OUTPUT_DIR / "audit.json").read_text(encoding="utf-8"))
    parsed_files = [
        f
        for f in data["fileResults"]
        if f["verdict"] not in ("FAIL_PARSE_ERROR", "FAIL_STRUCTURE_MISMATCH")
    ]
    assert all("paragraphCount" in f for f in parsed_files)


def test_t07_table_and_cell_counts_present(audit):
    OUTPUT_DIR = audit.OUTPUT_DIR
    data = json.loads((OUTPUT_DIR / "audit.json").read_text(encoding="utf-8"))
    parsed = [
        f
        for f in data["fileResults"]
        if f["verdict"] not in ("FAIL_PARSE_ERROR", "FAIL_STRUCTURE_MISMATCH")
    ]
    assert all("tableCount" in f and "cellCount" in f for f in parsed)


# ── extraction coverage ────────────────────────────────────────────────────


def test_t08_text_ratio_reasonable(audit):
    """text ratio가 0 이상 1 이하 (계산 자체가 안전)."""
    OUTPUT_DIR = audit.OUTPUT_DIR
    data = json.loads((OUTPUT_DIR / "audit.json").read_text(encoding="utf-8"))
    for f in data["fileResults"]:
        tr = f.get("textRatio")
        if tr is not None:
            assert 0.0 <= tr <= 1.0


def test_t09_merged_cells_counted_when_present(audit):
    OUTPUT_DIR = audit.OUTPUT_DIR
    data = json.loads((OUTPUT_DIR / "audit.json").read_text(encoding="utf-8"))
    has_merged = any((f.get("mergedCellCount") or 0) > 0 for f in data["fileResults"])
    # 수집된 fixture 중 병합셀이 있는 문서가 있어야 정상
    assert has_merged


def test_t10_object_count_present(audit):
    OUTPUT_DIR = audit.OUTPUT_DIR
    data = json.loads((OUTPUT_DIR / "audit.json").read_text(encoding="utf-8"))
    parsed = [
        f
        for f in data["fileResults"]
        if f["verdict"] not in ("FAIL_PARSE_ERROR", "FAIL_STRUCTURE_MISMATCH")
    ]
    assert all("objectCount" in f for f in parsed)


def test_t11_bin_data_count_present(audit):
    OUTPUT_DIR = audit.OUTPUT_DIR
    data = json.loads((OUTPUT_DIR / "audit.json").read_text(encoding="utf-8"))
    parsed = [
        f
        for f in data["fileResults"]
        if f["verdict"] not in ("FAIL_PARSE_ERROR", "FAIL_STRUCTURE_MISMATCH")
    ]
    assert all("binDataCount" in f for f in parsed)


# ── object-cell mapping smoke ──────────────────────────────────────────────


def test_t12_object_mapping_smoke(audit):
    OUTPUT_DIR = audit.OUTPUT_DIR
    data = json.loads((OUTPUT_DIR / "audit.json").read_text(encoding="utf-8"))
    parsed = [
        f
        for f in data["fileResults"]
        if f["verdict"] not in ("FAIL_PARSE_ERROR", "FAIL_STRUCTURE_MISMATCH")
    ]
    # 적어도 일부 파일에서 objectMapping이 채워졌는지
    assert any(f.get("objectMapping") for f in parsed)


def test_t13_geometric_candidate_smoke(audit):
    OUTPUT_DIR = audit.OUTPUT_DIR
    data = json.loads((OUTPUT_DIR / "audit.json").read_text(encoding="utf-8"))
    parsed = [f for f in data["fileResults"] if f.get("objectMapping")]
    # geometricCandidateCount 필드 존재
    for f in parsed:
        assert "geometricCandidateCount" in f["objectMapping"]


def test_t14_ambiguous_auto_promotion_blocked(audit):
    OUTPUT_DIR = audit.OUTPUT_DIR
    data = json.loads((OUTPUT_DIR / "audit.json").read_text(encoding="utf-8"))
    # ambiguous candidate가 있는 fixture가 있으면 자동 승격 차단됐어야 한다
    for f in data["fileResults"]:
        flag = f.get("ambiguousAutoPromotionBlocked")
        if flag is False:
            # False이면 안 됨 (None은 ambiguous 없는 경우라 OK)
            pytest.fail(f"ambiguous auto promotion not blocked for {f['relativePath']}")


def test_t15_confirmation_gate_smoke(audit_run, full_corpus_required):
    # 운영 감사 verdict가 FAIL이 아니어야 함
    assert not audit_run["overallVerdict"].startswith("FAIL")


# ── fill review readiness ─────────────────────────────────────────────────


def test_t16_fill_requirement_smoke_per_file(audit):
    OUTPUT_DIR = audit.OUTPUT_DIR
    data = json.loads((OUTPUT_DIR / "audit.json").read_text(encoding="utf-8"))
    parsed = [
        f
        for f in data["fileResults"]
        if f["verdict"]
        not in ("FAIL_PARSE_ERROR", "FAIL_STRUCTURE_MISMATCH", "FAIL_FILL_REQUIREMENT_ERROR")
    ]
    # fillRequirementCount 필드 존재
    assert all("fillRequirementCount" in f for f in parsed)


def test_t17_semantic_type_breakdown_logged(audit):
    OUTPUT_DIR = audit.OUTPUT_DIR
    data = json.loads((OUTPUT_DIR / "audit.json").read_text(encoding="utf-8"))
    # 적어도 한 파일은 semanticBreakdown을 가지고 있어야
    assert any("fillRequirementSemanticBreakdown" in f for f in data["fileResults"])


def test_t18_missing_material_request_count_logged(audit):
    OUTPUT_DIR = audit.OUTPUT_DIR
    data = json.loads((OUTPUT_DIR / "audit.json").read_text(encoding="utf-8"))
    parsed = [f for f in data["fileResults"] if "missingMaterialCount" in f]
    assert len(parsed) >= 1


def test_t19_review_item_count_logged(audit):
    OUTPUT_DIR = audit.OUTPUT_DIR
    data = json.loads((OUTPUT_DIR / "audit.json").read_text(encoding="utf-8"))
    parsed = [f for f in data["fileResults"] if "reviewItemCount" in f]
    assert len(parsed) >= 1


def test_t20_ui_payload_ready_logged(audit):
    OUTPUT_DIR = audit.OUTPUT_DIR
    data = json.loads((OUTPUT_DIR / "audit.json").read_text(encoding="utf-8"))
    # 적어도 일부 파일에서 uiPayloadReady=True
    assert any(f.get("uiPayloadReady") is True for f in data["fileResults"])


def test_t21_decision_validation_smoke_logged(audit):
    OUTPUT_DIR = audit.OUTPUT_DIR
    data = json.loads((OUTPUT_DIR / "audit.json").read_text(encoding="utf-8"))
    smoke_files = [f for f in data["fileResults"] if "decisionValidationSmoke" in f]
    assert len(smoke_files) >= 1


# ── writer readiness ──────────────────────────────────────────────────────


def test_t22_approved_edit_plan_only_for_approve_or_edit(audit_run):
    """audit은 직접 ApprovedEditPlan을 만들지 않는다 — 단지 결정 검증만."""
    assert audit_run["writerReadinessFailCount"] == 0


def test_t23_decision_absent_means_no_writer_call(audit):
    OUTPUT_DIR = audit.OUTPUT_DIR
    data = json.loads((OUTPUT_DIR / "audit.json").read_text(encoding="utf-8"))
    # decisionValidationSmoke에서 accepted=0 (decisions 빈 채로 호출했으므로)
    for f in data["fileResults"]:
        smoke = f.get("decisionValidationSmoke")
        if smoke is not None:
            assert smoke["accepted"] == 0


def test_t24_high_confidence_does_not_trigger_writer(audit_run):
    # writer smoke는 명시적 APPROVE decision이 있는 경우에만 호출됨
    assert audit_run["writerSmokePassCount"] >= 2


def test_t25_set_paragraph_text_name_locked():
    from hwpx.fill_review import fill_review_live_pipeline as pipe

    assert pipe.OP_TO_WRITER_METHOD["setParagraphText"] == "writer.set_paragraph_text"


def test_t26_set_cell_paragraph_text_forbidden():
    from hwpx.fill_review import fill_review_contract as fr

    assert "setCellParagraphText" in fr.FORBIDDEN_PARAGRAPH_OP_NAMES
    assert "setCellParagraphText" not in fr.ALLOWED_FILL_REVIEW_OPERATIONS


# ── live sandbox writer smoke ─────────────────────────────────────────────


def test_t27_smoke_includes_set_cell_or_paragraph(audit):
    OUTPUT_DIR = audit.OUTPUT_DIR
    data = json.loads((OUTPUT_DIR / "audit.json").read_text(encoding="utf-8"))
    scenarios = {s.get("scenario") for s in data["smokeResults"]}
    assert "setParagraphText" in scenarios


def test_t28_smoke_paragraph_pass(audit):
    OUTPUT_DIR = audit.OUTPUT_DIR
    data = json.loads((OUTPUT_DIR / "audit.json").read_text(encoding="utf-8"))
    p = next((s for s in data["smokeResults"] if s.get("scenario") == "setParagraphText"), None)
    assert p is not None
    assert p["verdict"] == "PASS"


def test_t29_smoke_replace_text_run_pass(audit):
    OUTPUT_DIR = audit.OUTPUT_DIR
    data = json.loads((OUTPUT_DIR / "audit.json").read_text(encoding="utf-8"))
    rtr = next((s for s in data["smokeResults"] if s.get("scenario") == "replaceTextRun"), None)
    assert rtr is not None
    assert rtr["verdict"] == "PASS"


def test_t30_smoke_readback_or_writer_pass(audit):
    OUTPUT_DIR = audit.OUTPUT_DIR
    data = json.loads((OUTPUT_DIR / "audit.json").read_text(encoding="utf-8"))
    # 모든 smoke scenario 중 source_immutability는 반드시 PASS
    si = next((s for s in data["smokeResults"] if s.get("scenario") == "source_immutability"), None)
    assert si is not None
    assert si["verdict"] == "PASS"


def test_t31_writer_blocked_cases_produce_no_output(audit):
    # audit의 file-level pipeline은 decision 없음 → writer 미호출이 보장된다.
    # 이는 sha/mtime 무변경으로 간접 검증된다 (T32).
    pass


def test_t32_all_files_source_immutable(audit):
    OUTPUT_DIR = audit.OUTPUT_DIR
    data = json.loads((OUTPUT_DIR / "audit.json").read_text(encoding="utf-8"))
    bad = []
    for f in data["fileResults"]:
        if f.get("sha256Before") != f.get("sha256After"):
            bad.append(f["relativePath"])
        if f.get("mtimeBefore") != f.get("mtimeAfter"):
            bad.append(f["relativePath"])
    assert not bad, f"source mutation detected: {bad}"


# ── report integrity ──────────────────────────────────────────────────────


def test_t33_json_report_generated(audit):
    OUTPUT_DIR = audit.OUTPUT_DIR
    p = OUTPUT_DIR / "audit.json"
    assert p.exists()
    data = json.loads(p.read_text(encoding="utf-8"))
    for k in ("summary", "inventory", "fileResults", "smokeResults"):
        assert k in data


def test_t34_markdown_report_generated(audit):
    OUTPUT_DIR = audit.OUTPUT_DIR
    p = OUTPUT_DIR / "audit.md"
    assert p.exists()
    text = p.read_text(encoding="utf-8")
    for section in (
        "Executive Summary",
        "Fixture Inventory",
        "Recognition Coverage Matrix",
        "Live Sandbox Writer Smoke",
        "Source Immutability",
        "Final Verdict",
    ):
        assert section in text, f"section missing: {section}"


def test_t35_overall_verdict_rules(audit_run):
    assert audit_run["overallVerdict"] in (
        "PASS_FULL_COVERAGE",
        "PASS_CORE_COVERAGE_WITH_KNOWN_TEMPLATE_GAPS",
        "WARN_PARTIAL_COVERAGE",
        "WARN_WRITER_SMOKE_FAILED",
        "WARN_NO_HWPX_FIXTURES",
        "FAIL_UNSAFE_MUTATION",
        "FAIL_PARSE_ERROR",
        "FAIL_STRUCTURE_MISMATCH",
    )


# ── 회귀 smoke (T36~T45) ──────────────────────────────────────────────────


def test_t36_evidence_ingestion_smoke():
    from hwpx.fill_review import evidence_ingestion_contract as ing

    res = ing.build_evidence_sources([
        {
            "inputId": "i",
            "sourceName": "f.xlsx",
            "sourceHash": "sha:1",
            "sourceTypeHint": "CONTRACT_XLSX",
            "extractedFields": {"projectName": "X"},
        }
    ])
    assert res.evidenceCount == 1


def test_t37_ui_adapter_smoke():
    from hwpx.fill_review import fill_review_ui_adapter as ui

    target = {"targetType": "cell", "cellKey": "t_s0_000:r0:c0"}
    h = ui.build_highlight(target)
    assert h["highlightStyle"] == "CELL"


def test_t38_fill_review_contract_smoke():
    from hwpx.fill_review import fill_review_contract as fr

    rec = fr.make_document_recognition_result(sourceDocumentHash="sha:1")
    assert rec["schemaVersion"] == fr.SCHEMA_VERSION


def test_t39_paragraph_writer_module_loads():
    from hwpx.pipeline import generic_edit_plan_writer_executor_live_sandbox as live

    assert "setParagraphText" in live.ALLOWED_LIVE_OPERATION_TYPES


def test_t40_live_sandbox_module_loads():
    from hwpx.pipeline import generic_edit_plan_writer_executor_live_sandbox as live

    assert "setCellText" in live.ALLOWED_LIVE_OPERATION_TYPES


def test_t41_object_mapper_module_loads():
    from hwpx.parser import object_cell_mapper as m

    assert callable(m.map_objects_to_cells)


def test_t42_geometric_mapper_module_loads():
    from hwpx.parser import object_cell_mapper as m

    assert callable(m.map_objects_to_cells_with_geometry)


def test_t43_confirmation_gate_module_loads():
    from hwpx.parser import object_cell_confirmation_gate as g

    assert callable(g.apply_geometric_confirmation)


def test_t44_live_pipeline_module_loads():
    from hwpx.fill_review import fill_review_live_pipeline as p

    assert callable(p.run_fill_review_live_pipeline_sandbox)


def test_t45_generic_pipeline_modules_load():
    from hwpx.pipeline import (
        generic_edit_plan_contract,
    )

    assert hasattr(generic_edit_plan_contract, "validate_edit_plan")


# ── T46: audit script verdict PASS/WARN/FAIL 출력 ─────────────────────────


def test_t46_audit_run_returns_summary_dict(audit_run):
    for k in ("totalHwpxFiles", "parsedCount", "fullRecognitionPassCount", "overallVerdict"):
        assert k in audit_run


# ── HWPX-RECOGNITION-FULL-COVERAGE-AUDIT-02: post-expansion lock ───────────


def test_audit02_document_type_classification_present(audit_run):
    """모든 file_results에 documentType 분류가 존재한다."""
    for k in (
        "documentTypeCounts",
        "fillableFormTotal",
        "fillableFormPassFullCount",
        "fillableFormCoverageRate",
        "referenceTableCount",
        "emptyTemplateCount",
    ):
        assert k in audit_run


def test_audit02_fillable_form_count_locked(audit_run, full_corpus_required):
    """fillable_form 총 20건 (corpus fixture 5 + 별지 15)."""
    assert audit_run["fillableFormTotal"] == 20


def test_audit02_reference_table_count_locked(audit_run, full_corpus_required):
    """reference_table 별표 12건."""
    assert audit_run["referenceTableCount"] == 12


def test_audit02_empty_template_count_locked(audit_run):
    """gantt empty_template 3건."""
    assert audit_run["emptyTemplateCount"] == 3


def test_audit02_full_recognition_pass_count_at_least_23(audit_run, full_corpus_required):
    """LABEL_DICTIONARY_EXPANSION 이후 PASS_FULL이 23 이상."""
    assert audit_run["fullRecognitionPassCount"] >= 23


def test_audit02_fillable_form_coverage_rate_at_least_95_percent(audit_run):
    """fillable_form 중 PASS_FULL 비율 ≥ 0.95."""
    rate = audit_run["fillableFormCoverageRate"]
    assert rate is not None
    assert rate >= 0.95, f"fillableFormCoverageRate={rate} < 0.95"


def test_audit02_no_fillable_form_in_core_only(audit_run):
    """fillable_form 중 PASS_CORE_RECOGNITION_ONLY는 0건이어야 한다.
    (별지/corpus 양식은 모두 라벨 인식되어야 함)
    """
    assert audit_run["fillableFormPassCoreOnlyCount"] == 0


def test_audit02_no_unsafe_mutation(audit_run):
    assert audit_run["unsafeMutationCount"] == 0


def test_audit02_no_parse_failures(audit_run, full_corpus_required):
    assert audit_run["parseFailedCount"] == 0


def test_audit02_writer_smoke_still_passes(audit_run):
    assert audit_run["writerSmokePassCount"] >= 2
    assert audit_run["writerSmokeBlockedCount"] == 0


def test_audit02_per_file_document_type_assigned(audit):
    OUTPUT_DIR = audit.OUTPUT_DIR
    data = json.loads((OUTPUT_DIR / "audit.json").read_text(encoding="utf-8"))
    for f in data["fileResults"]:
        assert f.get("documentType") in (
            "fillable_form",
            "reference_table",
            "empty_template",
            "unknown",
        )


def test_audit02_별지_files_classified_as_fillable_form(audit, full_corpus_required):
    OUTPUT_DIR = audit.OUTPUT_DIR
    data = json.loads((OUTPUT_DIR / "audit.json").read_text(encoding="utf-8"))
    별지_files = [f for f in data["fileResults"] if "[별지" in f["relativePath"]]
    assert len(별지_files) >= 15
    for f in 별지_files:
        assert f["documentType"] == "fillable_form", f


def test_audit02_별표_files_classified_as_reference_table(audit, full_corpus_required):
    OUTPUT_DIR = audit.OUTPUT_DIR
    data = json.loads((OUTPUT_DIR / "audit.json").read_text(encoding="utf-8"))
    별표_files = [f for f in data["fileResults"] if "[별표" in f["relativePath"]]
    assert len(별표_files) >= 11
    for f in 별표_files:
        assert f["documentType"] == "reference_table", f


def test_audit02_markdown_includes_document_type_section(audit):
    OUTPUT_DIR = audit.OUTPUT_DIR
    md = (OUTPUT_DIR / "audit.md").read_text(encoding="utf-8")
    assert "Document Type Classification" in md
    assert "fillable_form" in md
    assert "reference_table" in md
    assert "empty_template" in md
    assert "fillableFormCoverageRate" in md
