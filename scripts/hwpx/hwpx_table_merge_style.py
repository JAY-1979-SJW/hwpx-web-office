"""Merged-cell style mapping for generated HWPX tables."""

from __future__ import annotations

from typing import Any


def _int_value(value: Any, field: str, warnings: list[dict[str, Any]], min_value: int = 0) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        warnings.append({"type": "MERGED_CELL_VALUE_IGNORED", "field": field, "value": value})
        return None
    if number < min_value:
        warnings.append({"type": "MERGED_CELL_VALUE_IGNORED", "field": field, "value": value, "min": min_value})
        return None
    return number


def _span_value(spec: dict[str, Any], snake_key: str, camel_key: str, default: int) -> Any:
    if snake_key in spec:
        return spec[snake_key]
    if camel_key in spec:
        return spec[camel_key]
    return default


def table_merge_refs(style: dict[str, Any] | None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Convert a job table style merge spec into factory refs.

    The refs intentionally preserve logical row/column counts. Covered cells are
    omitted from generated XML while anchor cells receive hp:cellSpan values.
    """

    if not style or "merged_cells" not in style:
        return {}, []
    warnings: list[dict[str, Any]] = []
    raw_specs = style.get("merged_cells")
    if not isinstance(raw_specs, list):
        return {}, [{"type": "MERGED_CELLS_NOT_LIST"}]

    merged: dict[str, dict[str, str]] = {}
    covered: set[str] = set()
    occupied: set[str] = set()
    for index, spec in enumerate(raw_specs):
        if not isinstance(spec, dict):
            warnings.append({"type": "MERGED_CELL_SPEC_NOT_OBJECT", "index": index, "value": spec})
            continue
        row = _int_value(spec.get("row"), f"merged_cells[{index}].row", warnings, 0)
        col = _int_value(spec.get("col"), f"merged_cells[{index}].col", warnings, 0)
        row_span = _int_value(_span_value(spec, "row_span", "rowSpan", 1), f"merged_cells[{index}].row_span", warnings, 1)
        col_span = _int_value(_span_value(spec, "col_span", "colSpan", 1), f"merged_cells[{index}].col_span", warnings, 1)
        if row is None or col is None or row_span is None or col_span is None:
            continue
        if row_span == 1 and col_span == 1:
            warnings.append({"type": "MERGED_CELL_SPAN_IGNORED", "index": index, "row": row, "col": col})
            continue

        anchor = f"{row},{col}"
        cells = {f"{r},{c}" for r in range(row, row + row_span) for c in range(col, col + col_span)}
        overlap = sorted(cells & occupied)
        if overlap:
            warnings.append(
                {
                    "type": "MERGED_CELL_OVERLAP_IGNORED",
                    "index": index,
                    "row": row,
                    "col": col,
                    "overlap": overlap,
                }
            )
            continue

        occupied.update(cells)
        merged[anchor] = {"rowSpan": str(row_span), "colSpan": str(col_span)}
        covered.update(cell for cell in cells if cell != anchor)

    refs: dict[str, Any] = {}
    if merged:
        refs["mergedCells"] = merged
        refs["coveredCells"] = sorted(covered)
    return refs, warnings


__all__ = ["table_merge_refs"]
