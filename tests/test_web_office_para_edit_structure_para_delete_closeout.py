"""WEB-OFFICE-PARA-EDIT-STRUCTURE-PARA-DELETE-CLOSEOUT-01 감리.

Backspace paragraph merge 준공 동결 — 시방서 + audit + 회귀 자재
목록 + 5db3d7f baseline 잠금 확인. 신규 시공 없음.
"""
from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path

PR = Path(__file__).parents[1]

CLOSEOUT_DOC = (PR / "docs/architecture/"
                   "web_office_para_edit_structure_para_delete_closeout.md")
BASELINE_COMMIT = "b411164"  # M2 문단서식 준공 후 갱신 (b411164 → b411164)
FEATURE_COMMIT  = "1f442ec"

LOCKED_VS_BASELINE = [
    "frontend/web_office_viewer/para_edit_command.mjs",
    "frontend/web_office_viewer/para_edit_state.mjs",
    "frontend/web_office_viewer/para_edit_runtime.mjs",
    "frontend/web_office_viewer/para_edit_structure_smoke.mjs",
    "scripts/hwpx/web_office/para_edit_model.py",
    "scripts/hwpx/web_office/paragraph_writer_adapter.py",
    "scripts/hwpx/web_office/paragraph_save_verify7.py",
    "scripts/hwpx/web_office/paragraph_save_pipeline.py",
    "scripts/hwpx/web_office/para_edit_e2e_pipeline.py",
    "scripts/hwpx/web_office/charpr_inventory.py",
    "scripts/hwpx/web_office/render_payload.py",
]


# ── 1. 시방서 존재 + baseline / feature commit 표기 ─────────────

def test_closeout_doc_exists():
    assert CLOSEOUT_DOC.is_file(), CLOSEOUT_DOC


def test_closeout_doc_lists_baseline_commit():
    src = CLOSEOUT_DOC.read_text(encoding="utf-8")
    assert BASELINE_COMMIT in src, f"baseline {BASELINE_COMMIT} missing"


def test_closeout_doc_lists_feature_commit():
    src = CLOSEOUT_DOC.read_text(encoding="utf-8")
    assert FEATURE_COMMIT in src, f"feature commit {FEATURE_COMMIT} missing"


# ── 2. 완료 범위 명시 ────────────────────────────────────────────

def test_closeout_doc_lists_completed_scopes():
    src = CLOSEOUT_DOC.read_text(encoding="utf-8")
    for phrase in (
        "CT_PARA_DELETE",
        "makeParaDeleteCommand",
        "applyParaDeleteForwardToParagraphs",
        "mergeParagraphWithPrevious",
        "deleteBackward",
        "_apply_para_delete",
        "make_para_delete_command",
        "REASON_NO_PREV_PARAGRAPH",
        "REASON_PARA_DELETE_CELL_SCOPE_NOT_SUPPORTED",
        "charPrIDRef / parPrIDRef",
        "paragraph id 제거",
        "V8",
    ):
        assert phrase in src, phrase


# ── 3. 차단 범위 명시 ────────────────────────────────────────────

def test_closeout_doc_lists_blocked_scopes():
    src = CLOSEOUT_DOC.read_text(encoding="utf-8")
    for phrase in (
        "table cell paragraph merge",
        "header/footer paragraph merge",
        "image/shape run special merge",
        "section break merge",
        "list/numbering merge",
        "multi-paragraph selection merge",
        "Shift+Enter soft break",
        "신규 charPr 생성",
        "header.xml mutation",
        "Excel 공정",
        "원본 HWPX 직접 수정",
        "AI 자동 입력",
    ):
        assert phrase in src, phrase


# ── 4. 다음 공정 후보 명시 ───────────────────────────────────────

def test_closeout_doc_lists_next_processes():
    src = CLOSEOUT_DOC.read_text(encoding="utf-8")
    for name in (
        "STRUCTURE-SOFT-BREAK-01",
        "STRUCTURE-PARA-DELETE-CELL-01",
        "UNDO-REDO-STACK-LIMIT-01",
    ):
        assert name in src, name


# ── 5. 회귀 자재 존재 ────────────────────────────────────────────

REQUIRED_TESTS = [
    "test_web_office_para_edit_structure_para_delete.py",
    "test_web_office_para_edit_structure_para_insert.py",
]
REQUIRED_JS_SMOKES = [
    "para_edit_structure_smoke.mjs",
]


def test_all_required_tests_exist():
    missing = [n for n in REQUIRED_TESTS
               if not (PR / "tests" / n).is_file()]
    assert not missing, missing


def test_all_required_js_smokes_exist():
    missing = [n for n in REQUIRED_JS_SMOKES
               if not (PR / "frontend/web_office_viewer" / n).is_file()]
    assert not missing, missing


def test_required_files_listed_in_closeout_doc():
    src = CLOSEOUT_DOC.read_text(encoding="utf-8")
    for name in REQUIRED_TESTS + REQUIRED_JS_SMOKES:
        assert name in src, name


# ── 6. 핵심 자재 무수정 vs 5db3d7f ──────────────────────────────

def test_locked_files_unchanged_vs_baseline():
    for rel in LOCKED_VS_BASELINE:
        r = subprocess.run(
            ["git", "diff", BASELINE_COMMIT, "--", rel],
            capture_output=True, text=True, cwd=str(PR), timeout=20)
        assert not r.stdout.strip(), f"{rel} changed vs {BASELINE_COMMIT}"


# ── 7. HWPX staged 0 ─────────────────────────────────────────────

def test_hwpx_staged_zero():
    r = subprocess.run(["git", "diff", "--cached", "--name-only"],
                       capture_output=True, text=True, cwd=str(PR), timeout=10)
    hwpx_staged = [
        f for f in r.stdout.strip().splitlines()
        if any(f.startswith(p) for p in (
            "frontend/web_office_viewer/", "scripts/hwpx/web_office/",
            "tests/test_web_office_", "scripts/ops/audit_web_office_",
            "docs/architecture/web_office_",
        ))
    ]
    assert not hwpx_staged, f"HWPX staged: {hwpx_staged}"


# ── 8. git diff --check (whitespace) ─────────────────────────────

def test_git_diff_check_clean():
    r = subprocess.run(["git", "diff", "--check"],
                       capture_output=True, text=True, cwd=str(PR), timeout=10)
    assert r.returncode == 0, r.stdout


# ── 9. JS smoke PASS ─────────────────────────────────────────────

def test_js_structure_smoke_pass():
    smoke = PR / "frontend/web_office_viewer/para_edit_structure_smoke.mjs"
    assert smoke.exists(), "smoke file missing"
    r = subprocess.run(["node", str(smoke)], capture_output=True,
                       text=True, timeout=30)
    out = json.loads(r.stdout.strip().split("\n")[-1])
    assert out.get("verdict") == "PASS", out


# ── 10. PARA_DELETE 회귀 ─────────────────────────────────────────

def test_para_delete_regression():
    r = subprocess.run(
        [sys.executable, "-m", "pytest",
         "tests/test_web_office_para_edit_structure_para_delete.py",
         "-q", "--tb=short"],
        capture_output=True, text=True, cwd=str(PR), timeout=60)
    assert r.returncode == 0, r.stdout[-2000:]


# ── 11. PARA_INSERT 회귀 ─────────────────────────────────────────

def test_para_insert_regression():
    r = subprocess.run(
        [sys.executable, "-m", "pytest",
         "tests/test_web_office_para_edit_structure_para_insert.py",
         "-q", "--tb=short"],
        capture_output=True, text=True, cwd=str(PR), timeout=60)
    assert r.returncode == 0, r.stdout[-2000:]


# ── 12. ApplyFormat 회귀 샘플 ────────────────────────────────────

def test_applyformat_regression_sample():
    r = subprocess.run(
        [sys.executable, "-m", "pytest",
         "tests/test_web_office_para_edit_applyformat_toolbar_command_closeout.py",
         "tests/test_web_office_para_edit_applyformat_matching_existing_charpr_closeout.py",
         "-q", "--tb=short"],
        capture_output=True, text=True, cwd=str(PR), timeout=120)
    assert r.returncode == 0, r.stdout[-2000:]


# ── 13. 안전 게이트 — 금지 심볼 없음 ─────────────────────────────

def test_no_cell_merge_in_adapter():
    src = (PR / "scripts/hwpx/web_office/paragraph_writer_adapter.py"
           ).read_text(encoding="utf-8")
    assert "_apply_para_delete_cell" not in src
    assert "TABLE_CELL_MERGE" not in src


def test_no_new_charpr_in_adapter():
    src = (PR / "scripts/hwpx/web_office/paragraph_writer_adapter.py"
           ).read_text(encoding="utf-8")
    assert "def create_char_pr" not in src


# ── 14. audit script PASS ────────────────────────────────────────

def test_audit_script_pass():
    r = subprocess.run(
        [sys.executable,
         "scripts/ops/audit_web_office_para_edit_structure_para_delete_closeout.py"],
        capture_output=True, text=True, cwd=str(PR), timeout=120)
    out = json.loads(r.stdout.strip())
    assert out.get("verdict") == "PASS", out
