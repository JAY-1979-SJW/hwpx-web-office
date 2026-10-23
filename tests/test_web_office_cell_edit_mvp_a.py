"""WEB-OFFICE-CELL-EDIT-MVP-A-01 계약 테스트.

Python EditCommand 모델 + dry-run plan 게이트 + JS 자체 테스트 결과를
회귀 잠금한다. writer 본 실행 / output HWPX 생성 / apply_edit_plan
호출은 절대 발생하지 않는다.
"""
from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path
import pytest

PR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PR))

from scripts.hwpx.web_office.edit_command_model import (  # noqa: E402
    make_set_cell_text_command, apply_forward, apply_inverse,
    COMMAND_TYPE_SET_CELL_TEXT,
    STATUS_PENDING,
)
from scripts.hwpx.web_office.cell_edit_plan import (  # noqa: E402
    build_dry_run_edit_plan, SAVE_DRY_RUN_NOOP, SAVE_DRY_RUN_READY, SAVE_DRY_RUN_REJECTED,
)
from scripts.ops.audit_web_office_cell_edit_mvp_a import (  # noqa: E402
    audit, VIEWER_DIR, SELF_TEST_JS, PY_FILES, JS_FILES,
    FORBIDDEN_TOKENS_PY, FORBIDDEN_TOKENS_JS,
)


SAMPLE_HASH = "abc123"
SAMPLE_CELL = "cell_t_s0_001_r2_c1"
SAMPLE_DOC = {"cells": [
    {"cellId": SAMPLE_CELL, "text": "구값"},
    {"cellId": "cell_t_s0_001_r2_c2", "text": "다른셀"},
]}


# ── EditCommand v1 schema ──────────────────────────────────────

def test_edit_command_schema_required_fields():
    cmd = make_set_cell_text_command(
        cell_id=SAMPLE_CELL, table_index=1,
        before="구값", after="새값",
        source_document_hash=SAMPLE_HASH)
    d = cmd.to_dict()
    for k in ("commandId", "commandType", "targetId", "targetKind",
                      "before", "after", "expectedBefore", "forward",
                      "inverse", "createdAt", "sourceDocumentHash",
                      "status"):
        assert k in d, f"missing field: {k}"
    assert d["commandType"] == COMMAND_TYPE_SET_CELL_TEXT
    assert d["targetKind"] == "cell"
    assert d["status"] == STATUS_PENDING
    assert d["sourceDocumentHash"] == SAMPLE_HASH


def test_no_command_when_before_equals_after():
    with pytest.raises(ValueError):
        make_set_cell_text_command(
            cell_id=SAMPLE_CELL, table_index=1,
            before="x", after="x",
            source_document_hash=SAMPLE_HASH)


def test_expected_before_blocks_apply_forward():
    cmd = make_set_cell_text_command(
        cell_id=SAMPLE_CELL, table_index=1,
        before="구값", after="새값",
        source_document_hash=SAMPLE_HASH)
    # expectedBefore = before by default → 다른 현재값이면 차단
    with pytest.raises(ValueError):
        apply_forward("이질적인값", cmd)


def test_forward_and_inverse_roundtrip():
    cmd = make_set_cell_text_command(
        cell_id=SAMPLE_CELL, table_index=1,
        before="구값", after="새값",
        source_document_hash=SAMPLE_HASH)
    assert apply_forward("구값", cmd) == "새값"
    assert apply_inverse("새값", cmd) == "구값"


# ── dry-run plan 게이트 ──────────────────────────────────────────

def test_empty_command_log_is_noop():
    r = build_dry_run_edit_plan([], SAMPLE_DOC, SAMPLE_HASH)
    assert r["status"] == SAVE_DRY_RUN_NOOP
    assert r["plan"] is None
    assert r["dryRun"] is True


def test_ready_plan_for_valid_command():
    cmd = make_set_cell_text_command(
        cell_id=SAMPLE_CELL, table_index=1,
        before="구값", after="새값",
        source_document_hash=SAMPLE_HASH)
    r = build_dry_run_edit_plan([cmd], SAMPLE_DOC, SAMPLE_HASH)
    assert r["status"] == SAVE_DRY_RUN_READY
    assert r["plan"]["set_cells"][0]["value"] == "새값"
    assert r["plan"]["set_cells"][0]["row"] == 2
    assert r["plan"]["set_cells"][0]["col"] == 1
    assert r["dryRun"] is True
    assert r["sourceDocumentHash"] == SAMPLE_HASH
    assert r["acceptedCount"] == 1
    assert r["rejectedCount"] == 0


def test_source_hash_mismatch_rejected():
    cmd = make_set_cell_text_command(
        cell_id=SAMPLE_CELL, table_index=1,
        before="구값", after="새값",
        source_document_hash="WRONG_HASH")
    r = build_dry_run_edit_plan([cmd], SAMPLE_DOC, SAMPLE_HASH)
    assert r["status"] == SAVE_DRY_RUN_REJECTED
    assert any(x["reason"] == "SOURCE_HASH_MISMATCH"
                      for x in r["rejected"])


def test_expected_before_mismatch_rejected():
    # 셀의 현재 텍스트 = "구값", 그러나 command의 expectedBefore = "다른기준"
    cmd = make_set_cell_text_command(
        cell_id=SAMPLE_CELL, table_index=1,
        before="다른기준", after="결과",
        source_document_hash=SAMPLE_HASH)
    r = build_dry_run_edit_plan([cmd], SAMPLE_DOC, SAMPLE_HASH)
    assert r["status"] == SAVE_DRY_RUN_REJECTED
    assert any(x["reason"] == "EXPECTED_BEFORE_MISMATCH"
                      for x in r["rejected"])


def test_chained_commands_on_same_cell_use_last_value():
    cmd1 = make_set_cell_text_command(
        cell_id=SAMPLE_CELL, table_index=1,
        before="구값", after="중간",
        source_document_hash=SAMPLE_HASH)
    cmd2 = make_set_cell_text_command(
        cell_id=SAMPLE_CELL, table_index=1,
        before="중간", after="최종",
        source_document_hash=SAMPLE_HASH)
    r = build_dry_run_edit_plan([cmd1, cmd2], SAMPLE_DOC, SAMPLE_HASH)
    assert r["status"] == SAVE_DRY_RUN_READY
    assert len(r["plan"]["set_cells"]) == 1
    assert r["plan"]["set_cells"][0]["value"] == "최종"


# ── 정적 잠금: writer / apply 토큰 부재 ─────────────────────────

def test_no_writer_tokens_in_python_modules():
    for p in PY_FILES:
        src = p.read_text(encoding="utf-8")
        for tok in FORBIDDEN_TOKENS_PY:
            assert tok not in src, f"{p.name} has forbidden: {tok}"


def test_no_writer_tokens_in_js_modules():
    for p in JS_FILES:
        src = p.read_text(encoding="utf-8")
        for tok in FORBIDDEN_TOKENS_JS:
            assert tok not in src, f"{p.name} has forbidden: {tok}"


def test_python_cell_edit_plan_does_not_import_hwpx_edit_tool():
    """cell_edit_plan.py 가 직접 hwpx_edit_tool 을 import 하지 않는지
    정적으로 확인. (sys.modules 검사는 같은 세션에서 다른 모듈이 import 한
    경우 false-positive 가 될 수 있어 정적 grep 으로 분리한다 — writer 본
    실행 경로는 cell_save_pipeline.py 에서만 도입된다.)"""
    src = (PR / "scripts/hwpx/web_office/cell_edit_plan.py").read_text(
        encoding="utf-8")
    for tok in ("hwpx_edit_tool", "apply_edit_plan(",
                            "from scripts.hwpx import hwpx_edit_tool"):
        assert tok not in src, f"cell_edit_plan.py has forbidden: {tok}"


# ── JS 자체 테스트 / audit ──────────────────────────────────────

def _node_ok() -> bool:
    try:
        r = subprocess.run(["node", "--version"], capture_output=True,
                                          text=True, encoding="utf-8", errors="replace", timeout=10)
        return r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


@pytest.mark.skipif(not _node_ok(), reason="node not available")
def test_js_self_test_passes_all_scenarios():
    r = subprocess.run(["node", str(SELF_TEST_JS)],
                                      capture_output=True, text=True,
                                      timeout=30, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    last = r.stdout.strip().splitlines()[-1]
    out = json.loads(last)
    assert out["verdict"] == "PASS"
    expected_checks = [
        "selectCell", "enterCellEdit", "commitChange",
        "noChangeNoCommand", "expectedBeforeBlock",
        "undo", "redo", "emptyUndo",
        "saveNoop", "savePayload", "commandLogAppendOnly",
    ]
    for k in expected_checks:
        assert out["checks"].get(k) is True, f"check missing: {k}"


def test_audit_returns_pass():
    out = audit()
    assert out["verdict"] == "PASS", json.dumps(
        out, ensure_ascii=False, indent=2)[:2000]


def test_no_hwpx_output_in_viewer_or_python_dir():
    leaks = (list(VIEWER_DIR.glob("*.hwpx"))
                  + list((PR / "scripts/hwpx/web_office").glob("*.hwpx")))
    assert leaks == []
