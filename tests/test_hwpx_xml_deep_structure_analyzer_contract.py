"""HWPX-XML-DEEP-STRUCTURE-ANALYZER-CONTRACT-01 tests.

deterministic XML fixture 기반 감리검사. writer 미호출, output 미생성,
AI/OCR 미호출, secret 미출력. B동(진단동) 격리 확인.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def an():
    from scripts.hwpx.recognition_corpus import xml_deep_structure_analyzer as m
    return m


# ── T01 모듈 contract ───────────────────────────────────────────────────────

def test_t01_contract_name(an):
    assert an.CONTRACT_NAME == "HWPX-XML-DEEP-STRUCTURE-ANALYZER-CONTRACT-01"


def test_t02_required_analyzers_exist(an):
    for name in an.REQUIRED_ANALYZER_NAMES:
        assert hasattr(an, name), name


def test_t03_reason_code_set(an):
    assert "RUN_BOUNDARY_UNSUPPORTED" in an.ALLOWED_REASON_CODE
    assert len(an.ALLOWED_REASON_CODE) == 9


def test_t04_severity_set(an):
    assert an.ALLOWED_SEVERITY == frozenset({"LOW", "MEDIUM", "HIGH"})


def test_t05_invalid_reason_rejected(an):
    with pytest.raises(ValueError):
        an._make_flag(reason_code="BOGUS", severity="LOW")


def test_t06_invalid_severity_rejected(an):
    with pytest.raises(ValueError):
        an._make_flag(reason_code="READBACK_MISMATCH", severity="BOGUS")


# ── T10 run boundary ────────────────────────────────────────────────────────

_SINGLE_RUN = (
    "<p xmlns='hp'><run><t>공사명: ○○건축공사</t></run></p>"
)
_TWO_RUN = (
    "<p xmlns='hp'>"
    "<run><t>공사명: </t></run>"
    "<run><t>○○건축공사</t></run>"
    "</p>"
)
_THREE_RUN = (
    "<p xmlns='hp'>"
    "<run><t>공사명: </t></run>"
    "<run><t>[</t></run>"
    "<run><t>○○건축공사]</t></run>"
    "</p>"
)


def test_t10_run_boundary_single_run_ok(an):
    assert an.analyze_run_boundary(_SINGLE_RUN) is None


def test_t11_run_boundary_two_runs_medium(an):
    f = an.analyze_run_boundary(_TWO_RUN)
    assert f and f["reason_code"] == "RUN_BOUNDARY_UNSUPPORTED"
    assert f["severity"] == "MEDIUM"


def test_t12_run_boundary_three_runs_high(an):
    f = an.analyze_run_boundary(_THREE_RUN)
    assert f["severity"] == "HIGH"


def test_t13_run_boundary_parse_error(an):
    f = an.analyze_run_boundary("<not xml<<<")
    assert f and f["reason_code"] == "RUN_BOUNDARY_UNSUPPORTED"
    assert f["severity"] == "HIGH"


# ── T20 checkbox/shape ──────────────────────────────────────────────────────

_CHECKBOX_XML = "<p xmlns='hp'><ctrlCheck/></p>"
_SHAPE_XML = "<p xmlns='hp'><rect/></p>"
_PLAIN_XML = "<p xmlns='hp'><run><t>abc</t></run></p>"


def test_t20_checkbox_detected(an):
    f = an.analyze_checkbox_or_shape(_CHECKBOX_XML)
    assert f and f["severity"] == "HIGH"


def test_t21_shape_detected(an):
    f = an.analyze_checkbox_or_shape(_SHAPE_XML)
    assert f and f["severity"] == "MEDIUM"


def test_t22_plain_no_flag(an):
    assert an.analyze_checkbox_or_shape(_PLAIN_XML) is None


# ── T30 object anchor ───────────────────────────────────────────────────────

_OBJ_ONE = "<p xmlns='hp'><pic/></p>"
_OBJ_MANY = "<p xmlns='hp'><pic/><equation/></p>"


def test_t30_object_one(an):
    f = an.analyze_object_anchor(_OBJ_ONE)
    assert f and f["severity"] == "MEDIUM"


def test_t31_object_many(an):
    f = an.analyze_object_anchor(_OBJ_MANY)
    assert f["severity"] == "HIGH"
    assert f["context"]["objectNodeCount"] == 2


def test_t32_object_none(an):
    assert an.analyze_object_anchor(_PLAIN_XML) is None


# ── T40 style resolution ────────────────────────────────────────────────────

_STYLE_SAME = (
    "<p xmlns='hp'>"
    "<run charPrIDRef='1'><t>a</t></run>"
    "<run charPrIDRef='1'><t>b</t></run>"
    "</p>"
)
_STYLE_TWO = (
    "<p xmlns='hp'>"
    "<run charPrIDRef='1'><t>a</t></run>"
    "<run charPrIDRef='2'><t>b</t></run>"
    "</p>"
)
_STYLE_THREE = (
    "<p xmlns='hp'>"
    "<run charPrIDRef='1'><t>a</t></run>"
    "<run charPrIDRef='2'><t>b</t></run>"
    "<run charPrIDRef='3'><t>c</t></run>"
    "</p>"
)


def test_t40_style_same(an):
    assert an.analyze_style_resolution(_STYLE_SAME) is None


def test_t41_style_two(an):
    f = an.analyze_style_resolution(_STYLE_TWO)
    assert f and f["severity"] == "MEDIUM"


def test_t42_style_three(an):
    f = an.analyze_style_resolution(_STYLE_THREE)
    assert f["severity"] == "HIGH"


# ── T50 cell internal paragraph ─────────────────────────────────────────────

_CELL_ONE_P = (
    "<tc xmlns='hp'><p><run><t>x</t></run></p></tc>"
)
_CELL_ZERO_P = "<tc xmlns='hp'></tc>"
_CELL_TWO_P = (
    "<tc xmlns='hp'>"
    "<p><run><t>a</t></run></p>"
    "<p><run><t>b</t></run></p>"
    "</tc>"
)


def test_t50_cell_one_paragraph_ok(an):
    assert an.analyze_cell_internal_paragraph(_CELL_ONE_P) is None


def test_t51_cell_zero_paragraph_high(an):
    f = an.analyze_cell_internal_paragraph(_CELL_ZERO_P)
    assert f and f["severity"] == "HIGH"
    assert f["context"]["paragraphCount"] == 0


def test_t52_cell_two_paragraph_medium(an):
    f = an.analyze_cell_internal_paragraph(_CELL_TWO_P)
    assert f["severity"] == "MEDIUM"
    assert f["context"]["paragraphCount"] == 2


# ── T60 merged cell ─────────────────────────────────────────────────────────

_CELL_NORMAL = "<tc xmlns='hp' rowSpan='1' colSpan='1'><p/></tc>"
_CELL_ROW_MERGED = "<tc xmlns='hp' rowSpan='2' colSpan='1'><p/></tc>"
_CELL_MULTI_MERGED = (
    "<tbl xmlns='hp'>"
    "<tc rowSpan='2' colSpan='2'><p/></tc>"
    "<tc rowSpan='1' colSpan='1' hidden='1'><p/></tc>"
    "</tbl>"
)


def test_t60_cell_normal(an):
    assert an.analyze_merged_cell_geometry(_CELL_NORMAL) is None


def test_t61_cell_row_merged(an):
    f = an.analyze_merged_cell_geometry(_CELL_ROW_MERGED)
    assert f and f["severity"] == "MEDIUM"


def test_t62_cell_multi_merged(an):
    f = an.analyze_merged_cell_geometry(_CELL_MULTI_MERGED)
    assert f["severity"] == "HIGH"
    assert len(f["context"]["mergedCells"]) == 2


# ── T70 readback mismatch ───────────────────────────────────────────────────

def test_t70_readback_match_no_flag(an):
    assert an.analyze_readback_mismatch(expected_hash="a",
                                              actual_hash="a") is None


def test_t71_readback_mismatch_flag(an):
    f = an.analyze_readback_mismatch(expected_hash="a", actual_hash="b")
    assert f and f["reason_code"] == "READBACK_MISMATCH"
    assert f["severity"] == "HIGH"


def test_t72_readback_none_no_flag(an):
    assert an.analyze_readback_mismatch(expected_hash=None,
                                              actual_hash="a") is None


# ── T80 target ambiguous ────────────────────────────────────────────────────

def test_t80_single_target_no_flag(an):
    assert an.analyze_target_ambiguous(candidate_targets=["t1"]) is None


def test_t81_two_targets_medium(an):
    f = an.analyze_target_ambiguous(candidate_targets=["t1", "t2"])
    assert f and f["severity"] == "MEDIUM"


def test_t82_three_targets_high(an):
    f = an.analyze_target_ambiguous(candidate_targets=["t1", "t2", "t3"])
    assert f["severity"] == "HIGH"


def test_t83_dedupe_candidates(an):
    f = an.analyze_target_ambiguous(candidate_targets=["t1", "t1"])
    assert f is None


# ── T90 label context sufficiency ───────────────────────────────────────────

def test_t90_missing_label(an):
    f = an.analyze_label_context_sufficiency(
        normalized_label=None, neighbor_text=None)
    assert f["severity"] == "HIGH"
    assert f["context"]["missingLabel"] is True


def test_t91_short_label(an):
    f = an.analyze_label_context_sufficiency(
        normalized_label="ㄱ", neighbor_text="x")
    assert f["severity"] == "HIGH"


def test_t92_no_neighbor(an):
    f = an.analyze_label_context_sufficiency(
        normalized_label="공사명", neighbor_text="")
    assert f["severity"] == "MEDIUM"


def test_t93_high_occurrence_low_doc(an):
    f = an.analyze_label_context_sufficiency(
        normalized_label="공사명", neighbor_text="...",
        occurrence_count=500, document_count=3)
    assert f and f["severity"] == "LOW"


def test_t94_sufficient_label(an):
    f = an.analyze_label_context_sufficiency(
        normalized_label="공사명", neighbor_text="현장 주소",
        occurrence_count=500, document_count=300)
    assert f is None


# ── T100 통합 진단 ──────────────────────────────────────────────────────────

def test_t100_diagnose_session_collects_all(an):
    flags = an.diagnose_session(
        paragraph_xml_list=[
            {"xml": _THREE_RUN, "target_key": "tk1",
                "normalized_label": "공사명"},
        ],
        cell_xml_list=[
            {"xml": _CELL_ZERO_P, "target_key": "tk2"},
        ],
        element_xml_list=[
            {"xml": _CHECKBOX_XML, "target_key": "tk3"},
        ],
        readback_checks=[
            {"expected_hash": "a", "actual_hash": "b",
                "target_key": "tk4"},
        ],
        ambiguity_checks=[
            {"candidate_targets": ["x", "y", "z"],
                "normalized_label": "주소"},
        ],
        label_checks=[
            {"normalized_label": "ㄱ", "neighbor_text": "y"},
        ],
    )
    codes = sorted({f["reason_code"] for f in flags})
    expected = {
        "RUN_BOUNDARY_UNSUPPORTED", "CELL_INTERNAL_PARAGRAPH_NEEDED",
        "CHECKBOX_OR_SHAPE_NEEDED", "READBACK_MISMATCH",
        "TARGET_AMBIGUOUS", "LABEL_CONTEXT_INSUFFICIENT",
    }
    assert expected.issubset(set(codes))


def test_t101_backlog_record_conversion(an):
    flags = an.diagnose_session(
        readback_checks=[{"expected_hash": "a", "actual_hash": "b"}])
    recs = an.to_backlog_records(flags, session_id="s",
                                       document_id="d",
                                       created_at="2026-05-18T00:00:00Z")
    assert recs[0]["reason_code"] == "READBACK_MISMATCH"
    assert recs[0]["session_id"] == "s"
    assert recs[0]["severity"] == "HIGH"


# ── T110 D동 schema와 호환되는지 (통합) ─────────────────────────────────────

def test_t110_flags_match_d_dong_schema(an):
    """이번 공정에서 만든 flag들이 D동
    xml_deep_analyzer_need_flags 테이블에 그대로 들어가야 한다."""
    import sqlite3
    from scripts.hwpx.recognition_corpus import (
        corpus_schema as cs,
        audit_learning_log_contract as al,
    )
    c = sqlite3.connect(":memory:")
    c.execute("PRAGMA foreign_keys = ON")
    cs.init_db(c)
    al.init_audit_learning_log_schema(c)

    flags = an.diagnose_session(
        readback_checks=[{"expected_hash": "x", "actual_hash": "y",
                              "target_key": "tk",
                              "normalized_label": "공사명"}])
    recs = an.to_backlog_records(flags, session_id=None,
                                       document_id="d-1",
                                       created_at="2026-05-18T00:00:00Z")
    for r in recs:
        flag = {
            "session_id": None,
            "document_id": r["document_id"],
            "reason_code": r["reason_code"],
            "target_key": r.get("target_key"),
            "normalized_label": r.get("normalized_label"),
            "context_json": None,
            "severity": r["severity"],
            "created_at": r["created_at"],
        }
        al.insert_xml_backlog(c, flag)
    row = c.execute(
        "SELECT reason_code FROM xml_deep_analyzer_need_flags"
    ).fetchone()
    assert row[0] == "READBACK_MISMATCH"
    c.close()


# ── T120 방화구획 ───────────────────────────────────────────────────────────

def test_t120_production_isolation(an):
    res = an.audit_analyzer_isolation()
    assert res["ok"], res["violations"]


def test_t121_no_writer_in_module(an):
    src = Path(an.__file__).read_text(encoding="utf-8")
    for needle in ("GenericEditPlanWriter", "writer_executor",
                      "writer_adapter"):
        assert needle not in src


def test_t122_no_ai_ocr_in_module(an):
    src = Path(an.__file__).read_text(encoding="utf-8").lower()
    for needle in ("anthropic", "openai", "tesseract",
                      "anthropic_api_key", "claude_cli"):
        assert needle not in src


def test_t123_no_secret_in_module(an):
    src = Path(an.__file__).read_text(encoding="utf-8")
    for needle in ("DATABASE_URL", "password=", "haehan-ai.pem"):
        assert needle not in src


# ════════════════════════════════════════════════════════════════════════════
# B동 내부 정밀화 (v2) — 추가 detail 검증
# ════════════════════════════════════════════════════════════════════════════


def test_v2_analyzer_version_bumped(an):
    assert an.ANALYZER_VERSION == "v2"


def test_v2_run_boundary_detail_lengths_and_preview(an):
    f = an.analyze_run_boundary(_THREE_RUN)
    ctx = f["context"]
    assert "runLengths" in ctx
    assert "firstRunHead" in ctx
    assert "lastRunHead" in ctx
    assert "emptyRunCount" in ctx
    # 3 text run이므로 runLengths 길이 3
    assert len(ctx["runLengths"]) == 3


def test_v2_style_resolution_par_pr_id_detected(an):
    xml = (
        "<sec xmlns='hp'>"
        "<p parPrIDRef='1'><run charPrIDRef='1'><t>a</t></run></p>"
        "<p parPrIDRef='2'><run charPrIDRef='1'><t>b</t></run></p>"
        "</sec>"
    )
    f = an.analyze_style_resolution(xml)
    assert f is not None
    assert sorted(f["context"]["distinctParPrIds"]) == ["1", "2"]


def test_v2_style_resolution_lang_id_detected(an):
    xml = (
        "<p xmlns='hp'>"
        "<run charPrIDRef='1' langId='1042'><t>a</t></run>"
        "<run charPrIDRef='1' langId='1033'><t>b</t></run>"
        "</p>"
    )
    f = an.analyze_style_resolution(xml)
    assert f is not None
    assert "1042" in f["context"]["distinctLangIds"]
    assert "1033" in f["context"]["distinctLangIds"]


def test_v2_cell_paragraph_classifies_empty_vs_content(an):
    xml = (
        "<tc xmlns='hp'>"
        "<p></p>"
        "<p><run><t>실제값</t></run></p>"
        "<p></p>"
        "</tc>"
    )
    f = an.analyze_cell_internal_paragraph(xml)
    ctx = f["context"]
    assert ctx["paragraphCount"] == 3
    assert ctx["emptyParagraphCount"] == 2
    assert ctx["contentParagraphCount"] == 1


def test_v2_merged_cell_direction_counts(an):
    xml = (
        "<tbl xmlns='hp'>"
        "<tc rowSpan='2' colSpan='1'><p/></tc>"      # vertical
        "<tc rowSpan='1' colSpan='2'><p/></tc>"      # horizontal
        "<tc rowSpan='2' colSpan='2'><p/></tc>"      # bidirectional
        "<tc rowSpan='1' colSpan='1' hidden='1'><p/></tc>"
        "</tbl>"
    )
    f = an.analyze_merged_cell_geometry(xml)
    ctx = f["context"]
    assert ctx["verticalMergeCount"] == 1
    assert ctx["horizontalMergeCount"] == 1
    assert ctx["bidirectionalMergeCount"] == 1
    assert ctx["hiddenCellCount"] == 1


def test_v2_target_ambiguous_jaccard_similarity(an):
    # 매우 유사한 두 후보 (1글자만 다름)
    f = an.analyze_target_ambiguous(
        candidate_targets=["t0:r0:c1", "t0:r0:c2"])
    assert f["context"]["maxPairwiseSimilarity"] >= 0.5


def test_v2_target_ambiguous_disjoint(an):
    f = an.analyze_target_ambiguous(
        candidate_targets=["t0:r0:c1", "x9:r9:c9"])
    assert f["context"]["maxPairwiseSimilarity"] == 0.0
