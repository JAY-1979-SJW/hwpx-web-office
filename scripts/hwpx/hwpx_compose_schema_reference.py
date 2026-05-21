"""Generate a compact reference for supported HWPX compose job fields."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from hwpx_compose_examples import EXPERIMENTAL_EXAMPLE_PROFILES, STABLE_EXAMPLE_PROFILES
from hwpx_job_schema import SUPPORTED_TABLE_OPERATION_TYPES
from hwpx_schema_rules import OUTLINE_PRESETS, SUPPORTED_IMAGE_MODES
from hwpx_package import write_json


def compose_schema_reference() -> dict[str, Any]:
    """Return a machine-readable compose job field reference."""
    return {
        "status": "PASS",
        "top_level_fields": {
            "template": {"type": "string", "required": True, "description": "Input HWPX template path."},
            "output": {"type": "string", "required": False, "description": "Output HWPX path."},
            "mapping": {"type": "object", "required": False, "description": "Placeholder mapping."},
            "document_metadata": {"type": "object", "required": False, "description": "OPF package metadata."},
            "package_manifest": {"type": "object", "required": False, "description": "Repair content.hpf manifest/spine; enabled by default."},
            "preview_text": {"type": "object", "required": False, "description": "Generate Preview/PrvText.txt; enabled by default."},
            "style_definitions": {
                "type": "object",
                "required": False,
                "groups": ["char_styles", "para_styles", "border_fills", "list_styles"],
            },
            "paragraphs": {"type": "array", "required": False},
            "tables": {"type": "array", "required": False},
            "table_operations": {"type": "array", "required": False},
            "images": {"type": "array", "required": False},
            "page_layout": {"type": "object", "required": False},
            "page_layouts": {"type": "array", "required": False, "description": "Section-specific page layout objects."},
            "page_numbering": {"type": "object", "required": False},
            "page_numberings": {"type": "array", "required": False, "description": "Section-specific page numbering/header/footer objects."},
            "expected_values": {"type": "array", "required": False},
            "validate": {"type": "boolean", "required": False, "default": True},
        },
        "paragraph_style_fields": [
            "char_style",
            "para_style",
            "list_style",
            "list_level",
            "level",
            "charPrIDRef",
            "paraPrIDRef",
            "styleIDRef",
        ],
        "table_style_fields": [
            "width",
            "row_height",
            "row_heights",
            "repeat_header",
            "column_widths",
            "merged_cells",
            "border_fill_style",
            "header_border_fill_style",
            "body_border_fill_style",
            "cell_border_fill_style",
            "cell_border_fill_map",
            "cell_vertical_align",
            "cell_vertical_align_map",
            "cell_text_direction",
            "cell_text_direction_map",
            "cell_line_wrap",
            "cell_line_wrap_map",
            "cell_margin",
            "cell_margin_map",
        ],
        "supported_table_operations": sorted(SUPPORTED_TABLE_OPERATION_TYPES),
        "supported_image_modes": sorted(SUPPORTED_IMAGE_MODES),
        "supported_list_presets": sorted(OUTLINE_PRESETS),
        "page_layout_fields": {
            "section_index": "integer >= 0; defaults to 0",
            "orientation": ["portrait", "landscape"],
            "width": "positive integer HWPUNIT",
            "height": "positive integer HWPUNIT",
            "margins": ["left", "right", "top", "bottom", "header", "footer", "gutter"],
        },
        "document_metadata_fields": {
            "title": "string",
            "language": "string",
            "creator": "string",
            "subject": "string",
            "description": "string",
            "keywords": "string or list of strings",
            "created_date": "ISO-like string",
            "modified_date": "ISO-like string",
            "date": "string",
        },
        "package_manifest_fields": {
            "enabled": "boolean; default true",
        },
        "preview_text_fields": {
            "enabled": "boolean; default true",
            "include_metadata": "boolean; default true",
            "max_chars": "positive integer; default 4000",
        },
        "page_numbering_fields": {
            "section_index": "integer >= 0; defaults to 0",
            "start_page": "integer >= 1",
            "page_starts_on": ["BOTH", "EVEN", "ODD"],
            "page_number_mode": ["STATIC_TEXT", "NATIVE_DYNAMIC"],
            "hide_first_page_number": "boolean",
            "hide_first_header": "boolean",
            "hide_first_footer": "boolean",
            "visible_header": "boolean; generate visible header body text when true",
            "header_text": "string; {page} is replaced with start_page",
            "header_align": ["LEFT", "CENTER", "RIGHT"],
            "visible_footer": "boolean; generate visible footer body text when true",
            "footer_text": "string; {page} is replaced with start_page",
            "footer_align": ["LEFT", "CENTER", "RIGHT"],
            "page_number_format": ["DECIMAL"],
        },
        "image_fields": {
            "mode": sorted(SUPPORTED_IMAGE_MODES),
            "section_index": "integer >= 0; defaults to 0",
            "path": "PNG path for png_insert or visible_png_insert mode",
            "chart": "bar chart data object for chart_png or visible_chart_png mode",
            "chart_json": "external chart data JSON path for chart_png or visible_chart_png mode",
            "chart_output": "generated PNG output path for chart_png or visible_chart_png mode",
            "image_entry": "target BinData/*.png entry name",
            "manifest_id": "optional content.hpf manifest id",
            "picture_index": "visible_* modes only; index of an existing visible picture object to clone",
            "width": "positive integer HWPUNIT; default handled by style resolver",
            "height": "positive integer HWPUNIT; default handled by style resolver",
            "policy": "prefer visible_* modes when a template picture placeholder exists; use png_insert/chart_png only as explicit synthetic fallback",
        },
        "section_aware_fields": {
            "sections": "integer or object with count and clear_body",
            "paragraphs[].section_index": "place paragraph in target section",
            "tables[].section_index": "place generated table in target section",
            "images[].section_index": "place generated PNG picture in target section for synthetic modes",
            "page_layouts[].section_index": "apply page layout to target section",
            "page_numberings[].section_index": "apply page numbering/header/footer to target section",
        },
        "example_profiles": list(STABLE_EXAMPLE_PROFILES),
        "experimental_example_profiles": list(EXPERIMENTAL_EXAMPLE_PROFILES),
        "limits": [
            "visible header/footer text generation is supported with page_number_mode=STATIC_TEXT",
            "page_number_mode=NATIVE_DYNAMIC is accepted as an explicit unsupported request and fails with NATIVE_DYNAMIC_PAGE_FIELD_UNSUPPORTED until a cloneable page field sample is acquired",
            "HWP conversion is out of scope for direct writer",
            "complex native chart objects are out of scope; prefer visible_chart_png when a picture placeholder exists",
            "chart_png remains available only as an explicit experimental synthetic fallback example",
            "visible_png_insert and visible_chart_png require an existing visible picture object in the template and clone/rebind that object",
            "png_insert and chart_png generate synthetic picture XML and return EXPERIMENTAL_SYNTHETIC_PICTURE_XML until a cloneable picture template is available",
            "visual Hancom GUI verification is separate from ZIP/XML and Java parser validation",
        ],
    }


def markdown_reference(reference: dict[str, Any]) -> str:
    lines = [
        "# HWPX Compose Job Schema Reference",
        "",
        "## Top-Level Fields",
        "",
        "| Field | Type | Required | Notes |",
        "| --- | --- | --- | --- |",
    ]
    for name, spec in reference["top_level_fields"].items():
        required = "yes" if spec.get("required") else "no"
        notes = spec.get("description") or ", ".join(spec.get("groups", [])) or str(spec.get("default", ""))
        lines.append(f"| `{name}` | `{spec.get('type')}` | {required} | {notes} |")

    lines.extend(
        [
            "",
            "## Supported Values",
            "",
            f"- list presets: {', '.join(reference['supported_list_presets'])}",
            f"- table operations: {', '.join(reference['supported_table_operations'])}",
            f"- image modes: {', '.join(reference['supported_image_modes'])}",
            "",
            "## Paragraph Style Fields",
            "",
            ", ".join(f"`{field}`" for field in reference["paragraph_style_fields"]),
            "",
            "## Table Style Fields",
            "",
            ", ".join(f"`{field}`" for field in reference["table_style_fields"]),
            "",
            "## Page Layout",
            "",
            "- orientation: portrait, landscape",
            "- margins: left/right/top/bottom/header/footer/gutter",
            "",
            "## Document Metadata",
            "",
            ", ".join(f"`{field}`" for field in reference["document_metadata_fields"]),
            "",
            "## Package Manifest",
            "",
            "- enabled: boolean; when omitted, compose repairs content.hpf manifest/spine",
            "",
            "## Preview Text",
            "",
            "- enabled: boolean; when omitted, compose writes Preview/PrvText.txt",
            "- include_metadata: boolean",
            "- max_chars: positive integer",
            "",
            "## Page Numbering",
            "",
            "- start_page: integer >= 1",
            "- page_starts_on: BOTH, EVEN, ODD",
            "- page_number_mode: STATIC_TEXT, NATIVE_DYNAMIC",
            "- visible_header: generate visible header body text",
            "- header_text: string, with `{page}` replaced by start_page",
            "- header_align: LEFT, CENTER, RIGHT",
            "- visible_footer: generate visible footer body text",
            "- footer_text: string, with `{page}` replaced by start_page",
            "- footer_align: LEFT, CENTER, RIGHT",
            "",
            "## Images",
            "",
            f"- mode: {', '.join(sorted(SUPPORTED_IMAGE_MODES))}",
            "- section_index: target section index for generated picture XML modes",
            "- image_entry: target BinData/*.png path",
            "- picture_index: existing visible picture object index for visible_* modes",
            "- preferred: visible_png_insert / visible_chart_png when a template picture placeholder exists",
            "- fallback: png_insert / chart_png generates synthetic picture XML and should be chosen explicitly",
            "- chart_png generates a PNG image and inserts a generated picture object",
            "- visible_png_insert / visible_chart_png clone an existing picture object and rebind it to the new BinData image",
            "",
            "## Section-Aware Fields",
            "",
            "- sections: create/ensure multiple section XML entries",
            "- page_layouts/page_numberings: per-section layout and header/footer",
            "- paragraphs/tables/images: support section_index placement",
            "",
            "## Example Profiles",
            "",
            "- stable: " + ", ".join(f"`{name}`" for name in reference["example_profiles"]),
            "- experimental synthetic fallback: "
            + ", ".join(f"`{name}`" for name in reference["experimental_example_profiles"]),
            "",
            "## Limits",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in reference["limits"])
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate HWPX compose job schema reference")
    parser.add_argument("--out-json")
    parser.add_argument("--out-md")
    args = parser.parse_args()

    reference = compose_schema_reference()
    if args.out_json:
        write_json(Path(args.out_json), reference)
    if args.out_md:
        Path(args.out_md).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out_md).write_text(markdown_reference(reference), encoding="utf-8")
    print(json.dumps(reference, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
