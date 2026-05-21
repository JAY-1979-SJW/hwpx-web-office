"""Schedule diagram data model and HWPX table renderers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
import json
from pathlib import Path
from typing import Any

from hwpx_border_fill_style import apply_border_fill_definitions
from hwpx_element_factory import create_table_paragraph, create_text_paragraph, infer_paragraph_defaults, next_paragraph_id
from hwpx_header_style import apply_header_style_definitions
from hwpx_package import HwpxPackage
from hwpx_special_text import sanitize_hwpx_text


WORK_FILL_NAMES = ["work_blue", "work_green", "work_teal", "work_yellow", "work_pink", "work_gray"]
WORK_MARK = ""
INACTIVE_MARK = " "


@dataclass(frozen=True)
class ScheduleItem:
    name: str
    start: date
    end: date
    progress: int
    group: str = "공통"
    owner: str = ""

    @property
    def duration_days(self) -> int:
        return max((self.end - self.start).days + 1, 1)


DEFAULT_SCHEDULE_ITEMS = [
    ScheduleItem("착공 및 현장정리", date(2026, 5, 1), date(2026, 5, 5), 100, "준비", "시공사"),
    ScheduleItem("배관 공사", date(2026, 5, 6), date(2026, 5, 14), 85, "시공", "설비팀"),
    ScheduleItem("배선 공사", date(2026, 5, 12), date(2026, 5, 22), 70, "시공", "전기팀"),
    ScheduleItem("장비 설치", date(2026, 5, 20), date(2026, 5, 28), 40, "설치", "장비팀"),
    ScheduleItem("시험 및 시운전", date(2026, 5, 27), date(2026, 5, 31), 10, "검사", "감리"),
    ScheduleItem("준공 정리", date(2026, 6, 1), date(2026, 6, 5), 0, "준공", "감리"),
]


def parse_schedule_items(path: Path | None) -> list[ScheduleItem]:
    if path is None:
        return DEFAULT_SCHEDULE_ITEMS
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(data, list):
        raise ValueError("schedule item JSON must be a list")
    items: list[ScheduleItem] = []
    for index, row in enumerate(data, start=1):
        if not isinstance(row, dict):
            raise ValueError(f"schedule item #{index} must be an object")
        items.append(
            ScheduleItem(
                name=str(row["name"]),
                start=datetime.strptime(str(row["start"]), "%Y-%m-%d").date(),
                end=datetime.strptime(str(row["end"]), "%Y-%m-%d").date(),
                progress=max(0, min(100, int(row.get("progress", 0)))),
                group=str(row.get("group", "공통")),
                owner=str(row.get("owner", "")),
            )
        )
    return items


def sanitize_rows(rows: list[list[str]]) -> tuple[list[list[str]], list[dict[str, Any]]]:
    clean_rows: list[list[str]] = []
    warnings: list[dict[str, Any]] = []
    for row_index, row in enumerate(rows):
        clean_row = []
        for col_index, value in enumerate(row):
            sanitized = sanitize_hwpx_text(value)
            clean_row.append(sanitized["text"])
            if sanitized["changed"]:
                warnings.append({"row": row_index, "col": col_index, "replacements": sanitized["replacements"]})
        clean_rows.append(clean_row)
    return clean_rows, warnings


def month_starts(first_month: date, count: int) -> list[date]:
    result = []
    year = first_month.year
    month = first_month.month
    for _ in range(count):
        result.append(date(year, month, 1))
        month += 1
        if month > 12:
            year += 1
            month = 1
    return result


def month_end(month_start: date) -> date:
    if month_start.month == 12:
        return date(month_start.year + 1, 1, 1) - timedelta(days=1)
    return date(month_start.year, month_start.month + 1, 1) - timedelta(days=1)


def active_days(item: ScheduleItem, start: date, end: date) -> int:
    first = max(item.start, start)
    last = min(item.end, end)
    return max((last - first).days + 1, 0) if first <= last else 0


def monthly_schedule_rows(items: list[ScheduleItem], first_month: date, month_count: int) -> list[list[str]]:
    months = month_starts(first_month, month_count)
    rows = [["공종", "기간", *[f"{month.month}월" for month in months], "진척률"]]
    for item in items:
        row = [item.name, f"{item.start:%m.%d}~{item.end:%m.%d}"]
        for month in months:
            days = active_days(item, month, month_end(month))
            row.append(WORK_MARK if days else INACTIVE_MARK)
        row.append(f"{item.progress}%")
        rows.append(row)
    return rows


def daily_schedule_rows(items: list[ScheduleItem], start: date, day_count: int) -> list[list[str]]:
    days = [start + timedelta(days=index) for index in range(day_count)]
    rows = [["공종", *[str(day.day) for day in days]]]
    for item in items:
        rows.append([item.name, *[WORK_MARK if item.start <= day <= item.end else INACTIVE_MARK for day in days]])
    return rows


def horizontal_bar_rows(items: list[ScheduleItem], segments: int = 10) -> list[list[str]]:
    segment_headers = ["수평 막대", *[str(index * 10) for index in range(2, segments + 1)]]
    rows = [["공종", "기간", *segment_headers, "진척률"]]
    for item in items:
        filled = round(segments * item.progress / 100)
        rows.append([item.name, f"{item.start:%m.%d}~{item.end:%m.%d}", *[WORK_MARK if index < filled else INACTIVE_MARK for index in range(segments)], f"{item.progress}%"])
    return rows


def vertical_bar_rows(items: list[ScheduleItem], levels: int = 10) -> list[list[str]]:
    short_names = [item.name[:5] for item in items]
    rows = [["수준", *short_names]]
    for level in range(levels, 0, -1):
        threshold = level * 100 // levels
        rows.append([f"{threshold}%", *[WORK_MARK if item.progress >= threshold else INACTIVE_MARK for item in items]])
    rows.append(["진척률", *[f"{item.progress}%" for item in items]])
    return rows


def summary_rows(items: list[ScheduleItem]) -> list[list[str]]:
    total = len(items)
    done = sum(1 for item in items if item.progress >= 100)
    running = sum(1 for item in items if 0 < item.progress < 100)
    pending = sum(1 for item in items if item.progress == 0)
    average = round(sum(item.progress for item in items) / total) if total else 0
    start = min((item.start for item in items), default=date.today())
    end = max((item.end for item in items), default=date.today())
    return [
        ["구분", "값", "비고"],
        ["전체 공종", str(total), f"{start:%Y.%m.%d}~{end:%Y.%m.%d}"],
        ["완료", str(done), "진척률 100%"],
        ["진행", str(running), "0% 초과 100% 미만"],
        ["대기", str(pending), "진척률 0%"],
        ["평균 진척률", f"{average}%", "단순 평균"],
    ]


def legend_rows(items: list[ScheduleItem]) -> list[list[str]]:
    rows = [["표시", "의미", "적용"]]
    rows.append(["", "색상 채움", "작업/진행 구간"])
    rows.append(["", "연한 회색", "비작업/미진행 구간"])
    for index, item in enumerate(items):
        rows.append(["", item.name, f"{item.group} / {item.owner}".strip(" /")])
    return rows


def schedule_style_definitions() -> dict[str, Any]:
    return {
        "border_fills": {
            "schedule_header": {"fill_color": "#1F4E79", "border_color": "#2F2F2F", "border_width": "0.12 mm"},
            "schedule_label": {"fill_color": "#D9EAF7", "border_color": "#7F8C8D", "border_width": "0.12 mm"},
            "schedule_body": {"fill_color": "#FFFFFF", "border_color": "#B7B7B7", "border_width": "0.12 mm"},
            "schedule_inactive": {"fill_color": "#F2F2F2", "border_color": "#D0D0D0", "border_width": "0.12 mm"},
            "schedule_progress": {"fill_color": "#E2F0D9", "border_color": "#70AD47", "border_width": "0.12 mm"},
            "work_blue": {"fill_color": "#BDD7EE", "border_color": "#5B9BD5", "border_width": "0.12 mm"},
            "work_green": {"fill_color": "#C6E0B4", "border_color": "#70AD47", "border_width": "0.12 mm"},
            "work_teal": {"fill_color": "#B7DEE8", "border_color": "#00A2A5", "border_width": "0.12 mm"},
            "work_yellow": {"fill_color": "#FFE699", "border_color": "#C9A227", "border_width": "0.12 mm"},
            "work_pink": {"fill_color": "#F4CCCC", "border_color": "#C0504D", "border_width": "0.12 mm"},
            "work_gray": {"fill_color": "#D9D9D9", "border_color": "#808080", "border_width": "0.12 mm"},
        }
    }


def schedule_text_style_definitions() -> dict[str, Any]:
    return {
        "char_styles": {
            "schedule_title": {"height": 1200, "text_color": "#1F1F1F", "bold": True},
            "schedule_header_text": {"height": 780, "text_color": "#FFFFFF", "bold": True},
            "schedule_body_text": {"height": 760, "text_color": "#1F1F1F"},
            "schedule_small_text": {"height": 620, "text_color": "#1F1F1F"},
            "schedule_tiny_text": {"height": 520, "text_color": "#1F1F1F"},
            "schedule_percent_text": {"height": 720, "text_color": "#1F1F1F", "bold": True},
        },
        "para_styles": {
            "schedule_center": {"align": "CENTER", "line_spacing": 110},
            "schedule_left": {"align": "LEFT", "line_spacing": 110},
        },
    }


def ensure_schedule_styles(package: HwpxPackage) -> dict[str, Any]:
    fill_result = apply_border_fill_definitions(package, schedule_style_definitions())
    text_result = apply_header_style_definitions(package, schedule_text_style_definitions())
    status = "PASS" if fill_result.get("status") == "PASS" and text_result.get("status") in {"PASS", "HEADER_NOT_FOUND"} else "WARN"
    return {
        "status": status,
        "border_fills": fill_result.get("border_fills", {}),
        "char_styles": text_result.get("char_styles", {}),
        "para_styles": text_result.get("para_styles", {}),
        "report": {"border_fill_result": fill_result, "text_style_result": text_result, "status": status},
    }


def is_work_cell(mode: str, row_index: int, col_index: int, row: list[str]) -> bool:
    if row_index == 0:
        return False
    if mode == "monthly":
        return 2 <= col_index < len(row) - 1 and row[col_index] == WORK_MARK
    if mode == "daily":
        return col_index > 0 and row[col_index] == WORK_MARK
    if mode == "horizontal":
        return 2 <= col_index < len(row) - 1 and row[col_index] == WORK_MARK
    if mode == "vertical":
        return 0 < col_index < len(row) and row[0] != "진척률" and row[col_index] == WORK_MARK
    return False


def is_inactive_cell(mode: str, row_index: int, col_index: int, row: list[str]) -> bool:
    if row_index == 0:
        return False
    if mode == "monthly":
        return 2 <= col_index < len(row) - 1 and row[col_index] == INACTIVE_MARK
    if mode == "daily":
        return col_index > 0 and row[col_index] == INACTIVE_MARK
    if mode == "horizontal":
        return 2 <= col_index < len(row) - 1 and row[col_index] == INACTIVE_MARK
    if mode == "vertical":
        return 0 < col_index < len(row) and row[0] != "진척률" and row[col_index] == INACTIVE_MARK
    return False


def fill_map(rows: list[list[str]], border_fills: dict[str, str], *, mode: str) -> dict[str, str]:
    mapping: dict[str, str] = {}
    if not rows:
        return mapping
    for col in range(len(rows[0])):
        if border_fills.get("schedule_header"):
            mapping[f"0,{col}"] = border_fills["schedule_header"]
    for row_index, row in enumerate(rows[1:], start=1):
        work_fill = border_fills.get(WORK_FILL_NAMES[(row_index - 1) % len(WORK_FILL_NAMES)])
        for col_index, value in enumerate(row):
            if col_index == 0 and border_fills.get("schedule_label"):
                mapping[f"{row_index},{col_index}"] = border_fills["schedule_label"]
            elif mode in {"monthly", "horizontal", "summary"} and col_index == len(row) - 1 and border_fills.get("schedule_progress"):
                mapping[f"{row_index},{col_index}"] = border_fills["schedule_progress"]
            elif mode == "legend" and col_index == 0 and work_fill:
                mapping[f"{row_index},{col_index}"] = work_fill
            elif is_work_cell(mode, row_index, col_index, row) and work_fill:
                mapping[f"{row_index},{col_index}"] = work_fill
            elif is_inactive_cell(mode, row_index, col_index, row) and border_fills.get("schedule_inactive"):
                mapping[f"{row_index},{col_index}"] = border_fills["schedule_inactive"]
            elif border_fills.get("schedule_body"):
                mapping[f"{row_index},{col_index}"] = border_fills["schedule_body"]
    return mapping


def visual_text_len(value: str) -> int:
    return sum(2 if ord(ch) > 127 else 1 for ch in value)


def fitted_char_style_name(value: str, width: int, *, header: bool = False, progress: bool = False) -> str:
    if header:
        return "schedule_header_text"
    if progress:
        return "schedule_percent_text"
    length = visual_text_len(value)
    if width <= 1200 or length > 22:
        return "schedule_tiny_text"
    if width <= 3200 or length > 14:
        return "schedule_small_text"
    return "schedule_body_text"


def cell_text_style_maps(rows: list[list[str]], widths: list[int], char_styles: dict[str, str], para_styles: dict[str, str], *, mode: str) -> tuple[dict[str, str], dict[str, str]]:
    char_map: dict[str, str] = {}
    para_map: dict[str, str] = {}
    center_para = para_styles.get("schedule_center")
    left_para = para_styles.get("schedule_left", center_para)
    for row_index, row in enumerate(rows):
        for col_index, value in enumerate(row):
            width = widths[min(col_index, len(widths) - 1)] if widths else 6000
            is_progress = row_index > 0 and mode in {"monthly", "horizontal", "summary"} and col_index == len(row) - 1
            char_name = fitted_char_style_name(value, width, header=row_index == 0, progress=is_progress)
            if char_styles.get(char_name):
                char_map[f"{row_index},{col_index}"] = char_styles[char_name]
            para_id = left_para if col_index == 0 and row_index > 0 else center_para
            if para_id:
                para_map[f"{row_index},{col_index}"] = para_id
    return char_map, para_map


def table_style(rows: list[list[str]], border_fills: dict[str, str], *, mode: str, char_styles: dict[str, str] | None = None, para_styles: dict[str, str] | None = None) -> dict[str, Any]:
    char_styles = char_styles or {}
    para_styles = para_styles or {}
    col_count = max((len(row) for row in rows), default=1)
    if mode == "daily":
        widths = [9000, *([max((47904 - 9000) // max(col_count - 1, 1), 850)] * max(col_count - 1, 0))]
        heights = [1800] + [2100] * max(len(rows) - 1, 0)
    elif mode == "vertical":
        widths = [6500, *([max((47904 - 6500) // max(col_count - 1, 1), 4200)] * max(col_count - 1, 0))]
        heights = [1800] + [1700] * max(len(rows) - 1, 0)
    elif mode == "horizontal":
        segment_cols = max(col_count - 3, 1)
        segment_width = max((47904 - 12000 - 8000 - 5000) // segment_cols, 1500)
        widths = [12000, 8000, *([segment_width] * segment_cols), 5000]
        heights = [1900] + [2200] * max(len(rows) - 1, 0)
    elif mode == "summary":
        widths = [12000, 9000, 26904]
        heights = [2000] + [2200] * max(len(rows) - 1, 0)
    elif mode == "legend":
        widths = [7000, 17000, 23904]
        heights = [2000] + [2100] * max(len(rows) - 1, 0)
    else:
        month_cols = max(col_count - 3, 1)
        widths = [14000, 9000, *([max((47904 - 14000 - 9000 - 5500) // month_cols, 3000)] * month_cols), 5500]
        heights = [2000] + [2300] * max(len(rows) - 1, 0)
    char_map, para_map = cell_text_style_maps(rows, widths[:col_count], char_styles, para_styles, mode=mode)
    return {
        "tableWidth": "47904",
        "columnWidths": widths[:col_count],
        "rowHeights": heights,
        "repeatHeader": "1",
        "cellMargin": {"left": "120", "right": "120", "top": "100", "bottom": "100"},
        "cellVertAlign": "CENTER",
        "cellLineWrap": "BREAK",
        "headerBorderFillIDRef": border_fills.get("schedule_header", ""),
        "bodyBorderFillIDRef": border_fills.get("schedule_body", ""),
        "cellBorderFillIDRefMap": fill_map(rows, border_fills, mode=mode),
        "cellCharPrIDRefMap": char_map,
        "cellParaPrIDRefMap": para_map,
    }


def diagram_tables(items: list[ScheduleItem], daily_start: date, daily_days: int, month_count: int) -> list[dict[str, Any]]:
    first_month = date(daily_start.year, daily_start.month, 1)
    return [
        {"title": "월별 공종표", "mode": "monthly", "rows": monthly_schedule_rows(items, first_month, month_count)},
        {"title": f"일별 공종표({daily_start:%Y.%m.%d}~{daily_start + timedelta(days=daily_days - 1):%Y.%m.%d})", "mode": "daily", "rows": daily_schedule_rows(items, daily_start, daily_days)},
        {"title": "수평 막대 그래프", "mode": "horizontal", "rows": horizontal_bar_rows(items)},
        {"title": "수직 막대 그래프", "mode": "vertical", "rows": vertical_bar_rows(items)},
        {"title": "진척률 요약표", "mode": "summary", "rows": summary_rows(items)},
        {"title": "범례표", "mode": "legend", "rows": legend_rows(items)},
    ]


def insert_schedule_diagram_tables(
    package: HwpxPackage,
    items: list[ScheduleItem],
    *,
    section_index: int = 0,
    insert_at_start: bool = True,
    daily_start: date,
    daily_days: int = 31,
    month_count: int = 3,
    title: str = "공정표 및 그래프 도식",
) -> dict[str, Any]:
    sections = package.section_entries()
    if section_index < 0 or section_index >= len(sections):
        return {"status": "SECTION_NOT_FOUND", "section_index": section_index, "section_count": len(sections)}
    style_result = ensure_schedule_styles(package)
    border_fills = style_result["border_fills"]
    char_styles = style_result.get("char_styles", {})
    para_styles = style_result.get("para_styles", {})
    entry = sections[section_index]
    root = package.read_xml(entry)
    defaults = infer_paragraph_defaults(root)
    next_id = int(next_paragraph_id(root))
    elements = [create_text_paragraph(title, str(next_id), defaults)]
    table_reports = []
    warnings = []
    paragraph_id = next_id + 1
    for diagram in diagram_tables(items, daily_start, daily_days, month_count):
        rows, row_warnings = sanitize_rows(diagram["rows"])
        warnings.extend(row_warnings)
        elements.append(create_text_paragraph(str(diagram["title"]), str(paragraph_id), defaults))
        paragraph_id += 1
        style = table_style(rows, border_fills, mode=str(diagram["mode"]), char_styles=char_styles, para_styles=para_styles)
        elements.append(create_table_paragraph(rows, str(paragraph_id), {**defaults, **style}))
        table_reports.append(
            {
                "title": diagram["title"],
                "mode": diagram["mode"],
                "paragraph_id": str(paragraph_id),
                "row_count": len(rows),
                "col_count": max(len(row) for row in rows),
            }
        )
        paragraph_id += 1
    if insert_at_start:
        for offset, element in enumerate(elements):
            root.insert(offset, element)
    else:
        for element in elements:
            root.append(element)
    package.write_xml(entry, root)
    return {
        "status": "SCHEDULE_DIAGRAM_TABLES_INSERT_PASS",
        "entry": entry,
        "section_index": section_index,
        "insert_at_start": insert_at_start,
        "style_result": style_result["report"],
        "diagram_count": len(table_reports),
        "table_reports": table_reports,
        "sanitize_warnings": warnings,
    }


__all__ = [
    "ScheduleItem",
    "DEFAULT_SCHEDULE_ITEMS",
    "parse_schedule_items",
    "insert_schedule_diagram_tables",
    "diagram_tables",
]
