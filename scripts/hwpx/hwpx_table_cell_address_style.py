"""Cell-address style mapping for generated HWPX tables."""

from __future__ import annotations

from typing import Any

from hwpx_schema_rules import normalize_cell_address


def cell_address_refs_from_names(style: dict[str, Any] | None, style_maps: dict[str, dict[str, str]]) -> dict[str, dict[str, str]]:
    if not style:
        return {}
    raw_map = style.get("cell_border_fill_map", {})
    if not isinstance(raw_map, dict):
        return {}
    border_fills = style_maps.get("border_fills", {})
    resolved: dict[str, str] = {}
    for raw_address, style_name in raw_map.items():
        address = normalize_cell_address(raw_address)
        if address and style_name in border_fills:
            resolved[address] = border_fills[style_name]
    return {"cellBorderFillIDRefMap": resolved} if resolved else {}


__all__ = ["cell_address_refs_from_names", "normalize_cell_address"]
