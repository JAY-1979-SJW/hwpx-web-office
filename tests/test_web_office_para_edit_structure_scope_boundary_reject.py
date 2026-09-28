"""WEB-OFFICE-PARA-EDIT-STRUCTURE-SCOPE-BOUNDARY-REJECT-01 감리.

body paragraph (kind=="block") 외 scope에서 PARA_INSERT / PARA_DELETE가
명시적 reason code로 reject되는지 고정한다.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PR = Path(__file__).parents[1]

BASELINE_COMMIT = "15364fe"

SCOPE_REASON_CONSTANTS = [
    "REASON_HEADER_SCOPE_NOT_SUPPORTED",
    "REASON_FOOTER_SCOPE_NOT_SUPPORTED",
    "REASON_FOOTNOTE_SCOPE_NOT_SUPPORTED",
    "REASON_ENDNOTE_SCOPE_NOT_SUPPORTED",
    "REASON_CAPTION_SCOPE_NOT_SUPPORTED",
    "REASON_BODY_SCOPE_ONLY_SUPPORTED",
]

SCOPE_REASON_VALUES = [
    "HEADER_SCOPE_NOT_SUPPORTED",
    "FOOTER_SCOPE_NOT_SUPPORTED",
    "FOOTNOTE_SCOPE_NOT_SUPPORTED",
    "ENDNOTE_SCOPE_NOT_SUPPORTED",
    "CAPTION_SCOPE_NOT_SUPPORTED",
    "BODY_SCOPE_ONLY_SUPPORTED",
]

SMOKE_CHECKS = [
    "headerScopeInsertReject",
    "footerScopeInsertReject",
    "captionScopeInsertReject",
    "headerScopeDeleteReject",
    "footerScopeDeleteReject",
    "unknownScopeDeleteReject",
]


# ── 1. para_edit_model.py reason constants ──────────────────────


def test_scope_reason_constants_in_model():
    src = (PR / "scripts/hwpx/web_office/para_edit_model.py").read_text(encoding="utf-8")
    for name in SCOPE_REASON_CONSTANTS:
        assert name in src, name


def test_scope_reason_values_in_model():
    src = (PR / "scripts/hwpx/web_office/para_edit_model.py").read_text(encoding="utf-8")
    for val in SCOPE_REASON_VALUES:
        assert val in src, val


# ── 2. _scopeBoundaryRejectReason helper in para_edit_state.mjs ─


def test_scope_helper_function_exists():
    src = (PR / "frontend/web_office_viewer/para_edit_state.mjs").read_text(encoding="utf-8")
    assert "_scopeBoundaryRejectReason" in src


def test_scope_helper_covers_header():
    src = (PR / "frontend/web_office_viewer/para_edit_state.mjs").read_text(encoding="utf-8")
    assert '"header"' in src
    assert "HEADER_SCOPE_NOT_SUPPORTED" in src


def test_scope_helper_covers_footer():
    src = (PR / "frontend/web_office_viewer/para_edit_state.mjs").read_text(encoding="utf-8")
    assert '"footer"' in src
    assert "FOOTER_SCOPE_NOT_SUPPORTED" in src


def test_scope_helper_covers_footnote():
    src = (PR / "frontend/web_office_viewer/para_edit_state.mjs").read_text(encoding="utf-8")
    assert '"footnote"' in src
    assert "FOOTNOTE_SCOPE_NOT_SUPPORTED" in src


def test_scope_helper_covers_endnote():
    src = (PR / "frontend/web_office_viewer/para_edit_state.mjs").read_text(encoding="utf-8")
    assert '"endnote"' in src
    assert "ENDNOTE_SCOPE_NOT_SUPPORTED" in src


def test_scope_helper_covers_caption():
    src = (PR / "frontend/web_office_viewer/para_edit_state.mjs").read_text(encoding="utf-8")
    assert '"caption"' in src
    assert "CAPTION_SCOPE_NOT_SUPPORTED" in src


def test_scope_helper_has_fallback():
    src = (PR / "frontend/web_office_viewer/para_edit_state.mjs").read_text(encoding="utf-8")
    assert "BODY_SCOPE_ONLY_SUPPORTED" in src


# ── 3. guard uses helper (no more hardcoded string in guards) ────


def test_split_para_uses_scope_helper():
    src = (PR / "frontend/web_office_viewer/para_edit_state.mjs").read_text(encoding="utf-8")
    assert "_scopeBoundaryRejectReason" in src
    assert "_insertScopeReject" in src


def test_merge_para_uses_scope_helper():
    src = (PR / "frontend/web_office_viewer/para_edit_state.mjs").read_text(encoding="utf-8")
    assert "_deleteScopeReject" in src


# ── 4. JS smoke — new scope boundary checks pass ─────────────────


def test_js_smoke_scope_boundary_pass():
    smoke = PR / "frontend/web_office_viewer/para_edit_structure_smoke.mjs"
    r = subprocess.run(["node", str(smoke)], capture_output=True, text=True, timeout=30)
    out = json.loads(r.stdout.strip().split("\n")[-1])
    assert out.get("verdict") == "PASS", out
    checks = out.get("checks", {})
    for name in SMOKE_CHECKS:
        assert checks.get(name, {}).get("ok") is True, f"smoke check failed: {name}"


# ── 5. 안전 게이트 — header/footer 편집 활성화 없음 ─────────────


def test_no_header_edit_in_state():
    src = (PR / "frontend/web_office_viewer/para_edit_state.mjs").read_text(encoding="utf-8")
    assert "activateHeaderEdit" not in src
    assert "enableHeaderScope" not in src


def test_no_header_xml_mutation():
    src = (PR / "scripts/hwpx/web_office/paragraph_writer_adapter.py").read_text(encoding="utf-8")
    assert 'package.entries["header.xml"]' not in src


def test_no_new_charpr():
    src = (PR / "scripts/hwpx/web_office/paragraph_writer_adapter.py").read_text(encoding="utf-8")
    assert "def create_char_pr" not in src


# ── 6. baseline lock — scope boundary 자재 무수정 ────────────────

LOCKED_VS_BASELINE = [
    "frontend/web_office_viewer/para_edit_command.mjs",
    "frontend/web_office_viewer/para_edit_runtime.mjs",
    "scripts/hwpx/web_office/paragraph_save_pipeline.py",
    "scripts/hwpx/web_office/para_edit_e2e_pipeline.py",
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
        assert not r.stdout.strip(), f"{rel} changed vs {BASELINE_COMMIT}"


# ── 7. HWPX staged 0 ─────────────────────────────────────────────


def test_hwpx_staged_zero():
    r = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        capture_output=True,
        text=True,
        cwd=str(PR),
        timeout=10,
    )
    hwpx_staged = [
        f
        for f in r.stdout.strip().splitlines()
        if any(
            f.startswith(p)
            for p in (
                "frontend/web_office_viewer/",
                "scripts/hwpx/web_office/",
                "tests/test_web_office_",
                "scripts/ops/audit_web_office_",
                "docs/architecture/web_office_",
            )
        )
    ]
    assert not hwpx_staged, f"HWPX staged: {hwpx_staged}"


# ── 8. 기존 PARA_INSERT/DELETE 회귀 ──────────────────────────────


def test_para_insert_regression():
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_web_office_para_edit_structure_para_insert.py",
            "-q",
            "--tb=short",
        ],
        capture_output=True,
        text=True,
        cwd=str(PR),
        timeout=60,
    )
    assert r.returncode == 0, r.stdout[-2000:]


def test_para_delete_regression():
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_web_office_para_edit_structure_para_delete.py",
            "-q",
            "--tb=short",
        ],
        capture_output=True,
        text=True,
        cwd=str(PR),
        timeout=60,
    )
    assert r.returncode == 0, r.stdout[-2000:]


# ── 9. audit script PASS ─────────────────────────────────────────


def test_audit_script_pass():
    r = subprocess.run(
        [
            sys.executable,
            "scripts/ops/audit_web_office_para_edit_structure_scope_boundary_reject.py",
        ],
        capture_output=True,
        text=True,
        cwd=str(PR),
        timeout=120,
    )
    out = json.loads(r.stdout.strip())
    assert out.get("verdict") == "PASS", out
