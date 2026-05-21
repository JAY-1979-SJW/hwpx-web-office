"""HWPX Parser V2 — style parser (read-only).

header.xml에서 charPr / paraPr / borderFill 정의와 참조 정보를 추출한다.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from .parser_contract import StyleInfo
from .errors import WarnCode

NS_HH = "http://www.hancom.co.kr/hwpml/2011/head"
NS_HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"

_CHARPR_ID_RE = re.compile(r'charPrIDRef="(\d+)"')
_PARAPR_ID_RE = re.compile(r'paraPrIDRef="(\d+)"')
_BORDERFILL_ID_RE = re.compile(r'borderFillIDRef="(\d+)"')


def parse_font_face_table(header_xml: bytes) -> dict[str, dict[str, str]]:
    """header.xml의 fontface 테이블을 {lang: {id: faceName}} 형태로 반환.

    예: {"HANGUL": {"0": "굴림체", "1": "돋움", ...}, "LATIN": {...}, ...}
    """
    try:
        root = ET.fromstring(header_xml)
    except ET.ParseError:
        return {}
    result: dict[str, dict[str, str]] = {}
    for ff in root.iter(f"{{{NS_HH}}}fontface"):
        lang = (ff.get("lang", "") or "").upper()
        if not lang:
            continue
        bucket: dict[str, str] = result.setdefault(lang, {})
        for font in ff.findall(f"{{{NS_HH}}}font"):
            fid = font.get("id", "")
            face = font.get("face", "") or font.get("name", "")
            if fid and face:
                bucket[fid] = face
    return result


def _resolve_font_name(fr_attribs: dict, font_table: dict[str, dict[str, str]]) -> str | None:
    """fontRef attr 딕셔너리에서 hangul → latin 순서로 실제 폰트명 lookup."""
    if not font_table:
        return None
    for lang_key, attr in (("HANGUL", "hangul"), ("LATIN", "latin")):
        fid = fr_attribs.get(attr, "")
        if fid and fid in font_table.get(lang_key, {}):
            return font_table[lang_key][fid]
    # 모든 lang 순차 fallback
    for lang_key, attr in (("HANJA", "hanja"), ("JAPANESE", "japanese"),
                            ("OTHER", "other"), ("SYMBOL", "symbol"), ("USER", "user")):
        fid = fr_attribs.get(attr, "")
        if fid and fid in font_table.get(lang_key, {}):
            return font_table[lang_key][fid]
    return None


def parse_char_pr_defs(header_xml: bytes,
                        font_table: dict[str, dict[str, str]] | None = None) -> dict[str, dict]:
    """header.xml에서 charPr 정의를 {id: {...}} 형태로 반환.

    font_table이 주어지면 fontFace ID를 실제 폰트명(fontName)으로 역참조.
    """
    try:
        root = ET.fromstring(header_xml)
    except ET.ParseError:
        return {}
    if font_table is None:
        font_table = parse_font_face_table(header_xml)
    result: dict[str, dict] = {}
    for el in root.iter(f"{{{NS_HH}}}charPr"):
        cid = el.get("id", "")
        if not cid:
            continue
        height_raw = el.get("height", "")
        height = int(height_raw) if height_raw.isdigit() else None
        font_face = el.get("fontRef", el.get("face", el.get("fontName", "")))
        font_name: str | None = None
        if not font_face:
            fr = el.find(f"{{{NS_HH}}}fontRef")
            if fr is not None:
                font_face = fr.get("face", fr.get("hangul", ""))
                font_name = _resolve_font_name(fr.attrib, font_table)
        b_el = el.find(f"{{{NS_HH}}}bold")
        i_el = el.find(f"{{{NS_HH}}}italic")
        u_el = el.find(f"{{{NS_HH}}}underline")
        u_type = u_el.get("type", "") if u_el is not None else ""
        underline_on = u_el is not None and u_type.upper() not in ("", "NONE")
        text_color_raw = el.get("textColor", "")
        result[cid] = {
            "height": height,
            "fontSizePt": round(height / 100, 1) if height is not None else None,
            "textColor": text_color_raw,
            "fontFace": font_face or None,
            "fontName": font_name,
            "bold": b_el is not None,
            "italic": i_el is not None,
            "underline": underline_on,
        }
    return result


def parse_para_pr_defs(header_xml: bytes) -> dict[str, dict]:
    """header.xml에서 paraPr 정의를 {id: {...}} 형태로 반환."""
    try:
        root = ET.fromstring(header_xml)
    except ET.ParseError:
        return {}
    result: dict[str, dict] = {}
    for el in root.iter(f"{{{NS_HH}}}paraPr"):
        pid = el.get("id", "")
        if not pid:
            continue
        def _int(v: str) -> int:
            try:
                return int(v)
            except (ValueError, TypeError):
                return 0
        align_val = el.get("align", "")
        if not align_val:
            ach = el.find(f"{{{NS_HH}}}align")
            if ach is not None:
                align_val = ach.get("horizontal", "") or ach.get("align", "")
        result[pid] = {
            "align": align_val,
            "marginLeft": _int(el.get("marginLeft", "0")),
            "marginRight": _int(el.get("marginRight", "0")),
            "marginTop": _int(el.get("marginTop", "0")),
            "marginBottom": _int(el.get("marginBottom", "0")),
        }
    return result


def extract_fill_color(element: ET.Element) -> str | None:
    """borderFill 요소에서 배경 채우기 색상을 추출."""
    fb = element.find(f"{{{NS_HH}}}fillBrush")
    if fb is None:
        return None
    for attr in ("faceColor", "color", "startColor", "fillColor"):
        val = fb.get(attr, "")
        if val and val.lower() not in ("none", ""):
            return val
    # fillBrush/winBrush 자식 검색 (set_table_visual_cell_solid_fill 경로)
    for child in fb:
        for attr in ("faceColor", "color", "startColor"):
            val = child.get(attr, "")
            if val and val.lower() not in ("none", ""):
                return val
    return None


def _border_summary(borders: dict[str, dict]) -> str:
    """border 정의 딕셔너리에서 요약 문자열을 반환."""
    sides = ("leftBorder", "rightBorder", "topBorder", "bottomBorder")
    types = [borders.get(s, {}).get("type", "NONE") for s in sides]
    none_count = sum(1 for t in types if t in ("NONE", "none", ""))
    if none_count == 4:
        return "no_border"
    if none_count == 0:
        return "full_box"
    return "partial"


def parse_border_fill_defs(header_xml: bytes) -> dict[str, dict]:
    """header.xml에서 borderFill 정의를 {id: {...}} 형태로 반환."""
    try:
        root = ET.fromstring(header_xml)
    except ET.ParseError:
        return {}
    result: dict[str, dict] = {}
    for el in root.iter(f"{{{NS_HH}}}borderFill"):
        bid = el.get("id", "")
        if not bid:
            continue
        fill_color = extract_fill_color(el)
        borders: dict[str, dict] = {}
        for side in ("leftBorder", "rightBorder", "topBorder", "bottomBorder"):
            b = el.find(f"{{{NS_HH}}}{side}")
            if b is not None:
                borders[side] = {
                    "type": b.get("type", "NONE"),
                    "color": b.get("color", ""),
                    "width": b.get("width", ""),
                }
        result[bid] = {
            "fillColor": fill_color,
            "borders": borders,
            "borderSummary": _border_summary(borders),
        }
    return result


def parse_style_summary(header_xml: bytes) -> StyleInfo:
    """header.xml에서 스타일 정의를 파싱해 StyleInfo로 반환."""
    try:
        root = ET.fromstring(header_xml)
    except ET.ParseError:
        return StyleInfo()

    char_pr_count = sum(1 for _ in root.iter(f"{{{NS_HH}}}charPr"))
    para_pr_count = sum(1 for _ in root.iter(f"{{{NS_HH}}}paraPr"))
    border_fill_count = sum(1 for _ in root.iter(f"{{{NS_HH}}}borderFill"))

    char_pr_defs = parse_char_pr_defs(header_xml)
    para_pr_defs = parse_para_pr_defs(header_xml)
    border_fill_defs = parse_border_fill_defs(header_xml)

    colors: list[str] = []
    for bf in border_fill_defs.values():
        fc = bf.get("fillColor")
        if fc and fc not in colors:
            colors.append(fc)
    for cp in char_pr_defs.values():
        tc = cp.get("textColor", "")
        if tc and tc not in colors:
            colors.append(tc)

    return StyleInfo(
        charPrCount=char_pr_count,
        paraPrCount=para_pr_count,
        borderFillCount=border_fill_count,
        charPr=char_pr_defs,
        paraPr=para_pr_defs,
        borderFill=border_fill_defs,
        colorPalette=colors,
    )


def collect_referenced_style_ids(section_xmls: list[bytes]) -> dict[str, list[str]]:
    """section XML들에서 참조되는 스타일 ID를 수집."""
    char_refs: list[str] = []
    para_refs: list[str] = []
    border_refs: list[str] = []

    for raw in section_xmls:
        try:
            text = raw.decode("utf-8", errors="replace")
        except Exception:
            continue
        char_refs.extend(_CHARPR_ID_RE.findall(text))
        para_refs.extend(_PARAPR_ID_RE.findall(text))
        border_refs.extend(_BORDERFILL_ID_RE.findall(text))

    return {
        "charPrIDRefs": list(dict.fromkeys(char_refs)),
        "paraPrIDRefs": list(dict.fromkeys(para_refs)),
        "borderFillIDRefs": list(dict.fromkeys(border_refs)),
    }


def detect_dangling_refs(style_info: StyleInfo, referenced_ids: dict[str, list[str]]) -> list[str]:
    """header에 정의되지 않은 참조 ID 목록을 반환."""
    dangling: list[str] = []
    char_defs = set(style_info.charPr.keys())
    para_defs = set(style_info.paraPr.keys())
    border_defs = set(style_info.borderFill.keys())

    if char_defs:
        for rid in referenced_ids.get("charPrIDRefs", []):
            if rid not in char_defs:
                dangling.append(f"charPr:{rid}")
    if para_defs:
        for rid in referenced_ids.get("paraPrIDRefs", []):
            if rid not in para_defs:
                dangling.append(f"paraPr:{rid}")
    if border_defs:
        for rid in referenced_ids.get("borderFillIDRefs", []):
            if rid not in border_defs:
                dangling.append(f"borderFill:{rid}")
    return dangling


def enrich_style_info(style_info: StyleInfo, section_xmls: list[bytes]) -> StyleInfo:
    """section XML 참조를 반영해 StyleInfo를 보강."""
    refs = collect_referenced_style_ids(section_xmls)
    style_info.referencedCharPrIds = refs["charPrIDRefs"]
    style_info.referencedParaPrIds = refs["paraPrIDRefs"]
    style_info.referencedBorderFillIds = refs["borderFillIDRefs"]
    style_info.danglingRefs = detect_dangling_refs(style_info, refs)
    return style_info
