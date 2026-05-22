#!/usr/bin/env python3
"""Evaluate standalone conversion fidelity policy without writing HWPX output."""

from __future__ import annotations

import argparse
from pathlib import Path

from hwp_diag_common import exit_code, print_report, status_from_errors, utc_now, write_report
from extract_hwp_body_fields import extract_hwp_text
from hwp_to_hwpx_standalone import FIDELITY_POLICIES, fidelity_gate


def check_fidelity_gate(input_path: Path, policy: str) -> dict:
    input_path = Path(input_path).expanduser().resolve()
    extraction = extract_hwp_text(input_path)
    gate = fidelity_gate(extraction, policy=policy)
    errors: list[str] = []
    warnings: list[str] = []
    if not extraction.get("ok"):
        errors.append(str(extraction.get("error") or "EXTRACTION_FAILED"))
    if gate.get("status") == "FAIL":
        errors.append("FIDELITY_GATE_FAILED")
    elif gate.get("status") == "WARN":
        warnings.append("FIDELITY_GATE_WARN")
    return {
        "status": status_from_errors(errors, warnings),
        "tool": "02_fidelity_gate",
        "checked_at": utc_now(),
        "input": str(input_path),
        "policy": policy,
        "extract_ok": bool(extraction.get("ok")),
        "fidelity_gate": gate,
        "errors": errors,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--policy", choices=FIDELITY_POLICIES, default="audit")
    parser.add_argument("--report-json", type=Path)
    args = parser.parse_args()
    report = check_fidelity_gate(args.input, args.policy)
    write_report(args.report_json, report)
    print_report(report)
    return exit_code(report)


if __name__ == "__main__":
    raise SystemExit(main())
