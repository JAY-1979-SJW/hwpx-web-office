"""Run HWPX form auto-fill verification files one by one.

This operational runner executes each verification target as an independent
pytest process, then runs the closeout audit automatically. Reports are written
with sanitized summaries only.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = ROOT / "data" / "reports" / "hwpx_form_auto_fill_individual_verification"

ABS_PATH_RE = re.compile(r"(?<![A-Za-z])([A-Za-z]:[\\/][^\s\"']*|/(home|tmp|var|Users)/[^\s\"']*)")
RAW_FILENAME_RE = re.compile(r"\b[^\\/:\s]+\.hwpx\b", re.IGNORECASE)
PII_RE = re.compile(
    r"(\d{6}-\d{7}|\d{3}-\d{2}-\d{5}|\d{2,3}-\d{3,4}-\d{4}|"
    r"\d{2,6}-\d{2,6}-\d{2,6}|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})"
)

DEFAULT_TARGETS = [
    ("closeout", "tests/test_hwpx_form_auto_fill_user_flow_closeout.py"),
    ("api_browser_e2e", "tests/test_hwpx_form_auto_fill_real_like_api_browser_e2e.py"),
    ("api_batch", "tests/test_hwpx_form_auto_fill_real_like_api_batch.py"),
    ("browser_batch", "tests/test_hwpx_form_auto_fill_real_like_browser_batch.py"),
    ("sandbox_batch", "tests/test_hwpx_form_auto_fill_real_like_sandbox_batch.py"),
    ("real_file_preflight", "tests/test_hwpx_form_auto_fill_real_file_preflight.py"),
    ("browser_smoke", "tests/test_hwpx_form_autofill_browser_smoke.py"),
    ("api_route", "tests/test_hwpx_form_autofill_api_route.py"),
    ("frontend_contract", "tests/test_hwpx_form_autofill_frontend_contract.py"),
    ("e2e_smoke", "tests/test_hwpx_form_auto_fill_e2e_smoke.py"),
    ("final_export_gate", "tests/test_hwpx_form_writer_final_export_gate.py"),
    ("download_review", "tests/test_hwpx_form_writer_download_review.py"),
    ("ui_connect", "tests/test_hwpx_form_writer_ui_connect.py"),
    ("readback_hardening", "tests/test_hwpx_form_writer_readback_hardening.py"),
    ("writer_sandbox", "tests/test_hwpx_form_auto_fill_writer_sandbox.py"),
    ("human_approval_gate", "tests/test_hwpx_approval_gate.py"),
    ("missing_review_panel", "tests/test_hwpx_review_panel.py"),
    ("field_mapping", "tests/test_hwpx_form_field_mapping.py"),
]
DEFAULT_AUDITS = [
    ("user_flow_closeout_audit", "scripts/ops/audit_hwpx_form_auto_fill_user_flow_closeout.py"),
]
TRANSIENT_ERROR_MARKERS = (
    "PermissionError: [WinError 5]",
    "winerror 5",
    "access is denied",
    "denied",
)


def _safe_text(text: str) -> str:
    text = ABS_PATH_RE.sub("<abs-path>", text)
    text = RAW_FILENAME_RE.sub("<hwpx-file>", text)
    text = PII_RE.sub("<masked>", text)
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
    return {
        "documented": True,
        "knownHold": [
            label
            for label, present in [
                ("change_history_log_modified", any(line.startswith("M logs/change_history.jsonl") for line in lines)),
                ("devlog_untracked", any(line.startswith("?? docs/devlog/") for line in lines)),
                ("reports_untracked", any(line.startswith("?? reports/") for line in lines)),
            ]
            if present
        ],
        "knownHoldCounts": {
            "changeHistoryLog": sum(1 for line in lines if line.startswith("M logs/change_history.jsonl")),
            "devlogUntracked": sum(1 for line in lines if line.startswith("?? docs/devlog/")),
            "reportsUntracked": sum(1 for line in lines if line.startswith("?? reports/")),
        },
    }


def _run_target(label: str, rel_path: str, timeout: int) -> dict[str, Any]:
    return _run_process(
        label=label,
        rel_path=rel_path,
        command=[sys.executable, "-m", "pytest", rel_path, "-q", "--tb=no"],
        timeout=timeout,
        missing_summary="target missing",
    )


def _run_audit(label: str, rel_path: str, timeout: int) -> dict[str, Any]:
    item = _run_process(
        label=label,
        rel_path=rel_path,
        command=[sys.executable, rel_path],
        timeout=timeout,
        missing_summary="audit missing",
    )
    item["summary"] = _audit_summary(item.pop("rawOutput", ""))
    return item


def _run_process(
    *,
    label: str,
    rel_path: str,
    command: list[str],
    timeout: int,
    missing_summary: str,
) -> dict[str, Any]:
    started = time.perf_counter()
    path = ROOT / rel_path
    if not path.is_file():
        return {
            "label": label,
            "path": rel_path,
            "status": "FAIL",
            "returncode": 2,
            "durationSeconds": 0.0,
            "attempts": 0,
            "summary": missing_summary,
            "rawOutput": "",
        }
    result: subprocess.CompletedProcess[str] | None = None
    output = ""
    summary = "no output"
    attempts = 0
    for attempt in (1, 2):
        attempts = attempt
        result = subprocess.run(
            command,
            cwd=str(ROOT),
            capture_output=True,
            text=True, encoding="utf-8", errors="replace",
            timeout=timeout,
        )
        output = result.stdout + "\n" + result.stderr
        lines = [line.strip() for line in output.splitlines() if line.strip()]
        summary = _safe_text(lines[-1] if lines else "no output")
        if result.returncode == 0 or not _is_transient_error(output):
            break
        time.sleep(0.5)
    duration = round(time.perf_counter() - started, 3)
    assert result is not None
    return {
        "label": label,
        "path": rel_path,
        "status": "PASS" if result.returncode == 0 else "FAIL",
        "returncode": result.returncode,
        "durationSeconds": duration,
        "attempts": attempts,
        "summary": summary,
        "rawOutput": _safe_text(output),
    }


def _audit_summary(output: str) -> str:
    safe_output = _safe_text(output)
    try:
        parsed = json.loads(safe_output[safe_output.index("{") : safe_output.rindex("}") + 1])
    except (ValueError, json.JSONDecodeError):
        lines = [line.strip() for line in safe_output.splitlines() if line.strip()]
        return lines[-1] if lines else "no output"
    verdict = parsed.get("verdict", "unknown")
    checks = parsed.get("checks", [])
    passed = sum(1 for item in checks if item.get("status") == "PASS")
    failed = sum(1 for item in checks if item.get("status") == "FAIL")
    return f"{verdict}; checks PASS={passed} FAIL={failed}"


def _is_transient_error(text: str) -> bool:
    lower = text.lower()
    return any(marker.lower() in lower for marker in TRANSIENT_ERROR_MARKERS)


def _strip_raw_output(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{key: value for key, value in item.items() if key != "rawOutput"} for item in items]


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if ABS_PATH_RE.search(text) or RAW_FILENAME_RE.search(text) or PII_RE.search(text):
        raise ValueError(f"unsafe report payload: {path.name}")
    path.write_text(text, encoding="utf-8")


def _write_md(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# HWPX Form Auto Fill Individual Verification",
        "",
        f"- verdict: {payload['verdict']}",
        f"- total: {payload['summary']['total']}",
        f"- passed: {payload['summary']['passed']}",
        f"- failed: {payload['summary']['failed']}",
        f"- audits: {payload['summary']['auditsPassed']}/{payload['summary']['auditsTotal']} passed",
        f"- warnings: {', '.join(payload['warnings'])}",
        "",
        "## Results",
    ]
    for item in payload["results"]:
        lines.append(f"- {item['status']} {item['label']} - attempts={item['attempts']} - {item['summary']}")
    lines.append("")
    lines.append("## Audits")
    if payload["auditRuns"]:
        for item in payload["auditRuns"]:
            lines.append(f"- {item['status']} {item['label']} - attempts={item['attempts']} - {item['summary']}")
    else:
        lines.append("- SKIP audit auto-run disabled")
    text = "\n".join(lines) + "\n"
    if ABS_PATH_RE.search(text) or RAW_FILENAME_RE.search(text) or PII_RE.search(text):
        raise ValueError("unsafe markdown report")
    path.write_text(text, encoding="utf-8")


def run_individual_verification(
    targets: list[tuple[str, str]],
    report_dir: Path,
    timeout: int,
    audit_targets: list[tuple[str, str]],
    audit_timeout: int,
) -> dict[str, Any]:
    results = [_run_target(label, rel_path, timeout) for label, rel_path in targets]
    audit_runs = [_run_audit(label, rel_path, audit_timeout) for label, rel_path in audit_targets]
    results = _strip_raw_output(results)
    audit_runs = _strip_raw_output(audit_runs)
    failed = [item for item in results if item["status"] != "PASS"]
    audit_failed = [item for item in audit_runs if item["status"] != "PASS"]
    payload = {
        "schemaVersion": "hwpx_form_auto_fill_individual_verification_v2",
        "verdict": "PASS_HWPX_FORM_AUTO_FILL_INDIVIDUAL_VERIFICATION"
        if not failed and not audit_failed
        else "FAIL_HWPX_FORM_AUTO_FILL_INDIVIDUAL_VERIFICATION",
        "summary": {
            "total": len(results),
            "passed": len(results) - len(failed),
            "failed": len(failed),
            "auditsTotal": len(audit_runs),
            "auditsPassed": len(audit_runs) - len(audit_failed),
            "auditsFailed": len(audit_failed),
        },
        "results": results,
        "auditRuns": audit_runs,
        "dirtyBaseline": _dirty_baseline(),
        "warnings": [
            "WARN_SANDBOX_ONLY",
            "WARN_REAL_USER_FILE_NOT_TESTED",
            "WARN_DEPLOY_NOT_PERFORMED",
            "WARN_EXISTING_DIRTY_BASELINE_DOCUMENTED",
        ],
    }
    _write_json(report_dir / "individual_verification_summary.json", payload)
    _write_json(report_dir / "individual_verification_results.json", results)
    _write_json(report_dir / "individual_verification_audits.json", audit_runs)
    _write_md(report_dir / "individual_verification_summary.md", payload)
    return payload


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", default=str(REPORT_DIR), help="Directory for PII-safe verification reports.")
    parser.add_argument("--timeout", type=int, default=300, help="Per-target timeout in seconds.")
    parser.add_argument("--audit-timeout", type=int, default=1800, help="Per-audit timeout in seconds.")
    parser.add_argument("--skip-audit", action="store_true", help="Do not auto-run closeout audit after verification.")
    parser.add_argument(
        "--target",
        action="append",
        choices=[label for label, _ in DEFAULT_TARGETS],
        help="Run only the selected target label. May be repeated.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    selected = set(args.target or [])
    targets = [item for item in DEFAULT_TARGETS if not selected or item[0] in selected]
    audit_targets = [] if args.skip_audit else DEFAULT_AUDITS
    payload = run_individual_verification(targets, Path(args.report_dir), args.timeout, audit_targets, args.audit_timeout)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["summary"]["failed"] == 0 and payload["summary"]["auditsFailed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
