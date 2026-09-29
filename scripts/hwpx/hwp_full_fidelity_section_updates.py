"""HWPX section XML update builders for full-fidelity conversion bridges."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any

HP_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"
ET.register_namespace("hp", HP_NS)


def _xml_string(root: ET.Element) -> str:
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(
        root, encoding="unicode", short_empty_elements=True
    )


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _xml_local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _paragraph_has_text(elem: ET.Element) -> bool:
    return bool("".join(text for text in elem.itertext() if text).strip())


def _section_sort_key(name: str) -> tuple[int, str]:
    stem = name.replace("\\", "/").rsplit("/", 1)[-1]
    digits = "".join(ch for ch in stem if ch.isdigit())
    return (int(digits) if digits else 999999, name.lower())


def _section_layout_map(body_layout: dict[str, Any]) -> dict[int, list[dict[str, Any]]]:
    result: dict[int, list[dict[str, Any]]] = {}
    sections = body_layout.get("sections") if isinstance(body_layout.get("sections"), list) else []
    for index, section in enumerate(sections):
        if not isinstance(section, dict):
            continue
        paragraphs = (
            section.get("paragraphs") if isinstance(section.get("paragraphs"), list) else []
        )
        result[index] = [
            paragraph
            for paragraph in paragraphs
            if isinstance(paragraph, dict) and paragraph.get("has_para_text")
        ]
    return result


def _direct_children_by_local(parent: ET.Element, local: str) -> list[ET.Element]:
    return [child for child in list(parent) if _xml_local_name(child.tag) == local]


def _single_direct_text_run(paragraph: ET.Element) -> tuple[ET.Element, ET.Element] | None:
    runs = _direct_children_by_local(paragraph, "run")
    if len(runs) != 1:
        return None
    run = runs[0]
    children = list(run)
    text_children = [child for child in children if _xml_local_name(child.tag) == "t"]
    if len(text_children) != 1 or len(text_children) != len(children):
        return None
    return run, text_children[0]


def _collect_char_shape_points(char_shape_runs: list, text_length: int) -> list[dict[str, int]]:
    points = []
    for row in char_shape_runs:
        if not isinstance(row, dict):
            continue
        start = _int_or_none(row.get("start_pos"))
        char_shape_id = _int_or_none(row.get("char_shape_id"))
        if start is None or char_shape_id is None or start < 0 or start >= text_length:
            continue
        points.append({"start": start, "char_shape_id": char_shape_id})
    return points


def _dedupe_char_shape_points(points: list[dict[str, int]]) -> list[dict[str, int]]:
    deduped = []
    for point in points:
        if deduped and deduped[-1]["start"] == point["start"]:
            deduped[-1] = point
        else:
            deduped.append(point)
    return deduped


def _normalized_char_shape_segments(char_shape_runs: Any, text_length: int) -> list[dict[str, int]]:
    if not isinstance(char_shape_runs, list) or text_length <= 0:
        return []
    points = _collect_char_shape_points(char_shape_runs, text_length)
    if not points:
        return []
    points.sort(key=lambda item: item["start"])
    deduped = _dedupe_char_shape_points(points)
    if deduped[0]["start"] != 0:
        return []
    segments = []
    for index, point in enumerate(deduped):
        end = deduped[index + 1]["start"] if index + 1 < len(deduped) else text_length
        if end <= point["start"]:
            continue
        segments.append({
            "start": point["start"],
            "end": end,
            "char_shape_id": point["char_shape_id"],
        })
    return segments


def _char_shape_refs_for_source(source: dict[str, Any]) -> list[int]:
    refs = []
    runs = source.get("char_shape_runs") if isinstance(source.get("char_shape_runs"), list) else []
    for row in runs:
        if not isinstance(row, dict):
            continue
        char_shape_id = _int_or_none(row.get("char_shape_id"))
        if char_shape_id is not None:
            refs.append(char_shape_id)
    if refs:
        return refs
    first_char_shape_id = _int_or_none(source.get("first_char_shape_id"))
    return [first_char_shape_id] if first_char_shape_id is not None else []


def apply_char_shape_segments_to_paragraph(
    paragraph: ET.Element, source: dict[str, Any]
) -> dict[str, Any]:
    first_char_shape_id = source.get("first_char_shape_id")
    single = _single_direct_text_run(paragraph)
    if single is None:
        for child in paragraph.iter():
            if _xml_local_name(child.tag) == "run":
                if first_char_shape_id is not None:
                    child.attrib["charPrIDRef"] = str(first_char_shape_id)
                    return {
                        "status": "FIRST_RUN_ONLY",
                        "split_run_count": 0,
                        "reason": "COMPLEX_PARAGRAPH",
                        "applied_char_shape_ids": [_int_or_none(first_char_shape_id)],
                    }
                return {
                    "status": "FIRST_RUN_ONLY",
                    "split_run_count": 0,
                    "reason": "COMPLEX_PARAGRAPH",
                    "applied_char_shape_ids": [],
                }
        return {"status": "RUN_NOT_FOUND", "split_run_count": 0, "applied_char_shape_ids": []}
    run, text_elem = single
    text = text_elem.text or ""
    segments = _normalized_char_shape_segments(source.get("char_shape_runs"), len(text))
    if len(segments) <= 1:
        if first_char_shape_id is not None:
            run.attrib["charPrIDRef"] = str(first_char_shape_id)
            return {
                "status": "FIRST_RUN_ONLY",
                "split_run_count": 0,
                "reason": "SINGLE_OR_NO_SEGMENT",
                "applied_char_shape_ids": [_int_or_none(first_char_shape_id)],
            }
        return {
            "status": "FIRST_RUN_ONLY",
            "split_run_count": 0,
            "reason": "SINGLE_OR_NO_SEGMENT",
            "applied_char_shape_ids": [],
        }
    index = list(paragraph).index(run)
    paragraph.remove(run)
    for segment in segments:
        segment_text = text[segment["start"] : segment["end"]]
        if not segment_text:
            continue
        new_run = ET.Element(f"{{{HP_NS}}}run", {"charPrIDRef": str(segment["char_shape_id"])})
        new_t = ET.SubElement(new_run, f"{{{HP_NS}}}t")
        new_t.text = segment_text
        paragraph.insert(index, new_run)
        index += 1
    return {
        "status": "SPLIT",
        "split_run_count": len(segments),
        "applied_char_shape_ids": [segment["char_shape_id"] for segment in segments],
    }


def apply_line_segments_to_paragraph(
    paragraph: ET.Element, source: dict[str, Any]
) -> dict[str, Any]:
    segments = source.get("line_segments") if isinstance(source.get("line_segments"), list) else []
    valid_segments = [segment for segment in segments if isinstance(segment, dict)]
    if not valid_segments:
        return {"status": "SKIPPED", "line_segment_count": 0}
    for child in list(paragraph):
        if _xml_local_name(child.tag) == "lineSegArray":
            paragraph.remove(child)
    container = ET.Element(f"{{{HP_NS}}}lineSegArray")
    for segment in valid_segments:
        ET.SubElement(
            container,
            f"{{{HP_NS}}}lineSeg",
            {
                "textpos": str(segment.get("text_pos", 0) or 0),
                "vertpos": str(segment.get("line_vertical_pos", 0) or 0),
                "vertsize": str(segment.get("line_height", 0) or 0),
                "textheight": str(segment.get("text_height", 0) or 0),
                "baseline": str(segment.get("baseline", 0) or 0),
                "spacing": str(segment.get("line_spacing", 0) or 0),
                "horzpos": str(segment.get("column_start", 0) or 0),
                "horzsize": str(segment.get("segment_width", 0) or 0),
                "flags": str(segment.get("flags", 0) or 0),
            },
        )
    paragraph.append(container)
    return {"status": "PASS", "line_segment_count": len(valid_segments)}


def _find_first_child_by_local(root: ET.Element, local: str) -> ET.Element | None:
    for elem in root.iter():
        if _xml_local_name(elem.tag) == local:
            return elem
    return None


def _find_or_create_section_parent(root: ET.Element) -> ET.Element:
    sec_pr = _find_first_child_by_local(root, "secPr")
    if sec_pr is not None:
        return sec_pr
    first_paragraph = _find_first_child_by_local(root, "p")
    if first_paragraph is None:
        first_paragraph = ET.Element(f"{{{HP_NS}}}p")
        root.insert(0, first_paragraph)
    first_run = None
    for child in list(first_paragraph):
        if _xml_local_name(child.tag) == "run":
            first_run = child
            break
    if first_run is None:
        first_run = ET.Element(f"{{{HP_NS}}}run")
        first_paragraph.insert(0, first_run)
    sec_pr = ET.Element(
        f"{{{HP_NS}}}secPr",
        {
            "id": "",
            "textDirection": "HORIZONTAL",
            "spaceColumns": "1134",
            "tabStop": "8000",
        },
    )
    first_run.insert(0, sec_pr)
    return sec_pr


def _find_or_create_child(parent: ET.Element, local: str) -> tuple[ET.Element, bool]:
    for child in list(parent):
        if _xml_local_name(child.tag) == local:
            return child, False
    child = ET.Element(f"{{{HP_NS}}}{local}")
    parent.append(child)
    return child, True


def _remove_direct_children_by_local(parent: ET.Element, local: str) -> int:
    removed = 0
    for child in list(parent):
        if _xml_local_name(child.tag) == local:
            parent.remove(child)
            removed += 1
    return removed


def _bool_xml(value: Any) -> str:
    return "1" if bool(value) else "0"


def _non_negative_attr(value: Any, default: int = 0) -> str:
    parsed = _int_or_none(value)
    if parsed is None:
        parsed = default
    return str(max(0, parsed))


def _positive_attr(value: Any, default: int = 1) -> str:
    parsed = _int_or_none(value)
    if parsed is None or parsed <= 0:
        parsed = default
    return str(parsed)


def _note_string(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def _append_note_shape(sec_pr: ET.Element, local: str, row: dict[str, Any], note_kind: str) -> bool:
    if not isinstance(row, dict):
        return False
    note_pr = ET.SubElement(sec_pr, f"{{{HP_NS}}}{local}")
    ET.SubElement(
        note_pr,
        f"{{{HP_NS}}}autoNumFormat",
        {
            "type": str(row.get("number_format") or "DIGIT"),
            "userChar": _note_string(row.get("user_char")),
            "prefixChar": _note_string(row.get("prefix_char")),
            "suffixChar": _note_string(row.get("suffix_char"), ")"),
            "supscript": _bool_xml(row.get("superscript")),
        },
    )
    ET.SubElement(
        note_pr,
        f"{{{HP_NS}}}noteLine",
        {
            "length": str(row.get("separator_length") or 0),
            "type": str(row.get("separator_line_type") or "SOLID"),
            "width": str(row.get("separator_line_width") or "0.12 mm"),
            "color": str((row.get("separator_line_color") or {}).get("hex") or "#000000"),
        },
    )
    ET.SubElement(
        note_pr,
        f"{{{HP_NS}}}noteSpacing",
        {
            "betweenNotes": _non_negative_attr(row.get("space_between"), 850),
            "belowLine": _non_negative_attr(row.get("space_below"), 567),
            "aboveLine": _non_negative_attr(row.get("space_above"), 567),
        },
    )
    numbering_type = (
        row.get("endnote_numbering_type") if note_kind == "endnote" else row.get("numbering_type")
    )
    ET.SubElement(
        note_pr,
        f"{{{HP_NS}}}numbering",
        {
            "type": str(numbering_type or "CONTINUOUS"),
            "newNum": _positive_attr(row.get("start_number"), 1),
        },
    )
    if note_kind == "endnote":
        placement = (
            "END_OF_SECTION" if int(row.get("placement_raw") or 0) == 1 else "END_OF_DOCUMENT"
        )
    else:
        placement = {0: "EACH_COLUMN", 1: "MERGED_COLUMN", 2: "RIGHT_MOST_COLUMN"}.get(
            int(row.get("placement_raw") or 0), "EACH_COLUMN"
        )
    ET.SubElement(
        note_pr,
        f"{{{HP_NS}}}placement",
        {
            "place": placement,
            "beneathText": _bool_xml(row.get("beneath_text")),
        },
    )
    return True


def _append_note_shapes(sec_pr: ET.Element, rows: list[dict[str, Any]]) -> dict[str, int]:
    _remove_direct_children_by_local(sec_pr, "footNotePr")
    _remove_direct_children_by_local(sec_pr, "endNotePr")
    valid_rows = [row for row in rows if isinstance(row, dict)]
    footnote_applied = (
        1
        if valid_rows and _append_note_shape(sec_pr, "footNotePr", valid_rows[0], "footnote")
        else 0
    )
    endnote_applied = (
        1
        if len(valid_rows) > 1 and _append_note_shape(sec_pr, "endNotePr", valid_rows[1], "endnote")
        else 0
    )
    return {
        "applied_footnote_shape_count": footnote_applied,
        "applied_endnote_shape_count": endnote_applied,
    }


def _append_page_border_fills(
    sec_pr: ET.Element, rows: list[dict[str, Any]], border_fill_ids: set[int] | None = None
) -> dict[str, Any]:
    _remove_direct_children_by_local(sec_pr, "pageBorderFill")
    applied = 0
    unresolved = []
    for row in rows[:3]:
        if not isinstance(row, dict):
            continue
        border_fill_id = _int_or_none(row.get("border_fill_id"))
        resolved_border_fill_id = _resolve_ref_id(border_fill_id, border_fill_ids or set())
        margins = row.get("margins") if isinstance(row.get("margins"), dict) else {}
        page_border = ET.SubElement(
            sec_pr,
            f"{{{HP_NS}}}pageBorderFill",
            {
                "type": str(row.get("type") or "BOTH"),
                "borderFillIDRef": str(
                    resolved_border_fill_id
                    if resolved_border_fill_id is not None
                    else border_fill_id or 0
                ),
                "textBorder": str(row.get("text_border") or "PAPER"),
                "headerInside": _bool_xml(row.get("header_inside")),
                "footerInside": _bool_xml(row.get("footer_inside")),
                "fillArea": str(row.get("fill_area") or "PAPER"),
            },
        )
        ET.SubElement(
            page_border,
            f"{{{HP_NS}}}offset",
            {
                "left": _non_negative_attr(margins.get("left"), 1417),
                "right": _non_negative_attr(margins.get("right"), 1417),
                "top": _non_negative_attr(margins.get("top"), 1417),
                "bottom": _non_negative_attr(margins.get("bottom"), 1417),
            },
        )
        applied += 1
        if border_fill_id is not None and border_fill_ids and resolved_border_fill_id is None:
            unresolved.append({
                "border_fill_id": border_fill_id,
                "record_index": row.get("record_index"),
            })
    return {"applied": applied, "unresolved": unresolved}


def _page_layout_by_index(page_layout: dict[str, Any]) -> dict[int, dict[str, Any]]:
    sections = page_layout.get("sections") if isinstance(page_layout.get("sections"), list) else []
    result: dict[int, dict[str, Any]] = {}
    for section in sections:
        if not isinstance(section, dict):
            continue
        try:
            section_index = int(section.get("section_index") or 0)
        except (TypeError, ValueError):
            section_index = 0
        result[section_index] = section
    return result


def _table_layout_by_index(table_layout: dict[str, Any]) -> dict[int, list[dict[str, Any]]]:
    sections = (
        table_layout.get("sections") if isinstance(table_layout.get("sections"), list) else []
    )
    result: dict[int, list[dict[str, Any]]] = {}
    for section in sections:
        if not isinstance(section, dict):
            continue
        try:
            section_index = int(section.get("section_index") or 0)
        except (TypeError, ValueError):
            section_index = 0
        tables = section.get("tables") if isinstance(section.get("tables"), list) else []
        result[section_index] = [table for table in tables if isinstance(table, dict)]
    return result


def build_page_layout_section_updates(
    existing_entries: dict[str, bytes],
    page_layout: dict[str, Any],
    decoded_docinfo: dict[str, Any] | None = None,
) -> tuple[dict[str, bytes], dict[str, Any]]:
    layout_by_index = _page_layout_by_index(page_layout)
    border_fill_ids = _known_ids(
        decoded_docinfo.get("border_fills") if isinstance(decoded_docinfo, dict) else []
    )
    section_entries = sorted(
        [
            name
            for name in existing_entries
            if name.replace("\\", "/").lower().startswith("contents/section")
            and name.lower().endswith(".xml")
        ],
        key=_section_sort_key,
    )
    updates: dict[str, bytes] = {}
    section_reports = []
    for section_index, entry in enumerate(section_entries):
        section_layout = layout_by_index.get(section_index, {})
        page_def = (
            section_layout.get("page_definition")
            if isinstance(section_layout.get("page_definition"), dict)
            else None
        )
        if not page_def:
            section_reports.append({
                "entry": entry,
                "status": "PAGE_DEF_NOT_FOUND",
                "section_index": section_index,
            })
            continue
        try:
            root = ET.fromstring(existing_entries[entry])
        except ET.ParseError as exc:
            section_reports.append({
                "entry": entry,
                "status": "FAIL",
                "error": str(exc),
                "section_index": section_index,
            })
            continue
        sec_pr = _find_or_create_section_parent(root)
        page_pr, created_page_pr = _find_or_create_child(sec_pr, "pagePr")
        margin, created_margin = _find_or_create_child(page_pr, "margin")
        footnote_shapes = (
            section_layout.get("footnote_shapes")
            if isinstance(section_layout.get("footnote_shapes"), list)
            else []
        )
        applied_note_shapes = _append_note_shapes(sec_pr, footnote_shapes)
        page_border_fills = (
            section_layout.get("page_border_fills")
            if isinstance(section_layout.get("page_border_fills"), list)
            else []
        )
        page_border_report = _append_page_border_fills(sec_pr, page_border_fills, border_fill_ids)
        page_pr.attrib["landscape"] = str(
            page_def.get("landscape")
            or (
                "WIDELY"
                if int(page_def.get("width") or 0) > int(page_def.get("height") or 0)
                else "NARROWLY"
            )
        )
        page_pr.attrib["width"] = str(page_def.get("width") or 0)
        page_pr.attrib["height"] = str(page_def.get("height") or 0)
        page_pr.attrib["gutterType"] = "LEFT_ONLY"
        margins = page_def.get("margins") if isinstance(page_def.get("margins"), dict) else {}
        for name in ("left", "right", "top", "bottom", "header", "footer", "gutter"):
            margin.attrib[name] = str(margins.get(name, 0) or 0)
        updates[entry] = _xml_string(root).encode("utf-8")
        section_reports.append({
            "entry": entry,
            "status": "PASS",
            "section_index": section_index,
            "created_page_pr": created_page_pr,
            "created_margin": created_margin,
            "page_definition": page_def,
            "source_footnote_shape_count": len(footnote_shapes),
            **applied_note_shapes,
            "source_page_border_fill_count": len(page_border_fills),
            "applied_page_border_fill_count": page_border_report["applied"],
            "unresolved_page_border_fill_refs": page_border_report["unresolved"],
            "unresolved_page_border_fill_ref_count": len(page_border_report["unresolved"]),
        })
    applied = sum(1 for row in section_reports if row.get("status") == "PASS")
    page_border_applied = sum(
        int(row.get("applied_page_border_fill_count") or 0) for row in section_reports
    )
    unresolved_page_border_refs = sum(
        int(row.get("unresolved_page_border_fill_ref_count") or 0) for row in section_reports
    )
    footnote_applied = sum(
        int(row.get("applied_footnote_shape_count") or 0) for row in section_reports
    )
    endnote_applied = sum(
        int(row.get("applied_endnote_shape_count") or 0) for row in section_reports
    )
    return updates, {
        "status": "PASS" if applied else "PAGE_LAYOUT_NOT_APPLIED",
        "section_count": len(section_entries),
        "applied_section_count": applied,
        "applied_footnote_shape_count": footnote_applied,
        "applied_endnote_shape_count": endnote_applied,
        "applied_page_border_fill_count": page_border_applied,
        "unresolved_page_border_fill_ref_count": unresolved_page_border_refs,
        "sections": section_reports,
        "full_fidelity": False,
        "warning": "PAGE_DEF, FOOTNOTE_SHAPE, and PAGE_BORDER_FILL are mapped to HWPX pagePr/footNotePr/endNotePr/pageBorderFill; headers/footers and control-specific layout are still audited only.",
    }


def _table_elements(root: ET.Element) -> list[ET.Element]:
    return [elem for elem in root.iter() if _xml_local_name(elem.tag) == "tbl"]


def _table_cells(table: ET.Element) -> list[ET.Element]:
    return [elem for elem in table.iter() if _xml_local_name(elem.tag) == "tc"]


def _table_rows(table: ET.Element) -> list[ET.Element]:
    return [elem for elem in table.iter() if _xml_local_name(elem.tag) == "tr"]


def _direct_table_cells(row: ET.Element) -> list[ET.Element]:
    return [child for child in list(row) if _xml_local_name(child.tag) == "tc"]


def _first_child_local(root: ET.Element, local: str) -> ET.Element | None:
    for child in list(root):
        if _xml_local_name(child.tag) == local:
            return child
    return None


def _element_text(elem: ET.Element) -> str:
    return "".join(text for text in elem.itertext() if text).strip()


def _distributed_col_spans(col_count: int, cell_count: int) -> list[int]:
    if col_count <= 0 or cell_count <= 0 or cell_count > col_count:
        return []
    base = col_count // cell_count
    remainder = col_count % cell_count
    return [base + (1 if index < remainder else 0) for index in range(cell_count)]


def _parse_row_cell_counts(row_cell_counts: Any) -> list[int] | None:
    if not isinstance(row_cell_counts, list) or not row_cell_counts:
        return None
    counts = []
    for value in row_cell_counts:
        parsed = _int_or_none(value)
        if parsed is None or parsed < 0:
            return None
        counts.append(parsed)
    return counts


def _apply_col_spans_to_row(
    row: ET.Element,
    row_index: int,
    row_cells: list[ET.Element],
    logical_count: int,
    parsed_col_count: int,
) -> tuple[str, dict[str, Any] | None, int, int]:
    """단일 행에 대한 colSpan 재분배. (outcome, skip_reason, applied_cells, removed_cells) 반환."""
    if logical_count <= 0 or logical_count > parsed_col_count or logical_count > len(row_cells):
        return (
            "skip",
            {
                "row_index": row_index,
                "reason": "INVALID_LOGICAL_CELL_COUNT",
                "logical_count": logical_count,
                "target_cells": len(row_cells),
            },
            0,
            0,
        )
    if logical_count == parsed_col_count:
        return ("noop", None, 0, 0)
    covered_cells = row_cells[logical_count:]
    non_empty_covered = [
        cell_index
        for cell_index, cell in enumerate(covered_cells, start=logical_count)
        if _element_text(cell)
    ]
    if non_empty_covered:
        return (
            "skip",
            {
                "row_index": row_index,
                "reason": "COVERED_CELL_HAS_TEXT",
                "covered_cell_indexes": non_empty_covered[:10],
            },
            0,
            0,
        )
    spans = _distributed_col_spans(parsed_col_count, logical_count)
    if not spans:
        return (
            "skip",
            {
                "row_index": row_index,
                "reason": "SPAN_DISTRIBUTION_FAILED",
                "logical_count": logical_count,
                "col_count": parsed_col_count,
            },
            0,
            0,
        )
    col_addr = 0
    applied_cells = 0
    for cell, col_span in zip(row_cells[:logical_count], spans, strict=True):
        addr = _first_child_local(cell, "cellAddr")
        if addr is None:
            addr = ET.SubElement(cell, f"{{{HP_NS}}}cellAddr")
        addr.attrib["rowAddr"] = str(row_index)
        addr.attrib["colAddr"] = str(col_addr)
        span = _first_child_local(cell, "cellSpan")
        if span is None:
            span = ET.SubElement(cell, f"{{{HP_NS}}}cellSpan")
        span.attrib["rowSpan"] = str(max(_int_or_none(span.attrib.get("rowSpan")) or 1, 1))
        span.attrib["colSpan"] = str(col_span)
        col_addr += col_span
        applied_cells += 1
    removed = 0
    for cell in covered_cells:
        row.remove(cell)
        removed += 1
    return ("applied", None, applied_cells, removed)


def _apply_row_cell_count_col_spans(
    target_table: ET.Element, row_cell_counts: Any, col_count: Any
) -> dict[str, Any]:
    counts = _parse_row_cell_counts(row_cell_counts)
    parsed_col_count = _int_or_none(col_count)
    if not counts or parsed_col_count is None or parsed_col_count <= 0:
        return {
            "status": "SKIPPED",
            "applied_rows": 0,
            "applied_cells": 0,
            "removed_covered_cells": 0,
            "skipped_rows": 0,
        }
    rows = _table_rows(target_table)
    if len(rows) < len(counts):
        return {
            "status": "SKIPPED_TARGET_ROWS_MISSING",
            "applied_rows": 0,
            "applied_cells": 0,
            "removed_covered_cells": 0,
            "skipped_rows": 0,
        }

    applied_rows = 0
    applied_cells = 0
    removed_covered_cells = 0
    skipped_rows = 0
    skipped_reasons: list[dict[str, Any]] = []
    for row_index, (row, logical_count) in enumerate(zip(rows, counts, strict=False)):
        row_cells = _direct_table_cells(row)
        outcome, reason, row_applied_cells, row_removed = _apply_col_spans_to_row(
            row, row_index, row_cells, logical_count, parsed_col_count
        )
        if outcome == "skip":
            skipped_rows += 1
            skipped_reasons.append(reason)
            continue
        if outcome == "noop":
            continue
        applied_cells += row_applied_cells
        removed_covered_cells += row_removed
        applied_rows += 1
    return {
        "status": "PASS" if applied_rows else "NO_ROWS_CHANGED",
        "applied_rows": applied_rows,
        "applied_cells": applied_cells,
        "removed_covered_cells": removed_covered_cells,
        "skipped_rows": skipped_rows,
        "skipped_reasons": skipped_reasons[:20],
    }


def _row_cell_count_targets(
    target_table: ET.Element, row_cell_counts: Any, list_header_count: int
) -> tuple[list[ET.Element], str]:
    counts = _parse_row_cell_counts(row_cell_counts)
    if not counts:
        return _table_cells(target_table), "flat_row_major"
    if sum(counts) != list_header_count:
        return _table_cells(target_table), "flat_row_major_count_mismatch"
    rows = _table_rows(target_table)
    if len(rows) < len(counts):
        return _table_cells(target_table), "flat_row_major_target_rows_missing"
    targets = []
    for row, count in zip(rows, counts, strict=False):
        row_cells = _direct_table_cells(row)
        targets.extend(row_cells[:count])
    if len(targets) != list_header_count:
        return _table_cells(target_table), "flat_row_major_target_cells_missing"
    return targets, "row_cell_counts"


def _apply_cell_size_from_list_header(
    cell: ET.Element, list_header: dict[str, Any], margins: dict[str, Any]
) -> bool:
    text_width = _int_or_none(list_header.get("text_width"))
    text_height = _int_or_none(list_header.get("text_height"))
    if text_width is None and text_height is None:
        return False
    cell_size = _first_child_local(cell, "cellSz")
    if cell_size is None:
        cell_size = ET.SubElement(cell, f"{{{HP_NS}}}cellSz")
    margin_left = _int_or_none(margins.get("left")) or 0
    margin_right = _int_or_none(margins.get("right")) or 0
    margin_top = _int_or_none(margins.get("top")) or 0
    margin_bottom = _int_or_none(margins.get("bottom")) or 0
    if text_width is not None:
        cell_size.attrib["width"] = str(max(0, text_width + margin_left + margin_right))
    if text_height is not None:
        cell_size.attrib["height"] = str(max(0, text_height + margin_top + margin_bottom))
    return True


def _apply_addr_span_from_list_header(
    cell: ET.Element, list_header: dict[str, Any]
) -> tuple[int, int]:
    applied_addr = 0
    applied_span = 0
    cell_addr = (
        list_header.get("cell_addr") if isinstance(list_header.get("cell_addr"), dict) else {}
    )
    row_addr = _int_or_none(cell_addr.get("row"))
    col_addr = _int_or_none(cell_addr.get("col"))
    if row_addr is not None or col_addr is not None:
        addr = _first_child_local(cell, "cellAddr")
        if addr is None:
            addr = ET.SubElement(cell, f"{{{HP_NS}}}cellAddr")
        if row_addr is not None:
            addr.attrib["rowAddr"] = str(row_addr)
        if col_addr is not None:
            addr.attrib["colAddr"] = str(col_addr)
        applied_addr = 1
    cell_span = (
        list_header.get("cell_span") if isinstance(list_header.get("cell_span"), dict) else {}
    )
    row_span = _int_or_none(cell_span.get("row"))
    col_span = _int_or_none(cell_span.get("col"))
    if row_span is not None or col_span is not None:
        span = _first_child_local(cell, "cellSpan")
        if span is None:
            span = ET.SubElement(cell, f"{{{HP_NS}}}cellSpan")
        if row_span is not None:
            span.attrib["rowSpan"] = str(max(row_span, 1))
        if col_span is not None:
            span.attrib["colSpan"] = str(max(col_span, 1))
        applied_span = 1
    return applied_addr, applied_span


def _apply_exact_cell_geometry_from_list_header(
    cell: ET.Element,
    list_header: dict[str, Any],
    *,
    apply_addr_span: bool = True,
    border_fill_ids: set[int] | None = None,
) -> dict[str, Any]:
    applied_addr = 0
    applied_span = 0
    applied_border = 0
    unresolved_border_refs = []
    if apply_addr_span:
        applied_addr, applied_span = _apply_addr_span_from_list_header(cell, list_header)
    border_fill_id = _int_or_none(list_header.get("border_fill_id"))
    if border_fill_id is not None:
        resolved_border_fill_id = _resolve_ref_id(border_fill_id, border_fill_ids or set())
        if resolved_border_fill_id is not None or not border_fill_ids:
            cell.attrib["borderFillIDRef"] = str(
                resolved_border_fill_id if resolved_border_fill_id is not None else border_fill_id
            )
            applied_border = 1
        if border_fill_ids and resolved_border_fill_id is None:
            unresolved_border_refs.append({
                "border_fill_id": border_fill_id,
                "record_index": list_header.get("record_index"),
            })
    return {
        "addr": applied_addr,
        "span": applied_span,
        "border": applied_border,
        "unresolved_border_refs": unresolved_border_refs,
    }


def _apply_cell_addr_span(table: ET.Element) -> int:
    applied = 0
    rows = _table_rows(table)
    for row_index, row in enumerate(rows):
        cells = _direct_table_cells(row)
        col_index = 0
        for cell in cells:
            addr = _first_child_local(cell, "cellAddr")
            if addr is None:
                addr = ET.SubElement(cell, f"{{{HP_NS}}}cellAddr")
            addr.attrib["colAddr"] = str(col_index)
            addr.attrib["rowAddr"] = str(row_index)
            span = _first_child_local(cell, "cellSpan")
            if span is None:
                span = ET.SubElement(cell, f"{{{HP_NS}}}cellSpan")
            col_span = max(_int_or_none(span.attrib.get("colSpan")) or 1, 1)
            span.attrib["colSpan"] = str(col_span)
            span.attrib["rowSpan"] = str(max(_int_or_none(span.attrib.get("rowSpan")) or 1, 1))
            col_index += col_span
            applied += 1
    return applied


def _apply_cell_geometry_for_table(
    cells: list[Any],
    list_headers: list[Any],
    decoded_table: dict[str, Any],
    border_fill_ids: set[int],
    apply_exact_addr_span: bool,
) -> dict[str, Any]:
    applied_cells = 0
    applied_cell_sizes = 0
    applied_exact_cell_addrs = 0
    applied_exact_cell_spans = 0
    applied_cell_borders = 0
    unresolved_cell_border_refs = []
    for cell, list_header in zip(cells, list_headers, strict=False):
        if not isinstance(list_header, dict):
            continue
        cell_addr = (
            list_header.get("cell_addr") if isinstance(list_header.get("cell_addr"), dict) else {}
        )
        row_addr = _int_or_none(cell_addr.get("row"))
        col_addr = _int_or_none(cell_addr.get("col"))
        row_count = _int_or_none(decoded_table.get("row_count"))
        col_count = _int_or_none(decoded_table.get("col_count"))
        out_of_range_addr = (
            row_addr is not None
            and col_addr is not None
            and row_count is not None
            and col_count is not None
            and (row_addr >= row_count or col_addr >= col_count)
        )
        geometry_header = (
            {**list_header, "cell_addr": None, "cell_span": None, "border_fill_id": None}
            if out_of_range_addr
            else list_header
        )
        exact_geometry = _apply_exact_cell_geometry_from_list_header(
            cell,
            geometry_header,
            apply_addr_span=apply_exact_addr_span and not out_of_range_addr,
            border_fill_ids=border_fill_ids,
        )
        applied_exact_cell_addrs += exact_geometry["addr"]
        applied_exact_cell_spans += exact_geometry["span"]
        applied_cell_borders += exact_geometry["border"]
        unresolved_cell_border_refs.extend(exact_geometry["unresolved_border_refs"])
        sub_list = _first_child_local(cell, "subList")
        if sub_list is not None:
            if list_header.get("text_width") is not None:
                sub_list.attrib["textWidth"] = str(list_header.get("text_width"))
            if list_header.get("text_height") is not None:
                sub_list.attrib["textHeight"] = str(list_header.get("text_height"))
        cell_margin = _first_child_local(cell, "cellMargin")
        header_margins = (
            list_header.get("margins") if isinstance(list_header.get("margins"), dict) else {}
        )
        if cell_margin is not None:
            for name in ("left", "right", "top", "bottom"):
                if header_margins.get(name) is not None:
                    cell_margin.attrib[name] = str(header_margins.get(name))
        if _apply_cell_size_from_list_header(cell, list_header, header_margins):
            applied_cell_sizes += 1
        applied_cells += 1
    return {
        "applied_cells": applied_cells,
        "applied_cell_sizes": applied_cell_sizes,
        "applied_exact_cell_addrs": applied_exact_cell_addrs,
        "applied_exact_cell_spans": applied_exact_cell_spans,
        "applied_cell_borders": applied_cell_borders,
        "unresolved_cell_border_refs": unresolved_cell_border_refs,
    }


def _process_one_target_table(
    target_table: Any,
    table_index: int,
    source_tables: list[Any],
    border_fill_ids: set[int],
) -> dict[str, Any]:
    if table_index >= len(source_tables):
        return {"table_index": table_index, "status": "SOURCE_TABLE_NOT_FOUND"}
    source_table = source_tables[table_index]
    decoded_table = source_table.get("table") if isinstance(source_table.get("table"), dict) else {}
    margins = decoded_table.get("margins") if isinstance(decoded_table.get("margins"), dict) else {}
    if decoded_table.get("row_count"):
        target_table.attrib["rowCnt"] = str(decoded_table.get("row_count"))
    if decoded_table.get("col_count"):
        target_table.attrib["colCnt"] = str(decoded_table.get("col_count"))
    if decoded_table.get("cell_spacing") is not None:
        target_table.attrib["cellSpacing"] = str(decoded_table.get("cell_spacing") or 0)
    row_span_report = _apply_row_cell_count_col_spans(
        target_table, decoded_table.get("row_cell_counts"), decoded_table.get("col_count")
    )
    applied_cell_addr_spans = _apply_cell_addr_span(target_table)
    in_margin = _first_child_local(target_table, "inMargin")
    if in_margin is not None:
        for name in ("left", "right", "top", "bottom"):
            if margins.get(name) is not None:
                in_margin.attrib[name] = str(margins.get(name))
    list_headers = (
        source_table.get("list_headers")
        if isinstance(source_table.get("list_headers"), list)
        else []
    )
    all_cells = _table_cells(target_table)
    cells, cell_mapping_policy = _row_cell_count_targets(
        target_table, decoded_table.get("row_cell_counts"), len(list_headers)
    )
    apply_exact_addr_span = cell_mapping_policy == "row_cell_counts"
    geometry = _apply_cell_geometry_for_table(
        cells, list_headers, decoded_table, border_fill_ids, apply_exact_addr_span
    )
    return {
        "table_index": table_index,
        "status": "PASS",
        "source_record_index": source_table.get("record_index"),
        "row_count": decoded_table.get("row_count"),
        "col_count": decoded_table.get("col_count"),
        "target_cell_count": len(all_cells),
        "target_metric_cell_count": len(cells),
        "source_list_header_count": len(list_headers),
        "source_row_cell_counts": decoded_table.get("row_cell_counts"),
        "source_row_cell_count_total": decoded_table.get("row_cell_count_total"),
        "cell_mapping_policy": cell_mapping_policy,
        "row_cell_span_inference": row_span_report,
        "applied_cell_metrics": geometry["applied_cells"],
        "applied_cell_sizes": geometry["applied_cell_sizes"],
        "applied_cell_addr_spans": applied_cell_addr_spans,
        "applied_exact_cell_addrs": geometry["applied_exact_cell_addrs"],
        "applied_exact_cell_spans": geometry["applied_exact_cell_spans"],
        "applied_cell_borders": geometry["applied_cell_borders"],
        "unresolved_cell_border_refs": geometry["unresolved_cell_border_refs"],
        "unresolved_cell_border_ref_count": len(geometry["unresolved_cell_border_refs"]),
        "applied_inferred_col_spans": row_span_report.get("applied_cells"),
        "removed_covered_cells": row_span_report.get("removed_covered_cells"),
        "unmapped_target_cells": max(0, len(all_cells) - geometry["applied_cells"]),
    }


def _aggregate_table_layout_totals(section_reports: list[dict[str, Any]]) -> dict[str, int]:
    fields = (
        "applied_cell_metrics",
        "applied_cell_sizes",
        "applied_cell_addr_spans",
        "applied_inferred_col_spans",
        "removed_covered_cells",
        "applied_exact_cell_addrs",
        "applied_exact_cell_spans",
        "applied_cell_borders",
        "unresolved_cell_border_ref_count",
    )
    tables = [
        table
        for section in section_reports
        for table in section.get("tables", [])
        if isinstance(table, dict)
    ]
    return {field: sum(int(table.get(field) or 0) for table in tables) for field in fields}


def build_table_layout_section_updates(
    existing_entries: dict[str, bytes],
    table_layout: dict[str, Any],
    decoded_docinfo: dict[str, Any] | None = None,
) -> tuple[dict[str, bytes], dict[str, Any]]:
    layout_by_index = _table_layout_by_index(table_layout)
    border_fill_ids = _known_ids(
        decoded_docinfo.get("border_fills") if isinstance(decoded_docinfo, dict) else []
    )
    section_entries = sorted(
        [
            name
            for name in existing_entries
            if name.replace("\\", "/").lower().startswith("contents/section")
            and name.lower().endswith(".xml")
        ],
        key=_section_sort_key,
    )
    updates: dict[str, bytes] = {}
    section_reports = []
    for section_index, entry in enumerate(section_entries):
        source_tables = layout_by_index.get(section_index, [])
        if not source_tables:
            section_reports.append({
                "entry": entry,
                "status": "TABLE_LAYOUT_NOT_FOUND",
                "section_index": section_index,
            })
            continue
        try:
            root = ET.fromstring(existing_entries[entry])
        except ET.ParseError as exc:
            section_reports.append({
                "entry": entry,
                "status": "FAIL",
                "error": str(exc),
                "section_index": section_index,
            })
            continue
        target_tables = _table_elements(root)
        table_reports = [
            _process_one_target_table(target_table, table_index, source_tables, border_fill_ids)
            for table_index, target_table in enumerate(target_tables)
        ]
        if table_reports:
            updates[entry] = _xml_string(root).encode("utf-8")
        section_reports.append({
            "entry": entry,
            "status": "PASS" if table_reports else "NO_TABLES",
            "section_index": section_index,
            "source_table_count": len(source_tables),
            "target_table_count": len(target_tables),
            "tables": table_reports,
        })
    totals = _aggregate_table_layout_totals(section_reports)
    return updates, {
        "status": "PASS" if totals["applied_cell_metrics"] else "TABLE_CELL_METRICS_NOT_APPLIED",
        "section_count": len(section_entries),
        **totals,
        "sections": section_reports,
        "full_fidelity": False,
        "warning": "TABLE row/column/margins, LIST_HEADER cell text box metrics, cell addresses/spans, and borderFillIDRef values are mapped; complex merged-cell identity and table zone border overrides remain pending.",
    }


def _known_ids(rows: Any) -> set[int]:
    ids = set()
    if not isinstance(rows, list):
        return ids
    for row in rows:
        if not isinstance(row, dict):
            continue
        parsed = _int_or_none(row.get("index"))
        if parsed is not None:
            ids.add(parsed)
    return ids


def _resolve_ref_id(raw: Any, known_ids: set[int]) -> int | None:
    value = _int_or_none(raw)
    if value is None:
        return None
    if value in known_ids:
        return value
    if value > 0 and value - 1 in known_ids:
        return value - 1
    return None


@dataclass
class _ShapeRefValidation:
    """Bundled shape-id validation context for paragraph style application."""

    para_shape_ids: set[int]
    char_shape_ids: set[int]
    validate_para_refs: bool
    validate_char_refs: bool


def _apply_para_pr_ref(
    target: Any, source: dict[str, Any], target_index: int, refs: _ShapeRefValidation
) -> dict[str, Any]:
    if source.get("para_shape_id") is None:
        return {"applied_para_pr_refs": 0, "unresolved_para_pr_refs": []}
    para_shape_id = _int_or_none(source.get("para_shape_id"))
    target.attrib["paraPrIDRef"] = str(source.get("para_shape_id"))
    if para_shape_id is not None and (
        not refs.validate_para_refs or para_shape_id in refs.para_shape_ids
    ):
        return {"applied_para_pr_refs": 1, "unresolved_para_pr_refs": []}
    if para_shape_id is not None:
        return {
            "applied_para_pr_refs": 0,
            "unresolved_para_pr_refs": [
                {"target_index": target_index, "para_shape_id": para_shape_id}
            ],
        }
    return {"applied_para_pr_refs": 0, "unresolved_para_pr_refs": []}


def _apply_char_pr_refs(
    source: dict[str, Any],
    target_index: int,
    char_shape_report: dict[str, Any],
    refs: _ShapeRefValidation,
) -> dict[str, Any]:
    applied_char_pr_refs = 0
    unresolved_char_pr_refs = []
    applied_char_shape_ids = [
        item
        for item in (char_shape_report.get("applied_char_shape_ids") or [])
        if _int_or_none(item) is not None
    ]
    for char_shape_id in applied_char_shape_ids:
        parsed = _int_or_none(char_shape_id)
        if parsed is not None and (not refs.validate_char_refs or parsed in refs.char_shape_ids):
            applied_char_pr_refs += 1
        elif parsed is not None:
            unresolved_char_pr_refs.append({"target_index": target_index, "char_shape_id": parsed})
    if not applied_char_shape_ids:
        unresolved_char_pr_refs.extend({
                    "target_index": target_index,
                    "char_shape_id": char_shape_id,
                } for char_shape_id in _char_shape_refs_for_source(source) if refs.validate_char_refs and char_shape_id not in refs.char_shape_ids)
    return {
        "applied_char_pr_refs": applied_char_pr_refs,
        "unresolved_char_pr_refs": unresolved_char_pr_refs,
    }


def _apply_one_paragraph_style(
    target: Any,
    source: dict[str, Any],
    target_index: int,
    refs: _ShapeRefValidation,
) -> dict[str, Any]:
    para_pr = _apply_para_pr_ref(target, source, target_index, refs)
    if source.get("style_id") is not None:
        target.attrib["styleIDRef"] = str(source.get("style_id"))
    char_shape_report = apply_char_shape_segments_to_paragraph(target, source)
    char_pr = _apply_char_pr_refs(source, target_index, char_shape_report, refs)
    first_run_only = 0
    complex_paragraph = 0
    if char_shape_report.get("status") == "FIRST_RUN_ONLY":
        first_run_only = 1
        if char_shape_report.get("reason") == "COMPLEX_PARAGRAPH":
            complex_paragraph = 1
    line_segment_report = apply_line_segments_to_paragraph(target, source)
    line_segment_arrays = 0
    line_segments = 0
    if line_segment_report.get("status") == "PASS":
        line_segment_arrays = 1
        line_segments = int(line_segment_report.get("line_segment_count") or 0)
    return {
        "applied_para_pr_refs": para_pr["applied_para_pr_refs"],
        "unresolved_para_pr_refs": para_pr["unresolved_para_pr_refs"],
        "applied_char_pr_refs": char_pr["applied_char_pr_refs"],
        "unresolved_char_pr_refs": char_pr["unresolved_char_pr_refs"],
        "split_runs": int(char_shape_report.get("split_run_count") or 0),
        "first_run_only": first_run_only,
        "complex_paragraph": complex_paragraph,
        "line_segment_arrays": line_segment_arrays,
        "line_segments": line_segments,
    }


def _aggregate_body_style_totals(section_reports: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "applied_text_paragraphs": sum(
            int(row.get("applied_text_paragraphs") or 0) for row in section_reports
        ),
        "applied_para_pr_refs": sum(
            int(row.get("applied_para_pr_refs") or 0) for row in section_reports
        ),
        "unresolved_para_pr_ref_count": sum(
            int(row.get("unresolved_para_pr_ref_count") or 0) for row in section_reports
        ),
        "applied_char_pr_refs": sum(
            int(row.get("applied_char_pr_refs") or 0) for row in section_reports
        ),
        "unresolved_char_pr_ref_count": sum(
            int(row.get("unresolved_char_pr_ref_count") or 0) for row in section_reports
        ),
        "split_char_shape_runs": sum(
            int(row.get("split_char_shape_runs") or 0) for row in section_reports
        ),
        "line_segment_arrays": sum(
            int(row.get("line_segment_arrays") or 0) for row in section_reports
        ),
        "line_segments": sum(int(row.get("line_segments") or 0) for row in section_reports),
    }


def build_body_style_section_updates(
    existing_entries: dict[str, bytes],
    body_layout: dict[str, Any],
    decoded_docinfo: dict[str, Any] | None = None,
) -> tuple[dict[str, bytes], dict[str, Any]]:
    layout_by_index = _section_layout_map(body_layout)
    para_shape_ids = _known_ids(
        decoded_docinfo.get("para_shapes") if isinstance(decoded_docinfo, dict) else []
    )
    char_shape_ids = _known_ids(
        decoded_docinfo.get("char_shapes") if isinstance(decoded_docinfo, dict) else []
    )
    validate_para_refs = bool(para_shape_ids)
    validate_char_refs = bool(char_shape_ids)
    shape_refs = _ShapeRefValidation(
        para_shape_ids, char_shape_ids, validate_para_refs, validate_char_refs
    )
    section_entries = sorted(
        [
            name
            for name in existing_entries
            if name.replace("\\", "/").lower().startswith("contents/section")
            and name.lower().endswith(".xml")
        ],
        key=_section_sort_key,
    )
    updates: dict[str, bytes] = {}
    section_reports = []
    for section_index, entry in enumerate(section_entries):
        try:
            root = ET.fromstring(existing_entries[entry])
        except ET.ParseError as exc:
            section_reports.append({"entry": entry, "status": "FAIL", "error": str(exc)})
            continue
        source_paragraphs = layout_by_index.get(section_index, [])
        target_paragraphs = [
            elem
            for elem in root.iter()
            if _xml_local_name(elem.tag) == "p" and _paragraph_has_text(elem)
        ]
        applied = 0
        split_runs = 0
        first_run_only = 0
        complex_paragraphs = 0
        line_segment_arrays = 0
        line_segments = 0
        applied_para_pr_refs = 0
        unresolved_para_pr_refs = []
        applied_char_pr_refs = 0
        unresolved_char_pr_refs = []
        for target_index, (target, source) in enumerate(
            zip(target_paragraphs, source_paragraphs, strict=False)
        ):
            para_stats = _apply_one_paragraph_style(target, source, target_index, shape_refs)
            applied_para_pr_refs += para_stats["applied_para_pr_refs"]
            unresolved_para_pr_refs.extend(para_stats["unresolved_para_pr_refs"])
            applied_char_pr_refs += para_stats["applied_char_pr_refs"]
            unresolved_char_pr_refs.extend(para_stats["unresolved_char_pr_refs"])
            split_runs += para_stats["split_runs"]
            first_run_only += para_stats["first_run_only"]
            complex_paragraphs += para_stats["complex_paragraph"]
            line_segment_arrays += para_stats["line_segment_arrays"]
            line_segments += para_stats["line_segments"]
            applied += 1
        if applied:
            updates[entry] = _xml_string(root).encode("utf-8")
        section_reports.append({
            "entry": entry,
            "status": "PASS",
            "source_text_paragraphs": len(source_paragraphs),
            "target_text_paragraphs": len(target_paragraphs),
            "applied_text_paragraphs": applied,
            "applied_para_pr_refs": applied_para_pr_refs,
            "unresolved_para_pr_refs": unresolved_para_pr_refs,
            "unresolved_para_pr_ref_count": len(unresolved_para_pr_refs),
            "applied_char_pr_refs": applied_char_pr_refs,
            "unresolved_char_pr_refs": unresolved_char_pr_refs,
            "unresolved_char_pr_ref_count": len(unresolved_char_pr_refs),
            "split_char_shape_runs": split_runs,
            "first_run_only_paragraphs": first_run_only,
            "complex_char_shape_paragraphs": complex_paragraphs,
            "line_segment_arrays": line_segment_arrays,
            "line_segments": line_segments,
            "unmapped_source_text_paragraphs": max(0, len(source_paragraphs) - applied),
            "unmapped_target_text_paragraphs": max(0, len(target_paragraphs) - applied),
        })
    totals = _aggregate_body_style_totals(section_reports)
    report = {
        "status": "PASS" if totals["applied_text_paragraphs"] else "NO_BODY_STYLE_REFS_APPLIED",
        "section_count": len(section_entries),
        **totals,
        "sections": section_reports,
        "policy": "sequential_text_paragraph_mapping",
        "full_fidelity": False,
        "warning": "Paragraph/run style references and line segment arrays are mapped for generated text-bearing paragraphs; exact control/table paragraph correlation is still pending.",
    }
    return updates, report
