"""WEB-OFFICE-PARA-ADAPTER-APPLYCHARPR-01 계약 테스트.

paragraph_writer_adapter.applied[] 의 applyCharPrIDRef + commandType
metadata 적재를 통한 V4_CHARPR_PRESERVED 활성화. REPLACE/DELETE 의
V1/V7 회귀 PASS 유지. TYPE_TEXT 는 expectedBefore reject 로 applied=∅
시나리오 → V4 DEFERRED 명시.
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
sys.path.insert(0, str(PR / "scripts/hwpx"))

from scripts.hwpx.web_office.ro_view_importer import (  # noqa: E402
    import_hwpx_as_ro_view)
from scripts.hwpx.web_office.para_edit_e2e_pipeline import (  # noqa: E402
    run_para_edit_e2e,
    SCENARIO_TYPE, SCENARIO_REPLACE, SCENARIO_DELETE,
    READBACK_PASS, READBACK_DEFERRED)


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


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _pick_cell_paragraph(doc):
    for p in doc.paragraphs:
        cs = p.containerScope or {}
        if (cs.get("kind") == "cell" and p.parPrIDRef
                and p.runs and p.runs[0].charPrIDRef
                and len(p.text or "") >= 2):
            return p
    return None


# ── 1. applied[] 에 applyCharPrIDRef + commandType 포함 ──────────

@need_fx
def test_replace_applied_has_applycharpr_and_commandtype(tmp_path):
    doc = import_hwpx_as_ro_view(FIXTURE)
    ro_p = _pick_cell_paragraph(doc)
    out = tmp_path / "ap_replace.hwpx"
    res = run_para_edit_e2e(
        source_path=FIXTURE, output_path=out,
        scenario=SCENARIO_REPLACE,
        paragraph_id=ro_p.paragraphId,
        range_anchor=0, range_focus=1, replace_after="Q",
        allow_writer=True)
    applied = res.get("appliedPlanEdits") or []
    assert applied, res
    for it in applied:
        assert "applyCharPrIDRef" in it, it
        assert it.get("commandType") == "REPLACE_TEXT_RANGE", it


@need_fx
def test_delete_applied_has_applycharpr_and_commandtype(tmp_path):
    doc = import_hwpx_as_ro_view(FIXTURE)
    ro_p = _pick_cell_paragraph(doc)
    out = tmp_path / "ap_delete.hwpx"
    res = run_para_edit_e2e(
        source_path=FIXTURE, output_path=out,
        scenario=SCENARIO_DELETE,
        paragraph_id=ro_p.paragraphId,
        range_anchor=0, range_focus=1, allow_writer=True)
    applied = res.get("appliedPlanEdits") or []
    assert applied, res
    for it in applied:
        assert "applyCharPrIDRef" in it, it
        assert it.get("commandType") == "DELETE_TEXT_RANGE", it


# ── 2. REPLACE / DELETE 의 V4_CHARPR_PRESERVED verify7 + readback PASS ─

@need_fx
def test_replace_v4_verify7_and_readback_pass(tmp_path):
    doc = import_hwpx_as_ro_view(FIXTURE)
    ro_p = _pick_cell_paragraph(doc)
    out = tmp_path / "ap_v4_replace.hwpx"
    res = run_para_edit_e2e(
        source_path=FIXTURE, output_path=out,
        scenario=SCENARIO_REPLACE,
        paragraph_id=ro_p.paragraphId,
        range_anchor=0, range_focus=1, replace_after="Q",
        allow_writer=True)
    v7r = (res.get("verify7") or {}).get("results", {})
    assert v7r.get("V4_CHARPR_PRESERVED") == "PASS", v7r
    rb = res.get("readback") or {}
    assert rb.get("V4_CHARPR_PRESERVED") == READBACK_PASS, rb


@need_fx
def test_delete_v4_verify7_and_readback_pass(tmp_path):
    doc = import_hwpx_as_ro_view(FIXTURE)
    ro_p = _pick_cell_paragraph(doc)
    out = tmp_path / "ap_v4_delete.hwpx"
    res = run_para_edit_e2e(
        source_path=FIXTURE, output_path=out,
        scenario=SCENARIO_DELETE,
        paragraph_id=ro_p.paragraphId,
        range_anchor=0, range_focus=1, allow_writer=True)
    v7r = (res.get("verify7") or {}).get("results", {})
    assert v7r.get("V4_CHARPR_PRESERVED") == "PASS", v7r
    rb = res.get("readback") or {}
    assert rb.get("V4_CHARPR_PRESERVED") == READBACK_PASS, rb


# ── 3. 신규 charPr 생성 0건 — applied / output 집합 ⊆ source ─────

@need_fx
def test_no_new_charpr_introduced(tmp_path):
    doc = import_hwpx_as_ro_view(FIXTURE)
    ro_p = _pick_cell_paragraph(doc)
    src = {r.charPrIDRef for r in ro_p.runs}
    out = tmp_path / "ap_no_new.hwpx"
    res = run_para_edit_e2e(
        source_path=FIXTURE, output_path=out,
        scenario=SCENARIO_REPLACE,
        paragraph_id=ro_p.paragraphId,
        range_anchor=0, range_focus=1, replace_after="P",
        allow_writer=True)
    rb = res.get("readback") or {}
    out_set = {x if x != "None" else None
                  for x in (rb.get("outputCharPrSet") or [])}
    src_str = {str(x) for x in src}
    new = set(rb.get("outputCharPrSet") or []) - src_str
    assert not new, (new, src_str, rb.get("outputCharPrSet"))
    applied = res.get("appliedPlanEdits") or []
    apply_set = {str(it.get("applyCharPrIDRef")) for it in applied}
    new_applied = apply_set - src_str
    assert not new_applied, (new_applied, src_str)


# ── 4. parPrIDRef 변경 0건 ────────────────────────────────────────

@need_fx
def test_parpr_unchanged(tmp_path):
    doc = import_hwpx_as_ro_view(FIXTURE)
    ro_p = _pick_cell_paragraph(doc)
    par_before = ro_p.parPrIDRef
    out = tmp_path / "ap_parpr.hwpx"
    res = run_para_edit_e2e(
        source_path=FIXTURE, output_path=out,
        scenario=SCENARIO_REPLACE,
        paragraph_id=ro_p.paragraphId,
        range_anchor=0, range_focus=1, replace_after="P",
        allow_writer=True)
    rb = res.get("readback") or {}
    assert rb.get("outputParPrIDRef") == par_before


# ── 5. V1/V7 회귀 PASS 유지 ───────────────────────────────────────

@need_fx
def test_replace_v1_v7_regression(tmp_path):
    doc = import_hwpx_as_ro_view(FIXTURE)
    ro_p = _pick_cell_paragraph(doc)
    out = tmp_path / "ap_reg_replace.hwpx"
    res = run_para_edit_e2e(
        source_path=FIXTURE, output_path=out,
        scenario=SCENARIO_REPLACE,
        paragraph_id=ro_p.paragraphId,
        range_anchor=0, range_focus=1, replace_after="Q",
        allow_writer=True)
    rb = res.get("readback") or {}
    assert rb.get("V1_RANGE_POSITION_OK") == READBACK_PASS
    assert rb.get("V7_READBACK_MATCH") == READBACK_PASS


@need_fx
def test_delete_v1_v7_regression(tmp_path):
    doc = import_hwpx_as_ro_view(FIXTURE)
    ro_p = _pick_cell_paragraph(doc)
    out = tmp_path / "ap_reg_delete.hwpx"
    res = run_para_edit_e2e(
        source_path=FIXTURE, output_path=out,
        scenario=SCENARIO_DELETE,
        paragraph_id=ro_p.paragraphId,
        range_anchor=0, range_focus=1, allow_writer=True)
    rb = res.get("readback") or {}
    assert rb.get("V1_RANGE_POSITION_OK") == READBACK_PASS
    assert rb.get("V7_READBACK_MATCH") == READBACK_PASS


# ── 6. TYPE_TEXT 계약 무변경 — applied=∅ → V4 readback DEFERRED ──

@need_fx
def test_type_text_v4_deferred_when_applied_empty(tmp_path):
    doc = import_hwpx_as_ro_view(FIXTURE)
    ro_p = _pick_cell_paragraph(doc)
    out = tmp_path / "ap_type.hwpx"
    res = run_para_edit_e2e(
        source_path=FIXTURE, output_path=out,
        scenario=SCENARIO_TYPE, paragraph_id=ro_p.paragraphId,
        range_anchor=0, insert_text="T", allow_writer=True)
    applied = res.get("appliedPlanEdits") or []
    rb = res.get("readback") or {}
    if not applied:
        # expectedBefore reject 경로 — V4 readback DEFERRED 명시.
        assert rb.get("V4_CHARPR_PRESERVED") == READBACK_DEFERRED, rb


# ── 7. 원본 sha/mtime 사전=사후 ─────────────────────────────────

@need_fx
def test_source_sha_mtime_preserved(tmp_path):
    sha_b = _sha(FIXTURE)
    mt_b = FIXTURE.stat().st_mtime_ns
    doc = import_hwpx_as_ro_view(FIXTURE)
    ro_p = _pick_cell_paragraph(doc)
    for i, (scn, kw) in enumerate([
        (SCENARIO_REPLACE,
         {"range_focus": 1, "replace_after": "Y"}),
        (SCENARIO_DELETE, {"range_focus": 1}),
    ]):
        out = tmp_path / f"ap_pres_{i}.hwpx"
        run_para_edit_e2e(
            source_path=FIXTURE, output_path=out,
            scenario=scn, paragraph_id=ro_p.paragraphId,
            range_anchor=0, allow_writer=True, **kw)
    assert _sha(FIXTURE) == sha_b
    assert FIXTURE.stat().st_mtime_ns == mt_b


# ── 8. output sandbox(tmp_path) 만 생성 ──────────────────────────

@need_fx
def test_output_only_in_sandbox(tmp_path):
    doc = import_hwpx_as_ro_view(FIXTURE)
    ro_p = _pick_cell_paragraph(doc)
    out = tmp_path / "ap_sandbox.hwpx"
    res = run_para_edit_e2e(
        source_path=FIXTURE, output_path=out,
        scenario=SCENARIO_REPLACE,
        paragraph_id=ro_p.paragraphId,
        range_anchor=0, range_focus=1, replace_after="S",
        allow_writer=True)
    assert res.get("outputCreated") is True
    assert out.exists()
    assert str(out).startswith(str(tmp_path))


# ── 9. audit script verdict=="PASS" ─────────────────────────────

def test_audit_script_pass():
    from scripts.ops.audit_web_office_para_adapter_applycharpr import (
        audit)
    rep = audit()
    fails = [f for f in rep["findings"]
                if f.get("level") == "FAIL"]
    assert not fails, json.dumps(rep, ensure_ascii=False, indent=2)
    assert rep["verdict"] == "PASS"
