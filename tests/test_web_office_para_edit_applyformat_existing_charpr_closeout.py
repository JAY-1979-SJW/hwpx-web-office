"""WEB-OFFICE-PARA-EDIT-APPLYFORMAT-EXISTING-CHARPR-CLOSEOUT-01 감리.

ApplyFormat existing-charPr 부분 준공 동결 — 시방서 + audit + 회귀 자재
목록 + 97c4095 baseline 잠금 확인. 신규 시공 없음.
"""
from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path

PR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PR))

CLOSEOUT_DOC = (PR / "docs/architecture/"
                   "web_office_para_edit_applyformat_existing_charpr_closeout.md")
BASELINE_COMMIT = "98d64ed"


# ── 1. 시방서 존재 + baseline 표기 ─────────────────────────────

def test_closeout_doc_exists():
    assert CLOSEOUT_DOC.is_file(), CLOSEOUT_DOC


def test_closeout_doc_lists_baseline_commit():
    src = CLOSEOUT_DOC.read_text(encoding="utf-8")
    assert BASELINE_COMMIT in src, (
        f"baseline {BASELINE_COMMIT} 미명시")


# ── 2. 공식 완료 범위 명시 ─────────────────────────────────

def test_closeout_doc_lists_completed_scopes():
    src = CLOSEOUT_DOC.read_text(encoding="utf-8")
    for phrase in (
        "CT_APPLY_FORMAT",
        "make_apply_format_command",
        "apply_charpr_to_range_existing",
        "single-run", "multi-run",
        "full-run", "partial-run",
        "paragraph.text 무변경",
        "header.xml 무변경",
    ):
        assert phrase in src, phrase


def test_closeout_doc_lists_v_gates():
    src = CLOSEOUT_DOC.read_text(encoding="utf-8")
    for v in ("V1_RANGE_POSITION_OK", "V2_NO_CROSS_PARAGRAPH_LEAK",
                "V3_UNTOUCHED_RUNS_PRESERVED", "V4_CHARPR_PRESERVED",
                "V5_PARPR_PRESERVED", "V6_OUTPUT_ISOLATED",
                "V7_READBACK_MATCH"):
        assert v in src, v


def test_closeout_doc_lists_safety_gates():
    src = CLOSEOUT_DOC.read_text(encoding="utf-8")
    for phrase in (
        "TARGET_CHARPR_NOT_IN_HEADER",
        "OUTPUT_EQUALS_SOURCE",
        "UNSAFE_RUN_CHILDREN",
        "EMPTY_RANGE",
        "sourceDocumentHash",
    ):
        assert phrase in src, phrase


# ── 3. 공식 차단 범위 명시 ─────────────────────────────────

def test_closeout_doc_lists_blocked_scopes():
    src = CLOSEOUT_DOC.read_text(encoding="utf-8")
    for phrase in (
        "신규 charPr 생성",
        "toolbar UI 완성",
        "bold/italic/color/fontSize",
        "paragraph add/delete",
        "table structure",
        "image/stamp/signature",
        "AI 자동 입력",
        "원본 HWPX 직접 수정",
        "POLICY_CARET_RIGHT",
        "문서 전체 스타일 일괄 변경",
    ):
        assert phrase in src, phrase


# ── 4. 핵심 회귀 자재 (테스트 파일) 존재 ───────────────────────

REQUIRED_TESTS = [
    "test_web_office_para_edit_applyformat_existing_charpr.py",
    "test_web_office_para_edit_format_charpr_inventory.py",
    "test_web_office_para_edit_content_closeout.py",
    "test_web_office_para_edit_e2e_full_closeout.py",
    "test_web_office_para_type_text_contract.py",
    "test_web_office_para_edit_e2e_integration.py",
    "test_web_office_para_edit_model.py",
    "test_web_office_para_adapter_applycharpr.py",
    "test_web_office_para_readback_parser.py",
    "test_web_office_para_edit_save_verify7.py",
    "test_web_office_para_edit_container_scope_bridge.py",
    "test_web_office_writer_para_plan.py",
    "test_web_office_para_edit_ime_live.py",
    "test_web_office_body_paragraph_writer.py",
    "test_web_office_para_edit_multi_run.py",
    "test_web_office_para_edit_type_multi_run.py",
]


def test_all_required_tests_exist():
    missing = [name for name in REQUIRED_TESTS
                  if not (PR / "tests" / name).is_file()]
    assert not missing, missing


def test_required_tests_listed_in_closeout_doc():
    src = CLOSEOUT_DOC.read_text(encoding="utf-8")
    for name in REQUIRED_TESTS:
        assert name in src, f"{name} 미인용"


def test_required_tests_listed_in_audit():
    from scripts.ops.audit_web_office_para_edit_applyformat_existing_charpr_closeout import (
        REQUIRED_TESTS as AUDIT_TESTS)
    audit_names = {Path(p).name for p in AUDIT_TESTS}
    expected = set(REQUIRED_TESTS)
    assert audit_names == expected, (
        f"missing: {expected - audit_names}, "
        f"extra: {audit_names - expected}")


# ── 5. 핵심 시공 자재 무수정 vs 97c4095 ────────────────────

LOCKED_VS_BASELINE = [
    "scripts/hwpx/hwpx_paragraph_ops.py",
    "scripts/hwpx/hwpx_edit_tool.py",
    "scripts/hwpx/web_office/para_edit_model.py",
    "scripts/hwpx/web_office/paragraph_edit_plan.py",
    "scripts/hwpx/web_office/paragraph_writer_adapter.py",
    "scripts/hwpx/web_office/paragraph_save_verify7.py",
    "scripts/hwpx/web_office/para_edit_e2e_pipeline.py",
    "scripts/hwpx/web_office/paragraph_save_pipeline.py",
    "scripts/hwpx/web_office/ro_view_importer.py",
    "scripts/hwpx/web_office/charpr_inventory.py",
    # WEB-OFFICE-PARA-EDIT-APPLYFORMAT-TOOLBAR-COMMAND-01:
    # para_edit_command.mjs / para_edit_state.mjs 본 LOCKED 에서 제거.
    "frontend/web_office_viewer/para_edit_runtime.mjs",
]


def test_locked_sources_unchanged_vs_baseline():
    for rel in LOCKED_VS_BASELINE:
        r = subprocess.run(
            ["git", "diff", BASELINE_COMMIT, "--", rel],
            capture_output=True, text=True, cwd=str(PR), timeout=20)
        assert r.returncode == 0, (rel, r.stderr)
        assert not r.stdout.strip(), (
            f"{rel} changed vs {BASELINE_COMMIT}")


# ── 6. 차단 범위 코드 흔적 없음 ───────────────────────────

def test_no_forbidden_traces_in_writer_chain():
    import re
    forbidden = [
        r"def\s+create_char_pr\b",
        r"def\s+apply_paragraph_add\b",
        r"def\s+apply_paragraph_delete\b",
        r"def\s+add_table_row\b",
        r"def\s+delete_table_row\b",
        r"def\s+insert_image\b",
        r"POLICY_CARET_RIGHT",
        r"package\.entries\[[^\]]*header\.xml[^\]]*\]\s*=",
    ]
    targets = [
        "scripts/hwpx/web_office/paragraph_writer_adapter.py",
        "scripts/hwpx/web_office/para_edit_model.py",
        "scripts/hwpx/web_office/paragraph_edit_plan.py",
        "scripts/hwpx/hwpx_paragraph_ops.py",
        "scripts/hwpx/web_office/charpr_inventory.py",
    ]
    for rel in targets:
        src = (PR / rel).read_text(encoding="utf-8")
        for pat in forbidden:
            assert not re.search(pat, src), (rel, pat)


# ── 7. audit verdict PASS ──────────────────────────────────

def test_audit_script_pass():
    from scripts.ops.audit_web_office_para_edit_applyformat_existing_charpr_closeout import (
        audit)
    rep = audit()
    fails = [f for f in rep["findings"]
              if f.get("level") == "FAIL"]
    assert not fails, json.dumps(rep, ensure_ascii=False, indent=2)
    assert rep["verdict"] in ("PASS", "WARN"), rep
