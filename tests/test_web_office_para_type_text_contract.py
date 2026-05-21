"""WEB-OFFICE-PARA-TYPE-TEXT-CONTRACT-01 계약 테스트.

TYPE_TEXT command 의 expectedBefore 가 빈 range slice 기준으로 정렬되어
writer adapter 의 slice 계약과 일치함을 확인한다.
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
from scripts.hwpx.web_office.para_edit_model import (  # noqa: E402
    Paragraph, ParaTextRun, ParagraphTarget,
    make_type_text_command, make_replace_text_range_command,
    make_delete_text_range_command,
    apply_command_to_paragraph,
    validate_expected_before,
    CT_TYPE_TEXT, CT_DELETE_TEXT_RANGE)
from scripts.hwpx.web_office.paragraph_edit_plan import (  # noqa: E402
    build_dry_run_paragraph_plan, PARA_DRY_RUN_READY)
from scripts.hwpx.web_office.para_edit_e2e_pipeline import (  # noqa: E402
    run_para_edit_e2e, SCENARIO_TYPE, SCENARIO_REPLACE, SCENARIO_DELETE)


def _para(text: str = "abcde", pid: str = "par_x") -> Paragraph:
    return Paragraph(
        paragraphId=pid, parPrIDRef="0",
        runs=[ParaTextRun(runId=f"{pid}_run0", text=text,
                          charPrIDRef="7")])


def _target(pid: str = "par_x") -> ParagraphTarget:
    return ParagraphTarget(
        paragraphId=pid, containerKind="cell",
        containerId="cell_t0_r0_c0",
        sourceSha256="HASH",
        cellCoord={"table": 0, "row": 0, "col": 0},
        containerScope={"kind": "cell", "tableIndex": 0,
                        "rowIndex": 0, "colIndex": 0,
                        "paragraphIndex": 0, "runIndex": 0})


def test_type_text_expected_before_empty():
    p = _para()
    cmd = make_type_text_command(
        target=_target(), paragraph=p,
        caret_offset=2, insert_text="Z",
        source_document_hash="HASH",
        container_scope=_target().containerScope)
    assert cmd.expectedBefore == ""


def test_type_text_range_start_equals_end():
    p = _para()
    cmd = make_type_text_command(
        target=_target(), paragraph=p,
        caret_offset=3, insert_text="QQ",
        source_document_hash="HASH",
        container_scope=_target().containerScope)
    fwd = cmd.forward
    assert fwd["rangeStart"] == fwd["rangeEnd"] == 3
    assert fwd["rangeAnchor"] == fwd["rangeFocus"] == 3
    assert fwd["afterText"] == "QQ"
    assert fwd["insertText"] == "QQ"


def test_type_text_inverse_range_consistent():
    p = _para()
    cmd = make_type_text_command(
        target=_target(), paragraph=p,
        caret_offset=1, insert_text="abc",
        source_document_hash="HASH",
        container_scope=_target().containerScope)
    inv = cmd.inverse
    assert inv["kind"] == "DELETE_TEXT_RANGE"
    assert inv["rangeAnchor"] == 1
    assert inv["rangeFocus"] == 1 + len("abc")
    assert inv["deletedText"] == "abc"


def test_type_text_validate_expected_before():
    p = _para()
    cmd = make_type_text_command(
        target=_target(), paragraph=p,
        caret_offset=0, insert_text="X",
        source_document_hash="HASH",
        container_scope=_target().containerScope)
    assert validate_expected_before(cmd, p) is True
    # caret 범위 밖이면 reject
    cmd.forward["caretOffset"] = 999
    assert validate_expected_before(cmd, p) is False


def test_type_text_plan_validate_ready():
    p = _para()
    cmd = make_type_text_command(
        target=_target(), paragraph=p,
        caret_offset=2, insert_text="ZZ",
        source_document_hash="HASH",
        container_scope=_target().containerScope)
    res = build_dry_run_paragraph_plan(
        [cmd], {p.paragraphId: p}, "HASH")
    assert res["status"] == PARA_DRY_RUN_READY, res
    items = res["plan"]["paragraph_edits"]
    assert len(items) == 1
    it = items[0]
    assert it["commandType"] == CT_TYPE_TEXT
    assert it["expectedBefore"] == ""
    assert it["rangeStart"] == it["rangeEnd"] == 2
    assert it["afterText"] == "ZZ"


def test_replace_contract_unchanged():
    p = _para()
    cmd = make_replace_text_range_command(
        target=_target(), paragraph=p,
        range_anchor=0, range_focus=2, after_text="QQ",
        source_document_hash="HASH",
        container_scope=_target().containerScope)
    assert cmd.expectedBefore == "ab"
    assert cmd.forward["rangeAnchor"] == 0
    assert cmd.forward["rangeFocus"] == 2


def test_delete_contract_unchanged():
    p = _para()
    cmd = make_delete_text_range_command(
        target=_target(), paragraph=p,
        range_anchor=1, range_focus=3,
        source_document_hash="HASH",
        container_scope=_target().containerScope)
    assert cmd.expectedBefore == "bc"
    assert cmd.commandType == CT_DELETE_TEXT_RANGE


def test_type_text_apply_consistent_with_inverse():
    p = _para("hello")
    cmd = make_type_text_command(
        target=_target(), paragraph=p,
        caret_offset=2, insert_text="XX",
        source_document_hash="HASH",
        container_scope=_target().containerScope)
    after = apply_command_to_paragraph(p, cmd)
    assert after.text == "heXXllo"
    reverted = apply_command_to_paragraph(after, type(cmd)(
        commandId=cmd.commandId, commandType="DELETE_TEXT_RANGE",
        target=cmd.target, payload=cmd.payload,
        forward=cmd.inverse, inverse=cmd.forward,
        expectedBefore=cmd.expectedBefore,
        createdAt=cmd.createdAt,
        sourceDocumentHash=cmd.sourceDocumentHash,
        commandGroupId=cmd.commandGroupId,
        status=cmd.status))
    assert reverted.text == "hello"


# ── 동적 fixture 기반 E2E ───────────────────────────────────────

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


def _pick(doc):
    for p in doc.paragraphs:
        cs = p.containerScope or {}
        if (cs.get("kind") == "cell" and p.parPrIDRef
                and p.runs and p.runs[0].charPrIDRef
                and len(p.text or "") >= 2):
            return p
    return None


REQUIRED_V7 = ("V2_NO_CROSS_PARAGRAPH_LEAK",
                "V3_UNTOUCHED_RUNS_PRESERVED",
                "V4_CHARPR_PRESERVED", "V5_PARPR_PRESERVED",
                "V6_OUTPUT_ISOLATED")
REQUIRED_RB = ("V1_RANGE_POSITION_OK",
                "V4_CHARPR_PRESERVED", "V7_READBACK_MATCH")


@need_fx
def test_e2e_type_text_v1_to_v7_pass(tmp_path):
    doc = import_hwpx_as_ro_view(FIXTURE)
    ro_p = _pick(doc)
    out = tmp_path / "type_v17.hwpx"
    res = run_para_edit_e2e(
        source_path=FIXTURE, output_path=out,
        scenario=SCENARIO_TYPE, paragraph_id=ro_p.paragraphId,
        range_anchor=0, insert_text="T", allow_writer=True)
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


@need_fx
def test_e2e_replace_delete_regression_unchanged(tmp_path):
    """REPLACE / DELETE 기존 V1~V7 PASS 유지."""
    doc = import_hwpx_as_ro_view(FIXTURE)
    ro_p = _pick(doc)
    for scn, kw, name in [
        (SCENARIO_REPLACE, {"range_focus": 1, "replace_after": "R"},
          "replace"),
        (SCENARIO_DELETE, {"range_focus": 1}, "delete"),
    ]:
        out = tmp_path / f"reg_{name}.hwpx"
        res = run_para_edit_e2e(
            source_path=FIXTURE, output_path=out,
            scenario=scn, paragraph_id=ro_p.paragraphId,
            range_anchor=0, allow_writer=True, **kw)
        v7 = (res.get("verify7") or {}).get("results", {})
        for k in REQUIRED_V7:
            assert v7.get(k) == "PASS", (name, k, v7)
        rb = res.get("readback") or {}
        for k in REQUIRED_RB:
            assert rb.get(k) == "PASS", (name, k, rb)


@need_fx
def test_source_sha_mtime_preserved(tmp_path):
    sha_b = _sha(FIXTURE)
    mt_b = FIXTURE.stat().st_mtime_ns
    doc = import_hwpx_as_ro_view(FIXTURE)
    ro_p = _pick(doc)
    out = tmp_path / "type_pres.hwpx"
    run_para_edit_e2e(
        source_path=FIXTURE, output_path=out,
        scenario=SCENARIO_TYPE, paragraph_id=ro_p.paragraphId,
        range_anchor=0, insert_text="X", allow_writer=True)
    assert _sha(FIXTURE) == sha_b
    assert FIXTURE.stat().st_mtime_ns == mt_b


@need_fx
def test_type_text_output_in_sandbox(tmp_path):
    doc = import_hwpx_as_ro_view(FIXTURE)
    ro_p = _pick(doc)
    out = tmp_path / "type_sandbox.hwpx"
    res = run_para_edit_e2e(
        source_path=FIXTURE, output_path=out,
        scenario=SCENARIO_TYPE, paragraph_id=ro_p.paragraphId,
        range_anchor=0, insert_text="S", allow_writer=True)
    assert res.get("outputCreated") is True
    assert out.exists()
    assert str(out).startswith(str(tmp_path))


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


def test_audit_script_pass():
    from scripts.ops.audit_web_office_para_type_text_contract import (
        audit)
    rep = audit()
    fails = [f for f in rep["findings"]
              if f.get("level") == "FAIL"]
    assert not fails, json.dumps(rep, ensure_ascii=False, indent=2)
    assert rep["verdict"] in ("PASS", "WARN"), rep
