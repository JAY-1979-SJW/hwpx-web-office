"""WEB-OFFICE-P3-EMPTY-PARAGRAPH-WRITER-GUARD-01 테스트.

빈 paragraph / 빈 run 의 writer/save/readback 소실 방지 게이트 검증.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

PR = Path(__file__).parents[1]
BASELINE_COMMIT = "9b9a30f"

_CMD_MJS = PR / "frontend/web_office_viewer/para_edit_command.mjs"
_STATE_MJS = PR / "frontend/web_office_viewer/para_edit_state.mjs"
_SMOKE_MJS = PR / "frontend/web_office_viewer/para_edit_structure_smoke.mjs"
_MODEL_PY = PR / "scripts/hwpx/web_office/para_edit_model.py"


# ── Python model 상수 ────────────────────────────────────────────────


def test_python_reason_empty_para_id_missing():
    sys.path.insert(0, str(PR))
    from scripts.hwpx.web_office.para_edit_model import REASON_EMPTY_PARA_ID_MISSING

    assert REASON_EMPTY_PARA_ID_MISSING == "EMPTY_PARA_ID_MISSING"


def test_python_reason_empty_para_pr_missing():
    sys.path.insert(0, str(PR))
    from scripts.hwpx.web_office.para_edit_model import REASON_EMPTY_PARA_PR_MISSING

    assert REASON_EMPTY_PARA_PR_MISSING == "EMPTY_PARA_PR_MISSING"


def test_python_reason_empty_run_charpr_missing():
    sys.path.insert(0, str(PR))
    from scripts.hwpx.web_office.para_edit_model import REASON_EMPTY_RUN_CHARPR_MISSING

    assert REASON_EMPTY_RUN_CHARPR_MISSING == "EMPTY_RUN_CHARPR_MISSING"


def test_python_reason_paragraph_count_decreased():
    sys.path.insert(0, str(PR))
    from scripts.hwpx.web_office.para_edit_model import REASON_PARAGRAPH_COUNT_DECREASED

    assert REASON_PARAGRAPH_COUNT_DECREASED == "PARAGRAPH_COUNT_DECREASED"


# ── validateEmptyParagraphIntegrity ──────────────────────────────────


def test_validate_empty_paragraph_integrity_valid():
    sys.path.insert(0, str(PR))
    from scripts.hwpx.web_office.para_edit_model import (
        Paragraph,
        ParaTextRun,
        validate_empty_paragraph_integrity,
    )

    p = Paragraph("P1", "6", [ParaTextRun("P1_run0", "hello", "11")])
    result = validate_empty_paragraph_integrity(p)
    assert result["valid"] is True
    assert result["issues"] == []


def test_validate_empty_paragraph_integrity_no_par_pr():
    sys.path.insert(0, str(PR))
    from scripts.hwpx.web_office.para_edit_model import (
        REASON_EMPTY_PARA_PR_MISSING,
        Paragraph,
        ParaTextRun,
        validate_empty_paragraph_integrity,
    )

    p = Paragraph("P2", None, [ParaTextRun("P2_run0", "", "11")])
    result = validate_empty_paragraph_integrity(p)
    assert result["valid"] is False
    assert REASON_EMPTY_PARA_PR_MISSING in result["issues"]


def test_validate_empty_paragraph_integrity_empty_run_no_charpr():
    sys.path.insert(0, str(PR))
    from scripts.hwpx.web_office.para_edit_model import (
        REASON_EMPTY_RUN_CHARPR_MISSING,
        Paragraph,
        ParaTextRun,
        validate_empty_paragraph_integrity,
    )

    p = Paragraph("P3", "6", [ParaTextRun("P3_run0", "", None)])
    result = validate_empty_paragraph_integrity(p)
    assert result["valid"] is False
    assert REASON_EMPTY_RUN_CHARPR_MISSING in result["issues"]


# ── normalize_paragraph — 빈 paragraph 보존 ──────────────────────────


def test_normalize_preserves_paragraphid():
    sys.path.insert(0, str(PR))
    from scripts.hwpx.web_office.para_edit_model import (
        Paragraph,
        ParaTextRun,
        normalize_paragraph,
    )

    p = Paragraph("MYID", "6", [ParaTextRun("MYID_r0", "", "11")])
    result = normalize_paragraph(p)
    assert result.paragraphId == "MYID"


def test_normalize_preserves_parpr():
    sys.path.insert(0, str(PR))
    from scripts.hwpx.web_office.para_edit_model import (
        Paragraph,
        ParaTextRun,
        normalize_paragraph,
    )

    p = Paragraph("P4", "42", [ParaTextRun("P4_r0", "", "11")])
    result = normalize_paragraph(p)
    assert result.parPrIDRef == "42"


def test_normalize_keeps_at_least_one_run():
    sys.path.insert(0, str(PR))
    from scripts.hwpx.web_office.para_edit_model import (
        Paragraph,
        ParaTextRun,
        normalize_paragraph,
    )

    p = Paragraph("P5", "6", [ParaTextRun("P5_r0", "", "11")])
    result = normalize_paragraph(p)
    assert len(result.runs) >= 1


def test_normalize_empty_run_preserves_charpr():
    sys.path.insert(0, str(PR))
    from scripts.hwpx.web_office.para_edit_model import (
        Paragraph,
        ParaTextRun,
        normalize_paragraph,
    )

    p = Paragraph("P6", "6", [ParaTextRun("P6_r0", "", "99")])
    result = normalize_paragraph(p)
    assert result.runs[0].charPrIDRef == "99"


def test_delete_all_text_paragraph_survives():
    """전체 텍스트 삭제 후 paragraph 자체는 보존."""
    sys.path.insert(0, str(PR))
    from scripts.hwpx.web_office.para_edit_model import (
        Paragraph,
        ParaTextRun,
        normalize_paragraph,
    )

    empty_run = ParaTextRun("DEL1_r0", "", "11")
    p_after = Paragraph("DEL1", "6", [empty_run])
    result = normalize_paragraph(p_after)
    assert result.paragraphId == "DEL1"
    assert len(result.runs) == 1
    assert result.runs[0].charPrIDRef == "11"


def test_multi_run_delete_paragraph_survives():
    """multi-run 모두 빈 text → paragraph 보존 (첫 run charPr 유지)."""
    sys.path.insert(0, str(PR))
    from scripts.hwpx.web_office.para_edit_model import (
        Paragraph,
        ParaTextRun,
        normalize_paragraph,
    )

    p = Paragraph(
        "MR1",
        "6",
        [
            ParaTextRun("MR1_r0", "", "C1"),
            ParaTextRun("MR1_r1", "", "C2"),
        ],
    )
    result = normalize_paragraph(p)
    assert result.paragraphId == "MR1"
    assert len(result.runs) == 1
    assert result.runs[0].charPrIDRef == "C1"


# ── validateParagraphCountPreserved ──────────────────────────────────


def test_validate_paragraph_count_same():
    sys.path.insert(0, str(PR))
    from scripts.hwpx.web_office.para_edit_model import (
        Paragraph,
        validate_paragraph_count_preserved,
    )

    before = [Paragraph("A", "6", []), Paragraph("B", "6", [])]
    after = [Paragraph("A", "6", []), Paragraph("B", "6", [])]
    result = validate_paragraph_count_preserved(before, after)
    assert result["valid"] is True


def test_validate_paragraph_count_decreased_rejects():
    sys.path.insert(0, str(PR))
    from scripts.hwpx.web_office.para_edit_model import (
        REASON_PARAGRAPH_COUNT_DECREASED,
        Paragraph,
        validate_paragraph_count_preserved,
    )

    before = [Paragraph("A", "6", []), Paragraph("B", "6", [])]
    after = [Paragraph("A", "6", [])]
    result = validate_paragraph_count_preserved(before, after)
    assert result["valid"] is False
    assert result["reason"] == REASON_PARAGRAPH_COUNT_DECREASED


def test_validate_paragraph_count_increased_ok():
    sys.path.insert(0, str(PR))
    from scripts.hwpx.web_office.para_edit_model import (
        Paragraph,
        validate_paragraph_count_preserved,
    )

    before = [Paragraph("A", "6", [])]
    after = [Paragraph("A", "6", []), Paragraph("B", "6", [])]
    result = validate_paragraph_count_preserved(before, after)
    assert result["valid"] is True


# ── JS exports 존재 확인 ─────────────────────────────────────────────


def test_js_exports_validate_empty_paragraph_integrity():
    src = _CMD_MJS.read_text(encoding="utf-8")
    assert "validateEmptyParagraphIntegrity" in src
    assert "export function validateEmptyParagraphIntegrity" in src


def test_js_exports_validate_paragraph_count_preserved():
    src = _CMD_MJS.read_text(encoding="utf-8")
    assert "validateParagraphCountPreserved" in src
    assert "export function validateParagraphCountPreserved" in src


def test_js_exports_empty_para_reason_constants():
    src = _CMD_MJS.read_text(encoding="utf-8")
    assert "REASON_EMPTY_PARA_ID_MISSING" in src
    assert "REASON_EMPTY_PARA_PR_MISSING" in src
    assert "REASON_EMPTY_RUN_CHARPR_MISSING" in src
    assert "REASON_PARAGRAPH_COUNT_DECREASED" in src


def test_js_state_imports_empty_para_guard():
    src = _STATE_MJS.read_text(encoding="utf-8")
    assert "validateEmptyParagraphIntegrity" in src
    assert "_emptyParaGuard" in src


# ── JS smoke ─────────────────────────────────────────────────────────


@pytest.mark.skipif(
    not __import__("shutil").which("node"),
    reason="WARN_ENV_DEPENDENT: node not available",
)
def test_js_smoke_pass():
    result = subprocess.run(
        ["node", str(_SMOKE_MJS)],
        capture_output=True,
        text=True, encoding="utf-8", errors="replace",
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data.get("verdict") == "PASS", json.dumps(data, indent=2)
    checks = data.get("checks", {})
    for key in (
        "emptyParaIntegrityValid",
        "emptyParaPrMissingReject",
        "emptyParaRunCharPrMissingReject",
        "normEmptyParaPreserved",
        "paragraphCountDecreaseReject",
        "paraInsertEmptyBackParaPreserved",
    ):
        assert checks.get(key, {}).get("ok"), f"smoke check failed: {key}"
    failed = [k for k, v in checks.items() if not v.get("ok")]
    assert not failed, f"FAILED checks: {failed}"


# ── 기존 회귀 ─────────────────────────────────────────────────────────


def test_regression_existing_para_edit_tests_pass():
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_web_office_para_edit_structure_para_insert.py",
            "tests/test_web_office_para_edit_structure_para_delete.py",
            "tests/test_web_office_p3_run_split_merge_charpr_guard.py",
            "-q",
            "--tb=short",
        ],
        capture_output=True,
        text=True, encoding="utf-8", errors="replace",
        timeout=180,
        cwd=str(PR),
    )
    assert result.returncode == 0, result.stdout + result.stderr


# ── git diff --check ──────────────────────────────────────────────────


def test_git_diff_check():
    result = subprocess.run(
        ["git", "diff", "--check", "HEAD"],
        capture_output=True,
        text=True, encoding="utf-8", errors="replace",
        cwd=str(PR),
    )
    assert result.returncode == 0, result.stdout + result.stderr


# ── baseline lock ─────────────────────────────────────────────────────

_LOCKED_FILES = [
    "frontend/web_office_viewer/para_edit_command.mjs",
    "frontend/web_office_viewer/para_edit_state.mjs",
    "scripts/hwpx/web_office/para_edit_model.py",
    "frontend/web_office_viewer/para_edit_structure_smoke.mjs",
]


def test_locked_files_changed_from_baseline():
    """이번 공정 대상 파일이 BASELINE 이후 변경되어야 한다."""
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
