"""Schema-level constants and pure normalizers for HWPX compose jobs."""

from __future__ import annotations

from typing import Any

VISIBLE_IMAGE_MODES = {"visible_png_insert", "visible_chart_png"}
SYNTHETIC_IMAGE_MODES = {"png_insert", "chart_png"}
SUPPORTED_IMAGE_MODES = SYNTHETIC_IMAGE_MODES | VISIBLE_IMAGE_MODES

OUTLINE_PRESETS: dict[str, list[dict[str, Any]]] = {
    "decimal": [
        {"level": 1, "text": "^1.", "numFormat": "DIGIT"},
        {"level": 2, "text": "^2)", "numFormat": "DIGIT"},
        {"level": 3, "text": "(^3)", "numFormat": "DIGIT"},
    ],
    "korean": [
        {"level": 1, "text": "^1.", "numFormat": "HANGUL_SYLLABLE"},
        {"level": 2, "text": "^2)", "numFormat": "HANGUL_SYLLABLE"},
        {"level": 3, "text": "(^3)", "numFormat": "HANGUL_SYLLABLE"},
    ],
    "mixed_legal": [
        {"level": 1, "text": "^1.", "numFormat": "DIGIT"},
        {"level": 2, "text": "^2.", "numFormat": "HANGUL_SYLLABLE"},
        {"level": 3, "text": "^3)", "numFormat": "DIGIT"},
        {"level": 4, "text": "^4)", "numFormat": "HANGUL_SYLLABLE"},
    ],
    "bullet_dash": [
        {"level": 1, "text": "-", "numFormat": "USER_CHAR"},
    ],
}

PARAGRAPH_REF_KEYS = {
    "para_pr_id": "paraPrIDRef",
    "paraPrIDRef": "paraPrIDRef",
    "style_id": "styleIDRef",
    "styleIDRef": "styleIDRef",
    "char_pr_id": "charPrIDRef",
    "charPrIDRef": "charPrIDRef",
}

TABLE_REF_KEYS = {
    "border_fill_id": "borderFillIDRef",
    "borderFillIDRef": "borderFillIDRef",
}


def _positive_int(
    value: Any, field: str, warnings: list[dict[str, Any]], min_value: int = 1
) -> str | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        warnings.append({"type": "STYLE_VALUE_IGNORED", "field": field, "value": value})
        return None
    if number < min_value:
        warnings.append({
            "type": "STYLE_VALUE_IGNORED",
            "field": field,
            "value": value,
            "min": min_value,
        })
        return None
    return str(number)


def normalize_paragraph_style(
    style: dict[str, Any] | None,
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    if not style:
        return {}, []
    result: dict[str, str] = {}
    warnings: list[dict[str, Any]] = []
    for key, target in PARAGRAPH_REF_KEYS.items():
        if key in style:
            normalized = _positive_int(style[key], key, warnings, 0)
            if normalized is not None:
                result[target] = normalized
    supported_names = {"char_style", "para_style", "list_style", "list_level", "level"}
    unsupported = sorted(set(style) - set(PARAGRAPH_REF_KEYS) - supported_names)
    for key in unsupported:
        warnings.append({
            "type": "STYLE_ATTRIBUTE_REQUIRES_HEADER_DEFINITION",
            "field": key,
            "message": "Direct writer currently applies existing style references only.",
        })
    return result, warnings


def _apply_simple_table_style_fields(
    style: dict[str, Any], result: dict[str, str], warnings: list[dict[str, Any]]
) -> None:
    if "width" in style:
        normalized = _positive_int(style["width"], "width", warnings, 1000)
        if normalized is not None:
            result["tableWidth"] = normalized
    if "row_height" in style:
        normalized = _positive_int(style["row_height"], "row_height", warnings, 500)
        if normalized is not None:
            result["rowHeight"] = normalized
    if "repeat_header" in style:
        result["repeatHeader"] = "1" if bool(style["repeat_header"]) else "0"


def normalize_table_style(
    style: dict[str, Any] | None,
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    if not style:
        return {}, []
    result: dict[str, str] = {}
    warnings: list[dict[str, Any]] = []
    for key, target in TABLE_REF_KEYS.items():
        if key in style:
            normalized = _positive_int(style[key], key, warnings, 0)
            if normalized is not None:
                result[target] = normalized
    _apply_simple_table_style_fields(style, result, warnings)
    supported_names = {
        "width",
        "row_height",
        "row_heights",
        "repeat_header",
        "column_widths",
        "merged_cells",
        "border_fill_style",
        "cell_border_fill_style",
        "cell_border_fill_map",
        "cell_vertical_align",
        "vertical_align",
        "vert_align",
        "cell_vertical_align_map",
        "cell_text_direction",
        "text_direction",
        "cell_text_direction_map",
        "cell_line_wrap",
        "line_wrap",
        "cell_line_wrap_map",
        "cell_margin",
        "cell_margin_map",
        "header_border_fill_style",
        "body_border_fill_style",
    }
    unsupported = sorted(set(style) - set(TABLE_REF_KEYS) - supported_names)
    for key in unsupported:
        warnings.append({
            "type": "TABLE_STYLE_ATTRIBUTE_PENDING",
            "field": key,
            "message": "Complex table styling requires header/style definition support.",
        })
    return result, warnings


def normalize_image_layout(image: dict[str, Any]) -> tuple[dict[str, int], list[dict[str, Any]]]:
    warnings: list[dict[str, Any]] = []
    layout: dict[str, int] = {}
    for field, default in (("width", 12000), ("height", 9000), ("section_index", 0)):
        value = image.get(field, default)
        min_value = 0 if field == "section_index" else 1
        normalized = _positive_int(value, field, warnings, min_value)
        layout[field] = int(normalized) if normalized is not None else default
    return layout, warnings


def normalize_cell_address(key: Any) -> str | None:
    text = str(key).strip()
    if not text:
        return None
    if "," in text:
        left, right = text.split(",", 1)
    elif ":" in text:
        left, right = text.split(":", 1)
    else:
        lower = text.lower()
        if lower.startswith("r") and "c" in lower:
            left, right = lower[1:].split("c", 1)
        else:
            return None
    try:
        row = int(left.strip())
        col = int(right.strip())
    except ValueError:
        return None
    if row < 0 or col < 0:
        return None
    return f"{row},{col}"


__all__ = [
    "OUTLINE_PRESETS",
    "PARAGRAPH_REF_KEYS",
    "SUPPORTED_IMAGE_MODES",
    "SYNTHETIC_IMAGE_MODES",
    "TABLE_REF_KEYS",
    "VISIBLE_IMAGE_MODES",
    "normalize_cell_address",
    "normalize_image_layout",
    "normalize_paragraph_style",
    "normalize_table_style",
]
