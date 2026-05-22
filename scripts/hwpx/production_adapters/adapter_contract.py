"""HWPX-PRODUCTION-ADAPTER-CONTRACT-01.

자재창고에 외부 자재(실 모델 / 실 파서)를 인입하는 표준 어댑터 패턴.

원칙:
- 모든 어댑터는 **환경 변수 게이트**로 활성/비활성 결정 (env unset → placeholder)
- CLAUDE.md §9 준수 (외부 모델 키 직접 사용 금지, Claude Code CLI Haiku만)
- 어댑터 내부 캐싱·상태 금지 (stateless)
- raw 개인정보가 어댑터 외부로 노출되지 않도록 PII redaction 책임은 호출자(자동 채움 설계실)에 위임

어댑터 종류:
- AI proposal — Haiku CLI subprocess wrapper (`ENABLE_LIVE_HAIKU=1` 게이트)
- Source extractor — KPRC / PDF / Excel / HWP (각각 env 게이트)

본 모듈은 어댑터 **표준 contract**만 잠근다. 실제 어댑터 구현은 별도 파일.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable

CONTRACT_NAME = "HWPX-PRODUCTION-ADAPTER-CONTRACT-01"
CONTRACT_VERSION = "v1"

# 어댑터 env 게이트 이름 표준
ENV_FLAG_HAIKU = "ENABLE_LIVE_HAIKU"
ENV_FLAG_KPRC = "ENABLE_LIVE_KPRC"
ENV_FLAG_PDF = "ENABLE_LIVE_PDF_PARSER"
ENV_FLAG_EXCEL = "ENABLE_LIVE_EXCEL_PARSER"
ENV_FLAG_HWP = "ENABLE_LIVE_HWP_PARSER"

ALL_ENV_FLAGS: tuple[str, ...] = (
    ENV_FLAG_HAIKU, ENV_FLAG_KPRC, ENV_FLAG_PDF,
    ENV_FLAG_EXCEL, ENV_FLAG_HWP,
)


class AdapterDisabled(RuntimeError):
    """env 게이트 미활성 — 안전한 placeholder 반환 시그널."""


def is_flag_enabled(env_name: str) -> bool:
    """환경 변수가 '1' / 'true' / 'yes' 로 설정되었는지."""
    val = os.environ.get(env_name, "").strip().lower()
    return val in ("1", "true", "yes", "on")


def require_flag(env_name: str) -> None:
    """env 미활성 시 AdapterDisabled raise. 호출자가 fallback 책임."""
    if not is_flag_enabled(env_name):
        raise AdapterDisabled(
            f"adapter disabled — set {env_name}=1 to activate")


# ── adapter signature 표준 ────────────────────────────────────────────

AiProposalCallable = Callable[[dict, list[dict], list[dict]], list[dict]]
# fn(recognition_result, input_slots, extracted_values) -> list[proposal dict]

SourceExtractorCallable = Callable[[dict, list[str]], list[dict]]
# fn(source_descriptor, target_labels) -> list[extracted dict]


# ── placeholder fallback (env unset 시) ───────────────────────────────

def placeholder_ai_proposal(rec: dict, slots: list[dict],
                                  extracted: list[dict]) -> list[dict]:
    """env unset — extractor 결과를 그대로 proposal로 통과."""
    out: list[dict] = []
    for i, e in enumerate(extracted or []):
        out.append({
            "proposalId": f"placeholder-{i}",
            "label": e.get("label"),
            "value": e.get("value"),
            "confidence": float(e.get("confidence") or 0.7),
            "evidence": [{"sourceRef": e.get("sourceRef"),
                            "evidenceType": e.get("evidenceType")}],
            "modelId": "placeholder_passthrough",
        })
    return out


def placeholder_source_extractor(
    source: dict, labels: list[str],
) -> list[dict]:
    """env unset — 추출 0건 반환 (안전)."""
    return []


# ── 어댑터 status snapshot ───────────────────────────────────────────

def dump_adapter_status() -> dict:
    """env 게이트 현황 + 활성/비활성 매트릭스."""
    return {
        "contractName": CONTRACT_NAME,
        "contractVersion": CONTRACT_VERSION,
        "flags": {f: is_flag_enabled(f) for f in ALL_ENV_FLAGS},
        "anyEnabled": any(is_flag_enabled(f) for f in ALL_ENV_FLAGS),
    }


# ── production 격리 ─────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PRODUCTION_PATHS_FOR_ADAPTER: tuple[Path, ...] = (
    PROJECT_ROOT / "scripts/hwpx/fill_review/fill_review_contract.py",
    PROJECT_ROOT / "scripts/hwpx/fill_review/fill_review_ui_adapter.py",
    PROJECT_ROOT / "scripts/hwpx/fill_review/fill_review_live_pipeline.py",
    PROJECT_ROOT / "scripts/hwpx/fill_review/evidence_ingestion_contract.py",
)
FORBIDDEN_ADAPTER_IMPORTS: tuple[str, ...] = (
    "adapter_contract",
    "placeholder_ai_proposal",
    "haiku_cli_proposal_adapter",
    "kprc_extractor_adapter",
)


def audit_adapter_isolation() -> dict:
    violations: list[dict] = []
    checked: list[str] = []
    for path in PRODUCTION_PATHS_FOR_ADAPTER:
        if not path.is_file():
            continue
        checked.append(str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"))
        text = path.read_text(encoding="utf-8", errors="ignore")
        for needle in FORBIDDEN_ADAPTER_IMPORTS:
            if needle in text:
                violations.append({
                    "file": str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
                    "forbidden": needle,
                })
    return {"violations": violations, "ok": not violations,
              "filesChecked": checked}
