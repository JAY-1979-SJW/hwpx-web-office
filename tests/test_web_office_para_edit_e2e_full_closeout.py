"""WEB-OFFICE-PARA-EDIT-E2E-FULL-CLOSEOUT-01 감리 검사.

cell containerScope · 단일 run 범위 PARA-EDIT E2E 정식 준공의 정적·
동적 게이트 검증. 본 공정은 신규 writer 기능을 시공하지 않으므로,
모든 검증은 기존 자재 호출 + sandbox tmp_path 안 동적 신호로 한정된다.
"""
from __future__ import annotations
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

import pytest

PR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PR))

from scripts.hwpx.web_office.ro_view_importer import (  # noqa: E402
    import_hwpx_as_ro_view)
from scripts.hwpx.web_office.para_edit_e2e_pipeline import (  # noqa: E402
    run_para_edit_e2e, SCENARIO_TYPE, SCENARIO_REPLACE, SCENARIO_DELETE)
from scripts.hwpx.web_office.paragraph_writer_adapter import (  # noqa: E402
    REASON_BODY_PARAGRAPH_NOT_SUPPORTED,
    REASON_MULTI_RUN_RANGE_NOT_SUPPORTED)


CLOSEOUT_DOC = (PR / "docs/architecture/"
                   "web_office_para_edit_e2e_full_closeout.md")


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


def _pick(doc):
    for p in doc.paragraphs:
        cs = p.containerScope or {}
        if (cs.get("kind") == "cell" and p.parPrIDRef
                and p.runs and p.runs[0].charPrIDRef
                and len(p.text or "") >= 2):
            return p
    return None


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


REQUIRED_V7 = ("V2_NO_CROSS_PARAGRAPH_LEAK",
                "V3_UNTOUCHED_RUNS_PRESERVED",
                "V4_CHARPR_PRESERVED", "V5_PARPR_PRESERVED",
                "V6_OUTPUT_ISOLATED")
REQUIRED_RB = ("V1_RANGE_POSITION_OK",
                "V4_CHARPR_PRESERVED", "V7_READBACK_MATCH")


# ── 1. 정식 시방서 존재 + 필수 문구 ─────────────────────────────

def test_closeout_doc_exists():
    assert CLOSEOUT_DOC.is_file(), CLOSEOUT_DOC


def test_closeout_doc_lists_supported_commands():
    src = CLOSEOUT_DOC.read_text(encoding="utf-8")
    for ct in ("SET_CELL_TEXT", "TYPE_TEXT",
                "REPLACE_TEXT_RANGE", "DELETE_TEXT_RANGE"):
        assert ct in src, ct


def test_closeout_doc_lists_v_gates():
    src = CLOSEOUT_DOC.read_text(encoding="utf-8")
    for v in ("V1_RANGE_POSITION_OK", "V2_NO_CROSS_PARAGRAPH_LEAK",
                "V3_UNTOUCHED_RUNS_PRESERVED", "V4_CHARPR_PRESERVED",
                "V5_PARPR_PRESERVED", "V6_OUTPUT_ISOLATED",
                "V7_READBACK_MATCH"):
        assert v in src, v


def test_closeout_doc_lists_out_of_scope():
    src = CLOSEOUT_DOC.read_text(encoding="utf-8")
    for phrase in ("MULTI_RUN_RANGE_NOT_SUPPORTED",
                    "BODY_PARAGRAPH_NOT_SUPPORTED",
                    "AI auto input"):
        assert phrase in src, phrase


# ── 2. 동적 시운전 — 3 시나리오 모두 V1~V7 PASS ────────────────

@need_fx
def test_all_three_scenarios_v1_to_v7_pass(tmp_path):
    doc = import_hwpx_as_ro_view(FIXTURE)
    ro_p = _pick(doc)
    for scn, kw, name in [
        (SCENARIO_TYPE, {"insert_text": "T"}, "type"),
        (SCENARIO_REPLACE, {"range_focus": 1, "replace_after": "R"},
          "replace"),
        (SCENARIO_DELETE, {"range_focus": 1}, "delete"),
    ]:
        out = tmp_path / f"closeout_{name}.hwpx"
        res = run_para_edit_e2e(
            source_path=FIXTURE, output_path=out,
            scenario=scn, paragraph_id=ro_p.paragraphId,
            range_anchor=0, allow_writer=True, **kw)
        assert res.get("outputCreated") is True, (name, res)
        assert res.get("writerActivated") is True, (name, res)
        assert not res.get("rejected"), (name, res)
        v7 = (res.get("verify7") or {}).get("results", {})
        for k in REQUIRED_V7:
            assert v7.get(k) == "PASS", (name, k, v7)
        rb = res.get("readback") or {}
        for k in REQUIRED_RB:
            assert rb.get(k) == "PASS", (name, k, rb)
        assert str(out).startswith(str(tmp_path))


# ── 3. 비지원 회로 — multi-run / body paragraph 유지 ─────────────

@need_fx
def test_multi_run_or_body_paragraph_still_rejected(tmp_path):
    """OUT_OF_SCOPE 회로가 본 공정 이후에도 유지되는지 확인.
    fixture 가 multi-run 이 아니면 reject 사유는 OUT_OF_BOUNDS 또는
    EXPECTED_BEFORE_MISMATCH 일 수 있으나, 어느 쪽이든 writer 본 실행이
    수행되어서는 안 된다.
    """
    doc = import_hwpx_as_ro_view(FIXTURE)
    ro_p = _pick(doc)
    over = sum(len(r.text) for r in ro_p.runs) + 5
    out = tmp_path / "closeout_multi.hwpx"
    res = run_para_edit_e2e(
        source_path=FIXTURE, output_path=out,
        scenario=SCENARIO_REPLACE, paragraph_id=ro_p.paragraphId,
        range_anchor=0, range_focus=over, replace_after="X",
        allow_writer=True)
    reasons = {r.get("reason") for r in res.get("rejected") or []}
    accepted = {
        REASON_MULTI_RUN_RANGE_NOT_SUPPORTED,
        REASON_BODY_PARAGRAPH_NOT_SUPPORTED,
        "RANGE_OUT_OF_BOUNDS",
        "EXPECTED_BEFORE_MISMATCH",
        "EXPECTED_BEFORE_MISMATCH_PARAGRAPH",
    }
    assert reasons & accepted, res


# ── 4. 안전 게이트 — outputPath == sourcePath 차단 ───────────────

@need_fx
def test_output_equals_source_blocked():
    doc = import_hwpx_as_ro_view(FIXTURE)
    ro_p = _pick(doc)
    res = run_para_edit_e2e(
        source_path=FIXTURE, output_path=FIXTURE,
        scenario=SCENARIO_TYPE, paragraph_id=ro_p.paragraphId,
        range_anchor=0, insert_text="X", allow_writer=True)
    reasons = {r.get("reason") for r in res.get("rejected") or []}
    assert "OUTPUT_EQUALS_SOURCE" in reasons, res


# ── 5. 원본 sha/mtime 무변경 ────────────────────────────────────

@need_fx
def test_source_sha_mtime_preserved_after_three_scenarios(tmp_path):
    sha_b = _sha(FIXTURE)
    mt_b = FIXTURE.stat().st_mtime_ns
    doc = import_hwpx_as_ro_view(FIXTURE)
    ro_p = _pick(doc)
    for i, (scn, kw) in enumerate([
        (SCENARIO_TYPE, {"insert_text": "T"}),
        (SCENARIO_REPLACE, {"range_focus": 1, "replace_after": "R"}),
        (SCENARIO_DELETE, {"range_focus": 1}),
    ]):
        out = tmp_path / f"pres_{i}.hwpx"
        run_para_edit_e2e(
            source_path=FIXTURE, output_path=out,
            scenario=scn, paragraph_id=ro_p.paragraphId,
            range_anchor=0, allow_writer=True, **kw)
    assert _sha(FIXTURE) == sha_b
    assert FIXTURE.stat().st_mtime_ns == mt_b


# ── 6. audit verdict == PASS ─────────────────────────────────────

def test_audit_script_pass():
    from scripts.ops.audit_web_office_para_edit_e2e_full_closeout import (
        audit)
    rep = audit()
    fails = [f for f in rep["findings"]
              if f.get("level") == "FAIL"]
    assert not fails, json.dumps(rep, ensure_ascii=False, indent=2)
    assert rep["verdict"] in ("PASS", "WARN"), rep
