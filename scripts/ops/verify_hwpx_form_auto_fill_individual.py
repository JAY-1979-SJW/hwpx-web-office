"""Run HWPX form auto-fill verification files one by one.

This script is a small operational runner for post-closeout checks. It executes
each verification target as an independent pytest process so a failure can be
attributed to one file without mixing reports or dirty worktree state.
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
TRANSIENT_ERROR_MARKERS = (
    "PermissionError: [WinError 5]",
    "access is denied",
    "액세스가 거부되었습니다",
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
        text=True,
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
            "summary": "target missing",
        }
    result: subprocess.CompletedProcess[str] | None = None
    summary = "no output"
    attempts = 0
    for attempt in (1, 2):
        attempts = attempt
        result = subprocess.run(
            [sys.executable, "-m", "pytest", rel_path, "-q", "--tb=no"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        lines = [line.strip() for line in (result.stdout + "\n" + result.stderr).splitlines() if line.strip()]
        summary = _safe_text(lines[-1] if lines else "no output")
        if result.returncode == 0 or not _is_transient_error(result.stdout + "\n" + result.stderr):
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
    }


def _is_transient_error(text: str) -> bool:
    lower = text.lower()
    return any(marker.lower() in lower for marker in TRANSIENT_ERROR_MARKERS)


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
        f"- warnings: {', '.join(payload['warnings'])}",
        "",
        "## Results",
    ]
    for item in payload["results"]:
        lines.append(f"- {item['status']} {item['label']} - {item['summary']}")
    text = "\n".join(lines) + "\n"
    if ABS_PATH_RE.search(text) or RAW_FILENAME_RE.search(text) or PII_RE.search(text):
        raise ValueError("unsafe markdown report")
    path.write_text(text, encoding="utf-8")


def run_individual_verification(targets: list[tuple[str, str]], report_dir: Path, timeout: int) -> dict[str, Any]:
    results = [_run_target(label, rel_path, timeout) for label, rel_path in targets]
    failed = [item for item in results if item["status"] != "PASS"]
    payload = {
        "schemaVersion": "hwpx_form_auto_fill_individual_verification_v1",
        "verdict": "PASS_HWPX_FORM_AUTO_FILL_INDIVIDUAL_VERIFICATION" if not failed else "FAIL_HWPX_FORM_AUTO_FILL_INDIVIDUAL_VERIFICATION",
        "summary": {
            "total": len(results),
            "passed": len(results) - len(failed),
            "failed": len(failed),
        },
        "results": results,
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
    _write_md(report_dir / "individual_verification_summary.md", payload)
    return payload


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", default=str(REPORT_DIR), help="Directory for PII-safe verification reports.")
    parser.add_argument("--timeout", type=int, default=300, help="Per-target timeout in seconds.")
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
    payload = run_individual_verification(targets, Path(args.report_dir), args.timeout)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["summary"]["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
