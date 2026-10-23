"""
HWPX-FORM-AUTO-FILL-WRITER-DOWNLOAD-AND-USER-REVIEW-04

sandbox writer output을 사용자 다운로드/검토 흐름으로 연결하는 모듈.
- writer UI result → 다운로드 payload 생성
- downloadEnabled 활성화 규칙 적용
- 사용자 검토 결정(ACCEPT/REJECT/REWRITE/HOLD) 처리
- ACCEPT_OUTPUT은 운영 반영이 아님 — sourceMutationAllowed=false 불변
- raw path / filename / PII 원문 노출 금지
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta

SCHEMA_VERSION = "form_writer_download_review_v1"

# Download blocked reasons
BLOCKED_WRITER_FAILED = "BLOCKED_WRITER_FAILED"
BLOCKED_READBACK_FAILED = "BLOCKED_READBACK_FAILED"
BLOCKED_SOURCE_MUTATED = "BLOCKED_SOURCE_MUTATED"
BLOCKED_OUTPUT_BROKEN = "BLOCKED_OUTPUT_BROKEN"
BLOCKED_OUTPUT_ID_MISSING = "BLOCKED_OUTPUT_ID_MISSING"
BLOCKED_HASH_MISSING = "BLOCKED_HASH_MISSING"
BLOCKED_SECURITY_RISK = "BLOCKED_SECURITY_RISK"
BLOCKED_OUTPUT_EQUALS_SOURCE = "BLOCKED_OUTPUT_EQUALS_SOURCE"

# Review actions
ACTION_ACCEPT = "ACCEPT_OUTPUT"
ACTION_REJECT = "REJECT_OUTPUT"
ACTION_REWRITE = "REQUEST_REWRITE"
ACTION_HOLD = "HOLD_REVIEW"
_VALID_ACTIONS = frozenset({ACTION_ACCEPT, ACTION_REJECT, ACTION_REWRITE, ACTION_HOLD})

# Review decision results
DECISION_ACCEPTED = "ACCEPTED_BY_USER"
DECISION_REJECTED = "REJECTED_BY_USER"
DECISION_REWRITE = "REWRITE_REQUESTED"
DECISION_HOLD = "REVIEW_ON_HOLD"

_ACTION_TO_RESULT = {
    ACTION_ACCEPT: DECISION_ACCEPTED,
    ACTION_REJECT: DECISION_REJECTED,
    ACTION_REWRITE: DECISION_REWRITE,
    ACTION_HOLD: DECISION_HOLD,
}

# Review statuses
REVIEW_WAITING = "WAITING_USER_REVIEW"
REVIEW_ACCEPTED = DECISION_ACCEPTED
REVIEW_REJECTED = DECISION_REJECTED
REVIEW_REWRITE = DECISION_REWRITE
REVIEW_HOLD = DECISION_HOLD

WRITER_SUCCESS = "SUCCESS"

_PII_RE = re.compile(r"\d{6}-\d{7}|\d{3}-\d{2}-\d{5}")
_DEFAULT_EXPIRY_DAYS = 7


def _val_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:16]


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _expires_iso(days: int = _DEFAULT_EXPIRY_DAYS) -> str:
    dt = datetime.now(timezone.utc) + timedelta(days=days)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _has_pii_risk(value: str) -> bool:
    return bool(_PII_RE.search(value))


# ---------------------------------------------------------------------------
# Download eligibility check
# ---------------------------------------------------------------------------

def _check_download_eligible(ui_result: dict, source_template_hash: str = "") -> tuple[bool, str]:
    """
    downloadEnabled 활성화 여부와 차단 사유 반환.
    Returns (enabled: bool, blocked_reason: str)
    """
    writer_status = ui_result.get("writerStatus", "")
    summary = ui_result.get("summary", {})
    output = ui_result.get("output", {})

    source_mutated = summary.get("sourceMutated", False)
    readback_fail = summary.get("readbackFail", 0)
    output_file_id = output.get("outputFileId", "")
    output_hash = output.get("outputHash", "")

    # sourceMutated는 FAIL_SOURCE_MUTATED 즉시 차단
    if source_mutated:
        return False, BLOCKED_SOURCE_MUTATED

    # writer 자체 실패
    if writer_status != WRITER_SUCCESS:
        if "BROKEN" in writer_status:
            return False, BLOCKED_OUTPUT_BROKEN
        if "READBACK" in writer_status or "MISMATCH" in writer_status:
            return False, BLOCKED_READBACK_FAILED
        return False, BLOCKED_WRITER_FAILED

    # readback fail
    if readback_fail > 0:
        return False, BLOCKED_READBACK_FAILED

    # 필수 식별자
    if not output_file_id:
        return False, BLOCKED_OUTPUT_ID_MISSING
    if not output_hash:
        return False, BLOCKED_HASH_MISSING

    # output_path == source_path (outputFileId가 sourceTemplateHash와 같으면 위험)
    src_hash = source_template_hash or ui_result.get("sourceTemplateHash", "")
    if src_hash and output_file_id == src_hash:
        return False, BLOCKED_OUTPUT_EQUALS_SOURCE

    return True, ""


# ---------------------------------------------------------------------------
# Build download payload
# ---------------------------------------------------------------------------

def build_download_payload(
    ui_result: dict,
    form_id: str = "",
    display_name: str = "작성본_검토용.hwpx",
    source_template_hash: str = "",
    expiry_days: int = _DEFAULT_EXPIRY_DAYS,
) -> dict:
    """
    writer UI result → 사용자 다운로드 payload.
    raw path / filename / PII 원문 미포함.
    """
    enabled, blocked_reason = _check_download_eligible(ui_result, source_template_hash)
    output = ui_result.get("output", {})
    summary = ui_result.get("summary", {})

    download_info: dict = {
        "downloadEnabled": enabled,
        "outputFileId": output.get("outputFileId", ""),
        "displayName": display_name,
        "outputHash": output.get("outputHash", ""),
        "sourceTemplateHash": source_template_hash,
        "createdAt": _now_iso(),
        "expiresAt": _expires_iso(expiry_days),
    }
    if not enabled:
        download_info["blockedReason"] = blocked_reason

    return {
        "schemaVersion": SCHEMA_VERSION,
        "formId": form_id,
        "writerStatus": ui_result.get("writerStatus", ""),
        "reviewStatus": REVIEW_WAITING if enabled else blocked_reason,
        "download": download_info,
        "summary": {
            "written": summary.get("written", 0),
            "blocked": summary.get("blocked", 0),
            "readbackPass": summary.get("readbackPass", 0),
            "readbackFail": summary.get("readbackFail", 0),
            "sourceMutated": summary.get("sourceMutated", False),
        },
        "allowedReviewActions": list(_VALID_ACTIONS) if enabled else [],
        "security": {
            "sourceMutationAllowed": False,
            "rawPathVisible": False,
            "rawFilenameVisible": False,
            "piiMasked": True,
        },
        "warnings": list(ui_result.get("warnings", [])),
    }


# ---------------------------------------------------------------------------
# User review decision
# ---------------------------------------------------------------------------

@dataclass
class ReviewDecision:
    formId: str
    outputFileId: str
    action: str
    decisionBy: str = "user"
    reason: str = ""

    def __post_init__(self) -> None:
        if self.action not in _VALID_ACTIONS:
            raise ValueError(f"Invalid review action: {self.action!r}. Must be one of {sorted(_VALID_ACTIONS)}")


def apply_review_decision(
    download_payload: dict,
    decision: ReviewDecision,
) -> dict:
    """
    사용자 검토 결정을 처리하고 result payload를 반환한다.
    ACCEPT_OUTPUT은 원본 수정으로 연결되지 않는다.
    """
    if not download_payload.get("download", {}).get("downloadEnabled", False):
        raise ValueError("Download not enabled — review decision cannot be applied")

    result = _ACTION_TO_RESULT[decision.action]

    return {
        "schemaVersion": SCHEMA_VERSION,
        "formId": decision.formId,
        "outputFileId": decision.outputFileId,
        "action": decision.action,
        "decisionResult": result,
        "decisionBy": decision.decisionBy,
        "reason": decision.reason,
        "sourceMutated": False,      # ACCEPT_OUTPUT은 원본 수정이 아님
        "operationalDeployment": False,  # 운영 반영 아님
        "security": {
            "sourceMutationAllowed": False,
            "rawPathVisible": False,
            "rawFilenameVisible": False,
            "piiMasked": True,
        },
    }


def apply_review_decision_from_dict(
    download_payload: dict,
    decision_dict: dict,
) -> dict:
    """dict 형태 decision 입력 편의 함수."""
    decision = ReviewDecision(
        formId=decision_dict.get("formId", ""),
        outputFileId=decision_dict.get("outputFileId", ""),
        action=decision_dict.get("action", ""),
        decisionBy=decision_dict.get("decisionBy", "user"),
        reason=decision_dict.get("reason", ""),
    )
    return apply_review_decision(download_payload, decision)
