"""Cell layout mutation operations for existing HWPX tables."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any, NamedTuple

from hwpx_package import HwpxPackage, local_name
from hwpx_table_cell_layout_style import (
    LINE_WRAP_VALUES,
    MARGIN_FIELDS,
    TEXT_DIRECTION_VALUES,
    VERT_ALIGN_VALUES,
)


def _table_elements(package: HwpxPackage) -> list[tuple[str, ET.Element, ET.Element]]:
    tables = []
    for entry in package.section_entries():
        try:
            root = package.read_xml(entry)
        except (KeyError, ET.ParseError, OSError):
            continue
        for elem in root.iter():
            name = local_name(elem.tag).lower()
            if name in {"tbl", "table"} or "tbl" in name or "table" in name:
                tables.append((entry, root, elem))
    return tables


def _find_table(
    package: HwpxPackage, table_index: int
) -> tuple[str, ET.Element, ET.Element] | None:
    tables = _table_elements(package)
    if table_index < 0 or table_index >= len(tables):
        return None
    return tables[table_index]


def _rows(table: ET.Element) -> list[ET.Element]:
    return [
        elem
        for elem in table.iter()
        if local_name(elem.tag).lower() in {"tr", "row"}
        or local_name(elem.tag).lower().endswith("tr")
    ]


def _cells(row: ET.Element) -> list[ET.Element]:
    return [
        elem
        for elem in list(row)
        if local_name(elem.tag).lower() in {"tc", "cell"}
        or local_name(elem.tag).lower().endswith("tc")
    ]


def _child(elem: ET.Element, name: str) -> ET.Element | None:
    for item in list(elem):
        if local_name(item.tag) == name:
            return item
    return None


def _cell_by_addr(rows: list[ET.Element], row_index: int, col_index: int) -> ET.Element | None:
    if row_index < 0 or row_index >= len(rows):
        return None
    saw_addr = False
    for cell in _cells(rows[row_index]):
        addr = _child(cell, "cellAddr")
        if addr is None:
            continue
        saw_addr = True
        if addr.attrib.get("rowAddr") == str(row_index) and addr.attrib.get("colAddr") == str(
            col_index
        ):
            return cell
    if saw_addr:
        return None
    row_cells = _cells(rows[row_index])
    return row_cells[col_index] if 0 <= col_index < len(row_cells) else None


def _enum(value: Any, allowed: set[str]) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().upper()
    return normalized if normalized in allowed else None


def _margin(value: Any) -> dict[str, str] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        return None
    result = {}
    for field in MARGIN_FIELDS:
        if field not in value:
            continue
        try:
            number = int(value[field])
        except (TypeError, ValueError):
            return None
        if number < 0:
            return None
        result[field] = str(number)
    return result or None


class _SublistEnumField(NamedTuple):
    keys: tuple[str, ...]
    enum_values: Any
    attrib_name: str
    warn_type: str


def _apply_sublist_enum_field(
    sublist: ET.Element,
    layout: dict[str, Any],
    field: _SublistEnumField,
    applied: dict[str, Any],
    warnings: list[dict[str, Any]],
) -> None:
    raw = None
    for key in field.keys:
        if key in layout:
            raw = layout[key]
            break
    value = _enum(raw, field.enum_values)
    if value:
        sublist.attrib[field.attrib_name] = value
        applied[field.attrib_name] = value
    elif any(key in layout for key in field.keys):
        warnings.append({"type": field.warn_type, "value": layout})


def set_cell_layout(
    package: HwpxPackage,
    table_index: int,
    row_index: int,
    col_index: int,
    layout: dict[str, Any],
) -> dict[str, Any]:
    found = _find_table(package, table_index)
    if not found:
        return {"status": "TABLE_NOT_FOUND", "table_index": table_index}
    entry, root, table = found
    rows = _rows(table)
    cell = _cell_by_addr(rows, row_index, col_index)
    if cell is None:
        return {
            "status": "CELL_NOT_FOUND",
            "table_index": table_index,
            "row_index": row_index,
            "col_index": col_index,
        }
    sublist = _child(cell, "subList")
    margin = _child(cell, "cellMargin")
    if sublist is None:
        return {
            "status": "CELL_SUBLIST_NOT_FOUND",
            "table_index": table_index,
            "row_index": row_index,
            "col_index": col_index,
        }

    applied: dict[str, Any] = {}
    warnings: list[dict[str, Any]] = []
    _apply_sublist_enum_field(
        sublist,
        layout,
        _SublistEnumField(
            ("cell_vertical_align", "vertical_align", "vert_align"),
            VERT_ALIGN_VALUES,
            "vertAlign",
            "VERT_ALIGN_INVALID",
        ),
        applied,
        warnings,
    )
    _apply_sublist_enum_field(
        sublist,
        layout,
        _SublistEnumField(
            ("cell_text_direction", "text_direction"),
            TEXT_DIRECTION_VALUES,
            "textDirection",
            "TEXT_DIRECTION_INVALID",
        ),
        applied,
        warnings,
    )
    _apply_sublist_enum_field(
        sublist,
        layout,
        _SublistEnumField(
            ("cell_line_wrap", "line_wrap"),
            LINE_WRAP_VALUES,
            "lineWrap",
            "LINE_WRAP_INVALID",
        ),
        applied,
        warnings,
    )

    cell_margin = _margin(layout.get("cell_margin"))
    if cell_margin and margin is not None:
        margin.attrib.update(cell_margin)
        applied["cellMargin"] = cell_margin
    elif "cell_margin" in layout and margin is None:
        warnings.append({"type": "CELL_MARGIN_NOT_FOUND"})
    elif "cell_margin" in layout and cell_margin is None:
        warnings.append({"type": "CELL_MARGIN_INVALID"})

    package.write_xml(entry, root)
    return {
        "status": "SET_CELL_LAYOUT_PASS" if applied else "SET_CELL_LAYOUT_NOOP",
        "table_index": table_index,
        "entry": entry,
        "cell": {"row": row_index, "col": col_index},
        "applied": applied,
        "warnings": warnings,
    }


__all__ = ["set_cell_layout"]
