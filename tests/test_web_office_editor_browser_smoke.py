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
LOAD_FAIL_STATUS = "hwpx editor load failed: load rejected"
SAVE_FAIL_STATUS = "cell save apply failed: save rejected"
SAVE_BLOCKED_STATUS = "Save was blocked by backend validation."
VIEWPORTS = {
    "desktop": {"width": 1366, "height": 900},
    "mobile": {"width": 390, "height": 844},
}
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


def _overlap(a: dict[str, float], b: dict[str, float]) -> bool:
    return not (
        a["x"] + a["width"] <= b["x"]
        or b["x"] + b["width"] <= a["x"]
        or a["y"] + a["height"] <= b["y"]
        or b["y"] + b["height"] <= a["y"]
    )


def _start_editor_server(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[subprocess.Popen[str], Any, str]:
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
    _wait_health(base_url, proc)
    return proc, log_handle, base_url


def _stop_editor_server(proc: subprocess.Popen[str], log_handle: Any) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=10)
    log_handle.close()


@pytest.fixture(scope="session")
def editor_browser_smoke_result(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # pragma: no cover - environment failure path
        pytest.fail(f"playwright import failed: {exc}")

    proc, log_handle, base_url = _start_editor_server(tmp_path_factory)

    console_messages: list[str] = []
    page_errors: list[str] = []
    failed_requests: list[str] = []
    api_responses: list[dict[str, Any]] = []
    observed: dict[str, Any] = {}

    try:
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
        _stop_editor_server(proc, log_handle)

    return {
        "observed": observed,
        "consoleMessages": console_messages,
        "pageErrors": page_errors,
        "failedRequests": failed_requests,
        "apiResponses": api_responses,
    }


@pytest.fixture(scope="session")
def editor_failure_state_result(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # pragma: no cover - environment failure path
        pytest.fail(f"playwright import failed: {exc}")

    proc, log_handle, base_url = _start_editor_server(tmp_path_factory)
    result: dict[str, Any] = {
        "pageErrors": [],
        "failedRequests": [],
        "scenarios": {},
    }

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)

            def new_page() -> Any:
                page = browser.new_page()
                page.on("pageerror", lambda exc: result["pageErrors"].append(str(exc)))
                page.on("requestfailed", lambda req: result["failedRequests"].append(req.url))
                return page

            page = new_page()
            page.route(
                "**/api/web-office/hwpx-load",
                lambda route: route.fulfill(
                    status=500,
                    content_type="application/json",
                    body=json.dumps({
                        "status": "FAILED",
                        "errors": [{"message": "load rejected"}],
                    }),
                ),
            )
            page.goto(f"{base_url}{URL_PATH}", wait_until="networkidle")
            page.get_by_role("button", name="Load sample").click()
            page.wait_for_function(
                f"() => document.querySelector('[data-role=\"status\"]')?.textContent === {json.dumps(LOAD_FAIL_STATUS)}",
                timeout=10000,
            )
            result["scenarios"]["load_http_fail"] = {
                "statusKind": page.locator("[data-role='status']").get_attribute("data-status"),
                "statusText": page.locator("[data-role='status']").inner_text(),
                "successShown": PASS_STATUS in page.locator("body").inner_text(),
            }
            page.close()

            for scenario, response_status, response_body, expected_text in (
                (
                    "save_blocked",
                    200,
                    {
                        "status": "SUCCESS",
                        "mode": "SANDBOX_ONLY",
                        "sourceMutationAllowed": False,
                        "data": {"verdict": "REJECTED"},
                        "errors": [],
                    },
                    SAVE_BLOCKED_STATUS,
                ),
                (
                    "save_http_fail",
                    500,
                    {
                        "status": "FAILED",
                        "mode": "SANDBOX_ONLY",
                        "sourceMutationAllowed": False,
                        "errors": [{"message": "save rejected"}],
                    },
                    SAVE_FAIL_STATUS,
                ),
            ):
                page = new_page()

                def save_route(
                    route: Any,
                    _request: Any = None,
                    *,
                    status: int = response_status,
                    body: dict[str, Any] = response_body,
                ) -> None:
                    route.fulfill(
                        status=status,
                        content_type="application/json",
                        body=json.dumps(body),
                    )

                page.route("**/api/web-office/cell-save-apply", save_route)
                page.goto(f"{base_url}{URL_PATH}", wait_until="networkidle")
                page.get_by_role("button", name="Load sample").click()
                page.wait_for_selector("[data-cell-id]", state="visible", timeout=30000)
                page.locator("[data-cell-id]").nth(0).click()
                page.locator("[data-role='cell-text']").fill(f"BROWSER_SMOKE_51_{scenario}")
                page.get_by_role("button", name="Commit cell text").click()
                page.wait_for_function(
                    "() => document.querySelector('[data-role=\"command-count\"]')?.textContent === '1'",
                    timeout=10000,
                )
                page.get_by_role("button", name="Save apply").click()
                page.wait_for_function(
                    f"() => document.querySelector('[data-role=\"status\"]')?.textContent === {json.dumps(expected_text)}",
                    timeout=10000,
                )
                result["scenarios"][scenario] = {
                    "statusKind": page.locator("[data-role='status']").get_attribute("data-status"),
                    "statusText": page.locator("[data-role='status']").inner_text(),
                    "successShown": PASS_STATUS in page.locator("body").inner_text(),
                    "commandCount": page.locator("[data-role='command-count']").inner_text(),
                }
                page.close()

            browser.close()
    finally:
        _stop_editor_server(proc, log_handle)

    return result


@pytest.fixture(scope="session")
def editor_visual_smoke_result(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # pragma: no cover - environment failure path
        pytest.fail(f"playwright import failed: {exc}")

    proc, log_handle, base_url = _start_editor_server(tmp_path_factory)
    result: dict[str, Any] = {
        "pageErrors": [],
        "failedRequests": [],
        "viewports": {},
    }

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            for name, viewport in VIEWPORTS.items():
                page = browser.new_page(viewport=viewport)
                page.on("pageerror", lambda exc: result["pageErrors"].append(str(exc)))
                page.on("requestfailed", lambda req: result["failedRequests"].append(req.url))
                page.goto(f"{base_url}{URL_PATH}", wait_until="networkidle")
                page.get_by_role("button", name="Load sample").click()
                page.wait_for_selector("[data-cell-id]", state="visible", timeout=30000)

                appbar = page.locator(".wo-appbar").bounding_box()
                status = page.locator("[data-role='status']").bounding_box()
                document = page.locator("[data-role='cell-list']").bounding_box()
                inspector = page.locator(".wo-inspector").bounding_box()
                first_cell = page.locator("[data-cell-id]").nth(0)
                first_cell_box = first_cell.bounding_box()
                screenshot = page.screenshot(full_page=False)
                body_text = page.locator("body").inner_text()
                required_visible = {
                    "title": page.get_by_text("HWPX Web Office").first.is_visible(),
                    "load": page.get_by_role("button", name="Load sample").is_visible(),
                    "save": page.get_by_role("button", name="Save apply").is_visible(),
                    "status": page.locator("[data-role='status']").is_visible(),
                    "document": page.locator("[data-role='cell-list']").is_visible(),
                    "inspector": page.locator(".wo-inspector").is_visible(),
                    "firstCell": first_cell.is_visible(),
                }
                boxes_present = all(box is not None for box in (appbar, status, document, inspector, first_cell_box))
                layout_ok = False
                if boxes_present:
                    if name == "desktop":
                        layout_ok = (
                            status["y"] >= appbar["y"] + appbar["height"]
                            and document["y"] >= status["y"] + status["height"]
                            and inspector["y"] >= status["y"] + status["height"]
                            and not _overlap(document, inspector)
                            and first_cell_box["width"] > 40
                            and first_cell_box["height"] > 40
                        )
                    else:
                        layout_ok = (
                            status["y"] >= appbar["y"] + appbar["height"]
                            and document["y"] >= status["y"] + status["height"]
                            and inspector["y"] >= document["y"] + document["height"]
                            and not _overlap(document, inspector)
                            and first_cell_box["width"] > 40
                            and first_cell_box["height"] > 40
                        )
                result["viewports"][name] = {
                    "requiredVisible": required_visible,
                    "boxesPresent": boxes_present,
                    "layoutOk": layout_ok,
                    "nonBlankScreenshot": len(set(screenshot[:2048])) > 1,
                    "domLeak": _has_leak(body_text),
                }
                page.close()
            browser.close()
    finally:
        _stop_editor_server(proc, log_handle)

    return result


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


def test_editor_failure_states_are_not_success(editor_failure_state_result: dict[str, Any]) -> None:
    scenarios = editor_failure_state_result["scenarios"]
    assert scenarios["load_http_fail"] == {
        "statusKind": "fail",
        "statusText": LOAD_FAIL_STATUS,
        "successShown": False,
    }
    assert scenarios["save_blocked"]["statusKind"] == "blocked"
    assert scenarios["save_blocked"]["statusText"] == SAVE_BLOCKED_STATUS
    assert scenarios["save_blocked"]["successShown"] is False
    assert scenarios["save_blocked"]["commandCount"] == "1"
    assert scenarios["save_http_fail"]["statusKind"] == "fail"
    assert scenarios["save_http_fail"]["statusText"] == SAVE_FAIL_STATUS
    assert scenarios["save_http_fail"]["successShown"] is False
    assert scenarios["save_http_fail"]["commandCount"] == "1"


def test_editor_failure_states_have_no_runtime_errors(editor_failure_state_result: dict[str, Any]) -> None:
    assert editor_failure_state_result["pageErrors"] == []


def test_editor_visual_smoke_desktop_and_mobile(editor_visual_smoke_result: dict[str, Any]) -> None:
    assert set(editor_visual_smoke_result["viewports"]) == {"desktop", "mobile"}
    for item in editor_visual_smoke_result["viewports"].values():
        assert all(item["requiredVisible"].values())
        assert item["boxesPresent"] is True
        assert item["layoutOk"] is True
        assert item["nonBlankScreenshot"] is True
        assert item["domLeak"] is False


def test_editor_visual_smoke_has_no_runtime_errors(editor_visual_smoke_result: dict[str, Any]) -> None:
    assert editor_visual_smoke_result["pageErrors"] == []
    assert editor_visual_smoke_result["failedRequests"] == []
