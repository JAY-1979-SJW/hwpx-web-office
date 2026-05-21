"""End-to-end HWPX direct writer scenario runner.

This module ties together the stable public flows without adding new document
mutation logic. Feature work stays in the focused composer, builder, image,
table, and validation modules.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from hwpx_api import batch_compose_documents_from_files, generate_examples, generate_schema_reference
from hwpx_api_smoke import run_smoke
from hwpx_compose_regression import run_regression_suite
from hwpx_java_roundtrip import run_many_java_roundtrips
from hwpx_package import write_json


def _status_rank(status: str | None) -> int:
    if status == "FAIL":
        return 2
    if status == "WARN":
        return 1
    if status == "PASS":
        return 0
    return 2


def _overall_status(items: list[dict[str, Any]]) -> str:
    worst = max((_status_rank(item.get("status")) for item in items), default=2)
    if worst == 2:
        return "FAIL"
    if worst == 1:
        return "WARN"
    return "PASS"


def _phase(name: str, report: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": name,
        "status": report.get("status", "FAIL"),
        "warnings": report.get("warnings", []),
        "errors": report.get("errors", []),
        "report": report,
    }


def _example_job_paths(examples: dict[str, Any]) -> list[Path]:
    files = examples.get("result", {}).get("files", {})
    return [Path(path) for _, path in sorted(files.items())]


def _regression_parser_text_expected(profile: str | None) -> list[str]:
    """Expected values that should be visible in Java parser fullText.

    The broader regression expected_values list also contains metadata and
    package-level values. Those remain covered by package audit, while this
    list is intentionally limited to rendered body/header/footer/table text.
    """
    values_by_profile = {
        "metadata_text_table": [
            "P40 metadata paragraph",
            "P40 table regression paragraph",
            "Field",
            "Value",
            "profile",
            "metadata_text_table",
            "status",
            "PASS",
        ],
        "page_header_footer": ["P40 Header", "Page 1", "P40 page layout paragraph"],
        "image_chart": ["P40 chart image paragraph"],
        "visible_picture_clone": ["P47 visible picture clone paragraph"],
        "multi_section": [
            "P41 section zero paragraph",
            "P41 section one paragraph",
            "P41 section two paragraph",
            "Section",
            "Value",
            "one",
            "table",
        ],
        "section_layout_header_footer": [
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
        "section_table_image_chart": [
            "P44 Section 0 Header",
            "P44 Section 1 Header",
            "P44 Section 2 Header",
            "P44 Footer 1",
            "P44 Footer 10",
            "P44 Footer 20",
            "P44 section zero intro",
            "P44 section one table intro",
            "P44 section two chart intro",
            "PASS",
        ],
    }
    return values_by_profile.get(str(profile), [])


def run_full_scenario(
    template: Path,
    out_dir: Path,
    *,
    include_experimental: bool = False,
    strict_regression: bool = True,
    java_roundtrip: bool = False,
) -> dict[str, Any]:
    """Run the stable HWPX direct writer scenario and return one report."""
    out_dir.mkdir(parents=True, exist_ok=True)
    schema_json = out_dir / "schema_reference.json"
    schema_md = out_dir / "schema_reference.md"
    examples_dir = out_dir / "examples"
    examples_batch_dir = out_dir / "examples_batch_outputs"
    api_smoke_dir = out_dir / "api_smoke"
    regression_dir = out_dir / "regression"

    schema = generate_schema_reference(schema_json, schema_md)
    examples = generate_examples(examples_dir, template, include_experimental=include_experimental)
    example_jobs = _example_job_paths(examples)
    examples_batch = batch_compose_documents_from_files(
        example_jobs,
        examples_batch_dir,
        out_dir / "examples_batch_report.json",
    )
    api_smoke = run_smoke(template, api_smoke_dir)
    write_json(out_dir / "api_smoke_report.json", api_smoke)
    regression = run_regression_suite(template, regression_dir, strict=bool(strict_regression))
    write_json(out_dir / "regression_report.json", regression)

    phases = [
        _phase("schema_reference", schema),
        _phase("examples", examples),
        _phase("examples_batch", examples_batch),
        _phase("api_smoke", api_smoke),
        _phase("regression", regression),
    ]
    if java_roundtrip:
        roundtrip_items = []
        styled_table_output = api_smoke.get("styled_table_output")
        if styled_table_output:
            roundtrip_items.append(
                {
                    "name": "api_smoke_styled_table",
                    "input": styled_table_output,
                    "expected_values": ["PASS"],
                    "parser_text_expected_values": ["PASS"],
                }
            )
        visible_output = api_smoke.get("visible_builder_compose", {}).get("output") or api_smoke.get(
            "visible_builder_compose", {}
        ).get("output")
        if not visible_output:
            visible_output = api_smoke.get("visible_builder_validate", {}).get("output")
        if visible_output:
            roundtrip_items.append(
                {
                    "name": "api_smoke_visible_builder",
                    "input": visible_output,
                    "expected_values": ["P48 Builder Visible Chart", "P48 builder visible chart body"],
                    "parser_text_expected_values": ["P48 builder visible chart body"],
                    "metadata_expected_values": ["P48 Builder Visible Chart"],
                }
            )
        for item in regression.get("results", []):
            profile = item.get("profile")
            expected_values = item.get("expected_values", [])
            parser_text_expected = _regression_parser_text_expected(str(profile))
            metadata_expected = [
                value for value in expected_values if value not in set(parser_text_expected)
            ]
            roundtrip_items.append(
                {
                    "name": f"regression_{profile}",
                    "input": item.get("output"),
                    "expected_values": expected_values,
                    "parser_text_expected_values": parser_text_expected,
                    "metadata_expected_values": metadata_expected,
                }
            )
        java_report = run_many_java_roundtrips(roundtrip_items, out_dir / "java_roundtrip")
        write_json(out_dir / "java_roundtrip_report.json", java_report)
        phases.append(_phase("java_roundtrip", java_report))
    status = _overall_status(phases)
    artifacts = {
        "schema_json": str(schema_json),
        "schema_md": str(schema_md),
        "examples_index": str(examples_dir / "index.json"),
        "examples_batch_report": str(out_dir / "examples_batch_report.json"),
        "api_smoke_report": str(out_dir / "api_smoke_report.json"),
        "regression_report": str(out_dir / "regression_report.json"),
        "java_roundtrip_report": str(out_dir / "java_roundtrip_report.json") if java_roundtrip else None,
    }
    return {
        "status": status,
        "template": str(template),
        "out_dir": str(out_dir),
        "include_experimental": bool(include_experimental),
        "strict_regression": bool(strict_regression),
        "java_roundtrip": bool(java_roundtrip),
        "summary": {
            "phase_count": len(phases),
            "pass_count": sum(1 for item in phases if item.get("status") == "PASS"),
            "warn_count": sum(1 for item in phases if item.get("status") == "WARN"),
            "fail_count": sum(1 for item in phases if item.get("status") == "FAIL"),
            "example_job_count": len(example_jobs),
            "regression_profile_count": regression.get("profile_count", 0),
        },
        "phases": phases,
        "artifacts": artifacts,
        "next_actions": [
            "keep Java parser roundtrip as a stable callable gate for generated HWPX outputs",
            "replace synthetic regression bootstrap once a committed visible-picture fixture is available",
            "continue expanding direct writer features behind focused modules",
        ],
    }


__all__ = ["run_full_scenario"]
