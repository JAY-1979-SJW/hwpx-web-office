"""HWPX-FORM-AUTO-FILL-WRITER-REAL-LIKE-USER-FLOW-CLOSEOUT-14 tests."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLOSEOUT = ROOT / "docs" / "reports" / "HWPX_FORM_AUTO_FILL_USER_FLOW_CLOSEOUT_14.md"

ABS_PATH_RE = re.compile(r"(?<![A-Za-z])([A-Za-z]:[\\/]|/(home|tmp|var|Users)/)")
RAW_FILENAME_RE = re.compile(r"\b[^\\/:\s]+\.hwpx\b", re.IGNORECASE)
PII_RE = re.compile(
    r"(\d{6}-\d{7}|\d{3}-\d{2}-\d{5}|\d{2,3}-\d{3,4}-\d{4}|"
    r"\d{2,6}-\d{2,6}-\d{2,6}|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})"
)


def _text() -> str:
    return CLOSEOUT.read_text(encoding="utf-8")


def test_01_closeout_report_exists() -> None:
    assert CLOSEOUT.is_file()


def test_02_completed_stages_listed() -> None:
    text = _text()
    for stage in [
        "Form index / recommend",
        "Form field catalog",
        "Upload document parser",
        "Field mapper",
        "Review panel",
        "Human approval gate",
        "Sandbox writer",
        "Readback hardening",
        "Download review",
        "Final export gate",
        "E2E smoke",
        "API route + frontend contract",
        "Browser smoke",
        "Real-file preflight",
        "Real-like sandbox batch",
        "Real-like browser batch",
        "Real-like API batch",
        "Real-like API browser E2E",
    ]:
        assert stage in text


def test_03_sandbox_only_scope_documented() -> None:
    text = _text()
    assert "SANDBOX_ONLY" in text
    assert "Output copy writing only" in text


def test_04_prohibited_real_user_file_scope_documented() -> None:
    assert "Real user source file input" in _text()


def test_05_source_overwrite_prohibition_documented() -> None:
    text = _text()
    assert "Source HWPX overwrite" in text
    assert "Source overwrite endpoint" in text


def test_06_production_write_prohibition_documented() -> None:
    assert "Production write" in _text()


def test_07_final_deploy_prohibition_documented() -> None:
    assert "Final deploy endpoint" in _text()


def test_08_promotion_criteria_documented() -> None:
    text = _text()
    for token in [
        "At least 30 sanitized real-like samples",
        "readbackFail remains 0",
        "sourceMutation remains 0",
        "unexpectedMutation remains 0",
        "user file upload gate",
        "personal information detection and block gate",
    ]:
        assert token in text


def test_09_latest_commit_referenced() -> None:
    assert "ad53a0f" in _text()


def test_10_previous_pass_verdicts_summarized() -> None:
    text = _text()
    for verdict in [
        "PASS_HWPX_FORM_AUTO_FILL_WRITER_API_ROUTE_AND_FRONTEND",
        "PASS_HWPX_FORM_AUTO_FILL_WRITER_BROWSER_SMOKE",
        "PASS_HWPX_FORM_AUTO_FILL_WRITER_REAL_FILE_PREFLIGHT",
        "PASS_HWPX_FORM_AUTO_FILL_WRITER_REAL_LIKE_SANDBOX_BATCH",
        "PASS_HWPX_FORM_AUTO_FILL_WRITER_REAL_LIKE_BROWSER_BATCH",
        "PASS_HWPX_FORM_AUTO_FILL_WRITER_REAL_LIKE_API_BATCH",
        "PASS_HWPX_FORM_AUTO_FILL_WRITER_REAL_LIKE_API_BROWSER_E2E",
    ]:
        assert verdict in text


def test_11_no_raw_path_leak() -> None:
    assert not ABS_PATH_RE.search(_text())


def test_12_no_raw_filename_leak() -> None:
    assert not RAW_FILENAME_RE.search(_text())


def test_13_no_pii_pattern_leak() -> None:
    assert not PII_RE.search(_text())


def test_14_dirty_baseline_documented() -> None:
    text = _text()
    assert "Dirty Baseline" in text
    assert "known hold" in text


def test_15_existing_api_browser_e2e_test_exists() -> None:
    assert (ROOT / "tests" / "test_hwpx_form_auto_fill_real_like_api_browser_e2e.py").is_file()


def test_16_existing_api_browser_sandbox_batch_tests_exist() -> None:
    for name in [
        "test_hwpx_form_auto_fill_real_like_api_batch.py",
        "test_hwpx_form_auto_fill_real_like_browser_batch.py",
        "test_hwpx_form_auto_fill_real_like_sandbox_batch.py",
    ]:
        assert (ROOT / "tests" / name).is_file()


def test_17_existing_writer_chain_tests_exist() -> None:
    for name in [
        "test_hwpx_form_auto_fill_real_file_preflight.py",
        "test_hwpx_form_autofill_browser_smoke.py",
        "test_hwpx_form_autofill_api_route.py",
        "test_hwpx_form_autofill_frontend_contract.py",
        "test_hwpx_form_auto_fill_e2e_smoke.py",
        "test_hwpx_form_writer_final_export_gate.py",
        "test_hwpx_form_writer_download_review.py",
        "test_hwpx_form_writer_ui_connect.py",
        "test_hwpx_form_writer_readback_hardening.py",
        "test_hwpx_form_auto_fill_writer_sandbox.py",
        "test_hwpx_approval_gate.py",
        "test_hwpx_review_panel.py",
        "test_hwpx_form_field_mapping.py",
    ]:
        assert (ROOT / "tests" / name).is_file()
