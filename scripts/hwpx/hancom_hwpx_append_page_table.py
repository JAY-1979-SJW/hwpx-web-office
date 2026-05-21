#!/usr/bin/env python3
"""Append a new HWPX section/page with a generated table."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from hwpx_element_factory import append_generated_paragraph, append_generated_table
from hwpx_package import HwpxPackage, HwpxValidator
from hwpx_section_ops import append_section, inspect_sections
from hwpx_table_ops import append_cloned_table_to_section, find_tables


DEFAULT_ROWS = [
    ["구분", "내용", "확인결과", "비고"],
    ["문서 상태", "임의 입력값 기반 완성본", "확인", "실제 제출 전 사실값 교체 필요"],
    ["표 파싱", "기존 5개 표 + 신규 1개 표", "확인", "API 검증 대상"],
    ["문자 겹침", "호/㎡/날짜 단위 중복 없음", "확인", "자동 검사"],
    ["미입력 항목", "미입력 표시 잔존 없음", "확인", "자동 검사"],
]


def load_rows(path: Path | None) -> list[list[str]]:
    if not path:
        return DEFAULT_ROWS
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(raw, list) or not all(isinstance(row, list) for row in raw):
        raise ValueError("table-json must be a list of row arrays")
    rows = [[str(cell) for cell in row] for row in raw]
    if not rows or not any(rows):
        raise ValueError("table-json must include at least one non-empty row")
    return rows


def append_page_table(
    input_path: Path,
    output_path: Path,
    title: str,
    rows: list[list[str]],
    *,
    table_mode: str = "generated",
    source_table_index: int = 0,
) -> dict[str, Any]:
    package = HwpxPackage(input_path)
    before_sections = inspect_sections(package)
    before_tables = find_tables(package)
    section_result = append_section(package, clone_from_index=0, clear_body=True)
    if section_result.get("status") != "SECTION_APPEND_PASS":
        return {
            "status": "FAIL",
            "input": str(input_path),
            "output": str(output_path),
            "section_result": section_result,
        }
    section_index = int(section_result["section_count_after"]) - 1
    title_result = append_generated_paragraph(package, title, section_index=section_index)
    if table_mode == "clone-template":
        table_result = append_cloned_table_to_section(
            package,
            source_table_index=source_table_index,
            rows=rows,
            section_index=section_index,
            clear_extra_cells=True,
        )
    else:
        table_result = append_generated_table(
            package,
            rows,
            section_index=section_index,
            style_refs={
                "tableWidth": "47904",
                "rowHeight": "2400",
                "repeatHeader": "1",
                "cellMargin": {"left": "220", "right": "220", "top": "120", "bottom": "120"},
            },
        )
    package.write_package(output_path)
    validation = HwpxValidator.validate_hwpx(output_path)
    after_package = HwpxPackage(output_path)
    after_sections = inspect_sections(after_package)
    after_tables = find_tables(after_package)
    status = (
        "PASS"
        if validation.get("xml_ok") and table_result.get("status") in {"GENERATED_TABLE_APPEND_PASS", "CLONED_TABLE_APPEND_PASS"}
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
        "table_mode": table_mode,
        "section_result": section_result,
        "title_result": title_result,
        "table_result": table_result,
        "validation": validation,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--title", default="추가 점검표")
    parser.add_argument("--table-mode", choices=["generated", "clone-template"], default="generated")
    parser.add_argument("--source-table-index", type=int, default=0)
    parser.add_argument("--table-json", type=Path, help="Optional JSON list of table rows")
    parser.add_argument("--report-json", type=Path)
    args = parser.parse_args()

    report = append_page_table(
        args.input,
        args.output,
        args.title,
        load_rows(args.table_json),
        table_mode=args.table_mode,
        source_table_index=args.source_table_index,
    )
    if args.report_json:
        args.report_json.parent.mkdir(parents=True, exist_ok=True)
        args.report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
