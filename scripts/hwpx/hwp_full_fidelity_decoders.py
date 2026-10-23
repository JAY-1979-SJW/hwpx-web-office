"""Binary HWP record decoders used by the full-fidelity converter workbench."""

from __future__ import annotations

import hashlib
from typing import Any


LANGUAGE_SLOTS = ["hangul", "latin", "hanja", "japanese", "other", "symbol", "user"]
BORDER_SIDES = ["left", "right", "top", "bottom"]
ID_MAPPING_NAMES = [
    "binary_data",
    "hangul_font",
    "latin_font",
    "hanja_font",
    "japanese_font",
    "other_font",
    "symbol_font",
    "user_font",
    "border_fill",
    "char_shape",
    "tab_def",
    "numbering",
    "bullet",
    "para_shape",
    "style",
    "memo_shape",
    "track_change",
    "track_change_author",
]


def _u8(data: bytes, offset: int, default: int = 0) -> int:
    return data[offset] if offset < len(data) else default


def _i8(data: bytes, offset: int, default: int = 0) -> int:
    if offset >= len(data):
        return default
    value = data[offset]
    return value - 256 if value > 127 else value


def _u16(data: bytes, offset: int, default: int = 0) -> int:
    if offset + 2 > len(data):
        return default
    return int.from_bytes(data[offset : offset + 2], "little", signed=False)


def _i16(data: bytes, offset: int, default: int = 0) -> int:
    if offset + 2 > len(data):
        return default
    return int.from_bytes(data[offset : offset + 2], "little", signed=True)


def _u32(data: bytes, offset: int, default: int = 0) -> int:
    if offset + 4 > len(data):
        return default
    return int.from_bytes(data[offset : offset + 4], "little", signed=False)


def _i32(data: bytes, offset: int, default: int = 0) -> int:
    if offset + 4 > len(data):
        return default
    return int.from_bytes(data[offset : offset + 4], "little", signed=True)


def _colorref(data: bytes, offset: int) -> dict[str, Any]:
    raw = _u32(data, offset)
    return {
        "raw": raw,
        "r": raw & 0xFF,
        "g": (raw >> 8) & 0xFF,
        "b": (raw >> 16) & 0xFF,
        "hex": f"#{raw & 0xFF:02x}{(raw >> 8) & 0xFF:02x}{(raw >> 16) & 0xFF:02x}",
    }


def _read_wchar_string(data: bytes, offset: int) -> tuple[str, int]:
    length = _u16(data, offset)
    start = offset + 2
    end = min(len(data), start + length * 2)
    text = data[start:end].decode("utf-16le", errors="replace")
    return text.rstrip("\x00"), end


def _hwp_line_style_type2(value: Any) -> str:
    try:
        raw = int(value)
    except (TypeError, ValueError):
        raw = 0
    return {
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
    }.get(raw, "SOLID")


def _hwp_line_width(value: Any) -> str:
    try:
        raw = int(value)
    except (TypeError, ValueError):
        raw = 1
    return {
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
    }.get(raw, "0.12 mm")


def _slash_type(value: int) -> str:
    return {
        0: "NONE",
        2: "CENTER",
        3: "CENTER_BELOW",
        6: "CENTER_ABOVE",
        7: "ALL",
    }.get(value, "NONE")


def _slash_shape(value: int, crooked: int, is_counter: bool) -> dict[str, Any]:
    return {
        "type_raw": value,
        "type": _slash_type(value),
        "crooked": bool(crooked),
        "is_counter": bool(is_counter),
    }


def _hatch_style(value: Any) -> str | None:
    try:
        raw = int(value)
    except (TypeError, ValueError):
        raw = 0
    return {
        1: "HORIZONTAL",
        2: "VERTICAL",
        3: "BACK_SLASH",
        4: "SLASH",
        5: "CROSS",
        6: "CROSS_DIAGONAL",
    }.get(raw)


def _gradient_type(value: Any) -> str:
    try:
        raw = int(value)
    except (TypeError, ValueError):
        raw = 1
    return {1: "LINEAR", 2: "RADIAL", 3: "CONICAL", 4: "SQUARE"}.get(raw, "LINEAR")


def _image_fill_mode(value: Any) -> str:
    try:
        raw = int(value)
    except (TypeError, ValueError):
        raw = 0
    return {
        0: "TILE",
        1: "TILE_HORZ_TOP",
        2: "TILE_HORZ_BOTTOM",
        3: "TILE_VERT_LEFT",
        4: "TILE_VERT_RIGHT",
        5: "TOTAL",
        6: "CENTER",
        7: "CENTER_TOP",
        8: "CENTER_BOTTOM",
        9: "LEFT_CENTER",
        10: "LEFT_TOP",
        11: "LEFT_BOTTOM",
        12: "RIGHT_CENTER",
        13: "RIGHT_TOP",
        14: "RIGHT_BOTTOM",
        15: "ZOOM",
    }.get(raw, "TILE")


def _wchar(data: bytes, offset: int) -> str:
    value = _u16(data, offset)
    if value == 0:
        return ""
    return chr(value) if value <= 0x10FFFF else ""


def decode_document_properties(payload: bytes) -> dict[str, Any]:
    fields = [
        "section_count",
        "page_start",
        "footnote_start",
        "endnote_start",
        "picture_start",
        "table_start",
        "equation_start",
    ]
    decoded = {name: _u16(payload, index * 2) for index, name in enumerate(fields)}
    decoded["caret_list_id"] = _u32(payload, 14)
    decoded["caret_para_id"] = _u32(payload, 18)
    decoded["caret_char_pos"] = _u32(payload, 22)
    return decoded


def decode_id_mappings(payload: bytes) -> dict[str, Any]:
    counts = [_i32(payload, index * 4) for index in range(min(18, len(payload) // 4))]
    return {
        "counts": {
            ID_MAPPING_NAMES[index] if index < len(ID_MAPPING_NAMES) else f"mapping_{index}": count
            for index, count in enumerate(counts)
        },
        "raw_count": len(counts),
    }


def _binary_data_type(value: int) -> str:
    return {0: "LINK", 1: "EMBEDDING", 2: "STORAGE"}.get(value & 0x0F, "EMBEDDING")


def _binary_compression(value: int) -> str:
    return {0: "DEFAULT", 1: "COMPRESS", 2: "NO_COMPRESS"}.get((value >> 4) & 0x03, "DEFAULT")


def _binary_state(value: int) -> str:
    return {
        0: "NOT_ACCESSED",
        1: "ACCESS_SUCCESS",
        2: "ACCESS_FAILED",
        3: "ACCESS_IGNORED",
    }.get((value >> 8) & 0x03, "NOT_ACCESSED")


def _bindata_stream_name(storage_id: int | None, extension: str | None = None) -> str | None:
    if storage_id is None:
        return None
    ext = (extension or "bin").strip().lstrip(".") or "bin"
    return f"BinData/BIN{storage_id:04X}.{ext}"


def _alternate_font_type(value: int) -> str:
    return {0: "UNKNOWN", 1: "TTF", 2: "HFT"}.get(value, "UNKNOWN")


def _font_kind(value: int) -> str:
    return {
        0: "UNKNOWN",
        1: "TTF",
        2: "HFT",
        3: "BOTH",
    }.get(value, "UNKNOWN")


def decode_binary_data(payload: bytes) -> dict[str, Any]:
    properties = _u16(payload, 0)
    offset = 2
    data_type = _binary_data_type(properties)
    decoded: dict[str, Any] = {
        "property": properties,
        "data_type": data_type,
        "compression": _binary_compression(properties),
        "state": _binary_state(properties),
        "payload_size": len(payload),
        "payload_prefix_hex": payload[:32].hex(" "),
    }
    if data_type == "LINK":
        absolute_path, offset = _read_wchar_string(payload, offset)
        relative_path, offset = _read_wchar_string(payload, offset)
        decoded.update(
            {
                "absolute_path": absolute_path,
                "relative_path": relative_path,
                "consumed": offset,
            }
        )
    elif data_type == "EMBEDDING":
        storage_id = _u16(payload, offset)
        offset += 2
        extension, offset = _read_wchar_string(payload, offset)
        decoded.update(
            {
                "storage_id": storage_id,
                "extension": extension,
                "stream_name": _bindata_stream_name(storage_id, extension),
                "manifest_id": f"BIN{storage_id:04X}",
                "consumed": offset,
            }
        )
    else:
        storage_id = _u16(payload, offset)
        offset += 2
        decoded.update(
            {
                "storage_id": storage_id,
                "stream_name": _bindata_stream_name(storage_id, "bin"),
                "manifest_id": f"BIN{storage_id:04X}",
                "consumed": offset,
            }
        )
    return decoded


def decode_face_name(payload: bytes) -> dict[str, Any]:
    offset = 0
    flags = _u8(payload, offset)
    offset += 1
    name, offset = _read_wchar_string(payload, offset)
    decoded: dict[str, Any] = {
        "flags": flags,
        "has_alternate_font": bool(flags & 0x80),
        "has_font_type_info": bool(flags & 0x40),
        "has_base_font": bool(flags & 0x20),
        "name": name,
    }
    if decoded["has_alternate_font"] and offset < len(payload):
        decoded["alternate_type"] = _u8(payload, offset)
        decoded["alternate_type_name"] = _alternate_font_type(int(decoded["alternate_type"]))
        offset += 1
        decoded["alternate_name"], offset = _read_wchar_string(payload, offset)
    if decoded["has_font_type_info"] and offset + 10 <= len(payload):
        type_info = list(payload[offset : offset + 10])
        decoded["type_info"] = type_info
        decoded["type_info_names"] = [_font_kind(value) for value in type_info]
        decoded["font_type"] = next((name for name in decoded["type_info_names"] if name != "UNKNOWN"), "TTF")
        offset += 10
    if decoded["has_base_font"] and offset < len(payload):
        decoded["base_font"], offset = _read_wchar_string(payload, offset)
    decoded["consumed"] = offset
    decoded["payload_size"] = len(payload)
    return decoded


def decode_border_fill(payload: bytes) -> dict[str, Any]:
    properties = _u16(payload, 0)
    border_types = list(payload[2:6])
    border_widths = list(payload[6:10])
    border_colors = [_colorref(payload, 10 + index * 4) for index in range(4)]
    borders = {
        side: {
            "type_raw": border_types[index] if index < len(border_types) else 0,
            "type": _hwp_line_style_type2(border_types[index] if index < len(border_types) else 0),
            "width_raw": border_widths[index] if index < len(border_widths) else 1,
            "width": _hwp_line_width(border_widths[index] if index < len(border_widths) else 1),
            "color": border_colors[index] if index < len(border_colors) else _colorref(b"", 0),
        }
        for index, side in enumerate(BORDER_SIDES)
    }
    diagonal_raw = {
        "slash_type_raw": (properties >> 2) & 0x07,
        "back_slash_type_raw": (properties >> 5) & 0x07,
        "slash_crooked_raw": (properties >> 8) & 0x03,
        "back_slash_crooked": bool(properties & (1 << 10)),
        "slash_counter": bool(properties & (1 << 11)),
        "back_slash_counter": bool(properties & (1 << 12)),
        "center_line": bool(properties & (1 << 13)),
    }
    diagonal_type = _u8(payload, 26)
    diagonal_width = _u8(payload, 27)
    decoded: dict[str, Any] = {
        "property": properties,
        "three_d": bool(properties & 0x01),
        "shadow": bool(properties & 0x02),
        "slash": _slash_shape(diagonal_raw["slash_type_raw"], diagonal_raw["slash_crooked_raw"], diagonal_raw["slash_counter"]),
        "back_slash": _slash_shape(diagonal_raw["back_slash_type_raw"], 1 if diagonal_raw["back_slash_crooked"] else 0, diagonal_raw["back_slash_counter"]),
        "center_line_present": diagonal_raw["center_line"],
        "diagonal_flags": diagonal_raw,
        "border_types": border_types,
        "border_widths": border_widths,
        "border_colors": border_colors,
        "borders": borders,
        "diagonal_type": diagonal_type,
        "diagonal_type_name": _hwp_line_style_type2(diagonal_type),
        "diagonal_width": diagonal_width,
        "diagonal_width_name": _hwp_line_width(diagonal_width),
        "diagonal_color": _colorref(payload, 28),
        "fill": {"type": _u32(payload, 32) if len(payload) >= 36 else None},
        "payload_size": len(payload),
    }
    fill_type = decoded["fill"]["type"]
    if isinstance(fill_type, int):
        offset = 36
        decoded["fill"]["has_solid"] = bool(fill_type & 0x1)
        decoded["fill"]["has_image"] = bool(fill_type & 0x2)
        decoded["fill"]["has_gradient"] = bool(fill_type & 0x4)
        if fill_type & 0x1 and offset + 12 <= len(payload):
            decoded["fill"]["solid"] = {
                "background": _colorref(payload, offset),
                "pattern": _colorref(payload, offset + 4),
                "pattern_type": _i32(payload, offset + 8),
                "pattern_name": _hatch_style(_i32(payload, offset + 8)),
            }
            offset += 12
        if fill_type & 0x4 and offset + 12 <= len(payload):
            color_count = max(0, _i16(payload, offset + 10))
            gradient: dict[str, Any] = {
                "type_raw": _i16(payload, offset),
                "type": _gradient_type(_i16(payload, offset)),
                "angle": _i16(payload, offset + 2),
                "center_x": _i16(payload, offset + 4),
                "center_y": _i16(payload, offset + 6),
                "step": _i16(payload, offset + 8),
                "color_count": color_count,
                "colors": [],
            }
            offset += 12
            if color_count > 2 and offset + 4 * color_count <= len(payload):
                gradient["positions"] = [_i32(payload, offset + index * 4) for index in range(color_count)]
                offset += 4 * color_count
            if offset + 4 * color_count <= len(payload):
                gradient["colors"] = [_colorref(payload, offset + index * 4) for index in range(color_count)]
                offset += 4 * color_count
            decoded["fill"]["gradient"] = gradient
        if fill_type & 0x2 and offset + 6 <= len(payload):
            decoded["fill"]["image"] = {
                "mode_raw": _u8(payload, offset),
                "mode": _image_fill_mode(_u8(payload, offset)),
                "brightness": _i8(payload, offset + 1),
                "contrast": _i8(payload, offset + 2),
                "effect": _u8(payload, offset + 3),
                "binary_data_id": _u16(payload, offset + 4),
            }
            offset += 6
        if offset + 4 <= len(payload):
            extra_size = _u32(payload, offset)
            decoded["fill"]["extra_size"] = extra_size
            offset += 4
            if extra_size and offset + extra_size <= len(payload):
                if "gradient" in decoded["fill"] and extra_size >= 1:
                    decoded["fill"]["gradient"]["step_center"] = _u8(payload, offset)
                decoded["fill"]["extra_hex"] = payload[offset : offset + extra_size].hex(" ")
    return decoded


def decode_char_shape(payload: bytes) -> dict[str, Any]:
    face_ids = [_u16(payload, index * 2) for index in range(7)]
    ratios = [_u8(payload, 14 + index) for index in range(7)]
    spacings = [_i8(payload, 21 + index) for index in range(7)]
    relative_sizes = [_u8(payload, 28 + index) for index in range(7)]
    offsets = [_i8(payload, 35 + index) for index in range(7)]
    attrs = _u32(payload, 46)
    return {
        "face_ids": dict(zip(LANGUAGE_SLOTS, face_ids)),
        "ratios": dict(zip(LANGUAGE_SLOTS, ratios)),
        "spacings": dict(zip(LANGUAGE_SLOTS, spacings)),
        "relative_sizes": dict(zip(LANGUAGE_SLOTS, relative_sizes)),
        "offsets": dict(zip(LANGUAGE_SLOTS, offsets)),
        "base_size_hwpunit": _i32(payload, 42),
        "base_size_pt": round(_i32(payload, 42) / 100.0, 2),
        "attributes": attrs,
        "bold": bool(attrs & 0x2),
        "italic": bool(attrs & 0x1),
        "underline_type": (attrs >> 2) & 0x3,
        "strikeout_type": (attrs >> 18) & 0x7,
        "shadow_offset_x": _i8(payload, 50),
        "shadow_offset_y": _i8(payload, 51),
        "text_color": _colorref(payload, 52),
        "underline_color": _colorref(payload, 56),
        "shade_color": _colorref(payload, 60),
        "shadow_color": _colorref(payload, 64),
        "border_fill_id": _u16(payload, 68) if len(payload) >= 70 else None,
        "strikeout_color": _colorref(payload, 70) if len(payload) >= 74 else None,
        "payload_size": len(payload),
    }


def decode_tab_def(payload: bytes) -> dict[str, Any]:
    count = _i16(payload, 4)
    tabs = []
    offset = 6
    for _index in range(max(0, count)):
        if offset + 8 > len(payload):
            break
        tabs.append(
            {
                "position": _i32(payload, offset),
                "type": _u8(payload, offset + 4),
                "leader": _u8(payload, offset + 5),
            }
        )
        offset += 8
    return {
        "property": _u32(payload, 0),
        "count": count,
        "tabs": tabs,
        "payload_size": len(payload),
    }


def number_text_format(text: str) -> str:
    if "^" in text:
        return "DIGIT"
    if text:
        return "USER_CHAR"
    return "DIGIT"


def decode_numbering(payload: bytes) -> dict[str, Any]:
    levels = []
    offset = 0
    for level_index in range(1, 8):
        if offset + 14 > len(payload):
            break
        property_value = _u32(payload, offset)
        reserved = _u16(payload, offset + 4)
        text_offset = _u16(payload, offset + 6)
        char_shape_id = _u32(payload, offset + 8)
        text, next_offset = _read_wchar_string(payload, offset + 12)
        if next_offset <= offset + 12:
            break
        levels.append(
            {
                "level": level_index,
                "property": property_value,
                "reserved": reserved,
                "text_offset": text_offset,
                "char_shape_id": char_shape_id,
                "text": text,
                "num_format": number_text_format(text),
            }
        )
        offset = next_offset
    return {
        "levels": levels,
        "level_count": len(levels),
        "consumed": offset,
        "payload_size": len(payload),
        "payload_prefix_hex": payload[:48].hex(" "),
    }


def _utf16le_text(payload: bytes, offset: int, length: int) -> str:
    if length <= 0 or offset < 0:
        return ""
    end = min(len(payload), offset + length * 2)
    return payload[offset:end].decode("utf-16le", errors="ignore").rstrip("\x00")


def decode_eqedit(payload: bytes) -> dict[str, Any]:
    formula_len = _u16(payload, 4) if len(payload) >= 6 else 0
    version_marker = "Equation Version".encode("utf-16le")
    version_offset = payload.find(version_marker)
    if version_offset >= 14:
        formula_end = version_offset - 14
        formula = payload[8:formula_end].decode("utf-16le", errors="ignore").rstrip("\x00")
        offset = formula_end
    else:
        formula = _utf16le_text(payload, 8, max(0, formula_len - 1)) if len(payload) >= 8 else ""
        offset = 8 + max(0, formula_len - 1) * 2
    options_hex = payload[offset : min(len(payload), offset + 12)].hex(" ") if offset < len(payload) else ""
    version = ""
    application = ""
    if version_offset >= 2:
        version_len = _u16(payload, version_offset - 2)
        version = _utf16le_text(payload, version_offset, version_len)
        app_offset = version_offset + version_len * 2
        if app_offset + 2 <= len(payload):
            app_len = _u16(payload, app_offset)
            application = _utf16le_text(payload, app_offset + 2, app_len)
    elif offset + 14 <= len(payload):
        version_len = _u16(payload, offset + 12)
        version = _utf16le_text(payload, offset + 14, version_len)
        app_offset = offset + 14 + version_len * 2
        if app_offset + 2 <= len(payload):
            app_len = _u16(payload, app_offset)
            application = _utf16le_text(payload, app_offset + 2, app_len)
    return {
        "formula": formula,
        "formula_length": formula_len,
        "options_hex": options_hex,
        "version": version,
        "application": application,
        "payload_size": len(payload),
        "payload_prefix_hex": payload[:48].hex(" "),
        "preservation": "formula_text_and_payload_metadata",
    }


def decode_bullet(payload: bytes) -> dict[str, Any]:
    candidates = []
    for offset in range(0, min(len(payload), 24), 2):
        length = _u16(payload, offset)
        if 0 < length <= 32 and offset + 2 + length * 2 <= len(payload):
            text, next_offset = _read_wchar_string(payload, offset)
            if text:
                candidates.append({"offset": offset, "text": text, "next_offset": next_offset})
    return {
        "property": _u32(payload, 0),
        "char_shape_id": _u32(payload, 4) if len(payload) >= 8 else None,
        "bullet_char": candidates[0]["text"] if candidates else "",
        "text_candidates": candidates[:5],
        "payload_size": len(payload),
        "payload_prefix_hex": payload[:48].hex(" "),
    }


def decode_para_shape(payload: bytes) -> dict[str, Any]:
    attr1 = _u32(payload, 0)
    attr2 = _u32(payload, 46)
    attr3 = _u32(payload, 50)
    return {
        "attributes1": attr1,
        "align": (attr1 >> 2) & 0x7,
        "line_spacing_type_legacy": attr1 & 0x3,
        "line_break_latin": (attr1 >> 5) & 0x3,
        "line_break_hangul": (attr1 >> 7) & 0x1,
        "heading_type": (attr1 >> 23) & 0x3,
        "level": (attr1 >> 25) & 0x7,
        "margins": {
            "left": _i32(payload, 4),
            "right": _i32(payload, 8),
            "indent": _i32(payload, 12),
            "before": _i32(payload, 16),
            "after": _i32(payload, 20),
        },
        "line_spacing_legacy": _i32(payload, 24),
        "tab_def_id": _u16(payload, 28),
        "numbering_bullet_id": _u16(payload, 30),
        "border_fill_id": _u16(payload, 32),
        "border_spacing": {
            "left": _i16(payload, 34),
            "right": _i16(payload, 36),
            "top": _i16(payload, 38),
            "bottom": _i16(payload, 40),
        },
        "attributes2": attr2,
        "attributes3": attr3,
        "line_spacing": _i32(payload, 54) if len(payload) >= 58 else _i32(payload, 50),
        "line_spacing_type": attr3 & 0x1F,
        "payload_size": len(payload),
    }


def decode_style(payload: bytes) -> dict[str, Any]:
    name, offset = _read_wchar_string(payload, 0)
    english_name, offset = _read_wchar_string(payload, offset)
    return {
        "name": name,
        "english_name": english_name,
        "style_type": _u8(payload, offset) & 0x7 if offset < len(payload) else None,
        "next_style_id": _u8(payload, offset + 1) if offset + 1 < len(payload) else None,
        "language_id": _i16(payload, offset + 2) if offset + 4 <= len(payload) else None,
        "para_shape_id": _u16(payload, offset + 4) if offset + 6 <= len(payload) else None,
        "char_shape_id": _u16(payload, offset + 6) if offset + 8 <= len(payload) else None,
        "payload_size": len(payload),
    }


def _raw_payload_audit(payload: bytes) -> dict[str, Any]:
    return {
        "payload_size": len(payload),
        "payload_sha256": hashlib.sha256(payload).hexdigest(),
        "payload_prefix_hex": payload[:32].hex(" "),
    }


def decode_distribute_doc_data(payload: bytes) -> dict[str, Any]:
    decoded = _raw_payload_audit(payload)
    decoded.update({"expected_size": 256, "size_matches_spec": len(payload) == 256})
    return decoded


def decode_compatible_document(payload: bytes) -> dict[str, Any]:
    target = _u32(payload, 0)
    decoded = _raw_payload_audit(payload)
    decoded.update(
        {
            "target_program_raw": target,
            "target_program": {0: "HWP_CURRENT", 1: "HWP_2007", 2: "MS_WORD"}.get(target, "UNKNOWN"),
        }
    )
    return decoded


def decode_layout_compatibility(payload: bytes) -> dict[str, Any]:
    decoded = _raw_payload_audit(payload)
    decoded.update(
        {
            "flags": {
                "character_format": _u32(payload, 0),
                "paragraph_format": _u32(payload, 4),
                "section_format": _u32(payload, 8),
                "object_format": _u32(payload, 12),
                "field_format": _u32(payload, 16),
            },
            "size_matches_spec": len(payload) >= 20,
        }
    )
    return decoded


def decode_track_change_info(payload: bytes) -> dict[str, Any]:
    flags = _u32(payload, 0)
    decoded = _raw_payload_audit(payload)
    decoded.update(
        {
            "flags": flags,
            "enabled": bool(flags & 0x01),
            "show_changes": bool(flags & 0x02),
            "expected_size": 1032,
            "size_matches_spec": len(payload) == 1032,
        }
    )
    return decoded


def decode_memo_shape(payload: bytes) -> dict[str, Any]:
    decoded = _raw_payload_audit(payload)
    decoded.update(
        {
            "border_color": _colorref(payload, 0),
            "fill_color": _colorref(payload, 4),
            "hatch_color": _colorref(payload, 8),
            "width": _u32(payload, 12),
            "memo_index": _u32(payload, 16),
            "line_type": _u8(payload, 20),
            "line_style": _u8(payload, 21),
            "expected_size": 22,
            "size_matches_spec": len(payload) == 22,
        }
    )
    return decoded


def decode_forbidden_char(payload: bytes) -> dict[str, Any]:
    line_start_chars, offset = _read_wchar_string(payload, 0)
    line_end_chars, _ = _read_wchar_string(payload, offset)
    decoded = _raw_payload_audit(payload)
    decoded.update({"line_start_chars": line_start_chars, "line_end_chars": line_end_chars})
    return decoded


def decode_track_change_content(payload: bytes) -> dict[str, Any]:
    change_type = _u8(payload, 0)
    decoded = _raw_payload_audit(payload)
    decoded.update(
        {
            "change_type_raw": change_type,
            "change_type": {0: "INSERT", 1: "DELETE", 2: "FORMAT"}.get(change_type, "UNKNOWN"),
            "author_index": _u16(payload, 1),
            "timestamp": _u32(payload, 3),
        }
    )
    return decoded


def decode_track_change_author(payload: bytes) -> dict[str, Any]:
    name, offset = _read_wchar_string(payload, 0)
    decoded = _raw_payload_audit(payload)
    decoded.update({"name": name, "author_id": _u32(payload, offset)})
    return decoded


def decode_para_header(payload: bytes) -> dict[str, Any]:
    raw_text_count = _u32(payload, 0)
    return {
        "text_char_count": raw_text_count & 0x7FFFFFFF,
        "raw_text_char_count": raw_text_count,
        "control_mask": _u32(payload, 4),
        "para_shape_id": _u16(payload, 8),
        "style_id": _u8(payload, 10),
        "divide_type": _u8(payload, 11),
        "char_shape_count": _u16(payload, 12),
        "range_tag_count": _u16(payload, 14),
        "line_seg_count": _u16(payload, 16),
        "instance_id": _u32(payload, 18),
        "merged_by_track": _u16(payload, 22) if len(payload) >= 24 else None,
        "payload_size": len(payload),
    }


def decode_para_char_shape(payload: bytes) -> dict[str, Any]:
    runs = [{
                "start_pos": _u32(payload, offset),
                "char_shape_id": _u32(payload, offset + 4),
            } for offset in range(0, len(payload) - 7, 8)]
    return {
        "run_count": len(runs),
        "runs": runs,
        "first_char_shape_id": runs[0]["char_shape_id"] if runs else None,
        "payload_size": len(payload),
    }


def decode_para_line_seg(payload: bytes) -> dict[str, Any]:
    segments = [{
                "text_pos": _u32(payload, offset),
                "line_vertical_pos": _i32(payload, offset + 4),
                "line_height": _i32(payload, offset + 8),
                "text_height": _i32(payload, offset + 12),
                "baseline": _i32(payload, offset + 16),
                "line_spacing": _i32(payload, offset + 20),
                "column_start": _i32(payload, offset + 24),
                "segment_width": _i32(payload, offset + 28),
                "flags": _u32(payload, offset + 32),
            } for offset in range(0, len(payload) - 35, 36)]
    return {
        "segment_count": len(segments),
        "segments": segments,
        "payload_size": len(payload),
    }


def _control_id(payload: bytes) -> dict[str, str]:
    raw = payload[:4]
    return {
        "raw_hex": raw.hex(" "),
        "ascii": raw.decode("latin1", errors="replace"),
        "canonical": raw[::-1].decode("latin1", errors="replace"),
    }


def decode_object_common_properties(properties: int) -> dict[str, Any]:
    treat_as_char = bool(properties & 0x01)
    vert_bits = (properties >> 3) & 0x03
    horz_bits = (properties >> 8) & 0x03
    wrap_bits = (properties >> 21) & 0x07
    flow_bits = (properties >> 24) & 0x03
    raw_text_wrap = {
        0: "SQUARE",
        1: "TIGHT",
        2: "THROUGH",
        3: "TOP_AND_BOTTOM",
        4: "BEHIND_TEXT",
        5: "IN_FRONT_OF_TEXT",
    }.get(wrap_bits, "SQUARE")
    return {
        "raw": properties,
        "treat_as_char": treat_as_char,
        "allow_overlap": bool((properties >> 14) & 0x01),
        "vert_rel_to": {0: "PAPER", 1: "PAGE", 2: "PARA", 3: "PAPER"}[vert_bits],
        "horz_rel_to": {0: "PAPER", 1: "PAGE", 2: "COLUMN", 3: "PARA"}[horz_bits],
        "raw_text_wrap": raw_text_wrap,
        "text_wrap": "TOP_AND_BOTTOM" if treat_as_char else raw_text_wrap,
        "text_flow": {0: "BOTH_SIDES", 1: "LEFT_ONLY", 2: "RIGHT_ONLY", 3: "LARGEST_ONLY"}[flow_bits],
        "flow_with_text": False,
        "bits": {
            "treat_as_char": int(properties & 0x01),
            "vert_rel_to": vert_bits,
            "horz_rel_to": horz_bits,
            "allow_overlap": (properties >> 14) & 0x01,
            "text_wrap": wrap_bits,
            "text_flow": flow_bits,
        },
    }


def decode_ctrl_header(payload: bytes) -> dict[str, Any]:
    properties = _u32(payload, 4)
    return {
        "control_id": _control_id(payload),
        "properties": properties,
        "layout": decode_object_common_properties(properties),
        "position": {
            "vertical_offset": _i32(payload, 8),
            "horizontal_offset": _i32(payload, 12),
            "width": _i32(payload, 16),
            "height": _i32(payload, 20),
            "z_order": _i32(payload, 24),
        }
        if len(payload) >= 28
        else None,
        "margins": {
            "left": _u16(payload, 28),
            "right": _u16(payload, 30),
            "top": _u16(payload, 32),
            "bottom": _u16(payload, 34),
        }
        if len(payload) >= 36
        else None,
        "instance_id": _u32(payload, 36) if len(payload) >= 40 else None,
        "prevent_page_break": _u32(payload, 40) if len(payload) >= 44 else None,
        "payload_size": len(payload),
        "payload_prefix_hex": payload[:32].hex(" "),
    }


def decode_list_header(payload: bytes) -> dict[str, Any]:
    return {
        "paragraph_count": _u32(payload, 0),
        "property": _u32(payload, 4),
        "cell_addr": {
            "col": _u16(payload, 8),
            "row": _u16(payload, 10),
        }
        if len(payload) >= 12
        else None,
        "cell_span": {
            "col": max(_u16(payload, 12), 1),
            "row": max(_u16(payload, 14), 1),
        }
        if len(payload) >= 16
        else None,
        "text_width": _i32(payload, 16),
        "text_height": _i32(payload, 20),
        "margins": {
            "left": _i16(payload, 24),
            "right": _i16(payload, 26),
            "top": _i16(payload, 28),
            "bottom": _i16(payload, 30),
        },
        "border_fill_id": _u16(payload, 32) if len(payload) >= 34 else None,
        "payload_size": len(payload),
        "payload_extra_u16": [_u16(payload, offset) for offset in range(32, len(payload) - 1, 2)] if len(payload) > 32 else [],
        "payload_prefix_hex": payload[:32].hex(" "),
    }


def decode_page_def(payload: bytes) -> dict[str, Any]:
    width = _i32(payload, 0)
    height = _i32(payload, 4)
    return {
        "width": width,
        "height": height,
        "orientation": "landscape" if width > height else "portrait",
        "landscape": "WIDELY" if width > height else "NARROWLY",
        "margins": {
            "left": _i32(payload, 8),
            "right": _i32(payload, 12),
            "top": _i32(payload, 16),
            "bottom": _i32(payload, 20),
            "header": _i32(payload, 24),
            "footer": _i32(payload, 28),
            "gutter": _i32(payload, 32),
        },
        "property": _u32(payload, 36) if len(payload) >= 40 else None,
        "payload_size": len(payload),
    }


def _note_number_format(value: int) -> str:
    return {
        0: "DIGIT",
        1: "CIRCLED_DIGIT",
        2: "ROMAN_CAPITAL",
        3: "ROMAN_SMALL",
        4: "LATIN_CAPITAL",
        5: "LATIN_SMALL",
        6: "CIRCLED_LATIN_CAPITAL",
        7: "CIRCLED_LATIN_SMALL",
        8: "HANGUL_SYLLABLE",
        9: "CIRCLED_HANGUL_SYLLABLE",
        10: "HANGUL_JAMO",
        11: "CIRCLED_HANGUL_JAMO",
        12: "HANGUL_PHONETIC",
        13: "IDEOGRAPH",
        14: "CIRCLED_IDEOGRAPH",
        15: "DECAGON_CIRCLE",
        16: "DECAGON_CIRCLE_HANJA",
        0x80: "SYMBOL",
        0x81: "USER_CHAR",
    }.get(value, "DIGIT")


def _note_numbering_type(value: int, kind: str) -> str:
    if value == 1:
        return "ON_SECTION"
    if value == 2 and kind == "footnote":
        return "ON_PAGE"
    return "CONTINUOUS"


def _line_style_type2(value: int) -> str:
    return _hwp_line_style_type2(value)


def _line_width(value: int) -> str:
    return _hwp_line_width(value)


def decode_footnote_shape(payload: bytes) -> dict[str, Any]:
    properties = _u32(payload, 0)
    number_format_raw = properties & 0xFF
    placement_raw = (properties >> 8) & 0x03
    numbering_raw = (properties >> 10) & 0x03
    offset = 12
    separator_length = _u16(payload, offset)
    offset += 2
    separator_position = None
    if len(payload) >= 28:
        separator_position = _u16(payload, offset)
        offset += 2
    space_above = _u16(payload, offset)
    offset += 2
    space_below = _u16(payload, offset)
    offset += 2
    space_between = _u16(payload, offset)
    offset += 2
    line_type = _u8(payload, offset)
    line_thickness = _u8(payload, offset + 1)
    line_color = _colorref(payload, offset + 2)
    return {
        "property": properties,
        "number_format_raw": number_format_raw,
        "number_format": _note_number_format(number_format_raw),
        "placement_raw": placement_raw,
        "numbering_raw": numbering_raw,
        "numbering_type": _note_numbering_type(numbering_raw, "footnote"),
        "endnote_numbering_type": _note_numbering_type(numbering_raw, "endnote"),
        "superscript": bool(properties & (1 << 12)),
        "beneath_text": bool(properties & (1 << 13)),
        "user_char": _wchar(payload, 4),
        "prefix_char": _wchar(payload, 6),
        "suffix_char": _wchar(payload, 8) or ")",
        "start_number": _u16(payload, 10, 1),
        "separator_length": separator_length,
        "separator_position": separator_position,
        "space_above": space_above,
        "space_below": space_below,
        "space_between": space_between,
        "separator_line_type_raw": line_type,
        "separator_line_type": _line_style_type2(line_type),
        "separator_line_thickness": line_thickness,
        "separator_line_width": _line_width(line_thickness),
        "separator_line_color": line_color,
        "payload_size": len(payload),
        "payload_prefix_hex": payload[:28].hex(" "),
    }


def decode_page_border_fill(payload: bytes) -> dict[str, Any]:
    if len(payload) >= 22:
        properties = _u32(payload, 0)
        return {
            "property": properties,
            "text_border": "CONTENT" if (properties & 0x01) else "PAPER",
            "header_inside": bool(properties & 0x02),
            "footer_inside": bool(properties & 0x04),
            "fill_behind": bool(properties & 0x08),
            "type": "BOTH",
            "fill_area": "PAPER",
            "border_fill_id": _u16(payload, 4),
            "margins": {
                "left": _i32(payload, 6),
                "right": _i32(payload, 10),
                "top": _i32(payload, 14),
                "bottom": _i32(payload, 18),
            },
            "payload_size": len(payload),
            "payload_prefix_hex": payload[:32].hex(" "),
        }
    properties = _u16(payload, 0)
    return {
        "property": properties,
        "reserved": _u16(payload, 2),
        "text_border": "CONTENT" if (properties & 0x01) else "PAPER",
        "header_inside": bool(properties & 0x02),
        "footer_inside": bool(properties & 0x04),
        "fill_behind": bool(properties & 0x08),
        "type": "BOTH",
        "fill_area": "PAPER",
        "margins": {
            "left": _i16(payload, 4),
            "right": _i16(payload, 6),
            "top": _i16(payload, 8),
            "bottom": _i16(payload, 10),
        },
        "border_fill_id": _u16(payload, 12),
        "payload_size": len(payload),
        "payload_prefix_hex": payload[:32].hex(" "),
    }


def decode_table(payload: bytes) -> dict[str, Any]:
    row_count = _u16(payload, 4)
    col_count = _u16(payload, 6)
    cell_spacing = _u16(payload, 8)
    extra_u16 = [_u16(payload, offset) for offset in range(18, len(payload) - 1, 2)]
    row_cell_counts = extra_u16[:row_count] if len(extra_u16) >= row_count else []
    return {
        "property": _u32(payload, 0),
        "row_count": row_count,
        "col_count": col_count,
        "cell_spacing": cell_spacing,
        "margins": {
            "left": _i16(payload, 10),
            "right": _i16(payload, 12),
            "top": _i16(payload, 14),
            "bottom": _i16(payload, 16),
        },
        "cell_count_capacity": row_count * col_count,
        "row_cell_counts": row_cell_counts,
        "row_cell_count_total": sum(row_cell_counts),
        "table_zone_u16": extra_u16[row_count:] if row_cell_counts else extra_u16,
        "extra_u16": extra_u16,
        "payload_size": len(payload),
        "payload_prefix_hex": payload[:48].hex(" "),
    }


def _normalize_shape_coord(value: int) -> int:
    if value and abs(value) >= 200000 and value % 256 == 0:
        return value // 256
    return value


def _shape_point(payload: bytes, offset: int) -> dict[str, int]:
    raw_x = _i32(payload, offset)
    raw_y = _i32(payload, offset + 4)
    return {
        "raw_x": raw_x,
        "raw_y": raw_y,
        "x": _normalize_shape_coord(raw_x),
        "y": _normalize_shape_coord(raw_y),
    }


def _shape_bbox(points: list[dict[str, int]]) -> dict[str, int]:
    if not points:
        return {"left": 0, "top": 0, "right": 0, "bottom": 0, "width": 0, "height": 0}
    xs = [int(point.get("x") or 0) for point in points]
    ys = [int(point.get("y") or 0) for point in points]
    left = min(xs)
    top = min(ys)
    right = max(xs)
    bottom = max(ys)
    return {
        "left": left,
        "top": top,
        "right": right,
        "bottom": bottom,
        "width": max(0, right - left),
        "height": max(0, bottom - top),
    }


def decode_shape_component(payload: bytes) -> dict[str, Any]:
    decoded = {
        "offset": {"x": _i32(payload, 0), "y": _i32(payload, 4)} if len(payload) >= 8 else {"x": 0, "y": 0},
        "group_level": _u16(payload, 8) if len(payload) >= 10 else 0,
        "local_version": _u16(payload, 10) if len(payload) >= 12 else 0,
        "initial_size": {"width": _u32(payload, 12), "height": _u32(payload, 16)} if len(payload) >= 20 else None,
        "current_size": {"width": _u32(payload, 20), "height": _u32(payload, 24)} if len(payload) >= 28 else None,
        "property": _u32(payload, 28) if len(payload) >= 32 else None,
        "rotation": _i16(payload, 32) if len(payload) >= 34 else 0,
        "rotation_center": {"x": _i32(payload, 34), "y": _i32(payload, 38)} if len(payload) >= 42 else {"x": 0, "y": 0},
        "payload_size": len(payload),
        "payload_prefix_hex": payload[:48].hex(" "),
    }
    if decoded["current_size"]:
        decoded["current_size_normalized"] = {
            "width": _normalize_shape_coord(int(decoded["current_size"]["width"])),
            "height": _normalize_shape_coord(int(decoded["current_size"]["height"])),
        }
    if decoded["initial_size"]:
        decoded["initial_size_normalized"] = {
            "width": _normalize_shape_coord(int(decoded["initial_size"]["width"])),
            "height": _normalize_shape_coord(int(decoded["initial_size"]["height"])),
        }
    return decoded


def decode_shape_component_rectangle(payload: bytes) -> dict[str, Any]:
    points = [_shape_point(payload, 1 + index * 8) for index in range(4) if 1 + index * 8 + 8 <= len(payload)]
    bbox = _shape_bbox(points)
    return {
        "round_ratio": _u8(payload, 0),
        "points": points,
        "bbox": bbox,
        "payload_size": len(payload),
        "payload_prefix_hex": payload[:48].hex(" "),
    }


def decode_picture(payload: bytes) -> dict[str, Any]:
    corners = [_shape_point(payload, 12 + index * 8) for index in range(4) if 12 + index * 8 + 8 <= len(payload)]
    bbox = _shape_bbox(corners)
    return {
        "border_color": _colorref(payload, 0),
        "border_thickness": _i32(payload, 4),
        "border_properties": _u32(payload, 8),
        "corners": corners,
        "bbox": bbox,
        "crop": {
            "left": _i32(payload, 44),
            "top": _i32(payload, 48),
            "right": _i32(payload, 52),
            "bottom": _i32(payload, 56),
        }
        if len(payload) >= 60
        else None,
        "inner_margin": {
            "left": _u16(payload, 60),
            "right": _u16(payload, 62),
            "top": _u16(payload, 64),
            "bottom": _u16(payload, 66),
        }
        if len(payload) >= 68
        else None,
        "effect": {
            "brightness": _i8(payload, 68),
            "contrast": _i8(payload, 69),
            "type": _u8(payload, 70),
        }
        if len(payload) >= 71
        else None,
        "binary_data_id": _u16(payload, 71) if len(payload) >= 73 else None,
        "border_transparency": _u8(payload, 73) if len(payload) >= 74 else None,
        "instance_id": _u32(payload, 74) if len(payload) >= 78 else None,
        "image_dimension_candidates": {
            "u16_pair": {"width": _u16(payload, 82), "height": _u16(payload, 86)} if len(payload) >= 88 else None,
            "u32_pair": {"width": _u32(payload, 82), "height": _u32(payload, 86)} if len(payload) >= 90 else None,
        },
        "payload_size": len(payload),
        "payload_prefix_hex": payload[:48].hex(" "),
    }


def decode_known_record(tag_id: int, payload: bytes) -> dict[str, Any] | None:
    decoders = {
        16: decode_document_properties,
        17: decode_id_mappings,
        18: decode_binary_data,
        19: decode_face_name,
        20: decode_border_fill,
        21: decode_char_shape,
        22: decode_tab_def,
        23: decode_numbering,
        24: decode_bullet,
        25: decode_para_shape,
        26: decode_style,
        28: decode_distribute_doc_data,
        30: decode_compatible_document,
        31: decode_layout_compatibility,
        32: decode_track_change_info,
        66: decode_para_header,
        68: decode_para_char_shape,
        69: decode_para_line_seg,
        71: decode_ctrl_header,
        72: decode_list_header,
        73: decode_page_def,
        74: decode_footnote_shape,
        75: decode_page_border_fill,
        76: decode_shape_component,
        77: decode_table,
        79: decode_shape_component_rectangle,
        85: decode_picture,
        88: decode_eqedit,
        92: decode_memo_shape,
        94: decode_forbidden_char,
        96: decode_track_change_content,
        97: decode_track_change_author,
    }
    decoder = decoders.get(tag_id)
    if not decoder:
        return None
    try:
        return decoder(payload)
    except Exception as exc:  # noqa: BLE001
        return {"decode_error": type(exc).__name__, "message": str(exc), "payload_size": len(payload)}
