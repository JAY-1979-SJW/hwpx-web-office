"""HWPX-RECOGNITION-CONTENT-CLASSIFIER-CONTRACT-01 tests."""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.hwpx.recognition_corpus import content_classifier as cc
from scripts.hwpx.recognition_corpus import corpus_schema as cs


# ── fixture builders ─────────────────────────────────────────────────────

class FCell:
    def __init__(self, row, col, text, tid="t"):
        self.tableId = tid; self.row = row; self.col = col
        self.normalizedText = text


class FPara:
    def __init__(self, text): self.normalizedText = text


class FRes:
    def __init__(self, tables, paragraphs=()):
        self.tables = tables
        self.paragraphs = list(paragraphs)


class FTable:
    def __init__(self, cells, tid="t"):
        self.tableId = tid; self.cells = cells


def _make_fillable(filename="samples/[별지 1] 신청서.hwpx"):
    cells = []
    for i, label in enumerate(["신청인", "대표자", "주소",
                                  "전화번호", "상호", "성명",
                                  "접수번호", "접수일자"]):
        cells.append(FCell(i, 0, label))
        cells.append(FCell(i, 1, ""))
    res = FRes([FTable(cells)], [FPara("신청서 작성 안내")])
    return cc.extract_content_features(res, filename), filename


def _make_reference(filename="samples/[별표 3] 작성기준.hwpx"):
    cells = []
    for r in range(20):
        for c in range(5):
            cells.append(FCell(r, c, f"기준값{r}-{c}"))
    paras = [FPara("작성기준 및 단위량 산출기준 별표"), FPara("보유기준")]
    res = FRes([FTable(cells)], paras)
    return cc.extract_content_features(res, filename), filename


def _make_empty(filename="tests/fixtures/hwpx/gantt/공정표.hwpx"):
    res = FRes([], [])
    return cc.extract_content_features(res, filename), filename


def _make_inspection(filename="samples/[별지] 점검표.hwpx"):
    cells = [FCell(0, 0, "공사명"), FCell(0, 1, ""),
              FCell(1, 0, "점검자"), FCell(1, 1, "")]
    paras = [FPara("적합 여부 확인"), FPara("점검 결과 양호 또는 불량 확인 여부"),
              FPara("부적합 입니까?")]
    res = FRes([FTable(cells)], paras)
    return cc.extract_content_features(res, filename), filename


def _make_application():
    return _make_fillable("samples/[별지 2] 등록신청서.hwpx")


def _make_plan(filename="samples/[별지] 품질관리계획.hwpx"):
    cells = [FCell(0, 0, "공사명"), FCell(0, 1, ""),
              FCell(1, 0, "착공일"), FCell(1, 1, "")]
    paras = [FPara("품질관리계획서 작성"), FPara("시공계획 및 안전관리계획")]
    res = FRes([FTable(cells)], paras)
    return cc.extract_content_features(res, filename), filename


def _make_contract(filename="samples/[별지] 계약서.hwpx"):
    cells = [FCell(0, 0, "공사명"), FCell(0, 1, ""),
              FCell(1, 0, "계약금액"), FCell(1, 1, "")]
    paras = [FPara("계약 발주자 시공자 착공 준공 계약금액")]
    res = FRes([FTable(cells)], paras)
    return cc.extract_content_features(res, filename), filename


def _make_ambiguous(filename="random.hwpx"):
    # 동률 유도: fillable signals 약함 + reference signals 강함
    cells = [FCell(0, 0, "신청인"), FCell(0, 1, ""),
              FCell(1, 0, "구분"), FCell(1, 1, ""),
              FCell(2, 0, "항목"), FCell(2, 1, "")]
    for r in range(3, 8):
        for c in range(4):
            cells.append(FCell(r, c, "긴설명문장" * 10))
    paras = [FPara("작성기준")]
    res = FRes([FTable(cells)], paras)
    return cc.extract_content_features(res, filename), filename


def _make_unknown_sparse(filename="random.hwpx"):
    # 셀은 있지만 라벨/우측-빈 셀/키워드 모두 없는 잡음 문서
    cells = [FCell(r, c, "잡음" * 20 + f"{r}{c}")
                  for r in range(6) for c in range(6)]
    res = FRes([FTable(cells)], [FPara("의미없는장문잡음내용")])
    return cc.extract_content_features(res, filename), filename


# ── T01 fillable ────────────────────────────────────────────────────────

def test_t01_fillable_form():
    f, fn = _make_fillable()
    r = cc.classify_document_content(f, document_id="d1")
    assert r["contentType"] == "fillable_form"


def test_t02_reference_table():
    f, fn = _make_reference()
    r = cc.classify_document_content(f, document_id="d2")
    assert r["contentType"] == "reference_table"


def test_t03_empty_template():
    f, fn = _make_empty()
    r = cc.classify_document_content(f, document_id="d3")
    assert r["contentType"] == "empty_template"


def test_t04_inspection_subtype():
    f, fn = _make_inspection()
    r = cc.classify_document_content(f, document_id="d4")
    assert r["contentType"] == "fillable_form"
    assert r["subType"] in ("inspection_form", "checklist_form")


def test_t05_application_subtype():
    f, fn = _make_application()
    r = cc.classify_document_content(f, document_id="d5")
    assert r["contentType"] == "fillable_form"
    assert r["subType"] == "application_form"


def test_t06_plan_subtype():
    f, fn = _make_plan()
    r = cc.classify_document_content(f, document_id="d6")
    assert r["contentType"] == "fillable_form"
    assert r["subType"] == "plan_form"


def test_t07_contract_subtype():
    f, fn = _make_contract()
    r = cc.classify_document_content(f, document_id="d7")
    assert r["contentType"] == "fillable_form"
    assert r["subType"] == "contract_form"


def test_t08_unknown_sparse():
    f, fn = _make_unknown_sparse()
    r = cc.classify_document_content(f, filename_type="unknown",
                                          document_id="d8")
    assert r["contentType"] == "unknown"
    assert "UNKNOWN_DOCUMENT_TYPE" in r["warnings"]


def test_t09_agreement_no_disagreement():
    f, fn = _make_fillable()
    r = cc.classify_document_content(f, document_id="d9")
    assert r["disagreement"] is False


def test_t10_disagreement_flagged():
    f, fn = _make_reference()
    # filename은 fillable로 강제 (의도적 불일치)
    r = cc.classify_document_content(f, filename_type="fillable_form",
                                          document_id="d10")
    assert r["disagreement"] is True
    assert "FILENAME_CONTENT_DISAGREEMENT" in r["warnings"]
    assert "NEEDS_HUMAN_REVIEW" in r["warnings"]


def test_t11_ambiguous_close_scores():
    f, fn = _make_ambiguous()
    r = cc.classify_document_content(f, document_id="d11")
    # ambiguous 또는 unknown 인정 (close scores 의도)
    assert r["ambiguous"] or r["contentType"] == "unknown"


def test_t12_ambiguous_review_warning():
    f, fn = _make_ambiguous()
    r = cc.classify_document_content(f, document_id="d12")
    if r["ambiguous"]:
        assert "NEEDS_HUMAN_REVIEW" in r["warnings"]


def test_t13_confidence_in_range():
    for builder in (_make_fillable, _make_reference, _make_empty,
                       _make_unknown_sparse):
        f, _ = builder()
        r = cc.classify_document_content(f, document_id="x")
        assert 0.0 <= r["confidence"] <= 1.0


def test_t14_required_fields_present():
    f, _ = _make_fillable()
    r = cc.classify_document_content(f, document_id="d14")
    for k in ("schemaVersion", "engineVersion", "classifierVersion",
                 "documentId", "filenamePatternType", "contentType",
                 "subType", "confidence", "evidence", "featureSummary",
                 "disagreement", "ambiguous", "warnings"):
        assert k in r, k


def test_t15_feature_summary_fields():
    f, _ = _make_fillable()
    r = cc.classify_document_content(f, document_id="d15")
    fs = r["featureSummary"]
    for k in ("tableCount", "cellCount", "labelOccurrenceCount",
                 "uniqueLabelCount", "rightNeighborEmptyCount",
                 "labelValuePairCandidateCount", "questionSentenceCount",
                 "knownSemanticLabelCount", "unknownLabelCount"):
        assert k in fs, k


def test_t16_evidence_fields():
    f, _ = _make_fillable()
    r = cc.classify_document_content(f, document_id="d16")
    ev = r["evidence"]
    for k in ("matchedRules", "labelExamples", "topLabels", "reason"):
        assert k in ev, k


def test_t17_record_compatible_with_schema():
    f, _ = _make_fillable()
    r = cc.classify_document_content(f, document_id="d17")
    rec = cc.build_document_classification_record(r, classified_at="now")
    assert rec["document_type"] in cc.ALLOWED_DOCUMENT_TYPES
    assert rec["classifier_version"] == "content_classifier_v1"


def test_t18_insert_into_in_memory_db():
    conn = cs.open_corpus_db(":memory:")
    conn.execute(
        "INSERT INTO hwpx_documents "
        "(document_id, source_path, source_kind, file_size, mtime,"
        " detected_type, inventory_status, sha256, first_seen_at) "
        "VALUES (?, '/x.hwpx', 'collected', 1, 1.0, 'hwpx', 'FOUND', ?, 'now')",
        ("docX", "0" * 64),
    )
    f, _ = _make_fillable()
    r = cc.classify_document_content(f, document_id="docX")
    rec = cc.build_document_classification_record(r, classified_at="now")
    conn.execute(
        "INSERT INTO document_classifications "
        "(document_id, classifier_version, document_type, confidence,"
        " evidence_json, classified_at) VALUES (?,?,?,?,?,?)",
        (rec["document_id"], rec["classifier_version"],
            rec["document_type"], rec["confidence"],
            rec["evidence_json"], rec["classified_at"]),
    )
    conn.commit()
    n = conn.execute(
        "SELECT COUNT(*) FROM document_classifications "
        "WHERE classifier_version=?", ("content_classifier_v1",)
    ).fetchone()[0]
    assert n == 1
    conn.close()


def test_t19_unique_constraint_doc_classifier():
    conn = cs.open_corpus_db(":memory:")
    conn.execute(
        "INSERT INTO hwpx_documents "
        "(document_id, source_path, source_kind, file_size, mtime,"
        " detected_type, inventory_status, sha256, first_seen_at) "
        "VALUES (?, '/x', 'collected', 1, 1.0, 'hwpx', 'FOUND', ?, 'now')",
        ("d", "0" * 64))
    for _ in range(2):
        conn.execute(
            "INSERT OR REPLACE INTO document_classifications "
            "(document_id, classifier_version, document_type, confidence,"
            " evidence_json, classified_at) "
            "VALUES (?, 'content_classifier_v1', 'unknown', 0.2, '{}', 'now')",
            ("d",),
        )
    conn.commit()
    n = conn.execute(
        "SELECT COUNT(*) FROM document_classifications WHERE document_id='d'"
    ).fetchone()[0]
    assert n == 1
    conn.close()


def test_t20_disagreements_view_lookup():
    conn = cs.open_corpus_db(":memory:")
    conn.execute(
        "INSERT INTO hwpx_documents "
        "(document_id, source_path, source_kind, file_size, mtime,"
        " detected_type, inventory_status, sha256, first_seen_at) "
        "VALUES (?, '/x', 'collected', 1, 1.0, 'hwpx', 'FOUND', ?, 'now')",
        ("d", "0" * 64))
    conn.execute(
        "INSERT INTO document_classifications "
        "(document_id, classifier_version, document_type, confidence,"
        " evidence_json, classified_at) "
        "VALUES ('d','filename_pattern_v1','reference_table',1.0,'{}','now')")
    conn.execute(
        "INSERT INTO document_classifications "
        "(document_id, classifier_version, document_type, confidence,"
        " evidence_json, classified_at) "
        "VALUES ('d','content_classifier_v1','fillable_form',0.6,'{}','now')")
    conn.commit()
    rows = conn.execute(
        "SELECT * FROM classification_disagreements"
    ).fetchall()
    assert len(rows) == 1
    conn.close()


def test_t21_confidence_alone_not_promotion():
    """confidence 0.99여도 disagreement면 자동 promotion 금지."""
    f, _ = _make_reference()
    r = cc.classify_document_content(f, filename_type="fillable_form",
                                          document_id="d")
    # confidence와 무관하게 disagreement면 NEEDS_HUMAN_REVIEW
    assert r["disagreement"] is True
    assert "NEEDS_HUMAN_REVIEW" in r["warnings"]


def test_t22_production_isolation_for_classifier():
    """production 모듈에 content_classifier import 없음."""
    needles = ("content_classifier", "from scripts.hwpx.recognition_corpus")
    for p in (
        PROJECT_ROOT / "scripts/hwpx/fill_review/fill_review_contract.py",
        PROJECT_ROOT / "scripts/hwpx/fill_review/fill_review_ui_adapter.py",
        PROJECT_ROOT / "scripts/hwpx/fill_review/fill_review_live_pipeline.py",
        PROJECT_ROOT / "scripts/hwpx/pipeline/"
            "generic_edit_plan_writer_executor_live_sandbox.py",
    ):
        if not p.is_file(): continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        for n in needles:
            assert n not in text, f"{p.name} contains {n}"


def test_t23_no_writer_invocation():
    src = (PROJECT_ROOT
            / "scripts/hwpx/recognition_corpus/content_classifier.py"
           ).read_text(encoding="utf-8")
    assert "execute_writer_call_plan_live_sandbox" not in src
    assert "execute_writer_call_plan" not in src


def test_t24_no_output_hwpx_creation():
    src = (PROJECT_ROOT
            / "scripts/hwpx/recognition_corpus/content_classifier.py"
           ).read_text(encoding="utf-8")
    assert ".hwpx" not in src or "[별지]" in src or "별지" in src
    # 핵심: zipfile.ZipFile 쓰기/write 호출 없음
    assert "ZipFile" not in src


def test_t25_no_ai_no_ocr():
    src = (PROJECT_ROOT
            / "scripts/hwpx/recognition_corpus/content_classifier.py"
           ).read_text(encoding="utf-8")
    # 실제 import / 호출 패턴만 검사 (docstring 언급은 허용)
    for n in ("import anthropic", "import openai",
                 "anthropic.Anthropic", "openai.", "pytesseract",
                 "ANTHROPIC_API_KEY=", "OPENAI_API_KEY="):
        assert n not in src


def test_t26_no_secret_in_module():
    src = (PROJECT_ROOT
            / "scripts/hwpx/recognition_corpus/content_classifier.py"
           ).read_text(encoding="utf-8")
    for n in ("sk-", "Bearer ", "DATABASE_URL="):
        assert n not in src


def test_t27_no_default_db_write():
    """기본 동작은 in-memory dict — corpus.sqlite3 write 없음."""
    src = (PROJECT_ROOT
            / "scripts/hwpx/recognition_corpus/content_classifier.py"
           ).read_text(encoding="utf-8")
    assert "open_corpus_db" not in src
    assert "DB_PATH" not in src
    assert "corpus.sqlite3" not in src


def test_t28_helpers_present():
    assert hasattr(cc, "extract_content_features")
    assert hasattr(cc, "classify_document_content")
    assert hasattr(cc, "compare_filename_and_content_classification")
    assert hasattr(cc, "build_document_classification_record")
    assert hasattr(cc, "summarize_classification_disagreements")


def test_t29_compare_helper():
    assert cc.compare_filename_and_content_classification(
        "fillable_form", "reference_table") is True
    assert cc.compare_filename_and_content_classification(
        "unknown", "fillable_form") is False
    assert cc.compare_filename_and_content_classification(
        "fillable_form", "fillable_form") is False


def test_t30_summary_helper():
    rs = [
        {"disagreement": True, "ambiguous": False,
            "filenamePatternType": "fillable_form",
            "contentType": "reference_table",
            "warnings": ["NEEDS_HUMAN_REVIEW"]},
        {"disagreement": False, "ambiguous": True,
            "filenamePatternType": "fillable_form",
            "contentType": "fillable_form",
            "warnings": ["NEEDS_HUMAN_REVIEW"]},
    ]
    s = cc.summarize_classification_disagreements(rs)
    assert s["total"] == 2
    assert s["disagreementCount"] == 1
    assert s["ambiguousCount"] == 1
    assert s["needsHumanReviewCount"] == 2
    assert s["byPair"]["fillable_form->reference_table"] == 1


def test_t31_record_rejects_invalid_doctype():
    f, _ = _make_fillable()
    r = cc.classify_document_content(f, document_id="d")
    r["contentType"] = "inspection_form"  # subType, not allowed in main
    with pytest.raises(ValueError):
        cc.build_document_classification_record(r, classified_at="now")


def test_t32_schema_isolation_still_holds():
    iso = cs.audit_production_isolation()
    assert iso["ok"] is True, iso["violations"]
