#!/usr/bin/env python3
"""Audit a generated HWPX form directly against its input report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from hwpx_package import HwpxPackage, HwpxValidator, local_name
from hwpx_table_ops import (
    all_cell_text_nodes,
    cell_elements,
    cell_visual_address,
    estimate_text_fit,
    find_cell_text_style_reference,
    find_table,
    get_table_cell_matrix,
    row_elements,
)


def load_report(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError("report JSON root must be an object")
    return data


def table_cell_at(matrix: dict[str, Any], row: int, col: int) -> dict[str, Any] | None:
    for row_info in matrix.get("rows", []):
        for cell in row_info.get("cells", []):
            if cell.get("visual_row") == row and cell.get("visual_col") == col:
                return cell
    return None


def find_visual_cell(package: HwpxPackage, table_index: int, row: int, col: int) -> dict[str, Any]:
    found = find_table(package, table_index)
    if not found:
        return {"status": "TABLE_NOT_FOUND", "table": table_index, "row": row, "col": col}
    entry, _root, table = found
    for physical_row, row_elem in enumerate(row_elements(table)):
        for physical_col, cell in enumerate(cell_elements(row_elem)):
            visual = cell_visual_address(physical_row, physical_col, cell)
            if visual["row"] == row and visual["col"] == col:
                return {
                    "status": "PASS",
                    "entry": entry,
                    "physical_row": physical_row,
                    "physical_col": physical_col,
                    "cell": cell,
                }
    return {"status": "CELL_NOT_FOUND", "table": table_index, "row": row, "col": col}


def char_pr_height(package: HwpxPackage, char_pr_id: str | None) -> int:
    if not char_pr_id:
        return 1000
    for entry in package.xml_entries():
        if not entry.replace("\\", "/").lower().endswith("contents/header.xml"):
            continue
        root = package.read_xml(entry)
        for elem in root.iter():
            if local_name(elem.tag) == "charPr" and elem.attrib.get("id") == str(char_pr_id):
                try:
                    return int(elem.attrib.get("height", "1000") or 1000)
                except ValueError:
                    return 1000
    return 1000


def audit_update(package: HwpxPackage, update: dict[str, Any], matrix_cache: dict[int, dict[str, Any]]) -> dict[str, Any]:
    table_index = int(update.get("table_index", update.get("table", -1)))
    row = int(update.get("visual_row", update.get("row", -1)))
    col = int(update.get("visual_col", update.get("col", -1)))
    expected = str(update.get("field", update.get("after_text", "")))
    label = str(update.get("label", ""))
    problems: list[dict[str, Any]] = []

    matrix = matrix_cache.setdefault(table_index, get_table_cell_matrix(package, table_index))
    matrix_cell = table_cell_at(matrix, row, col) or {}
    located = find_visual_cell(package, table_index, row, col)
    if located.get("status") != "PASS":
        return {
            "status": "FAIL",
            "label": label,
            "table": table_index,
            "row": row,
            "col": col,
            "problems": [{"code": located.get("status"), "message": "Target cell could not be found."}],
        }

    cell = located["cell"]
    text_nodes = all_cell_text_nodes(cell)
    node_texts = [node.text or "" for node in text_nodes]
    non_empty_nodes = [text for text in node_texts if text.strip()]
    actual = "".join(node_texts)
    style = find_cell_text_style_reference(cell)
    font_height = char_pr_height(package, style.get("charPrIDRef"))
    fit_cell = dict(matrix_cell)
    fit_cell["font_height"] = font_height
    fit_check = estimate_text_fit(actual, fit_cell)
    sublist = matrix_cell.get("sublist", {}) if isinstance(matrix_cell.get("sublist"), dict) else {}
    vertical_align = sublist.get("vertAlign")

    if actual != expected:
        problems.append(
            {
                "code": "TEXT_MISMATCH",
                "message": "Actual cell text does not match the input report.",
                "expected": expected,
                "actual": actual,
            }
        )
    if len(non_empty_nodes) > 1:
        problems.append(
            {
                "code": "MULTIPLE_NON_EMPTY_TEXT_NODES",
                "message": "The cell has more than one non-empty text node and may render overlapping text.",
                "non_empty_text_node_count": len(non_empty_nodes),
                "texts": non_empty_nodes,
            }
        )
    if str(fit_check.get("status", "")).startswith("WARN"):
        problems.append(
            {
                "code": "TEXT_FIT_WARNING",
                "message": "The current HWPX cell still has a text fit warning.",
                "fit_check": fit_check,
            }
        )
    if vertical_align and str(vertical_align).upper() != "CENTER":
        problems.append(
            {
                "code": "VERTICAL_ALIGN_NOT_CENTER",
                "message": "The input cell text is not vertically centered.",
                "actual_vertAlign": vertical_align,
            }
        )

    font_adjustment = update.get("font_adjustment", {}) if isinstance(update.get("font_adjustment"), dict) else {}
    expected_char_pr = font_adjustment.get("new_charPrIDRef")
    if expected_char_pr and str(style.get("charPrIDRef")) != str(expected_char_pr):
        problems.append(
            {
                "code": "FONT_ADJUSTMENT_STYLE_NOT_APPLIED",
                "message": "The target cell does not reference the cloned smaller charPr.",
                "expected_charPrIDRef": str(expected_char_pr),
                "actual_charPrIDRef": style.get("charPrIDRef"),
            }
        )

    return {
        "status": "PASS" if not problems else "FAIL",
        "label": label,
        "table": table_index,
        "row": row,
        "col": col,
        "expected_text": expected,
        "actual_text": actual,
        "text_node_count": len(text_nodes),
        "non_empty_text_node_count": len(non_empty_nodes),
        "charPrIDRef": style.get("charPrIDRef"),
        "font_height": font_height,
        "vertical_align": vertical_align,
        "fit_check": fit_check,
        "problems": problems,
    }


def audit_hwpx_form_output(hwpx_path: Path, form_report_path: Path) -> dict[str, Any]:
    report = load_report(form_report_path)
    package = HwpxPackage(hwpx_path)
    validation = HwpxValidator.validate_hwpx(hwpx_path)
    updates = [item for item in report.get("updates", []) if isinstance(item, dict)]
    matrix_cache: dict[int, dict[str, Any]] = {}
    results = [audit_update(package, update, matrix_cache) for update in updates]
    failed = [item for item in results if item.get("status") != "PASS"]
    problem_counts: dict[str, int] = {}
    for item in failed:
        for problem in item.get("problems", []):
            code = str(problem.get("code", "UNKNOWN"))
            problem_counts[code] = problem_counts.get(code, 0) + 1
    return {
        "status": "PASS" if validation.get("xml_ok") and not failed else "FAIL",
        "hwpx": str(hwpx_path),
        "form_report": str(form_report_path),
        "validation": validation,
        "checked_update_count": len(results),
        "failed_update_count": len(failed),
        "problem_counts": problem_counts,
        "failed_updates": failed[:50],
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hwpx", required=True, type=Path)
    parser.add_argument("--form-report-json", required=True, type=Path)
    parser.add_argument("--report-json", type=Path)
    args = parser.parse_args()

    report = audit_hwpx_form_output(args.hwpx, args.form_report_json)
    if args.report_json:
        args.report_json.parent.mkdir(parents=True, exist_ok=True)
        args.report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
