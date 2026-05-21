"""Section operations for direct HWPX package generation."""

from __future__ import annotations

from copy import deepcopy
from typing import Any
import re
import xml.etree.ElementTree as ET

from hwpx_package import HwpxPackage, local_name
from hwpx_manifest_ops import repair_package_manifest


def _section_number(entry: str) -> int:
    match = re.search(r"section(\d+)\.xml$", entry.replace("\\", "/").lower())
    return int(match.group(1)) if match else -1


def _next_section_entry(package: HwpxPackage) -> str:
    numbers = [_section_number(entry) for entry in package.section_entries()]
    next_index = (max(numbers) + 1) if numbers else 0
    return f"Contents/section{next_index}.xml"


def _clear_body_content(root: ET.Element) -> ET.Element:
    copied = deepcopy(root)
    for child in list(copied):
        if local_name(child.tag) == "p":
            copied.remove(child)
    return copied


def inspect_sections(package: HwpxPackage) -> dict[str, Any]:
    sections = []
    for index, entry in enumerate(package.section_entries()):
        try:
            root = package.read_xml(entry)
            paragraph_count = sum(1 for elem in root.iter() if local_name(elem.tag) == "p")
            table_count = sum(1 for elem in root.iter() if local_name(elem.tag) == "tbl")
            picture_count = sum(1 for elem in root.iter() if local_name(elem.tag) in {"pic", "img"})
            status = "PASS"
        except Exception as exc:  # noqa: BLE001
            paragraph_count = 0
            table_count = 0
            picture_count = 0
            status = "XML_PARSE_ERROR"
            error = str(exc)
        row = {
            "index": index,
            "entry": entry,
            "section_number": _section_number(entry),
            "status": status,
            "paragraph_count": paragraph_count,
            "table_count": table_count,
            "picture_count": picture_count,
        }
        if status != "PASS":
            row["error"] = error
        sections.append(row)
    return {
        "status": "PASS" if sections and all(item["status"] == "PASS" for item in sections) else "FAIL",
        "section_count": len(sections),
        "sections": sections,
    }


def append_section(
    package: HwpxPackage,
    *,
    clone_from_index: int = 0,
    clear_body: bool = True,
    entry_name: str | None = None,
) -> dict[str, Any]:
    sections = package.section_entries()
    if not sections:
        return {"status": "SECTION_TEMPLATE_NOT_FOUND", "section_count": 0}
    if clone_from_index < 0 or clone_from_index >= len(sections):
        return {"status": "SECTION_TEMPLATE_NOT_FOUND", "clone_from_index": clone_from_index, "section_count": len(sections)}
    source_entry = sections[clone_from_index]
    target_entry = (entry_name or _next_section_entry(package)).replace("\\", "/")
    if target_entry in package.entries:
        return {"status": "SECTION_ENTRY_ALREADY_EXISTS", "entry": target_entry}
    try:
        root = package.read_xml(source_entry)
    except Exception as exc:  # noqa: BLE001
        return {"status": "XML_PARSE_ERROR", "entry": source_entry, "error": str(exc)}
    new_root = _clear_body_content(root) if clear_body else deepcopy(root)
    package.write_xml(target_entry, new_root)
    manifest_result = repair_package_manifest(package)
    return {
        "status": "SECTION_APPEND_PASS",
        "source_entry": source_entry,
        "entry": target_entry,
        "clear_body": clear_body,
        "section_count_after": len(package.section_entries()),
        "manifest_result": manifest_result,
    }


def ensure_section_count(package: HwpxPackage, count: int, *, clear_body: bool = True) -> dict[str, Any]:
    if not isinstance(count, int) or count < 1:
        return {"status": "SECTION_COUNT_INVALID", "requested_count": count}
    results = []
    while len(package.section_entries()) < count:
        result = append_section(package, clear_body=clear_body)
        results.append(result)
        if result.get("status") != "SECTION_APPEND_PASS":
            return {
                "status": result.get("status", "SECTION_APPEND_FAIL"),
                "requested_count": count,
                "section_count": len(package.section_entries()),
                "results": results,
            }
    return {
        "status": "SECTION_COUNT_READY",
        "requested_count": count,
        "section_count": len(package.section_entries()),
        "results": results,
        "sections": inspect_sections(package),
    }


__all__ = ["append_section", "ensure_section_count", "inspect_sections"]
