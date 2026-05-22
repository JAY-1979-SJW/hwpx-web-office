"""
HWPX-EDITOR-APPEND-ROW-EMPTY-CELL-TEXTNODE-FIX-01 회귀 테스트.

원본 row의 빈 셀에 <hp:t> 노드가 없거나 비어있을 때도 append_table_row가
row_values의 모든 값을 정상 입력하는지 검증한다.
"""
from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "hwpx"))

from hwpx_package import HwpxPackage  # noqa: E402
from hwpx_table_ops import append_table_row  # noqa: E402

NS_HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _build_fixture(tmp_path: Path, *, empty_cells_in_last_row: bool = True) -> Path:
    """8셀 1행 + (헤더1행 + 데이터1행) 테이블을 가진 최소 HWPX 픽스처 생성.

    empty_cells_in_last_row=True 이면 데이터 행의 8셀 중 7개에 <hp:t> 노드가 없고
    1개에만 'm'이 들어있다 (굴착공사 협의서 fixture 형태와 동일).
    """
    section_xml = _section_xml(empty_cells_in_last_row)
    header_xml = _header_xml()
    content_hpf = _content_hpf()
    manifest_xml = _manifest_xml()
    container_xml = _container_xml()
    container_rdf = _container_rdf()
    version_xml = _version_xml()
    settings_xml = _settings_xml()

    path = tmp_path / "fixture.hwpx"
    with zipfile.ZipFile(path, "w") as zf:
        info = zipfile.ZipInfo("mimetype")
        info.compress_type = zipfile.ZIP_STORED
        zf.writestr(info, "application/hwp+zip")
        zf.writestr("version.xml", version_xml, compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr("settings.xml", settings_xml, compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr("META-INF/container.xml", container_xml, compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr("META-INF/container.rdf", container_rdf, compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr("META-INF/manifest.xml", manifest_xml, compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr("Contents/content.hpf", content_hpf, compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr("Contents/header.xml", header_xml, compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr("Contents/section0.xml", section_xml, compress_type=zipfile.ZIP_DEFLATED)
    return path


def _section_xml(empty_cells_in_last_row: bool) -> str:
    """단일 4x8 (실제로는 1x8 헤더 + 1x8 데이터) 테이블 포함 섹션 XML."""
    head_cells = "".join(
        f'<hp:tc name="" header="0" hasMargin="0" protect="0" editable="0" dirty="0" borderFillIDRef="1">'
        f'<hp:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="CENTER" linkListIDRef="0" linkListNextIDRef="0" textWidth="0" textHeight="0" hasTextRef="0" hasNumRef="0">'
        f'<hp:p id="0" paraPrIDRef="3" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
        f'<hp:run charPrIDRef="5"><hp:t>H{idx}</hp:t></hp:run></hp:p></hp:subList>'
        f'<hp:cellAddr colAddr="{idx}" rowAddr="0"/><hp:cellSpan colSpan="1" rowSpan="1"/><hp:cellMargin left="510" right="510" top="141" bottom="141"/></hp:tc>'
        for idx in range(8)
    )
    if empty_cells_in_last_row:
        # 첫 7개 셀: <hp:t> 노드 없음 (한컴 hwpx 변환 결과 형태). 8번째 셀만 'm' 보유.
        body_cells = "".join(
            f'<hp:tc name="" header="0" hasMargin="0" protect="0" editable="0" dirty="0" borderFillIDRef="1">'
            f'<hp:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="CENTER" linkListIDRef="0" linkListNextIDRef="0" textWidth="0" textHeight="0" hasTextRef="0" hasNumRef="0">'
            f'<hp:p id="0" paraPrIDRef="3" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
            f'<hp:run charPrIDRef="5"/></hp:p></hp:subList>'
            f'<hp:cellAddr colAddr="{idx}" rowAddr="1"/><hp:cellSpan colSpan="1" rowSpan="1"/><hp:cellMargin left="510" right="510" top="141" bottom="141"/></hp:tc>'
            for idx in range(7)
        )
        body_cells += (
            '<hp:tc name="" header="0" hasMargin="0" protect="0" editable="0" dirty="0" borderFillIDRef="1">'
            '<hp:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="CENTER" linkListIDRef="0" linkListNextIDRef="0" textWidth="0" textHeight="0" hasTextRef="0" hasNumRef="0">'
            '<hp:p id="0" paraPrIDRef="3" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
            '<hp:run charPrIDRef="5"><hp:t>m</hp:t></hp:run></hp:p></hp:subList>'
            '<hp:cellAddr colAddr="7" rowAddr="1"/><hp:cellSpan colSpan="1" rowSpan="1"/><hp:cellMargin left="510" right="510" top="141" bottom="141"/></hp:tc>'
        )
    else:
        body_cells = "".join(
            f'<hp:tc name="" header="0" hasMargin="0" protect="0" editable="0" dirty="0" borderFillIDRef="1">'
            f'<hp:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="CENTER" linkListIDRef="0" linkListNextIDRef="0" textWidth="0" textHeight="0" hasTextRef="0" hasNumRef="0">'
            f'<hp:p id="0" paraPrIDRef="3" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
            f'<hp:run charPrIDRef="5"><hp:t>B{idx}</hp:t></hp:run></hp:p></hp:subList>'
            f'<hp:cellAddr colAddr="{idx}" rowAddr="1"/><hp:cellSpan colSpan="1" rowSpan="1"/><hp:cellMargin left="510" right="510" top="141" bottom="141"/></hp:tc>'
            for idx in range(8)
        )
    table = (
        '<hp:tbl id="0" zOrder="0" numberingType="TABLE" textWrap="TOP_AND_BOTTOM" textFlow="BOTH_SIDES" lock="0" dropcapStyle="None" pageBreak="CELL" repeatHeader="1" rowCnt="2" colCnt="8" cellSpacing="0" borderFillIDRef="2" noAdjust="0">'
        '<hp:sz width="40000" widthRelTo="ABSOLUTE" height="2000" heightRelTo="ABSOLUTE" protect="0"/>'
        '<hp:pos treatAsChar="0" affectLSpacing="0" flowWithText="1" allowOverlap="0" holdAnchorAndSO="0" vertRelTo="PARA" horzRelTo="COLUMN" vertAlign="TOP" horzAlign="LEFT" vertOffset="0" horzOffset="0"/>'
        '<hp:outMargin left="0" right="0" top="0" bottom="0"/>'
        '<hp:inMargin left="510" right="510" top="141" bottom="141"/>'
        f'<hp:tr>{head_cells}</hp:tr>'
        f'<hp:tr>{body_cells}</hp:tr>'
        "</hp:tbl>"
    )
    section = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>'
        f'<hs:sec xmlns:hp="{NS_HP}" xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" xmlns:hh="http://www.hancom.co.kr/hwpml/2011/head">'
        '<hp:p id="0" paraPrIDRef="3" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
        '<hp:run charPrIDRef="5">'
        f'{table}'
        "</hp:run></hp:p></hs:sec>"
    )
    return section


def _header_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>'
        '<hh:head xmlns:hh="http://www.hancom.co.kr/hwpml/2011/head" xmlns:hc="http://www.hancom.co.kr/hwpml/2011/core" version="5.1">'
        '<hh:beginNum page="1" footnote="1" endnote="1" pic="1" tbl="1" equation="1"/>'
        '<hh:refList>'
        '<hh:fontfaces itemCnt="1"><hh:fontface lang="HANGUL" itemCnt="1"><hh:font id="0" face="함초롬바탕" type="TTF" isEmbedded="0"/></hh:fontface></hh:fontfaces>'
        '<hh:borderFills itemCnt="2">'
        '<hh:borderFill id="1" threeD="0" shadow="0" centerLine="NONE" breakCellSeparateLine="0"><hh:slash type="NONE" Crooked="0" isCounter="0"/><hh:backSlash type="NONE" Crooked="0" isCounter="0"/><hh:leftBorder type="SOLID" width="0.12 mm" color="#000000"/><hh:rightBorder type="SOLID" width="0.12 mm" color="#000000"/><hh:topBorder type="SOLID" width="0.12 mm" color="#000000"/><hh:bottomBorder type="SOLID" width="0.12 mm" color="#000000"/><hh:diagonal type="SOLID" width="0.1 mm" color="#000000"/></hh:borderFill>'
        '<hh:borderFill id="2" threeD="0" shadow="0" centerLine="NONE" breakCellSeparateLine="0"><hh:slash type="NONE" Crooked="0" isCounter="0"/><hh:backSlash type="NONE" Crooked="0" isCounter="0"/><hh:leftBorder type="SOLID" width="0.12 mm" color="#000000"/><hh:rightBorder type="SOLID" width="0.12 mm" color="#000000"/><hh:topBorder type="SOLID" width="0.12 mm" color="#000000"/><hh:bottomBorder type="SOLID" width="0.12 mm" color="#000000"/><hh:diagonal type="SOLID" width="0.1 mm" color="#000000"/></hh:borderFill>'
        '</hh:borderFills>'
        '<hh:charProperties itemCnt="1"><hh:charPr id="5" height="1000" textColor="#000000" shadeColor="none" useFontSpace="0" useKerning="0" symMark="NONE" borderFillIDRef="0"><hh:fontRef hangul="0" latin="0" hanja="0" japanese="0" other="0" symbol="0" user="0"/><hh:ratio hangul="100" latin="100" hanja="100" japanese="100" other="100" symbol="100" user="100"/><hh:spacing hangul="0" latin="0" hanja="0" japanese="0" other="0" symbol="0" user="0"/><hh:relSz hangul="100" latin="100" hanja="100" japanese="100" other="100" symbol="100" user="100"/><hh:offset hangul="0" latin="0" hanja="0" japanese="0" other="0" symbol="0" user="0"/><hh:italic/><hh:bold/><hh:underline type="NONE" shape="SOLID" color="#000000"/><hh:strikeout shape="NONE" color="#000000"/><hh:outline type="NONE"/><hh:shadow type="NONE" color="#C0C0C0" offsetX="10" offsetY="10"/></hh:charPr></hh:charProperties>'
        '<hh:tabProperties itemCnt="0"></hh:tabProperties>'
        '<hh:numberings itemCnt="0"></hh:numberings>'
        '<hh:bullets itemCnt="0"></hh:bullets>'
        '<hh:paraProperties itemCnt="1"><hh:paraPr id="3" tabPrIDRef="0" condense="0" fontLineHeight="0" snapToGrid="1" suppressLineNumbers="0" checked="0"><hh:align horizontal="JUSTIFY" vertical="BASELINE"/><hh:heading type="NONE" idRef="0" level="0"/><hh:breakSetting breakLatinWord="KEEP_WORD" breakNonLatinWord="KEEP_WORD" widowOrphan="0" keepWithNext="0" keepLines="0" pageBreakBefore="0" lineWrap="BREAK"/><hh:margin><hh:intent value="0" relative="0"/><hh:left value="0" relative="0"/><hh:right value="0" relative="0"/><hh:prev value="0" relative="0"/><hh:next value="0" relative="0"/></hh:margin><hh:lineSpacing type="PERCENT" value="160" unit="PERCENT"/><hh:border borderFillIDRef="0" offsetLeft="0" offsetRight="0" offsetTop="0" offsetBottom="0" connect="0" ignoreMargin="0"/></hh:paraPr></hh:paraProperties>'
        '<hh:styles itemCnt="1"><hh:style id="0" type="PARA" name="바탕글" engName="Normal" paraPrIDRef="3" charPrIDRef="5" nextStyleIDRef="0" langID="1042" lockForm="0"/></hh:styles>'
        '<hh:memoProperties itemCnt="0"></hh:memoProperties>'
        '<hh:trackChanges itemCnt="0"></hh:trackChanges>'
        '<hh:trackChangeAuthors itemCnt="0"></hh:trackChangeAuthors>'
        '</hh:refList>'
        '<hh:forbiddenWordList itemCnt="0"></hh:forbiddenWordList>'
        '<hh:compatibleDocument targetProgram="HWP301"/>'
        '<hh:metaTag></hh:metaTag>'
        '<hh:trackchangeConfig flags="0"/>'
        '</hh:head>'
    )


def _content_hpf() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<opf:package xmlns:opf="http://www.idpf.org/2007/opf/" version="1.0">'
        '<opf:metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        '<dc:title/><dc:creator/><dc:format>application/hwpml-package+xml</dc:format>'
        '</opf:metadata>'
        '<opf:manifest>'
        '<opf:item id="header" href="header.xml" media-type="application/xml"/>'
        '<opf:item id="section0" href="section0.xml" media-type="application/xml"/>'
        '<opf:item id="settings" href="../settings.xml" media-type="application/xml"/>'
        '</opf:manifest>'
        '<opf:spine><opf:itemref idref="header"/><opf:itemref idref="section0"/></opf:spine>'
        '</opf:package>'
    )


def _manifest_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0">'
        '<manifest:file-entry manifest:full-path="/" manifest:media-type="application/hwpml-package+xml"/>'
        '</manifest:manifest>'
    )


def _container_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
        '<rootfiles>'
        '<rootfile full-path="Contents/content.hpf" media-type="application/hwpml-package+xml"/>'
        '</rootfiles>'
        '</container>'
    )


def _container_rdf() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns:hpf="http://www.hancom.co.kr/schema/2011/hpf">'
        '<rdf:Description rdf:about="Contents/content.hpf"><rdf:type rdf:resource="http://www.hancom.co.kr/schema/2011/hpf#Document"/></rdf:Description>'
        '</rdf:RDF>'
    )


def _version_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<ha:HCFVersion xmlns:ha="http://www.hancom.co.kr/hwpml/2011/app" ha:targetApplication="WORDPROCESSOR" ha:major="5" ha:minor="1" ha:micro="0" ha:buildNumber="1"/>'
    )


def _settings_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<ha:HWPApplicationSetting xmlns:ha="http://www.hancom.co.kr/hwpml/2011/app"/>'
    )


def _read_section_cells(path: Path) -> list[list[list[str]]]:
    """결과 HWPX에서 section0.xml의 (table, row, col) → cell text 추출."""
    import xml.etree.ElementTree as ET
    with zipfile.ZipFile(path) as zf:
        root = ET.fromstring(zf.read("Contents/section0.xml"))
    tables = list(root.iter(f"{{{NS_HP}}}tbl"))
    result = []
    for tbl in tables:
        rows_out = []
        for tr in [c for c in tbl if c.tag == f"{{{NS_HP}}}tr"]:
            cells_out = []
            for tc in [c for c in tr if c.tag == f"{{{NS_HP}}}tc"]:
                text = "".join(t.text or "" for t in tc.iter(f"{{{NS_HP}}}t"))
                cells_out.append(text)
            rows_out.append(cells_out)
        result.append(rows_out)
    return result


# ──────────────────────────────────────────────────────────────────────────────


def test_append_row_into_table_with_empty_cells_writes_all_values(tmp_path):
    """빈 셀로 구성된 row를 복제해도 row_values 8개 모두 반영된다."""
    fixture = _build_fixture(tmp_path, empty_cells_in_last_row=True)
    pkg = HwpxPackage(fixture)
    values = ["1", "배관 B구간", "LNG", "0.2MPa", "SPPS", "DN100", "120m", "비고메모"]
    result = append_table_row(pkg, table_index=0, row_values=values, clear_remaining=True)
    pkg.write_package(fixture)

    assert result["status"] == "APPEND_ROW_PASS"
    assert result["row_count_before"] == 2
    assert result["row_count_after"] == 3
    assert result["cell_count"] == 8
    assert result["updated_cells"] == 8, f"updated_cells expected 8, got {result['updated_cells']}"

    cells = _read_section_cells(fixture)
    assert len(cells) == 1  # 단일 테이블
    assert len(cells[0]) == 3  # 헤더 + 데이터 + 추가행
    appended = cells[0][2]
    assert appended == values, f"appended row mismatch: {appended} vs {values}"


def test_append_row_does_not_alter_existing_rows(tmp_path):
    """기존 행 텍스트는 변경되지 않는다."""
    fixture = _build_fixture(tmp_path, empty_cells_in_last_row=True)
    pkg = HwpxPackage(fixture)
    before = _read_section_cells(fixture)[0]
    append_table_row(pkg, table_index=0, row_values=["X"] * 8, clear_remaining=True)
    pkg.write_package(fixture)
    after = _read_section_cells(fixture)[0]
    assert after[0] == before[0], "header row was altered"
    assert after[1] == before[1], "original data row was altered"


def test_append_row_preserves_charPrIDRef_paraPrIDRef(tmp_path):
    """추가된 셀의 charPrIDRef / paraPrIDRef가 dangling 없이 보존된다."""
    import xml.etree.ElementTree as ET
    fixture = _build_fixture(tmp_path, empty_cells_in_last_row=True)
    pkg = HwpxPackage(fixture)
    append_table_row(pkg, table_index=0, row_values=["A"] * 8, clear_remaining=True)
    pkg.write_package(fixture)

    with zipfile.ZipFile(fixture) as zf:
        section = ET.fromstring(zf.read("Contents/section0.xml"))
        header = ET.fromstring(zf.read("Contents/header.xml"))

    char_ids = {cp.attrib.get("id") for cp in header.iter(f"{{http://www.hancom.co.kr/hwpml/2011/head}}charPr")}
    para_ids = {pp.attrib.get("id") for pp in header.iter(f"{{http://www.hancom.co.kr/hwpml/2011/head}}paraPr")}
    referenced_chars = {run.attrib.get("charPrIDRef") for run in section.iter(f"{{{NS_HP}}}run") if run.attrib.get("charPrIDRef")}
    referenced_paras = {p.attrib.get("paraPrIDRef") for p in section.iter(f"{{{NS_HP}}}p") if p.attrib.get("paraPrIDRef")}
    assert referenced_chars <= char_ids, f"dangling charPrIDRef: {referenced_chars - char_ids}"
    assert referenced_paras <= para_ids, f"dangling paraPrIDRef: {referenced_paras - para_ids}"


def test_mimetype_remains_zip_stored_after_rewrite(tmp_path):
    """write_package 후에도 mimetype은 ZIP_STORED여야 한다 (한컴 호환성)."""
    fixture = _build_fixture(tmp_path, empty_cells_in_last_row=True)
    pkg = HwpxPackage(fixture)
    append_table_row(pkg, table_index=0, row_values=["a", "b"], clear_remaining=True)
    pkg.write_package(fixture)
    with zipfile.ZipFile(fixture) as zf:
        info = zf.getinfo("mimetype")
        assert info.compress_type == zipfile.ZIP_STORED, f"mimetype compressed: {info.compress_type}"
        assert zf.read("mimetype") == b"application/hwp+zip"


def test_append_row_with_partially_filled_cells_still_writes_all_values(tmp_path):
    """원본 row의 일부 셀에 텍스트가 있어도 추가 행은 모든 값을 받는다."""
    fixture = _build_fixture(tmp_path, empty_cells_in_last_row=False)
    pkg = HwpxPackage(fixture)
    values = ["v0", "v1", "v2", "v3", "v4", "v5", "v6", "v7"]
    result = append_table_row(pkg, table_index=0, row_values=values, clear_remaining=True)
    pkg.write_package(fixture)
    assert result["updated_cells"] == 8
    appended = _read_section_cells(fixture)[0][2]
    assert appended == values


def test_clear_remaining_clears_unset_cells(tmp_path):
    """row_values가 셀 수보다 적고 clear_remaining=True면 나머지 셀이 비워진다."""
    fixture = _build_fixture(tmp_path, empty_cells_in_last_row=True)
    pkg = HwpxPackage(fixture)
    result = append_table_row(pkg, table_index=0, row_values=["a", "b", "c"], clear_remaining=True)
    pkg.write_package(fixture)
    assert result["updated_cells"] == 3
    appended = _read_section_cells(fixture)[0][2]
    assert appended[:3] == ["a", "b", "c"]
    # 나머지 5개는 빈 문자열
    assert all(cell == "" for cell in appended[3:])
