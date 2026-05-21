"""Capability coverage gate for the HWPX direct writer toolchain.

This script is intentionally static and non-destructive. It checks the current
module/CLI surface against the implementation roadmap and writes a coverage
matrix that separates implemented, verified, partial, experimental, and pending
features.
"""

from __future__ import annotations

import argparse
import ast
import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


ROOT = Path.cwd()
HWPX_DIR = ROOT / "scripts" / "hwpx"


@dataclass(frozen=True)
class Capability:
    capability: str
    category: str
    priority: str
    status: str
    required_modules: tuple[str, ...]
    required_symbols: tuple[str, ...] = ()
    required_cli: tuple[str, ...] = ()
    verification: str = ""
    blocker: str = ""
    next_action: str = ""


CAPABILITIES: tuple[Capability, ...] = (
    Capability(
        "package_zip_xml_io",
        "package",
        "P0",
        "IMPLEMENTED_VERIFIED",
        ("hwpx_package.py", "hwpx_validation.py"),
        ("HwpxPackage", "validate_rendered"),
        ("validate", "audit"),
        "ZIP/XML validation and package audit are included in full-scenario.",
    ),
    Capability(
        "placeholder_text_replace",
        "text",
        "P0",
        "IMPLEMENTED_VERIFIED",
        ("hwpx_text_ops.py", "hwpx_template_render.py"),
        ("replace_placeholders", "render_one"),
        ("render",),
        "P0/P2 template replacement and validation PASS.",
    ),
    Capability(
        "paragraph_add",
        "text",
        "P0",
        "IMPLEMENTED_VERIFIED",
        ("hwpx_text_ops.py", "hwpx_template_engine.py"),
        ("append_generated_paragraph", "command_paragraph_add"),
        ("paragraph-add",),
        "Stable scenario and regression include generated paragraphs.",
    ),
    Capability(
        "table_create_and_basic_ops",
        "table",
        "P0",
        "IMPLEMENTED_VERIFIED",
        ("hwpx_table_ops.py", "hwpx_template_engine.py"),
        ("append_generated_table", "update_table_cells", "append_table_row", "delete_table_row"),
        ("table-create", "table-op"),
        "P2.5 table operations and Java roundtrip PASS.",
    ),
    Capability(
        "table_merge_and_cell_layout",
        "table",
        "P1",
        "IMPLEMENTED_VERIFIED",
        (
            "hwpx_table_merge_ops.py",
            "hwpx_table_cell_layout_ops.py",
            "hwpx_table_cell_address_style.py",
            "hwpx_table_dimension_style.py",
        ),
        ("merge_table_cells", "unmerge_table_cell", "set_cell_layout"),
        ("compose", "regression-suite"),
        "Covered by modular table ops and regression audit.",
    ),
    Capability(
        "style_definitions",
        "style",
        "P1",
        "IMPLEMENTED_VERIFIED",
        ("hwpx_border_fill_style.py", "hwpx_header_style.py", "hwpx_list_style_ops.py", "hwpx_style_ops.py"),
        ("apply_border_fill_definitions", "apply_header_style_definitions", "apply_list_style_definitions"),
        ("compose", "schema-reference"),
        "Schema reference and compose flow expose style definitions.",
    ),
    Capability(
        "metadata_manifest_preview",
        "package",
        "P1",
        "IMPLEMENTED_VERIFIED",
        ("hwpx_metadata_ops.py", "hwpx_manifest_ops.py", "hwpx_preview_ops.py"),
        ("apply_document_metadata", "repair_package_manifest", "build_preview_text"),
        ("compose",),
        "Package audit and full scenario include metadata/manifest/preview.",
    ),
    Capability(
        "section_page_layout",
        "layout",
        "P1",
        "IMPLEMENTED_VERIFIED",
        ("hwpx_section_ops.py", "hwpx_page_layout_ops.py", "hwpx_header_footer_ops.py"),
        ("ensure_section_count", "set_page_layout", "apply_page_numbering"),
        ("compose", "regression-suite"),
        "Multi-section and section layout regressions PASS.",
    ),
    Capability(
        "static_header_footer_page_numbering",
        "layout",
        "P1",
        "IMPLEMENTED_VERIFIED",
        ("hwpx_header_footer_ops.py",),
        ("apply_page_numbering",),
        ("compose",),
        "Static visible header/footer text is verified. Native dynamic fields remain pending.",
        next_action="Add native page-field clone support when a cloneable fixture exists.",
    ),
    Capability(
        "bindata_image_seed_replace",
        "image",
        "P1",
        "IMPLEMENTED_VERIFIED",
        ("hwpx_image_ops.py", "hwpx_writer_adapter.py"),
        ("add_bindata_image", "replace_image_by_entry", "list_images"),
        ("image-seed", "image-replace"),
        "P3 package image seed/replace PASS.",
    ),
    Capability(
        "visible_picture_clone_rebind",
        "image",
        "P1",
        "IMPLEMENTED_VERIFIED",
        ("hwpx_picture_ops.py", "hwpx_visible_image_ops.py", "hwpx_image_policy.py"),
        ("clone_picture_object", "insert_visible_image_from_template", "normalize_image_mode"),
        ("picture-inspect", "picture-clone-rebind", "visible-image-insert"),
        "Visible image clone path is stable when the template contains a visible picture object.",
        next_action="Replace bootstrap synthetic fixture with a committed visible-picture fixture.",
    ),
    Capability(
        "synthetic_picture_xml",
        "image",
        "P2",
        "EXPERIMENTAL",
        ("hwpx_visible_image_ops.py", "hwpx_image_policy.py"),
        ("insert_generated_png_picture",),
        ("png-insert",),
        "Explicit synthetic fallback only; stable examples exclude it by default.",
        blocker="Generated picture XML needs visual verification against Hancom.",
        next_action="Keep behind experimental mode until cloneable fixture coverage is enough.",
    ),
    Capability(
        "chart_png_as_image",
        "image",
        "P2",
        "IMPLEMENTED_VERIFIED",
        ("hwpx_chart_png.py", "hwpx_composer.py"),
        ("generate_bar_chart_png",),
        ("chart-png", "compose"),
        "Charts are generated as PNG images and inserted through image policy.",
        blocker="Native Hancom chart object is not implemented.",
    ),
    Capability(
        "java_parser_roundtrip_gate",
        "validation",
        "P0",
        "IMPLEMENTED_VERIFIED",
        ("hwpx_java_roundtrip.py", "hwpx_full_scenario.py"),
        ("run_java_roundtrip", "run_many_java_roundtrips", "run_full_scenario"),
        ("full-scenario",),
        "P52 full-scenario --java-roundtrip PASS, 9/9 parser roundtrip.",
    ),
    Capability(
        "python_facade_api",
        "api",
        "P1",
        "IMPLEMENTED_VERIFIED",
        ("hwpx_api.py", "hwpx_document_builder.py"),
        ("render_document", "compose_document", "document", "run_scenario"),
        (),
        "API smoke and builder flows are included in full-scenario.",
    ),
    Capability(
        "batch_render_and_examples",
        "api",
        "P1",
        "IMPLEMENTED_VERIFIED",
        ("hwpx_compose_examples.py", "hwpx_api.py"),
        ("write_example_jobs", "batch_compose_documents_from_files"),
        ("examples", "batch-render", "full-scenario"),
        "Stable examples and batch outputs PASS.",
    ),
    Capability(
        "native_chart_object",
        "advanced_object",
        "P3",
        "PENDING",
        (),
        (),
        (),
        "Currently represented as PNG, not native chart XML.",
        blocker="Need real native chart sample or official schema mapping.",
        next_action="Acquire chart-bearing HWPX fixture and catalog chart XML.",
    ),
    Capability(
        "field_form_controls",
        "field_form",
        "P3",
        "NOT_REQUIRED",
        (),
        (),
        (),
        "Field/nurimtle controls are out of scope for the current HWPX writer goal.",
        next_action="Do not prioritize unless a future document workflow explicitly requires fields.",
    ),
    Capability(
        "toc_index",
        "document_structure",
        "P4",
        "PENDING",
        (),
        (),
        (),
        "No TOC/index object generation yet.",
        blocker="Need TOC/index XML fixture.",
        next_action="Defer until heading/style model is stable.",
    ),
    Capability(
        "footnote_endnote",
        "document_structure",
        "P4",
        "PENDING",
        (),
        (),
        (),
        "Footnote/endnote section shape settings are bridged; note body object generation is still pending.",
        blocker="Need note body XML fixture.",
    ),
    Capability(
        "drawing_shapes",
        "advanced_object",
        "P4",
        "PENDING",
        (),
        (),
        (),
        "No arbitrary drawing/shape generation yet.",
        blocker="Need shape/control XML fixture and visual verification.",
    ),
    Capability(
        "browser_viewer",
        "viewer",
        "P5",
        "DEFERRED",
        (),
        (),
        (),
        "User explicitly deferred browser view work.",
        next_action="Resume only after writer/editor tool coverage is stronger.",
    ),
    Capability(
        "hwp_to_hwpx_conversion",
        "conversion",
        "P5",
        "BLOCKED_EXTERNAL",
        (),
        (),
        (),
        "HWP conversion is outside direct writer. Hancom official converter/Add-in or SDK remains separate.",
        blocker="Official converter Add-in/SDK not installed or not integrated.",
    ),
)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def _ast_symbols(path: Path) -> set[str]:
    if not path.exists() or path.suffix != ".py":
        return set()
    tree = ast.parse(path.read_text(encoding="utf-8"))
    symbols: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            symbols.add(node.name)
    return symbols


def _cli_commands() -> set[str]:
    path = HWPX_DIR / "hwpx_template_engine.py"
    commands: set[str] = set()
    if not path.exists():
        return commands
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr != "add_parser":
            continue
        if not node.args:
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            commands.add(first.value)
    return commands


def _module_index() -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for path in sorted(HWPX_DIR.glob("*.py")):
        symbols = sorted(_ast_symbols(path))
        index[path.name] = {
            "path": str(path),
            "exists": True,
            "symbol_count": len(symbols),
            "symbols": symbols,
        }
    return index


def _evaluate_capability(capability: Capability, modules: dict[str, dict[str, Any]], cli: set[str]) -> dict[str, Any]:
    missing_modules = [name for name in capability.required_modules if name not in modules]
    available_symbols = set()
    for name in capability.required_modules:
        available_symbols.update(modules.get(name, {}).get("symbols", []))
    missing_symbols = [name for name in capability.required_symbols if name not in available_symbols]
    missing_cli = [name for name in capability.required_cli if name not in cli]
    structural_ok = not missing_modules and not missing_symbols and not missing_cli
    effective_status = capability.status
    if capability.status == "IMPLEMENTED_VERIFIED" and not structural_ok:
        effective_status = "FAIL"
    elif capability.status in {"EXPERIMENTAL", "PENDING", "DEFERRED", "BLOCKED_EXTERNAL", "NOT_REQUIRED"}:
        effective_status = capability.status
    return {
        **asdict(capability),
        "required_modules": list(capability.required_modules),
        "required_symbols": list(capability.required_symbols),
        "required_cli": list(capability.required_cli),
        "missing_modules": missing_modules,
        "missing_symbols": missing_symbols,
        "missing_cli": missing_cli,
        "structural_ok": structural_ok,
        "effective_status": effective_status,
    }


def _overall_status(rows: list[dict[str, Any]]) -> str:
    if any(row["effective_status"] == "FAIL" and row["priority"] in {"P0", "P1"} for row in rows):
        return "FAIL"
    if any(row["effective_status"] in {"PENDING", "EXPERIMENTAL", "BLOCKED_EXTERNAL"} for row in rows):
        return "WARN"
    return "PASS"


def build_coverage_report() -> dict[str, Any]:
    modules = _module_index()
    cli = _cli_commands()
    rows = [_evaluate_capability(item, modules, cli) for item in CAPABILITIES]
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["effective_status"]] = counts.get(row["effective_status"], 0) + 1
    p0_p1 = [row for row in rows if row["priority"] in {"P0", "P1"}]
    implemented_verified = [row for row in rows if row["effective_status"] == "IMPLEMENTED_VERIFIED"]
    next_priorities = [
        row
        for row in rows
        if row["effective_status"] in {"PENDING", "EXPERIMENTAL", "BLOCKED_EXTERNAL"}
        and row["priority"] in {"P2", "P3", "P4", "P5"}
    ]
    return {
        "status": _overall_status(rows),
        "module_count": len(modules),
        "cli_commands": sorted(cli),
        "summary": {
            "capability_count": len(rows),
            "implemented_verified": len(implemented_verified),
            "p0_p1_count": len(p0_p1),
            "p0_p1_implemented_verified": sum(1 for row in p0_p1 if row["effective_status"] == "IMPLEMENTED_VERIFIED"),
            "status_counts": counts,
        },
        "capabilities": rows,
        "next_priorities": next_priorities,
    }


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "capability",
        "category",
        "priority",
        "effective_status",
        "status",
        "structural_ok",
        "missing_modules",
        "missing_symbols",
        "missing_cli",
        "verification",
        "blocker",
        "next_action",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: "|".join(str(item) for item in row.get(key, []))
                    if isinstance(row.get(key), list)
                    else row.get(key, "")
                    for key in fields
                }
            )


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# HWPX Direct Writer Capability Coverage",
        "",
        "## Summary",
        "",
        f"- status: {report['status']}",
        f"- module_count: {report['module_count']}",
        f"- capability_count: {report['summary']['capability_count']}",
        f"- implemented_verified: {report['summary']['implemented_verified']}",
        f"- P0/P1 implemented: {report['summary']['p0_p1_implemented_verified']}/{report['summary']['p0_p1_count']}",
        "",
        "## Capability Matrix",
        "",
        "| capability | priority | status | category | blocker | next_action |",
        "|---|---:|---|---|---|---|",
    ]
    for row in report["capabilities"]:
        lines.append(
            "| {capability} | {priority} | {status} | {category} | {blocker} | {next_action} |".format(
                capability=row["capability"],
                priority=row["priority"],
                status=row["effective_status"],
                category=row["category"],
                blocker=str(row.get("blocker", "")).replace("|", "/"),
                next_action=str(row.get("next_action", "")).replace("|", "/"),
            )
        )
    lines.extend(
        [
            "",
            "## Next Priorities",
            "",
        ]
    )
    for row in report["next_priorities"]:
        lines.append(f"- {row['priority']} {row['capability']}: {row.get('next_action') or row.get('blocker')}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build HWPX direct writer capability coverage matrix")
    parser.add_argument("--out-dir", default="tmp/hwpx_capability_coverage")
    parser.add_argument("--report-json")
    parser.add_argument("--report-csv")
    parser.add_argument("--report-md")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    report = build_coverage_report()
    json_path = Path(args.report_json) if args.report_json else out_dir / "capability_coverage.json"
    csv_path = Path(args.report_csv) if args.report_csv else out_dir / "capability_coverage.csv"
    md_path = Path(args.report_md) if args.report_md else out_dir / "capability_coverage.md"
    write_json(json_path, report)
    write_csv(csv_path, report["capabilities"])
    write_markdown(md_path, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] in {"PASS", "WARN"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
