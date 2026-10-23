"""WEB-OFFICE-PARA-EDIT-IME-LIVE-01 감리 검사.

브라우저 IME composition 흐름을 node 기반 live smoke 로 회귀 잠금하고,
fixture 가용 시 finalText 를 SCENARIO_TYPE 으로 Python E2E 에 투입해
V1~V7 PASS + 원본 sha/mtime 무변경 + sandbox 격리를 확인한다.
"""
from __future__ import annotations
import hashlib
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

PR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PR))

SMOKE_JS = (PR / "frontend/web_office_viewer/"
                  "para_edit_ime_live_smoke.mjs")


def _node_ok() -> bool:
    try:
        r = subprocess.run(["node", "--version"], capture_output=True,
                                          text=True, encoding="utf-8", errors="replace", timeout=10)
        return r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


NODE_OK = _node_ok()
need_node = pytest.mark.skipif(not NODE_OK, reason="node not available")


def _run_smoke() -> dict:
    r = subprocess.run(["node", str(SMOKE_JS)], capture_output=True,
                                      text=True, timeout=30, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


# ── 1. smoke script 존재 + import 정합 ─────────────────────────

def test_smoke_script_exists():
    assert SMOKE_JS.is_file()
    src = SMOKE_JS.read_text(encoding="utf-8")
    for pat in ("para_edit_state.mjs", "para_edit_runtime.mjs",
                  "onCompositionStart", "onCompositionUpdate",
                  "onCompositionEnd"):
        assert pat in src, pat


# ── 2. live smoke verdict PASS + 38 checks all ok ──────────────

@need_node
def test_live_smoke_verdict_pass():
    out = _run_smoke()
    assert out["verdict"] == "PASS", out
    assert len(out["checks"]) >= 30
    bad = {k: v for k, v in out["checks"].items() if not v.get("ok")}
    assert not bad, bad


# ── 3. compositionupdate 중 command 생성 0건 ──────────────────

@need_node
def test_composition_update_no_command():
    out = _run_smoke()
    assert out["checks"]["compositionUpdateNoCommand"]["ok"] is True
    assert out["checks"]["compositionStartNoCommand"]["ok"] is True


# ── 4. compositionend 후 TYPE_TEXT 1건 생성 ────────────────────

@need_node
def test_composition_end_creates_single_type_text():
    out = _run_smoke()
    for k in ("compositionEndCommandCreated",
                "compositionEndCommandType",
                "compositionEndCommandCount"):
        assert out["checks"][k]["ok"] is True, k
    lc = out["liveCommand"]
    assert lc["commandType"] == "TYPE_TEXT"


# ── 5. TYPE_TEXT 계약 — expectedBefore=="" + rangeStart==rangeEnd ─

@need_node
def test_type_text_contract_aligned():
    out = _run_smoke()
    lc = out["liveCommand"]
    assert lc["expectedBefore"] == ""
    assert lc["rangeStart"] == lc["rangeEnd"]
    assert lc["caretOffset"] == lc["rangeStart"]
    assert lc["afterText"] == out["finalText"]
    assert lc["insertText"] == out["finalText"]


# ── 6. containerScope 유지 ─────────────────────────────────────

@need_node
def test_container_scope_preserved():
    out = _run_smoke()
    lc = out["liveCommand"]
    assert lc["containerScope"]["kind"] == "cell"
    assert lc["containerScope"]["tableIndex"] == 0
    assert lc["containerScope"]["rowIndex"] == 0
    assert lc["containerScope"]["colIndex"] == 0


# ── 7. undo/redo + commandLog append-only ──────────────────────

@need_node
def test_undo_redo_command_log_append_only():
    out = _run_smoke()
    for k in ("undoOk", "undoTextReverted",
                "undoCommandLogAppendOnly", "redoOk",
                "redoTextReApplied"):
        assert out["checks"][k]["ok"] is True, k


# ── 8. cancel + composition lock ──────────────────────────────

@need_node
def test_composition_cancel_and_lock():
    out = _run_smoke()
    for k in ("cancelNoCommand", "cancelReasonCancelled",
                "cancelLogUnchanged", "compositionLocksTypeText",
                "compositionLockedLogUnchanged"):
        assert out["checks"][k]["ok"] is True, k


# ── 9. inverse DELETE_TEXT_RANGE 정합 ─────────────────────────

@need_node
def test_inverse_delete_text_range_consistent():
    out = _run_smoke()
    lc = out["liveCommand"]
    assert lc["inverse"]["kind"] == "DELETE_TEXT_RANGE"
    assert lc["inverse"]["rangeAnchor"] == lc["rangeStart"]
    assert (lc["inverse"]["rangeFocus"]
            == lc["rangeStart"] + len(lc["afterText"]))


# ── 10. fixture E2E — finalText 를 SCENARIO_TYPE 으로 투입 ─────

def _fixture() -> Path | None:
    db = PR / "data/recognition_corpus/corpus.sqlite3"
    if not db.is_file():
        return None
    try:
        conn = sqlite3.connect(db)
        row = conn.execute("""
            SELECT d.source_path FROM hwpx_documents d
            JOIN document_classifications c
                ON c.document_id = d.document_id
            WHERE d.inventory_status='FOUND'
              AND c.document_type='fillable_form'
              AND d.file_size BETWEEN 30000 AND 80000
            ORDER BY d.first_seen_at LIMIT 1
        """).fetchone()
        conn.close()
    except sqlite3.Error:
        return None
    if not row:
        return None
    p = PR / row[0]
    return p if p.is_file() else None


FIXTURE = _fixture()
need_fx = pytest.mark.skipif(FIXTURE is None, reason="fixture missing")
REQUIRED_V7 = ("V2_NO_CROSS_PARAGRAPH_LEAK",
                "V3_UNTOUCHED_RUNS_PRESERVED",
                "V4_CHARPR_PRESERVED", "V5_PARPR_PRESERVED",
                "V6_OUTPUT_ISOLATED")
REQUIRED_RB = ("V1_RANGE_POSITION_OK",
                "V4_CHARPR_PRESERVED", "V7_READBACK_MATCH")


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


@need_fx
@need_node
def test_live_command_final_text_e2e_v1_to_v7(tmp_path):
    from scripts.hwpx.web_office.ro_view_importer import (
        import_hwpx_as_ro_view)
    from scripts.hwpx.web_office.para_edit_e2e_pipeline import (
        run_para_edit_e2e, SCENARIO_TYPE)

    out_smoke = _run_smoke()
    final_text = out_smoke["finalText"]
    doc = import_hwpx_as_ro_view(FIXTURE)
    ro_p = next(
        (p for p in doc.paragraphs
          if (p.containerScope or {}).get("kind") == "cell"
          and p.parPrIDRef and p.runs and p.runs[0].charPrIDRef
          and len(p.text or "") >= 2), None)
    assert ro_p is not None
    sha_b = _sha(FIXTURE); mt_b = FIXTURE.stat().st_mtime_ns
    out = tmp_path / "ime_e2e.hwpx"
    res = run_para_edit_e2e(
        source_path=FIXTURE, output_path=out,
        scenario=SCENARIO_TYPE, paragraph_id=ro_p.paragraphId,
        range_anchor=0, insert_text=final_text, allow_writer=True)
    assert res.get("outputCreated") is True, res
    assert res.get("writerActivated") is True, res
    assert not res.get("rejected"), res
    v7 = (res.get("verify7") or {}).get("results", {})
    for k in REQUIRED_V7:
        assert v7.get(k) == "PASS", (k, v7)
    rb = res.get("readback") or {}
    for k in REQUIRED_RB:
        assert rb.get(k) == "PASS", (k, rb)
    assert str(out).startswith(str(tmp_path))
    assert _sha(FIXTURE) == sha_b
    assert FIXTURE.stat().st_mtime_ns == mt_b


# ── 11. audit verdict PASS ───────────────────────────────────

def test_audit_script_pass():
    from scripts.ops.audit_web_office_para_edit_ime_live import audit
    rep = audit()
    fails = [f for f in rep["findings"]
              if f.get("level") == "FAIL"]
    assert not fails, json.dumps(rep, ensure_ascii=False, indent=2)
    assert rep["verdict"] in ("PASS", "WARN"), rep
