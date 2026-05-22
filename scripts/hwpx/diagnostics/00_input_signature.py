#!/usr/bin/env python3
"""Validate HWP input path, suffix, signature, and basic file metadata."""

from __future__ import annotations

import argparse
from pathlib import Path

from hwp_diag_common import HWP_SIGNATURE, exit_code, print_report, read_prefix, status_from_errors, utc_now, write_report
from hwp_to_hwpx_standalone import file_snapshot


def check_input_signature(input_path: Path) -> dict:
    input_path = Path(input_path).expanduser().resolve()
    errors: list[str] = []
    warnings: list[str] = []
    prefix = b""
    if not input_path.exists():
        errors.append("INPUT_NOT_FOUND")
    elif not input_path.is_file():
        errors.append("INPUT_NOT_FILE")
    else:
        prefix = read_prefix(input_path, len(HWP_SIGNATURE))
        if input_path.suffix.lower() != ".hwp":
            warnings.append("INPUT_SUFFIX_NOT_HWP")
        if prefix != HWP_SIGNATURE:
            errors.append("HWP_SIGNATURE_MISMATCH")
        if input_path.stat().st_size <= len(HWP_SIGNATURE):
            warnings.append("INPUT_TOO_SMALL")
    return {
        "status": status_from_errors(errors, warnings),
        "tool": "00_input_signature",
        "checked_at": utc_now(),
        "input": str(input_path),
        "snapshot": file_snapshot(input_path),
        "prefix_hex": prefix.hex(),
        "expected_signature_hex": HWP_SIGNATURE.hex(),
        "errors": errors,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--report-json", type=Path)
    args = parser.parse_args()
    report = check_input_signature(args.input)
    write_report(args.report_json, report)
    print_report(report)
    return exit_code(report)


if __name__ == "__main__":
    raise SystemExit(main())

