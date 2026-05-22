#!/usr/bin/env python3
"""Run a forensic conversion and inspect the generated audit JSONL."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from hwp_diag_common import exit_code, print_report, status_from_errors, utc_now, write_report
from hwp_to_hwpx_standalone import convert_hwp_to_hwpx, write_audit_log


def check_audit_log_probe(input_path: Path, output_path: Path, audit_log: Path) -> dict:
    input_path = Path(input_path).expanduser().resolve()
    output_path = Path(output_path).expanduser().resolve()
    audit_log = Path(audit_log).expanduser().resolve()
    report = convert_hwp_to_hwpx(input_path, output_path, fidelity_policy="audit", existing_policy="overwrite")
    write_audit_log(audit_log, report, event="diagnostic_conversion", audit_level="forensic")
    rows = []
    if audit_log.exists():
        rows = [json.loads(line) for line in audit_log.read_text(encoding="utf-8").splitlines() if line.strip()]
    last = rows[-1] if rows else {}
    errors: list[str] = []
    warnings: list[str] = []
    if not rows:
        errors.append("AUDIT_LOG_EMPTY")
    if last.get("audit_level") != "forensic":
        errors.append("AUDIT_LEVEL_NOT_FORENSIC")
    if len(str(last.get("report_sha256") or "")) != 64:
        errors.append("REPORT_DIGEST_MISSING")
    if "result" not in last:
        errors.append("FORENSIC_RESULT_MISSING")
    if report.get("status") != "PASS":
        errors.append(str(report.get("error") or "CONVERSION_NOT_PASS"))
    if (last.get("result") or {}).get("fidelity_gate", {}).get("status") == "WARN":
        warnings.append("FIDELITY_WARN")
    return {
        "status": status_from_errors(errors, warnings),
        "tool": "04_audit_log_probe",
        "checked_at": utc_now(),
        "input": str(input_path),
        "output": str(output_path),
        "audit_log": str(audit_log),
        "audit_row_count": len(rows),
        "last_event": last.get("event"),
        "last_audit_level": last.get("audit_level"),
        "last_report_sha256": last.get("report_sha256"),
        "last_fidelity_status": (last.get("result") or {}).get("fidelity_gate", {}).get("status"),
        "errors": errors,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--audit-log", required=True, type=Path)
    parser.add_argument("--report-json", type=Path)
    args = parser.parse_args()
    report = check_audit_log_probe(args.input, args.output, args.audit_log)
    write_report(args.report_json, report)
    print_report(report)
    return exit_code(report)


if __name__ == "__main__":
    raise SystemExit(main())

