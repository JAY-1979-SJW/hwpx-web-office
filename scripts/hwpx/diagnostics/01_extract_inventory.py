#!/usr/bin/env python3
"""Run HWP text extraction and emit record/feature inventory."""

from __future__ import annotations

import argparse
from pathlib import Path

from hwp_diag_common import exit_code, print_report, status_from_errors, utc_now, write_report
from extract_hwp_body_fields import extract_hwp_text


def check_extract_inventory(input_path: Path) -> dict:
    input_path = Path(input_path).expanduser().resolve()
    errors: list[str] = []
    warnings: list[str] = []
    extraction = extract_hwp_text(input_path)
    if not extraction.get("ok"):
        errors.append(str(extraction.get("error") or "EXTRACTION_FAILED"))
    inventory = extraction.get("feature_inventory") if isinstance(extraction.get("feature_inventory"), dict) else {}
    if inventory.get("risk_record_tags"):
        warnings.append("FIDELITY_RISK_RECORDS_PRESENT")
    if int(inventory.get("bindata_count") or 0) > 0:
        warnings.append("BINDATA_PRESENT")
    return {
        "status": status_from_errors(errors, warnings),
        "tool": "01_extract_inventory",
        "checked_at": utc_now(),
        "input": str(input_path),
        "extract_ok": bool(extraction.get("ok")),
        "extract_error": extraction.get("error"),
        "header": extraction.get("header"),
        "section_count": len(extraction.get("sections") or []),
        "paragraph_count": sum(int(section.get("paragraphs") or 0) for section in extraction.get("sections") or [] if isinstance(section, dict)),
        "text_length": len(str(extraction.get("text") or "")),
        "record_counts": extraction.get("record_counts", {}),
        "record_tag_names": extraction.get("record_tag_names", {}),
        "feature_inventory": inventory,
        "errors": errors,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--report-json", type=Path)
    args = parser.parse_args()
    report = check_extract_inventory(args.input)
    write_report(args.report_json, report)
    print_report(report)
    return exit_code(report)


if __name__ == "__main__":
    raise SystemExit(main())
