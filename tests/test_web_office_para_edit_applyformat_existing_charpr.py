"""WEB-OFFICE-PARA-EDIT-APPLYFORMAT-EXISTING-CHARPR-01 감리.

APPLY_FORMAT command — paragraph offset range 의 run.@charPrIDRef 를
header.xml 에 이미 존재하는 charPrIDRef 로만 교체. 신규 charPr 생성 금지,
header.xml 무수정, paragraph.text 무변경.
"""
from __future__ import annotations
import hashlib
import json
import sqlite3
import sys
import zipfile
from pathlib import Path

import pytest

PR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PR))
sys.path.insert(0, str(PR / "scripts/hwpx"))

from scripts.hwpx.web_office.ro_view_importer import (  # noqa: E402
    import_hwpx_as_ro_view)
from scripts.hwpx.web_office.para_edit_e2e_pipeline import (  # noqa: E402
    run_para_edit_e2e, _ro_paragraph_to_model, _build_target,
    SCENARIO_APPLY_FORMAT, SCENARIO_TYPE, SCENARIO_REPLACE)
from scripts.hwpx.web_office.charpr_inventory import (  # noqa: E402
    paragraph_char_pr_inventory)
from scripts.hwpx.web_office.para_edit_model import (  # noqa: E402
    make_apply_format_command, CT_APPLY_FORMAT)
from scripts.hwpx.web_office.paragraph_writer_adapter import (  # noqa: E402
    apply_paragraph_edits_plan,
    REASON_TARGET_CHARPR_NOT_IN_HEADER,
    REASON_EXPECTED_BEFORE_MISMATCH,
    REASON_UNSAFE_RUN_CHILDREN,
    REASON_EMPTY_RANGE)


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


def _pick(scope_kind: str, min_runs: int):
    for p in _all_fixtures():
        try:
            doc = import_hwpx_as_ro_view(p)
        except Exception:  # noqa: BLE001
            continue
        for par in doc.paragraphs:
            sc = par.containerScope or {}
            if sc.get("kind") != scope_kind:
                continue
            if not par.parPrIDRef or len(par.runs) < min_runs:
                continue
            if not all(r.text and r.charPrIDRef
                          for r in par.runs[:min_runs]):
                continue
            return p, par
    return None, None


CELL_SINGLE_FX, CELL_SINGLE = _pick("cell", 1)
CELL_MULTI_FX, CELL_MULTI = _pick("cell", 3)
BODY_SINGLE_FX, BODY_SINGLE = _pick("block", 1)
BODY_MULTI_FX, BODY_MULTI = _pick("block", 3)
need_cell_single = pytest.mark.skipif(
    CELL_SINGLE_FX is None, reason="no cell fixture")
need_cell_multi = pytest.mark.skipif(
    CELL_MULTI_FX is None, reason="no multi-run cell fixture")
need_body_single = pytest.mark.skipif(
    BODY_SINGLE_FX is None, reason="no body fixture")
need_body_multi = pytest.mark.skipif(
    BODY_MULTI_FX is None, reason="no multi-run body fixture")


def _pick_target_charpr(fixture, paragraph) -> str | None:
    """paragraph 안에 이미 쓰이는 charPr 중 target 으로 안전한 1개."""
    inv = paragraph_char_pr_inventory(fixture)
    entries = inv["paragraphInventory"][paragraph.paragraphId]
    in_para = [e["charPrId"] for e in entries
                  if e["inHeader"] and e["charPrId"] is not None]
    if not in_para:
        return None
    # 첫 번째 in_para 사용
    return str(in_para[0])


# ── 1. single-run cell ApplyFormat ─────────────────────────────

@need_cell_single
def test_single_run_cell_apply_format(tmp_path):
    par = CELL_SINGLE
    tgt = _pick_target_charpr(CELL_SINGLE_FX, par)
    if tgt is None:
        pytest.skip("no target charPr in cell paragraph")
    out = tmp_path / "single_cell.hwpx"
    res = run_para_edit_e2e(
        source_path=CELL_SINGLE_FX, output_path=out,
        scenario=SCENARIO_APPLY_FORMAT,
        paragraph_id=par.paragraphId,
        range_anchor=0, range_focus=min(2, len(par.text)),
        target_char_pr_id=tgt, allow_writer=True)
    assert res.get("outputCreated") is True, res
    assert not res.get("rejected"), res
    v7 = (res.get("verify7") or {}).get("results", {})
    for k in REQUIRED_V7:
        assert v7.get(k) == "PASS", (k, v7)
    rb = res.get("readback") or {}
    for k in REQUIRED_RB:
        assert rb.get(k) == "PASS", (k, rb)
    applied = res.get("appliedPlanEdits") or []
    assert applied[0].get("applyFormatExistingCharPr") is True


# ── 2. single-run body ApplyFormat ─────────────────────────────

@need_body_single
def test_single_run_body_apply_format(tmp_path):
    par = BODY_SINGLE
    tgt = _pick_target_charpr(BODY_SINGLE_FX, par)
    if tgt is None:
        pytest.skip("no target charPr")
    out = tmp_path / "single_body.hwpx"
    res = run_para_edit_e2e(
        source_path=BODY_SINGLE_FX, output_path=out,
        scenario=SCENARIO_APPLY_FORMAT,
        paragraph_id=par.paragraphId,
        range_anchor=0, range_focus=min(2, len(par.text)),
        target_char_pr_id=tgt, allow_writer=True)
    assert res.get("outputCreated") is True, res
    assert not res.get("rejected"), res
    v7 = (res.get("verify7") or {}).get("results", {})
    for k in REQUIRED_V7:
        assert v7.get(k) == "PASS", (k, v7)
    rb = res.get("readback") or {}
    for k in REQUIRED_RB:
        assert rb.get(k) == "PASS", (k, rb)


# ── 3. multi-run cell ApplyFormat ─────────────────────────────

@need_cell_multi
def test_multi_run_cell_apply_format(tmp_path):
    par = CELL_MULTI
    tgt = _pick_target_charpr(CELL_MULTI_FX, par)
    if tgt is None:
        pytest.skip("no target charPr")
    r0_len = len(par.runs[0].text)
    out = tmp_path / "multi_cell.hwpx"
    res = run_para_edit_e2e(
        source_path=CELL_MULTI_FX, output_path=out,
        scenario=SCENARIO_APPLY_FORMAT,
        paragraph_id=par.paragraphId,
        range_anchor=max(0, r0_len - 1),
        range_focus=r0_len + 1,
        target_char_pr_id=tgt, allow_writer=True)
    assert res.get("outputCreated") is True, res
    assert not res.get("rejected"), res
    v7 = (res.get("verify7") or {}).get("results", {})
    for k in REQUIRED_V7:
        assert v7.get(k) == "PASS", (k, v7)
    rb = res.get("readback") or {}
    for k in REQUIRED_RB:
        assert rb.get(k) == "PASS", (k, rb)


# ── 4. multi-run body ApplyFormat ─────────────────────────────

@need_body_multi
def test_multi_run_body_apply_format(tmp_path):
    par = BODY_MULTI
    tgt = _pick_target_charpr(BODY_MULTI_FX, par)
    if tgt is None:
        pytest.skip("no target charPr")
    r0_len = len(par.runs[0].text)
    out = tmp_path / "multi_body.hwpx"
    res = run_para_edit_e2e(
        source_path=BODY_MULTI_FX, output_path=out,
        scenario=SCENARIO_APPLY_FORMAT,
        paragraph_id=par.paragraphId,
        range_anchor=max(0, r0_len - 1),
        range_focus=r0_len + 1,
        target_char_pr_id=tgt, allow_writer=True)
    assert res.get("outputCreated") is True, res
    assert not res.get("rejected"), res
    v7 = (res.get("verify7") or {}).get("results", {})
    for k in REQUIRED_V7:
        assert v7.get(k) == "PASS", (k, v7)
    rb = res.get("readback") or {}
    for k in REQUIRED_RB:
        assert rb.get(k) == "PASS", (k, rb)


# ── 5. partial range — 좌/중/우 split 정확성 + paragraph.text 무변경 ─

@need_cell_multi
def test_partial_range_split_preserves_paragraph_text(tmp_path):
    par = CELL_MULTI
    tgt = _pick_target_charpr(CELL_MULTI_FX, par)
    if tgt is None:
        pytest.skip("no target charPr")
    text_before = par.text
    out = tmp_path / "partial.hwpx"
    res = run_para_edit_e2e(
        source_path=CELL_MULTI_FX, output_path=out,
        scenario=SCENARIO_APPLY_FORMAT,
        paragraph_id=par.paragraphId,
        range_anchor=1, range_focus=3,
        target_char_pr_id=tgt, allow_writer=True)
    assert res.get("outputCreated") is True
    # output paragraph.text 확인
    out_doc = import_hwpx_as_ro_view(out)
    out_par = next(p for p in out_doc.paragraphs
                          if p.paragraphId == par.paragraphId)
    assert out_par.text == text_before, (out_par.text, text_before)


# ── 6. targetCharPrIDRef header 미존재 → reject ──────────────────

@need_cell_multi
def test_target_char_pr_not_in_header_rejected(tmp_path):
    par = CELL_MULTI
    sc = par.containerScope
    item = {
        "commandId": "c-bad",
        "paragraphId": par.paragraphId,
        "runId": par.runs[0].runId,
        "rangeStart": 0, "rangeEnd": 2,
        "rangeAnchor": 0, "rangeFocus": 2,
        "expectedBefore": par.text[0:2],
        "afterText": par.text[0:2],
        "targetCharPrIDRef": "9999999",
        "commandType": "APPLY_FORMAT",
        "sourceDocumentHash": _sha(CELL_MULTI_FX),
        "containerScope": dict(sc),
    }
    from scripts.hwpx.hwpx_package import HwpxPackage
    pkg = HwpxPackage(CELL_MULTI_FX)
    res = apply_paragraph_edits_plan(
        pkg, [item],
        source_document_hash=_sha(CELL_MULTI_FX), dry_run=True)
    reasons = {r.get("reason") for r in res.get("rejected", [])}
    assert REASON_TARGET_CHARPR_NOT_IN_HEADER in reasons, res


# ── 7. 신규 charPr 생성 시도 — 합성 케이스에서 reject 회로 ──────

@need_cell_multi
def test_new_char_pr_creation_blocked(tmp_path):
    """header.xml 에 없는 새 id 를 targetCharPrIDRef 로 지정하면
    TARGET_CHARPR_NOT_IN_HEADER 로 reject — 신규 charPr 생성 차단.
    """
    par = CELL_MULTI
    cmd = make_apply_format_command(
        target=_build_target(par, _sha(CELL_MULTI_FX)),
        paragraph=_ro_paragraph_to_model(par),
        range_anchor=0, range_focus=2,
        target_char_pr_id="99999",
        source_document_hash=_sha(CELL_MULTI_FX),
        container_scope=par.containerScope)
    assert cmd.commandType == CT_APPLY_FORMAT
    from scripts.hwpx.web_office.paragraph_save_pipeline import (
        save_paragraph_edits)
    out = tmp_path / "new_pr.hwpx"
    res = save_paragraph_edits(
        source_path=CELL_MULTI_FX, output_path=out,
        command_log=[cmd],
        paragraphs_by_id={cmd.target["paragraphId"]:
                                            _ro_paragraph_to_model(par)},
        source_document_hash=_sha(CELL_MULTI_FX),
        allow_writer=True)
    reasons = {r.get("reason") for r in res.get("rejected") or []}
    assert REASON_TARGET_CHARPR_NOT_IN_HEADER in reasons, res


# ── 8. expectedBefore mismatch reject ────────────────────────

@need_cell_multi
def test_expected_before_mismatch_rejected(tmp_path):
    par = CELL_MULTI
    tgt = _pick_target_charpr(CELL_MULTI_FX, par)
    if tgt is None:
        pytest.skip("no target charPr")
    sc = par.containerScope
    item = {
        "commandId": "c-eb",
        "paragraphId": par.paragraphId,
        "runId": par.runs[0].runId,
        "rangeStart": 0, "rangeEnd": 2,
        "rangeAnchor": 0, "rangeFocus": 2,
        "expectedBefore": "WRONG",
        "afterText": "WRONG",
        "targetCharPrIDRef": tgt,
        "commandType": "APPLY_FORMAT",
        "sourceDocumentHash": _sha(CELL_MULTI_FX),
        "containerScope": dict(sc),
    }
    from scripts.hwpx.hwpx_package import HwpxPackage
    pkg = HwpxPackage(CELL_MULTI_FX)
    res = apply_paragraph_edits_plan(
        pkg, [item],
        source_document_hash=_sha(CELL_MULTI_FX), dry_run=True)
    reasons = {r.get("reason") for r in res.get("rejected", [])}
    assert REASON_EXPECTED_BEFORE_MISMATCH in reasons, res


# ── 9. source hash mismatch reject ────────────────────────────

@need_cell_multi
def test_source_hash_mismatch_rejected(tmp_path):
    par = CELL_MULTI
    tgt = _pick_target_charpr(CELL_MULTI_FX, par)
    if tgt is None:
        pytest.skip("no target charPr")
    cmd = make_apply_format_command(
        target=_build_target(par, "WRONG"),
        paragraph=_ro_paragraph_to_model(par),
        range_anchor=0, range_focus=2,
        target_char_pr_id=tgt,
        source_document_hash="WRONG",
        container_scope=par.containerScope)
    from scripts.hwpx.web_office.paragraph_save_pipeline import (
        save_paragraph_edits)
    out = tmp_path / "badhash.hwpx"
    res = save_paragraph_edits(
        source_path=CELL_MULTI_FX, output_path=out,
        command_log=[cmd],
        paragraphs_by_id={cmd.target["paragraphId"]:
                                            _ro_paragraph_to_model(par)},
        source_document_hash=_sha(CELL_MULTI_FX),
        allow_writer=True)
    reasons = {r.get("reason") for r in res.get("rejected") or []}
    assert any("SOURCE_HASH" in r or "HASH_MISMATCH" in r
                  for r in reasons), res


# ── 10. outputPath == sourcePath reject ─────────────────────

@need_cell_multi
def test_output_equals_source_rejected():
    par = CELL_MULTI
    tgt = _pick_target_charpr(CELL_MULTI_FX, par)
    if tgt is None:
        pytest.skip("no target charPr")
    res = run_para_edit_e2e(
        source_path=CELL_MULTI_FX, output_path=CELL_MULTI_FX,
        scenario=SCENARIO_APPLY_FORMAT,
        paragraph_id=par.paragraphId,
        range_anchor=0, range_focus=2,
        target_char_pr_id=tgt, allow_writer=True)
    reasons = {r.get("reason") for r in res.get("rejected") or []}
    assert "OUTPUT_EQUALS_SOURCE" in reasons, res


# ── 11. 원본 sha/mtime + header.xml 무변경 ───────────────────

@need_cell_multi
def test_source_sha_mtime_and_header_preserved(tmp_path):
    par = CELL_MULTI
    tgt = _pick_target_charpr(CELL_MULTI_FX, par)
    if tgt is None:
        pytest.skip("no target charPr")
    sha_b = _sha(CELL_MULTI_FX)
    mt_b = CELL_MULTI_FX.stat().st_mtime_ns
    # header.xml bytes (원본) 추출
    with zipfile.ZipFile(CELL_MULTI_FX) as z:
        header_before = z.read("Contents/header.xml")
    out = tmp_path / "sm.hwpx"
    res = run_para_edit_e2e(
        source_path=CELL_MULTI_FX, output_path=out,
        scenario=SCENARIO_APPLY_FORMAT,
        paragraph_id=par.paragraphId,
        range_anchor=0, range_focus=2,
        target_char_pr_id=tgt, allow_writer=True)
    assert res.get("outputCreated") is True
    assert _sha(CELL_MULTI_FX) == sha_b
    assert CELL_MULTI_FX.stat().st_mtime_ns == mt_b
    # output 의 header.xml 도 원본과 동일 — header 무수정
    with zipfile.ZipFile(out) as z:
        header_after = z.read("Contents/header.xml")
    assert header_after == header_before, (
        "header.xml must not be modified by APPLY_FORMAT")


# ── 12. output sandbox 격리 ───────────────────────────────

@need_cell_multi
def test_output_in_sandbox(tmp_path):
    par = CELL_MULTI
    tgt = _pick_target_charpr(CELL_MULTI_FX, par)
    if tgt is None:
        pytest.skip("no target charPr")
    out = tmp_path / "sb.hwpx"
    res = run_para_edit_e2e(
        source_path=CELL_MULTI_FX, output_path=out,
        scenario=SCENARIO_APPLY_FORMAT,
        paragraph_id=par.paragraphId,
        range_anchor=0, range_focus=2,
        target_char_pr_id=tgt, allow_writer=True)
    assert res.get("outputCreated") is True
    assert str(out).startswith(str(tmp_path))


# ── 13. charPr inventory 정합 — ApplyFormat 후 target 등장 ─────

@need_cell_multi
def test_inventory_reflects_apply_format(tmp_path):
    par = CELL_MULTI
    # paragraph 에 안 쓰이는 (그러나 header 에는 있는) charPr 선택
    inv_before = paragraph_char_pr_inventory(CELL_MULTI_FX)
    pid = par.paragraphId
    in_para_ids = {e["charPrId"]
                              for e in inv_before["paragraphInventory"][pid]
                              if e["charPrId"] is not None}
    candidates = [c for c in inv_before["unusedHeaderCharPrIds"]
                              if c not in in_para_ids]
    if not candidates:
        pytest.skip("no unused header charPr")
    tgt = candidates[0]
    out = tmp_path / "inv.hwpx"
    res = run_para_edit_e2e(
        source_path=CELL_MULTI_FX, output_path=out,
        scenario=SCENARIO_APPLY_FORMAT,
        paragraph_id=pid, range_anchor=0, range_focus=2,
        target_char_pr_id=tgt, allow_writer=True)
    assert res.get("outputCreated") is True
    # output inventory 에서 target charPr 가 paragraph 에 등장해야 함
    inv_after = paragraph_char_pr_inventory(out)
    after_ids = {e["charPrId"]
                          for e in inv_after["paragraphInventory"][pid]}
    assert tgt in after_ids, (tgt, after_ids)


# ── 14. inverse 자료 — beforeSegments 가 적재되는지 ────────────

@need_cell_multi
def test_inverse_before_segments_populated():
    par = CELL_MULTI
    tgt = _pick_target_charpr(CELL_MULTI_FX, par)
    if tgt is None:
        pytest.skip("no target charPr")
    cmd = make_apply_format_command(
        target=_build_target(par, _sha(CELL_MULTI_FX)),
        paragraph=_ro_paragraph_to_model(par),
        range_anchor=0, range_focus=len(par.text),
        target_char_pr_id=tgt,
        source_document_hash=_sha(CELL_MULTI_FX),
        container_scope=par.containerScope)
    inverse = cmd.inverse
    assert inverse["kind"] == "APPLY_FORMAT_INVERSE"
    segs = inverse["restoreSegments"]
    assert len(segs) >= len(par.runs)
    for seg in segs:
        assert "segmentStart" in seg
        assert "segmentEnd" in seg
        assert "charPrIDRef" in seg


# ── 15. TYPE/REPLACE 회귀 PASS ─────────────────────────────

@need_cell_multi
def test_type_replace_regression_still_pass(tmp_path):
    par = CELL_MULTI
    out1 = tmp_path / "r_type.hwpx"
    out2 = tmp_path / "r_replace.hwpx"
    res1 = run_para_edit_e2e(
        source_path=CELL_MULTI_FX, output_path=out1,
        scenario=SCENARIO_TYPE, paragraph_id=par.paragraphId,
        range_anchor=0, insert_text="Z", allow_writer=True)
    assert res1.get("outputCreated") is True, res1
    res2 = run_para_edit_e2e(
        source_path=CELL_MULTI_FX, output_path=out2,
        scenario=SCENARIO_REPLACE, paragraph_id=par.paragraphId,
        range_anchor=0, range_focus=1, replace_after="R",
        allow_writer=True)
    assert res2.get("outputCreated") is True, res2


# ── 16. audit verdict PASS ──────────────────────────────────

def test_audit_script_pass():
    from scripts.ops.audit_web_office_para_edit_applyformat_existing_charpr \
        import audit
    rep = audit()
    fails = [f for f in rep["findings"]
              if f.get("level") == "FAIL"]
    assert not fails, json.dumps(rep, ensure_ascii=False, indent=2)
    assert rep["verdict"] in ("PASS", "WARN"), rep
