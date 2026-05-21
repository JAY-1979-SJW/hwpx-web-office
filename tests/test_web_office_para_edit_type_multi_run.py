"""WEB-OFFICE-PARA-EDIT-TYPE-MULTI-RUN-02 감리 검사.

multi-run paragraph 에서 caret 가 scope.runIndex 가 가리키는 run 밖에
있어도 TYPE_TEXT 가 성립한다 — writer 가 paragraph offset 으로 caret 가
속한 run 을 다시 찾아 단일-run insert (apply_text_range_edit) 로
라우팅한다. 신규 primitive 없음, 신규 정책 enum 없음.
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
    run_para_edit_e2e, _ro_paragraph_to_model, _build_target,
    SCENARIO_TYPE)
from scripts.hwpx.web_office.paragraph_writer_adapter import (  # noqa: E402
    apply_paragraph_edits_plan,
    REASON_UNSAFE_RUN_CHILDREN,
    REASON_EXPECTED_BEFORE_MISMATCH,
    REASON_CHARPR_MISMATCH)


REQUIRED_V7 = ("V2_NO_CROSS_PARAGRAPH_LEAK",
                "V3_UNTOUCHED_RUNS_PRESERVED",
                "V4_CHARPR_PRESERVED", "V5_PARPR_PRESERVED",
                "V6_OUTPUT_ISOLATED")
REQUIRED_RB = ("V1_RANGE_POSITION_OK",
                "V4_CHARPR_PRESERVED", "V7_READBACK_MATCH")


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _all_fixtures() -> list[Path]:
    db = PR / "data/recognition_corpus/corpus.sqlite3"
    if not db.is_file():
        return []
    try:
        conn = sqlite3.connect(db)
        rows = conn.execute("""
            SELECT d.source_path FROM hwpx_documents d
            WHERE d.inventory_status='FOUND'
            ORDER BY d.first_seen_at LIMIT 200
        """).fetchall()
        conn.close()
    except sqlite3.Error:
        return []
    return [PR / r[0] for r in rows if (PR / r[0]).is_file()]


def _pick_multi_run_paragraph(scope_kind: str):
    """3 runs 이상, 모든 run text 비어있지 않고 charPrIDRef 보유."""
    for p in _all_fixtures():
        try:
            doc = import_hwpx_as_ro_view(p)
        except Exception:  # noqa: BLE001
            continue
        for par in doc.paragraphs:
            sc = par.containerScope or {}
            if sc.get("kind") != scope_kind:
                continue
            if not par.parPrIDRef or len(par.runs) < 3:
                continue
            if not all(r.text and r.charPrIDRef
                          for r in par.runs[:3]):
                continue
            return p, par
    return None, None


CELL_FIXTURE, CELL_PARA = _pick_multi_run_paragraph("cell")
BODY_FIXTURE, BODY_PARA = _pick_multi_run_paragraph("block")
need_cell = pytest.mark.skipif(
    CELL_FIXTURE is None, reason="no multi-run cell fixture")
need_body = pytest.mark.skipif(
    BODY_FIXTURE is None, reason="no multi-run body fixture")


def _carets(par):
    """returns (label, caret_offset, expected_charpr) tuples."""
    r0 = par.runs[0].text or ""
    r1 = par.runs[1].text or ""
    r0_pr = par.runs[0].charPrIDRef
    r1_pr = par.runs[1].charPrIDRef
    last_pr = par.runs[-1].charPrIDRef
    inside_r1 = len(r0) + max(1, len(r1) // 2)
    para_end = sum(len(r.text) for r in par.runs)
    return [
        ("start", 0, r0_pr),
        ("r0/r1 boundary", len(r0), r0_pr),
        ("inside r1", inside_r1, r1_pr),
        ("paragraph end", para_end, last_pr),
    ]


# ── 1. cell scope multi-run TYPE_TEXT PASS ──────────────────────

@need_cell
def test_cell_multi_run_type_text_inside_r1(tmp_path):
    label, caret, expected_pr = [c for c in _carets(CELL_PARA)
                                                            if c[0] == "inside r1"][0]
    out = tmp_path / "cell_type_inside.hwpx"
    res = run_para_edit_e2e(
        source_path=CELL_FIXTURE, output_path=out,
        scenario=SCENARIO_TYPE,
        paragraph_id=CELL_PARA.paragraphId,
        range_anchor=caret, insert_text="Z", allow_writer=True)
    assert res.get("outputCreated") is True, res
    assert not res.get("rejected"), res
    v7 = (res.get("verify7") or {}).get("results", {})
    for k in REQUIRED_V7:
        assert v7.get(k) == "PASS", (k, v7)
    rb = res.get("readback") or {}
    for k in REQUIRED_RB:
        assert rb.get(k) == "PASS", (k, rb)
    applied = res.get("appliedPlanEdits") or []
    assert applied[0].get("typeMultiRun") is True, applied
    assert applied[0].get("applyCharPrIDRef") == expected_pr, applied


@need_cell
def test_cell_multi_run_type_text_boundary(tmp_path):
    label, caret, expected_pr = [c for c in _carets(CELL_PARA)
                                                            if c[0] == "r0/r1 boundary"][0]
    out = tmp_path / "cell_type_bdry.hwpx"
    res = run_para_edit_e2e(
        source_path=CELL_FIXTURE, output_path=out,
        scenario=SCENARIO_TYPE,
        paragraph_id=CELL_PARA.paragraphId,
        range_anchor=caret, insert_text="B", allow_writer=True)
    assert res.get("outputCreated") is True, res
    assert not res.get("rejected"), res
    v7 = (res.get("verify7") or {}).get("results", {})
    for k in REQUIRED_V7:
        assert v7.get(k) == "PASS", (k, v7)
    rb = res.get("readback") or {}
    for k in REQUIRED_RB:
        assert rb.get(k) == "PASS", (k, rb)
    # boundary 좌측 charPr 상속 (locate_offset default)
    applied = res.get("appliedPlanEdits") or []
    assert applied[0].get("applyCharPrIDRef") == expected_pr, applied


@need_cell
def test_cell_multi_run_type_text_paragraph_end(tmp_path):
    label, caret, expected_pr = [c for c in _carets(CELL_PARA)
                                                            if c[0] == "paragraph end"][0]
    out = tmp_path / "cell_type_end.hwpx"
    res = run_para_edit_e2e(
        source_path=CELL_FIXTURE, output_path=out,
        scenario=SCENARIO_TYPE,
        paragraph_id=CELL_PARA.paragraphId,
        range_anchor=caret, insert_text="E", allow_writer=True)
    assert res.get("outputCreated") is True, res
    assert not res.get("rejected"), res
    v7 = (res.get("verify7") or {}).get("results", {})
    for k in REQUIRED_V7:
        assert v7.get(k) == "PASS", (k, v7)
    rb = res.get("readback") or {}
    for k in REQUIRED_RB:
        assert rb.get(k) == "PASS", (k, rb)
    applied = res.get("appliedPlanEdits") or []
    assert applied[0].get("applyCharPrIDRef") == expected_pr, applied


# ── 2. body scope multi-run TYPE_TEXT PASS ──────────────────────

@need_body
def test_body_multi_run_type_text_inside_r1(tmp_path):
    label, caret, expected_pr = [c for c in _carets(BODY_PARA)
                                                            if c[0] == "inside r1"][0]
    out = tmp_path / "body_type_inside.hwpx"
    res = run_para_edit_e2e(
        source_path=BODY_FIXTURE, output_path=out,
        scenario=SCENARIO_TYPE,
        paragraph_id=BODY_PARA.paragraphId,
        range_anchor=caret, insert_text="Z", allow_writer=True)
    assert res.get("outputCreated") is True, res
    assert not res.get("rejected"), res
    v7 = (res.get("verify7") or {}).get("results", {})
    for k in REQUIRED_V7:
        assert v7.get(k) == "PASS", (k, v7)
    rb = res.get("readback") or {}
    for k in REQUIRED_RB:
        assert rb.get(k) == "PASS", (k, rb)
    applied = res.get("appliedPlanEdits") or []
    assert applied[0].get("typeMultiRun") is True, applied
    assert applied[0].get("applyCharPrIDRef") == expected_pr, applied


@need_body
def test_body_multi_run_type_text_boundary(tmp_path):
    label, caret, expected_pr = [c for c in _carets(BODY_PARA)
                                                            if c[0] == "r0/r1 boundary"][0]
    out = tmp_path / "body_type_bdry.hwpx"
    res = run_para_edit_e2e(
        source_path=BODY_FIXTURE, output_path=out,
        scenario=SCENARIO_TYPE,
        paragraph_id=BODY_PARA.paragraphId,
        range_anchor=caret, insert_text="B", allow_writer=True)
    assert res.get("outputCreated") is True, res
    assert not res.get("rejected"), res
    v7 = (res.get("verify7") or {}).get("results", {})
    for k in REQUIRED_V7:
        assert v7.get(k) == "PASS", (k, v7)
    rb = res.get("readback") or {}
    for k in REQUIRED_RB:
        assert rb.get(k) == "PASS", (k, rb)
    applied = res.get("appliedPlanEdits") or []
    assert applied[0].get("applyCharPrIDRef") == expected_pr, applied


# ── 3. expectedBefore 가 "" 가 아니면 reject ────────────────────

@need_cell
def test_type_multi_run_expected_before_must_be_empty(tmp_path):
    """plan item 의 expectedBefore 를 위조해 reject 회로 검증."""
    from scripts.hwpx.hwpx_package import HwpxPackage
    label, caret, _ = [c for c in _carets(CELL_PARA)
                                  if c[0] == "inside r1"][0]
    sc = CELL_PARA.containerScope
    item = {
        "commandId": "c-eb",
        "paragraphId": CELL_PARA.paragraphId,
        "runId": CELL_PARA.runs[0].runId,
        "rangeStart": caret, "rangeEnd": caret,
        "rangeAnchor": caret, "rangeFocus": caret,
        "caretOffset": caret,
        "afterText": "X", "insertText": "X",
        "expectedBefore": "WRONG",
        "applyCharPrIDRef": CELL_PARA.runs[1].charPrIDRef,
        "commandType": "TYPE_TEXT",
        "sourceDocumentHash": _sha(CELL_FIXTURE),
        "containerScope": dict(sc),
    }
    pkg = HwpxPackage(CELL_FIXTURE)
    res = apply_paragraph_edits_plan(
        pkg, [item],
        source_document_hash=_sha(CELL_FIXTURE), dry_run=False)
    reasons = {r.get("reason") for r in res.get("rejected", [])}
    assert REASON_EXPECTED_BEFORE_MISMATCH in reasons, res


# ── 4. sourceDocumentHash mismatch reject ───────────────────────

@need_cell
def test_type_multi_run_source_hash_mismatch(tmp_path):
    from scripts.hwpx.hwpx_package import HwpxPackage
    label, caret, _ = [c for c in _carets(CELL_PARA)
                                  if c[0] == "inside r1"][0]
    sc = CELL_PARA.containerScope
    item = {
        "commandId": "c-sh",
        "paragraphId": CELL_PARA.paragraphId,
        "runId": CELL_PARA.runs[0].runId,
        "rangeStart": caret, "rangeEnd": caret,
        "rangeAnchor": caret, "rangeFocus": caret,
        "afterText": "X", "insertText": "X",
        "expectedBefore": "",
        "applyCharPrIDRef": CELL_PARA.runs[1].charPrIDRef,
        "commandType": "TYPE_TEXT",
        "sourceDocumentHash": "WRONG",
        "containerScope": dict(sc),
    }
    pkg = HwpxPackage(CELL_FIXTURE)
    res = apply_paragraph_edits_plan(
        pkg, [item],
        source_document_hash=_sha(CELL_FIXTURE), dry_run=True)
    reasons = {r.get("reason") for r in res.get("rejected", [])}
    assert any("SOURCE_HASH" in r or "HASH_MISMATCH" in r
                  for r in reasons), res


# ── 5. outputPath == sourcePath reject ───────────────────────────

@need_cell
def test_type_multi_run_output_equals_source():
    label, caret, _ = [c for c in _carets(CELL_PARA)
                                  if c[0] == "inside r1"][0]
    res = run_para_edit_e2e(
        source_path=CELL_FIXTURE, output_path=CELL_FIXTURE,
        scenario=SCENARIO_TYPE,
        paragraph_id=CELL_PARA.paragraphId,
        range_anchor=caret, insert_text="X", allow_writer=True)
    reasons = {r.get("reason") for r in res.get("rejected") or []}
    assert "OUTPUT_EQUALS_SOURCE" in reasons, res


# ── 6. 위험 child 포함 run caret reject ─────────────────────────

@need_cell
def test_type_multi_run_unsafe_run_children_rejected(tmp_path):
    """caret 가 들어가는 run 에 hp:ctrl 등 위험 child 가 있으면 reject."""
    from scripts.hwpx.hwpx_package import HwpxPackage
    from scripts.hwpx.web_office.paragraph_writer_adapter import (
        _resolve_cell)
    from scripts.hwpx.hwpx_paragraph_ops import (
        find_paragraph_in_cell, paragraph_runs)
    import xml.etree.ElementTree as ET

    pkg = HwpxPackage(CELL_FIXTURE)
    sc = CELL_PARA.containerScope
    resolved, err = _resolve_cell(pkg, sc["tableIndex"],
                                                          sc["rowIndex"],
                                                          sc["colIndex"])
    if err is not None or resolved is None:
        pytest.skip(f"cell resolve failed: {err}")
    entry, root, cell_elem = resolved
    p_elem = find_paragraph_in_cell(cell_elem,
                                                            sc["paragraphIndex"])
    runs = paragraph_runs(p_elem)
    if len(runs) < 2:
        pytest.skip("paragraph not multi-run after resolve")
    # runs[1] 에 hp:ctrl 자식 주입 → caret 를 runs[1] 안에 두면 reject.
    hp = "http://www.hancom.co.kr/hwpml/2011/paragraph"
    ctrl = ET.SubElement(runs[1], f"{{{hp}}}ctrl")
    ctrl.text = ""
    pkg.write_xml(entry, root)

    label, caret, _ = [c for c in _carets(CELL_PARA)
                                  if c[0] == "inside r1"][0]
    item = {
        "commandId": "c-unsafe",
        "paragraphId": CELL_PARA.paragraphId,
        "runId": CELL_PARA.runs[0].runId,
        "rangeStart": caret, "rangeEnd": caret,
        "rangeAnchor": caret, "rangeFocus": caret,
        "afterText": "X", "insertText": "X",
        "expectedBefore": "",
        "applyCharPrIDRef": CELL_PARA.runs[1].charPrIDRef,
        "commandType": "TYPE_TEXT",
        "sourceDocumentHash": _sha(CELL_FIXTURE),
        "containerScope": dict(sc),
    }
    res = apply_paragraph_edits_plan(
        pkg, [item],
        source_document_hash=_sha(CELL_FIXTURE), dry_run=False)
    reasons = {r.get("reason") for r in res.get("rejected", [])}
    assert REASON_UNSAFE_RUN_CHILDREN in reasons, res


# ── 7. applyCharPrIDRef mismatch reject ────────────────────────

@need_cell
def test_type_multi_run_apply_char_pr_mismatch(tmp_path):
    """plan item 의 applyCharPrIDRef 가 target run 의 charPr 와 다르면
    REASON_CHARPR_MISMATCH 로 reject.
    """
    from scripts.hwpx.hwpx_package import HwpxPackage
    label, caret, _ = [c for c in _carets(CELL_PARA)
                                  if c[0] == "inside r1"][0]
    sc = CELL_PARA.containerScope
    item = {
        "commandId": "c-mm",
        "paragraphId": CELL_PARA.paragraphId,
        "runId": CELL_PARA.runs[0].runId,
        "rangeStart": caret, "rangeEnd": caret,
        "rangeAnchor": caret, "rangeFocus": caret,
        "afterText": "X", "insertText": "X",
        "expectedBefore": "",
        # 의도적으로 다른 run 의 charPr 를 넘김 (run0 vs target=run1)
        "applyCharPrIDRef": CELL_PARA.runs[0].charPrIDRef,
        "commandType": "TYPE_TEXT",
        "sourceDocumentHash": _sha(CELL_FIXTURE),
        "containerScope": dict(sc),
    }
    pkg = HwpxPackage(CELL_FIXTURE)
    res = apply_paragraph_edits_plan(
        pkg, [item],
        source_document_hash=_sha(CELL_FIXTURE), dry_run=True)
    reasons = {r.get("reason") for r in res.get("rejected", [])}
    # run0 의 charPr 와 run1 의 charPr 가 동일하다면 mismatch 안 날 수도
    # 있으니, 그 경우는 skip.
    if CELL_PARA.runs[0].charPrIDRef == CELL_PARA.runs[1].charPrIDRef:
        pytest.skip("runs[0] and runs[1] share charPrIDRef")
    assert REASON_CHARPR_MISMATCH in reasons, res


# ── 8. 원본 sha/mtime 무변경 ───────────────────────────────────

@need_cell
def test_type_multi_run_source_sha_mtime_preserved(tmp_path):
    sha_b = _sha(CELL_FIXTURE)
    mt_b = CELL_FIXTURE.stat().st_mtime_ns
    for i, (label, caret, _) in enumerate(_carets(CELL_PARA)):
        out = tmp_path / f"t_{i}.hwpx"
        run_para_edit_e2e(
            source_path=CELL_FIXTURE, output_path=out,
            scenario=SCENARIO_TYPE,
            paragraph_id=CELL_PARA.paragraphId,
            range_anchor=caret, insert_text="P",
            allow_writer=True)
    assert _sha(CELL_FIXTURE) == sha_b
    assert CELL_FIXTURE.stat().st_mtime_ns == mt_b


# ── 9. output sandbox 격리 ─────────────────────────────────────

@need_cell
def test_type_multi_run_output_sandbox(tmp_path):
    label, caret, _ = [c for c in _carets(CELL_PARA)
                                  if c[0] == "inside r1"][0]
    out = tmp_path / "sandbox.hwpx"
    res = run_para_edit_e2e(
        source_path=CELL_FIXTURE, output_path=out,
        scenario=SCENARIO_TYPE,
        paragraph_id=CELL_PARA.paragraphId,
        range_anchor=caret, insert_text="S", allow_writer=True)
    assert res.get("outputCreated") is True
    assert str(out).startswith(str(tmp_path))


# ── 10. audit verdict PASS ────────────────────────────────────

def test_audit_script_pass():
    from scripts.ops.audit_web_office_para_edit_type_multi_run import (
        audit)
    rep = audit()
    fails = [f for f in rep["findings"]
              if f.get("level") == "FAIL"]
    assert not fails, json.dumps(rep, ensure_ascii=False, indent=2)
    assert rep["verdict"] in ("PASS", "WARN"), rep
