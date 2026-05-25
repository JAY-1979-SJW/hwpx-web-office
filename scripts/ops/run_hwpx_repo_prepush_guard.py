"""Run fail-fast smoke checks suitable for a pre-push or PR precheck."""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.ops import gate_hwpx_form_auto_fill_fail_fast as fail_fast_gate  # noqa: E402

REPORT_DIR = ROOT / "data" / "reports" / "hwpx_repo_prepush_guard"
TEMP_ROOT = ROOT / "data" / "tmp" / "hpg"

PASS_VERDICT = "PASS_HWPX_REPO_PREPUSH_GUARD"
FAIL_VERDICT = "FAIL_HWPX_REPO_PREPUSH_GUARD"


def evaluate_prepush_guard(fail_fast_payload: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    if fail_fast_payload.get("verdict") != fail_fast_gate.PASS_VERDICT:
        failures.append("FAIL_FAIL_FAST_GATE")
    return {
        "schemaVersion": "hwpx_repo_prepush_guard_v1",
        "verdict": PASS_VERDICT if not failures else FAIL_VERDICT,
        "summary": {
            "stepsTotal": fail_fast_payload.get("summary", {}).get("stepsTotal", 0),
            "stepsFailed": fail_fast_payload.get("summary", {}).get("stepsFailed", 0),
        },
        "failFastVerdict": fail_fast_payload.get("verdict"),
        "repoManifestDriftZeroVerdict": fail_fast_payload.get("repoManifestDriftZeroVerdict"),
        "failures": failures,
        "security": {
            "piiLeak": 0,
            "rawPathLeak": 0,
            "rawFilenameLeak": 0,
        },
    }


def run_prepush_guard(report_dir: Path | None = REPORT_DIR, temp_only: bool = False) -> dict[str, Any]:
    if temp_only:
        TEMP_ROOT.mkdir(parents=True, exist_ok=True)
        tmpdir = TEMP_ROOT / uuid.uuid4().hex[:8]
        tmpdir.mkdir(parents=True, exist_ok=False)
        return _run_core(tmpdir)
    target = report_dir or REPORT_DIR
    target.mkdir(parents=True, exist_ok=True)
    return _run_core(target)


def _run_core(report_dir: Path) -> dict[str, Any]:
    fail_fast_payload = fail_fast_gate.run_fail_fast_gate(
        report_dir=report_dir / "fail_fast",
        full_module_audit=False,
    )
    payload = evaluate_prepush_guard(fail_fast_payload)
    if report_dir == REPORT_DIR or report_dir.is_relative_to(ROOT):
        _write_reports(report_dir, payload)
    return payload


def _no_leak(text: str) -> bool:
    return not (
        fail_fast_gate.ABS_PATH_RE.search(text)
        or fail_fast_gate.RAW_FILENAME_RE.search(text)
        or fail_fast_gate.PII_RE.search(text)
    )


def _safe_write(path: Path, payload: Any) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if not _no_leak(text):
        raise ValueError(f"unsafe prepush guard payload: {path.name}")
    path.write_text(text, encoding="utf-8")


def _write_reports(report_dir: Path, payload: dict[str, Any]) -> None:
    _safe_write(report_dir / "prepush_guard_summary.json", payload)
    lines = [
        "# HWPX Repo Prepush Guard",
        "",
        f"- verdict: {payload['verdict']}",
        f"- fail-fast verdict: {payload['failFastVerdict']}",
        f"- repo manifest drift zero: {payload['repoManifestDriftZeroVerdict']}",
        f"- steps failed: {payload['summary']['stepsFailed']}/{payload['summary']['stepsTotal']}",
    ]
    text = "\n".join(lines) + "\n"
    if not _no_leak(text):
        raise ValueError("unsafe prepush guard markdown")
    (report_dir / "prepush_guard_summary.md").write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", default=str(REPORT_DIR))
    parser.add_argument("--temp-only", action="store_true")
    args = parser.parse_args()
    payload = run_prepush_guard(report_dir=Path(args.report_dir), temp_only=args.temp_only)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["verdict"] == PASS_VERDICT else 1


if __name__ == "__main__":
    raise SystemExit(main())
