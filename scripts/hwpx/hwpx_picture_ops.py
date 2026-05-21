"""Visible picture/control discovery and safe rebinding for HWPX sections.

This module does not synthesize new picture XML from scratch. HWPX visible
objects contain layout, anchor, shape, and control metadata that should be
cloned from a known-good template. The safe operations here are:

- inspect existing picture-like controls
- rebind existing picture references to another BinData entry/id
"""

from __future__ import annotations

from typing import Any
import copy
import xml.etree.ElementTree as ET

from hwpx_package import HwpxPackage, local_name

PICTURE_NAME_HINTS = {
    "pic",
    "picture",
    "img",
    "image",
    "draw",
}

PICTURE_ATTR_HINTS = (
    "binary",
    "bindata",
    "image",
    "img",
    "pic",
    "href",
    "ref",
    "idref",
)

IMAGE_REFERENCE_ATTR_NAMES = {
    "binaryitemidref",
    "binaryitemid",
    "bindata",
    "bindataref",
    "imgref",
    "imageref",
    "href",
    "src",
}


def _looks_like_picture_element(elem: ET.Element) -> bool:
    name = local_name(elem.tag).lower()
    if name in PICTURE_NAME_HINTS:
        return True
    if any(hint in name for hint in PICTURE_NAME_HINTS):
        return True
    for key, value in elem.attrib.items():
        k = local_name(key).lower()
        v = str(value).lower()
        if any(hint in k for hint in PICTURE_ATTR_HINTS) and (
            "bindata" in v or v.endswith((".png", ".jpg", ".jpeg", ".bmp", ".gif")) or "image" in v
        ):
            return True
    return False


def _reference_values(elem: ET.Element) -> list[dict[str, str]]:
    refs = []
    for key, value in elem.attrib.items():
        text = str(value)
        key_lower = local_name(key).lower()
        lowered = text.lower()
        if (
            "binary" in key_lower
            or "image" in key_lower
            or "ref" in key_lower
            or "bindata" in lowered
            or lowered.endswith((".png", ".jpg", ".jpeg", ".bmp", ".gif"))
            or "image" in lowered
        ):
            refs.append({"attribute": key, "value": text})
    return refs


def find_picture_objects(package: HwpxPackage) -> list[dict[str, Any]]:
    pictures = []
    for entry in package.section_entries():
        try:
            root = package.read_xml(entry)
        except Exception:
            continue
        for index, elem in enumerate(root.iter()):
            if not _looks_like_picture_element(elem):
                continue
            pictures.append(
                {
                    "index": len(pictures),
                    "entry": entry,
                    "element_index": index,
                    "tag": local_name(elem.tag),
                    "attributes": dict(elem.attrib),
                    "reference_values": _reference_values(elem),
                }
            )
    return pictures


def picture_inventory(package: HwpxPackage) -> dict[str, Any]:
    pictures = find_picture_objects(package)
    return {
        "status": "PASS" if pictures else "PICTURE_OBJECT_NOT_FOUND",
        "picture_count": len(pictures),
        "pictures": pictures,
    }


def _is_image_reference_attribute(key: str, value: str) -> bool:
    key_lower = local_name(key).lower()
    value_lower = value.lower()
    if key_lower in IMAGE_REFERENCE_ATTR_NAMES:
        return True
    if "binary" in key_lower or "bindata" in key_lower:
        return True
    if key_lower.endswith("idref") and local_name(key).lower().startswith(("img", "image", "pic", "picture")):
        return True
    if "bindata/" in value_lower or value_lower.endswith((".png", ".jpg", ".jpeg", ".bmp", ".gif")):
        return True
    return False


def _set_rebound_value(key: str, value: str, new_entry: str, new_manifest_id: str | None) -> str:
    if not _is_image_reference_attribute(key, value):
        return value
    lowered = value.lower()
    if "bindata/" in lowered or value.endswith((".png", ".jpg", ".jpeg", ".bmp", ".gif")):
        return new_entry
    if new_manifest_id:
        return new_manifest_id
    return value


def _parent_map(root: ET.Element) -> dict[ET.Element, ET.Element]:
    return {child: parent for parent in root.iter() for child in list(parent)}


def _rebind_element_tree(elem: ET.Element, new_entry: str, new_manifest_id: str | None) -> list[dict[str, str]]:
    changed = []
    for target in elem.iter():
        for key, value in list(target.attrib.items()):
            next_value = _set_rebound_value(key, str(value), new_entry, new_manifest_id)
            if next_value != value:
                target.set(key, next_value)
                changed.append(
                    {
                        "tag": local_name(target.tag),
                        "attribute": key,
                        "old": str(value),
                        "new": next_value,
                    }
                )
    return changed


def rebind_picture_object(
    package: HwpxPackage,
    picture_index: int,
    new_entry: str,
    new_manifest_id: str | None = None,
) -> dict[str, Any]:
    pictures = find_picture_objects(package)
    if picture_index < 0 or picture_index >= len(pictures):
        return {
            "status": "PICTURE_OBJECT_NOT_FOUND",
            "picture_index": picture_index,
            "picture_count": len(pictures),
        }

    target = pictures[picture_index]
    entry = target["entry"]
    root = package.read_xml(entry)
    matching = [elem for elem in root.iter() if _looks_like_picture_element(elem)]
    if picture_index >= len(matching):
        return {
            "status": "PICTURE_OBJECT_NOT_FOUND",
            "picture_index": picture_index,
            "reason": "matching_element_not_found",
        }
    elem = matching[picture_index]
    changed = []
    for key, value in list(elem.attrib.items()):
        next_value = _set_rebound_value(key, str(value), new_entry, new_manifest_id)
        if next_value != value:
            elem.set(key, next_value)
            changed.append({"attribute": key, "old": str(value), "new": next_value})
    if not changed:
        return {
            "status": "PICTURE_REFERENCE_NOT_FOUND",
            "picture_index": picture_index,
            "entry": entry,
            "tag": local_name(elem.tag),
        }
    package.write_xml(entry, root)
    return {
        "status": "PICTURE_REBIND_PASS",
        "picture_index": picture_index,
        "entry": entry,
        "tag": local_name(elem.tag),
        "changed": changed,
    }


def clone_picture_object(
    package: HwpxPackage,
    picture_index: int,
    new_entry: str,
    new_manifest_id: str | None = None,
) -> dict[str, Any]:
    pictures = find_picture_objects(package)
    if picture_index < 0 or picture_index >= len(pictures):
        return {
            "status": "PICTURE_OBJECT_NOT_FOUND",
            "picture_index": picture_index,
            "picture_count": len(pictures),
        }

    target = pictures[picture_index]
    entry = target["entry"]
    root = package.read_xml(entry)
    matching = [elem for elem in root.iter() if _looks_like_picture_element(elem)]
    if picture_index >= len(matching):
        return {
            "status": "PICTURE_OBJECT_NOT_FOUND",
            "picture_index": picture_index,
            "reason": "matching_element_not_found",
        }
    source = matching[picture_index]
    parent = _parent_map(root).get(source)
    if parent is None:
        return {
            "status": "PICTURE_PARENT_NOT_FOUND",
            "picture_index": picture_index,
            "entry": entry,
            "tag": local_name(source.tag),
        }
    clone = copy.deepcopy(source)
    changed = _rebind_element_tree(clone, new_entry, new_manifest_id)
    if not changed:
        return {
            "status": "PICTURE_REFERENCE_NOT_FOUND",
            "picture_index": picture_index,
            "entry": entry,
            "tag": local_name(source.tag),
        }
    siblings = list(parent)
    insert_at = siblings.index(source) + 1 if source in siblings else len(siblings)
    parent.insert(insert_at, clone)
    package.write_xml(entry, root)
    return {
        "status": "PICTURE_CLONE_REBIND_PASS",
        "picture_index": picture_index,
        "entry": entry,
        "source_tag": local_name(source.tag),
        "insert_index": insert_at,
        "changed": changed,
    }
