"""Failure-path smoke tests for the HWPX Python facade API."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from hwpx_api import (
    batch_compose_documents,
    compose_document,
    compose_document_from_file,
    validate_document,
)
from hwpx_package import write_json


def _case(name: str, report: dict[str, Any], expected_status: str, **extra: Any) -> dict[str, Any]:
    actual = report.get("status")
    return {
        "name": name,
        "expected_status": expected_status,
        "actual_status": actual,
        "pass": actual == expected_status,
        "report": report,
        **extra,
    }


def run_failure_smoke(template: Path, out_dir: Path) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    valid_job = {
        "template": str(template),
        "output": str(out_dir / "valid_from_failure_smoke.hwpx"),
        "paragraphs": [{"text": "P32 valid batch control"}],
        "expected_values": ["P32 valid batch control"],
        "validate": True,
    }
    missing_template_job = {
        "template": str(out_dir / "missing_template.hwpx"),
        "output": str(out_dir / "missing_template_output.hwpx"),
        "paragraphs": [{"text": "should not render"}],
    }

    invalid_job_path = out_dir / "missing_job_file.json"

    cases = [
        _case(
            "compose_missing_template",
            compose_document(missing_template_job),
            "FAIL",
        ),
        _case(
            "compose_invalid_page_layout",
            compose_document(
                {
                    "template": str(template),
                    "output": str(out_dir / "invalid_page_layout.hwpx"),
                    "page_layout": {"orientation": "diagonal", "width": -1},
                }
            ),
            "FAIL",
        ),
        _case(
            "compose_missing_image_file",
            compose_document(
                {
                    "template": str(template),
                    "output": str(out_dir / "missing_image_file.hwpx"),
                    "images": [{"mode": "png_insert", "path": str(out_dir / "not_found.png")}],
                }
            ),
            "FAIL",
        ),
        _case(
            "compose_visible_picture_template_missing",
            compose_document(
                {
                    "template": str(template),
                    "output": str(out_dir / "visible_picture_template_missing.hwpx"),
                    "images": [
                        {
                            "mode": "visible_chart_png",
                            "chart": {
                                "title": "visible template missing",
                                "series": [
                                    {"label": "A", "value": 1},
                                    {"label": "B", "value": 2},
                                ],
                            },
                            "chart_output": str(out_dir / "visible_picture_template_missing.png"),
                        }
                    ],
                    "validate": True,
                }
            ),
            "WARN",
        ),
        _case(
            "validate_missing_output",
            validate_document(out_dir / "missing_output.hwpx"),
            "FAIL",
        ),
        _case(
            "compose_missing_job_file",
            compose_document_from_file(invalid_job_path),
            "FAIL",
        ),
        _case(
            "batch_continue_on_error",
            batch_compose_documents(
                [valid_job, missing_template_job],
                out_dir / "batch_continue",
                out_dir / "batch_continue_report.json",
                continue_on_error=True,
            ),
            "FAIL",
            expected_job_count=2,
        ),
        _case(
            "batch_stop_on_error",
            batch_compose_documents(
                [missing_template_job, valid_job],
                out_dir / "batch_stop",
                out_dir / "batch_stop_report.json",
                continue_on_error=False,
            ),
            "FAIL",
            expected_job_count=1,
        ),
    ]

    for item in cases:
        expected_job_count = item.get("expected_job_count")
        if expected_job_count is not None:
            actual_job_count = item["report"].get("job_count")
            item["actual_job_count"] = actual_job_count
            item["pass"] = bool(item["pass"] and actual_job_count == expected_job_count)

    summary = {
        "status": "PASS" if all(item["pass"] for item in cases) else "FAIL",
        "template": str(template),
        "out_dir": str(out_dir),
        "case_count": len(cases),
        "pass_count": sum(1 for item in cases if item["pass"]),
        "fail_count": sum(1 for item in cases if not item["pass"]),
        "cases": cases,
    }
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test HWPX facade API failure paths")
    parser.add_argument("--template", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--report-json")
    args = parser.parse_args()

    report = run_failure_smoke(Path(args.template), Path(args.out_dir))
    if args.report_json:
        write_json(Path(args.report_json), report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
