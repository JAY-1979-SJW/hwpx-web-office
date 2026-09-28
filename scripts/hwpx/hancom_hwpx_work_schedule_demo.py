#!/usr/bin/env python3
"""Append monthly and daily work-schedule tables to an HWPX file."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from hancom_hwpx_table_integrity_audit import audit_tables
from hwpx_border_fill_style import apply_border_fill_definitions
from hwpx_element_factory import (
    create_table_paragraph,
    create_text_paragraph,
    infer_paragraph_defaults,
    next_paragraph_id,
)
from hwpx_package import HwpxPackage, HwpxValidator
from hwpx_section_ops import append_section, inspect_sections
from hwpx_special_text import sanitize_hwpx_text
from hwpx_table_ops import append_generated_table, find_tables
from hwpx_text_ops import append_generated_paragraph


@dataclass(frozen=True)
class WorkItem:
    name: str
    start: date
    end: date
    progress: int


DEFAULT_WORK_ITEMS = [
    WorkItem("착공 및 현장정리", date(2026, 5, 1), date(2026, 5, 5), 100),
    WorkItem("배관 공사", date(2026, 5, 6), date(2026, 5, 14), 85),
    WorkItem("배선 공사", date(2026, 5, 12), date(2026, 5, 22), 70),
    WorkItem("장비 설치", date(2026, 5, 20), date(2026, 5, 28), 40),
    WorkItem("시험 및 시운전", date(2026, 5, 27), date(2026, 5, 31), 10),
    WorkItem("준공 정리", date(2026, 6, 1), date(2026, 6, 5), 0),
]


WORK_COLORS = ["work_blue", "work_green", "work_teal", "work_yellow", "work_pink", "work_gray"]


def month_range(start: date, count: int) -> list[date]:
    months = []
    year = start.year
    month = start.month
    for _ in range(count):
        months.append(date(year, month, 1))
        month += 1
        if month > 12:
            year += 1
            month = 1
    return months


def parse_work_items(path: Path | None) -> list[WorkItem]:
    if path is None:
        return DEFAULT_WORK_ITEMS
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, list):
        raise ValueError("work-items-json must be a list")
    items: list[WorkItem] = []
    for index, row in enumerate(data, start=1):
        if not isinstance(row, dict):
            raise ValueError(f"work item #{index} must be an object")
        items.append(
            WorkItem(
                str(row["name"]),
                datetime.strptime(str(row["start"]), "%Y-%m-%d").date(),
                datetime.strptime(str(row["end"]), "%Y-%m-%d").date(),
                int(row.get("progress", 0)),
            )
        )
    return items


def overlaps(a_start: date, a_end: date, b_start: date, b_end: date) -> bool:
    return a_start <= b_end and b_start <= a_end


def month_end(month_start: date) -> date:
    if month_start.month == 12:
        return date(month_start.year + 1, 1, 1) - timedelta(days=1)
    return date(month_start.year, month_start.month + 1, 1) - timedelta(days=1)


def active_days(item: WorkItem, start: date, end: date) -> int:
    if not overlaps(item.start, item.end, start, end):
        return 0
    first = max(item.start, start)
    last = min(item.end, end)
    return (last - first).days + 1


def make_monthly_rows(
    items: list[WorkItem], first_month: date, month_count: int
) -> list[list[str]]:
    months = month_range(first_month, month_count)
    header = ["공종", "기간", *[f"{m.month}월" for m in months], "진척률"]
    rows = [header]
    for item in items:
        row = [item.name, f"{item.start:%m.%d}~{item.end:%m.%d}"]
        for month in months:
            days = active_days(item, month, month_end(month))
            row.append("■" * min(days, 12) if days else "·")
        row.append(f"{item.progress}%")
        rows.append(row)
    return rows


def make_daily_rows(items: list[WorkItem], start: date, day_count: int) -> list[list[str]]:
    days = [start + timedelta(days=i) for i in range(day_count)]
    rows = [["공종", *[str(day.day) for day in days]]]
    for item in items:
        row = [item.name]
        for day in days:
            row.append("■" if item.start <= day <= item.end else "·")
        rows.append(row)
    return rows


def sanitize_rows(rows: list[list[str]]) -> tuple[list[list[str]], list[dict[str, Any]]]:
    clean_rows: list[list[str]] = []
    warnings: list[dict[str, Any]] = []
    for row_index, row in enumerate(rows):
        clean_row = []
        for col_index, value in enumerate(row):
            sanitized = sanitize_hwpx_text(value)
            clean_row.append(sanitized["text"])
            if sanitized["changed"]:
                warnings.append({
                    "row": row_index,
                    "col": col_index,
                    "replacements": sanitized["replacements"],
                })
        clean_rows.append(clean_row)
    return clean_rows, warnings


def schedule_border_fill_definitions() -> dict[str, Any]:
    return {
        "border_fills": {
            "schedule_header": {
                "fill_color": "#1F4E79",
                "border_color": "#2F2F2F",
                "border_width": "0.12 mm",
            },
            "schedule_label": {
                "fill_color": "#D9EAF7",
                "border_color": "#7F8C8D",
                "border_width": "0.12 mm",
            },
            "schedule_body": {
                "fill_color": "#FFFFFF",
                "border_color": "#B7B7B7",
                "border_width": "0.12 mm",
            },
            "schedule_inactive": {
                "fill_color": "#F2F2F2",
                "border_color": "#D0D0D0",
                "border_width": "0.12 mm",
            },
            "schedule_progress": {
                "fill_color": "#E2F0D9",
                "border_color": "#70AD47",
                "border_width": "0.12 mm",
            },
            "work_blue": {
                "fill_color": "#BDD7EE",
                "border_color": "#5B9BD5",
                "border_width": "0.12 mm",
            },
            "work_green": {
                "fill_color": "#C6E0B4",
                "border_color": "#70AD47",
                "border_width": "0.12 mm",
            },
            "work_teal": {
                "fill_color": "#B7DEE8",
                "border_color": "#00A2A5",
                "border_width": "0.12 mm",
            },
            "work_yellow": {
                "fill_color": "#FFE699",
                "border_color": "#C9A227",
                "border_width": "0.12 mm",
            },
            "work_pink": {
                "fill_color": "#F4CCCC",
                "border_color": "#C0504D",
                "border_width": "0.12 mm",
            },
            "work_gray": {
                "fill_color": "#D9D9D9",
                "border_color": "#808080",
                "border_width": "0.12 mm",
            },
        }
    }


def schedule_cell_fill_map(
    rows: list[list[str]], border_fills: dict[str, str], *, kind: str
) -> dict[str, str]:
    cell_map: dict[str, str] = {}
    header = border_fills.get("schedule_header")
    label = border_fills.get("schedule_label")
    body = border_fills.get("schedule_body")
    inactive = border_fills.get("schedule_inactive")
    progress = border_fills.get("schedule_progress")
    for col in range(len(rows[0]) if rows else 0):
        if header:
            cell_map[f"0,{col}"] = header
    for row_index, row in enumerate(rows[1:], start=1):
        work_fill = border_fills.get(WORK_COLORS[(row_index - 1) % len(WORK_COLORS)])
        for col_index, value in enumerate(row):
            if col_index == 0 and label:
                cell_map[f"{row_index},{col_index}"] = label
            elif kind == "monthly" and col_index == len(row) - 1 and progress:
                cell_map[f"{row_index},{col_index}"] = progress
            elif value and value != "·" and "■" in value and work_fill:
                cell_map[f"{row_index},{col_index}"] = work_fill
            elif value == "·" and inactive:
                cell_map[f"{row_index},{col_index}"] = inactive
            elif body:
                cell_map[f"{row_index},{col_index}"] = body
    return cell_map


def resolve_schedule_style_maps(package: HwpxPackage) -> dict[str, Any]:
    result = apply_border_fill_definitions(package, schedule_border_fill_definitions())
    return {"border_fills": result.get("border_fills", {}), "report": result}


def monthly_style(
    col_count: int,
    row_count: int,
    border_fills: dict[str, str] | None = None,
    rows: list[list[str]] | None = None,
) -> dict[str, Any]:
    month_cols = max(col_count - 3, 1)
    month_width = max((47904 - 14000 - 9000 - 5500) // month_cols, 3000)
    border_fills = border_fills or {}
    rows = rows or []
    return {
        "tableWidth": "47904",
        "columnWidths": [14000, 9000, *([month_width] * month_cols), 5500],
        "rowHeights": [2200] + [2500] * max(row_count - 1, 0),
        "repeatHeader": "1",
        "cellMargin": {"left": "180", "right": "180", "top": "120", "bottom": "120"},
        "cellVertAlign": "CENTER",
        "cellLineWrap": "BREAK",
        "headerBorderFillIDRef": border_fills.get("schedule_header", ""),
        "bodyBorderFillIDRef": border_fills.get("schedule_body", ""),
        "cellBorderFillIDRefMap": schedule_cell_fill_map(rows, border_fills, kind="monthly")
        if rows
        else {},
    }


def daily_style(
    col_count: int,
    row_count: int,
    border_fills: dict[str, str] | None = None,
    rows: list[list[str]] | None = None,
) -> dict[str, Any]:
    day_width = max((47904 - 9000) // max(col_count - 1, 1), 900)
    border_fills = border_fills or {}
    rows = rows or []
    return {
        "tableWidth": "47904",
        "columnWidths": [9000, *([day_width] * max(col_count - 1, 0))],
        "rowHeights": [1900] + [2200] * max(row_count - 1, 0),
        "repeatHeader": "1",
        "cellMargin": {"left": "70", "right": "70", "top": "100", "bottom": "100"},
        "cellVertAlign": "CENTER",
        "cellLineWrap": "BREAK",
        "headerBorderFillIDRef": border_fills.get("schedule_header", ""),
        "bodyBorderFillIDRef": border_fills.get("schedule_body", ""),
        "cellBorderFillIDRefMap": schedule_cell_fill_map(rows, border_fills, kind="daily")
        if rows
        else {},
    }


@dataclass(frozen=True)
class ScheduleTables:
    title: str
    monthly_rows: list[list[str]]
    daily_rows: list[list[str]]
    daily_start: date
    daily_days: int


def insert_schedule_at_section_start(
    package: HwpxPackage,
    section_index: int,
    content: ScheduleTables,
    border_fills: dict[str, str] | None = None,
) -> dict[str, Any]:
    title = content.title
    monthly_rows = content.monthly_rows
    daily_rows = content.daily_rows
    daily_start = content.daily_start
    daily_days = content.daily_days
    sections = package.section_entries()
    if section_index < 0 or section_index >= len(sections):
        return {
            "status": "SECTION_NOT_FOUND",
            "section_index": section_index,
            "section_count": len(sections),
        }
    entry = sections[section_index]
    root = package.read_xml(entry)
    defaults = infer_paragraph_defaults(root)
    next_id = int(next_paragraph_id(root))
    elements = [
        create_text_paragraph(title, str(next_id), defaults),
        create_text_paragraph("월별 공종표", str(next_id + 1), defaults),
        create_table_paragraph(
            monthly_rows,
            str(next_id + 2),
            {
                **defaults,
                **monthly_style(
                    len(monthly_rows[0]), len(monthly_rows), border_fills, monthly_rows
                ),
            },
        ),
        create_text_paragraph(
            f"일별 공종표({daily_start:%Y.%m.%d}~{daily_start + timedelta(days=daily_days - 1):%Y.%m.%d})",
            str(next_id + 3),
            defaults,
        ),
        create_table_paragraph(
            daily_rows,
            str(next_id + 4),
            {
                **defaults,
                **daily_style(len(daily_rows[0]), len(daily_rows), border_fills, daily_rows),
            },
        ),
    ]
    for offset, element in enumerate(elements):
        root.insert(offset, element)
    package.write_xml(entry, root)
    return {
        "status": "SCHEDULE_INSERT_AT_START_PASS",
        "entry": entry,
        "section_index": section_index,
        "title_result": {
            "status": "GENERATED_PARAGRAPH_INSERT_PASS",
            "entry": entry,
            "section_index": section_index,
            "paragraph_id": str(next_id),
        },
        "monthly_title_result": {
            "status": "GENERATED_PARAGRAPH_INSERT_PASS",
            "entry": entry,
            "section_index": section_index,
            "paragraph_id": str(next_id + 1),
        },
        "monthly_table_result": {
            "status": "GENERATED_TABLE_APPEND_PASS",
            "entry": entry,
            "section_index": section_index,
            "paragraph_id": str(next_id + 2),
            "row_count": len(monthly_rows),
            "col_count": max(len(row) for row in monthly_rows),
        },
        "daily_title_result": {
            "status": "GENERATED_PARAGRAPH_INSERT_PASS",
            "entry": entry,
            "section_index": section_index,
            "paragraph_id": str(next_id + 3),
        },
        "daily_table_result": {
            "status": "GENERATED_TABLE_APPEND_PASS",
            "entry": entry,
            "section_index": section_index,
            "paragraph_id": str(next_id + 4),
            "row_count": len(daily_rows),
            "col_count": max(len(row) for row in daily_rows),
        },
    }


def append_work_schedule(  # ruff: ignore[too-many-arguments] - 외부 호출부 다수(hwpx_server_ops.py, 테스트) 시그니처 변경 보류
    input_path: Path,
    output_path: Path,
    *,
    work_items: list[WorkItem],
    daily_start: date,
    daily_days: int,
    month_count: int,
    title: str,
    append_to_existing_section: bool = False,
    insert_at_start: bool = False,
) -> dict[str, Any]:
    package = HwpxPackage(input_path)
    before_sections = inspect_sections(package)
    before_tables = find_tables(package)
    style_maps = resolve_schedule_style_maps(package)
    if append_to_existing_section:
        section_index = 0
        section_result = {
            "status": "EXISTING_SECTION_APPEND",
            "entry": package.section_entries()[section_index],
            "section_index": section_index,
        }
    else:
        section_result = append_section(package, clone_from_index=0, clear_body=True)
        if section_result.get("status") != "SECTION_APPEND_PASS":
            return {
                "status": "FAIL",
                "section_result": section_result,
                "input": str(input_path),
                "output": str(output_path),
            }
        section_index = int(section_result["section_count_after"]) - 1

    monthly_rows, monthly_warnings = sanitize_rows(
        make_monthly_rows(work_items, date(daily_start.year, daily_start.month, 1), month_count)
    )
    daily_rows, daily_warnings = sanitize_rows(make_daily_rows(work_items, daily_start, daily_days))
    if insert_at_start:
        insert_result = insert_schedule_at_section_start(
            package,
            section_index,
            ScheduleTables(title, monthly_rows, daily_rows, daily_start, daily_days),
            style_maps["border_fills"],
        )
        title_result = insert_result["title_result"]
        monthly_title = insert_result["monthly_title_result"]
        monthly_result = insert_result["monthly_table_result"]
        daily_title = insert_result["daily_title_result"]
        daily_result = insert_result["daily_table_result"]
    else:
        title_result = append_generated_paragraph(package, title, section_index=section_index)
        monthly_title = append_generated_paragraph(
            package, "월별 공종표", section_index=section_index
        )
        monthly_result = append_generated_table(
            package,
            monthly_rows,
            section_index=section_index,
            style_refs=monthly_style(
                len(monthly_rows[0]), len(monthly_rows), style_maps["border_fills"], monthly_rows
            ),
        )
        daily_title = append_generated_paragraph(
            package,
            f"일별 공종표({daily_start:%Y.%m.%d}~{daily_start + timedelta(days=daily_days - 1):%Y.%m.%d})",
            section_index=section_index,
        )
        daily_result = append_generated_table(
            package,
            daily_rows,
            section_index=section_index,
            style_refs=daily_style(
                len(daily_rows[0]), len(daily_rows), style_maps["border_fills"], daily_rows
            ),
        )

    package.write_package(output_path)
    validation = HwpxValidator.validate_hwpx(output_path)
    integrity = audit_tables(output_path)
    after_package = HwpxPackage(output_path)
    after_sections = inspect_sections(after_package)
    after_tables = find_tables(after_package)
    status = (
        "PASS"
        if validation.get("xml_ok")
        and monthly_result.get("status") == "GENERATED_TABLE_APPEND_PASS"
        and daily_result.get("status") == "GENERATED_TABLE_APPEND_PASS"
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
        "work_item_count": len(work_items),
        "style_result": style_maps["report"],
        "sanitize_warnings": monthly_warnings + daily_warnings,
        "section_result": section_result,
        "insert_at_start": insert_at_start,
        "title_result": title_result,
        "monthly_title_result": monthly_title,
        "monthly_table_result": monthly_result,
        "daily_title_result": daily_title,
        "daily_table_result": daily_result,
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
    parser.add_argument("--work-items-json", type=Path)
    parser.add_argument("--daily-start", default="2026-05-01")
    parser.add_argument("--daily-days", type=int, default=31)
    parser.add_argument("--month-count", type=int, default=3)
    parser.add_argument("--title", default="공종별 월별/일별 공정표")
    parser.add_argument("--append-to-existing-section", action="store_true")
    parser.add_argument("--insert-at-start", action="store_true")
    parser.add_argument("--report-json", type=Path)
    args = parser.parse_args()

    report = append_work_schedule(
        args.input,
        args.output,
        work_items=parse_work_items(args.work_items_json),
        daily_start=datetime.strptime(args.daily_start, "%Y-%m-%d").date(),
        daily_days=args.daily_days,
        month_count=args.month_count,
        title=args.title,
        append_to_existing_section=args.append_to_existing_section,
        insert_at_start=args.insert_at_start,
    )
    if args.report_json:
        args.report_json.parent.mkdir(parents=True, exist_ok=True)
        args.report_json.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
