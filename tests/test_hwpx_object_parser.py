"""HWPX-RECOGNITION-OBJECT-MODEL-RESOLVER-01 단위/통합 테스트."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

NS_HH = "http://www.hancom.co.kr/hwpml/2011/head"
NS_HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"


_BIN_DATA_HEADER = f"""<?xml version="1.0" encoding="UTF-8"?>
<hh:head xmlns:hh="{NS_HH}">
  <hh:binDataList>
    <hh:binItem id="0" href="BinData/image0.png" format="png"/>
    <hh:binItem id="1" href="BinData/stamp1.bmp" format="bmp"/>
  </hh:binDataList>
</hh:head>""".encode()


_SECTION_WITH_OBJECTS = f"""<?xml version="1.0" encoding="UTF-8"?>
<hp:sec xmlns:hp="{NS_HP}">
  <hp:p>
    <hp:rect id="100" zOrder="0">
      <hp:offset x="50" y="100"/>
      <hp:curSz width="800" height="600"/>
    </hp:rect>
    <hp:line id="101"><hp:offset x="0" y="0"/><hp:curSz width="500" height="2"/></hp:line>
    <hp:ellipse id="102"><hp:curSz width="200" height="200"/></hp:ellipse>
    <hp:pic id="103"><hp:offset x="10" y="20"/><hp:curSz width="300" height="400"/></hp:pic>
  </hp:p>
</hp:sec>""".encode()


# ── 1. BinData 파싱 ──────────────────────────────────────────────────────────

def test_parse_bin_data_from_header_returns_list():
    from hwpx.parser.object_parser import parse_bin_data_from_header
    bins = parse_bin_data_from_header(_BIN_DATA_HEADER)
    assert len(bins) == 2
    by_id = {b.binId: b for b in bins}
    assert by_id["0"].href == "BinData/image0.png"
    assert by_id["0"].format == "png"
    assert by_id["1"].href == "BinData/stamp1.bmp"


def test_parse_bin_data_empty_returns_empty():
    from hwpx.parser.object_parser import parse_bin_data_from_header
    empty = f'<hh:head xmlns:hh="{NS_HH}"/>'.encode()
    assert parse_bin_data_from_header(empty) == []


# ── 2. section 객체 파싱 ─────────────────────────────────────────────────────

def test_parse_objects_detects_rect_line_ellipse_picture():
    from hwpx.parser.object_parser import parse_objects_from_section
    objs = parse_objects_from_section(_SECTION_WITH_OBJECTS, 0, "Contents/section0.xml")
    types = {o.objectType for o in objs}
    assert "rect" in types
    assert "line" in types
    assert "ellipse" in types
    assert "picture" in types


def test_parsed_objects_have_geometry():
    from hwpx.parser.object_parser import parse_objects_from_section
    objs = parse_objects_from_section(_SECTION_WITH_OBJECTS, 0, "Contents/section0.xml")
    rect = [o for o in objs if o.objectType == "rect"][0]
    assert rect.width == 800
    assert rect.height == 600
    assert rect.posX == 50
    assert rect.posY == 100
    assert rect.sectionIndex == 0
    assert rect.sourcePath == "Contents/section0.xml"
    assert rect.rawTag == "rect"


# ── 3. ParserV2Result 통합 ───────────────────────────────────────────────────

def test_parser_v2_result_exposes_objects_for_gantt_fixture():
    from hwpx.parser import parse_hwpx_v2
    r = parse_hwpx_v2(PROJECT_ROOT / "tests/fixtures/hwpx/gantt/fx_gantt_like_basic.hwpx")
    assert hasattr(r, "objects")
    assert hasattr(r, "binData")
    assert len(r.objects) >= 1, "gantt 문서에서 shape/container 객체가 노출되지 않음"
    types = {o.objectType for o in r.objects}
    assert "rect" in types or "container" in types


def test_parser_v2_result_objects_have_dict_repr():
    from hwpx.parser import parse_hwpx_v2
    r = parse_hwpx_v2(PROJECT_ROOT / "tests/fixtures/hwpx/gantt/fx_gantt_like_basic.hwpx")
    d = r.to_dict()
    assert "objects" in d
    assert "binData" in d
    if r.objects:
        first = d["objects"][0]
        for key in ("objectId", "objectType", "sectionIndex", "rawTag"):
            assert key in first
