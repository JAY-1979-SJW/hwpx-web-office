"""HWPX-FILL-REVIEW-EVIDENCE-INGESTION-CONTRACT-01 테스트.

업로드 자료 → EvidenceSource 변환 계약 검증. writer 미호출 / output 미생성 / 원본 무수정.
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


@pytest.fixture(scope="module")
def ing():
    from hwpx.fill_review import evidence_ingestion_contract as m
    return m


def _input(input_id="in1", name="file.xlsx", hint=None, ext=None,
              source_hash="sha:1", fields=None, text=None, tables=None,
              metadata=None):
    d = {"inputId": input_id, "sourceName": name, "sourceHash": source_hash}
    if hint is not None:
        d["sourceTypeHint"] = hint
    if ext is not None:
        d["fileExtension"] = ext
    if fields is not None:
        d["extractedFields"] = fields
    if text is not None:
        d["extractedText"] = text
    if tables is not None:
        d["extractedTables"] = tables
    if metadata is not None:
        d["metadata"] = metadata
    return d


# ── T01: sourceHash 누락 ────────────────────────────────────────────────────

def test_missing_source_hash_rejected(ing):
    inp = _input(source_hash="", fields={"projectName": "X"})
    res = ing.build_evidence_sources([inp])
    assert res.evidenceCount == 0
    assert res.rejectedCount == 1
    rej = res.rejectedInputs[0]
    assert rej.warningCode == "SOURCE_HASH_REQUIRED"


# ── T02: 빈 input ───────────────────────────────────────────────────────────

def test_empty_input_rejected(ing):
    inp = _input()  # 모든 추출 필드 비어 있음
    res = ing.build_evidence_sources([inp])
    assert res.evidenceCount == 0
    assert res.rejectedCount == 1
    assert res.rejectedInputs[0].warningCode == "EMPTY_INPUT"


# ── T03: hint=CONTRACT_XLSX ─────────────────────────────────────────────────

def test_hint_contract_xlsx_propagated(ing):
    inp = _input(hint="CONTRACT_XLSX",
                    fields={"projectName": "ABC 신축공사"})
    res = ing.build_evidence_sources([inp])
    assert res.evidenceCount == 1
    ev = res.evidenceSources[0]
    assert ev["sourceType"] == "CONTRACT_XLSX"


# ── T04: 파일명 "계약내역서.xlsx" → CONTRACT_XLSX 또는 ESTIMATE_XLSX ───────

def test_filename_contract_or_estimate_detected(ing):
    inp = _input(name="계약내역서.xlsx", ext="xlsx",
                    fields={"projectName": "P"})
    res = ing.build_evidence_sources([inp])
    ev = res.evidenceSources[0]
    # "계약"과 "내역" 둘 다 키워드 — 내역(ESTIMATE)가 우선순위 상위
    assert ev["sourceType"] in ("CONTRACT_XLSX", "ESTIMATE_XLSX")
    # 경고는 없음
    assert not any(w.code == "UNKNOWN_SOURCE_TYPE" for w in res.warnings)


# ── T05: 파일명 "기성내역서.xlsx" → ESTIMATE_XLSX ───────────────────────────

def test_filename_estimate_detected(ing):
    inp = _input(name="기성내역서.xlsx", ext="xlsx",
                    fields={"contractAmount": "100원"})
    res = ing.build_evidence_sources([inp])
    assert res.evidenceSources[0]["sourceType"] == "ESTIMATE_XLSX"


# ── T06: 파일명 "사업자등록증.pdf" → BUSINESS_LICENSE ──────────────────────

def test_filename_business_license_detected(ing):
    inp = _input(name="사업자등록증.pdf", ext="pdf",
                    fields={"businessRegistrationNumber": "123-45-67890"})
    res = ing.build_evidence_sources([inp])
    assert res.evidenceSources[0]["sourceType"] == "BUSINESS_LICENSE"


# ── T07: 파일명 "도장.png" → SEAL_IMAGE ─────────────────────────────────────

def test_filename_seal_image_detected(ing):
    inp = _input(name="도장.png", ext="png",
                    fields={"sealImageRef": "ref://seal/1"})
    res = ing.build_evidence_sources([inp])
    assert res.evidenceSources[0]["sourceType"] == "SEAL_IMAGE"


def test_filename_seal_english_detected(ing):
    inp = _input(name="seal_company.png", ext="png",
                    fields={"sealImageRef": "ref://seal/2"})
    res = ing.build_evidence_sources([inp])
    assert res.evidenceSources[0]["sourceType"] == "SEAL_IMAGE"


# ── T08: 알 수 없는 확장자 ─────────────────────────────────────────────────

def test_unknown_extension_yields_unknown_source_type(ing):
    inp = _input(name="data.unknown_ext", ext="xyz",
                    fields={"freeText": "raw"})
    res = ing.build_evidence_sources([inp])
    ev = res.evidenceSources[0]
    assert ev["sourceType"] == "UNKNOWN"
    # warning 기록
    assert any(w.code == "UNKNOWN_SOURCE_TYPE" for w in res.warnings)


# ── T09: projectName 정규화 ─────────────────────────────────────────────────

def test_project_name_field_normalized(ing):
    inp = _input(hint="CONTRACT_XLSX", fields={"projectName": "  ○○센터 신축공사  "})
    res = ing.build_evidence_sources([inp])
    ev = res.evidenceSources[0]
    assert ev["extractedFields"]["projectName"] == "○○센터 신축공사"


# ── T10: contractAmount 정규화 ─────────────────────────────────────────────

def test_contract_amount_normalized_with_number_candidate(ing):
    inp = _input(hint="CONTRACT_XLSX", fields={"contractAmount": "12,300,000원"})
    res = ing.build_evidence_sources([inp])
    ev = res.evidenceSources[0]
    assert ev["extractedFields"]["contractAmount"] == "12,300,000원"
    detail = ev["extractedFieldDetails"]["contractAmount"]
    assert detail["numberCandidate"] == 12300000


def test_invalid_amount_warns(ing):
    inp = _input(hint="CONTRACT_XLSX", fields={"contractAmount": "abc"})
    res = ing.build_evidence_sources([inp])
    ev = res.evidenceSources[0]
    # 경고 발생
    codes = [w["code"] for w in ev["warnings"]]
    assert "INVALID_AMOUNT_FORMAT" in codes


# ── T11: startDate "2026.01.01" → ISO ──────────────────────────────────────

def test_start_date_normalized_to_iso(ing):
    inp = _input(hint="CONTRACT_XLSX", fields={"startDate": "2026.01.01"})
    res = ing.build_evidence_sources([inp])
    ev = res.evidenceSources[0]
    assert ev["extractedFields"]["startDate"] == "2026-01-01"


# ── T12: endDate "2026-03-01" → ISO ────────────────────────────────────────

def test_end_date_normalized_to_iso(ing):
    inp = _input(hint="CONTRACT_XLSX", fields={"endDate": "2026-03-01"})
    res = ing.build_evidence_sources([inp])
    assert res.evidenceSources[0]["extractedFields"]["endDate"] == "2026-03-01"


def test_invalid_date_warns(ing):
    inp = _input(hint="CONTRACT_XLSX", fields={"startDate": "Tomorrow"})
    res = ing.build_evidence_sources([inp])
    ev = res.evidenceSources[0]
    codes = [w["code"] for w in ev["warnings"]]
    assert "INVALID_DATE_FORMAT" in codes


# ── T13: businessRegistrationNumber 유효 ────────────────────────────────────

def test_valid_business_registration_number(ing):
    inp = _input(hint="BUSINESS_LICENSE",
                    fields={"businessRegistrationNumber": "123-45-67890"})
    res = ing.build_evidence_sources([inp])
    ev = res.evidenceSources[0]
    assert ev["extractedFields"]["businessRegistrationNumber"] == "123-45-67890"
    codes = [w["code"] for w in ev["warnings"]]
    assert "INVALID_BUSINESS_REGISTRATION_NUMBER" not in codes


# ── T14: businessRegistrationNumber 형식 이상 → warning ────────────────────

def test_invalid_business_registration_number_warns(ing):
    inp = _input(hint="BUSINESS_LICENSE",
                    fields={"businessRegistrationNumber": "1234567890"})
    res = ing.build_evidence_sources([inp])
    ev = res.evidenceSources[0]
    codes = [w["code"] for w in ev["warnings"]]
    assert "INVALID_BUSINESS_REGISTRATION_NUMBER" in codes


# ── T15: extractedText "공사명: ..." 추출 ──────────────────────────────────

def test_extracted_text_project_name(ing):
    inp = _input(hint="OCR_RESULT",
                    text="공사명: ABC프로젝트\n계약금액: 100,000,000원\n착공일: 2026.05.01")
    res = ing.build_evidence_sources([inp])
    ev = res.evidenceSources[0]
    assert ev["extractedFields"]["projectName"] == "ABC프로젝트"


# ── T16: extractedText "계약금액: ..." 추출 ───────────────────────────────

def test_extracted_text_contract_amount(ing):
    inp = _input(hint="OCR_RESULT",
                    text="계약금액: 100,000,000원")
    res = ing.build_evidence_sources([inp])
    ev = res.evidenceSources[0]
    assert ev["extractedFields"]["contractAmount"] == "100,000,000원"
    assert ev["extractedFieldDetails"]["contractAmount"]["numberCandidate"] == 100000000


# ── T17: extractedTables label/value 추출 ─────────────────────────────────

def test_extracted_tables_company_name(ing):
    inp = _input(hint="CONTRACT_XLSX",
                    tables=[[["회사명", "○○건설(주)"], ["주소", "서울시"]]])
    res = ing.build_evidence_sources([inp])
    ev = res.evidenceSources[0]
    assert ev["extractedFields"]["companyName"] == "○○건설(주)"
    assert ev["extractedFields"]["address"] == "서울시"


# ── T18: 중복 field 동일 값 → conflict 없음 ────────────────────────────────

def test_same_field_same_value_no_conflict(ing):
    inp = _input(hint="CONTRACT_XLSX",
                    fields={"projectName": "P"},
                    text="공사명: P",
                    tables=[[["공사명", "P"]]])
    res = ing.build_evidence_sources([inp])
    ev = res.evidenceSources[0]
    codes = [w["code"] for w in ev["warnings"]]
    assert "FIELD_CONFLICT" not in codes
    assert ev["extractedFields"]["projectName"] == "P"


# ── T19: 중복 field 다른 값 → FIELD_CONFLICT ──────────────────────────────

def test_same_field_different_values_yields_conflict(ing):
    inp = _input(hint="CONTRACT_XLSX",
                    fields={"projectName": "A"},
                    text="공사명: B")
    res = ing.build_evidence_sources([inp])
    ev = res.evidenceSources[0]
    codes = [w["code"] for w in ev["warnings"]]
    assert "FIELD_CONFLICT" in codes


# ── T20: EvidenceSource 필수 7키 ───────────────────────────────────────────

def test_evidence_source_required_keys(ing):
    inp = _input(hint="CONTRACT_XLSX", fields={"projectName": "X"})
    res = ing.build_evidence_sources([inp])
    ev = res.evidenceSources[0]
    for k in ("evidenceId", "sourceType", "sourceName", "sourceHash",
                "extractedFields", "confidence", "warnings"):
        assert k in ev, f"missing key {k}"


# ── T21: EvidenceIngestionResult 필수 필드 ────────────────────────────────

def test_ingestion_result_required_fields(ing):
    inp = _input(hint="CONTRACT_XLSX", fields={"projectName": "X"})
    res = ing.build_evidence_sources([inp]).to_dict()
    for k in ("schemaVersion", "engineVersion", "requestId",
                "evidenceSources", "rejectedInputs", "warnings",
                "sourceCount", "evidenceCount", "rejectedCount"):
        assert k in res, f"missing key {k}"


# ── T22: confidence 높아도 자동 승인 필드 없음 ────────────────────────────

def test_no_auto_approval_field_on_evidence(ing):
    inp = _input(hint="MANUAL_ENTRY",
                    fields={"projectName": "user typed"})
    res = ing.build_evidence_sources([inp])
    ev = res.evidenceSources[0]
    # 자동 승인을 의미하는 어떤 필드도 없음
    for forbidden in ("autoApprove", "approved", "approvedAt", "isApproved"):
        assert forbidden not in ev
    # match를 만들면 needsUserReview=True (fill_review_contract 연계)
    # — 이 테스트는 T26-T29에서 실제로 확인


# ── T23: writer 미호출 ────────────────────────────────────────────────────

def test_writer_not_invoked(ing, monkeypatch):
    from hwpx.pipeline import generic_edit_plan_writer_executor_live_sandbox as live
    call_log: list = []
    monkeypatch.setattr(live, "execute_writer_call_plan_live_sandbox",
                          lambda *a, **k: call_log.append("live"))
    ing.build_evidence_sources([_input(hint="CONTRACT_XLSX",
                                            fields={"projectName": "P"})])
    assert call_log == []


# ── T24: output 미생성 ───────────────────────────────────────────────────

def test_no_output_files_created(ing, tmp_path):
    before = sorted(p.name for p in tmp_path.iterdir())
    ing.build_evidence_sources([_input(hint="CONTRACT_XLSX",
                                            fields={"projectName": "P"})])
    after = sorted(p.name for p in tmp_path.iterdir())
    assert before == after


# ── T25: 원본 fixture sha256/mtime 무변경 ────────────────────────────────

def test_original_fixture_unchanged(ing):
    sha_before = hashlib.sha256(METADATA_FORM.read_bytes()).hexdigest()
    mtime_before = METADATA_FORM.stat().st_mtime
    ing.build_evidence_sources([_input(hint="CONTRACT_XLSX",
                                            fields={"projectName": "P"})])
    assert hashlib.sha256(METADATA_FORM.read_bytes()).hexdigest() == sha_before
    assert METADATA_FORM.stat().st_mtime == mtime_before


# ── T26: EvidenceSource[] → match_requirements_with_evidence smoke ───────

def test_evidence_feeds_match_requirements(ing, fr):
    inp = _input(hint="CONTRACT_XLSX", fields={"projectName": "ABC공사"})
    res = ing.build_evidence_sources([inp])
    # requirement 생성
    cells = [
        {"cellKey": "t_s0_000:r0:c0", "normalizedText": "공사명",
          "rowIndex": 0, "cellIndex": 0},
        {"cellKey": "t_s0_000:r0:c1", "normalizedText": "",
          "rowIndex": 0, "cellIndex": 1},
    ]
    rec = fr.make_document_recognition_result(sourceDocumentHash="sha:1",
                                                    cells=cells)
    reqs = fr.build_fill_requirements(rec)
    matches = fr.match_requirements_with_evidence(reqs, res.evidenceSources)
    assert len(matches) == 1
    m = matches[0]
    assert m["proposedValue"] == "ABC공사"
    assert m["needsUserReview"] is True   # confidence와 무관하게 항상 True


# ── T27: evidence 없으면 MissingMaterialRequest 유지 ─────────────────────

def test_missing_material_request_preserved_when_no_evidence(ing, fr):
    cells = [
        {"cellKey": "t_s0_000:r0:c0", "normalizedText": "사업자등록번호",
          "rowIndex": 0, "cellIndex": 0},
        {"cellKey": "t_s0_000:r0:c1", "normalizedText": "",
          "rowIndex": 0, "cellIndex": 1},
    ]
    rec = fr.make_document_recognition_result(sourceDocumentHash="sha:1",
                                                    cells=cells)
    reqs = fr.build_fill_requirements(rec)
    # build_evidence_sources에 빈 입력 → evidenceSources=[]
    res = ing.build_evidence_sources([])
    matches = fr.match_requirements_with_evidence(reqs, res.evidenceSources)
    requests = fr.build_missing_material_requests(reqs, res.evidenceSources, matches)
    assert len(requests) == 1
    assert requests[0]["requestedMaterialType"] == "BUSINESS_LICENSE"


# ── T28: BUSINESS_LICENSE evidence가 businessRegistrationNumber 매칭 ────

def test_business_license_evidence_matches_brn_requirement(ing, fr):
    inp = _input(hint="BUSINESS_LICENSE",
                    fields={"businessRegistrationNumber": "123-45-67890"})
    res = ing.build_evidence_sources([inp])
    cells = [
        {"cellKey": "t:r0:c0", "normalizedText": "사업자등록번호",
          "rowIndex": 0, "cellIndex": 0},
        {"cellKey": "t:r0:c1", "normalizedText": "",
          "rowIndex": 0, "cellIndex": 1},
    ]
    rec = fr.make_document_recognition_result(sourceDocumentHash="sha:1",
                                                    cells=cells)
    reqs = fr.build_fill_requirements(rec)
    matches = fr.match_requirements_with_evidence(reqs, res.evidenceSources)
    assert len(matches) == 1
    assert matches[0]["proposedValue"] == "123-45-67890"


# ── T29: SEAL_IMAGE evidence가 STAMP_OR_SEAL requirement와 연결 ─────────

def test_seal_image_evidence_resolves_missing_material(ing, fr):
    inp = _input(name="seal.png", ext="png", hint="SEAL_IMAGE",
                    fields={"sealImageRef": "ref://seal/x"})
    res = ing.build_evidence_sources([inp])
    cells = [
        {"cellKey": "t:r0:c0", "normalizedText": "직인",
          "rowIndex": 0, "cellIndex": 0},
        {"cellKey": "t:r0:c1", "normalizedText": "",
          "rowIndex": 0, "cellIndex": 1},
    ]
    rec = fr.make_document_recognition_result(sourceDocumentHash="sha:1",
                                                    cells=cells)
    reqs = fr.build_fill_requirements(rec)
    matches = fr.match_requirements_with_evidence(reqs, res.evidenceSources)
    # match는 sealImageRef→STAMP_OR_SEAL 매핑이 없으므로 0건 (현재 contract)
    # 단, MissingMaterialRequest는 SEAL_IMAGE evidence가 있어도 생성되지 않아야 함
    requests = fr.build_missing_material_requests(reqs, res.evidenceSources, matches)
    assert requests == []


# ── T30: USER_INPUT / MANUAL_ENTRY → needsUserReview 유지 ──────────────

def test_manual_entry_keeps_needs_user_review(ing, fr):
    inp = _input(hint="MANUAL_ENTRY", fields={"projectName": "user filled"})
    res = ing.build_evidence_sources([inp])
    cells = [
        {"cellKey": "t:r0:c0", "normalizedText": "공사명",
          "rowIndex": 0, "cellIndex": 0},
        {"cellKey": "t:r0:c1", "normalizedText": "",
          "rowIndex": 0, "cellIndex": 1},
    ]
    rec = fr.make_document_recognition_result(sourceDocumentHash="sha:1",
                                                    cells=cells)
    reqs = fr.build_fill_requirements(rec)
    matches = fr.match_requirements_with_evidence(reqs, res.evidenceSources)
    assert len(matches) == 1
    assert matches[0]["needsUserReview"] is True


# ── T31: UNKNOWN sourceType도 EvidenceSource 생성 + warning ───────────

def test_unknown_source_type_still_creates_evidence(ing):
    inp = _input(name="random.unknown_ext", ext="xyz",
                    fields={"freeText": "raw text"})
    res = ing.build_evidence_sources([inp])
    assert res.evidenceCount == 1
    assert res.evidenceSources[0]["sourceType"] == "UNKNOWN"
    assert any(w.code == "UNKNOWN_SOURCE_TYPE" for w in res.warnings)


# ── T32: schemaVersion / engineVersion / requestId ─────────────────────

def test_ingestion_result_metadata(ing):
    res = ing.build_evidence_sources([])
    assert res.schemaVersion == ing.SCHEMA_VERSION
    assert res.engineVersion == ing.ENGINE_VERSION
    assert res.requestId


# ── T33: audit script PASS ─────────────────────────────────────────────

def test_audit_script_passes():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "audit_hwpx_fill_review_evidence_ingestion_contract",
        PROJECT_ROOT
        / "scripts/ops/audit_hwpx_fill_review_evidence_ingestion_contract.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    result = mod.run_audit()
    assert result["auditVerdict"] == "PASS", result
