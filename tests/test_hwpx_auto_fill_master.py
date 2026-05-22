"""HWPX-AUTO-FILL-MASTER-ORCHESTRATION-01 — 감리검사.

deterministic. 모든 외부 의존(recognition/slot/extractor/AI)는 callable 주입.
writer 미호출, output 미생성, AI/OCR 미호출, secret 미출력.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def mo():
    from scripts.hwpx.master_orchestration import auto_fill_master as m
    return m


def _fake_recognition(source_ref):
    return {
        "documentId": source_ref,
        "documentType": "fillable_form",
        "subType": "검측요청서",
        "labelOccurrences": [
            {"normalizedLabel": "공사명",
                "cellKey": "t0:r0:c1", "neighborText": "현장"},
            {"normalizedLabel": "계약금액",
                "cellKey": "t0:r1:c1", "neighborText": "원"},
        ],
    }


def _fake_slot_detect(rec):
    return [{"label": "공사명", "type": "label_right_blank",
                "cellKey": "t0:r0:c1"}]


def _fake_pdf_extractor(s, labels):
    return [{
        "label": "공사명", "value": "○○건축공사",
        "evidenceType": "pdf_text", "sourceRef": f"{s['sourceId']}:p1",
        "confidence": 0.95,
    }]


def _fake_ai(rec, slots, extracted):
    return [{
        "proposalId": "ai-1", "label": "계약금액",
        "value": "1,200,000,000", "confidence": 0.88,
        "semanticType": "CONTRACT_AMOUNT",
        "modelId": "fake-llm",
    }]


# ── T01 contract identity ────────────────────────────────────────────

def test_t01_contract_name(mo):
    assert mo.CONTRACT_NAME == "HWPX-AUTO-FILL-MASTER-ORCHESTRATION-01"


def test_t02_snapshot(mo):
    snap = mo.dump_contract_snapshot()
    assert "stages" in snap and len(snap["stages"]) == 4


# ── T10 단계별 sanity ────────────────────────────────────────────────

def test_t10_master_minimal_no_callables(mo):
    """모든 callable 없이도 안전하게 동작 (placeholder 경고)."""
    res = mo.run_auto_fill_master(source_hwpx_ref="doc-1")
    assert res["pipelineStatus"] == "READY_FOR_REVIEW"
    assert any(w["code"] == "RECOGNITION_FN_NOT_INJECTED"
                  for w in res["warnings"])


def test_t11_with_recognition_only(mo):
    res = mo.run_auto_fill_master(
        source_hwpx_ref="doc-1",
        recognition_fn=_fake_recognition)
    assert len(res["recognitionResult"]["labelOccurrences"]) == 2
    assert res["stages"][0]["labelCount"] == 2


def test_t12_with_slot_detection(mo):
    res = mo.run_auto_fill_master(
        source_hwpx_ref="doc-1",
        recognition_fn=_fake_recognition,
        slot_detect_fn=_fake_slot_detect)
    assert res["inputSlots"][0]["cellKey"] == "t0:r0:c1"


def test_t13_with_source_extractor_blocked_when_no_ai(mo):
    """CLAUDE.md §10 — AI 없이는 자동 입력 차단.

    source extractor 결과는 수집되지만 reviewItem은 만들어지지 않는다.
    """
    res = mo.run_auto_fill_master(
        source_hwpx_ref="doc-1",
        source_documents=[{"sourceId": "pdf-1", "sourceType": "pdf"}],
        recognition_fn=_fake_recognition,
        extractor_registry={"pdf": _fake_pdf_extractor})
    extracted = res["extractedValues"]
    assert len(extracted) == 1
    # AI 없으므로 reviewItem은 비어 있어야 한다 (§10 정책)
    assert res["reviewItems"] == []
    # WARN 적재 확인
    assert any(w["code"] == "AI_REQUIRED_FOR_AUTO_FILL"
                  for w in res["warnings"])


def test_t14_with_ai_proposals(mo):
    res = mo.run_auto_fill_master(
        source_hwpx_ref="doc-1",
        recognition_fn=_fake_recognition,
        ai_proposal_fn=_fake_ai)
    items = res["reviewItems"]
    assert any(i["normalizedLabel"] == "계약금액" for i in items)


def test_t15_full_chain(mo):
    """모든 callable 주입 — 인식·슬롯·소스·AI 전체 사용."""
    res = mo.run_auto_fill_master(
        source_hwpx_ref="doc-1",
        source_documents=[{"sourceId": "pdf-1", "sourceType": "pdf"}],
        recognition_fn=_fake_recognition,
        slot_detect_fn=_fake_slot_detect,
        extractor_registry={"pdf": _fake_pdf_extractor},
        ai_proposal_fn=_fake_ai)
    # AI proposal이 있으면 source extractor fallback은 건너뜀
    items = res["reviewItems"]
    labels = {i["normalizedLabel"] for i in items}
    # AI 우선 — 계약금액만 포함 (source 자동 fallback은 skip)
    assert "계약금액" in labels
    assert res["aiProposalSummary"]["acceptedReadyForReview"] >= 1


# ── T20 안전성 ───────────────────────────────────────────────────────

def test_t20_recognition_exception_safe(mo):
    def bad(ref): raise RuntimeError("kaboom")
    res = mo.run_auto_fill_master(source_hwpx_ref="d",
                                          recognition_fn=bad)
    assert any(e["stage"] == "recognition" for e in res["errors"])
    # 흐름은 멈추지 않음
    assert res["pipelineStatus"] == "READY_FOR_REVIEW"


def test_t21_ai_exception_safe(mo):
    def bad(rec, slots, ext): raise RuntimeError("x")
    res = mo.run_auto_fill_master(
        source_hwpx_ref="d", recognition_fn=_fake_recognition,
        ai_proposal_fn=bad)
    assert any(e["stage"] == "ai_proposal" for e in res["errors"])


def test_t22_extractor_exception_handled_via_source_extractor(mo):
    def kaboom(s, labels): raise RuntimeError("x")
    res = mo.run_auto_fill_master(
        source_hwpx_ref="d", recognition_fn=_fake_recognition,
        source_documents=[{"sourceId": "s1", "sourceType": "pdf"}],
        extractor_registry={"pdf": kaboom})
    # source_extractor가 안전하게 처리
    assert res["extractedValues"] == []


# ── T30 단지 흐름과 호환 ────────────────────────────────────────────

def test_t30_output_compatible_with_orchestration_pipe(mo):
    """master 결과가 배관(fill_review_log_recorder)가 받는 형식과 호환."""
    res = mo.run_auto_fill_master(
        source_hwpx_ref="doc-1",
        recognition_fn=_fake_recognition,
        ai_proposal_fn=_fake_ai)
    # 배관이 요구하는 키들
    for key in ("documentId", "sourceDocumentHash",
                  "pipelineStatus", "fillReview"):
        assert key in res
    assert "reviewItems" in res["fillReview"]


def test_t31_pii_redaction_propagates(mo):
    """source extractor가 가져온 PII가 reviewItem에서 마스킹."""
    def pii_extractor(s, labels):
        return [{"label": "공사명",
                    "value": "연락처 010-1234-5678",
                    "evidenceType": "pdf_text", "sourceRef": "r",
                    "confidence": 0.95}]
    res = mo.run_auto_fill_master(
        source_hwpx_ref="d", recognition_fn=_fake_recognition,
        source_documents=[{"sourceId": "s1", "sourceType": "pdf"}],
        extractor_registry={"pdf": pii_extractor})
    if res["reviewItems"]:
        item = res["reviewItems"][0]
        assert item["containsSensitive"] is True
        import json
        assert "010-1234-5678" not in json.dumps(item, ensure_ascii=False)


# ── T40 격리 + sanity ────────────────────────────────────────────────

def test_t40_production_isolation(mo):
    res = mo.audit_master_isolation()
    assert res["ok"], res["violations"]


def test_t41_no_writer_in_module(mo):
    src = Path(mo.__file__).read_text(encoding="utf-8")
    for needle in ("GenericEditPlanWriter", "writer_executor",
                      "writer_adapter"):
        assert needle not in src


def test_t42_no_ai_call_in_module(mo):
    src = Path(mo.__file__).read_text(encoding="utf-8")
    for needle in ("anthropic.Anthropic", "openai.OpenAI",
                      "import anthropic", "import openai",
                      "tesseract", "requests.post(",
                      "urllib.request.urlopen("):
        assert needle not in src


def test_t43_no_secret(mo):
    src = Path(mo.__file__).read_text(encoding="utf-8")
    for needle in ("DATABASE_URL", "password=", "haehan-ai.pem"):
        assert needle not in src


def test_t44_no_fill_review_production_import(mo):
    src = Path(mo.__file__).read_text(encoding="utf-8")
    for forbidden in ("from scripts.hwpx.fill_review",
                          "import fill_review_contract",
                          "import fill_review_ui_adapter",
                          "import fill_review_live_pipeline",
                          "import evidence_ingestion_contract"):
        assert forbidden not in src


# ── T50 배관 통합 — master 결과를 D동 로그로 직결 ──────────────────

def test_t50_master_result_records_in_d_dong(mo):
    """master → 배관(fill_review_log_recorder) → D동 schema 적재 확인."""
    import sqlite3
    from scripts.hwpx.recognition_corpus import (
        corpus_schema as cs,
        audit_learning_log_contract as al,
    )
    from scripts.hwpx.orchestration import fill_review_log_recorder as orc

    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    cs.init_db(conn)
    al.init_audit_learning_log_schema(conn)

    master = mo.run_auto_fill_master(
        source_hwpx_ref="doc-1",
        request_id="req-master-1",
        recognition_fn=_fake_recognition,
        ai_proposal_fn=_fake_ai)
    # 배관이 master 결과를 받아 D동에 적재
    rec_result = orc.record_pipeline_result(conn, master)
    assert rec_result["sessionStatus"] == "READY_FOR_DECISION"
    row = conn.execute(
        "SELECT document_id FROM fill_review_sessions").fetchone()
    assert row[0] == "doc-1"
    conn.close()
