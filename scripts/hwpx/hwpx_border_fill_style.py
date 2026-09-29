"""Header borderFill definition builders for generated HWPX tables."""

from __future__ import annotations

import copy
from typing import Any
import xml.etree.ElementTree as ET

from hwpx_package import HwpxPackage, local_name

HH_NS = "http://www.hancom.co.kr/hwpml/2011/head"
HC_NS = "http://www.hancom.co.kr/hwpml/2011/core"


def hh(tag: str) -> str:
    return f"{{{HH_NS}}}{tag}"


def hc(tag: str) -> str:
    return f"{{{HC_NS}}}{tag}"


def _find_container(root: ET.Element, name: str) -> ET.Element | None:
    for elem in root.iter():
        if local_name(elem.tag) == name:
            return elem
    return None


def _find_first(root: ET.Element, name: str) -> ET.Element | None:
    for elem in root.iter():
        if local_name(elem.tag) == name:
            return elem
    return None


def _max_child_id(container: ET.Element, child_name: str) -> int:
    ids = []
    for child in list(container):
        if local_name(child.tag) != child_name:
            continue
        try:
            ids.append(int(child.attrib.get("id", "0")))
        except ValueError:
            continue
    return max(ids) if ids else -1


def _bump_item_count(container: ET.Element) -> None:
    try:
        count = int(container.attrib.get("itemCnt", "0"))
    except ValueError:
        count = len(list(container))
    container.attrib["itemCnt"] = str(max(count + 1, len(list(container))))


def _normalize_color(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.lower() == "none":
        return "none"
    if not text.startswith("#"):
        text = "#" + text
    if len(text) not in {7, 9}:
        return None
    return text.upper()


def _border_spec(spec: dict[str, Any], side: str) -> dict[str, str]:
    borders = spec.get("borders") if isinstance(spec.get("borders"), dict) else {}
    side_spec = borders.get(side, {}) if isinstance(borders.get(side, {}), dict) else {}
    all_spec = borders.get("all", {}) if isinstance(borders.get("all", {}), dict) else {}
    border_type = side_spec.get("type", all_spec.get("type", spec.get("border_type", "SOLID")))
    width = side_spec.get("width", all_spec.get("width", spec.get("border_width", "0.12 mm")))
    color = _normalize_color(side_spec.get("color", all_spec.get("color", spec.get("border_color", "#000000"))))
    return {
        "type": str(border_type).upper(),
        "width": str(width),
        "color": color or "#000000",
    }


def _set_border(border_fill: ET.Element, child_name: str, values: dict[str, str]) -> None:
    child = _find_first(border_fill, child_name)
    if child is None:
        child = ET.SubElement(border_fill, hh(child_name))
    child.attrib["type"] = values["type"]
    child.attrib["width"] = values["width"]
    child.attrib["color"] = values["color"]


def _set_fill(border_fill: ET.Element, color: str) -> None:
    fill_brush = _find_first(border_fill, "fillBrush")
    if fill_brush is None:
        fill_brush = ET.SubElement(border_fill, hc("fillBrush"))
    win_brush = _find_first(fill_brush, "winBrush")
    if win_brush is None:
        win_brush = ET.SubElement(fill_brush, hc("winBrush"))
    win_brush.attrib["faceColor"] = color
    win_brush.attrib.setdefault("hatchColor", "#000000")
    win_brush.attrib.setdefault("alpha", "0")


def create_border_fill(root: ET.Element, name: str, spec: dict[str, Any]) -> tuple[str | None, list[dict[str, Any]]]:
    warnings: list[dict[str, Any]] = []
    container = _find_container(root, "borderFills")
    if container is None:
        return None, [{"type": "BORDER_FILLS_NOT_FOUND", "name": name}]
    source = _find_first(container, "borderFill")
    if source is None:
        return None, [{"type": "BORDER_FILL_TEMPLATE_NOT_FOUND", "name": name}]
    next_id = str(_max_child_id(container, "borderFill") + 1)
    border_fill = copy.deepcopy(source)
    border_fill.attrib["id"] = next_id
    border_fill.attrib.setdefault("threeD", "0")
    border_fill.attrib.setdefault("shadow", "0")
    border_fill.attrib.setdefault("centerLine", "NONE")
    border_fill.attrib.setdefault("breakCellSeparateLine", "0")

    for side, child_name in (
        ("left", "leftBorder"),
        ("right", "rightBorder"),
        ("top", "topBorder"),
        ("bottom", "bottomBorder"),
    ):
        _set_border(border_fill, child_name, _border_spec(spec, side))

    fill_color = _normalize_color(spec.get("fill_color", spec.get("background_color")))
    if fill_color:
        _set_fill(border_fill, fill_color)
    elif "fill_color" in spec or "background_color" in spec:
        warnings.append({"type": "FILL_COLOR_INVALID", "name": name})

    unsupported = sorted(
        set(spec)
        - {"background_color", "fill_color", "border_type", "border_width", "border_color", "borders"}
    )
    warnings.extend({"type": "BORDER_FILL_FIELD_PENDING", "name": name, "field": field} for field in unsupported)

    container.append(border_fill)
    _bump_item_count(container)
    return next_id, warnings


def apply_border_fill_definitions(package: HwpxPackage, definitions: dict[str, Any] | None) -> dict[str, Any]:
    border_defs = (definitions or {}).get("border_fills", {}) if isinstance(definitions, dict) else {}
    if not border_defs:
        return {"status": "SKIPPED", "border_fills": {}, "warnings": []}
    header_entry = "Contents/header.xml"
    if header_entry not in package.entries:
        return {"status": "HEADER_NOT_FOUND", "border_fills": {}, "warnings": []}
    root = package.read_xml(header_entry)
    border_fills: dict[str, str] = {}
    warnings: list[dict[str, Any]] = []
    for name, spec in border_defs.items():
        if not isinstance(spec, dict):
            warnings.append({"type": "BORDER_FILL_SPEC_INVALID", "name": name})
            continue
        new_id, style_warnings = create_border_fill(root, str(name), spec)
        if new_id is not None:
            border_fills[str(name)] = new_id
        warnings.extend(style_warnings)
    package.write_xml(header_entry, root)
    return {
        "status": "PASS",
        "entry": header_entry,
        "border_fills": border_fills,
        "warnings": warnings,
    }


def table_refs_from_names(style: dict[str, Any] | None, style_maps: dict[str, dict[str, str]]) -> dict[str, str]:
    if not style:
        return {}
    refs: dict[str, str] = {}
    border_name = style.get("border_fill_style")
    if border_name in style_maps.get("border_fills", {}):
        refs["borderFillIDRef"] = style_maps["border_fills"][border_name]
    return refs


__all__ = ["apply_border_fill_definitions", "create_border_fill", "table_refs_from_names"]
