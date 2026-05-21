#!/usr/bin/env python3
"""Combine HWPX input and verification reports into a delivery quality gate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_json(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    if not path.exists():
        return {"_load_error": f"file not found: {path}"}
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    return data if isinstance(data, dict) else {"_load_error": f"JSON root is not an object: {path}"}


def _count(data: dict[str, Any], key: str) -> int:
    value = data.get(key)
    if isinstance(value, int):
        return value
    if isinstance(value, list):
        return len(value)
    return 0


def _add_if(items: list[dict[str, Any]], condition: bool, code: str, message: str, evidence: Any = None) -> None:
    if condition:
        item = {"code": code, "message": message}
        if evidence is not None:
            item["evidence"] = evidence
        items.append(item)


def summarize_form_report(form_report: dict[str, Any]) -> dict[str, Any]:
    updates = form_report.get("updates", [])
    failed_updates = [item for item in updates if isinstance(item, dict) and item.get("status") != "PASS"]
    font_adjustments = form_report.get("font_adjustments", [])
    bad_font_adjustments = [
        item
        for item in font_adjustments
        if isinstance(item, dict) and item.get("after_fit", {}).get("status") != "PASS"
    ]
    validation = form_report.get("validation", {}) if isinstance(form_report.get("validation"), dict) else {}
    encoding_check = validation.get("encoding_check", {}) if isinstance(validation.get("encoding_check"), dict) else {}
    return {
        "status": form_report.get("status"),
        "updated_cells": form_report.get("updated_cells", 0),
        "failed_update_count": len(failed_updates),
        "missing_user_input_count": _count(form_report, "missing_user_input_count"),
        "layout_warning_count": _count(form_report, "layout_warning_count"),
        "layout_compaction_count": _count(form_report, "layout_compaction_count"),
        "font_adjustment_count": _count(form_report, "font_adjustment_count"),
        "bad_font_adjustment_count": len(bad_font_adjustments),
        "value_warning_count": _count(form_report, "value_warning_count"),
        "xml_ok": bool(validation.get("xml_ok")),
        "encoding_status": encoding_check.get("status"),
        "failed_updates": failed_updates[:10],
        "bad_font_adjustments": bad_font_adjustments[:10],
    }


def summarize_visual_gate(visual_gate: dict[str, Any]) -> dict[str, Any]:
    api_parse = visual_gate.get("api_parse", {}) if isinstance(visual_gate.get("api_parse"), dict) else {}
    table_style = visual_gate.get("table_style_summary", {}) if isinstance(visual_gate.get("table_style_summary"), dict) else {}
    visual_review = visual_gate.get("visual_review", {}) if isinstance(visual_gate.get("visual_review"), dict) else {}
    return {
        "status": visual_gate.get("status"),
        "machine_ok": bool(visual_gate.get("machine_ok")),
        "api_status": api_parse.get("status"),
        "api_warnings": int(api_parse.get("warnings") or 0),
        "api_errors": int(api_parse.get("errors") or 0),
        "table_style_status": table_style.get("status"),
        "missing_style_reference_count": int(table_style.get("missing_style_reference_count") or 0),
        "fit_warning_count": int(table_style.get("fit_warning_count") or 0),
        "visual_review_status": visual_review.get("status"),
        "reviewer": visual_review.get("reviewer", ""),
    }


def summarize_output_audit(output_audit: dict[str, Any]) -> dict[str, Any]:
    if not output_audit:
        return {"status": "SKIPPED"}
    validation = output_audit.get("validation", {}) if isinstance(output_audit.get("validation"), dict) else {}
    return {
        "status": output_audit.get("status"),
        "checked_update_count": int(output_audit.get("checked_update_count") or 0),
        "failed_update_count": int(output_audit.get("failed_update_count") or 0),
        "problem_counts": output_audit.get("problem_counts", {}),
        "xml_ok": bool(validation.get("xml_ok")),
    }


def build_quality_report(
    form_report: dict[str, Any],
    visual_gate: dict[str, Any],
    output_audit: dict[str, Any] | None = None,
    *,
    strict_visual: bool = False,
    allow_value_warnings: bool = False,
    allow_api_warnings: bool = False,
) -> dict[str, Any]:
    blockers: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    _add_if(blockers, bool(form_report.get("_load_error")), "FORM_REPORT_LOAD_FAIL", "Input report could not be loaded.", form_report.get("_load_error"))
    _add_if(blockers, bool(visual_gate.get("_load_error")), "VISUAL_GATE_LOAD_FAIL", "Visual gate report could not be loaded.", visual_gate.get("_load_error"))

    form = summarize_form_report(form_report)
    visual = summarize_visual_gate(visual_gate)
    output = summarize_output_audit(output_audit or {})

    _add_if(blockers, form["status"] != "PASS", "FORM_INPUT_NOT_PASS", "Form input report is not PASS.", form["status"])
    _add_if(blockers, not form["xml_ok"], "FORM_XML_INVALID", "Generated HWPX XML validation did not pass.")
    _add_if(blockers, form["encoding_status"] != "PASS", "FORM_ENCODING_INVALID", "Generated HWPX encoding audit did not pass.", form["encoding_status"])
    _add_if(blockers, form["failed_update_count"] > 0, "CELL_UPDATE_FAILED", "One or more cell updates failed.", form["failed_updates"])
    _add_if(blockers, form["missing_user_input_count"] > 0, "MISSING_USER_INPUT", "Required user input is still missing.", form["missing_user_input_count"])
    _add_if(blockers, form["layout_warning_count"] > 0, "CELL_LAYOUT_WARNING", "Inserted text still has layout warnings.", form["layout_warning_count"])
    _add_if(blockers, form["bad_font_adjustment_count"] > 0, "FONT_ADJUSTMENT_FAILED", "A font-size adjustment did not resolve fit.", form["bad_font_adjustments"])

    value_warning_target = blockers if not allow_value_warnings else warnings
    _add_if(value_warning_target, form["value_warning_count"] > 0, "VALUE_FORMAT_WARNING", "Supplied values have format warnings.", form["value_warning_count"])

    _add_if(blockers, not visual["machine_ok"], "MACHINE_GATE_FAILED", "Machine verification gate did not pass.")
    _add_if(blockers, visual["api_status"] not in {"PASS", "SKIPPED", None}, "API_PARSE_FAILED", "API parse result is not PASS.", visual["api_status"])
    _add_if(blockers, visual["api_errors"] > 0, "API_PARSE_ERRORS", "API parse returned errors.", visual["api_errors"])
    api_warning_target = blockers if not allow_api_warnings else warnings
    _add_if(api_warning_target, visual["api_warnings"] > 0, "API_PARSE_WARNINGS", "API parse returned warnings.", visual["api_warnings"])
    _add_if(blockers, visual["missing_style_reference_count"] > 0, "STYLE_REFERENCE_MISSING", "Table cells have missing style references.", visual["missing_style_reference_count"])

    _add_if(blockers, output["status"] not in {"PASS", "SKIPPED"}, "HWPX_OUTPUT_AUDIT_FAILED", "Direct HWPX output audit did not pass.", output)
    _add_if(blockers, output["status"] == "PASS" and not output["xml_ok"], "HWPX_OUTPUT_XML_INVALID", "Direct HWPX output audit XML validation did not pass.")
    _add_if(blockers, output["failed_update_count"] > 0, "HWPX_OUTPUT_UPDATE_MISMATCH", "Direct HWPX output audit found bad cells.", output.get("problem_counts"))

    visual_unreviewed = visual["visual_review_status"] != "PASS"
    _add_if(blockers if strict_visual else warnings, visual_unreviewed, "VISUAL_REVIEW_REQUIRED", "Rendered layout still needs Hancom/PDF visual review.", visual["visual_review_status"])

    status = "FAIL" if blockers else ("WARN" if warnings else "PASS")
    return {
        "status": status,
        "delivery_ready": status == "PASS",
        "machine_ready": not blockers,
        "blocker_count": len(blockers),
        "warning_count": len(warnings),
        "blockers": blockers,
        "warnings": warnings,
        "form_summary": form,
        "visual_gate_summary": visual,
        "output_audit_summary": output,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--form-report-json", required=True, type=Path)
    parser.add_argument("--visual-gate-json", required=True, type=Path)
    parser.add_argument("--output-audit-json", type=Path)
    parser.add_argument("--report-json", type=Path)
    parser.add_argument("--strict-visual", action="store_true", help="Fail when visual review is not acknowledged.")
    parser.add_argument("--allow-value-warnings", action="store_true")
    parser.add_argument("--allow-api-warnings", action="store_true")
    args = parser.parse_args()

    report = build_quality_report(
        load_json(args.form_report_json),
        load_json(args.visual_gate_json),
        load_json(args.output_audit_json) if args.output_audit_json else None,
        strict_visual=args.strict_visual,
        allow_value_warnings=args.allow_value_warnings,
        allow_api_warnings=args.allow_api_warnings,
    )
    if args.report_json:
        args.report_json.parent.mkdir(parents=True, exist_ok=True)
        args.report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] in {"PASS", "WARN"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
