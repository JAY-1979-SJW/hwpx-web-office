#!/usr/bin/env python3
"""Gate final HWPX delivery with machine checks and explicit visual-review status."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from hwpx_encoding_audit import audit_path
from hwpx_package import HwpxValidator
from hwpx_table_style_audit import audit_table_styles


def load_api_parse(path: Path | None) -> dict[str, Any]:
    if not path:
        return {"status": "SKIPPED", "reason": "api parse JSON was not provided"}
    if not path.exists():
        return {"status": "FAIL", "reason": "api parse JSON not found", "path": str(path)}
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    response = data.get("response", {}) if isinstance(data, dict) else {}
    return {
        "status": "PASS" if data.get("parse_ok") and response.get("ok") and not response.get("errors") else "FAIL",
        "path": str(path),
        "parse_ok": data.get("parse_ok"),
        "api_ok": response.get("ok"),
        "tables": len(response.get("tables", []) or []),
        "warnings": len(response.get("warnings", []) or []),
        "errors": len(response.get("errors", []) or []),
    }


def build_gate_report(input_path: Path, api_parse_json: Path | None, ack_visual_ok: bool, reviewer: str) -> dict[str, Any]:
    validation = HwpxValidator.validate_hwpx(input_path)
    encoding = audit_path(input_path)
    table_style = audit_table_styles(input_path)
    api_parse = load_api_parse(api_parse_json)
    machine_ok = (
        validation.get("xml_ok")
        and validation.get("encoding_check", {}).get("status") == "PASS"
        and encoding.get("status") == "PASS"
        and table_style.get("missing_style_reference_count") == 0
        and api_parse.get("status") in {"PASS", "SKIPPED"}
    )
    visual_review = {
        "status": "PASS" if ack_visual_ok else "USER_PRESENT_REQUIRED",
        "reviewer": reviewer if ack_visual_ok else "",
        "note": (
            "Reviewer acknowledged opening/visual inspection in Hancom or an equivalent renderer."
            if ack_visual_ok
            else "Automated XML/API checks passed where available, but rendered layout requires Hancom/PDF review."
        ),
    }
    final_status = "PASS" if machine_ok and ack_visual_ok else ("WARN" if machine_ok else "FAIL")
    return {
        "status": final_status,
        "input": str(input_path),
        "machine_ok": bool(machine_ok),
        "validation": validation,
        "encoding": encoding,
        "api_parse": api_parse,
        "table_style_summary": {
            "status": table_style.get("status"),
            "table_count": table_style.get("table_count"),
            "cell_count": table_style.get("cell_count"),
            "missing_style_reference_count": table_style.get("missing_style_reference_count"),
            "fit_warning_count": table_style.get("fit_warning_count"),
        },
        "visual_review": visual_review,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--api-parse-json", type=Path)
    parser.add_argument("--ack-visual-ok", action="store_true")
    parser.add_argument("--reviewer", default="")
    parser.add_argument("--report-json", type=Path)
    args = parser.parse_args()

    report = build_gate_report(args.input, args.api_parse_json, args.ack_visual_ok, args.reviewer)
    if args.report_json:
        args.report_json.parent.mkdir(parents=True, exist_ok=True)
        args.report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] in {"PASS", "WARN"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
