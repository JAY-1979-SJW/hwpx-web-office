"""List and numbering style definitions for generated HWPX paragraphs."""

from __future__ import annotations

import copy
from typing import Any
import xml.etree.ElementTree as ET

from hwpx_package import HwpxPackage, local_name
from hwpx_schema_rules import OUTLINE_PRESETS


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


def _ensure_child(elem: ET.Element, child_name: str) -> ET.Element:
    child = _find_first(elem, child_name)
    if child is None:
        child = ET.SubElement(elem, hh(child_name))
    return child


def _set_margin(para_pr: ET.Element, left: int, intent: int) -> None:
    margin = _ensure_child(para_pr, "margin")
    fields = {"intent": intent, "left": left, "right": 0, "prev": 0, "next": 0}
    for name, value in fields.items():
        child = None
        for candidate in list(margin):
            if local_name(candidate.tag) == name:
                child = candidate
                break
        if child is None:
            child = ET.SubElement(margin, hc(name))
        child.attrib["value"] = str(value)
        child.attrib["unit"] = "HWPUNIT"


def _level_specs(spec: dict[str, Any]) -> list[dict[str, Any]]:
    levels = spec.get("levels")
    if isinstance(levels, list) and levels:
        return [level for level in levels if isinstance(level, dict)]
    preset = spec.get("preset")
    if preset:
        preset_levels = OUTLINE_PRESETS.get(str(preset))
        if preset_levels:
            return [dict(level) for level in preset_levels]
    kind = str(spec.get("type", "number")).lower()
    if kind == "bullet":
        return [{"level": 1, "text": str(spec.get("text", "-")), "numFormat": "USER_CHAR"}]
    return [{"level": 1, "text": str(spec.get("text", "^1.")), "numFormat": "DIGIT"}]


def _create_numbering(numberings: ET.Element, spec: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    warnings: list[dict[str, Any]] = []
    numbering_id = str(_max_child_id(numberings, "numbering") + 1)
    numbering_start = 0 if spec.get("restart", True) else int(spec.get("continue_from", 0))
    numbering = ET.Element(hh("numbering"), {"id": numbering_id, "start": str(numbering_start)})
    for raw_level in _level_specs(spec):
        try:
            level = max(int(raw_level.get("level", 1)), 1)
        except (TypeError, ValueError):
            warnings.append({"type": "LIST_LEVEL_INVALID", "value": raw_level.get("level")})
            level = 1
        text = str(raw_level.get("text", f"^{level}."))
        num_format = str(raw_level.get("numFormat", raw_level.get("num_format", "DIGIT"))).upper()
        para_head = ET.SubElement(
            numbering,
            hh("paraHead"),
            {
                "start": str(int(raw_level.get("start", spec.get("start_number", 1)))),
                "level": str(level),
                "align": "LEFT",
                "useInstWidth": "1",
                "autoIndent": "1",
                "widthAdjust": "0",
                "textOffsetType": "PERCENT",
                "textOffset": str(int(raw_level.get("text_offset", 50))),
                "numFormat": num_format,
                "charPrIDRef": str(raw_level.get("charPrIDRef", "4294967295")),
                "checkable": "0",
            },
        )
        para_head.text = text
    numberings.append(numbering)
    _bump_item_count(numberings)
    return numbering_id, warnings


def _create_para_ref(para_properties: ET.Element, numbering_id: str, level: int, spec: dict[str, Any]) -> str | None:
    source = _find_first(para_properties, "paraPr")
    if source is None:
        return None
    next_id = str(_max_child_id(para_properties, "paraPr") + 1)
    para_pr = copy.deepcopy(source)
    para_pr.attrib["id"] = next_id
    heading = _ensure_child(para_pr, "heading")
    heading.attrib["type"] = "OUTLINE"
    heading.attrib["idRef"] = numbering_id
    heading.attrib["level"] = str(max(level - 1, 0))
    left = int(spec.get("left_margin", 2000 + (level - 1) * 1200))
    intent = int(spec.get("intent", -800))
    _set_margin(para_pr, left, intent)
    para_properties.append(para_pr)
    _bump_item_count(para_properties)
    return next_id


def create_list_style(root: ET.Element, name: str, spec: dict[str, Any]) -> tuple[dict[str, str] | None, list[dict[str, Any]]]:
    warnings: list[dict[str, Any]] = []
    if spec.get("preset") and str(spec.get("preset")) not in OUTLINE_PRESETS:
        warnings.append({"type": "LIST_PRESET_UNKNOWN", "name": name, "preset": spec.get("preset")})
    numberings = _find_container(root, "numberings")
    para_properties = _find_container(root, "paraProperties")
    if numberings is None:
        return None, [{"type": "NUMBERINGS_NOT_FOUND", "name": name}]
    if para_properties is None:
        return None, [{"type": "PARA_PROPERTIES_NOT_FOUND", "name": name}]
    numbering_id, numbering_warnings = _create_numbering(numberings, spec)
    warnings.extend(numbering_warnings)
    refs: dict[str, str] = {}
    for raw_level in _level_specs(spec):
        try:
            level = max(int(raw_level.get("level", 1)), 1)
        except (TypeError, ValueError):
            level = 1
        para_pr_id = _create_para_ref(para_properties, numbering_id, level, {**spec, **raw_level})
        if para_pr_id is None:
            warnings.append({"type": "PARA_PR_TEMPLATE_NOT_FOUND", "name": name, "level": level})
            continue
        refs[str(level)] = para_pr_id
    return refs, warnings


def apply_list_style_definitions(package: HwpxPackage, definitions: dict[str, Any] | None) -> dict[str, Any]:
    style_defs = definitions or {}
    list_styles = style_defs.get("list_styles", {}) if isinstance(style_defs, dict) else {}
    if not list_styles:
        return {"status": "SKIPPED", "list_styles": {}, "warnings": []}
    header_entry = "Contents/header.xml"
    if header_entry not in package.entries:
        return {"status": "HEADER_NOT_FOUND", "list_styles": {}, "warnings": [{"type": "HEADER_NOT_FOUND"}]}
    root = package.read_xml(header_entry)
    refs: dict[str, dict[str, str]] = {}
    warnings: list[dict[str, Any]] = []
    for name, spec in list_styles.items():
        if not isinstance(spec, dict):
            warnings.append({"type": "LIST_STYLE_SPEC_INVALID", "name": name})
            continue
        level_refs, style_warnings = create_list_style(root, str(name), spec)
        if level_refs:
            refs[str(name)] = level_refs
        warnings.extend(style_warnings)
    package.write_xml(header_entry, root)
    return {"status": "PASS", "entry": header_entry, "list_styles": refs, "warnings": warnings}


def list_refs_from_names(style: dict[str, Any] | None, style_maps: dict[str, dict[str, Any]]) -> dict[str, str]:
    if not style:
        return {}
    name = style.get("list_style")
    if not name:
        return {}
    levels = style_maps.get("list_styles", {}).get(name)
    if not isinstance(levels, dict):
        return {}
    level = str(style.get("list_level", style.get("level", 1)))
    para_ref = levels.get(level) or levels.get("1")
    return {"paraPrIDRef": para_ref} if para_ref else {}


__all__ = ["OUTLINE_PRESETS", "apply_list_style_definitions", "list_refs_from_names"]
