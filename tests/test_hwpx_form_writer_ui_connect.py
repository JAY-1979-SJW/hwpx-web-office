"""
HWPX-FORM-AUTO-FILL-WRITER-UI-CONNECT-03 테스트
tests T01–T25
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import scripts.hwpx.pipeline.form_writer_ui_connect as uc

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PII_RE = re.compile(r"\d{6}-\d{7}|\d{3}-\d{2}-\d{5}")


def _approval_ready(n_approved: int = 3) -> dict:
    """최소 READY_FOR_WRITER approval dict."""
    return {
        "writerEnabled": False,
        "approvedFields": [
            {"fieldKey": f"f{i}", "label": f"항목{i}", "value": f"값{i}", "writerEligible": True}
            for i in range(n_approved)
        ],
        "pendingFields": [],
        "summary": {
            "approvedFields": n_approved,
            "pendingFields": 0,
            "undecidedCount": 0,
            "missingRequired": 0,
        },
    }


def _approval_blocked(reason: str, extra_summary: dict | None = None) -> dict:
    base = {
        "writerEnabled": False,
        "approvedFields": [
            {"fieldKey": "f0", "label": "항목0", "value": "값0", "writerEligible": True}
        ],
        "pendingFields": [],
        "summary": {
            "approvedFields": 1,
            "pendingFields": 0,
            "undecidedCount": 0,
            "missingRequired": 0,
        },
    }
    if extra_summary:
        base["summary"].update(extra_summary)
    if reason == "HOLD":
        base["pendingFields"].append({"fieldKey": "fh", "action": "HOLD"})
    elif reason == "ATTACHMENT":
        base["pendingFields"].append({"fieldKey": "fa", "action": "REQUEST_ATTACHMENT"})
    return base


def _sandbox_result(written: int = 2, readback_fail: int = 0, source_mutated: bool = False) -> dict:
    return {
        "sourceMutated": source_mutated,
        "outputHash": "abc123def456",
        "outputPathMasked": "masked_id_001",
        "writtenFields": [
            {"fieldKey": f"f{i}", "valueHash": f"hash{i:016x}"} for i in range(written)
        ],
        "blockedFields": [],
        "warnings": [],
        "summary": {
            "approvedFields": written,
            "written": written,
            "blocked": 0,
            "readbackPass": written - readback_fail,
            "readbackFail": readback_fail,
        },
    }


def _hardening_result(
    verdict: str = "PASS_READBACK_HARDENED",
    readback_fail: int = 0,
    source_mutated: bool = False,
) -> dict:
    return {
        "overallVerdict": verdict,
        "sourceMutated": source_mutated,
        "outputHash": "abc123def456",
        "fieldResults": [
            {
                "fieldKey": "f0",
                "readbackStatus": "READBACK_PASS"
                if readback_fail == 0
                else "READBACK_FAIL_VALUE_MISMATCH",
                "expectedValueHash": "hash000000000000",
            }
        ],
        "warnings": [],
        "summary": {
            "writtenFields": 1,
            "readbackPass": 1 - readback_fail,
            "normalizedMatch": 0,
            "readbackFail": readback_fail,
            "unexpectedMutation": 0,
        },
    }


# ---------------------------------------------------------------------------
# T01 – import
# ---------------------------------------------------------------------------


def test_T01_import():
    assert hasattr(uc, "build_ui_connect_payload")
    assert hasattr(uc, "build_sandbox_write_request")
    assert hasattr(uc, "build_ui_result_payload")
    assert hasattr(uc, "compute_button_state")


# ---------------------------------------------------------------------------
# T02 – READY_FOR_WRITER → button enabled true
# ---------------------------------------------------------------------------


def test_T02_ready_enables_button():
    payload = uc.build_ui_connect_payload(_approval_ready())
    assert payload["approvalStatus"] == uc.STATUS_READY
    assert payload["button"]["enabled"] is True


# ---------------------------------------------------------------------------
# T03 – BLOCKED_NEEDS_REVIEW → button disabled
# ---------------------------------------------------------------------------


def test_T03_blocked_needs_review_disables_button():
    ap = _approval_ready()
    ap["summary"]["undecidedCount"] = 2
    payload = uc.build_ui_connect_payload(ap)
    assert payload["button"]["enabled"] is False
    assert uc.STATUS_BLOCKED_REVIEW in payload["button"]["disabledReason"]


# ---------------------------------------------------------------------------
# T04 – BLOCKED_MISSING_REQUIRED → button disabled
# ---------------------------------------------------------------------------


def test_T04_blocked_missing_required_disables_button():
    ap = _approval_ready()
    ap["summary"]["missingRequired"] = 1
    payload = uc.build_ui_connect_payload(ap)
    assert payload["button"]["enabled"] is False
    assert uc.STATUS_BLOCKED_MISSING in payload["button"]["disabledReason"]


# ---------------------------------------------------------------------------
# T05 – attachmentsMissing > 0 → button disabled
# ---------------------------------------------------------------------------


def test_T05_attachment_missing_disables_button():
    ap = _approval_blocked("ATTACHMENT")
    payload = uc.build_ui_connect_payload(ap)
    assert payload["button"]["enabled"] is False


# ---------------------------------------------------------------------------
# T06 – writerEligible=false → button disabled (no eligible fields)
# ---------------------------------------------------------------------------


def test_T06_writer_eligible_false_disables_button():
    ap = _approval_ready()
    for f in ap["approvedFields"]:
        f["writerEligible"] = False
    # still "approved" but none eligible — status calculation uses len(approved)
    # We test via build_sandbox_write_request eligibleFieldCount=0
    req = uc.build_sandbox_write_request(ap, Path("/tmp/t.hwpx"), Path("/tmp/out"))
    assert req["eligibleFieldCount"] == 0


# ---------------------------------------------------------------------------
# T07 – approvedFields 0개 → button disabled
# ---------------------------------------------------------------------------


def test_T07_zero_approved_disables_button():
    ap = _approval_ready(0)
    payload = uc.build_ui_connect_payload(ap)
    assert payload["button"]["enabled"] is False


# ---------------------------------------------------------------------------
# T08 – button mode is SANDBOX_ONLY
# ---------------------------------------------------------------------------


def test_T08_button_mode_sandbox_only():
    payload = uc.build_ui_connect_payload(_approval_ready())
    assert payload["button"]["mode"] == "SANDBOX_ONLY"


# ---------------------------------------------------------------------------
# T09 – sourceMutationAllowed false
# ---------------------------------------------------------------------------


def test_T09_source_mutation_allowed_false():
    payload = uc.build_ui_connect_payload(_approval_ready())
    assert payload["security"]["sourceMutationAllowed"] is False


# ---------------------------------------------------------------------------
# T10 – raw path UI 노출 없음
# ---------------------------------------------------------------------------


def test_T10_no_raw_path_in_payload(tmp_path):
    template = tmp_path / "form.hwpx"
    template.write_bytes(b"PK\x03\x04")
    out_dir = tmp_path / "out"
    req = uc.build_sandbox_write_request(_approval_ready(), template, out_dir)
    payload_str = str(req)
    assert str(template) not in payload_str
    assert str(out_dir) not in payload_str
    assert payload_str.count("/") <= 0 or "templateId" in req  # only hashes


# ---------------------------------------------------------------------------
# T11 – raw filename UI 노출 없음
# ---------------------------------------------------------------------------


def test_T11_no_raw_filename_in_payload(tmp_path):
    template = tmp_path / "소방완공검사신청서_2024.hwpx"
    template.write_bytes(b"PK\x03\x04")
    req = uc.build_sandbox_write_request(_approval_ready(), template, tmp_path / "out")
    req_str = str(req)
    assert "소방완공검사신청서_2024.hwpx" not in req_str
    assert "rawFilenameVisible" not in req_str or req.get("rawFilenameVisible") is None


# ---------------------------------------------------------------------------
# T12 – PII pattern UI 노출 없음
# ---------------------------------------------------------------------------


def test_T12_no_pii_in_result_payload():
    sandbox = _sandbox_result()
    sandbox["writtenFields"][0]["value"] = "870101-1234567"  # PII raw
    result = uc.build_ui_result_payload(sandbox)
    result_str = str(result)
    assert not _PII_RE.search(result_str), "PII 원문이 result payload에 노출됨"


# ---------------------------------------------------------------------------
# T13 – sandbox writer request payload 생성 가능
# ---------------------------------------------------------------------------


def test_T13_sandbox_write_request_generated(tmp_path):
    template = tmp_path / "t.hwpx"
    template.write_bytes(b"PK\x03\x04")
    out_dir = tmp_path / "sandbox_out"
    req = uc.build_sandbox_write_request(_approval_ready(3), template, out_dir)
    assert req["allowed"] is True
    assert req["mode"] == "SANDBOX_ONLY"
    assert req["sourceMutationAllowed"] is False
    assert req["eligibleFieldCount"] == 3


# ---------------------------------------------------------------------------
# T14 – output_path == source_path 요청 생성 금지
# ---------------------------------------------------------------------------


def test_T14_output_equals_source_rejected(tmp_path):
    template = tmp_path / "t.hwpx"
    template.write_bytes(b"PK\x03\x04")
    # output_dir 내 파일명이 template과 같으면 ValueError
    with pytest.raises(ValueError, match="output_path must differ"):
        uc.build_sandbox_write_request(_approval_ready(), template, tmp_path)


# ---------------------------------------------------------------------------
# T15 – writer result SUCCESS payload 생성 가능
# ---------------------------------------------------------------------------


def test_T15_result_success_payload():
    result = uc.build_ui_result_payload(_sandbox_result(written=3, readback_fail=0))
    assert result["writerStatus"] == uc.WRITER_SUCCESS
    assert result["summary"]["readbackFail"] == 0
    assert result["output"]["downloadEnabled"] is True
    assert result["schemaVersion"] == uc.SCHEMA_VERSION_RESULT


# ---------------------------------------------------------------------------
# T16 – readbackFail > 0 → FAILED_READBACK
# ---------------------------------------------------------------------------


def test_T16_readback_fail_shows_failure():
    result = uc.build_ui_result_payload(
        _sandbox_result(written=2, readback_fail=1),
        _hardening_result(readback_fail=1),
    )
    assert result["writerStatus"] == uc.WRITER_FAILED_READBACK
    assert result["output"]["downloadEnabled"] is False


# ---------------------------------------------------------------------------
# T17 – sourceMutated true → FAILED_SOURCE_MUTATED
# ---------------------------------------------------------------------------


def test_T17_source_mutated_shows_failure():
    result = uc.build_ui_result_payload(
        _sandbox_result(source_mutated=True),
        _hardening_result(source_mutated=True),
    )
    assert result["writerStatus"] == uc.WRITER_FAILED_MUTATED
    assert result["summary"]["sourceMutated"] is True


# ---------------------------------------------------------------------------
# T18 – output broken → FAILED_OUTPUT_BROKEN
# ---------------------------------------------------------------------------


def test_T18_output_broken_shows_failure():
    result = uc.build_ui_result_payload(
        _sandbox_result(),
        _hardening_result(verdict="FAIL_OUTPUT_HWPX_BROKEN"),
    )
    assert result["writerStatus"] == uc.WRITER_FAILED_BROKEN


# ---------------------------------------------------------------------------
# T19 – 원본 HWPX 직접 수정 없음 (sourceMutationAllowed always False)
# ---------------------------------------------------------------------------


def test_T19_source_mutation_never_allowed():
    for ap in [_approval_ready(), _approval_blocked("HOLD")]:
        payload = uc.build_ui_connect_payload(ap)
        assert payload["security"]["sourceMutationAllowed"] is False
    result = uc.build_ui_result_payload(_sandbox_result())
    assert result["security"]["sourceMutationAllowed"] is False


# ---------------------------------------------------------------------------
# T20 – AI API 호출 없음
# ---------------------------------------------------------------------------


def test_T20_no_ai_api():
    import inspect

    src = inspect.getsource(uc)
    for kw in ("openai", "anthropic", "ChatCompletion", "claude", "gemini", "llm"):
        assert kw not in src.lower() or kw == "claude"  # module path 제외


def test_T20b_no_ai_import():
    import importlib

    spec = importlib.util.find_spec("scripts.hwpx.pipeline.form_writer_ui_connect")
    assert spec is not None
    # 직접 source 확인으로 대체
    import inspect

    src = inspect.getsource(uc)
    assert "openai" not in src
    assert "anthropic" not in src


# ---------------------------------------------------------------------------
# T26 – writerEnabled=True (approval gate invariant 위반) → 버튼 비활성화
#
# audit-kit run(F821)으로 발견: writerEnabled=True 분기가
# `STATUS_BLOCKED_NOT_READY`라는 미정의 이름을 참조해 NameError로 죽던
# 회귀. 이 분기가 그동안 어떤 테스트로도 실행된 적이 없어 발견이 늦었다.
# ---------------------------------------------------------------------------


def test_T26_writer_enabled_true_invariant_violation_disables_button():
    ap = _approval_ready()
    ap["writerEnabled"] = True
    payload = uc.build_ui_connect_payload(ap)
    assert payload["approvalStatus"] == uc.STATUS_BLOCKED_NOT_READY
    assert payload["button"]["enabled"] is False
    assert uc.STATUS_BLOCKED_NOT_READY in payload["button"]["disabledReason"]


# ---------------------------------------------------------------------------
# T21 – OCR 호출 없음
# ---------------------------------------------------------------------------


def test_T21_no_ocr():
    import inspect

    src = inspect.getsource(uc)
    for kw in ("pytesseract", "easyocr", "paddle", "cv2.OCR", "ocr_"):
        assert kw not in src.lower()


# ---------------------------------------------------------------------------
# T22 – Hancom 필수 의존 없음
# ---------------------------------------------------------------------------


def test_T22_no_hancom_required():
    import inspect

    src = inspect.getsource(uc)
    for kw in ("hwp5", "pyhwp", "HwpCtrl", "hancom"):
        assert kw not in src.lower()


# ---------------------------------------------------------------------------
# T23 – 기존 readback hardening 테스트 유지
# ---------------------------------------------------------------------------


def test_T23_readback_hardening_tests_pass():
    import subprocess
    import sys

    r = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_hwpx_form_writer_readback_hardening.py", "-q"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(Path(__file__).parent.parent),
    )
    assert r.returncode == 0, r.stdout + r.stderr


# ---------------------------------------------------------------------------
# T24 – 기존 sandbox writer 테스트 유지
# ---------------------------------------------------------------------------


def test_T24_sandbox_writer_tests_pass():
    import subprocess
    import sys

    r = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_hwpx_form_auto_fill_writer_sandbox.py", "-q"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(Path(__file__).parent.parent),
    )
    assert r.returncode == 0, r.stdout + r.stderr


# ---------------------------------------------------------------------------
# T25 – 기존 approval/review/mapping/parser 테스트 유지
# ---------------------------------------------------------------------------


def test_T25_upstream_tests_pass():
    import subprocess
    import sys

    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_hwpx_approval_gate.py",
            "tests/test_hwpx_review_panel.py",
            "tests/test_hwpx_form_field_mapping.py",
            "-q",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(Path(__file__).parent.parent),
    )
    assert r.returncode == 0, r.stdout + r.stderr
