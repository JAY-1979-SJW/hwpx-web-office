"""coord_styles — header.xml 스타일(정렬/서식/테두리) + 페이지 규격 파싱.

coordinate_layout 에서 분리(모듈화). 실패 시 빈 결과 반환 — 좌표(위치)
재현은 서식 없이도 계속된다. read-only, 원본 무수정.
"""
import xml.etree.ElementTree as ET

try:
    from .coord_xml import HU, ln, mm_px
except ImportError:                      # 스크립트 직접 실행 폴백
    from coord_xml import HU, ln, mm_px


def parse_para_aligns(z):
    """header.xml 의 paraPr → {id: 'LEFT'|'CENTER'|'RIGHT'|'JUSTIFY'|...}.
    가운데/오른쪽 정렬 문단의 수평 배치를 재현하기 위함."""
    hdr = [n for n in z.namelist() if n.lower().endswith("header.xml")]
    if not hdr:
        return {}
    root = ET.fromstring(z.read(hdr[0]))
    out = {}
    for pp in root.iter():
        if ln(pp.tag) != "paraPr":
            continue
        pid = pp.attrib.get("id")
        al = pp.attrib.get("align", "")
        if not al:
            ach = next((c.attrib for c in pp if ln(c.tag) == "align"), {})
            al = ach.get("horizontal", "") or ach.get("align", "")
        if pid is not None:
            out[pid] = (al or "LEFT").upper()
    return out


def css_align(a):
    """HWPX 수평정렬 → CSS text-align (LEFT/기본은 None)."""
    if a in ("CENTER",):
        return "center"
    if a in ("RIGHT",):
        return "right"
    if a in ("JUSTIFY", "DISTRIBUTE"):
        return "justify"
    return None


def parse_char_prs(z):
    """header.xml 의 charPr 정의 → {id: {...서식...}} (style_parser 재사용).

    실패해도 {} 반환 — 좌표(위치) 재현은 서식 없이도 계속된다.
    """
    hdr = [n for n in z.namelist() if n.lower().endswith("header.xml")]
    if not hdr:
        return {}
    try:
        hb = z.read(hdr[0])
        from scripts.hwpx.parser.style_parser import (
            parse_char_pr_defs, parse_font_face_table)
        return parse_char_pr_defs(hb, parse_font_face_table(hb))
    except Exception:
        return {}


def _fill_color(bf_el):
    """borderFill 의 fillBrush 채움색(faceColor 등) → '#RRGGBB' 또는 None.
    'none'/흰색은 None(칠하지 않음 — 흰 배경 위 덧칠 방지)."""
    fb = next((c for c in bf_el if ln(c.tag) == "fillBrush"), None)
    if fb is None:
        return None
    for el in fb.iter():
        for attr in ("faceColor", "color", "startColor"):
            v = (el.attrib.get(attr) or "").strip()
            if not v or v.lower() == "none":
                continue
            h = v[1:] if v.startswith("#") else v
            if len(h) == 8:      # AARRGGBB/RRGGBBAA → 앞 6자리
                h = h[:6]
            if len(h) == 6 and all(c in "0123456789abcdefABCDEF" for c in h):
                col = "#" + h.upper()
                if col != "#FFFFFF":
                    return col
            # 흰색/비정형 값은 건너뛰고 다음 후보 계속 탐색 (엄격 hex 만 채택)
    return None


def parse_border_fills(z):
    """header.xml 의 borderFill → {id: {"sides": {...}, "fill": '#RRGGBB'|None}}."""
    hdr = [n for n in z.namelist() if n.lower().endswith("header.xml")]
    if not hdr:
        return {}
    root = ET.fromstring(z.read(hdr[0]))
    out = {}
    for bf in root.iter():
        if ln(bf.tag) != "borderFill":
            continue
        bid = bf.attrib.get("id")
        sides = {}
        for ch in bf:
            name = ln(ch.tag)
            if name in ("leftBorder", "rightBorder", "topBorder",
                        "bottomBorder"):
                sides[name] = dict(ch.attrib)
        if bid is not None:
            out[bid] = {"sides": sides, "fill": _fill_color(bf)}
    return out


def border_sides_css(sides):
    """borderFill sides → 변별 CSS border 선언({"l","r","t","b"})."""
    def one(sd):
        if not sd or sd.get("type", "NONE") == "NONE":
            return "none"
        w = max(0.7, mm_px(sd.get("width")))
        return f"{w:.2f}px solid {sd.get('color', '#000')}"
    return {
        "l": one(sides.get("leftBorder")),
        "r": one(sides.get("rightBorder")),
        "t": one(sides.get("topBorder")),
        "b": one(sides.get("bottomBorder")),
    }


def parse_page_geometry(root):
    """secPr 의 pagePr·margin → 페이지 규격(px).

    content_h 는 인쇄 가능 높이(상·하·머리·꼬리 여백 제외) — 자동흐름
    페이지 나눔의 권위 기준. 비정상 여백은 방어적으로 완화한다.
    """
    pp = next((e.attrib for e in root.iter() if ln(e.tag) == "pagePr"), {})
    mg = next((e.attrib for e in root.iter() if ln(e.tag) == "margin"), {})
    page_w = float(pp.get("width", "59528")) * HU
    page_h = float(pp.get("height", "84186")) * HU
    m_left = float(mg.get("left", "4251")) * HU
    m_top = float(mg.get("top", "4251")) * HU
    m_bottom = float(mg.get("bottom", "4251")) * HU
    m_header = float(mg.get("header", "0")) * HU
    m_footer = float(mg.get("footer", "0")) * HU
    content_h = page_h - m_top - m_bottom - m_header - m_footer
    if content_h < page_h * 0.3:   # 비정상 여백 방어
        content_h = page_h - m_top - m_bottom
    if content_h <= 0:
        content_h = page_h
    return {
        "page_w": page_w, "page_h": page_h,
        "m_left": m_left, "m_top": m_top,
        "content_h": content_h,
    }
