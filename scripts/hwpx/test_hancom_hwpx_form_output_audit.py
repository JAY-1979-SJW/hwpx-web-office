from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from hancom_hwpx_form_output_audit import audit_hwpx_form_output


def write_hwpx(path: Path, text_nodes: str = "<hp:t>value</hp:t>", vert_align: str = "CENTER") -> None:
    section = f"""<?xml version="1.0" encoding="UTF-8"?>
<hp:sec xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">
  <hp:tbl>
    <hp:tr>
      <hp:tc>
        <hp:subList lineWrap="BREAK" vertAlign="{vert_align}" />
        <hp:p><hp:run charPrIDRef="1">{text_nodes}</hp:run></hp:p>
        <hp:cellAddr rowAddr="0" colAddr="0" />
        <hp:cellSpan rowSpan="1" colSpan="1" />
        <hp:cellSz width="8000" height="1000" />
        <hp:cellMargin left="100" right="100" top="0" bottom="0" />
      </hp:tc>
    </hp:tr>
  </hp:tbl>
</hp:sec>
"""
    header = """<?xml version="1.0" encoding="UTF-8"?>
<hh:head xmlns:hh="http://www.hancom.co.kr/hwpml/2011/head">
  <hh:refList><hh:charProperties itemCnt="1"><hh:charPr id="1" height="1000" /></hh:charProperties></hh:refList>
</hh:head>
"""
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", "application/hwp+zip")
        zf.writestr("Contents/header.xml", header)
        zf.writestr("Contents/section0.xml", section)


def write_report(path: Path, field: str = "value") -> None:
    path.write_text(
        json.dumps(
            {
                "updates": [
                    {
                        "status": "PASS",
                        "table_index": 0,
                        "visual_row": 0,
                        "visual_col": 0,
                        "label": "field",
                        "field": field,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


def test_output_audit_passes_exact_single_node_value(tmp_path: Path) -> None:
    hwpx = tmp_path / "ok.hwpx"
    report = tmp_path / "report.json"
    write_hwpx(hwpx)
    write_report(report)

    audit = audit_hwpx_form_output(hwpx, report)

    assert audit["status"] == "PASS"
    assert audit["failed_update_count"] == 0


def test_output_audit_fails_when_cell_has_multiple_non_empty_text_nodes(tmp_path: Path) -> None:
    hwpx = tmp_path / "overlap-risk.hwpx"
    report = tmp_path / "report.json"
    write_hwpx(hwpx, "<hp:t>val</hp:t><hp:t>ue</hp:t>")
    write_report(report)

    audit = audit_hwpx_form_output(hwpx, report)

    assert audit["status"] == "FAIL"
    assert audit["problem_counts"]["MULTIPLE_NON_EMPTY_TEXT_NODES"] == 1


def test_output_audit_fails_when_input_cell_is_top_aligned(tmp_path: Path) -> None:
    hwpx = tmp_path / "top-align.hwpx"
    report = tmp_path / "report.json"
    write_hwpx(hwpx, vert_align="TOP")
    write_report(report)

    audit = audit_hwpx_form_output(hwpx, report)

    assert audit["status"] == "FAIL"
    assert audit["problem_counts"]["VERTICAL_ALIGN_NOT_CENTER"] == 1
