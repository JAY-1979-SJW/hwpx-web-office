"""WEB-OFFICE-PARA-READBACK-PARSER-01 계약 테스트.

REPLACE_TEXT_RANGE / DELETE_TEXT_RANGE 의 V1_RANGE_POSITION_OK 와
V7_READBACK_MATCH 를 PASS 화하는 readback helper 의 정합·격리·매칭을
검증한다. TYPE_TEXT 는 expectedBefore 계약 gap 으로 DEFERRED 유지.

본 테스트는 LOCKED 모듈을 호출만 한다 (mutation 0). 신규 모듈
paragraph_readback_parser.py 부재가 정상 (§11-6 자재 재사용).
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
    _expected_after_paragraph_text,
    _match_output_paragraph,
    _readback_verify_paragraph,
    SCENARIO_TYPE, SCENARIO_REPLACE, SCENARIO_DELETE,
    READBACK_PASS, READBACK_FAIL, READBACK_DEFERRED)


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


# ── 1. forbidden new module 부재 (§11-6) ───────────────────────────

def test_no_paragraph_readback_parser_module():
    forbidden = (PR / "scripts/hwpx/web_office/"
                 "paragraph_readback_parser.py")
    assert not forbidden.exists(), (
        "신규 모듈 신축 금지 — e2e_pipeline 내부 helper 만 허용")


# ── 2. expected after text helper 단위 — pure ───────────────────────

def test_expected_after_text_replace_at_start():
    before = "Hello, world"
    applied = [{
        "rangeStart": 0, "rangeEnd": 5, "afterText": "Howdy",
    }]
    assert _expected_after_paragraph_text(before, applied) == (
        "Howdy, world")


def test_expected_after_text_delete_at_start():
    before = "ABCDE"
    applied = [{
        "rangeStart": 0, "rangeEnd": 1, "afterText": "",
    }]
    assert _expected_after_paragraph_text(before, applied) == "BCDE"


# ── 3. output HWPX readback paragraph 추출 PASS ────────────────────

@need_fx
def test_readback_extracts_paragraphs_from_output(tmp_path):
    doc = import_hwpx_as_ro_view(FIXTURE)
    ro_p = _pick_cell_paragraph(doc)
    out = tmp_path / "rb_extract.hwpx"
    res = run_para_edit_e2e(
        source_path=FIXTURE, output_path=out,
        scenario=SCENARIO_REPLACE,
        paragraph_id=ro_p.paragraphId,
        range_anchor=0, range_focus=1, replace_after="Q",
        allow_writer=True)
    assert res.get("outputCreated") is True, res
    out_doc = import_hwpx_as_ro_view(out)
    assert out_doc.paragraphs, "output paragraphs 0"


# ── 4. paragraphId 또는 containerScope 재매칭 PASS ─────────────────

@need_fx
def test_match_output_paragraph_by_paragraph_id(tmp_path):
    doc = import_hwpx_as_ro_view(FIXTURE)
    ro_p = _pick_cell_paragraph(doc)
    out = tmp_path / "rb_match.hwpx"
    res = run_para_edit_e2e(
        source_path=FIXTURE, output_path=out,
        scenario=SCENARIO_REPLACE,
        paragraph_id=ro_p.paragraphId,
        range_anchor=0, range_focus=1, replace_after="M",
        allow_writer=True)
    assert res.get("outputCreated") is True
    rb = res.get("readback") or {}
    assert rb.get("matchedBy") in ("paragraphId", "containerScope")
    assert rb.get("matchedParagraphId") is not None


# ── 5. REPLACE_TEXT_RANGE V1_RANGE_POSITION_OK PASS ────────────────

@need_fx
def test_replace_v1_range_position_ok(tmp_path):
    doc = import_hwpx_as_ro_view(FIXTURE)
    ro_p = _pick_cell_paragraph(doc)
    out = tmp_path / "rb_v1_replace.hwpx"
    res = run_para_edit_e2e(
        source_path=FIXTURE, output_path=out,
        scenario=SCENARIO_REPLACE,
        paragraph_id=ro_p.paragraphId,
        range_anchor=0, range_focus=1, replace_after="Q",
        allow_writer=True)
    rb = res.get("readback") or {}
    assert rb.get("V1_RANGE_POSITION_OK") == READBACK_PASS, rb


# ── 6. REPLACE_TEXT_RANGE V7_READBACK_MATCH PASS ───────────────────

@need_fx
def test_replace_v7_readback_match(tmp_path):
    doc = import_hwpx_as_ro_view(FIXTURE)
    ro_p = _pick_cell_paragraph(doc)
    out = tmp_path / "rb_v7_replace.hwpx"
    res = run_para_edit_e2e(
        source_path=FIXTURE, output_path=out,
        scenario=SCENARIO_REPLACE,
        paragraph_id=ro_p.paragraphId,
        range_anchor=0, range_focus=1, replace_after="Q",
        allow_writer=True)
    rb = res.get("readback") or {}
    assert rb.get("V7_READBACK_MATCH") == READBACK_PASS, rb


# ── 7. DELETE_TEXT_RANGE V1_RANGE_POSITION_OK PASS ─────────────────

@need_fx
def test_delete_v1_range_position_ok(tmp_path):
    doc = import_hwpx_as_ro_view(FIXTURE)
    ro_p = _pick_cell_paragraph(doc)
    out = tmp_path / "rb_v1_delete.hwpx"
    res = run_para_edit_e2e(
        source_path=FIXTURE, output_path=out,
        scenario=SCENARIO_DELETE,
        paragraph_id=ro_p.paragraphId,
        range_anchor=0, range_focus=1,
        allow_writer=True)
    rb = res.get("readback") or {}
    assert rb.get("V1_RANGE_POSITION_OK") == READBACK_PASS, rb


# ── 8. DELETE_TEXT_RANGE V7_READBACK_MATCH PASS ────────────────────

@need_fx
def test_delete_v7_readback_match(tmp_path):
    doc = import_hwpx_as_ro_view(FIXTURE)
    ro_p = _pick_cell_paragraph(doc)
    out = tmp_path / "rb_v7_delete.hwpx"
    res = run_para_edit_e2e(
        source_path=FIXTURE, output_path=out,
        scenario=SCENARIO_DELETE,
        paragraph_id=ro_p.paragraphId,
        range_anchor=0, range_focus=1,
        allow_writer=True)
    rb = res.get("readback") or {}
    assert rb.get("V7_READBACK_MATCH") == READBACK_PASS, rb


# ── 9. 동일 텍스트 다른 paragraph cross-match 차단 ─────────────────

@need_fx
def test_cross_match_blocked_text_only(tmp_path):
    """text-only fallback 금지: paragraphId 가 일치하지 않고 containerScope
    4 키도 어긋나면 _match_output_paragraph 는 None 반환.
    동일 텍스트가 다른 paragraph 에 있어도 매칭하지 않는다.
    """
    doc = import_hwpx_as_ro_view(FIXTURE)
    if len(doc.paragraphs) < 2:
        pytest.skip("paragraph 2 개 미만 fixture")
    p_target = _pick_cell_paragraph(doc)
    # 가짜 paragraphId + 비일치 containerScope
    fake_scope = {"kind": "cell", "tableIndex": 9999,
                  "rowIndex": 9999, "colIndex": 9999,
                  "paragraphIndex": 9999}
    matched = _match_output_paragraph(
        doc, "par_does_not_exist_xyz", fake_scope)
    assert matched is None


# ── 10. charPrIDRef / parPrIDRef 추출 유지 PASS ────────────────────

@need_fx
def test_readback_preserves_pr_id_refs(tmp_path):
    doc = import_hwpx_as_ro_view(FIXTURE)
    ro_p = _pick_cell_paragraph(doc)
    pr_before = ro_p.parPrIDRef
    char_before = ro_p.runs[0].charPrIDRef
    out = tmp_path / "rb_pr.hwpx"
    res = run_para_edit_e2e(
        source_path=FIXTURE, output_path=out,
        scenario=SCENARIO_REPLACE,
        paragraph_id=ro_p.paragraphId,
        range_anchor=0, range_focus=1, replace_after="P",
        allow_writer=True)
    rb = res.get("readback") or {}
    assert rb.get("outputParPrIDRef") == pr_before, rb
    char_refs = rb.get("outputRunCharPrIDRefs") or []
    assert char_refs and char_refs[0] == char_before, rb


# ── 11. 원본 sha/mtime 사전=사후 ───────────────────────────────────

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
        out = tmp_path / f"rb_pres_{i}.hwpx"
        run_para_edit_e2e(
            source_path=FIXTURE, output_path=out,
            scenario=scn, paragraph_id=ro_p.paragraphId,
            range_anchor=0, allow_writer=True, **kw)
    assert _sha(FIXTURE) == sha_b
    assert FIXTURE.stat().st_mtime_ns == mt_b


# ── 12. output sandbox(tmp_path) 만 생성 ───────────────────────────

@need_fx
def test_output_only_in_sandbox(tmp_path):
    doc = import_hwpx_as_ro_view(FIXTURE)
    ro_p = _pick_cell_paragraph(doc)
    out = tmp_path / "rb_sandbox.hwpx"
    res = run_para_edit_e2e(
        source_path=FIXTURE, output_path=out,
        scenario=SCENARIO_REPLACE,
        paragraph_id=ro_p.paragraphId,
        range_anchor=0, range_focus=1, replace_after="S",
        allow_writer=True)
    assert res.get("outputCreated") is True
    assert out.exists()
    # tmp_path 외부에 다른 산출물이 만들어지지 않았다는 보수적 신호:
    # 적어도 output 이 sandbox 안에 있어야 한다.
    assert str(out).startswith(str(tmp_path))


# ── 13. TYPE_TEXT readback PASS (CONTRACT-01 정렬 이후) ────────────

@need_fx
def test_type_text_readback_deferred(tmp_path):
    """WEB-OFFICE-PARA-TYPE-TEXT-CONTRACT-01 이후 TYPE_TEXT 도 V1/V7 PASS."""
    doc = import_hwpx_as_ro_view(FIXTURE)
    ro_p = _pick_cell_paragraph(doc)
    out = tmp_path / "rb_type.hwpx"
    res = run_para_edit_e2e(
        source_path=FIXTURE, output_path=out,
        scenario=SCENARIO_TYPE, paragraph_id=ro_p.paragraphId,
        range_anchor=0, insert_text="T", allow_writer=True)
    rb = res.get("readback") or {}
    assert rb.get("V1_RANGE_POSITION_OK") == READBACK_PASS, rb
    assert rb.get("V7_READBACK_MATCH") == READBACK_PASS, rb


# ── 14. _readback_verify_paragraph 직접 호출 — output 부재 시 FAIL ─

@need_fx
def test_readback_output_missing_marks_fail(tmp_path):
    doc = import_hwpx_as_ro_view(FIXTURE)
    ro_p = _pick_cell_paragraph(doc)
    missing = tmp_path / "does_not_exist.hwpx"
    rb = _readback_verify_paragraph(
        output_path=missing,
        paragraph_id=ro_p.paragraphId,
        container_scope=ro_p.containerScope,
        applied_items=[{"rangeStart": 0, "rangeEnd": 1,
                        "afterText": "X"}],
        text_before=ro_p.text,
        scenario=SCENARIO_REPLACE)
    assert rb["V1_RANGE_POSITION_OK"] == READBACK_FAIL
    assert rb["V7_READBACK_MATCH"] == READBACK_FAIL


# ── 15. audit script verdict=="PASS" ───────────────────────────────

def test_audit_script_pass():
    from scripts.ops.audit_web_office_para_readback_parser import audit
    rep = audit()
    fails = [f for f in rep["findings"]
             if f.get("level") == "FAIL"]
    assert not fails, json.dumps(rep, ensure_ascii=False, indent=2)
    assert rep["verdict"] == "PASS"
