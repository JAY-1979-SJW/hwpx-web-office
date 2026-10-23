"""Header style definition builders for direct HWPX generation."""

from __future__ import annotations

import copy
import xml.etree.ElementTree as ET
from typing import Any

from hwpx_package import HwpxPackage, local_name

HH_NS = "http://www.hancom.co.kr/hwpml/2011/head"


def hh(tag: str) -> str:
    return f"{{{HH_NS}}}{tag}"


def _find_first(root: ET.Element, name: str) -> ET.Element | None:
    for elem in root.iter():
        if local_name(elem.tag) == name:
            return elem
    return None


def _find_container(root: ET.Element, name: str) -> ET.Element | None:
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
    if not text.startswith("#"):
        text = "#" + text
    if len(text) not in {7, 9}:
        return None
    return text.upper()


def _set_child_presence(elem: ET.Element, child_name: str, present: bool) -> None:
    existing = [child for child in list(elem) if local_name(child.tag) == child_name]
    if present and not existing:
        elem.append(ET.Element(hh(child_name)))
    if not present:
        for child in existing:
            elem.remove(child)


def _set_para_align(para_pr: ET.Element, horizontal: str) -> None:
    align = _find_first(para_pr, "align")
    if align is None:
        align = ET.SubElement(para_pr, hh("align"))
    align.attrib["horizontal"] = horizontal.upper()
    align.attrib.setdefault("vertical", "BASELINE")


def _set_line_spacing(para_pr: ET.Element, value: Any) -> bool:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return False
    line_spacing = _find_first(para_pr, "lineSpacing")
    if line_spacing is None:
        line_spacing = ET.SubElement(para_pr, hh("lineSpacing"))
    line_spacing.attrib["type"] = "PERCENT"
    line_spacing.attrib["value"] = str(number)
    line_spacing.attrib["unit"] = "HWPUNIT"
    return True


def _apply_char_color_fields(
    char_pr: ET.Element, spec: dict[str, Any], name: str, warnings: list[dict[str, Any]]
) -> None:
    color = _normalize_color(spec.get("text_color"))
    if color:
        char_pr.attrib["textColor"] = color
    elif "text_color" in spec:
        warnings.append({
            "type": "TEXT_COLOR_INVALID",
            "name": name,
            "value": spec.get("text_color"),
        })
    shade = _normalize_color(spec.get("shade_color"))
    if shade:
        char_pr.attrib["shadeColor"] = shade
    elif spec.get("shade_color") in {"none", "NONE"}:
        char_pr.attrib["shadeColor"] = "none"
    elif "shade_color" in spec:
        warnings.append({
            "type": "SHADE_COLOR_INVALID",
            "name": name,
            "value": spec.get("shade_color"),
        })


def create_char_property(
    root: ET.Element, name: str, spec: dict[str, Any]
) -> tuple[str | None, list[dict[str, Any]]]:
    warnings: list[dict[str, Any]] = []
    container = _find_container(root, "charProperties")
    if container is None:
        return None, [{"type": "CHAR_PROPERTIES_NOT_FOUND", "name": name}]
    source = _find_first(container, "charPr")
    if source is None:
        return None, [{"type": "CHAR_PR_TEMPLATE_NOT_FOUND", "name": name}]
    next_id = str(_max_child_id(container, "charPr") + 1)
    char_pr = copy.deepcopy(source)
    char_pr.attrib["id"] = next_id
    if "height" in spec:
        try:
            char_pr.attrib["height"] = str(int(spec["height"]))
        except (TypeError, ValueError):
            warnings.append({
                "type": "CHAR_HEIGHT_INVALID",
                "name": name,
                "value": spec.get("height"),
            })
    _apply_char_color_fields(char_pr, spec, name, warnings)
    if "bold" in spec:
        _set_child_presence(char_pr, "bold", bool(spec["bold"]))
    unsupported = sorted(set(spec) - {"height", "text_color", "shade_color", "bold"})
    warnings.extend({"type": "CHAR_STYLE_FIELD_PENDING", "name": name, "field": field} for field in unsupported)
    container.append(char_pr)
    _bump_item_count(container)
    return next_id, warnings


def create_para_property(
    root: ET.Element, name: str, spec: dict[str, Any]
) -> tuple[str | None, list[dict[str, Any]]]:
    warnings: list[dict[str, Any]] = []
    container = _find_container(root, "paraProperties")
    if container is None:
        return None, [{"type": "PARA_PROPERTIES_NOT_FOUND", "name": name}]
    source = _find_first(container, "paraPr")
    if source is None:
        return None, [{"type": "PARA_PR_TEMPLATE_NOT_FOUND", "name": name}]
    next_id = str(_max_child_id(container, "paraPr") + 1)
    para_pr = copy.deepcopy(source)
    para_pr.attrib["id"] = next_id
    if "align" in spec:
        _set_para_align(para_pr, str(spec["align"]))
    if "line_spacing" in spec and not _set_line_spacing(para_pr, spec["line_spacing"]):
        warnings.append({
            "type": "LINE_SPACING_INVALID",
            "name": name,
            "value": spec.get("line_spacing"),
        })
    unsupported = sorted(set(spec) - {"align", "line_spacing"})
    warnings.extend({"type": "PARA_STYLE_FIELD_PENDING", "name": name, "field": field} for field in unsupported)
    container.append(para_pr)
    _bump_item_count(container)
    return next_id, warnings


def apply_header_style_definitions(
    package: HwpxPackage, definitions: dict[str, Any] | None
) -> dict[str, Any]:
    if not definitions:
        return {"status": "SKIPPED", "char_styles": {}, "para_styles": {}, "warnings": []}
    header_entry = "Contents/header.xml"
    if header_entry not in package.entries:
        return {"status": "HEADER_NOT_FOUND", "char_styles": {}, "para_styles": {}, "warnings": []}
    root = package.read_xml(header_entry)
    char_styles: dict[str, str] = {}
    para_styles: dict[str, str] = {}
    warnings: list[dict[str, Any]] = []
    for name, spec in definitions.get("char_styles", {}).items():
        if not isinstance(spec, dict):
            warnings.append({"type": "CHAR_STYLE_SPEC_INVALID", "name": name})
            continue
        new_id, style_warnings = create_char_property(root, str(name), spec)
        if new_id is not None:
            char_styles[str(name)] = new_id
        warnings.extend(style_warnings)
    for name, spec in definitions.get("para_styles", {}).items():
        if not isinstance(spec, dict):
            warnings.append({"type": "PARA_STYLE_SPEC_INVALID", "name": name})
            continue
        new_id, style_warnings = create_para_property(root, str(name), spec)
        if new_id is not None:
            para_styles[str(name)] = new_id
        warnings.extend(style_warnings)
    package.write_xml(header_entry, root)
    return {
        "status": "PASS",
        "entry": header_entry,
        "char_styles": char_styles,
        "para_styles": para_styles,
        "warnings": warnings,
    }


def style_refs_from_names(
    style: dict[str, Any] | None, style_maps: dict[str, dict[str, str]]
) -> dict[str, str]:
    if not style:
        return {}
    refs: dict[str, str] = {}
    char_name = style.get("char_style")
    para_name = style.get("para_style")
    if char_name in style_maps.get("char_styles", {}):
        refs["charPrIDRef"] = style_maps["char_styles"][char_name]
    if para_name in style_maps.get("para_styles", {}):
        refs["paraPrIDRef"] = style_maps["para_styles"][para_name]
    return refs


__all__ = ["apply_header_style_definitions", "style_refs_from_names"]
