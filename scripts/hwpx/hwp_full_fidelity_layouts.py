"""Analysis-time HWP layout catalog builders for full-fidelity conversion."""

from __future__ import annotations

from typing import Any


def _section_sort_key_from_stream(value: str) -> int:
    return int("".join(ch for ch in value if ch.isdigit()) or 0)


def build_body_layout(body_records_by_section: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    sections = []
    paragraph_total = 0
    text_paragraph_total = 0
    for section_name in sorted(body_records_by_section, key=_section_sort_key_from_stream):
        paragraphs = []
        current: dict[str, Any] | None = None
        for record in body_records_by_section.get(section_name, []):
            tag_id = int(record.get("tag_id") or 0)
            decoded = record.get("decoded") if isinstance(record.get("decoded"), dict) else {}
            if tag_id == 66:
                if current is not None:
                    paragraphs.append(current)
                current = {
                    "record_index": record.get("index"),
                    "level": record.get("level"),
                    "text_char_count": decoded.get("text_char_count"),
                    "para_shape_id": decoded.get("para_shape_id"),
                    "style_id": decoded.get("style_id"),
                    "char_shape_count": decoded.get("char_shape_count"),
                    "line_seg_count": decoded.get("line_seg_count"),
                    "has_para_text": False,
                    "char_shape_runs": [],
                    "line_segments": [],
                }
            elif current is not None and tag_id == 67:
                current["has_para_text"] = True
                current["para_text_record_index"] = record.get("index")
                current["para_text_payload_size"] = record.get("payload_size")
            elif current is not None and tag_id == 68:
                current["char_shape_runs"] = decoded.get("runs") if isinstance(decoded.get("runs"), list) else []
                current["first_char_shape_id"] = decoded.get("first_char_shape_id")
            elif current is not None and tag_id == 69:
                current["line_segments"] = decoded.get("segments") if isinstance(decoded.get("segments"), list) else []
                current["line_segment_count"] = decoded.get("segment_count")
        if current is not None:
            paragraphs.append(current)
        text_paragraphs = [paragraph for paragraph in paragraphs if paragraph.get("has_para_text")]
        paragraph_total += len(paragraphs)
        text_paragraph_total += len(text_paragraphs)
        sections.append(
            {
                "name": section_name,
                "paragraph_count": len(paragraphs),
                "text_paragraph_count": len(text_paragraphs),
                "paragraphs": paragraphs,
            }
        )
    return {
        "section_count": len(sections),
        "paragraph_count": paragraph_total,
        "text_paragraph_count": text_paragraph_total,
        "sections": sections,
    }


def build_page_layout(body_records_by_section: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    sections = []
    for section_index, section_name in enumerate(sorted(body_records_by_section, key=_section_sort_key_from_stream)):
        page_defs = []
        page_border_fills = []
        footnote_shapes = []
        ctrl_headers = []
        list_headers = []
        for record in body_records_by_section.get(section_name, []):
            tag_id = int(record.get("tag_id") or 0)
            decoded = record.get("decoded") if isinstance(record.get("decoded"), dict) else {}
            row = {
                "record_index": record.get("index"),
                "level": record.get("level"),
                **decoded,
            }
            if tag_id == 71:
                ctrl_headers.append(row)
            elif tag_id == 72:
                list_headers.append(row)
            elif tag_id == 73:
                page_defs.append(row)
            elif tag_id == 74:
                footnote_shapes.append(row)
            elif tag_id == 75:
                page_border_fills.append(row)
        active_page_def = page_defs[0] if page_defs else None
        sections.append(
            {
                "section_index": section_index,
                "name": section_name,
                "page_definition": active_page_def,
                "page_definition_count": len(page_defs),
                "page_border_fill_count": len(page_border_fills),
                "footnote_shape_count": len(footnote_shapes),
                "ctrl_header_count": len(ctrl_headers),
                "list_header_count": len(list_headers),
                "page_border_fills": page_border_fills,
                "footnote_shapes": footnote_shapes,
                "ctrl_headers": ctrl_headers[:20],
                "list_headers_sample": list_headers[:20],
            }
        )
    mapped = sum(1 for section in sections if section.get("page_definition"))
    return {
        "status": "PASS" if mapped else "PAGE_DEF_NOT_FOUND",
        "section_count": len(sections),
        "mapped_page_definition_count": mapped,
        "sections": sections,
    }


def build_table_layout(body_records_by_section: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    sections = []
    table_total = 0
    for section_index, section_name in enumerate(sorted(body_records_by_section, key=_section_sort_key_from_stream)):
        records = body_records_by_section.get(section_name, [])
        tables = []
        active: dict[str, Any] | None = None
        for record in records:
            tag_id = int(record.get("tag_id") or 0)
            level = int(record.get("level") or 0)
            decoded = record.get("decoded") if isinstance(record.get("decoded"), dict) else {}
            if tag_id == 77:
                if active is not None:
                    tables.append(active)
                active = {
                    "table_index": len(tables),
                    "record_index": record.get("index"),
                    "level": level,
                    "table": decoded,
                    "list_headers": [],
                    "paragraph_count": 0,
                }
            elif active is not None:
                if tag_id == 77:
                    continue
                if level <= int(active.get("level") or 0) and tag_id not in {72, 66, 67, 68, 69}:
                    tables.append(active)
                    active = None
                    continue
                if tag_id == 72:
                    active["list_headers"].append(
                        {
                            "record_index": record.get("index"),
                            "level": level,
                            **decoded,
                        }
                    )
                elif tag_id == 66:
                    active["paragraph_count"] = int(active.get("paragraph_count") or 0) + 1
        if active is not None:
            tables.append(active)
        for table in tables:
            decoded_table = table.get("table") if isinstance(table.get("table"), dict) else {}
            capacity = int(decoded_table.get("cell_count_capacity") or 0)
            list_count = len(table.get("list_headers") or [])
            table["mapped_list_header_count"] = min(capacity, list_count) if capacity else list_count
            table["unmapped_cell_capacity"] = max(0, capacity - list_count)
            table["extra_list_header_count"] = max(0, list_count - capacity)
        table_total += len(tables)
        sections.append(
            {
                "section_index": section_index,
                "name": section_name,
                "table_count": len(tables),
                "tables": tables,
            }
        )
    return {
        "status": "PASS" if table_total else "TABLE_NOT_FOUND",
        "section_count": len(sections),
        "table_count": table_total,
        "sections": sections,
    }


def build_shape_layout(body_records_by_section: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    sections = []
    component_total = 0
    rectangle_total = 0
    picture_total = 0
    for section_index, section_name in enumerate(sorted(body_records_by_section, key=_section_sort_key_from_stream)):
        components = []
        rectangles = []
        pictures = []
        active_component: dict[str, Any] | None = None
        active_control: dict[str, Any] | None = None
        for record in body_records_by_section.get(section_name, []):
            tag_id = int(record.get("tag_id") or 0)
            level = int(record.get("level") or 0)
            decoded = record.get("decoded") if isinstance(record.get("decoded"), dict) else {}
            if tag_id == 71:
                active_control = {
                    "record_index": record.get("index"),
                    "level": level,
                    "control": decoded,
                }
            elif tag_id == 76:
                active_component = {
                    "record_index": record.get("index"),
                    "level": level,
                    "component": decoded,
                    "control_record_index": active_control.get("record_index") if active_control else None,
                    "control": active_control.get("control") if active_control else None,
                }
                components.append(active_component)
            elif tag_id == 79:
                rectangles.append(
                    {
                        "shape_index": len(rectangles),
                        "record_index": record.get("index"),
                        "level": level,
                        "component_record_index": active_component.get("record_index") if active_component else None,
                        "component": active_component.get("component") if active_component else None,
                        "control_record_index": active_component.get("control_record_index") if active_component else active_control.get("record_index") if active_control else None,
                        "control": active_component.get("control") if active_component else active_control.get("control") if active_control else None,
                        "rectangle": decoded,
                    }
                )
            elif tag_id == 85:
                pictures.append(
                    {
                        "picture_index": len(pictures),
                        "record_index": record.get("index"),
                        "level": level,
                        "component_record_index": active_component.get("record_index") if active_component else None,
                        "component": active_component.get("component") if active_component else None,
                        "control_record_index": active_component.get("control_record_index") if active_component else active_control.get("record_index") if active_control else None,
                        "control": active_component.get("control") if active_component else active_control.get("control") if active_control else None,
                        "picture": decoded,
                    }
                )
        component_total += len(components)
        rectangle_total += len(rectangles)
        picture_total += len(pictures)
        sections.append(
            {
                "section_index": section_index,
                "name": section_name,
                "shape_component_count": len(components),
                "rectangle_count": len(rectangles),
                "picture_count": len(pictures),
                "components": components[:50],
                "rectangles": rectangles,
                "pictures": pictures,
            }
        )
    return {
        "status": "PASS" if component_total or rectangle_total or picture_total else "SHAPE_NOT_FOUND",
        "section_count": len(sections),
        "shape_component_count": component_total,
        "rectangle_count": rectangle_total,
        "picture_count": picture_total,
        "sections": sections,
    }


def build_equation_layout(body_records_by_section: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    sections = []
    equation_total = 0
    for section_index, section_name in enumerate(sorted(body_records_by_section, key=_section_sort_key_from_stream)):
        equations = []
        for record in body_records_by_section.get(section_name, []):
            if int(record.get("tag_id") or 0) != 88:
                continue
            decoded = record.get("decoded") if isinstance(record.get("decoded"), dict) else {}
            equations.append(
                {
                    "equation_index": len(equations),
                    "record_index": record.get("index"),
                    "level": record.get("level"),
                    "formula": decoded.get("formula"),
                    "formula_length": decoded.get("formula_length"),
                    "version": decoded.get("version"),
                    "application": decoded.get("application"),
                    "payload_size": decoded.get("payload_size") or record.get("payload_size"),
                    "payload_prefix_hex": decoded.get("payload_prefix_hex") or record.get("payload_prefix_hex"),
                    "options_hex": decoded.get("options_hex"),
                    "decode_error": decoded.get("decode_error"),
                }
            )
        equation_total += len(equations)
        sections.append(
            {
                "section_index": section_index,
                "name": section_name,
                "equation_count": len(equations),
                "equations": equations,
            }
        )
    return {
        "status": "PASS" if equation_total else "EQUATION_NOT_FOUND",
        "section_count": len(sections),
        "equation_count": equation_total,
        "sections": sections,
    }
