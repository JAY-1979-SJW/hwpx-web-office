"""Smoke test for the HWPX Python facade API."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from hwpx_api import (
    batch_compose_documents_from_files,
    compose_document_from_file,
    document,
    generate_examples,
    generate_schema_reference,
    validate_document,
)
from hwpx_package import read_json, write_json


def _status_ok(report: dict[str, Any]) -> bool:
    return report.get("status") in {"PASS", "WARN"}


def run_smoke(template: Path, out_dir: Path) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    schema = generate_schema_reference(out_dir / "schema_reference.json", out_dir / "schema_reference.md")
    examples = generate_examples(out_dir / "examples", template)

    styled_table_job = Path(examples.get("result", {}).get("files", {}).get("styled_table", ""))
    if not styled_table_job.exists():
        return {
            "status": "FAIL",
            "schema_reference": schema,
            "examples": examples,
            "compose": {"status": "FAIL", "error": "styled_table example job not found"},
            "validate": {"status": "FAIL", "error": "styled_table output not available"},
        }

    compose_report_path = out_dir / "styled_table_compose_report.json"
    compose = compose_document_from_file(styled_table_job, report_json=compose_report_path)
    result = compose.get("result", {})
    expected_values = [str(value) for value in result.get("expected_values", [])]
    output = result.get("output") or read_json(styled_table_job).get("output")
    validate = validate_document(output, expected_values)
    example_files = examples.get("result", {}).get("files", {})
    batch_job_files = [
        Path(path)
        for key, path in sorted(example_files.items())
        if key in {"complex_section_table_chart", "page_layout_numbering", "paragraph_list", "styled_table"}
    ]
    batch = batch_compose_documents_from_files(
        batch_job_files,
        out_dir / "batch_outputs",
        out_dir / "batch_compose_report.json",
    )
    builder_report_path = out_dir / "builder_multisection_report.json"
    builder = (
        document(template, out_dir / "builder_multisection.hwpx")
        .sections(3)
        .metadata(
            title="P43 Builder Multi Section",
            creator="office-analysis-engine",
            subject="Builder API smoke",
            keywords=["P43", "builder"],
            date="2026-05-10",
        )
        .section_page_layout(0, orientation="portrait", width=59528, height=84188)
        .section_page_layout(1, orientation="landscape", width=84188, height=59528)
        .section_page_layout(2, orientation="portrait", width=59528, height=84188)
        .section_page_numbering(
            0,
            start_page=1,
            visible_header=True,
            header_text="P43 Builder Section 0 Header",
            visible_footer=True,
            footer_text="P43 Builder Footer {page}",
        )
        .section_page_numbering(
            1,
            start_page=10,
            visible_header=True,
            header_text="P43 Builder Section 1 Header",
            visible_footer=True,
            footer_text="P43 Builder Footer {page}",
        )
        .section_page_numbering(
            2,
            start_page=20,
            visible_header=True,
            header_text="P43 Builder Section 2 Header",
            visible_footer=True,
            footer_text="P43 Builder Footer {page}",
        )
        .paragraph("P43 builder section zero body", section_index=0)
        .paragraph("P43 builder section one body", section_index=1)
        .paragraph("P43 builder section two body", section_index=2)
        .preview_text()
        .package_manifest()
    )
    builder_compose = builder.compose(report_json=builder_report_path)
    builder_validate = validate_document(
        builder_compose.get("output", ""),
        [
            "P43 Builder Section 0 Header",
            "P43 Builder Section 1 Header",
            "P43 Builder Section 2 Header",
            "P43 Builder Footer 1",
            "P43 Builder Footer 10",
            "P43 Builder Footer 20",
            "P43 builder section one body",
            "P43 builder section two body",
        ],
    )
    builder_complex_report_path = out_dir / "builder_complex_report.json"
    builder_complex = (
        document(template, out_dir / "builder_complex_section_table_chart.hwpx")
        .sections(3)
        .metadata(
            title="P44 Builder Complex Section Table Chart",
            creator="office-analysis-engine",
            subject="Builder complex API smoke",
            keywords=["P44", "builder", "table", "chart"],
            date="2026-05-10",
        )
        .section_page_layout(0, orientation="portrait", width=59528, height=84188)
        .section_page_layout(1, orientation="landscape", width=84188, height=59528)
        .section_page_layout(2, orientation="portrait", width=59528, height=84188)
        .section_page_numbering(
            0,
            start_page=1,
            visible_header=True,
            header_text="P44 Builder Section 0 Header",
            visible_footer=True,
            footer_text="P44 Builder Footer {page}",
        )
        .section_page_numbering(
            1,
            start_page=10,
            visible_header=True,
            header_text="P44 Builder Section 1 Header",
            visible_footer=True,
            footer_text="P44 Builder Footer {page}",
        )
        .section_page_numbering(
            2,
            start_page=20,
            visible_header=True,
            header_text="P44 Builder Section 2 Header",
            visible_footer=True,
            footer_text="P44 Builder Footer {page}",
        )
        .paragraph("P44 builder section zero body", section_index=0)
        .paragraph("P44 builder section one table body", section_index=1)
        .paragraph("P44 builder section two chart body", section_index=2)
        .table(
            [
                ["항목", "값"],
                ["섹션", "1"],
                ["복합표", "PASS"],
            ],
            section_index=1,
        )
        .synthetic_chart_png(
            {
                "title": "P44 Builder Chart",
                "series": [
                    {"label": "section", "value": 45},
                    {"label": "table", "value": 30},
                    {"label": "image", "value": 25},
                ],
            },
            width=17000,
            height=11000,
            section_index=2,
            image_entry="BinData/p44_builder_chart.png",
            chart_output=out_dir / "p44_builder_chart.png",
        )
        .preview_text()
        .package_manifest()
    )
    builder_complex_compose = builder_complex.compose(report_json=builder_complex_report_path)
    builder_complex_validate = validate_document(
        builder_complex_compose.get("output", ""),
        [
            "P44 Builder Complex Section Table Chart",
            "P44 Builder Section 0 Header",
            "P44 Builder Section 1 Header",
            "P44 Builder Section 2 Header",
            "P44 Builder Footer 1",
            "P44 Builder Footer 10",
            "P44 Builder Footer 20",
            "P44 builder section one table body",
            "P44 builder section two chart body",
            "복합표",
            "PASS",
        ],
    )
    visible_builder_report_path = out_dir / "builder_visible_chart_report.json"
    visible_builder = (
        document(builder_complex_compose.get("output", ""), out_dir / "builder_visible_chart.hwpx")
        .metadata(
            title="P48 Builder Visible Chart",
            creator="office-analysis-engine",
            subject="Builder visible picture clone API smoke",
            keywords=["P48", "builder", "visible-picture"],
            date="2026-05-10",
        )
        .paragraph("P48 builder visible chart body")
        .visible_chart_png(
            {
                "title": "P48 Visible Builder Chart",
                "series": [
                    {"label": "visible", "value": 60},
                    {"label": "clone", "value": 40},
                ],
            },
            picture_index=0,
            image_entry="BinData/p48_builder_visible_chart.png",
            chart_output=out_dir / "p48_builder_visible_chart.png",
            manifest_id="p48_builder_visible_chart",
        )
        .preview_text()
        .package_manifest()
    )
    visible_builder_compose = visible_builder.compose(report_json=visible_builder_report_path)
    visible_builder_validate = validate_document(
        visible_builder_compose.get("output", ""),
        [
            "P48 Builder Visible Chart",
            "P48 builder visible chart body",
        ],
    )

    status = "PASS"
    smoke_items = (
        schema,
        examples,
        compose,
        validate,
        batch,
        builder_compose,
        builder_validate,
        visible_builder_compose,
        visible_builder_validate,
    )
    if not all(_status_ok(item) for item in smoke_items):
        status = "FAIL"
    elif any(item.get("status") == "WARN" for item in smoke_items):
        status = "WARN"

    return {
        "status": status,
        "template": str(template),
        "out_dir": str(out_dir),
        "schema_reference": schema,
        "examples": examples,
        "compose": compose,
        "validate": validate,
        "batch": batch,
        "builder_compose": builder_compose,
        "builder_validate": builder_validate,
        "builder_complex_compose": builder_complex_compose,
        "builder_complex_validate": builder_complex_validate,
        "visible_builder_compose": visible_builder_compose,
        "visible_builder_validate": visible_builder_validate,
        "styled_table_job": str(styled_table_job),
        "styled_table_output": str(output),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test HWPX Python facade API")
    parser.add_argument("--template", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--report-json")
    args = parser.parse_args()

    report = run_smoke(Path(args.template), Path(args.out_dir))
    if args.report_json:
        write_json(Path(args.report_json), report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] in {"PASS", "WARN"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
