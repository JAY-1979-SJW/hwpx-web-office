"""Build a PII-safe dashboard from HWPX form auto-fill gate reports."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

REPORT_DIR = Path("data") / "reports" / "hwpx_form_auto_fill_gate_dashboard"
ABS_PATH_RE = re.compile(r"(?<![A-Za-z])([A-Za-z]:[\\/][^\s\"']*|/(home|tmp|var|Users)/[^\s\"']*)")
RAW_FILENAME_RE = re.compile(r"\b[^\\/:\s]+\.hwpx\b", re.IGNORECASE)
PII_RE = re.compile(
    r"(\d{6}-\d{7}|\d{3}-\d{2}-\d{5}|\d{2,3}-\d{3,4}-\d{4}|"
    r"\d{2,6}-\d{2,6}-\d{2,6}|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})"
)
PASS_VERDICT = "PASS_HWPX_FORM_AUTO_FILL_GATE_DASHBOARD"


def _no_leak(text: str) -> bool:
    return not (ABS_PATH_RE.search(text) or RAW_FILENAME_RE.search(text) or PII_RE.search(text))


def build_dashboard(
    fail_fast_payload: dict[str, Any],
    upload_payload: dict[str, Any],
    history_summary: dict[str, Any],
    report_dir: Path = REPORT_DIR,
) -> dict[str, Any]:
    dashboard = {
        "schemaVersion": "hwpx_form_auto_fill_gate_dashboard_v1",
        "verdict": PASS_VERDICT
        if fail_fast_payload.get("verdict", "").startswith("PASS")
        and upload_payload.get("verdict", "").startswith("PASS")
        and history_summary.get("modulesFailed", 0) == 0
        else "FAIL_HWPX_FORM_AUTO_FILL_GATE_DASHBOARD",
        "sections": {
            "failFast": {
                "verdict": fail_fast_payload.get("verdict"),
                "failedChecks": fail_fast_payload.get("summary", {}).get("failedChecks", 0),
            },
            "uploadGate": {
                "verdict": upload_payload.get("verdict"),
                "accepted": upload_payload.get("summary", {}).get("accepted", 0),
                "blocked": upload_payload.get("summary", {}).get("blocked", 0),
            },
            "moduleHistory": {
                "entriesWritten": history_summary.get("entriesWritten", 0),
                "modulesPassed": history_summary.get("modulesPassed", 0),
                "modulesFailed": history_summary.get("modulesFailed", 0),
            },
        },
        "security": {
            "piiLeak": 0,
            "rawPathLeak": 0,
            "rawFilenameLeak": 0,
            "aiApiCalled": False,
            "ocrCalled": False,
            "hancomRequired": False,
        },
        "warnings": [
            "WARN_SANDBOX_ONLY",
            "WARN_REAL_USER_FILE_NOT_TESTED",
            "WARN_DEPLOY_NOT_PERFORMED",
        ],
    }
    _write_reports(report_dir, dashboard)
    return dashboard


def _write_reports(report_dir: Path, dashboard: dict[str, Any]) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(dashboard, ensure_ascii=False, indent=2)
    if not _no_leak(text):
        raise ValueError("unsafe dashboard json")
    (report_dir / "gate_dashboard.json").write_text(text, encoding="utf-8")
    lines = [
        "# HWPX Form Auto Fill Gate Dashboard",
        "",
        f"- verdict: {dashboard['verdict']}",
        f"- fail-fast: {dashboard['sections']['failFast']['verdict']}",
        f"- upload gate: {dashboard['sections']['uploadGate']['verdict']}",
        f"- module history passed: {dashboard['sections']['moduleHistory']['modulesPassed']}",
        f"- module history failed: {dashboard['sections']['moduleHistory']['modulesFailed']}",
        f"- security: pii={dashboard['security']['piiLeak']} rawPath={dashboard['security']['rawPathLeak']} rawFilename={dashboard['security']['rawFilenameLeak']}",
        "",
        "## Sections",
        "- fail-fast integrated gate",
        "- module audit history",
        "- upload gate",
        "- security summary",
    ]
    md = "\n".join(lines) + "\n"
    if not _no_leak(md):
        raise ValueError("unsafe dashboard markdown")
    (report_dir / "gate_dashboard.md").write_text(md, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fail-fast", required=True)
    parser.add_argument("--upload-gate", required=True)
    parser.add_argument("--history-summary", required=True)
    parser.add_argument("--report-dir", default=str(REPORT_DIR))
    args = parser.parse_args()
    payload = build_dashboard(
        json.loads(Path(args.fail_fast).read_text(encoding="utf-8")),
        json.loads(Path(args.upload_gate).read_text(encoding="utf-8")),
        json.loads(Path(args.history_summary).read_text(encoding="utf-8")),
        report_dir=Path(args.report_dir),
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["verdict"] == PASS_VERDICT else 1


if __name__ == "__main__":
    raise SystemExit(main())

