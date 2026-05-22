"""HWPX-SCHEDULE-AXIS-DETECTOR-01 — 날짜축·작업행·막대구간 탐지 테스트.

원본 fixture 수정 없음 (read-only).
apply_edit_plan / write_package / fill_schedule_bars 호출 없음.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "hwpx" / "gantt"
FX_BASIC = FIXTURE_DIR / "fx_gantt_like_basic.hwpx"
FX_EMPTY = FIXTURE_DIR / "fx_gantt_like_template_empty.hwpx"
FX_PARTIAL = FIXTURE_DIR / "fx_gantt_like_partial_filled.hwpx"


def _parse(path: Path):
    import sys
    sys.path.insert(0, str(Path(__file__).parents[1]))
    from scripts.hwpx.parser.parser_engine import parse_hwpx_v2
    return parse_hwpx_v2(path)


def _gantt_schedule(result):
    """schedules 중 7×6 gantt 테이블에 해당하는 ScheduleInfo 반환."""
    for s in result.schedules:
        if len(s.taskRows) >= 5 and len(s.timeAxis.dateColumns) >= 2:
            return s
    return result.schedules[0] if result.schedules else None


# ── T01: 모듈 import ────────────────────────────────────────────────────────

def test_schedule_detector_importable():
    from scripts.hwpx.parser.schedule_detector import (
        detect_schedule_structure,
        detect_time_axis,
        detect_task_rows,
        detect_bar_ranges,
        detect_progress_column,
        classify_bar_type,
        normalize_axis_label,
        infer_axis_unit,
    )


def test_parser_contract_schedule_info_importable():
    from scripts.hwpx.parser.parser_contract import (
        ScheduleInfo, TimeAxisInfo, DateColumnInfo,
        TaskRowInfo, BarRangeInfo, ProgressColumnInfo,
    )


# ── T02: 매니페스트 로드 ────────────────────────────────────────────────────

def test_manifest_loads():
    manifest_path = FIXTURE_DIR / "gantt_fixture_manifest.json"
    assert manifest_path.exists()
    m = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert len(m["fixtures"]) == 3


# ── T03–T05: fixture별 timeAxis 탐지 ────────────────────────────────────────

@pytest.mark.parametrize("fx_path", [FX_BASIC, FX_EMPTY, FX_PARTIAL])
def test_time_axis_detected(fx_path):
    result = _parse(fx_path)
    s = _gantt_schedule(result)
    assert s is not None, "no schedule detected"
    axis = s.timeAxis
    assert axis.confidence > 0.5, f"low axis confidence: {axis.confidence}"
    assert len(axis.dateColumns) >= 2


@pytest.mark.parametrize("fx_path", [FX_BASIC, FX_EMPTY, FX_PARTIAL])
def test_time_axis_unit_month(fx_path):
    result = _parse(fx_path)
    s = _gantt_schedule(result)
    assert s.timeAxis.unit == "month"


@pytest.mark.parametrize("fx_path", [FX_BASIC, FX_EMPTY, FX_PARTIAL])
def test_time_axis_columns_correct(fx_path):
    result = _parse(fx_path)
    s = _gantt_schedule(result)
    labels = [d.label for d in s.timeAxis.dateColumns]
    assert "5월" in labels
    assert "6월" in labels
    assert "7월" in labels


# ── T06: taskRows 탐지 ──────────────────────────────────────────────────────

@pytest.mark.parametrize("fx_path", [FX_BASIC, FX_EMPTY, FX_PARTIAL])
def test_task_rows_detected(fx_path):
    result = _parse(fx_path)
    s = _gantt_schedule(result)
    assert len(s.taskRows) >= 5, f"expected ≥5 task rows, got {len(s.taskRows)}"


def test_task_row_names_correct():
    result = _parse(FX_BASIC)
    s = _gantt_schedule(result)
    names = [r.taskName for r in s.taskRows]
    assert "착공및현장정리" in names
    assert "배관공사" in names


# ── T07–T09: barRanges 탐지 ─────────────────────────────────────────────────

@pytest.mark.parametrize("fx_path", [FX_BASIC, FX_EMPTY, FX_PARTIAL])
def test_bar_ranges_detected(fx_path):
    result = _parse(fx_path)
    s = _gantt_schedule(result)
    assert len(s.barRanges) >= 1, "no bar ranges detected"


def test_empty_template_bar_type():
    result = _parse(FX_EMPTY)
    s = _gantt_schedule(result)
    types = {b.barType for b in s.barRanges}
    assert "empty_template" in types, f"expected empty_template, got {types}"


def test_basic_text_full_bar_type():
    result = _parse(FX_BASIC)
    s = _gantt_schedule(result)
    types = {b.barType for b in s.barRanges}
    assert "text_full" in types, f"expected text_full, got {types}"


def test_partial_text_partial_bar_type():
    result = _parse(FX_PARTIAL)
    s = _gantt_schedule(result)
    types = {b.barType for b in s.barRanges}
    assert "text_partial" in types, f"expected text_partial, got {types}"


def test_bar_range_col_bounds():
    result = _parse(FX_BASIC)
    s = _gantt_schedule(result)
    date_cols = {d.col for d in s.timeAxis.dateColumns}
    for br in s.barRanges:
        if br.barType == "empty_template":
            continue
        assert br.colStart in date_cols or br.colEnd in date_cols, \
            f"bar range ({br.colStart},{br.colEnd}) outside date columns {date_cols}"


# ── T10: progressColumn 탐지 ────────────────────────────────────────────────

@pytest.mark.parametrize("fx_path", [FX_BASIC, FX_EMPTY, FX_PARTIAL])
def test_progress_column_detected(fx_path):
    result = _parse(fx_path)
    s = _gantt_schedule(result)
    assert s.progressColumn is not None, "progress column not detected"
    assert s.progressColumn.col >= 0
    assert s.progressColumn.confidence > 0.5


# ── T11: parser result에 schedules 포함 ─────────────────────────────────────

def test_parser_result_has_schedules():
    result = _parse(FX_BASIC)
    assert hasattr(result, "schedules")
    assert len(result.schedules) >= 1


# ── T12: JSON 직렬화 ─────────────────────────────────────────────────────────

def test_schedule_json_serializable():
    result = _parse(FX_BASIC)
    s = _gantt_schedule(result)
    assert s is not None
    d = s.to_dict()
    json_str = json.dumps(d, ensure_ascii=False)
    assert '"tableId"' in json_str
    assert '"timeAxis"' in json_str
    assert '"taskRows"' in json_str
    assert '"barRanges"' in json_str


# ── T13: 원본 fixture 수정 없음 ──────────────────────────────────────────────

@pytest.mark.parametrize("fx_path", [FX_BASIC, FX_EMPTY, FX_PARTIAL])
def test_fixture_not_modified(fx_path):
    mtime_before = fx_path.stat().st_mtime
    _parse(fx_path)
    mtime_after = fx_path.stat().st_mtime
    assert mtime_before == mtime_after, f"fixture was modified: {fx_path.name}"
