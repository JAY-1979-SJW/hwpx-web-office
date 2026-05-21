"""WRITER-PARA-PLAN-01 계약 테스트.

apply_edit_plan 에 paragraph_edits intake 가 추가되었는지,
paragraph_save_pipeline 의 BLOCKED_NO_PARAGRAPH_WRITER_SUPPORT
분기가 해제되었는지, 단일 run 셀 내부 paragraph TYPE/REPLACE/DELETE
가 본 실행되어 sandbox output 에 정확히 반영되는지 검증.
"""
from __future__ import annotations
import hashlib
import sqlite3
import sys
import zipfile
from pathlib import Path
import pytest
import xml.etree.ElementTree as ET

PR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PR))
sys.path.insert(0, str(PR / "scripts/hwpx"))

from scripts.hwpx import hwpx_edit_tool as _edit_tool  # noqa: E402
from scripts.hwpx.hwpx_package import HwpxPackage, local_name  # noqa: E402
from scripts.hwpx.web_office.paragraph_writer_adapter import (  # noqa: E402
    apply_paragraph_edits_plan,
)
from scripts.hwpx.web_office.ro_view_importer import (  # noqa: E402
    import_hwpx_as_ro_view,
)
from scripts.hwpx.web_office import (  # noqa: E402
    paragraph_save_pipeline as _para_pipe,
)
from scripts.hwpx.web_office import cell_save_pipeline as _cell_pipe  # noqa


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _fixture() -> Path | None:
    db = PR / "data/recognition_corpus/corpus.sqlite3"
    if not db.is_file():
        return None
    conn = sqlite3.connect(db)
    row = conn.execute("""
        SELECT d.source_path FROM hwpx_documents d
        JOIN document_classifications c ON c.document_id=d.document_id
        WHERE d.inventory_status='FOUND'
          AND c.document_type='fillable_form'
          AND d.file_size BETWEEN 30000 AND 80000
        ORDER BY d.first_seen_at LIMIT 1
    """).fetchone()
    conn.close()
    return (PR / row[0]) if row and (PR / row[0]).is_file() else None


FIXTURE = _fixture()
need_fx = pytest.mark.skipif(FIXTURE is None, reason="fixture missing")


# ── helpers ────────────────────────────────────────────────────

def _src_sha() -> str:
    return _sha(FIXTURE)


def _find_first_nonempty_cell_para():
    """fixture 에서 단일 run, 비어 있지 않은 cell paragraph 의 좌표 + 텍스트 반환.

    Returns
    -------
    (tableIndex, rowIndex, colIndex, paragraphIndex, runIndex, text,
     charPrIDRef, paraPrIDRef)
    """
    package = HwpxPackage(FIXTURE)
    ti = 0
    for entry in package.section_entries():
        root = package.read_xml(entry)
        tables = [e for e in root.iter()
                          if local_name(e.tag).lower() == "tbl"
                              or local_name(e.tag).lower() == "table"
                              or "tbl" in local_name(e.tag).lower()]
        for tbl in tables:
            rows = [r for r in list(tbl)
                          if local_name(r.tag).lower() in {"tr", "row"}
                              or local_name(r.tag).lower().endswith("tr")]
            for ri, row in enumerate(rows):
                cells = [c for c in list(row)
                                if local_name(c.tag).lower() in {"tc", "cell"}
                                or local_name(c.tag).lower().endswith("tc")
                                or "cell" in local_name(c.tag).lower()]
                for ci, cell in enumerate(cells):
                    paras = [p for p in cell.iter()
                                  if local_name(p.tag).lower() == "p"]
                    for pi, para in enumerate(paras):
                        runs = [rr for rr in para.iter()
                                      if local_name(rr.tag).lower() == "run"]
                        if not runs:
                            continue
                        run0 = runs[0]
                        tnodes = [n for n in run0.iter()
                                          if local_name(n.tag).lower() == "t"]
                        if not tnodes or not (tnodes[0].text or ""):
                            continue
                        return {
                            "tableIndex": ti, "rowIndex": ri,
                            "colIndex": ci, "paragraphIndex": pi,
                            "runIndex": 0,
                            "text": tnodes[0].text,
                            "charPrIDRef": run0.attrib.get("charPrIDRef"),
                            "paraPrIDRef": para.attrib.get("paraPrIDRef"),
                        }
            ti += 1
    raise RuntimeError("no single-run nonempty cell paragraph found")


def _readback(out_path: Path, ti: int, ri: int, ci: int, pi: int):
    """sandbox output 의 (ti,ri,ci) cell 의 pi 번째 paragraph 정보 읽기."""
    pkg = HwpxPackage(out_path)
    table_count = 0
    for entry in pkg.section_entries():
        root = pkg.read_xml(entry)
        for tbl in [e for e in root.iter()
                              if local_name(e.tag).lower() == "tbl"
                                  or "tbl" in local_name(e.tag).lower()
                                  or local_name(e.tag).lower() == "table"]:
            if table_count != ti:
                table_count += 1
                continue
            rows = [r for r in list(tbl)
                          if local_name(r.tag).lower() in {"tr", "row"}
                              or local_name(r.tag).lower().endswith("tr")]
            row = rows[ri]
            cells = [c for c in list(row)
                          if local_name(c.tag).lower() in {"tc", "cell"}
                              or local_name(c.tag).lower().endswith("tc")
                              or "cell" in local_name(c.tag).lower()]
            cell = cells[ci]
            paras = [p for p in cell.iter()
                              if local_name(p.tag).lower() == "p"]
            para = paras[pi]
            runs = [rr for rr in para.iter()
                          if local_name(rr.tag).lower() == "run"]
            tnodes = [n for n in runs[0].iter()
                              if local_name(n.tag).lower() == "t"]
            return {
                "text": tnodes[0].text if tnodes else "",
                "charPrIDRef": runs[0].attrib.get("charPrIDRef"),
                "paraPrIDRef": para.attrib.get("paraPrIDRef"),
            }
    raise AssertionError("readback: table not found")


def _plan_item(*, fx, command_type: str, range_start: int,
               range_end: int, expected_before: str,
               after_text: str, source_hash: str,
               command_id: str = "cmd-1",
               source_hash_override: str | None = None) -> dict:
    return {
        "commandId": command_id,
        "paragraphId": f"par_t0_r{fx['rowIndex']}_c{fx['colIndex']}_p0",
        "runId": "run-0",
        "rangeStart": range_start,
        "rangeEnd": range_end,
        "expectedBefore": expected_before,
        "afterText": after_text,
        "sourceDocumentHash": source_hash_override or source_hash,
        "commandType": command_type,
        "containerScope": {
            "kind": "cell",
            "tableIndex": fx["tableIndex"],
            "rowIndex": fx["rowIndex"],
            "colIndex": fx["colIndex"],
            "paragraphIndex": fx["paragraphIndex"],
            "runIndex": fx["runIndex"],
        },
        "applyCharPrIDRef": fx["charPrIDRef"],
    }


# ── 1. set_cells-only plan 회귀 (paragraph_edits 분기 미진입) ───

@need_fx
def test_set_cells_only_plan_regression(tmp_path):
    plan = {"set_cells": [
        {"table": 0, "row": 3, "col": 0, "value": "REG_T1"},
    ]}
    out = tmp_path / "reg.hwpx"
    src_sha_before = _src_sha()
    res = _edit_tool.apply_edit_plan(FIXTURE, out, plan, dry_run=False)
    kinds = {op.get("kind") for op in res["operations"]
                  if isinstance(op, dict)}
    assert "paragraph_edits" not in kinds
    assert _src_sha() == src_sha_before


# ── 2. dry_run=True PASS — applied=1, output 미생성 ────────────

@need_fx
def test_paragraph_edits_dry_run_pass(tmp_path):
    fx = _find_first_nonempty_cell_para()
    src_hash = _src_sha()
    item = _plan_item(
        fx=fx, command_type="TYPE_TEXT",
        range_start=0, range_end=0,
        expected_before="", after_text="X",
        source_hash=src_hash)
    plan = {"paragraph_edits": [item]}
    out = tmp_path / "dry.hwpx"
    res = _edit_tool.apply_edit_plan(FIXTURE, out, plan, dry_run=True)
    para_op = next(op for op in res["operations"]
                            if op.get("kind") == "paragraph_edits")
    assert para_op["applied"], para_op
    assert not para_op["rejected"]
    assert all(a.get("dryRun") for a in para_op["applied"])
    assert not out.exists()


# ── 3. TYPE_TEXT 본 실행 PASS ─────────────────────────────────

@need_fx
def test_type_text_apply_pass(tmp_path):
    fx = _find_first_nonempty_cell_para()
    src_hash = _src_sha()
    src_sha_before = src_hash
    item = _plan_item(
        fx=fx, command_type="TYPE_TEXT",
        range_start=0, range_end=0,
        expected_before="", after_text="ZZ_",
        source_hash=src_hash)
    plan = {"paragraph_edits": [item]}
    out = tmp_path / "type.hwpx"
    res = _edit_tool.apply_edit_plan(FIXTURE, out, plan, dry_run=False)
    para_op = next(op for op in res["operations"]
                            if op.get("kind") == "paragraph_edits")
    assert para_op["applied"], para_op
    assert not para_op["rejected"], para_op
    rb = _readback(out, fx["tableIndex"], fx["rowIndex"],
                          fx["colIndex"], fx["paragraphIndex"])
    assert rb["text"].startswith("ZZ_"), rb
    assert _src_sha() == src_sha_before


# ── 4. REPLACE_TEXT_RANGE 본 실행 PASS ─────────────────────────

@need_fx
def test_replace_text_range_apply_pass(tmp_path):
    fx = _find_first_nonempty_cell_para()
    src_hash = _src_sha()
    n = min(2, len(fx["text"]))
    item = _plan_item(
        fx=fx, command_type="REPLACE_TEXT_RANGE",
        range_start=0, range_end=n,
        expected_before=fx["text"][:n],
        after_text="RPLC",
        source_hash=src_hash)
    plan = {"paragraph_edits": [item]}
    out = tmp_path / "rpl.hwpx"
    res = _edit_tool.apply_edit_plan(FIXTURE, out, plan, dry_run=False)
    para_op = next(op for op in res["operations"]
                            if op.get("kind") == "paragraph_edits")
    assert para_op["applied"] and not para_op["rejected"], para_op
    rb = _readback(out, fx["tableIndex"], fx["rowIndex"],
                          fx["colIndex"], fx["paragraphIndex"])
    assert rb["text"] == "RPLC" + fx["text"][n:]


# ── 5. DELETE_TEXT_RANGE 본 실행 PASS ──────────────────────────

@need_fx
def test_delete_text_range_apply_pass(tmp_path):
    fx = _find_first_nonempty_cell_para()
    src_hash = _src_sha()
    n = min(1, len(fx["text"]))
    item = _plan_item(
        fx=fx, command_type="DELETE_TEXT_RANGE",
        range_start=0, range_end=n,
        expected_before=fx["text"][:n], after_text="",
        source_hash=src_hash)
    plan = {"paragraph_edits": [item]}
    out = tmp_path / "del.hwpx"
    res = _edit_tool.apply_edit_plan(FIXTURE, out, plan, dry_run=False)
    para_op = next(op for op in res["operations"]
                            if op.get("kind") == "paragraph_edits")
    assert para_op["applied"] and not para_op["rejected"], para_op
    rb = _readback(out, fx["tableIndex"], fx["rowIndex"],
                          fx["colIndex"], fx["paragraphIndex"])
    assert rb["text"] == fx["text"][n:]


# ── 6. expectedBefore mismatch reject ─────────────────────────

@need_fx
def test_expected_before_mismatch_reject(tmp_path):
    fx = _find_first_nonempty_cell_para()
    src_hash = _src_sha()
    item = _plan_item(
        fx=fx, command_type="REPLACE_TEXT_RANGE",
        range_start=0, range_end=1,
        expected_before="__never_matches__",
        after_text="X", source_hash=src_hash)
    plan = {"paragraph_edits": [item]}
    out = tmp_path / "ebm.hwpx"
    res = _edit_tool.apply_edit_plan(FIXTURE, out, plan, dry_run=False)
    para_op = next(op for op in res["operations"]
                            if op.get("kind") == "paragraph_edits")
    assert not para_op["applied"]
    assert any(r.get("reason") == "EXPECTED_BEFORE_MISMATCH"
                      for r in para_op["rejected"]), para_op


# ── 7. rangeOOB reject ────────────────────────────────────────

@need_fx
def test_range_oob_reject(tmp_path):
    fx = _find_first_nonempty_cell_para()
    src_hash = _src_sha()
    item = _plan_item(
        fx=fx, command_type="REPLACE_TEXT_RANGE",
        range_start=0, range_end=9999,
        expected_before="", after_text="X",
        source_hash=src_hash)
    plan = {"paragraph_edits": [item]}
    out = tmp_path / "oob.hwpx"
    res = _edit_tool.apply_edit_plan(FIXTURE, out, plan, dry_run=False)
    para_op = next(op for op in res["operations"]
                            if op.get("kind") == "paragraph_edits")
    assert any(r.get("reason") in {"RANGE_OUT_OF_BOUNDS",
                                                          "MULTI_RUN_RANGE_NOT_SUPPORTED"}
                      for r in para_op["rejected"]), para_op


# ── 8. paragraphIndex OOB → PARAGRAPH_NOT_FOUND ──────────────

@need_fx
def test_paragraph_not_found(tmp_path):
    fx = _find_first_nonempty_cell_para()
    src_hash = _src_sha()
    bad = dict(fx); bad["paragraphIndex"] = 999
    item = _plan_item(
        fx=bad, command_type="TYPE_TEXT",
        range_start=0, range_end=0,
        expected_before="", after_text="X",
        source_hash=src_hash)
    plan = {"paragraph_edits": [item]}
    out = tmp_path / "pnf.hwpx"
    res = _edit_tool.apply_edit_plan(FIXTURE, out, plan, dry_run=False)
    para_op = next(op for op in res["operations"]
                            if op.get("kind") == "paragraph_edits")
    assert any(r.get("reason") == "PARAGRAPH_NOT_FOUND"
                      for r in para_op["rejected"]), para_op


# ── 9. runIndex OOB → RUN_NOT_FOUND ──────────────────────────

@need_fx
def test_run_not_found(tmp_path):
    fx = _find_first_nonempty_cell_para()
    src_hash = _src_sha()
    bad = dict(fx); bad["runIndex"] = 999
    item = _plan_item(
        fx=bad, command_type="TYPE_TEXT",
        range_start=0, range_end=0,
        expected_before="", after_text="X",
        source_hash=src_hash)
    plan = {"paragraph_edits": [item]}
    out = tmp_path / "rnf.hwpx"
    res = _edit_tool.apply_edit_plan(FIXTURE, out, plan, dry_run=False)
    para_op = next(op for op in res["operations"]
                            if op.get("kind") == "paragraph_edits")
    assert any(r.get("reason") == "RUN_NOT_FOUND"
                      for r in para_op["rejected"]), para_op


# ── 10. charPrIDRef 보존 ──────────────────────────────────────

@need_fx
def test_charpr_preserved(tmp_path):
    fx = _find_first_nonempty_cell_para()
    src_hash = _src_sha()
    item = _plan_item(
        fx=fx, command_type="TYPE_TEXT",
        range_start=0, range_end=0,
        expected_before="", after_text="ABC",
        source_hash=src_hash)
    plan = {"paragraph_edits": [item]}
    out = tmp_path / "char.hwpx"
    _edit_tool.apply_edit_plan(FIXTURE, out, plan, dry_run=False)
    rb = _readback(out, fx["tableIndex"], fx["rowIndex"],
                          fx["colIndex"], fx["paragraphIndex"])
    assert rb["charPrIDRef"] == fx["charPrIDRef"]


# ── 11. parPrIDRef 보존 ───────────────────────────────────────

@need_fx
def test_parpr_preserved(tmp_path):
    fx = _find_first_nonempty_cell_para()
    src_hash = _src_sha()
    item = _plan_item(
        fx=fx, command_type="TYPE_TEXT",
        range_start=0, range_end=0,
        expected_before="", after_text="QQ",
        source_hash=src_hash)
    plan = {"paragraph_edits": [item]}
    out = tmp_path / "par.hwpx"
    _edit_tool.apply_edit_plan(FIXTURE, out, plan, dry_run=False)
    rb = _readback(out, fx["tableIndex"], fx["rowIndex"],
                          fx["colIndex"], fx["paragraphIndex"])
    assert rb["paraPrIDRef"] == fx["paraPrIDRef"]


# ── 12. outputPath == sourcePath 차단 (pipeline 게이트) ───────

@need_fx
def test_output_equals_source_blocked(tmp_path):
    # paragraph_save_pipeline 게이트 — source==output reject
    from scripts.hwpx.web_office.para_edit_model import Paragraph
    res = _para_pipe.save_paragraph_edits(
        source_path=FIXTURE, output_path=FIXTURE,
        command_log=[], paragraphs_by_id={},
        source_document_hash=_src_sha(),
        allow_writer=True)
    assert res["verdict"] == _para_pipe.VERDICT_REJECTED
    assert any(r.get("reason") == "OUTPUT_EQUALS_SOURCE"
                      for r in res["rejected"])


# ── 13. 원본 sha/mtime 무변경 (TYPE/REPLACE/DELETE 모두) ──────

@need_fx
def test_source_sha_unchanged(tmp_path):
    fx = _find_first_nonempty_cell_para()
    src_hash = _src_sha()
    src_mt = FIXTURE.stat().st_mtime_ns
    for ct, after in (("TYPE_TEXT", "A"), ("DELETE_TEXT_RANGE", ""),
                                ("REPLACE_TEXT_RANGE", "Y")):
        item = _plan_item(
            fx=fx, command_type=ct,
            range_start=0, range_end=(0 if ct == "TYPE_TEXT" else 1),
            expected_before=("" if ct == "TYPE_TEXT"
                                          else fx["text"][:1]),
            after_text=after, source_hash=src_hash)
        plan = {"paragraph_edits": [item]}
        out = tmp_path / f"sha_{ct}.hwpx"
        _edit_tool.apply_edit_plan(FIXTURE, out, plan, dry_run=False)
    assert _src_sha() == src_hash
    assert FIXTURE.stat().st_mtime_ns == src_mt


# ── 14. sandbox output 생성 ───────────────────────────────────

@need_fx
def test_sandbox_output_created(tmp_path):
    fx = _find_first_nonempty_cell_para()
    item = _plan_item(
        fx=fx, command_type="TYPE_TEXT",
        range_start=0, range_end=0,
        expected_before="", after_text="S",
        source_hash=_src_sha())
    out = tmp_path / "sandbox.hwpx"
    _edit_tool.apply_edit_plan(FIXTURE, out, {"paragraph_edits": [item]},
                                                dry_run=False)
    assert out.is_file()
    # ZIP 무결성
    with zipfile.ZipFile(out) as zf:
        names = zf.namelist()
    assert names[0] == "mimetype"


# ── 15. readback match — applied entry 별 ─────────────────────

@need_fx
def test_readback_match(tmp_path):
    fx = _find_first_nonempty_cell_para()
    item = _plan_item(
        fx=fx, command_type="TYPE_TEXT",
        range_start=0, range_end=0,
        expected_before="", after_text="HELLO_",
        source_hash=_src_sha())
    out = tmp_path / "rb.hwpx"
    res = _edit_tool.apply_edit_plan(FIXTURE, out,
                                                                  {"paragraph_edits": [item]},
                                                                  dry_run=False)
    para_op = next(op for op in res["operations"]
                            if op.get("kind") == "paragraph_edits")
    for a in para_op["applied"]:
        rb = _readback(out, fx["tableIndex"], fx["rowIndex"],
                              fx["colIndex"], fx["paragraphIndex"])
        assert a["afterText"] in rb["text"]


# ── 16. body paragraph reject ────────────────────────────────

@need_fx
def test_body_paragraph_reject(tmp_path):
    src_hash = _src_sha()
    item = {
        "commandId": "cmd-block",
        "paragraphId": "par_block_0",
        "runId": "run-0",
        "rangeStart": 0, "rangeEnd": 0,
        "expectedBefore": "", "afterText": "X",
        "sourceDocumentHash": src_hash,
        "commandType": "TYPE_TEXT",
        "containerScope": {"kind": "block",
                                              "blockId": "blk_0"},
    }
    plan = {"paragraph_edits": [item]}
    out = tmp_path / "blk.hwpx"
    res = _edit_tool.apply_edit_plan(FIXTURE, out, plan, dry_run=False)
    para_op = next(op for op in res["operations"]
                            if op.get("kind") == "paragraph_edits")
    # WEB-OFFICE-BODY-PARAGRAPH-WRITER-01: body scope 활성화 이후
    # blockId 만 있고 sectionIndex/blockIndex 가 없으면 SCOPE_MISSING.
    assert any(r.get("reason") in (
                                "BODY_PARAGRAPH_NOT_SUPPORTED",
                                "SCOPE_MISSING",
                                "SECTION_NOT_FOUND",
                                "PARAGRAPH_NOT_FOUND")
                      for r in para_op["rejected"]), para_op


# ── 17. multi-run range reject ────────────────────────────────

@need_fx
def test_multi_run_range_reject(tmp_path):
    fx = _find_first_nonempty_cell_para()
    # paragraph 전체 텍스트 길이 보다 큰 range — multi-run 또는 OOB
    item = _plan_item(
        fx=fx, command_type="REPLACE_TEXT_RANGE",
        range_start=0, range_end=len(fx["text"]) + 50,
        expected_before="", after_text="Z",
        source_hash=_src_sha())
    plan = {"paragraph_edits": [item]}
    out = tmp_path / "multi.hwpx"
    res = _edit_tool.apply_edit_plan(FIXTURE, out, plan, dry_run=False)
    para_op = next(op for op in res["operations"]
                            if op.get("kind") == "paragraph_edits")
    assert any(r.get("reason") in {"MULTI_RUN_RANGE_NOT_SUPPORTED",
                                                          "RANGE_OUT_OF_BOUNDS"}
                      for r in para_op["rejected"]), para_op


# ── 18. mixed plan conflict reject ────────────────────────────

@need_fx
def test_mixed_plan_conflict_reject(tmp_path):
    fx = _find_first_nonempty_cell_para()
    src_hash = _src_sha()
    para_item = _plan_item(
        fx=fx, command_type="TYPE_TEXT",
        range_start=0, range_end=0,
        expected_before="", after_text="M",
        source_hash=src_hash)
    plan = {
        "set_cells": [{"table": fx["tableIndex"],
                              "row": fx["rowIndex"],
                              "col": fx["colIndex"],
                              "value": "MIXED"}],
        "paragraph_edits": [para_item],
    }
    out = tmp_path / "mix.hwpx"
    res = _edit_tool.apply_edit_plan(FIXTURE, out, plan, dry_run=False)
    para_op = next(op for op in res["operations"]
                            if op.get("kind") == "paragraph_edits")
    assert any(r.get("reason") == "CELL_COORD_CONFLICT"
                      for r in para_op["rejected"]), para_op


# ── 19. sourceDocumentHash mismatch reject ────────────────────

@need_fx
def test_source_hash_mismatch_reject(tmp_path):
    """plan 의 첫 item 이 reference hash 가 되며, 두 번째 item 의
    hash 가 다르면 SOURCE_HASH_MISMATCH 로 reject 된다.
    """
    fx = _find_first_nonempty_cell_para()
    src_hash = _src_sha()
    item_ref = _plan_item(
        fx=fx, command_type="TYPE_TEXT",
        range_start=0, range_end=0,
        expected_before="", after_text="OK",
        source_hash=src_hash, command_id="cmd-ref")
    item_bad = _plan_item(
        fx=fx, command_type="TYPE_TEXT",
        range_start=0, range_end=0,
        expected_before="", after_text="BAD",
        source_hash=src_hash, command_id="cmd-bad",
        source_hash_override="deadbeef" * 8)
    plan = {"paragraph_edits": [item_ref, item_bad]}
    out = tmp_path / "shm.hwpx"
    res = _edit_tool.apply_edit_plan(FIXTURE, out, plan, dry_run=False)
    para_op = next(op for op in res["operations"]
                            if op.get("kind") == "paragraph_edits")
    assert any(r.get("reason") == "SOURCE_HASH_MISMATCH"
                      for r in para_op["rejected"]), para_op


# ── 20. CELL-SAVE 회귀 — cell_save_pipeline 토큰 무손상 ───────

def test_cell_save_pipeline_tokens_intact():
    src = (PR / "scripts/hwpx/web_office/cell_save_pipeline.py"
                ).read_text(encoding="utf-8")
    assert "def save_cell_edits" in src
    assert "VERDICT_PASS" in src
    assert "VERDICT_REJECTED" in src
    assert "verify7" in src


# ── 21. audit script PASS ─────────────────────────────────────

def test_audit_script_pass():
    from scripts.ops.audit_web_office_writer_para_plan import audit
    rep = audit()
    assert rep["verdict"] == "PASS", rep
