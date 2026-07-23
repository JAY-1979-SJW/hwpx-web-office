"""charpr_append — header.xml charProperties 에 신규 charPr append-only 추가.

CLAUDE.md §4.1 "서식 편집 (조건부 허용)" 조건 하에서만 쓴다:
  - 글꼴 종류·크기·색상·굵게/기울임/밑줄 변경 목적
  - append-only — 기존 charPr 의 수정·삭제·ID 재사용 금지
  - 신규 ID 는 기존 최대값+1부터 순차 부여
  - 글꼴은 문서 안에 이미 존재하는 폰트 리소스(fontFace id)만 참조 —
    fontfaces 테이블에 신규 폰트 등록은 하지 않는다

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

# overrides 에서 허용하는 키(그 외 키는 무시 — 알 수 없는 속성을 조용히
# 반영하다 예상 못 한 변형이 생기는 것 방지).
_SUPPORTED_OVERRIDE_KEYS = {
    "fontSizePt", "textColor", "bold", "italic", "underline", "fontFaceId",
}
_FONT_REF_SLOTS = ("hangul", "latin", "hanja", "japanese", "other",
                   "symbol", "user")


def _ln(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _find_char_pr_container(root: ET.Element) -> tuple[
        list[ET.Element], ET.Element | None]:
    char_pr_elems: list[ET.Element] = []
    container: ET.Element | None = None
    for parent in root.iter():
        for child in list(parent):
            if _ln(child.tag) == "charPr":
                char_pr_elems.append(child)
                if container is None:
                    container = parent
    return char_pr_elems, container


def _set_bool_child(elem: ET.Element, tag: str, present: bool,
                    default_attrib: dict[str, str] | None = None) -> None:
    """tag 자식 요소의 존재 여부로 on/off 를 표현하는 속성(bold/italic)
    을 append-only 복제본 위에서만 조정한다(원본 charPr 은 절대 안 건드림
    — 이 함수는 항상 copy.deepcopy 된 new_elem 에만 호출된다)."""
    existing = elem.find(f"{{{_HH_NS}}}{tag}")
    if present and existing is None:
        new_child = ET.SubElement(elem, f"{{{_HH_NS}}}{tag}")
        if default_attrib:
            for k, v in default_attrib.items():
                new_child.set(k, v)
    elif not present and existing is not None:
        elem.remove(existing)


def append_char_pr_with_overrides(
    header_bytes: bytes,
    source_char_pr_id: str,
    overrides: dict[str, Any],
) -> tuple[bytes, str]:
    """header_bytes 에서 source_char_pr_id 를 복제해 overrides 에 담긴
    속성만 바꾼 신규 charPr 를 append. 그 외 속성은 원본 그대로 상속.

    overrides 지원 키:
      fontSizePt(float), textColor(str, 예: "#FF0000"),
      bold/italic/underline(bool), fontFaceId(str — 문서에 이미 있는
      fontfaces id. 모든 언어 슬롯에 동일하게 적용하는 단순화된 방식).

    Returns (new_header_bytes, new_char_pr_id).
    기존 charPr element 는 어떤 방식으로도 수정하지 않는다(append-only).

    Raises ValueError: source_char_pr_id 가 없거나 컨테이너를 못 찾거나
    지원하지 않는 override 키가 있는 경우.
    """
    unknown = set(overrides) - _SUPPORTED_OVERRIDE_KEYS
    if unknown:
        raise ValueError(f"지원하지 않는 override 키: {sorted(unknown)}")

    root = ET.fromstring(header_bytes)
    char_pr_elems, char_pr_container = _find_char_pr_container(root)

    if char_pr_container is None:
        raise ValueError("header.xml 에 charProperties 컨테이너가 없습니다")

    source_elem = next(
        (e for e in char_pr_elems if e.get("id") == str(source_char_pr_id)),
        None)
    if source_elem is None:
        raise ValueError(
            f"source_char_pr_id={source_char_pr_id!r} 가 header.xml 에 없습니다")

    existing_ids = [int(e.get("id", "0")) for e in char_pr_elems
                    if (e.get("id") or "").isdigit()]
    new_id = str(max(existing_ids, default=0) + 1)

    new_elem = copy.deepcopy(source_elem)
    new_elem.set("id", new_id)

    if "fontSizePt" in overrides:
        # height 는 HWPUNIT 1/100pt 단위(예: 18.0pt → "1800")
        new_elem.set("height", str(int(round(float(overrides["fontSizePt"]) * 100))))
    if "textColor" in overrides:
        new_elem.set("textColor", str(overrides["textColor"]))
    if "bold" in overrides:
        _set_bool_child(new_elem, "bold", bool(overrides["bold"]))
    if "italic" in overrides:
        _set_bool_child(new_elem, "italic", bool(overrides["italic"]))
    if "underline" in overrides:
        _set_bool_child(new_elem, "underline", bool(overrides["underline"]),
                        default_attrib={"type": "SOLID", "shape": "SOLID",
                                        "color": "#000000"})
    if "fontFaceId" in overrides:
        face_id = str(overrides["fontFaceId"])
        fr = new_elem.find(f"{{{_HH_NS}}}fontRef")
        if fr is None:
            fr = ET.SubElement(new_elem, f"{{{_HH_NS}}}fontRef")
        for slot in _FONT_REF_SLOTS:
            fr.set(slot, face_id)

    char_pr_container.append(new_elem)
    # itemCnt 보정 — <hh:charProperties itemCnt="N"> 은 charPr 개수를
    # 선언한다. 실측(2026-07-24, 실제 Hancom Office COM): 요소만 append
    # 하고 itemCnt 를 안 늘리면 textColor 가 검정으로 렌더링된다(bold/
    # height 는 itemCnt 와 무관하게 정상 반영되지만, 색상은 이 카운트
    # 기준 조회 테이블을 쓰는 것으로 보인다). 반드시 +1 해야 한다.
    cnt_raw = char_pr_container.get("itemCnt")
    if cnt_raw is not None and cnt_raw.isdigit():
        char_pr_container.set("itemCnt", str(int(cnt_raw) + 1))

    new_bytes = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return new_bytes, new_id


def append_char_pr_for_size(
    header_bytes: bytes,
    source_char_pr_id: str,
    new_size_pt: float,
) -> tuple[bytes, str]:
    """하위호환 — 크기만 바꾸는 좁은 진입점. 신규 코드는
    append_char_pr_with_overrides 를 직접 쓸 것."""
    return append_char_pr_with_overrides(
        header_bytes, source_char_pr_id, {"fontSizePt": new_size_pt})


def find_matching_char_pr(
    char_pr_defs: dict[str, dict[str, Any]],
    source_char_pr_id: str,
    overrides: dict[str, Any] | float,
) -> str | None:
    """source_char_pr_id 에서 overrides 에 담긴 속성만 다르고 나머지는
    전부 같은 기존 charPr id 를 찾는다. 없으면 None(→ 신규 append 필요).

    overrides 는 dict(예: {"fontSizePt": 18.0, "bold": True}) 또는
    (하위호환) 숫자 하나 = target_size_pt.
    char_pr_defs 는 style_parser.parse_char_pr_defs 형식."""
    if not isinstance(overrides, dict):
        overrides = {"fontSizePt": overrides}
    unknown = set(overrides) - _SUPPORTED_OVERRIDE_KEYS
    if unknown:
        raise ValueError(f"지원하지 않는 override 키: {sorted(unknown)}")

    source = char_pr_defs.get(str(source_char_pr_id))
    if source is None:
        return None

    def _wanted(d: dict[str, Any], key: str) -> Any:
        if key == "fontSizePt":
            return overrides.get("fontSizePt", source.get("fontSizePt"))
        if key == "textColor":
            return overrides.get("textColor", source.get("textColor"))
        if key == "bold":
            return overrides.get("bold", source.get("bold"))
        if key == "italic":
            return overrides.get("italic", source.get("italic"))
        if key == "underline":
            return overrides.get("underline", source.get("underline"))
        return None

    for cid, d in char_pr_defs.items():
        if cid == str(source_char_pr_id):
            continue
        if "fontFaceId" in overrides:
            # fontRef 전체(모든 언어 슬롯)가 요청한 face id 로 통일돼
            # 있어야 매칭(append 함수가 그렇게 만들기 때문).
            fr = d.get("fontRef") or {}
            if not fr or any(
                    fr.get(slot) != str(overrides["fontFaceId"])
                    for slot in _FONT_REF_SLOTS if slot in fr):
                continue
        elif d.get("fontRef") != source.get("fontRef"):
            continue
        if d.get("fontSizePt") != _wanted(d, "fontSizePt"):
            continue
        if d.get("textColor") != _wanted(d, "textColor"):
            continue
        if d.get("bold") != _wanted(d, "bold"):
            continue
        if d.get("italic") != _wanted(d, "italic"):
            continue
        if d.get("underline") != _wanted(d, "underline"):
            continue
        return cid
    return None
