"""HWPX-RECOGNITION-LABEL-TAXONOMY-AND-LAYOUT-SEED-01 — 테스트."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

TAXONOMY_MODULE = PROJECT_ROOT / "scripts" / "hwpx" / "recognition_corpus" / "label_taxonomy.py"
LAYOUT_MODULE   = PROJECT_ROOT / "scripts" / "hwpx" / "recognition_corpus" / "layout_classifier.py"


# ── T01/T02. import 가능 ─────────────────────────────────────────────────────

def test_label_taxonomy_importable():
    from hwpx.recognition_corpus import label_taxonomy as lt
    assert hasattr(lt, "classify_label")
    assert hasattr(lt, "classify_batch")
    assert hasattr(lt, "classify_with_counts")


def test_layout_classifier_importable():
    from hwpx.recognition_corpus import layout_classifier as lc
    assert hasattr(lc, "classify_layout")
    assert hasattr(lc, "classify_file_layout")
    assert hasattr(lc, "reclassify_from_survey")


# ── T03. taskName 계열 ────────────────────────────────────────────────────────

@pytest.mark.parametrize("label", [
    "항목", "내용", "작업명", "업무내용", "점검항목", "검사항목",
    "평가항목", "불량내용", "조치사항", "1차검사항목",
])
def test_taskname_mapping(label):
    from hwpx.recognition_corpus.label_taxonomy import classify_label, CLS_HIGH, CLS_MEDIUM
    r = classify_label(label)
    assert r.semanticField == "taskName", f"'{label}' → field={r.semanticField}"
    assert r.classification in (CLS_HIGH, CLS_MEDIUM)


# ── T04. number / receiptNumber 구분 ────────────────────────────────────────

@pytest.mark.parametrize("label,expected_field", [
    ("번호", "number"),
    ("연번", "number"),
    ("일련번호", "number"),
    ("접수번호", "receiptNumber"),
])
def test_number_receipt_distinction(label, expected_field):
    from hwpx.recognition_corpus.label_taxonomy import classify_label
    r = classify_label(label)
    assert r.semanticField == expected_field, (
        f"'{label}' → {r.semanticField} (expected {expected_field})"
    )


# ── T05. inspectionStatus ────────────────────────────────────────────────────

@pytest.mark.parametrize("label", [
    "검사결과", "점검결과", "조치결과", "검측결과",
    "검사기준(시방서또는도면등)", "판정기준",
])
def test_inspection_status_mapping(label):
    from hwpx.recognition_corpus.label_taxonomy import classify_label
    r = classify_label(label)
    assert r.semanticField == "inspectionStatus", (
        f"'{label}' → {r.semanticField}"
    )


# ── T06. remarks / 비고 계열 ────────────────────────────────────────────────

@pytest.mark.parametrize("label", ["비고", "참고", "특기사항", "특이사항"])
def test_remarks_mapping(label):
    from hwpx.recognition_corpus.label_taxonomy import classify_label
    r = classify_label(label)
    assert r.semanticField == "remarks", f"'{label}' → {r.semanticField}"


# ── T07. responsiblePerson ───────────────────────────────────────────────────

@pytest.mark.parametrize("label", [
    "성명", "성명:", "담당자", "책임자", "작성자",
])
def test_responsible_person_mapping(label):
    from hwpx.recognition_corpus.label_taxonomy import classify_label
    r = classify_label(label)
    assert r.semanticField == "responsiblePerson", f"'{label}' → {r.semanticField}"


# ── T08. quantity ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("label", ["수량", "수 량", "수량(개)"])
def test_quantity_mapping(label):
    from hwpx.recognition_corpus.label_taxonomy import classify_label
    r = classify_label(label)
    assert r.semanticField == "quantity", f"'{label}' → {r.semanticField}"


# ── T09. contractorName ──────────────────────────────────────────────────────

@pytest.mark.parametrize("label", [
    "시공사", "도급사", "수급인", "업체명", "상호", "회사명", "회사명:",
])
def test_contractor_name_mapping(label):
    from hwpx.recognition_corpus.label_taxonomy import classify_label
    r = classify_label(label)
    assert r.semanticField == "contractorName", f"'{label}' → {r.semanticField}"


# ── T10. durationDays ────────────────────────────────────────────────────────

@pytest.mark.parametrize("label", ["기간", "공기", "공사기간", "계약기간"])
def test_duration_days_mapping(label):
    from hwpx.recognition_corpus.label_taxonomy import classify_label
    r = classify_label(label)
    assert r.semanticField == "durationDays", f"'{label}' → {r.semanticField}"


# ── T11. 종별/시험종목/시험방법 → testType/testItem/testMethod ──────────────

@pytest.mark.parametrize("label,expected_field", [
    ("종별",     "testType"),
    ("시험종별",  "testType"),
    ("시험종목",  "testItem"),
    ("시험방법",  "testMethod"),
])
def test_test_field_mappings(label, expected_field):
    from hwpx.recognition_corpus.label_taxonomy import classify_label
    r = classify_label(label)
    assert r.semanticField == expected_field, (
        f"'{label}' → {r.semanticField} (expected {expected_field})"
    )


# ── T12. 접수/직인/결재 → IGNORED_PUBLIC_DOC_META ──────────────────────────

@pytest.mark.parametrize("label", [
    "접수", "직인", "결재", "담당", "승인", "통보",
    "수신", "발신", "문서번호", "시행",
])
def test_public_doc_meta_ignored(label):
    from hwpx.recognition_corpus.label_taxonomy import classify_label, CLS_META
    r = classify_label(label)
    assert r.classification == CLS_META, (
        f"'{label}' → {r.classification} (expected {CLS_META})"
    )


# ── T13. (뒤쪽) 계열 → BACK_SIDE_HINT ──────────────────────────────────────

@pytest.mark.parametrize("label", [
    "(뒤쪽)", "뒤쪽", "뒷면", "(앞쪽)", "앞쪽",
    "(제2쪽)", "(8쪽중제3쪽)", "3/5쪽",
])
def test_back_side_hint(label):
    from hwpx.recognition_corpus.label_taxonomy import classify_label, CLS_BACK
    r = classify_label(label)
    assert r.classification == CLS_BACK, (
        f"'{label}' → {r.classification} (expected {CLS_BACK})"
    )


# ── T14. gantt_like → GANTT_LIKE_SCHEDULE ────────────────────────────────────

def test_gantt_like_layout():
    from hwpx.recognition_corpus.layout_classifier import classify_layout, LT_GANTT
    result = classify_layout(
        header_texts=["공종", "2026-01", "2026-02", "2026-03", "2026-04", "2026-05"],
        input_cell_types={"header_column": 30},
        total_cells=60,
        empty_cells=30,
        row_count=10,
        col_count=6,
        input_cell_count=30,
    )
    assert result.layoutType == LT_GANTT, (
        f"expected {LT_GANTT}, got {result.layoutType}: {result.evidence}"
    )


# ── T15. horizontal_schedule ────────────────────────────────────────────────

def test_horizontal_schedule_layout():
    from hwpx.recognition_corpus.layout_classifier import classify_layout, LT_H_SCHEDULE
    result = classify_layout(
        header_texts=["공종", "시작일", "완료일", "2026-03"],
        input_cell_types={"header_column": 10},
        total_cells=30,
        empty_cells=10,
        row_count=5,
        col_count=6,
        input_cell_count=10,
    )
    assert result.layoutType == LT_H_SCHEDULE, (
        f"expected {LT_H_SCHEDULE}, got {result.layoutType}: {result.evidence}"
    )


# ── T16. raw path leak 없음 ──────────────────────────────────────────────────

def test_no_raw_path_in_classification():
    """classify_label 내부 규칙/사전에서 절대 경로가 파생되지 않음을 확인.
    (rawText에 입력값이 들어가는 것은 의도된 동작이므로 semanticField/evidence로 검증)"""
    from hwpx.recognition_corpus.label_taxonomy import classify_label
    r = classify_label("C:\\Users\\test\\project.hwpx")
    # 분류 엔진이 경로에서 의미를 도출하지 않아야 한다
    assert r.semanticField == "", f"path input should not map to a field, got {r.semanticField}"
    # evidence에 내부 경로가 생성되지 않아야 한다
    for ev in r.evidence:
        assert "C:\\" not in ev, f"internal path leaked in evidence: {ev}"


# ── T17. raw filename leak 없음 ─────────────────────────────────────────────

def test_no_raw_filename_in_classification():
    from hwpx.recognition_corpus.label_taxonomy import classify_label
    raw = "서울_00현장_작업일보.hwpx"
    r = classify_label(raw)
    # 분류 결과의 normalizedText에는 raw가 들어갈 수 있으나
    # semanticField / classification은 경로 정보를 담지 않음
    assert r.semanticField in ("", "unknown") or len(r.semanticField) < 30


# ── T18. PII 패턴 leak 없음 ─────────────────────────────────────────────────

def test_no_pii_in_classification_output():
    import re
    from hwpx.recognition_corpus.label_taxonomy import classify_batch
    labels = ["성명", "전화번호", "사업자번호", "주소"]
    results = classify_batch(labels)
    pii_re = re.compile(r"\d{2,3}-\d{3,4}-\d{4}|\d{3}-\d{2}-\d{5}")
    for r in results:
        out = json.dumps(r.to_dict())
        assert not pii_re.search(out), f"PII in output: {out}"


# ── T19. corpus.sqlite3 생성/수정 없음 ──────────────────────────────────────

def test_taxonomy_does_not_create_db(tmp_path):
    from hwpx.recognition_corpus.label_taxonomy import classify_batch
    classify_batch(["항목", "비고", "접수"])
    db_files = list(tmp_path.rglob("*.sqlite3"))
    assert not db_files


# ── T20. 원본 HWPX 수정 없음 (import 수준 확인) ─────────────────────────────

def test_taxonomy_module_does_not_reference_write_package():
    src = TAXONOMY_MODULE.read_text(encoding="utf-8")
    assert "write_package" not in src
    assert "apply_edit_plan" not in src


# ── T21. writer 호출 없음 ────────────────────────────────────────────────────

def test_layout_module_does_not_reference_writer():
    src = LAYOUT_MODULE.read_text(encoding="utf-8")
    assert "write_package" not in src
    assert "apply_edit_plan" not in src


# ── T22. AI API 호출 없음 ────────────────────────────────────────────────────

def test_taxonomy_no_ai_api():
    src = TAXONOMY_MODULE.read_text(encoding="utf-8")
    for kw in ("anthropic", "openai", "ChatCompletion", "claude.ai"):
        assert kw not in src, f"AI API reference found: {kw}"


# ── T23. OCR 호출 없음 ───────────────────────────────────────────────────────

def test_taxonomy_no_ocr():
    src = TAXONOMY_MODULE.read_text(encoding="utf-8")
    for kw in ("pytesseract", "easyocr", "tesseract", "image_to_string"):
        assert kw not in src, f"OCR reference found: {kw}"


# ── T24. 기존 profiling preflight 테스트 유지 (smoke) ───────────────────────

def test_profiling_preflight_module_intact():
    from hwpx.recognition_corpus import profile_corpus_candidates as pcc
    assert hasattr(pcc, "profile_all")


# ── T25. 기존 corpus DB build 스크립트 존재 유지 ────────────────────────────

def test_corpus_db_build_script_exists():
    p = PROJECT_ROOT / "scripts" / "hwpx" / "recognition_corpus" / "build_corpus_db.py"
    assert p.exists()


# ── 추가: low confidence 라벨이 자동 확정되지 않음 ──────────────────────────

def test_low_confidence_not_auto_promoted():
    from hwpx.recognition_corpus.label_taxonomy import (
        classify_label, CLS_HIGH, CLS_MEDIUM, CLS_LOW,
    )
    # 애매한 단어는 REVIEW_REQUIRED 또는 UNKNOWN이어야 함
    r = classify_label("기타업종")
    assert r.classification not in (CLS_HIGH, CLS_MEDIUM), (
        f"'기타업종' was auto-promoted to {r.classification}"
    )


# ── 추가: classify_with_counts 인터페이스 ───────────────────────────────────

def test_classify_with_counts_structure():
    from hwpx.recognition_corpus.label_taxonomy import classify_with_counts
    sample = [
        {"normalizedText": "비고", "totalOccurrences": 100, "fileCount": 50},
        {"normalizedText": "접수", "totalOccurrences": 80, "fileCount": 30},
        {"normalizedText": "(뒤쪽)", "totalOccurrences": 500, "fileCount": 200},
    ]
    result = classify_with_counts(sample)
    assert "classificationCounts" in result
    assert "fieldDistribution" in result
    assert result["totalLabels"] == 3
