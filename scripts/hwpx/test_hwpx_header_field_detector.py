from __future__ import annotations

import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from hancom_hwpx_detect_input_fields import run_detect_input_fields
from hwpx_header_field_detector import detect_input_fields
from hwpx_package import HwpxPackage


def write_header_fixture(path: Path) -> None:
    header = """<?xml version="1.0" encoding="UTF-8"?>
<hh:head xmlns:hh="http://www.hancom.co.kr/hwpml/2011/head">
  <hh:refList>
    <hh:charProperties itemCnt="1"><hh:charPr id="0" height="1000" /></hh:charProperties>
  </hh:refList>
</hh:head>
"""
    section = """<?xml version="1.0" encoding="UTF-8"?>
<hp:sec xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">
  <hp:p id="top1"><hp:run><hp:t>Project Title :</hp:t></hp:run></hp:p>
  <hp:p id="top2"><hp:run><hp:t>검사 예정일 : 20  년  월  일</hp:t></hp:run></hp:p>
  <hp:p id="1"><hp:run><hp:tbl>
    <hp:tr>
      <hp:tc><hp:subList><hp:p><hp:run><hp:t>감리자 상호</hp:t></hp:run></hp:p></hp:subList><hp:cellAddr rowAddr="0" colAddr="0" /><hp:cellSpan rowSpan="1" colSpan="1" /><hp:cellSz width="6000" height="1800" /><hp:cellMargin left="100" right="100" top="100" bottom="100" /></hp:tc>
      <hp:tc><hp:subList><hp:p><hp:run><hp:t></hp:t></hp:run></hp:p></hp:subList><hp:cellAddr rowAddr="0" colAddr="1" /><hp:cellSpan rowSpan="1" colSpan="1" /><hp:cellSz width="12000" height="1800" /><hp:cellMargin left="100" right="100" top="100" bottom="100" /></hp:tc>
    </hp:tr>
    <hp:tr>
      <hp:tc><hp:subList><hp:p><hp:run><hp:t>품명</hp:t></hp:run></hp:p></hp:subList><hp:cellAddr rowAddr="1" colAddr="0" /><hp:cellSpan rowSpan="1" colSpan="1" /><hp:cellSz width="6000" height="1800" /><hp:cellMargin left="100" right="100" top="100" bottom="100" /></hp:tc>
      <hp:tc><hp:subList><hp:p><hp:run><hp:t>규격</hp:t></hp:run></hp:p></hp:subList><hp:cellAddr rowAddr="1" colAddr="1" /><hp:cellSpan rowSpan="1" colSpan="1" /><hp:cellSz width="6000" height="1800" /><hp:cellMargin left="100" right="100" top="100" bottom="100" /></hp:tc>
    </hp:tr>
    <hp:tr>
      <hp:tc><hp:subList><hp:p><hp:run><hp:t></hp:t></hp:run></hp:p></hp:subList><hp:cellAddr rowAddr="2" colAddr="0" /><hp:cellSpan rowSpan="1" colSpan="1" /><hp:cellSz width="6000" height="1800" /><hp:cellMargin left="100" right="100" top="100" bottom="100" /></hp:tc>
      <hp:tc><hp:subList><hp:p><hp:run><hp:t></hp:t></hp:run></hp:p></hp:subList><hp:cellAddr rowAddr="2" colAddr="1" /><hp:cellSpan rowSpan="1" colSpan="1" /><hp:cellSz width="6000" height="1800" /><hp:cellMargin left="100" right="100" top="100" bottom="100" /></hp:tc>
    </hp:tr>
  </hp:tbl></hp:run></hp:p>
</hp:sec>
"""
    content = """<?xml version="1.0" encoding="UTF-8"?>
<opf:package xmlns:opf="http://www.idpf.org/2007/opf">
  <opf:manifest>
    <opf:item id="header" href="Contents/header.xml" media-type="application/xml"/>
    <opf:item id="section0" href="Contents/section0.xml" media-type="application/xml"/>
  </opf:manifest>
  <opf:spine><opf:itemref idref="section0"/></opf:spine>
</opf:package>
"""
    container = """<?xml version="1.0" encoding="UTF-8"?>
<ocf:container xmlns:ocf="urn:oasis:names:tc:opendocument:xmlns:container">
  <ocf:rootfiles><ocf:rootfile full-path="Contents/content.hpf" media-type="application/hwpml-package+xml"/></ocf:rootfiles>
</ocf:container>
"""
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", "application/hwp+zip")
        zf.writestr("Contents/header.xml", header)
        zf.writestr("Contents/section0.xml", section)
        zf.writestr("Contents/content.hpf", content)
        zf.writestr("META-INF/container.xml", container)


def test_detects_right_and_below_input_fields(tmp_path: Path) -> None:
    path = tmp_path / "sample.hwpx"
    write_header_fixture(path)

    report = detect_input_fields(HwpxPackage(path))
    labels = {field["label"]: field for field in report["fields"]}

    assert report["status"] == "PASS"
    assert labels["Project Title"]["target"]["kind"] == "paragraph"
    assert labels["검사 예정일"]["target"]["kind"] == "paragraph"
    assert labels["감리자 상호"]["target"] == {"row": 0, "col": 1, "rowspan": 1, "colspan": 1, "current_text": "", "empty_or_placeholder": True}
    assert labels["품명"]["target"]["row"] == 2
    assert labels["규격"]["target"]["col"] == 1


def test_detect_cli_writes_template(tmp_path: Path) -> None:
    path = tmp_path / "sample.hwpx"
    write_header_fixture(path)

    report = run_detect_input_fields(path)

    assert report["status"] == "PASS"
    assert "감리자 상호" in report["input_template"]
