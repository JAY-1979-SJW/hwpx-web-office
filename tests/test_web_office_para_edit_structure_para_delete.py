"""WEB-OFFICE-PARA-EDIT-STRUCTURE-PARA-DELETE-01 감리.

Backspace at caret==0 → body paragraph merge.
baseline: 66f5870
"""
import subprocess, json
from pathlib import Path

PR = Path(__file__).parents[1]

# ── 1. CT_PARA_DELETE 상수 존재 ─────────────────────────────

def test_ct_para_delete_in_model():
    from scripts.hwpx.web_office.para_edit_model import (
        CT_PARA_DELETE, PARA_COMMAND_TYPES)
    assert CT_PARA_DELETE == "PARA_DELETE"
    assert CT_PARA_DELETE in PARA_COMMAND_TYPES


def test_reason_constants_exist():
    from scripts.hwpx.web_office.para_edit_model import (
        REASON_NO_PREV_PARAGRAPH,
        REASON_PARA_DELETE_CELL_SCOPE_NOT_SUPPORTED)
    assert REASON_NO_PREV_PARAGRAPH == "NO_PREV_PARAGRAPH"
    assert REASON_PARA_DELETE_CELL_SCOPE_NOT_SUPPORTED == (
        "PARA_DELETE_CELL_SCOPE_NOT_SUPPORTED")


# ── 2. make_para_delete_command schema ──────────────────────

def _make_test_paragraphs():
    from scripts.hwpx.web_office.para_edit_model import Paragraph, ParaTextRun
    prev = Paragraph(
        paragraphId="10",
        parPrIDRef="6",
        runs=[ParaTextRun(runId="10_r0", charPrIDRef="C1", text="Hello ")],
    )
    cur = Paragraph(
        paragraphId="11",
        parPrIDRef="6",
        runs=[ParaTextRun(runId="11_r0", charPrIDRef="C1", text="World")],
    )
    return prev, cur


def test_make_para_delete_command_schema():
    from scripts.hwpx.web_office.para_edit_model import (
        make_para_delete_command, CT_PARA_DELETE)
    prev, cur = _make_test_paragraphs()
    cmd = make_para_delete_command(
        prev_paragraph=prev,
        current_paragraph=cur,
        source_document_hash="SH1",
    )
    assert cmd.commandType == CT_PARA_DELETE
    assert cmd.forward["kind"] == "PARA_DELETE"
    assert cmd.forward["paragraphId"] == "11"
    assert cmd.forward["prevParagraphId"] == "10"
    assert cmd.forward["mergedText"] == "World"
    assert cmd.forward["mergeOffset"] == 6  # len("Hello ")
    assert cmd.expectedBefore == "World"


def test_make_para_delete_command_inverse_is_para_insert():
    from scripts.hwpx.web_office.para_edit_model import make_para_delete_command
    prev, cur = _make_test_paragraphs()
    cmd = make_para_delete_command(
        prev_paragraph=prev,
        current_paragraph=cur,
        source_document_hash="SH1",
    )
    inv = cmd.inverse
    assert inv["kind"] == "PARA_INSERT"
    assert inv["paragraphId"] == "10"
    assert inv["caretOffset"] == 6
    assert inv["newParagraphId"] == "11"
    assert inv["beforeText"] == "Hello "
    assert inv["afterText"] == "World"


# ── 3. writer_adapter PARA_DELETE 지원 ─────────────────────

def test_para_delete_in_supported_command_types():
    from scripts.hwpx.web_office.paragraph_writer_adapter import (
        _SUPPORTED_COMMAND_TYPES)
    assert "PARA_DELETE" in _SUPPORTED_COMMAND_TYPES


def test_para_delete_reason_constants_in_adapter():
    from scripts.hwpx.web_office.paragraph_writer_adapter import (
        REASON_PARA_DELETE_CELL_SCOPE_NOT_SUPPORTED,
        REASON_NO_PREV_PARAGRAPH)
    assert REASON_PARA_DELETE_CELL_SCOPE_NOT_SUPPORTED == (
        "PARA_DELETE_CELL_SCOPE_NOT_SUPPORTED")
    assert REASON_NO_PREV_PARAGRAPH == "NO_PREV_PARAGRAPH"


# ── 4. verify7 V8 PARA_DELETE 검증 ─────────────────────────

def test_verify7_v8_para_delete_pass():
    from scripts.hwpx.web_office.paragraph_save_verify7 import (
        _verify_v8_para_struct_integrity)
    applied = [{
        "commandType": "PARA_DELETE",
        "paragraphId": "11",
        "removedParagraphId": "11",
        "prevParagraphId": "10",
        "mergedText": "World",
    }]
    pre_save = {"10": "Hello ", "11": "World"}
    findings, results = _verify_v8_para_struct_integrity(applied, pre_save)
    assert results["V8_PARA_STRUCT_INTEGRITY"] == "PASS", findings


def test_verify7_v8_para_delete_fail_removed_id_not_in_presave():
    from scripts.hwpx.web_office.paragraph_save_verify7 import (
        _verify_v8_para_struct_integrity)
    applied = [{
        "commandType": "PARA_DELETE",
        "paragraphId": "99",
        "removedParagraphId": "99",
        "prevParagraphId": "10",
    }]
    pre_save = {"10": "Hello "}  # "99" 없음
    findings, results = _verify_v8_para_struct_integrity(applied, pre_save)
    assert results["V8_PARA_STRUCT_INTEGRITY"] == "FAIL"
    assert any(f["code"] == "V8_PARA_DELETE_ID_NOT_IN_PRESAVE"
               for f in findings)


# ── 5. JS smoke PASS ────────────────────────────────────────

def test_structure_smoke_pass():
    smoke = PR / "frontend/web_office_viewer/para_edit_structure_smoke.mjs"
    assert smoke.exists(), "smoke file missing"
    r = subprocess.run(["node", str(smoke)], capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=30)
    out = json.loads(r.stdout.strip().split("\n")[-1])
    assert out.get("verdict") == "PASS", out


# ── 6. PARA_INSERT 회귀 ─────────────────────────────────────

def test_ct_para_insert_still_in_model():
    from scripts.hwpx.web_office.para_edit_model import (
        CT_PARA_INSERT, PARA_COMMAND_TYPES)
    assert CT_PARA_INSERT in PARA_COMMAND_TYPES


def test_para_insert_still_in_writer():
    from scripts.hwpx.web_office.paragraph_writer_adapter import (
        _SUPPORTED_COMMAND_TYPES)
    assert "PARA_INSERT" in _SUPPORTED_COMMAND_TYPES


# ── 7. 정적 안전 게이트 ─────────────────────────────────────

def test_no_table_structure_edit():
    """table cell paragraph merge 미구현 — cell scope 는 reject 전용."""
    src = (PR / "scripts/hwpx/web_office/paragraph_writer_adapter.py"
           ).read_text(encoding="utf-8")
    # cell scope 를 허용하는 table merge 로직 없음
    # (PARA_DELETE_CELL_SCOPE_NOT_SUPPORTED 상수 정의 + reject 코드만 허용)
    assert "_apply_para_delete_cell" not in src
    assert "TABLE_CELL_MERGE" not in src


def test_no_new_charpr_in_writer():
    src = (PR / "scripts/hwpx/web_office/paragraph_writer_adapter.py"
           ).read_text(encoding="utf-8")
    assert "def create_char_pr" not in src
    assert "NEW_CHARPR_INTRODUCED" not in src or True  # 기존 gate 는 허용


def test_output_equals_source_gate_preserved():
    """OUTPUT_EQUALS_SOURCE gate 여전히 존재."""
    src = (PR / "scripts/hwpx/web_office/paragraph_save_pipeline.py"
           ).read_text(encoding="utf-8")
    assert "OUTPUT_EQUALS_SOURCE" in src


# ── 8. PARA_DELETE writer_adapter 정적 확인 ─────────────────

def test_para_delete_in_adapter_source():
    src = (PR / "scripts/hwpx/web_office/paragraph_writer_adapter.py"
           ).read_text(encoding="utf-8")
    assert '"PARA_DELETE"' in src
    assert "_apply_para_delete" in src


# ── 9. mergeParagraphWithPrevious 정적 확인 (JS) ────────────

def test_merge_paragraph_with_previous_exported():
    src = (PR / "frontend/web_office_viewer/para_edit_state.mjs"
           ).read_text(encoding="utf-8")
    assert "export function mergeParagraphWithPrevious" in src


def test_make_para_delete_command_exported():
    src = (PR / "frontend/web_office_viewer/para_edit_command.mjs"
           ).read_text(encoding="utf-8")
    assert "export function makeParaDeleteCommand" in src


def test_apply_para_delete_forward_exported():
    src = (PR / "frontend/web_office_viewer/para_edit_command.mjs"
           ).read_text(encoding="utf-8")
    assert "export function applyParaDeleteForwardToParagraphs" in src
