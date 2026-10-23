"""
HWPX-FORM-AUTO-FILL-WRITER-UI-CONNECT-03

UI "승인 후 작성" 버튼 → sandbox writer pipeline 연결 모듈.
- approval gate result를 받아 버튼 상태 계산
- sandbox writer 실행 가능한 request payload 생성
- 실행 결과를 UI 표시용 payload로 변환
- SANDBOX_ONLY / sourceMutationAllowed=false 불변
- raw path / raw filename / PII 원문 노출 금지
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCHEMA_VERSION_PAYLOAD = "form_writer_ui_connect_v1"
SCHEMA_VERSION_RESULT = "form_writer_ui_result_v1"

# Approval statuses
STATUS_READY = "READY_FOR_WRITER"
STATUS_BLOCKED_REVIEW = "BLOCKED_NEEDS_REVIEW"
STATUS_BLOCKED_MISSING = "BLOCKED_MISSING_REQUIRED"
STATUS_BLOCKED_ATTACHMENT = "BLOCKED_ATTACHMENT_MISSING"
STATUS_HOLD = "HOLD_BY_USER"
STATUS_BLOCKED_NO_FIELDS = "BLOCKED_NO_ELIGIBLE_FIELDS"
STATUS_BLOCKED_NOT_READY = "BLOCKED_NOT_READY"

# Writer result statuses
WRITER_SUCCESS = "SUCCESS"
WRITER_BLOCKED_NOT_READY = "BLOCKED_NOT_READY"
WRITER_BLOCKED_MISSING = "BLOCKED_MISSING_REQUIRED"
WRITER_BLOCKED_REVIEW = "BLOCKED_NEEDS_REVIEW"
WRITER_BLOCKED_ATTACHMENT = "BLOCKED_ATTACHMENT_MISSING"
WRITER_FAILED_READBACK = "FAILED_READBACK"
WRITER_FAILED_MUTATED = "FAILED_SOURCE_MUTATED"
WRITER_FAILED_BROKEN = "FAILED_OUTPUT_BROKEN"

_PII_RE = re.compile(r"\d{6}-\d{7}|\d{3}-\d{2}-\d{5}")


def _mask_pii(value: str) -> str:
    return _PII_RE.sub("[MASKED]", value)


def _path_id(path: Any) -> str:
    """sha256 기반 불투명 ID — raw path 노출 금지."""
    return hashlib.sha256(str(path).encode()).hexdigest()[:16]


def _val_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Approval status derivation
# ---------------------------------------------------------------------------


def _derive_approval_status(approval_dict: dict) -> str:
    """ApprovalResult dict에서 버튼 활성화 가능 상태를 계산한다."""
    summary = approval_dict.get("summary", {})
    pending = approval_dict.get("pendingFields", [])
    approved = approval_dict.get("approvedFields", [])

    # writerEnabled must be False (invariant from approval gate)
    # writer_enabled 필드 자체가 없거나 False여야 한다
    if approval_dict.get("writerEnabled"):
        return STATUS_BLOCKED_NOT_READY

    approved_count = len(approved)
    if approved_count == 0:
        return STATUS_BLOCKED_NO_FIELDS

    # pending 필드 분류
    hold_count = sum(1 for p in pending if p.get("action") == "HOLD")
    attachment_count = sum(1 for p in pending if p.get("action") == "REQUEST_ATTACHMENT")
    undecided = summary.get("undecidedCount", 0)

    missing_required = summary.get("missingRequired", 0)

    if missing_required > 0:
        return STATUS_BLOCKED_MISSING
    if undecided > 0:
        return STATUS_BLOCKED_REVIEW
    if attachment_count > 0:
        return STATUS_BLOCKED_ATTACHMENT
    if hold_count > 0:
        return STATUS_HOLD

    return STATUS_READY


# ---------------------------------------------------------------------------
# Button state
# ---------------------------------------------------------------------------


@dataclass
class ButtonState:
    label: str = "승인 후 작성"
    enabled: bool = False
    mode: str = "SANDBOX_ONLY"
    warningText: str = "원본 HWPX는 수정하지 않고 sandbox 복사본에만 작성합니다."
    disabledReason: str = ""


def compute_button_state(approval_dict: dict) -> ButtonState:
    status = _derive_approval_status(approval_dict)
    btn = ButtonState()
    if status == STATUS_READY:
        btn.enabled = True
    else:
        btn.enabled = False
        btn.disabledReason = status
    return btn


# ---------------------------------------------------------------------------
# UI connect payload
# ---------------------------------------------------------------------------


def build_ui_connect_payload(
    approval_dict: dict,
    form_id: str = "",
) -> dict:
    """
    approval gate result → UI 버튼 + writer request payload.
    raw path / filename / PII 원문 미포함.
    """
    status = _derive_approval_status(approval_dict)
    btn = compute_button_state(approval_dict)

    approved = approval_dict.get("approvedFields", [])
    blocked = approval_dict.get("pendingFields", [])

    # writerRequest
    allowed = status == STATUS_READY
    writer_request: dict = {
        "allowed": allowed,
        "target": "SANDBOX_WRITER",
        "approvedFieldCount": len(approved),
        "blockedFieldCount": len(blocked),
    }

    blocked_reasons: list[str] = []
    if not allowed:
        blocked_reasons.append(status)

    return {
        "schemaVersion": SCHEMA_VERSION_PAYLOAD,
        "formId": form_id,
        "approvalStatus": status,
        "button": {
            "label": btn.label,
            "enabled": btn.enabled,
            "mode": btn.mode,
            "warningText": btn.warningText,
            "disabledReason": btn.disabledReason,
        },
        "writerRequest": writer_request,
        "blockedReasons": blocked_reasons,
        "security": {
            "sourceMutationAllowed": False,
            "rawPathVisible": False,
            "rawFilenameVisible": False,
            "piiMasked": True,
        },
    }


# ---------------------------------------------------------------------------
# Sandbox write request (actual pipeline call)
# ---------------------------------------------------------------------------


def build_sandbox_write_request(
    approval_dict: dict,
    template_path: Path,
    output_dir: Path,
) -> dict:
    """
    sandbox writer 실행을 위한 request dict.
    output_path != source_path 강제 검증.
    raw path 대신 불투명 ID만 반환.
    """
    template_path = Path(template_path)
    output_dir = Path(output_dir)

    # Safety: output_dir 내 경로가 template_path와 같아질 수 없도록 검증
    candidate_output = output_dir / template_path.name
    if candidate_output.resolve() == template_path.resolve():
        raise ValueError(
            "output_path must differ from source_path — "
            f"candidate={candidate_output} equals source={template_path}"
        )

    status = _derive_approval_status(approval_dict)
    if status != STATUS_READY:
        return {
            "allowed": False,
            "blockedReason": status,
            "templateId": _path_id(template_path),
            "outputDirId": _path_id(output_dir),
        }

    approved = approval_dict.get("approvedFields", [])
    eligible = [f for f in approved if f.get("writerEligible", False)]

    return {
        "allowed": True,
        "mode": "SANDBOX_ONLY",
        "sourceMutationAllowed": False,
        "templateId": _path_id(template_path),
        "outputDirId": _path_id(output_dir),
        "eligibleFieldCount": len(eligible),
        "fieldKeys": [f.get("fieldKey", "") for f in eligible],
    }


# ---------------------------------------------------------------------------
# Writer result → UI result payload
# ---------------------------------------------------------------------------


def build_ui_result_payload(
    sandbox_result_dict: dict,
    hardening_result_dict: dict | None = None,
) -> dict:
    """
    SandboxWriteResult + ReadbackHardeningResult → UI 표시용 payload.
    raw path / filename / PII 원문 미노출.
    """
    summary = sandbox_result_dict.get("summary", {})
    source_mutated = sandbox_result_dict.get("sourceMutated", False)
    output_hash = sandbox_result_dict.get("outputHash", "")

    # overall status from hardening result if available
    overall_verdict = ""
    if hardening_result_dict:
        overall_verdict = hardening_result_dict.get("overallVerdict", "")
        source_mutated = source_mutated or hardening_result_dict.get("sourceMutated", False)
        h_summary = hardening_result_dict.get("summary", {})
        readback_fail = h_summary.get("readbackFail", 0)
    else:
        readback_fail = summary.get("readbackFail", 0)

    # Determine writer status
    if source_mutated:
        writer_status = WRITER_FAILED_MUTATED
    elif overall_verdict in ("FAIL_OUTPUT_HWPX_BROKEN", "FAIL_READBACK_MISMATCH"):
        writer_status = (
            WRITER_FAILED_BROKEN if "BROKEN" in overall_verdict else WRITER_FAILED_READBACK
        )
    elif readback_fail > 0:
        writer_status = WRITER_FAILED_READBACK
    else:
        writer_status = WRITER_SUCCESS

    # output info — only hash, no raw path/filename
    output_masked = sandbox_result_dict.get("outputPathMasked", _val_hash(output_hash))
    download_enabled = writer_status == WRITER_SUCCESS

    # field results — strip raw values, keep only hashes and statuses
    raw_field_results = (
        hardening_result_dict.get("fieldResults", [])
        if hardening_result_dict
        else sandbox_result_dict.get("writtenFields", [])
    )
    field_results_ui = [
        {
            "fieldKey": fr.get("fieldKey", ""),
            "readbackStatus": fr.get("readbackStatus", ""),
            "valueHash": fr.get("expectedValueHash", fr.get("valueHash", "")),
        }
        for fr in raw_field_results
    ]

    warnings = list(sandbox_result_dict.get("warnings", []))
    if hardening_result_dict:
        warnings.extend(hardening_result_dict.get("warnings", []))

    return {
        "schemaVersion": SCHEMA_VERSION_RESULT,
        "writerStatus": writer_status,
        "summary": {
            "written": summary.get("written", 0),
            "blocked": summary.get("blocked", 0),
            "readbackPass": summary.get("readbackPass", 0),
            "readbackFail": readback_fail,
            "sourceMutated": source_mutated,
        },
        "output": {
            "outputFileId": output_masked,
            "outputHash": output_hash[:16] if output_hash else "",
            "downloadEnabled": download_enabled,
        },
        "fieldResults": field_results_ui,
        "warnings": warnings,
        "security": {
            "sourceMutationAllowed": False,
            "rawPathVisible": False,
            "rawFilenameVisible": False,
            "piiMasked": True,
        },
    }
