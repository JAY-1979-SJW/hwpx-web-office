"""HWPX XML element factory for generated document structures."""

from __future__ import annotations

from typing import Any
import xml.etree.ElementTree as ET

from hwpx_image_ops import add_bindata_image_data
from hwpx_package import HwpxPackage, local_name

HP_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"


def hp(tag: str) -> str:
    return f"{{{HP_NS}}}{tag}"


def _int_attr(value: str | None, default: int = 0) -> int:
    try:
        return int(value or default)
    except ValueError:
        return default


def next_paragraph_id(root: ET.Element) -> str:
    ids = []
    for elem in root.iter():
        if local_name(elem.tag) == "p" and "id" in elem.attrib:
            ids.append(_int_attr(elem.attrib.get("id"), 0))
    return str((max(ids) + 1) if ids else 0)


def infer_paragraph_defaults(root: ET.Element) -> dict[str, str]:
    defaults = {
        "paraPrIDRef": "0",
        "styleIDRef": "0",
        "charPrIDRef": "0",
    }
    for elem in root.iter():
        if local_name(elem.tag) != "p":
            continue
        defaults["paraPrIDRef"] = elem.attrib.get("paraPrIDRef", defaults["paraPrIDRef"])
        defaults["styleIDRef"] = elem.attrib.get("styleIDRef", defaults["styleIDRef"])
        for child in elem.iter():
            if local_name(child.tag) == "run":
                defaults["charPrIDRef"] = child.attrib.get("charPrIDRef", defaults["charPrIDRef"])
                return defaults
    return defaults


def create_text_paragraph(text: str, paragraph_id: str, defaults: dict[str, str] | None = None) -> ET.Element:
    defaults = defaults or {}
    paragraph = ET.Element(
        hp("p"),
        {
            "id": str(paragraph_id),
            "paraPrIDRef": defaults.get("paraPrIDRef", "0"),
            "styleIDRef": defaults.get("styleIDRef", "0"),
            "pageBreak": "0",
            "columnBreak": "0",
            "merged": "0",
        },
    )
    run = ET.SubElement(paragraph, hp("run"), {"charPrIDRef": defaults.get("charPrIDRef", "0")})
    t = ET.SubElement(run, hp("t"))
    t.text = text
    linesegarray = ET.SubElement(paragraph, hp("linesegarray"))
    ET.SubElement(
        linesegarray,
        hp("lineseg"),
        {
            "textpos": "0",
            "vertpos": "0",
            "vertsize": "1000",
            "textheight": "1000",
            "baseline": "850",
            "spacing": "600",
            "horzpos": "0",
            "horzsize": "48188",
            "flags": "393216",
        },
    )
    return paragraph


def _line_seg(horzsize: str = "48188") -> ET.Element:
    return ET.Element(
        hp("lineseg"),
        {
            "textpos": "0",
            "vertpos": "0",
            "vertsize": "1000",
            "textheight": "1000",
            "baseline": "850",
            "spacing": "600",
            "horzpos": "0",
            "horzsize": horzsize,
            "flags": "393216",
        },
    )


def create_cell_paragraph(text: str, defaults: dict[str, str] | None = None, horzsize: str = "12000") -> ET.Element:
    defaults = defaults or {}
    paragraph = ET.Element(
        hp("p"),
        {
            "id": "2147483648",
            "paraPrIDRef": defaults.get("paraPrIDRef", "0"),
            "styleIDRef": defaults.get("styleIDRef", "0"),
            "pageBreak": "0",
            "columnBreak": "0",
            "merged": "0",
        },
    )
    run = ET.SubElement(paragraph, hp("run"), {"charPrIDRef": defaults.get("charPrIDRef", "0")})
    t = ET.SubElement(run, hp("t"))
    t.text = text
    linesegarray = ET.SubElement(paragraph, hp("linesegarray"))
    linesegarray.append(_line_seg(horzsize))
    return paragraph


def create_table_cell(
    text: str,
    row_index: int,
    col_index: int,
    col_width: int,
    row_height: int,
    defaults: dict[str, str],
    col_span: int = 1,
    row_span: int = 1,
) -> ET.Element:
    border_fill_id = defaults.get("borderFillIDRef", "2")
    cell_map = defaults.get("cellBorderFillIDRefMap", {})
    cell_key = f"{row_index},{col_index}"
    if isinstance(cell_map, dict) and cell_map.get(cell_key):
        border_fill_id = cell_map[cell_key]
    elif row_index == 0 and defaults.get("headerBorderFillIDRef"):
        border_fill_id = defaults["headerBorderFillIDRef"]
    elif row_index > 0 and defaults.get("bodyBorderFillIDRef"):
        border_fill_id = defaults["bodyBorderFillIDRef"]
    vert_align_map = defaults.get("cellVertAlignMap", {})
    text_direction_map = defaults.get("cellTextDirectionMap", {})
    line_wrap_map = defaults.get("cellLineWrapMap", {})
    margin_map = defaults.get("cellMarginMap", {})
    vert_align = defaults.get("cellVertAlign", "CENTER")
    text_direction = defaults.get("cellTextDirection", "HORIZONTAL")
    line_wrap = defaults.get("cellLineWrap", "BREAK")
    cell_margin = defaults.get("cellMargin", {"left": "510", "right": "510", "top": "141", "bottom": "141"})
    if isinstance(vert_align_map, dict) and vert_align_map.get(cell_key):
        vert_align = vert_align_map[cell_key]
    if isinstance(text_direction_map, dict) and text_direction_map.get(cell_key):
        text_direction = text_direction_map[cell_key]
    if isinstance(line_wrap_map, dict) and line_wrap_map.get(cell_key):
        line_wrap = line_wrap_map[cell_key]
    if isinstance(margin_map, dict) and margin_map.get(cell_key):
        cell_margin = margin_map[cell_key]
    if not isinstance(cell_margin, dict):
        cell_margin = {"left": "510", "right": "510", "top": "141", "bottom": "141"}
    cell_defaults = dict(defaults)
    char_pr_map = defaults.get("cellCharPrIDRefMap", {})
    para_pr_map = defaults.get("cellParaPrIDRefMap", {})
    if isinstance(char_pr_map, dict) and char_pr_map.get(cell_key):
        cell_defaults["charPrIDRef"] = str(char_pr_map[cell_key])
    if isinstance(para_pr_map, dict) and para_pr_map.get(cell_key):
        cell_defaults["paraPrIDRef"] = str(para_pr_map[cell_key])
    cell = ET.Element(
        hp("tc"),
        {
            "name": "",
            "header": "1" if row_index == 0 and defaults.get("repeatHeader", "1") == "1" else "0",
            "hasMargin": "0",
            "protect": "0",
            "editable": "0",
            "dirty": "0",
            "borderFillIDRef": border_fill_id,
        },
    )
    sublist = ET.SubElement(
        cell,
        hp("subList"),
        {
            "id": "",
            "textDirection": str(text_direction),
            "lineWrap": str(line_wrap),
            "vertAlign": str(vert_align),
            "linkListIDRef": "0",
            "linkListNextIDRef": "0",
            "textWidth": "0",
            "textHeight": "0",
            "hasTextRef": "0",
            "hasNumRef": "0",
        },
    )
    sublist.append(create_cell_paragraph(text, cell_defaults, str(max(col_width - 1020, 1000))))
    ET.SubElement(cell, hp("cellAddr"), {"colAddr": str(col_index), "rowAddr": str(row_index)})
    ET.SubElement(cell, hp("cellSpan"), {"colSpan": str(col_span), "rowSpan": str(row_span)})
    ET.SubElement(cell, hp("cellSz"), {"width": str(col_width), "height": str(row_height)})
    ET.SubElement(
        cell,
        hp("cellMargin"),
        {
            "left": str(cell_margin.get("left", "510")),
            "right": str(cell_margin.get("right", "510")),
            "top": str(cell_margin.get("top", "141")),
            "bottom": str(cell_margin.get("bottom", "141")),
        },
    )
    return cell


def create_generated_table(rows: list[list[str]], defaults: dict[str, str] | None = None) -> ET.Element:
    defaults = defaults or {}
    normalized_rows = [[str(cell) for cell in row] for row in rows]
    row_count = len(normalized_rows)
    col_count = max((len(row) for row in normalized_rows), default=0)
    if row_count == 0 or col_count == 0:
        raise ValueError("table rows must include at least one row and one cell")

    column_widths = defaults.get("columnWidths")
    if isinstance(column_widths, list) and column_widths:
        normalized_widths = [int(width) for width in column_widths[:col_count]]
        if len(normalized_widths) < col_count:
            fallback_width = int(defaults.get("columnWidth", "12000"))
            normalized_widths.extend([fallback_width] * (col_count - len(normalized_widths)))
    else:
        total_width = int(defaults.get("tableWidth", "47904"))
        normalized_widths = [max(total_width // col_count, 1)] * col_count
    total_width = sum(normalized_widths)
    row_heights = defaults.get("rowHeights")
    if isinstance(row_heights, list) and row_heights:
        normalized_heights = [int(height) for height in row_heights[:row_count]]
        if len(normalized_heights) < row_count:
            fallback_height = int(defaults.get("rowHeight", "2814"))
            normalized_heights.extend([fallback_height] * (row_count - len(normalized_heights)))
    else:
        normalized_heights = [int(defaults.get("rowHeight", "2814"))] * row_count
    table_height = sum(normalized_heights)
    table = ET.Element(
        hp("tbl"),
        {
            "id": defaults.get("tableId", "1694229367"),
            "zOrder": "0",
            "numberingType": "TABLE",
            "textWrap": "TOP_AND_BOTTOM",
            "textFlow": "BOTH_SIDES",
            "lock": "0",
            "dropcapstyle": "None",
            "pageBreak": "CELL",
            "repeatHeader": defaults.get("repeatHeader", "1"),
            "rowCnt": str(row_count),
            "colCnt": str(col_count),
            "cellSpacing": "0",
            "borderFillIDRef": defaults.get("borderFillIDRef", "2"),
            "noAdjust": "0",
        },
    )
    ET.SubElement(table, hp("sz"), {"width": str(total_width), "widthRelTo": "ABSOLUTE", "height": str(table_height), "heightRelTo": "ABSOLUTE", "protect": "0"})
    ET.SubElement(table, hp("pos"), {"treatAsChar": "1", "affectLSpacing": "0", "flowWithText": "1", "allowOverlap": "0", "holdAnchorAndSO": "0", "vertRelTo": "PARA", "horzRelTo": "PARA", "vertAlign": "TOP", "horzAlign": "LEFT", "vertOffset": "0", "horzOffset": "0"})
    ET.SubElement(table, hp("outMargin"), {"left": "141", "right": "141", "top": "141", "bottom": "141"})
    ET.SubElement(table, hp("inMargin"), {"left": "510", "right": "510", "top": "141", "bottom": "141"})
    merged_cells = defaults.get("mergedCells", {})
    if not isinstance(merged_cells, dict):
        merged_cells = {}
    covered_cells = set(defaults.get("coveredCells", [])) if isinstance(defaults.get("coveredCells", []), list) else set()

    for row_index, row in enumerate(normalized_rows):
        tr = ET.SubElement(table, hp("tr"))
        row_height = normalized_heights[row_index]
        for col_index in range(col_count):
            cell_key = f"{row_index},{col_index}"
            if cell_key in covered_cells:
                continue
            span = merged_cells.get(cell_key, {})
            if not isinstance(span, dict):
                span = {}
            col_span = max(int(span.get("colSpan", "1")), 1)
            row_span = max(int(span.get("rowSpan", "1")), 1)
            text = row[col_index] if col_index < len(row) else ""
            col_width = sum(normalized_widths[col_index : min(col_index + col_span, col_count)])
            row_height = sum(normalized_heights[row_index : min(row_index + row_span, row_count)])
            tr.append(create_table_cell(text, row_index, col_index, col_width, row_height, defaults, col_span, row_span))
    return table


def create_table_paragraph(rows: list[list[str]], paragraph_id: str, defaults: dict[str, str] | None = None) -> ET.Element:
    defaults = defaults or {}
    paragraph = ET.Element(
        hp("p"),
        {
            "id": str(paragraph_id),
            "paraPrIDRef": defaults.get("paraPrIDRef", "0"),
            "styleIDRef": defaults.get("styleIDRef", "0"),
            "pageBreak": "0",
            "columnBreak": "0",
            "merged": "0",
        },
    )
    run = ET.SubElement(paragraph, hp("run"), {"charPrIDRef": defaults.get("charPrIDRef", "0")})
    run.append(create_generated_table(rows, defaults))
    linesegarray = ET.SubElement(paragraph, hp("linesegarray"))
    linesegarray.append(_line_seg())
    return paragraph


def create_picture_object(
    image_entry: str,
    manifest_id: str | None = None,
    width: int = 12000,
    height: int = 9000,
    position: dict[str, Any] | None = None,
) -> ET.Element:
    manifest_id = manifest_id or image_entry.replace("\\", "/").split("/")[-1].rsplit(".", 1)[0]
    position = position or {}
    horz_offset = str(max(int(position.get("horizontal_offset") or 0), 0))
    vert_offset = str(max(int(position.get("vertical_offset") or 0), 0))
    treat_as_char = "1" if position.get("treat_as_char", True) else "0"
    flow_with_text = "1" if position.get("flow_with_text", False) else "0"
    allow_overlap = "1" if position.get("allow_overlap", False) else "0"
    picture = ET.Element(
        hp("pic"),
        {
            "id": "",
            "zOrder": str(int(position.get("z_order") or 0)),
            "numberingType": "PICTURE",
            "textWrap": str(position.get("text_wrap") or "TOP_AND_BOTTOM"),
            "textFlow": str(position.get("text_flow") or "BOTH_SIDES"),
            "lock": "0",
            "dropcapstyle": "None",
        },
    )
    ET.SubElement(
        picture,
        hp("sz"),
        {
            "width": str(width),
            "widthRelTo": "ABSOLUTE",
            "height": str(height),
            "heightRelTo": "ABSOLUTE",
            "protect": "0",
        },
    )
    ET.SubElement(
        picture,
        hp("pos"),
        {
            "treatAsChar": treat_as_char,
            "affectLSpacing": "0",
            "flowWithText": flow_with_text,
            "allowOverlap": allow_overlap,
            "holdAnchorAndSO": "0",
            "vertRelTo": str(position.get("vert_rel_to") or "PARA"),
            "horzRelTo": str(position.get("horz_rel_to") or "PARA"),
            "vertAlign": "TOP",
            "horzAlign": "LEFT",
            "vertOffset": vert_offset,
            "horzOffset": horz_offset,
        },
    )
    ET.SubElement(picture, hp("outMargin"), {"left": "0", "right": "0", "top": "0", "bottom": "0"})
    ET.SubElement(picture, hp("imgClip"), {"left": "0", "right": "0", "top": "0", "bottom": "0"})
    img_rect = ET.SubElement(picture, hp("imgRect"))
    ET.SubElement(img_rect, hp("pt0"), {"x": "0", "y": "0"})
    ET.SubElement(img_rect, hp("pt1"), {"x": str(width), "y": "0"})
    ET.SubElement(img_rect, hp("pt2"), {"x": str(width), "y": str(height)})
    ET.SubElement(img_rect, hp("pt3"), {"x": "0", "y": str(height)})
    ET.SubElement(
        picture,
        hp("img"),
        {
            "binaryItemIDRef": manifest_id,
            "bright": "0",
            "contrast": "0",
            "effect": "REAL_PIC",
            "alpha": "0",
        },
    )
    ET.SubElement(picture, hp("inMargin"), {"left": "0", "right": "0", "top": "0", "bottom": "0"})
    return picture


def create_picture_paragraph(
    image_entry: str,
    paragraph_id: str,
    defaults: dict[str, str] | None = None,
    manifest_id: str | None = None,
    width: int = 12000,
    height: int = 9000,
    position: dict[str, Any] | None = None,
) -> ET.Element:
    defaults = defaults or {}
    paragraph = ET.Element(
        hp("p"),
        {
            "id": str(paragraph_id),
            "paraPrIDRef": defaults.get("paraPrIDRef", "0"),
            "styleIDRef": defaults.get("styleIDRef", "0"),
            "pageBreak": "0",
            "columnBreak": "0",
            "merged": "0",
        },
    )
    run = ET.SubElement(paragraph, hp("run"), {"charPrIDRef": defaults.get("charPrIDRef", "0")})
    run.append(create_picture_object(image_entry, manifest_id, width, height, position))
    linesegarray = ET.SubElement(paragraph, hp("linesegarray"))
    linesegarray.append(_line_seg())
    return paragraph


def append_generated_paragraph(
    package: HwpxPackage,
    text: str,
    section_index: int = 0,
    style_refs: dict[str, str] | None = None,
) -> dict[str, Any]:
    sections = package.section_entries()
    if section_index < 0 or section_index >= len(sections):
        return {"status": "SECTION_NOT_FOUND", "section_index": section_index, "section_count": len(sections)}
    entry = sections[section_index]
    try:
        root = package.read_xml(entry)
    except Exception as exc:  # noqa: BLE001
        return {"status": "XML_PARSE_ERROR", "entry": entry, "error": str(exc)}
    defaults = infer_paragraph_defaults(root)
    defaults.update(style_refs or {})
    paragraph = create_text_paragraph(text, next_paragraph_id(root), defaults)
    root.append(paragraph)
    package.write_xml(entry, root)
    return {
        "status": "GENERATED_PARAGRAPH_APPEND_PASS",
        "entry": entry,
        "section_index": section_index,
        "paragraph_id": paragraph.attrib.get("id"),
        "text_length": len(text),
    }


def append_generated_table(
    package: HwpxPackage,
    rows: list[list[str]],
    section_index: int = 0,
    style_refs: dict[str, str] | None = None,
) -> dict[str, Any]:
    sections = package.section_entries()
    if section_index < 0 or section_index >= len(sections):
        return {"status": "SECTION_NOT_FOUND", "section_index": section_index, "section_count": len(sections)}
    entry = sections[section_index]
    try:
        root = package.read_xml(entry)
    except Exception as exc:  # noqa: BLE001
        return {"status": "XML_PARSE_ERROR", "entry": entry, "error": str(exc)}
    if not rows or not any(rows):
        return {"status": "EMPTY_TABLE_DATA", "entry": entry}
    defaults = infer_paragraph_defaults(root)
    defaults.update(style_refs or {})
    table_paragraph = create_table_paragraph(rows, next_paragraph_id(root), defaults)
    root.append(table_paragraph)
    package.write_xml(entry, root)
    return {
        "status": "GENERATED_TABLE_APPEND_PASS",
        "entry": entry,
        "section_index": section_index,
        "paragraph_id": table_paragraph.attrib.get("id"),
        "row_count": len(rows),
        "col_count": max(len(row) for row in rows),
    }


def append_generated_picture(
    package: HwpxPackage,
    image_path: str | Any,
    image_entry: str = "BinData/generated_picture001.png",
    section_index: int = 0,
    width: int = 12000,
    height: int = 9000,
    manifest_id: str | None = None,
) -> dict[str, Any]:
    sections = package.section_entries()
    if section_index < 0 or section_index >= len(sections):
        return {"status": "SECTION_NOT_FOUND", "section_index": section_index, "section_count": len(sections)}
    entry = sections[section_index]
    add_result = add_bindata_image_data(package.entries, image_path, image_entry)
    if add_result.get("status") != "IMAGE_BINDATA_ADD_PASS":
        return {
            "status": add_result.get("status", "IMAGE_BINDATA_ADD_FAIL"),
            "entry": entry,
            "section_index": section_index,
            "add_result": add_result,
        }
    manifest_id = manifest_id or add_result.get("manifest", {}).get("id")
    try:
        root = package.read_xml(entry)
    except Exception as exc:  # noqa: BLE001
        return {"status": "XML_PARSE_ERROR", "entry": entry, "error": str(exc), "add_result": add_result}
    defaults = infer_paragraph_defaults(root)
    paragraph = create_picture_paragraph(
        image_entry,
        next_paragraph_id(root),
        defaults,
        manifest_id,
        width,
        height,
    )
    root.append(paragraph)
    package.write_xml(entry, root)
    return {
        "status": "GENERATED_PICTURE_APPEND_PASS",
        "entry": entry,
        "section_index": section_index,
        "paragraph_id": paragraph.attrib.get("id"),
        "image_entry": image_entry,
        "manifest_id": manifest_id,
        "width": width,
        "height": height,
        "add_result": add_result,
    }
