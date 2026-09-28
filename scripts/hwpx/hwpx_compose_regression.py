"""Golden compose regression profiles for the HWPX direct writer.

The suite creates representative HWPX documents from a template, audits package
completeness, and records deterministic JSON/CSV results. It does not require
Hancom, COM, GUI automation, or external services.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from hwpx_composer import compose_hwpx
from hwpx_package import write_csv, write_json
from hwpx_package_audit import audit_hwpx_package


def _expected_from_metadata(metadata: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for field in ("title", "creator", "subject", "description", "date"):
        if metadata.get(field):
            values.append(str(metadata[field]))
    keywords = metadata.get("keywords", metadata.get("keyword"))
    if isinstance(keywords, list):
        values.extend(str(item) for item in keywords)
    elif keywords:
        values.append(str(keywords))
    return values


def _expected_from_content(job: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for paragraph in job.get("paragraphs", []):
        if isinstance(paragraph, str):
            values.append(paragraph)
        elif paragraph.get("text"):
            values.append(str(paragraph["text"]))
    for table in job.get("tables", []):
        for row in table.get("rows", []):
            values.extend(str(cell) for cell in row)
    for table in job.get("render_tables", job.get("tables_replace", [])):
        values.extend(str(value) for value in table.get("headers", []))
        for row in table.get("rows", []):
            values.extend(str(cell) for cell in row)
    return values


def _expected_from_page_numbering(job: dict[str, Any]) -> list[str]:
    values: list[str] = []
    page_numberings = []
    if isinstance(job.get("page_numbering"), dict):
        page_numberings.append(job["page_numbering"])
    page_numberings.extend(
        item for item in job.get("page_numberings", []) if isinstance(item, dict)
    )
    for spec in page_numberings:
        start_page = spec.get("start_page", 1)
        if not isinstance(start_page, int) or start_page < 1:
            start_page = 1
        if spec.get("visible_header") and isinstance(spec.get("header_text"), str):
            values.append(spec["header_text"].replace("{page}", str(start_page)))
        if spec.get("visible_footer") and isinstance(spec.get("footer_text"), str):
            values.append(spec["footer_text"].replace("{page}", str(start_page)))
    return values


def _expected_from_job(job: dict[str, Any]) -> list[str]:
    values: list[str] = [str(value) for value in job.get("expected_values", [])]
    values.extend(_expected_from_metadata(job.get("document_metadata", {})))
    values.extend(_expected_from_content(job))
    values.extend(_expected_from_page_numbering(job))
    seen = set()
    unique = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            unique.append(value)
    return unique


def golden_jobs(template: Path, out_dir: Path) -> dict[str, dict[str, Any]]:
    return {
        "metadata_text_table": {
            "template": str(template),
            "output": str(out_dir / "metadata_text_table.hwpx"),
            "document_metadata": {
                "title": "P40 Metadata Text Table",
                "creator": "office-analysis-engine",
                "subject": "HWPX compose regression",
                "keywords": ["P40", "regression", "metadata"],
                "date": "2026-05-09",
            },
            "paragraphs": [
                {"text": "P40 metadata paragraph"},
                {"text": "P40 table regression paragraph"},
            ],
            "tables": [
                {
                    "rows": [
                        ["Field", "Value"],
                        ["profile", "metadata_text_table"],
                        ["status", "PASS"],
                    ]
                }
            ],
            "preview_text": {"enabled": True, "include_metadata": True},
            "package_manifest": {"enabled": True},
            "expected_values": ["P40 Metadata Text Table", "metadata_text_table", "PASS"],
            "validate": True,
        },
        "page_header_footer": {
            "template": str(template),
            "output": str(out_dir / "page_header_footer.hwpx"),
            "document_metadata": {
                "title": "P40 Page Header Footer",
                "creator": "office-analysis-engine",
                "subject": "Page layout regression",
                "keywords": ["P40", "page"],
                "date": "2026-05-09",
            },
            "page_layout": {
                "orientation": "portrait",
                "width": 59528,
                "height": 84188,
                "margins": {
                    "left": 8500,
                    "right": 8500,
                    "top": 7000,
                    "bottom": 7000,
                    "header": 4250,
                    "footer": 4250,
                },
            },
            "page_numbering": {
                "start_page": 1,
                "visible_header": True,
                "header_text": "P40 Header",
                "header_align": "CENTER",
                "visible_footer": True,
                "footer_text": "Page {page}",
                "footer_align": "CENTER",
            },
            "paragraphs": [{"text": "P40 page layout paragraph"}],
            "preview_text": {"enabled": True, "include_metadata": True},
            "package_manifest": {"enabled": True},
            "expected_values": [
                "P40 Page Header Footer",
                "P40 Header",
                "Page 1",
                "P40 page layout paragraph",
            ],
            "validate": True,
        },
        "image_chart": {
            "template": str(template),
            "output": str(out_dir / "image_chart.hwpx"),
            "document_metadata": {
                "title": "P40 Image Chart",
                "creator": "office-analysis-engine",
                "subject": "Generated PNG picture regression",
                "keywords": ["P40", "image", "chart"],
                "date": "2026-05-09",
            },
            "paragraphs": [{"text": "P40 chart image paragraph"}],
            "images": [
                {
                    "mode": "chart_png",
                    "chart_output": str(out_dir / "p40_chart.png"),
                    "image_entry": "BinData/p40_chart.png",
                    "width": 16000,
                    "height": 10000,
                    "chart": {
                        "title": "P40 Chart",
                        "series": [
                            {"label": "text", "value": 40},
                            {"label": "table", "value": 35},
                            {"label": "image", "value": 25},
                        ],
                    },
                }
            ],
            "preview_text": {"enabled": True, "include_metadata": True},
            "package_manifest": {"enabled": True},
            "expected_values": ["P40 Image Chart", "P40 chart image paragraph"],
            "validate": True,
        },
        "visible_picture_clone": {
            "template": str(out_dir / "image_chart.hwpx"),
            "output": str(out_dir / "visible_picture_clone.hwpx"),
            "document_metadata": {
                "title": "P47 Visible Picture Clone",
                "creator": "office-analysis-engine",
                "subject": "Visible picture clone/rebind regression",
                "keywords": ["P47", "visible-picture", "clone"],
                "date": "2026-05-10",
            },
            "paragraphs": [{"text": "P47 visible picture clone paragraph"}],
            "images": [
                {
                    "mode": "visible_chart_png",
                    "picture_index": 0,
                    "chart_output": str(out_dir / "p47_visible_chart.png"),
                    "image_entry": "BinData/p47_visible_chart.png",
                    "manifest_id": "p47_visible_chart",
                    "chart": {
                        "title": "P47 Visible Chart",
                        "series": [
                            {"label": "template", "value": 50},
                            {"label": "clone", "value": 35},
                            {"label": "rebind", "value": 15},
                        ],
                    },
                }
            ],
            "preview_text": {"enabled": True, "include_metadata": True},
            "package_manifest": {"enabled": True},
            "expected_values": ["P47 Visible Picture Clone", "P47 visible picture clone paragraph"],
            "validate": True,
        },
        "multi_section": {
            "template": str(template),
            "output": str(out_dir / "multi_section.hwpx"),
            "sections": {"count": 3, "clear_body": True},
            "document_metadata": {
                "title": "P41 Multi Section",
                "creator": "office-analysis-engine",
                "subject": "Multi-section regression",
                "keywords": ["P41", "multi-section"],
                "date": "2026-05-09",
            },
            "paragraphs": [
                {"text": "P41 section zero paragraph", "section_index": 0},
                {"text": "P41 section one paragraph", "section_index": 1},
                {"text": "P41 section two paragraph", "section_index": 2},
            ],
            "tables": [
                {
                    "section_index": 1,
                    "rows": [
                        ["Section", "Value"],
                        ["one", "table"],
                    ],
                }
            ],
            "preview_text": {"enabled": True, "include_metadata": True},
            "package_manifest": {"enabled": True},
            "expected_values": [
                "P41 Multi Section",
                "P41 section one paragraph",
                "P41 section two paragraph",
                "Section",
                "table",
            ],
            "validate": True,
        },
        "section_layout_header_footer": {
            "template": str(template),
            "output": str(out_dir / "section_layout_header_footer.hwpx"),
            "sections": {"count": 3, "clear_body": True},
            "document_metadata": {
                "title": "P42 Section Layout Header Footer",
                "creator": "office-analysis-engine",
                "subject": "Section-specific page layout regression",
                "keywords": ["P42", "section-layout", "header-footer"],
                "date": "2026-05-09",
            },
            "page_layouts": [
                {
                    "section_index": 0,
                    "orientation": "portrait",
                    "width": 59528,
                    "height": 84188,
                    "margins": {
                        "left": 8000,
                        "right": 8000,
                        "top": 7000,
                        "bottom": 7000,
                        "header": 4200,
                        "footer": 4200,
                    },
                },
                {
                    "section_index": 1,
                    "orientation": "landscape",
                    "width": 84188,
                    "height": 59528,
                    "margins": {
                        "left": 6500,
                        "right": 6500,
                        "top": 6000,
                        "bottom": 6000,
                        "header": 3800,
                        "footer": 3800,
                    },
                },
                {
                    "section_index": 2,
                    "orientation": "portrait",
                    "width": 59528,
                    "height": 84188,
                    "margins": {
                        "left": 9000,
                        "right": 9000,
                        "top": 7500,
                        "bottom": 7500,
                        "header": 4500,
                        "footer": 4500,
                    },
                },
            ],
            "page_numberings": [
                {
                    "section_index": 0,
                    "start_page": 1,
                    "visible_header": True,
                    "header_text": "P42 Section 0 Header",
                    "visible_footer": True,
                    "footer_text": "P42 Footer {page}",
                },
                {
                    "section_index": 1,
                    "start_page": 10,
                    "visible_header": True,
                    "header_text": "P42 Section 1 Header",
                    "visible_footer": True,
                    "footer_text": "P42 Footer {page}",
                },
                {
                    "section_index": 2,
                    "start_page": 20,
                    "visible_header": True,
                    "header_text": "P42 Section 2 Header",
                    "visible_footer": True,
                    "footer_text": "P42 Footer {page}",
                },
            ],
            "paragraphs": [
                {"text": "P42 section zero body", "section_index": 0},
                {"text": "P42 section one body", "section_index": 1},
                {"text": "P42 section two body", "section_index": 2},
            ],
            "preview_text": {"enabled": True, "include_metadata": True},
            "package_manifest": {"enabled": True},
            "expected_values": [
                "P42 Section Layout Header Footer",
                "P42 Section 0 Header",
                "P42 Section 1 Header",
                "P42 Section 2 Header",
                "P42 Footer 1",
                "P42 Footer 10",
                "P42 Footer 20",
                "P42 section zero body",
                "P42 section one body",
                "P42 section two body",
            ],
            "validate": True,
        },
        "section_table_image_chart": {
            "template": str(template),
            "output": str(out_dir / "section_table_image_chart.hwpx"),
            "sections": {"count": 3, "clear_body": True},
            "document_metadata": {
                "title": "P44 Section Table Image Chart",
                "creator": "office-analysis-engine",
                "subject": "Section-aware table and image regression",
                "keywords": ["P44", "section", "table", "image", "chart"],
                "date": "2026-05-10",
            },
            "page_layouts": [
                {
                    "section_index": 0,
                    "orientation": "portrait",
                    "width": 59528,
                    "height": 84188,
                    "margins": {
                        "left": 8000,
                        "right": 8000,
                        "top": 7000,
                        "bottom": 7000,
                        "header": 4200,
                        "footer": 4200,
                    },
                },
                {
                    "section_index": 1,
                    "orientation": "landscape",
                    "width": 84188,
                    "height": 59528,
                    "margins": {
                        "left": 6500,
                        "right": 6500,
                        "top": 6000,
                        "bottom": 6000,
                        "header": 3800,
                        "footer": 3800,
                    },
                },
                {
                    "section_index": 2,
                    "orientation": "portrait",
                    "width": 59528,
                    "height": 84188,
                    "margins": {
                        "left": 9000,
                        "right": 9000,
                        "top": 7500,
                        "bottom": 7500,
                        "header": 4500,
                        "footer": 4500,
                    },
                },
            ],
            "page_numberings": [
                {
                    "section_index": 0,
                    "start_page": 1,
                    "visible_header": True,
                    "header_text": "P44 Section 0 Header",
                    "visible_footer": True,
                    "footer_text": "P44 Footer {page}",
                },
                {
                    "section_index": 1,
                    "start_page": 10,
                    "visible_header": True,
                    "header_text": "P44 Section 1 Header",
                    "visible_footer": True,
                    "footer_text": "P44 Footer {page}",
                },
                {
                    "section_index": 2,
                    "start_page": 20,
                    "visible_header": True,
                    "header_text": "P44 Section 2 Header",
                    "visible_footer": True,
                    "footer_text": "P44 Footer {page}",
                },
            ],
            "paragraphs": [
                {"text": "P44 section zero intro", "section_index": 0},
                {"text": "P44 section one table intro", "section_index": 1},
                {"text": "P44 section two chart intro", "section_index": 2},
            ],
            "tables": [
                {
                    "section_index": 1,
                    "rows": [
                        ["항목", "값"],
                        ["섹션", "1"],
                        ["표", "PASS"],
                    ],
                }
            ],
            "images": [
                {
                    "mode": "chart_png",
                    "section_index": 2,
                    "chart_output": str(out_dir / "p44_section_chart.png"),
                    "image_entry": "BinData/p44_section_chart.png",
                    "width": 17000,
                    "height": 11000,
                    "chart": {
                        "title": "P44 Section Chart",
                        "series": [
                            {"label": "section", "value": 45},
                            {"label": "table", "value": 30},
                            {"label": "image", "value": 25},
                        ],
                    },
                }
            ],
            "preview_text": {"enabled": True, "include_metadata": True},
            "package_manifest": {"enabled": True},
            "expected_values": [
                "P44 Section Table Image Chart",
                "P44 Section 0 Header",
                "P44 Section 1 Header",
                "P44 Section 2 Header",
                "P44 Footer 1",
                "P44 Footer 10",
                "P44 Footer 20",
                "P44 section one table intro",
                "P44 section two chart intro",
                "표",
                "PASS",
            ],
            "validate": True,
        },
    }


def _profile_checks(
    profile: str, compose_report: dict[str, Any], audit_report: dict[str, Any]
) -> list[dict[str, Any]]:
    checks = []
    if profile == "image_chart":
        image_count = audit_report.get("summary", {}).get("bindata_images", 0)
        checks.append({
            "name": "bindata_image_count",
            "status": "PASS" if image_count >= 1 else "FAIL",
            "value": image_count,
        })
    if profile == "visible_picture_clone":
        summary = audit_report.get("summary", {})
        image_count = summary.get("bindata_images", 0)
        image_refs = summary.get("image_reference_count", 0)
        validation = compose_report.get("validation", {})
        checks.extend([
            {
                "name": "bindata_image_count",
                "status": "PASS" if image_count >= 2 else "FAIL",
                "value": image_count,
            },
            {
                "name": "image_reference_count",
                "status": "PASS" if image_refs >= 2 else "FAIL",
                "value": image_refs,
            },
            {
                "name": "visible_clone_insert",
                "status": "PASS"
                if any(
                    step.get("step") == "visible_image_insert"
                    and step.get("status") == "VISIBLE_IMAGE_INSERT_PASS"
                    for step in compose_report.get("steps", [])
                )
                else "FAIL",
            },
            {
                "name": "expected_values",
                "status": "PASS" if not validation.get("missing_expected_values") else "FAIL",
                "missing_expected_values": validation.get("missing_expected_values", []),
            },
        ])
    if profile == "metadata_text_table":
        validation = compose_report.get("validation", {})
        checks.append({
            "name": "table_expected_values",
            "status": "PASS" if not validation.get("missing_expected_values") else "FAIL",
            "missing_expected_values": validation.get("missing_expected_values", []),
        })
    if profile == "multi_section":
        section_count = audit_report.get("summary", {}).get("section_entries", 0)
        checks.append({
            "name": "section_count",
            "status": "PASS" if section_count >= 3 else "FAIL",
            "value": section_count,
        })
    if profile == "section_layout_header_footer":
        section_count = audit_report.get("summary", {}).get("section_entries", 0)
        checks.append({
            "name": "section_count",
            "status": "PASS" if section_count >= 3 else "FAIL",
            "value": section_count,
        })
        layout_statuses = [item.get("status") for item in audit_report.get("page_layouts", [])[:3]]
        checks.append({
            "name": "section_page_layouts",
            "status": "PASS"
            if len(layout_statuses) >= 3 and all(status == "PASS" for status in layout_statuses)
            else "FAIL",
            "statuses": layout_statuses,
        })
        numbering_statuses = [
            item.get("status") for item in audit_report.get("page_numberings", [])[:3]
        ]
        start_nums = [
            item.get("startNum", {}) for item in audit_report.get("page_numberings", [])[:3]
        ]
        checks.append({
            "name": "section_page_numberings",
            "status": "PASS"
            if len(numbering_statuses) >= 3
            and all(
                status == "PASS" and start
                for status, start in zip(numbering_statuses, start_nums, strict=True)
            )
            else "FAIL",
            "statuses": numbering_statuses,
            "startNum": start_nums,
        })
    if profile == "section_table_image_chart":
        summary = audit_report.get("summary", {})
        section_count = summary.get("section_entries", 0)
        image_count = summary.get("bindata_images", 0)
        image_refs = summary.get("image_reference_count", 0)
        validation = compose_report.get("validation", {})
        checks.extend([
            {
                "name": "section_count",
                "status": "PASS" if section_count >= 3 else "FAIL",
                "value": section_count,
            },
            {
                "name": "bindata_image_count",
                "status": "PASS" if image_count >= 1 else "FAIL",
                "value": image_count,
            },
            {
                "name": "image_reference_count",
                "status": "PASS" if image_refs >= 1 else "FAIL",
                "value": image_refs,
            },
            {
                "name": "expected_values",
                "status": "PASS" if not validation.get("missing_expected_values") else "FAIL",
                "missing_expected_values": validation.get("missing_expected_values", []),
            },
        ])
    return checks


def _has_only_allowed_warnings(profile: str, compose_report: dict[str, Any]) -> bool:
    warnings = compose_report.get("warnings", [])
    if not warnings:
        return True
    allowed = set()
    if profile in {"image_chart", "section_table_image_chart"}:
        allowed.add("EXPERIMENTAL_SYNTHETIC_PICTURE_XML")
    for warning in warnings:
        if not isinstance(warning, dict) or warning.get("type") not in allowed:
            return False
    return True


def run_regression_suite(template: Path, out_dir: Path, *, strict: bool = True) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    jobs_dir = out_dir / "jobs"
    jobs_dir.mkdir(parents=True, exist_ok=True)
    jobs = golden_jobs(template, out_dir)
    results = []
    for profile, job in jobs.items():
        job_path = jobs_dir / f"{profile}.json"
        write_json(job_path, job)
        compose_report = compose_hwpx(job)
        compose_report_path = out_dir / f"{profile}_compose_report.json"
        write_json(compose_report_path, compose_report)
        output = Path(job["output"])
        expected = _expected_from_job(job)
        audit_report = audit_hwpx_package(output, expected_values=expected, strict=strict)
        audit_report_path = out_dir / f"{profile}_audit_report.json"
        write_json(audit_report_path, audit_report)
        profile_checks = _profile_checks(profile, compose_report, audit_report)
        compose_effective_status = compose_report.get("status")
        if compose_effective_status == "WARN" and _has_only_allowed_warnings(
            profile, compose_report
        ):
            compose_effective_status = "PASS"
        status = "PASS"
        if compose_effective_status == "FAIL" or audit_report.get("status") == "FAIL":
            status = "FAIL"
        elif compose_effective_status == "WARN" or audit_report.get("status") == "WARN":
            status = "WARN"
        if any(check.get("status") == "FAIL" for check in profile_checks):
            status = "FAIL"
        results.append({
            "profile": profile,
            "status": status,
            "job": str(job_path),
            "output": str(output),
            "compose_report": str(compose_report_path),
            "audit_report": str(audit_report_path),
            "compose_status": compose_report.get("status"),
            "compose_effective_status": compose_effective_status,
            "audit_status": audit_report.get("status"),
            "expected_values": expected,
            "profile_checks": profile_checks,
        })

    summary = {
        "status": "PASS"
        if results and all(item["status"] == "PASS" for item in results)
        else "FAIL",
        "template": str(template),
        "out_dir": str(out_dir),
        "profile_count": len(results),
        "pass_count": sum(1 for item in results if item["status"] == "PASS"),
        "warn_count": sum(1 for item in results if item["status"] == "WARN"),
        "fail_count": sum(1 for item in results if item["status"] == "FAIL"),
        "results": results,
    }
    if summary["fail_count"] == 0 and summary["warn_count"] > 0:
        summary["status"] = "WARN"
    return summary


def regression_csv_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "profile": item["profile"],
            "status": item["status"],
            "compose_status": item["compose_status"],
            "compose_effective_status": item.get(
                "compose_effective_status", item["compose_status"]
            ),
            "audit_status": item["audit_status"],
            "output": item["output"],
        }
        for item in report.get("results", [])
    ]


def command_run(args: argparse.Namespace) -> int:
    report = run_regression_suite(Path(args.template), Path(args.out_dir), strict=bool(args.strict))
    if args.report_json:
        write_json(Path(args.report_json), report)
    if args.report_csv:
        write_csv(Path(args.report_csv), regression_csv_rows(report))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] in {"PASS", "WARN"} else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run HWPX direct writer compose regression profiles"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="Run golden compose regression profiles")
    run.add_argument("--template", required=True)
    run.add_argument("--out-dir", required=True)
    run.add_argument("--strict", action="store_true")
    run.add_argument("--report-json")
    run.add_argument("--report-csv")
    run.set_defaults(func=command_run)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
