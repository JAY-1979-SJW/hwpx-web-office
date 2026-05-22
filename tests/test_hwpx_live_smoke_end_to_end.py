"""HWPX-LIVE-SMOKE-HARNESS-01 — 단지 전체 회로 1회 시운전 감리."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def ls():
    from scripts.hwpx.master_orchestration import live_smoke_harness as m
    return m


def test_t01_harness_name(ls):
    assert ls.HARNESS_NAME == "HWPX-LIVE-SMOKE-HARNESS-01"


def test_t02_full_circuit_pass(ls):
    res = ls.run_live_smoke()
    assert res["status"] == "PASS", res["errors"]
    # 단계별 확인
    stages = {s["stage"] for s in res["stages"]}
    assert "master_pipeline" in stages
    assert "log_recorder" in stages
    assert "d_dong_views_query" in stages


def test_t03_recognition_label_count(ls):
    res = ls.run_live_smoke()
    master_stage = next(s for s in res["stages"]
                              if s["stage"] == "master_pipeline")
    assert master_stage["labelCount"] == 2


def test_t04_source_extraction_routed(ls):
    res = ls.run_live_smoke()
    master_stage = next(s for s in res["stages"]
                              if s["stage"] == "master_pipeline")
    assert master_stage["extractedCount"] == 2  # PDF + Excel 각 1건


def test_t05_review_items_generated(ls):
    res = ls.run_live_smoke()
    master_stage = next(s for s in res["stages"]
                              if s["stage"] == "master_pipeline")
    assert master_stage["reviewItemCount"] >= 2


def test_t06_log_recorder_session_status(ls):
    res = ls.run_live_smoke()
    log_stage = next(s for s in res["stages"]
                            if s["stage"] == "log_recorder")
    assert log_stage["sessionStatus"] == "READY_FOR_DECISION"


def test_t07_d_dong_views_queryable(ls):
    res = ls.run_live_smoke()
    view_stage = next(s for s in res["stages"]
                              if s["stage"] == "d_dong_views_query")
    assert view_stage["ok"] is True


def test_t08_no_errors_in_smoke(ls):
    res = ls.run_live_smoke()
    assert res["errors"] == []


def test_t09_master_summary_no_pii_keys(ls):
    """summary 출력에 raw value 포함 안 됨 — PII 보호."""
    import json
    res = ls.run_live_smoke()
    text = json.dumps(res, ensure_ascii=False)
    # 실 값(○○건축공사, 1,200,000,000)이 hash로만 들어가야 함
    # master 요약에서는 raw value 노출 안 됨 (review item은 hash + redactedPreview만)
    assert "1,200,000,000" not in text or "redactedPreview" in text


def test_t10_isolation(ls):
    res = ls.audit_harness_isolation()
    assert res["ok"], res["violations"]


def test_t11_no_writer_in_module(ls):
    src = Path(ls.__file__).read_text(encoding="utf-8")
    for needle in ("GenericEditPlanWriter", "writer_executor",
                      "writer_adapter"):
        assert needle not in src


def test_t12_no_ai_call_in_module(ls):
    src = Path(ls.__file__).read_text(encoding="utf-8").lower()
    for needle in ("anthropic.anthropic", "openai.openai",
                      "import anthropic", "import openai",
                      "tesseract", "requests.post(",
                      "urllib.request.urlopen("):
        assert needle not in src


def test_t13_no_secret(ls):
    src = Path(ls.__file__).read_text(encoding="utf-8")
    for needle in ("DATABASE_URL", "password=", "haehan-ai.pem"):
        assert needle not in src
