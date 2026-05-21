#!/usr/bin/env python3
"""Insert a schedule diagram suite into an HWPX document."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
from typing import Any

from hancom_hwpx_table_integrity_audit import audit_tables
from hwpx_manifest_ops import inspect_package_manifest, repair_package_manifest
from hwpx_package import HwpxPackage, HwpxValidator
from hwpx_schedule_diagrams import insert_schedule_diagram_tables, parse_schedule_items
from hwpx_section_ops import inspect_sections
from hwpx_table_ops import find_tables


def run_schedule_diagram_suite(
    input_path: Path,
    output_path: Path,
    *,
    items_json: Path | None = None,
    daily_start: str = "2026-05-01",
    daily_days: int = 31,
    month_count: int = 3,
    insert_at_start: bool = True,
    title: str = "공정표 및 그래프 도식",
) -> dict[str, Any]:
    package = HwpxPackage(input_path)
    before_sections = inspect_sections(package)
    before_tables = find_tables(package)
    items = parse_schedule_items(items_json)
    insert_result = insert_schedule_diagram_tables(
        package,
        items,
        section_index=0,
        insert_at_start=insert_at_start,
        daily_start=datetime.strptime(daily_start, "%Y-%m-%d").date(),
        daily_days=daily_days,
        month_count=month_count,
        title=title,
    )
    manifest_repair = repair_package_manifest(package)
    package.write_package(output_path)
    validation = HwpxValidator.validate_hwpx(output_path)
    output_package = HwpxPackage(output_path)
    manifest = inspect_package_manifest(output_package)
    after_sections = inspect_sections(output_package)
    after_tables = find_tables(output_package)
    integrity = audit_tables(output_path)
    status = (
        "PASS"
        if insert_result.get("status") == "SCHEDULE_DIAGRAM_TABLES_INSERT_PASS"
        and validation.get("xml_ok")
        and manifest.get("status") == "PASS"
        and integrity.get("status") in {"PASS", "WARN"}
        else "FAIL"
    )
    return {
        "status": status,
        "input": str(input_path),
        "output": str(output_path),
        "item_count": len(items),
        "before_sections": before_sections,
        "after_sections": after_sections,
        "before_table_count": len(before_tables),
        "after_table_count": len(after_tables),
        "insert_result": insert_result,
        "manifest_repair": manifest_repair,
        "manifest": {
            "status": manifest.get("status"),
            "missing_manifest_entries": manifest.get("missing_manifest_entries"),
            "missing_spine_sections": manifest.get("missing_spine_sections"),
        },
        "validation": validation,
        "integrity_summary": {
            "status": integrity.get("status"),
            "table_count": integrity.get("table_count"),
            "problem_count": integrity.get("problem_count"),
            "problem_counts": integrity.get("problem_counts"),
            "warning_count": integrity.get("warning_count"),
            "warning_counts": integrity.get("warning_counts"),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--items-json", type=Path)
    parser.add_argument("--daily-start", default="2026-05-01")
    parser.add_argument("--daily-days", type=int, default=31)
    parser.add_argument("--month-count", type=int, default=3)
    parser.add_argument("--append", action="store_true", help="Append diagrams at the end instead of inserting at document start.")
    parser.add_argument("--title", default="공정표 및 그래프 도식")
    parser.add_argument("--report-json", type=Path)
    args = parser.parse_args()

    report = run_schedule_diagram_suite(
        args.input,
        args.output,
        items_json=args.items_json,
        daily_start=args.daily_start,
        daily_days=args.daily_days,
        month_count=args.month_count,
        insert_at_start=not args.append,
        title=args.title,
    )
    if args.report_json:
        args.report_json.parent.mkdir(parents=True, exist_ok=True)
        args.report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
