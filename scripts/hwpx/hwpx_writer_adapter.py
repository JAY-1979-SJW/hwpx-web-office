"""Compatibility facade for direct HWPX package editing.

Feature implementations live in focused modules:

- hwpx_package.py: ZIP/XML package IO and validation
- hwpx_text_ops.py: placeholder and paragraph edits
- hwpx_table_ops.py: table inspection/mutation
- hwpx_image_ops.py: BinData image seed/replace
- hwpx_section_ops.py: section inspection/creation

This file keeps the historical HwpxEditor API and the small PoC CLI stable.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil

from hwpx_image_ops import (
    add_bindata_image_data,
    image_inventory,
    replace_image_data,
    xml_references_for_entry,
)
from hwpx_package import (
    HwpxPackage,
    HwpxValidator,
    decode_xml,
    is_section_entry,
    is_xml_entry,
    local_name,
    package_contains,
    package_has_placeholders,
    read_json,
    serialize_xml,
    text_nodes,
    write_csv,
    write_json,
)
from hwpx_picture_ops import clone_picture_object, picture_inventory, rebind_picture_object
from hwpx_section_ops import append_section, ensure_section_count, inspect_sections
from hwpx_table_ops import (
    append_generated_table,
    append_table_row,
    clone_table,
    delete_table_row,
    find_tables,
    get_table_cell_matrix,
    get_table_cells,
    replace_table_placeholder,
    set_table_cell_text,
    set_table_visual_cell_text,
    update_table_cell_matrix,
    update_table_cells,
)
from hwpx_table_merge_ops import merge_table_cells, unmerge_table_cell
from hwpx_table_cell_layout_ops import set_cell_layout
from hwpx_text_ops import append_generated_paragraph, append_paragraph, inject_placeholders, replace_placeholders
from hwpx_visible_image_ops import insert_generated_png_picture, insert_visible_image_from_template


DEFAULT_MAPPING = {
    "PROJECT_NAME": "테스트 소방공사",
    "BID_DEADLINE": "2026-05-15",
    "AWARD_METHOD": "제한최저가",
    "CLIENT_NAME": "테스트 발주처",
}


class HwpxEditor:
    """Thin adapter that delegates each feature to its module."""

    def __init__(self, package: HwpxPackage):
        self.package = package

    def inspect_sections(self) -> dict:
        return inspect_sections(self.package)

    def append_section(self, clone_from_index: int = 0, clear_body: bool = True) -> dict:
        return append_section(self.package, clone_from_index=clone_from_index, clear_body=clear_body)

    def ensure_section_count(self, count: int, clear_body: bool = True) -> dict:
        return ensure_section_count(self.package, count, clear_body=clear_body)

    def find_tables(self) -> list[dict]:
        return find_tables(self.package)

    def get_table_cells(self, table_index: int) -> dict:
        return get_table_cells(self.package, table_index)

    def get_table_cell_matrix(self, table_index: int) -> dict:
        return get_table_cell_matrix(self.package, table_index)

    def update_table_cells(self, table_index: int, values: list[str], clear_remaining: bool = False) -> dict:
        return update_table_cells(self.package, table_index, values, clear_remaining)

    def set_table_cell_text(
        self,
        table_index: int,
        row_index: int,
        col_index: int,
        value: str,
        clear_remaining: bool = True,
    ) -> dict:
        return set_table_cell_text(self.package, table_index, row_index, col_index, value, clear_remaining)

    def update_table_cell_matrix(self, table_index: int, updates: list[dict]) -> dict:
        return update_table_cell_matrix(self.package, table_index, updates)

    def set_table_visual_cell_text(
        self,
        table_index: int,
        visual_row: int,
        visual_col: int,
        value: str,
        clear_remaining: bool = True,
    ) -> dict:
        return set_table_visual_cell_text(self.package, table_index, visual_row, visual_col, value, clear_remaining)

    def append_table_row(self, table_index: int, row_values: list[str], clear_remaining: bool = True) -> dict:
        return append_table_row(self.package, table_index, row_values, clear_remaining)

    def append_generated_table(
        self,
        rows: list[list[str]],
        section_index: int = 0,
        style_refs: dict[str, str] | None = None,
    ) -> dict:
        return append_generated_table(self.package, rows, section_index, style_refs)

    def delete_table_row(self, table_index: int, row_index: int, protect_header: bool = True) -> dict:
        return delete_table_row(self.package, table_index, row_index, protect_header)

    def clone_table(self, table_index: int) -> dict:
        return clone_table(self.package, table_index)

    def merge_table_cells(
        self,
        table_index: int,
        row_index: int,
        col_index: int,
        row_span: int,
        col_span: int,
    ) -> dict:
        return merge_table_cells(self.package, table_index, row_index, col_index, row_span, col_span)

    def unmerge_table_cell(
        self,
        table_index: int,
        row_index: int,
        col_index: int,
        clear_generated_cells: bool = True,
    ) -> dict:
        return unmerge_table_cell(self.package, table_index, row_index, col_index, clear_generated_cells)

    def set_cell_layout(self, table_index: int, row_index: int, col_index: int, layout: dict) -> dict:
        return set_cell_layout(self.package, table_index, row_index, col_index, layout)

    def replace_table_placeholder(self, table_id: str | None, headers: list[str], rows: list[list[str]]) -> dict:
        return replace_table_placeholder(self.package, table_id, headers, rows)

    def _xml_text_by_entry(self) -> dict[str, str]:
        return {entry: self.package.read_text(entry) for entry in self.package.xml_entries()}

    def list_images(self) -> list[dict]:
        return image_inventory(self.package.entries, self._xml_text_by_entry())

    def replace_image(self, image_index: int, replacement_path: Path) -> dict:
        images = self.list_images()
        if image_index < 0 or image_index >= len(images):
            return {"status": "IMAGE_NOT_FOUND", "image_index": image_index, "image_count": len(images)}
        return self.replace_image_by_entry(images[image_index]["entry_name"], replacement_path)

    def replace_image_by_entry(self, entry_name: str, replacement_path: Path) -> dict:
        return replace_image_data(self.package.entries, self._xml_text_by_entry(), entry_name, replacement_path)

    def add_bindata_image(self, image_path: Path, entry_name: str = "BinData/image001.png") -> dict:
        return add_bindata_image_data(self.package.entries, image_path, entry_name)

    def xml_references_for_image(self, image_entry: str) -> dict:
        return xml_references_for_entry(image_entry, self._xml_text_by_entry())

    def list_picture_objects(self) -> dict:
        return picture_inventory(self.package)

    def rebind_picture_object(self, picture_index: int, new_entry: str, new_manifest_id: str | None = None) -> dict:
        return rebind_picture_object(self.package, picture_index, new_entry, new_manifest_id)

    def clone_picture_object(self, picture_index: int, new_entry: str, new_manifest_id: str | None = None) -> dict:
        return clone_picture_object(self.package, picture_index, new_entry, new_manifest_id)

    def insert_visible_image(
        self,
        image_path: Path,
        picture_index: int = 0,
        image_entry: str = "BinData/visible_image001.png",
        manifest_id: str | None = None,
    ) -> dict:
        return insert_visible_image_from_template(self.package, image_path, picture_index, image_entry, manifest_id)

    def insert_generated_png_picture(
        self,
        image_path: Path,
        image_entry: str = "BinData/generated_picture001.png",
        section_index: int = 0,
        width: int = 12000,
        height: int = 9000,
        manifest_id: str | None = None,
    ) -> dict:
        return insert_generated_png_picture(self.package, image_path, image_entry, section_index, width, height, manifest_id)

    def replace_placeholders(self, mapping: dict[str, str]) -> dict:
        return replace_placeholders(self.package, mapping)

    def inject_placeholders(self, placeholders: list[str]) -> dict:
        return inject_placeholders(self.package, placeholders)

    def append_paragraph(self, text: str, style: str | None = None) -> dict:
        return append_paragraph(self.package, text, style)

    def append_generated_paragraph(
        self,
        text: str,
        section_index: int = 0,
        style_refs: dict[str, str] | None = None,
    ) -> dict:
        return append_generated_paragraph(self.package, text, section_index, style_refs)

    def replace_first_image(self, image_path: Path) -> dict:
        result = self.replace_image(0, image_path)
        if result["status"] == "IMAGE_REPLACE_PASS":
            result["entry"] = result["entry_name"]
            return result
        if result["status"] == "REPLACEMENT_NOT_FOUND":
            return {"status": "IMAGE_INSERT_PENDING", "reason": "image_file_missing"}
        if result["status"] == "IMAGE_NOT_FOUND":
            return {"status": "IMAGE_INSERT_PENDING", "reason": "existing_image_bindata_not_found"}
        return result


def generate_chart_png(out_dir: Path) -> dict:
    chart_path = out_dir / "chart_sample.png"
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as exc:  # noqa: BLE001
        return {"status": "CHART_IMAGE_GENERATION_PENDING", "reason": repr(exc), "path": None}

    labels = ["fire_electric", "fire_mechanical", "common"]
    values = [40, 35, 25]
    fig, ax = plt.subplots(figsize=(4, 3))
    ax.bar(labels, values, color=["#3b82f6", "#16a34a", "#f59e0b"])
    ax.set_ylabel("share")
    ax.set_title("Sample work split")
    fig.tight_layout()
    fig.savefig(chart_path)
    plt.close(fig)
    return {"status": "PASS", "path": str(chart_path), "size": chart_path.stat().st_size}


def inspect_command(input_path: Path, out_path: Path | None) -> int:
    validation = HwpxValidator.validate_hwpx(input_path)
    if out_path:
        write_json(out_path, validation)
    else:
        print(json.dumps(validation, ensure_ascii=False, indent=2))
    return 0 if validation["zip_ok"] and validation["xml_ok"] else 1


def replace_command(input_path: Path, output_path: Path, mapping_path: Path) -> int:
    mapping = read_json(mapping_path)
    package = HwpxPackage(input_path)
    editor = HwpxEditor(package)
    result = editor.replace_placeholders(mapping)
    package.write_package(output_path)
    validation = HwpxValidator.validate_hwpx(output_path)
    print(json.dumps({"replace": result, "validation": validation}, ensure_ascii=False, indent=2))
    return 0 if validation["zip_ok"] and validation["xml_ok"] else 1


def self_test(sample: Path, out_dir: Path) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    summary: dict[str, object] = {"sample": str(sample), "out_dir": str(out_dir)}
    mapping_path = out_dir / "mapping.json"
    write_json(mapping_path, DEFAULT_MAPPING)

    seed_path = out_dir / "template_seed.hwpx"
    shutil.copyfile(sample, seed_path)
    package = HwpxPackage(seed_path)
    editor = HwpxEditor(package)
    if not package_has_placeholders(seed_path):
        inject_result = editor.inject_placeholders(list(DEFAULT_MAPPING))
        package.write_package(seed_path)
    else:
        inject_result = {"status": "EXISTING_PLACEHOLDERS_USED"}
    summary["template_seed"] = {
        "path": str(seed_path),
        "inject_result": inject_result,
        "validation": HwpxValidator.validate_hwpx(seed_path),
    }

    replaced_path = out_dir / "template_replaced.hwpx"
    package = HwpxPackage(seed_path)
    editor = HwpxEditor(package)
    replace_result = editor.replace_placeholders(DEFAULT_MAPPING)
    package.write_package(replaced_path)
    summary["template_replaced"] = {
        "path": str(replaced_path),
        "replace_result": replace_result,
        "validation": HwpxValidator.validate_hwpx(replaced_path),
        "contains_replaced_values": package_contains(replaced_path, list(DEFAULT_MAPPING.values())),
        "placeholder_remaining": package_has_placeholders(replaced_path),
    }

    paragraph_path = out_dir / "paragraph_added.hwpx"
    package = HwpxPackage(replaced_path)
    editor = HwpxEditor(package)
    paragraph_result = editor.append_paragraph("이 문단은 HWPX direct writer/editor PoC에서 추가되었습니다.")
    paragraph_validation = None
    if paragraph_result["status"] == "PASS":
        package.write_package(paragraph_path)
        paragraph_validation = HwpxValidator.validate_hwpx(paragraph_path)
    summary["paragraph_added"] = {
        "path": str(paragraph_path) if paragraph_validation else None,
        "result": paragraph_result,
        "validation": paragraph_validation,
    }

    table_path = out_dir / "table_updated.hwpx"
    package = HwpxPackage(paragraph_path if paragraph_validation else replaced_path)
    editor = HwpxEditor(package)
    table_result = editor.replace_table_placeholder(
        None,
        ["항목", "값"],
        [
            ["공사명", DEFAULT_MAPPING["PROJECT_NAME"]],
            ["입찰마감일", DEFAULT_MAPPING["BID_DEADLINE"]],
            ["낙찰방법", DEFAULT_MAPPING["AWARD_METHOD"]],
        ],
    )
    table_validation = None
    if table_result["status"] == "PASS":
        package.write_package(table_path)
        table_validation = HwpxValidator.validate_hwpx(table_path)
    summary["table_updated"] = {
        "path": str(table_path) if table_validation else None,
        "result": table_result,
        "validation": table_validation,
    }

    chart_result = generate_chart_png(out_dir)
    summary["chart_sample"] = chart_result

    image_path = out_dir / "image_replaced_or_inserted.hwpx"
    image_validation = None
    if chart_result.get("status") == "PASS":
        source = table_path if table_validation else paragraph_path if paragraph_validation else replaced_path
        package = HwpxPackage(source)
        editor = HwpxEditor(package)
        image_result = editor.replace_first_image(Path(str(chart_result["path"])))
        if image_result["status"] == "IMAGE_REPLACE_PASS":
            package.write_package(image_path)
            image_validation = HwpxValidator.validate_hwpx(image_path)
    else:
        image_result = {"status": "IMAGE_INSERT_PENDING", "reason": "chart_png_not_available"}
    summary["image_result"] = {
        "path": str(image_path) if image_validation else None,
        "result": image_result,
        "validation": image_validation,
    }

    summary["generated_basic"] = {
        "status": "NEW_DOCUMENT_GENERATION_PENDING",
        "reason": "template-first PoC only; full package synthesis deferred",
    }
    generated_outputs = [
        item["path"]
        for item in summary.values()
        if isinstance(item, dict) and item.get("path") and str(item["path"]).endswith(".hwpx")
    ]
    summary["roundtrip_validation"] = {
        "mode": "ZIP_XML_VALIDATION",
        "existing_parser": "NOT_EXECUTED",
        "outputs": [{"path": path, "validation": HwpxValidator.validate_hwpx(Path(path))} for path in generated_outputs],
    }
    write_json(out_dir / "self_test_summary.json", summary)

    rows = []
    for key in ("template_seed", "template_replaced", "paragraph_added", "table_updated", "image_result", "generated_basic"):
        item = summary.get(key)
        if not isinstance(item, dict):
            continue
        status = item.get("status") or item.get("result", {}).get("status") or item.get("replace_result", {}).get("status")
        rows.append({"artifact": key, "status": status, "path": item.get("path")})
    write_csv(out_dir / "self_test_summary.csv", rows)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    replaced_ok = summary["template_replaced"]["validation"]["zip_ok"] and summary["template_replaced"]["validation"]["xml_ok"]
    edited_ok = bool(paragraph_validation or table_validation)
    return 0 if replaced_ok and edited_ok else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Direct HWPX writer/editor PoC")
    sub = parser.add_subparsers(dest="command", required=True)

    inspect_parser = sub.add_parser("inspect", help="Validate a HWPX package")
    inspect_parser.add_argument("--input", required=True)
    inspect_parser.add_argument("--out")

    replace_parser = sub.add_parser("replace", help="Replace placeholders in XML entries")
    replace_parser.add_argument("--input", required=True)
    replace_parser.add_argument("--output", required=True)
    replace_parser.add_argument("--mapping-json", required=True)

    self_parser = sub.add_parser("self-test", help="Run template replacement and edit PoC")
    self_parser.add_argument("--sample", required=True)
    self_parser.add_argument("--out-dir", required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "inspect":
        return inspect_command(Path(args.input), Path(args.out) if args.out else None)
    if args.command == "replace":
        return replace_command(Path(args.input), Path(args.output), Path(args.mapping_json))
    if args.command == "self-test":
        return self_test(Path(args.sample), Path(args.out_dir))
    raise ValueError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
