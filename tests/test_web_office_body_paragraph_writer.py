"""WEB-OFFICE-BODY-PARAGRAPH-WRITER-01 감리 검사.

containerScope.kind="block" + 단일 run 범위 body paragraph 가 TYPE_TEXT
/ REPLACE_TEXT_RANGE / DELETE_TEXT_RANGE 시나리오에서 V1~V7 PASS 되는지,
관련 reject 회로 (SECTION_NOT_FOUND, multi-run, expectedBefore mismatch,
sourceHash mismatch, outputPath==sourcePath) 가 정상 동작하는지 확인.
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
    run_para_edit_e2e, _ro_paragraph_to_model, _build_target,
    SCENARIO_TYPE, SCENARIO_REPLACE, SCENARIO_DELETE)
from scripts.hwpx.web_office.paragraph_writer_adapter import (  # noqa: E402
    REASON_BODY_PARAGRAPH_NOT_SUPPORTED,
    REASON_SECTION_NOT_FOUND,
    REASON_MULTI_RUN_RANGE_NOT_SUPPORTED,
    _resolve_body_paragraph,
)


REQUIRED_V7 = ("V2_NO_CROSS_PARAGRAPH_LEAK",
                "V3_UNTOUCHED_RUNS_PRESERVED",
                "V4_CHARPR_PRESERVED", "V5_PARPR_PRESERVED",
                "V6_OUTPUT_ISOLATED")
REQUIRED_RB = ("V1_RANGE_POSITION_OK",
                "V4_CHARPR_PRESERVED", "V7_READBACK_MATCH")


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _pick_body_fixture():
    db = PR / "data/recognition_corpus/corpus.sqlite3"
    if not db.is_file():
        return None, None
    try:
        conn = sqlite3.connect(db)
        rows = conn.execute("""
            SELECT d.source_path FROM hwpx_documents d
            WHERE d.inventory_status='FOUND'
            ORDER BY d.first_seen_at LIMIT 200
        """).fetchall()
        conn.close()
    except sqlite3.Error:
        return None, None
    for (sp,) in rows:
        p = PR / sp
        if not p.is_file():
            continue
        try:
            doc = import_hwpx_as_ro_view(p)
        except Exception:  # noqa: BLE001
            continue
        for par in doc.paragraphs:
            sc = par.containerScope or {}
            if (sc.get("kind") == "block" and par.parPrIDRef
                    and par.runs and par.runs[0].charPrIDRef
                    and len(par.runs) == 1
                    and len(par.text or "") >= 3):
                return p, par
    return None, None


FIXTURE, BODY_PARAGRAPH = _pick_body_fixture()
need_fx = pytest.mark.skipif(
    FIXTURE is None, reason="no single-run body fixture")


# ── 1. body paragraph containerScope 추출 ──────────────────────

@need_fx
def test_body_paragraph_container_scope_extracted():
    sc = BODY_PARAGRAPH.containerScope
    assert sc["kind"] == "block"
    assert "sectionIndex" in sc
    assert "blockIndex" in sc
    assert "paragraphIndex" in sc
    assert len(BODY_PARAGRAPH.runs) == 1
    assert BODY_PARAGRAPH.parPrIDRef is not None
    assert BODY_PARAGRAPH.runs[0].charPrIDRef is not None


# ── 2. body paragraph 3 시나리오 V1~V7 PASS ─────────────────────

@need_fx
def test_body_type_text_v1_to_v7(tmp_path):
    out = tmp_path / "body_type.hwpx"
    res = run_para_edit_e2e(
        source_path=FIXTURE, output_path=out,
        scenario=SCENARIO_TYPE,
        paragraph_id=BODY_PARAGRAPH.paragraphId,
        range_anchor=0, insert_text="Z", allow_writer=True)
    assert res.get("outputCreated") is True, res
    assert res.get("writerActivated") is True, res
    assert not res.get("rejected"), res
    v7 = (res.get("verify7") or {}).get("results", {})
    for k in REQUIRED_V7:
        assert v7.get(k) == "PASS", (k, v7)
    rb = res.get("readback") or {}
    for k in REQUIRED_RB:
        assert rb.get(k) == "PASS", (k, rb)


@need_fx
def test_body_replace_text_range_v1_to_v7(tmp_path):
    out = tmp_path / "body_replace.hwpx"
    res = run_para_edit_e2e(
        source_path=FIXTURE, output_path=out,
        scenario=SCENARIO_REPLACE,
        paragraph_id=BODY_PARAGRAPH.paragraphId,
        range_anchor=0, range_focus=2, replace_after="RR",
        allow_writer=True)
    assert res.get("outputCreated") is True, res
    assert not res.get("rejected"), res
    v7 = (res.get("verify7") or {}).get("results", {})
    for k in REQUIRED_V7:
        assert v7.get(k) == "PASS", (k, v7)
    rb = res.get("readback") or {}
    for k in REQUIRED_RB:
        assert rb.get(k) == "PASS", (k, rb)


@need_fx
def test_body_delete_text_range_v1_to_v7(tmp_path):
    out = tmp_path / "body_delete.hwpx"
    res = run_para_edit_e2e(
        source_path=FIXTURE, output_path=out,
        scenario=SCENARIO_DELETE,
        paragraph_id=BODY_PARAGRAPH.paragraphId,
        range_anchor=0, range_focus=2,
        allow_writer=True)
    assert res.get("outputCreated") is True, res
    assert not res.get("rejected"), res
    v7 = (res.get("verify7") or {}).get("results", {})
    for k in REQUIRED_V7:
        assert v7.get(k) == "PASS", (k, v7)
    rb = res.get("readback") or {}
    for k in REQUIRED_RB:
        assert rb.get(k) == "PASS", (k, rb)


# ── 3. 안전 게이트 ────────────────────────────────────────────

@need_fx
def test_body_expected_before_mismatch_rejected(tmp_path):
    """REPLACE 범위 안의 expectedBefore 와 다른 텍스트로 직접 위조 →
    plan validate 단계에서 EXPECTED_BEFORE_MISMATCH_PARAGRAPH reject.
    """
    from scripts.hwpx.web_office.para_edit_model import (
        make_replace_text_range_command)
    from scripts.hwpx.web_office.paragraph_save_pipeline import (
        save_paragraph_edits)

    doc = import_hwpx_as_ro_view(FIXTURE)
    ro_p = next(p for p in doc.paragraphs
                  if p.paragraphId == BODY_PARAGRAPH.paragraphId)
    model_p = _ro_paragraph_to_model(ro_p)
    target = _build_target(ro_p, doc.sourceDocumentHash)
    cmd = make_replace_text_range_command(
        target=target, paragraph=model_p,
        range_anchor=0, range_focus=2, after_text="QQ",
        source_document_hash=doc.sourceDocumentHash,
        container_scope=target.containerScope)
    # expectedBefore 위조
    cmd.expectedBefore = "WRONG"
    out = tmp_path / "body_mismatch.hwpx"
    res = save_paragraph_edits(
        source_path=FIXTURE, output_path=out, command_log=[cmd],
        paragraphs_by_id={model_p.paragraphId: model_p},
        source_document_hash=doc.sourceDocumentHash,
        allow_writer=True)
    reasons = {r.get("reason") for r in res.get("rejected") or []}
    assert "EXPECTED_BEFORE_MISMATCH_PARAGRAPH" in reasons, res


@need_fx
def test_body_source_hash_mismatch_rejected(tmp_path):
    from scripts.hwpx.web_office.para_edit_model import (
        make_type_text_command)
    from scripts.hwpx.web_office.paragraph_save_pipeline import (
        save_paragraph_edits)
    doc = import_hwpx_as_ro_view(FIXTURE)
    ro_p = next(p for p in doc.paragraphs
                  if p.paragraphId == BODY_PARAGRAPH.paragraphId)
    model_p = _ro_paragraph_to_model(ro_p)
    target = _build_target(ro_p, "WRONG_HASH")
    cmd = make_type_text_command(
        target=target, paragraph=model_p,
        caret_offset=0, insert_text="X",
        source_document_hash="WRONG_HASH",
        container_scope=target.containerScope)
    out = tmp_path / "body_badhash.hwpx"
    res = save_paragraph_edits(
        source_path=FIXTURE, output_path=out, command_log=[cmd],
        paragraphs_by_id={model_p.paragraphId: model_p},
        source_document_hash=doc.sourceDocumentHash,
        allow_writer=True)
    reasons = {r.get("reason") for r in res.get("rejected") or []}
    assert any("SOURCE_HASH" in r or "HASH_MISMATCH" in r
                  for r in reasons), res


@need_fx
def test_body_output_equals_source_rejected():
    res = run_para_edit_e2e(
        source_path=FIXTURE, output_path=FIXTURE,
        scenario=SCENARIO_TYPE,
        paragraph_id=BODY_PARAGRAPH.paragraphId,
        range_anchor=0, insert_text="X", allow_writer=True)
    reasons = {r.get("reason") for r in res.get("rejected") or []}
    assert "OUTPUT_EQUALS_SOURCE" in reasons, res


@need_fx
def test_body_section_not_found_rejected(tmp_path):
    """body scope 가 활성화된 이후, sectionIndex 부재 시
    SECTION_NOT_FOUND 로 reject — BODY_PARAGRAPH_NOT_SUPPORTED 아님."""
    from scripts.hwpx.hwpx_package import HwpxPackage
    from scripts.hwpx.web_office.paragraph_writer_adapter import (
        apply_paragraph_edits_plan)
    pkg = HwpxPackage(FIXTURE)
    item = {
        "commandId": "c", "paragraphId": "par_x", "runId": "par_x_run0",
        "rangeStart": 0, "rangeEnd": 0,
        "rangeAnchor": 0, "rangeFocus": 0,
        "afterText": "X", "expectedBefore": "",
        "commandType": "TYPE_TEXT",
        "applyCharPrIDRef": None,
        "sourceDocumentHash": _sha(FIXTURE),
        "containerScope": {"kind": "block", "sectionIndex": 9999,
                                              "blockIndex": 0,
                                              "paragraphIndex": 0,
                                              "runIndex": 0},
    }
    res = apply_paragraph_edits_plan(
        pkg, [item], source_document_hash=_sha(FIXTURE), dry_run=True)
    reasons = {r.get("reason") for r in res.get("rejected", [])}
    assert REASON_SECTION_NOT_FOUND in reasons, res
    assert REASON_BODY_PARAGRAPH_NOT_SUPPORTED not in reasons, res


@need_fx
def test_body_original_sha_mtime_preserved(tmp_path):
    sha_b = _sha(FIXTURE)
    mt_b = FIXTURE.stat().st_mtime_ns
    for scn, kw in [
        (SCENARIO_TYPE, {"insert_text": "T"}),
        (SCENARIO_REPLACE, {"range_focus": 2, "replace_after": "R"}),
        (SCENARIO_DELETE, {"range_focus": 2}),
    ]:
        out = tmp_path / f"body_pres_{scn}.hwpx"
        run_para_edit_e2e(
            source_path=FIXTURE, output_path=out, scenario=scn,
            paragraph_id=BODY_PARAGRAPH.paragraphId,
            range_anchor=0, allow_writer=True, **kw)
    assert _sha(FIXTURE) == sha_b
    assert FIXTURE.stat().st_mtime_ns == mt_b


@need_fx
def test_body_output_in_sandbox(tmp_path):
    out = tmp_path / "body_sandbox.hwpx"
    res = run_para_edit_e2e(
        source_path=FIXTURE, output_path=out,
        scenario=SCENARIO_TYPE,
        paragraph_id=BODY_PARAGRAPH.paragraphId,
        range_anchor=0, insert_text="S", allow_writer=True)
    assert res.get("outputCreated") is True
    assert out.exists()
    assert str(out).startswith(str(tmp_path))


# ── 4. multi-run reject 유지 (body 에도 적용) ────────────────

@need_fx
def test_body_multi_run_still_rejected_or_oob(tmp_path):
    """body paragraph 에 paragraph 전체 길이를 초과하는 범위 → reject.
    multi-run / out-of-bounds 중 하나로 떨어져야 한다.
    """
    text_len = len(BODY_PARAGRAPH.text or "")
    out = tmp_path / "body_oob.hwpx"
    res = run_para_edit_e2e(
        source_path=FIXTURE, output_path=out,
        scenario=SCENARIO_REPLACE,
        paragraph_id=BODY_PARAGRAPH.paragraphId,
        range_anchor=0, range_focus=text_len + 5, replace_after="Z",
        allow_writer=True)
    reasons = {r.get("reason") for r in res.get("rejected") or []}
    assert reasons & {
        REASON_MULTI_RUN_RANGE_NOT_SUPPORTED,
        "RANGE_OUT_OF_BOUNDS",
        "EXPECTED_BEFORE_MISMATCH",
        "EXPECTED_BEFORE_MISMATCH_PARAGRAPH",
    }, res


# ── 5. _resolve_body_paragraph 직접 호출 ────────────────────

@need_fx
def test_resolve_body_paragraph_direct():
    from scripts.hwpx.hwpx_package import HwpxPackage
    pkg = HwpxPackage(FIXTURE)
    sc = BODY_PARAGRAPH.containerScope
    resolved, err = _resolve_body_paragraph(
        pkg, sc["sectionIndex"], sc["blockIndex"])
    assert err is None, err
    entry, root, p_elem = resolved
    assert entry
    assert p_elem is not None
    tag = (p_elem.tag.rsplit("}", 1)[-1]
              if "}" in p_elem.tag else p_elem.tag).lower()
    assert tag == "p"


# ── 6. paragraph add/delete 미지원 — UNSUPPORTED_COMMAND_TYPE ─

@need_fx
def test_paragraph_add_delete_still_unsupported(tmp_path):
    """ADD_PARAGRAPH 등 새 commandType 은 미지원."""
    from scripts.hwpx.hwpx_package import HwpxPackage
    from scripts.hwpx.web_office.paragraph_writer_adapter import (
        apply_paragraph_edits_plan)
    pkg = HwpxPackage(FIXTURE)
    item = {
        "commandId": "c", "paragraphId": "x",
        "rangeStart": 0, "rangeEnd": 0,
        "afterText": "", "expectedBefore": "",
        "commandType": "ADD_PARAGRAPH",
        "sourceDocumentHash": _sha(FIXTURE),
        "containerScope": dict(BODY_PARAGRAPH.containerScope),
    }
    res = apply_paragraph_edits_plan(
        pkg, [item], source_document_hash=_sha(FIXTURE), dry_run=True)
    reasons = {r.get("reason") for r in res.get("rejected", [])}
    assert "UNSUPPORTED_COMMAND_TYPE" in reasons, res


# ── 7. audit verdict PASS ─────────────────────────────────────

def test_audit_script_pass():
    from scripts.ops.audit_web_office_body_paragraph_writer import audit
    rep = audit()
    fails = [f for f in rep["findings"]
              if f.get("level") == "FAIL"]
    assert not fails, json.dumps(rep, ensure_ascii=False, indent=2)
    assert rep["verdict"] in ("PASS", "WARN"), rep
