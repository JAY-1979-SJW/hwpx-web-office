"""Stable Python facade for HWPX direct writer operations.

This module is intentionally thin. It gives callers a small, stable function
surface while keeping actual HWPX mutation logic in the focused lower-level
modules.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

from hwpx_compose_examples import write_example_jobs
from hwpx_compose_schema_reference import compose_schema_reference, markdown_reference
from hwpx_composer import compose_from_job_file, compose_hwpx
from hwpx_document_builder import DocumentBuilder, document
from hwpx_delivery_auto_verify import verify_hwpx_delivery
from hwpx_package import read_json, write_json
from hwpx_server_ops import (
    convert_hwp_for_server,
    fill_cells_for_server,
    insert_schedule_for_server,
    insert_schedule_graph_for_server,
    insert_table_for_server,
    repair_for_server,
)
from hwpx_template_render import normalize_table_config, render_one
from hwpx_validation import validate_rendered


def _path(value: str | Path) -> Path:
    return value if isinstance(value, Path) else Path(value)


def _failure(operation: str, exc: Exception, **context: Any) -> dict[str, Any]:
    return {
        "status": "FAIL",
        "operation": operation,
        "warnings": [],
        "errors": [
            {
                "type": type(exc).__name__,
                "message": str(exc),
            }
        ],
        **context,
    }


def _wrap(operation: str, result: dict[str, Any], **context: Any) -> dict[str, Any]:
    status = result.get("status", "FAIL")
    return {
        "status": status,
        "operation": operation,
        "warnings": result.get("warnings", []),
        "errors": result.get("errors", []),
        "result": result,
        **context,
    }


def render_document(
    template: str | Path,
    output: str | Path,
    mapping: dict[str, Any] | None = None,
    tables: list[dict[str, Any]] | None = None,
    validate: bool = True,
    roundtrip: bool = False,
) -> dict[str, Any]:
    """Render placeholders/table data into a HWPX template."""
    operation = "render_document"
    try:
        normalized_tables = normalize_table_config(None, tables)
        result = render_one(
            _path(template),
            _path(output),
            mapping or {},
            normalized_tables,
            bool(validate),
            bool(roundtrip),
        )
        return _wrap(operation, result, output=str(output))
    except Exception as exc:  # noqa: BLE001
        return _failure(operation, exc, output=str(output))


def compose_document(job: dict[str, Any], output: str | Path | None = None, report_json: str | Path | None = None) -> dict[str, Any]:
    """Apply a declarative compose job dictionary."""
    operation = "compose_document"
    try:
        result = compose_hwpx(job, _path(output) if output else None)
        if report_json:
            write_json(_path(report_json), result)
        return _wrap(operation, result, output=str(output or job.get("output", "composed.hwpx")))
    except Exception as exc:  # noqa: BLE001
        return _failure(operation, exc, output=str(output or job.get("output", "composed.hwpx")))


def compose_document_from_file(
    job_json: str | Path,
    output: str | Path | None = None,
    report_json: str | Path | None = None,
) -> dict[str, Any]:
    """Apply a declarative compose job JSON file."""
    operation = "compose_document_from_file"
    try:
        result = compose_from_job_file(
            _path(job_json),
            _path(output) if output else None,
            _path(report_json) if report_json else None,
        )
        return _wrap(operation, result, output=str(output or result.get("output", "")))
    except Exception as exc:  # noqa: BLE001
        return _failure(operation, exc, job_json=str(job_json), output=str(output or ""))


def _batch_status(results: list[dict[str, Any]]) -> str:
    if not results or any(item.get("status") == "FAIL" for item in results):
        return "FAIL"
    if any(item.get("status") == "WARN" for item in results):
        return "WARN"
    return "PASS"


def _batch_summary(operation: str, results: list[dict[str, Any]], **context: Any) -> dict[str, Any]:
    return {
        "status": _batch_status(results),
        "operation": operation,
        "job_count": len(results),
        "pass_count": sum(1 for item in results if item.get("status") == "PASS"),
        "warn_count": sum(1 for item in results if item.get("status") == "WARN"),
        "fail_count": sum(1 for item in results if item.get("status") == "FAIL"),
        "results": results,
        **context,
    }


def _batch_output(output_dir: Path | None, output: str | Path | None, fallback: str) -> Path | None:
    if not output_dir:
        return None
    if output:
        return output_dir / Path(output).name
    return output_dir / fallback


def batch_compose_documents(
    jobs: list[dict[str, Any]],
    output_dir: str | Path | None = None,
    report_json: str | Path | None = None,
    continue_on_error: bool = True,
) -> dict[str, Any]:
    """Apply multiple compose job dictionaries and return a standard summary."""
    operation = "batch_compose_documents"
    output_root = _path(output_dir) if output_dir else None
    if output_root:
        output_root.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    for index, job in enumerate(jobs, start=1):
        output = _batch_output(output_root, job.get("output"), f"batch_{index:03d}.hwpx")
        result = compose_document(job, output)
        result["job_index"] = index
        results.append(result)
        if result.get("status") == "FAIL" and not continue_on_error:
            break
    summary = _batch_summary(
        operation,
        results,
        output_dir=str(output_root or ""),
        continue_on_error=bool(continue_on_error),
    )
    if report_json:
        write_json(_path(report_json), summary)
    return summary


def batch_compose_documents_from_files(
    job_jsons: list[str | Path],
    output_dir: str | Path | None = None,
    report_json: str | Path | None = None,
    continue_on_error: bool = True,
) -> dict[str, Any]:
    """Apply multiple compose job JSON files and return a standard summary."""
    operation = "batch_compose_documents_from_files"
    output_root = _path(output_dir) if output_dir else None
    if output_root:
        output_root.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    for index, job_json in enumerate(job_jsons, start=1):
        job_path = _path(job_json)
        output: Path | None = None
        try:
            job = read_json(job_path)
            output = _batch_output(output_root, job.get("output"), f"batch_{index:03d}.hwpx")
        except Exception:
            if output_root:
                output = output_root / f"batch_{index:03d}.hwpx"
        result = compose_document_from_file(job_path, output)
        result["job_index"] = index
        result["job_json"] = str(job_path)
        results.append(result)
        if result.get("status") == "FAIL" and not continue_on_error:
            break
    summary = _batch_summary(
        operation,
        results,
        output_dir=str(output_root or ""),
        continue_on_error=bool(continue_on_error),
    )
    if report_json:
        write_json(_path(report_json), summary)
    return summary


def validate_document(path: str | Path, expected_values: list[str] | None = None) -> dict[str, Any]:
    """Validate a rendered HWPX package and expected text values."""
    operation = "validate_document"
    try:
        result = validate_rendered(_path(path), expected_values or [])
        if not result.get("zip_ok") or not result.get("xml_ok"):
            result["status"] = "FAIL"
        elif result.get("missing_expected_values"):
            result["status"] = "WARN"
        else:
            result["status"] = "PASS"
        return _wrap(operation, result, output=str(path))
    except Exception as exc:  # noqa: BLE001
        return _failure(operation, exc, output=str(path))


def repair_document_for_server(input_path: str | Path, output_path: str | Path | None = None, strict: bool = True) -> dict[str, Any]:
    """Repair HWPX package sidecars/spine for server delivery."""
    operation = "repair_document_for_server"
    try:
        result = repair_for_server(_path(input_path), _path(output_path) if output_path else None, strict=bool(strict))
        return _wrap(operation, result, output=str(output_path or result.get("output", "")))
    except Exception as exc:  # noqa: BLE001
        return _failure(operation, exc, output=str(output_path or ""))


def convert_hwp_document_for_server(
    input_path: str | Path,
    output_path: str | Path,
    decoded_style_bridge: bool = False,
    strict_quality: bool = False,
    fidelity_policy: str = "audit",
) -> dict[str, Any]:
    """Convert HWP to server-deliverable HWPX with package repair and audit."""
    operation = "convert_hwp_document_for_server"
    try:
        result = convert_hwp_for_server(
            _path(input_path),
            _path(output_path),
            decoded_style_bridge=bool(decoded_style_bridge),
            strict_quality=bool(strict_quality),
            fidelity_policy=str(fidelity_policy),
        )
        return _wrap(operation, result, output=str(output_path))
    except Exception as exc:  # noqa: BLE001
        return _failure(operation, exc, output=str(output_path))


def verify_delivery_for_server(
    hwpx_path: str | Path,
    source_hwp: str | Path | None = None,
    strict: bool = True,
    hancom: str = "auto",
    report_json: str | Path | None = None,
) -> dict[str, Any]:
    """Run automatic HWPX delivery gates, optionally including Hancom COM render."""
    operation = "verify_delivery_for_server"
    try:
        result = verify_hwpx_delivery(
            _path(hwpx_path),
            source_hwp=_path(source_hwp) if source_hwp else None,
            strict=bool(strict),
            hancom=str(hancom),
        )
        if report_json:
            write_json(_path(report_json), result)
        return _wrap(operation, result, output=str(hwpx_path))
    except Exception as exc:  # noqa: BLE001
        return _failure(operation, exc, output=str(hwpx_path))


def insert_table_for_server_document(
    input_path: str | Path,
    output_path: str | Path,
    rows: list[list[Any]],
    section_index: int = 0,
    style_refs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Insert a table into a HWPX file and repair the package for server delivery."""
    operation = "insert_table_for_server_document"
    try:
        result = insert_table_for_server(_path(input_path), _path(output_path), rows, section_index=section_index, style_refs=style_refs)
        return _wrap(operation, result, output=str(output_path))
    except Exception as exc:  # noqa: BLE001
        return _failure(operation, exc, output=str(output_path))


def fill_cells_for_server_document(
    input_path: str | Path,
    output_path: str | Path,
    table_index: int,
    cells: list[dict[str, Any]],
    color: str = "#FFE699",
) -> dict[str, Any]:
    """Apply solid fill to table cells and repair the HWPX package."""
    operation = "fill_cells_for_server_document"
    try:
        result = fill_cells_for_server(_path(input_path), _path(output_path), table_index=table_index, cells=cells, color=color)
        return _wrap(operation, result, output=str(output_path))
    except Exception as exc:  # noqa: BLE001
        return _failure(operation, exc, output=str(output_path))


def insert_schedule_for_server_document(input_path: str | Path, output_path: str | Path, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Insert a work schedule into HWPX and repair the package."""
    operation = "insert_schedule_for_server_document"
    try:
        result = insert_schedule_for_server(_path(input_path), _path(output_path), payload or {})
        return _wrap(operation, result, output=str(output_path))
    except Exception as exc:  # noqa: BLE001
        return _failure(operation, exc, output=str(output_path))


def insert_schedule_graph_for_server_document(input_path: str | Path, output_path: str | Path, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Insert a schedule graph/table suite into HWPX and repair the package."""
    operation = "insert_schedule_graph_for_server_document"
    try:
        result = insert_schedule_graph_for_server(_path(input_path), _path(output_path), payload or {})
        return _wrap(operation, result, output=str(output_path))
    except Exception as exc:  # noqa: BLE001
        return _failure(operation, exc, output=str(output_path))


def generate_examples(
    out_dir: str | Path,
    template: str | Path = "smoke-test.hwpx",
    include_experimental: bool = False,
) -> dict[str, Any]:
    """Write compose job examples to a directory."""
    operation = "generate_examples"
    try:
        result = write_example_jobs(_path(out_dir), str(template), include_experimental=include_experimental)
        return _wrap(operation, result, output=str(out_dir))
    except Exception as exc:  # noqa: BLE001
        return _failure(operation, exc, output=str(out_dir))


def generate_schema_reference(out_json: str | Path | None = None, out_md: str | Path | None = None) -> dict[str, Any]:
    """Generate the compose job schema reference."""
    operation = "generate_schema_reference"
    try:
        result = compose_schema_reference()
        if out_json:
            write_json(_path(out_json), result)
        if out_md:
            out_md_path = _path(out_md)
            out_md_path.parent.mkdir(parents=True, exist_ok=True)
            out_md_path.write_text(markdown_reference(result), encoding="utf-8")
        return _wrap(operation, result, output=str(out_json or out_md or ""))
    except Exception as exc:  # noqa: BLE001
        return _failure(operation, exc, output=str(out_json or out_md or ""))


def run_scenario(
    template: str | Path,
    out_dir: str | Path,
    include_experimental: bool = False,
    strict_regression: bool = True,
    java_roundtrip: bool = False,
) -> dict[str, Any]:
    """Run the full HWPX direct writer scenario."""
    operation = "run_scenario"
    try:
        run_full_scenario = importlib.import_module("hwpx_full_scenario").run_full_scenario
        result = run_full_scenario(
            _path(template),
            _path(out_dir),
            include_experimental=bool(include_experimental),
            strict_regression=bool(strict_regression),
            java_roundtrip=bool(java_roundtrip),
        )
        return _wrap(operation, result, output=str(out_dir))
    except Exception as exc:  # noqa: BLE001
        return _failure(operation, exc, output=str(out_dir))


__all__ = [
    "batch_compose_documents",
    "batch_compose_documents_from_files",
    "compose_document",
    "compose_document_from_file",
    "convert_hwp_document_for_server",
    "document",
    "DocumentBuilder",
    "fill_cells_for_server_document",
    "generate_examples",
    "generate_schema_reference",
    "insert_schedule_for_server_document",
    "insert_schedule_graph_for_server_document",
    "insert_table_for_server_document",
    "repair_document_for_server",
    "render_document",
    "run_scenario",
    "validate_document",
    "verify_delivery_for_server",
]
