"""Source extractor adapters (env-gated).

KPRC / PDF / Excel / HWP 파서를 source_extractor_contract의 registry에
등록할 수 있는 어댑터. 각 어댑터는 별도 env 게이트로 활성화된다.

실 가동:
- ENABLE_LIVE_KPRC=1 / ENABLE_LIVE_PDF_PARSER=1 / ...

env unset 시: AdapterDisabled raise → source_extractor가 skipped로 처리 (안전).
"""
from __future__ import annotations

from typing import Any

from . import adapter_contract as ac


def kprc_extractor(source: dict, target_labels: list[str]) -> list[dict]:
    """KPRC 파서 어댑터.

    sourceType: 'kprc'
    """
    ac.require_flag(ac.ENV_FLAG_KPRC)
    # production에서 활성화 — `scripts.kprc_parse` 등 실제 파서 호출.
    # 본 함수는 env unset 환경에서는 도달하지 않으므로 import도 lazy.
    raise NotImplementedError(
        "kprc extractor live invocation pending P14B-2 activation")


def pdf_extractor(source: dict, target_labels: list[str]) -> list[dict]:
    """PDF batch 파서 어댑터.

    sourceType: 'pdf'
    """
    ac.require_flag(ac.ENV_FLAG_PDF)
    raise NotImplementedError(
        "pdf extractor live invocation pending P14B-2 activation")


def excel_extractor(source: dict, target_labels: list[str]) -> list[dict]:
    """Excel 파서 어댑터 (Apache POI Java 경유, CLAUDE.md §9).

    sourceType: 'excel'
    """
    ac.require_flag(ac.ENV_FLAG_EXCEL)
    raise NotImplementedError(
        "excel extractor live invocation pending P14B-2 activation")


def hwp_extractor(source: dict, target_labels: list[str]) -> list[dict]:
    """HWP(.hwp 바이너리) 파서 어댑터.

    sourceType: 'hwp'
    """
    ac.require_flag(ac.ENV_FLAG_HWP)
    raise NotImplementedError(
        "hwp extractor live invocation pending P14B-2 activation")


def build_default_registry() -> dict:
    """env가 set된 어댑터만 registry에 포함.

    env unset 환경에서는 빈 registry — source_extractor가 모두 skipped로 처리.
    """
    registry: dict = {}
    if ac.is_flag_enabled(ac.ENV_FLAG_KPRC):
        registry["kprc"] = kprc_extractor
    if ac.is_flag_enabled(ac.ENV_FLAG_PDF):
        registry["pdf"] = pdf_extractor
    if ac.is_flag_enabled(ac.ENV_FLAG_EXCEL):
        registry["excel"] = excel_extractor
    if ac.is_flag_enabled(ac.ENV_FLAG_HWP):
        registry["hwp"] = hwp_extractor
    return registry
