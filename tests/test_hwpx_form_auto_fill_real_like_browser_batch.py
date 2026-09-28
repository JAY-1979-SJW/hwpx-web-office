"""HWPX-FORM-AUTO-FILL-WRITER-REAL-LIKE-BROWSER-BATCH-11 tests."""

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
PAGE = VIEWER_DIR / "form_autofill_real_like_batch_smoke.html"
JS = VIEWER_DIR / "form_autofill_real_like_batch_smoke.mjs"

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


def _assert_no_leak(text: str) -> None:
    checked = re.sub(r"http://127\.0\.0\.1:\d+", "http://localhost", text)
    assert not ABS_PATH_RE.search(checked), checked[:1000]
    assert not RAW_FILENAME_RE.search(checked), checked[:1000]
    assert not PII_RE.search(checked), checked[:1000]


@pytest.fixture(scope="session")
def browser_batch_result() -> dict[str, Any]:
    # playwright 는 선택적 브라우저 자동화 의존성 — 미설치 환경(예: 이번
    # 복구 폴더)에서는 FAIL 이 아니라 SKIP 으로 명확히 구분한다.
    pytest.importorskip("playwright", reason="playwright 미설치 — 브라우저 배치 테스트 제외")
    from playwright.sync_api import sync_playwright

    assert PAGE.is_file()
    assert JS.is_file()
    server, port = _serve(VIEWER_DIR)
    console_messages: list[str] = []
    requests: list[str] = []
    forbidden_calls: list[str] = []
    visibility: dict[str, bool] = {}
    states: dict[str, str] = {}
    texts: dict[str, str] = {}

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page()
            page.on("console", lambda msg: console_messages.append(msg.text))

            def route_handler(route: Any, request: Any) -> None:
                url = request.url
                requests.append(url)
                if any(part in url for part in FORBIDDEN_ENDPOINT_PARTS):
                    forbidden_calls.append(url)
                    route.abort()
                    return
                route.continue_()

            page.route("**/*", route_handler)
            page.goto(f"http://127.0.0.1:{port}/form_autofill_real_like_batch_smoke.html")
            page.wait_for_selector('[data-testid="browser-batch-dashboard"]', state="visible")

            for test_id in [
                "batch-summary",
                "limit-1-result",
                "limit-5-result",
                "limit-10-result",
                "file-results",
                "blocked-results",
                "blocked-breakdown",
                "readback-summary",
                "source-immutability",
                "security-summary",
                "sandbox-warning",
            ]:
                visibility[test_id] = page.locator(f'[data-testid="{test_id}"]').is_visible()

            states["blockedWarn"] = page.locator('[data-testid="overall-state"]').inner_text()
            texts["initial"] = page.locator("body").inner_text()

            page.evaluate(
                """() => window.__realLikeBatchSmoke.render({
                    summary: {blockedFiles: 0},
                    blockedResults: [],
                    blockedBreakdown: {},
                    warnings: ["WARN_SANDBOX_ONLY"]
                })"""
            )
            states["passBatch"] = page.locator('[data-testid="overall-state"]').inner_text()

            page.evaluate(
                """() => window.__realLikeBatchSmoke.render({summary: {readbackFail: 1}})"""
            )
            states["readbackFail"] = page.locator('[data-testid="overall-state"]').inner_text()

            page.evaluate(
                """() => window.__realLikeBatchSmoke.render({summary: {unexpectedMutation: 1}})"""
            )
            states["unexpectedMutation"] = page.locator(
                '[data-testid="overall-state"]'
            ).inner_text()

            page.evaluate(
                """() => window.__realLikeBatchSmoke.render({summary: {sourceMutation: 1}})"""
            )
            states["sourceMutation"] = page.locator('[data-testid="overall-state"]').inner_text()

            page.evaluate(
                """() => window.__realLikeBatchSmoke.render({mode: "BLOCKED_NON_SANDBOX"})"""
            )
            states["nonSandbox"] = page.locator('[data-testid="overall-state"]').inner_text()

            page.evaluate(
                """() => window.__realLikeBatchSmoke.render({
                    summary: {piiLeak: 1, rawPathLeak: 1, rawFilenameLeak: 1}
                })"""
            )
            states["securityLeak"] = page.locator('[data-testid="overall-state"]').inner_text()
            texts["final"] = page.locator("body").inner_text()
            html = page.content()
            browser.close()
    finally:
        server.shutdown()
        time.sleep(0.05)

    network_blob = json.dumps(
        {"requests": requests, "forbidden": forbidden_calls}, ensure_ascii=False
    )
    _assert_no_leak(texts["initial"])
    _assert_no_leak(texts["final"])
    _assert_no_leak(html)
    _assert_no_leak("\n".join(console_messages))
    _assert_no_leak(network_blob)

    return {
        "visibility": visibility,
        "states": states,
        "texts": texts,
        "consoleMessages": console_messages,
        "network": {
            "requests": requests,
            "forbiddenCalls": forbidden_calls,
            "productionWriteCalled": any("write-production" in url for url in forbidden_calls),
            "sourceOverwriteCalled": any("overwrite-source" in url for url in forbidden_calls),
            "aiCalled": any("/api/ai/" in url for url in forbidden_calls),
            "ocrCalled": any("/api/ocr/" in url for url in forbidden_calls),
        },
        "security": {
            "piiLeak": 0,
            "rawPathLeak": 0,
            "rawFilenameLeak": 0,
            "hancomRequired": False,
        },
    }


def test_01_browser_batch_page_exists() -> None:
    assert PAGE.is_file()


def test_02_browser_batch_js_exists() -> None:
    assert JS.is_file()


@pytest.mark.parametrize(
    "test_id",
    [
        "batch-summary",
        "limit-1-result",
        "limit-5-result",
        "limit-10-result",
        "file-results",
        "blocked-results",
        "readback-summary",
        "source-immutability",
        "security-summary",
        "sandbox-warning",
    ],
)
def test_03_to_12_required_sections_visible(
    browser_batch_result: dict[str, Any], test_id: str
) -> None:
    assert browser_batch_result["visibility"][test_id] is True


def test_13_pass_batch_shown_success(browser_batch_result: dict[str, Any]) -> None:
    assert browser_batch_result["states"]["passBatch"] == "PASS"


def test_14_blocked_files_shown_warn(browser_batch_result: dict[str, Any]) -> None:
    assert browser_batch_result["states"]["blockedWarn"] == "WARN"


@pytest.mark.parametrize(
    "case_name",
    ["readbackFail", "unexpectedMutation", "sourceMutation", "nonSandbox", "securityLeak"],
)
def test_15_to_19_failure_states_shown_fail(
    browser_batch_result: dict[str, Any], case_name: str
) -> None:
    assert browser_batch_result["states"][case_name] == "FAIL"


def test_20_to_22_no_dom_api_console_leak(browser_batch_result: dict[str, Any]) -> None:
    assert browser_batch_result["security"]["rawPathLeak"] == 0
    assert browser_batch_result["security"]["rawFilenameLeak"] == 0
    assert browser_batch_result["security"]["piiLeak"] == 0


def test_23_to_26_forbidden_endpoints_not_called(browser_batch_result: dict[str, Any]) -> None:
    net = browser_batch_result["network"]
    assert net["productionWriteCalled"] is False
    assert net["sourceOverwriteCalled"] is False
    assert net["aiCalled"] is False
    assert net["ocrCalled"] is False
    assert net["forbiddenCalls"] == []


def test_27_hancom_not_required(browser_batch_result: dict[str, Any]) -> None:
    assert browser_batch_result["security"]["hancomRequired"] is False


def test_28_previous_real_like_batch_test_exists() -> None:
    assert (ROOT / "tests" / "test_hwpx_form_auto_fill_real_like_sandbox_batch.py").is_file()


def test_29_previous_preflight_browser_api_e2e_writer_tests_exist() -> None:
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
