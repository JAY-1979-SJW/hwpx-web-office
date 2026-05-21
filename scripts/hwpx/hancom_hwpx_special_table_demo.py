#!/usr/bin/env python3
"""Append a special-character and merged-cell table demo section to a HWPX file."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from hancom_hwpx_table_integrity_audit import audit_tables
from hwpx_package import HwpxPackage, HwpxValidator
from hwpx_section_ops import append_section, inspect_sections
from hwpx_special_text import sanitize_hwpx_text
from hwpx_text_ops import append_generated_paragraph
from hwpx_table_ops import append_generated_table, find_tables


DEMO_ROWS = [
    ["HWPX 표/특수문자 기능 검증", "", "", ""],
    ["구분", "입력값", "검증 포인트", "상태"],
    ["단위", "1,000㎡ / 210㎜×297㎜", "단위기호 ㎡, ㎜, × 보존", "PASS"],
    ["기호", "※ 주의 / ① ② ③ / 「법령」", "원형번호, 주석, 괄호류 보존", "PASS"],
    ["XML문자", "A & B < C > D", "XML escape 후 재파싱 가능", "PASS"],
    ["줄바꿈", "1행\n2행\n3행", "개행 보존 및 UTF-8 유지", "PASS"],
]


def sanitize_rows(rows: list[list[str]]) -> tuple[list[list[str]], list[dict[str, Any]]]:
    clean_rows: list[list[str]] = []
    warnings: list[dict[str, Any]] = []
    for row_index, row in enumerate(rows):
        clean_row = []
        for col_index, value in enumerate(row):
            sanitized = sanitize_hwpx_text(value)
            clean_row.append(sanitized["text"])
            if sanitized["changed"]:
                warnings.append(
                    {
                        "row": row_index,
                        "col": col_index,
                        "replacements": sanitized["replacements"],
                    }
                )
        clean_rows.append(clean_row)
    return clean_rows, warnings


def demo_style_refs() -> dict[str, Any]:
    return {
        "tableWidth": "47904",
        "columnWidths": [9000, 18000, 15000, 5904],
        "rowHeights": [2600, 2200, 2400, 2400, 2400, 3600],
        "repeatHeader": "1",
        "cellMargin": {"left": "220", "right": "220", "top": "160", "bottom": "160"},
        "cellVertAlign": "CENTER",
        "cellLineWrap": "BREAK",
        "mergedCells": {"0,0": {"rowSpan": 1, "colSpan": 4}},
        "coveredCells": ["0,1", "0,2", "0,3"],
        "cellVertAlignMap": {"5,1": "CENTER"},
    }


def append_special_table_demo(input_path: Path, output_path: Path, title: str = "HWPX 표 기능 응용 검증") -> dict[str, Any]:
    package = HwpxPackage(input_path)
    before_sections = inspect_sections(package)
    before_tables = find_tables(package)
    section_result = append_section(package, clone_from_index=0, clear_body=True)
    if section_result.get("status") != "SECTION_APPEND_PASS":
        return {"status": "FAIL", "section_result": section_result, "input": str(input_path), "output": str(output_path)}
    section_index = int(section_result["section_count_after"]) - 1
    clean_rows, sanitize_warnings = sanitize_rows(DEMO_ROWS)
    title_result = append_generated_paragraph(package, title, section_index=section_index)
    table_result = append_generated_table(package, clean_rows, section_index=section_index, style_refs=demo_style_refs())
    package.write_package(output_path)
    validation = HwpxValidator.validate_hwpx(output_path)
    integrity = audit_tables(output_path)
    after_package = HwpxPackage(output_path)
    after_sections = inspect_sections(after_package)
    after_tables = find_tables(after_package)
    status = (
        "PASS"
        if validation.get("xml_ok")
        and table_result.get("status") == "GENERATED_TABLE_APPEND_PASS"
        and integrity.get("status") in {"PASS", "WARN"}
        else "FAIL"
    )
    return {
        "status": status,
        "input": str(input_path),
        "output": str(output_path),
        "before_sections": before_sections,
        "after_sections": after_sections,
        "before_table_count": len(before_tables),
        "after_table_count": len(after_tables),
        "sanitize_warnings": sanitize_warnings,
        "section_result": section_result,
        "title_result": title_result,
        "table_result": table_result,
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
    parser.add_argument("--title", default="HWPX 표 기능 응용 검증")
    parser.add_argument("--report-json", type=Path)
    args = parser.parse_args()

    report = append_special_table_demo(args.input, args.output, args.title)
    if args.report_json:
        args.report_json.parent.mkdir(parents=True, exist_ok=True)
        args.report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
