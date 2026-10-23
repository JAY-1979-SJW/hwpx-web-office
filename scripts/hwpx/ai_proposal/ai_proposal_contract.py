"""HWPX-AI-AUTO-FILL-PROPOSAL-CONTRACT-01.

자동 채움 설계실 — AI 손님이 보낸 입력 후보(`{label, value, confidence}`)를
받아 검증·정렬·표준화해서 운영동(fill_review)에 안전한 형태로 넘기는 contract.

본 모듈은 외부 모델 API를 직접 호출하지 않는다. 모델은 외부 callable로 주입한다.
(CLAUDE.md §9 — 외부 모델 키 직접 사용 금지)

방화구획:
- production 운영동에서 본 모듈 import 금지
- 외부 모델 / OCR / writer / output HWPX / secret 미참조
- raw 개인정보 저장 금지 (해시만)
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

CONTRACT_NAME = "HWPX-AI-AUTO-FILL-PROPOSAL-CONTRACT-01"
CONTRACT_VERSION = "v1"

# AI proposal envelope 필수 필드
REQUIRED_PROPOSAL_FIELDS: tuple[str, ...] = (
    "proposalId",
    "label",
    "value",
    "confidence",
)
OPTIONAL_PROPOSAL_FIELDS: tuple[str, ...] = (
    "semanticType",
    "targetHint",
    "evidence",
    "rationale",
    "modelId",
)

# 외부 손님이 보내면 안 되는 필드 (방화구획)
FORBIDDEN_PROPOSAL_FIELDS: tuple[str, ...] = (
    "filesystemPath",
    "outputPath",
    "absolutePath",
    "credential",
    "token",
    "password",
    "secret",
    "apiKey",
    "sessionCookie",
)

# 개인정보 가능 패턴 — raw value 저장 거부
_BIZNO_RE = re.compile(r"\b\d{3}-\d{2}-\d{5}\b")
_PHONE_RE = re.compile(r"\b01[016789][-\s]?\d{3,4}[-\s]?\d{4}\b")
_RRN_RE = re.compile(r"\b\d{6}-?\d{7}\b")


class ProposalRejection(ValueError):
    pass


# ── proposal envelope validation ───────────────────────────────────────────


def _validate_confidence_field(p: dict) -> list[str]:
    errs: list[str] = []
    conf = p.get("confidence")
    if conf is not None:
        if not isinstance(conf, (int, float)):
            errs.append("CONFIDENCE_NOT_NUMBER")
        elif not (0.0 <= float(conf) <= 1.0):
            errs.append("CONFIDENCE_OUT_OF_RANGE")
    return errs


def _validate_string_fields(p: dict) -> list[str]:
    errs: list[str] = []
    label = p.get("label")
    if label is not None and not isinstance(label, str):
        errs.append("LABEL_NOT_STRING")
    val = p.get("value")
    if val is not None and not isinstance(val, str):
        errs.append("VALUE_NOT_STRING")
    return errs


def validate_proposal_envelope(p: dict) -> list[str]:
    if not isinstance(p, dict):
        return ["PROPOSAL_NOT_OBJECT"]
    errs: list[str] = [f"MISSING_FIELD:{k}" for k in REQUIRED_PROPOSAL_FIELDS if k not in p]
    errs.extend(_validate_confidence_field(p))
    errs.extend(_validate_string_fields(p))
    errs.extend(f"FORBIDDEN_FIELD:{forbidden}" for forbidden in FORBIDDEN_PROPOSAL_FIELDS if forbidden in p)
    return errs


def validate_proposal_batch(proposals: list) -> dict:
    """proposal 리스트 검증. return {accepted: list, rejected: list}."""
    accepted: list[dict] = []
    rejected: list[dict] = []
    seen_ids: set[str] = set()
    for p in proposals or []:
        errs = validate_proposal_envelope(p)
        pid = p.get("proposalId") if isinstance(p, dict) else None
        if isinstance(pid, str) and pid in seen_ids:
            errs.append("DUPLICATE_PROPOSAL_ID")
        if errs:
            rejected.append({
                "proposalId": pid,
                "errors": errs,
            })
        else:
            seen_ids.add(pid)
            accepted.append(p)
    return {
        "accepted": accepted,
        "rejected": rejected,
        "acceptedCount": len(accepted),
        "rejectedCount": len(rejected),
    }


# ── value redaction (개인정보 보호) ─────────────────────────────────────────


def hash_value(v: str | None) -> str | None:
    if v is None:
        return None
    return hashlib.sha256(v.encode("utf-8")).hexdigest()


def redact_proposal_value(value: str | None) -> dict:
    """proposal value를 hash + redactedPreview(≤20자) 형태로 변환.

    사업자번호/전화번호/주민번호 패턴은 preview에서도 마스킹.
    """
    if value is None:
        return {"valueHash": None, "redactedPreview": None, "containsSensitive": False}
    sensitive = bool(_BIZNO_RE.search(value) or _PHONE_RE.search(value) or _RRN_RE.search(value))
    preview = value[:20]
    if sensitive:
        preview = "[REDACTED]"
    return {
        "valueHash": hash_value(value),
        "redactedPreview": preview,
        "containsSensitive": sensitive,
    }


# ── snapshot ───────────────────────────────────────────────────────────────


def dump_contract_snapshot() -> dict:
    return {
        "contractName": CONTRACT_NAME,
        "contractVersion": CONTRACT_VERSION,
        "requiredFields": list(REQUIRED_PROPOSAL_FIELDS),
        "optionalFields": list(OPTIONAL_PROPOSAL_FIELDS),
        "forbiddenFields": list(FORBIDDEN_PROPOSAL_FIELDS),
    }


# ── production isolation ───────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PRODUCTION_PATHS_FOR_AI_PROPOSAL: tuple[Path, ...] = (
    PROJECT_ROOT / "scripts/hwpx/fill_review/fill_review_contract.py",
    PROJECT_ROOT / "scripts/hwpx/fill_review/fill_review_ui_adapter.py",
    PROJECT_ROOT / "scripts/hwpx/fill_review/fill_review_live_pipeline.py",
    PROJECT_ROOT / "scripts/hwpx/fill_review/evidence_ingestion_contract.py",
)
FORBIDDEN_AI_PROPOSAL_IMPORTS: tuple[str, ...] = (
    "ai_proposal_contract",
    "target_resolver",
    "confidence_policy",
    "review_item_builder",
)


def audit_ai_proposal_isolation() -> dict:
    violations: list[dict] = []
    checked: list[str] = []
    for path in PRODUCTION_PATHS_FOR_AI_PROPOSAL:
        if not path.is_file():
            continue
        checked.append(str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"))
        text = path.read_text(encoding="utf-8", errors="ignore")
        violations.extend({
                    "file": str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
                    "forbidden": needle,
                } for needle in FORBIDDEN_AI_PROPOSAL_IMPORTS if needle in text)
    return {"violations": violations, "ok": not violations, "filesChecked": checked}
