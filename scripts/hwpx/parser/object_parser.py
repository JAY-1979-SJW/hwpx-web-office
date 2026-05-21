"""HWPX Parser V2 — object/binData parser (read-only).

section XML에서 그림/도형/컨테이너 객체를 ObjectInfo 목록으로 추출하고
header.xml의 binItem(BinData 참조)을 BinDataInfo 목록으로 추출한다.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

from .parser_contract import ObjectInfo, BinDataInfo

NS_HH = "http://www.hancom.co.kr/hwpml/2011/head"
NS_HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"

_OBJECT_TAGS = {
    "pic": "picture",
    "rect": "rect",
    "line": "line",
    "ellipse": "ellipse",
    "container": "container",
    "arc": "arc",
    "curve": "curve",
    "polygon": "polygon",
}


def _int_or_none(v: str) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _extract_geom(el: ET.Element) -> tuple[int | None, int | None, int | None, int | None]:
    width = height = pos_x = pos_y = None
    sz = el.find(f"{{{NS_HP}}}curSz")
    if sz is None:
        sz = el.find(f"{{{NS_HP}}}orgSz")
    if sz is not None:
        width = _int_or_none(sz.get("width", ""))
        height = _int_or_none(sz.get("height", ""))
    off = el.find(f"{{{NS_HP}}}offset")
    if off is not None:
        pos_x = _int_or_none(off.get("x", ""))
        pos_y = _int_or_none(off.get("y", ""))
    return width, height, pos_x, pos_y


def _find_bin_data_ref(el: ET.Element) -> str | None:
    """picture/container 내부에서 binData ref(img binaryItemIDRef 등) 탐색."""
    for child in el.iter():
        bid = child.get("binaryItemIDRef", "") if hasattr(child, "get") else ""
        if bid:
            return bid
    return None


def parse_objects_from_section(section_xml: bytes, section_index: int,
                                 source_path: str = "") -> list[ObjectInfo]:
    """section XML에서 객체(도형/그림/컨테이너) 목록을 ObjectInfo로 반환."""
    try:
        root = ET.fromstring(section_xml)
    except ET.ParseError:
        return []

    objects: list[ObjectInfo] = []
    counter = 0
    for el in root.iter():
        tag = el.tag.split("}")[-1]
        obj_type = _OBJECT_TAGS.get(tag)
        if obj_type is None:
            continue
        width, height, pos_x, pos_y = _extract_geom(el)
        obj_id = el.get("id", "") or f"obj_s{section_index}_{counter:04d}"
        bin_ref = _find_bin_data_ref(el)
        objects.append(ObjectInfo(
            objectId=obj_id,
            objectType=obj_type,
            sectionIndex=section_index,
            sourcePath=source_path,
            binDataRef=bin_ref,
            width=width,
            height=height,
            posX=pos_x,
            posY=pos_y,
            rawTag=tag,
        ))
        counter += 1
    return objects


def parse_bin_data_from_header(header_xml: bytes) -> list[BinDataInfo]:
    """header.xml의 binData/binItem 목록을 BinDataInfo로 반환."""
    try:
        root = ET.fromstring(header_xml)
    except ET.ParseError:
        return []
    result: list[BinDataInfo] = []
    for el in root.iter():
        tag = el.tag.split("}")[-1]
        if tag in ("binItem", "binData"):
            bin_id = el.get("id", "") or el.get("itemID", "")
            href = el.get("href", "") or el.get("path", "")
            fmt = el.get("format", "") or el.get("type", "")
            if bin_id or href:
                result.append(BinDataInfo(
                    binId=bin_id,
                    href=href,
                    format=fmt,
                    sourceTag=tag,
                ))
    return result
