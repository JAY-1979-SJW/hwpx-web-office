"""Resolve compose job style declarations into HWPX reference attributes.

The composer should orchestrate document operations, not know every style
module's reference mapping rules. This module centralizes that glue so new
style modules can be added without growing the composer loops.
"""

from __future__ import annotations

from typing import Any

from hwpx_border_fill_style import table_refs_from_names
from hwpx_header_style import style_refs_from_names
from hwpx_list_style_ops import list_refs_from_names
from hwpx_style_ops import normalize_image_layout, normalize_paragraph_style, normalize_table_style
from hwpx_table_cell_address_style import cell_address_refs_from_names
from hwpx_table_cell_layout_style import table_cell_layout_refs
from hwpx_table_cell_style import table_cell_refs_from_names
from hwpx_table_dimension_style import table_dimension_refs
from hwpx_table_merge_style import table_merge_refs


def resolve_paragraph_style(
    style: dict[str, Any] | None,
    style_maps: dict[str, dict[str, Any]],
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    """Return paragraph-level HWPX refs and warnings for a compose style block."""
    refs, warnings = normalize_paragraph_style(style)
    refs.update(style_refs_from_names(style, style_maps))
    refs.update(list_refs_from_names(style, style_maps))
    return refs, warnings


def resolve_table_style(
    style: dict[str, Any] | None,
    style_maps: dict[str, dict[str, Any]],
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    """Return table/cell HWPX refs and warnings for a compose style block."""
    refs, warnings = normalize_table_style(style)
    refs.update(table_refs_from_names(style, style_maps))
    refs.update(table_cell_refs_from_names(style, style_maps))
    refs.update(cell_address_refs_from_names(style, style_maps))

    dimension_refs, dimension_warnings = table_dimension_refs(style)
    refs.update(dimension_refs)
    warnings.extend(dimension_warnings)

    merge_refs, merge_warnings = table_merge_refs(style)
    refs.update(merge_refs)
    warnings.extend(merge_warnings)

    layout_refs, layout_warnings = table_cell_layout_refs(style)
    refs.update(layout_refs)
    warnings.extend(layout_warnings)
    return refs, warnings


def resolve_image_layout(image: dict[str, Any]) -> tuple[dict[str, int], list[dict[str, Any]]]:
    """Normalize generated picture/chart layout values."""
    return normalize_image_layout(image)


__all__ = ["resolve_image_layout", "resolve_paragraph_style", "resolve_table_style"]
