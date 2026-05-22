"""HWPX-SOURCE-EXTRACTOR-CONTRACT-01 — 감리검사.

deterministic. extractor 호출은 callable 주입. AI/OCR 미호출, secret 미출력.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def se():
    from scripts.hwpx.source_extractor import source_extractor_contract as m
    return m


def _src(sid="s1", st="pdf"):
    return {"sourceId": sid, "sourceType": st}


def _fake_pdf_extractor(s, labels):
    return [{
        "label": "공사명", "value": "○○건축공사",
        "evidenceType": "pdf_text", "sourceRef": f"{s['sourceId']}:p1",
        "confidence": 0.92,
    }]


def _fake_excel_extractor(s, labels):
    return [{
        "label": "계약금액", "value": "1,200,000,000",
        "evidenceType": "excel_cell",
        "sourceRef": f"{s['sourceId']}:Sheet1!B5",
        "confidence": 0.88,
    }]


# ── T01 contract identity ────────────────────────────────────────────────

def test_t01_contract_name(se):
    assert se.CONTRACT_NAME == "HWPX-SOURCE-EXTRACTOR-CONTRACT-01"


def test_t02_allowed_source_types(se):
    for t in ("pdf", "excel", "hwp", "hwpx", "text"):
        assert t in se.ALLOWED_SOURCE_TYPES


# ── source descriptor 검증 ──────────────────────────────────────────────

def test_t10_valid_source(se):
    assert se.validate_source_descriptor(_src()) == []


def test_t11_missing_fields(se):
    errs = se.validate_source_descriptor({})
    assert "MISSING_FIELD:sourceId" in errs
    assert "MISSING_FIELD:sourceType" in errs


def test_t12_unknown_type(se):
    errs = se.validate_source_descriptor(_src(st="bogus"))
    assert any(e.startswith("UNKNOWN_SOURCE_TYPE") for e in errs)


def test_t13_forbidden_field(se):
    s = _src(); s["apiKey"] = "sk-..."
    errs = se.validate_source_descriptor(s)
    assert any(e.startswith("FORBIDDEN_FIELD:apiKey") for e in errs)


def test_t14_batch_dedup(se):
    res = se.validate_source_batch([_src("s1"), _src("s1"), _src("s2")])
    assert res["acceptedCount"] == 2
    assert res["rejectedCount"] == 1


# ── extracted value 검증 ────────────────────────────────────────────────

def test_t20_extracted_required(se):
    errs = se.validate_extracted_value({"label": "x"})
    for k in ("value", "evidenceType", "sourceRef", "confidence"):
        assert f"MISSING_FIELD:{k}" in errs


def test_t21_extracted_confidence_range(se):
    errs = se.validate_extracted_value({
        "label": "x", "value": "y", "evidenceType": "t",
        "sourceRef": "r", "confidence": 1.5,
    })
    assert "CONFIDENCE_OUT_OF_RANGE" in errs


# ── 통합 추출기 ──────────────────────────────────────────────────────────

def test_t30_no_registry_skips_all(se):
    res = se.extract_values_from_sources([_src()], ["공사명"])
    assert res["summary"]["extractedCount"] == 0
    assert len(res["skippedSources"]) == 1
    assert "NO_EXTRACTOR" in res["skippedSources"][0]["reason"]


def test_t31_pdf_extractor_routes(se):
    res = se.extract_values_from_sources(
        [_src("pdf-1", "pdf")], ["공사명"],
        extractor_registry={"pdf": _fake_pdf_extractor})
    assert res["summary"]["extractedCount"] == 1
    val = res["extractedValues"][0]
    assert val["label"] == "공사명"
    assert val["sourceId"] == "pdf-1"


def test_t32_target_filter(se):
    """요청 안 한 라벨은 결과에서 제거된다."""
    def extractor(s, labels):
        return [
            {"label": "공사명", "value": "v1", "evidenceType": "pdf",
                "sourceRef": "r", "confidence": 0.9},
            {"label": "기타라벨", "value": "v2", "evidenceType": "pdf",
                "sourceRef": "r", "confidence": 0.9},
        ]
    res = se.extract_values_from_sources(
        [_src()], ["공사명"], extractor_registry={"pdf": extractor})
    assert res["summary"]["extractedCount"] == 1
    assert res["extractedValues"][0]["label"] == "공사명"


def test_t33_multiple_sources_routed(se):
    res = se.extract_values_from_sources(
        [_src("pdf-1", "pdf"), _src("xl-1", "excel")],
        ["공사명", "계약금액"],
        extractor_registry={
            "pdf": _fake_pdf_extractor,
            "excel": _fake_excel_extractor,
        })
    assert res["summary"]["extractedCount"] == 2
    types = {v["evidenceType"] for v in res["extractedValues"]}
    assert types == {"pdf_text", "excel_cell"}


def test_t34_extractor_exception_handled(se):
    def bad(s, labels):
        raise RuntimeError("kaboom")
    res = se.extract_values_from_sources(
        [_src()], ["x"], extractor_registry={"pdf": bad})
    assert res["summary"]["extractedCount"] == 0
    assert len(res["skippedSources"]) == 1
    assert "EXTRACTOR_ERROR" in res["skippedSources"][0]["reason"]


def test_t35_extractor_returns_invalid_shape(se):
    def bad(s, labels):
        return "not a list"
    res = se.extract_values_from_sources(
        [_src()], ["x"], extractor_registry={"pdf": bad})
    assert "EXTRACTOR_RETURN_NOT_LIST" in res["skippedSources"][0]["reason"]


def test_t36_invalid_extracted_values_filtered(se):
    def extractor(s, labels):
        return [
            {"label": "공사명"},  # missing required fields
            {"label": "공사명", "value": "v", "evidenceType": "pdf",
                "sourceRef": "r", "confidence": 0.9},
        ]
    res = se.extract_values_from_sources(
        [_src()], ["공사명"],
        extractor_registry={"pdf": extractor})
    assert res["summary"]["extractedCount"] == 1


# ── evidence_ingestion 변환 ─────────────────────────────────────────────

def test_t40_to_evidence_inputs(se):
    inputs = se.to_evidence_inputs([{
        "label": "공사명", "value": "x", "evidenceType": "pdf_text",
        "sourceRef": "r", "confidence": 0.9, "sourceId": "s1",
    }])
    assert inputs[0]["label"] == "공사명"
    assert inputs[0]["sourceType"] == "pdf_text"


# ── 격리 ─────────────────────────────────────────────────────────────────

def test_t50_production_isolation(se):
    res = se.audit_source_extractor_isolation()
    assert res["ok"], res["violations"]


def test_t51_no_ai_call_in_module(se):
    src = Path(se.__file__).read_text(encoding="utf-8")
    for needle in ("anthropic.Anthropic", "openai.OpenAI",
                      "import anthropic", "import openai",
                      "tesseract", "requests.post(",
                      "urllib.request.urlopen("):
        assert needle not in src


def test_t52_no_writer_in_module(se):
    src = Path(se.__file__).read_text(encoding="utf-8")
    for needle in ("GenericEditPlanWriter", "writer_executor",
                      "writer_adapter"):
        assert needle not in src


def test_t53_no_secret(se):
    src = Path(se.__file__).read_text(encoding="utf-8")
    for needle in ("DATABASE_URL", "password=", "haehan-ai.pem"):
        assert needle not in src


def test_t54_snapshot(se):
    snap = se.dump_contract_snapshot()
    assert snap["contractName"] == "HWPX-SOURCE-EXTRACTOR-CONTRACT-01"
    assert "allowedSourceTypes" in snap
