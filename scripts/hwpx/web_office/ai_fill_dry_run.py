"""AI 자동채움 드라이 런 — 해석→검증까지만, 기입은 하지 않는다.

기준서: docs/design/hwpx_ai_doc_interpretation_fill_standard.md §4
운영규칙: CLAUDE.md §4.5 — 드라이 런 게이트 PASS 인 제안만 기입 단계로
넘어갈 수 있다.

이 모듈은 조립만 한다: 로드(캐시) → 스키마 → 문맥 → AI 해석 → 검증 →
보고서. 어떤 단계에서도 HWPX 를 쓰지 않는다.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .ai_doc_context import build_context_fields
from .ai_doc_interpret import Runner, propose_with_context
from .ai_fill_validate import (
    apply_address_results,
    gate_verdict,
    validate_non_source,
    verify_addresses,
)

_PR = Path(__file__).resolve().parents[3]


def _mask(value: str) -> str:
    v = str(value or "")
    return (v[0] + "***") if v else ""


def _public_proposal(p: dict) -> dict:
    """보고서용 제안 — 민감칸 값은 마스킹(§3 원칙 6)."""
    out = dict(p)
    if p.get("requiresConfirmation"):
        out["value"] = _mask(p.get("value", ""))
        out["valueMasked"] = True
    return out


def run_dry_run(
    source_rel: str, source_data: dict, *,
    project_root: Path = _PR,
    timeout_sec: int = 120,
    runner: Runner | None = None,
) -> dict[str, Any]:
    """드라이 런 1회. 반환 = 보고서(JSON 직렬화 가능). 기입 없음."""
    from .editor_api_route import call_hwpx_load
    from .form_input_schema import build_input_schema

    env = call_hwpx_load(
        {"operation": "HWPX_EDITOR_LOAD", "sourcePath": source_rel},
        project_root=project_root)
    data = (env or {}).get("data") or {}
    if data.get("verdict") != "PASS":
        return {"verdict": "REJECTED", "reason": "LOAD_FAILED",
                "sourcePath": source_rel}

    schema = build_input_schema(
        data["documentModel"], data["renderPayload"],
        name=Path(source_rel).name, field_count=None)
    fields = build_context_fields(
        schema["inputs"], data["documentModel"], title=schema["cleanName"])
    if not fields:
        return {"verdict": "NOOP", "reason": "NO_APPLICANT_FIELDS",
                "sourcePath": source_rel, "formKind": schema["formKind"]}

    res = propose_with_context(fields, source_data,
                               timeout_sec=timeout_sec, runner=runner)
    held = res.get("heldForThirdParty") or []
    if not res.get("ok"):
        return {"verdict": "FAIL", "reason": res.get("error"),
                "detail": res.get("detail", ""), "sourcePath": source_rel,
                "fieldCount": len(fields),
                "heldForThirdPartyCount": len(held)}

    accepted, rejected = validate_non_source(
        res.get("proposals") or [], source_data)
    addr_failures = verify_addresses(
        source_rel, [p["key"] for p in accepted], project_root=project_root)
    accepted, addr_bad = apply_address_results(accepted, addr_failures)
    rejected = rejected + addr_bad

    gate = gate_verdict(accepted, rejected, held)
    return {
        "verdict": "PASS" if gate["pass"] else "FAIL",
        "operation": "AI_FILL_DRY_RUN",
        "sourcePath": source_rel,
        "cleanName": schema["cleanName"],
        "formKind": schema["formKind"],
        "fieldCount": len(fields),
        "proposals": [_public_proposal(p) for p in accepted],
        "rejected": [{"key": p.get("key"), "label": p.get("label"),
                      "reason": p.get("reason"),
                      "addressFailure": p.get("addressFailure")}
                     for p in rejected],
        "heldForThirdParty": held,
        "gate": gate,
        # 기입은 별도 공정(§4.5): gate.pass 인 proposals 만
        # form_direct_fill/para_save_apply 로 넘길 수 있다.
        "dryRun": True,
    }
