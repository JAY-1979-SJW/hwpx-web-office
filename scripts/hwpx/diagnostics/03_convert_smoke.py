#!/usr/bin/env python3
"""Convert one HWP file and verify output, conversion gate, and validation."""

from __future__ import annotations

import argparse
from pathlib import Path

from hwp_diag_common import exit_code, print_report, status_from_errors, utc_now, write_report
from hwp_to_hwpx_standalone import FIDELITY_POLICIES, convert_hwp_to_hwpx


def check_convert_smoke(input_path: Path, output_path: Path, fidelity_policy: str, strict_quality: bool) -> dict:
    input_path = Path(input_path).expanduser().resolve()
    output_path = Path(output_path).expanduser().resolve()
    report = convert_hwp_to_hwpx(
        input_path,
        output_path,
        fidelity_policy=fidelity_policy,
        strict_quality=strict_quality,
        existing_policy="overwrite",
    )
    validation = report.get("validation") if isinstance(report.get("validation"), dict) else {}
    gate = report.get("conversion_gate") if isinstance(report.get("conversion_gate"), dict) else {}
    errors: list[str] = []
    warnings: list[str] = []
    if report.get("status") != "PASS":
        errors.append(str(report.get("error") or "CONVERSION_NOT_PASS"))
    if gate.get("status") != "PASS":
        errors.append("CONVERSION_GATE_NOT_PASS")
    if report.get("status") == "PASS" and not output_path.exists():
        errors.append("OUTPUT_NOT_WRITTEN")
    if report.get("status") == "PASS" and (validation.get("zip_ok") is not True or validation.get("xml_ok") is not True):
        errors.append("OUTPUT_VALIDATION_FAILED")
    fidelity = report.get("fidelity_gate") if isinstance(report.get("fidelity_gate"), dict) else {}
    if fidelity.get("status") == "WARN":
        warnings.append("FIDELITY_WARN")
    return {
        "status": status_from_errors(errors, warnings),
        "tool": "03_convert_smoke",
        "checked_at": utc_now(),
        "input": str(input_path),
        "output": str(output_path),
        "converter_status": report.get("status"),
        "conversion_gate": gate,
        "fidelity_gate": fidelity,
        "validation": validation,
        "report": report,
        "errors": errors,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--fidelity-policy", choices=FIDELITY_POLICIES, default="audit")
    parser.add_argument("--strict-quality", action="store_true")
    parser.add_argument("--report-json", type=Path)
    args = parser.parse_args()
    report = check_convert_smoke(args.input, args.output, args.fidelity_policy, bool(args.strict_quality))
    write_report(args.report_json, report)
    print_report(report)
    return exit_code(report)


if __name__ == "__main__":
    raise SystemExit(main())

