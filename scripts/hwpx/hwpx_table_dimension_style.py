"""Dimension style mapping for generated HWPX tables."""

from __future__ import annotations

from typing import Any


def _positive_int(value: Any, field: str, warnings: list[dict[str, Any]], min_value: int = 1) -> str | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        warnings.append({"type": "TABLE_DIMENSION_VALUE_IGNORED", "field": field, "value": value})
        return None
    if number < min_value:
        warnings.append({"type": "TABLE_DIMENSION_VALUE_IGNORED", "field": field, "value": value, "min": min_value})
        return None
    return str(number)


def table_dimension_refs(style: dict[str, Any] | None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not style:
        return {}, []
    refs: dict[str, Any] = {}
    warnings: list[dict[str, Any]] = []
    column_widths = style.get("column_widths")
    if column_widths is not None:
        if not isinstance(column_widths, list):
            warnings.append({"type": "COLUMN_WIDTHS_NOT_LIST"})
        else:
            normalized = []
            for index, value in enumerate(column_widths):
                width = _positive_int(value, f"column_widths[{index}]", warnings, 100)
                if width is not None:
                    normalized.append(width)
            if normalized:
                refs["columnWidths"] = normalized
                refs["tableWidth"] = str(sum(int(width) for width in normalized))
    row_heights = style.get("row_heights")
    if row_heights is not None:
        if not isinstance(row_heights, list):
            warnings.append({"type": "ROW_HEIGHTS_NOT_LIST"})
        else:
            normalized = []
            for index, value in enumerate(row_heights):
                height = _positive_int(value, f"row_heights[{index}]", warnings, 100)
                if height is not None:
                    normalized.append(height)
            if normalized:
                refs["rowHeights"] = normalized
    return refs, warnings


__all__ = ["table_dimension_refs"]
