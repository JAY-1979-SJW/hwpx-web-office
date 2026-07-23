"""charpr_append — header.xml charProperties 에 신규 charPr append-only 추가.

CLAUDE.md §4.1 "서식 편집 (조건부 허용)" 조건 하에서만 쓴다:
  - 폰트 **크기** 변경 목적만 (fontFace/폰트 종류는 그대로)
  - append-only — 기존 charPr 의 수정·삭제·ID 재사용 금지
  - 신규 ID 는 기존 최대값+1부터 순차 부여

이 모듈은 header.xml 바이트만 다룬다. section*.xml 의 run charPrIDRef
교체(기존 charPr 로의 스왑)는 이미 구현된 APPLY_FORMAT 경로
(paragraph_writer_adapter.py, hwpx_paragraph_ops.apply_charpr_to_range_existing)
를 그대로 쓴다 — 이 모듈이 새 id 를 header.xml 에 먼저 심어두면, 그
경로가 "이미 header 에 있는 id" 로 인식해 정상 진행된다.
"""
from __future__ import annotations

import copy
import xml.etree.ElementTree as ET
from typing import Any

_HH_NS = "http://www.hancom.co.kr/hwpml/2011/head"
ET.register_namespace("hh", _HH_NS)


def _ln(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def append_char_pr_for_size(
    header_bytes: bytes,
    source_char_pr_id: str,
    new_size_pt: float,
) -> tuple[bytes, str]:
    """header_bytes 에서 source_char_pr_id 를 복제해 height 만
    new_size_pt(1/100pt 단위로 변환)로 바꾼 신규 charPr 를 append.

    Returns (new_header_bytes, new_char_pr_id).
    기존 charPr element 는 어떤 방식으로도 수정하지 않는다(append-only).

    Raises ValueError: source_char_pr_id 가 header.xml 에 없거나
    charProperties 컨테이너를 못 찾은 경우.
    """
    root = ET.fromstring(header_bytes)

    char_pr_elems: list[ET.Element] = []
    char_pr_container: ET.Element | None = None
    for parent in root.iter():
        for child in list(parent):
            if _ln(child.tag) == "charPr":
                char_pr_elems.append(child)
                if char_pr_container is None:
                    char_pr_container = parent

    if char_pr_container is None:
        raise ValueError("header.xml 에 charProperties 컨테이너가 없습니다")

    source_elem = next(
        (e for e in char_pr_elems if e.get("id") == str(source_char_pr_id)),
        None)
    if source_elem is None:
        raise ValueError(
            f"source_char_pr_id={source_char_pr_id!r} 가 header.xml 에 없습니다")

    # 기존 최대 id — append-only 순차 부여(재사용 금지)
    existing_ids = [int(e.get("id", "0")) for e in char_pr_elems
                    if (e.get("id") or "").isdigit()]
    new_id = str(max(existing_ids, default=0) + 1)

    new_elem = copy.deepcopy(source_elem)
    new_elem.set("id", new_id)
    # height 는 HWPUNIT 1/100pt 단위(예: 18.0pt → "1800")
    new_elem.set("height", str(int(round(new_size_pt * 100))))

    char_pr_container.append(new_elem)

    new_bytes = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return new_bytes, new_id


def find_matching_char_pr(
    char_pr_defs: dict[str, dict[str, Any]],
    source_char_pr_id: str,
    target_size_pt: float,
) -> str | None:
    """source_char_pr_id 와 폰트(fontFace/이름)는 같고 크기만
    target_size_pt 인 기존 charPr id 를 찾는다. 없으면 None(→ 신규
    append 필요). char_pr_defs 는 style_parser.parse_char_pr_defs 형식."""
    source = char_pr_defs.get(str(source_char_pr_id))
    if source is None:
        return None
    for cid, d in char_pr_defs.items():
        if cid == str(source_char_pr_id):
            continue
        if d.get("fontFace") != source.get("fontFace"):
            continue
        if d.get("fontName") != source.get("fontName"):
            continue
        if d.get("bold") != source.get("bold"):
            continue
        if d.get("italic") != source.get("italic"):
            continue
        if d.get("fontSizePt") == target_size_pt:
            return cid
    return None
