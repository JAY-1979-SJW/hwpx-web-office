"""Dimension style mapping for generated HWPX tables."""

from __future__ import annotations

from typing import Any


def _positive_int(
    value: Any, field: str, warnings: list[dict[str, Any]], min_value: int = 1
) -> str | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        warnings.append({"type": "TABLE_DIMENSION_VALUE_IGNORED", "field": field, "value": value})
        return None
    if number < min_value:
        warnings.append({
            "type": "TABLE_DIMENSION_VALUE_IGNORED",
            "field": field,
            "value": value,
            "min": min_value,
        })
        return None
    return str(number)


def _normalize_dimension_list(
    values: Any,
    label: str,
    warnings: list[dict[str, Any]],
    *,
    not_list_warning_type: str,
    min_value: int = 100,
) -> list[str]:
    if not isinstance(values, list):
        warnings.append({"type": not_list_warning_type})
        return []
    normalized = []
    for index, value in enumerate(values):
        item = _positive_int(value, f"{label}[{index}]", warnings, min_value)
        if item is not None:
            normalized.append(item)
    return normalized


def table_dimension_refs(
    style: dict[str, Any] | None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not style:
        return {}, []
    refs: dict[str, Any] = {}
    warnings: list[dict[str, Any]] = []
    column_widths = style.get("column_widths")
    if column_widths is not None:
        normalized = _normalize_dimension_list(
            column_widths, "column_widths", warnings, not_list_warning_type="COLUMN_WIDTHS_NOT_LIST"
        )
        if normalized:
            refs["columnWidths"] = normalized
            refs["tableWidth"] = str(sum(int(width) for width in normalized))
    row_heights = style.get("row_heights")
    if row_heights is not None:
        normalized = _normalize_dimension_list(
            row_heights, "row_heights", warnings, not_list_warning_type="ROW_HEIGHTS_NOT_LIST"
        )
        if normalized:
            refs["rowHeights"] = normalized
    return refs, warnings


__all__ = ["table_dimension_refs"]
