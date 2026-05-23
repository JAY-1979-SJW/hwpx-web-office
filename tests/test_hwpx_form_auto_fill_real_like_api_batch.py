"""HWPX-FORM-AUTO-FILL-WRITER-REAL-LIKE-API-BATCH-12 tests."""

from __future__ import annotations

import inspect
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import scripts.ops.hwpx_form_autofill_batch_api_route as api  # noqa: E402

PII_RE = re.compile(
    r"(\d{6}-\d{7}|\d{3}-\d{2}-\d{5}|\d{2,3}-\d{3,4}-\d{4}|"
    r"\d{2,6}-\d{2,6}-\d{2,6}|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})"
)


def _batch_result(
    limit: int,
    *,
    readback_fail: int = 0,
    unexpected_mutation: int = 0,
    source_mutation: int = 0,
    pii_leak: int = 0,
    raw_path_leak: int = 0,
    raw_filename_leak: int = 0,
) -> dict:
    status = "SANDBOX_WRITE_PASS"
    if readback_fail:
        status = "FAILED_READBACK"
    if unexpected_mutation:
        status = "FAILED_UNEXPECTED_MUTATION"
    if source_mutation:
        status = "FAILED_SOURCE_MUTATED"
    return {
        "schemaVersion": "form_auto_fill_real_like_sandbox_batch_v1",
        "mode": "SANDBOX_ONLY",
        "batchLimit": limit,
        "overallVerdict": "PASS_REAL_LIKE_SANDBOX_BATCH",
        "summary": {
            "totalCandidates": limit,
            "processed": limit,
            "ready": limit,
            "writtenFiles": 0 if any([readback_fail, unexpected_mutation, source_mutation]) else limit,
            "blockedFiles": 0,
            "failedFiles": 1 if any([readback_fail, unexpected_mutation, source_mutation]) else 0,
            "readbackFail": readback_fail,
            "unexpectedMutation": unexpected_mutation,
            "sourceMutation": source_mutation,
            "piiLeak": pii_leak,
            "rawPathLeak": raw_path_leak,
            "rawFilenameLeak": raw_filename_leak,
        },
        "fileResults": [
            {
                "sampleId": "sample_001",
                "status": status,
                "sourceHashChanged": bool(source_mutation),
                "sourceMtimeChanged": False,
                "writtenFields": 3,
                "readbackPass": 3 - readback_fail,
                "readbackFail": readback_fail,
                "unexpectedMutation": unexpected_mutation,
                "finalExportEnabled": not any([readback_fail, unexpected_mutation, source_mutation]),
            }
        ],
        "blockedResults": [],
        "warnings": ["WARN_SANDBOX_ONLY"],
    }


def _runner(**kwargs):
    return lambda limit: _batch_result(limit, **kwargs)


def _assert_no_response_leak(response: dict) -> None:
    text = json.dumps(response, ensure_ascii=False)
    assert not api._ABS_PATH_RE.search(text), text[:1000]
    assert not api._RAW_FILENAME_RE.search(text), text[:1000]
    assert not PII_RE.search(text), text[:1000]


def test_01_api_route_importable() -> None:
    assert hasattr(api, "call_health")
    assert hasattr(api, "call_real_like_sandbox")
    assert hasattr(api, "call_result")


def test_02_health_endpoint_pass() -> None:
    response = api.call_health()
    assert response["status"] == "SUCCESS"
    assert response["mode"] == "SANDBOX_ONLY"
    assert response["sourceMutationAllowed"] is False


def test_03_real_like_sandbox_endpoint_pass() -> None:
    response = api.call_real_like_sandbox({"limit": 10, "mode": "SANDBOX_ONLY"}, runner=_runner())
    assert response["status"] == "SUCCESS"
    assert response["summary"]["processed"] == 10


def test_04_limit_1_request_pass() -> None:
    response = api.call_real_like_sandbox({"limit": 1}, runner=_runner())
    assert response["summary"]["limit"] == 1
    assert response["summary"]["processed"] == 1


def test_05_limit_5_request_pass() -> None:
    response = api.call_real_like_sandbox({"limit": 5}, runner=_runner())
    assert response["summary"]["limit"] == 5
    assert response["summary"]["processed"] == 5


def test_06_limit_10_request_pass() -> None:
    response = api.call_real_like_sandbox({"limit": 10}, runner=_runner())
    assert response["summary"]["limit"] == 10
    assert response["summary"]["processed"] == 10


def test_07_mode_always_sandbox_only() -> None:
    response = api.call_real_like_sandbox({"limit": 1}, runner=_runner())
    assert response["mode"] == "SANDBOX_ONLY"


def test_08_source_mutation_allowed_false() -> None:
    response = api.call_real_like_sandbox({"limit": 1}, runner=_runner())
    assert response["sourceMutationAllowed"] is False


def test_09_non_sandbox_mode_blocked() -> None:
    response = api.call_real_like_sandbox({"limit": 1, "mode": "PRODUCTION"})
    assert response["status"] == "BLOCKED"
    assert response["errors"][0]["code"] == api.BLOCKED_NON_SANDBOX_MODE


def test_10_real_user_file_flag_blocked() -> None:
    response = api.call_real_like_sandbox({"limit": 1, "realUserFile": True})
    assert response["status"] == "BLOCKED"
    assert response["errors"][0]["code"] == api.BLOCKED_REAL_USER_FILE


def test_11_readback_fail_returns_failed() -> None:
    response = api.call_real_like_sandbox({"limit": 1}, runner=_runner(readback_fail=1))
    assert response["status"] == "FAILED"
    assert response["errors"][0]["code"] == api.FAILED_READBACK


def test_12_unexpected_mutation_returns_failed() -> None:
    response = api.call_real_like_sandbox({"limit": 1}, runner=_runner(unexpected_mutation=1))
    assert response["status"] == "FAILED"
    assert response["errors"][0]["code"] == api.FAILED_UNEXPECTED_MUTATION


def test_13_source_mutation_returns_failed() -> None:
    response = api.call_real_like_sandbox({"limit": 1}, runner=_runner(source_mutation=1))
    assert response["status"] == "FAILED"
    assert response["errors"][0]["code"] == api.FAILED_SOURCE_MUTATION


def test_14_security_leak_returns_failed() -> None:
    response = api.call_real_like_sandbox(
        {"limit": 1},
        runner=_runner(pii_leak=1, raw_path_leak=1, raw_filename_leak=1),
    )
    assert response["status"] == "FAILED"
    assert response["errors"][0]["code"] == api.FAILED_SECURITY_LEAK


def test_15_no_raw_path_in_response() -> None:
    response = api.call_real_like_sandbox({"limit": 1}, runner=_runner())
    _assert_no_response_leak(response)


def test_16_no_raw_filename_in_response() -> None:
    response = api.call_real_like_sandbox({"limit": 1}, runner=_runner())
    _assert_no_response_leak(response)


def test_17_no_pii_pattern_in_response() -> None:
    response = api.call_real_like_sandbox({"limit": 1}, runner=_runner())
    _assert_no_response_leak(response)


def test_18_production_write_not_called() -> None:
    source = inspect.getsource(api)
    assert "write-production" not in source


def test_19_source_overwrite_not_called() -> None:
    source = inspect.getsource(api)
    assert "overwrite-source" not in source


def test_20_no_ai_api() -> None:
    source = inspect.getsource(api).lower()
    for token in ("openai", "anthropic", "chatcompletion", "gemini"):
        assert token not in source


def test_21_no_ocr() -> None:
    source = inspect.getsource(api).lower()
    for token in ("pytesseract", "easyocr", "paddleocr"):
        assert token not in source


def test_22_hancom_not_required() -> None:
    source = inspect.getsource(api).lower()
    for token in ("hwp5", "pyhwp", "hwpctrl", "import hancom"):
        assert token not in source


def test_23_previous_real_like_browser_batch_test_exists() -> None:
    assert (ROOT / "tests" / "test_hwpx_form_auto_fill_real_like_browser_batch.py").is_file()


def test_24_previous_real_like_sandbox_batch_test_exists() -> None:
    assert (ROOT / "tests" / "test_hwpx_form_auto_fill_real_like_sandbox_batch.py").is_file()


def test_25_previous_preflight_browser_api_e2e_writer_tests_exist() -> None:
    for name in [
        "test_hwpx_form_auto_fill_real_file_preflight.py",
        "test_hwpx_form_autofill_browser_smoke.py",
        "test_hwpx_form_autofill_api_route.py",
        "test_hwpx_form_autofill_frontend_contract.py",
        "test_hwpx_form_auto_fill_e2e_smoke.py",
        "test_hwpx_form_writer_final_export_gate.py",
        "test_hwpx_form_writer_download_review.py",
        "test_hwpx_form_writer_ui_connect.py",
        "test_hwpx_form_writer_readback_hardening.py",
        "test_hwpx_form_auto_fill_writer_sandbox.py",
        "test_hwpx_approval_gate.py",
        "test_hwpx_review_panel.py",
        "test_hwpx_form_field_mapping.py",
    ]:
        assert (ROOT / "tests" / name).is_file()

