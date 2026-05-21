"""Decoded HWP DocInfo to HWPX header/list-style mapping helpers."""

from __future__ import annotations

from typing import Any
import xml.etree.ElementTree as ET

from hwp_full_fidelity_decoders import LANGUAGE_SLOTS, number_text_format


HH_NS = "http://www.hancom.co.kr/hwpml/2011/head"
HC_NS = "http://www.hancom.co.kr/hwpml/2011/core"
ET.register_namespace("hh", HH_NS)
ET.register_namespace("hc", HC_NS)

HWPX_LANGUAGE_NAMES = {
    "hangul": "HANGUL",
    "latin": "LATIN",
    "hanja": "HANJA",
    "japanese": "JAPANESE",
    "other": "OTHER",
    "symbol": "SYMBOL",
    "user": "USER",
}

DEFAULT_FONT_FACE = "HCR Batang"


def _hh(tag: str) -> str:
    return f"{{{HH_NS}}}{tag}"


def _hc(tag: str) -> str:
    return f"{{{HC_NS}}}{tag}"


def _xml_string(root: ET.Element) -> str:
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode", short_empty_elements=True)


def build_decoded_docinfo(records: list[dict[str, Any]]) -> dict[str, Any]:
    catalog: dict[str, Any] = {
        "document_properties": None,
        "id_mappings": None,
        "binary_data": [],
        "face_names": [],
        "border_fills": [],
        "char_shapes": [],
        "tab_defs": [],
        "numberings": [],
        "bullets": [],
        "para_shapes": [],
        "styles": [],
        "docinfo_extensions": [],
        "decoded_record_count": 0,
        "decode_error_count": 0,
    }
    list_targets = {
        18: "binary_data",
        19: "face_names",
        20: "border_fills",
        21: "char_shapes",
        22: "tab_defs",
        23: "numberings",
        24: "bullets",
        25: "para_shapes",
        26: "styles",
    }
    extension_tags = {28, 30, 31, 32, 92, 94, 96, 97}
    for record in records:
        decoded = record.get("decoded")
        if not isinstance(decoded, dict):
            continue
        catalog["decoded_record_count"] += 1
        if decoded.get("decode_error"):
            catalog["decode_error_count"] += 1
        tag_id = int(record.get("tag_id") or 0)
        if tag_id == 16:
            catalog["document_properties"] = decoded
        elif tag_id == 17:
            catalog["id_mappings"] = decoded
        elif tag_id in list_targets:
            row = {"index": len(catalog[list_targets[tag_id]]), **decoded}
            catalog[list_targets[tag_id]].append(row)
        elif tag_id in extension_tags:
            catalog["docinfo_extensions"].append(
                {
                    "index": len(catalog["docinfo_extensions"]),
                    "record_index": record.get("index"),
                    "tag_id": tag_id,
                    "tag_name": record.get("tag_name"),
                    **decoded,
                }
            )
    catalog["counts"] = {
        "binary_data": len(catalog["binary_data"]),
        "face_names": len(catalog["face_names"]),
        "border_fills": len(catalog["border_fills"]),
        "char_shapes": len(catalog["char_shapes"]),
        "tab_defs": len(catalog["tab_defs"]),
        "numberings": len(catalog["numberings"]),
        "bullets": len(catalog["bullets"]),
        "para_shapes": len(catalog["para_shapes"]),
        "styles": len(catalog["styles"]),
        "docinfo_extensions": len(catalog["docinfo_extensions"]),
    }
    catalog["face_name_groups"] = _assign_face_name_groups(catalog)
    return catalog


def _id_mapping_count(decoded_docinfo: dict[str, Any], key: str) -> int | None:
    mappings = decoded_docinfo.get("id_mappings") if isinstance(decoded_docinfo.get("id_mappings"), dict) else {}
    counts = mappings.get("counts") if isinstance(mappings.get("counts"), dict) else {}
    value = counts.get(key)
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _assign_face_name_groups(catalog: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    faces = catalog.get("face_names") if isinstance(catalog.get("face_names"), list) else []
    groups: dict[str, list[dict[str, Any]]] = {slot: [] for slot in LANGUAGE_SLOTS}
    expected_counts = {
        slot: _id_mapping_count(catalog, f"{slot}_font")
        for slot in LANGUAGE_SLOTS
    }
    if not any(value is not None for value in expected_counts.values()):
        for slot in LANGUAGE_SLOTS:
            groups[slot] = [dict(face, language_slot=slot, language_index=index) for index, face in enumerate(faces)]
        return groups

    offset = 0
    for slot in LANGUAGE_SLOTS:
        count = max(0, expected_counts.get(slot) or 0)
        selected = faces[offset : offset + count]
        groups[slot] = [dict(face, language_slot=slot, language_index=index) for index, face in enumerate(selected)]
        offset += count
    if offset < len(faces):
        groups["unassigned"] = [dict(face, language_slot="unassigned", language_index=index) for index, face in enumerate(faces[offset:])]
    return groups


def _color_hex(value: Any, default: str = "#000000") -> str:
    if isinstance(value, dict):
        raw = value.get("hex")
    else:
        raw = value
    text = str(raw or default).strip()
    if not text:
        text = default
    if not text.startswith("#"):
        text = "#" + text
    if len(text) != 7:
        return default
    return text.upper()


def _border_type(value: Any) -> str:
    types = {
        0: "SOLID",
        1: "LONG_DASH",
        2: "DASH",
        3: "DASH_DOT",
        4: "DASH_DOT_DOT",
        5: "LONG_DASH",
        6: "CIRCLE",
        7: "DOUBLE_SLIM",
        8: "SLIM_THICK",
        9: "THICK_SLIM",
        10: "SLIM_THICK_SLIM",
    }
    try:
        return types.get(int(value), "SOLID")
    except (TypeError, ValueError):
        return "SOLID"


def _border_width(value: Any) -> str:
    widths = {
        0: "0.1 mm",
        1: "0.12 mm",
        2: "0.15 mm",
        3: "0.2 mm",
        4: "0.25 mm",
        5: "0.3 mm",
        6: "0.4 mm",
        7: "0.5 mm",
        8: "0.6 mm",
        9: "0.7 mm",
        10: "1.0 mm",
        11: "1.5 mm",
        12: "2.0 mm",
        13: "3.0 mm",
        14: "4.0 mm",
        15: "5.0 mm",
    }
    try:
        return widths.get(int(value), "0.12 mm")
    except (TypeError, ValueError):
        return "0.12 mm"


def _para_align(value: Any) -> str:
    aligns = {
        0: "LEFT",
        1: "JUSTIFY",
        2: "RIGHT",
        3: "CENTER",
        4: "DISTRIBUTE",
        5: "DISTRIBUTE_SPACE",
    }
    try:
        return aligns.get(int(value), "LEFT")
    except (TypeError, ValueError):
        return "LEFT"


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _clamp_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    parsed = _int_or_none(value)
    if parsed is None:
        parsed = default
    return max(minimum, min(maximum, parsed))


def _language_attrs(values: Any, default: int, minimum: int, maximum: int) -> dict[str, str]:
    source = values if isinstance(values, dict) else {}
    return {
        slot: str(_clamp_int(source.get(slot), default, minimum, maximum))
        for slot in LANGUAGE_SLOTS
    }


def _hwp_value(value: Any) -> dict[str, str]:
    return {"value": str(_int_or_none(value) or 0), "unit": "HWPUNIT"}


def _border_fill_ids(decoded_docinfo: dict[str, Any]) -> set[int]:
    rows = decoded_docinfo.get("border_fills") if isinstance(decoded_docinfo.get("border_fills"), list) else []
    ids = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        parsed = _int_or_none(row.get("index"))
        if parsed is not None:
            ids.add(parsed)
    return ids


def _border_fill_ref(value: Any, known_ids: set[int]) -> str:
    parsed = _int_or_none(value)
    if parsed is None:
        return "0"
    if parsed in known_ids:
        return str(parsed)
    if parsed > 0 and parsed - 1 in known_ids:
        return str(parsed - 1)
    return str(parsed)


def _underline_type(value: Any) -> str:
    return {1: "BOTTOM", 2: "CENTER", 3: "TOP"}.get(_int_or_none(value) or 0, "BOTTOM")


def _line_spacing_type(value: Any) -> str:
    return {
        0: "PERCENT",
        1: "FIXED",
        2: "BETWEEN_LINES",
        3: "AT_LEAST",
    }.get(_int_or_none(value) or 0, "PERCENT")


def _break_latin_word(value: Any) -> str:
    return {0: "KEEP_WORD", 1: "HYPHENATION", 2: "BREAK_WORD"}.get(_int_or_none(value) or 0, "KEEP_WORD")


def _break_non_latin_word(value: Any) -> str:
    return "BREAK_WORD" if (_int_or_none(value) or 0) else "KEEP_WORD"


def _bool_xml(value: Any) -> str:
    return "1" if bool(value) else "0"


def _font_type(value: Any) -> str:
    text = str(value or "").upper()
    if text in {"TTF", "HFT"}:
        return text
    return "TTF"


def build_fontface_mapping(decoded_docinfo: dict[str, Any]) -> dict[str, Any]:
    faces = decoded_docinfo.get("face_names") if isinstance(decoded_docinfo.get("face_names"), list) else []
    groups = decoded_docinfo.get("face_name_groups") if isinstance(decoded_docinfo.get("face_name_groups"), dict) else {}
    rows = []
    expected_total = 0
    mapped_total = 0
    mismatches = []
    for slot in LANGUAGE_SLOTS:
        expected = _id_mapping_count(decoded_docinfo, f"{slot}_font")
        group = groups.get(slot) if isinstance(groups.get(slot), list) else []
        if expected is None:
            expected = len(group) if group else len(faces)
        expected_total += max(0, expected)
        mapped_total += len(group)
        if len(group) != expected:
            mismatches.append({"slot": slot, "expected": expected, "actual": len(group)})
        rows.append(
            {
                "slot": slot,
                "expected_count": expected,
                "mapped_count": len(group),
                "font_names": [str(face.get("name") or "") for face in group if isinstance(face, dict)],
                "alternate_font_count": sum(1 for face in group if isinstance(face, dict) and face.get("has_alternate_font")),
                "font_type_info_count": sum(1 for face in group if isinstance(face, dict) and face.get("has_font_type_info")),
                "base_font_count": sum(1 for face in group if isinstance(face, dict) and face.get("has_base_font")),
            }
        )
    unassigned = groups.get("unassigned") if isinstance(groups.get("unassigned"), list) else []
    status = "PASS" if faces and not mismatches and not unassigned else "NO_FONTFACES" if not faces else "PARTIAL_FONTFACE_MAPPING"
    return {
        "status": status,
        "face_name_count": len(faces),
        "expected_total": expected_total,
        "mapped_total": mapped_total,
        "unassigned_count": len(unassigned),
        "mismatches": mismatches,
        "groups": rows,
    }


def _slash_attrs(value: Any) -> dict[str, str] | None:
    if not isinstance(value, dict):
        return None
    slash_type = str(value.get("type") or "NONE")
    if slash_type == "NONE":
        return None
    return {
        "type": slash_type,
        "Crooked": _bool_xml(value.get("crooked")),
        "isCounter": _bool_xml(value.get("is_counter")),
    }


def _hatch_style(value: Any) -> str | None:
    try:
        raw = int(value)
    except (TypeError, ValueError):
        return None
    return {
        1: "HORIZONTAL",
        2: "VERTICAL",
        3: "BACK_SLASH",
        4: "SLASH",
        5: "CROSS",
        6: "CROSS_DIAGONAL",
    }.get(raw)


def _append_begin_num(root: ET.Element, decoded_docinfo: dict[str, Any]) -> None:
    props = decoded_docinfo.get("document_properties") if isinstance(decoded_docinfo.get("document_properties"), dict) else {}
    ET.SubElement(
        root,
        _hh("beginNum"),
        {
            "page": str(props.get("page_start", 1) or 1),
            "footnote": str(props.get("footnote_start", 1) or 1),
            "endnote": str(props.get("endnote_start", 1) or 1),
            "pic": str(props.get("picture_start", 1) or 1),
            "tbl": str(props.get("table_start", 1) or 1),
            "equation": str(props.get("equation_start", 1) or 1),
        },
    )


def _append_fontfaces(ref_list: ET.Element, decoded_docinfo: dict[str, Any]) -> None:
    faces = decoded_docinfo.get("face_names") if isinstance(decoded_docinfo.get("face_names"), list) else []
    groups = decoded_docinfo.get("face_name_groups") if isinstance(decoded_docinfo.get("face_name_groups"), dict) else {}
    fontfaces = ET.SubElement(ref_list, _hh("fontfaces"), {"itemCnt": str(len(HWPX_LANGUAGE_NAMES))})
    for slot in LANGUAGE_SLOTS:
        slot_faces = groups.get(slot) if isinstance(groups.get(slot), list) else faces
        source_rows = slot_faces or [{"index": 0, "language_index": 0, "name": DEFAULT_FONT_FACE}]
        face_group = ET.SubElement(
            fontfaces,
            _hh("fontface"),
            {
                "lang": HWPX_LANGUAGE_NAMES[slot],
                "itemCnt": str(max(1, len(source_rows))),
            },
        )
        for index, face in enumerate(source_rows):
            ET.SubElement(
                face_group,
                _hh("font"),
                {
                    "id": str(face.get("language_index", index)),
                    "face": str(face.get("name") or DEFAULT_FONT_FACE),
                    "type": _font_type(face.get("font_type")),
                    "isEmbedded": "0",
                },
            )
    return
    fontfaces = ET.SubElement(ref_list, _hh("fontfaces"), {"itemCnt": str(len(HWPX_LANGUAGE_NAMES))})
    for slot in LANGUAGE_SLOTS:
        face_group = ET.SubElement(
            fontfaces,
            _hh("fontface"),
            {
                "lang": HWPX_LANGUAGE_NAMES[slot],
                "itemCnt": str(max(1, len(faces))),
            },
        )
        if faces:
            for face in faces:
                ET.SubElement(
                    face_group,
                    _hh("font"),
                    {
                        "id": str(face.get("index", 0)),
                        "face": str(face.get("name") or "함초롬바탕"),
                        "type": "TTF",
                        "isEmbedded": "0",
                    },
                )
        else:
            ET.SubElement(face_group, _hh("font"), {"id": "0", "face": "함초롬바탕", "type": "TTF", "isEmbedded": "0"})


def _append_border_fills(ref_list: ET.Element, decoded_docinfo: dict[str, Any]) -> None:
    fills = decoded_docinfo.get("border_fills") if isinstance(decoded_docinfo.get("border_fills"), list) else []
    container = ET.SubElement(ref_list, _hh("borderFills"), {"itemCnt": str(max(1, len(fills)))})
    source_rows = fills or [{"index": 0, "border_types": [0, 0, 0, 0], "border_widths": [1, 1, 1, 1], "border_colors": [{"hex": "#000000"}] * 4, "fill": {}}]
    for row in source_rows:
        border_fill = ET.SubElement(
            container,
            _hh("borderFill"),
            {
                "id": str(row.get("index", 0)),
                "threeD": _bool_xml(row.get("three_d")),
                "shadow": _bool_xml(row.get("shadow")),
                "centerLine": "NONE",
                "breakCellSeparateLine": "0",
            },
        )
        slash_attrs = _slash_attrs(row.get("slash"))
        if slash_attrs is not None:
            ET.SubElement(border_fill, _hh("slash"), slash_attrs)
        back_slash_attrs = _slash_attrs(row.get("back_slash"))
        if back_slash_attrs is not None:
            ET.SubElement(border_fill, _hh("backSlash"), back_slash_attrs)
        types = row.get("border_types") if isinstance(row.get("border_types"), list) else []
        widths = row.get("border_widths") if isinstance(row.get("border_widths"), list) else []
        colors = row.get("border_colors") if isinstance(row.get("border_colors"), list) else []
        borders = row.get("borders") if isinstance(row.get("borders"), dict) else {}
        for index, child_name in enumerate(("leftBorder", "rightBorder", "topBorder", "bottomBorder")):
            side = ("left", "right", "top", "bottom")[index]
            border = borders.get(side) if isinstance(borders.get(side), dict) else {}
            ET.SubElement(
                border_fill,
                _hh(child_name),
                {
                    "type": str(border.get("type") or _border_type(types[index] if index < len(types) else 0)),
                    "width": str(border.get("width") or _border_width(widths[index] if index < len(widths) else 1)),
                    "color": _color_hex(border.get("color") or (colors[index] if index < len(colors) else "#000000")),
                },
            )
        if slash_attrs is not None or back_slash_attrs is not None:
            ET.SubElement(
                border_fill,
                _hh("diagonal"),
                {
                    "type": str(row.get("diagonal_type_name") or _border_type(row.get("diagonal_type"))),
                    "width": str(row.get("diagonal_width_name") or _border_width(row.get("diagonal_width"))),
                    "color": _color_hex(row.get("diagonal_color"), "#000000"),
                },
            )
        fill = row.get("fill") if isinstance(row.get("fill"), dict) else {}
        solid = fill.get("solid") if isinstance(fill.get("solid"), dict) else {}
        gradient = fill.get("gradient") if isinstance(fill.get("gradient"), dict) else {}
        if solid:
            brush = ET.SubElement(border_fill, _hc("fillBrush"))
            attrs = {
                "faceColor": _color_hex(solid.get("background"), "#FFFFFF"),
                "hatchColor": _color_hex(solid.get("pattern"), "#000000"),
                "alpha": "0",
            }
            hatch_style = solid.get("pattern_name") or _hatch_style(solid.get("pattern_type"))
            if hatch_style:
                attrs["hatchStyle"] = str(hatch_style)
            ET.SubElement(brush, _hc("winBrush"), attrs)
        elif gradient:
            brush = ET.SubElement(border_fill, _hc("fillBrush"))
            gradation = ET.SubElement(
                brush,
                _hc("gradation"),
                {
                    "type": str(gradient.get("type") or "LINEAR"),
                    "angle": str(gradient.get("angle") or 0),
                    "centerX": str(gradient.get("center_x") or 0),
                    "centerY": str(gradient.get("center_y") or 0),
                    "step": str(max(0, min(255, _int_or_none(gradient.get("step")) or 0))),
                    "colorNum": str(max(0, _int_or_none(gradient.get("color_count")) or 0)),
                    "stepCenter": str(max(0, min(100, _int_or_none(gradient.get("step_center")) or 50))),
                    "alpha": "0",
                },
            )
            colors = gradient.get("colors") if isinstance(gradient.get("colors"), list) else []
            for color in colors:
                ET.SubElement(gradation, _hc("color"), {"value": _color_hex(color, "#FFFFFF")})


def _append_char_properties(ref_list: ET.Element, decoded_docinfo: dict[str, Any]) -> None:
    shapes = decoded_docinfo.get("char_shapes") if isinstance(decoded_docinfo.get("char_shapes"), list) else []
    border_fill_ids = _border_fill_ids(decoded_docinfo)
    container = ET.SubElement(ref_list, _hh("charProperties"), {"itemCnt": str(max(1, len(shapes)))})
    source_rows = shapes or [
        {
            "index": 0,
            "face_ids": {},
            "ratios": {},
            "spacings": {},
            "relative_sizes": {},
            "offsets": {},
            "base_size_hwpunit": 1000,
            "text_color": {"hex": "#000000"},
            "shade_color": {"hex": "#FFFFFF"},
        }
    ]
    for row in source_rows:
        attrs = {
            "id": str(row.get("index", 0)),
            "height": str(row.get("base_size_hwpunit") or 1000),
            "textColor": _color_hex(row.get("text_color"), "#000000"),
            "shadeColor": _color_hex(row.get("shade_color"), "#FFFFFF"),
            "useFontSpace": "0",
            "useKerning": "0",
            "symMark": "NONE",
        }
        if row.get("border_fill_id") is not None:
            attrs["borderFillIDRef"] = _border_fill_ref(row.get("border_fill_id"), border_fill_ids)
        char_pr = ET.SubElement(container, _hh("charPr"), attrs)
        ET.SubElement(char_pr, _hh("fontRef"), _language_attrs(row.get("face_ids"), 0, 0, 65535))
        ET.SubElement(char_pr, _hh("ratio"), _language_attrs(row.get("ratios"), 100, 50, 200))
        ET.SubElement(char_pr, _hh("spacing"), _language_attrs(row.get("spacings"), 0, -50, 50))
        ET.SubElement(char_pr, _hh("relSz"), _language_attrs(row.get("relative_sizes"), 100, 10, 250))
        ET.SubElement(char_pr, _hh("offset"), _language_attrs(row.get("offsets"), 0, -100, 100))
        if row.get("bold"):
            ET.SubElement(char_pr, _hh("bold"))
        if row.get("italic"):
            ET.SubElement(char_pr, _hh("italic"))
        underline_type = int(row.get("underline_type") or 0)
        if underline_type:
            ET.SubElement(
                char_pr,
                _hh("underline"),
                {"type": _underline_type(underline_type), "shape": "SOLID", "color": _color_hex(row.get("underline_color"))},
            )
        if int(row.get("strikeout_type") or 0):
            ET.SubElement(char_pr, _hh("strikeout"), {"shape": "SOLID", "color": _color_hex(row.get("strikeout_color"), "#000000")})
        if int(row.get("shadow_offset_x") or 0) or int(row.get("shadow_offset_y") or 0):
            ET.SubElement(
                char_pr,
                _hh("shadow"),
                {
                    "type": "DROP",
                    "color": _color_hex(row.get("shadow_color"), "#000000"),
                    "offsetX": str(_clamp_int(row.get("shadow_offset_x"), 0, -100, 100)),
                    "offsetY": str(_clamp_int(row.get("shadow_offset_y"), 0, -100, 100)),
                },
            )


def _list_definition_ids(decoded_docinfo: dict[str, Any], key: str) -> set[int]:
    rows = decoded_docinfo.get(key) if isinstance(decoded_docinfo.get(key), list) else []
    ids = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_id = _int_or_none(row.get("index"))
        if row_id is not None:
            ids.add(row_id)
    return ids


def _resolve_list_ref(row: dict[str, Any], decoded_docinfo: dict[str, Any]) -> dict[str, Any]:
    raw_id = _int_or_none(row.get("numbering_bullet_id"))
    heading_type = _int_or_none(row.get("heading_type")) or 0
    level = _int_or_none(row.get("level")) or 0
    numbering_ids = _list_definition_ids(decoded_docinfo, "numberings")
    bullet_ids = _list_definition_ids(decoded_docinfo, "bullets")
    if (raw_id is None or raw_id <= 0) and heading_type and 0 in numbering_ids:
        return {
            "status": "APPLIED",
            "kind": "numbering",
            "heading_type": "OUTLINE",
            "id_ref": 0,
            "raw_id": raw_id,
            "level": level,
            "implicit_default": True,
        }
    if raw_id is None or raw_id <= 0:
        return {
            "status": "NOT_APPLIED",
            "raw_id": raw_id,
            "heading_type": heading_type,
            "level": level,
            "reason": "NO_NUMBERING_BULLET_ID",
        }
    candidates = [raw_id - 1, raw_id]
    for candidate in candidates:
        if candidate in numbering_ids:
            return {
                "status": "APPLIED",
                "kind": "numbering",
                "heading_type": "OUTLINE",
                "id_ref": candidate,
                "raw_id": raw_id,
                "level": level,
            }
    for candidate in candidates:
        if candidate in bullet_ids:
            return {
                "status": "APPLIED",
                "kind": "bullet",
                "heading_type": "BULLET",
                "id_ref": candidate,
                "raw_id": raw_id,
                "level": level,
            }
    return {
        "status": "UNRESOLVED",
        "raw_id": raw_id,
        "heading_type": heading_type,
        "level": level,
        "numbering_ids": sorted(numbering_ids),
        "bullet_ids": sorted(bullet_ids),
    }


def _append_para_properties(ref_list: ET.Element, decoded_docinfo: dict[str, Any]) -> None:
    shapes = decoded_docinfo.get("para_shapes") if isinstance(decoded_docinfo.get("para_shapes"), list) else []
    border_fill_ids = _border_fill_ids(decoded_docinfo)
    container = ET.SubElement(ref_list, _hh("paraProperties"), {"itemCnt": str(max(1, len(shapes)))})
    source_rows = shapes or [{"index": 0, "align": 0, "line_spacing": 160, "margins": {}, "border_fill_id": 0, "tab_def_id": 0, "border_spacing": {}}]
    for row in source_rows:
        para_pr = ET.SubElement(
            container,
            _hh("paraPr"),
            {
                "id": str(row.get("index", 0)),
                "tabPrIDRef": str(row.get("tab_def_id") or 0),
                "condense": "0",
                "fontLineHeight": "0",
                "snapToGrid": "1",
                "suppressLineNumbers": "0",
                "checked": "0",
            },
        )
        ET.SubElement(para_pr, _hh("align"), {"horizontal": _para_align(row.get("align")), "vertical": "BASELINE"})
        list_ref = _resolve_list_ref(row, decoded_docinfo) if isinstance(row, dict) else {"status": "NOT_APPLIED"}
        if list_ref.get("status") == "APPLIED":
            ET.SubElement(
                para_pr,
                _hh("heading"),
                {
                    "type": str(list_ref.get("heading_type")),
                    "idRef": str(list_ref.get("id_ref")),
                    "level": str(list_ref.get("level") or 0),
                },
            )
        else:
            ET.SubElement(para_pr, _hh("heading"), {"type": "NONE", "idRef": "0", "level": str(row.get("level") or 0)})
        ET.SubElement(
            para_pr,
            _hh("breakSetting"),
            {
                "breakLatinWord": _break_latin_word(row.get("line_break_latin")),
                "breakNonLatinWord": _break_non_latin_word(row.get("line_break_hangul")),
                "widowOrphan": "0",
                "keepWithNext": "0",
                "keepLines": "0",
                "pageBreakBefore": "0",
                "lineWrap": "BREAK",
            },
        )
        margins = row.get("margins") if isinstance(row.get("margins"), dict) else {}
        margin = ET.SubElement(para_pr, _hh("margin"))
        ET.SubElement(margin, _hh("intent"), _hwp_value(margins.get("indent", 0)))
        ET.SubElement(margin, _hh("left"), _hwp_value(margins.get("left", 0)))
        ET.SubElement(margin, _hh("right"), _hwp_value(margins.get("right", 0)))
        ET.SubElement(margin, _hh("prev"), _hwp_value(margins.get("before", 0)))
        ET.SubElement(margin, _hh("next"), _hwp_value(margins.get("after", 0)))
        ET.SubElement(
            para_pr,
            _hh("lineSpacing"),
            {
                "type": _line_spacing_type(row.get("line_spacing_type")),
                "value": str(row.get("line_spacing") or row.get("line_spacing_legacy") or 160),
                "unit": "HWPUNIT",
            },
        )
        border_spacing = row.get("border_spacing") if isinstance(row.get("border_spacing"), dict) else {}
        ET.SubElement(
            para_pr,
                _hh("border"),
                {
                    "borderFillIDRef": _border_fill_ref(row.get("border_fill_id"), border_fill_ids),
                "offsetLeft": str(border_spacing.get("left", 0) or 0),
                "offsetRight": str(border_spacing.get("right", 0) or 0),
                "offsetTop": str(border_spacing.get("top", 0) or 0),
                "offsetBottom": str(border_spacing.get("bottom", 0) or 0),
                "connect": "0",
                "ignoreMargin": "0",
            },
        )
        ET.SubElement(para_pr, _hh("autoSpacing"), {"eAsianEng": "0", "eAsianNum": "0"})


def _append_numberings(ref_list: ET.Element, decoded_docinfo: dict[str, Any]) -> None:
    numberings = decoded_docinfo.get("numberings") if isinstance(decoded_docinfo.get("numberings"), list) else []
    if not numberings:
        return
    container = ET.SubElement(ref_list, _hh("numberings"), {"itemCnt": str(len(numberings))})
    for row in numberings:
        numbering = ET.SubElement(
            container,
            _hh("numbering"),
            {
                "id": str(row.get("index", 0)),
                "start": str(row.get("start", 0) or 0),
            },
        )
        levels = row.get("levels") if isinstance(row.get("levels"), list) else []
        for level_row in levels:
            if not isinstance(level_row, dict):
                continue
            try:
                level = max(1, int(level_row.get("level") or 1))
            except (TypeError, ValueError):
                level = 1
            text = str(level_row.get("text") or f"^{level}.")
            para_head = ET.SubElement(
                numbering,
                _hh("paraHead"),
                {
                    "start": str(level_row.get("start", 1) or 1),
                    "level": str(level),
                    "align": "LEFT",
                    "useInstWidth": "1",
                    "autoIndent": "1",
                    "widthAdjust": "0",
                    "textOffsetType": "PERCENT",
                    "textOffset": str(level_row.get("text_offset", 50) or 50),
                    "numFormat": str(level_row.get("num_format") or number_text_format(text)),
                    "charPrIDRef": str(level_row.get("char_shape_id", 4294967295)),
                    "checkable": "0",
                },
            )
            para_head.text = text


def _append_bullets(ref_list: ET.Element, decoded_docinfo: dict[str, Any]) -> None:
    bullets = decoded_docinfo.get("bullets") if isinstance(decoded_docinfo.get("bullets"), list) else []
    if not bullets:
        return
    container = ET.SubElement(ref_list, _hh("bullets"), {"itemCnt": str(len(bullets))})
    for row in bullets:
        bullet = ET.SubElement(
            container,
            _hh("bullet"),
            {
                "id": str(row.get("index", 0)),
                "charPrIDRef": str(row.get("char_shape_id", 0) or 0),
                "checkable": "0",
            },
        )
        bullet.text = str(row.get("bullet_char") or "")


def _append_styles(ref_list: ET.Element, decoded_docinfo: dict[str, Any]) -> None:
    styles = decoded_docinfo.get("styles") if isinstance(decoded_docinfo.get("styles"), list) else []
    container = ET.SubElement(ref_list, _hh("styles"), {"itemCnt": str(max(1, len(styles)))})
    source_rows = styles or [{"index": 0, "name": "바탕글", "english_name": "Normal", "style_type": 0, "para_shape_id": 0, "char_shape_id": 0}]
    for row in source_rows:
        ET.SubElement(
            container,
            _hh("style"),
            {
                "id": str(row.get("index", 0)),
                "type": "PARA" if int(row.get("style_type") or 0) == 0 else "CHAR",
                "name": str(row.get("name") or "바탕글"),
                "engName": str(row.get("english_name") or "Normal"),
                "paraPrIDRef": str(row.get("para_shape_id") or 0),
                "charPrIDRef": str(row.get("char_shape_id") or 0),
                "nextStyleIDRef": str(row.get("next_style_id") or 0),
                "langID": str(row.get("language_id") or 1042),
            },
        )


def build_decoded_header_xml(decoded_docinfo: dict[str, Any]) -> str:
    root = ET.Element(_hh("head"))
    _append_begin_num(root, decoded_docinfo)
    ref_list = ET.SubElement(root, _hh("refList"))
    _append_fontfaces(ref_list, decoded_docinfo)
    _append_border_fills(ref_list, decoded_docinfo)
    _append_char_properties(ref_list, decoded_docinfo)
    _append_para_properties(ref_list, decoded_docinfo)
    _append_numberings(ref_list, decoded_docinfo)
    _append_bullets(ref_list, decoded_docinfo)
    _append_styles(ref_list, decoded_docinfo)
    return _xml_string(root)


def decoded_header_summary(decoded_docinfo: dict[str, Any]) -> dict[str, Any]:
    counts = decoded_docinfo.get("counts") if isinstance(decoded_docinfo.get("counts"), dict) else {}
    props = decoded_docinfo.get("document_properties") if isinstance(decoded_docinfo.get("document_properties"), dict) else {}
    mappings = decoded_docinfo.get("id_mappings") if isinstance(decoded_docinfo.get("id_mappings"), dict) else {}
    return {
        "document_properties": 1 if props else 0,
        "document_section_count": props.get("section_count"),
        "begin_num": {
            "page": props.get("page_start"),
            "footnote": props.get("footnote_start"),
            "endnote": props.get("endnote_start"),
            "pic": props.get("picture_start"),
            "tbl": props.get("table_start"),
            "equation": props.get("equation_start"),
        } if props else None,
        "id_mappings": 1 if mappings else 0,
        "id_mapping_raw_count": mappings.get("raw_count"),
        "binary_data": int(counts.get("binary_data") or 0),
        "fontfaces": int(counts.get("face_names") or 0),
        "border_fills": int(counts.get("border_fills") or 0),
        "char_properties": int(counts.get("char_shapes") or 0),
        "para_properties": int(counts.get("para_shapes") or 0),
        "numberings": int(counts.get("numberings") or 0),
        "bullets": int(counts.get("bullets") or 0),
        "styles": int(counts.get("styles") or 0),
    }


def build_list_style_mapping(decoded_docinfo: dict[str, Any]) -> dict[str, Any]:
    numberings = decoded_docinfo.get("numberings") if isinstance(decoded_docinfo.get("numberings"), list) else []
    bullets = decoded_docinfo.get("bullets") if isinstance(decoded_docinfo.get("bullets"), list) else []
    para_shapes = decoded_docinfo.get("para_shapes") if isinstance(decoded_docinfo.get("para_shapes"), list) else []
    referenced_para_shapes = []
    applied_para_shape_count = 0
    unresolved_para_shape_count = 0
    for row in para_shapes:
        if not isinstance(row, dict):
            continue
        list_id = row.get("numbering_bullet_id")
        heading_type = row.get("heading_type")
        level = row.get("level")
        if list_id or heading_type:
            resolved = _resolve_list_ref(row, decoded_docinfo)
            if resolved.get("status") == "APPLIED":
                applied_para_shape_count += 1
            elif resolved.get("status") == "UNRESOLVED":
                unresolved_para_shape_count += 1
            referenced_para_shapes.append(
                {
                    "para_shape_id": row.get("index"),
                    "heading_type": heading_type,
                    "level": level,
                    "numbering_bullet_id": list_id,
                    "mapping": resolved,
                }
            )
    return {
        "status": "PASS" if numberings or bullets or referenced_para_shapes else "NO_LIST_STYLES",
        "numbering_count": len(numberings),
        "bullet_count": len(bullets),
        "referenced_para_shape_count": len(referenced_para_shapes),
        "applied_para_shape_count": applied_para_shape_count,
        "unresolved_para_shape_count": unresolved_para_shape_count,
        "numberings": numberings,
        "bullets": bullets,
        "referenced_para_shapes": referenced_para_shapes,
        "full_fidelity": False,
        "warning": "NUMBERING/BULLET definitions are emitted to header.xml; paragraph properties are linked only when IDs resolve conservatively.",
    }
