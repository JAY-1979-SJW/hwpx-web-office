#!/usr/bin/env python3
"""Audit HWPX tables for structure, spans, text-node, and special-character risks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from hwpx_package import HwpxPackage, HwpxValidator
from hwpx_special_text import text_special_char_profile
from hwpx_table_ops import all_cell_text_nodes, cell_elements, cell_visual_address, find_table, find_tables, row_elements


def audit_table(package: HwpxPackage, table_index: int) -> dict[str, Any]:
    found = find_table(package, table_index)
    if not found:
        return {"status": "TABLE_NOT_FOUND", "table": table_index}
    entry, _root, table = found
    occupied: dict[tuple[int, int], dict[str, Any]] = {}
    problems: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    cells = []
    for physical_row, row in enumerate(row_elements(table)):
        for physical_col, cell in enumerate(cell_elements(row)):
            visual = cell_visual_address(physical_row, physical_col, cell)
            text_nodes = all_cell_text_nodes(cell)
            node_texts = [node.text or "" for node in text_nodes]
            non_empty = [text for text in node_texts if text.strip()]
            text = "".join(node_texts)
            profile = text_special_char_profile(text)
            cell_info = {
                "physical_row": physical_row,
                "physical_col": physical_col,
                "row": visual["row"],
                "col": visual["col"],
                "rowspan": visual["rowspan"],
                "colspan": visual["colspan"],
                "text": text,
                "text_node_count": len(text_nodes),
                "non_empty_text_node_count": len(non_empty),
                "special_profile": profile,
            }
            cells.append(cell_info)
            if len(non_empty) > 1:
                warnings.append({"code": "MULTIPLE_NON_EMPTY_TEXT_NODES", "cell": cell_info})
            if not profile["ok"]:
                problems.append({"code": "INVALID_TEXT_CHARACTER", "cell": cell_info})
            for r in range(visual["row"], visual["row"] + visual["rowspan"]):
                for c in range(visual["col"], visual["col"] + visual["colspan"]):
                    key = (r, c)
                    if key in occupied:
                        problems.append(
                            {
                                "code": "VISUAL_GRID_OVERLAP",
                                "row": r,
                                "col": c,
                                "first": occupied[key],
                                "second": {"row": visual["row"], "col": visual["col"]},
                            }
                        )
                    else:
                        occupied[key] = {"row": visual["row"], "col": visual["col"]}
    return {
        "status": "FAIL" if problems else ("WARN" if warnings else "PASS"),
        "table": table_index,
        "entry": entry,
        "cell_count": len(cells),
        "occupied_grid_count": len(occupied),
        "problem_count": len(problems),
        "warning_count": len(warnings),
        "problems": problems,
        "warnings": warnings,
        "cells": cells,
    }


def audit_tables(input_path: Path) -> dict[str, Any]:
    package = HwpxPackage(input_path)
    tables = find_tables(package)
    table_reports = [audit_table(package, index) for index in range(len(tables))]
    problems = [problem for table in table_reports for problem in table.get("problems", [])]
    warnings = [warning for table in table_reports for warning in table.get("warnings", [])]
    validation = HwpxValidator.validate_hwpx(input_path)
    status = "FAIL" if not validation.get("xml_ok") or problems else ("WARN" if warnings else "PASS")
    return {
        "status": status,
        "input": str(input_path),
        "validation": validation,
        "table_count": len(tables),
        "problem_count": len(problems),
        "warning_count": len(warnings),
        "problem_counts": {code: sum(1 for p in problems if p.get("code") == code) for code in sorted({p.get("code") for p in problems})},
        "warning_counts": {code: sum(1 for w in warnings if w.get("code") == code) for code in sorted({w.get("code") for w in warnings})},
        "tables": table_reports,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--report-json", type=Path)
    args = parser.parse_args()

    report = audit_tables(args.input)
    if args.report_json:
        args.report_json.parent.mkdir(parents=True, exist_ok=True)
        args.report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] in {"PASS", "WARN"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
