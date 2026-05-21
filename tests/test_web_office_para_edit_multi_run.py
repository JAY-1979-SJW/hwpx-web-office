"""WEB-OFFICE-PARA-EDIT-MULTI-RUN-01 감리 검사.

같은 문단 내부에서 여러 run 을 가로지르는 REPLACE_TEXT_RANGE /
DELETE_TEXT_RANGE 활성화. cell scope + body paragraph scope 모두 포함.
기본 정책 POLICY_ANCHOR_CHARPR. TYPE_TEXT multi-run, paragraph 구조 변경,
서식 생성/변경, 표 구조 변경, 이미지 편집은 계속 차단.
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
    SCENARIO_TYPE, SCENARIO_REPLACE, SCENARIO_DELETE)
from scripts.hwpx.web_office.paragraph_writer_adapter import (  # noqa: E402
    REASON_REQUIRES_REVIEW, REASON_UNSAFE_RUN_CHILDREN,
    REASON_TYPE_TEXT_MULTI_RUN_NOT_SUPPORTED,
    REASON_MULTI_RUN_RANGE_NOT_SUPPORTED,
    apply_paragraph_edits_plan)
from scripts.hwpx.web_office.para_edit_model import (  # noqa: E402
    make_replace_text_range_command,
    make_delete_text_range_command,
    POLICY_ANCHOR_CHARPR, POLICY_FOCUS_CHARPR, POLICY_REQUIRES_REVIEW)


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
    return [PR / r[0] for (r,) in [(row,) for row in rows]
              if (PR / r[0]).is_file()]


def _pick_multi_run_paragraph(scope_kind: str):
    """scope_kind 의 multi-run paragraph (>=3 runs, 모두 안전 텍스트,
    모두 charPrIDRef 보유) 와 fixture 를 찾는다.
    """
    for p in _all_fixtures():
        try:
            doc = import_hwpx_as_ro_view(p)
        except Exception:  # noqa: BLE001
            continue
        for par in doc.paragraphs:
            sc = par.containerScope or {}
            if sc.get("kind") != scope_kind:
                continue
            if not par.parPrIDRef:
                continue
            if len(par.runs) < 3:
                continue
            if not all(r.text and r.charPrIDRef for r in par.runs[:3]):
                continue
            return p, par
    return None, None


CELL_FIXTURE, CELL_PARA = _pick_multi_run_paragraph("cell")
BODY_FIXTURE, BODY_PARA = _pick_multi_run_paragraph("block")
need_cell = pytest.mark.skipif(
    CELL_FIXTURE is None, reason="no multi-run cell fixture")
need_body = pytest.mark.skipif(
    BODY_FIXTURE is None, reason="no multi-run body fixture")


def _cross_run_range(par):
    """runs[0]/[1] 경계를 가로지르는 [start, end) 산출."""
    r0 = par.runs[0].text or ""
    r1 = par.runs[1].text or ""
    # 1 char from r0 + 1 char from r1
    start = max(0, len(r0) - 1)
    end = len(r0) + min(1, len(r1))
    return start, end


# ── 1. cell scope multi-run REPLACE PASS ──────────────────────

@need_cell
def test_cell_multi_run_replace_v1_to_v7(tmp_path):
    s, e = _cross_run_range(CELL_PARA)
    out = tmp_path / "cell_mr_replace.hwpx"
    res = run_para_edit_e2e(
        source_path=CELL_FIXTURE, output_path=out,
        scenario=SCENARIO_REPLACE,
        paragraph_id=CELL_PARA.paragraphId,
        range_anchor=s, range_focus=e, replace_after="MR",
        allow_writer=True)
    assert res.get("outputCreated") is True, res
    assert not res.get("rejected"), res
    v7 = (res.get("verify7") or {}).get("results", {})
    for k in REQUIRED_V7:
        assert v7.get(k) == "PASS", (k, v7)
    rb = res.get("readback") or {}
    for k in REQUIRED_RB:
        assert rb.get(k) == "PASS", (k, rb)
    # multi-run flag 적재 확인
    assert any(a.get("multiRun") is True
                  for a in res.get("appliedPlanEdits") or []), res


# ── 2. cell scope multi-run DELETE PASS ───────────────────────

@need_cell
def test_cell_multi_run_delete_v1_to_v7(tmp_path):
    s, e = _cross_run_range(CELL_PARA)
    out = tmp_path / "cell_mr_delete.hwpx"
    res = run_para_edit_e2e(
        source_path=CELL_FIXTURE, output_path=out,
        scenario=SCENARIO_DELETE,
        paragraph_id=CELL_PARA.paragraphId,
        range_anchor=s, range_focus=e, allow_writer=True)
    assert res.get("outputCreated") is True, res
    assert not res.get("rejected"), res
    v7 = (res.get("verify7") or {}).get("results", {})
    for k in REQUIRED_V7:
        assert v7.get(k) == "PASS", (k, v7)
    rb = res.get("readback") or {}
    for k in REQUIRED_RB:
        assert rb.get(k) == "PASS", (k, rb)


# ── 3. body scope multi-run REPLACE PASS ──────────────────────

@need_body
def test_body_multi_run_replace_v1_to_v7(tmp_path):
    s, e = _cross_run_range(BODY_PARA)
    out = tmp_path / "body_mr_replace.hwpx"
    res = run_para_edit_e2e(
        source_path=BODY_FIXTURE, output_path=out,
        scenario=SCENARIO_REPLACE,
        paragraph_id=BODY_PARA.paragraphId,
        range_anchor=s, range_focus=e, replace_after="MR",
        allow_writer=True)
    assert res.get("outputCreated") is True, res
    assert not res.get("rejected"), res
    v7 = (res.get("verify7") or {}).get("results", {})
    for k in REQUIRED_V7:
        assert v7.get(k) == "PASS", (k, v7)
    rb = res.get("readback") or {}
    for k in REQUIRED_RB:
        assert rb.get(k) == "PASS", (k, rb)


# ── 4. body scope multi-run DELETE PASS ───────────────────────

@need_body
def test_body_multi_run_delete_v1_to_v7(tmp_path):
    s, e = _cross_run_range(BODY_PARA)
    out = tmp_path / "body_mr_delete.hwpx"
    res = run_para_edit_e2e(
        source_path=BODY_FIXTURE, output_path=out,
        scenario=SCENARIO_DELETE,
        paragraph_id=BODY_PARA.paragraphId,
        range_anchor=s, range_focus=e, allow_writer=True)
    assert res.get("outputCreated") is True, res
    assert not res.get("rejected"), res
    v7 = (res.get("verify7") or {}).get("results", {})
    for k in REQUIRED_V7:
        assert v7.get(k) == "PASS", (k, v7)
    rb = res.get("readback") or {}
    for k in REQUIRED_RB:
        assert rb.get(k) == "PASS", (k, rb)


# ── 5. POLICY_ANCHOR_CHARPR 적용 확인 ─────────────────────────

@need_cell
def test_policy_anchor_charpr_applied(tmp_path):
    s, e = _cross_run_range(CELL_PARA)
    out = tmp_path / "policy_anchor.hwpx"
    res = run_para_edit_e2e(
        source_path=CELL_FIXTURE, output_path=out,
        scenario=SCENARIO_REPLACE,
        paragraph_id=CELL_PARA.paragraphId,
        range_anchor=s, range_focus=e, replace_after="A",
        allow_writer=True)
    applied = res.get("appliedPlanEdits") or []
    assert applied, res
    # anchor run 의 charPrIDRef 가 적용되어야 한다
    anchor_pr = CELL_PARA.runs[0].charPrIDRef
    assert applied[0].get("applyCharPrIDRef") == anchor_pr, applied[0]
    assert applied[0].get("policy") == POLICY_ANCHOR_CHARPR


# ── 6. POLICY_FOCUS_CHARPR — 정합 검증 ────────────────────────

@need_cell
def test_policy_focus_charpr_validates(tmp_path):
    """POLICY_FOCUS_CHARPR: 1차 공정에서는 anchor 의 charPr 를 그대로
    유지하되, policy 신호와 expectedBefore mismatch 차단 회로는 동작.
    """
    doc = import_hwpx_as_ro_view(CELL_FIXTURE)
    ro_p = next(p for p in doc.paragraphs
                  if p.paragraphId == CELL_PARA.paragraphId)
    model_p = _ro_paragraph_to_model(ro_p)
    target = _build_target(ro_p, doc.sourceDocumentHash)
    s, e = _cross_run_range(CELL_PARA)
    cmd = make_replace_text_range_command(
        target=target, paragraph=model_p,
        range_anchor=s, range_focus=e, after_text="F",
        source_document_hash=doc.sourceDocumentHash,
        policy=POLICY_FOCUS_CHARPR,
        container_scope=target.containerScope)
    from scripts.hwpx.web_office.paragraph_save_pipeline import (
        save_paragraph_edits)
    out = tmp_path / "policy_focus.hwpx"
    res = save_paragraph_edits(
        source_path=CELL_FIXTURE, output_path=out,
        command_log=[cmd],
        paragraphs_by_id={model_p.paragraphId: model_p},
        source_document_hash=doc.sourceDocumentHash,
        allow_writer=True)
    # FOCUS policy 도 writer 까지 도달해야 한다 (1차 공정 한정 동작)
    # — output 생성 + V1~V7 PASS.
    assert res.get("outputCreated") is True, res
    assert not res.get("rejected"), res


# ── 7. POLICY_REQUIRES_REVIEW reject ──────────────────────────

@need_cell
def test_policy_requires_review_rejected(tmp_path):
    doc = import_hwpx_as_ro_view(CELL_FIXTURE)
    ro_p = next(p for p in doc.paragraphs
                  if p.paragraphId == CELL_PARA.paragraphId)
    # POLICY_REQUIRES_REVIEW + multi-charPr 면 model 단계에서 reject.
    # 직접 multi 검증 위해 plan item 만 생성해 writer 호출 — model 이
    # raise 하므로, 여기서는 plan 위조로 writer 의 REQUIRES_REVIEW
    # 회로를 직접 검증한다.
    from scripts.hwpx.hwpx_package import HwpxPackage
    s, e = _cross_run_range(CELL_PARA)
    para_text = ro_p.text
    item = {
        "commandId": "c-rev",
        "paragraphId": ro_p.paragraphId,
        "runId": ro_p.runs[0].runId,
        "rangeStart": s, "rangeEnd": e,
        "rangeAnchor": s, "rangeFocus": e,
        "afterText": "Q", "expectedBefore": para_text[s:e],
        "applyCharPrIDRef": ro_p.runs[0].charPrIDRef,
        "commandType": "REPLACE_TEXT_RANGE",
        "policy": POLICY_REQUIRES_REVIEW,
        "sourceDocumentHash": _sha(CELL_FIXTURE),
        "containerScope": dict(ro_p.containerScope),
    }
    pkg = HwpxPackage(CELL_FIXTURE)
    res = apply_paragraph_edits_plan(
        pkg, [item],
        source_document_hash=_sha(CELL_FIXTURE), dry_run=True)
    reasons = {r.get("reason") for r in res.get("rejected", [])}
    assert REASON_REQUIRES_REVIEW in reasons, res


# ── 8. expectedBefore mismatch reject ─────────────────────────

@need_cell
def test_multi_run_expected_before_mismatch_rejected(tmp_path):
    doc = import_hwpx_as_ro_view(CELL_FIXTURE)
    ro_p = next(p for p in doc.paragraphs
                  if p.paragraphId == CELL_PARA.paragraphId)
    model_p = _ro_paragraph_to_model(ro_p)
    target = _build_target(ro_p, doc.sourceDocumentHash)
    s, e = _cross_run_range(CELL_PARA)
    cmd = make_replace_text_range_command(
        target=target, paragraph=model_p,
        range_anchor=s, range_focus=e, after_text="N",
        source_document_hash=doc.sourceDocumentHash,
        container_scope=target.containerScope)
    cmd.expectedBefore = "WRONG_SLICE"
    from scripts.hwpx.web_office.paragraph_save_pipeline import (
        save_paragraph_edits)
    out = tmp_path / "mr_mismatch.hwpx"
    res = save_paragraph_edits(
        source_path=CELL_FIXTURE, output_path=out,
        command_log=[cmd],
        paragraphs_by_id={model_p.paragraphId: model_p},
        source_document_hash=doc.sourceDocumentHash,
        allow_writer=True)
    reasons = {r.get("reason") for r in res.get("rejected") or []}
    assert ("EXPECTED_BEFORE_MISMATCH" in reasons
              or "EXPECTED_BEFORE_MISMATCH_PARAGRAPH" in reasons), res


# ── 9. source hash mismatch reject ───────────────────────────

@need_cell
def test_multi_run_source_hash_mismatch_rejected(tmp_path):
    doc = import_hwpx_as_ro_view(CELL_FIXTURE)
    ro_p = next(p for p in doc.paragraphs
                  if p.paragraphId == CELL_PARA.paragraphId)
    model_p = _ro_paragraph_to_model(ro_p)
    target = _build_target(ro_p, "WRONG")
    s, e = _cross_run_range(CELL_PARA)
    cmd = make_replace_text_range_command(
        target=target, paragraph=model_p,
        range_anchor=s, range_focus=e, after_text="N",
        source_document_hash="WRONG",
        container_scope=target.containerScope)
    from scripts.hwpx.web_office.paragraph_save_pipeline import (
        save_paragraph_edits)
    out = tmp_path / "mr_badhash.hwpx"
    res = save_paragraph_edits(
        source_path=CELL_FIXTURE, output_path=out,
        command_log=[cmd],
        paragraphs_by_id={model_p.paragraphId: model_p},
        source_document_hash=doc.sourceDocumentHash,
        allow_writer=True)
    reasons = {r.get("reason") for r in res.get("rejected") or []}
    assert any("SOURCE_HASH" in r or "HASH_MISMATCH" in r
                  for r in reasons), res


# ── 10. outputPath == sourcePath reject ──────────────────────

@need_cell
def test_multi_run_output_equals_source_rejected():
    s, e = _cross_run_range(CELL_PARA)
    res = run_para_edit_e2e(
        source_path=CELL_FIXTURE, output_path=CELL_FIXTURE,
        scenario=SCENARIO_REPLACE,
        paragraph_id=CELL_PARA.paragraphId,
        range_anchor=s, range_focus=e, replace_after="X",
        allow_writer=True)
    reasons = {r.get("reason") for r in res.get("rejected") or []}
    assert "OUTPUT_EQUALS_SOURCE" in reasons, res


# ── 11. 원본 sha/mtime 무변경 ────────────────────────────────

@need_cell
def test_multi_run_source_sha_mtime_preserved(tmp_path):
    sha_b = _sha(CELL_FIXTURE)
    mt_b = CELL_FIXTURE.stat().st_mtime_ns
    s, e = _cross_run_range(CELL_PARA)
    for i, (scn, kw) in enumerate([
        (SCENARIO_REPLACE, {"replace_after": "X"}),
        (SCENARIO_DELETE, {}),
    ]):
        out = tmp_path / f"mr_pres_{i}.hwpx"
        run_para_edit_e2e(
            source_path=CELL_FIXTURE, output_path=out,
            scenario=scn, paragraph_id=CELL_PARA.paragraphId,
            range_anchor=s, range_focus=e, allow_writer=True, **kw)
    assert _sha(CELL_FIXTURE) == sha_b
    assert CELL_FIXTURE.stat().st_mtime_ns == mt_b


# ── 12. TYPE_TEXT multi-run 계속 차단 ────────────────────────

@need_cell
def test_type_text_multi_run_still_rejected(tmp_path):
    """TYPE_TEXT 는 caret 가 한 run 안에 있어야 한다 — 본 공정에서
    multi-run TYPE_TEXT 는 계속 차단.
    """
    from scripts.hwpx.hwpx_package import HwpxPackage
    # paragraph offset 이 multi-run boundary 를 가로지르는 비현실 케이스를
    # 직접 위조하여 writer 가 TYPE_TEXT_MULTI_RUN_NOT_SUPPORTED 로
    # 차단함을 확인.
    doc = import_hwpx_as_ro_view(CELL_FIXTURE)
    ro_p = next(p for p in doc.paragraphs
                  if p.paragraphId == CELL_PARA.paragraphId)
    r0_len = len(ro_p.runs[0].text)
    # rangeStart=0, rangeEnd 가 run0 끝을 넘는 (multi-run) 경우 +
    # run_local 로도 해석 불가능한 위치
    item = {
        "commandId": "c-typemr",
        "paragraphId": ro_p.paragraphId,
        "runId": ro_p.runs[0].runId,
        "rangeStart": 0, "rangeEnd": r0_len + 1,
        "rangeAnchor": 0, "rangeFocus": r0_len + 1,
        "caretOffset": 0,
        "afterText": "Z", "expectedBefore": "",
        "applyCharPrIDRef": ro_p.runs[0].charPrIDRef,
        "commandType": "TYPE_TEXT",
        "sourceDocumentHash": _sha(CELL_FIXTURE),
        "containerScope": dict(ro_p.containerScope),
    }
    pkg = HwpxPackage(CELL_FIXTURE)
    res = apply_paragraph_edits_plan(
        pkg, [item],
        source_document_hash=_sha(CELL_FIXTURE), dry_run=True)
    reasons = {r.get("reason") for r in res.get("rejected", [])}
    assert REASON_TYPE_TEXT_MULTI_RUN_NOT_SUPPORTED in reasons, res


# ── 13. 위험 child (hp:ctrl 등) 가 포함된 run 은 UNSAFE_RUN_CHILDREN

@need_cell
def test_unsafe_run_children_rejected(tmp_path, monkeypatch):
    """span 의 run 에 hp:t 외 child 가 있으면 reject.

    fixture 가 깨끗할 가능성이 높으므로, package 로드 후 다중 run
    paragraph 의 첫 run 에 hp:ctrl 자식을 in-memory 로 주입한 뒤
    apply_paragraph_edits_plan 직접 호출.
    """
    from scripts.hwpx.hwpx_package import HwpxPackage
    from scripts.hwpx.web_office.paragraph_writer_adapter import (
        _resolve_cell)
    import xml.etree.ElementTree as ET

    pkg = HwpxPackage(CELL_FIXTURE)
    sc = CELL_PARA.containerScope
    resolved, err = _resolve_cell(pkg, sc["tableIndex"],
                                                          sc["rowIndex"], sc["colIndex"])
    if err is not None or resolved is None:
        pytest.skip(f"cell resolve failed: {err}")
    entry, root, cell_elem = resolved
    from scripts.hwpx.hwpx_paragraph_ops import (
        find_paragraph_in_cell, paragraph_runs)
    p_elem = find_paragraph_in_cell(cell_elem,
                                                            sc["paragraphIndex"])
    runs = paragraph_runs(p_elem)
    if len(runs) < 2:
        pytest.skip("paragraph not multi-run after resolve")
    # 첫 run 에 hp:ctrl 자식 (가짜 위험 child) 주입 후 write_xml 으로
    # in-memory package entries 에 다시 반영해야 apply_paragraph_edits_plan
    # 의 read_xml 이 변경된 XML 을 보게 된다.
    hp_ns = "http://www.hancom.co.kr/hwpml/2011/paragraph"
    ctrl = ET.SubElement(runs[0], f"{{{hp_ns}}}ctrl")
    ctrl.text = ""
    pkg.write_xml(entry, root)

    s, e = _cross_run_range(CELL_PARA)
    item = {
        "commandId": "c-unsafe",
        "paragraphId": CELL_PARA.paragraphId,
        "runId": CELL_PARA.runs[0].runId,
        "rangeStart": s, "rangeEnd": e,
        "rangeAnchor": s, "rangeFocus": e,
        "afterText": "U",
        "expectedBefore": CELL_PARA.text[s:e],
        "applyCharPrIDRef": CELL_PARA.runs[0].charPrIDRef,
        "commandType": "REPLACE_TEXT_RANGE",
        "sourceDocumentHash": _sha(CELL_FIXTURE),
        "containerScope": dict(CELL_PARA.containerScope),
    }
    res = apply_paragraph_edits_plan(
        pkg, [item],
        source_document_hash=_sha(CELL_FIXTURE), dry_run=False)
    reasons = {r.get("reason") for r in res.get("rejected", [])}
    assert REASON_UNSAFE_RUN_CHILDREN in reasons, res


# ── 14. multi-run primitive 직접 단위 테스트 ───────────────────

def test_multi_run_primitive_direct():
    """ET 합성 paragraph 로 primitive 단독 검증."""
    import xml.etree.ElementTree as ET
    from scripts.hwpx.hwpx_paragraph_ops import (
        apply_text_range_edit_multi_run, paragraph_text,
        STATUS_OK)

    hp = "http://www.hancom.co.kr/hwpml/2011/paragraph"
    p = ET.Element(f"{{{hp}}}p", {"paraPrIDRef": "1"})
    for txt, pr in [("AAA", "11"), ("BBB", "22"), ("CCC", "11")]:
        r = ET.SubElement(p, f"{{{hp}}}run", {"charPrIDRef": pr})
        t = ET.SubElement(r, f"{{{hp}}}t")
        t.text = txt
    assert paragraph_text(p) == "AAABBBCCC"
    # cross runs[0]→runs[1] [2,4) → "AB"
    res = apply_text_range_edit_multi_run(
        p, 2, 4, "X",
        apply_charpr_idref="11",
        expected_before="AB")
    assert res["status"] == STATUS_OK, res
    assert paragraph_text(p) == "AAXBBCCC", paragraph_text(p)
    assert res["removedMiddleRuns"] == 0


def test_multi_run_primitive_removes_middle():
    """anchor→focus 사이 중간 run 제거 동작."""
    import xml.etree.ElementTree as ET
    from scripts.hwpx.hwpx_paragraph_ops import (
        apply_text_range_edit_multi_run, paragraph_text,
        paragraph_runs, STATUS_OK)
    hp = "http://www.hancom.co.kr/hwpml/2011/paragraph"
    p = ET.Element(f"{{{hp}}}p", {"paraPrIDRef": "1"})
    for txt, pr in [("AA", "1"), ("BB", "2"), ("CC", "3"),
                                ("DD", "1")]:
        r = ET.SubElement(p, f"{{{hp}}}run", {"charPrIDRef": pr})
        t = ET.SubElement(r, f"{{{hp}}}t")
        t.text = txt
    # [1, 7) -> "ABBCCD" (cross 4 runs)
    res = apply_text_range_edit_multi_run(
        p, 1, 7, "Z",
        apply_charpr_idref="1",
        expected_before="ABBCCD")
    assert res["status"] == STATUS_OK, res
    assert paragraph_text(p) == "AZD", paragraph_text(p)
    assert res["removedMiddleRuns"] == 2
    runs = paragraph_runs(p)
    assert len(runs) == 2


# ── 15. audit verdict PASS ──────────────────────────────────

def test_audit_script_pass():
    from scripts.ops.audit_web_office_para_edit_multi_run import audit
    rep = audit()
    fails = [f for f in rep["findings"]
              if f.get("level") == "FAIL"]
    assert not fails, json.dumps(rep, ensure_ascii=False, indent=2)
    assert rep["verdict"] in ("PASS", "WARN"), rep
