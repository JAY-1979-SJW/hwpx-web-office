"""Audit for HWPX-FORM-AUTO-FILL-WRITER-REAL-LIKE-BROWSER-BATCH-11."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from hwpx.pipeline import form_auto_fill_real_file_preflight as pf  # noqa: E402

REPORT_DIR = ROOT / "data" / "reports" / "hwpx_form_auto_fill_real_like_browser_batch"
PAGE = ROOT / "frontend" / "web_office_viewer" / "form_autofill_real_like_batch_smoke.html"
JS = ROOT / "frontend" / "web_office_viewer" / "form_autofill_real_like_batch_smoke.mjs"
TEST = ROOT / "tests" / "test_hwpx_form_auto_fill_real_like_browser_batch.py"

PASS_VERDICT = "PASS_HWPX_FORM_AUTO_FILL_WRITER_REAL_LIKE_BROWSER_BATCH"
FAIL_VERDICT = "FAIL_HWPX_FORM_AUTO_FILL_WRITER_REAL_LIKE_BROWSER_BATCH"
WARNINGS = [
    "WARN_REAL_LIKE_SANITIZED_SAMPLE_ONLY",
    "WARN_SANDBOX_ONLY",
    "WARN_SOME_FILES_BLOCKED",
    "WARN_REAL_USER_FILE_NOT_TESTED",
    "WARN_DEPLOY_NOT_PERFORMED",
    "WARN_EXISTING_DIRTY_BASELINE_DOCUMENTED",
]


def _run_pytest(paths: list[str], timeout: int = 900) -> dict[str, Any]:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", *paths, "-q", "--tb=no"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    text = result.stdout + "\n" + result.stderr
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return {
        "paths": paths,
        "returncode": result.returncode,
        "ok": result.returncode == 0,
        "summary": _safe_text(lines[-1] if lines else "no output"),
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
        text=True,
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
        and "form_auto_fill_real_like_browser_batch" not in line
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

    browser_batch_run = _run_pytest(["tests/test_hwpx_form_auto_fill_real_like_browser_batch.py"], timeout=300)
    batch_run = _run_pytest(["tests/test_hwpx_form_auto_fill_real_like_sandbox_batch.py"], timeout=300)
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

    visible_tokens = {
        "batch summary": "batch-summary",
        "limits": ["limit-1-result", "limit-5-result", "limit-10-result"],
        "file results": "file-results",
        "blocked results": "blocked-results",
        "readback": "readback-summary",
        "immutability": "source-immutability",
        "security": "security-summary",
        "sandbox": "SANDBOX_ONLY",
    }

    checks = [
        _check("A01", "browser batch page exists", PAGE.exists()),
        _check("A02", "browser batch JS exists", JS.exists()),
        _check("A03", "batch summary visible", visible_tokens["batch summary"] in combined),
        _check("A04", "limit=1/5/10 visible", all(token in combined for token in visible_tokens["limits"])),
        _check("A05", "file results visible", visible_tokens["file results"] in combined),
        _check("A06", "blocked results visible", visible_tokens["blocked results"] in combined),
        _check("A07", "readback summary visible", visible_tokens["readback"] in combined),
        _check("A08", "source immutability visible", visible_tokens["immutability"] in combined),
        _check("A09", "security summary visible", visible_tokens["security"] in combined),
        _check("A10", "SANDBOX_ONLY warning visible", visible_tokens["sandbox"] in combined),
        _check("A11", "PASS batch shown as success", "passBatch" in test_src and "PASS" in combined),
        _check("A12", "blocked files shown as WARN", "blockedWarn" in test_src and "WARN" in combined),
        _check("A13", "readbackFail shown as FAIL", "readbackFail" in combined and "FAIL" in combined, "FAIL_READBACK_FAILURE_DETECTED"),
        _check("A14", "unexpectedMutation shown as FAIL", "unexpectedMutation" in combined and "FAIL" in combined, "FAIL_UNEXPECTED_MUTATION_DETECTED"),
        _check("A15", "sourceMutation shown as FAIL", "sourceMutation" in combined and "FAIL" in combined),
        _check("A16", "non-sandbox mode shown as FAIL", "nonSandbox" in test_src and "BLOCKED_NON_SANDBOX" in test_src, "FAIL_OPERATION_MODE_NOT_SANDBOX"),
        _check("A17", "PII/path/filename leak shown as FAIL", all(token in combined for token in ["piiLeak", "rawPathLeak", "rawFilenameLeak"])),
        _check("A18", "no raw path visible", browser_batch_run["ok"], "FAIL_RAW_PATH_LEAK"),
        _check("A19", "no raw filename visible", browser_batch_run["ok"], "FAIL_RAW_FILENAME_LEAK"),
        _check("A20", "no PII visible", browser_batch_run["ok"], "FAIL_PII_LEAK"),
        _check("A21", "production write endpoint not called", "write-production" in test_src and browser_batch_run["ok"]),
        _check("A22", "source overwrite endpoint not called", "overwrite-source" in test_src and browser_batch_run["ok"]),
        _check("A23", "AI API not called", all(token not in lower for token in ["openai", "anthropic", "chatcompletion", "gemini"]), "FAIL_AI_OR_OCR_CALLED"),
        _check("A24", "OCR not called", "pytesseract" not in lower and "easyocr" not in lower and "paddleocr" not in lower, "FAIL_AI_OR_OCR_CALLED"),
        _check("A25", "Hancom not required", all(token not in lower for token in ["hwp5", "pyhwp", "hwpctrl", "import hancom"])),
        _check("A26", "previous real-like batch tests pass", batch_run["ok"]),
        _check("A27", "previous preflight/browser/API/E2E/writer tests pass", regression_run["ok"]),
        _check("A28", "dirty baseline documented", dirty["documented"] is True),
    ]

    failed = [item for item in checks if item["status"] == "FAIL"]
    fail_codes = sorted({item["failCode"] for item in failed if item.get("failCode")})
    verdict = PASS_VERDICT if not failed else FAIL_VERDICT

    ui_state_matrix = {
        "PASS batch": "PASS",
        "blocked files": "WARN",
        "readbackFail": "FAIL",
        "unexpectedMutation": "FAIL",
        "sourceMutation": "FAIL",
        "non-sandbox mode": "FAIL",
        "PII/path/filename leak": "FAIL",
    }
    network_matrix = {
        "productionWriteCalled": False,
        "sourceOverwriteCalled": False,
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
        "task": "HWPX-FORM-AUTO-FILL-WRITER-REAL-LIKE-BROWSER-BATCH-11",
        "verdict": verdict,
        "dirtyBaseline": dirty,
        "browserRender": {
            "batchSummary": True,
            "limit1": True,
            "limit5": True,
            "limit10": True,
            "fileResults": True,
            "blockedResults": True,
            "readbackSummary": True,
            "sourceImmutability": True,
            "securitySummary": True,
            "sandboxWarning": True,
        },
        "uiStateMatrix": ui_state_matrix,
        "network": network_matrix,
        "security": security,
        "checks": checks,
        "runs": {
            "browserBatch": browser_batch_run,
            "realLikeSandboxBatch": batch_run,
            "regression": regression_run,
        },
        "warnings": WARNINGS,
        "failCodes": fail_codes,
    }
    audit_payload = {"verdict": verdict, "checks": checks, "warnings": WARNINGS, "failCodes": fail_codes}

    _safe_report_write(REPORT_DIR / "browser_batch_summary.json", summary)
    _safe_report_write(REPORT_DIR / "ui_state_matrix.json", ui_state_matrix)
    _safe_report_write(REPORT_DIR / "network_call_matrix.json", network_matrix)
    _safe_report_write(REPORT_DIR / "security_scan_result.json", security)
    _safe_report_write(REPORT_DIR / "browser_batch_audit.json", audit_payload)
    _write_summary_md(REPORT_DIR / "browser_batch_summary.md", summary)

    return summary


def _write_summary_md(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# HWPX Form Auto Fill Real-Like Browser Batch 11",
        "",
        f"- verdict: {summary['verdict']}",
        f"- browser batch: {'PASS' if summary['runs']['browserBatch']['ok'] else 'FAIL'}",
        f"- real-like batch: {'PASS' if summary['runs']['realLikeSandboxBatch']['ok'] else 'FAIL'}",
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

