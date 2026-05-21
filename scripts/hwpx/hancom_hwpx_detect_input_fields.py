#!/usr/bin/env python3
"""Detect HWPX table input fields from headers and labels."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from hwpx_header_field_detector import detect_input_fields, input_request_markdown
from hwpx_package import HwpxPackage, HwpxValidator


def run_detect_input_fields(
    input_path: Path,
    *,
    table_limit: int | None = None,
    min_confidence: float = 0.7,
) -> dict:
    package = HwpxPackage(input_path)
    report = detect_input_fields(package, table_limit=table_limit, min_confidence=min_confidence)
    validation = HwpxValidator.validate_hwpx(input_path)
    report["input"] = str(input_path)
    report["validation"] = validation
    report["status"] = "PASS" if report.get("status") == "PASS" and validation.get("xml_ok") else "FAIL"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--table-limit", type=int)
    parser.add_argument("--min-confidence", type=float, default=0.7)
    parser.add_argument("--report-json", type=Path)
    parser.add_argument("--request-md", type=Path)
    parser.add_argument("--template-json", type=Path)
    args = parser.parse_args()

    report = run_detect_input_fields(args.input, table_limit=args.table_limit, min_confidence=args.min_confidence)
    if args.report_json:
        args.report_json.parent.mkdir(parents=True, exist_ok=True)
        args.report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.request_md:
        args.request_md.parent.mkdir(parents=True, exist_ok=True)
        args.request_md.write_text(input_request_markdown(report), encoding="utf-8")
    if args.template_json:
        args.template_json.parent.mkdir(parents=True, exist_ok=True)
        args.template_json.write_text(json.dumps(report.get("input_template", {}), ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
