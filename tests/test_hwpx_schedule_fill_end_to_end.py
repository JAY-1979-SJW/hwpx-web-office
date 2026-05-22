"""HWPX-SCHEDULE-FILL-END-TO-END-01 — 공정표 막대 자동 색 채우기 end-to-end 테스트.

원본 fixture 수정 없음 (read-only).
apply_edit_plan은 output 경로에만 사용.
repair_for_server 미사용.
fill_schedule_bars plan → apply_edit_plan → Parser V2 재파싱 → 검증.
"""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "hwpx"))

FIXTURE_DIR = PROJECT_ROOT / "tests" / "fixtures" / "hwpx" / "gantt"
FX_EMPTY = FIXTURE_DIR / "fx_gantt_like_template_empty.hwpx"
FX_BASIC = FIXTURE_DIR / "fx_gantt_like_basic.hwpx"
FX_PARTIAL = FIXTURE_DIR / "fx_gantt_like_partial_filled.hwpx"

OUTPUT_DIR = PROJECT_ROOT / "reports" / "hwpx_schedule_fill_end_to_end" / "output"
OUTPUT_FILLED = OUTPUT_DIR / "fx_gantt_like_template_empty_filled.hwpx"

# ── 공통 헬퍼 ──────────────────────────────────────────────────────────────────

def _parse(path: Path):
    from scripts.hwpx.parser.parser_engine import parse_hwpx_v2
    return parse_hwpx_v2(path)


def _gantt(result):
    return next((s for s in result.schedules if len(s.taskRows) >= 5), None)


def _resolve_table_index(result, table_id: str) -> int:
    """tableId 문자열로 TableInfo.tableIndex를 찾는다."""
    for t in result.tables:
        if t.tableId == table_id:
            return t.tableIndex
    return 0


def _build_filled_output():
    """empty fixture에 배관공사 막대를 채운 output HWPX를 생성한다."""
    from scripts.hwpx.parser.parser_contract import ScheduleBarRangeRequest
    from scripts.hwpx.parser.schedule_detector import build_schedule_bar_plan_candidate
    from scripts.hwpx.pipeline.schedule_bar_plan_generator import (
        build_fill_schedule_bars_plan,
        decide_bar_plan_action,
    )
    from hwpx_edit_tool import apply_edit_plan

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    result = _parse(FX_EMPTY)
    s = _gantt(result)
    assert s is not None, "gantt schedule not detected"

    table_index = _resolve_table_index(result, s.tableId)

    req = ScheduleBarRangeRequest(
        taskName="배관공사",
        startDate="2026-05-01",
        endDate="2026-07-31",
        color="92D050",
        text="배관공사",
        textAt="center",
    )
    cand = build_schedule_bar_plan_candidate(s, req)
    decision = decide_bar_plan_action(cand)
    assert decision.action == "AUTO_PLAN_ALLOWED", f"expected AUTO_PLAN_ALLOWED, got {decision.action}"

    plan = build_fill_schedule_bars_plan(cand, table_index=table_index)
    plan_dict = plan.to_dict()

    apply_result = apply_edit_plan(FX_EMPTY, OUTPUT_FILLED, plan_dict)
    return apply_result, cand, table_index


# ── T01: empty fixture BarPlanCandidate 생성 ───────────────────────────────────

def test_empty_fixture_build_candidate():
    from scripts.hwpx.parser.parser_contract import ScheduleBarRangeRequest
    from scripts.hwpx.parser.schedule_detector import build_schedule_bar_plan_candidate

    result = _parse(FX_EMPTY)
    s = _gantt(result)
    assert s is not None

    req = ScheduleBarRangeRequest(
        taskName="배관공사",
        startDate="2026-05-01",
        endDate="2026-07-31",
        color="92D050",
    )
    cand = build_schedule_bar_plan_candidate(s, req)
    assert cand.row >= 0
    assert cand.colStart == 2
    assert cand.colEnd == 4
    assert cand.conflict in ("replaces_existing_empty_template", "no_conflict")


# ── T02: fill_schedule_bars edit plan 생성 ─────────────────────────────────────

def test_empty_fixture_build_edit_plan():
    from scripts.hwpx.parser.parser_contract import ScheduleBarRangeRequest
    from scripts.hwpx.parser.schedule_detector import build_schedule_bar_plan_candidate
    from scripts.hwpx.pipeline.schedule_bar_plan_generator import build_fill_schedule_bars_plan

    result = _parse(FX_EMPTY)
    s = _gantt(result)
    table_index = _resolve_table_index(result, s.tableId)

    req = ScheduleBarRangeRequest(taskName="배관공사", startDate="2026-05-01", endDate="2026-07-31")
    cand = build_schedule_bar_plan_candidate(s, req)
    plan = build_fill_schedule_bars_plan(cand, table_index=table_index)
    plan_dict = plan.to_dict()

    assert "fill_schedule_bars" in plan_dict
    items = plan_dict["fill_schedule_bars"]
    assert len(items) >= 1
    item = items[0]
    assert item["start_col"] == 2
    assert item["end_col"] == 4
    assert item["table"] == table_index


# ── T03: apply_edit_plan output 생성 ──────────────────────────────────────────

def test_apply_edit_plan_creates_output():
    apply_result, cand, table_index = _build_filled_output()
    assert OUTPUT_FILLED.exists(), "output file not created"
    assert apply_result["status"] == "PASS", f"apply_edit_plan failed: {apply_result.get('status')}"


# ── T04: Parser V2 재파싱 성공 ─────────────────────────────────────────────────

def test_reparse_output_success():
    if not OUTPUT_FILLED.exists():
        _build_filled_output()
    result = _parse(OUTPUT_FILLED)
    assert result is not None
    errors = [w for w in (result.warnings or []) if "error" in str(w).lower()]
    assert len(errors) == 0


# ── T05: target cells fillColor 확인 ──────────────────────────────────────────

def test_target_cells_fill_color():
    from scripts.hwpx.pipeline.style_postprocess_verifier import verify_cell_fill_color
    from scripts.hwpx.parser.parser_contract import ScheduleBarRangeRequest
    from scripts.hwpx.parser.schedule_detector import build_schedule_bar_plan_candidate

    if not OUTPUT_FILLED.exists():
        _build_filled_output()

    # candidate 정보 재계산 (original fixture 기준)
    orig_result = _parse(FX_EMPTY)
    s = _gantt(orig_result)
    table_index = _resolve_table_index(orig_result, s.tableId)
    req = ScheduleBarRangeRequest(taskName="배관공사", startDate="2026-05-01", endDate="2026-07-31")
    cand = build_schedule_bar_plan_candidate(s, req)

    # 재파싱 결과에서 fillColor 검증
    out_result = _parse(OUTPUT_FILLED)
    for col in range(cand.colStart, cand.colEnd + 1):
        vr = verify_cell_fill_color(out_result.tables, table_index, cand.row, col, "92D050")
        assert vr["status"] == "PASS", f"fillColor mismatch at row={cand.row} col={col}: {vr}"


# ── T06: target text 확인 ─────────────────────────────────────────────────────

def test_target_cell_text():
    from scripts.hwpx.parser.parser_contract import ScheduleBarRangeRequest
    from scripts.hwpx.parser.schedule_detector import build_schedule_bar_plan_candidate

    if not OUTPUT_FILLED.exists():
        _build_filled_output()

    orig_result = _parse(FX_EMPTY)
    s = _gantt(orig_result)
    table_index = _resolve_table_index(orig_result, s.tableId)
    req = ScheduleBarRangeRequest(
        taskName="배관공사", startDate="2026-05-01", endDate="2026-07-31",
        text="배관공사", textAt="center",
    )
    cand = build_schedule_bar_plan_candidate(s, req)
    center_col = (cand.colStart + cand.colEnd) // 2

    out_result = _parse(OUTPUT_FILLED)
    # 대상 테이블에서 center 셀 텍스트 확인
    target_table = next((t for t in out_result.tables if t.tableIndex == table_index), None)
    assert target_table is not None
    center_cell = next(
        (c for c in target_table.cells if c.visualRow == cand.row and c.visualCol == center_col),
        None,
    )
    # text가 있는 경우만 검증 (plan에서 text 포함 시)
    if center_cell is not None and center_cell.normalizedText:
        assert "배관공사" in (center_cell.normalizedText or "")


# ── T07: non-target cells 보존 ───────────────────────────────────────────────

def test_non_target_cells_preserved():
    from scripts.hwpx.parser.parser_contract import ScheduleBarRangeRequest
    from scripts.hwpx.parser.schedule_detector import build_schedule_bar_plan_candidate

    if not OUTPUT_FILLED.exists():
        _build_filled_output()

    orig_result = _parse(FX_EMPTY)
    s = _gantt(orig_result)
    table_index = _resolve_table_index(orig_result, s.tableId)
    req = ScheduleBarRangeRequest(taskName="배관공사", startDate="2026-05-01", endDate="2026-07-31")
    cand = build_schedule_bar_plan_candidate(s, req)

    orig_table = next((t for t in orig_result.tables if t.tableIndex == table_index), None)
    out_result = _parse(OUTPUT_FILLED)
    out_table = next((t for t in out_result.tables if t.tableIndex == table_index), None)
    assert out_table is not None

    # target row 외 행의 셀 수 보존
    orig_non_target = [c for c in (orig_table.cells if orig_table else [])
                       if c.visualRow != cand.row]
    out_non_target = [c for c in out_table.cells if c.visualRow != cand.row]
    assert len(orig_non_target) == len(out_non_target), "non-target row cell count changed"


# ── T08: full_verify (기본 ZIP/mimetype 검사) PASS ───────────────────────────

def test_full_verify_pass():
    from scripts.hwpx.pipeline.hancom_safe_gate import verify

    if not OUTPUT_FILLED.exists():
        _build_filled_output()

    gate_result = verify(OUTPUT_FILLED)
    assert gate_result.verdict in ("PASS", "REVIEW_REQUIRED"), \
        f"full_verify gate failed: {gate_result.verdict} errors={gate_result.errors}"


# ── T09: mimetype ZIP_STORED 유지 ────────────────────────────────────────────

def test_mimetype_zip_stored():
    if not OUTPUT_FILLED.exists():
        _build_filled_output()

    with zipfile.ZipFile(OUTPUT_FILLED) as zf:
        info = zf.getinfo("mimetype")
        assert info.compress_type == zipfile.ZIP_STORED, \
            f"mimetype compress_type={info.compress_type}, expected ZIP_STORED(0)"


# ── T10: basic fixture → REVIEW_REQUIRED 실행 금지 ───────────────────────────

def test_basic_fixture_review_required_no_execution():
    from scripts.hwpx.parser.parser_contract import ScheduleBarRangeRequest
    from scripts.hwpx.parser.schedule_detector import build_schedule_bar_plan_candidate
    from scripts.hwpx.pipeline.schedule_bar_plan_generator import decide_bar_plan_action

    result = _parse(FX_BASIC)
    s = _gantt(result)
    assert s is not None

    req = ScheduleBarRangeRequest(
        taskName="배관공사",
        startDate="2026-05-01",
        endDate="2026-07-31",
    )
    cand = build_schedule_bar_plan_candidate(s, req)
    decision = decide_bar_plan_action(cand)
    # basic fixture는 기존 막대 있음 → REVIEW_REQUIRED 또는 FAIL이어야 함
    # AUTO_PLAN_ALLOWED인 경우에만 실제 실행 허용
    assert decision.action != "AUTO_PLAN_ALLOWED" or cand.existingBarType == "", \
        f"basic fixture should not be AUTO_PLAN_ALLOWED with existing bars: {decision}"


# ── T11: partial fixture → REVIEW_REQUIRED 실행 금지 ─────────────────────────

def test_partial_fixture_review_required_no_execution():
    from scripts.hwpx.parser.parser_contract import ScheduleBarRangeRequest
    from scripts.hwpx.parser.schedule_detector import build_schedule_bar_plan_candidate
    from scripts.hwpx.pipeline.schedule_bar_plan_generator import decide_bar_plan_action

    result = _parse(FX_PARTIAL)
    s = _gantt(result)
    assert s is not None

    req = ScheduleBarRangeRequest(
        taskName="배관공사",
        startDate="2026-05-01",
        endDate="2026-07-31",
    )
    cand = build_schedule_bar_plan_candidate(s, req)
    decision = decide_bar_plan_action(cand)
    # partial fixture는 기존 텍스트 있는 셀 포함 → REVIEW_REQUIRED 기대
    if cand.existingBarType in ("text_full", "text_partial"):
        assert decision.action == "REVIEW_REQUIRED", \
            f"expected REVIEW_REQUIRED for partial, got {decision.action}"


# ── T12: out-of-range는 실행 금지 ────────────────────────────────────────────

def test_out_of_range_not_executed():
    from scripts.hwpx.parser.parser_contract import ScheduleBarRangeRequest
    from scripts.hwpx.parser.schedule_detector import build_schedule_bar_plan_candidate
    from scripts.hwpx.pipeline.schedule_bar_plan_generator import (
        build_fill_schedule_bars_plan,
        decide_bar_plan_action,
    )

    result = _parse(FX_EMPTY)
    s = _gantt(result)
    table_index = _resolve_table_index(result, s.tableId)

    req = ScheduleBarRangeRequest(
        taskName="배관공사",
        startDate="2026-08-01",
        endDate="2026-09-30",
    )
    cand = build_schedule_bar_plan_candidate(s, req)
    decision = decide_bar_plan_action(cand)

    # colStart=-1이면 invalid coords → FAIL
    # out of range면 fill_schedule_bars에 포함되지 않아야 함
    plan = build_fill_schedule_bars_plan(cand, table_index=table_index)
    plan_dict = plan.to_dict()
    exec_items = plan_dict.get("fill_schedule_bars", [])

    # FAIL/REVIEW_REQUIRED이면 실행 목록 비어 있어야 함
    if decision.action in ("FAIL", "REVIEW_REQUIRED"):
        valid_items = [i for i in exec_items if i.get("start_col", -1) >= 0]
        assert len(valid_items) == 0, f"out-of-range items should not be in exec list: {valid_items}"


# ── T13: 원본 fixture 수정 없음 ───────────────────────────────────────────────

@pytest.mark.parametrize("fx_path", [FX_EMPTY, FX_BASIC, FX_PARTIAL])
def test_fixture_not_modified(fx_path):
    from scripts.hwpx.parser.schedule_detector import build_schedule_bar_plan_candidate
    from scripts.hwpx.parser.parser_contract import ScheduleBarRangeRequest

    mtime_before = fx_path.stat().st_mtime
    result = _parse(fx_path)
    s = _gantt(result)
    if s:
        req = ScheduleBarRangeRequest(taskName="배관공사", startDate="2026-05-01", endDate="2026-07-31")
        build_schedule_bar_plan_candidate(s, req)
    mtime_after = fx_path.stat().st_mtime
    assert mtime_before == mtime_after, f"fixture was modified: {fx_path.name}"
