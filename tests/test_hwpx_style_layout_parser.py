"""HWPX-STYLE-LAYOUT-PARSER-01 테스트.

style_parser / parser_contract / table_parser / parser_engine의
스타일 필드 파싱 기능을 검증한다.
"""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = PROJECT_ROOT / "tests" / "fixtures" / "hwpx" / "corpus"
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

METADATA_FX = FIXTURE_DIR / "fx_metadata_form.hwpx"
STAMP_FX = FIXTURE_DIR / "fx_stamp_approval_legal.hwpx"
NESTED_FX = FIXTURE_DIR / "fx_nested_legal_complex.hwpx"

NS_HH = "http://www.hancom.co.kr/hwpml/2011/head"
NS_HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"

_MINIMAL_HEADER = b"""<?xml version="1.0" encoding="UTF-8"?>
<hh:head xmlns:hh="http://www.hancom.co.kr/hwpml/2011/head">
  <hh:charPr id="0" height="1000" textColor="#000000">
    <hh:fontRef hangul="1" latin="1"/>
  </hh:charPr>
  <hh:charPr id="1" height="2400" textColor="#FF0000">
    <hh:fontRef hangul="2" latin="2"/>
  </hh:charPr>
  <hh:paraPr id="0" align="JUSTIFY" marginLeft="0" marginRight="0" marginTop="0" marginBottom="0"/>
  <hh:paraPr id="1" align="CENTER" marginLeft="100" marginRight="100" marginTop="50" marginBottom="50"/>
  <hh:borderFill id="1">
    <hh:leftBorder type="NONE" color="#000000" width="0.1mm"/>
    <hh:rightBorder type="NONE" color="#000000" width="0.1mm"/>
    <hh:topBorder type="NONE" color="#000000" width="0.1mm"/>
    <hh:bottomBorder type="NONE" color="#000000" width="0.1mm"/>
    <hh:fillBrush/>
  </hh:borderFill>
  <hh:borderFill id="2">
    <hh:leftBorder type="SOLID" color="#000000" width="0.4mm"/>
    <hh:rightBorder type="SOLID" color="#000000" width="0.4mm"/>
    <hh:topBorder type="SOLID" color="#000000" width="0.4mm"/>
    <hh:bottomBorder type="SOLID" color="#000000" width="0.4mm"/>
    <hh:fillBrush faceColor="#FFFF00"/>
  </hh:borderFill>
</hh:head>
"""


# ── 1. parse_char_pr_defs ──────────────────────────────────────────────────────

def test_parse_char_pr_defs_returns_dict():
    from hwpx.parser.style_parser import parse_char_pr_defs
    defs = parse_char_pr_defs(_MINIMAL_HEADER)
    assert isinstance(defs, dict)
    assert "0" in defs
    assert "1" in defs


def test_parse_char_pr_defs_height_and_font_size():
    from hwpx.parser.style_parser import parse_char_pr_defs
    defs = parse_char_pr_defs(_MINIMAL_HEADER)
    assert defs["0"]["height"] == 1000
    assert defs["0"]["fontSizePt"] == 10.0
    assert defs["1"]["height"] == 2400
    assert defs["1"]["fontSizePt"] == 24.0


def test_parse_char_pr_defs_text_color():
    from hwpx.parser.style_parser import parse_char_pr_defs
    defs = parse_char_pr_defs(_MINIMAL_HEADER)
    assert defs["0"]["textColor"] == "#000000"
    assert defs["1"]["textColor"] == "#FF0000"


# ── 2. parse_para_pr_defs ─────────────────────────────────────────────────────

def test_parse_para_pr_defs_returns_dict():
    from hwpx.parser.style_parser import parse_para_pr_defs
    defs = parse_para_pr_defs(_MINIMAL_HEADER)
    assert "0" in defs
    assert "1" in defs


def test_parse_para_pr_defs_align_and_margins():
    from hwpx.parser.style_parser import parse_para_pr_defs
    defs = parse_para_pr_defs(_MINIMAL_HEADER)
    assert defs["0"]["align"] == "JUSTIFY"
    assert defs["1"]["align"] == "CENTER"
    assert defs["1"]["marginLeft"] == 100
    assert defs["1"]["marginTop"] == 50


# ── 3. parse_border_fill_defs / extract_fill_color ────────────────────────────

def test_parse_border_fill_defs_returns_dict():
    from hwpx.parser.style_parser import parse_border_fill_defs
    defs = parse_border_fill_defs(_MINIMAL_HEADER)
    assert "1" in defs
    assert "2" in defs


def test_extract_fill_color_none_for_empty_brush():
    from hwpx.parser.style_parser import extract_fill_color
    el = ET.fromstring(f'<hh:borderFill xmlns:hh="{NS_HH}" id="1"><hh:fillBrush/></hh:borderFill>')
    assert extract_fill_color(el) is None


def test_extract_fill_color_returns_color():
    from hwpx.parser.style_parser import extract_fill_color
    el = ET.fromstring(f'<hh:borderFill xmlns:hh="{NS_HH}" id="2"><hh:fillBrush faceColor="#FFFF00"/></hh:borderFill>')
    assert extract_fill_color(el) == "#FFFF00"


def test_border_fill_summary_no_border():
    from hwpx.parser.style_parser import parse_border_fill_defs
    defs = parse_border_fill_defs(_MINIMAL_HEADER)
    assert defs["1"]["borderSummary"] == "no_border"


def test_border_fill_summary_full_box():
    from hwpx.parser.style_parser import parse_border_fill_defs
    defs = parse_border_fill_defs(_MINIMAL_HEADER)
    assert defs["2"]["borderSummary"] == "full_box"
    assert defs["2"]["fillColor"] == "#FFFF00"


# ── 4. detect_dangling_refs ───────────────────────────────────────────────────

def test_detect_dangling_refs_no_dangling():
    from hwpx.parser.style_parser import parse_style_summary, detect_dangling_refs
    si = parse_style_summary(_MINIMAL_HEADER)
    refs = {"charPrIDRefs": ["0"], "paraPrIDRefs": ["1"], "borderFillIDRefs": ["1", "2"]}
    dangling = detect_dangling_refs(si, refs)
    assert dangling == []


def test_detect_dangling_refs_detects_missing():
    from hwpx.parser.style_parser import parse_style_summary, detect_dangling_refs
    si = parse_style_summary(_MINIMAL_HEADER)
    refs = {"charPrIDRefs": ["99"], "paraPrIDRefs": [], "borderFillIDRefs": []}
    dangling = detect_dangling_refs(si, refs)
    assert any("charPr:99" in d for d in dangling)


# ── 5. parse_hwpx_v2 스타일 통합 검증 ─────────────────────────────────────────

@pytest.fixture(scope="session")
def metadata_parsed():
    from hwpx.parser import parse_hwpx_v2
    return parse_hwpx_v2(METADATA_FX)


def test_parsed_cells_have_border_fill_id(metadata_parsed):
    r = metadata_parsed
    cells = [c for t in r.tables for c in t.cells]
    filled = [c for c in cells if c.borderFillIDRef]
    assert len(filled) >= 1, "borderFillIDRef가 채워진 셀이 없음"


def test_parsed_cells_have_font_height(metadata_parsed):
    r = metadata_parsed
    cells = [c for t in r.tables for c in t.cells]
    with_font = [c for c in cells if c.fontHeight is not None]
    assert len(with_font) >= 1, "fontHeight가 채워진 셀이 없음"


def test_parsed_cells_have_vertical_align(metadata_parsed):
    r = metadata_parsed
    cells = [c for t in r.tables for c in t.cells]
    with_align = [c for c in cells if c.verticalAlign]
    assert len(with_align) >= 1, "verticalAlign이 채워진 셀이 없음"


def test_parsed_cells_have_border_summary(metadata_parsed):
    r = metadata_parsed
    cells = [c for t in r.tables for c in t.cells]
    with_bs = [c for c in cells if c.borderSummary]
    assert len(with_bs) >= 1, "borderSummary가 채워진 셀이 없음"


def test_style_info_has_defs(metadata_parsed):
    s = metadata_parsed.styles
    assert s.charPrCount >= 1
    assert len(s.charPr) == s.charPrCount
    assert s.borderFillCount >= 1
    assert len(s.borderFill) == s.borderFillCount


def test_style_info_no_dangling_refs(metadata_parsed):
    assert metadata_parsed.styles.danglingRefs == [], \
        f"dangling refs 발견: {metadata_parsed.styles.danglingRefs}"


# ── 6. paraPr child <align horizontal=".."/> 파싱 ────────────────────────────

_CHILD_ALIGN_HEADER = f"""<?xml version="1.0" encoding="UTF-8"?>
<hh:head xmlns:hh="{NS_HH}">
  <hh:paraPr id="10"><hh:align horizontal="LEFT"/></hh:paraPr>
  <hh:paraPr id="11"><hh:align horizontal="CENTER"/></hh:paraPr>
  <hh:paraPr id="12"><hh:align horizontal="RIGHT"/></hh:paraPr>
</hh:head>""".encode()


def test_parse_para_pr_defs_reads_child_align_horizontal():
    from hwpx.parser.style_parser import parse_para_pr_defs
    defs = parse_para_pr_defs(_CHILD_ALIGN_HEADER)
    assert defs["10"]["align"] == "LEFT"
    assert defs["11"]["align"] == "CENTER"
    assert defs["12"]["align"] == "RIGHT"


# ── 7. charPr child bold/italic/underline + textColor 파싱 ────────────────────

_CHAR_STYLE_HEADER = f"""<?xml version="1.0" encoding="UTF-8"?>
<hh:head xmlns:hh="{NS_HH}">
  <hh:charPr id="100" height="1000" textColor="#000000"/>
  <hh:charPr id="101" height="1000" textColor="#FF0000"><hh:bold/></hh:charPr>
  <hh:charPr id="102" height="1000" textColor="#0000FF"><hh:italic/></hh:charPr>
  <hh:charPr id="103" height="1000" textColor="#00AA00"><hh:underline type="SOLID"/></hh:charPr>
  <hh:charPr id="104" height="1000" textColor="#222222"><hh:underline type="NONE"/></hh:charPr>
</hh:head>""".encode()


def test_parse_char_pr_defs_extracts_bold_italic_underline_textcolor():
    from hwpx.parser.style_parser import parse_char_pr_defs
    defs = parse_char_pr_defs(_CHAR_STYLE_HEADER)
    assert defs["100"]["bold"] is False
    assert defs["100"]["italic"] is False
    assert defs["100"]["underline"] is False
    assert defs["100"]["textColor"] == "#000000"
    assert defs["101"]["bold"] is True
    assert defs["101"]["textColor"] == "#FF0000"
    assert defs["102"]["italic"] is True
    assert defs["102"]["textColor"] == "#0000FF"
    assert defs["103"]["underline"] is True
    assert defs["103"]["textColor"] == "#00AA00"
    # type="NONE"는 underline=False
    assert defs["104"]["underline"] is False


# ── 8. fontFace table → 실제 폰트명 역참조 ────────────────────────────────────

_FONT_TABLE_HEADER = f"""<?xml version="1.0" encoding="UTF-8"?>
<hh:head xmlns:hh="{NS_HH}">
  <hh:fontface lang="HANGUL" fontCnt="2">
    <hh:font id="0" face="굴림체" type="TTF"/>
    <hh:font id="1" face="돋움" type="TTF"/>
  </hh:fontface>
  <hh:fontface lang="LATIN" fontCnt="1">
    <hh:font id="0" face="Arial" type="TTF"/>
  </hh:fontface>
  <hh:charPr id="50" height="1000">
    <hh:fontRef hangul="1" latin="0"/>
  </hh:charPr>
  <hh:charPr id="51" height="1000">
    <hh:fontRef hangul="0" latin="0"/>
  </hh:charPr>
</hh:head>""".encode()


def test_parse_font_face_table_returns_lang_keyed_dict():
    from hwpx.parser.style_parser import parse_font_face_table
    table = parse_font_face_table(_FONT_TABLE_HEADER)
    assert table["HANGUL"]["0"] == "굴림체"
    assert table["HANGUL"]["1"] == "돋움"
    assert table["LATIN"]["0"] == "Arial"


def test_parse_char_pr_defs_resolves_fontName_via_font_table():
    from hwpx.parser.style_parser import parse_char_pr_defs
    defs = parse_char_pr_defs(_FONT_TABLE_HEADER)
    assert defs["50"]["fontName"] == "돋움"
    assert defs["51"]["fontName"] == "굴림체"
    # fontFace는 raw hangul ID 그대로 유지 (backward compat)
    assert defs["50"]["fontFace"] == "1"


def test_parsed_cells_have_resolved_font_name(metadata_parsed):
    cells = [c for t in metadata_parsed.tables for c in t.cells]
    with_name = [c for c in cells if c.fontName]
    assert len(with_name) >= 1, "fontName이 채워진 셀이 없음"
    # 숫자 ID가 아니라 실제 폰트명 문자열인지 검증
    for c in with_name[:20]:
        assert not c.fontName.isdigit(), f"fontName이 숫자 ID로 노출됨: {c.fontName}"


def test_parsed_cells_have_text_color(metadata_parsed):
    cells = [c for t in metadata_parsed.tables for c in t.cells]
    with_tc = [c for c in cells if c.textColor]
    assert len(with_tc) >= 1, "textColor 노출된 셀이 없음"


def test_parsed_cells_have_bold(metadata_parsed):
    cells = [c for t in metadata_parsed.tables for c in t.cells]
    assert any(c.bold for c in cells), "bold=True 셀이 없음"


def test_parsed_cells_font_size_preserved(metadata_parsed):
    cells = [c for t in metadata_parsed.tables for c in t.cells]
    assert any(c.fontSizePt is not None for c in cells), "fontSizePt 회귀"


def test_parsed_cells_have_horizontal_align(metadata_parsed):
    r = metadata_parsed
    cells = [c for t in r.tables for c in t.cells]
    with_h = [c for c in cells if c.horizontalAlign]
    assert len(with_h) >= 1, "horizontalAlign이 채워진 셀이 없음"
    vals = {c.horizontalAlign for c in with_h}
    # LEFT/CENTER/RIGHT/JUSTIFY 중 최소 2종 이상 노출
    expected = {"LEFT", "CENTER", "RIGHT", "JUSTIFY"}
    assert len(vals & expected) >= 2, \
        f"horizontalAlign 값 다양성 부족: {vals}"
