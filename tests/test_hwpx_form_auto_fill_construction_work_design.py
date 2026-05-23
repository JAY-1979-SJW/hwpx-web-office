"""Tests for construction-work master design coverage."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs" / "reports" / "HWPX_FORM_AUTO_FILL_CONSTRUCTION_WORK_MASTER_DESIGN.md"
AUDIT = ROOT / "scripts" / "ops" / "audit_hwpx_form_auto_fill_construction_work_design.py"

ABS_PATH_RE = re.compile(r"(?<![A-Za-z])([A-Za-z]:[\\/]|/(home|tmp|var|Users)/)")
RAW_FILENAME_RE = re.compile(r"\b[^\\/:\s]+\.hwpx\b", re.IGNORECASE)
PII_RE = re.compile(
    r"(\d{6}-\d{7}|\d{3}-\d{2}-\d{5}|\d{2,3}-\d{3,4}-\d{4}|"
    r"\d{2,6}-\d{2,6}-\d{2,6}|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})"
)


def _text() -> str:
    return DESIGN.read_text(encoding="utf-8")


def test_01_design_report_exists() -> None:
    assert DESIGN.is_file()


def test_02_baseline_commit_referenced() -> None:
    assert "d95dcac" in _text()


def test_03_construction_scope_documented() -> None:
    text = _text()
    for token in [
        "Building construction start and completion forms",
        "Construction contract summary forms",
        "Building permit summary forms",
        "Supervision and inspection summary forms",
        "Attachment checklist forms",
    ]:
        assert token in text


def test_04_construction_data_zones_documented() -> None:
    text = _text()
    for token in [
        "Z01 Project Identity",
        "Z02 Parties And Roles",
        "Z03 Schedule And Phase",
        "Z04 Size Quantity Cost",
        "Z05 Attachments And Evidence",
        "Z06 Safety And Compliance Gate",
        "Z07 Batch API Browser Gate",
    ]:
        assert token in text


def test_05_pipeline_layers_documented() -> None:
    text = _text()
    for token in [
        "Input Layer",
        "Recognition Layer",
        "Review Layer",
        "Approval Layer",
        "Writer Layer",
        "Readback Layer",
        "Download And Final Export Layer",
        "Batch API Browser Layer",
    ]:
        assert token in text


def test_06_sandbox_only_and_source_safety_documented() -> None:
    text = _text()
    for token in [
        "SANDBOX_ONLY",
        "sourceMutationAllowed false",
        "output path does not equal source path",
        "source hash unchanged",
        "source mtime unchanged",
    ]:
        assert token in text


def test_07_writer_enable_rules_documented() -> None:
    text = _text()
    for token in [
        "approvalStatus is READY_FOR_WRITER",
        "writerEligible is true",
        "approvedFields is at least 1",
        "missingRequired is 0",
        "needsReviewRemaining is 0",
        "attachmentsMissing is 0",
    ]:
        assert token in text


def test_08_existing_gate_verdicts_documented() -> None:
    text = _text()
    for token in [
        "PASS_HWPX_FORM_AUTO_FILL_WRITER_USER_FLOW_CLOSEOUT",
        "PASS_HWPX_FORM_AUTO_FILL_INDIVIDUAL_VERIFICATION",
        "PASS_HWPX_FORM_AUTO_FILL_MODULE_AUDITS",
        "PASS_HWPX_FORM_AUTO_FILL_ZONE_GATES",
    ]:
        assert token in text


def test_09_prohibited_scope_documented() -> None:
    text = _text()
    for token in [
        "real user source file input",
        "source HWPX overwrite",
        "production write",
        "source overwrite endpoint",
        "final deploy endpoint",
        "AI API fallback",
        "OCR fallback",
        "required Hancom dependency",
    ]:
        assert token in text


def test_10_promotion_criteria_documented() -> None:
    text = _text()
    for token in [
        "At least 30 sanitized construction-like real-like samples",
        "readbackFail remains 0",
        "sourceMutation remains 0",
        "unexpectedMutation remains 0",
        "user file upload gate",
        "personal information detection and block gate",
        "Construction document policy mapping",
    ]:
        assert token in text


def test_11_no_raw_path_leak() -> None:
    assert not ABS_PATH_RE.search(_text())


def test_12_no_raw_filename_leak() -> None:
    assert not RAW_FILENAME_RE.search(_text())


def test_13_no_pii_pattern_leak() -> None:
    assert not PII_RE.search(_text())


def test_14_audit_script_exists() -> None:
    assert AUDIT.is_file()


def test_15_existing_zone_and_module_gate_files_exist() -> None:
    for rel in [
        "scripts/ops/audit_hwpx_form_auto_fill_modules.py",
        "scripts/ops/audit_hwpx_form_auto_fill_module_manifest.json",
        "scripts/ops/gate_hwpx_form_auto_fill_zones.py",
        "scripts/ops/gate_hwpx_form_auto_fill_zones_manifest.json",
    ]:
        assert (ROOT / rel).is_file()

