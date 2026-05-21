from __future__ import annotations

import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from hancom_hwpx_table_integrity_audit import audit_tables


def write_table(path: Path, text: str = "값") -> None:
    section = f"""<?xml version="1.0" encoding="UTF-8"?>
<hp:sec xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">
  <hp:tbl>
    <hp:tr>
      <hp:tc>
        <hp:subList lineWrap="BREAK" vertAlign="CENTER" />
        <hp:p><hp:run><hp:t>{text}</hp:t></hp:run></hp:p>
        <hp:cellAddr rowAddr="0" colAddr="0" />
        <hp:cellSpan rowSpan="1" colSpan="1" />
        <hp:cellSz width="8000" height="2000" />
        <hp:cellMargin left="100" right="100" top="100" bottom="100" />
      </hp:tc>
    </hp:tr>
  </hp:tbl>
</hp:sec>
"""
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", "application/hwp+zip")
        zf.writestr("Contents/section0.xml", section)


def test_table_integrity_audit_passes_valid_special_char_text(tmp_path: Path) -> None:
    path = tmp_path / "special.hwpx"
    write_table(path, "1,000㎡ ※ ①")

    report = audit_tables(path)

    assert report["status"] == "PASS"
    assert report["problem_count"] == 0


def test_table_integrity_audit_detects_multiple_non_empty_text_nodes(tmp_path: Path) -> None:
    path = tmp_path / "multi-node.hwpx"
    write_table(path, "A</hp:t><hp:t>B")

    report = audit_tables(path)

    assert report["status"] == "WARN"
    assert report["warning_counts"]["MULTIPLE_NON_EMPTY_TEXT_NODES"] == 1
