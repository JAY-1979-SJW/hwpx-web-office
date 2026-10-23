"""Structured HWPX inspection and JSON-driven edit pipeline.

This tool is intentionally built on top of the existing HwpxEditor facade so
manual edits, batch edits, and audit output all exercise the same code paths.
"""

from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path
from typing import Any

from hwpx_package import HwpxPackage, HwpxValidator, local_name, read_json, text_nodes, text_quality_report, write_csv, write_json
from hwpx_table_ops import (
    find_tables,
    get_table_cell_matrix,
    set_table_visual_cell_vertical_align,
    set_table_visual_cell_solid_fill,
    shrink_table_visual_cell_text_to_fit,
)
from hwpx_writer_adapter import HwpxEditor
from hwp_to_hwpx_standalone import write_text_hwpx


PLACEHOLDER_RE = re.compile(r"\{\{([^{}]+)\}\}")
INPUT_REQUIRED_RE = re.compile(r"\[INPUT_REQUIRED:([^\]]+)\]")
MOJIBAKE_SHAPE_RE = re.compile(r"\?[\uac00-\ud7a3]|\ufffd")


def _preview(value: str, limit: int = 160) -> str:
    value = " ".join(str(value or "").split())
    return value if len(value) <= limit else value[: limit - 3] + "..."


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _rel_output_path(input_path: Path, input_root: Path, output_root: Path) -> Path:
    try:
        rel = input_path.resolve().relative_to(input_root.resolve())
    except ValueError:
        rel = Path(input_path.name)
    return output_root / rel


def _resolve_visual_coords(package: HwpxPackage, table_index: int, row_index: int, col_index: int) -> tuple[int | None, int | None]:
    """Physical (row_index, col_index) → visual_row/visual_col using cellAddr.

    set_cells uses physical coordinates while shrink_table_visual_cell_text_to_fit
    needs visual coordinates. get_table_cell_matrix exposes both per cell.
    Returns (None, None) if the cell cannot be located so callers can skip
    post-edit options safely.
    """
    matrix = get_table_cell_matrix(package, table_index)
    if matrix.get("status") != "PASS":
        return None, None
    for row in matrix.get("rows", []):
        for cell in row.get("cells", []):
            if cell.get("row_index") == row_index and cell.get("col_index") == col_index:
                return cell.get("visual_row"), cell.get("visual_col")
    return None, None


def _apply_cell_post_edit_options(
    package: HwpxPackage,
    table_index: int,
    visual_row: int | None,
    visual_col: int | None,
    value: str,
    item: dict[str, Any],
) -> list[dict[str, Any]]:
    """Run optional post-edit operations (vertical_align, shrink_to_fit).

    Returns the list of operation reports so callers can extend the operations
    list. Skipped silently when visual coordinates cannot be resolved (e.g.
    physical cell that does not yet expose a cellAddr); set_cells fallback
    swallows None coordinates to keep API contract intact.
    """
    ops: list[dict[str, Any]] = []
    if visual_row is None or visual_col is None:
        return ops
    if item.get("vertical_align"):
        ops.append(
            set_table_visual_cell_vertical_align(
                package, table_index, int(visual_row), int(visual_col), str(item["vertical_align"])
            )
        )
    # solid_fill: {"color": "D9EAF7"} 또는 fill_color: "D9EAF7"
    fill_color = None
    sf = item.get("solid_fill")
    if isinstance(sf, dict):
        fill_color = str(sf.get("color", ""))
    elif isinstance(sf, str) and sf:
        fill_color = sf
    elif item.get("fill_color"):
        fill_color = str(item["fill_color"])
    if fill_color:
        ops.append(
            set_table_visual_cell_solid_fill(
                package, table_index, int(visual_row), int(visual_col), fill_color
            )
        )
    if item.get("shrink_to_fit"):
        ops.append(
            shrink_table_visual_cell_text_to_fit(
                package, table_index, int(visual_row), int(visual_col), str(value)
            )
        )
    return ops


def _count_descendants(root: Any, names: set[str]) -> int:
    return sum(1 for elem in root.iter() if local_name(elem.tag).lower() in names)


def _table_like_count(root: Any) -> int:
    count = 0
    for elem in root.iter():
        name = local_name(elem.tag).lower()
        if name in {"tbl", "table"} or "tbl" in name or "table" in name:
            count += 1
    return count


def _collect_placeholders(package: HwpxPackage) -> dict[str, Any]:
    by_entry = []
    tokens: dict[str, int] = {}
    for entry in package.xml_entries():
        xml_text = package.read_text(entry)
        matches = []
        for pattern, kind in ((PLACEHOLDER_RE, "double_brace"), (INPUT_REQUIRED_RE, "input_required")):
            for match in pattern.finditer(xml_text):
                token = match.group(1).strip()
                tokens[token] = tokens.get(token, 0) + 1
                matches.append(
                    {
                        "kind": kind,
                        "token": token,
                        "offset": match.start(),
                        "preview": _preview(xml_text[max(0, match.start() - 50) : match.end() + 50]),
                    }
                )
        if matches:
            by_entry.append({"entry": entry, "count": len(matches), "matches": matches})
    return {"count": sum(tokens.values()), "unique_count": len(tokens), "tokens": tokens, "by_entry": by_entry}


def _inspect_sections(package: HwpxPackage) -> list[dict[str, Any]]:
    sections = []
    for section_index, entry in enumerate(package.section_entries()):
        try:
            root = package.read_xml(entry)
        except Exception as exc:  # noqa: BLE001
            sections.append({"section_index": section_index, "entry": entry, "status": "XML_PARSE_ERROR", "error": str(exc)})
            continue
        node_texts = [node.text or "" for node in text_nodes(root)]
        joined_text = " ".join(node_texts)
        quality = text_quality_report(joined_text)
        shape_hits = len(MOJIBAKE_SHAPE_RE.findall(joined_text))
        quality["mojibake_shape_hit_count"] = shape_hits
        if shape_hits:
            quality["ok"] = False
        sections.append(
            {
                "section_index": section_index,
                "entry": entry,
                "status": "PASS",
                "paragraph_count": _count_descendants(root, {"p", "para"}),
                "table_count": _table_like_count(root),
                "text_node_count": len(node_texts),
                "text_length": sum(len(value) for value in node_texts),
                "preview": _preview(joined_text),
                "text_quality": quality,
            }
        )
    return sections


def _inspect_tables(package: HwpxPackage) -> list[dict[str, Any]]:
    tables = []
    for table in find_tables(package):
        table_index = int(table["table_index"])
        matrix = get_table_cell_matrix(package, table_index)
        cells = []
        warning_count = 0
        if matrix.get("status") == "PASS":
            for row in matrix.get("rows", []):
                for cell in row.get("cells", []):
                    fit_status = (cell.get("fit_check") or {}).get("status")
                    if fit_status and fit_status != "PASS":
                        warning_count += 1
                    cells.append(
                        {
                            "row": cell.get("row_index"),
                            "col": cell.get("col_index"),
                            "visual_row": cell.get("visual_row"),
                            "visual_col": cell.get("visual_col"),
                            "rowspan": cell.get("rowspan"),
                            "colspan": cell.get("colspan"),
                            "text": cell.get("text", ""),
                            "preview": _preview(cell.get("text", "")),
                            "text_node_count": cell.get("text_node_count"),
                            "borderFillIDRef": cell.get("borderFillIDRef"),
                            "font_height": cell.get("font_height"),
                            "fit_check": cell.get("fit_check"),
                        }
                    )
        tables.append(
            {
                **table,
                "status": matrix.get("status"),
                "matrix_row_count": len(matrix.get("rows", [])),
                "cell_count": len(cells),
                "fit_warning_count": warning_count,
                "cells": cells,
            }
        )
    return tables


def _text_match(value: str, selector: dict[str, Any]) -> bool:
    value = str(value or "")
    if selector.get("regex") is not None:
        return re.search(str(selector["regex"]), value) is not None
    if selector.get("exact") is not None:
        return value == str(selector["exact"])
    if selector.get("contains") is not None:
        return str(selector["contains"]) in value
    if selector.get("text") is not None:
        return value == str(selector["text"])
    return False


def find_table_cells_by_text(package: HwpxPackage, selector: dict[str, Any]) -> list[dict[str, Any]]:
    matches = []
    table_indexes = [int(selector["table"])] if selector.get("table") is not None else [int(t["table_index"]) for t in find_tables(package)]
    for table_index in table_indexes:
        matrix = get_table_cell_matrix(package, table_index)
        if matrix.get("status") != "PASS":
            continue
        for row in matrix.get("rows", []):
            for cell in row.get("cells", []):
                if not _text_match(str(cell.get("text", "")), selector):
                    continue
                matches.append(
                    {
                        "table": table_index,
                        "entry": matrix.get("entry"),
                        "row": cell.get("row_index"),
                        "col": cell.get("col_index"),
                        "visual_row": cell.get("visual_row"),
                        "visual_col": cell.get("visual_col"),
                        "text": cell.get("text", ""),
                    }
                )
    return matches


def _inspect_images(package: HwpxPackage) -> dict[str, Any]:
    editor = HwpxEditor(package)
    result: dict[str, Any] = {"images": [], "pictures": {}}
    try:
        result["images"] = editor.list_images()
    except Exception as exc:  # noqa: BLE001
        result["image_error"] = str(exc)
    try:
        result["pictures"] = editor.list_picture_objects()
    except Exception as exc:  # noqa: BLE001
        result["picture_error"] = str(exc)
    return result


def _build_gate(report: dict[str, Any]) -> dict[str, Any]:
    validation = report.get("validation") if isinstance(report.get("validation"), dict) else {}
    encoding = validation.get("encoding_check") if isinstance(validation.get("encoding_check"), dict) else {}
    package_consistency = validation.get("package_consistency") if isinstance(validation.get("package_consistency"), dict) else {}
    table_failures = [table for table in report.get("tables", []) if table.get("status") != "PASS"]
    section_failures = [section for section in report.get("sections", []) if section.get("status") != "PASS"]
    text_quality_warnings = [
        section
        for section in report.get("sections", [])
        if isinstance(section.get("text_quality"), dict) and not section["text_quality"].get("ok")
    ]
    checks = [
        {"name": "zip_ok", "status": "PASS" if validation.get("zip_ok") else "FAIL"},
        {"name": "xml_ok", "status": "PASS" if validation.get("xml_ok") else "FAIL", "errors": validation.get("xml_errors")},
        {
            "name": "package_consistency",
            "status": "PASS" if package_consistency.get("status") in {"PASS", "WARN"} else "FAIL",
            "consistency_status": package_consistency.get("status"),
            "errors": package_consistency.get("errors", []),
            "warnings": package_consistency.get("warnings", []),
        },
        {"name": "sections_readable", "status": "PASS" if not section_failures else "FAIL", "failed_count": len(section_failures)},
        {"name": "tables_addressable", "status": "PASS" if not table_failures else "FAIL", "failed_count": len(table_failures)},
        {
            "name": "section_text_quality",
            "status": "PASS" if not text_quality_warnings else "WARN",
            "warning_count": len(text_quality_warnings),
        },
        {
            "name": "encoding_quality",
            "status": "PASS" if not encoding or encoding.get("status") == "PASS" else "WARN",
            "problem_entries": encoding.get("problem_entries", []),
        },
    ]
    hard_failed = [check["name"] for check in checks if check["status"] == "FAIL"]
    return {
        "status": "PASS" if not hard_failed else "FAIL",
        "failed_checks": hard_failed,
        "checks": checks,
    }


KNOWN_PLAN_KEYS = {
    "dry_run",
    "ensure_section_count",
    "replace_placeholders",
    "placeholders",
    "replace_text",
    "replace_text_scope",
    "set_cells",
    "set_cells_by_text",
    "set_cells_by_label",
    "set_visual_cells",
    "append_table_rows",
    "delete_table_rows",
    "clone_tables",
    "merge_cells",
    "unmerge_cells",
    "set_cell_layouts",
    "append_generated_tables",
    "insert_generated_pictures",
    "append_paragraphs",
    "replace_images",
    "add_bindata_images",
    "rebind_pictures",
    "clone_pictures",
    "set_cell_styles",
    "fill_schedule_bars",
    "paragraph_edits",
}

KNOWN_CREATE_KEYS = {
    "metadata",
    "paragraphs",
    "sections",
    "section_blocks",
    "append_generated_tables",
    "original_hwp",
}


def _normalize_create_section(section: Any) -> tuple[list[str], list[dict[str, Any]] | None]:
    if isinstance(section, dict):
        if "blocks" in section:
            blocks = [dict(block) for block in section.get("blocks", [])]
            paragraphs = []
            for block in blocks:
                if block.get("type") == "table":
                    for row in block.get("rows", []):
                        paragraphs.extend(str(cell) for cell in row if str(cell))
                else:
                    text = str(block.get("text", ""))
                    if text:
                        paragraphs.append(text)
            return paragraphs, blocks
        if "paragraphs" in section:
            return [str(item) for item in section.get("paragraphs", [])], None
    if isinstance(section, list):
        if all(isinstance(item, dict) for item in section):
            return _normalize_create_section({"blocks": section})
        return [str(item) for item in section], None
    return [str(section)], None


def normalize_create_plan(plan: dict[str, Any]) -> dict[str, Any]:
    if "section_blocks" in plan:
        blocks_by_section = [[dict(block) for block in section] for section in plan.get("section_blocks", [])]
        paragraphs = []
        for section_blocks in blocks_by_section:
            section_texts = []
            for block in section_blocks:
                if block.get("type") == "table":
                    for row in block.get("rows", []):
                        section_texts.extend(str(cell) for cell in row if str(cell))
                else:
                    text = str(block.get("text", ""))
                    if text:
                        section_texts.append(text)
            paragraphs.append(section_texts)
        return {"paragraphs": paragraphs, "section_blocks": blocks_by_section}
    if "sections" in plan:
        paragraphs = []
        section_blocks = []
        has_blocks = False
        for section in plan.get("sections", []):
            section_paragraphs, blocks = _normalize_create_section(section)
            paragraphs.append(section_paragraphs)
            section_blocks.append(blocks or [{"type": "paragraph", "text": text} for text in section_paragraphs])
            has_blocks = has_blocks or blocks is not None
        return {"paragraphs": paragraphs, "section_blocks": section_blocks if has_blocks else None}
    paragraphs = [str(item) for item in plan.get("paragraphs", [])]
    appended_tables = [
        {"type": "table", "rows": item.get("rows", [])}
        for item in plan.get("append_generated_tables", []) or []
        if isinstance(item, dict)
    ]
    if appended_tables:
        section_blocks = [{"type": "paragraph", "text": text} for text in paragraphs]
        section_blocks.extend(appended_tables)
        for block in appended_tables:
            for row in block.get("rows", []):
                paragraphs.extend(str(cell) for cell in row if str(cell))
        return {"paragraphs": paragraphs, "section_blocks": [section_blocks]}
    return {"paragraphs": paragraphs, "section_blocks": None}


def validate_create_plan(plan: dict[str, Any], *, base_dir: Path | None = None) -> dict[str, Any]:
    errors = []
    warnings = []
    if not isinstance(plan, dict):
        return {"status": "FAIL", "errors": [{"path": "$", "message": "create plan must be a JSON object"}], "warnings": []}
    for key in sorted(set(plan) - KNOWN_CREATE_KEYS):
        warnings.append({"path": key, "message": "unknown create key will be ignored"})
    normalized = normalize_create_plan(plan)
    paragraphs = normalized["paragraphs"]
    section_blocks = normalized["section_blocks"]
    if not paragraphs:
        errors.append({"path": "paragraphs", "message": "at least one paragraph or section is required"})
    for section_index, section in enumerate(paragraphs):
        if not section:
            warnings.append({"path": f"sections[{section_index}]", "message": "empty section will be created"})
    for section_index, blocks in enumerate(section_blocks or []):
        for block_index, block in enumerate(blocks):
            if block.get("type") == "table":
                rows = block.get("rows", [])
                if not isinstance(rows, list) or not rows:
                    errors.append({"path": f"sections[{section_index}].blocks[{block_index}].rows", "message": "table rows are required"})
    original_hwp = plan.get("original_hwp")
    if original_hwp:
        candidate = Path(str(original_hwp))
        if not candidate.is_absolute() and base_dir is not None:
            candidate = base_dir / candidate
        if not candidate.exists():
            errors.append({"path": "original_hwp", "message": f"original HWP file not found: {candidate}"})
    return {"status": "PASS" if not errors else "FAIL", "errors": errors, "warnings": warnings}


def create_hwpx_document(output_path: Path, plan: dict[str, Any], *, base_dir: Path | None = None) -> dict[str, Any]:
    output_path = Path(output_path)
    validation = validate_create_plan(plan, base_dir=base_dir)
    if validation["status"] != "PASS":
        return {
            "mode": "hwpx_edit_create",
            "status": "FAIL",
            "output": None,
            "plan_validation": validation,
        }
    normalized = normalize_create_plan(plan)
    original_hwp = plan.get("original_hwp")
    original_hwp_path = None
    if original_hwp:
        original_hwp_path = Path(str(original_hwp))
        if not original_hwp_path.is_absolute() and base_dir is not None:
            original_hwp_path = base_dir / original_hwp_path
    write_text_hwpx(
        output_path,
        normalized["paragraphs"],
        metadata=dict(plan.get("metadata", {})),
        section_blocks=normalized["section_blocks"],
        original_hwp_path=original_hwp_path,
    )
    inspection = inspect_hwpx(output_path)
    file_validation = HwpxValidator.validate_hwpx(output_path)
    return {
        "mode": "hwpx_edit_create",
        "status": _validation_status(file_validation),
        "output": str(output_path),
        "plan_validation": validation,
        "validation": file_validation,
        "inspection": inspection,
        "summary": {
            "sections": inspection.get("entries", {}).get("section_count"),
            "tables": len(inspection.get("tables", [])),
            "paragraphs": sum(int(section.get("paragraph_count") or 0) for section in inspection.get("sections", [])),
        },
    }


def validate_edit_plan(plan: dict[str, Any], *, base_dir: Path | None = None) -> dict[str, Any]:
    errors = []
    warnings = []
    if not isinstance(plan, dict):
        return {"status": "FAIL", "errors": [{"path": "$", "message": "plan must be a JSON object"}], "warnings": []}

    unknown = sorted(set(plan) - KNOWN_PLAN_KEYS)
    for key in unknown:
        warnings.append({"path": key, "message": "unknown plan key will be ignored"})

    for index, item in enumerate(_as_list(plan.get("replace_text"))):
        if not isinstance(item, dict) or not item.get("old"):
            errors.append({"path": f"replace_text[{index}].old", "message": "old text is required"})
        if isinstance(item, dict) and item.get("regex"):
            try:
                re.compile(str(item.get("old", "")))
            except re.error as exc:
                errors.append({"path": f"replace_text[{index}].old", "message": f"invalid regex: {exc}"})

    for key in ("set_cells", "set_visual_cells", "set_cells_by_text", "set_cells_by_label"):
        for index, item in enumerate(plan.get(key, []) or []):
            if not isinstance(item, dict):
                errors.append({"path": f"{key}[{index}]", "message": "operation must be an object"})
                continue
            if key == "set_cells" and not {"row", "row_index"} & set(item):
                errors.append({"path": f"{key}[{index}]", "message": "row or row_index is required"})
            if key == "set_cells" and not {"col", "col_index"} & set(item):
                errors.append({"path": f"{key}[{index}]", "message": "col or col_index is required"})
            if key == "set_visual_cells" and not {"visual_row", "row"} & set(item):
                errors.append({"path": f"{key}[{index}]", "message": "visual_row or row is required"})
            if key == "set_visual_cells" and not {"visual_col", "col"} & set(item):
                errors.append({"path": f"{key}[{index}]", "message": "visual_col or col is required"})
            if key == "set_cells_by_text" and not {"exact", "contains", "regex", "text"} & set(item):
                errors.append({"path": f"{key}[{index}]", "message": "one of exact, contains, regex, text is required"})
            if key == "set_cells_by_label" and not {"label", "exact", "contains", "regex", "text"} & set(item):
                errors.append({"path": f"{key}[{index}]", "message": "label or text selector is required"})

    for key in ("replace_images", "add_bindata_images", "insert_generated_pictures"):
        for index, item in enumerate(plan.get(key, []) or []):
            if not isinstance(item, dict):
                errors.append({"path": f"{key}[{index}]", "message": "operation must be an object"})
                continue
            image_path = item.get("path", item.get("replacement", item.get("image")))
            if not image_path:
                errors.append({"path": f"{key}[{index}].path", "message": "image path is required"})
                continue
            candidate = Path(str(image_path))
            if not candidate.is_absolute() and base_dir is not None:
                candidate = base_dir / candidate
            if not candidate.exists():
                errors.append({"path": f"{key}[{index}].path", "message": f"image file not found: {candidate}"})

    for index, item in enumerate(plan.get("paragraph_edits", []) or []):
        if not isinstance(item, dict):
            errors.append({"path": f"paragraph_edits[{index}]", "message": "operation must be an object"})
            continue
        ct = item.get("commandType")
        # WEB-OFFICE-PARA-EDIT-APPLYFORMAT-EXISTING-CHARPR-01:
        # APPLY_FORMAT 은 afterText 대신 targetCharPrIDRef 가 필수.
        if ct == "APPLY_FORMAT":
            required = ("commandId", "paragraphId", "rangeStart", "rangeEnd",
                        "expectedBefore", "targetCharPrIDRef",
                        "sourceDocumentHash", "commandType", "containerScope")
        else:
            required = ("commandId", "paragraphId", "runId", "rangeStart", "rangeEnd",
                        "expectedBefore", "afterText", "sourceDocumentHash",
                        "commandType", "containerScope")
        for k in required:
            if k not in item:
                errors.append({"path": f"paragraph_edits[{index}].{k}",
                               "message": f"{k} is required"})
        scope = item.get("containerScope") or {}
        # CLAUDE.md §4.2 — header/footer 는 텍스트 편집만(구조 변경 아님).
        if scope.get("kind") not in {"cell", "block", "header", "footer"}:
            errors.append({"path": f"paragraph_edits[{index}].containerScope.kind",
                           "message": "kind must be 'cell', 'block', 'header' or 'footer'"})
        if scope.get("kind") == "cell":
            for k in ("tableIndex", "rowIndex", "colIndex", "paragraphIndex"):
                if k not in scope:
                    errors.append({"path": f"paragraph_edits[{index}].containerScope.{k}",
                                   "message": f"{k} is required for cell scope"})
        if scope.get("kind") in ("header", "footer"):
            for k in ("sectionIndex", "objectId", "paragraphIndex"):
                if k not in scope:
                    errors.append({"path": f"paragraph_edits[{index}].containerScope.{k}",
                                   "message": f"{k} is required for {scope.get('kind')} scope"})
        if ct not in {"TYPE_TEXT", "REPLACE_TEXT_RANGE", "DELETE_TEXT_RANGE",
                            "APPLY_FORMAT"}:
            errors.append({"path": f"paragraph_edits[{index}].commandType",
                           "message": "unsupported commandType"})

    return {"status": "PASS" if not errors else "FAIL", "errors": errors, "warnings": warnings}


def _cell_key(cell: dict[str, Any]) -> tuple[Any, ...]:
    return (cell.get("row"), cell.get("col"), cell.get("visual_row"), cell.get("visual_col"))


def diff_inspections(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    section_changes = []
    for index, before_section in enumerate(before.get("sections", [])):
        after_section = after.get("sections", [])[index] if index < len(after.get("sections", [])) else {}
        if before_section.get("preview") != after_section.get("preview") or before_section.get("text_length") != after_section.get("text_length"):
            section_changes.append(
                {
                    "section_index": index,
                    "before_preview": before_section.get("preview"),
                    "after_preview": after_section.get("preview"),
                    "before_text_length": before_section.get("text_length"),
                    "after_text_length": after_section.get("text_length"),
                }
            )

    cell_changes = []
    before_tables = {table.get("table_index"): table for table in before.get("tables", [])}
    for after_table in after.get("tables", []):
        table_index = after_table.get("table_index")
        before_table = before_tables.get(table_index, {})
        before_cells = {_cell_key(cell): cell for cell in before_table.get("cells", [])}
        for after_cell in after_table.get("cells", []):
            before_cell = before_cells.get(_cell_key(after_cell))
            if not before_cell:
                cell_changes.append({"table": table_index, "change": "ADDED_OR_REKEYED", "after": after_cell})
                continue
            if before_cell.get("text") != after_cell.get("text"):
                cell_changes.append(
                    {
                        "table": table_index,
                        "row": after_cell.get("row"),
                        "col": after_cell.get("col"),
                        "visual_row": after_cell.get("visual_row"),
                        "visual_col": after_cell.get("visual_col"),
                        "before": before_cell.get("text"),
                        "after": after_cell.get("text"),
                    }
                )

    before_placeholder_count = int(before.get("placeholders", {}).get("count") or 0)
    after_placeholder_count = int(after.get("placeholders", {}).get("count") or 0)
    return {
        "status": "PASS",
        "section_change_count": len(section_changes),
        "cell_change_count": len(cell_changes),
        "placeholder_delta": after_placeholder_count - before_placeholder_count,
        "before_gate": before.get("gate", {}).get("status"),
        "after_gate": after.get("gate", {}).get("status"),
        "section_changes": section_changes,
        "cell_changes": cell_changes,
    }


def replace_text_nodes(package: HwpxPackage, replacements: list[dict[str, Any]], *, xml_scope: str = "sections") -> dict[str, Any]:
    entries = package.section_entries() if xml_scope == "sections" else package.xml_entries()
    results = []
    total = 0
    for item in replacements:
        old = str(item.get("old", ""))
        new = str(item.get("new", ""))
        use_regex = bool(item.get("regex", False))
        if not old:
            results.append({"status": "SKIP_EMPTY_OLD", "old": old})
            continue
        item_count = 0
        touched_entries = []
        for entry in entries:
            try:
                root = package.read_xml(entry)
            except Exception as exc:  # noqa: BLE001
                results.append({"status": "XML_PARSE_ERROR", "entry": entry, "error": str(exc)})
                continue
            entry_count = 0
            for elem in root.iter():
                if elem.text is None:
                    continue
                before = elem.text
                after = re.sub(old, new, before) if use_regex else before.replace(old, new)
                if after != before:
                    entry_count += 1
                    elem.text = after
            if entry_count:
                package.write_xml(entry, root)
                touched_entries.append({"entry": entry, "text_nodes": entry_count})
                item_count += entry_count
        results.append(
            {
                "status": "PASS" if item_count else "TEXT_NOT_FOUND",
                "old": old,
                "new": new,
                "regex": use_regex,
                "text_nodes": item_count,
                "entries": touched_entries,
            }
        )
        total += item_count
    return {"status": "PASS" if total else "TEXT_NOT_FOUND", "replacement_count": total, "results": results}


def set_cells_by_text(package: HwpxPackage, editor: HwpxEditor, item: dict[str, Any]) -> dict[str, Any]:
    matches = find_table_cells_by_text(package, item)
    limit = int(item.get("limit", 1 if item.get("first_only", False) else len(matches)))
    selected = matches[: max(limit, 0)]
    results = []
    for match in selected:
        results.append(
            editor.set_table_cell_text(
                int(match["table"]),
                int(match["row"]),
                int(match["col"]),
                str(item.get("value", "")),
                bool(item.get("clear_remaining", True)),
            )
        )
    return {
        "status": "PASS" if results and all(result.get("status") == "PASS" for result in results) else "CELL_TEXT_MATCH_NOT_FOUND",
        "match_count": len(matches),
        "updated_count": sum(1 for result in results if result.get("status") == "PASS"),
        "matches": matches,
        "results": results,
    }


def set_cells_by_label(package: HwpxPackage, editor: HwpxEditor, item: dict[str, Any]) -> dict[str, Any]:
    selector = dict(item)
    selector["text"] = item.get("label", item.get("text", item.get("exact")))
    label_matches = find_table_cells_by_text(package, selector)
    row_offset = int(item.get("row_offset", 0))
    col_offset = int(item.get("col_offset", 1))
    limit = int(item.get("limit", 1))
    results = []
    selected = label_matches[: max(limit, 0)]
    for match in selected:
        results.append(
            editor.set_table_cell_text(
                int(match["table"]),
                int(match["row"]) + row_offset,
                int(match["col"]) + col_offset,
                str(item.get("value", "")),
                bool(item.get("clear_remaining", True)),
            )
        )
    return {
        "status": "PASS" if results and all(result.get("status") == "PASS" for result in results) else "LABEL_CELL_NOT_FOUND",
        "label_match_count": len(label_matches),
        "updated_count": sum(1 for result in results if result.get("status") == "PASS"),
        "matches": label_matches,
        "results": results,
    }


def inspect_hwpx(input_path: Path) -> dict[str, Any]:
    package = HwpxPackage(input_path)
    validation = HwpxValidator.validate_hwpx(input_path)
    return inspect_hwpx_package(package, str(input_path), validation)


def inspect_hwpx_package(package: HwpxPackage, label: str, validation: dict[str, Any] | None = None) -> dict[str, Any]:
    validation = validation or HwpxValidator.validate_entries(package.entries, label)
    report = {
        "mode": "hwpx_edit_inspect",
        "input": label,
        "validation": validation,
        "entries": {
            "count": len(package.list_entries()),
            "xml_count": len(package.xml_entries()),
            "section_count": len(package.section_entries()),
        },
        "sections": _inspect_sections(package),
        "tables": _inspect_tables(package),
        "placeholders": _collect_placeholders(package),
        "media": _inspect_images(package),
    }
    report["gate"] = _build_gate(report)
    return report


def _operation_status(results: list[dict[str, Any]]) -> str:
    pass_statuses = {
        "PASS",
        "SKIP",
        "FONT_SHRINK_PASS",
        "FONT_SHRINK_NOT_NEEDED",
        "VERTICAL_ALIGN_PASS",
        "NO_PLACEHOLDER_FOUND",
        "APPEND_ROW_PASS",
        "DELETE_ROW_PASS",
        "CLONE_TABLE_PASS",
        "CLONED_TABLE_APPEND_PASS",
        "GENERATED_TABLE_APPEND_PASS",
        "GENERATED_PARAGRAPH_APPEND_PASS",
        "GENERATED_PNG_PICTURE_INSERT_PASS",
        "GENERATED_PICTURE_APPEND_PASS",
        "IMAGE_REPLACE_PASS",
        "IMAGE_BINDATA_ADD_PASS",
        "PICTURE_REBIND_PASS",
        "PICTURE_CLONE_REBIND_PASS",
        "MERGE_CELLS_PASS",
        "UNMERGE_CELL_PASS",
        "SET_CELL_LAYOUT_PASS",
        "MERGE_SPAN_NOOP",
        "UNMERGE_NOOP",
        "SET_CELL_LAYOUT_NOOP",
        "SOLID_FILL_PASS",
        "REUSED_EXISTING",
        "CREATED_NEW",
        "SET_TEXT_PASS",
        "TEXT_WRITTEN",
    }
    return "PASS" if all(result.get("status") in pass_statuses for result in results) else "FAIL"


def _validation_status(validation: dict[str, Any]) -> str:
    package_status = (validation.get("package_consistency") or {}).get("status")
    return "PASS" if validation.get("zip_ok") and validation.get("xml_ok") and package_status in {"PASS", "WARN"} else "FAIL"


def apply_edit_plan(input_path: Path, output_path: Path, plan: dict[str, Any], *, dry_run: bool = False) -> dict[str, Any]:
    input_path = Path(input_path)
    output_path = Path(output_path)
    plan_validation = validate_edit_plan(plan, base_dir=input_path.parent)
    plan_is_dict = isinstance(plan, dict)
    before_inspection = inspect_hwpx(input_path)
    if plan_validation["status"] != "PASS":
        return {
            "mode": "hwpx_edit_apply",
            "status": "FAIL",
            "dry_run": dry_run or bool(plan.get("dry_run", False)) if plan_is_dict else dry_run,
            "input": str(input_path),
            "output": None,
            "plan_validation": plan_validation,
            "operation_count": 0,
            "operations": [],
            "inspection": before_inspection,
            "diff": {"status": "SKIPPED_PLAN_INVALID"},
        }
    package = HwpxPackage(input_path)
    editor = HwpxEditor(package)
    operations: list[dict[str, Any]] = []
    dry_run = dry_run or bool(plan.get("dry_run", False))

    if plan.get("ensure_section_count") is not None:
        operations.append(editor.ensure_section_count(int(plan["ensure_section_count"])))

    mapping = plan.get("replace_placeholders") or plan.get("placeholders")
    if isinstance(mapping, dict) and mapping:
        operations.append(editor.replace_placeholders({str(key): str(value) for key, value in mapping.items()}))

    text_replacements = plan.get("replace_text")
    if text_replacements:
        operations.append(replace_text_nodes(package, [dict(item) for item in _as_list(text_replacements)], xml_scope=str(plan.get("replace_text_scope", "sections"))))

    for item in plan.get("set_cells", []) or []:
        table_index = int(item.get("table", item.get("table_index", 0)))
        row_index = int(item.get("row", item.get("row_index", -1)))
        col_index = int(item.get("col", item.get("col_index", -1)))
        value = str(item.get("value", ""))
        operations.append(
            editor.set_table_cell_text(
                table_index,
                row_index,
                col_index,
                value,
                bool(item.get("clear_remaining", True)),
            )
        )
        if item.get("vertical_align") or item.get("shrink_to_fit") or item.get("solid_fill") or item.get("fill_color"):
            visual_row, visual_col = _resolve_visual_coords(package, table_index, row_index, col_index)
            operations.extend(_apply_cell_post_edit_options(package, table_index, visual_row, visual_col, value, item))

    para_edit_items = plan.get("paragraph_edits", []) or []
    if para_edit_items:
        # set_cells 좌표 충돌 set 계산
        conflict_cells: set[tuple[int, int, int]] = set()
        for sc in plan.get("set_cells", []) or []:
            if not isinstance(sc, dict):
                continue
            try:
                ti = int(sc.get("table", sc.get("table_index", 0)))
                ri = int(sc.get("row", sc.get("row_index", -1)))
                ci = int(sc.get("col", sc.get("col_index", -1)))
                conflict_cells.add((ti, ri, ci))
            except (TypeError, ValueError):
                continue
        source_hash = None
        for item in para_edit_items:
            if isinstance(item, dict) and item.get("sourceDocumentHash"):
                source_hash = item["sourceDocumentHash"]
                break
        # lazy import — 신규 모듈
        try:
            from scripts.hwpx.web_office.paragraph_writer_adapter import (
                apply_paragraph_edits_plan,
            )
        except ImportError:  # pragma: no cover
            import sys as _sys
            _here = Path(__file__).resolve().parent
            _root = _here.parent.parent
            for _p in (str(_root), str(_here)):
                if _p not in _sys.path:
                    _sys.path.insert(0, _p)
            from scripts.hwpx.web_office.paragraph_writer_adapter import (
                apply_paragraph_edits_plan,
            )
        para_result = apply_paragraph_edits_plan(
            package,
            [dict(it) for it in para_edit_items if isinstance(it, dict)],
            source_hash,
            dry_run=dry_run,
            conflict_cells=conflict_cells,
        )
        operations.append({
            "kind": "paragraph_edits",
            "status": "PASS" if para_result["applied"] and not para_result["rejected"] else (
                "PARTIAL" if para_result["applied"] else "FAIL"
            ),
            "applied": para_result["applied"],
            "rejected": para_result["rejected"],
            "operation_count": para_result["operationCount"],
            "touched_entries": para_result["touchedEntries"],
        })

    for item in plan.get("set_cells_by_text", []) or []:
        item_dict = dict(item)
        result = set_cells_by_text(package, editor, item_dict)
        operations.append(result)
        if item_dict.get("vertical_align") or item_dict.get("shrink_to_fit") or item_dict.get("solid_fill") or item_dict.get("fill_color"):
            value = str(item_dict.get("value", ""))
            for match in result.get("matches", [])[: len(result.get("results", []))]:
                operations.extend(
                    _apply_cell_post_edit_options(
                        package,
                        int(match.get("table", 0)),
                        match.get("visual_row"),
                        match.get("visual_col"),
                        value,
                        item_dict,
                    )
                )

    for item in plan.get("set_cells_by_label", []) or []:
        item_dict = dict(item)
        result = set_cells_by_label(package, editor, item_dict)
        operations.append(result)
        if item_dict.get("vertical_align") or item_dict.get("shrink_to_fit") or item_dict.get("solid_fill") or item_dict.get("fill_color"):
            value = str(item_dict.get("value", ""))
            row_offset = int(item_dict.get("row_offset", 0))
            col_offset = int(item_dict.get("col_offset", 1))
            for match in result.get("matches", [])[: len(result.get("results", []))]:
                table_index = int(match.get("table", 0))
                target_row = int(match.get("row", -1)) + row_offset
                target_col = int(match.get("col", -1)) + col_offset
                visual_row, visual_col = _resolve_visual_coords(package, table_index, target_row, target_col)
                operations.extend(_apply_cell_post_edit_options(package, table_index, visual_row, visual_col, value, item_dict))

    for item in plan.get("set_visual_cells", []) or []:
        table_index = int(item.get("table", item.get("table_index", 0)))
        visual_row = int(item.get("visual_row", item.get("row", -1)))
        visual_col = int(item.get("visual_col", item.get("col", -1)))
        value = str(item.get("value", ""))
        operations.append(
            editor.set_table_visual_cell_text(
                table_index,
                visual_row,
                visual_col,
                value,
                bool(item.get("clear_remaining", True)),
            )
        )
        operations.extend(_apply_cell_post_edit_options(package, table_index, visual_row, visual_col, value, item))

    for item in plan.get("append_table_rows", []) or []:
        operations.append(
            editor.append_table_row(
                int(item.get("table", item.get("table_index", 0))),
                [str(value) for value in item.get("values", item.get("row_values", []))],
                bool(item.get("clear_remaining", True)),
            )
        )

    for item in plan.get("delete_table_rows", []) or []:
        operations.append(
            editor.delete_table_row(
                int(item.get("table", item.get("table_index", 0))),
                int(item.get("row", item.get("row_index", -1))),
                bool(item.get("protect_header", True)),
            )
        )

    for item in plan.get("clone_tables", []) or []:
        operations.append(editor.clone_table(int(item.get("table", item.get("table_index", 0)))))

    for item in plan.get("merge_cells", []) or []:
        operations.append(
            editor.merge_table_cells(
                int(item.get("table", item.get("table_index", 0))),
                int(item.get("row", item.get("row_index", -1))),
                int(item.get("col", item.get("col_index", -1))),
                int(item.get("rowspan", item.get("row_span", 1))),
                int(item.get("colspan", item.get("col_span", 1))),
            )
        )

    for item in plan.get("unmerge_cells", []) or []:
        operations.append(
            editor.unmerge_table_cell(
                int(item.get("table", item.get("table_index", 0))),
                int(item.get("row", item.get("row_index", -1))),
                int(item.get("col", item.get("col_index", -1))),
                bool(item.get("clear_generated_cells", True)),
            )
        )

    for item in plan.get("set_cell_layouts", []) or []:
        operations.append(
            editor.set_cell_layout(
                int(item.get("table", item.get("table_index", 0))),
                int(item.get("row", item.get("row_index", -1))),
                int(item.get("col", item.get("col_index", -1))),
                dict(item.get("layout", {})),
            )
        )

    for item in plan.get("append_generated_tables", []) or []:
        operations.append(
            editor.append_generated_table(
                [[str(value) for value in row] for row in item.get("rows", [])],
                int(item.get("section", item.get("section_index", 0))),
                item.get("style_refs"),
            )
        )

    for item in plan.get("insert_generated_pictures", []) or []:
        operations.append(
            editor.insert_generated_png_picture(
                Path(str(item.get("path", item.get("image", "")))),
                str(item.get("entry", item.get("image_entry", "BinData/generated_picture001.png"))),
                int(item.get("section", item.get("section_index", 0))),
                int(item.get("width", 12000)),
                int(item.get("height", 9000)),
                item.get("manifest_id"),
            )
        )

    for item in plan.get("append_paragraphs", []) or []:
        if isinstance(item, str):
            operations.append(editor.append_generated_paragraph(item))
        else:
            operations.append(
                editor.append_generated_paragraph(
                    str(item.get("text", "")),
                    int(item.get("section", item.get("section_index", 0))),
                    item.get("style_refs"),
                )
            )

    for item in plan.get("replace_images", []) or []:
        if item.get("entry"):
            operations.append(editor.replace_image_by_entry(str(item["entry"]), Path(str(item.get("path", item.get("replacement", ""))))))
        else:
            operations.append(editor.replace_image(int(item.get("index", 0)), Path(str(item.get("path", item.get("replacement", ""))))))

    for item in plan.get("add_bindata_images", []) or []:
        operations.append(editor.add_bindata_image(Path(str(item.get("path", item.get("image", "")))), str(item.get("entry", "BinData/image001.png"))))

    for item in plan.get("rebind_pictures", []) or []:
        operations.append(
            editor.rebind_picture_object(
                int(item.get("picture", item.get("picture_index", 0))),
                str(item.get("entry", item.get("new_entry", ""))),
                item.get("manifest_id", item.get("new_manifest_id")),
            )
        )

    for item in plan.get("clone_pictures", []) or []:
        operations.append(
            editor.clone_picture_object(
                int(item.get("picture", item.get("picture_index", 0))),
                str(item.get("entry", item.get("new_entry", ""))),
                item.get("manifest_id", item.get("new_manifest_id")),
            )
        )

    for item in plan.get("set_cell_styles", []) or []:
        table_index = int(item.get("table", item.get("table_index", 0)))
        row_start = int(item.get("visual_row_start", item.get("visual_row", item.get("row", -1))))
        row_end = int(item.get("visual_row_end", row_start))
        col_start = int(item.get("visual_col_start", item.get("visual_col", item.get("col", -1))))
        col_end = int(item.get("visual_col_end", col_start))
        for vr in range(row_start, row_end + 1):
            for vc in range(col_start, col_end + 1):
                ops = _apply_cell_post_edit_options(package, table_index, vr, vc, "", item)
                operations.extend(ops)

    for item in plan.get("fill_schedule_bars", []) or []:
        table_index = int(item.get("table", item.get("table_index", 0)))
        task_row = int(item.get("task_row", item.get("visual_row", -1)))
        start_col = int(item.get("start_col", -1))
        end_col = int(item.get("end_col", start_col))
        color = str(item.get("color", "92D050"))
        text = str(item.get("text", ""))
        text_at = str(item.get("text_at", "center")).lower()
        shrink = bool(item.get("shrink_to_fit", False))
        for vc in range(start_col, end_col + 1):
            fill_result = set_table_visual_cell_solid_fill(package, table_index, task_row, vc, color)
            operations.append(fill_result)
            if text:
                cell_text = ""
                if text_at == "start" and vc == start_col:
                    cell_text = text
                elif text_at == "end" and vc == end_col:
                    cell_text = text
                elif text_at == "center" and vc == (start_col + end_col) // 2:
                    cell_text = text
                if cell_text:
                    operations.append(
                        editor.set_table_visual_cell_text(table_index, task_row, vc, cell_text, True)
                    )
                    if shrink:
                        operations.append(
                            shrink_table_visual_cell_text_to_fit(package, table_index, task_row, vc, cell_text)
                        )

    cleanup: dict[str, Any] | None = None
    if dry_run:
        validation = HwpxValidator.validate_entries(package.entries, str(output_path) + " (dry-run)")
        inspection = inspect_hwpx_package(package, str(input_path) + " (dry-run)", validation)
        cleanup = {"status": "PASS", "path": None, "removed": False, "reason": "in_memory_dry_run"}
    else:
        package.write_package(output_path)
        validation = HwpxValidator.validate_hwpx(output_path)
        inspection = inspect_hwpx(output_path)
    status = "PASS" if _validation_status(validation) == "PASS" and _operation_status(operations) == "PASS" else "FAIL"
    return {
        "mode": "hwpx_edit_apply",
        "status": status,
        "dry_run": dry_run,
        "input": str(input_path),
        "output": None if dry_run else str(output_path),
        "plan_validation": plan_validation,
        "operation_count": len(operations),
        "operations": operations,
        "validation": validation,
        "cleanup": cleanup,
        "inspection": inspection,
        "inspection_gate": inspection.get("gate"),
        "diff": diff_inspections(before_inspection, inspection),
        "summary": {
            "sections": inspection.get("entries", {}).get("section_count"),
            "tables": len(inspection.get("tables", [])),
            "placeholders_remaining": inspection.get("placeholders", {}).get("count"),
        },
    }


def write_inspection_html(report: dict[str, Any], output_path: Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for table in report.get("tables", []):
        for cell in table.get("cells", []):
            rows.append(
                "<tr>"
                f"<td>{html.escape(str(table.get('table_index')))}</td>"
                f"<td>{html.escape(str(cell.get('row')))}:{html.escape(str(cell.get('col')))}</td>"
                f"<td>{html.escape(str(cell.get('visual_row')))}:{html.escape(str(cell.get('visual_col')))}</td>"
                f"<td>{html.escape(str(cell.get('rowspan')))}x{html.escape(str(cell.get('colspan')))}</td>"
                f"<td>{html.escape(str(cell.get('fit_check', {}).get('status')))}</td>"
                f"<td>{html.escape(str(cell.get('preview')))}</td>"
                "</tr>"
            )
    section_rows = [
        "<tr>"
        f"<td>{html.escape(str(section.get('section_index')))}</td>"
        f"<td>{html.escape(str(section.get('paragraph_count')))}</td>"
        f"<td>{html.escape(str(section.get('table_count')))}</td>"
        f"<td>{html.escape(str(section.get('text_node_count')))}</td>"
        f"<td>{html.escape(str(section.get('preview')))}</td>"
        "</tr>"
        for section in report.get("sections", [])
    ]
    placeholder_rows = [
        f"<tr><td>{html.escape(str(token))}</td><td>{html.escape(str(count))}</td></tr>"
        for token, count in sorted((report.get("placeholders", {}).get("tokens") or {}).items())
    ]
    html_text = f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <title>HWPX Edit Inspection</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; color: #202124; }}
    h1, h2 {{ margin: 0 0 12px; }}
    section {{ margin: 22px 0; }}
    table {{ border-collapse: collapse; width: 100%; table-layout: fixed; }}
    th, td {{ border: 1px solid #d0d7de; padding: 6px 8px; vertical-align: top; word-break: break-word; }}
    th {{ background: #f6f8fa; text-align: left; }}
    .status {{ font-weight: 700; }}
  </style>
</head>
<body>
  <h1>HWPX Edit Inspection</h1>
  <p class="status">Gate: {html.escape(str(report.get('gate', {}).get('status')))} / Input: {html.escape(str(report.get('input')))}</p>
  <section>
    <h2>Sections</h2>
    <table><thead><tr><th>Section</th><th>Paragraphs</th><th>Tables</th><th>Text Nodes</th><th>Preview</th></tr></thead><tbody>{''.join(section_rows)}</tbody></table>
  </section>
  <section>
    <h2>Tables</h2>
    <table><thead><tr><th>Table</th><th>Physical</th><th>Visual</th><th>Span</th><th>Fit</th><th>Text</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
  </section>
  <section>
    <h2>Placeholders</h2>
    <table><thead><tr><th>Token</th><th>Count</th></tr></thead><tbody>{''.join(placeholder_rows)}</tbody></table>
  </section>
</body>
</html>
"""
    output_path.write_text(html_text, encoding="utf-8")
    return output_path


def write_batch_html(report: dict[str, Any], output_path: Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for item in report.get("items", []):
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(item.get('status')))}</td>"
            f"<td>{html.escape(str(item.get('input')))}</td>"
            f"<td>{html.escape(str(item.get('output')))}</td>"
            f"<td>{html.escape(str(item.get('operation_count')))}</td>"
            f"<td>{html.escape(str(item.get('cell_change_count')))}</td>"
            f"<td>{html.escape(str(item.get('section_change_count')))}</td>"
            f"<td>{html.escape(str(item.get('error', '')))}</td>"
            "</tr>"
        )
    html_text = f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <title>HWPX Batch Edit Report</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; color: #202124; }}
    table {{ border-collapse: collapse; width: 100%; table-layout: fixed; }}
    th, td {{ border: 1px solid #d0d7de; padding: 6px 8px; vertical-align: top; word-break: break-word; }}
    th {{ background: #f6f8fa; text-align: left; }}
  </style>
</head>
<body>
  <h1>HWPX Batch Edit Report</h1>
  <p>Status: {html.escape(str(report.get('status')))} / Files: {html.escape(str(report.get('target_count')))}</p>
  <table>
    <thead><tr><th>Status</th><th>Input</th><th>Output</th><th>Ops</th><th>Cell Changes</th><th>Section Changes</th><th>Error</th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
</body>
</html>
"""
    output_path.write_text(html_text, encoding="utf-8")
    return output_path


def batch_apply(input_dir: Path, output_dir: Path, plan: dict[str, Any], *, pattern: str = "*.hwpx", dry_run: bool = False, limit: int | None = None) -> dict[str, Any]:
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    targets = sorted(path for path in input_dir.rglob(pattern) if path.is_file())
    if limit is not None:
        targets = targets[: max(int(limit), 0)]
    items = []
    for target in targets:
        output_path = _rel_output_path(target, input_dir, output_dir)
        try:
            result = apply_edit_plan(target, output_path, plan, dry_run=dry_run)
            diff = result.get("diff", {})
            items.append(
                {
                    "status": result.get("status"),
                    "input": str(target),
                    "output": result.get("output"),
                    "operation_count": result.get("operation_count"),
                    "cell_change_count": diff.get("cell_change_count"),
                    "section_change_count": diff.get("section_change_count"),
                    "placeholder_delta": diff.get("placeholder_delta"),
                    "inspection_gate": result.get("inspection_gate", {}).get("status"),
                    "plan_validation": result.get("plan_validation", {}).get("status"),
                    "error": None,
                }
            )
        except Exception as exc:  # noqa: BLE001
            items.append(
                {
                    "status": "FAIL",
                    "input": str(target),
                    "output": str(output_path),
                    "operation_count": 0,
                    "cell_change_count": None,
                    "section_change_count": None,
                    "placeholder_delta": None,
                    "inspection_gate": None,
                    "plan_validation": None,
                    "error": str(exc),
                }
            )
    failed = [item for item in items if item.get("status") != "PASS"]
    return {
        "mode": "hwpx_edit_batch_apply",
        "status": "PASS" if targets and not failed else "FAIL",
        "input_dir": str(input_dir),
        "output_dir": None if dry_run else str(output_dir),
        "pattern": pattern,
        "dry_run": dry_run,
        "target_count": len(targets),
        "pass_count": len(items) - len(failed),
        "fail_count": len(failed),
        "items": items,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect and edit HWPX files with audit output")
    sub = parser.add_subparsers(dest="command", required=True)

    inspect_parser = sub.add_parser("inspect", help="Build an editable HWPX map")
    inspect_parser.add_argument("--input", required=True)
    inspect_parser.add_argument("--report-json")
    inspect_parser.add_argument("--report-html")

    create_parser = sub.add_parser("create", help="Create a new HWPX document from a JSON plan")
    create_parser.add_argument("--output", required=True)
    create_parser.add_argument("--plan-json", required=True)
    create_parser.add_argument("--report-json")
    create_parser.add_argument("--report-html")

    apply_parser = sub.add_parser("apply", help="Apply a JSON edit plan")
    apply_parser.add_argument("--input", required=True)
    apply_parser.add_argument("--output", required=True)
    apply_parser.add_argument("--plan-json", required=True)
    apply_parser.add_argument("--report-json")
    apply_parser.add_argument("--report-html")
    apply_parser.add_argument("--dry-run", action="store_true")

    validate_parser = sub.add_parser("validate-plan", help="Validate a JSON edit plan without editing")
    validate_parser.add_argument("--plan-json", required=True)
    validate_parser.add_argument("--base-dir")
    validate_parser.add_argument("--report-json")

    batch_parser = sub.add_parser("batch", help="Apply a JSON edit plan to a folder of HWPX files")
    batch_parser.add_argument("--input-dir", required=True)
    batch_parser.add_argument("--output-dir", required=True)
    batch_parser.add_argument("--plan-json", required=True)
    batch_parser.add_argument("--glob", default="*.hwpx")
    batch_parser.add_argument("--limit", type=int)
    batch_parser.add_argument("--dry-run", action="store_true")
    batch_parser.add_argument("--report-json")
    batch_parser.add_argument("--report-csv")
    batch_parser.add_argument("--report-html")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "inspect":
        report = inspect_hwpx(Path(args.input))
        if args.report_json:
            write_json(Path(args.report_json), report)
        if args.report_html:
            write_inspection_html(report, Path(args.report_html))
        if not args.report_json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report.get("gate", {}).get("status") == "PASS" else 1
    if args.command == "create":
        plan_path = Path(args.plan_json)
        report = create_hwpx_document(Path(args.output), read_json(plan_path), base_dir=plan_path.parent)
        if args.report_json:
            write_json(Path(args.report_json), report)
        if args.report_html and report.get("inspection"):
            write_inspection_html(report["inspection"], Path(args.report_html))
        if not args.report_json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report.get("status") == "PASS" else 1
    if args.command == "apply":
        report = apply_edit_plan(Path(args.input), Path(args.output), read_json(Path(args.plan_json)), dry_run=bool(args.dry_run))
        if args.report_json:
            write_json(Path(args.report_json), report)
        if args.report_html:
            write_inspection_html(report["inspection"], Path(args.report_html))
        if not args.report_json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report.get("status") == "PASS" else 1
    if args.command == "validate-plan":
        report = validate_edit_plan(read_json(Path(args.plan_json)), base_dir=Path(args.base_dir) if args.base_dir else Path(args.plan_json).parent)
        if args.report_json:
            write_json(Path(args.report_json), report)
        else:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report.get("status") == "PASS" else 1
    if args.command == "batch":
        report = batch_apply(
            Path(args.input_dir),
            Path(args.output_dir),
            read_json(Path(args.plan_json)),
            pattern=str(args.glob),
            dry_run=bool(args.dry_run),
            limit=args.limit,
        )
        if args.report_json:
            write_json(Path(args.report_json), report)
        if args.report_csv:
            write_csv(Path(args.report_csv), report.get("items", []))
        if args.report_html:
            write_batch_html(report, Path(args.report_html))
        if not args.report_json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report.get("status") == "PASS" else 1
    raise ValueError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
