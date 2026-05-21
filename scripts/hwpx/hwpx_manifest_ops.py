"""Package manifest and spine repair helpers for HWPX packages."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import re
import xml.etree.ElementTree as ET

from hwpx_image_ops import IMAGE_MEDIA_TYPES
from hwpx_metadata_ops import CONTENT_HPF_ENTRY, CONTAINER_ENTRY, HPF_MEDIA_TYPE, OCF_NS, OPF_NS, ocf, opf
from hwpx_package import HwpxPackage, local_name


ET.register_namespace("opf", OPF_NS)
ET.register_namespace("ocf", OCF_NS)


def _media_type(entry: str) -> str:
    lower = entry.lower()
    if lower == CONTENT_HPF_ENTRY.lower():
        return HPF_MEDIA_TYPE
    if lower.endswith(".xml"):
        return "application/xml"
    if lower.endswith(".hpf"):
        return HPF_MEDIA_TYPE
    image_type = IMAGE_MEDIA_TYPES.get(Path(entry).suffix.lower())
    if image_type:
        return image_type
    if lower.endswith(".txt"):
        return "text/plain"
    return "application/octet-stream"


def _href(entry: str) -> str:
    normalized = entry.replace("\\", "/")
    if normalized.startswith("BinData/"):
        return "../" + normalized
    return normalized


def _item_id(entry: str) -> str:
    normalized = entry.replace("\\", "/")
    lower = normalized.lower()
    if lower == "contents/header.xml":
        return "header"
    if lower == "settings.xml":
        return "settings"
    match = re.match(r"contents/section(\d+)\.xml$", lower)
    if match:
        return f"section{match.group(1)}"
    stem = Path(normalized).stem.replace(" ", "_").replace("-", "_")
    return re.sub(r"[^A-Za-z0-9_]", "_", stem) or "item"


def _manifest_entries(package: HwpxPackage) -> list[str]:
    entries = []
    for name in package.entries:
        normalized = name.replace("\\", "/")
        lower = normalized.lower()
        if lower == CONTENT_HPF_ENTRY.lower():
            continue
        if lower.startswith("contents/") and lower.endswith(".xml"):
            entries.append(normalized)
        elif lower == "settings.xml":
            entries.append(normalized)
        elif lower.startswith("bindata/"):
            entries.append(normalized)
        elif lower == "preview/prvtext.txt":
            entries.append(normalized)
    return sorted(set(entries), key=lambda item: (0 if item.lower() == "contents/header.xml" else 1, item.lower()))


def _read_or_create_content_root(package: HwpxPackage) -> tuple[ET.Element, bool]:
    if CONTENT_HPF_ENTRY in package.entries:
        return package.read_xml(CONTENT_HPF_ENTRY), False
    root = ET.Element(opf("package"), {"version": "", "unique-identifier": "", "id": ""})
    ET.SubElement(root, opf("metadata"))
    ET.SubElement(root, opf("manifest"))
    ET.SubElement(root, opf("spine"))
    return root, True


def _ensure_child(root: ET.Element, child_name: str) -> tuple[ET.Element, bool]:
    for child in list(root):
        if local_name(child.tag) == child_name:
            return child, False
    child = ET.SubElement(root, opf(child_name))
    return child, True


def _ids_in_manifest(manifest: ET.Element) -> set[str]:
    return {child.attrib.get("id", "") for child in list(manifest) if local_name(child.tag) == "item"}


def _hrefs_in_manifest(manifest: ET.Element) -> set[str]:
    return {child.attrib.get("href", "") for child in list(manifest) if local_name(child.tag) == "item"}


def _ensure_manifest_item(manifest: ET.Element, entry: str) -> dict[str, Any]:
    item_id = _item_id(entry)
    href = _href(entry)
    for child in list(manifest):
        if local_name(child.tag) != "item":
            continue
        if child.attrib.get("href") == href or child.attrib.get("id") == item_id:
            child.attrib.setdefault("media-type", _media_type(entry))
            return {"status": "EXISTS", "id": child.attrib.get("id"), "href": child.attrib.get("href")}

    existing_ids = _ids_in_manifest(manifest)
    base_id = item_id
    index = 1
    while item_id in existing_ids:
        index += 1
        item_id = f"{base_id}_{index}"
    ET.SubElement(manifest, opf("item"), {"id": item_id, "href": href, "media-type": _media_type(entry)})
    return {"status": "ADDED", "id": item_id, "href": href, "media_type": _media_type(entry)}


def _ensure_spine_item(spine: ET.Element, idref: str) -> dict[str, str]:
    for child in list(spine):
        if local_name(child.tag) == "itemref" and child.attrib.get("idref") == idref:
            return {"status": "EXISTS", "idref": idref}
    ET.SubElement(spine, opf("itemref"), {"idref": idref})
    return {"status": "ADDED", "idref": idref}


def _ensure_container(package: HwpxPackage) -> dict[str, Any]:
    if CONTAINER_ENTRY in package.entries:
        try:
            root = package.read_xml(CONTAINER_ENTRY)
        except Exception as exc:  # noqa: BLE001
            return {"status": "CONTAINER_XML_PARSE_ERROR", "error": str(exc)}
    else:
        root = ET.Element(ocf("container"))

    rootfiles = None
    for elem in root.iter():
        if local_name(elem.tag) == "rootfiles":
            rootfiles = elem
            break
    if rootfiles is None:
        rootfiles = ET.SubElement(root, ocf("rootfiles"))

    for elem in list(rootfiles):
        if local_name(elem.tag) == "rootfile" and elem.attrib.get("full-path") == CONTENT_HPF_ENTRY:
            elem.attrib["media-type"] = HPF_MEDIA_TYPE
            package.write_xml(CONTAINER_ENTRY, root)
            return {"status": "CONTAINER_ROOTFILE_EXISTS"}

    ET.SubElement(rootfiles, ocf("rootfile"), {"full-path": CONTENT_HPF_ENTRY, "media-type": HPF_MEDIA_TYPE})
    package.write_xml(CONTAINER_ENTRY, root)
    return {"status": "CONTAINER_ROOTFILE_ADDED"}


def inspect_package_manifest(package: HwpxPackage) -> dict[str, Any]:
    result: dict[str, Any] = {
        "content_entry": CONTENT_HPF_ENTRY,
        "content_exists": CONTENT_HPF_ENTRY in package.entries,
        "manifest_items": [],
        "spine_itemrefs": [],
        "missing_manifest_entries": [],
        "missing_spine_sections": [],
    }
    required_entries = _manifest_entries(package)
    if CONTENT_HPF_ENTRY not in package.entries:
        result["status"] = "CONTENT_HPF_NOT_FOUND"
        result["missing_manifest_entries"] = required_entries
        return result
    try:
        root = package.read_xml(CONTENT_HPF_ENTRY)
    except Exception as exc:  # noqa: BLE001
        result["status"] = "CONTENT_HPF_PARSE_ERROR"
        result["error"] = str(exc)
        return result
    manifest, _ = _ensure_child(root, "manifest")
    spine, _ = _ensure_child(root, "spine")
    hrefs = _hrefs_in_manifest(manifest)
    result["manifest_items"] = [
        {"id": child.attrib.get("id"), "href": child.attrib.get("href"), "media_type": child.attrib.get("media-type")}
        for child in list(manifest)
        if local_name(child.tag) == "item"
    ]
    result["spine_itemrefs"] = [
        {"idref": child.attrib.get("idref")}
        for child in list(spine)
        if local_name(child.tag) == "itemref"
    ]
    result["missing_manifest_entries"] = [entry for entry in required_entries if _href(entry) not in hrefs]
    item_ids = {item["id"] for item in result["manifest_items"]}
    spine_ids = {item["idref"] for item in result["spine_itemrefs"]}
    for entry in required_entries:
        lower = entry.lower()
        if lower == "contents/header.xml" or re.match(r"contents/section\d+\.xml$", lower):
            item_id = _item_id(entry)
            if item_id in item_ids and item_id not in spine_ids:
                result["missing_spine_sections"].append(item_id)
    result["status"] = "PASS" if not result["missing_manifest_entries"] and not result["missing_spine_sections"] else "WARN"
    return result


def repair_package_manifest(package: HwpxPackage, spec: dict[str, Any] | None = None) -> dict[str, Any]:
    spec = spec or {}
    if spec.get("enabled") is False:
        return {"status": "SKIPPED"}
    before = inspect_package_manifest(package)
    root, created_content_hpf = _read_or_create_content_root(package)
    manifest, created_manifest = _ensure_child(root, "manifest")
    spine, created_spine = _ensure_child(root, "spine")

    added_items = []
    spine_updates = []
    for entry in _manifest_entries(package):
        item_result = _ensure_manifest_item(manifest, entry)
        if item_result["status"] == "ADDED":
            added_items.append(item_result)
        lower = entry.lower()
        if lower == "contents/header.xml" or re.match(r"contents/section\d+\.xml$", lower):
            spine_result = _ensure_spine_item(spine, str(item_result.get("id") or _item_id(entry)))
            if spine_result["status"] == "ADDED":
                spine_updates.append(spine_result)

    package.write_xml(CONTENT_HPF_ENTRY, root)
    container = _ensure_container(package)
    after = inspect_package_manifest(package)
    return {
        "status": "PACKAGE_MANIFEST_REPAIR_PASS" if after.get("status") == "PASS" else "PACKAGE_MANIFEST_REPAIR_WARN",
        "created_content_hpf": created_content_hpf,
        "created_manifest": created_manifest,
        "created_spine": created_spine,
        "added_items": added_items,
        "spine_updates": spine_updates,
        "container": container,
        "before": before,
        "after": after,
        "warnings": [] if after.get("status") == "PASS" else [{"type": "PACKAGE_MANIFEST_REPAIR_INCOMPLETE"}],
    }


__all__ = ["inspect_package_manifest", "repair_package_manifest"]
