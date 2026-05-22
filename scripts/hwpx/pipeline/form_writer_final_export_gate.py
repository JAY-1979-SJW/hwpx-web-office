"""
HWPX-FORM-AUTO-FILL-WRITER-FINAL-EXPORT-GATE-05

ACCEPTED_BY_USER sandbox 작성본을 final export 후보로 봉인하는 게이트.
- ACCEPTED_BY_USER + SUCCESS + readbackFail=0 + sourceMutated=false 모두 충족 시에만 허용
- final export = 제출/다운로드 가능한 완성본 (원본 HWPX 교체/운영 반영 아님)
- sourceMutationAllowed=false 불변
- raw path / filename / PII 원문 노출 금지
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone, timedelta

SCHEMA_VERSION = "form_writer_final_export_gate_v1"

# Export statuses
EXPORT_READY = "READY_FOR_FINAL_EXPORT"
EXPORT_BLOCKED = "BLOCKED_FINAL_EXPORT"

# Blocked reasons
BLOCKED_NOT_ACCEPTED = "BLOCKED_NOT_ACCEPTED"
BLOCKED_REJECTED = "BLOCKED_REJECTED_BY_USER"
BLOCKED_REWRITE = "BLOCKED_REWRITE_REQUESTED"
BLOCKED_HOLD = "BLOCKED_REVIEW_ON_HOLD"
BLOCKED_WRITER_FAILED = "BLOCKED_WRITER_FAILED"
BLOCKED_READBACK_FAILED = "BLOCKED_READBACK_FAILED"
BLOCKED_SOURCE_MUTATED = "BLOCKED_SOURCE_MUTATED"
BLOCKED_OUTPUT_BROKEN = "BLOCKED_OUTPUT_BROKEN"
BLOCKED_HASH_MISSING = "BLOCKED_HASH_MISSING"
BLOCKED_OUTPUT_ID_MISSING = "BLOCKED_OUTPUT_ID_MISSING"
BLOCKED_SECURITY_RISK = "BLOCKED_SECURITY_RISK"
BLOCKED_OUTPUT_EQUALS_SOURCE = "BLOCKED_OUTPUT_EQUALS_SOURCE"

_DECISION_TO_BLOCKED = {
    "REJECTED_BY_USER": BLOCKED_REJECTED,
    "REWRITE_REQUESTED": BLOCKED_REWRITE,
    "REVIEW_ON_HOLD": BLOCKED_HOLD,
}

WRITER_SUCCESS = "SUCCESS"
_DEFAULT_EXPIRY_DAYS = 30

_PII_RE = re.compile(r"\d{6}-\d{7}|\d{3}-\d{2}-\d{5}")


def _val_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:16]


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _expires_iso(days: int = _DEFAULT_EXPIRY_DAYS) -> str:
    dt = datetime.now(timezone.utc) + timedelta(days=days)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _export_id(output_file_id: str, ts: str) -> str:
    return _val_hash(f"{output_file_id}:{ts}")


# ---------------------------------------------------------------------------
# Export eligibility check
# ---------------------------------------------------------------------------

def _check_export_eligible(
    download_review_payload: dict,
    decision_result: dict,
    source_template_hash: str = "",
) -> tuple[bool, str]:
    """
    final export 허용 여부와 차단 사유 반환.
    Returns (enabled: bool, blocked_reason: str)
    """
    review_status = decision_result.get("decisionResult", "")
    source_mutated_decision = decision_result.get("sourceMutated", False)

    # review decision 검사
    if review_status != "ACCEPTED_BY_USER":
        return False, _DECISION_TO_BLOCKED.get(review_status, BLOCKED_NOT_ACCEPTED)

    if source_mutated_decision:
        return False, BLOCKED_SOURCE_MUTATED

    # download review payload 검사
    dl = download_review_payload
    writer_status = dl.get("writerStatus", "")
    summary = dl.get("summary", {})
    download_info = dl.get("download", {})

    source_mutated = summary.get("sourceMutated", False)
    readback_fail = summary.get("readbackFail", 0)
    output_file_id = download_info.get("outputFileId", "")
    output_hash = download_info.get("outputHash", "")
    download_enabled = download_info.get("downloadEnabled", False)

    if source_mutated:
        return False, BLOCKED_SOURCE_MUTATED
    if writer_status != WRITER_SUCCESS:
        if "BROKEN" in writer_status:
            return False, BLOCKED_OUTPUT_BROKEN
        if "READBACK" in writer_status:
            return False, BLOCKED_READBACK_FAILED
        return False, BLOCKED_WRITER_FAILED
    if not download_enabled:
        return False, BLOCKED_WRITER_FAILED
    if readback_fail > 0:
        return False, BLOCKED_READBACK_FAILED
    if not output_file_id:
        return False, BLOCKED_OUTPUT_ID_MISSING
    if not output_hash:
        return False, BLOCKED_HASH_MISSING

    # output == source 검사
    src_hash = source_template_hash or download_info.get("sourceTemplateHash", "")
    if src_hash and output_file_id == src_hash:
        return False, BLOCKED_OUTPUT_EQUALS_SOURCE

    return True, ""


# ---------------------------------------------------------------------------
# Build final export payload
# ---------------------------------------------------------------------------

def build_final_export_payload(
    download_review_payload: dict,
    decision_result: dict,
    form_id: str = "",
    form_title: str = "",
    display_name: str = "최종작성본.hwpx",
    source_template_hash: str = "",
    expiry_days: int = _DEFAULT_EXPIRY_DAYS,
) -> dict:
    """
    download review payload + user decision → final export gate payload.
    ACCEPTED_BY_USER + 모든 안전 조건 만족 시에만 finalExportEnabled=true.
    raw path / filename / PII 원문 미포함.
    """
    enabled, blocked_reason = _check_export_eligible(
        download_review_payload, decision_result, source_template_hash
    )

    dl = download_review_payload
    summary = dl.get("summary", {})
    download_info = dl.get("download", {})
    output_file_id = download_info.get("outputFileId", "")
    output_hash = download_info.get("outputHash", "")
    src_hash = source_template_hash or download_info.get("sourceTemplateHash", "")

    created_at = _now_iso()
    final_export_id = _export_id(output_file_id, created_at) if enabled else ""

    final_export: dict = {
        "finalExportId": final_export_id,
        "sourceOutputFileId": output_file_id,
        "displayName": display_name,
        "fileType": "hwpx",
        "createdAt": created_at,
        "expiresAt": _expires_iso(expiry_days) if enabled else "",
        "downloadEnabled": enabled,
    }
    if not enabled:
        final_export["blockedReason"] = blocked_reason

    approval_trace: dict = {
        "userReviewAction": decision_result.get("action", ""),
        "reviewStatus": decision_result.get("decisionResult", ""),
        "approvedFieldCount": summary.get("written", 0) + summary.get("blocked", 0),
        "writtenFieldCount": summary.get("written", 0),
        "blockedFieldCount": summary.get("blocked", 0),
        "readbackPass": summary.get("readbackPass", 0),
        "readbackFail": summary.get("readbackFail", 0),
    }

    return {
        "schemaVersion": SCHEMA_VERSION,
        "formId": form_id,
        "formTitle": form_title,
        "exportStatus": EXPORT_READY if enabled else f"{EXPORT_BLOCKED}:{blocked_reason}",
        "finalExportEnabled": enabled,
        "sourceMutationAllowed": False,
        "sourceTemplateHash": src_hash,
        "outputHash": output_hash,
        "finalExport": final_export,
        "approvalTrace": approval_trace,
        "security": {
            "rawPathVisible": False,
            "rawFilenameVisible": False,
            "piiMasked": True,
            "originalTemplateMutated": False,
        },
        "warnings": [_PII_RE.sub("[MASKED]", w) for w in dl.get("warnings", [])],
    }
