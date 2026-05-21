"""HWPX template engine CLI.

The CLI is intentionally thin. Feature logic lives in dedicated modules:

- hwpx_template_render.py: render/batch/self-test orchestration
- hwpx_table_ops.py: table operation execution
- hwpx_validation.py: rendered package validation
- hwpx_writer_adapter.py: compatibility facade over package/text/table/image ops
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from hwpx_chart_png import generate_bar_chart_png_from_json
from hwpx_compose_examples import write_example_jobs
from hwpx_compose_regression import regression_csv_rows, run_regression_suite
from hwpx_compose_schema_reference import compose_schema_reference, markdown_reference
from hwpx_composer import compose_from_job_file
from hwpx_full_scenario import run_full_scenario
from hwpx_job_schema import validate_compose_job
from hwpx_package import HwpxPackage, read_json, unique_path, write_json
from hwpx_package_audit import audit_csv_rows, audit_hwpx_package, audit_many
from hwpx_table_ops import apply_table_operations, table_values_from_ops, validate_table_config
from hwpx_template_render import (
    expected_values,
    materialize_job_files,
    normalize_table_config,
    render_one,
    write_self_test_inputs,
)
from hwpx_validation import validate_rendered
from hwpx_writer_adapter import HwpxEditor


def command_render(args: argparse.Namespace) -> int:
    try:
        mapping = read_json(Path(args.mapping_json)) if args.mapping_json else {}
        tables = normalize_table_config(Path(args.table_json) if args.table_json else None)
        validate_table_config(tables)
        report = render_one(
            Path(args.template),
            Path(args.output),
            mapping,
            tables,
            bool(args.validate),
            bool(args.roundtrip),
        )
    except Exception as exc:  # noqa: BLE001
        report = {
            "template": str(args.template),
            "output": str(args.output),
            "status": "FAIL",
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        }
    if args.report_json:
        write_json(Path(args.report_json), report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] in {"PASS", "WARN"} else 1


def command_validate(args: argparse.Namespace) -> int:
    expected = []
    if args.expected_json:
        data = read_json(Path(args.expected_json))
        expected = data.get("expected_values", data if isinstance(data, list) else [])
    report = validate_rendered(Path(args.input), [str(value) for value in expected])
    if not report.get("zip_ok") or not report.get("xml_ok"):
        report["status"] = "FAIL"
    elif report.get("missing_expected_values"):
        report["status"] = "WARN"
    else:
        report["status"] = "PASS"
    if args.report_json:
        write_json(Path(args.report_json), report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] in {"PASS", "WARN"} else 1


def _audit_expected_values(args: argparse.Namespace) -> list[str]:
    values = [str(value) for value in getattr(args, "expected", []) or []]
    expected_json = getattr(args, "expected_json", None)
    if not expected_json:
        return values
    data = read_json(Path(expected_json))
    if isinstance(data, list):
        values.extend(str(value) for value in data)
    elif isinstance(data, dict):
        expected = data.get("expected_values", data.get("expected", []))
        if isinstance(expected, list):
            values.extend(str(value) for value in expected)
    return values


def command_audit(args: argparse.Namespace) -> int:
    expected = _audit_expected_values(args)
    if getattr(args, "input_dir", None):
        paths = sorted(Path(args.input_dir).glob(args.glob))
        if args.limit:
            paths = paths[: args.limit]
        report = audit_many(paths, expected_values=expected, strict=bool(args.strict))
        if args.out_csv:
            from hwpx_package import write_csv

            write_csv(Path(args.out_csv), audit_csv_rows(report["results"]))
    else:
        report = audit_hwpx_package(Path(args.input), expected_values=expected, strict=bool(args.strict))
        if args.out_csv:
            from hwpx_package import write_csv

            write_csv(Path(args.out_csv), audit_csv_rows([report]))
    if args.report_json:
        write_json(Path(args.report_json), report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] in {"PASS", "WARN"} else 1


def command_batch_render(args: argparse.Namespace) -> int:
    try:
        job_data = read_json(Path(args.job_json))
        jobs = job_data.get("jobs", [])
    except Exception as exc:  # noqa: BLE001
        summary = {
            "status": "FAIL",
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "job_count": 0,
            "pass_count": 0,
            "warn_count": 0,
            "fail_count": 0,
            "results": [],
        }
        if args.report_json:
            write_json(Path(args.report_json), summary)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 1

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for index, job in enumerate(jobs, start=1):
        try:
            template, output, mapping, tables = materialize_job_files(job, output_dir, index)
            validate_table_config(tables)
            result = render_one(template, output, mapping, tables, True, bool(args.roundtrip))
        except Exception as exc:  # noqa: BLE001
            result = {
                "status": "FAIL",
                "job_index": index,
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            }
        result["job_index"] = index
        results.append(result)

    summary = {
        "status": "PASS" if results and all(item["status"] in {"PASS", "WARN"} for item in results) else "FAIL",
        "job_count": len(jobs),
        "pass_count": sum(1 for item in results if item["status"] == "PASS"),
        "warn_count": sum(1 for item in results if item["status"] == "WARN"),
        "fail_count": sum(1 for item in results if item["status"] == "FAIL"),
        "results": results,
    }
    if args.report_json:
        write_json(Path(args.report_json), summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["status"] == "PASS" else 1


def command_compose(args: argparse.Namespace) -> int:
    try:
        report = compose_from_job_file(
            Path(args.job_json),
            Path(args.output) if args.output else None,
            Path(args.report_json) if args.report_json else None,
        )
    except Exception as exc:  # noqa: BLE001
        report = {
            "status": "FAIL",
            "job_json": str(args.job_json),
            "output": str(args.output) if args.output else None,
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        }
        if args.report_json:
            write_json(Path(args.report_json), report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] in {"PASS", "WARN"} else 1


def command_validate_job(args: argparse.Namespace) -> int:
    try:
        job_path = Path(args.job_json)
        job = read_json(job_path)
        report = validate_compose_job(
            job,
            base_dir=job_path.parent,
            require_template_exists=bool(args.require_template_exists),
            require_external_files=bool(args.require_external_files),
        )
    except Exception as exc:  # noqa: BLE001
        report = {
            "status": "FAIL",
            "job_json": str(args.job_json),
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        }
    if args.report_json:
        write_json(Path(args.report_json), report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] in {"PASS", "WARN"} else 1


def command_examples(args: argparse.Namespace) -> int:
    try:
        report = write_example_jobs(
            Path(args.out_dir),
            str(args.template),
            include_experimental=bool(args.include_experimental),
        )
    except Exception as exc:  # noqa: BLE001
        report = {
            "status": "FAIL",
            "out_dir": str(args.out_dir),
            "template": str(args.template),
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        }
    if args.report_json:
        write_json(Path(args.report_json), report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


def command_schema_reference(args: argparse.Namespace) -> int:
    try:
        reference = compose_schema_reference()
        if args.out_json:
            write_json(Path(args.out_json), reference)
        if args.out_md:
            out_md = Path(args.out_md)
            out_md.parent.mkdir(parents=True, exist_ok=True)
            out_md.write_text(markdown_reference(reference), encoding="utf-8")
        report = {
            "status": "PASS",
            "out_json": str(args.out_json) if args.out_json else None,
            "out_md": str(args.out_md) if args.out_md else None,
            "result": reference,
        }
    except Exception as exc:  # noqa: BLE001
        report = {
            "status": "FAIL",
            "out_json": str(args.out_json) if args.out_json else None,
            "out_md": str(args.out_md) if args.out_md else None,
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


def command_regression_suite(args: argparse.Namespace) -> int:
    report = run_regression_suite(Path(args.template), Path(args.out_dir), strict=bool(args.strict))
    if args.report_json:
        write_json(Path(args.report_json), report)
    if args.report_csv:
        from hwpx_package import write_csv

        write_csv(Path(args.report_csv), regression_csv_rows(report))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] in {"PASS", "WARN"} else 1


def command_full_scenario(args: argparse.Namespace) -> int:
    report = run_full_scenario(
        Path(args.template),
        Path(args.out_dir),
        include_experimental=bool(args.include_experimental),
        strict_regression=bool(args.strict_regression),
        java_roundtrip=bool(args.java_roundtrip),
    )
    if args.report_json:
        write_json(Path(args.report_json), report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] in {"PASS", "WARN"} else 1


def command_chart_png(args: argparse.Namespace) -> int:
    try:
        report = generate_bar_chart_png_from_json(Path(args.data_json), Path(args.output))
    except Exception as exc:  # noqa: BLE001
        report = {
            "status": "FAIL",
            "data_json": str(args.data_json),
            "output": str(args.output),
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        }
    if args.report_json:
        write_json(Path(args.report_json), report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


def command_table_op(args: argparse.Namespace) -> int:
    try:
        ops_data = read_json(Path(args.ops_json))
        operations = ops_data.get("operations", [])
        if not isinstance(operations, list):
            raise ValueError("operations must be a list")
        package = HwpxPackage(Path(args.template))
        editor = HwpxEditor(package)
        op_report = apply_table_operations(editor, operations)
        output = Path(args.output)
        package.write_package(output)
        expected = table_values_from_ops(operations)
        validation = validate_rendered(output, expected) if args.validate else {"enabled": False}
        status = op_report["status"]
        if args.validate:
            if not validation.get("zip_ok") or not validation.get("xml_ok"):
                status = "FAIL"
            elif validation.get("missing_expected_values") and status == "PASS":
                status = "WARN"
        report = {
            "template": str(args.template),
            "output": str(output),
            "status": status,
            "table_operations": op_report,
            "validation": validation,
            "warnings": op_report.get("warnings", []),
        }
    except Exception as exc:  # noqa: BLE001
        report = {
            "template": str(args.template),
            "output": str(args.output),
            "status": "FAIL",
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        }
    if args.report_json:
        write_json(Path(args.report_json), report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] in {"PASS", "WARN"} else 1


def command_image_replace(args: argparse.Namespace) -> int:
    try:
        if (args.image_index is None) == (args.image_entry is None):
            raise ValueError("exactly one of --image-index or --image-entry is required")
        replacement = Path(args.replacement)
        if not replacement.exists():
            report = {
                "template": str(args.template),
                "output": str(args.output),
                "status": "FAIL",
                "error": "REPLACEMENT_NOT_FOUND",
                "replacement": str(replacement),
            }
        else:
            package = HwpxPackage(Path(args.template))
            editor = HwpxEditor(package)
            before_images = editor.list_images()
            if args.image_entry is not None:
                replace_result = editor.replace_image_by_entry(args.image_entry, replacement)
            else:
                replace_result = editor.replace_image(int(args.image_index), replacement)
            status = "PASS" if replace_result.get("status") == "IMAGE_REPLACE_PASS" else "FAIL"
            output = Path(args.output)
            validation = {"enabled": False}
            after_images = before_images
            if replace_result.get("status") == "IMAGE_REPLACE_PASS":
                package.write_package(output)
                after_package = HwpxPackage(output)
                after_images = HwpxEditor(after_package).list_images()
                validation = validate_rendered(output) if args.validate else {"enabled": False}
                if args.validate and (not validation.get("zip_ok") or not validation.get("xml_ok")):
                    status = "FAIL"
                elif not replace_result.get("hash_changed") or not replace_result.get("xml_refs_preserved"):
                    status = "WARN"
            report = {
                "template": str(args.template),
                "output": str(output),
                "status": status,
                "image_inventory_before": before_images,
                "replace_result": replace_result,
                "image_inventory_after": after_images,
                "validation": validation,
                "warnings": [],
            }
            if not before_images:
                report["warnings"].append({"type": "IMAGE_NOT_FOUND"})
            if replace_result.get("status") == "IMAGE_EXTENSION_MISMATCH":
                report["warnings"].append({"type": "IMAGE_EXTENSION_MISMATCH"})
    except Exception as exc:  # noqa: BLE001
        report = {
            "template": str(args.template),
            "output": str(args.output),
            "status": "FAIL",
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        }
    if args.report_json:
        write_json(Path(args.report_json), report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] in {"PASS", "WARN"} else 1


def command_image_seed(args: argparse.Namespace) -> int:
    try:
        package = HwpxPackage(Path(args.template))
        editor = HwpxEditor(package)
        before_images = editor.list_images()
        add_result = editor.add_bindata_image(Path(args.image), args.image_entry)
        output = Path(args.output)
        validation = {"enabled": False}
        after_images = before_images
        status = "PASS" if add_result.get("status") == "IMAGE_BINDATA_ADD_PASS" else "FAIL"
        if add_result.get("status") == "IMAGE_BINDATA_ADD_PASS":
            package.write_package(output)
            after_package = HwpxPackage(output)
            after_images = HwpxEditor(after_package).list_images()
            validation = validate_rendered(output) if args.validate else {"enabled": False}
            if args.validate and (not validation.get("zip_ok") or not validation.get("xml_ok")):
                status = "FAIL"
        report = {
            "template": str(args.template),
            "output": str(output),
            "status": status,
            "image_inventory_before": before_images,
            "add_result": add_result,
            "image_inventory_after": after_images,
            "validation": validation,
            "warnings": [
                {
                    "type": "BINDATA_ONLY_IMAGE_SEED",
                    "message": "This adds a package image entry, not a visible anchored picture object.",
                }
            ],
        }
    except Exception as exc:  # noqa: BLE001
        report = {
            "template": str(args.template),
            "output": str(args.output),
            "status": "FAIL",
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        }
    if args.report_json:
        write_json(Path(args.report_json), report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] in {"PASS", "WARN"} else 1


def command_picture_inspect(args: argparse.Namespace) -> int:
    try:
        package = HwpxPackage(Path(args.input))
        editor = HwpxEditor(package)
        report = {
            "input": str(args.input),
            "status": "PASS",
            "picture_inventory": editor.list_picture_objects(),
            "image_inventory": editor.list_images(),
        }
        if report["picture_inventory"].get("status") == "PICTURE_OBJECT_NOT_FOUND":
            report["status"] = "WARN"
            report["warning"] = "No visible picture/control object was found; BinData-only images are not displayed in body text."
    except Exception as exc:  # noqa: BLE001
        report = {
            "input": str(args.input),
            "status": "FAIL",
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        }
    if args.report_json:
        write_json(Path(args.report_json), report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] in {"PASS", "WARN"} else 1


def command_picture_rebind(args: argparse.Namespace) -> int:
    try:
        package = HwpxPackage(Path(args.template))
        editor = HwpxEditor(package)
        rebind_result = editor.rebind_picture_object(
            int(args.picture_index),
            args.image_entry,
            args.manifest_id,
        )
        output = Path(args.output)
        validation = {"enabled": False}
        status = "PASS" if rebind_result.get("status") == "PICTURE_REBIND_PASS" else "FAIL"
        if rebind_result.get("status") == "PICTURE_REBIND_PASS":
            package.write_package(output)
            validation = validate_rendered(output) if args.validate else {"enabled": False}
            if args.validate and (not validation.get("zip_ok") or not validation.get("xml_ok")):
                status = "FAIL"
        report = {
            "template": str(args.template),
            "output": str(output),
            "status": status,
            "rebind_result": rebind_result,
            "validation": validation,
        }
    except Exception as exc:  # noqa: BLE001
        report = {
            "template": str(args.template),
            "output": str(args.output),
            "status": "FAIL",
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        }
    if args.report_json:
        write_json(Path(args.report_json), report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] in {"PASS", "WARN"} else 1


def command_picture_clone_rebind(args: argparse.Namespace) -> int:
    try:
        package = HwpxPackage(Path(args.template))
        editor = HwpxEditor(package)
        clone_result = editor.clone_picture_object(
            int(args.picture_index),
            args.image_entry,
            args.manifest_id,
        )
        output = Path(args.output)
        validation = {"enabled": False}
        status = "PASS" if clone_result.get("status") == "PICTURE_CLONE_REBIND_PASS" else "FAIL"
        if clone_result.get("status") == "PICTURE_CLONE_REBIND_PASS":
            package.write_package(output)
            validation = validate_rendered(output) if args.validate else {"enabled": False}
            if args.validate and (not validation.get("zip_ok") or not validation.get("xml_ok")):
                status = "FAIL"
        report = {
            "template": str(args.template),
            "output": str(output),
            "status": status,
            "clone_result": clone_result,
            "validation": validation,
        }
    except Exception as exc:  # noqa: BLE001
        report = {
            "template": str(args.template),
            "output": str(args.output),
            "status": "FAIL",
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        }
    if args.report_json:
        write_json(Path(args.report_json), report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] in {"PASS", "WARN"} else 1


def command_visible_image_insert(args: argparse.Namespace) -> int:
    try:
        package = HwpxPackage(Path(args.template))
        editor = HwpxEditor(package)
        insert_result = editor.insert_visible_image(
            Path(args.image),
            int(args.picture_index),
            args.image_entry,
            args.manifest_id,
        )
        output = Path(args.output)
        validation = {"enabled": False}
        status = "PASS" if insert_result.get("status") == "VISIBLE_IMAGE_INSERT_PASS" else "FAIL"
        if insert_result.get("status") == "VISIBLE_IMAGE_INSERT_PASS":
            package.write_package(output)
            validation = validate_rendered(output) if args.validate else {"enabled": False}
            if args.validate and (not validation.get("zip_ok") or not validation.get("xml_ok")):
                status = "FAIL"
        elif insert_result.get("status") == "VISIBLE_PICTURE_TEMPLATE_NOT_FOUND":
            status = "WARN"
        report = {
            "template": str(args.template),
            "output": str(output),
            "status": status,
            "insert_result": insert_result,
            "validation": validation,
        }
    except Exception as exc:  # noqa: BLE001
        report = {
            "template": str(args.template),
            "output": str(args.output),
            "status": "FAIL",
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        }
    if args.report_json:
        write_json(Path(args.report_json), report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] in {"PASS", "WARN"} else 1


def command_png_insert(args: argparse.Namespace) -> int:
    try:
        package = HwpxPackage(Path(args.template))
        editor = HwpxEditor(package)
        insert_result = editor.insert_generated_png_picture(
            Path(args.image),
            args.image_entry,
            int(args.section_index),
            int(args.width),
            int(args.height),
            args.manifest_id,
        )
        output = Path(args.output)
        validation = {"enabled": False}
        status = "PASS" if insert_result.get("status") == "GENERATED_PNG_PICTURE_INSERT_PASS" else "FAIL"
        if insert_result.get("status") == "GENERATED_PNG_PICTURE_INSERT_PASS":
            package.write_package(output)
            validation = validate_rendered(output) if args.validate else {"enabled": False}
            if args.validate and (not validation.get("zip_ok") or not validation.get("xml_ok")):
                status = "FAIL"
        report = {
            "template": str(args.template),
            "output": str(output),
            "status": status,
            "insert_result": insert_result,
            "validation": validation,
        }
    except Exception as exc:  # noqa: BLE001
        report = {
            "template": str(args.template),
            "output": str(args.output),
            "status": "FAIL",
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        }
    if args.report_json:
        write_json(Path(args.report_json), report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] in {"PASS", "WARN"} else 1


def command_paragraph_add(args: argparse.Namespace) -> int:
    try:
        package = HwpxPackage(Path(args.template))
        editor = HwpxEditor(package)
        add_result = editor.append_generated_paragraph(args.text, int(args.section_index))
        output = Path(args.output)
        validation = {"enabled": False}
        status = "PASS" if add_result.get("status") == "GENERATED_PARAGRAPH_APPEND_PASS" else "FAIL"
        if add_result.get("status") == "GENERATED_PARAGRAPH_APPEND_PASS":
            package.write_package(output)
            expected = [args.text] if args.validate else []
            validation = validate_rendered(output, expected) if args.validate else {"enabled": False}
            if args.validate and (not validation.get("zip_ok") or not validation.get("xml_ok")):
                status = "FAIL"
            elif args.validate and validation.get("missing_expected_values"):
                status = "WARN"
        report = {
            "template": str(args.template),
            "output": str(output),
            "status": status,
            "add_result": add_result,
            "validation": validation,
        }
    except Exception as exc:  # noqa: BLE001
        report = {
            "template": str(args.template),
            "output": str(args.output),
            "status": "FAIL",
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        }
    if args.report_json:
        write_json(Path(args.report_json), report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] in {"PASS", "WARN"} else 1


def _rows_from_json(path: Path) -> list[list[str]]:
    data = read_json(path)
    if isinstance(data, dict):
        if "rows" in data:
            rows = data["rows"]
        elif "headers" in data:
            rows = [data.get("headers", [])] + data.get("rows", [])
        else:
            rows = data.get("tables", [{}])[0].get("rows", [])
    elif isinstance(data, list):
        rows = data
    else:
        raise ValueError("table data JSON must be a list or object")
    if not isinstance(rows, list) or not all(isinstance(row, list) for row in rows):
        raise ValueError("table rows must be a list of lists")
    return [[str(cell) for cell in row] for row in rows]


def command_table_create(args: argparse.Namespace) -> int:
    try:
        rows = _rows_from_json(Path(args.rows_json))
        package = HwpxPackage(Path(args.template))
        editor = HwpxEditor(package)
        add_result = editor.append_generated_table(rows, int(args.section_index))
        output = Path(args.output)
        validation = {"enabled": False}
        status = "PASS" if add_result.get("status") == "GENERATED_TABLE_APPEND_PASS" else "FAIL"
        if add_result.get("status") == "GENERATED_TABLE_APPEND_PASS":
            package.write_package(output)
            expected = [cell for row in rows for cell in row] if args.validate else []
            validation = validate_rendered(output, expected) if args.validate else {"enabled": False}
            if args.validate and (not validation.get("zip_ok") or not validation.get("xml_ok")):
                status = "FAIL"
            elif args.validate and validation.get("missing_expected_values"):
                status = "WARN"
        report = {
            "template": str(args.template),
            "output": str(output),
            "status": status,
            "add_result": add_result,
            "validation": validation,
        }
    except Exception as exc:  # noqa: BLE001
        report = {
            "template": str(args.template),
            "output": str(args.output),
            "status": "FAIL",
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        }
    if args.report_json:
        write_json(Path(args.report_json), report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] in {"PASS", "WARN"} else 1


def command_self_test(args: argparse.Namespace) -> int:
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    template = Path(args.template)
    input_paths = write_self_test_inputs(template, out_dir)

    render_output = unique_path(out_dir / "rendered.hwpx")
    render_report_path = unique_path(out_dir / "render_report.json")
    validate_report_path = unique_path(out_dir / "validate_report.json")
    batch_report_path = unique_path(out_dir / "batch_report.json")

    mapping = read_json(input_paths["mapping"])
    tables = normalize_table_config(input_paths["table"])
    validate_table_config(tables)
    render_report = render_one(template, render_output, mapping, tables, True, bool(args.roundtrip))
    write_json(render_report_path, render_report)

    expected_path = unique_path(out_dir / "expected_values.json")
    write_json(expected_path, {"expected_values": expected_values(mapping, tables)})
    validate_report = validate_rendered(render_output, expected_values(mapping, tables))
    validate_report["status"] = (
        "PASS"
        if validate_report.get("zip_ok")
        and validate_report.get("xml_ok")
        and not validate_report.get("placeholder_remaining")
        and not validate_report.get("missing_expected_values")
        else "FAIL"
    )
    write_json(validate_report_path, validate_report)

    batch_args = argparse.Namespace(
        job_json=str(input_paths["batch"]),
        output_dir=str(out_dir),
        roundtrip=bool(args.roundtrip),
        report_json=str(batch_report_path),
    )
    batch_exit = command_batch_render(batch_args)
    batch_report = read_json(batch_report_path)

    summary = {
        "status": "PASS",
        "template": str(template),
        "out_dir": str(out_dir),
        "inputs": {key: str(value) for key, value in input_paths.items()},
        "outputs": {
            "rendered": str(render_output),
            "render_report": str(render_report_path),
            "validate_report": str(validate_report_path),
            "batch_report": str(batch_report_path),
            "expected_values": str(expected_path),
        },
        "render": render_report,
        "validate": validate_report,
        "batch": batch_report,
        "warnings": [],
    }
    if render_report.get("status") == "FAIL":
        summary["status"] = "FAIL"
    if validate_report.get("status") != "PASS":
        summary["status"] = "FAIL"
    if batch_exit != 0:
        summary["status"] = "FAIL"
    if render_report.get("status") == "WARN" or batch_report.get("warn_count"):
        summary["status"] = "WARN" if summary["status"] != "FAIL" else "FAIL"
    if args.report_json:
        write_json(Path(args.report_json), summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["status"] in {"PASS", "WARN"} else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="HWPX template engine CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    render = sub.add_parser("render", help="Render one HWPX template")
    render.add_argument("--template", required=True)
    render.add_argument("--output", required=True)
    render.add_argument("--mapping-json")
    render.add_argument("--table-json")
    render.add_argument("--validate", action="store_true")
    render.add_argument("--roundtrip", action="store_true")
    render.add_argument("--report-json")
    render.set_defaults(func=command_render)

    validate = sub.add_parser("validate", help="Validate a rendered HWPX")
    validate.add_argument("--input", required=True)
    validate.add_argument("--expected-json")
    validate.add_argument("--report-json")
    validate.set_defaults(func=command_validate)

    audit = sub.add_parser("audit", help="Audit generated HWPX package completeness")
    audit_input = audit.add_mutually_exclusive_group(required=True)
    audit_input.add_argument("--input")
    audit_input.add_argument("--input-dir")
    audit.add_argument("--glob", default="*.hwpx")
    audit.add_argument("--limit", type=int)
    audit.add_argument("--expected", action="append", default=[])
    audit.add_argument("--expected-json")
    audit.add_argument("--strict", action="store_true")
    audit.add_argument("--report-json")
    audit.add_argument("--out-csv")
    audit.set_defaults(func=command_audit)

    batch = sub.add_parser("batch-render", help="Render a small batch of HWPX jobs")
    batch.add_argument("--job-json", required=True)
    batch.add_argument("--output-dir", required=True)
    batch.add_argument("--roundtrip", action="store_true")
    batch.add_argument("--report-json")
    batch.set_defaults(func=command_batch_render)

    compose = sub.add_parser("compose", help="Apply a document composition job JSON")
    compose.add_argument("--job-json", required=True)
    compose.add_argument("--output")
    compose.add_argument("--report-json")
    compose.set_defaults(func=command_compose)

    validate_job = sub.add_parser("validate-job", help="Validate a document composition job JSON")
    validate_job.add_argument("--job-json", required=True)
    validate_job.add_argument("--require-template-exists", action="store_true")
    validate_job.add_argument("--require-external-files", action="store_true")
    validate_job.add_argument("--report-json")
    validate_job.set_defaults(func=command_validate_job)

    examples = sub.add_parser("examples", help="Write validated compose job examples")
    examples.add_argument("--out-dir", required=True)
    examples.add_argument("--template", default="smoke-test.hwpx")
    examples.add_argument("--include-experimental", action="store_true")
    examples.add_argument("--report-json")
    examples.set_defaults(func=command_examples)

    schema_reference = sub.add_parser("schema-reference", help="Write compose job schema reference")
    schema_reference.add_argument("--out-json")
    schema_reference.add_argument("--out-md")
    schema_reference.set_defaults(func=command_schema_reference)

    regression = sub.add_parser("regression-suite", help="Run golden HWPX compose regression profiles")
    regression.add_argument("--template", required=True)
    regression.add_argument("--out-dir", required=True)
    regression.add_argument("--strict", action="store_true")
    regression.add_argument("--report-json")
    regression.add_argument("--report-csv")
    regression.set_defaults(func=command_regression_suite)

    full_scenario = sub.add_parser("full-scenario", help="Run full stable HWPX direct writer scenario")
    full_scenario.add_argument("--template", required=True)
    full_scenario.add_argument("--out-dir", required=True)
    full_scenario.add_argument("--include-experimental", action="store_true")
    full_scenario.add_argument("--strict-regression", action="store_true")
    full_scenario.add_argument("--java-roundtrip", action="store_true")
    full_scenario.add_argument("--report-json")
    full_scenario.set_defaults(func=command_full_scenario)

    chart_png = sub.add_parser("chart-png", help="Generate a dependency-free PNG bar chart")
    chart_png.add_argument("--data-json", required=True)
    chart_png.add_argument("--output", required=True)
    chart_png.add_argument("--report-json")
    chart_png.set_defaults(func=command_chart_png)

    table_op = sub.add_parser("table-op", help="Apply table operations to an existing HWPX table")
    table_op.add_argument("--template", required=True)
    table_op.add_argument("--output", required=True)
    table_op.add_argument("--ops-json", required=True)
    table_op.add_argument("--validate", action="store_true")
    table_op.add_argument("--report-json")
    table_op.set_defaults(func=command_table_op)

    image_replace = sub.add_parser("image-replace", help="Replace an existing BinData image in a HWPX template")
    image_replace.add_argument("--template", required=True)
    image_replace.add_argument("--output", required=True)
    image_replace.add_argument("--image-index", type=int)
    image_replace.add_argument("--image-entry")
    image_replace.add_argument("--replacement", required=True)
    image_replace.add_argument("--validate", action="store_true")
    image_replace.add_argument("--report-json")
    image_replace.set_defaults(func=command_image_replace)

    image_seed = sub.add_parser("image-seed", help="Add a BinData image entry to a HWPX package")
    image_seed.add_argument("--template", required=True)
    image_seed.add_argument("--output", required=True)
    image_seed.add_argument("--image", required=True)
    image_seed.add_argument("--image-entry", default="BinData/image001.png")
    image_seed.add_argument("--validate", action="store_true")
    image_seed.add_argument("--report-json")
    image_seed.set_defaults(func=command_image_seed)

    picture_inspect = sub.add_parser("picture-inspect", help="Inspect visible picture/control objects")
    picture_inspect.add_argument("--input", required=True)
    picture_inspect.add_argument("--report-json")
    picture_inspect.set_defaults(func=command_picture_inspect)

    picture_rebind = sub.add_parser("picture-rebind", help="Rebind an existing visible picture object to a BinData entry")
    picture_rebind.add_argument("--template", required=True)
    picture_rebind.add_argument("--output", required=True)
    picture_rebind.add_argument("--picture-index", type=int, required=True)
    picture_rebind.add_argument("--image-entry", required=True)
    picture_rebind.add_argument("--manifest-id")
    picture_rebind.add_argument("--validate", action="store_true")
    picture_rebind.add_argument("--report-json")
    picture_rebind.set_defaults(func=command_picture_rebind)

    picture_clone = sub.add_parser("picture-clone-rebind", help="Clone an existing visible picture object and rebind it to a BinData entry")
    picture_clone.add_argument("--template", required=True)
    picture_clone.add_argument("--output", required=True)
    picture_clone.add_argument("--picture-index", type=int, required=True)
    picture_clone.add_argument("--image-entry", required=True)
    picture_clone.add_argument("--manifest-id")
    picture_clone.add_argument("--validate", action="store_true")
    picture_clone.add_argument("--report-json")
    picture_clone.set_defaults(func=command_picture_clone_rebind)

    visible_image = sub.add_parser(
        "visible-image-insert",
        help="Add a BinData image and clone an existing visible picture object to show it",
    )
    visible_image.add_argument("--template", required=True)
    visible_image.add_argument("--output", required=True)
    visible_image.add_argument("--image", required=True)
    visible_image.add_argument("--picture-index", type=int, default=0)
    visible_image.add_argument("--image-entry", default="BinData/visible_image001.png")
    visible_image.add_argument("--manifest-id")
    visible_image.add_argument("--validate", action="store_true")
    visible_image.add_argument("--report-json")
    visible_image.set_defaults(func=command_visible_image_insert)

    png_insert = sub.add_parser(
        "png-insert",
        help="Insert a PNG as a generated HWPX picture object without requiring a picture template",
    )
    png_insert.add_argument("--template", required=True)
    png_insert.add_argument("--output", required=True)
    png_insert.add_argument("--image", required=True)
    png_insert.add_argument("--image-entry", default="BinData/generated_picture001.png")
    png_insert.add_argument("--section-index", type=int, default=0)
    png_insert.add_argument("--width", type=int, default=12000)
    png_insert.add_argument("--height", type=int, default=9000)
    png_insert.add_argument("--manifest-id")
    png_insert.add_argument("--validate", action="store_true")
    png_insert.add_argument("--report-json")
    png_insert.set_defaults(func=command_png_insert)

    paragraph_add = sub.add_parser("paragraph-add", help="Append a generated paragraph without cloning an existing paragraph")
    paragraph_add.add_argument("--template", required=True)
    paragraph_add.add_argument("--output", required=True)
    paragraph_add.add_argument("--text", required=True)
    paragraph_add.add_argument("--section-index", type=int, default=0)
    paragraph_add.add_argument("--validate", action="store_true")
    paragraph_add.add_argument("--report-json")
    paragraph_add.set_defaults(func=command_paragraph_add)

    table_create = sub.add_parser("table-create", help="Append a generated table without cloning an existing table")
    table_create.add_argument("--template", required=True)
    table_create.add_argument("--output", required=True)
    table_create.add_argument("--rows-json", required=True)
    table_create.add_argument("--section-index", type=int, default=0)
    table_create.add_argument("--validate", action="store_true")
    table_create.add_argument("--report-json")
    table_create.set_defaults(func=command_table_create)

    self_test = sub.add_parser("self-test", help="Run render/validate/batch-render hardening flow")
    self_test.add_argument("--template", required=True)
    self_test.add_argument("--out-dir", required=True)
    self_test.add_argument("--roundtrip", action="store_true")
    self_test.add_argument("--report-json")
    self_test.set_defaults(func=command_self_test)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
