"""Job-based HWPX document composer.

The composer is the next layer above the focused editing modules. It applies a
single declarative job in a stable order so callers can build documents without
manually invoking each low-level CLI.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from hwpx_border_fill_style import apply_border_fill_definitions
from hwpx_chart_png import generate_bar_chart_png
from hwpx_header_footer_ops import apply_page_numbering
from hwpx_header_style import apply_header_style_definitions
from hwpx_image_policy import image_step_name, visible_template_missing_warning
from hwpx_job_schema import validate_compose_job
from hwpx_list_style_ops import apply_list_style_definitions
from hwpx_manifest_ops import repair_package_manifest
from hwpx_metadata_ops import apply_document_metadata
from hwpx_package import HwpxPackage, read_json, write_json
from hwpx_page_layout_ops import set_page_layout
from hwpx_preview_ops import build_preview_text
from hwpx_style_resolver import (
    resolve_image_layout,
    resolve_paragraph_style,
    resolve_table_style,
)
from hwpx_table_ops import (
    apply_table_operations,
    render_tables,
    table_values_from_ops,
    validate_table_config,
)
from hwpx_validation import validate_rendered
from hwpx_write_gate import build_write_gate, resolve_audit_log_path, write_write_audit_log
from hwpx_writer_adapter import HwpxEditor


def _flatten(rows: list[list[Any]]) -> list[str]:
    return [str(cell) for row in rows for cell in row]


def _table_render_expected(tables: list[dict[str, Any]]) -> list[str]:
    values = []
    for table in tables:
        values.extend(str(value) for value in table.get("headers", []))
        for row in table.get("rows", []):
            values.extend(str(cell) for cell in row)
    return values


def _unique(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _page_numbering_expected_values(spec: dict[str, Any]) -> list[str]:
    values: list[str] = []
    start_page = spec.get("start_page", 1)
    if not isinstance(start_page, int) or start_page < 1:
        start_page = 1
    if spec.get("visible_header") and isinstance(spec.get("header_text"), str):
        values.append(spec["header_text"].replace("{page}", str(start_page)))
    if spec.get("visible_footer") and isinstance(spec.get("footer_text"), str):
        values.append(spec["footer_text"].replace("{page}", str(start_page)))
    return values


def _apply_one_image(
    editor: HwpxEditor, image: dict[str, Any], index: int, output_path: Path
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    mode = image.get("mode", "png_insert")
    image_layout, layout_warnings = resolve_image_layout(image)
    warnings: list[dict[str, Any]] = list(layout_warnings) if layout_warnings else []

    if mode in {"chart_png", "visible_chart_png"}:
        chart_data = image.get("chart")
        if "chart_json" in image:
            chart_data = read_json(Path(image["chart_json"]))
        if not isinstance(chart_data, dict):
            result = {"status": "CHART_DATA_NOT_FOUND", "mode": mode}
        else:
            chart_png = Path(
                image.get("chart_output", output_path.parent / f"chart_{index + 1:03d}.png")
            )
            chart_result = generate_bar_chart_png(chart_data, chart_png)
            if mode == "visible_chart_png":
                insert_result = editor.insert_visible_image(
                    chart_png,
                    int(image.get("picture_index", 0)),
                    image.get("image_entry", f"BinData/visible_chart_{index + 1:03d}.png"),
                    image.get("manifest_id"),
                )
            else:
                insert_result = editor.insert_generated_png_picture(
                    chart_png,
                    image.get("image_entry", f"BinData/composed_chart_{index + 1:03d}.png"),
                    image_layout["section_index"],
                    image_layout["width"],
                    image_layout["height"],
                    image.get("manifest_id"),
                )
            result = {
                "status": insert_result.get("status"),
                "chart": chart_result,
                "insert": insert_result,
            }
            warnings.extend(insert_result.get("warnings", []))
            warnings.extend(visible_template_missing_warning(insert_result))
    elif mode == "visible_png_insert":
        result = editor.insert_visible_image(
            Path(image["path"]),
            int(image.get("picture_index", 0)),
            image.get("image_entry", f"BinData/visible_image_{index + 1:03d}.png"),
            image.get("manifest_id"),
        )
        warnings.extend(result.get("warnings", []))
        warnings.extend(visible_template_missing_warning(result))
    elif mode != "png_insert":
        result = {"status": "UNSUPPORTED_IMAGE_MODE", "mode": mode}
    else:
        result = editor.insert_generated_png_picture(
            Path(image["path"]),
            image.get("image_entry", f"BinData/composed_image_{index + 1:03d}.png"),
            image_layout["section_index"],
            image_layout["width"],
            image_layout["height"],
            image.get("manifest_id"),
        )
        warnings.extend(result.get("warnings", []))

    step = {
        "step": image_step_name(mode),
        "index": index,
        "status": result.get("status"),
        "result": result,
    }
    return step, warnings


def load_compose_job(path: Path) -> dict[str, Any]:
    data = read_json(path)
    report = validate_compose_job(data, base_dir=Path(path).parent, require_template_exists=False)
    if report["status"] == "FAIL":
        raise ValueError(f"invalid compose job: {report['errors']}")
    return data


def _compose_schema_fail_result(
    job: dict[str, Any], schema_report: dict[str, Any], output: Path | None
) -> dict[str, Any]:
    output_path = Path(output or job.get("output") or "composed.hwpx")
    result = {
        "status": "FAIL",
        "schema": schema_report,
        "template": str(job.get("template")),
        "output": str(output_path),
        "steps": [],
        "validation": {"enabled": False},
        "expected_values": [],
        "warnings": schema_report.get("warnings", []),
        "failed_steps": [{"step": "schema", "status": "FAIL"}],
    }
    result["write_gate"] = build_write_gate(result, output_path)
    audit_log_path = resolve_audit_log_path(job, output_path)
    if audit_log_path:
        result["write_audit_log"] = write_write_audit_log(audit_log_path, result)
    return result


def _compute_style_reports_and_maps(
    package: HwpxPackage, job: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    style_report = apply_header_style_definitions(package, job.get("style_definitions"))
    border_fill_report = apply_border_fill_definitions(package, job.get("style_definitions"))
    list_style_report = apply_list_style_definitions(package, job.get("style_definitions"))
    style_maps = {
        "char_styles": style_report.get("char_styles", {}),
        "para_styles": style_report.get("para_styles", {}),
        "border_fills": border_fill_report.get("border_fills", {}),
        "list_styles": list_style_report.get("list_styles", {}),
    }
    return style_report, border_fill_report, list_style_report, style_maps


def _apply_sections_step(
    editor: HwpxEditor, sections_spec: Any
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    section_count = (
        int(sections_spec.get("count", 1))
        if isinstance(sections_spec, dict)
        else int(sections_spec)
    )
    clear_body = (
        bool(sections_spec.get("clear_body", True)) if isinstance(sections_spec, dict) else True
    )
    result = editor.ensure_section_count(section_count, clear_body)
    step = {"step": "sections", "status": result.get("status"), "result": result}
    warning = None
    if result.get("status") not in {"SECTION_COUNT_READY"}:
        warning = {"type": result.get("status", "SECTION_WARN"), "result": result}
    return step, warning


def _style_definition_report_steps(
    style_report: dict[str, Any],
    border_fill_report: dict[str, Any],
    list_style_report: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    steps: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    if style_report.get("status") != "SKIPPED":
        steps.append({
            "step": "style_definitions",
            "status": style_report.get("status"),
            "result": style_report,
        })
        warnings.extend(style_report.get("warnings", []))
    if border_fill_report.get("status") != "SKIPPED":
        steps.append({
            "step": "border_fill_definitions",
            "status": border_fill_report.get("status"),
            "result": border_fill_report,
        })
        warnings.extend(border_fill_report.get("warnings", []))
    if list_style_report.get("status") != "SKIPPED":
        steps.append({
            "step": "list_style_definitions",
            "status": list_style_report.get("status"),
            "result": list_style_report,
        })
        warnings.extend(list_style_report.get("warnings", []))
    return steps, warnings


def _apply_document_metadata_step(
    package: HwpxPackage, job: dict[str, Any]
) -> tuple[dict[str, Any] | None, list[str]]:
    if not job.get("document_metadata"):
        return None, []
    result = apply_document_metadata(package, job.get("document_metadata"))
    step = {"step": "document_metadata", "status": result.get("status"), "result": result}
    expected_values: list[str] = []
    metadata_values = job.get("document_metadata", {})
    for field in ("title", "language", "creator", "subject", "description", "date"):
        if metadata_values.get(field):
            expected_values.append(str(metadata_values[field]))
    keywords = metadata_values.get("keywords", metadata_values.get("keyword"))
    if isinstance(keywords, list):
        expected_values.extend(str(item) for item in keywords)
    elif keywords:
        expected_values.append(str(keywords))
    return step, expected_values


def _apply_page_layout_and_numbering_steps(
    package: HwpxPackage, job: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    steps: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    expected_values: list[str] = []

    page_layout_specs = _as_list(job.get("page_layout")) + _as_list(job.get("page_layouts"))
    for index, page_layout in enumerate(page_layout_specs):
        result = set_page_layout(package, page_layout)
        steps.append({
            "step": "page_layout",
            "index": index,
            "status": result.get("status"),
            "result": result,
        })
        warnings.extend(result.get("warnings", []))

    page_numbering_specs = _as_list(job.get("page_numbering")) + _as_list(
        job.get("page_numberings")
    )
    for index, page_numbering in enumerate(page_numbering_specs):
        result = apply_page_numbering(package, page_numbering)
        expected_values.extend(_page_numbering_expected_values(page_numbering))
        steps.append({
            "step": "page_numbering",
            "index": index,
            "status": result.get("status"),
            "result": result,
        })
        warnings.extend(result.get("warnings", []))

    return steps, warnings, expected_values


def _apply_mapping_and_table_config_steps(
    editor: HwpxEditor, job: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    steps: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    expected_values: list[str] = []

    mapping = job.get("mapping", {})
    if mapping:
        result = editor.replace_placeholders({
            str(key): str(value) for key, value in mapping.items()
        })
        expected_values.extend(str(value) for value in mapping.values())
        steps.append({
            "step": "replace_placeholders",
            "status": result.get("status"),
            "result": result,
        })

    render_table_config = job.get("render_tables", job.get("tables_replace", []))
    if render_table_config:
        validate_table_config(render_table_config)
        result = render_tables(editor, render_table_config)
        expected_values.extend(_table_render_expected(render_table_config))
        steps.append({"step": "render_tables", "status": result.get("status"), "result": result})
        warnings.extend(result.get("warnings", []))

    table_operations = job.get("table_operations", [])
    if table_operations:
        result = apply_table_operations(editor, table_operations)
        expected_values.extend(table_values_from_ops(table_operations))
        steps.append({
            "step": "table_operations",
            "status": result.get("status"),
            "result": result,
        })
        warnings.extend(result.get("warnings", []))

    return steps, warnings, expected_values


def _apply_paragraphs_and_tables_steps(
    editor: HwpxEditor, job: dict[str, Any], style_maps: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    steps: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    expected_values: list[str] = []

    for index, paragraph in enumerate(job.get("paragraphs", [])):
        text = str(paragraph.get("text", paragraph if isinstance(paragraph, str) else ""))
        section_index = int(paragraph.get("section_index", 0)) if isinstance(paragraph, dict) else 0
        style_refs, style_warnings = resolve_paragraph_style(
            paragraph.get("style") if isinstance(paragraph, dict) else None,
            style_maps,
        )
        result = editor.append_generated_paragraph(text, section_index, style_refs)
        if style_refs:
            result["style_refs"] = style_refs
        if style_warnings:
            result["style_warnings"] = style_warnings
            warnings.extend(style_warnings)
        expected_values.append(text)
        steps.append({
            "step": "paragraph_add",
            "index": index,
            "status": result.get("status"),
            "result": result,
        })

    for index, table in enumerate(job.get("tables", [])):
        rows = table.get("rows", [])
        section_index = int(table.get("section_index", 0))
        style_refs, style_warnings = resolve_table_style(table.get("style"), style_maps)
        result = editor.append_generated_table(
            [[str(cell) for cell in row] for row in rows], section_index, style_refs
        )
        if style_refs:
            result["style_refs"] = style_refs
        if style_warnings:
            result["style_warnings"] = style_warnings
            warnings.extend(style_warnings)
        expected_values.extend(_flatten(rows))
        steps.append({
            "step": "table_create",
            "index": index,
            "status": result.get("status"),
            "result": result,
        })

    return steps, warnings, expected_values


def _apply_preview_and_manifest_steps(
    package: HwpxPackage, job: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    steps: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    preview_spec = job.get("preview_text", {"enabled": True})
    preview_result = build_preview_text(package, preview_spec)
    if preview_result.get("status") != "SKIPPED":
        steps.append({
            "step": "preview_text",
            "status": preview_result.get("status"),
            "result": preview_result,
        })
        if preview_result.get("status") != "PREVIEW_TEXT_SET_PASS":
            warnings.append({
                "type": preview_result.get("status", "PREVIEW_TEXT_WARN"),
                "result": preview_result,
            })

    package_manifest_spec = job.get("package_manifest", {"enabled": True})
    manifest_result = repair_package_manifest(package, package_manifest_spec)
    if manifest_result.get("status") != "SKIPPED":
        steps.append({
            "step": "package_manifest",
            "status": manifest_result.get("status"),
            "result": manifest_result,
        })
        warnings.extend(manifest_result.get("warnings", []))

    return steps, warnings


_COMPOSE_FAIL_STATUSES = {
    "FAIL",
    "SECTION_NOT_FOUND",
    "XML_PARSE_ERROR",
    "EMPTY_TABLE_DATA",
    "UNSUPPORTED_IMAGE_MODE",
    "REPLACEMENT_NOT_FOUND",
    "SECTION_COUNT_INVALID",
    "SECTION_TEMPLATE_NOT_FOUND",
    "SECTION_ENTRY_ALREADY_EXISTS",
    "PAGE_LAYOUT_INVALID",
    "PAGE_NUMBERING_INVALID",
    "SECTION_PROPERTIES_NOT_FOUND",
    "PICTURE_OBJECT_NOT_FOUND",
    "PICTURE_PARENT_NOT_FOUND",
    "PICTURE_REFERENCE_NOT_FOUND",
    "PICTURE_CLONE_REBIND_FAIL",
    "IMAGE_BINDATA_ADD_FAIL",
    "CHART_DATA_NOT_FOUND",
}


def _determine_compose_status(
    steps: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    job: dict[str, Any],
    validation: dict[str, Any],
) -> tuple[str, list[dict[str, Any]]]:
    """steps/warnings/validation으로 최종 status를 정한다.

    PLACEHOLDER_REMAINING 경고는 호출부와 공유하는 warnings 리스트에 바로
    append한다(별도 반환 불필요, 원본과 동일하게 in-place 변경).
    """
    failed_steps = [
        step
        for step in steps
        if step.get("status") in _COMPOSE_FAIL_STATUSES
        or str(step.get("status", "")).endswith("_FAIL")
    ]
    validate_enabled = job.get("validate", True)
    status = "PASS"
    if failed_steps or (
        validate_enabled and (not validation.get("zip_ok") or not validation.get("xml_ok"))
    ):
        status = "FAIL"
    elif validate_enabled and validation.get("placeholder_remaining"):
        status = "WARN"
        warnings.append({"type": "PLACEHOLDER_REMAINING"})
    elif (validate_enabled and validation.get("missing_expected_values")) or warnings:
        status = "WARN"
    return status, failed_steps


def compose_hwpx(job: dict[str, Any], output: Path | None = None) -> dict[str, Any]:
    schema_report = validate_compose_job(
        job, require_template_exists=True, require_external_files=True
    )
    if schema_report["status"] == "FAIL":
        return _compose_schema_fail_result(job, schema_report, output)

    template = Path(job["template"])
    output_path = Path(output or job.get("output") or "composed.hwpx")
    package = HwpxPackage(template)
    editor = HwpxEditor(package)

    expected_values: list[str] = []
    steps: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = list(schema_report.get("warnings", []))

    style_report, border_fill_report, list_style_report, style_maps = (
        _compute_style_reports_and_maps(package, job)
    )

    sections_spec = job.get("sections")
    if sections_spec:
        sections_step, sections_warning = _apply_sections_step(editor, sections_spec)
        steps.append(sections_step)
        if sections_warning:
            warnings.append(sections_warning)

    style_steps, style_warnings = _style_definition_report_steps(
        style_report, border_fill_report, list_style_report
    )
    steps.extend(style_steps)
    warnings.extend(style_warnings)

    metadata_step, metadata_values = _apply_document_metadata_step(package, job)
    if metadata_step:
        steps.append(metadata_step)
    expected_values.extend(metadata_values)

    layout_steps, layout_warnings, layout_values = _apply_page_layout_and_numbering_steps(
        package, job
    )
    steps.extend(layout_steps)
    warnings.extend(layout_warnings)
    expected_values.extend(layout_values)

    mapping_steps, mapping_warnings, mapping_values = _apply_mapping_and_table_config_steps(
        editor, job
    )
    steps.extend(mapping_steps)
    warnings.extend(mapping_warnings)
    expected_values.extend(mapping_values)

    content_steps, content_warnings, content_values = _apply_paragraphs_and_tables_steps(
        editor, job, style_maps
    )
    steps.extend(content_steps)
    warnings.extend(content_warnings)
    expected_values.extend(content_values)

    for index, image in enumerate(job.get("images", [])):
        image_step, image_warnings = _apply_one_image(editor, image, index, output_path)
        steps.append(image_step)
        warnings.extend(image_warnings)

    finish_steps, finish_warnings = _apply_preview_and_manifest_steps(package, job)
    steps.extend(finish_steps)
    warnings.extend(finish_warnings)

    package.write_package(output_path)
    expected = _unique([str(value) for value in job.get("expected_values", [])] + expected_values)
    validation = (
        validate_rendered(output_path, expected)
        if job.get("validate", True)
        else {"enabled": False}
    )

    status, failed_steps = _determine_compose_status(steps, warnings, job, validation)

    result = {
        "status": status,
        "schema": schema_report,
        "template": str(template),
        "output": str(output_path),
        "steps": steps,
        "validation": validation,
        "expected_values": expected,
        "warnings": warnings,
        "failed_steps": failed_steps,
    }
    result["write_gate"] = build_write_gate(result, output_path)
    audit_log_path = resolve_audit_log_path(job, output_path)
    if audit_log_path:
        result["write_audit_log"] = write_write_audit_log(audit_log_path, result)
    return result


def compose_from_job_file(
    job_json: Path, output: Path | None = None, report_json: Path | None = None
) -> dict[str, Any]:
    job = load_compose_job(job_json)
    report = compose_hwpx(job, output)
    if report_json:
        write_json(report_json, report)
    return report


__all__ = ["compose_from_job_file", "compose_hwpx", "load_compose_job"]
