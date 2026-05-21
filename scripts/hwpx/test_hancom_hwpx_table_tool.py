from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from hancom_hwpx_table_tool import run_table_tool
from hwpx_package import HwpxPackage
from hwpx_table_ops import get_table_cell_matrix


def write_two_by_two_hwpx(path: Path) -> None:
    section = """<?xml version="1.0" encoding="UTF-8"?>
<hp:sec xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">
  <hp:tbl>
    <hp:tr>
      <hp:tc><hp:subList lineWrap="BREAK" vertAlign="CENTER" /><hp:p><hp:run><hp:t>A</hp:t></hp:run></hp:p><hp:cellAddr rowAddr="0" colAddr="0" /><hp:cellSpan rowSpan="1" colSpan="1" /><hp:cellSz width="4000" height="1000" /><hp:cellMargin left="0" right="0" top="0" bottom="0" /></hp:tc>
      <hp:tc><hp:subList lineWrap="BREAK" vertAlign="CENTER" /><hp:p><hp:run><hp:t>B</hp:t></hp:run></hp:p><hp:cellAddr rowAddr="0" colAddr="1" /><hp:cellSpan rowSpan="1" colSpan="1" /><hp:cellSz width="4000" height="1000" /><hp:cellMargin left="0" right="0" top="0" bottom="0" /></hp:tc>
    </hp:tr>
    <hp:tr>
      <hp:tc><hp:subList lineWrap="BREAK" vertAlign="CENTER" /><hp:p><hp:run><hp:t>C</hp:t></hp:run></hp:p><hp:cellAddr rowAddr="1" colAddr="0" /><hp:cellSpan rowSpan="1" colSpan="1" /><hp:cellSz width="4000" height="1000" /><hp:cellMargin left="0" right="0" top="0" bottom="0" /></hp:tc>
      <hp:tc><hp:subList lineWrap="BREAK" vertAlign="CENTER" /><hp:p><hp:run><hp:t>D</hp:t></hp:run></hp:p><hp:cellAddr rowAddr="1" colAddr="1" /><hp:cellSpan rowSpan="1" colSpan="1" /><hp:cellSz width="4000" height="1000" /><hp:cellMargin left="0" right="0" top="0" bottom="0" /></hp:tc>
    </hp:tr>
  </hp:tbl>
</hp:sec>
"""
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", "application/hwp+zip")
        zf.writestr("Contents/section0.xml", section)


def test_table_tool_applies_special_text_and_layout_ops(tmp_path: Path) -> None:
    input_path = tmp_path / "input.hwpx"
    output_path = tmp_path / "output.hwpx"
    ops_path = tmp_path / "ops.json"
    write_two_by_two_hwpx(input_path)
    ops_path.write_text(
        json.dumps(
            [
                {"op": "set_visual_cell_text", "table_index": 0, "visual_row": 0, "visual_col": 0, "value": "1,000㎡ ※ ① & < > \u0000"},
                {"op": "set_cell_layout", "table_index": 0, "row_index": 0, "col_index": 0, "layout": {"vertical_align": "CENTER", "cell_margin": {"left": 100, "right": 100}}},
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    report = run_table_tool(input_path, output_path, ops_path)
    matrix = get_table_cell_matrix(HwpxPackage(output_path), 0)

    assert report["status"] == "PASS"
    assert report["operations"]["text_sanitize_warnings"][0]["field"] == "value"
    assert matrix["rows"][0]["cells"][0]["text"] == "1,000㎡ ※ ① & < > "
