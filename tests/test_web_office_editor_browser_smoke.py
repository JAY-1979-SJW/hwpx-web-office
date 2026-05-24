from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
URL_PATH = "/web-office/"
PASS_STATUS = "Backend save apply completed."
RAW_PATH_RE = re.compile(r"(?<![A-Za-z])([A-Za-z]:[\\/][^\s\"']*|/(home|tmp|var|Users)/[^\s\"']*)")
RAW_FILENAME_RE = re.compile(r"\b[^\\/:\s]+\.hwpx\b", re.IGNORECASE)
PII_RE = re.compile(
    r"(\d{6}-\d{7}|\d{3}-\d{2}-\d{5}|\d{2,3}-\d{3,4}-\d{4}|"
    r"\d{2,6}-\d{2,6}-\d{2,6}|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})"
)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_health(base_url: str, proc: subprocess.Popen[str]) -> None:
    last_error = ""
    for _ in range(80):
        if proc.poll() is not None:
            raise RuntimeError(f"uvicorn exited early: {proc.returncode}")
        try:
            with urllib.request.urlopen(f"{base_url}/api/web-office/health", timeout=2) as response:
                body = json.loads(response.read().decode("utf-8"))
            if body.get("status") == "SUCCESS":
                return
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            last_error = str(exc)
            time.sleep(0.25)
    raise RuntimeError(f"health endpoint did not become ready: {last_error}")


def _has_leak(text: str) -> bool:
    return bool(RAW_PATH_RE.search(text) or RAW_FILENAME_RE.search(text) or PII_RE.search(text))


@pytest.fixture(scope="session")
def editor_browser_smoke_result(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # pragma: no cover - environment failure path
        pytest.fail(f"playwright import failed: {exc}")

    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    out_dir = tmp_path_factory.mktemp("web_office_editor_browser_outputs")
    log_path = out_dir / "server.log"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    env["HWPX_WEB_OFFICE_API_OUTPUT_DIR"] = str(out_dir)
    log_handle = log_path.open("w", encoding="utf-8")
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "scripts.hwpx.web_office.editor_api_route:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=str(ROOT),
        env=env,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        text=True,
    )

    console_messages: list[str] = []
    page_errors: list[str] = []
    failed_requests: list[str] = []
    api_responses: list[dict[str, Any]] = []
    observed: dict[str, Any] = {}

    try:
        _wait_health(base_url, proc)
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page()
            page.on("console", lambda msg: console_messages.append(msg.text))
            page.on("pageerror", lambda exc: page_errors.append(str(exc)))
            page.on("requestfailed", lambda req: failed_requests.append(req.url))

            def on_response(response: Any) -> None:
                if "/api/web-office/" not in response.url:
                    return
                try:
                    api_responses.append({
                        "url": response.url,
                        "status": response.status,
                        "body": response.json(),
                    })
                except Exception:
                    api_responses.append({"url": response.url, "status": response.status})

            page.on("response", on_response)
            page.goto(f"{base_url}{URL_PATH}", wait_until="networkidle")
            page.get_by_role("button", name="Load sample").click()
            page.wait_for_selector("[data-cell-id]", state="visible", timeout=30000)

            first_cell = page.locator("[data-cell-id]").nth(0)
            first_cell.click()
            textarea = page.locator("[data-role='cell-text']")
            textarea.fill("BROWSER_SMOKE_50_OK")
            page.get_by_role("button", name="Commit cell text").click()
            page.wait_for_function(
                "() => document.querySelector('[data-role=\"command-count\"]')?.textContent === '1'",
                timeout=10000,
            )
            page.get_by_role("button", name="Save apply").click()
            page.wait_for_function(
                f"() => document.querySelector('[data-role=\"status\"]')?.textContent === {json.dumps(PASS_STATUS)}",
                timeout=30000,
            )
            body_text = page.locator("body").inner_text()
            observed = {
                "url": page.url,
                "statusText": page.locator("[data-role='status']").inner_text(),
                "cellCount": page.locator("[data-cell-id]").count(),
                "commandCount": page.locator("[data-role='command-count']").inner_text(),
                "domLeak": _has_leak(body_text),
                "consoleLeak": _has_leak("\n".join(console_messages)),
            }
            browser.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=10)
        log_handle.close()

    return {
        "observed": observed,
        "consoleMessages": console_messages,
        "pageErrors": page_errors,
        "failedRequests": failed_requests,
        "apiResponses": api_responses,
    }


def test_editor_browser_smoke_load_edit_save(editor_browser_smoke_result: dict[str, Any]) -> None:
    observed = editor_browser_smoke_result["observed"]
    assert observed["url"].endswith(URL_PATH)
    assert observed["statusText"] == PASS_STATUS
    assert observed["cellCount"] >= 1
    assert observed["commandCount"] == "0"


def test_editor_browser_smoke_has_no_runtime_errors(editor_browser_smoke_result: dict[str, Any]) -> None:
    assert editor_browser_smoke_result["pageErrors"] == []
    assert editor_browser_smoke_result["failedRequests"] == []
    assert all(item["status"] < 400 for item in editor_browser_smoke_result["apiResponses"])


def test_editor_browser_smoke_has_no_browser_leaks(editor_browser_smoke_result: dict[str, Any]) -> None:
    observed = editor_browser_smoke_result["observed"]
    assert observed["domLeak"] is False
    assert observed["consoleLeak"] is False
    for item in editor_browser_smoke_result["apiResponses"]:
        body = item.get("body", {})
        assert "outputPath" not in repr(body)
        assert body.get("mode") in {None, "SANDBOX_ONLY"}
        assert body.get("sourceMutationAllowed") in {None, False}
