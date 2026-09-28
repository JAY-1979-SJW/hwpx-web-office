"""Schema validation for HWPX composer job JSON.

This module validates the declarative job shape before lower-level writer
modules mutate a package. It is intentionally dependency-free and returns a
machine-readable report that can be used by CLI and API layers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from hwpx_schema_rules import (
    OUTLINE_PRESETS,
    SUPPORTED_IMAGE_MODES,
    normalize_cell_address,
    normalize_image_layout,
    normalize_paragraph_style,
    normalize_table_style,
)


SUPPORTED_TABLE_OPERATION_TYPES = {
    "inspect",
    "update_cells",
    "append_row",
    "delete_row",
    "clone_table",
    "merge_cells",
    "unmerge_cell",
    "set_cell_layout",
}


def _error(path: str, code: str, message: str, value: Any = None) -> dict[str, Any]:
    result = {"path": path, "code": code, "message": message}
    if value is not None:
        result["value"] = value
    return result


def _warning(path: str, code: str, message: str, value: Any = None) -> dict[str, Any]:
    result = {"path": path, "code": code, "message": message}
    if value is not None:
        result["value"] = value
    return result


def _is_list_of_rows(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(row, list) for row in value)


def _resolve_path(value: str, base_dir: Path) -> Path:
    path = Path(value)
    if path.is_absolute() or path.exists():
        return path
    return base_dir / path


def _validate_page_layout_spec(page_layout: Any, path: str, errors: list[dict[str, Any]]) -> None:
    if not isinstance(page_layout, dict):
        errors.append(_error(path, "PAGE_LAYOUT_NOT_OBJECT", "page layout must be an object"))
        return
    section_index = page_layout.get("section_index", 0)
    if not isinstance(section_index, int) or section_index < 0:
        errors.append(_error(path + ".section_index", "SECTION_INDEX_INVALID", "section_index must be >= 0", section_index))
    orientation = page_layout.get("orientation")
    if orientation is not None and str(orientation).lower() not in {"portrait", "landscape"}:
        errors.append(_error(path + ".orientation", "PAGE_ORIENTATION_INVALID", "orientation must be portrait or landscape", orientation))
    for field in ("width", "height"):
        if field in page_layout:
            value = page_layout[field]
            if not isinstance(value, int) or value <= 0:
                errors.append(_error(f"{path}.{field}", "PAGE_DIMENSION_INVALID", f"{field} must be a positive integer", value))
    margins = page_layout.get("margins", {})
    if margins is not None and not isinstance(margins, dict):
        errors.append(_error(path + ".margins", "PAGE_MARGINS_NOT_OBJECT", "margins must be an object"))
    elif isinstance(margins, dict):
        for field in ("left", "right", "top", "bottom", "header", "footer", "gutter"):
            if field in margins:
                value = margins[field]
                if not isinstance(value, int) or value < 0:
                    errors.append(_error(f"{path}.margins.{field}", "PAGE_MARGIN_INVALID", f"{field} must be a non-negative integer", value))


def _validate_page_numbering_spec(page_numbering: Any, path: str, errors: list[dict[str, Any]]) -> None:
    if not isinstance(page_numbering, dict):
        errors.append(_error(path, "PAGE_NUMBERING_NOT_OBJECT", "page numbering must be an object"))
        return
    section_index = page_numbering.get("section_index", 0)
    if not isinstance(section_index, int) or section_index < 0:
        errors.append(_error(path + ".section_index", "SECTION_INDEX_INVALID", "section_index must be >= 0", section_index))
    start_page = page_numbering.get("start_page", 1)
    if not isinstance(start_page, int) or start_page < 1:
        errors.append(_error(path + ".start_page", "PAGE_START_INVALID", "start_page must be >= 1", start_page))
    page_starts_on = page_numbering.get("page_starts_on")
    if page_starts_on is not None and str(page_starts_on).upper() not in {"BOTH", "EVEN", "ODD"}:
        errors.append(_error(path + ".page_starts_on", "PAGE_STARTS_ON_INVALID", "page_starts_on must be BOTH, EVEN, or ODD", page_starts_on))
    page_number_mode = page_numbering.get("page_number_mode")
    if page_number_mode is not None and str(page_number_mode).upper() not in {"STATIC_TEXT", "NATIVE_DYNAMIC"}:
        errors.append(
            _error(path + ".page_number_mode", "PAGE_NUMBER_MODE_UNSUPPORTED", "page_number_mode must be STATIC_TEXT or NATIVE_DYNAMIC", page_number_mode)
        )
    for body in ("header", "footer"):
        visible_key = f"visible_{body}"
        text_key = f"{body}_text"
        align_key = f"{body}_align"
        if visible_key in page_numbering and not isinstance(page_numbering[visible_key], bool):
            errors.append(_error(f"{path}.{visible_key}", f"VISIBLE_{body.upper()}_NOT_BOOLEAN", f"{visible_key} must be boolean"))
        if text_key in page_numbering and not isinstance(page_numbering[text_key], str):
            errors.append(_error(f"{path}.{text_key}", f"{body.upper()}_TEXT_NOT_STRING", f"{text_key} must be a string"))
        align_value = page_numbering.get(align_key)
        if align_value is not None and str(align_value).upper() not in {"LEFT", "CENTER", "RIGHT"}:
            errors.append(_error(f"{path}.{align_key}", f"{body.upper()}_ALIGN_INVALID", f"{align_key} must be LEFT, CENTER, or RIGHT", align_value))
    page_number_format = page_numbering.get("page_number_format")
    if page_number_format is not None and str(page_number_format).upper() not in {"DECIMAL"}:
        errors.append(
            _error(path + ".page_number_format", "PAGE_NUMBER_FORMAT_UNSUPPORTED", "only DECIMAL page_number_format is currently supported", page_number_format)
        )


def validate_compose_job(
    job: dict[str, Any],
    *,
    base_dir: Path | None = None,
    require_template_exists: bool = True,
    require_external_files: bool = False,
) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    base_dir = base_dir or Path()

    if not isinstance(job, dict):
        return {
            "status": "FAIL",
            "errors": [_error("$", "JOB_NOT_OBJECT", "compose job must be a JSON object")],
            "warnings": [],
        }

    template = job.get("template")
    if not isinstance(template, str) or not template:
        errors.append(_error("$.template", "TEMPLATE_REQUIRED", "template must be a non-empty string"))
    elif require_template_exists:
        template_path = _resolve_path(template, base_dir)
        if not template_path.exists():
            errors.append(_error("$.template", "TEMPLATE_NOT_FOUND", "template file does not exist", template))

    output = job.get("output")
    if output is not None and not isinstance(output, str):
        errors.append(_error("$.output", "OUTPUT_NOT_STRING", "output must be a string when provided", output))

    mapping = job.get("mapping", {})
    if mapping is not None and not isinstance(mapping, dict):
        errors.append(_error("$.mapping", "MAPPING_NOT_OBJECT", "mapping must be an object"))

    document_metadata = job.get("document_metadata")
    if document_metadata is not None:
        if not isinstance(document_metadata, dict):
            errors.append(_error("$.document_metadata", "DOCUMENT_METADATA_NOT_OBJECT", "document_metadata must be an object"))
        else:
            for field in ("title", "language", "creator", "subject", "description", "created_date", "modified_date", "date"):
                if field in document_metadata and not isinstance(document_metadata[field], str):
                    errors.append(
                        _error(
                            f"$.document_metadata.{field}",
                            "DOCUMENT_METADATA_FIELD_NOT_STRING",
                            f"{field} must be a string",
                            document_metadata[field],
                        )
                    )
            keywords = document_metadata.get("keywords", document_metadata.get("keyword"))
            if keywords is not None and not isinstance(keywords, (str, list)):
                errors.append(
                    _error(
                        "$.document_metadata.keywords",
                        "DOCUMENT_METADATA_KEYWORDS_INVALID",
                        "keywords must be a string or list of strings",
                        keywords,
                    )
                )
            elif isinstance(keywords, list):
                for index, item in enumerate(keywords):
                    if not isinstance(item, str):
                        errors.append(
                            _error(
                                f"$.document_metadata.keywords[{index}]",
                                "DOCUMENT_METADATA_KEYWORD_NOT_STRING",
                                "keyword items must be strings",
                                item,
                            )
                        )

    package_manifest = job.get("package_manifest")
    if package_manifest is not None:
        if not isinstance(package_manifest, dict):
            errors.append(_error("$.package_manifest", "PACKAGE_MANIFEST_NOT_OBJECT", "package_manifest must be an object"))
        else:
            enabled = package_manifest.get("enabled")
            if enabled is not None and not isinstance(enabled, bool):
                errors.append(_error("$.package_manifest.enabled", "PACKAGE_MANIFEST_ENABLED_NOT_BOOLEAN", "enabled must be boolean", enabled))

    for audit_key in ("write_audit_log", "audit_log"):
        audit_log = job.get(audit_key)
        if audit_log is None:
            continue
        if isinstance(audit_log, (bool, str)):
            continue
        if not isinstance(audit_log, dict):
            errors.append(_error(f"$.{audit_key}", "AUDIT_LOG_INVALID", f"{audit_key} must be boolean, string, or object"))
            continue
        enabled = audit_log.get("enabled")
        if enabled is not None and not isinstance(enabled, bool):
            errors.append(_error(f"$.{audit_key}.enabled", "AUDIT_LOG_ENABLED_NOT_BOOLEAN", "enabled must be boolean", enabled))
        path = audit_log.get("path")
        if path is not None and not isinstance(path, str):
            errors.append(_error(f"$.{audit_key}.path", "AUDIT_LOG_PATH_NOT_STRING", "path must be a string", path))

    sections = job.get("sections")
    if sections is not None:
        if isinstance(sections, int):
            if sections < 1:
                errors.append(_error("$.sections", "SECTION_COUNT_INVALID", "sections must be >= 1", sections))
        elif not isinstance(sections, dict):
            errors.append(_error("$.sections", "SECTIONS_NOT_OBJECT", "sections must be an integer or object"))
        else:
            count = sections.get("count")
            if not isinstance(count, int) or count < 1:
                errors.append(_error("$.sections.count", "SECTION_COUNT_INVALID", "sections.count must be >= 1", count))
            clear_body = sections.get("clear_body")
            if clear_body is not None and not isinstance(clear_body, bool):
                errors.append(_error("$.sections.clear_body", "SECTION_CLEAR_BODY_NOT_BOOLEAN", "sections.clear_body must be boolean", clear_body))

    preview_text = job.get("preview_text")
    if preview_text is not None:
        if not isinstance(preview_text, dict):
            errors.append(_error("$.preview_text", "PREVIEW_TEXT_NOT_OBJECT", "preview_text must be an object"))
        else:
            enabled = preview_text.get("enabled")
            if enabled is not None and not isinstance(enabled, bool):
                errors.append(_error("$.preview_text.enabled", "PREVIEW_TEXT_ENABLED_NOT_BOOLEAN", "enabled must be boolean", enabled))
            include_metadata = preview_text.get("include_metadata")
            if include_metadata is not None and not isinstance(include_metadata, bool):
                errors.append(
                    _error("$.preview_text.include_metadata", "PREVIEW_INCLUDE_METADATA_NOT_BOOLEAN", "include_metadata must be boolean", include_metadata)
                )
            max_chars = preview_text.get("max_chars")
            if max_chars is not None and (not isinstance(max_chars, int) or max_chars < 1):
                errors.append(_error("$.preview_text.max_chars", "PREVIEW_MAX_CHARS_INVALID", "max_chars must be a positive integer", max_chars))

    page_layout = job.get("page_layout")
    if page_layout is not None:
        _validate_page_layout_spec(page_layout, "$.page_layout", errors)
    page_layouts = job.get("page_layouts", [])
    if page_layouts is not None:
        if not isinstance(page_layouts, list):
            errors.append(_error("$.page_layouts", "PAGE_LAYOUTS_NOT_LIST", "page_layouts must be a list"))
        else:
            for index, item in enumerate(page_layouts):
                _validate_page_layout_spec(item, f"$.page_layouts[{index}]", errors)

    page_numbering = job.get("page_numbering")
    if page_numbering is not None:
        _validate_page_numbering_spec(page_numbering, "$.page_numbering", errors)
    page_numberings = job.get("page_numberings", [])
    if page_numberings is not None:
        if not isinstance(page_numberings, list):
            errors.append(_error("$.page_numberings", "PAGE_NUMBERINGS_NOT_LIST", "page_numberings must be a list"))
        else:
            for index, item in enumerate(page_numberings):
                _validate_page_numbering_spec(item, f"$.page_numberings[{index}]", errors)

    expected_values = job.get("expected_values", [])
    if expected_values is not None and not isinstance(expected_values, list):
        errors.append(_error("$.expected_values", "EXPECTED_VALUES_NOT_LIST", "expected_values must be a list"))

    style_definitions = job.get("style_definitions", {})
    if style_definitions is not None and not isinstance(style_definitions, dict):
        errors.append(_error("$.style_definitions", "STYLE_DEFINITIONS_NOT_OBJECT", "style_definitions must be an object"))
    elif isinstance(style_definitions, dict):
        for group in ("char_styles", "para_styles", "border_fills", "list_styles"):
            value = style_definitions.get(group, {})
            if value is not None and not isinstance(value, dict):
                errors.append(_error(f"$.style_definitions.{group}", "STYLE_GROUP_NOT_OBJECT", f"{group} must be an object"))
            elif isinstance(value, dict):
                for name, spec in value.items():
                    if not isinstance(spec, dict):
                        errors.append(_error(f"$.style_definitions.{group}.{name}", "STYLE_SPEC_NOT_OBJECT", "style spec must be an object"))
                    elif group == "list_styles":
                        preset = spec.get("preset")
                        if preset is not None and str(preset) not in OUTLINE_PRESETS:
                            errors.append(
                                _error(
                                    f"$.style_definitions.list_styles.{name}.preset",
                                    "LIST_PRESET_UNSUPPORTED",
                                    "unsupported list preset",
                                    preset,
                                )
                            )
                        for field in ("start_number", "continue_from"):
                            if field in spec and (not isinstance(spec[field], int) or spec[field] < 0):
                                errors.append(
                                    _error(
                                        f"$.style_definitions.list_styles.{name}.{field}",
                                        "LIST_START_INVALID",
                                        f"{field} must be a non-negative integer",
                                        spec[field],
                                    )
                                )
                        levels = spec.get("levels")
                        if levels is not None:
                            if not isinstance(levels, list):
                                errors.append(_error(f"$.style_definitions.list_styles.{name}.levels", "LIST_LEVELS_NOT_LIST", "levels must be a list"))
                            else:
                                for level_index, level_spec in enumerate(levels):
                                    level_path = f"$.style_definitions.list_styles.{name}.levels[{level_index}]"
                                    if not isinstance(level_spec, dict):
                                        errors.append(_error(level_path, "LIST_LEVEL_NOT_OBJECT", "list level must be an object"))
                                        continue
                                    level = level_spec.get("level", 1)
                                    if not isinstance(level, int) or level < 1:
                                        errors.append(_error(level_path + ".level", "LIST_LEVEL_INVALID", "level must be >= 1", level))
                                    start = level_spec.get("start")
                                    if start is not None and (not isinstance(start, int) or start < 1):
                                        errors.append(_error(level_path + ".start", "LIST_START_INVALID", "start must be >= 1", start))

    paragraphs = job.get("paragraphs", [])
    if not isinstance(paragraphs, list):
        errors.append(_error("$.paragraphs", "PARAGRAPHS_NOT_LIST", "paragraphs must be a list"))
    else:
        for index, paragraph in enumerate(paragraphs):
            path = f"$.paragraphs[{index}]"
            if isinstance(paragraph, str):
                continue
            if not isinstance(paragraph, dict):
                errors.append(_error(path, "PARAGRAPH_NOT_OBJECT", "paragraph must be a string or object"))
                continue
            if "text" not in paragraph:
                errors.append(_error(path + ".text", "PARAGRAPH_TEXT_REQUIRED", "paragraph text is required"))
            elif not isinstance(paragraph["text"], (str, int, float, bool)):
                errors.append(_error(path + ".text", "PARAGRAPH_TEXT_INVALID", "paragraph text must be scalar"))
            _style_refs, style_warnings = normalize_paragraph_style(paragraph.get("style"))
            for warning in style_warnings:
                warnings.append(_warning(path + ".style", warning["type"], warning.get("message", "style warning"), warning))
            style = paragraph.get("style", {})
            if isinstance(style, dict):
                char_style = style.get("char_style")
                para_style = style.get("para_style")
                char_defs = style_definitions.get("char_styles", {}) if isinstance(style_definitions, dict) else {}
                para_defs = style_definitions.get("para_styles", {}) if isinstance(style_definitions, dict) else {}
                if char_style and char_style not in char_defs:
                    warnings.append(_warning(path + ".style.char_style", "CHAR_STYLE_NAME_UNRESOLVED", "char_style is not defined", char_style))
                if para_style and para_style not in para_defs:
                    warnings.append(_warning(path + ".style.para_style", "PARA_STYLE_NAME_UNRESOLVED", "para_style is not defined", para_style))
                list_style = style.get("list_style")
                list_defs = style_definitions.get("list_styles", {}) if isinstance(style_definitions, dict) else {}
                if list_style and list_style not in list_defs:
                    warnings.append(_warning(path + ".style.list_style", "LIST_STYLE_NAME_UNRESOLVED", "list_style is not defined", list_style))
                if "list_level" in style:
                    level = style["list_level"]
                    if not isinstance(level, int) or level < 1:
                        errors.append(_error(path + ".style.list_level", "LIST_LEVEL_INVALID", "list_level must be >= 1", level))

    tables = job.get("tables", [])
    if not isinstance(tables, list):
        errors.append(_error("$.tables", "TABLES_NOT_LIST", "tables must be a list"))
    else:
        for index, table in enumerate(tables):
            path = f"$.tables[{index}]"
            if not isinstance(table, dict):
                errors.append(_error(path, "TABLE_NOT_OBJECT", "table must be an object"))
                continue
            if not _is_list_of_rows(table.get("rows")):
                errors.append(_error(path + ".rows", "TABLE_ROWS_INVALID", "table rows must be a list of row lists"))
            _style_refs, style_warnings = normalize_table_style(table.get("style"))
            for warning in style_warnings:
                warnings.append(_warning(path + ".style", warning["type"], warning.get("message", "table style warning"), warning))
            style = table.get("style", {})
            if isinstance(style, dict):
                if "column_widths" in style and not isinstance(style["column_widths"], list):
                    errors.append(_error(path + ".style.column_widths", "COLUMN_WIDTHS_NOT_LIST", "column_widths must be a list"))
                if "row_heights" in style and not isinstance(style["row_heights"], list):
                    errors.append(_error(path + ".style.row_heights", "ROW_HEIGHTS_NOT_LIST", "row_heights must be a list"))
                merged_cells = style.get("merged_cells")
                if merged_cells is not None and not isinstance(merged_cells, list):
                    errors.append(_error(path + ".style.merged_cells", "MERGED_CELLS_NOT_LIST", "merged_cells must be a list"))
                elif isinstance(merged_cells, list):
                    for merge_index, merge_spec in enumerate(merged_cells):
                        merge_path = path + f".style.merged_cells[{merge_index}]"
                        if not isinstance(merge_spec, dict):
                            errors.append(_error(merge_path, "MERGED_CELL_NOT_OBJECT", "merged cell spec must be an object"))
                            continue
                        for field in ("row", "col"):
                            if not isinstance(merge_spec.get(field), int):
                                errors.append(_error(merge_path + f".{field}", "MERGED_CELL_ADDRESS_NOT_INT", f"{field} must be an integer"))
                            elif merge_spec[field] < 0:
                                errors.append(_error(merge_path + f".{field}", "MERGED_CELL_ADDRESS_NEGATIVE", f"{field} must be >= 0"))
                        for snake_field, camel_field in (("row_span", "rowSpan"), ("col_span", "colSpan")):
                            if snake_field not in merge_spec and camel_field not in merge_spec:
                                continue
                            value = merge_spec.get(snake_field, merge_spec.get(camel_field))
                            if not isinstance(value, int):
                                errors.append(_error(merge_path + f".{snake_field}", "MERGED_CELL_SPAN_NOT_INT", f"{snake_field} must be an integer"))
                            elif value < 1:
                                errors.append(_error(merge_path + f".{snake_field}", "MERGED_CELL_SPAN_INVALID", f"{snake_field} must be >= 1"))
                border_defs = style_definitions.get("border_fills", {}) if isinstance(style_definitions, dict) else {}
                for field in (
                    "border_fill_style",
                    "cell_border_fill_style",
                    "header_border_fill_style",
                    "body_border_fill_style",
                ):
                    border_fill_style = style.get(field)
                    if border_fill_style and border_fill_style not in border_defs:
                        warnings.append(
                            _warning(
                                path + f".style.{field}",
                                "BORDER_FILL_STYLE_NAME_UNRESOLVED",
                                f"{field} is not defined",
                                border_fill_style,
                            )
                        )
                cell_style_map = style.get("cell_border_fill_map")
                if cell_style_map is not None and not isinstance(cell_style_map, dict):
                    errors.append(_error(path + ".style.cell_border_fill_map", "CELL_STYLE_MAP_NOT_OBJECT", "cell_border_fill_map must be an object"))
                elif isinstance(cell_style_map, dict):
                    for raw_address, style_name in cell_style_map.items():
                        normalized = normalize_cell_address(raw_address)
                        if normalized is None:
                            warnings.append(
                                _warning(
                                    path + ".style.cell_border_fill_map",
                                    "CELL_STYLE_ADDRESS_INVALID",
                                    "cell style address must be row,col, row:col, or r{row}c{col}",
                                    raw_address,
                                )
                            )
                        elif style_name not in border_defs:
                            warnings.append(
                                _warning(
                                    path + f".style.cell_border_fill_map.{raw_address}",
                                    "BORDER_FILL_STYLE_NAME_UNRESOLVED",
                                    "cell border fill style is not defined",
                                    style_name,
                                )
                            )
                for field in (
                    "cell_vertical_align_map",
                    "cell_text_direction_map",
                    "cell_line_wrap_map",
                    "cell_margin_map",
                ):
                    if field in style and not isinstance(style[field], dict):
                        errors.append(_error(path + f".style.{field}", "CELL_LAYOUT_MAP_NOT_OBJECT", f"{field} must be an object"))
                if "cell_margin" in style and not isinstance(style["cell_margin"], dict):
                    errors.append(_error(path + ".style.cell_margin", "CELL_MARGIN_NOT_OBJECT", "cell_margin must be an object"))
                if isinstance(style.get("cell_margin"), dict):
                    for margin_field in ("left", "right", "top", "bottom"):
                        if margin_field in style["cell_margin"] and not isinstance(style["cell_margin"][margin_field], int):
                            errors.append(
                                _error(
                                    path + f".style.cell_margin.{margin_field}",
                                    "CELL_MARGIN_NOT_INT",
                                    f"{margin_field} must be an integer",
                                )
                            )

    table_operations = job.get("table_operations", [])
    if not isinstance(table_operations, list):
        errors.append(_error("$.table_operations", "TABLE_OPERATIONS_NOT_LIST", "table_operations must be a list"))
    else:
        for index, operation in enumerate(table_operations):
            path = f"$.table_operations[{index}]"
            if not isinstance(operation, dict):
                errors.append(_error(path, "TABLE_OPERATION_NOT_OBJECT", "table operation must be an object"))
                continue
            op = operation.get("op")
            if op not in SUPPORTED_TABLE_OPERATION_TYPES:
                errors.append(_error(path + ".op", "TABLE_OPERATION_UNSUPPORTED", "unsupported table operation", op))
            if "table_index" in operation and not isinstance(operation["table_index"], int):
                errors.append(_error(path + ".table_index", "TABLE_INDEX_NOT_INT", "table_index must be an integer"))
            if op in {"update_cells", "append_row"} and not isinstance(operation.get("values"), list):
                errors.append(_error(path + ".values", "TABLE_VALUES_NOT_LIST", "values must be a list"))
            if op in {"merge_cells", "unmerge_cell"}:
                for field in ("row_index", "col_index"):
                    if not isinstance(operation.get(field), int):
                        errors.append(_error(path + f".{field}", "TABLE_CELL_ADDRESS_NOT_INT", f"{field} must be an integer"))
                if op == "merge_cells":
                    for field in ("row_span", "col_span"):
                        if not isinstance(operation.get(field), int):
                            errors.append(_error(path + f".{field}", "TABLE_CELL_SPAN_NOT_INT", f"{field} must be an integer"))
                        elif operation[field] < 1:
                            errors.append(_error(path + f".{field}", "TABLE_CELL_SPAN_INVALID", f"{field} must be >= 1"))
            if op == "set_cell_layout":
                for field in ("row_index", "col_index"):
                    if not isinstance(operation.get(field), int):
                        errors.append(_error(path + f".{field}", "TABLE_CELL_ADDRESS_NOT_INT", f"{field} must be an integer"))
                layout = operation.get("layout")
                if not isinstance(layout, dict):
                    errors.append(_error(path + ".layout", "TABLE_CELL_LAYOUT_NOT_OBJECT", "layout must be an object"))

    images = job.get("images", [])
    if not isinstance(images, list):
        errors.append(_error("$.images", "IMAGES_NOT_LIST", "images must be a list"))
    else:
        for index, image in enumerate(images):
            path = f"$.images[{index}]"
            if not isinstance(image, dict):
                errors.append(_error(path, "IMAGE_NOT_OBJECT", "image must be an object"))
                continue
            mode = image.get("mode", "png_insert")
            if mode not in SUPPORTED_IMAGE_MODES:
                errors.append(_error(path + ".mode", "IMAGE_MODE_UNSUPPORTED", "unsupported image mode", mode))
            if mode in {"png_insert", "visible_png_insert"} and not image.get("path"):
                errors.append(_error(path + ".path", "IMAGE_PATH_REQUIRED", f"{mode} image requires path"))
            if mode in {"chart_png", "visible_chart_png"} and "chart" not in image and "chart_json" not in image:
                errors.append(_error(path + ".chart", "CHART_DATA_REQUIRED", f"{mode} image requires chart or chart_json"))
            if "picture_index" in image and (not isinstance(image["picture_index"], int) or image["picture_index"] < 0):
                errors.append(_error(path + ".picture_index", "PICTURE_INDEX_INVALID", "picture_index must be a non-negative integer"))
            if require_external_files:
                for field in ("path", "chart_json"):
                    if field in image:
                        file_path = Path(str(image[field]))
                        resolved = _resolve_path(str(file_path), base_dir)
                        if not resolved.exists():
                            errors.append(_error(path + f".{field}", "EXTERNAL_FILE_NOT_FOUND", "external file not found", str(image[field])))
            _layout, layout_warnings = normalize_image_layout(image)
            for warning in layout_warnings:
                warnings.append(_warning(path, warning["type"], "image layout warning", warning))

    status = "FAIL" if errors else ("WARN" if warnings else "PASS")
    return {
        "status": status,
        "errors": errors,
        "warnings": warnings,
        "counts": {
            "paragraphs": len(paragraphs) if isinstance(paragraphs, list) else 0,
            "tables": len(tables) if isinstance(tables, list) else 0,
            "table_operations": len(table_operations) if isinstance(table_operations, list) else 0,
            "images": len(images) if isinstance(images, list) else 0,
            "document_metadata": 1 if isinstance(document_metadata, dict) else 0,
            "sections": sections.get("count", 0) if isinstance(sections, dict) else (sections if isinstance(sections, int) else 0),
            "package_manifest": 1 if isinstance(package_manifest, dict) else 0,
            "preview_text": 1 if isinstance(preview_text, dict) else 0,
            "page_layout": (1 if isinstance(page_layout, dict) else 0) + (len(page_layouts) if isinstance(page_layouts, list) else 0),
            "page_numbering": (1 if isinstance(page_numbering, dict) else 0)
            + (len(page_numberings) if isinstance(page_numberings, list) else 0),
        },
    }


__all__ = ["validate_compose_job"]
