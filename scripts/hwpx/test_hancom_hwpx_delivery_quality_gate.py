from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from hancom_hwpx_delivery_quality_gate import build_quality_report


def _passing_form_report() -> dict:
    return {
        "status": "PASS",
        "updated_cells": 50,
        "validation": {"xml_ok": True, "encoding_check": {"status": "PASS"}},
        "updates": [{"status": "PASS"}],
        "missing_user_input_count": 0,
        "layout_warning_count": 0,
        "font_adjustment_count": 1,
        "font_adjustments": [{"after_fit": {"status": "PASS"}}],
        "value_warning_count": 0,
    }


def _passing_visual_gate() -> dict:
    return {
        "status": "WARN",
        "machine_ok": True,
        "api_parse": {"status": "PASS", "warnings": 0, "errors": 0},
        "table_style_summary": {"status": "PASS", "missing_style_reference_count": 0, "fit_warning_count": 38},
        "visual_review": {"status": "USER_PRESENT_REQUIRED"},
    }


def _passing_output_audit() -> dict:
    return {
        "status": "PASS",
        "checked_update_count": 50,
        "failed_update_count": 0,
        "problem_counts": {},
        "validation": {"xml_ok": True},
    }


def test_quality_gate_warns_when_only_visual_review_is_missing() -> None:
    report = build_quality_report(_passing_form_report(), _passing_visual_gate(), _passing_output_audit())

    assert report["status"] == "WARN"
    assert report["machine_ready"] is True
    assert report["blocker_count"] == 0
    assert report["warnings"][0]["code"] == "VISUAL_REVIEW_REQUIRED"


def test_quality_gate_fails_on_missing_input_and_layout_warning() -> None:
    form = _passing_form_report()
    form["missing_user_input_count"] = 1
    form["layout_warning_count"] = 2

    report = build_quality_report(form, _passing_visual_gate(), _passing_output_audit())

    assert report["status"] == "FAIL"
    assert {item["code"] for item in report["blockers"]} >= {"MISSING_USER_INPUT", "CELL_LAYOUT_WARNING"}


def test_quality_gate_can_require_visual_review_acknowledgement() -> None:
    report = build_quality_report(_passing_form_report(), _passing_visual_gate(), _passing_output_audit(), strict_visual=True)

    assert report["status"] == "FAIL"
    assert report["blockers"][0]["code"] == "VISUAL_REVIEW_REQUIRED"


def test_quality_gate_fails_on_output_audit_failure() -> None:
    output_audit = _passing_output_audit()
    output_audit["status"] = "FAIL"
    output_audit["failed_update_count"] = 1
    output_audit["problem_counts"] = {"TEXT_MISMATCH": 1}

    report = build_quality_report(_passing_form_report(), _passing_visual_gate(), output_audit)

    assert report["status"] == "FAIL"
    assert {item["code"] for item in report["blockers"]} >= {"HWPX_OUTPUT_AUDIT_FAILED", "HWPX_OUTPUT_UPDATE_MISMATCH"}
