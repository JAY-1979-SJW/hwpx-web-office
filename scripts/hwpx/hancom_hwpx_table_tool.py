#!/usr/bin/env python3
"""Apply JSON table operations to a HWPX file and run table integrity audit."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from hancom_hwpx_table_integrity_audit import audit_tables
from hwpx_package import HwpxPackage, HwpxValidator
from hwpx_special_text import sanitize_hwpx_text
from hwpx_table_ops import apply_table_operations
from hwpx_writer_adapter import HwpxEditor


TEXT_KEYS = {"value", "values"}


def load_operations(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, list):
        raise ValueError("ops-json must be a list of operation objects")
    return [item for item in data if isinstance(item, dict)]


def sanitize_operation_text(operation: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    result = dict(operation)
    warnings: list[dict[str, Any]] = []
    if "value" in result:
        sanitized = sanitize_hwpx_text(result["value"])
        result["value"] = sanitized["text"]
        if sanitized["changed"]:
            warnings.append({"field": "value", "replacements": sanitized["replacements"]})
    if "values" in result and isinstance(result["values"], list):
        values = []
        for index, value in enumerate(result["values"]):
            sanitized = sanitize_hwpx_text(value)
            values.append(sanitized["text"])
            if sanitized["changed"]:
                warnings.append({"field": "values", "index": index, "replacements": sanitized["replacements"]})
        result["values"] = values
    if "updates" in result and isinstance(result["updates"], list):
        updates = []
        for update_index, update in enumerate(result["updates"]):
            if not isinstance(update, dict):
                continue
            updated = dict(update)
            if "value" in updated:
                sanitized = sanitize_hwpx_text(updated["value"])
                updated["value"] = sanitized["text"]
                if sanitized["changed"]:
                    warnings.append({"field": "updates.value", "index": update_index, "replacements": sanitized["replacements"]})
            updates.append(updated)
        result["updates"] = updates
    return result, warnings


def run_table_tool(input_path: Path, output_path: Path | None, ops_json: Path | None) -> dict[str, Any]:
    package = HwpxPackage(input_path)
    operation_report = {"status": "SKIPPED", "operations": [], "warnings": []}
    if ops_json:
        raw_ops = load_operations(ops_json)
        operations = []
        sanitize_warnings = []
        for index, operation in enumerate(raw_ops, start=1):
            sanitized, warnings = sanitize_operation_text(operation)
            operations.append(sanitized)
            for warning in warnings:
                warning["operation_index"] = index
                sanitize_warnings.append(warning)
        editor = HwpxEditor(package)
        operation_report = apply_table_operations(editor, operations)
        operation_report["text_sanitize_warnings"] = sanitize_warnings
    target = output_path or input_path
    if output_path:
        package.write_package(output_path)
    validation = HwpxValidator.validate_hwpx(target)
    integrity = audit_tables(target)
    return {
        "status": "PASS"
        if validation.get("xml_ok") and integrity.get("status") in {"PASS", "WARN"} and operation_report.get("status") in {"PASS", "SKIPPED"}
        else "WARN",
        "input": str(input_path),
        "output": str(target),
        "operations": operation_report,
        "validation": validation,
        "table_integrity": {
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
    parser.add_argument("--output", type=Path)
    parser.add_argument("--ops-json", type=Path)
    parser.add_argument("--report-json", type=Path)
    args = parser.parse_args()

    report = run_table_tool(args.input, args.output, args.ops_json)
    if args.report_json:
        args.report_json.parent.mkdir(parents=True, exist_ok=True)
        args.report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] in {"PASS", "WARN"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
