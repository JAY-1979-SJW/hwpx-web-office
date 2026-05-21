"""Document metadata operations for HWPX packages."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import xml.etree.ElementTree as ET

from hwpx_package import HwpxPackage, local_name


OPF_NS = "http://www.idpf.org/2007/opf/"
OCF_NS = "urn:oasis:names:tc:opendocument:xmlns:container"
HPF_MEDIA_TYPE = "application/hwpml-package+xml"
CONTENT_HPF_ENTRY = "Contents/content.hpf"
CONTAINER_ENTRY = "META-INF/container.xml"

ET.register_namespace("opf", OPF_NS)
ET.register_namespace("ocf", OCF_NS)


def opf(tag: str) -> str:
    return f"{{{OPF_NS}}}{tag}"


def ocf(tag: str) -> str:
    return f"{{{OCF_NS}}}{tag}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _first_child(root: ET.Element, name: str) -> ET.Element | None:
    for child in list(root):
        if local_name(child.tag) == name:
            return child
    return None


def _find_metadata(root: ET.Element) -> ET.Element | None:
    for elem in root.iter():
        if local_name(elem.tag) == "metadata":
            return elem
    return None


def _ensure_metadata(root: ET.Element) -> ET.Element:
    metadata = _find_metadata(root)
    if metadata is not None:
        return metadata
    metadata = ET.Element(opf("metadata"))
    root.insert(0, metadata)
    return metadata


def _new_content_root() -> ET.Element:
    root = ET.Element(
        opf("package"),
        {
            "version": "",
            "unique-identifier": "",
            "id": "",
        },
    )
    ET.SubElement(root, opf("metadata"))
    manifest = ET.SubElement(root, opf("manifest"))
    ET.SubElement(manifest, opf("item"), {"id": "section0", "href": "Contents/section0.xml", "media-type": "application/xml"})
    spine = ET.SubElement(root, opf("spine"))
    ET.SubElement(spine, opf("itemref"), {"idref": "section0"})
    return root


def _read_or_create_content_root(package: HwpxPackage) -> tuple[ET.Element, bool]:
    if CONTENT_HPF_ENTRY in package.entries:
        return package.read_xml(CONTENT_HPF_ENTRY), False
    return _new_content_root(), True


def _set_direct_text(metadata: ET.Element, tag_name: str, value: Any) -> bool:
    if value is None:
        return False
    elem = None
    for child in list(metadata):
        if local_name(child.tag) == tag_name:
            elem = child
            break
    if elem is None:
        elem = ET.SubElement(metadata, opf(tag_name))
    elem.text = str(value)
    return True


def _set_meta(metadata: ET.Element, name: str, value: Any) -> bool:
    if value is None:
        return False
    elem = None
    for child in list(metadata):
        if local_name(child.tag) == "meta" and child.attrib.get("name") == name:
            elem = child
            break
    if elem is None:
        elem = ET.SubElement(metadata, opf("meta"), {"name": name, "content": "text"})
    elem.attrib["content"] = "text"
    elem.text = str(value)
    return True


def _keywords(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, list):
        return ", ".join(str(item) for item in value if str(item))
    return str(value)


def _ensure_container_rootfile(package: HwpxPackage) -> dict[str, Any]:
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

    for elem in rootfiles:
        if local_name(elem.tag) == "rootfile" and elem.attrib.get("full-path") == CONTENT_HPF_ENTRY:
            return {"status": "CONTAINER_ROOTFILE_EXISTS"}

    ET.SubElement(rootfiles, ocf("rootfile"), {"full-path": CONTENT_HPF_ENTRY, "media-type": HPF_MEDIA_TYPE})
    package.write_xml(CONTAINER_ENTRY, root)
    return {"status": "CONTAINER_ROOTFILE_ADDED"}


def inspect_document_metadata(package: HwpxPackage) -> dict[str, Any]:
    result: dict[str, Any] = {
        "entry": CONTENT_HPF_ENTRY,
        "exists": CONTENT_HPF_ENTRY in package.entries,
        "metadata": {},
        "meta": {},
    }
    if CONTENT_HPF_ENTRY not in package.entries:
        result["status"] = "CONTENT_HPF_NOT_FOUND"
        return result
    try:
        root = package.read_xml(CONTENT_HPF_ENTRY)
    except Exception as exc:  # noqa: BLE001
        result["status"] = "CONTENT_HPF_PARSE_ERROR"
        result["error"] = str(exc)
        return result
    metadata = _find_metadata(root)
    if metadata is None:
        result["status"] = "METADATA_NOT_FOUND"
        return result
    for child in list(metadata):
        name = local_name(child.tag)
        if name == "meta":
            meta_name = child.attrib.get("name")
            if meta_name:
                result["meta"][meta_name] = child.text or ""
        else:
            result["metadata"][name] = child.text or ""
    result["status"] = "PASS"
    return result


def apply_document_metadata(package: HwpxPackage, spec: dict[str, Any] | None) -> dict[str, Any]:
    if not spec:
        return {"status": "SKIPPED"}
    root, created_content_hpf = _read_or_create_content_root(package)
    metadata = _ensure_metadata(root)
    fields_set: list[str] = []

    direct_fields = {
        "title": spec.get("title"),
        "language": spec.get("language"),
    }
    meta_fields = {
        "creator": spec.get("creator"),
        "subject": spec.get("subject"),
        "description": spec.get("description"),
        "CreatedDate": spec.get("created_date") or spec.get("createdDate"),
        "ModifiedDate": spec.get("modified_date") or spec.get("modifiedDate") or _now_iso(),
        "date": spec.get("date"),
        "keyword": _keywords(spec.get("keywords", spec.get("keyword"))),
    }

    for field, value in direct_fields.items():
        if _set_direct_text(metadata, field, value):
            fields_set.append(field)
    for field, value in meta_fields.items():
        if _set_meta(metadata, field, value):
            fields_set.append(field)

    package.write_xml(CONTENT_HPF_ENTRY, root)
    container_result = _ensure_container_rootfile(package)
    return {
        "status": "DOCUMENT_METADATA_SET_PASS",
        "entry": CONTENT_HPF_ENTRY,
        "created_content_hpf": created_content_hpf,
        "fields_set": fields_set,
        "container": container_result,
        "metadata": inspect_document_metadata(package),
    }


__all__ = ["apply_document_metadata", "inspect_document_metadata"]
