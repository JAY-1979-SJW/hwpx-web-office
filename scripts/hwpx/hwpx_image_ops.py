"""Image entry helpers for direct HWPX package editing.

These helpers operate only on package entries and XML text maps. They do not
create visible HWPX picture objects or change anchored layout XML.
"""

from __future__ import annotations

import hashlib
from pathlib import Path


IMAGE_EXTENSIONS = {".bmp", ".gif", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".wmf", ".emf"}
IMAGE_MEDIA_TYPES = {
    ".bmp": "image/bmp",
    ".gif": "image/gif",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".wmf": "image/wmf",
    ".emf": "image/emf",
}


def is_image_entry(name: str) -> bool:
    return Path(name).suffix.lower() in IMAGE_EXTENSIONS


def bindata_image_entries(entry_names: list[str]) -> list[str]:
    return [
        entry
        for entry in entry_names
        if entry.replace("\\", "/").lower().startswith("bindata/") and is_image_entry(entry)
    ]


def xml_references_for_entry(image_entry: str, xml_text_by_entry: dict[str, str]) -> dict:
    normalized = image_entry.replace("\\", "/")
    basename = Path(normalized).name
    stem = Path(normalized).stem
    referenced_by = []
    reference_count = 0
    for entry, xml_text in xml_text_by_entry.items():
        count = xml_text.count(normalized) + xml_text.count(basename)
        if stem:
            count += xml_text.count(stem)
        if count:
            referenced_by.append(entry)
            reference_count += count
    return {"referenced_by_xml": referenced_by, "reference_count": reference_count}


def image_inventory(entries: dict[str, bytes], xml_text_by_entry: dict[str, str]) -> list[dict]:
    images = []
    for index, entry in enumerate(bindata_image_entries(list(entries))):
        data = entries[entry]
        refs = xml_references_for_entry(entry, xml_text_by_entry)
        images.append(
            {
                "index": index,
                "entry_name": entry,
                "extension": Path(entry).suffix.lower(),
                "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "referenced_by_xml": refs["referenced_by_xml"],
                "reference_count": refs["reference_count"],
            }
        )
    return images


def replace_image_data(
    entries: dict[str, bytes],
    xml_text_by_entry: dict[str, str],
    entry_name: str,
    replacement_path: Path,
) -> dict:
    replacement_path = Path(replacement_path)
    if not replacement_path.exists():
        return {"status": "REPLACEMENT_NOT_FOUND", "replacement": str(replacement_path)}
    if entry_name not in entries or not is_image_entry(entry_name):
        return {"status": "IMAGE_NOT_FOUND", "entry_name": entry_name}
    old_ext = Path(entry_name).suffix.lower()
    replacement_ext = replacement_path.suffix.lower()
    if old_ext != replacement_ext:
        return {
            "status": "IMAGE_EXTENSION_MISMATCH",
            "entry_name": entry_name,
            "entry_extension": old_ext,
            "replacement_extension": replacement_ext,
        }
    old_data = entries[entry_name]
    new_data = replacement_path.read_bytes()
    before_refs = xml_references_for_entry(entry_name, xml_text_by_entry)
    entries[entry_name] = new_data
    after_refs = xml_references_for_entry(entry_name, xml_text_by_entry)
    old_hash = hashlib.sha256(old_data).hexdigest()
    new_hash = hashlib.sha256(new_data).hexdigest()
    return {
        "status": "IMAGE_REPLACE_PASS",
        "entry_name": entry_name,
        "replacement": str(replacement_path),
        "old_size": len(old_data),
        "new_size": len(new_data),
        "old_sha256": old_hash,
        "new_sha256": new_hash,
        "hash_changed": old_hash != new_hash,
        "xml_refs_before": before_refs,
        "xml_refs_after": after_refs,
        "xml_refs_preserved": before_refs == after_refs,
    }


def add_bindata_image_data(
    entries: dict[str, bytes],
    image_path: Path,
    entry_name: str = "BinData/image001.png",
) -> dict:
    image_path = Path(image_path)
    if not image_path.exists():
        return {"status": "REPLACEMENT_NOT_FOUND", "image": str(image_path)}
    normalized = entry_name.replace("\\", "/")
    if not normalized.lower().startswith("bindata/") or not is_image_entry(normalized):
        return {"status": "INVALID_IMAGE_ENTRY", "entry_name": entry_name}
    if normalized in entries:
        return {"status": "IMAGE_ENTRY_ALREADY_EXISTS", "entry_name": normalized}
    image_data = image_path.read_bytes()
    entries[normalized] = image_data
    manifest_result = add_content_manifest_item(entries, normalized)
    return {
        "status": "IMAGE_BINDATA_ADD_PASS",
        "entry_name": normalized,
        "source": str(image_path),
        "size": len(image_data),
        "sha256": hashlib.sha256(image_data).hexdigest(),
        "manifest": manifest_result,
    }


def add_content_manifest_item(entries: dict[str, bytes], entry_name: str) -> dict:
    content_entry = "Contents/content.hpf"
    if content_entry not in entries:
        return {"status": "CONTENT_HPF_NOT_FOUND"}
    content = entries[content_entry].decode("utf-8", errors="replace")
    if entry_name in content or Path(entry_name).name in content:
        return {"status": "CONTENT_HPF_ALREADY_REFERENCES_ENTRY"}
    media_type = IMAGE_MEDIA_TYPES.get(Path(entry_name).suffix.lower(), "application/octet-stream")
    item_id = Path(entry_name).stem.replace(" ", "_")
    href = "../" + entry_name
    item = f'<opf:item id="{item_id}" href="{href}" media-type="{media_type}"/>'
    marker = "</opf:manifest>"
    if marker not in content:
        return {"status": "CONTENT_HPF_MANIFEST_NOT_FOUND"}
    entries[content_entry] = content.replace(marker, item + marker, 1).encode("utf-8")
    return {"status": "CONTENT_HPF_ITEM_ADDED", "href": href, "media_type": media_type, "id": item_id}
