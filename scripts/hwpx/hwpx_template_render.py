"""Template rendering orchestration shared by HWPX CLIs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from hwpx_package import HwpxPackage, read_json, unique_path, write_json
from hwpx_table_ops import render_tables, validate_table_config
from hwpx_validation import validate_rendered
from hwpx_writer_adapter import HwpxEditor


def normalize_table_config(table_json: Path | None, inline_tables: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    if inline_tables is not None:
        return inline_tables
    if not table_json:
        return []
    data = read_json(table_json)
    if isinstance(data, dict):
        return data.get("tables", [])
    if isinstance(data, list):
        return data
    raise ValueError("table JSON must be an object with tables[] or a list")


def count_placeholders(package: HwpxPackage, mapping: dict[str, Any]) -> dict[str, int]:
    counts = {key: 0 for key in mapping}
    for entry in package.xml_entries():
        text = package.read_text(entry)
        for key in mapping:
            counts[key] += text.count("{{" + key + "}}")
    return counts


def build_mapping_report(mapping: dict[str, Any], before_counts: dict[str, int]) -> dict[str, Any]:
    keys = []
    replaced_keys = []
    missing_keys = []
    for key, value in mapping.items():
        count = before_counts.get(key, 0)
        if count:
            replaced_keys.append(key)
        else:
            missing_keys.append(key)
        keys.append(
            {
                "mapping_key": key,
                "placeholder": "{{" + key + "}}",
                "replacement_length": len(str(value)),
                "found_count": count,
                "replaced_count": count,
            }
        )
    return {
        "total_keys": len(mapping),
        "replaced_keys": len(replaced_keys),
        "missing_keys": missing_keys,
        "keys": keys,
    }


def build_ordering_report(mapping: dict[str, Any], replace_result: dict[str, Any], table_report: dict[str, Any]) -> dict[str, Any]:
    mapping_entries = {item.get("entry") for item in replace_result.get("replacements", []) if item.get("entry")}
    table_entries = {
        item.get("entry")
        for item in table_report.get("results", [])
        if isinstance(item, dict) and item.get("entry")
    }
    overlap = sorted(mapping_entries & table_entries)
    mapping_values = {str(value) for value in mapping.values()}
    overwritten_mapping_values = sorted(
        {
            str(value)
            for item in table_report.get("results", [])
            if isinstance(item, dict)
            for value in item.get("overwritten_text_values", [])
            if str(value) in mapping_values
        }
    )
    warnings = []
    if overwritten_mapping_values:
        warnings.append(
            {
                "type": "TABLE_UPDATE_MAY_OVERRIDE_MAPPING_IN_SAME_XML_ENTRY",
                "entries": overlap,
                "overwritten_mapping_values": overwritten_mapping_values,
            }
        )
    return {
        "mapping_applied_before_table": True,
        "table_update_may_override_mapping": bool(overwritten_mapping_values),
        "mapping_entries": sorted(mapping_entries),
        "table_entries": sorted(table_entries),
        "overlap_entries": overlap,
        "overwritten_mapping_values": overwritten_mapping_values,
        "warnings": warnings,
    }


def expected_values(mapping: dict[str, Any], tables: list[dict[str, Any]]) -> list[str]:
    values = [] if tables else [str(value) for value in mapping.values()]
    for table in tables:
        values.extend(str(value) for value in table.get("headers", []))
        for row in table.get("rows", []):
            values.extend(str(cell) for cell in row)
    seen = set()
    unique = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            unique.append(value)
    return unique


def run_roundtrip_if_requested(output: Path, expected: list[str], enabled: bool) -> dict[str, Any]:
    if not enabled:
        return {"enabled": False}
    return {
        "enabled": True,
        "status": "NOT_EXECUTED",
        "reason": "Stable Java parser CLI integration is deferred; P1/P2.5 evidence uses temporary runner.",
        "input": str(output),
        "expected_values": expected,
    }


def render_one(
    template: Path,
    output: Path,
    mapping: dict[str, Any],
    tables: list[dict[str, Any]],
    do_validate: bool,
    do_roundtrip: bool,
) -> dict[str, Any]:
    package = HwpxPackage(template)
    editor = HwpxEditor(package)
    before_counts = count_placeholders(package, mapping)
    replace_result = editor.replace_placeholders({key: str(value) for key, value in mapping.items()})
    table_report = render_tables(editor, tables)
    package.write_package(output)

    expected = expected_values(mapping, tables)
    validation = validate_rendered(output, expected) if do_validate else {"enabled": False}
    roundtrip = run_roundtrip_if_requested(output, expected, do_roundtrip)
    map_report = build_mapping_report(mapping, before_counts)
    ordering = build_ordering_report(mapping, replace_result, table_report)

    warnings = []
    if map_report["missing_keys"]:
        warnings.append({"type": "MISSING_PLACEHOLDERS", "keys": map_report["missing_keys"]})
    warnings.extend(table_report.get("warnings", []))
    warnings.extend(ordering.get("warnings", []))
    if do_validate and validation.get("missing_expected_values"):
        warnings.append({"type": "MISSING_EXPECTED_VALUES", "values": validation["missing_expected_values"]})

    status = "PASS"
    blocking_warnings = [
        warning
        for warning in warnings
        if isinstance(warning, dict)
        and warning.get("type") != "TABLE_UPDATE_MAY_OVERRIDE_MAPPING_IN_SAME_XML_ENTRY"
    ]
    if not Path(output).exists():
        status = "FAIL"
    elif do_validate and (not validation.get("zip_ok") or not validation.get("xml_ok")):
        status = "FAIL"
    elif blocking_warnings or (do_roundtrip and roundtrip.get("status") != "PASS"):
        status = "WARN"

    return {
        "template": str(template),
        "output": str(output),
        "status": status,
        "mapping": map_report,
        "replace_result": replace_result,
        "tables": table_report,
        "ordering": ordering,
        "validation": validation,
        "roundtrip": roundtrip,
        "warnings": warnings,
    }


def materialize_job_files(job: dict[str, Any], output_dir: Path, index: int) -> tuple[Path, Path, dict[str, Any], list[dict[str, Any]]]:
    template = Path(job["template"])
    output = Path(job.get("output") or output_dir / f"batch_{index:03d}.hwpx")
    mapping = job.get("mapping", {})
    tables = job.get("tables", [])
    return template, output, mapping, tables


def default_mapping(project_name: str = "테스트 소방공사") -> dict[str, str]:
    return {
        "PROJECT_NAME": project_name,
        "BID_DEADLINE": "2026-05-15",
        "AWARD_METHOD": "제한최저가",
        "CLIENT_NAME": "테스트 발주처",
    }


def default_tables(project_name: str = "테스트 소방공사") -> list[dict[str, Any]]:
    return [
        {
            "table_id": "main_summary",
            "mode": "replace_first_table_cells",
            "headers": ["항목", "값"],
            "rows": [
                ["공사명", project_name],
                ["입찰마감일", "2026-05-15"],
                ["낙찰방법", "제한최저가"],
            ],
        }
    ]


def write_self_test_inputs(template: Path, out_dir: Path) -> dict[str, Path]:
    paths = {
        "mapping": unique_path(out_dir / "mapping.json"),
        "table": unique_path(out_dir / "table_data.json"),
        "batch": unique_path(out_dir / "batch_job.json"),
    }
    mapping = default_mapping()
    tables = default_tables()
    write_json(paths["mapping"], mapping)
    write_json(paths["table"], {"tables": tables})
    batch_jobs = {
        "jobs": [
            {
                "template": str(template),
                "output": str(unique_path(out_dir / "batch_001.hwpx")),
                "mapping": default_mapping("테스트 소방공사 1"),
                "tables": default_tables("테스트 소방공사 1"),
            },
            {
                "template": str(template),
                "output": str(unique_path(out_dir / "batch_002.hwpx")),
                "mapping": default_mapping("테스트 소방공사 2"),
                "tables": default_tables("테스트 소방공사 2"),
            },
        ]
    }
    write_json(paths["batch"], batch_jobs)
    return paths


__all__ = [
    "default_mapping",
    "default_tables",
    "expected_values",
    "materialize_job_files",
    "normalize_table_config",
    "render_one",
    "validate_table_config",
    "write_self_test_inputs",
]
