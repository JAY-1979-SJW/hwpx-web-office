"""Merged-cell mutation operations for existing HWPX tables."""

from __future__ import annotations

import copy
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any, NamedTuple

from hwpx_package import HwpxPackage, local_name, text_nodes


def _table_elements(package: HwpxPackage) -> list[tuple[str, ET.Element, ET.Element]]:
    tables = []
    for entry in package.section_entries():
        try:
            root = package.read_xml(entry)
        except Exception:  # ruff: ignore[blind-except] -- 이 section만 건너뛰고 계속
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


def _row_elements(table: ET.Element) -> list[ET.Element]:
    return [
        elem
        for elem in table.iter()
        if local_name(elem.tag).lower() in {"tr", "row"}
        or local_name(elem.tag).lower().endswith("tr")
    ]


def _cell_elements(row: ET.Element) -> list[ET.Element]:
    return [
        elem
        for elem in list(row)
        if local_name(elem.tag).lower() in {"tc", "cell"}
        or local_name(elem.tag).lower().endswith("tc")
    ]


def _child_by_name(elem: ET.Element, name: str) -> ET.Element | None:
    for child in list(elem):
        if local_name(child.tag) == name:
            return child
    return None


def _cell_by_addr(rows: list[ET.Element], row_index: int, col_index: int) -> ET.Element | None:
    if row_index < 0 or row_index >= len(rows):
        return None
    saw_addr = False
    for cell in _cell_elements(rows[row_index]):
        addr = _child_by_name(cell, "cellAddr")
        if addr is None:
            continue
        saw_addr = True
        if addr.attrib.get("rowAddr") == str(row_index) and addr.attrib.get("colAddr") == str(
            col_index
        ):
            return cell
    if saw_addr:
        return None
    cells = _cell_elements(rows[row_index])
    return cells[col_index] if 0 <= col_index < len(cells) else None


def _set_cell_addr(cell: ET.Element, row_index: int, col_index: int) -> None:
    addr = _child_by_name(cell, "cellAddr")
    if addr is not None:
        addr.attrib["rowAddr"] = str(row_index)
        addr.attrib["colAddr"] = str(col_index)


def _set_cell_span(cell: ET.Element, row_span: int, col_span: int) -> None:
    span = _child_by_name(cell, "cellSpan")
    if span is not None:
        span.attrib["rowSpan"] = str(row_span)
        span.attrib["colSpan"] = str(col_span)


def _cell_size(cell: ET.Element) -> tuple[int, int]:
    size = _child_by_name(cell, "cellSz")
    if size is None:
        return 0, 0
    try:
        width = int(size.attrib.get("width", "0"))
    except ValueError:
        width = 0
    try:
        height = int(size.attrib.get("height", "0"))
    except ValueError:
        height = 0
    return width, height


def _set_cell_size(cell: ET.Element, width: int, height: int) -> None:
    size = _child_by_name(cell, "cellSz")
    if size is not None:
        if width > 0:
            size.attrib["width"] = str(width)
        if height > 0:
            size.attrib["height"] = str(height)


def _clear_cell_text(cell: ET.Element) -> None:
    nodes = text_nodes(cell)
    for node in nodes:
        node.text = ""


def _cell_col_index(cell: ET.Element) -> int:
    addr = _child_by_name(cell, "cellAddr")
    if addr is None:
        return 999999
    try:
        return int(addr.attrib.get("colAddr", "999999"))
    except ValueError:
        return 999999


def _insert_cell_sorted(row: ET.Element, cell: ET.Element) -> None:
    target_col = _cell_col_index(cell)
    for index, existing in enumerate(list(row)):
        if local_name(existing.tag).lower() not in {"tc", "cell"} and not local_name(
            existing.tag
        ).lower().endswith("tc"):
            continue
        if _cell_col_index(existing) > target_col:
            row.insert(index, cell)
            return
    row.append(cell)


class _MergeRegion(NamedTuple):
    row_index: int
    col_index: int
    row_span: int
    col_span: int


def _scan_merge_region(
    rows: list[Any],
    table_index: int,
    region: _MergeRegion,
    anchor: Any,
) -> tuple[dict[str, Any] | None, list[dict[str, int]], int, int]:
    row_index, col_index, row_span, col_span = region
    covered: list[dict[str, int]] = []
    total_width = 0
    total_height = 0
    first_row_height = 0
    for r in range(row_index, row_index + row_span):
        row_width = 0
        row_height = 0
        for c in range(col_index, col_index + col_span):
            cell = _cell_by_addr(rows, r, c)
            if cell is None:
                error = {
                    "status": "CELL_NOT_FOUND",
                    "table_index": table_index,
                    "row_index": r,
                    "col_index": c,
                }
                return error, covered, total_width, total_height
            width, height = _cell_size(cell)
            row_width += width
            row_height = max(row_height, height)
            if cell is not anchor:
                covered.append({"row": r, "col": c})
        if r == row_index:
            total_width = row_width
            first_row_height = row_height
        total_height += row_height or first_row_height
    return None, covered, total_width, total_height


def merge_table_cells(
    package: HwpxPackage,
    table_index: int,
    row_index: int,
    col_index: int,
    row_span: int,
    col_span: int,
) -> dict[str, Any]:
    if row_span < 1 or col_span < 1:
        return {"status": "MERGE_SPAN_INVALID", "row_span": row_span, "col_span": col_span}
    if row_span == 1 and col_span == 1:
        return {
            "status": "MERGE_SPAN_NOOP",
            "table_index": table_index,
            "row_index": row_index,
            "col_index": col_index,
        }
    found = _find_table(package, table_index)
    if not found:
        return {"status": "TABLE_NOT_FOUND", "table_index": table_index}
    entry, root, table = found
    rows = _row_elements(table)
    if row_index < 0 or row_index + row_span > len(rows):
        return {
            "status": "ROW_NOT_FOUND",
            "table_index": table_index,
            "row_index": row_index,
            "row_count": len(rows),
        }

    anchor = _cell_by_addr(rows, row_index, col_index)
    if anchor is None:
        return {
            "status": "CELL_NOT_FOUND",
            "table_index": table_index,
            "row_index": row_index,
            "col_index": col_index,
        }
    error, covered, total_width, total_height = _scan_merge_region(
        rows, table_index, _MergeRegion(row_index, col_index, row_span, col_span), anchor
    )
    if error is not None:
        return error

    for item in covered:
        row = rows[item["row"]]
        cell = _cell_by_addr(rows, item["row"], item["col"])
        if cell is not None and cell in list(row):
            row.remove(cell)
    _set_cell_span(anchor, row_span, col_span)
    _set_cell_size(anchor, total_width, total_height)
    package.write_xml(entry, root)
    return {
        "status": "MERGE_CELLS_PASS",
        "table_index": table_index,
        "entry": entry,
        "anchor": {"row": row_index, "col": col_index},
        "row_span": row_span,
        "col_span": col_span,
        "covered_cells_removed": covered,
    }


@dataclass
class _UnmergeGeometry:
    row_index: int
    col_index: int
    row_span: int
    col_span: int
    unit_width: int
    unit_height: int


def _create_unmerged_covered_cells(
    rows: list[ET.Element],
    anchor: ET.Element,
    geom: _UnmergeGeometry,
    clear_generated_cells: bool,
) -> list[dict[str, int]]:
    created = []
    for r in range(geom.row_index, geom.row_index + geom.row_span):
        if r < 0 or r >= len(rows):
            continue
        row = rows[r]
        for c in range(geom.col_index, geom.col_index + geom.col_span):
            if r == geom.row_index and c == geom.col_index:
                continue
            existing = _cell_by_addr(rows, r, c)
            if existing is not None:
                continue
            clone = copy.deepcopy(anchor)
            _set_cell_addr(clone, r, c)
            _set_cell_span(clone, 1, 1)
            _set_cell_size(clone, geom.unit_width, geom.unit_height)
            if clear_generated_cells:
                _clear_cell_text(clone)
            _insert_cell_sorted(row, clone)
            created.append({"row": r, "col": c})
    return created


def unmerge_table_cell(
    package: HwpxPackage,
    table_index: int,
    row_index: int,
    col_index: int,
    clear_generated_cells: bool = True,
) -> dict[str, Any]:
    found = _find_table(package, table_index)
    if not found:
        return {"status": "TABLE_NOT_FOUND", "table_index": table_index}
    entry, root, table = found
    rows = _row_elements(table)
    anchor = _cell_by_addr(rows, row_index, col_index)
    if anchor is None:
        return {
            "status": "CELL_NOT_FOUND",
            "table_index": table_index,
            "row_index": row_index,
            "col_index": col_index,
        }
    span = _child_by_name(anchor, "cellSpan")
    if span is None:
        return {
            "status": "CELL_SPAN_NOT_FOUND",
            "table_index": table_index,
            "row_index": row_index,
            "col_index": col_index,
        }
    row_span = int(span.attrib.get("rowSpan", "1"))
    col_span = int(span.attrib.get("colSpan", "1"))
    if row_span == 1 and col_span == 1:
        return {
            "status": "UNMERGE_NOOP",
            "table_index": table_index,
            "row_index": row_index,
            "col_index": col_index,
        }
    width, height = _cell_size(anchor)
    unit_width = width // col_span if col_span else width
    unit_height = height // row_span if row_span else height
    _set_cell_span(anchor, 1, 1)
    _set_cell_size(anchor, unit_width, unit_height)

    geom = _UnmergeGeometry(
        row_index=row_index,
        col_index=col_index,
        row_span=row_span,
        col_span=col_span,
        unit_width=unit_width,
        unit_height=unit_height,
    )
    created = _create_unmerged_covered_cells(rows, anchor, geom, clear_generated_cells)
    package.write_xml(entry, root)
    return {
        "status": "UNMERGE_CELL_PASS",
        "table_index": table_index,
        "entry": entry,
        "anchor": {"row": row_index, "col": col_index},
        "row_span_before": row_span,
        "col_span_before": col_span,
        "created_cells": created,
    }


__all__ = ["merge_table_cells", "unmerge_table_cell"]
