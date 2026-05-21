#!/usr/bin/env python3
"""Inspect original HWPX table/cell style references and text-fit risk."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from hwpx_package import HwpxPackage, HwpxValidator
from hwpx_table_ops import find_tables, get_table_cell_matrix


def audit_table_styles(input_path: Path) -> dict[str, Any]:
    package = HwpxPackage(input_path)
    tables = find_tables(package)
    matrices = [get_table_cell_matrix(package, index) for index in range(len(tables))]
    cells = []
    missing_style = []
    fit_warnings = []
    for matrix in matrices:
        table_index = matrix.get("table_index")
        for row in matrix.get("rows", []):
            for cell in row.get("cells", []):
                style = cell.get("style_reference") or {}
                fit = cell.get("fit_check") or {}
                item = {
                    "table": table_index,
                    "row": cell.get("visual_row"),
                    "col": cell.get("visual_col"),
                    "text": cell.get("text", ""),
                    "charPrIDRef": style.get("charPrIDRef"),
                    "paraPrIDRef": style.get("paraPrIDRef"),
                    "styleIDRef": style.get("styleIDRef"),
                    "cell_width": cell.get("cell_width"),
                    "cell_height": cell.get("cell_height"),
                    "line_wrap": (cell.get("sublist") or {}).get("lineWrap"),
                    "fit_status": fit.get("status"),
                }
                cells.append(item)
                if not item["charPrIDRef"]:
                    missing_style.append(item)
                if str(item["fit_status"]).startswith("WARN"):
                    fit_warnings.append(item)
    validation = HwpxValidator.validate_hwpx(input_path)
    return {
        "status": "PASS" if validation.get("xml_ok") and not missing_style else "WARN",
        "input": str(input_path),
        "validation": validation,
        "table_count": len(tables),
        "cell_count": len(cells),
        "missing_style_reference_count": len(missing_style),
        "fit_warning_count": len(fit_warnings),
        "missing_style_references": missing_style,
        "fit_warnings": fit_warnings,
        "tables": matrices,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--report-json", type=Path)
    args = parser.parse_args()

    report = audit_table_styles(args.input)
    if args.report_json:
        args.report_json.parent.mkdir(parents=True, exist_ok=True)
        args.report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] in {"PASS", "WARN"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
