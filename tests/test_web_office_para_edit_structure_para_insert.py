"""WEB-OFFICE-PARA-EDIT-STRUCTURE-PARA-INSERT-01 감리검사.

Enter 키 → body paragraph split 기능 Python 측 계약 테스트.
JS smoke 는 para_edit_structure_smoke.mjs 에서 별도 실행.
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
    make_para_insert_command,
    CT_PARA_INSERT, CT_PARA_DELETE,
    PARA_COMMAND_TYPES,
    REASON_MULTI_PARA_RANGE_NOT_SUPPORTED,
    REASON_SECTION_BOUNDARY_NOT_SUPPORTED,
    REASON_LIST_ITEM_NOT_SUPPORTED,
    REASON_SOFT_BREAK_NOT_SUPPORTED,
)


# ── fixtures ────────────────────────────────────────────────

def _para(pid="100", text="Hello World", pr="6", cpr="11"):
    return Paragraph(
        paragraphId=pid, parPrIDRef=pr,
        runs=[ParaTextRun(f"{pid}_run0", text, cpr)])


def _target(pid="100"):
    return ParagraphTarget(
        paragraphId=pid,
        containerKind="block",
        containerId="blk_0",
        sourceSha256="SHA256",
    )


# ── 1. CT_PARA_INSERT 등록 확인 ──────────────────────────────

def test_ct_para_insert_registered_in_para_command_types():
    assert CT_PARA_INSERT in PARA_COMMAND_TYPES


def test_ct_para_delete_in_para_command_types():
    # PARA_DELETE 는 PARA_DELETE-01 공정에서 정식 등록됨
    assert CT_PARA_DELETE in PARA_COMMAND_TYPES


# ── 2. make_para_insert_command 기본 계약 ────────────────────

def test_make_para_insert_command_returns_ct_para_insert():
    p = _para()
    cmd = make_para_insert_command(
        target=_target(), paragraph=p,
        caret_offset=5, source_document_hash="SHA",
        new_paragraph_id="101")
    assert cmd.commandType == CT_PARA_INSERT


def test_forward_before_after_split_correctly():
    p = _para(text="Hello World")
    cmd = make_para_insert_command(
        target=_target(), paragraph=p,
        caret_offset=5, source_document_hash="SHA",
        new_paragraph_id="101")
    assert cmd.forward["beforeText"] == "Hello"
    assert cmd.forward["afterText"] == " World"


def test_forward_new_paragraph_id_propagated():
    p = _para()
    cmd = make_para_insert_command(
        target=_target(), paragraph=p,
        caret_offset=5, source_document_hash="SHA",
        new_paragraph_id="999")
    assert cmd.forward["newParagraphId"] == "999"
    assert cmd.payload["newParagraphId"] == "999"


def test_forward_inherits_parPrIDRef():
    p = _para(pr="P5")
    cmd = make_para_insert_command(
        target=_target(), paragraph=p,
        caret_offset=5, source_document_hash="SHA",
        new_paragraph_id="101")
    assert cmd.forward["newParPrIDRef"] == "P5"


def test_forward_inherits_charPrIDRef_at_caret():
    p = _para(cpr="C7")
    cmd = make_para_insert_command(
        target=_target(), paragraph=p,
        caret_offset=5, source_document_hash="SHA",
        new_paragraph_id="101")
    assert cmd.forward["newCharPrIDRef"] == "C7"


def test_inverse_is_para_delete():
    p = _para()
    cmd = make_para_insert_command(
        target=_target(), paragraph=p,
        caret_offset=5, source_document_hash="SHA",
        new_paragraph_id="101")
    assert cmd.inverse["kind"] == "PARA_DELETE"
    assert cmd.inverse["paragraphId"] == "101"
    assert cmd.inverse["mergeIntoParagraphId"] == "100"
    assert cmd.inverse["originalCaretOffset"] == 5


def test_caret_at_start_before_text_empty():
    p = _para(text="Hello")
    cmd = make_para_insert_command(
        target=_target(), paragraph=p,
        caret_offset=0, source_document_hash="SHA",
        new_paragraph_id="101")
    assert cmd.forward["beforeText"] == ""
    assert cmd.forward["afterText"] == "Hello"


def test_caret_at_end_after_text_empty():
    p = _para(text="Hello")
    cmd = make_para_insert_command(
        target=_target(), paragraph=p,
        caret_offset=5, source_document_hash="SHA",
        new_paragraph_id="101")
    assert cmd.forward["beforeText"] == "Hello"
    assert cmd.forward["afterText"] == ""


def test_caret_out_of_range_raises():
    p = _para(text="Hello")
    with pytest.raises(ValueError):
        make_para_insert_command(
            target=_target(), paragraph=p,
            caret_offset=10, source_document_hash="SHA",
            new_paragraph_id="101")


def test_expected_before_is_full_text():
    p = _para(text="Hello World")
    cmd = make_para_insert_command(
        target=_target(), paragraph=p,
        caret_offset=5, source_document_hash="SHA",
        new_paragraph_id="101")
    assert cmd.expectedBefore == "Hello World"


# ── 3. multi-run paragraph caret 분할 ────────────────────────

def test_caret_mid_run_split():
    """run 경계가 아닌 run 내부 caret — beforeText/afterText 올바른지."""
    p = Paragraph(
        paragraphId="200", parPrIDRef="P1",
        runs=[
            ParaTextRun("200_r0", "AB", "C1"),
            ParaTextRun("200_r1", "CD", "C2"),
        ])
    # text = "ABCD", caret=3 (run1 의 1번째)
    cmd = make_para_insert_command(
        target=ParagraphTarget("200", "block", "blk", "H"),
        paragraph=p,
        caret_offset=3, source_document_hash="H",
        new_paragraph_id="201")
    assert cmd.forward["beforeText"] == "ABC"
    assert cmd.forward["afterText"] == "D"


# ── 4. reason code 상수 존재 ─────────────────────────────────

def test_reason_constants_defined():
    assert REASON_MULTI_PARA_RANGE_NOT_SUPPORTED
    assert REASON_SECTION_BOUNDARY_NOT_SUPPORTED
    assert REASON_LIST_ITEM_NOT_SUPPORTED
    assert REASON_SOFT_BREAK_NOT_SUPPORTED


# ── 5. JS smoke 실행 PASS ────────────────────────────────────

JS_SMOKE = PR / "frontend/web_office_viewer/para_edit_structure_smoke.mjs"


def test_js_smoke_exists():
    assert JS_SMOKE.is_file(), JS_SMOKE


def test_js_smoke_passes():
    r = subprocess.run(
        ["node", str(JS_SMOKE)],
        capture_output=True, text=True, timeout=30)
    out_text = r.stdout.strip()
    assert r.returncode == 0, r.stderr
    assert out_text, "smoke 출력 없음"
    result = json.loads(out_text)
    assert result.get("verdict") == "PASS", json.dumps(
        result, ensure_ascii=False, indent=2)
    failed = [k for k, v in result.get("checks", {}).items()
              if not v.get("ok")]
    assert not failed, f"실패 체크: {failed}"
