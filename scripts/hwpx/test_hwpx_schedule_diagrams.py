from __future__ import annotations

import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from hancom_hwpx_schedule_diagram_suite import run_schedule_diagram_suite
from hwpx_package import HwpxPackage
from hwpx_schedule_diagrams import DEFAULT_SCHEDULE_ITEMS, diagram_tables
from hwpx_table_ops import find_tables


def write_minimal_hwpx(path: Path) -> None:
    header = """<?xml version="1.0" encoding="UTF-8"?>
<hh:head xmlns:hh="http://www.hancom.co.kr/hwpml/2011/head" xmlns:hc="http://www.hancom.co.kr/hwpml/2011/core">
  <hh:refList>
    <hh:borderFills itemCnt="1">
      <hh:borderFill id="1" threeD="0" shadow="0" centerLine="NONE" breakCellSeparateLine="0">
        <hh:leftBorder type="SOLID" width="0.12 mm" color="#000000" />
        <hh:rightBorder type="SOLID" width="0.12 mm" color="#000000" />
        <hh:topBorder type="SOLID" width="0.12 mm" color="#000000" />
        <hh:bottomBorder type="SOLID" width="0.12 mm" color="#000000" />
        <hc:fillBrush><hc:winBrush faceColor="#FFFFFF" hatchColor="#000000" alpha="0" /></hc:fillBrush>
      </hh:borderFill>
    </hh:borderFills>
  </hh:refList>
</hh:head>
"""
    section = """<?xml version="1.0" encoding="UTF-8"?>
<hp:sec xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">
  <hp:p id="1"><hp:run><hp:t>base</hp:t></hp:run></hp:p>
</hp:sec>
"""
    content = """<?xml version="1.0" encoding="UTF-8"?>
<opf:package xmlns:opf="http://www.idpf.org/2007/opf">
  <opf:metadata />
  <opf:manifest>
    <opf:item id="header" href="Contents/header.xml" media-type="application/xml"/>
    <opf:item id="section0" href="Contents/section0.xml" media-type="application/xml"/>
  </opf:manifest>
  <opf:spine>
    <opf:itemref idref="header"/>
    <opf:itemref idref="section0"/>
  </opf:spine>
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
        zf.writestr("Preview/PrvText.txt", "base")


def test_diagram_tables_include_required_modes() -> None:
    tables = diagram_tables(DEFAULT_SCHEDULE_ITEMS, DEFAULT_SCHEDULE_ITEMS[0].start, 31, 3)

    assert [table["mode"] for table in tables] == ["monthly", "daily", "horizontal", "vertical", "summary", "legend"]
    assert tables[0]["rows"][0][:2] == ["공종", "기간"]
    assert "수평 막대" in tables[2]["rows"][0]
    generated_text = "\n".join(str(cell) for table in tables for row in table["rows"] for cell in row)
    assert "■" not in generated_text


def test_schedule_diagram_suite_inserts_six_tables(tmp_path: Path) -> None:
    input_path = tmp_path / "input.hwpx"
    output_path = tmp_path / "output.hwpx"
    write_minimal_hwpx(input_path)

    report = run_schedule_diagram_suite(input_path, output_path)
    package = HwpxPackage(output_path)
    tables = find_tables(package)

    assert report["status"] == "PASS"
    assert report["before_table_count"] == 0
    assert report["after_table_count"] == 6
    assert len(tables) == 6
    assert report["insert_result"]["diagram_count"] == 6
