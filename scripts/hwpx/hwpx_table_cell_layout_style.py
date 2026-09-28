"""Cell layout style mapping for generated HWPX tables."""

from __future__ import annotations

from typing import Any

from hwpx_table_cell_address_style import normalize_cell_address

VERT_ALIGN_VALUES = {"TOP", "CENTER", "BOTTOM"}
TEXT_DIRECTION_VALUES = {"HORIZONTAL", "VERTICAL"}
LINE_WRAP_VALUES = {"BREAK", "SQUEEZE"}
MARGIN_FIELDS = ("left", "right", "top", "bottom")


def _enum_value(
    value: Any, field: str, allowed: set[str], warnings: list[dict[str, Any]]
) -> str | None:
    normalized = str(value).strip().upper()
    if normalized not in allowed:
        warnings.append({
            "type": "TABLE_CELL_LAYOUT_VALUE_IGNORED",
            "field": field,
            "value": value,
            "allowed": sorted(allowed),
        })
        return None
    return normalized


def _positive_int(
    value: Any, field: str, warnings: list[dict[str, Any]], min_value: int = 0
) -> str | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        warnings.append({"type": "TABLE_CELL_LAYOUT_VALUE_IGNORED", "field": field, "value": value})
        return None
    if number < min_value:
        warnings.append({
            "type": "TABLE_CELL_LAYOUT_VALUE_IGNORED",
            "field": field,
            "value": value,
            "min": min_value,
        })
        return None
    return str(number)


def _margin_refs(raw: Any, field: str, warnings: list[dict[str, Any]]) -> dict[str, str] | None:
    if not isinstance(raw, dict):
        warnings.append({"type": "CELL_MARGIN_NOT_OBJECT", "field": field, "value": raw})
        return None
    result: dict[str, str] = {}
    for margin_field in MARGIN_FIELDS:
        if margin_field not in raw:
            continue
        value = _positive_int(raw[margin_field], f"{field}.{margin_field}", warnings, 0)
        if value is not None:
            result[margin_field] = value
    return result or None


def _address_value_map(
    raw: Any,
    field: str,
    warnings: list[dict[str, Any]],
    normalizer,
) -> dict[str, Any]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        warnings.append({"type": "CELL_LAYOUT_MAP_NOT_OBJECT", "field": field})
        return {}
    result: dict[str, Any] = {}
    for address, value in raw.items():
        normalized_address = normalize_cell_address(address)
        if normalized_address is None:
            warnings.append({
                "type": "CELL_LAYOUT_ADDRESS_INVALID",
                "field": field,
                "address": address,
            })
            continue
        normalized_value = normalizer(value, f"{field}.{address}")
        if normalized_value is not None:
            result[normalized_address] = normalized_value
    return result


def _scalar_cell_refs(style: dict[str, Any], warnings: list[dict[str, Any]]) -> dict[str, Any]:
    refs: dict[str, Any] = {}
    vert_align = style.get(
        "cell_vertical_align", style.get("vertical_align", style.get("vert_align"))
    )
    if vert_align is not None:
        value = _enum_value(vert_align, "cell_vertical_align", VERT_ALIGN_VALUES, warnings)
        if value is not None:
            refs["cellVertAlign"] = value
    text_direction = style.get("cell_text_direction", style.get("text_direction"))
    if text_direction is not None:
        value = _enum_value(text_direction, "cell_text_direction", TEXT_DIRECTION_VALUES, warnings)
        if value is not None:
            refs["cellTextDirection"] = value
    line_wrap = style.get("cell_line_wrap", style.get("line_wrap"))
    if line_wrap is not None:
        value = _enum_value(line_wrap, "cell_line_wrap", LINE_WRAP_VALUES, warnings)
        if value is not None:
            refs["cellLineWrap"] = value
    margin = (
        _margin_refs(style.get("cell_margin"), "cell_margin", warnings)
        if "cell_margin" in style
        else None
    )
    if margin:
        refs["cellMargin"] = margin
    return refs


def _map_cell_refs(style: dict[str, Any], warnings: list[dict[str, Any]]) -> dict[str, Any]:
    refs: dict[str, Any] = {}
    vert_map = _address_value_map(
        style.get("cell_vertical_align_map"),
        "cell_vertical_align_map",
        warnings,
        lambda value, field: _enum_value(value, field, VERT_ALIGN_VALUES, warnings),
    )
    if vert_map:
        refs["cellVertAlignMap"] = vert_map
    text_map = _address_value_map(
        style.get("cell_text_direction_map"),
        "cell_text_direction_map",
        warnings,
        lambda value, field: _enum_value(value, field, TEXT_DIRECTION_VALUES, warnings),
    )
    if text_map:
        refs["cellTextDirectionMap"] = text_map
    line_map = _address_value_map(
        style.get("cell_line_wrap_map"),
        "cell_line_wrap_map",
        warnings,
        lambda value, field: _enum_value(value, field, LINE_WRAP_VALUES, warnings),
    )
    if line_map:
        refs["cellLineWrapMap"] = line_map
    margin_map = _address_value_map(
        style.get("cell_margin_map"),
        "cell_margin_map",
        warnings,
        lambda value, field: _margin_refs(value, field, warnings),
    )
    if margin_map:
        refs["cellMarginMap"] = margin_map
    return refs


def table_cell_layout_refs(
    style: dict[str, Any] | None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not style:
        return {}, []
    warnings: list[dict[str, Any]] = []
    refs: dict[str, Any] = {**_scalar_cell_refs(style, warnings), **_map_cell_refs(style, warnings)}
    return refs, warnings


__all__ = ["table_cell_layout_refs"]
