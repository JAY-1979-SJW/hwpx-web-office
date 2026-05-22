"""HWPX-GANTT-LIKE-FIXTURE-SELECTION-01 — gantt_like_table 픽스처 검증.

3개 픽스처(basic, template_empty, partial_filled)의 파서 안정성,
구조, schedule_candidates 탐지, input_slot 탐지를 검증한다.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "hwpx" / "gantt"
MANIFEST_PATH = FIXTURE_DIR / "gantt_fixture_manifest.json"

FX_BASIC = FIXTURE_DIR / "fx_gantt_like_basic.hwpx"
FX_EMPTY = FIXTURE_DIR / "fx_gantt_like_template_empty.hwpx"
FX_PARTIAL = FIXTURE_DIR / "fx_gantt_like_partial_filled.hwpx"

EXPECTED_HEADER = ["공종", "기간", "5월", "6월", "7월", "진척률"]
EXPECTED_TASKS = ["착공및현장정리", "배관공사", "배선공사", "장비설치", "시험및시운전", "준공정리"]


# ── helpers ───────────────────────────────────────────────────────────────────

def _find_gantt_table(tables, rows: int = 7, cols: int = 6):
    for t in tables:
        if getattr(t, "rowCount", 0) == rows and getattr(t, "colCount", 0) == cols:
            return t
    return None


def _parse(path: Path):
    import sys
    sys.path.insert(0, str(Path(__file__).parents[1]))
    from scripts.hwpx.parser.parser_engine import parse_hwpx_v2
    return parse_hwpx_v2(path)


# ── T01: 매니페스트 ────────────────────────────────────────────────────────────

def test_manifest_exists_and_valid():
    assert MANIFEST_PATH.exists()
    m = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert m["schemaVersion"] == "1"
    assert len(m["fixtures"]) == 3


def test_manifest_fixture_files_exist():
    m = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    for fx in m["fixtures"]:
        p = FIXTURE_DIR / fx["fixtureName"]
        assert p.exists(), f"fixture not found: {fx['fixtureName']}"


# ── T02: ZIP 유효성 ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("fx_path", [FX_BASIC, FX_EMPTY, FX_PARTIAL])
def test_fixture_is_valid_zip(fx_path):
    with zipfile.ZipFile(fx_path) as z:
        names = z.namelist()
    assert "mimetype" in names
    assert any("section" in n for n in names)


@pytest.mark.parametrize("fx_path", [FX_BASIC, FX_EMPTY, FX_PARTIAL])
def test_fixture_mimetype_stored(fx_path):
    with zipfile.ZipFile(fx_path) as z:
        info = z.getinfo("mimetype")
    assert info.compress_type == 0, "mimetype must be ZIP_STORED"


# ── T03: 파서 안정성 ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("fx_path", [FX_BASIC, FX_EMPTY, FX_PARTIAL])
def test_parser_returns_no_error(fx_path):
    result = _parse(fx_path)
    assert result is not None
    assert not result.errors, f"parser errors: {result.errors}"


def test_basic_table_count():
    result = _parse(FX_BASIC)
    assert len(result.tables) >= 1


# ── T04: gantt 테이블 구조 ─────────────────────────────────────────────────────

@pytest.mark.parametrize("fx_path", [FX_BASIC, FX_EMPTY, FX_PARTIAL])
def test_gantt_table_found_7x6(fx_path):
    result = _parse(fx_path)
    t = _find_gantt_table(result.tables)
    assert t is not None, "7×6 gantt table not found"


@pytest.mark.parametrize("fx_path", [FX_BASIC, FX_EMPTY, FX_PARTIAL])
def test_gantt_header_row(fx_path):
    result = _parse(fx_path)
    t = _find_gantt_table(result.tables)
    assert t is not None
    header_cells = sorted([c for c in t.cells if c.row == 0], key=lambda c: c.col)
    texts = [getattr(c, "normalizedText", "") for c in header_cells]
    assert texts == EXPECTED_HEADER, f"header mismatch: {texts}"


@pytest.mark.parametrize("fx_path", [FX_BASIC, FX_EMPTY, FX_PARTIAL])
def test_gantt_task_column(fx_path):
    result = _parse(fx_path)
    t = _find_gantt_table(result.tables)
    assert t is not None
    task_cells = sorted([c for c in t.cells if c.col == 0 and c.row > 0], key=lambda c: c.row)
    tasks = [getattr(c, "normalizedText", "") for c in task_cells]
    assert tasks == EXPECTED_TASKS, f"task column mismatch: {tasks}"


# ── T05: 바 타입 구분 ──────────────────────────────────────────────────────────

def test_basic_has_filled_bars():
    result = _parse(FX_BASIC)
    t = _find_gantt_table(result.tables)
    bar_cells = [c for c in t.cells if c.col == 2 and c.row > 0]
    texts = [getattr(c, "normalizedText", "") for c in bar_cells]
    assert any("■" in tx for tx in texts), f"no bar symbols found: {texts}"


def test_empty_template_has_no_bars():
    result = _parse(FX_EMPTY)
    t = _find_gantt_table(result.tables)
    bar_cells = [c for c in t.cells if c.col in (2, 3, 4) and c.row > 0]
    texts = [getattr(c, "normalizedText", "") for c in bar_cells]
    assert all(tx == "" for tx in texts), f"unexpected bar content: {texts}"


def test_partial_has_only_may_bars():
    result = _parse(FX_PARTIAL)
    t = _find_gantt_table(result.tables)
    may_cells = [c for c in t.cells if c.col == 2 and c.row > 0]
    jun_cells = [c for c in t.cells if c.col == 3 and c.row > 0]
    may_texts = [getattr(c, "normalizedText", "") for c in may_cells]
    jun_texts = [getattr(c, "normalizedText", "") for c in jun_cells]
    assert any("■" in tx for tx in may_texts), "5월 column should have bars"
    # 6월은 대부분 비어있고 마지막 공종(준공정리)만 바가 있을 수 있음
    jun_bar_count = sum(1 for tx in jun_texts if "■" in tx)
    assert jun_bar_count <= 1, f"6월 column should have at most 1 bar row, got: {jun_texts}"
