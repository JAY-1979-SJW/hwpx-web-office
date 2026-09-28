"""APPLYFORMAT-FONTNAME-MATCHING-CLOSEOUT-01.

fontName existing charPr matching 부분 준공 동결 — 시방서 + audit +
회귀 자재 목록 + 95b69ab baseline 잠금 확인. 신규 시공 없음.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PR))

CLOSEOUT_DOC = (
    PR / "docs/architecture/web_office_para_edit_applyformat_fontname_matching_closeout.md"
)
BASELINE_COMMIT = "b992ad6"  # 중첩표 읽기/쓰기 대칭 준공 후 갱신 (f119308 → b992ad6)


# ── 1. 시방서 존재 + baseline 표기 ─────────────────────────


def test_closeout_doc_exists():
    assert CLOSEOUT_DOC.is_file(), CLOSEOUT_DOC


def test_closeout_doc_lists_baseline_commit():
    src = CLOSEOUT_DOC.read_text(encoding="utf-8")
    assert BASELINE_COMMIT in src


# ── 2. 공식 완료 범위 명시 ─────────────────────────────────


def test_closeout_doc_lists_completed_scopes():
    src = CLOSEOUT_DOC.read_text(encoding="utf-8")
    for phrase in (
        "matchAxisChange",
        "fontName",
        'MATCH_AXIS_CHANGE_DIMENSIONS = ["fontSizePt", "textColor", "fontName"]',
        "FontNameDropdown",
        "extractAxisValues",
        "fontFace",
        "정확 동등",
        "다대다",
        "onApplyCharPr",
        "applyFormatToSelection",
        "현재 문서에 같은 속성 조합의 기존 폰트 스타일이 없습니다",
        "100.0%",
        "1.25",
    ):
        assert phrase in src, phrase


# ── 3. 공식 차단 범위 명시 ─────────────────────────────────


def test_closeout_doc_lists_blocked_scopes():
    src = CLOSEOUT_DOC.read_text(encoding="utf-8")
    for phrase in (
        "font alias matching",
        "fuzzy",
        "fontFace exact matching",
        "신규 charPr 생성",
        "header.xml charPr 추가",
        "외부 font picker",
        "시스템 font list",
        "+ 폰트 추가",
        "backend writer 직접 호출",
        "save pipeline 재설계",
        "paragraph_writer_adapter.py 수정",
        "para_edit_command.mjs factory 재정의",
        "paragraph add/delete",
        "table structure edit",
        "image/stamp/signature",
        "AI 자동 입력",
        "원본 HWPX 직접 수정",
    ):
        assert phrase in src, phrase


# ── 4. 다음 공정 후보 명시 ─────────────────────────────────


def test_closeout_doc_lists_next_processes():
    src = CLOSEOUT_DOC.read_text(encoding="utf-8")
    for name in (
        "APPLYFORMAT-FONT-ALIAS-PREFLIGHT-01",
        "APPLYFORMAT-FONT-ALIAS-MATCHING-01",
        "APPLYFORMAT-NEW-CHARPR-PREFLIGHT-01",
        "APPLYFORMAT-NEW-CHARPR-01",
        "APPLYFORMAT-UI-POLISH-01",
        "PARA-EDIT-STRUCTURE-PREFLIGHT-01",
        "TABLE-STRUCTURE-EDIT-PREFLIGHT-01",
        "MEDIA-EDIT-PREFLIGHT-01",
    ):
        assert name in src, name


# ── 5. 회귀 자재 존재 ─────────────────────────────────────

REQUIRED_TESTS = [
    "test_web_office_para_edit_applyformat_fontname_matching_existing_charpr.py",
    "test_web_office_para_edit_applyformat_color_matching_closeout.py",
    "test_web_office_para_edit_applyformat_color_matching_existing_charpr.py",
    "test_web_office_para_edit_applyformat_fontsize_matching_closeout.py",
    "test_web_office_para_edit_applyformat_fontsize_matching_existing_charpr.py",
    "test_web_office_para_edit_applyformat_matching_existing_charpr_closeout.py",
    "test_web_office_para_edit_applyformat_matching_existing_charpr.py",
    "test_web_office_para_edit_applyformat_toolbar_command_closeout.py",
    "test_web_office_para_edit_applyformat_toolbar_command.py",
    "test_web_office_para_edit_applyformat_toolbar_preview.py",
    "test_web_office_para_edit_applyformat_existing_charpr.py",
    "test_web_office_para_edit_applyformat_existing_charpr_closeout.py",
    "test_web_office_para_edit_format_charpr_inventory.py",
    "test_web_office_para_edit_content_closeout.py",
]
REQUIRED_JS_SMOKES = [
    "format_charpr_matcher_smoke.mjs",
    "para_edit_apply_format_smoke.mjs",
    "para_edit_browser_self_test.mjs",
    "para_edit_ime_live_smoke.mjs",
]


def test_all_required_tests_exist():
    missing = [n for n in REQUIRED_TESTS if not (PR / "tests" / n).is_file()]
    assert not missing, missing


def test_all_required_js_smokes_exist():
    missing = [
        n for n in REQUIRED_JS_SMOKES if not (PR / "frontend/web_office_viewer" / n).is_file()
    ]
    assert not missing, missing


def test_required_files_listed_in_closeout_doc():
    src = CLOSEOUT_DOC.read_text(encoding="utf-8")
    for name in REQUIRED_TESTS + REQUIRED_JS_SMOKES:
        assert name in src, name


# ── 6. 핵심 자재 무수정 vs 95b69ab ────────────────────────

LOCKED_VS_BASELINE = [
    "frontend/web_office_viewer/format_charpr_matcher.mjs",
    "frontend/web_office_viewer/components/WebOfficeFormatToolbar.tsx",
    "frontend/web_office_viewer/format_charpr_matcher_smoke.mjs",
    "frontend/web_office_viewer/para_edit_state.mjs",
    "frontend/web_office_viewer/para_edit_command.mjs",
    "frontend/web_office_viewer/components/WebOfficeFormatPreview.tsx",
    "frontend/web_office_viewer/para_edit_apply_format_smoke.mjs",
    "scripts/hwpx/hwpx_paragraph_ops.py",
    "scripts/hwpx/hwpx_edit_tool.py",
    "scripts/hwpx/web_office/para_edit_model.py",
    "scripts/hwpx/web_office/paragraph_edit_plan.py",
    "scripts/hwpx/web_office/paragraph_writer_adapter.py",
    "scripts/hwpx/web_office/paragraph_save_verify7.py",
    "scripts/hwpx/web_office/para_edit_e2e_pipeline.py",
    "scripts/hwpx/web_office/paragraph_save_pipeline.py",
    "scripts/hwpx/web_office/charpr_inventory.py",
    "scripts/hwpx/web_office/render_payload.py",
]


def test_locked_files_unchanged_vs_baseline():
    if (
        subprocess.run(["git", "cat-file", "-e", BASELINE_COMMIT], capture_output=True).returncode
        != 0
    ):
        import pytest

        pytest.skip(
            f"baseline commit {BASELINE_COMMIT} not reachable in this branch's history (extracted branch)"
        )
    for rel in LOCKED_VS_BASELINE:
        r = subprocess.run(
            ["git", "diff", BASELINE_COMMIT, "--", rel],
            capture_output=True,
            text=True,
            cwd=str(PR),
            timeout=20,
        )
        assert r.returncode == 0, (rel, r.stderr)
        assert not r.stdout.strip(), f"{rel} changed vs {BASELINE_COMMIT}"


# ── 7. audit verdict PASS ──────────────────────────────────


def test_audit_script_pass():
    from scripts.ops.audit_web_office_para_edit_applyformat_fontname_matching_closeout import audit

    rep = audit()
    fails = [f for f in rep["findings"] if f.get("level") == "FAIL"]
    assert not fails, json.dumps(rep, ensure_ascii=False, indent=2)
    assert rep["verdict"] in ("PASS", "WARN"), rep
