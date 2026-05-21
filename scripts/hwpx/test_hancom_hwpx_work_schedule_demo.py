from __future__ import annotations

import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from hancom_hwpx_work_schedule_demo import DEFAULT_WORK_ITEMS, append_work_schedule
from hwpx_package import HwpxPackage
from hwpx_table_ops import find_tables


def write_minimal_hwpx(path: Path) -> None:
    section = """<?xml version="1.0" encoding="UTF-8"?>
<hp:sec xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">
  <hp:p id="1"><hp:run><hp:t>base</hp:t></hp:run></hp:p>
</hp:sec>
"""
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", "application/hwp+zip")
        zf.writestr("Contents/section0.xml", section)


def test_append_work_schedule_adds_monthly_and_daily_tables(tmp_path: Path) -> None:
    input_path = tmp_path / "input.hwpx"
    output_path = tmp_path / "output.hwpx"
    write_minimal_hwpx(input_path)

    report = append_work_schedule(
        input_path,
        output_path,
        work_items=DEFAULT_WORK_ITEMS,
        daily_start=DEFAULT_WORK_ITEMS[0].start,
        daily_days=31,
        month_count=3,
        title="공종별 월별/일별 공정표",
    )
    package = HwpxPackage(output_path)
    tables = find_tables(package)

    assert report["status"] == "PASS"
    assert report["before_table_count"] == 0
    assert report["after_table_count"] == 2
    assert len(tables) == 2
    assert report["monthly_table_result"]["row_count"] == len(DEFAULT_WORK_ITEMS) + 1
    assert report["daily_table_result"]["row_count"] == len(DEFAULT_WORK_ITEMS) + 1
    assert report["style_result"]["status"] in {"PASS", "HEADER_NOT_FOUND"}


def test_append_work_schedule_can_write_into_existing_section(tmp_path: Path) -> None:
    input_path = tmp_path / "input-in-place.hwpx"
    output_path = tmp_path / "output-in-place.hwpx"
    write_minimal_hwpx(input_path)

    report = append_work_schedule(
        input_path,
        output_path,
        work_items=DEFAULT_WORK_ITEMS,
        daily_start=DEFAULT_WORK_ITEMS[0].start,
        daily_days=31,
        month_count=3,
        title="공종별 월별/일별 공정표",
        append_to_existing_section=True,
    )
    package = HwpxPackage(output_path)
    sections = package.section_entries()
    tables = find_tables(package)

    assert report["status"] == "PASS"
    assert report["section_result"]["status"] == "EXISTING_SECTION_APPEND"
    assert len(sections) == 1
    assert len(tables) == 2
