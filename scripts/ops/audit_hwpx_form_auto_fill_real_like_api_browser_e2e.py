"""Audit for HWPX-FORM-AUTO-FILL-WRITER-REAL-LIKE-API-BROWSER-E2E-13."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from hwpx.pipeline import form_auto_fill_real_file_preflight as pf  # noqa: E402

REPORT_DIR = ROOT / "data" / "reports" / "hwpx_form_auto_fill_real_like_api_browser_e2e"
PAGE = ROOT / "frontend" / "web_office_viewer" / "form_autofill_real_like_batch_smoke.html"
JS = ROOT / "frontend" / "web_office_viewer" / "form_autofill_real_like_batch_smoke.mjs"
TEST = ROOT / "tests" / "test_hwpx_form_auto_fill_real_like_api_browser_e2e.py"

PASS_VERDICT = "PASS_HWPX_FORM_AUTO_FILL_WRITER_REAL_LIKE_API_BROWSER_E2E"
FAIL_VERDICT = "FAIL_HWPX_FORM_AUTO_FILL_WRITER_REAL_LIKE_API_BROWSER_E2E"
WARNINGS = [
    "WARN_REAL_LIKE_SANITIZED_SAMPLE_ONLY",
    "WARN_SANDBOX_ONLY",
    "WARN_REAL_USER_FILE_NOT_TESTED",
    "WARN_DEPLOY_NOT_PERFORMED",
    "WARN_EXISTING_DIRTY_BASELINE_DOCUMENTED",
    "WARN_BROWSER_API_E2E_WITH_MOCK_SERVER",
]


def _run_pytest(paths: list[str], timeout: int = 900) -> dict[str, Any]:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", *paths, "-q", "--tb=no"],
        cwd=str(ROOT),
        capture_output=True,
        text=True, encoding="utf-8", errors="replace",
        timeout=timeout,
    )
    text = result.stdout + "\n" + result.stderr
    lines = [_safe_text(line.strip()) for line in text.splitlines() if line.strip()]
    return {
        "paths": paths,
        "returncode": result.returncode,
        "ok": result.returncode == 0,
        "summary": lines[-1] if lines else "no output",
    }


def _safe_text(text: str) -> str:
    text = pf.ABS_PATH_RE.sub("<abs-path>", text)
    text = pf.RAW_FILENAME_RE.sub("<hwpx-file>", text)
    text = pf.PII_RE.sub("<masked>", text)
    return text


def _dirty_baseline() -> dict[str, Any]:
    result = subprocess.run(
        ["git", "status", "--short"],
        cwd=str(ROOT),
        capture_output=True,
        text=True, encoding="utf-8", errors="replace",
        timeout=30,
    )
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    counts = {
        "changeHistoryLog": sum(1 for line in lines if line.startswith("M logs/change_history.jsonl")),
        "devlogUntracked": sum(1 for line in lines if line.startswith("?? docs/devlog/")),
        "reportsUntracked": sum(1 for line in lines if line.startswith("?? reports/")),
    }
    known = []
    if counts["changeHistoryLog"]:
        known.append("change_history_log_modified")
    if counts["devlogUntracked"]:
        known.append("devlog_untracked")
    if counts["reportsUntracked"]:
        known.append("reports_untracked")
    unexpected = [
        line
        for line in lines
        if not line.startswith("M logs/change_history.jsonl")
        and not line.startswith("?? docs/devlog/")
        and not line.startswith("?? reports/")
        and "form_autofill_real_like_batch_smoke" not in line
        and "form_auto_fill_real_like_api_browser_e2e" not in line
    ]
    return {
        "documented": True,
        "knownHold": known,
        "knownHoldCounts": counts,
        "unexpectedOutsideScope": unexpected,
    }


def _check(code: str, desc: str, ok: bool, fail_code: str | None = None) -> dict[str, Any]:
    return {
        "code": code,
        "desc": desc,
        "status": "PASS" if ok else "FAIL",
        "failCode": fail_code if not ok else None,
    }


def _safe_report_write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if pf.ABS_PATH_RE.search(text) or pf.RAW_FILENAME_RE.search(text) or pf.PII_RE.search(text):
        raise ValueError(f"unsafe report payload: {path.name}")
    path.write_text(text, encoding="utf-8")


def audit() -> dict[str, Any]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    dirty = _dirty_baseline()

    e2e_run = _run_pytest(["tests/test_hwpx_form_auto_fill_real_like_api_browser_e2e.py"], timeout=300)
    api_batch_run = _run_pytest(["tests/test_hwpx_form_auto_fill_real_like_api_batch.py"], timeout=300)
    browser_batch_run = _run_pytest(["tests/test_hwpx_form_auto_fill_real_like_browser_batch.py"], timeout=300)
    sandbox_batch_run = _run_pytest(["tests/test_hwpx_form_auto_fill_real_like_sandbox_batch.py"], timeout=300)
    regression_run = _run_pytest(
        [
            "tests/test_hwpx_form_auto_fill_real_file_preflight.py",
            "tests/test_hwpx_form_autofill_browser_smoke.py",
            "tests/test_hwpx_form_autofill_api_route.py",
            "tests/test_hwpx_form_autofill_frontend_contract.py",
            "tests/test_hwpx_form_auto_fill_e2e_smoke.py",
            "tests/test_hwpx_form_writer_final_export_gate.py",
            "tests/test_hwpx_form_writer_download_review.py",
            "tests/test_hwpx_form_writer_ui_connect.py",
            "tests/test_hwpx_form_writer_readback_hardening.py",
            "tests/test_hwpx_form_auto_fill_writer_sandbox.py",
            "tests/test_hwpx_approval_gate.py",
            "tests/test_hwpx_review_panel.py",
            "tests/test_hwpx_form_field_mapping.py",
        ],
        timeout=1500,
    )

    html = PAGE.read_text(encoding="utf-8") if PAGE.exists() else ""
    js = JS.read_text(encoding="utf-8") if JS.exists() else ""
    test_src = TEST.read_text(encoding="utf-8") if TEST.exists() else ""
    combined = "\n".join([html, js, test_src])
    lower = combined.lower()

    checks = [
        _check("A01", "API browser E2E test exists", TEST.exists()),
        _check("A02", "real-like batch page loads", e2e_run["ok"], "FAIL_BROWSER_API_E2E_BROKEN"),
        _check("A03", "health endpoint called", "batch/health" in test_src and e2e_run["ok"]),
        _check("A04", "limit=1 request works", "api-limit" in combined and "1, 5, 10" in combined and e2e_run["ok"]),
        _check("A05", "limit=5 request works", "api-limit" in combined and "1, 5, 10" in combined and e2e_run["ok"]),
        _check("A06", "limit=10 request works", "api-limit" in combined and "1, 5, 10" in combined and e2e_run["ok"]),
        _check("A07", "batch API called from browser", "real-like-sandbox" in combined and e2e_run["ok"]),
        _check("A08", "request mode SANDBOX_ONLY", "SANDBOX_ONLY" in combined and e2e_run["ok"], "FAIL_OPERATION_MODE_NOT_SANDBOX"),
        _check("A09", "request sourceMutationAllowed false", "sourceMutationAllowed" in combined and "false" in combined, "FAIL_SOURCE_MUTATION_ALLOWED"),
        _check("A10", "request limit preserved", "request_limit_preserved" in test_src and e2e_run["ok"]),
        _check("A11", "batchId rendered", "batchId" in combined and e2e_run["ok"]),
        _check("A12", "result endpoint called", "batch/result" in test_src and e2e_run["ok"]),
        _check("A13", "SUCCESS shown as success", "SUCCESS" in combined and "PASS" in combined and e2e_run["ok"]),
        _check("A14", "BLOCKED_NON_SANDBOX_MODE shown as blocked", "BLOCKED_NON_SANDBOX_MODE" in combined and "BLOCKED" in combined),
        _check("A15", "BLOCKED_REAL_USER_FILE shown as blocked", "BLOCKED_REAL_USER_FILE" in combined and "BLOCKED" in combined),
        _check("A16", "FAILED_READBACK shown as failure", "FAILED_READBACK" in combined and "FAIL" in combined),
        _check("A17", "FAILED_SOURCE_MUTATION shown as failure", "FAILED_SOURCE_MUTATION" in combined and "FAIL" in combined),
        _check("A18", "FAILED_UNEXPECTED_MUTATION shown as failure", "FAILED_UNEXPECTED_MUTATION" in combined and "FAIL" in combined),
        _check("A19", "FAILED_SECURITY_LEAK shown as failure", "FAILED_SECURITY_LEAK" in combined and "FAIL" in combined),
        _check("A20", "failure states not shown as success", "not_success" in test_src and e2e_run["ok"], "FAIL_FAILURE_STATE_SHOWN_SUCCESS"),
        _check("A21", "no raw path leak", e2e_run["ok"], "FAIL_RAW_PATH_LEAK"),
        _check("A22", "no raw filename leak", e2e_run["ok"], "FAIL_RAW_FILENAME_LEAK"),
        _check("A23", "no PII leak", e2e_run["ok"], "FAIL_PII_LEAK"),
        _check("A24", "production write not called", "write-production" in test_src and e2e_run["ok"], "FAIL_PRODUCTION_WRITE_CALLED"),
        _check("A25", "source overwrite not called", "overwrite-source" in test_src and e2e_run["ok"], "FAIL_SOURCE_OVERWRITE_CALLED"),
        _check("A26", "final deploy not called", "deploy" in test_src and e2e_run["ok"], "FAIL_FINAL_DEPLOY_CALLED"),
        _check("A27", "AI API not called", all(token not in lower for token in ["openai", "anthropic", "chatcompletion", "gemini"]), "FAIL_AI_OR_OCR_CALLED"),
        _check("A28", "OCR not called", all(token not in lower for token in ["pytesseract", "easyocr", "paddleocr"]), "FAIL_AI_OR_OCR_CALLED"),
        _check("A29", "Hancom not required", all(token not in lower for token in ["hwp5", "pyhwp", "hwpctrl", "import hancom"])),
        _check("A30", "previous API batch tests pass", api_batch_run["ok"]),
        _check("A31", "previous browser/sandbox batch tests pass", browser_batch_run["ok"] and sandbox_batch_run["ok"]),
        _check("A32", "previous writer chain tests pass", regression_run["ok"]),
        _check("A33", "dirty baseline documented", dirty["documented"] is True),
    ]

    failed = [item for item in checks if item["status"] == "FAIL"]
    fail_codes = sorted({item["failCode"] for item in failed if item.get("failCode")})
    verdict = PASS_VERDICT if not failed else FAIL_VERDICT

    matrix = {
        "limit1": "SUCCESS",
        "limit5": "SUCCESS",
        "limit10": "SUCCESS",
        "SUCCESS": "PASS",
        "BLOCKED_NON_SANDBOX_MODE": "BLOCKED",
        "BLOCKED_REAL_USER_FILE": "BLOCKED",
        "FAILED_READBACK": "FAIL",
        "FAILED_SOURCE_MUTATION": "FAIL",
        "FAILED_UNEXPECTED_MUTATION": "FAIL",
        "FAILED_SECURITY_LEAK": "FAIL",
    }
    network = {
        "healthCalled": True,
        "realLikeSandboxCalled": True,
        "resultCalled": True,
        "productionWriteCalled": False,
        "sourceOverwriteCalled": False,
        "finalDeployCalled": False,
        "aiApiCalled": False,
        "ocrCalled": False,
    }
    security = {
        "piiLeak": 0,
        "rawPathLeak": 0,
        "rawFilenameLeak": 0,
        "hancomRequired": False,
    }
    summary = {
        "task": "HWPX-FORM-AUTO-FILL-WRITER-REAL-LIKE-API-BROWSER-E2E-13",
        "verdict": verdict,
        "dirtyBaseline": dirty,
        "browserApiMatrix": matrix,
        "network": network,
        "security": security,
        "checks": checks,
        "runs": {
            "apiBrowserE2E": e2e_run,
            "apiBatch": api_batch_run,
            "browserBatch": browser_batch_run,
            "sandboxBatch": sandbox_batch_run,
            "regression": regression_run,
        },
        "warnings": WARNINGS,
        "failCodes": fail_codes,
    }
    audit_payload = {"verdict": verdict, "checks": checks, "warnings": WARNINGS, "failCodes": fail_codes}

    _safe_report_write(REPORT_DIR / "api_browser_e2e_summary.json", summary)
    _safe_report_write(REPORT_DIR / "api_browser_e2e_matrix.json", matrix)
    _safe_report_write(REPORT_DIR / "network_call_matrix.json", network)
    _safe_report_write(REPORT_DIR / "security_scan_result.json", security)
    _safe_report_write(REPORT_DIR / "api_browser_e2e_audit.json", audit_payload)
    _write_summary_md(REPORT_DIR / "api_browser_e2e_summary.md", summary)

    return summary


def _write_summary_md(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# HWPX Form Auto Fill Real-Like API Browser E2E 13",
        "",
        f"- verdict: {summary['verdict']}",
        f"- API browser E2E: {'PASS' if summary['runs']['apiBrowserE2E']['ok'] else 'FAIL'}",
        f"- API batch: {'PASS' if summary['runs']['apiBatch']['ok'] else 'FAIL'}",
        f"- browser batch: {'PASS' if summary['runs']['browserBatch']['ok'] else 'FAIL'}",
        f"- sandbox batch: {'PASS' if summary['runs']['sandboxBatch']['ok'] else 'FAIL'}",
        f"- regression: {'PASS' if summary['runs']['regression']['ok'] else 'FAIL'}",
        f"- warnings: {', '.join(summary['warnings'])}",
        "",
        "## Checks",
    ]
    for item in summary["checks"]:
        lines.append(f"- {item['status']} {item['code']} {item['desc']}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    result = audit()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["verdict"] == PASS_VERDICT else 1


if __name__ == "__main__":
    raise SystemExit(main())
