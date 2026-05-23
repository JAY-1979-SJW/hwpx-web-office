"""HWPX-FORM-AUTO-FILL-WRITER-REAL-LIKE-API-BROWSER-E2E-13 tests."""

from __future__ import annotations

import json
import re
import socket
import sys
import threading
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
VIEWER_DIR = ROOT / "frontend" / "web_office_viewer"
PAGE = VIEWER_DIR / "form_autofill_real_like_batch_smoke.html"
JS = VIEWER_DIR / "form_autofill_real_like_batch_smoke.mjs"

ABS_PATH_RE = re.compile(r"(?<![A-Za-z])([A-Za-z]:[\\/]|/(home|tmp|var|Users)/)")
RAW_FILENAME_RE = re.compile(r"\b[^\\/:\s]+\.hwpx\b", re.IGNORECASE)
PII_RE = re.compile(
    r"(\d{6}-\d{7}|\d{3}-\d{2}-\d{5}|\d{2,3}-\d{3,4}-\d{4}|"
    r"\d{2,6}-\d{2,6}-\d{2,6}|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})"
)
HEALTH = "/api/hwpx/form-autofill/batch/health"
RUN = "/api/hwpx/form-autofill/batch/real-like-sandbox"
RESULT = "/api/hwpx/form-autofill/batch/result/"
FORBIDDEN_ENDPOINT_PARTS = (
    "/api/hwpx/form-autofill/write-production",
    "/api/hwpx/form-autofill/overwrite-source",
    "/api/hwpx/form-autofill/deploy",
    "/api/deploy",
    "/api/ai/",
    "/api/ocr/",
    "/api/hancom/",
)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args: Any, **kwargs: Any) -> None:
        pass


def _serve(directory: Path) -> tuple[HTTPServer, int]:
    port = _free_port()

    class _Handler(_QuietHandler):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, directory=str(directory), **kwargs)

    server = HTTPServer(("127.0.0.1", port), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, port


def _api_response(limit: int, case: str = "SUCCESS") -> dict[str, Any]:
    batch_id = f"batch_safe_{limit}_{case.lower()}"
    errors: list[dict[str, str]] = []
    status = "SUCCESS"
    summary = {
        "limit": limit,
        "processed": limit,
        "ready": limit,
        "writtenFiles": limit,
        "blockedFiles": 0,
        "failedFiles": 0,
        "readbackFail": 0,
        "unexpectedMutation": 0,
        "sourceMutation": 0,
    }
    security = {
        "piiLeak": 0,
        "rawPathLeak": 0,
        "rawFilenameLeak": 0,
        "aiCalled": False,
        "ocrCalled": False,
        "hancomRequired": False,
    }
    if case.startswith("BLOCKED_"):
        status = "BLOCKED"
        summary["writtenFiles"] = 0
        summary["blockedFiles"] = 1
        errors = [{"code": case, "message": case}]
    elif case.startswith("FAILED_"):
        status = "FAILED"
        summary["writtenFiles"] = 0
        summary["failedFiles"] = 1
        errors = [{"code": case, "message": case}]
        if case == "FAILED_READBACK":
            summary["readbackFail"] = 1
        elif case == "FAILED_SOURCE_MUTATION":
            summary["sourceMutation"] = 1
        elif case == "FAILED_UNEXPECTED_MUTATION":
            summary["unexpectedMutation"] = 1
        elif case == "FAILED_SECURITY_LEAK":
            security["piiLeak"] = 1
            security["rawPathLeak"] = 1
            security["rawFilenameLeak"] = 1

    return {
        "schemaVersion": "hwpx_form_autofill_real_like_api_batch_v1",
        "requestId": f"req_safe_{limit}",
        "batchId": batch_id,
        "mode": "SANDBOX_ONLY",
        "status": status,
        "sourceMutationAllowed": False,
        "summary": summary,
        "security": security,
        "fileResults": [
            {
                "sampleId": "sample_001",
                "status": "SANDBOX_WRITE_PASS" if status == "SUCCESS" else case,
                "sourceHashChanged": summary["sourceMutation"] > 0,
                "sourceMtimeChanged": False,
                "writtenFields": 3 if status == "SUCCESS" else 0,
                "readbackPass": 3 if status == "SUCCESS" else 0,
                "readbackFail": summary["readbackFail"],
                "unexpectedMutation": summary["unexpectedMutation"],
                "finalExportEnabled": status == "SUCCESS",
            }
        ],
        "blockedResults": [
            {
                "sampleId": "blocked_001",
                "status": case,
                "blockedReason": case,
                "writtenFields": 0,
            }
        ]
        if status == "BLOCKED"
        else [],
        "warnings": ["WARN_SANDBOX_ONLY", "WARN_REAL_LIKE_SANITIZED_SAMPLE_ONLY"],
        "errors": errors,
    }


def _assert_no_leak(text: str) -> None:
    checked = re.sub(r"http://127\.0\.0\.1:\d+", "http://localhost", text)
    assert not ABS_PATH_RE.search(checked), checked[:1000]
    assert not RAW_FILENAME_RE.search(checked), checked[:1000]
    assert not PII_RE.search(checked), checked[:1000]


@pytest.fixture(scope="session")
def api_browser_e2e_result() -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # pragma: no cover
        pytest.fail(f"playwright import failed: {exc}")

    assert PAGE.is_file()
    assert JS.is_file()
    server, port = _serve(VIEWER_DIR)
    console_messages: list[str] = []
    requests: list[dict[str, Any]] = []
    forbidden_calls: list[str] = []
    payloads: list[dict[str, Any]] = []
    responses: list[dict[str, Any]] = []
    result_store: dict[str, dict[str, Any]] = {}
    case_holder = {"case": "SUCCESS"}
    observed: dict[str, Any] = {"limits": {}, "states": {}, "texts": {}}

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page()
            page.on("console", lambda msg: console_messages.append(msg.text))

            def route_handler(route: Any, request: Any) -> None:
                url = request.url
                path = "/" + url.split("/", 3)[3] if url.startswith("http") and len(url.split("/", 3)) > 3 else url
                if any(part in url for part in FORBIDDEN_ENDPOINT_PARTS):
                    forbidden_calls.append(url)
                    route.abort()
                    return
                if HEALTH in url:
                    body = {
                        "schemaVersion": "hwpx_form_autofill_real_like_api_batch_v1",
                        "mode": "SANDBOX_ONLY",
                        "status": "SUCCESS",
                        "sourceMutationAllowed": False,
                        "data": {"pipelineReady": True, "supportedLimits": [1, 5, 10]},
                        "security": {"piiLeak": 0, "rawPathLeak": 0, "rawFilenameLeak": 0},
                    }
                    requests.append({"method": request.method, "path": path, "body": None})
                    responses.append(body)
                    route.fulfill(status=200, content_type="application/json", body=json.dumps(body))
                    return
                if RUN in url:
                    payload = json.loads(request.post_data or "{}")
                    limit = int(payload.get("limit", 10))
                    body = _api_response(limit, case_holder["case"])
                    result_store[body["batchId"]] = body
                    payloads.append(payload)
                    requests.append({"method": request.method, "path": path, "body": payload})
                    responses.append(body)
                    route.fulfill(status=200, content_type="application/json", body=json.dumps(body))
                    return
                if RESULT in url:
                    batch_id = url.rsplit("/", 1)[-1]
                    body = result_store.get(batch_id, _api_response(10, "FAILED_READBACK"))
                    requests.append({"method": request.method, "path": path, "body": None})
                    responses.append(body)
                    route.fulfill(status=200, content_type="application/json", body=json.dumps(body))
                    return
                requests.append({"method": request.method, "path": path, "body": None})
                route.continue_()

            page.route("**/*", route_handler)
            page.goto(f"http://127.0.0.1:{port}/form_autofill_real_like_batch_smoke.html")
            page.wait_for_selector('[data-testid="browser-batch-dashboard"]', state="visible")
            page.evaluate("() => window.__realLikeBatchSmoke.enableApiMode()")

            for limit in [1, 5, 10]:
                case_holder["case"] = "SUCCESS"
                page.locator(f'[data-testid="api-limit-{limit}"]').click()
                page.locator('[data-testid="api-run-batch"]').click()
                page.wait_for_function(
                    """expected => document.body.innerText.includes(`batch_safe_${expected}_success`)""",
                    arg=limit,
                )
                observed["limits"][limit] = {
                    "state": page.locator('[data-testid="overall-state"]').inner_text(),
                    "body": page.locator("body").inner_text(),
                }

            for case in [
                "BLOCKED_NON_SANDBOX_MODE",
                "BLOCKED_REAL_USER_FILE",
                "FAILED_READBACK",
                "FAILED_SOURCE_MUTATION",
                "FAILED_UNEXPECTED_MUTATION",
                "FAILED_SECURITY_LEAK",
            ]:
                case_holder["case"] = case
                page.locator('[data-testid="api-limit-1"]').click()
                page.locator('[data-testid="api-run-batch"]').click()
                page.wait_for_function("code => document.body.innerText.includes(code)", arg=case)
                observed["states"][case] = page.locator('[data-testid="overall-state"]').inner_text()
                observed["texts"][case] = page.locator("body").inner_text()

            html = page.content()
            browser.close()
    finally:
        server.shutdown()
        time.sleep(0.05)

    network_blob = json.dumps({"requests": requests, "payloads": payloads, "responses": responses}, ensure_ascii=False)
    _assert_no_leak(network_blob)
    _assert_no_leak("\n".join(console_messages))
    _assert_no_leak(json.dumps(observed, ensure_ascii=False))
    _assert_no_leak(html)

    return {
        "requests": requests,
        "payloads": payloads,
        "responses": responses,
        "forbiddenCalls": forbidden_calls,
        "consoleMessages": console_messages,
        "observed": observed,
        "security": {
            "piiLeak": 0,
            "rawPathLeak": 0,
            "rawFilenameLeak": 0,
            "hancomRequired": False,
        },
    }


def test_01_browser_e2e_test_importable() -> None:
    assert PAGE.is_file()
    assert JS.is_file()


def test_02_real_like_batch_page_loads(api_browser_e2e_result: dict[str, Any]) -> None:
    assert any("form_autofill_real_like_batch_smoke.html" in item["path"] for item in api_browser_e2e_result["requests"])


def test_03_health_endpoint_called(api_browser_e2e_result: dict[str, Any]) -> None:
    assert any(item["method"] == "GET" and HEALTH in item["path"] for item in api_browser_e2e_result["requests"])


@pytest.mark.parametrize("limit", [1, 5, 10])
def test_04_to_06_limit_selection_works(api_browser_e2e_result: dict[str, Any], limit: int) -> None:
    assert api_browser_e2e_result["observed"]["limits"][limit]["state"] == "PASS"
    assert f"batch_safe_{limit}_success" in api_browser_e2e_result["observed"]["limits"][limit]["body"]


def test_07_write_batch_api_called(api_browser_e2e_result: dict[str, Any]) -> None:
    assert any(item["method"] == "POST" and RUN in item["path"] for item in api_browser_e2e_result["requests"])


def test_08_request_mode_sandbox_only(api_browser_e2e_result: dict[str, Any]) -> None:
    assert all(payload["mode"] == "SANDBOX_ONLY" for payload in api_browser_e2e_result["payloads"])


def test_09_request_source_mutation_allowed_false(api_browser_e2e_result: dict[str, Any]) -> None:
    assert all(payload["sourceMutationAllowed"] is False for payload in api_browser_e2e_result["payloads"])


def test_10_request_limit_preserved(api_browser_e2e_result: dict[str, Any]) -> None:
    requested = [payload["limit"] for payload in api_browser_e2e_result["payloads"][:3]]
    assert requested == [1, 5, 10]


def test_11_response_batch_id_rendered(api_browser_e2e_result: dict[str, Any]) -> None:
    assert "batch_safe_10_success" in api_browser_e2e_result["observed"]["limits"][10]["body"]


def test_12_result_endpoint_called(api_browser_e2e_result: dict[str, Any]) -> None:
    assert any(item["method"] == "GET" and RESULT in item["path"] for item in api_browser_e2e_result["requests"])


def test_13_success_response_shown_success(api_browser_e2e_result: dict[str, Any]) -> None:
    assert api_browser_e2e_result["observed"]["limits"][1]["state"] == "PASS"


@pytest.mark.parametrize("case", ["BLOCKED_NON_SANDBOX_MODE", "BLOCKED_REAL_USER_FILE"])
def test_14_to_15_blocked_responses_shown_blocked(api_browser_e2e_result: dict[str, Any], case: str) -> None:
    assert api_browser_e2e_result["observed"]["states"][case] == "BLOCKED"


@pytest.mark.parametrize(
    "case",
    ["FAILED_READBACK", "FAILED_SOURCE_MUTATION", "FAILED_UNEXPECTED_MUTATION", "FAILED_SECURITY_LEAK"],
)
def test_16_to_19_failed_responses_shown_failure(api_browser_e2e_result: dict[str, Any], case: str) -> None:
    assert api_browser_e2e_result["observed"]["states"][case] == "FAIL"


def test_20_readback_fail_not_success(api_browser_e2e_result: dict[str, Any]) -> None:
    assert api_browser_e2e_result["observed"]["states"]["FAILED_READBACK"] != "PASS"


def test_21_source_mutation_not_success(api_browser_e2e_result: dict[str, Any]) -> None:
    assert api_browser_e2e_result["observed"]["states"]["FAILED_SOURCE_MUTATION"] != "PASS"


def test_22_unexpected_mutation_not_success(api_browser_e2e_result: dict[str, Any]) -> None:
    assert api_browser_e2e_result["observed"]["states"]["FAILED_UNEXPECTED_MUTATION"] != "PASS"


def test_23_security_leak_not_success(api_browser_e2e_result: dict[str, Any]) -> None:
    assert api_browser_e2e_result["observed"]["states"]["FAILED_SECURITY_LEAK"] != "PASS"


def test_24_to_26_no_dom_api_console_leak(api_browser_e2e_result: dict[str, Any]) -> None:
    assert api_browser_e2e_result["security"]["rawPathLeak"] == 0
    assert api_browser_e2e_result["security"]["rawFilenameLeak"] == 0
    assert api_browser_e2e_result["security"]["piiLeak"] == 0


def test_27_to_31_forbidden_endpoints_not_called(api_browser_e2e_result: dict[str, Any]) -> None:
    forbidden = api_browser_e2e_result["forbiddenCalls"]
    assert not any("write-production" in url for url in forbidden)
    assert not any("overwrite-source" in url for url in forbidden)
    assert not any("/deploy" in url for url in forbidden)
    assert not any("/api/ai/" in url for url in forbidden)
    assert not any("/api/ocr/" in url for url in forbidden)
    assert forbidden == []


def test_32_hancom_not_required(api_browser_e2e_result: dict[str, Any]) -> None:
    assert api_browser_e2e_result["security"]["hancomRequired"] is False


def test_33_previous_api_batch_test_exists() -> None:
    assert (ROOT / "tests" / "test_hwpx_form_auto_fill_real_like_api_batch.py").is_file()


def test_34_previous_browser_batch_test_exists() -> None:
    assert (ROOT / "tests" / "test_hwpx_form_auto_fill_real_like_browser_batch.py").is_file()


def test_35_previous_sandbox_preflight_browser_api_e2e_writer_tests_exist() -> None:
    for name in [
        "test_hwpx_form_auto_fill_real_like_sandbox_batch.py",
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
