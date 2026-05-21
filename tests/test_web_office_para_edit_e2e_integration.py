"""WEB-OFFICE-PARA-EDIT-E2E-INTEGRATION-01 계약 테스트.

ro_view → state → command → plan → writer → verify7 → readback E2E
관통을 단일 fixture 기반으로 검증한다. writer 본 실행 회로 확장 없음,
모든 신규 코드는 호출만 수행 (§11-6).

부분 준공 사실 (baseline 81e86e9):
  - TYPE_TEXT: EditCommandV2.expectedBefore = paragraph.text 이고
    writer adapter 는 expectedBefore == rt[rangeStart:rangeEnd] 를
    요구 → caret=0 일 때 adapter 의 slice=""  mismatch.
    본 공정에서는 TYPE_TEXT 시나리오의 plan REJECTED 경로를 검증한다
    (정합 회로 — 다음 활성화 트리거: expectedBefore 계약 정렬).
  - V1_RANGE_POSITION_OK / V7_READBACK_MATCH:
    paragraph_save_verify7 의 paragraph readback parser 미지원 → FAIL.
  - V4_CHARPR_PRESERVED:
    paragraph_writer_adapter.applied 가 applyCharPrIDRef 를 적재하지
    않아 verify7 에서 None 으로 감지 → FAIL.
  - 위 V1/V4/V7 은 LOCKED 모듈 제약 — 본 공정에서 수정 금지 (§11-9).
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
from scripts.hwpx.web_office.para_edit_model import (  # noqa: E402
    ParagraphTarget,
    make_type_text_command, make_replace_text_range_command,
    make_delete_text_range_command)
from scripts.hwpx.web_office.paragraph_edit_plan import (  # noqa: E402
    build_dry_run_paragraph_plan)
from scripts.hwpx.web_office.paragraph_save_pipeline import (  # noqa: E402
    save_paragraph_edits, VERDICT_REJECTED)
from scripts.hwpx.web_office.para_edit_e2e_pipeline import (  # noqa: E402
    run_para_edit_e2e, _ro_paragraph_to_model, _build_target,
    SCENARIO_TYPE, SCENARIO_REPLACE, SCENARIO_DELETE)
from scripts.hwpx.web_office.paragraph_writer_adapter import (  # noqa: E402
    REASON_BODY_PARAGRAPH_NOT_SUPPORTED,
    REASON_MULTI_RUN_RANGE_NOT_SUPPORTED,
    REASON_RANGE_OUT_OF_BOUNDS)


# ── fixture 선정 ────────────────────────────────────────────────

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


def _doc():
    return import_hwpx_as_ro_view(FIXTURE)


def _pick_cell_paragraph(doc):
    for p in doc.paragraphs:
        cs = p.containerScope or {}
        if (cs.get("kind") == "cell" and p.parPrIDRef
                and p.runs and p.runs[0].charPrIDRef
                and len(p.text or "") >= 2):
            return p
    return None


REQUIRED_V_GATES = (
    "V2_NO_CROSS_PARAGRAPH_LEAK",
    "V3_UNTOUCHED_RUNS_PRESERVED",
    "V5_PARPR_PRESERVED",
    "V6_OUTPUT_ISOLATED",
)


# ── 1. RO-VIEW cell scope paragraph 1건 이상 추출 ────────────────

@need_fx
def test_ro_view_yields_cell_scope_paragraph():
    doc = _doc()
    cell_paras = [p for p in doc.paragraphs
                  if (p.containerScope or {}).get("kind") == "cell"]
    assert len(cell_paras) >= 1, "fixture 에 cell 단락 없음"


# ── 2. _ro_paragraph_to_model + _build_target containerScope 보존 ─

@need_fx
def test_build_target_preserves_container_scope():
    doc = _doc()
    ro_p = _pick_cell_paragraph(doc)
    assert ro_p is not None
    model_p = _ro_paragraph_to_model(ro_p)
    target = _build_target(ro_p, doc.sourceDocumentHash)
    assert target.containerScope == ro_p.containerScope
    assert model_p.paragraphId == ro_p.paragraphId
    assert model_p.parPrIDRef == ro_p.parPrIDRef


# ── 3. TYPE_TEXT command containerScope.kind=="cell" ─────────────

@need_fx
def test_type_text_command_container_scope_cell():
    doc = _doc()
    ro_p = _pick_cell_paragraph(doc)
    model_p = _ro_paragraph_to_model(ro_p)
    target = _build_target(ro_p, doc.sourceDocumentHash)
    cmd = make_type_text_command(
        target=target, paragraph=model_p,
        caret_offset=0, insert_text="Z",
        source_document_hash=doc.sourceDocumentHash,
        container_scope=target.containerScope)
    assert cmd.target["containerScope"]["kind"] == "cell"


# ── 4. REPLACE / DELETE containerScope 동일 ──────────────────────

@need_fx
def test_replace_delete_command_container_scope():
    doc = _doc()
    ro_p = _pick_cell_paragraph(doc)
    model_p = _ro_paragraph_to_model(ro_p)
    target = _build_target(ro_p, doc.sourceDocumentHash)
    rcmd = make_replace_text_range_command(
        target=target, paragraph=model_p,
        range_anchor=0, range_focus=1, after_text="Q",
        source_document_hash=doc.sourceDocumentHash,
        container_scope=target.containerScope)
    dcmd = make_delete_text_range_command(
        target=target, paragraph=model_p,
        range_anchor=0, range_focus=1,
        source_document_hash=doc.sourceDocumentHash,
        container_scope=target.containerScope)
    assert rcmd.target["containerScope"]["kind"] == "cell"
    assert dcmd.target["containerScope"]["kind"] == "cell"


# ── 5. dry-run plan: REPLACE 는 paragraph chain 검증 통과 ────────

@need_fx
def test_replace_dry_run_plan_chain_ok():
    """REPLACE_TEXT_RANGE 의 expectedBefore (slice) 는 paragraph chain
    검증에서 일치 — EXPECTED_BEFORE_MISMATCH_PARAGRAPH 없음.
    """
    doc = _doc()
    ro_p = _pick_cell_paragraph(doc)
    model_p = _ro_paragraph_to_model(ro_p)
    target = _build_target(ro_p, doc.sourceDocumentHash)
    cmd = make_replace_text_range_command(
        target=target, paragraph=model_p,
        range_anchor=0, range_focus=1, after_text="Q",
        source_document_hash=doc.sourceDocumentHash,
        container_scope=target.containerScope)
    res = build_dry_run_paragraph_plan(
        [cmd], {model_p.paragraphId: model_p},
        doc.sourceDocumentHash)
    bad = [r for r in (res.get("rejected") or [])
           if (r.get("reason") or "").startswith("EXPECTED_BEFORE")]
    assert not bad, res
    items = (res.get("plan") or {}).get("paragraph_edits", [])
    assert len(items) == 1
    assert items[0]["containerScope"]["kind"] == "cell"


# ── 6. REPLACE_TEXT_RANGE E2E: outputCreated + 필수 게이트 PASS ───

@need_fx
def test_e2e_replace_writer_path_required_gates(tmp_path):
    """REPLACE E2E — writer 본 실행 도달, V2/V3/V5/V6 PASS.
    V1/V4/V7 은 LOCKED 모듈 제약으로 부분 준공 (별도 트리거).
    """
    doc = _doc()
    ro_p = _pick_cell_paragraph(doc)
    out = tmp_path / "e2e_replace.hwpx"
    res = run_para_edit_e2e(
        source_path=FIXTURE, output_path=out,
        scenario=SCENARIO_REPLACE, paragraph_id=ro_p.paragraphId,
        range_anchor=0, range_focus=1, replace_after="Q",
        allow_writer=True)
    assert res.get("outputCreated") is True, res
    assert res.get("writerActivated") is True, res
    assert not res.get("rejected"), res
    gates = (res.get("verify7") or {}).get("results", {})
    for k in REQUIRED_V_GATES:
        assert gates.get(k) == "PASS", (k, gates)


# ── 7. DELETE_TEXT_RANGE E2E: outputCreated + 필수 게이트 PASS ────

@need_fx
def test_e2e_delete_writer_path_required_gates(tmp_path):
    doc = _doc()
    ro_p = _pick_cell_paragraph(doc)
    out = tmp_path / "e2e_delete.hwpx"
    res = run_para_edit_e2e(
        source_path=FIXTURE, output_path=out,
        scenario=SCENARIO_DELETE, paragraph_id=ro_p.paragraphId,
        range_anchor=0, range_focus=1, allow_writer=True)
    assert res.get("outputCreated") is True, res
    assert res.get("writerActivated") is True, res
    assert not res.get("rejected"), res
    gates = (res.get("verify7") or {}).get("results", {})
    for k in REQUIRED_V_GATES:
        assert gates.get(k) == "PASS", (k, gates)


# ── 8. TYPE_TEXT E2E: plan/expectedBefore 계약 gap 검증 ──────────

@need_fx
def test_e2e_type_text_partial_due_to_expected_before_contract(tmp_path):
    """WEB-OFFICE-PARA-TYPE-TEXT-CONTRACT-01: TYPE_TEXT expectedBefore 를
    빈 range slice 기준으로 정렬해 writer adapter 와 일치 → PASS.
    """
    doc = _doc()
    ro_p = _pick_cell_paragraph(doc)
    out = tmp_path / "e2e_type.hwpx"
    res = run_para_edit_e2e(
        source_path=FIXTURE, output_path=out,
        scenario=SCENARIO_TYPE, paragraph_id=ro_p.paragraphId,
        range_anchor=0, insert_text="E", allow_writer=True)
    assert res.get("outputCreated") is True, res
    assert res.get("writerActivated") is True, res
    assert not res.get("rejected"), res
    gates = (res.get("verify7") or {}).get("results", {})
    for k in REQUIRED_V_GATES:
        assert gates.get(k) == "PASS", (k, gates)


# ── 9. 3 시나리오 후 source sha + mtime 사전=사후 ─────────────────

@need_fx
def test_source_sha_and_mtime_preserved(tmp_path):
    sha_b = _sha(FIXTURE)
    mt_b = FIXTURE.stat().st_mtime_ns
    doc = _doc()
    ro_p = _pick_cell_paragraph(doc)
    for i, (scn, kw) in enumerate([
        (SCENARIO_TYPE, {"insert_text": "X"}),
        (SCENARIO_REPLACE, {"range_focus": 1, "replace_after": "Y"}),
        (SCENARIO_DELETE, {"range_focus": 1}),
    ]):
        out = tmp_path / f"e2e_pres_{i}.hwpx"
        run_para_edit_e2e(
            source_path=FIXTURE, output_path=out,
            scenario=scn, paragraph_id=ro_p.paragraphId,
            range_anchor=0, allow_writer=True, **kw)
    assert _sha(FIXTURE) == sha_b
    assert FIXTURE.stat().st_mtime_ns == mt_b


# ── 10. readback: REPLACE 후 output ro_view 재import → 변경 반영 ──

@need_fx
def test_e2e_replace_readback_reflects_change(tmp_path):
    doc = _doc()
    ro_p = _pick_cell_paragraph(doc)
    out = tmp_path / "e2e_readback.hwpx"
    res = run_para_edit_e2e(
        source_path=FIXTURE, output_path=out,
        scenario=SCENARIO_REPLACE, paragraph_id=ro_p.paragraphId,
        range_anchor=0, range_focus=1, replace_after="RB",
        allow_writer=True)
    assert res.get("outputCreated") is True
    out_doc = import_hwpx_as_ro_view(out)
    out_p = next((p for p in out_doc.paragraphs
                  if p.paragraphId == ro_p.paragraphId), None)
    assert out_p is not None
    # 첫 글자가 "RB" 로 치환되어 있어야 한다
    assert out_p.text.startswith("RB"), (out_p.text, ro_p.text)


# ── 11. TARGET_PARAGRAPH_NOT_FOUND 회로 ──────────────────────────

@need_fx
def test_unknown_paragraph_rejected(tmp_path):
    out = tmp_path / "e2e_unknown.hwpx"
    res = run_para_edit_e2e(
        source_path=FIXTURE, output_path=out,
        scenario=SCENARIO_REPLACE, paragraph_id="par_unknown_xyz",
        range_anchor=0, range_focus=1, replace_after="X",
        allow_writer=True)
    assert res["verdict"] == VERDICT_REJECTED
    reasons = {r.get("reason") for r in res.get("rejected") or []}
    assert "TARGET_PARAGRAPH_NOT_FOUND" in reasons, res


# ── 12. outputPath == sourcePath → REJECTED (OUTPUT_EQUALS_SOURCE) ─

@need_fx
def test_output_equals_source_rejected():
    doc = _doc()
    ro_p = _pick_cell_paragraph(doc)
    res = run_para_edit_e2e(
        source_path=FIXTURE, output_path=FIXTURE,
        scenario=SCENARIO_REPLACE, paragraph_id=ro_p.paragraphId,
        range_anchor=0, range_focus=1, replace_after="X",
        allow_writer=True)
    assert res["verdict"] == VERDICT_REJECTED
    reasons = {r.get("reason") for r in res.get("rejected") or []}
    assert "OUTPUT_EQUALS_SOURCE" in reasons, res


# ── 13. body paragraph 회로 — section 미존재 시 SECTION_NOT_FOUND ───

@need_fx
def test_body_paragraph_invalid_section_rejected(tmp_path):
    """WEB-OFFICE-BODY-PARAGRAPH-WRITER-01: body scope 가 활성화된 이후,
    sectionIndex 가 존재하지 않으면 SECTION_NOT_FOUND 로 reject 된다.
    """
    doc = _doc()
    ro_p = _pick_cell_paragraph(doc)
    body_scope = {
        "kind": "block", "sectionIndex": 9999, "blockIndex": 0,
        "paragraphIndex": 0,
    }
    model_p = _ro_paragraph_to_model(ro_p)
    target = ParagraphTarget(
        paragraphId=ro_p.paragraphId, containerKind="block",
        containerId=ro_p.paragraphId,
        sourceSha256=doc.sourceDocumentHash,
        containerScope=body_scope)
    cmd = make_replace_text_range_command(
        target=target, paragraph=model_p,
        range_anchor=0, range_focus=1, after_text="X",
        source_document_hash=doc.sourceDocumentHash,
        container_scope=body_scope)
    out = tmp_path / "e2e_body.hwpx"
    res = save_paragraph_edits(
        source_path=FIXTURE, output_path=out,
        command_log=[cmd],
        paragraphs_by_id={model_p.paragraphId: model_p},
        source_document_hash=doc.sourceDocumentHash,
        allow_writer=True)
    reasons = {r.get("reason") for r in res.get("rejected") or []}
    assert "SECTION_NOT_FOUND" in reasons, res
    # body scope 자체로는 더 이상 reject 되지 않는다 — section 미존재만 사유.
    assert REASON_BODY_PARAGRAPH_NOT_SUPPORTED not in reasons, res


# ── 14. multi-run range → MULTI_RUN_RANGE_NOT_SUPPORTED 등 reject ─

@need_fx
def test_multi_run_range_rejected(tmp_path):
    doc = _doc()
    ro_p = _pick_cell_paragraph(doc)
    if len(ro_p.runs) < 2:
        pytest.skip("fixture cell paragraph 가 multi-run 이 아님")
    first_run_len = len(ro_p.runs[0].text)
    over = first_run_len + 1
    out = tmp_path / "e2e_multi.hwpx"
    res = run_para_edit_e2e(
        source_path=FIXTURE, output_path=out,
        scenario=SCENARIO_REPLACE, paragraph_id=ro_p.paragraphId,
        range_anchor=0, range_focus=over, replace_after="Z",
        allow_writer=True)
    reasons = {r.get("reason") for r in res.get("rejected") or []}
    accepted_reject_codes = {
        REASON_MULTI_RUN_RANGE_NOT_SUPPORTED,
        REASON_RANGE_OUT_OF_BOUNDS,
        "EXPECTED_BEFORE_MISMATCH",
        "EXPECTED_BEFORE_MISMATCH_PARAGRAPH",
    }
    assert (reasons & accepted_reject_codes), res


# ── 15. audit script verdict=="PASS" ─────────────────────────────

def test_audit_script_pass():
    from scripts.ops.audit_web_office_para_edit_e2e_integration import (
        audit)
    rep = audit()
    fails = [f for f in rep["findings"]
             if f.get("level") == "FAIL"]
    assert not fails, json.dumps(rep, ensure_ascii=False, indent=2)
    assert rep["verdict"] == "PASS"
