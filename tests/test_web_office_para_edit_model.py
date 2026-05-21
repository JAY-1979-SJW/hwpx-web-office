"""WEB-OFFICE-PARA-EDIT-MODEL-01 계약 테스트.

Python EditCommand v2 모델 + JS para_edit_command 자체 테스트 회귀 잠금.
"""
from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path
import pytest

PR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PR))

from scripts.hwpx.web_office.para_edit_model import (  # noqa: E402
    Paragraph, ParaTextRun, ParagraphTarget,
    make_type_text_command, make_replace_text_range_command,
    make_delete_text_range_command,
    make_split_text_run_command, make_merge_text_runs_command,
    apply_command_to_paragraph, normalize_paragraph,
    split_run, merge_runs, locate_offset,
    validate_expected_before, validate_charpr_preserved,
    validate_parpr_preserved,
    CT_TYPE_TEXT, CT_REPLACE_TEXT_RANGE, CT_DELETE_TEXT_RANGE,
    CT_SPLIT_TEXT_RUN, CT_MERGE_TEXT_RUNS,
    POLICY_ANCHOR_CHARPR, POLICY_FOCUS_CHARPR,
    POLICY_REQUIRES_REVIEW,
    REASON_MERGE_CHARPR_MISMATCH, REASON_REQUIRES_REVIEW,
)
from scripts.ops.audit_web_office_para_edit_model import (  # noqa: E402
    audit, JS_SELF_TEST, PY_FILES, JS_FILES,
    FORBIDDEN_PY, FORBIDDEN_JS,
)


def _fixture():
    return Paragraph(
        paragraphId="par_p1", parPrIDRef="P1",
        runs=[
            ParaTextRun("par_p1_run0", "ab", "A"),
            ParaTextRun("par_p1_run1", "cd", "B"),
            ParaTextRun("par_p1_run2", "ef", "A"),
        ])


def _target():
    return ParagraphTarget(paragraphId="par_p1",
                                                      containerKind="block",
                                                      containerId="blk_p1",
                                                      sourceSha256="abc")


# ── 데이터 모델 ─────────────────────────────────────────────

def test_paragraph_text_concat():
    p = _fixture()
    assert p.text == "abcdef"


def test_char_pr_set():
    p = _fixture()
    assert p.char_pr_set() == {"A", "B"}


# ── 정규화 ─────────────────────────────────────────────────

def test_split_run_inherits_charpr():
    p = _fixture()
    p2, info = split_run(p, "par_p1_run0", 1)
    assert info is not None
    assert len(p2.runs) == 4
    assert p2.runs[0].text == "a" and p2.runs[0].charPrIDRef == "A"
    assert p2.runs[1].text == "b" and p2.runs[1].charPrIDRef == "A"


def test_split_run_noop_at_boundary():
    p = _fixture()
    p2, info = split_run(p, "par_p1_run0", 0)
    assert info is None
    p3, info2 = split_run(p, "par_p1_run0", 2)
    assert info2 is None


def test_merge_runs_same_charpr():
    p = Paragraph(
        paragraphId="par_p1", parPrIDRef="P1",
        runs=[ParaTextRun("par_p1_run0", "ab", "A"),
                      ParaTextRun("par_p1_run1", "cd", "A")])
    merged = merge_runs(p, "par_p1_run0", "par_p1_run1")
    assert len(merged.runs) == 1
    assert merged.runs[0].text == "abcd"


def test_merge_runs_mismatch_rejected():
    p = _fixture()
    with pytest.raises(ValueError) as ei:
        merge_runs(p, "par_p1_run0", "par_p1_run1")
    assert REASON_MERGE_CHARPR_MISMATCH in str(ei.value)


def test_normalize_drops_empty_and_merges():
    p = Paragraph(
        paragraphId="par_p1", parPrIDRef="P1",
        runs=[ParaTextRun("par_p1_run0", "a", "A"),
                      ParaTextRun("par_p1_run1", "", "B"),
                      ParaTextRun("par_p1_run2", "b", "A"),
                      ParaTextRun("par_p1_run3", "c", "A")])
    n = normalize_paragraph(p)
    assert len(n.runs) == 1
    assert n.runs[0].text == "abc"
    assert n.runs[0].charPrIDRef == "A"


def test_normalize_empty_paragraph_keeps_single_empty_run():
    p = Paragraph(
        paragraphId="par_p1", parPrIDRef="P1",
        runs=[ParaTextRun("par_p1_run0", "", "A")])
    n = normalize_paragraph(p)
    assert len(n.runs) == 1
    assert n.runs[0].text == ""


# ── TYPE_TEXT ──────────────────────────────────────────────

def test_type_text_creates_command_with_inverse_delete():
    p = _fixture()
    cmd = make_type_text_command(target=_target(), paragraph=p,
                                                                  caret_offset=1, insert_text="X",
                                                                  source_document_hash="abc")
    assert cmd.commandType == CT_TYPE_TEXT
    assert cmd.inverse["kind"] == "DELETE_TEXT_RANGE"
    assert cmd.forward["inheritCharPrIDRef"] == "A"


def test_type_text_empty_returns_none():
    p = _fixture()
    cmd = make_type_text_command(target=_target(), paragraph=p,
                                                                  caret_offset=1, insert_text="",
                                                                  source_document_hash="abc")
    assert cmd is None


def test_type_text_apply_and_inverse_roundtrip():
    p = _fixture()
    cmd = make_type_text_command(target=_target(), paragraph=p,
                                                                  caret_offset=1, insert_text="X",
                                                                  source_document_hash="abc")
    p1 = apply_command_to_paragraph(p, cmd)
    assert p1.text == "aXbcdef"
    assert validate_parpr_preserved(p, p1)
    assert validate_charpr_preserved(p, p1)


# ── REPLACE_TEXT_RANGE ─────────────────────────────────────

def test_replace_single_run_anchor_charpr():
    p = _fixture()
    cmd = make_replace_text_range_command(
        target=_target(), paragraph=p, range_anchor=0, range_focus=1,
        after_text="AB", source_document_hash="abc")
    assert cmd.expectedBefore == "a"
    p1 = apply_command_to_paragraph(p, cmd)
    assert p1.text == "ABbcdef"


def test_replace_multi_run_anchor_charpr_default():
    p = _fixture()
    cmd = make_replace_text_range_command(
        target=_target(), paragraph=p, range_anchor=1, range_focus=5,
        after_text="ZZ", source_document_hash="abc")
    p1 = apply_command_to_paragraph(p, cmd)
    assert p1.text == "aZZf"
    assert validate_charpr_preserved(p, p1)


def test_replace_requires_review_raises_on_multi_charpr():
    p = _fixture()
    with pytest.raises(ValueError) as ei:
        make_replace_text_range_command(
            target=_target(), paragraph=p, range_anchor=1, range_focus=3,
            after_text="ZZ", source_document_hash="abc",
            policy=POLICY_REQUIRES_REVIEW)
    assert REASON_REQUIRES_REVIEW in str(ei.value)


def test_replace_focus_charpr_policy():
    p = _fixture()
    cmd = make_replace_text_range_command(
        target=_target(), paragraph=p, range_anchor=1, range_focus=3,
        after_text="ZZ", source_document_hash="abc",
        policy=POLICY_FOCUS_CHARPR)
    # focus offset 3 → run1 ("cd") → charPr=B
    assert cmd.forward["applyCharPrIDRef"] == "B"


# ── DELETE_TEXT_RANGE ──────────────────────────────────────

def test_delete_creates_inverse_replace():
    p = _fixture()
    cmd = make_delete_text_range_command(
        target=_target(), paragraph=p, range_anchor=2, range_focus=4,
        source_document_hash="abc")
    assert cmd.commandType == CT_DELETE_TEXT_RANGE
    assert cmd.inverse["kind"] == "REPLACE_TEXT_RANGE"
    assert cmd.inverse["afterText"] == "cd"


def test_delete_apply_and_inverse_roundtrip():
    p = _fixture()
    cmd = make_delete_text_range_command(
        target=_target(), paragraph=p, range_anchor=2, range_focus=4,
        source_document_hash="abc")
    p1 = apply_command_to_paragraph(p, cmd)
    assert p1.text == "abef"
    # inverse 적용 — forward/inverse 스왑된 가짜 명령
    from dataclasses import replace
    inv = replace(cmd, forward=cmd.inverse, inverse=cmd.forward)
    p2 = apply_command_to_paragraph(p1, inv)
    assert p2.text == "abcdef"
    assert validate_parpr_preserved(p, p2)


# ── expectedBefore / 정합 ──────────────────────────────────

def test_validate_expected_before_catches_stale_paragraph():
    p = _fixture()
    cmd = make_replace_text_range_command(
        target=_target(), paragraph=p, range_anchor=0, range_focus=1,
        after_text="Z", source_document_hash="abc")
    # paragraph 가 외부 변형된 상태 — expectedBefore 불일치
    p_changed = Paragraph(
        paragraphId="par_p1", parPrIDRef="P1",
        runs=[ParaTextRun("par_p1_run0", "X", "A"),
                      *p.runs[1:]])
    assert not validate_expected_before(cmd, p_changed)


def test_parpr_preserved_invariance():
    p = _fixture()
    for cmd in [
        make_type_text_command(target=_target(), paragraph=p,
                                                            caret_offset=1, insert_text="X",
                                                            source_document_hash="abc"),
        make_delete_text_range_command(
            target=_target(), paragraph=p, range_anchor=2, range_focus=4,
            source_document_hash="abc"),
    ]:
        p2 = apply_command_to_paragraph(p, cmd)
        assert validate_parpr_preserved(p, p2)
        assert p2.parPrIDRef == "P1"


# ── 정적 잠금 ──────────────────────────────────────────────

def test_python_modules_no_writer_tokens():
    for p in PY_FILES:
        src = p.read_text(encoding="utf-8")
        for tok in FORBIDDEN_PY:
            assert tok not in src, f"{p.name} has forbidden: {tok}"


def test_js_modules_no_writer_tokens():
    for p in JS_FILES:
        src = p.read_text(encoding="utf-8")
        for tok in FORBIDDEN_JS:
            assert tok not in src, f"{p.name} has forbidden: {tok}"


def test_python_model_does_not_import_hwpx_edit_tool_statically():
    src = (PR / "scripts/hwpx/web_office/para_edit_model.py").read_text(
        encoding="utf-8")
    assert "hwpx_edit_tool" not in src
    assert "apply" + "_edit_plan" not in src


def _node_ok() -> bool:
    try:
        r = subprocess.run(["node", "--version"], capture_output=True,
                                          text=True, timeout=10)
        return r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


@pytest.mark.skipif(not _node_ok(), reason="node not available")
def test_js_self_test_all_scenarios_pass():
    r = subprocess.run(["node", str(JS_SELF_TEST)],
                                      capture_output=True, text=True,
                                      timeout=30, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    last = r.stdout.strip().splitlines()[-1]
    out = json.loads(last)
    assert out["verdict"] == "PASS"
    for k in ("typeTextSingleRun", "typeTextEmptyNull", "replaceInRun",
                          "replaceMultiRunAnchor", "requiresReviewBlocked",
                          "deleteRange", "splitRun", "mergeSameCharPr",
                          "mergeMismatchReject", "normalizeMergeAdjacent",
                          "emptyParaKept", "expectedBeforeMismatch"):
        assert out["checks"].get(k) is True, f"missing check: {k}"


def test_audit_returns_pass():
    out = audit()
    assert out["verdict"] == "PASS", out


def test_no_hwpx_output_in_para_edit_dirs():
    leaks = []
    for d in (PR / "scripts/hwpx/web_office",
                          PR / "frontend/web_office_viewer"):
        if d.is_dir():
            leaks.extend(d.glob("*.hwpx"))
    assert leaks == []
