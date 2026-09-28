"""WEB-OFFICE-P3-RUN-SPLIT-MERGE-CHARPR-GUARD-01 테스트.

Phase 3 문단 편집에서 run split/merge 시 charPrIDRef 무결성 게이트를 검증.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

PR = Path(__file__).parents[1]
BASELINE_COMMIT = "e04d325"

# ── 파일 경로 ────────────────────────────────────────────────────
_CMD_MJS = PR / "frontend/web_office_viewer/para_edit_command.mjs"
_STATE_MJS = PR / "frontend/web_office_viewer/para_edit_state.mjs"
_SMOKE_MJS = PR / "frontend/web_office_viewer/para_edit_structure_smoke.mjs"
_MODEL_PY = PR / "scripts/hwpx/web_office/para_edit_model.py"


# ─────────────────────────────────────────────────────────────────
# Python model — 상수 존재
# ─────────────────────────────────────────────────────────────────


def test_python_reason_charpr_missing_on_run():
    sys.path.insert(0, str(PR))
    from scripts.hwpx.web_office.para_edit_model import REASON_CHARPR_MISSING_ON_RUN

    assert REASON_CHARPR_MISSING_ON_RUN == "CHARPR_MISSING_ON_RUN"


def test_python_reason_charpr_split_source_missing():
    sys.path.insert(0, str(PR))
    from scripts.hwpx.web_office.para_edit_model import REASON_CHARPR_SPLIT_SOURCE_MISSING

    assert REASON_CHARPR_SPLIT_SOURCE_MISSING == "CHARPR_SPLIT_SOURCE_MISSING"


# ─────────────────────────────────────────────────────────────────
# Python model — validate_run_charpr_integrity
# ─────────────────────────────────────────────────────────────────


def test_python_validate_run_charpr_integrity_valid():
    sys.path.insert(0, str(PR))
    from scripts.hwpx.web_office.para_edit_model import (
        Paragraph,
        ParaTextRun,
        validate_run_charpr_integrity,
    )

    p = Paragraph(
        paragraphId="P1",
        parPrIDRef="6",
        runs=[
            ParaTextRun(runId="P1_r0", text="hello", charPrIDRef="11"),
            ParaTextRun(runId="P1_r1", text=" world", charPrIDRef="11"),
        ],
    )
    result = validate_run_charpr_integrity(p)
    assert result["valid"] is True
    assert result["missingRunIds"] == []


def test_python_validate_run_charpr_integrity_null():
    sys.path.insert(0, str(PR))
    from scripts.hwpx.web_office.para_edit_model import (
        Paragraph,
        ParaTextRun,
        validate_run_charpr_integrity,
    )

    p = Paragraph(
        paragraphId="P2",
        parPrIDRef="6",
        runs=[
            ParaTextRun(runId="P2_r0", text="hello", charPrIDRef=None),
        ],
    )
    result = validate_run_charpr_integrity(p)
    assert result["valid"] is False
    assert "P2_r0" in result["missingRunIds"]


def test_python_validate_run_charpr_integrity_empty_string():
    sys.path.insert(0, str(PR))
    from scripts.hwpx.web_office.para_edit_model import (
        Paragraph,
        ParaTextRun,
        validate_run_charpr_integrity,
    )

    p = Paragraph(
        paragraphId="P3",
        parPrIDRef="6",
        runs=[
            ParaTextRun(runId="P3_r0", text="x", charPrIDRef=""),
        ],
    )
    result = validate_run_charpr_integrity(p)
    assert result["valid"] is False


# ─────────────────────────────────────────────────────────────────
# Python model — split_run charPr guard
# ─────────────────────────────────────────────────────────────────


def test_python_split_run_preserves_charpr():
    sys.path.insert(0, str(PR))
    from scripts.hwpx.web_office.para_edit_model import (
        Paragraph,
        ParaTextRun,
        split_run,
    )

    p = Paragraph(
        paragraphId="S1",
        parPrIDRef="6",
        runs=[
            ParaTextRun(runId="S1_r0", text="Hello World", charPrIDRef="11"),
        ],
    )
    new_p, info = split_run(p, "S1_r0", 5)
    assert info is not None
    left = next(r for r in new_p.runs if r.runId == info["leftRunId"])
    right = next(r for r in new_p.runs if r.runId == info["rightRunId"])
    assert left.charPrIDRef == "11"
    assert right.charPrIDRef == "11"


def test_python_split_run_null_charpr_raises():
    sys.path.insert(0, str(PR))
    from scripts.hwpx.web_office.para_edit_model import (
        REASON_CHARPR_SPLIT_SOURCE_MISSING,
        Paragraph,
        ParaTextRun,
        split_run,
    )

    p = Paragraph(
        paragraphId="S2",
        parPrIDRef="6",
        runs=[
            ParaTextRun(runId="S2_r0", text="hello", charPrIDRef=None),
        ],
    )
    with pytest.raises(ValueError, match=REASON_CHARPR_SPLIT_SOURCE_MISSING):
        split_run(p, "S2_r0", 3)


# ─────────────────────────────────────────────────────────────────
# Python model — merge_runs charPr mismatch
# ─────────────────────────────────────────────────────────────────


def test_python_merge_runs_mismatch_rejected():
    sys.path.insert(0, str(PR))
    from scripts.hwpx.web_office.para_edit_model import (
        REASON_MERGE_CHARPR_MISMATCH,
        Paragraph,
        ParaTextRun,
        merge_runs,
    )

    p = Paragraph(
        paragraphId="M1",
        parPrIDRef="6",
        runs=[
            ParaTextRun(runId="M1_r0", text="First", charPrIDRef="C1"),
            ParaTextRun(runId="M1_r1", text="Second", charPrIDRef="C2"),
        ],
    )
    with pytest.raises(ValueError, match=REASON_MERGE_CHARPR_MISMATCH):
        merge_runs(p, "M1_r0", "M1_r1")


def test_python_merge_runs_same_charpr_ok():
    sys.path.insert(0, str(PR))
    from scripts.hwpx.web_office.para_edit_model import (
        Paragraph,
        ParaTextRun,
        merge_runs,
    )

    p = Paragraph(
        paragraphId="M2",
        parPrIDRef="6",
        runs=[
            ParaTextRun(runId="M2_r0", text="First", charPrIDRef="C1"),
            ParaTextRun(runId="M2_r1", text="Second", charPrIDRef="C1"),
        ],
    )
    merged = merge_runs(p, "M2_r0", "M2_r1")
    assert len(merged.runs) == 1
    assert merged.runs[0].charPrIDRef == "C1"
    assert merged.runs[0].text == "FirstSecond"


# ─────────────────────────────────────────────────────────────────
# JS constants / functions 존재 확인
# ─────────────────────────────────────────────────────────────────


def test_js_command_exports_charpr_reason_constants():
    src = _CMD_MJS.read_text(encoding="utf-8")
    assert "REASON_CHARPR_MISSING_ON_RUN" in src
    assert "REASON_CHARPR_SPLIT_SOURCE_MISSING" in src


def test_js_command_exports_validate_run_charpr_integrity():
    src = _CMD_MJS.read_text(encoding="utf-8")
    assert "validateRunCharPrIntegrity" in src
    assert "export function validateRunCharPrIntegrity" in src


def test_js_split_run_has_null_charpr_guard():
    src = _CMD_MJS.read_text(encoding="utf-8")
    assert "REASON_CHARPR_SPLIT_SOURCE_MISSING" in src
    assert "t.charPrIDRef" in src


def test_js_state_imports_charpr_guard():
    src = _STATE_MJS.read_text(encoding="utf-8")
    assert "validateRunCharPrIntegrity" in src
    assert "REASON_CHARPR_MISSING_ON_RUN" in src
    assert "_charPrGuard" in src


def test_js_state_applies_guard_in_type_text():
    src = _STATE_MJS.read_text(encoding="utf-8")
    assert "_charPrGuard" in src


# ─────────────────────────────────────────────────────────────────
# JS smoke — 69개 체크 전체 PASS
# ─────────────────────────────────────────────────────────────────


@pytest.mark.skipif(
    not (
        Path(r"C:/Program Files/nodejs/node.exe").exists()
        or Path("/usr/bin/node").exists()
        or __import__("shutil").which("node") is not None
    ),
    reason="WARN_ENV_DEPENDENT: node not available",
)
def test_js_smoke_pass():
    result = subprocess.run(
        ["node", str(_SMOKE_MJS)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data.get("verdict") == "PASS", json.dumps(data, indent=2)
    checks = data.get("checks", {})
    assert "charPrIntegrityValidNormal" in checks
    assert "charPrMissingRunReject" in checks
    assert "splitRunPreservesCharPr" in checks
    assert "splitNullCharPrThrows" in checks
    assert "paraDeleteMergeKeepsDifferentCharPrSeparate" in checks
    failed = [k for k, v in checks.items() if not v.get("ok")]
    assert not failed, f"FAILED checks: {failed}"


# ─────────────────────────────────────────────────────────────────
# 기존 Phase 3 회귀 — PARA_INSERT / PARA_DELETE / ApplyFormat
# ─────────────────────────────────────────────────────────────────


def test_regression_existing_para_edit_tests_pass():
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_web_office_para_edit_structure_para_insert.py",
            "tests/test_web_office_para_edit_structure_para_delete.py",
            "-q",
            "--tb=short",
        ],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(PR),
    )
    assert result.returncode == 0, result.stdout + result.stderr


# ─────────────────────────────────────────────────────────────────
# git diff --check
# ─────────────────────────────────────────────────────────────────


def test_git_diff_check():
    result = subprocess.run(
        ["git", "diff", "--check", "HEAD"],
        capture_output=True,
        text=True,
        cwd=str(PR),
    )
    assert result.returncode == 0, result.stdout + result.stderr


# ─────────────────────────────────────────────────────────────────
# baseline 잠금 — 대상 파일 변경 기록
# ─────────────────────────────────────────────────────────────────

_LOCKED_FILES = [
    "frontend/web_office_viewer/para_edit_command.mjs",
    "frontend/web_office_viewer/para_edit_state.mjs",
    "scripts/hwpx/web_office/para_edit_model.py",
    "frontend/web_office_viewer/para_edit_structure_smoke.mjs",
]


def test_locked_files_changed_from_baseline():
    """이번 공정에서 변경된 파일 목록 확인 (BASELINE 이후 diff 존재해야 함)."""
    import subprocess

    changed = []
    for f in _LOCKED_FILES:
        r = subprocess.run(
            ["git", "diff", BASELINE_COMMIT, "--", f],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(PR),
        )
        if r.stdout.strip():
            changed.append(f)
    assert len(changed) == len(_LOCKED_FILES), (
        f"예상 {len(_LOCKED_FILES)}개 변경, 실제 {len(changed)}개: {changed}"
    )
