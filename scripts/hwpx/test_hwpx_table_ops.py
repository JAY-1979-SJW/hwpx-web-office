from __future__ import annotations

import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from hwpx_package import HwpxPackage
from hwpx_table_ops import (
    delete_table_row,
    find_cell_text_style_reference,
    get_table_cell_matrix,
    set_table_cell_text,
    set_table_visual_cell_text,
    set_table_visual_cell_vertical_align,
    shrink_table_visual_cell_text_to_fit,
    table_elements,
)


def test_set_table_cell_text_reports_original_run_style_reference(tmp_path: Path) -> None:
    path = tmp_path / "styled.hwpx"
    section = """<?xml version="1.0" encoding="UTF-8"?>
<hp:sec xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">
  <hp:tbl>
    <hp:tr>
      <hp:tc>
        <hp:p paraPrIDRef="7" styleIDRef="3">
          <hp:run charPrIDRef="42"><hp:t>original</hp:t></hp:run>
        </hp:p>
      </hp:tc>
    </hp:tr>
  </hp:tbl>
</hp:sec>
"""
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", "application/hwp+zip")
        zf.writestr("Contents/section0.xml", section)
    package = HwpxPackage(path)

    result = set_table_cell_text(package, 0, 0, 0, "changed")

    assert result["status"] == "PASS"
    assert result["style_reference"]["source"] == "first_non_empty_text_node"
    assert result["style_reference"]["charPrIDRef"] == "42"
    assert result["style_reference"]["paraPrIDRef"] == "7"
    assert result["style_reference"]["styleIDRef"] == "3"


def test_empty_cell_text_node_uses_existing_run_style_as_reference(tmp_path: Path) -> None:
    path = tmp_path / "empty-styled.hwpx"
    section = """<?xml version="1.0" encoding="UTF-8"?>
<hp:sec xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">
  <hp:tbl>
    <hp:tr>
      <hp:tc>
        <hp:p paraPrIDRef="8" styleIDRef="4">
          <hp:run charPrIDRef="77"><hp:linesegarray /></hp:run>
        </hp:p>
      </hp:tc>
    </hp:tr>
  </hp:tbl>
</hp:sec>
"""
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", "application/hwp+zip")
        zf.writestr("Contents/section0.xml", section)
    package = HwpxPackage(path)
    _entry, _root, table = table_elements(package)[0]
    cell = list(list(table)[0])[0]

    before = find_cell_text_style_reference(cell)
    result = set_table_cell_text(package, 0, 0, 0, "created")

    assert before["source"] == "existing_run_without_text_node"
    assert before["charPrIDRef"] == "77"
    assert result["status"] == "PASS"
    assert result["style_reference"]["source"] == "created_text_node_in_original_run"
    assert result["style_reference"]["charPrIDRef"] == "77"


def test_shrink_table_visual_cell_text_to_fit_clones_char_style(tmp_path: Path) -> None:
    path = tmp_path / "shrink.hwpx"
    header = """<?xml version="1.0" encoding="UTF-8"?>
<hh:head xmlns:hh="http://www.hancom.co.kr/hwpml/2011/head">
  <hh:refList>
    <hh:charProperties itemCnt="1">
      <hh:charPr id="5" height="1000" textColor="#000000" shadeColor="none" />
    </hh:charProperties>
  </hh:refList>
</hh:head>
"""
    section = """<?xml version="1.0" encoding="UTF-8"?>
<hp:sec xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">
  <hp:tbl>
    <hp:tr>
      <hp:tc>
        <hp:subList lineWrap="BREAK" />
        <hp:p paraPrIDRef="1" styleIDRef="0">
          <hp:run charPrIDRef="5"><hp:t>5.10</hp:t></hp:run>
        </hp:p>
        <hp:cellAddr rowAddr="0" colAddr="0" />
        <hp:cellSpan rowSpan="1" colSpan="1" />
        <hp:cellSz width="3473" height="2000" />
        <hp:cellMargin left="141" right="141" top="141" bottom="141" />
      </hp:tc>
    </hp:tr>
  </hp:tbl>
</hp:sec>
"""
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", "application/hwp+zip")
        zf.writestr("Contents/header.xml", header)
        zf.writestr("Contents/section0.xml", section)
    package = HwpxPackage(path)

    result = shrink_table_visual_cell_text_to_fit(package, 0, 0, 0, "5.10")

    assert result["status"] == "FONT_SHRINK_PASS"
    assert result["source_charPrIDRef"] == "5"
    assert result["target_height"] < result["original_height"]
    assert result["after_fit"]["status"] == "PASS"


def test_set_table_visual_cell_vertical_align_updates_sublist(tmp_path: Path) -> None:
    path = tmp_path / "vertical-align.hwpx"
    section = """<?xml version="1.0" encoding="UTF-8"?>
<hp:sec xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">
  <hp:tbl>
    <hp:tr>
      <hp:tc>
        <hp:subList lineWrap="BREAK" vertAlign="TOP" />
        <hp:p><hp:run><hp:t>value</hp:t></hp:run></hp:p>
        <hp:cellAddr rowAddr="0" colAddr="0" />
        <hp:cellSpan rowSpan="1" colSpan="1" />
      </hp:tc>
    </hp:tr>
  </hp:tbl>
</hp:sec>
"""
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", "application/hwp+zip")
        zf.writestr("Contents/section0.xml", section)
    package = HwpxPackage(path)

    result = set_table_visual_cell_vertical_align(package, 0, 0, 0, "CENTER")
    matrix = get_table_cell_matrix(package, 0)

    assert result["status"] == "VERTICAL_ALIGN_PASS"
    assert result["before"] == "TOP"
    table_cell = matrix["rows"][0]["cells"][0]
    assert table_cell["sublist"]["vertAlign"] == "CENTER"


def write_minimal_hwpx(path: Path) -> None:
    section = """<?xml version="1.0" encoding="UTF-8"?>
<hp:sec xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">
  <hp:tbl>
    <hp:tr>
      <hp:tc><hp:p><hp:run><hp:t>label</hp:t></hp:run></hp:p></hp:tc>
      <hp:tc><hp:p><hp:run><hp:t>value</hp:t></hp:run></hp:p></hp:tc>
      <hp:tc><hp:p><hp:run><hp:t>제 </hp:t><hp:t>호</hp:t></hp:run></hp:p></hp:tc>
    </hp:tr>
    <hp:tr>
      <hp:tc><hp:p><hp:run><hp:t>next-label</hp:t></hp:run></hp:p><hp:cellAddr rowAddr="3" colAddr="2" /><hp:cellSpan rowSpan="1" colSpan="2" /></hp:tc>
      <hp:tc><hp:p><hp:run><hp:t>next-value</hp:t></hp:run></hp:p><hp:cellAddr rowAddr="3" colAddr="4" /><hp:cellSpan rowSpan="1" colSpan="1" /></hp:tc>
      <hp:tc><hp:p><hp:run><hp:linesegarray /></hp:run></hp:p><hp:cellAddr rowAddr="3" colAddr="5" /><hp:cellSpan rowSpan="1" colSpan="1" /></hp:tc>
    </hp:tr>
  </hp:tbl>
</hp:sec>
"""
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", "application/hwp+zip")
        zf.writestr("Contents/section0.xml", section)


def test_get_table_cell_matrix_uses_row_col_coordinates(tmp_path: Path) -> None:
    path = tmp_path / "sample.hwpx"
    write_minimal_hwpx(path)
    package = HwpxPackage(path)

    matrix = get_table_cell_matrix(package, 0)

    assert matrix["status"] == "PASS"
    assert matrix["rows"][0]["cells"][0]["text"] == "label"
    assert matrix["rows"][0]["cells"][1]["text"] == "value"
    assert matrix["rows"][1]["cells"][0]["text"] == "next-label"
    assert matrix["rows"][1]["cells"][0]["visual_row"] == 3
    assert matrix["rows"][1]["cells"][0]["visual_col"] == 2
    assert matrix["rows"][1]["cells"][0]["colspan"] == 2


def test_set_table_cell_text_updates_exact_cell_not_flat_text_index(tmp_path: Path) -> None:
    path = tmp_path / "sample.hwpx"
    output = tmp_path / "updated.hwpx"
    write_minimal_hwpx(path)
    package = HwpxPackage(path)

    result = set_table_cell_text(package, 0, 1, 0, "changed")
    package.write_package(output)
    updated = HwpxPackage(output)
    matrix = get_table_cell_matrix(updated, 0)

    assert result["status"] == "PASS"
    assert matrix["rows"][0]["cells"][0]["text"] == "label"
    assert matrix["rows"][0]["cells"][1]["text"] == "value"
    assert matrix["rows"][1]["cells"][0]["text"] == "changed"
    assert matrix["rows"][1]["cells"][1]["text"] == "next-value"


def test_set_table_cell_text_creates_text_node_in_empty_cell(tmp_path: Path) -> None:
    path = tmp_path / "sample.hwpx"
    output = tmp_path / "updated.hwpx"
    write_minimal_hwpx(path)
    package = HwpxPackage(path)

    result = set_table_cell_text(package, 0, 1, 2, "created")
    package.write_package(output)
    updated = HwpxPackage(output)
    matrix = get_table_cell_matrix(updated, 0)

    assert result["status"] == "PASS"
    assert matrix["rows"][1]["cells"][2]["text"] == "created"


def test_set_table_visual_cell_text_updates_celladdr_coordinates(tmp_path: Path) -> None:
    path = tmp_path / "sample.hwpx"
    output = tmp_path / "updated.hwpx"
    write_minimal_hwpx(path)
    package = HwpxPackage(path)

    result = set_table_visual_cell_text(package, 0, 3, 4, "visual-changed")
    package.write_package(output)
    updated = HwpxPackage(output)
    matrix = get_table_cell_matrix(updated, 0)

    assert result["status"] == "PASS"
    assert result["row_index"] == 1
    assert result["col_index"] == 1
    assert matrix["rows"][1]["cells"][0]["text"] == "next-label"
    assert matrix["rows"][1]["cells"][1]["text"] == "visual-changed"


def test_delete_table_row_renumbers_later_cell_addresses(tmp_path: Path) -> None:
    path = tmp_path / "delete-renumber.hwpx"
    output = tmp_path / "delete-renumber-updated.hwpx"
    section = """<?xml version="1.0" encoding="UTF-8"?>
<hp:sec xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">
  <hp:tbl>
    <hp:tr>
      <hp:tc><hp:p><hp:run><hp:t>header</hp:t></hp:run></hp:p><hp:cellAddr rowAddr="0" colAddr="0" /><hp:cellSpan rowSpan="1" colSpan="1" /></hp:tc>
    </hp:tr>
    <hp:tr>
      <hp:tc><hp:p><hp:run><hp:t>remove</hp:t></hp:run></hp:p><hp:cellAddr rowAddr="1" colAddr="0" /><hp:cellSpan rowSpan="1" colSpan="1" /></hp:tc>
    </hp:tr>
    <hp:tr>
      <hp:tc><hp:p><hp:run><hp:t>keep</hp:t></hp:run></hp:p><hp:cellAddr rowAddr="2" colAddr="0" /><hp:cellSpan rowSpan="1" colSpan="1" /></hp:tc>
    </hp:tr>
  </hp:tbl>
</hp:sec>
"""
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", "application/hwp+zip")
        zf.writestr("Contents/section0.xml", section)
    package = HwpxPackage(path)

    result = delete_table_row(package, 0, 1)
    package.write_package(output)
    updated = HwpxPackage(output)
    matrix = get_table_cell_matrix(updated, 0)

    assert result["status"] == "DELETE_ROW_PASS"
    assert result["renumbered_cells"] == 1
    assert matrix["rows"][1]["cells"][0]["text"] == "keep"
    assert matrix["rows"][1]["cells"][0]["visual_row"] == 1


def test_set_table_cell_text_clears_all_existing_text_nodes(tmp_path: Path) -> None:
    path = tmp_path / "sample.hwpx"
    output = tmp_path / "updated.hwpx"
    write_minimal_hwpx(path)
    package = HwpxPackage(path)

    result = set_table_cell_text(package, 0, 0, 2, "제 12345 호")
    package.write_package(output)
    updated = HwpxPackage(output)
    matrix = get_table_cell_matrix(updated, 0)

    assert result["status"] == "PASS"
    assert result["cleared_text_nodes"] == 1
    assert matrix["rows"][0]["cells"][2]["text"] == "제 12345 호"
    assert "호호" not in matrix["rows"][0]["cells"][2]["text"]
