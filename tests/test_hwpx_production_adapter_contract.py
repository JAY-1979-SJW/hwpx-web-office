"""HWPX-PRODUCTION-ADAPTER-CONTRACT-01 — 어댑터 표준 감리.

env unset 환경에서 모든 어댑터가 안전하게 비활성 상태인지 확인.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest import mock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def ac():
    from scripts.hwpx.production_adapters import adapter_contract as m
    return m


@pytest.fixture
def haiku():
    from scripts.hwpx.production_adapters import (
        haiku_cli_proposal_adapter as m,
    )
    return m


@pytest.fixture
def src_adapters():
    from scripts.hwpx.production_adapters import source_extractor_adapters as m
    return m


# ── env 게이트 ────────────────────────────────────────────────────────

def test_t01_contract_name(ac):
    assert ac.CONTRACT_NAME == "HWPX-PRODUCTION-ADAPTER-CONTRACT-01"


def test_t02_all_flags_listed(ac):
    assert ac.ENV_FLAG_HAIKU in ac.ALL_ENV_FLAGS
    assert ac.ENV_FLAG_KPRC in ac.ALL_ENV_FLAGS
    assert ac.ENV_FLAG_PDF in ac.ALL_ENV_FLAGS


def test_t03_env_unset_returns_false(ac):
    with mock.patch.dict(os.environ, {ac.ENV_FLAG_HAIKU: ""}):
        assert ac.is_flag_enabled(ac.ENV_FLAG_HAIKU) is False


def test_t04_env_set_returns_true(ac):
    for v in ("1", "true", "yes", "ON"):
        with mock.patch.dict(os.environ, {ac.ENV_FLAG_HAIKU: v}):
            assert ac.is_flag_enabled(ac.ENV_FLAG_HAIKU) is True


def test_t05_require_flag_raises_when_unset(ac):
    with mock.patch.dict(os.environ, {ac.ENV_FLAG_HAIKU: ""}, clear=False):
        with pytest.raises(ac.AdapterDisabled):
            ac.require_flag(ac.ENV_FLAG_HAIKU)


# ── placeholder fallback ────────────────────────────────────────────

def test_t10_placeholder_ai_passthrough(ac):
    out = ac.placeholder_ai_proposal(
        {}, [],
        [{"label": "공사명", "value": "v",
            "evidenceType": "pdf", "sourceRef": "r",
            "confidence": 0.9}])
    assert len(out) == 1
    assert out[0]["modelId"] == "placeholder_passthrough"


def test_t11_placeholder_extractor_empty(ac):
    out = ac.placeholder_source_extractor(
        {"sourceId": "s1", "sourceType": "pdf"}, ["공사명"])
    assert out == []


# ── Haiku 어댑터 ────────────────────────────────────────────────────

def test_t20_haiku_disabled_by_default(haiku, ac):
    with mock.patch.dict(os.environ, {ac.ENV_FLAG_HAIKU: ""}, clear=False):
        with pytest.raises(ac.AdapterDisabled):
            haiku.make_proposal({}, [], [])


def test_t21_haiku_module_no_api_key_usage(haiku):
    src = Path(haiku.__file__).read_text(encoding="utf-8")
    # CLAUDE.md §9: 외부 모델 키 직접 사용 금지
    for needle in ("anthropic.Anthropic", "openai.OpenAI",
                      "import anthropic", "import openai"):
        assert needle not in src
    # ANTHROPIC_API_KEY가 코드에 등장하면 안 됨 (docstring 제외)
    # 정확히 환경변수 명시적 참조 안 함 — CLAUDE Code CLI subprocess만
    assert "os.environ" not in src or "ANTHROPIC_API_KEY" not in src


def test_t22_haiku_prompt_does_not_leak_raw_value(haiku):
    """env가 설정돼도 prompt에 raw 값이 들어가지 않는지 확인.

    실제 subprocess 호출은 하지 않고 _build_prompt만 테스트.
    """
    extracted = [{
        "label": "공사명", "value": "010-1234-5678",
        "evidenceType": "pdf", "sourceRef": "r", "confidence": 0.9}]
    prompt = haiku._build_prompt({}, [], extracted)
    # raw 값이 prompt에 안 들어감 (summary만 동봉)
    assert "010-1234-5678" not in prompt


def test_t23_haiku_parse_response_handles_codeblock(haiku):
    out = haiku._parse_response('```json\n[{"a": 1}]\n```')
    assert out == [{"a": 1}]


def test_t24_haiku_parse_response_malformed(haiku):
    assert haiku._parse_response("not json") == []


# ── source extractor 어댑터 ────────────────────────────────────────

def test_t30_kprc_disabled_default(src_adapters, ac):
    with mock.patch.dict(os.environ, {ac.ENV_FLAG_KPRC: ""}, clear=False):
        with pytest.raises(ac.AdapterDisabled):
            src_adapters.kprc_extractor({}, [])


def test_t31_pdf_disabled_default(src_adapters, ac):
    with mock.patch.dict(os.environ, {ac.ENV_FLAG_PDF: ""}, clear=False):
        with pytest.raises(ac.AdapterDisabled):
            src_adapters.pdf_extractor({}, [])


def test_t32_excel_disabled_default(src_adapters, ac):
    with mock.patch.dict(os.environ, {ac.ENV_FLAG_EXCEL: ""}, clear=False):
        with pytest.raises(ac.AdapterDisabled):
            src_adapters.excel_extractor({}, [])


def test_t33_hwp_disabled_default(src_adapters, ac):
    with mock.patch.dict(os.environ, {ac.ENV_FLAG_HWP: ""}, clear=False):
        with pytest.raises(ac.AdapterDisabled):
            src_adapters.hwp_extractor({}, [])


def test_t34_default_registry_empty_when_all_unset(src_adapters, ac):
    with mock.patch.dict(os.environ, {f: "" for f in ac.ALL_ENV_FLAGS},
                              clear=False):
        registry = src_adapters.build_default_registry()
        assert registry == {}


def test_t35_default_registry_includes_kprc_when_enabled(src_adapters, ac):
    with mock.patch.dict(os.environ, {ac.ENV_FLAG_KPRC: "1"}, clear=False):
        registry = src_adapters.build_default_registry()
        assert "kprc" in registry


# ── adapter status snapshot ────────────────────────────────────────

def test_t40_dump_status_all_disabled(ac):
    with mock.patch.dict(os.environ, {f: "" for f in ac.ALL_ENV_FLAGS},
                              clear=False):
        snap = ac.dump_adapter_status()
        assert snap["anyEnabled"] is False
        assert all(not v for v in snap["flags"].values())


# ── 격리 + sanity ─────────────────────────────────────────────────

def test_t50_production_isolation(ac):
    res = ac.audit_adapter_isolation()
    assert res["ok"], res["violations"]


def test_t51_no_writer_in_modules():
    from scripts.hwpx.production_adapters import (
        adapter_contract, haiku_cli_proposal_adapter,
        source_extractor_adapters,
    )
    for mod in (adapter_contract, haiku_cli_proposal_adapter,
                  source_extractor_adapters):
        src = Path(mod.__file__).read_text(encoding="utf-8")
        for needle in ("GenericEditPlanWriter", "writer_executor",
                          "writer_adapter"):
            assert needle not in src


def test_t52_no_secret_in_modules():
    from scripts.hwpx.production_adapters import (
        adapter_contract, haiku_cli_proposal_adapter,
        source_extractor_adapters,
    )
    for mod in (adapter_contract, haiku_cli_proposal_adapter,
                  source_extractor_adapters):
        src = Path(mod.__file__).read_text(encoding="utf-8")
        for needle in ("DATABASE_URL", "password=", "haehan-ai.pem"):
            assert needle not in src


def test_t53_no_direct_anthropic_or_openai_sdk():
    """CLAUDE.md §9 — 외부 모델 SDK 직접 import 금지."""
    from scripts.hwpx.production_adapters import (
        haiku_cli_proposal_adapter,
        source_extractor_adapters,
    )
    for mod in (haiku_cli_proposal_adapter, source_extractor_adapters):
        src = Path(mod.__file__).read_text(encoding="utf-8")
        for needle in ("import anthropic", "from anthropic",
                          "import openai", "from openai"):
            assert needle not in src
