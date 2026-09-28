"""WEB-OFFICE-PARA-EDIT-CONTENT-CLOSEOUT-01 감리 검사.

PARA-EDIT 내용 편집 부분 준공 동결의 문서·테스트 등기 + audit 결과 +
baseline commit 무수정 잠금 확인. 신규 writer 시공 없음.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PR))

CLOSEOUT_DOC = PR / "docs/architecture/web_office_para_edit_content_closeout.md"
# 좌표조회 수리 준공 후 갱신 (334d665 → b9782a5) — ro_view_importer._find_cell_elem
# 이 셀 문단을 격자주소가 아닌 셀 순번으로 찾도록 교정.
# 셀 텍스트 손실·중첩 표 중복 수리 준공 후 재갱신 (b9782a5 → 3f94c2a) —
# hp:t 인라인 tail 유실 + 중첩 표 내용 중복 제거. 정당 변경 확인 후 재고정.
BASELINE_COMMIT = "5b33ccd"  # hp:ctrl 텍스트유출 수리 준공 후 갱신 (cbe8cce -> 5b33ccd)


# ── 1. 시방서 존재 + baseline 표기 ─────────────────────────────


def test_closeout_doc_exists():
    assert CLOSEOUT_DOC.is_file(), CLOSEOUT_DOC


def test_closeout_doc_lists_baseline_commit():
    src = CLOSEOUT_DOC.read_text(encoding="utf-8")
    assert BASELINE_COMMIT in src, f"closeout doc 에 baseline {BASELINE_COMMIT} 미명시"


# ── 2. 완료 범위 4종 ───────────────────────────────────────────


def test_closeout_doc_lists_completed_scopes():
    src = CLOSEOUT_DOC.read_text(encoding="utf-8")
    for phrase in (
        "single-run cell",
        "single-run body",
        "multi-run cell",
        "multi-run body",
    ):
        assert phrase in src, phrase


def test_closeout_doc_lists_completed_command_types():
    src = CLOSEOUT_DOC.read_text(encoding="utf-8")
    for ct in ("SET_CELL_TEXT", "TYPE_TEXT", "REPLACE_TEXT_RANGE", "DELETE_TEXT_RANGE"):
        assert ct in src, ct


def test_closeout_doc_lists_v_gates():
    src = CLOSEOUT_DOC.read_text(encoding="utf-8")
    for v in (
        "V1_RANGE_POSITION_OK",
        "V2_NO_CROSS_PARAGRAPH_LEAK",
        "V3_UNTOUCHED_RUNS_PRESERVED",
        "V4_CHARPR_PRESERVED",
        "V5_PARPR_PRESERVED",
        "V6_OUTPUT_ISOLATED",
        "V7_READBACK_MATCH",
    ):
        assert v in src, v


def test_closeout_doc_lists_ime_smoke():
    src = CLOSEOUT_DOC.read_text(encoding="utf-8")
    assert "IME" in src
    assert "compositionend" in src


# ── 3. 차단 범위 명시 ──────────────────────────────────────────


def test_closeout_doc_lists_blocked_scopes():
    src = CLOSEOUT_DOC.read_text(encoding="utf-8")
    for phrase in (
        "ApplyFormat",
        "paragraph add / delete",
        "table structure",
        "image / stamp / signature",
        "AI 자동 입력",
        "원본 HWPX 직접 수정",
        "POLICY_CARET_RIGHT",
    ):
        assert phrase in src, phrase


# ── 4. 핵심 회귀 자재 (테스트 파일) 모두 존재 ───────────────

REQUIRED_TESTS = [
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
    missing = [name for name in REQUIRED_TESTS if not (PR / "tests" / name).is_file()]
    assert not missing, missing


def test_required_tests_listed_in_audit():
    """audit 의 REQUIRED_TESTS 목록과 본 테스트 파일 목록이 일치."""
    from scripts.ops.audit_web_office_para_edit_content_closeout import (
        REQUIRED_TESTS as AUDIT_TESTS,
    )

    audit_names = {Path(p).name for p in AUDIT_TESTS}
    expected = set(REQUIRED_TESTS)
    assert audit_names == expected, (
        f"missing in audit: {expected - audit_names}, extra in audit: {audit_names - expected}"
    )


# ── 5. 핵심 시공 자재 (소스) 모두 존재 ────────────────────

REQUIRED_SOURCES = [
    "scripts/hwpx/web_office/para_edit_model.py",
    "scripts/hwpx/web_office/paragraph_edit_plan.py",
    "scripts/hwpx/web_office/paragraph_writer_adapter.py",
    "scripts/hwpx/web_office/paragraph_save_pipeline.py",
    "scripts/hwpx/web_office/paragraph_save_verify7.py",
    "scripts/hwpx/web_office/para_edit_e2e_pipeline.py",
    "scripts/hwpx/web_office/ro_view_importer.py",
    "scripts/hwpx/hwpx_paragraph_ops.py",
    "frontend/web_office_viewer/para_edit_state.mjs",
    "frontend/web_office_viewer/para_edit_runtime.mjs",
]
# WEB-OFFICE-PARA-EDIT-APPLYFORMAT-EXISTING-CHARPR-01: 본 후속 공정에서
# 다음 자재는 ApplyFormat 활성화로 변경되었다 — d61f10f 잠금에서 해제.
LOCKED_VS_BASELINE = [
    "scripts/hwpx/web_office/paragraph_save_pipeline.py",
    "scripts/hwpx/web_office/ro_view_importer.py",
    # WEB-OFFICE-PARA-EDIT-APPLYFORMAT-TOOLBAR-COMMAND-01:
    # para_edit_state.mjs 는 applyFormatToSelection 추가로 본 LOCKED 에서 제거.
    "frontend/web_office_viewer/para_edit_runtime.mjs",
]


def test_all_required_sources_exist():
    missing = [rel for rel in REQUIRED_SOURCES if not (PR / rel).is_file()]
    assert not missing, missing


# ── 6. baseline commit 무수정 (잠금 범위) ────────────────


def test_locked_sources_unchanged_vs_baseline():
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
            text=True, encoding="utf-8", errors="replace",
            cwd=str(PR),
            timeout=20,
        )
        assert r.returncode == 0, (rel, r.stderr)
        assert not r.stdout.strip(), f"{rel} changed vs {BASELINE_COMMIT}"


# ── 7. 차단 범위 코드 흔적 없음 ────────────────────────────


def test_no_apply_format_paragraph_add_delete_in_adapter():
    """주요 모듈에 ApplyFormat / paragraph add-delete / table-image
    함수 정의가 없음을 정적 확인.
    """
    import re

    # WEB-OFFICE-PARA-EDIT-APPLYFORMAT-EXISTING-CHARPR-01:
    # apply_format 패턴은 ApplyFormat 활성화로 차단 해제. create_char_pr
    # (신규 charPr 생성) 만 계속 금지.
    forbidden = [
        r"def\s+apply_paragraph_add\b",
        r"def\s+apply_paragraph_delete\b",
        r"def\s+create_char_pr\b",
        r"def\s+add_table_row\b",
        r"def\s+delete_table_row\b",
        r"def\s+insert_image\b",
        r"POLICY_CARET_RIGHT",
    ]
    targets = [
        "scripts/hwpx/web_office/paragraph_writer_adapter.py",
        "scripts/hwpx/web_office/para_edit_model.py",
        "scripts/hwpx/web_office/paragraph_edit_plan.py",
        "scripts/hwpx/hwpx_paragraph_ops.py",
    ]
    for rel in targets:
        src = (PR / rel).read_text(encoding="utf-8")
        for pat in forbidden:
            assert not re.search(pat, src), (rel, pat)


# ── 8. audit verdict PASS ──────────────────────────────────


def test_audit_script_pass():
    from scripts.ops.audit_web_office_para_edit_content_closeout import audit

    rep = audit()
    fails = [f for f in rep["findings"] if f.get("level") == "FAIL"]
    assert not fails, json.dumps(rep, ensure_ascii=False, indent=2)
    assert rep["verdict"] in ("PASS", "WARN"), rep
