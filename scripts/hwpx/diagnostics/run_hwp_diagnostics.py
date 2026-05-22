#!/usr/bin/env python3
"""Run the small HWP -> HWPX diagnostic scripts and summarize results."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from hwp_diag_common import exit_code, print_report, status_from_errors, utc_now, write_report


def run_step(name: str, cmd: list[str]) -> dict:
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    parsed = None
    try:
        parsed = json.loads(proc.stdout)
    except json.JSONDecodeError:
        parsed = None
    return {
        "name": name,
        "returncode": proc.returncode,
        "status": (parsed or {}).get("status", "FAIL" if proc.returncode else "PASS"),
        "stdout_json": parsed,
        "stdout_tail": proc.stdout[-2000:],
        "stderr_tail": proc.stderr[-2000:],
        "command": cmd,
    }


def run_diagnostics(input_path: Path, out_dir: Path) -> dict:
    input_path = Path(input_path).expanduser().resolve()
    out_dir = Path(out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    output_hwpx = out_dir / f"{input_path.stem}.diagnostic.hwpx"
    audit_log = out_dir / "diagnostic_audit.jsonl"
    py = sys.executable
    here = Path(__file__).resolve().parent
    steps = [
        ("input_signature", [py, str(here / "00_input_signature.py"), str(input_path), "--report-json", str(out_dir / "00_input_signature.json")]),
        ("extract_inventory", [py, str(here / "01_extract_inventory.py"), str(input_path), "--report-json", str(out_dir / "01_extract_inventory.json")]),
        ("fidelity_gate", [py, str(here / "02_fidelity_gate.py"), str(input_path), "--policy", "audit", "--report-json", str(out_dir / "02_fidelity_gate.json")]),
        ("convert_smoke", [py, str(here / "03_convert_smoke.py"), str(input_path), str(output_hwpx), "--fidelity-policy", "audit", "--report-json", str(out_dir / "03_convert_smoke.json")]),
        ("roundtrip_text_probe", [py, str(here / "06_roundtrip_text_probe.py"), str(input_path), str(output_hwpx), "--report-json", str(out_dir / "06_roundtrip_text_probe.json")]),
        ("audit_log_probe", [py, str(here / "04_audit_log_probe.py"), str(input_path), str(out_dir / "audit_probe.hwpx"), "--audit-log", str(audit_log), "--report-json", str(out_dir / "04_audit_log_probe.json")]),
        ("batch_plan_probe", [py, str(here / "05_batch_plan_probe.py"), str(input_path.parent), str(out_dir / "batch_out"), "--pattern", input_path.name, "--existing-policy", "skip", "--report-json", str(out_dir / "05_batch_plan_probe.json")]),
    ]
    results = [run_step(name, cmd) for name, cmd in steps]
    errors = [item["name"] for item in results if item["returncode"] not in (0,) or item["status"] == "FAIL"]
    warnings = [item["name"] for item in results if item["status"] == "WARN"]
    return {
        "status": status_from_errors(errors, warnings),
        "tool": "run_hwp_diagnostics",
        "checked_at": utc_now(),
        "input": str(input_path),
        "out_dir": str(out_dir),
        "output_hwpx": str(output_hwpx),
        "audit_log": str(audit_log),
        "step_count": len(results),
        "errors": errors,
        "warnings": warnings,
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--out-dir", type=Path, default=Path("tmp/hwp_diagnostics"))
    parser.add_argument("--report-json", type=Path)
    args = parser.parse_args()
    report = run_diagnostics(args.input, args.out_dir)
    write_report(args.report_json or Path(args.out_dir) / "diagnostics_summary.json", report)
    print_report(report)
    return exit_code(report)


if __name__ == "__main__":
    raise SystemExit(main())
