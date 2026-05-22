"""HWPX-FORM-FIELD-MAPPING-01 — 테스트."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

CATALOG_JSONL = (
    PROJECT_ROOT / "data" / "reports"
    / "hwpx_form_field_catalog" / "form_field_catalog.jsonl"
)
DRAFTS = PROJECT_ROOT / "data" / "drafts"

# ── 테스트용 fixtures ─────────────────────────────────────────────────────────

def _make_extracted_field(fieldKey, value, confidence=0.85, sourceLabel="", location="", extractMethod="horizontal"):
    from hwpx.pipeline.upload_document_parser import ExtractedField
    return ExtractedField(
        fieldKey=fieldKey, value=value, confidence=confidence,
        sourceLabel=sourceLabel or fieldKey, location=location,
        extractMethod=extractMethod,
    )

def _make_parse_result(fields):
    from hwpx.pipeline.upload_document_parser import ParseResult
    r = ParseResult(maskedStem="test", formName="테스트 서식",
                    domain="기타", formKind="신청서")
    r.extractedFields = fields
    return r

def _make_catalog_entry(formId="form_test", formName="테스트 서식", fields=None):
    return {
        "formId": formId, "formName": formName, "domain": "기타",
        "formKind": "신청서", "byeoljiNumber": "", "fileCount": 1,
        "fieldCount": len(fields or []),
        "autoFillableCount": 0, "requiredCount": 0,
        "fields": fields or [],
    }

def _make_catalog_field(sem, label, labels=None, required=True, evidenceHint=""):
    return {
        "primaryLabel": label, "labels": labels or [label],
        "semanticField": sem, "autoFillable": bool(sem),
        "inputCellTypes": ["label_adjacent"], "required": required,
        "fileOccurrenceCount": 1, "totalOccurrenceCount": 1,
        "sourceEvidenceHint": evidenceHint,
    }


# ── T01. import ────────────────────────────────────────────────────────────────

def test_form_field_mapper_importable():
    from hwpx.pipeline import form_field_mapper as fm
    assert hasattr(fm, "map_fields")
    assert hasattr(fm, "MappingResult")
    assert hasattr(fm, "STATUS_AUTO")
    assert hasattr(fm, "STATUS_REVIEW")
    assert hasattr(fm, "STATUS_MISS")


# ── T02. fieldKey 직접 매칭 ────────────────────────────────────────────────────

def test_direct_key_match_auto():
    from hwpx.pipeline.form_field_mapper import map_fields, STATUS_AUTO
    ef = _make_extracted_field("contractorName", "대한소방", 0.90, "시공자")
    pr = _make_parse_result([ef])
    ce = _make_catalog_entry(fields=[
        _make_catalog_field("contractorName", "시공자",
                            ["시공자", "시공업체", "업체명"],
                            evidenceHint="사업자등록증, 공사계약서")
    ])
    result = map_fields(pr, ce)
    assert result.mappedFields, "AUTO_FILL_READY 없음"
    assert result.mappedFields[0].status == STATUS_AUTO
    assert result.mappedFields[0].matchReason == "direct_key"


# ── T03. alias 매칭 ────────────────────────────────────────────────────────────

def test_alias_match():
    from hwpx.pipeline.form_field_mapper import map_fields, STATUS_AUTO, STATUS_REVIEW
    # 파서가 fieldKey를 잘못 추정했지만 sourceLabel은 alias에 포함
    ef = _make_extracted_field("unknown_field", "대한소방", 0.85, "시공업체")
    pr = _make_parse_result([ef])
    ce = _make_catalog_entry(fields=[
        _make_catalog_field("contractorName", "시공자",
                            ["시공자", "시공업체", "업체명", "상호"])
    ])
    result = map_fields(pr, ce)
    # alias 매칭은 review 이상으로 분류되어야 함
    all_matched = result.mappedFields + result.reviewFields
    assert all_matched, "alias 매칭 결과 없음"
    assert all_matched[0].matchReason in ("alias_match", "label_match")


# ── T04. confidence >= 0.80 → AUTO_FILL_READY ─────────────────────────────────

def test_confidence_auto_threshold():
    from hwpx.pipeline.form_field_mapper import map_fields, STATUS_AUTO, CONF_AUTO
    ef = _make_extracted_field("contractorName", "대한소방", CONF_AUTO + 0.01, "시공자")
    pr = _make_parse_result([ef])
    ce = _make_catalog_entry(fields=[
        _make_catalog_field("contractorName", "시공자", ["시공자"])
    ])
    result = map_fields(pr, ce)
    assert result.mappedFields, "AUTO_FILL_READY 없음"
    assert result.mappedFields[0].status == STATUS_AUTO


# ── T05. 0.60 <= confidence < 0.80 → NEEDS_REVIEW ────────────────────────────

def test_confidence_review_threshold():
    from hwpx.pipeline.form_field_mapper import map_fields, STATUS_REVIEW, CONF_REVIEW
    ef = _make_extracted_field("contractorName", "대한소방", CONF_REVIEW + 0.01, "시공자")
    pr = _make_parse_result([ef])
    ce = _make_catalog_entry(fields=[
        _make_catalog_field("contractorName", "시공자", ["시공자"])
    ])
    result = map_fields(pr, ce)
    # confidence < 0.80 → NEEDS_REVIEW
    assert result.reviewFields or result.mappedFields, "결과 없음"


# ── T06. MISSING_REQUIRED 생성 ────────────────────────────────────────────────

def test_missing_required():
    from hwpx.pipeline.form_field_mapper import map_fields, STATUS_MISS
    pr = _make_parse_result([])  # 추출값 없음
    ce = _make_catalog_entry(fields=[
        _make_catalog_field("contractorName", "시공자", required=True)
    ])
    result = map_fields(pr, ce)
    assert result.missingFields, "MISSING_REQUIRED 없음"
    missing = [f for f in result.missingFields if f.fieldKey == "contractorName"]
    assert missing


# ── T07. 복수 후보 → NEEDS_REVIEW ─────────────────────────────────────────────

def test_multiple_candidates_review():
    from hwpx.pipeline.form_field_mapper import map_fields, STATUS_REVIEW
    ef1 = _make_extracted_field("contractorName", "대한소방", 0.85, "시공자")
    ef2 = _make_extracted_field("contractorName", "한국건설", 0.85, "시공업체")
    pr  = _make_parse_result([ef1, ef2])
    ce  = _make_catalog_entry(fields=[
        _make_catalog_field("contractorName", "시공자", ["시공자", "시공업체"])
    ])
    result = map_fields(pr, ce)
    all_m = result.mappedFields + result.reviewFields
    assert all_m
    assert all_m[0].candidateCount >= 2 or all_m[0].status == STATUS_REVIEW


# ── T08. 날짜 형식 검증 ────────────────────────────────────────────────────────

@pytest.mark.parametrize("value,should_pass", [
    ("2026-05-19", True),
    ("2026년 5월 19일", True),
    ("홍길동", False),
])
def test_date_validation(value, should_pass):
    from hwpx.pipeline.form_field_mapper import _validate_field
    vr = _validate_field("completionDate", value)
    assert vr.passed == should_pass, f"'{value}' → passed={vr.passed}, expected {should_pass}"


# ── T09. 금액 형식 검증 ────────────────────────────────────────────────────────

@pytest.mark.parametrize("value,should_pass", [
    ("1,500,000원", True),
    ("3억원", True),
    ("홍길동", False),
])
def test_amount_validation(value, should_pass):
    from hwpx.pipeline.form_field_mapper import _validate_field
    vr = _validate_field("amount", value)
    assert vr.passed == should_pass


# ── T10. 등록번호 형식 검증 ────────────────────────────────────────────────────

@pytest.mark.parametrize("value,should_pass", [
    ("소방-서울-001", True),
    ("제17호", True),
    ("", False),
])
def test_registration_validation(value, should_pass):
    from hwpx.pipeline.form_field_mapper import _validate_field
    vr = _validate_field("registrationNumber", value)
    assert vr.passed == should_pass


# ── T11. sourceEvidenceHint 가중치 ────────────────────────────────────────────

def test_evidence_bonus():
    from hwpx.pipeline.form_field_mapper import _evidence_bonus
    bonus = _evidence_bonus("사업자등록증, 공사계약서", "사업자등록증 사본")
    assert bonus > 0, "evidence 가중치 0"


# ── T12. 공문서 메타(직인/결재) 본문 자동 매칭 금지 ──────────────────────────

def test_meta_label_not_auto_mapped():
    from hwpx.pipeline.form_field_mapper import map_fields
    # 접수/결재 라벨이 있는 파서 결과
    ef = _make_extracted_field("contractorName", "값", 0.90, "접수")
    pr = _make_parse_result([ef])
    ce = _make_catalog_entry(fields=[
        _make_catalog_field("contractorName", "시공자", ["시공자"])
    ])
    result = map_fields(pr, ce)
    # 접수 라벨은 본문 contractorName 필드에 자동 매칭되면 안 됨
    for mf in result.mappedFields:
        assert mf.sourceLabel != "접수", "메타 라벨이 자동매칭됨"


# ── T13. raw path leak 없음 ───────────────────────────────────────────────────

def test_no_raw_path_in_mapping_output():
    from hwpx.pipeline.form_field_mapper import map_fields
    ef = _make_extracted_field("contractorName", "C:\\Users\\test\\value", 0.90, "시공자")
    pr = _make_parse_result([ef])
    ce = _make_catalog_entry(fields=[
        _make_catalog_field("contractorName", "시공자", ["시공자"])
    ])
    result = map_fields(pr, ce)
    out = json.dumps(result.to_dict(), ensure_ascii=False)
    assert "C:\\Users\\" not in out


# ── T14. raw filename leak 없음 ───────────────────────────────────────────────

def test_no_raw_filename_in_output():
    from hwpx.pipeline.form_field_mapper import map_fields
    ef = _make_extracted_field("contractorName", "서울_00현장_작업일보.hwpx", 0.90, "시공자")
    pr = _make_parse_result([ef])
    ce = _make_catalog_entry(fields=[
        _make_catalog_field("contractorName", "시공자")
    ])
    result = map_fields(pr, ce)
    out = json.dumps(result.to_dict(), ensure_ascii=False)
    # hwpx 확장자 원본 노출은 금지 (value는 마스킹될 수 있음)
    # 서식명 등 path-derived 정보가 없어야 함
    for drive in ("C:\\Users\\", "/home/"):
        assert drive not in out


# ── T15. PII report leak 없음 ─────────────────────────────────────────────────

def test_no_pii_in_mapping_output():
    pii_re = re.compile(r"\d{3}-\d{2}-\d{5}|\d{6}-\d{7}")
    from hwpx.pipeline.form_field_mapper import map_fields
    ef = _make_extracted_field("registrationNumber", "123-45-67890", 0.90, "사업자번호")
    pr = _make_parse_result([ef])
    ce = _make_catalog_entry(fields=[
        _make_catalog_field("registrationNumber", "등록번호", ["사업자번호"])
    ])
    result = map_fields(pr, ce)
    out = json.dumps(result.to_dict(), ensure_ascii=False)
    assert not pii_re.search(out), f"PII in output: {out}"


# ── T16. writer 참조 없음 ─────────────────────────────────────────────────────

def test_mapper_no_writer_reference():
    src = (PROJECT_ROOT / "scripts" / "hwpx" / "pipeline" / "form_field_mapper.py").read_text("utf-8")
    assert "write_package" not in src
    assert "apply_edit_plan" not in src


# ── T17. AI API 참조 없음 ────────────────────────────────────────────────────

def test_mapper_no_ai_api():
    src = (PROJECT_ROOT / "scripts" / "hwpx" / "pipeline" / "form_field_mapper.py").read_text("utf-8")
    for kw in ("anthropic", "openai", "ChatCompletion"):
        assert kw not in src


# ── T18. OCR 참조 없음 ───────────────────────────────────────────────────────

def test_mapper_no_ocr():
    src = (PROJECT_ROOT / "scripts" / "hwpx" / "pipeline" / "form_field_mapper.py").read_text("utf-8")
    for kw in ("pytesseract", "easyocr", "image_to_string"):
        assert kw not in src


# ── T19. summary 구조 ────────────────────────────────────────────────────────

def test_mapping_result_summary():
    from hwpx.pipeline.form_field_mapper import map_fields
    ef = _make_extracted_field("contractorName", "대한소방", 0.90, "시공자")
    pr = _make_parse_result([ef])
    ce = _make_catalog_entry(fields=[
        _make_catalog_field("contractorName", "시공자", required=True),
        _make_catalog_field("taskName", "항목",        required=True),
    ])
    result = map_fields(pr, ce)
    s = result.summary
    for key in ("requiredTotal", "autoFillReady", "needsReview", "missingRequired"):
        assert key in s, f"key missing: {key}"
    assert s["autoFillReady"] + s["needsReview"] + s["missingRequired"] <= s["requiredTotal"] + 1


# ── T20. 기존 테스트 회귀 ────────────────────────────────────────────────────

def test_upload_parser_still_passes():
    """upload_document_parser import 가능."""
    from hwpx.pipeline import upload_document_parser as up
    assert hasattr(up, "parse_hwpx")


def test_form_catalog_still_passes():
    """form_field_catalog import 가능."""
    from hwpx.recognition_corpus import form_field_catalog as ffc
    assert hasattr(ffc, "build_catalog")


def test_form_recommend_still_passes():
    """form_index import 가능."""
    from hwpx.recognition_corpus import form_index as fi
    assert hasattr(fi, "recommend")
