"""Table inspection and mutation operations for HWPX XML sections."""

from __future__ import annotations

import copy
import math
import xml.etree.ElementTree as ET
from typing import Any

from hwpx_element_factory import append_generated_table as append_generated_table_to_package
from hwpx_element_factory import next_paragraph_id
from hwpx_package import HwpxPackage, local_name, text_nodes
from hwpx_special_text import sanitize_hwpx_text


def table_elements(package: HwpxPackage) -> list[tuple[str, ET.Element, ET.Element]]:
    tables = []
    for entry in package.section_entries():
        try:
            root = package.read_xml(entry)
        except (KeyError, ET.ParseError, UnicodeDecodeError, ValueError):
            continue
        for elem in root.iter():
            name = local_name(elem.tag).lower()
            if name in {"tbl", "table"} or "tbl" in name or "table" in name:
                tables.append((entry, root, elem))
    return tables


def find_table(package: HwpxPackage, table_index: int) -> tuple[str, ET.Element, ET.Element] | None:
    tables = table_elements(package)
    if table_index < 0 or table_index >= len(tables):
        return None
    return tables[table_index]


def row_elements(table: ET.Element) -> list[ET.Element]:
    rows = []
    for elem in list(table):
        name = local_name(elem.tag).lower()
        if name in {"tr", "row"} or name.endswith("tr"):
            rows.append(elem)
    return rows


def cell_elements(row: ET.Element) -> list[ET.Element]:
    cells = []
    for elem in list(row):
        name = local_name(elem.tag).lower()
        if name in {"tc", "cell"} or name.endswith("tc") or "cell" in name:
            cells.append(elem)
    return cells


def _qualified_sibling_tag(reference: ET.Element, local: str) -> str:
    if "}" in reference.tag:
        return f"{reference.tag.rsplit('}', 1)[0]}}}{local}"
    return local


def _first_direct_child(elem: ET.Element, local: str) -> ET.Element | None:
    for child in list(elem):
        if local_name(child.tag) == local:
            return child
    return None


def _int_attr(elem: ET.Element | None, name: str, default: int) -> int:
    if elem is None:
        return default
    try:
        value = elem.get(name)
        return int(value) if value not in (None, "") else default
    except ValueError:
        return default


def cell_visual_address(row_index: int, col_index: int, cell: ET.Element) -> dict[str, int]:
    addr = _first_direct_child(cell, "cellAddr")
    span = _first_direct_child(cell, "cellSpan")
    row = _int_attr(addr, "rowAddr", row_index)
    col = _int_attr(addr, "colAddr", col_index)
    row_span = max(_int_attr(span, "rowSpan", 1), 1)
    col_span = max(_int_attr(span, "colSpan", 1), 1)
    return {"row": row, "col": col, "rowspan": row_span, "colspan": col_span}


def _direct_child_attrs(elem: ET.Element, local: str) -> dict[str, str]:
    child = _first_direct_child(elem, local)
    return dict(child.attrib) if child is not None else {}


def _first_descendant_attrs(elem: ET.Element, local: str) -> dict[str, str]:
    for child in elem.iter():
        if local_name(child.tag) == local:
            return dict(child.attrib)
    return {}


def estimate_text_fit(text: str, cell: dict[str, Any]) -> dict[str, Any]:
    width = int(cell.get("cell_width") or 0)
    margin = cell.get("cell_margin") if isinstance(cell.get("cell_margin"), dict) else {}
    left = int(margin.get("left", 0) or 0)
    right = int(margin.get("right", 0) or 0)
    usable_width = max(width - left - right, 0)
    font_height = int(cell.get("font_height") or 1000)
    char_unit = max(1, int(900 * (font_height / 1000)))
    estimated_max_chars = max(1, usable_width // char_unit) if usable_width else 0
    stripped = str(text or "").strip()
    line_wrap = str(cell.get("sublist", {}).get("lineWrap", ""))
    status = "PASS"
    if estimated_max_chars and len(stripped) > estimated_max_chars:
        status = "WARN_WRAP_EXPECTED" if line_wrap.upper() == "BREAK" else "WARN_OVERFLOW_RISK"
    return {
        "status": status,
        "text_length": len(stripped),
        "cell_width": width,
        "usable_width": usable_width,
        "font_height": font_height,
        "estimated_max_chars_single_line": estimated_max_chars,
        "line_wrap": line_wrap,
    }


def _header_root(package: HwpxPackage) -> tuple[str, ET.Element] | None:
    for entry in package.xml_entries():
        if entry.replace("\\", "/").lower().endswith("contents/header.xml"):
            return entry, package.read_xml(entry)
    return None


def _find_first(root: ET.Element, local: str) -> ET.Element | None:
    for elem in root.iter():
        if local_name(elem.tag) == local:
            return elem
    return None


def _find_char_properties(root: ET.Element) -> ET.Element | None:
    return _find_first(root, "charProperties")


def _find_char_pr(root: ET.Element, char_pr_id: str) -> ET.Element | None:
    for elem in root.iter():
        if local_name(elem.tag) == "charPr" and elem.attrib.get("id") == str(char_pr_id):
            return elem
    return None


def char_pr_height(package: HwpxPackage, char_pr_id: str | None, default: int = 1000) -> int:
    if not char_pr_id:
        return default
    header = _header_root(package)
    if header is None:
        return default
    source_char = _find_char_pr(header[1], str(char_pr_id))
    if source_char is None:
        return default
    try:
        return int(source_char.attrib.get("height", str(default)) or default)
    except ValueError:
        return default


def _next_char_pr_id(container: ET.Element) -> str:
    ids = []
    for child in list(container):
        if local_name(child.tag) != "charPr":
            continue
        try:
            ids.append(int(child.attrib.get("id", "0")))
        except ValueError:
            continue
    return str((max(ids) + 1) if ids else 0)


def clone_char_pr_with_height(
    package: HwpxPackage, source_char_pr_id: str, target_height: int
) -> dict[str, Any]:
    header = _header_root(package)
    if header is None:
        return {"status": "HEADER_NOT_FOUND"}
    entry, root = header
    container = _find_char_properties(root)
    if container is None:
        return {"status": "CHAR_PROPERTIES_NOT_FOUND", "entry": entry}
    source = _find_char_pr(root, str(source_char_pr_id))
    if source is None:
        return {
            "status": "CHAR_PR_NOT_FOUND",
            "entry": entry,
            "charPrIDRef": str(source_char_pr_id),
        }
    original_height = int(source.attrib.get("height", "1000") or 1000)
    clone = copy.deepcopy(source)
    new_id = _next_char_pr_id(container)
    clone.attrib["id"] = new_id
    clone.attrib["height"] = str(int(target_height))
    container.append(clone)
    container.attrib["itemCnt"] = str(
        len([child for child in list(container) if local_name(child.tag) == "charPr"])
    )
    package.write_xml(entry, root)
    return {
        "status": "CHAR_PR_CLONE_PASS",
        "entry": entry,
        "source_charPrIDRef": str(source_char_pr_id),
        "new_charPrIDRef": new_id,
        "original_height": original_height,
        "target_height": int(target_height),
    }


def ensure_cell_text_node(cell: ET.Element) -> ET.Element | None:
    nodes = all_cell_text_nodes(cell)
    if nodes:
        return nodes[0]
    for elem in cell.iter():
        if local_name(elem.tag).lower() != "run":
            continue
        text_node = ET.Element(_qualified_sibling_tag(elem, "t"))
        insert_at = 0
        for index, child in enumerate(list(elem)):
            if local_name(child.tag).lower() == "linesegarray":
                insert_at = index
                break
            insert_at = index + 1
        elem.insert(insert_at, text_node)
        return text_node
    return None


def all_cell_text_nodes(cell: ET.Element) -> list[ET.Element]:
    return [elem for elem in cell.iter() if local_name(elem.tag).lower() == "t"]


def _element_style_snapshot(elem: ET.Element | None) -> dict[str, Any] | None:
    if elem is None:
        return None
    return {
        "tag": local_name(elem.tag),
        "attributes": dict(elem.attrib),
    }


def _ancestor(cell: ET.Element, target: ET.Element, local: str) -> ET.Element | None:
    parents = parent_map(cell)
    current = target
    while current in parents:
        current = parents[current]
        if local_name(current.tag).lower() == local.lower():
            return current
    return None


def _style_reference_for_text_node(
    cell: ET.Element, text_node: ET.Element, source: str, text_node_index: int
) -> dict[str, Any]:
    run = _ancestor(cell, text_node, "run")
    paragraph = _ancestor(cell, text_node, "p")
    return {
        "source": source,
        "text_node_index": text_node_index,
        "original_text": text_node.text or "",
        "text_node": _element_style_snapshot(text_node),
        "run": _element_style_snapshot(run),
        "paragraph": _element_style_snapshot(paragraph),
        "charPrIDRef": run.attrib.get("charPrIDRef") if run is not None else None,
        "paraPrIDRef": paragraph.attrib.get("paraPrIDRef") if paragraph is not None else None,
        "styleIDRef": paragraph.attrib.get("styleIDRef") if paragraph is not None else None,
    }


def find_cell_text_style_reference(cell: ET.Element) -> dict[str, Any]:
    """Find the original text/run style that should be preserved for cell input."""
    nodes = all_cell_text_nodes(cell)
    for index, node in enumerate(nodes):
        if (node.text or "").strip():
            return _style_reference_for_text_node(cell, node, "first_non_empty_text_node", index)
    if nodes:
        return _style_reference_for_text_node(cell, nodes[0], "first_text_node", 0)
    for elem in cell.iter():
        if local_name(elem.tag).lower() == "run":
            return {
                "source": "existing_run_without_text_node",
                "text_node_index": None,
                "original_text": "",
                "text_node": None,
                "run": _element_style_snapshot(elem),
                "paragraph": _element_style_snapshot(_ancestor(cell, elem, "p")),
                "charPrIDRef": elem.attrib.get("charPrIDRef"),
                "paraPrIDRef": _ancestor(cell, elem, "p").attrib.get("paraPrIDRef")
                if _ancestor(cell, elem, "p") is not None
                else None,
                "styleIDRef": _ancestor(cell, elem, "p").attrib.get("styleIDRef")
                if _ancestor(cell, elem, "p") is not None
                else None,
            }
    return {
        "source": "no_text_or_run_node",
        "text_node_index": None,
        "original_text": "",
        "text_node": None,
        "run": None,
        "paragraph": None,
        "charPrIDRef": None,
        "paraPrIDRef": None,
        "styleIDRef": None,
    }


def set_cell_single_text(cell: ET.Element, value: str) -> dict[str, Any] | None:
    sanitized = sanitize_hwpx_text(value)
    value = sanitized["text"]
    style_reference = find_cell_text_style_reference(cell)
    first_node = ensure_cell_text_node(cell)
    if first_node is None:
        return None
    nodes = all_cell_text_nodes(cell)
    if first_node not in nodes:
        nodes.insert(0, first_node)
    if style_reference["source"] == "existing_run_without_text_node":
        style_reference = find_cell_text_style_reference(cell)
        style_reference["source"] = "created_text_node_in_original_run"
    before_text = "".join(node.text or "" for node in nodes)
    first_node.text = value
    cleared_nodes = 0
    for node in nodes[1:]:
        if node.text:
            cleared_nodes += 1
        node.text = ""
    return {
        "before_text": before_text,
        "after_text": value,
        "text_node_count": len(nodes),
        "cleared_text_nodes": cleared_nodes,
        "style_reference": style_reference,
        "text_safety": {
            "changed": sanitized["changed"],
            "replacements": sanitized["replacements"],
            "profile": sanitized["profile"],
        },
    }


def parent_map(root: ET.Element) -> dict[ET.Element, ET.Element]:
    return {child: parent for parent in root.iter() for child in list(parent)}


def find_tables(package: HwpxPackage) -> list[dict[str, Any]]:
    result = []
    for index, (entry, _root, table) in enumerate(table_elements(package)):
        rows = row_elements(table)
        result.append({
            "table_index": index,
            "entry": entry,
            "row_count": len(rows),
            "text_node_count": len(text_nodes(table)),
        })
    return result


def get_table_cells(package: HwpxPackage, table_index: int) -> dict[str, Any]:
    found = find_table(package, table_index)
    if not found:
        return {"status": "TABLE_NOT_FOUND", "table_index": table_index, "cells": []}
    entry, _root, table = found
    values = [node.text or "" for node in text_nodes(table)]
    return {"status": "PASS", "table_index": table_index, "entry": entry, "cells": values}


def get_table_cell_matrix(package: HwpxPackage, table_index: int) -> dict[str, Any]:
    found = find_table(package, table_index)
    if not found:
        return {"status": "TABLE_NOT_FOUND", "table_index": table_index, "rows": []}
    entry, _root, table = found
    rows = []
    for row_index, row in enumerate(row_elements(table)):
        cells = []
        for col_index, cell in enumerate(cell_elements(row)):
            nodes = text_nodes(cell)
            visual = cell_visual_address(row_index, col_index, cell)
            style_reference = find_cell_text_style_reference(cell)
            cell_info = {
                "row_index": row_index,
                "col_index": col_index,
                "visual_row": visual["row"],
                "visual_col": visual["col"],
                "rowspan": visual["rowspan"],
                "colspan": visual["colspan"],
                "text": "".join(node.text or "" for node in nodes),
                "text_node_count": len(nodes),
                "cell_width": _int_attr(_first_direct_child(cell, "cellSz"), "width", 0),
                "cell_height": _int_attr(_first_direct_child(cell, "cellSz"), "height", 0),
                "cell_margin": _direct_child_attrs(cell, "cellMargin"),
                "sublist": _first_descendant_attrs(cell, "subList"),
                "borderFillIDRef": cell.attrib.get("borderFillIDRef"),
                "style_reference": style_reference,
                "font_height": char_pr_height(package, style_reference.get("charPrIDRef")),
            }
            cell_info["fit_check"] = estimate_text_fit(cell_info["text"], cell_info)
            cells.append(cell_info)
        rows.append({"row_index": row_index, "cells": cells})
    return {"status": "PASS", "table_index": table_index, "entry": entry, "rows": rows}


def set_table_cell_text(
    package: HwpxPackage,
    table_index: int,
    row_index: int,
    col_index: int,
    value: str,
    clear_remaining: bool = True,
) -> dict[str, Any]:
    found = find_table(package, table_index)
    if not found:
        return {"status": "TABLE_NOT_FOUND", "table_index": table_index}
    entry, root, table = found
    rows = row_elements(table)
    if row_index < 0 or row_index >= len(rows):
        return {
            "status": "ROW_NOT_FOUND",
            "table_index": table_index,
            "row_index": row_index,
            "row_count": len(rows),
        }
    cells = cell_elements(rows[row_index])
    if col_index < 0 or col_index >= len(cells):
        return {
            "status": "CELL_NOT_FOUND",
            "table_index": table_index,
            "row_index": row_index,
            "col_index": col_index,
            "cell_count": len(cells),
        }
    if clear_remaining:
        mutation = set_cell_single_text(cells[col_index], value)
        if mutation is None:
            return {
                "status": "CELL_TEXT_NODE_NOT_FOUND",
                "table_index": table_index,
                "row_index": row_index,
                "col_index": col_index,
            }
    else:
        first_node = ensure_cell_text_node(cells[col_index])
        if first_node is None:
            return {
                "status": "CELL_TEXT_NODE_NOT_FOUND",
                "table_index": table_index,
                "row_index": row_index,
                "col_index": col_index,
            }
        nodes = all_cell_text_nodes(cells[col_index])
        before_text = "".join(node.text or "" for node in nodes)
        first_node.text = value
        mutation = {
            "before_text": before_text,
            "after_text": value,
            "text_node_count": len(nodes),
            "cleared_text_nodes": 0,
            "style_reference": find_cell_text_style_reference(cells[col_index]),
        }
    package.write_xml(entry, root)
    return {
        "status": "PASS",
        "table_index": table_index,
        "row_index": row_index,
        "col_index": col_index,
        "entry": entry,
        **mutation,
    }


def _find_cell_by_visual_address(
    table: ET.Element, visual_row: int, visual_col: int
) -> tuple[int, int, ET.Element] | None:
    for row_index, row in enumerate(row_elements(table)):
        for col_index, cell in enumerate(cell_elements(row)):
            visual = cell_visual_address(row_index, col_index, cell)
            if visual["row"] == visual_row and visual["col"] == visual_col:
                return row_index, col_index, cell
    return None


def set_table_visual_cell_text(
    package: HwpxPackage,
    table_index: int,
    visual_row: int,
    visual_col: int,
    value: str,
    clear_remaining: bool = True,
) -> dict[str, Any]:
    found = find_table(package, table_index)
    if not found:
        return {"status": "TABLE_NOT_FOUND", "table_index": table_index}
    entry, root, table = found
    located = _find_cell_by_visual_address(table, visual_row, visual_col)
    if located is None:
        return {
            "status": "CELL_NOT_FOUND",
            "table_index": table_index,
            "visual_row": visual_row,
            "visual_col": visual_col,
        }
    row_index, col_index, cell = located
    if clear_remaining:
        mutation = set_cell_single_text(cell, value)
        if mutation is None:
            return {
                "status": "CELL_TEXT_NODE_NOT_FOUND",
                "table_index": table_index,
                "visual_row": visual_row,
                "visual_col": visual_col,
            }
    else:
        first_node = ensure_cell_text_node(cell)
        if first_node is None:
            return {
                "status": "CELL_TEXT_NODE_NOT_FOUND",
                "table_index": table_index,
                "visual_row": visual_row,
                "visual_col": visual_col,
            }
        nodes = all_cell_text_nodes(cell)
        before_text = "".join(node.text or "" for node in nodes)
        first_node.text = value
        mutation = {
            "before_text": before_text,
            "after_text": value,
            "text_node_count": len(nodes),
            "cleared_text_nodes": 0,
            "style_reference": find_cell_text_style_reference(cell),
        }
    package.write_xml(entry, root)
    return {
        "status": "PASS",
        "table_index": table_index,
        "row_index": row_index,
        "col_index": col_index,
        "visual_row": visual_row,
        "visual_col": visual_col,
        "entry": entry,
        **mutation,
    }


def _build_cell_font_info(
    package: HwpxPackage, cell: ET.Element, source_char_pr_id: str
) -> dict[str, Any]:
    cell_info: dict[str, Any] = {
        "cell_width": _int_attr(_first_direct_child(cell, "cellSz"), "width", 0),
        "cell_margin": _direct_child_attrs(cell, "cellMargin"),
        "sublist": _first_descendant_attrs(cell, "subList"),
        "font_height": 1000,
    }
    header = _header_root(package)
    if header is not None:
        source_char = _find_char_pr(header[1], str(source_char_pr_id))
        if source_char is not None:
            cell_info["font_height"] = int(source_char.attrib.get("height", "1000") or 1000)
    return cell_info


def shrink_table_visual_cell_text_to_fit(
    package: HwpxPackage,
    table_index: int,
    visual_row: int,
    visual_col: int,
    value: str,
    *,
    min_height: int = 600,
) -> dict[str, Any]:
    found = find_table(package, table_index)
    if not found:
        return {"status": "TABLE_NOT_FOUND", "table_index": table_index}
    entry, root, table = found
    located = _find_cell_by_visual_address(table, visual_row, visual_col)
    if located is None:
        return {
            "status": "CELL_NOT_FOUND",
            "table_index": table_index,
            "visual_row": visual_row,
            "visual_col": visual_col,
        }
    row_index, col_index, cell = located
    style = find_cell_text_style_reference(cell)
    source_char_pr_id = style.get("charPrIDRef")
    if not source_char_pr_id:
        return {
            "status": "CELL_CHAR_STYLE_NOT_FOUND",
            "table_index": table_index,
            "visual_row": visual_row,
            "visual_col": visual_col,
        }

    cell_info = _build_cell_font_info(package, cell, source_char_pr_id)
    before_fit = estimate_text_fit(value, cell_info)
    if before_fit.get("status") == "PASS":
        return {"status": "FONT_SHRINK_NOT_NEEDED", "fit_check": before_fit}
    text_length = max(int(before_fit.get("text_length") or 0), 1)
    estimated_max = max(int(before_fit.get("estimated_max_chars_single_line") or 0), 1)
    original_height = int(cell_info["font_height"])
    target_height = max(
        min_height,
        min(original_height, math.floor(original_height * (estimated_max / text_length))),
    )
    clone_result = clone_char_pr_with_height(package, str(source_char_pr_id), target_height)
    if clone_result.get("status") != "CHAR_PR_CLONE_PASS":
        return clone_result

    _entry2, root2, table2 = find_table(package, table_index)  # type: ignore[misc]
    located2 = _find_cell_by_visual_address(table2, visual_row, visual_col)
    if located2 is None:
        return {
            "status": "CELL_NOT_FOUND_AFTER_STYLE_CLONE",
            "table_index": table_index,
            "visual_row": visual_row,
            "visual_col": visual_col,
        }
    _row_index2, _col_index2, cell2 = located2
    updated_runs = 0
    for elem in cell2.iter():
        if local_name(elem.tag).lower() == "run":
            elem.attrib["charPrIDRef"] = str(clone_result["new_charPrIDRef"])
            updated_runs += 1
    package.write_xml(entry, root2)
    after_cell_info = dict(cell_info)
    after_cell_info["font_height"] = target_height
    after_fit = estimate_text_fit(value, after_cell_info)
    return {
        **clone_result,
        "status": "FONT_SHRINK_PASS",
        "table_index": table_index,
        "row_index": row_index,
        "col_index": col_index,
        "visual_row": visual_row,
        "visual_col": visual_col,
        "entry": entry,
        "updated_runs": updated_runs,
        "before_fit": before_fit,
        "after_fit": after_fit,
    }


def set_table_visual_cell_vertical_align(
    package: HwpxPackage,
    table_index: int,
    visual_row: int,
    visual_col: int,
    vertical_align: str = "CENTER",
) -> dict[str, Any]:
    found = find_table(package, table_index)
    if not found:
        return {"status": "TABLE_NOT_FOUND", "table_index": table_index}
    entry, root, table = found
    located = _find_cell_by_visual_address(table, visual_row, visual_col)
    if located is None:
        return {
            "status": "CELL_NOT_FOUND",
            "table_index": table_index,
            "visual_row": visual_row,
            "visual_col": visual_col,
        }
    row_index, col_index, cell = located
    sublist = None
    for elem in cell.iter():
        if local_name(elem.tag) == "subList":
            sublist = elem
            break
    if sublist is None:
        return {
            "status": "SUBLIST_NOT_FOUND",
            "table_index": table_index,
            "visual_row": visual_row,
            "visual_col": visual_col,
        }
    before = sublist.attrib.get("vertAlign")
    sublist.attrib["vertAlign"] = vertical_align
    package.write_xml(entry, root)
    return {
        "status": "VERTICAL_ALIGN_PASS",
        "table_index": table_index,
        "row_index": row_index,
        "col_index": col_index,
        "visual_row": visual_row,
        "visual_col": visual_col,
        "entry": entry,
        "before": before,
        "after": vertical_align,
    }


def _normalize_hex_color(value: str) -> str | None:
    """색상 문자열을 #RRGGBB 형식으로 정규화."""
    if not value:
        return None
    value = value.strip()
    if value.lower() == "none":
        return None
    if not value.startswith("#"):
        value = "#" + value
    if len(value) in (7, 9):
        return value.upper()
    return None


def _get_fill_color_from_border_fill(bf: ET.Element) -> str | None:
    """borderFill 요소에서 현재 채우기 색상을 읽는다."""
    for child in bf.iter():
        if local_name(child.tag) == "winBrush":
            fc = child.attrib.get("faceColor", "")
            return _normalize_hex_color(fc)
    return None


def _set_fill_color_on_border_fill(bf: ET.Element, color: str) -> None:
    """borderFill 요소의 fillBrush/winBrush faceColor를 설정한다."""
    fill_brush = None
    win_brush = None
    for child in bf.iter():
        ln = local_name(child.tag)
        if ln == "fillBrush":
            fill_brush = child
        elif ln == "winBrush":
            win_brush = child
    ns = bf.tag.rsplit("}", 1)[0].lstrip("{") if "}" in bf.tag else ""
    hh = lambda tag: f"{{{ns}}}{tag}" if ns else tag
    hc_ns = "http://www.hancom.co.kr/hwpml/2011/core"
    hc = lambda tag: f"{{{hc_ns}}}{tag}"
    if fill_brush is None:
        fill_brush = ET.SubElement(bf, hh("fillBrush"))
    if win_brush is None:
        win_brush = ET.SubElement(fill_brush, hc("winBrush"))
    win_brush.attrib["faceColor"] = color
    win_brush.attrib.setdefault("hatchColor", "#000000")
    win_brush.attrib.setdefault("alpha", "0")


def ensure_solid_border_fill(
    package: HwpxPackage,
    color: str,
    source_border_fill_id: str | None = None,
) -> dict[str, Any]:
    """header.xml에서 지정 색상의 solid fill borderFill ID를 반환하거나 새로 생성한다.

    - 동일 색상이 이미 있으면 재사용 (원본 보존)
    - 없으면 source_border_fill_id (또는 첫 번째) borderFill을 복제해 fill 색상 추가
    - dangling ref 방지: 반드시 header.xml에 정의된 ID만 반환
    """
    import copy as _copy

    norm_color = _normalize_hex_color(color)
    if norm_color is None:
        return {"status": "INVALID_COLOR", "color": color}

    header = _header_root(package)
    if header is None:
        return {"status": "HEADER_NOT_FOUND"}
    entry, root = header

    # borderFills 컨테이너 탐색
    container = None
    for elem in root.iter():
        if local_name(elem.tag) == "borderFills":
            container = elem
            break
    if container is None:
        return {"status": "BORDER_FILLS_NOT_FOUND"}

    all_bf = [child for child in list(container) if local_name(child.tag) == "borderFill"]
    if not all_bf:
        return {"status": "NO_BORDER_FILL_TEMPLATE"}

    # 동일 색상 재사용 검사
    for bf in all_bf:
        if _get_fill_color_from_border_fill(bf) == norm_color:
            return {
                "status": "REUSED_EXISTING",
                "borderFillIDRef": bf.attrib.get("id", ""),
                "color": norm_color,
            }

    # 복제 소스 선택: source_border_fill_id 우선, 없으면 첫 번째
    source = None
    if source_border_fill_id:
        for bf in all_bf:
            if bf.attrib.get("id") == str(source_border_fill_id):
                source = bf
                break
    if source is None:
        source = all_bf[0]

    new_id = str(max(int(bf.attrib.get("id", "0")) for bf in all_bf) + 1)
    cloned = _copy.deepcopy(source)
    cloned.attrib["id"] = new_id
    _set_fill_color_on_border_fill(cloned, norm_color)
    container.append(cloned)
    try:
        container.attrib["itemCnt"] = str(
            len([c for c in list(container) if local_name(c.tag) == "borderFill"])
        )
    except (AttributeError, TypeError):
        pass
    package.write_xml(entry, root)
    return {
        "status": "CREATED_NEW",
        "borderFillIDRef": new_id,
        "source_borderFillIDRef": source.attrib.get("id", ""),
        "color": norm_color,
    }


def set_table_visual_cell_solid_fill(
    package: HwpxPackage,
    table_index: int,
    visual_row: int,
    visual_col: int,
    color: str,
) -> dict[str, Any]:
    """셀 배경색을 solid fill로 설정한다.

    1. ensure_solid_border_fill로 ID 확보 (재사용 또는 신규)
    2. 대상 셀의 borderFillIDRef 속성 변경
    3. dangling ref 없음 보장
    """
    bf_result = ensure_solid_border_fill(package, color)
    if bf_result.get("status") not in ("REUSED_EXISTING", "CREATED_NEW"):
        return {
            **bf_result,
            "table_index": table_index,
            "visual_row": visual_row,
            "visual_col": visual_col,
        }

    new_id = bf_result["borderFillIDRef"]
    found = find_table(package, table_index)
    if not found:
        return {"status": "TABLE_NOT_FOUND", "table_index": table_index}
    entry, root, table = found
    located = _find_cell_by_visual_address(table, visual_row, visual_col)
    if located is None:
        return {
            "status": "CELL_NOT_FOUND",
            "table_index": table_index,
            "visual_row": visual_row,
            "visual_col": visual_col,
        }
    row_index, col_index, cell = located
    before_id = cell.attrib.get("borderFillIDRef", "")
    cell.attrib["borderFillIDRef"] = str(new_id)
    package.write_xml(entry, root)
    return {
        "status": "SOLID_FILL_PASS",
        "table_index": table_index,
        "row_index": row_index,
        "col_index": col_index,
        "visual_row": visual_row,
        "visual_col": visual_col,
        "before_borderFillIDRef": before_id,
        "after_borderFillIDRef": str(new_id),
        "color": bf_result["color"],
        "border_fill_action": bf_result["status"],
    }


def update_table_cell_matrix(
    package: HwpxPackage, table_index: int, updates: list[dict[str, Any]]
) -> dict[str, Any]:
    results = []
    status = "PASS"
    for update in updates:
        result = set_table_cell_text(
            package,
            table_index,
            int(update.get("row_index", -1)),
            int(update.get("col_index", -1)),
            str(update.get("value", "")),
            bool(update.get("clear_remaining", True)),
        )
        results.append(result)
        if result.get("status") != "PASS":
            status = "FAIL"
    return {
        "status": status,
        "table_index": table_index,
        "updated_cells": sum(1 for r in results if r.get("status") == "PASS"),
        "results": results,
    }


def update_table_cells(
    package: HwpxPackage, table_index: int, values: list[str], clear_remaining: bool = False
) -> dict:
    found = find_table(package, table_index)
    if not found:
        return {"status": "TABLE_NOT_FOUND", "table_index": table_index}
    entry, root, table = found
    nodes = text_nodes(table)
    updated = 0
    for node, value in zip(nodes, values, strict=False):
        node.text = value
        updated += 1
    if clear_remaining:
        for node in nodes[updated:]:
            node.text = ""
    warnings = []
    if len(values) > len(nodes):
        warnings.append({"type": "EXTRA_VALUES_IGNORED", "extra_count": len(values) - len(nodes)})
    if len(values) != len(nodes):
        warnings.append({
            "type": "CELL_COUNT_MISMATCH",
            "cell_count": len(nodes),
            "value_count": len(values),
        })
    package.write_xml(entry, root)
    return {
        "status": "PASS",
        "table_index": table_index,
        "entry": entry,
        "updated_cells": updated,
        "cell_count": len(nodes),
        "warnings": warnings,
    }


def append_table_row(
    package: HwpxPackage, table_index: int, row_values: list[str], clear_remaining: bool = True
) -> dict:
    found = find_table(package, table_index)
    if not found:
        return {"status": "TABLE_NOT_FOUND", "table_index": table_index}
    entry, root, table = found
    rows = row_elements(table)
    if not rows:
        return {"status": "ROW_NOT_FOUND", "table_index": table_index}
    source_row = rows[-1]
    parent = parent_map(root).get(source_row)
    if parent is None:
        return {
            "status": "ROW_NOT_FOUND",
            "table_index": table_index,
            "reason": "row_parent_not_found",
        }
    clone = copy.deepcopy(source_row)
    cells = cell_elements(clone)
    # 셀 단위 순회. set_cell_single_text가 빈 셀이면 ensure_cell_text_node로
    # <hp:t> 노드를 생성하면서 첫 run의 charPrIDRef를 상속하므로 폰트도 보존된다.
    # 이전 구현은 text_nodes(clone)을 사용해 빈 t 노드를 가진 셀이 누락되어
    # row_values 일부만 매핑되는 한계가 있었다 (HWPX-EDITOR-APPEND-ROW-EMPTY-CELL-TEXTNODE-FIX-01).
    updated = 0
    for cell, value in zip(cells, row_values, strict=False):
        if set_cell_single_text(cell, str(value)) is not None:
            updated += 1
    if clear_remaining:
        for cell in cells[len(row_values) :]:
            set_cell_single_text(cell, "")
    parent.append(clone)
    package.write_xml(entry, root)
    warnings = []
    if len(row_values) > len(cells):
        warnings.append({
            "type": "EXTRA_VALUES_IGNORED",
            "extra_count": len(row_values) - len(cells),
        })
    if len(row_values) != len(cells):
        warnings.append({
            "type": "CELL_COUNT_MISMATCH",
            "cell_count": len(cells),
            "value_count": len(row_values),
        })
    return {
        "status": "APPEND_ROW_PASS",
        "table_index": table_index,
        "entry": entry,
        "row_count_before": len(rows),
        "row_count_after": len(rows) + 1,
        "updated_cells": updated,
        "cell_count": len(cells),
        "warnings": warnings,
    }


def delete_table_row(
    package: HwpxPackage, table_index: int, row_index: int, protect_header: bool = True
) -> dict:
    if protect_header and row_index == 0:
        return {
            "status": "HEADER_ROW_DELETE_BLOCKED",
            "table_index": table_index,
            "row_index": row_index,
        }
    found = find_table(package, table_index)
    if not found:
        return {"status": "TABLE_NOT_FOUND", "table_index": table_index}
    entry, root, table = found
    rows = row_elements(table)
    if row_index < 0 or row_index >= len(rows):
        return {
            "status": "ROW_NOT_FOUND",
            "table_index": table_index,
            "row_index": row_index,
            "row_count": len(rows),
        }
    row = rows[row_index]
    parent = parent_map(root).get(row)
    if parent is None:
        return {
            "status": "ROW_NOT_FOUND",
            "table_index": table_index,
            "row_index": row_index,
            "reason": "row_parent_not_found",
        }
    removed_text = [node.text or "" for node in text_nodes(row)]
    parent.remove(row)
    renumbered_cells = 0
    for later_row in rows[row_index + 1 :]:
        for cell in cell_elements(later_row):
            addr = _first_direct_child(cell, "cellAddr")
            if addr is None:
                continue
            old_row_addr = _int_attr(addr, "rowAddr", -1)
            if old_row_addr > row_index:
                addr.attrib["rowAddr"] = str(old_row_addr - 1)
                renumbered_cells += 1
    package.write_xml(entry, root)
    return {
        "status": "DELETE_ROW_PASS",
        "table_index": table_index,
        "row_index": row_index,
        "entry": entry,
        "row_count_before": len(rows),
        "row_count_after": len(rows) - 1,
        "renumbered_cells": renumbered_cells,
        "removed_text": removed_text,
    }


def clone_table(package: HwpxPackage, table_index: int) -> dict:
    found = find_table(package, table_index)
    if not found:
        return {"status": "TABLE_NOT_FOUND", "table_index": table_index}
    entry, root, table = found
    parent = parent_map(root).get(table)
    if parent is None:
        return {
            "status": "TABLE_NOT_FOUND",
            "table_index": table_index,
            "reason": "table_parent_not_found",
        }
    parent.append(copy.deepcopy(table))
    package.write_xml(entry, root)
    return {"status": "CLONE_TABLE_PASS", "table_index": table_index, "entry": entry}


def _apply_row_values(
    physical_rows: list[ET.Element], rows: list[list[str]], clear_extra_cells: bool
) -> tuple[int, int]:
    updated_cells = 0
    cleared_cells = 0
    for row_index, row in enumerate(physical_rows):
        cells = cell_elements(row)
        for col_index, cell in enumerate(cells):
            if row_index < len(rows) and col_index < len(rows[row_index]):
                mutation = set_cell_single_text(cell, str(rows[row_index][col_index]))
                if mutation is not None:
                    updated_cells += 1
            elif clear_extra_cells:
                mutation = set_cell_single_text(cell, "")
                if mutation is not None:
                    cleared_cells += 1
    return updated_cells, cleared_cells


def append_cloned_table_to_section(
    package: HwpxPackage,
    source_table_index: int,
    rows: list[list[str]],
    section_index: int = 0,
    clear_extra_cells: bool = True,
) -> dict[str, Any]:
    found = find_table(package, source_table_index)
    if not found:
        return {"status": "TABLE_NOT_FOUND", "table_index": source_table_index}
    source_entry, source_root, source_table = found
    source_paragraph = _ancestor(source_root, source_table, "p")
    if source_paragraph is None:
        return {
            "status": "TABLE_PARAGRAPH_NOT_FOUND",
            "table_index": source_table_index,
            "entry": source_entry,
        }
    sections = package.section_entries()
    if section_index < 0 or section_index >= len(sections):
        return {
            "status": "SECTION_NOT_FOUND",
            "section_index": section_index,
            "section_count": len(sections),
        }
    target_entry = sections[section_index]
    target_root = package.read_xml(target_entry)
    clone = copy.deepcopy(source_paragraph)
    clone.attrib["id"] = next_paragraph_id(target_root)
    cloned_table = None
    for elem in clone.iter():
        if local_name(elem.tag).lower() == "tbl":
            cloned_table = elem
            break
    if cloned_table is None:
        return {"status": "CLONED_TABLE_NOT_FOUND", "table_index": source_table_index}

    physical_rows = row_elements(cloned_table)
    updated_cells, cleared_cells = _apply_row_values(physical_rows, rows, clear_extra_cells)
    target_root.append(clone)
    package.write_xml(target_entry, target_root)
    return {
        "status": "CLONED_TABLE_APPEND_PASS",
        "source_table_index": source_table_index,
        "source_entry": source_entry,
        "entry": target_entry,
        "section_index": section_index,
        "requested_row_count": len(rows),
        "requested_col_count": max((len(row) for row in rows), default=0),
        "template_row_count": len(physical_rows),
        "template_col_counts": [len(cell_elements(row)) for row in physical_rows],
        "updated_cells": updated_cells,
        "cleared_cells": cleared_cells,
        "clear_extra_cells": clear_extra_cells,
    }


def replace_table_placeholder(
    package: HwpxPackage, table_id: str | None, headers: list[str], rows: list[list[str]]
) -> dict:
    del table_id  # Current samples do not expose stable table ids.
    values = headers + [cell for row in rows for cell in row]
    for entry in package.section_entries():
        try:
            root = package.read_xml(entry)
        except Exception as exc:  # ruff: ignore[blind-except]
            return {"status": "XML_PARSE_ERROR", "entry": entry, "error": str(exc)}
        for elem in root.iter():
            name = local_name(elem.tag).lower()
            if name not in {"tbl", "table"} and "tbl" not in name and "table" not in name:
                continue
            nodes = text_nodes(elem)
            if not nodes:
                continue
            changed = 0
            for node, value in zip(nodes, values, strict=False):
                node.text = value
                changed += 1
            if changed:
                package.write_xml(entry, root)
                return {"status": "PASS", "entry": entry, "cell_text_nodes_updated": changed}
    return {"status": "TABLE_INSERT_PENDING", "reason": "table_node_not_found_or_no_text_nodes"}


def first_table_text_values(package: HwpxPackage) -> list[str]:
    for _entry, _root, table in table_elements(package):
        return [node.text for node in text_nodes(table) if node.text]
    return []


def render_tables(editor: Any, tables: list[dict[str, Any]]) -> dict[str, Any]:
    report = {
        "requested_tables": len(tables),
        "updated_tables": 0,
        "updated_cells": 0,
        "warnings": [],
        "results": [],
    }
    for table in tables:
        mode = table.get("mode", "replace_first_table_cells")
        if mode != "replace_first_table_cells":
            result = {"status": "UNSUPPORTED_TABLE_MODE", "mode": mode}
            report["warnings"].append(result)
            report["results"].append(result)
            continue
        before_values = first_table_text_values(editor.package)
        result = editor.replace_table_placeholder(
            table.get("table_id"),
            [str(value) for value in table.get("headers", [])],
            [[str(cell) for cell in row] for row in table.get("rows", [])],
        )
        if before_values:
            result["overwritten_text_values"] = before_values[
                : int(result.get("cell_text_nodes_updated", 0))
            ]
        if result.get("status") == "PASS":
            report["updated_tables"] += 1
            report["updated_cells"] += int(result.get("cell_text_nodes_updated", 0))
        else:
            report["warnings"].append(result)
        report["results"].append(result)
    return report


def validate_table_config(tables: list[dict[str, Any]]) -> None:
    if not isinstance(tables, list):
        raise ValueError("tables must be a list")
    for index, table in enumerate(tables, start=1):
        if not isinstance(table, dict):
            raise ValueError(f"table #{index} must be an object")
        if table.get("mode", "replace_first_table_cells") != "replace_first_table_cells":
            continue
        headers = table.get("headers", [])
        rows = table.get("rows", [])
        if not isinstance(headers, list):
            raise ValueError(f"table #{index} headers must be a list")
        if not isinstance(rows, list):
            raise ValueError(f"table #{index} rows must be a list")
        for row_index, row in enumerate(rows, start=1):
            if not isinstance(row, list):
                raise ValueError(f"table #{index} row #{row_index} must be a list")


def table_values_from_ops(operations: list[dict[str, Any]]) -> list[str]:
    values = []
    for op in operations:
        if op.get("op") == "update_cells" or op.get("op") == "append_row":
            values.extend(str(value) for value in op.get("values", []))
    unique = []
    seen = set()
    for value in values:
        if value and value not in seen:
            seen.add(value)
            unique.append(value)
    return unique


def apply_table_operations(editor: Any, operations: list[dict[str, Any]]) -> dict[str, Any]:
    report = {
        "initial_tables": editor.find_tables(),
        "operations": [],
        "warnings": [],
        "status": "PASS",
    }
    for index, operation in enumerate(operations, start=1):
        op = operation.get("op")
        table_index = int(operation.get("table_index", 0))
        if op == "inspect":
            result = editor.get_table_cells(table_index)
        elif op == "inspect_matrix":
            result = editor.get_table_cell_matrix(table_index)
        elif op == "update_cells":
            result = editor.update_table_cells(
                table_index,
                [str(value) for value in operation.get("values", [])],
                bool(operation.get("clear_remaining_cells", False)),
            )
        elif op == "set_cell_text":
            result = editor.set_table_cell_text(
                table_index,
                int(operation.get("row_index", -1)),
                int(operation.get("col_index", -1)),
                str(operation.get("value", "")),
                bool(operation.get("clear_remaining_cells", True)),
            )
        elif op == "set_visual_cell_text":
            result = editor.set_table_visual_cell_text(
                table_index,
                int(operation.get("visual_row", -1)),
                int(operation.get("visual_col", -1)),
                str(operation.get("value", "")),
                bool(operation.get("clear_remaining_cells", True)),
            )
        elif op == "update_cell_matrix":
            result = editor.update_table_cell_matrix(table_index, operation.get("updates", []))
        elif op == "append_row":
            result = editor.append_table_row(
                table_index,
                [str(value) for value in operation.get("values", [])],
                bool(operation.get("clear_remaining_cells", True)),
            )
        elif op == "delete_row":
            result = editor.delete_table_row(
                table_index,
                int(operation.get("row_index", -1)),
                bool(operation.get("protect_header", True)),
            )
        elif op == "clone_table":
            result = editor.clone_table(table_index)
        elif op == "merge_cells":
            result = editor.merge_table_cells(
                table_index,
                int(operation.get("row_index", -1)),
                int(operation.get("col_index", -1)),
                int(operation.get("row_span", 1)),
                int(operation.get("col_span", 1)),
            )
        elif op == "unmerge_cell":
            result = editor.unmerge_table_cell(
                table_index,
                int(operation.get("row_index", -1)),
                int(operation.get("col_index", -1)),
                bool(operation.get("clear_generated_cells", True)),
            )
        elif op == "set_cell_layout":
            result = editor.set_cell_layout(
                table_index,
                int(operation.get("row_index", -1)),
                int(operation.get("col_index", -1)),
                operation.get("layout", {}),
            )
        else:
            result = {"status": "UNSUPPORTED_TABLE_OPERATION", "op": op}
        result["operation_index"] = index
        result["op"] = op
        report["operations"].append(result)
        if result.get("warnings"):
            report["warnings"].extend(result["warnings"])
        status = result.get("status")
        if status in {
            "TABLE_NOT_FOUND",
            "ROW_NOT_FOUND",
            "CELL_NOT_FOUND",
            "UNSUPPORTED_TABLE_OPERATION",
        }:
            report["status"] = "FAIL"
        elif (
            status
            in {
                "HEADER_ROW_DELETE_BLOCKED",
                "MERGE_SPAN_NOOP",
                "UNMERGE_NOOP",
                "SET_CELL_LAYOUT_NOOP",
            }
            and report["status"] != "FAIL"
        ):
            report["status"] = "WARN"
    report["final_tables"] = editor.find_tables()
    return report


def append_generated_table(
    package: HwpxPackage,
    rows: list[list[str]],
    section_index: int = 0,
    style_refs: dict[str, str] | None = None,
) -> dict[str, Any]:
    return append_generated_table_to_package(package, rows, section_index, style_refs)
