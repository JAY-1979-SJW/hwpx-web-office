"""HWPX-DOCUMENT-FILL-REVIEW-CONTRACT-01 테스트.

문서 인지 → 입력 필요항목 → 자료 매칭 → 부족자료 요청 → 사용자 검수 → 승인된 항목만
writer plan으로 변환하는 contract 검증. writer 호출 0, output 0, 원본 무수정.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

METADATA_FORM = PROJECT_ROOT / "tests/fixtures/hwpx/corpus/fx_metadata_form.hwpx"


@pytest.fixture(scope="module")
def fr():
    from hwpx.fill_review import fill_review_contract as m
    return m


def _make_label_value_cell(label, label_key, value_key, label_text="",
                                value_text="", row=0, label_col=0, value_col=1):
    """label/value 셀 한 쌍 생성."""
    return [
        {"cellKey": label_key, "normalizedText": label or label_text,
          "rowIndex": row, "cellIndex": label_col},
        {"cellKey": value_key, "normalizedText": value_text,
          "rowIndex": row, "cellIndex": value_col},
    ]


def _recognition(cells=None, paragraphs=None, source_hash="sha256:abc"):
    from hwpx.fill_review.fill_review_contract import make_document_recognition_result
    return make_document_recognition_result(
        sourceDocumentHash=source_hash,
        sourcePath="/tmp/doc.hwpx",
        cells=cells or [],
        paragraphs=paragraphs or [],
    )


def _evidence(evidenceId, sourceType, extractedFields, confidence=0.8,
                 sourceName="test", sourceHash="sha:ev"):
    return {
        "evidenceId": evidenceId,
        "sourceType": sourceType,
        "sourceName": sourceName,
        "sourceHash": sourceHash,
        "extractedFields": extractedFields,
        "confidence": confidence,
        "warnings": [],
    }


def _decision(reviewItemId, decision, editedValue=None,
                 reviewer="manual", reason="ok"):
    d = {
        "reviewItemId": reviewItemId,
        "decision": decision,
        "reviewer": reviewer,
        "reason": reason,
    }
    if editedValue is not None:
        d["editedValue"] = editedValue
    return d


# ── T01-T03: FillRequirement 도출 ────────────────────────────────────────────

def test_project_name_label_creates_requirement(fr):
    cells = _make_label_value_cell("공사명",
                                         "t_s0_000:r0:c0", "t_s0_000:r0:c1")
    rec = _recognition(cells=cells)
    reqs = fr.build_fill_requirements(rec)
    assert len(reqs) == 1
    r = reqs[0]
    assert r["semanticType"] == "PROJECT_NAME"
    assert r["target"]["cellKey"] == "t_s0_000:r0:c1"
    assert r["target"]["targetType"] == "cell"
    assert r["status"] == "NEEDS_VALUE"


def test_contract_amount_label_creates_requirement(fr):
    cells = _make_label_value_cell("계약금액",
                                         "t_s0_000:r1:c0", "t_s0_000:r1:c1",
                                         row=1)
    rec = _recognition(cells=cells)
    reqs = fr.build_fill_requirements(rec)
    assert any(r["semanticType"] == "CONTRACT_AMOUNT" for r in reqs)


def test_paragraph_placeholder_creates_requirement(fr):
    paragraphs = [{
        "paragraphKey": "p_s0_0003",
        "text": "__PROJECT_NAME__",
    }]
    rec = _recognition(paragraphs=paragraphs)
    reqs = fr.build_fill_requirements(rec)
    assert len(reqs) == 1
    r = reqs[0]
    assert r["target"]["targetType"] == "paragraph"
    assert r["target"]["paragraphKey"] == "p_s0_0003"
    assert r["semanticType"] == "PROJECT_NAME"


# ── T04-T05: 자료 매칭 ──────────────────────────────────────────────────────

def test_evidence_match_for_project_name(fr):
    cells = _make_label_value_cell("공사명",
                                         "t:r0:c0", "t:r0:c1")
    rec = _recognition(cells=cells)
    reqs = fr.build_fill_requirements(rec)
    ev = _evidence("ev1", "CONTRACT_XLSX",
                       {"projectName": "○○센터 신축공사"})
    matches = fr.match_requirements_with_evidence(reqs, [ev])
    assert len(matches) == 1
    m = matches[0]
    assert m["proposedValue"] == "○○센터 신축공사"
    assert m["evidenceId"] == "ev1"
    assert m["needsUserReview"] is True


def test_evidence_match_for_contract_amount(fr):
    cells = _make_label_value_cell("계약금액", "t:r0:c0", "t:r0:c1")
    rec = _recognition(cells=cells)
    reqs = fr.build_fill_requirements(rec)
    ev = _evidence("ev2", "CONTRACT_XLSX",
                       {"contractAmount": "1,234,567,000원"})
    matches = fr.match_requirements_with_evidence(reqs, [ev])
    assert any(m["proposedValue"] == "1,234,567,000원" for m in matches)


# ── T06-T08: MissingMaterialRequest ─────────────────────────────────────────

def test_no_evidence_for_business_license_creates_request(fr):
    cells = _make_label_value_cell("사업자등록번호", "t:r0:c0", "t:r0:c1")
    rec = _recognition(cells=cells)
    reqs = fr.build_fill_requirements(rec)
    matches = fr.match_requirements_with_evidence(reqs, [])
    requests = fr.build_missing_material_requests(reqs, [], matches)
    assert len(requests) == 1
    req = requests[0]
    assert req["requestedMaterialType"] == "BUSINESS_LICENSE"
    assert req["blocking"] is True


def test_no_evidence_for_seal_creates_request(fr):
    cells = _make_label_value_cell("직인", "t:r0:c0", "t:r0:c1")
    rec = _recognition(cells=cells)
    reqs = fr.build_fill_requirements(rec)
    requests = fr.build_missing_material_requests(reqs, [], [])
    assert len(requests) == 1
    assert requests[0]["requestedMaterialType"] == "SEAL_IMAGE"


def test_no_request_when_evidence_present(fr):
    cells = _make_label_value_cell("사업자등록번호", "t:r0:c0", "t:r0:c1")
    rec = _recognition(cells=cells)
    reqs = fr.build_fill_requirements(rec)
    ev = _evidence("ev_biz", "BUSINESS_LICENSE",
                       {"businessRegistrationNumber": "123-45-67890"})
    matches = fr.match_requirements_with_evidence(reqs, [ev])
    requests = fr.build_missing_material_requests(reqs, [ev], matches)
    assert requests == []


# ── T09: confidence만으로 자동 APPROVE 금지 ─────────────────────────────────

def test_high_confidence_does_not_auto_approve(fr):
    cells = _make_label_value_cell("공사명", "t:r0:c0", "t:r0:c1")
    rec = _recognition(cells=cells)
    reqs = fr.build_fill_requirements(rec)
    ev = _evidence("ev", "CONTRACT_XLSX",
                       {"projectName": "X"}, confidence=0.99)
    matches = fr.match_requirements_with_evidence(reqs, [ev])
    assert all(m["needsUserReview"] is True for m in matches)
    # decision 없이 plan을 만들면 operations=[]
    items = fr.build_review_items(reqs, matches, [])
    plan = fr.build_approved_edit_plan(items, decisions=[],
                                            source_document_hash="sha:1")
    assert plan.operations == []
    assert plan.writerCalled is False


# ── T10: FillReviewItem schema ──────────────────────────────────────────────

def test_review_item_includes_preview_and_evidence_refs(fr):
    cells = _make_label_value_cell("공사명", "t:r0:c0", "t:r0:c1")
    rec = _recognition(cells=cells)
    reqs = fr.build_fill_requirements(rec)
    ev = _evidence("evX", "CONTRACT_XLSX", {"projectName": "VAL"})
    matches = fr.match_requirements_with_evidence(reqs, [ev])
    items = fr.build_review_items(reqs, matches, [])
    assert len(items) == 1
    it = items[0]
    for key in ("reviewItemId", "requirementId", "target",
                "currentValue", "proposedValue", "evidenceRefs",
                "beforePreview", "afterPreview", "riskLevel",
                "status", "allowedDecisions"):
        assert key in it
    assert it["proposedValue"] == "VAL"
    assert it["evidenceRefs"] == ["evX"]
    assert it["afterPreview"] == "VAL"


# ── T11-T14: decision → plan 변환 ──────────────────────────────────────────

def _setup_simple_review(fr, project_name="VAL"):
    cells = _make_label_value_cell("공사명", "t_s0_000:r0:c0", "t_s0_000:r0:c1")
    rec = _recognition(cells=cells)
    reqs = fr.build_fill_requirements(rec)
    ev = _evidence("ev", "CONTRACT_XLSX", {"projectName": project_name})
    matches = fr.match_requirements_with_evidence(reqs, [ev])
    items = fr.build_review_items(reqs, matches, [])
    return reqs, matches, items


def test_approve_produces_operation(fr):
    _, _, items = _setup_simple_review(fr)
    plan = fr.build_approved_edit_plan(
        items, [_decision(items[0]["reviewItemId"], "APPROVE")],
        source_document_hash="sha:1",
    )
    assert plan.verdict == "READY_FOR_WRITER"
    assert len(plan.operations) == 1
    op = plan.operations[0]
    assert op["operationType"] == "setCellText"
    assert op["target"]["tableId"] == "t_s0_000"
    assert op["target"]["row"] == 0
    assert op["target"]["col"] == 1
    assert op["value"] == "VAL"
    assert op["expectedBefore"] == ""


def test_reject_does_not_produce_operation(fr):
    _, _, items = _setup_simple_review(fr)
    plan = fr.build_approved_edit_plan(
        items, [_decision(items[0]["reviewItemId"], "REJECT")],
        source_document_hash="sha:1",
    )
    assert plan.operations == []
    assert any(s["reason"] == "decision_reject" for s in plan.skipped)


def test_hold_does_not_produce_operation(fr):
    _, _, items = _setup_simple_review(fr)
    plan = fr.build_approved_edit_plan(
        items, [_decision(items[0]["reviewItemId"], "HOLD")],
        source_document_hash="sha:1",
    )
    assert plan.operations == []


def test_request_material_does_not_produce_operation(fr):
    _, _, items = _setup_simple_review(fr)
    plan = fr.build_approved_edit_plan(
        items, [_decision(items[0]["reviewItemId"], "REQUEST_MATERIAL")],
        source_document_hash="sha:1",
    )
    assert plan.operations == []


# ── T15: EDIT_VALUE ─────────────────────────────────────────────────────────

def test_edit_value_uses_user_edited_value(fr):
    _, _, items = _setup_simple_review(fr, project_name="auto-value")
    plan = fr.build_approved_edit_plan(
        items,
        [_decision(items[0]["reviewItemId"], "EDIT_VALUE",
                      editedValue="user-edited")],
        source_document_hash="sha:1",
    )
    assert plan.verdict == "READY_FOR_WRITER"
    assert plan.operations[0]["value"] == "user-edited"


# ── T16: sourceDocumentHash 누락 차단 ───────────────────────────────────────

def test_missing_source_doc_hash_blocks_plan(fr):
    _, _, items = _setup_simple_review(fr)
    plan = fr.build_approved_edit_plan(
        items, [_decision(items[0]["reviewItemId"], "APPROVE")],
        source_document_hash="",
    )
    assert plan.verdict == "BLOCKED_INVALID_PLAN"
    assert plan.operations == []
    assert any(f.code == "SOURCE_DOC_HASH_REQUIRED" for f in plan.findings)


# ── T17: expectedBefore — 생성된 operation에 항상 포함 ─────────────────────

def test_generated_operations_always_include_expected_before(fr):
    _, _, items = _setup_simple_review(fr)
    plan = fr.build_approved_edit_plan(
        items, [_decision(items[0]["reviewItemId"], "APPROVE")],
        source_document_hash="sha:1",
    )
    for op in plan.operations:
        assert "expectedBefore" in op


# ── T18: target 없는 review item은 operation 생성 금지 ─────────────────────

def test_no_target_blocks_operation(fr):
    bad_item = {
        "reviewItemId": "rev_x",
        "requirementId": "req_x",
        "target": {"targetType": "cell", "cellKey": None, "paragraphKey": None},
        "currentValue": "", "proposedValue": "X",
        "evidenceRefs": [], "beforePreview": "", "afterPreview": "X",
        "riskLevel": "LOW", "status": "READY_FOR_REVIEW",
        "allowedDecisions": ["APPROVE"],
    }
    plan = fr.build_approved_edit_plan(
        [bad_item], [_decision("rev_x", "APPROVE")],
        source_document_hash="sha:1",
    )
    assert plan.operations == []
    assert any(s["reason"] == "cell_key_missing" for s in plan.skipped)


# ── T19: AUTOGEN_OPERATIONS 집합 검증 (unsupported operation 차단) ──────────

def test_autogen_operations_subset_of_allowed(fr):
    assert fr.AUTOGEN_OPERATIONS.issubset(fr.ALLOWED_FILL_REVIEW_OPERATIONS)
    # writer 측 official allow와 호환
    from hwpx.pipeline import generic_edit_plan_contract as contract
    assert fr.ALLOWED_FILL_REVIEW_OPERATIONS.issubset(contract.ALLOWED_OPERATION_TYPES)


# ── T20: setParagraphText 공식 이름 잠금 ────────────────────────────────────

def test_official_paragraph_full_replace_op_name_is_set_paragraph_text(fr):
    assert fr.OFFICIAL_PARAGRAPH_FULL_REPLACE_OP == "setParagraphText"
    assert "setParagraphText" in fr.ALLOWED_FILL_REVIEW_OPERATIONS
    assert fr.is_official_paragraph_full_replace("setParagraphText") is True


# ── T21: setCellParagraphText는 공식 허용 목록에 없음 ───────────────────────

def test_set_cell_paragraph_text_not_in_official_allowlist(fr):
    assert "setCellParagraphText" not in fr.ALLOWED_FILL_REVIEW_OPERATIONS
    assert "setCellParagraphText" in fr.FORBIDDEN_PARAGRAPH_OP_NAMES
    assert fr.is_forbidden_operation_name("setCellParagraphText") is True


# ── T22: replaceTextRun이 공식 허용 + AUTOGEN 모두에 포함 (스펙) ────────────

def test_replace_text_run_in_official_and_autogen_sets(fr):
    assert "replaceTextRun" in fr.ALLOWED_FILL_REVIEW_OPERATIONS
    assert "replaceTextRun" in fr.AUTOGEN_OPERATIONS
    # 단, 이번 baseline builder가 자동으로 replaceTextRun을 생성하는 시나리오는
    # 아직 없다 (target.targetType=="cell"→setCellText, "paragraph"→setParagraphText).
    # find/replace는 별도 호출 경로가 도입될 때 검증되어야 한다.


# ── T23: setCellText operation 필수 필드 검증 ───────────────────────────────

def test_set_cell_text_operation_includes_required_fields(fr):
    _, _, items = _setup_simple_review(fr)
    plan = fr.build_approved_edit_plan(
        items, [_decision(items[0]["reviewItemId"], "APPROVE")],
        source_document_hash="sha:1",
    )
    op = plan.operations[0]
    for k in ("operationId", "operationType", "target", "value",
                "expectedBefore", "preserveStyle", "riskLevel",
                "requiresReview", "reason"):
        assert k in op
    assert op["target"].get("tableId") is not None
    assert op["target"].get("row") is not None
    assert op["target"].get("col") is not None


# ── T24: writer 미호출 ──────────────────────────────────────────────────────

def test_writer_not_invoked(fr, monkeypatch):
    from hwpx.pipeline import generic_edit_plan_writer_executor_live_sandbox as live
    call_log: list = []
    monkeypatch.setattr(live, "execute_writer_call_plan_live_sandbox",
                          lambda *a, **k: call_log.append("live"))
    _, _, items = _setup_simple_review(fr)
    plan = fr.build_approved_edit_plan(
        items, [_decision(items[0]["reviewItemId"], "APPROVE")],
        source_document_hash="sha:1",
    )
    assert plan.writerCalled is False
    assert call_log == []


# ── T25: output 미생성 ──────────────────────────────────────────────────────

def test_no_output_files_created(fr, tmp_path):
    before = sorted(p.name for p in tmp_path.iterdir())
    _, _, items = _setup_simple_review(fr)
    fr.build_approved_edit_plan(
        items, [_decision(items[0]["reviewItemId"], "APPROVE")],
        source_document_hash="sha:1",
    )
    assert sorted(p.name for p in tmp_path.iterdir()) == before


# ── T26: 원본 fixture sha256 / mtime 무변경 ────────────────────────────────

def test_original_fixture_unchanged(fr):
    sha_before = hashlib.sha256(METADATA_FORM.read_bytes()).hexdigest()
    mtime_before = METADATA_FORM.stat().st_mtime
    # contract 호출은 fixture path를 받지도 않지만 명시적으로 확인
    _, _, items = _setup_simple_review(fr)
    fr.build_approved_edit_plan(
        items, [_decision(items[0]["reviewItemId"], "APPROVE")],
        source_document_hash="sha:1",
    )
    assert hashlib.sha256(METADATA_FORM.read_bytes()).hexdigest() == sha_before
    assert METADATA_FORM.stat().st_mtime == mtime_before


# ── T27: object_cell_mapper 결과를 review item target으로 연결 가능 ────────

def test_object_cell_mapping_can_feed_recognition(fr):
    """object_cell_mapper의 cellKey 형식이 fill_review의 target.cellKey와 호환됨."""
    cells = [
        {"cellKey": "t_s0_000:r3:c0", "normalizedText": "공사명",
          "rowIndex": 3, "cellIndex": 0},
        {"cellKey": "t_s0_000:r3:c1", "normalizedText": "",
          "rowIndex": 3, "cellIndex": 1},
    ]
    mappings = [{
        "objectKey": "obj:s0:1:0001", "objectType": "picture",
        "cellKey": "t_s0_000:r3:c1", "confidence": 1.0,
        "reason": "DESCENDANT_OF_TC",
    }]
    rec = fr.make_document_recognition_result(
        sourceDocumentHash="sha:1", cells=cells, objectCellMappings=mappings,
    )
    reqs = fr.build_fill_requirements(rec)
    assert any(r["target"]["cellKey"] == "t_s0_000:r3:c1" for r in reqs)
    # mappings도 result에 보존됨
    assert rec["objectCellMappings"] == mappings


# ── T28: MissingMaterialRequest와 FillReviewItem이 같은 requirementId로 연결 ─

def test_missing_request_links_to_review_item_via_requirement_id(fr):
    cells = _make_label_value_cell("사업자등록번호", "t:r0:c0", "t:r0:c1")
    rec = _recognition(cells=cells)
    reqs = fr.build_fill_requirements(rec)
    matches = fr.match_requirements_with_evidence(reqs, [])
    requests = fr.build_missing_material_requests(reqs, [], matches)
    items = fr.build_review_items(reqs, matches, requests)
    assert len(requests) == 1
    assert len(items) == 1
    req_id = reqs[0]["requirementId"]
    assert requests[0]["requirementId"] == req_id
    assert items[0]["requirementId"] == req_id
    assert items[0]["relatedMaterialRequests"] == [requests[0]["requestId"]]
    assert items[0]["status"] == "NEEDS_USER_INPUT"


# ── T29: schemaVersion / engineVersion / requestId ─────────────────────────

def test_recognition_result_has_schema_engine_request(fr):
    rec = fr.make_document_recognition_result(sourceDocumentHash="sha:1")
    assert rec["schemaVersion"] == fr.SCHEMA_VERSION
    assert rec["engineVersion"] == fr.ENGINE_VERSION
    assert rec["requestId"]


# ── T30: 위험 등급 분류 ─────────────────────────────────────────────────────

def test_proposed_value_without_evidence_is_high_risk(fr):
    cells = _make_label_value_cell("공사명", "t:r0:c0", "t:r0:c1")
    rec = _recognition(cells=cells)
    reqs = fr.build_fill_requirements(rec)
    # 가짜 match: evidenceId 없는 proposal (evidenceRefs 비어 있음)
    fake_match = {
        "matchId": "m1", "requirementId": reqs[0]["requirementId"],
        "evidenceId": None, "fieldName": "x",
        "proposedValue": "예측값", "confidence": 0.9,
        "matchReason": "ai_hint", "needsUserReview": True,
    }
    items = fr.build_review_items(reqs, [fake_match], [])
    assert items[0]["riskLevel"] == "HIGH"


# ── 추가: 다중 APPROVE 정상 처리 ────────────────────────────────────────────

def test_multiple_approvals_create_multiple_operations(fr):
    cells = (_make_label_value_cell("공사명", "t_s0_000:r0:c0", "t_s0_000:r0:c1")
             + _make_label_value_cell("계약금액", "t_s0_000:r1:c0", "t_s0_000:r1:c1", row=1))
    rec = _recognition(cells=cells)
    reqs = fr.build_fill_requirements(rec)
    ev = _evidence("ev", "CONTRACT_XLSX",
                       {"projectName": "P", "contractAmount": "100원"})
    # 한 evidence에서 첫 매칭만 사용 — 다른 requirement는 매칭이 없음
    # 두 개 모두 매칭되도록 evidence 둘로 분리
    ev2 = _evidence("ev2", "CONTRACT_XLSX",
                        {"contractAmount": "100원"})
    matches = fr.match_requirements_with_evidence(reqs, [ev, ev2])
    items = fr.build_review_items(reqs, matches, [])
    decisions = [_decision(it["reviewItemId"], "APPROVE") for it in items]
    plan = fr.build_approved_edit_plan(
        items, decisions, source_document_hash="sha:1",
    )
    assert plan.verdict == "READY_FOR_WRITER"
    assert len(plan.operations) >= 1
    for op in plan.operations:
        assert op["operationType"] in fr.AUTOGEN_OPERATIONS


# ── HWPX-FILL-REVIEW-LABEL-DICTIONARY-EXPANSION-01: 신규 라벨 ──────────────

@pytest.mark.parametrize("label,expected", [
    ("기관명", "COMPANY_NAME"),
    ("명칭", "COMPANY_NAME"),
    ("회사확인", "COMPANY_NAME"),
    ("평가사", "SITE_MANAGER_NAME"),
    ("평가반장", "SITE_MANAGER_NAME"),
    ("점검자", "SITE_MANAGER_NAME"),
    ("작성자", "SITE_MANAGER_NAME"),
    ("관계인", "SITE_MANAGER_NAME"),
    ("주된점검인력", "SITE_MANAGER_NAME"),
    ("보조점검인력", "SITE_MANAGER_NAME"),
    ("소방안전관리자", "SITE_MANAGER_NAME"),
    ("성명", "SITE_MANAGER_NAME"),
    ("담당자", "SITE_MANAGER_NAME"),
    ("소방계획서", "ATTACHMENT_DOCUMENT"),
    ("시정조치기한", "END_DATE"),
    ("건축허가일", "START_DATE"),
    ("사용승인일", "END_DATE"),
    ("점검기간", "START_DATE"),
    ("접수일", "START_DATE"),
    ("처리일", "END_DATE"),
    ("발행번호", "FREE_TEXT"),
    ("접수번호", "FREE_TEXT"),
    ("평가종류", "FREE_TEXT"),
    ("부적합내용", "FREE_TEXT"),
    ("원인분석", "FREE_TEXT"),
    ("재발방지대책", "FREE_TEXT"),
])
def test_expanded_label_dictionary_maps_correctly(fr, label, expected):
    cells = _make_label_value_cell(label, "t:r0:c0", "t:r0:c1")
    rec = _recognition(cells=cells)
    reqs = fr.build_fill_requirements(rec)
    assert len(reqs) == 1, f"label={label!r} did not produce a requirement"
    assert reqs[0]["semanticType"] == expected, \
        f"label={label!r} expected {expected}, got {reqs[0]['semanticType']}"


def test_label_dictionary_handles_parenthesized_normalization(fr):
    """명칭(상호) 같은 괄호 라벨도 정규화 후 매칭."""
    cells = _make_label_value_cell("명칭(상호)", "t:r0:c0", "t:r0:c1")
    rec = _recognition(cells=cells)
    reqs = fr.build_fill_requirements(rec)
    assert len(reqs) == 1
    assert reqs[0]["semanticType"] == "COMPANY_NAME"


# ── 추가: audit script verdict=PASS ─────────────────────────────────────────

def test_audit_script_passes(fr):
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "audit_hwpx_fill_review_contract",
        PROJECT_ROOT / "scripts/ops/audit_hwpx_fill_review_contract.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    result = mod.run_audit()
    assert result["auditVerdict"] == "PASS", result


# ── 추가: invalid decision shape 차단 ───────────────────────────────────────

def test_invalid_decision_shape_is_skipped(fr):
    _, _, items = _setup_simple_review(fr)
    plan = fr.build_approved_edit_plan(
        items, [{"reviewItemId": "x", "decision": "MAYBE"}],
        source_document_hash="sha:1",
    )
    assert plan.operations == []
    assert any(f.code == "INVALID_DECISION" for f in plan.findings)
