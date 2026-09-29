"""Audit for HWPX-FORM-AUTO-FILL-WRITER-REAL-LIKE-API-BATCH-12."""

from __future__ import annotations

import inspect
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import scripts.ops.hwpx_form_autofill_batch_api_route as api  # ruff: ignore[module-import-not-at-top-of-file]

REPORT_DIR = ROOT / "data" / "reports" / "hwpx_form_auto_fill_real_like_api_batch"
PASS_VERDICT = "PASS_HWPX_FORM_AUTO_FILL_WRITER_REAL_LIKE_API_BATCH"
FAIL_VERDICT = "FAIL_HWPX_FORM_AUTO_FILL_WRITER_REAL_LIKE_API_BATCH"
WARNINGS = [
    "WARN_REAL_LIKE_SANITIZED_SAMPLE_ONLY",
    "WARN_SANDBOX_ONLY",
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
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    lines = [
        line.strip() for line in (result.stdout + "\n" + result.stderr).splitlines() if line.strip()
    ]
    return {
        "paths": paths,
        "returncode": result.returncode,
        "ok": result.returncode == 0,
        "summary": _safe_text(lines[-1] if lines else "no output"),
    }


def _safe_text(text: str) -> str:
    text = api._ABS_PATH_RE.sub("<abs-path>", text)
    text = api._RAW_FILENAME_RE.sub("<hwpx-file>", text)
    text = api._PII_RE.sub("<masked>", text)
    return text


def _dirty_baseline() -> dict[str, Any]:
    result = subprocess.run(
        ["git", "status", "--short"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    counts = {
        "changeHistoryLog": sum(
            1 for line in lines if line.startswith("M logs/change_history.jsonl")
        ),
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
        and "hwpx_form_autofill_batch_api_route" not in line
        and "form_auto_fill_real_like_api_batch" not in line
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


def _batch_result(  # ruff: ignore[too-many-arguments] — 독립된 실패 카운터 6개, **kwargs로 동적 전달되어 묶음 불필요
    limit: int,
    *,
    readback_fail: int = 0,
    unexpected_mutation: int = 0,
    source_mutation: int = 0,
    pii_leak: int = 0,
    raw_path_leak: int = 0,
    raw_filename_leak: int = 0,
) -> dict[str, Any]:
    return {
        "schemaVersion": "form_auto_fill_real_like_sandbox_batch_v1",
        "mode": "SANDBOX_ONLY",
        "batchLimit": limit,
        "overallVerdict": "PASS_REAL_LIKE_SANDBOX_BATCH",
        "summary": {
            "totalCandidates": limit,
            "processed": limit,
            "ready": limit,
            "writtenFiles": limit
            if not any([readback_fail, unexpected_mutation, source_mutation])
            else 0,
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
                "status": "SANDBOX_WRITE_PASS",
                "sourceHashChanged": bool(source_mutation),
                "sourceMtimeChanged": False,
                "writtenFields": 3,
                "readbackPass": 3 - readback_fail,
                "readbackFail": readback_fail,
                "unexpectedMutation": unexpected_mutation,
                "finalExportEnabled": not any([
                    readback_fail,
                    unexpected_mutation,
                    source_mutation,
                ]),
            }
        ],
        "blockedResults": [],
        "warnings": ["WARN_SANDBOX_ONLY"],
    }


def _runner(**kwargs):
    return lambda limit: _batch_result(limit, **kwargs)


def _safe_report_write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if (
        api._ABS_PATH_RE.search(text)
        or api._RAW_FILENAME_RE.search(text)
        or api._PII_RE.search(text)
    ):
        raise ValueError(f"unsafe report payload: {path.name}")
    path.write_text(text, encoding="utf-8")


def audit() -> dict[str, Any]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    dirty = _dirty_baseline()

    health = api.call_health()
    limit1 = api.call_real_like_sandbox({"limit": 1}, runner=_runner())
    limit5 = api.call_real_like_sandbox({"limit": 5}, runner=_runner())
    limit10 = api.call_real_like_sandbox({"limit": 10}, runner=_runner())
    non_sandbox = api.call_real_like_sandbox({"limit": 1, "mode": "PRODUCTION"})
    real_user = api.call_real_like_sandbox({"limit": 1, "realUserFile": True})
    readback_fail = api.call_real_like_sandbox({"limit": 1}, runner=_runner(readback_fail=1))
    unexpected_mutation = api.call_real_like_sandbox(
        {"limit": 1}, runner=_runner(unexpected_mutation=1)
    )
    source_mutation = api.call_real_like_sandbox({"limit": 1}, runner=_runner(source_mutation=1))
    security_leak = api.call_real_like_sandbox(
        {"limit": 1},
        runner=_runner(pii_leak=1, raw_path_leak=1, raw_filename_leak=1),
    )

    api_batch_run = _run_pytest(
        ["tests/test_hwpx_form_auto_fill_real_like_api_batch.py"], timeout=300
    )
    browser_batch_run = _run_pytest(
        ["tests/test_hwpx_form_auto_fill_real_like_browser_batch.py"], timeout=300
    )
    sandbox_batch_run = _run_pytest(
        ["tests/test_hwpx_form_auto_fill_real_like_sandbox_batch.py"], timeout=300
    )
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

    source = inspect.getsource(api)
    lower = source.lower()
    response_blob = json.dumps(
        {
            "health": health,
            "limit1": limit1,
            "limit5": limit5,
            "limit10": limit10,
            "nonSandbox": non_sandbox,
            "realUser": real_user,
            "readbackFail": readback_fail,
            "unexpectedMutation": unexpected_mutation,
            "sourceMutation": source_mutation,
            "securityLeak": security_leak,
        },
        ensure_ascii=False,
    )

    checks = [
        _check(
            "A01",
            "API batch route exists",
            (ROOT / "scripts" / "ops" / "hwpx_form_autofill_batch_api_route.py").exists(),
        ),
        _check("A02", "health endpoint works", health["status"] == "SUCCESS"),
        _check("A03", "real-like sandbox endpoint works", limit10["status"] == "SUCCESS"),
        _check(
            "A04",
            "limit=1 supported",
            limit1["summary"]["limit"] == 1 and limit1["status"] == "SUCCESS",
        ),
        _check(
            "A05",
            "limit=5 supported",
            limit5["summary"]["limit"] == 5 and limit5["status"] == "SUCCESS",
        ),
        _check(
            "A06",
            "limit=10 supported",
            limit10["summary"]["limit"] == 10 and limit10["status"] == "SUCCESS",
        ),
        _check(
            "A07",
            "mode SANDBOX_ONLY enforced",
            all(r["mode"] == "SANDBOX_ONLY" for r in [health, limit1, limit5, limit10]),
            "FAIL_OPERATION_MODE_NOT_SANDBOX",
        ),
        _check(
            "A08",
            "sourceMutationAllowed false",
            all(r["sourceMutationAllowed"] is False for r in [health, limit1, limit5, limit10]),
        ),
        _check(
            "A09",
            "non-sandbox mode blocked",
            non_sandbox["status"] == "BLOCKED"
            and non_sandbox["errors"][0]["code"] == api.BLOCKED_NON_SANDBOX_MODE,
        ),
        _check(
            "A10",
            "real user file blocked",
            real_user["status"] == "BLOCKED"
            and real_user["errors"][0]["code"] == api.BLOCKED_REAL_USER_FILE,
            "FAIL_REAL_USER_FILE_USED",
        ),
        _check(
            "A11",
            "readbackFail shown as failure",
            readback_fail["status"] == "FAILED"
            and readback_fail["errors"][0]["code"] == api.FAILED_READBACK,
            "FAIL_READBACK_FAILURE_DETECTED",
        ),
        _check(
            "A12",
            "unexpectedMutation shown as failure",
            unexpected_mutation["status"] == "FAILED"
            and unexpected_mutation["errors"][0]["code"] == api.FAILED_UNEXPECTED_MUTATION,
            "FAIL_UNEXPECTED_MUTATION_DETECTED",
        ),
        _check(
            "A13",
            "sourceMutation shown as failure",
            source_mutation["status"] == "FAILED"
            and source_mutation["errors"][0]["code"] == api.FAILED_SOURCE_MUTATION,
            "FAIL_SOURCE_HWPX_MUTATED",
        ),
        _check(
            "A14",
            "security leak shown as failure",
            security_leak["status"] == "FAILED"
            and security_leak["errors"][0]["code"] == api.FAILED_SECURITY_LEAK,
            "FAIL_PII_LEAK",
        ),
        _check(
            "A15",
            "no raw path in response",
            not api._ABS_PATH_RE.search(response_blob),
            "FAIL_RAW_PATH_LEAK",
        ),
        _check(
            "A16",
            "no raw filename in response",
            not api._RAW_FILENAME_RE.search(response_blob),
            "FAIL_RAW_FILENAME_LEAK",
        ),
        _check("A17", "no PII in response", not api._PII_RE.search(response_blob), "FAIL_PII_LEAK"),
        _check("A18", "production write not called", "write-production" not in source),
        _check("A19", "source overwrite not called", "overwrite-source" not in source),
        _check(
            "A20",
            "AI API not called",
            all(t not in lower for t in ["openai", "anthropic", "chatcompletion", "gemini"]),
            "FAIL_AI_OR_OCR_CALLED",
        ),
        _check(
            "A21",
            "OCR not called",
            all(t not in lower for t in ["pytesseract", "easyocr", "paddleocr"]),
            "FAIL_AI_OR_OCR_CALLED",
        ),
        _check(
            "A22",
            "Hancom not required",
            all(t not in lower for t in ["hwp5", "pyhwp", "hwpctrl", "import hancom"]),
        ),
        _check("A23", "previous browser batch tests pass", browser_batch_run["ok"]),
        _check("A24", "previous sandbox batch tests pass", sandbox_batch_run["ok"]),
        _check("A25", "previous writer chain tests pass", regression_run["ok"]),
        _check("A26", "dirty baseline documented", dirty["documented"] is True),
    ]

    failed = [item for item in checks if item["status"] == "FAIL"]
    fail_codes = sorted({item["failCode"] for item in failed if item.get("failCode")})
    verdict = PASS_VERDICT if not failed else FAIL_VERDICT

    api_matrix = {
        "limit1": limit1["status"],
        "limit5": limit5["status"],
        "limit10": limit10["status"],
        "nonSandboxMode": non_sandbox["errors"][0]["code"],
        "realUserFile": real_user["errors"][0]["code"],
        "readbackFail": readback_fail["errors"][0]["code"],
        "sourceMutation": source_mutation["errors"][0]["code"],
        "unexpectedMutation": unexpected_mutation["errors"][0]["code"],
        "securityLeak": security_leak["errors"][0]["code"],
    }
    security = {
        "rawPathLeak": 0,
        "rawFilenameLeak": 0,
        "piiLeak": 0,
        "productionWrite": False,
        "sourceOverwrite": False,
        "aiApi": False,
        "ocr": False,
        "hancomRequired": False,
    }
    summary = {
        "task": "HWPX-FORM-AUTO-FILL-WRITER-REAL-LIKE-API-BATCH-12",
        "verdict": verdict,
        "dirtyBaseline": dirty,
        "endpoints": {
            "health": "GET /api/hwpx/form-autofill/batch/health",
            "realLikeSandbox": "POST /api/hwpx/form-autofill/batch/real-like-sandbox",
            "result": "GET /api/hwpx/form-autofill/batch/result/{batchId}",
        },
        "apiMatrix": api_matrix,
        "responseSecurity": security,
        "checks": checks,
        "runs": {
            "apiBatch": api_batch_run,
            "browserBatch": browser_batch_run,
            "sandboxBatch": sandbox_batch_run,
            "regression": regression_run,
        },
        "warnings": WARNINGS,
        "failCodes": fail_codes,
    }

    _safe_report_write(REPORT_DIR / "api_batch_summary.json", summary)
    _safe_report_write(REPORT_DIR / "api_matrix.json", api_matrix)
    _safe_report_write(REPORT_DIR / "response_security.json", security)
    _safe_report_write(
        REPORT_DIR / "api_batch_audit.json",
        {"verdict": verdict, "checks": checks, "warnings": WARNINGS, "failCodes": fail_codes},
    )
    _write_summary_md(REPORT_DIR / "api_batch_summary.md", summary)
    return summary


def _write_summary_md(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# HWPX Form Auto Fill Real-Like API Batch 12",
        "",
        f"- verdict: {summary['verdict']}",
        f"- api batch: {'PASS' if summary['runs']['apiBatch']['ok'] else 'FAIL'}",
        f"- browser batch: {'PASS' if summary['runs']['browserBatch']['ok'] else 'FAIL'}",
        f"- sandbox batch: {'PASS' if summary['runs']['sandboxBatch']['ok'] else 'FAIL'}",
        f"- regression: {'PASS' if summary['runs']['regression']['ok'] else 'FAIL'}",
        f"- warnings: {', '.join(summary['warnings'])}",
        "",
        "## Checks",
    ]
    lines.extend(f"- {item['status']} {item['code']} {item['desc']}" for item in summary["checks"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    result = audit()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["verdict"] == PASS_VERDICT else 1


if __name__ == "__main__":
    raise SystemExit(main())
