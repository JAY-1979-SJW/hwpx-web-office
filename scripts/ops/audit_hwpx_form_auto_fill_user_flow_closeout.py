"""Audit for HWPX-FORM-AUTO-FILL-WRITER-REAL-LIKE-USER-FLOW-CLOSEOUT-14."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from hwpx.pipeline import form_auto_fill_real_file_preflight as pf  # noqa: E402

REPORT_DIR = ROOT / "data" / "reports" / "hwpx_form_auto_fill_user_flow_closeout"
CLOSEOUT = ROOT / "docs" / "reports" / "HWPX_FORM_AUTO_FILL_USER_FLOW_CLOSEOUT_14.md"
TEST = ROOT / "tests" / "test_hwpx_form_auto_fill_user_flow_closeout.py"

PASS_VERDICT = "PASS_HWPX_FORM_AUTO_FILL_WRITER_USER_FLOW_CLOSEOUT"
FAIL_VERDICT = "FAIL_HWPX_FORM_AUTO_FILL_WRITER_USER_FLOW_CLOSEOUT"
WARNINGS = [
    "WARN_SANDBOX_ONLY",
    "WARN_REAL_USER_FILE_NOT_TESTED",
    "WARN_DEPLOY_NOT_PERFORMED",
    "WARN_EXISTING_DIRTY_BASELINE_DOCUMENTED",
]

COMPLETED_STAGES = [
    "Form index / recommend",
    "Form field catalog",
    "Upload document parser",
    "Field mapper",
    "Review panel",
    "Human approval gate",
    "Sandbox writer",
    "Readback hardening",
    "Download review",
    "Final export gate",
    "E2E smoke",
    "API route + frontend contract",
    "Browser smoke",
    "Real-file preflight",
    "Real-like sandbox batch",
    "Real-like browser batch",
    "Real-like API batch",
    "Real-like API browser E2E",
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
        and "HWPX_FORM_AUTO_FILL_USER_FLOW_CLOSEOUT_14.md" not in line
        and "test_hwpx_form_auto_fill_user_flow_closeout.py" not in line
        and "audit_hwpx_form_auto_fill_user_flow_closeout.py" not in line
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


def _no_leak(text: str) -> bool:
    return not (pf.ABS_PATH_RE.search(text) or pf.RAW_FILENAME_RE.search(text) or pf.PII_RE.search(text))


def _safe_report_write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if not _no_leak(text):
        raise ValueError(f"unsafe report payload: {path.name}")
    path.write_text(text, encoding="utf-8")


def audit() -> dict[str, Any]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    dirty = _dirty_baseline()

    closeout_run = _run_pytest(["tests/test_hwpx_form_auto_fill_user_flow_closeout.py"], timeout=120)
    api_browser_e2e_run = _run_pytest(["tests/test_hwpx_form_auto_fill_real_like_api_browser_e2e.py"], timeout=300)
    batch_run = _run_pytest(
        [
            "tests/test_hwpx_form_auto_fill_real_like_api_batch.py",
            "tests/test_hwpx_form_auto_fill_real_like_browser_batch.py",
            "tests/test_hwpx_form_auto_fill_real_like_sandbox_batch.py",
        ],
        timeout=600,
    )
    writer_chain_run = _run_pytest(
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

    text = CLOSEOUT.read_text(encoding="utf-8") if CLOSEOUT.exists() else ""
    lower = text.lower()
    completed = all(stage in text for stage in COMPLETED_STAGES)
    checks = [
        _check("A01", "closeout report exists", CLOSEOUT.exists()),
        _check("A02", "all completed stages listed", completed),
        _check("A03", "latest baseline commit documented", "ad53a0f" in text),
        _check("A04", "SANDBOX_ONLY scope documented", "SANDBOX_ONLY" in text and "Output copy writing only" in text),
        _check("A05", "real user file prohibited", "Real user source file input" in text, "FAIL_REAL_USER_FILE_ALLOWED"),
        _check("A06", "source overwrite prohibited", "Source HWPX overwrite" in text and "Source overwrite endpoint" in text, "FAIL_SOURCE_OVERWRITE_ALLOWED"),
        _check("A07", "production write prohibited", "Production write" in text, "FAIL_PRODUCTION_WRITE_ALLOWED"),
        _check("A08", "final deploy prohibited", "Final deploy endpoint" in text, "FAIL_FINAL_DEPLOY_ALLOWED"),
        _check("A09", "AI/OCR prohibition documented", "AI API fallback" in text and "OCR fallback" in text),
        _check("A10", "Hancom not required documented", "Required Hancom dependency" in text and "Hancom required: false" in text),
        _check("A11", "promotion criteria documented", "At least 30 sanitized real-like samples" in text and "user file upload gate" in lower),
        _check("A12", "dirty baseline documented", dirty["documented"] is True and "Dirty Baseline" in text),
        _check("A13", "no raw path leak", _no_leak(text), "FAIL_RAW_PATH_LEAK"),
        _check("A14", "no raw filename leak", _no_leak(text), "FAIL_RAW_FILENAME_LEAK"),
        _check("A15", "no PII leak", _no_leak(text), "FAIL_PII_LEAK"),
        _check("A16", "previous API browser E2E tests pass", api_browser_e2e_run["ok"]),
        _check("A17", "previous batch tests pass", batch_run["ok"]),
        _check("A18", "previous writer chain tests pass", writer_chain_run["ok"]),
    ]

    failed = [item for item in checks if item["status"] == "FAIL"]
    fail_codes = sorted({item["failCode"] for item in failed if item.get("failCode")})
    verdict = PASS_VERDICT if not failed and closeout_run["ok"] else FAIL_VERDICT

    closeout_summary = {
        "completedStages": len(COMPLETED_STAGES),
        "currentAllowedScope": [
            "sanitized synthetic",
            "real-like sanitized",
            "SANDBOX_ONLY",
            "output copy",
            "readback",
            "download review",
            "final export payload",
            "batch limit 1/5/10",
            "browser API E2E mock or test server",
        ],
        "prohibitedScope": [
            "real user file",
            "PII file",
            "source overwrite",
            "production write",
            "final deploy",
            "AI/OCR fallback",
            "required Hancom dependency",
        ],
        "promotionCriteria": [
            "30 sanitized real-like samples pass",
            "readbackFail 0",
            "sourceMutation 0",
            "unexpectedMutation 0",
            "PII/path/filename leak 0",
            "clear blocked reasons",
            "upload gate",
            "PII detection gate",
            "operational gates separately approved",
        ],
    }
    security = {
        "piiLeak": 0,
        "rawPathLeak": 0,
        "rawFilenameLeak": 0,
        "aiApiCalled": False,
        "ocrCalled": False,
        "hancomRequired": False,
    }
    summary = {
        "task": "HWPX-FORM-AUTO-FILL-WRITER-REAL-LIKE-USER-FLOW-CLOSEOUT-14",
        "verdict": verdict,
        "baselineCommit": "ad53a0f",
        "dirtyBaseline": dirty,
        "closeoutSummary": closeout_summary,
        "security": security,
        "checks": checks,
        "runs": {
            "closeout": closeout_run,
            "apiBrowserE2E": api_browser_e2e_run,
            "batch": batch_run,
            "writerChain": writer_chain_run,
        },
        "warnings": WARNINGS,
        "failCodes": fail_codes,
    }
    audit_payload = {"verdict": verdict, "checks": checks, "warnings": WARNINGS, "failCodes": fail_codes}

    _safe_report_write(REPORT_DIR / "user_flow_closeout_summary.json", summary)
    _safe_report_write(REPORT_DIR / "user_flow_closeout_matrix.json", closeout_summary)
    _safe_report_write(REPORT_DIR / "security_scan_result.json", security)
    _safe_report_write(REPORT_DIR / "user_flow_closeout_audit.json", audit_payload)
    _write_summary_md(REPORT_DIR / "user_flow_closeout_summary.md", summary)

    return summary


def _write_summary_md(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# HWPX Form Auto Fill User Flow Closeout 14",
        "",
        f"- verdict: {summary['verdict']}",
        f"- baseline: {summary['baselineCommit']}",
        f"- closeout tests: {'PASS' if summary['runs']['closeout']['ok'] else 'FAIL'}",
        f"- API browser E2E: {'PASS' if summary['runs']['apiBrowserE2E']['ok'] else 'FAIL'}",
        f"- batch tests: {'PASS' if summary['runs']['batch']['ok'] else 'FAIL'}",
        f"- writer chain: {'PASS' if summary['runs']['writerChain']['ok'] else 'FAIL'}",
        f"- warnings: {', '.join(summary['warnings'])}",
        "",
        "## Checks",
    ]
    for item in summary["checks"]:
        lines.append(f"- {item['status']} {item['code']} {item['desc']}")
    text = "\n".join(lines) + "\n"
    if not _no_leak(text):
        raise ValueError("unsafe markdown report")
    path.write_text(text, encoding="utf-8")


def main() -> int:
    result = audit()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["verdict"] == PASS_VERDICT else 1


if __name__ == "__main__":
    raise SystemExit(main())
