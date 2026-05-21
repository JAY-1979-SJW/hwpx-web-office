"""Cell-level style mapping for generated HWPX tables."""

from __future__ import annotations

from typing import Any


def table_cell_refs_from_names(style: dict[str, Any] | None, style_maps: dict[str, dict[str, str]]) -> dict[str, str]:
    if not style:
        return {}
    border_fills = style_maps.get("border_fills", {})
    refs: dict[str, str] = {}
    header_name = style.get("header_border_fill_style")
    body_name = style.get("body_border_fill_style")
    cell_name = style.get("cell_border_fill_style")
    if header_name in border_fills:
        refs["headerBorderFillIDRef"] = border_fills[header_name]
    if body_name in border_fills:
        refs["bodyBorderFillIDRef"] = border_fills[body_name]
    if cell_name in border_fills:
        refs["borderFillIDRef"] = border_fills[cell_name]
    return refs


__all__ = ["table_cell_refs_from_names"]
