"""HWPX package injection helpers for full-fidelity conversion reports."""

from __future__ import annotations

import hashlib
import json
import time
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any

import olefile

from hwp_full_fidelity_audit import build_original_integrity
from hwp_full_fidelity_header import (
    build_decoded_header_xml,
    build_fontface_mapping,
    build_list_style_mapping,
    decoded_header_summary,
)
from hwp_full_fidelity_section_updates import (
    build_body_style_section_updates,
    build_page_layout_section_updates,
    build_table_layout_section_updates,
)
from hwpx_element_factory import create_picture_paragraph

OPF_NS = "http://www.idpf.org/2007/opf/"
HP_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"
HC_NS = "http://www.hancom.co.kr/hwpml/2011/core"
ET.register_namespace("opf", OPF_NS)
ET.register_namespace("hp", HP_NS)
ET.register_namespace("hc", HC_NS)

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


def _opf(tag: str) -> str:
    return f"{{{OPF_NS}}}{tag}"


def _xml_string(root: ET.Element) -> str:
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(
        root, encoding="unicode", short_empty_elements=True
    )


def _xml_local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _hp(tag: str) -> str:
    return f"{{{HP_NS}}}{tag}"


def _hc(tag: str) -> str:
    return f"{{{HC_NS}}}{tag}"


def _manifest_media_type(entry: str) -> str:
    lower = entry.lower()
    if lower.endswith(".xml"):
        return "application/xml"
    if lower.endswith(".txt"):
        return "text/plain"
    return IMAGE_MEDIA_TYPES.get(Path(entry).suffix.lower(), "application/octet-stream")


def _manifest_href(entry: str) -> str:
    normalized = entry.replace("\\", "/")
    if normalized.startswith("BinData/"):
        return "../" + normalized
    return normalized


def _manifest_id(entry: str) -> str:
    normalized = entry.replace("\\", "/")
    if normalized.lower() == "contents/header.xml":
        return "header"
    stem = Path(normalized).stem.replace(" ", "_").replace("-", "_")
    text = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in stem)
    return text or "item"


def _ensure_manifest_item(manifest: ET.Element, entry: str) -> dict[str, Any]:
    href = _manifest_href(entry)
    item_id = _manifest_id(entry)
    for child in list(manifest):
        if child.tag.endswith("}item") or child.tag == "item":
            if child.attrib.get("href") == href or child.attrib.get("id") == item_id:
                child.attrib.setdefault("media-type", _manifest_media_type(entry))
                return {
                    "status": "EXISTS",
                    "id": child.attrib.get("id"),
                    "href": child.attrib.get("href"),
                }
    existing_ids = {
        child.attrib.get("id", "")
        for child in list(manifest)
        if child.tag.endswith("}item") or child.tag == "item"
    }
    base_id = item_id
    index = 1
    while item_id in existing_ids:
        index += 1
        item_id = f"{base_id}_{index}"
    ET.SubElement(
        manifest,
        _opf("item"),
        {"id": item_id, "href": href, "media-type": _manifest_media_type(entry)},
    )
    return {
        "status": "ADDED",
        "id": item_id,
        "href": href,
        "media_type": _manifest_media_type(entry),
    }


def _find_manifest_and_spine(root: ET.Element) -> tuple[ET.Element | None, ET.Element | None]:
    manifest = None
    spine = None
    for elem in root.iter():
        if elem.tag == _opf("manifest") or elem.tag.endswith("}manifest") or elem.tag == "manifest":
            manifest = elem
        elif elem.tag == _opf("spine") or elem.tag.endswith("}spine") or elem.tag == "spine":
            spine = elem
    return manifest, spine


def _rebuild_spine_itemrefs(
    spine: ET.Element, required_entries: list[str], section_entries: list[str]
) -> None:
    for child in list(spine):
        if child.tag.endswith("}itemref") or child.tag == "itemref":
            spine.remove(child)
    if "Contents/header.xml" in required_entries:
        ET.SubElement(spine, _opf("itemref"), {"idref": "header", "linear": "yes"})
    for entry in section_entries:
        section_id = _manifest_id(entry)
        ET.SubElement(spine, _opf("itemref"), {"idref": section_id})


def _content_hpf_with_entries(xml_text: str, entries: list[str]) -> str:
    try:
        root = ET.fromstring(xml_text.encode("utf-8"))
    except ET.ParseError:
        return xml_text
    manifest, spine = _find_manifest_and_spine(root)
    if manifest is None:
        manifest = ET.SubElement(root, _opf("manifest"))
    normalized_entries = [entry.replace("\\", "/") for entry in entries]
    section_entries = sorted({
        entry
        for entry in normalized_entries
        if entry.lower().startswith("contents/section") and entry.lower().endswith(".xml")
    })
    required_entries = (
        ["Contents/header.xml"]
        + section_entries
        + [
            "settings.xml",
            "Preview/PrvText.txt",
        ]
        + [entry for entry in normalized_entries if entry.startswith("BinData/")]
    )
    manifest_results = [
        _ensure_manifest_item(manifest, entry) for entry in sorted(set(required_entries))
    ]
    if spine is None:
        spine = ET.SubElement(root, _opf("spine"))
    _rebuild_spine_itemrefs(spine, required_entries, section_entries)
    root.attrib["_manifest_update_count"] = str(
        sum(1 for row in manifest_results if row.get("status") == "ADDED")
    )
    root.attrib.pop("_manifest_update_count", None)
    return _xml_string(root)


def _content_hpf_with_header(xml_text: str) -> str:
    return _content_hpf_with_entries(xml_text, ["Contents/header.xml"])


def _copy_bindata_from_source(
    input_path: Path | None, decoded_docinfo: dict[str, Any] | None = None
) -> tuple[dict[str, bytes], dict[str, Any]]:
    if not input_path:
        return {}, {"status": "SKIPPED", "reason": "INPUT_NOT_AVAILABLE"}
    source = Path(input_path).expanduser().resolve()
    if not source.exists():
        return {}, {"status": "FAIL", "reason": "INPUT_NOT_FOUND", "input": str(source)}
    try:
        ole = olefile.OleFileIO(str(source))
    except Exception as exc:  # ruff: ignore[blind-except]
        return {}, {
            "status": "FAIL",
            "reason": "OLE_OPEN_FAILED",
            "input": str(source),
            "error": str(exc),
        }
    updates: dict[str, bytes] = {}
    items: list[dict[str, Any]] = []
    records = _bindata_records(decoded_docinfo)
    with ole:
        for path_parts in sorted(ole.listdir(streams=True, storages=False)):
            name = "/".join(path_parts)
            if not name.startswith("BinData/"):
                continue
            data = ole.openstream(name).read()
            normalized = name.replace("\\", "/")
            record = _record_for_bindata_entry(normalized, records)
            updates[normalized] = data
            row = {
                "entry": normalized,
                "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "media_type": _manifest_media_type(normalized),
                "manifest_id": _manifest_id(normalized),
                "numeric_id": _bindata_numeric_id(normalized),
                "docinfo_record_matched": record is not None,
            }
            if record is not None:
                row["docinfo"] = {
                    "index": record.get("index"),
                    "data_type": record.get("data_type"),
                    "compression": record.get("compression"),
                    "state": record.get("state"),
                    "storage_id": record.get("storage_id"),
                    "extension": record.get("extension"),
                    "stream_name": record.get("stream_name"),
                    "manifest_id": record.get("manifest_id"),
                }
            items.append(row)
    copied_names = {str(item.get("entry") or "").lower() for item in items}
    missing_records = []
    for record in records:
        stream_name = str(record.get("stream_name") or "").replace("\\", "/")
        if stream_name and stream_name.lower() not in copied_names:
            missing_records.append({
                "index": record.get("index"),
                "data_type": record.get("data_type"),
                "storage_id": record.get("storage_id"),
                "extension": record.get("extension"),
                "stream_name": stream_name,
            })
    return updates, {
        "status": "PASS"
        if items and not missing_records
        else ("NO_BINDATA_STREAMS" if not items else "PARTIAL_RECORD_STREAM_MISMATCH"),
        "input": str(source),
        "bindata_count": len(items),
        "docinfo_binary_data_count": len(records),
        "docinfo_matched_count": sum(1 for item in items if item.get("docinfo_record_matched")),
        "missing_docinfo_stream_count": len(missing_records),
        "missing_docinfo_streams": missing_records,
        "items": items,
    }


def _section_sort_key(name: str) -> tuple[int, str]:
    stem = name.replace("\\", "/").rsplit("/", 1)[-1]
    digits = "".join(ch for ch in stem if ch.isdigit())
    return (int(digits) if digits else 999999, name.lower())


def _next_paragraph_id(root: ET.Element) -> str:
    max_id = -1
    for elem in root.iter():
        if _xml_local_name(elem.tag) != "p":
            continue
        try:
            max_id = max(max_id, int(elem.attrib.get("id", "-1")))
        except ValueError:
            continue
    return str(max_id + 1)


def _image_bindata_items(bindata_report: dict[str, Any]) -> list[dict[str, Any]]:
    items = bindata_report.get("items") if isinstance(bindata_report.get("items"), list) else []
    result = []
    for item in items:
        if not isinstance(item, dict):
            continue
        entry = str(item.get("entry") or "").replace("\\", "/")
        if not entry.startswith("BinData/"):
            continue
        if _manifest_media_type(entry).startswith("image/"):
            row = dict(item)
            row["entry"] = entry
            result.append(row)
    return result


def _body_record_tag_count(analysis: dict[str, Any], tag_ids: set[int]) -> int:
    record_counts = (
        analysis.get("record_counts") if isinstance(analysis.get("record_counts"), dict) else {}
    )
    total = 0
    for tag_id in tag_ids:
        total += int(record_counts.get(str(tag_id)) or record_counts.get(tag_id) or 0)
    return total


def _safe_positive_int(value: Any, default: int, *, maximum: int = 200000) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    if parsed <= 0:
        return default
    if parsed > maximum and parsed % 256 == 0:
        parsed //= 256
    return parsed if 0 < parsed <= maximum else default


def _shape_layout_rectangles(analysis: dict[str, Any]) -> list[dict[str, Any]]:
    shape_layout = (
        analysis.get("shape_layout") if isinstance(analysis.get("shape_layout"), dict) else {}
    )
    sections = (
        shape_layout.get("sections") if isinstance(shape_layout.get("sections"), list) else []
    )
    rectangles = []
    for section in sections:
        section_rectangles = (
            section.get("rectangles") if isinstance(section.get("rectangles"), list) else []
        )
        for row in section_rectangles:
            if isinstance(row, dict):
                rectangles.append(row)
    return rectangles


def _shape_layout_pictures(analysis: dict[str, Any]) -> list[dict[str, Any]]:
    shape_layout = (
        analysis.get("shape_layout") if isinstance(analysis.get("shape_layout"), dict) else {}
    )
    sections = (
        shape_layout.get("sections") if isinstance(shape_layout.get("sections"), list) else []
    )
    pictures = []
    for section in sections:
        section_pictures = (
            section.get("pictures") if isinstance(section.get("pictures"), list) else []
        )
        for row in section_pictures:
            if isinstance(row, dict):
                pictures.append(row)
    return pictures


def _rectangle_geometry(rectangle_row: dict[str, Any] | None) -> dict[str, Any]:
    rectangle = (
        rectangle_row.get("rectangle")
        if isinstance(rectangle_row, dict) and isinstance(rectangle_row.get("rectangle"), dict)
        else {}
    )
    component = (
        rectangle_row.get("component")
        if isinstance(rectangle_row, dict) and isinstance(rectangle_row.get("component"), dict)
        else {}
    )
    control = (
        rectangle_row.get("control")
        if isinstance(rectangle_row, dict) and isinstance(rectangle_row.get("control"), dict)
        else {}
    )
    control_mapped = isinstance(rectangle_row, dict) and isinstance(
        rectangle_row.get("control"), dict
    )
    bbox = rectangle.get("bbox") if isinstance(rectangle.get("bbox"), dict) else {}
    width = _safe_positive_int(bbox.get("width"), 12000)
    height = _safe_positive_int(bbox.get("height"), 5000)
    raw_points = rectangle.get("points") if isinstance(rectangle.get("points"), list) else []
    left = int(bbox.get("left") or 0)
    top = int(bbox.get("top") or 0)
    points = []
    for point in raw_points[:4]:
        if not isinstance(point, dict):
            continue
        points.append({
            "x": max(0, int(point.get("x") or 0) - left),
            "y": max(0, int(point.get("y") or 0) - top),
        })
    while len(points) < 4:
        fallback = [(0, 0), (width, 0), (width, height), (0, height)][len(points)]
        points.append({"x": fallback[0], "y": fallback[1]})
    offset = component.get("offset") if isinstance(component.get("offset"), dict) else {}
    rotation_center = (
        component.get("rotation_center")
        if isinstance(component.get("rotation_center"), dict)
        else {}
    )
    return {
        "width": width,
        "height": height,
        "round_ratio": int(rectangle.get("round_ratio") or 0),
        "points": points[:4],
        "offset": {"x": int(offset.get("x") or 0), "y": int(offset.get("y") or 0)},
        "position": _control_position(control),
        "position_mapped": control_mapped,
        "layout_policy_mapped": isinstance(control.get("layout"), dict),
        "rotation": int(component.get("rotation") or 0),
        "rotation_center": {
            "x": int(rotation_center.get("x") or width // 2),
            "y": int(rotation_center.get("y") or height // 2),
        },
        "source_record_index": rectangle_row.get("record_index")
        if isinstance(rectangle_row, dict)
        else None,
        "component_record_index": rectangle_row.get("component_record_index")
        if isinstance(rectangle_row, dict)
        else None,
        "control_record_index": rectangle_row.get("control_record_index")
        if isinstance(rectangle_row, dict)
        else None,
    }


def _control_position(control: dict[str, Any]) -> dict[str, Any]:
    position = control.get("position") if isinstance(control.get("position"), dict) else {}
    layout = control.get("layout") if isinstance(control.get("layout"), dict) else {}
    margins = control.get("margins") if isinstance(control.get("margins"), dict) else {}
    mapped = {
        "horizontal_offset": int(position.get("horizontal_offset") or 0),
        "vertical_offset": int(position.get("vertical_offset") or 0),
        "width": int(position.get("width") or 0),
        "height": int(position.get("height") or 0),
        "z_order": int(position.get("z_order") or 0),
        "text_wrap": str(layout.get("text_wrap") or "TOP_AND_BOTTOM"),
        "text_flow": str(layout.get("text_flow") or "BOTH_SIDES"),
        "treat_as_char": bool(layout.get("treat_as_char", True)),
        "flow_with_text": bool(layout.get("flow_with_text", False)),
        "allow_overlap": bool(layout.get("allow_overlap", False)),
        "vert_rel_to": str(layout.get("vert_rel_to") or "PARA"),
        "horz_rel_to": str(layout.get("horz_rel_to") or "PARA"),
    }
    if margins:
        mapped["margins"] = {
            "left": int(margins.get("left") or 0),
            "right": int(margins.get("right") or 0),
            "top": int(margins.get("top") or 0),
            "bottom": int(margins.get("bottom") or 0),
        }
    return mapped


def _bool_attr(value: Any) -> str:
    return "1" if bool(value) else "0"


def _shape_object_attrs(shape_id: int, position: dict[str, Any], **extra: str) -> dict[str, str]:
    attrs = {
        "id": str(shape_id),
        "zOrder": str(int(position.get("z_order") or 0)),
        "numberingType": "PICTURE",
        "textWrap": str(position.get("text_wrap") or "TOP_AND_BOTTOM"),
        "textFlow": str(position.get("text_flow") or "BOTH_SIDES"),
        "lock": "0",
        "dropcapstyle": "None",
    }
    attrs.update(extra)
    return attrs


def _shape_pos_attrs(position: dict[str, Any]) -> dict[str, str]:
    return {
        "treatAsChar": _bool_attr(position.get("treat_as_char", True)),
        "affectLSpacing": "0",
        "flowWithText": _bool_attr(position.get("flow_with_text", False)),
        "allowOverlap": _bool_attr(position.get("allow_overlap", False)),
        "holdAnchorAndSO": "0",
        "vertRelTo": str(position.get("vert_rel_to") or "PARA"),
        "horzRelTo": str(position.get("horz_rel_to") or "PARA"),
        "vertAlign": "TOP",
        "horzAlign": "LEFT",
        "vertOffset": str(max(int(position.get("vertical_offset") or 0), 0)),
        "horzOffset": str(max(int(position.get("horizontal_offset") or 0), 0)),
    }


def _shape_margin_attrs(position: dict[str, Any]) -> dict[str, str]:
    margins = position.get("margins") if isinstance(position.get("margins"), dict) else {}
    return {
        "left": str(max(int(margins.get("left") or 0), 0)),
        "right": str(max(int(margins.get("right") or 0), 0)),
        "top": str(max(int(margins.get("top") or 0), 0)),
        "bottom": str(max(int(margins.get("bottom") or 0), 0)),
    }


def _picture_geometry(picture_row: dict[str, Any] | None) -> dict[str, Any]:
    picture = (
        picture_row.get("picture")
        if isinstance(picture_row, dict) and isinstance(picture_row.get("picture"), dict)
        else {}
    )
    component = (
        picture_row.get("component")
        if isinstance(picture_row, dict) and isinstance(picture_row.get("component"), dict)
        else {}
    )
    control = (
        picture_row.get("control")
        if isinstance(picture_row, dict) and isinstance(picture_row.get("control"), dict)
        else {}
    )
    bbox = picture.get("bbox") if isinstance(picture.get("bbox"), dict) else {}
    component_size = (
        component.get("current_size_normalized")
        if isinstance(component.get("current_size_normalized"), dict)
        else {}
    )
    control_position = _control_position(control)
    width = _safe_positive_int(
        bbox.get("width"), _safe_positive_int(component_size.get("width"), 12000)
    )
    height = _safe_positive_int(
        bbox.get("height"), _safe_positive_int(component_size.get("height"), 9000)
    )
    return {
        "width": width,
        "height": height,
        "position": control_position,
        "binary_data_id": picture.get("binary_data_id"),
        "source_record_index": picture_row.get("record_index")
        if isinstance(picture_row, dict)
        else None,
        "component_record_index": picture_row.get("component_record_index")
        if isinstance(picture_row, dict)
        else None,
        "control_record_index": picture_row.get("control_record_index")
        if isinstance(picture_row, dict)
        else None,
        "geometry_mapped": isinstance(picture_row, dict) and bool(width and height),
        "position_mapped": isinstance(picture_row, dict)
        and isinstance(picture_row.get("control"), dict),
        "layout_policy_mapped": isinstance(control.get("layout"), dict),
    }


def _bindata_numeric_id(entry: str) -> int | None:
    stem = Path(entry.replace("\\", "/")).stem
    suffix = stem[3:] if stem.upper().startswith("BIN") else stem
    token = "".join(ch for ch in suffix if ch.isdigit() or ch.upper() in "ABCDEF")
    if not token:
        return None
    try:
        return int(token, 16)
    except ValueError:
        return None


def _bindata_records(decoded_docinfo: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(decoded_docinfo, dict):
        return []
    rows = (
        decoded_docinfo.get("binary_data")
        if isinstance(decoded_docinfo.get("binary_data"), list)
        else []
    )
    return [row for row in rows if isinstance(row, dict)]


def _normalized_ext(value: Any) -> str:
    return str(value or "").strip().lstrip(".").lower()


def _record_for_bindata_entry(entry: str, records: list[dict[str, Any]]) -> dict[str, Any] | None:
    normalized = entry.replace("\\", "/")
    entry_id = _bindata_numeric_id(normalized)
    entry_ext = _normalized_ext(Path(normalized).suffix)
    for row in records:
        if str(row.get("stream_name") or "").replace("\\", "/").lower() == normalized.lower():
            return row
    for row in records:
        try:
            storage_id = int(row.get("storage_id"))
        except (TypeError, ValueError):
            continue
        if entry_id == storage_id:
            record_ext = _normalized_ext(row.get("extension"))
            if not record_ext or not entry_ext or record_ext == entry_ext:
                return row
    return None


def _image_item_for_picture(
    image_items: list[dict[str, Any]], picture_geometry: dict[str, Any], fallback_index: int
) -> tuple[dict[str, Any], bool]:
    binary_data_id = picture_geometry.get("binary_data_id")
    try:
        wanted = int(binary_data_id)
    except (TypeError, ValueError):
        wanted = 0
    if wanted > 0:
        for item in image_items:
            if _bindata_numeric_id(str(item.get("entry") or "")) == wanted:
                return item, True
    return image_items[fallback_index % len(image_items)], False


def _create_rectangle_shape(shape_id: int, geometry: dict[str, Any] | None = None) -> ET.Element:
    geometry = geometry or {}
    width = _safe_positive_int(geometry.get("width"), 12000)
    height = _safe_positive_int(geometry.get("height"), 5000)
    offset = geometry.get("offset") if isinstance(geometry.get("offset"), dict) else {}
    position = geometry.get("position") if isinstance(geometry.get("position"), dict) else {}
    rotation_center = (
        geometry.get("rotation_center") if isinstance(geometry.get("rotation_center"), dict) else {}
    )
    points = geometry.get("points") if isinstance(geometry.get("points"), list) else []
    rect = ET.Element(
        _hp("rect"),
        _shape_object_attrs(
            shape_id,
            position,
            href="",
            groupLevel="0",
            instid=str(shape_id),
            ratio=str(int(geometry.get("round_ratio") or 0)),
        ),
    )
    ET.SubElement(
        rect,
        _hp("offset"),
        {"x": str(int(offset.get("x") or 0)), "y": str(int(offset.get("y") or 0))},
    )
    ET.SubElement(rect, _hp("orgSz"), {"width": str(width), "height": str(height)})
    ET.SubElement(rect, _hp("curSz"), {"width": str(width), "height": str(height)})
    ET.SubElement(rect, _hp("flip"), {"horizontal": "0", "vertical": "0"})
    ET.SubElement(
        rect,
        _hp("rotationInfo"),
        {
            "angle": str(int(geometry.get("rotation") or 0)),
            "centerX": str(int(rotation_center.get("x") or width // 2)),
            "centerY": str(int(rotation_center.get("y") or height // 2)),
            "rotateimage": "0",
        },
    )
    rendering = ET.SubElement(rect, _hp("renderingInfo"))
    for name in ("transMatrix", "scaMatrix", "rotMatrix"):
        ET.SubElement(
            rendering, _hc(name), {"e1": "1", "e2": "0", "e3": "0", "e4": "0", "e5": "1", "e6": "0"}
        )
    ET.SubElement(
        rect,
        _hp("lineShape"),
        {
            "color": "#000000",
            "width": "33",
            "style": "SOLID",
            "endCap": "FLAT",
            "headStyle": "NORMAL",
            "tailStyle": "NORMAL",
            "headfill": "0",
            "tailfill": "0",
            "headSz": "SMALL_SMALL",
            "tailSz": "SMALL_SMALL",
            "outlineStyle": "NORMAL",
            "alpha": "0",
        },
    )
    brush = ET.SubElement(rect, _hc("fillBrush"))
    ET.SubElement(
        brush, _hc("winBrush"), {"faceColor": "#FFFFFF", "hatchColor": "#000000", "alpha": "0"}
    )
    for index, point in enumerate(
        points[:4]
        or [
            {"x": 0, "y": 0},
            {"x": width, "y": 0},
            {"x": width, "y": height},
            {"x": 0, "y": height},
        ]
    ):
        ET.SubElement(
            rect,
            _hc(f"pt{index}"),
            {"x": str(int(point.get("x") or 0)), "y": str(int(point.get("y") or 0))},
        )
    ET.SubElement(
        rect,
        _hp("sz"),
        {
            "width": str(width),
            "widthRelTo": "ABSOLUTE",
            "height": str(height),
            "heightRelTo": "ABSOLUTE",
            "protect": "0",
        },
    )
    ET.SubElement(
        rect,
        _hp("pos"),
        _shape_pos_attrs(position),
    )
    ET.SubElement(rect, _hp("outMargin"), _shape_margin_attrs(position))
    return rect


def _create_rectangle_paragraph(
    paragraph_id: str, shape_id: int, geometry: dict[str, Any] | None = None
) -> ET.Element:
    paragraph = ET.Element(
        _hp("p"),
        {
            "id": str(paragraph_id),
            "paraPrIDRef": "0",
            "styleIDRef": "0",
            "pageBreak": "0",
            "columnBreak": "0",
            "merged": "0",
        },
    )
    run = ET.SubElement(paragraph, _hp("run"), {"charPrIDRef": "0"})
    run.append(_create_rectangle_shape(shape_id, geometry))
    return paragraph


def build_visual_section_updates(
    existing_entries: dict[str, bytes],
    bindata_report: dict[str, Any],
    analysis: dict[str, Any],
) -> tuple[dict[str, bytes], dict[str, Any]]:
    image_items = _image_bindata_items(bindata_report)
    section_entries = sorted(
        [
            name
            for name in existing_entries
            if name.replace("\\", "/").lower().startswith("contents/section")
            and name.lower().endswith(".xml")
        ],
        key=_section_sort_key,
    )
    picture_record_count = _body_record_tag_count(analysis, {85})
    vector_shape_count = _body_record_tag_count(analysis, {78, 79, 80, 81, 82, 83, 86})
    picture_rows = _shape_layout_pictures(analysis)
    rectangle_rows = _shape_layout_rectangles(analysis)
    if not image_items and picture_record_count > 0:
        return {}, {
            "status": "PICTURE_BINDATA_NOT_FOUND",
            "image_bindata_count": 0,
            "target_picture_count": picture_record_count,
            "visible_picture_count": 0,
            "picture_record_count": picture_record_count,
            "vector_shape_record_count": vector_shape_count,
            "visible_vector_shape_count": 0,
            "unmapped_vector_shape_record_count": vector_shape_count,
            "items": [],
            "vector_shapes": [],
        }
    if not image_items and vector_shape_count == 0:
        return {}, {
            "status": "NO_VISUAL_OBJECTS",
            "image_bindata_count": 0,
            "target_picture_count": 0,
            "visible_picture_count": 0,
            "picture_record_count": picture_record_count,
            "vector_shape_record_count": vector_shape_count,
            "visible_vector_shape_count": 0,
            "unmapped_vector_shape_record_count": vector_shape_count,
            "items": [],
            "vector_shapes": [],
        }
    if not section_entries:
        return {}, {
            "status": "SECTION_NOT_FOUND",
            "image_bindata_count": len(image_items),
            "target_picture_count": max(len(image_items), picture_record_count),
            "visible_picture_count": 0,
            "picture_record_count": picture_record_count,
            "vector_shape_record_count": vector_shape_count,
            "visible_vector_shape_count": 0,
            "unmapped_vector_shape_record_count": vector_shape_count,
            "items": image_items,
            "vector_shapes": [],
        }
    entry = section_entries[0]
    try:
        root = ET.fromstring(existing_entries[entry])
    except ET.ParseError as exc:
        return {}, {
            "status": "SECTION_XML_PARSE_FAILED",
            "error": str(exc),
            "entry": entry,
            "image_bindata_count": len(image_items),
            "target_picture_count": max(len(image_items), picture_record_count),
            "visible_picture_count": 0,
            "picture_record_count": picture_record_count,
            "vector_shape_record_count": vector_shape_count,
            "visible_vector_shape_count": 0,
            "unmapped_vector_shape_record_count": vector_shape_count,
            "items": image_items,
            "vector_shapes": [],
        }
    appended = []
    target_picture_count = max(len(image_items), picture_record_count)
    for index in range(target_picture_count):
        picture_geometry = (
            _picture_geometry(picture_rows[index])
            if index < len(picture_rows)
            else _picture_geometry(None)
        )
        item, bindata_id_mapped = _image_item_for_picture(image_items, picture_geometry, index)
        image_entry = str(item["entry"])
        paragraph = create_picture_paragraph(
            image_entry,
            _next_paragraph_id(root),
            {"paraPrIDRef": "0", "styleIDRef": "0", "charPrIDRef": "0"},
            _manifest_id(image_entry),
            width=int(picture_geometry.get("width") or 12000),
            height=int(picture_geometry.get("height") or 9000),
            position=picture_geometry.get("position")
            if isinstance(picture_geometry.get("position"), dict)
            else None,
        )
        root.append(paragraph)
        appended.append({
            "entry": image_entry,
            "manifest_id": _manifest_id(image_entry),
            "section_entry": entry,
            "paragraph_id": paragraph.attrib.get("id"),
            "source_index": index,
            "size": item.get("size"),
            "sha256": item.get("sha256"),
            "media_type": item.get("media_type"),
            "reused_bindata": index >= len(image_items),
            "binary_data_id": picture_geometry.get("binary_data_id"),
            "bindata_id_mapped": bindata_id_mapped,
            "geometry_mapped": picture_geometry.get("geometry_mapped"),
            "width": picture_geometry.get("width"),
            "height": picture_geometry.get("height"),
            "source_record_index": picture_geometry.get("source_record_index"),
            "component_record_index": picture_geometry.get("component_record_index"),
            "control_record_index": picture_geometry.get("control_record_index"),
            "position_mapped": picture_geometry.get("position_mapped"),
            "layout_policy_mapped": picture_geometry.get("layout_policy_mapped"),
            "position": picture_geometry.get("position"),
        })
    visible_vector_shapes = []
    for index in range(vector_shape_count):
        shape_id = 900000000 + index
        geometry = (
            _rectangle_geometry(rectangle_rows[index])
            if index < len(rectangle_rows)
            else _rectangle_geometry(None)
        )
        paragraph = _create_rectangle_paragraph(_next_paragraph_id(root), shape_id, geometry)
        root.append(paragraph)
        visible_vector_shapes.append({
            "shape_id": shape_id,
            "section_entry": entry,
            "paragraph_id": paragraph.attrib.get("id"),
            "shape_type": "rect",
            "geometry_mapped": index < len(rectangle_rows),
            "width": geometry.get("width"),
            "height": geometry.get("height"),
            "source_record_index": geometry.get("source_record_index"),
            "component_record_index": geometry.get("component_record_index"),
            "control_record_index": geometry.get("control_record_index"),
            "position_mapped": geometry.get("position_mapped"),
            "layout_policy_mapped": geometry.get("layout_policy_mapped"),
            "position": geometry.get("position"),
        })
    status = (
        "PASS"
        if len(appended) >= target_picture_count
        and len(visible_vector_shapes) == vector_shape_count
        else "PARTIAL_VECTOR_SHAPES_UNMAPPED"
    )
    return {entry: _xml_string(root).encode("utf-8")}, {
        "status": status,
        "section_entry": entry,
        "image_bindata_count": len(image_items),
        "target_picture_count": target_picture_count,
        "visible_picture_count": len(appended),
        "picture_record_count": picture_record_count,
        "picture_geometry_mapped_count": sum(1 for row in appended if row.get("geometry_mapped")),
        "picture_bindata_id_mapped_count": sum(
            1 for row in appended if row.get("bindata_id_mapped")
        ),
        "picture_position_mapped_count": sum(1 for row in appended if row.get("position_mapped")),
        "picture_layout_policy_mapped_count": sum(
            1 for row in appended if row.get("layout_policy_mapped")
        ),
        "vector_shape_record_count": vector_shape_count,
        "visible_vector_shape_count": len(visible_vector_shapes),
        "geometry_mapped_vector_shape_count": sum(
            1 for row in visible_vector_shapes if row.get("geometry_mapped")
        ),
        "position_mapped_vector_shape_count": sum(
            1 for row in visible_vector_shapes if row.get("position_mapped")
        ),
        "layout_policy_mapped_vector_shape_count": sum(
            1 for row in visible_vector_shapes if row.get("layout_policy_mapped")
        ),
        "unmapped_vector_shape_record_count": max(
            0, vector_shape_count - len(visible_vector_shapes)
        ),
        "items": appended,
        "vector_shapes": visible_vector_shapes,
        "full_fidelity": status == "PASS",
        "warning": "Vector shape coordinates are mapped for decoded rectangles; non-rectangle vector styles are still represented conservatively.",
    }


def build_equation_mapping(analysis: dict[str, Any]) -> dict[str, Any]:
    layout = (
        analysis.get("equation_layout") if isinstance(analysis.get("equation_layout"), dict) else {}
    )
    sections = layout.get("sections") if isinstance(layout.get("sections"), list) else []
    equations = []
    for section in sections:
        if not isinstance(section, dict):
            continue
        for row in section.get("equations") or []:
            if not isinstance(row, dict):
                continue
            equations.append({
                "section_index": section.get("section_index"),
                "section_name": section.get("name"),
                "equation_index": row.get("equation_index"),
                "record_index": row.get("record_index"),
                "level": row.get("level"),
                "formula": row.get("formula"),
                "formula_length": row.get("formula_length"),
                "version": row.get("version"),
                "application": row.get("application"),
                "payload_size": row.get("payload_size"),
                "payload_prefix_hex": row.get("payload_prefix_hex"),
                "options_hex": row.get("options_hex"),
                "decode_error": row.get("decode_error"),
            })
    missing_formula = [row for row in equations if not str(row.get("formula") or "").strip()]
    return {
        "status": "PASS"
        if equations and not missing_formula
        else ("NO_EQUATIONS" if not equations else "PARTIAL_EQUATION_MAPPING"),
        "equation_count": len(equations),
        "missing_formula_count": len(missing_formula),
        "equations": equations,
        "full_fidelity": bool(equations and not missing_formula),
        "warning": "EQEDIT formula text and payload metadata are preserved in Preview/EquationMapping.json; native editable equation object reconstruction remains conservative.",
    }


def _rewrite_zip_entries(path: Path, updates: dict[str, bytes]) -> list[str]:
    temp_path = path.with_name(f"{path.stem}.rewrite.tmp{path.suffix}")
    written = []
    with (
        zipfile.ZipFile(path, "r") as src,
        zipfile.ZipFile(temp_path, "w", compression=zipfile.ZIP_DEFLATED) as dst,
    ):
        updated_names = {name.replace("\\", "/") for name in updates}
        for info in src.infolist():
            normalized = info.filename.replace("\\", "/")
            if normalized in updated_names:
                continue
            dst.writestr(info, src.read(info.filename))
        for name, payload in updates.items():
            compress_type = zipfile.ZIP_STORED if name == "mimetype" else zipfile.ZIP_DEFLATED
            dst.writestr(name, payload, compress_type=compress_type)
            written.append(name)
    for attempt in range(5):
        try:
            temp_path.replace(path)
            return written
        except PermissionError:
            if attempt == 4:
                break
            time.sleep(0.2 * (attempt + 1))
    path.write_bytes(temp_path.read_bytes())
    try:
        temp_path.unlink(missing_ok=True)
    except PermissionError:
        pass
    return written


def inject_analysis_entries(output_path: Path, analysis: dict[str, Any]) -> dict[str, Any]:
    path = Path(output_path)
    if not path.exists():
        return {"status": "SKIP", "reason": "OUTPUT_NOT_FOUND", "output": str(path)}
    decoded_docinfo = (
        analysis.get("decoded_docinfo") if isinstance(analysis.get("decoded_docinfo"), dict) else {}
    )
    body_layout = (
        analysis.get("body_layout") if isinstance(analysis.get("body_layout"), dict) else {}
    )
    page_layout = (
        analysis.get("page_layout") if isinstance(analysis.get("page_layout"), dict) else {}
    )
    table_layout = (
        analysis.get("table_layout") if isinstance(analysis.get("table_layout"), dict) else {}
    )
    coverage = analysis.get("coverage") if isinstance(analysis.get("coverage"), dict) else {}
    ole_metadata = (
        analysis.get("ole_metadata") if isinstance(analysis.get("ole_metadata"), dict) else {}
    )
    record_audit = (
        analysis.get("record_audit") if isinstance(analysis.get("record_audit"), dict) else {}
    )
    source_manifest = (
        analysis.get("source_manifest") if isinstance(analysis.get("source_manifest"), dict) else {}
    )
    source_input = Path(str(analysis.get("input"))) if analysis.get("input") else None
    fontface_report = build_fontface_mapping(decoded_docinfo)
    list_style_report = build_list_style_mapping(decoded_docinfo)
    equation_report = build_equation_mapping(analysis)
    original_integrity: dict[str, Any] = {"status": "SKIPPED", "reason": "PACKAGE_NOT_READ"}
    bindata_updates, bindata_report = _copy_bindata_from_source(source_input, decoded_docinfo)
    updates: dict[str, bytes] = {
        "Preview/DecodedDocInfo.json": json.dumps(
            decoded_docinfo, ensure_ascii=False, indent=2
        ).encode("utf-8"),
        "Preview/DocumentMetadata.json": json.dumps(
            ole_metadata, ensure_ascii=False, indent=2
        ).encode("utf-8"),
        "Preview/FullFidelityCoverage.json": json.dumps(
            coverage, ensure_ascii=False, indent=2
        ).encode("utf-8"),
        "Preview/RecordAudit.json": json.dumps(record_audit, ensure_ascii=False, indent=2).encode(
            "utf-8"
        ),
        "Preview/SourceManifest.json": json.dumps(
            source_manifest, ensure_ascii=False, indent=2
        ).encode("utf-8"),
        "Preview/FontFaceMapping.json": json.dumps(
            fontface_report, ensure_ascii=False, indent=2
        ).encode("utf-8"),
        "Preview/ListStyleMapping.json": json.dumps(
            list_style_report, ensure_ascii=False, indent=2
        ).encode("utf-8"),
        "Preview/EquationMapping.json": json.dumps(
            equation_report, ensure_ascii=False, indent=2
        ).encode("utf-8"),
        "Preview/BinDataPreservation.json": json.dumps(
            bindata_report, ensure_ascii=False, indent=2
        ).encode("utf-8"),
        "Contents/header.xml": build_decoded_header_xml(decoded_docinfo).encode("utf-8"),
    }
    updates.update(bindata_updates)
    body_style_report: dict[str, Any] = {"status": "SKIPPED", "reason": "BODY_LAYOUT_NOT_AVAILABLE"}
    page_layout_report: dict[str, Any] = {
        "status": "SKIPPED",
        "reason": "PAGE_LAYOUT_NOT_AVAILABLE",
    }
    table_layout_report: dict[str, Any] = {
        "status": "SKIPPED",
        "reason": "TABLE_LAYOUT_NOT_AVAILABLE",
    }
    visual_object_report: dict[str, Any] = {
        "status": "SKIPPED",
        "reason": "VISUAL_MAPPING_NOT_AVAILABLE",
    }
    with zipfile.ZipFile(path, "r") as zf:
        existing = {name.replace("\\", "/"): name for name in zf.namelist()}
        if "Contents/content.hpf" in existing:
            content_text = zf.read(existing["Contents/content.hpf"]).decode(
                "utf-8", errors="replace"
            )
            known_entries = list(existing) + list(updates)
            updates["Contents/content.hpf"] = _content_hpf_with_entries(
                content_text, known_entries
            ).encode("utf-8")
        entries = {name: zf.read(name) for name in zf.namelist()}
        original_integrity = build_original_integrity(path, entries, source_manifest)
        updates["Preview/OriginalIntegrity.json"] = json.dumps(
            original_integrity, ensure_ascii=False, indent=2
        ).encode("utf-8")
        body_updates, body_style_report = build_body_style_section_updates(
            entries, body_layout, decoded_docinfo
        )
        updates.update(body_updates)
        effective_entries = dict(entries)
        effective_entries.update(body_updates)
        page_updates, page_layout_report = build_page_layout_section_updates(
            effective_entries, page_layout, decoded_docinfo
        )
        updates.update(page_updates)
        effective_entries.update(page_updates)
        table_updates, table_layout_report = build_table_layout_section_updates(
            effective_entries, table_layout, decoded_docinfo
        )
        updates.update(table_updates)
        effective_entries.update(table_updates)
        visual_updates, visual_object_report = build_visual_section_updates(
            effective_entries, bindata_report, analysis
        )
        updates.update(visual_updates)
        final_entries = dict(entries)
        final_entries.update(updates)
        if "Contents/content.hpf" in final_entries:
            content_text = final_entries["Contents/content.hpf"].decode("utf-8", errors="replace")
            updates["Contents/content.hpf"] = _content_hpf_with_entries(
                content_text, list(final_entries)
            ).encode("utf-8")
        updates["Preview/BodyStyleMapping.json"] = json.dumps(
            body_style_report, ensure_ascii=False, indent=2
        ).encode("utf-8")
        updates["Preview/PageLayoutMapping.json"] = json.dumps(
            page_layout_report, ensure_ascii=False, indent=2
        ).encode("utf-8")
        updates["Preview/TableLayoutMapping.json"] = json.dumps(
            table_layout_report, ensure_ascii=False, indent=2
        ).encode("utf-8")
        updates["Preview/VisualObjectMapping.json"] = json.dumps(
            visual_object_report, ensure_ascii=False, indent=2
        ).encode("utf-8")
    written = _rewrite_zip_entries(path, updates)
    return {
        "status": "PASS",
        "output": str(path),
        "entries": written,
        "decoded_header": decoded_header_summary(decoded_docinfo),
        "document_metadata": {
            "status": ole_metadata.get("status", "SKIPPED"),
            "present_field_count": ole_metadata.get("present_field_count", 0),
            "present_fields": ole_metadata.get("present_fields", []),
        },
        "record_audit": {
            "status": record_audit.get("status", "SKIPPED"),
            "record_count": record_audit.get("record_count", 0),
            "unknown_tag_count": record_audit.get("unknown_tag_count", 0),
            "risk_tag_count": record_audit.get("risk_tag_count", 0),
            "decoded_error_count": record_audit.get("decoded_error_count", 0),
        },
        "bindata_preservation": bindata_report,
        "source_manifest": {
            "status": source_manifest.get("status", "SKIPPED"),
            "stream_count": source_manifest.get("stream_count", 0),
            "hashed_stream_count": source_manifest.get("hashed_stream_count", 0),
            "storage_count": source_manifest.get("storage_count", 0),
            "unreadable_stream_count": source_manifest.get("unreadable_stream_count", 0),
        },
        "fontface_mapping": fontface_report,
        "original_integrity": {
            "status": original_integrity.get("status", "SKIPPED"),
            "entry_name": original_integrity.get("entry_name", "Original/original.hwp"),
            "byte_exact_original_embedded": original_integrity.get(
                "byte_exact_original_embedded", False
            ),
            "sha256_match": original_integrity.get("sha256_match", False),
            "size_match": original_integrity.get("size_match", False),
            "file_name_changed": original_integrity.get("file_name_changed", False),
        },
        "list_style_mapping": list_style_report,
        "equation_mapping": equation_report,
        "body_style_mapping": body_style_report,
        "page_layout_mapping": page_layout_report,
        "table_layout_mapping": table_layout_report,
        "visual_object_mapping": visual_object_report,
    }
