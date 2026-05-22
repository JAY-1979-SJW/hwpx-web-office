"""
HWPX-FORM-AUTO-FILL-WRITER-BROWSER-SMOKE-08

Actual Chromium smoke for the synthetic SANDBOX_ONLY form autofill screen.
No user files, real HWPX writes, AI, OCR, or Hancom runtime are used.
"""

from __future__ import annotations

import json
import re
import socket
import threading
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
VIEWER_DIR = ROOT / "frontend" / "web_office_viewer"
SMOKE_HTML = VIEWER_DIR / "form_autofill_browser_smoke.html"

ABS_PATH_RE = re.compile(r"(?<![A-Za-z])([A-Za-z]:[\\/]|/(home|tmp|var|Users)/)")
RAW_FILENAME_RE = re.compile(r"\b[^\\/:\s]+\.hwpx\b", re.IGNORECASE)
PII_RE = re.compile(
    r"(\d{6}-\d{7}|\d{3}-\d{2}-\d{5}|\d{2,3}-\d{3,4}-\d{4}|"
    r"\d{2,6}-\d{2,6}-\d{2,6}|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})"
)

FORBIDDEN_ENDPOINT_PARTS = (
    "/api/hwpx/form-autofill/write-production",
    "/api/hwpx/form-autofill/overwrite-source",
    "/api/hwpx/form-autofill/deploy",
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


def _redact_dynamic_ids(text: str) -> str:
    return re.sub(r"(requestId|outputFileId|finalExportId)=[^\s\"']+", r"\1=<id>", text)


def _assert_no_leak(blob: str) -> None:
    checked = _redact_dynamic_ids(blob)
    assert not ABS_PATH_RE.search(checked), checked[:1000]
    assert not RAW_FILENAME_RE.search(checked), checked[:1000]
    assert not PII_RE.search(checked), checked[:1000]
    assert "approvedValue" not in checked


@pytest.fixture(scope="session")
def browser_smoke_result() -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # pragma: no cover - environment failure path
        pytest.fail(f"playwright import failed: {exc}")

    assert SMOKE_HTML.is_file()
    server, port = _serve(VIEWER_DIR)
    console_messages: list[str] = []
    requests: list[dict[str, Any]] = []
    api_responses: list[dict[str, Any]] = []
    forbidden_calls: list[str] = []
    button_matrix: dict[str, dict[str, Any]] = {}
    failure_matrix: dict[str, dict[str, Any]] = {}

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page()
            page.on("console", lambda msg: console_messages.append(msg.text))

            def route_handler(route: Any, request: Any) -> None:
                url = request.url
                post_data = request.post_data or ""
                if any(part in url for part in FORBIDDEN_ENDPOINT_PARTS):
                    forbidden_calls.append(url)
                    route.abort()
                    return
                if url.endswith("/api/hwpx/form-autofill/write-sandbox"):
                    payload = json.loads(post_data or "{}")
                    requests.append({"url": url, "method": request.method, "payload": payload})
                    response = {
                        "schemaVersion": "hwpx_form_autofill_api_v1",
                        "requestId": "req_browser_smoke_08",
                        "status": "SUCCESS",
                        "mode": "SANDBOX_ONLY",
                        "sourceMutationAllowed": False,
                        "data": {
                            "writerStatus": "SUCCESS",
                            "readbackFail": 0,
                            "sourceMutated": False,
                            "outputFileId": "out_browser_smoke_08",
                            "finalExportId": "final_browser_smoke_08",
                        },
                        "warnings": ["WARN_SANDBOX_ONLY"],
                        "errors": [],
                    }
                    api_responses.append(response)
                    route.fulfill(
                        status=200,
                        content_type="application/json",
                        body=json.dumps(response),
                    )
                    return
                route.continue_()

            page.route("**/*", route_handler)
            page.goto(f"http://127.0.0.1:{port}/form_autofill_browser_smoke.html")
            page.wait_for_selector('[data-testid="form-autofill-workspace"]', state="visible")

            visible = {
                test_id: page.locator(f'[data-testid="{test_id}"]').is_visible()
                for test_id in (
                    "recommend-section",
                    "parser-section",
                    "auto-fill-ready",
                    "needs-review",
                    "missing-required",
                    "required-attachments",
                    "approval-panel",
                    "write-sandbox-button",
                    "sandbox-warning",
                    "readback-result",
                    "download-review-status",
                    "final-export-status",
                )
            }
            page_text = page.locator("body").inner_text()
            sandbox_warning = (
                "원본 HWPX는 수정하지 않고 sandbox 복사본에만 작성합니다."
                in page_text
            )

            matrix_cases = {
                "READY_FOR_WRITER": ({}, True),
                "BLOCKED_NEEDS_REVIEW": (
                    {"approvalStatus": "BLOCKED_NEEDS_REVIEW",
                     "needsReview": [{"fieldKey": "review_1", "reason": "masked conflict"}]},
                    False,
                ),
                "BLOCKED_MISSING_REQUIRED": (
                    {"approvalStatus": "BLOCKED_MISSING_REQUIRED",
                     "missingRequired": [{"fieldKey": "required_1", "label": "필수값", "required": True}]},
                    False,
                ),
                "BLOCKED_ATTACHMENT_MISSING": (
                    {"approvalStatus": "BLOCKED_ATTACHMENT_MISSING",
                     "requiredAttachments": [{"docType": "검토 첨부", "neededFor": ["masked"]}]},
                    False,
                ),
                "HOLD_BY_USER": ({"approvalStatus": "HOLD_BY_USER"}, False),
                "writerEligible_false": ({"writerEligible": False}, False),
                "approvedFields_zero": ({"approvedFields": []}, False),
                "mode_not_sandbox": ({"mode": "REJECTED_MODE"}, False),
            }

            for name, (overrides, expected_enabled) in matrix_cases.items():
                page.evaluate("overrides => window.__hwpxFormAutoFillSmoke.render(overrides)", overrides)
                button = page.locator('[data-testid="write-sandbox-button"]')
                reason = page.locator('[data-testid="button-disabled-reason"]').inner_text()
                enabled = button.is_enabled()
                button_matrix[name] = {
                    "expectedEnabled": expected_enabled,
                    "actualEnabled": enabled,
                    "reason": reason,
                }

            page.evaluate("() => window.__hwpxFormAutoFillSmoke.render({})")
            with page.expect_event("request", lambda req: req.url.endswith("/api/hwpx/form-autofill/write-sandbox")):
                page.locator('[data-testid="write-sandbox-button"]').click()
            page.wait_for_function("() => document.querySelector('[data-testid=\"writer-status\"]').textContent.includes('작성 성공')")

            for status in ("SUCCESS", "FAILED_READBACK", "FAILED_SOURCE_MUTATED", "FAILED_OUTPUT_BROKEN"):
                page.evaluate("status => window.__hwpxFormAutoFillSmoke.setWriterStatus(status)", status)
                failure_matrix[status] = {
                    "writerStatusText": page.locator('[data-testid="writer-status"]').inner_text(),
                    "readbackText": page.locator('[data-testid="readback-status"]').inner_text(),
                    "sourceMutationText": page.locator('[data-testid="source-mutation-status"]').inner_text(),
                    "downloadText": page.locator('[data-testid="download-status"]').inner_text(),
                    "finalExportText": page.locator('[data-testid="final-export-enabled"]').inner_text(),
                }

            final_dom_text = page.locator("body").inner_text()
            final_html = page.content()
            browser.close()
    finally:
        server.shutdown()
        time.sleep(0.05)

    network_blob = json.dumps({"requests": requests, "responses": api_responses}, ensure_ascii=False)
    _assert_no_leak(page_text)
    _assert_no_leak(final_dom_text)
    _assert_no_leak(final_html)
    _assert_no_leak(network_blob)
    _assert_no_leak("\n".join(console_messages))

    return {
        "pageLoaded": True,
        "visible": visible,
        "sandboxWarning": sandbox_warning,
        "buttonMatrix": button_matrix,
        "network": {
            "requests": requests,
            "responses": api_responses,
            "forbiddenCalls": forbidden_calls,
        },
        "failureMatrix": failure_matrix,
        "consoleMessages": console_messages,
        "leakChecks": {
            "rawPath": 0,
            "rawFilename": 0,
            "pii": 0,
            "approvedValue": 0,
        },
    }


def test_01_browser_page_loaded(browser_smoke_result: dict[str, Any]) -> None:
    assert browser_smoke_result["pageLoaded"] is True


@pytest.mark.parametrize(
    "test_id",
    [
        "recommend-section",
        "parser-section",
        "auto-fill-ready",
        "needs-review",
        "missing-required",
        "required-attachments",
        "sandbox-warning",
        "approval-panel",
        "readback-result",
        "download-review-status",
        "final-export-status",
    ],
)
def test_02_required_sections_visible(browser_smoke_result: dict[str, Any], test_id: str) -> None:
    assert browser_smoke_result["visible"][test_id] is True


def test_03_sandbox_warning_visible(browser_smoke_result: dict[str, Any]) -> None:
    assert browser_smoke_result["sandboxWarning"] is True


@pytest.mark.parametrize(
    ("case_name", "expected"),
    [
        ("READY_FOR_WRITER", True),
        ("BLOCKED_NEEDS_REVIEW", False),
        ("BLOCKED_MISSING_REQUIRED", False),
        ("BLOCKED_ATTACHMENT_MISSING", False),
        ("HOLD_BY_USER", False),
        ("writerEligible_false", False),
        ("approvedFields_zero", False),
        ("mode_not_sandbox", False),
    ],
)
def test_04_button_state_matrix(browser_smoke_result: dict[str, Any], case_name: str, expected: bool) -> None:
    row = browser_smoke_result["buttonMatrix"][case_name]
    assert row["actualEnabled"] is expected
    if not expected:
        assert "비활성화 사유" in row["reason"]


def test_05_write_sandbox_api_called_on_click(browser_smoke_result: dict[str, Any]) -> None:
    requests = browser_smoke_result["network"]["requests"]
    assert len(requests) == 1
    assert requests[0]["method"] == "POST"
    assert requests[0]["url"].endswith("/api/hwpx/form-autofill/write-sandbox")


def test_06_write_payload_is_sandbox_only(browser_smoke_result: dict[str, Any]) -> None:
    payload = browser_smoke_result["network"]["requests"][0]["payload"]
    assert payload["mode"] == "SANDBOX_ONLY"
    assert payload["sourceMutationAllowed"] is False
    assert "source_path" not in payload
    assert "output_path" not in payload
    assert "approvedValue" not in json.dumps(payload, ensure_ascii=False)
    assert payload["approvalResultDict"]["approvedFields"]


@pytest.mark.parametrize(
    ("status", "expected_text"),
    [
        ("SUCCESS", "작성 성공"),
        ("FAILED_READBACK", "readback 실패"),
        ("FAILED_SOURCE_MUTATED", "원본 변경 위험 실패"),
        ("FAILED_OUTPUT_BROKEN", "출력 파일 손상"),
    ],
)
def test_07_result_status_ui(browser_smoke_result: dict[str, Any], status: str, expected_text: str) -> None:
    row = browser_smoke_result["failureMatrix"][status]
    assert expected_text in row["writerStatusText"]
    if status != "SUCCESS":
        assert "차단" in row["downloadText"]
        assert "차단" in row["finalExportText"]


def test_08_download_and_final_export_status(browser_smoke_result: dict[str, Any]) -> None:
    success = browser_smoke_result["failureMatrix"]["SUCCESS"]
    assert "검토용 다운로드 가능" in success["downloadText"]
    assert "최종 산출물 후보" in success["finalExportText"]


def test_09_no_screen_api_console_leak(browser_smoke_result: dict[str, Any]) -> None:
    assert browser_smoke_result["leakChecks"] == {
        "rawPath": 0,
        "rawFilename": 0,
        "pii": 0,
        "approvedValue": 0,
    }


def test_10_no_forbidden_runtime_calls(browser_smoke_result: dict[str, Any]) -> None:
    assert browser_smoke_result["network"]["forbiddenCalls"] == []


def test_11_ai_ocr_hancom_not_required() -> None:
    src = (VIEWER_DIR / "form_autofill_browser_smoke.mjs").read_text(encoding="utf-8").lower()
    for token in ("openai", "anthropic", "chatcompletion", "gemini", "pytesseract", "easyocr", "paddleocr"):
        assert token not in src
    for token in ("hwp5", "pyhwp", "hwpctrl", "import hancom"):
        assert token not in src
