from __future__ import annotations

import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from hancom_hwpx_special_table_demo import append_special_table_demo
from hwpx_package import HwpxPackage
from hwpx_table_ops import get_table_cell_matrix


def write_base_hwpx(path: Path) -> None:
    section = """<?xml version="1.0" encoding="UTF-8"?>
<hp:sec xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">
  <hp:p id="1" paraPrIDRef="0" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">
    <hp:run charPrIDRef="0"><hp:t>base</hp:t></hp:run>
  </hp:p>
</hp:sec>
"""
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", "application/hwp+zip")
        zf.writestr("Contents/section0.xml", section)


def test_special_table_demo_appends_merged_special_char_table(tmp_path: Path) -> None:
    input_path = tmp_path / "base.hwpx"
    output_path = tmp_path / "demo.hwpx"
    write_base_hwpx(input_path)

    report = append_special_table_demo(input_path, output_path)
    matrix = get_table_cell_matrix(HwpxPackage(output_path), 0)

    assert report["status"] == "PASS"
    assert report["after_sections"]["section_count"] == 2
    assert report["after_table_count"] == 1
    assert matrix["rows"][0]["cells"][0]["colspan"] == 4
    assert "㎡" in matrix["rows"][2]["cells"][1]["text"]
    assert "A & B < C > D" == matrix["rows"][4]["cells"][1]["text"]
