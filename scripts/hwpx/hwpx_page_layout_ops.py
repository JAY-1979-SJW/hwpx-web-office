"""Page and section layout operations for HWPX packages."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

from hwpx_package import HwpxPackage, local_name

HP_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"
HS_NS = "http://www.hancom.co.kr/hwpml/2011/section"

DEFAULT_PAGE = {
    "orientation": "portrait",
    "width": 59528,
    "height": 84189,
    "gutter_type": "LEFT_ONLY",
}

DEFAULT_MARGINS = {
    "left": 5669,
    "right": 5669,
    "top": 5669,
    "bottom": 2834,
    "header": 0,
    "footer": 0,
    "gutter": 0,
}

MARGIN_FIELDS = tuple(DEFAULT_MARGINS)


def _qname(local: str, namespace: str = HP_NS) -> str:
    return f"{{{namespace}}}{local}"


def _find_first(root: ET.Element, local: str) -> ET.Element | None:
    for elem in root.iter():
        if local_name(elem.tag) == local:
            return elem
    return None


def _find_section_parent(root: ET.Element) -> ET.Element:
    sec_pr = _find_first(root, "secPr")
    if sec_pr is not None:
        return sec_pr

    first_paragraph = _find_first(root, "p")
    if first_paragraph is None:
        first_paragraph = ET.Element(_qname("p"))
        root.insert(0, first_paragraph)

    first_run = None
    for child in list(first_paragraph):
        if local_name(child.tag) == "run":
            first_run = child
            break
    if first_run is None:
        first_run = ET.Element(_qname("run"))
        first_paragraph.insert(0, first_run)

    sec_pr = ET.Element(
        _qname("secPr"),
        {
            "id": "",
            "textDirection": "HORIZONTAL",
            "spaceColumns": "1134",
            "tabStop": "8000",
        },
    )
    first_run.insert(0, sec_pr)
    return sec_pr


def _find_or_create_page_pr(root: ET.Element) -> tuple[ET.Element, ET.Element, bool]:
    sec_pr = _find_section_parent(root)
    page_pr = None
    for child in list(sec_pr):
        if local_name(child.tag) == "pagePr":
            page_pr = child
            break
    created = False
    if page_pr is None:
        page_pr = ET.Element(_qname("pagePr"))
        sec_pr.append(page_pr)
        created = True
    return sec_pr, page_pr, created


def _find_or_create_margin(page_pr: ET.Element) -> tuple[ET.Element, bool]:
    margin = None
    for child in list(page_pr):
        if local_name(child.tag) == "margin":
            margin = child
            break
    created = False
    if margin is None:
        margin = ET.Element(_qname("margin"))
        page_pr.append(margin)
        created = True
    return margin, created


def _resolve_margins(layout: dict[str, Any], errors: list[dict[str, Any]]) -> dict[str, int]:
    raw_margins = layout.get("margins", {})
    if raw_margins is None:
        raw_margins = {}
    if not isinstance(raw_margins, dict):
        errors.append({"type": "PAGE_MARGINS_NOT_OBJECT", "value": raw_margins})
        raw_margins = {}

    margins: dict[str, int] = {}
    for field, default in DEFAULT_MARGINS.items():
        value = raw_margins.get(field, default)
        if not isinstance(value, int) or value < 0:
            errors.append({"type": "PAGE_MARGIN_INVALID", "field": field, "value": value})
            value = default
        margins[field] = value
    return margins


def normalize_page_layout(layout: dict[str, Any] | None) -> dict[str, Any]:
    layout = layout or {}
    warnings: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    section_index = layout.get("section_index", 0)
    if not isinstance(section_index, int) or section_index < 0:
        errors.append({"type": "SECTION_INDEX_INVALID", "value": section_index})
        section_index = 0

    orientation = str(layout.get("orientation", DEFAULT_PAGE["orientation"])).lower()
    if orientation not in {"portrait", "landscape"}:
        errors.append({"type": "PAGE_ORIENTATION_INVALID", "value": layout.get("orientation")})
        orientation = DEFAULT_PAGE["orientation"]

    width = layout.get("width", DEFAULT_PAGE["width"])
    height = layout.get("height", DEFAULT_PAGE["height"])
    if not isinstance(width, int) or width <= 0:
        errors.append({"type": "PAGE_WIDTH_INVALID", "value": width})
        width = DEFAULT_PAGE["width"]
    if not isinstance(height, int) or height <= 0:
        errors.append({"type": "PAGE_HEIGHT_INVALID", "value": height})
        height = DEFAULT_PAGE["height"]

    if orientation == "landscape" and width < height:
        width, height = height, width
        warnings.append({"type": "PAGE_DIMENSIONS_SWAPPED_FOR_LANDSCAPE"})
    elif orientation == "portrait" and width > height:
        width, height = height, width
        warnings.append({"type": "PAGE_DIMENSIONS_SWAPPED_FOR_PORTRAIT"})

    margins = _resolve_margins(layout, errors)

    gutter_type = str(layout.get("gutter_type", DEFAULT_PAGE["gutter_type"]))
    return {
        "section_index": section_index,
        "orientation": orientation,
        "landscape": "WIDELY" if orientation == "landscape" else "NARROWLY",
        "width": width,
        "height": height,
        "gutter_type": gutter_type,
        "margins": margins,
        "warnings": warnings,
        "errors": errors,
    }


def inspect_page_layout(package: HwpxPackage, section_index: int = 0) -> dict[str, Any]:
    sections = package.section_entries()
    if section_index < 0 or section_index >= len(sections):
        return {
            "status": "SECTION_NOT_FOUND",
            "section_index": section_index,
            "section_count": len(sections),
        }
    entry = sections[section_index]
    root = package.read_xml(entry)
    page_pr = _find_first(root, "pagePr")
    margin = _find_first(page_pr, "margin") if page_pr is not None else None
    return {
        "status": "PASS" if page_pr is not None else "PAGE_LAYOUT_NOT_FOUND",
        "section_index": section_index,
        "entry": entry,
        "page_pr": dict(page_pr.attrib) if page_pr is not None else {},
        "margin": dict(margin.attrib) if margin is not None else {},
    }


def set_page_layout(package: HwpxPackage, layout: dict[str, Any] | None) -> dict[str, Any]:
    normalized = normalize_page_layout(layout)
    if normalized["errors"]:
        return {
            "status": "PAGE_LAYOUT_INVALID",
            "normalized": normalized,
            "warnings": normalized["warnings"],
        }

    sections = package.section_entries()
    section_index = normalized["section_index"]
    if section_index >= len(sections):
        return {
            "status": "SECTION_NOT_FOUND",
            "section_index": section_index,
            "section_count": len(sections),
            "warnings": normalized["warnings"],
        }

    entry = sections[section_index]
    root = package.read_xml(entry)
    before = inspect_page_layout(package, section_index)
    _sec_pr, page_pr, created_page_pr = _find_or_create_page_pr(root)
    margin, created_margin = _find_or_create_margin(page_pr)

    page_pr.set("landscape", normalized["landscape"])
    page_pr.set("width", str(normalized["width"]))
    page_pr.set("height", str(normalized["height"]))
    page_pr.set("gutterType", normalized["gutter_type"])
    for field in MARGIN_FIELDS:
        margin.set(field, str(normalized["margins"][field]))

    package.write_xml(entry, root)
    after = inspect_page_layout(package, section_index)
    return {
        "status": "PAGE_LAYOUT_SET_PASS",
        "section_index": section_index,
        "entry": entry,
        "created_page_pr": created_page_pr,
        "created_margin": created_margin,
        "before": before,
        "after": after,
        "normalized": normalized,
        "warnings": normalized["warnings"],
    }


__all__ = ["inspect_page_layout", "normalize_page_layout", "set_page_layout"]
