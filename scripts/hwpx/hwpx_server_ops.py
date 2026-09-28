"""Server-side HWPX operations without a local UI server."""

from __future__ import annotations

from datetime import date, datetime
import json
from pathlib import Path
import re
import shutil
from typing import Any
from uuid import uuid4
import xml.etree.ElementTree as ET

from hancom_hwpx_schedule_diagram_suite import run_schedule_diagram_suite
from hancom_hwpx_work_schedule_demo import WorkItem, append_work_schedule
from hwp_full_fidelity_header import build_decoded_header_xml
from hwp_to_hwpx_standalone import convert_hwp_to_hwpx
from hwpx_border_fill_style import apply_border_fill_definitions
from hwpx_package import HwpxPackage, audit_hwpx_package_consistency, local_name
from hwpx_package_audit import audit_hwpx_package
from hwpx_manifest_ops import repair_package_manifest
from hwpx_spine_repair import repair_hwpx_spine
from hwpx_table_ops import append_generated_table, cell_elements, cell_visual_address, find_table, row_elements


HH_NS = "http://www.hancom.co.kr/hwpml/2011/head"
HC_NS = "http://www.hancom.co.kr/hwpml/2011/core"


def _qname(ns: str, tag: str) -> str:
    return f"{{{ns}}}{tag}"


def _safe_version_path(base_path: Path, label: str) -> Path:
    safe_stem = re.sub(r"[^A-Za-z0-9가-힣_-]+", "_", base_path.stem).strip("_")[:70] or "document"
    safe_label = re.sub(r"[^A-Za-z0-9_-]+", "_", label).strip("_") or "edit"
    return base_path.with_name(f"{safe_stem}_{safe_label}_{uuid4().hex[:12]}{base_path.suffix}")


def _parse_ymd(value: Any, fallback: date) -> date:
    if value in (None, ""):
        return fallback
    return datetime.strptime(str(value), "%Y-%m-%d").date()


def _ensure_border_fill_template(root: ET.Element) -> None:
    ref_list = next((elem for elem in root.iter() if local_name(elem.tag) == "refList"), None)
    if ref_list is None:
        ref_list = ET.SubElement(root, _qname(HH_NS, "refList"))
    border_fills = next((elem for elem in ref_list.iter() if local_name(elem.tag) == "borderFills"), None)
    if border_fills is None:
        border_fills = ET.SubElement(ref_list, _qname(HH_NS, "borderFills"), {"itemCnt": "0"})
    if any(local_name(child.tag) == "borderFill" for child in list(border_fills)):
        return
    border_fill = ET.SubElement(
        border_fills,
        _qname(HH_NS, "borderFill"),
        {"id": "1", "threeD": "0", "shadow": "0", "centerLine": "NONE", "breakCellSeparateLine": "0"},
    )
    for side in ("leftBorder", "rightBorder", "topBorder", "bottomBorder", "diagonal"):
        ET.SubElement(border_fill, _qname(HH_NS, side), {"type": "SOLID", "width": "0.12 mm", "color": "#000000"})
    fill_brush = ET.SubElement(border_fill, _qname(HC_NS, "fillBrush"))
    ET.SubElement(fill_brush, _qname(HC_NS, "winBrush"), {"faceColor": "#FFFFFF", "hatchColor": "#000000", "alpha": "0"})
    border_fills.attrib["itemCnt"] = "1"


def ensure_server_header(package: HwpxPackage) -> dict[str, Any]:
    created = False
    if "Contents/header.xml" not in package.entries:
        package.set_entry("Contents/header.xml", build_decoded_header_xml({"counts": {"border_fills": 2}}).encode("utf-8"))
        created = True
    root = package.read_xml("Contents/header.xml")
    _ensure_border_fill_template(root)
    package.write_xml("Contents/header.xml", root)
    return {"status": "PASS", "created_header": created, "manifest": repair_package_manifest(package)}


def repair_for_server(input_path: str | Path, output_path: str | Path | None = None, *, strict: bool = True) -> dict[str, Any]:
    source = Path(input_path)
    requested_output = Path(output_path) if output_path else _safe_version_path(source, "server_repair")
    in_place = source.resolve() == requested_output.resolve()
    output = _safe_version_path(source, "server_repair_tmp") if in_place else requested_output
    repair = repair_hwpx_spine(source, output)
    warnings = []
    if repair.get("status") == "PASS" and in_place:
        try:
            output.replace(requested_output)
            repair["output"] = str(requested_output)
            output = requested_output
        except OSError as exc:
            warnings.append(
                {
                    "type": "IN_PLACE_REPLACE_FAILED",
                    "message": str(exc),
                    "requested_output": str(requested_output),
                    "actual_output": str(output),
                }
            )
            repair["output"] = str(output)
    audit = audit_hwpx_package(output, strict=strict) if output.exists() else {"status": "FAIL", "error": "OUTPUT_NOT_FOUND"}
    status = "PASS" if repair.get("status") == "PASS" and audit.get("status") == "PASS" else "WARN" if audit.get("status") == "WARN" else "FAIL"
    if warnings and status == "PASS":
        status = "WARN"
    return {"status": status, "input": str(source), "output": str(output), "requested_output": str(requested_output), "warnings": warnings, "repair": repair, "audit": audit}


def convert_hwp_for_server(
    input_path: str | Path,
    output_path: str | Path,
    *,
    decoded_style_bridge: bool = False,
    strict_quality: bool = False,
    fidelity_policy: str = "audit",
) -> dict[str, Any]:
    report = convert_hwp_to_hwpx(
        Path(input_path),
        Path(output_path),
        existing_policy="overwrite",
        fidelity_policy=fidelity_policy,
        embed_original=True,
        decoded_style_bridge=decoded_style_bridge,
        strict_quality=strict_quality,
    )
    audit = audit_hwpx_package(Path(output_path), strict=False) if Path(output_path).exists() else {"status": "FAIL"}
    return {"status": "PASS" if report.get("status") == "PASS" and audit.get("status") in {"PASS", "WARN"} else "FAIL", "conversion": report, "audit": audit}


def insert_table_for_server(
    input_path: str | Path,
    output_path: str | Path,
    rows: list[list[Any]],
    *,
    section_index: int = 0,
    style_refs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source = Path(input_path)
    output = Path(output_path)
    shutil.copy2(source, output)
    package = HwpxPackage(output)
    normalized_rows = [["" if cell is None else str(cell) for cell in row] for row in rows]
    result = append_generated_table(package, normalized_rows, section_index=section_index, style_refs=style_refs)
    package.write_package(output)
    repair = repair_for_server(output, output, strict=False)
    return {"status": "PASS" if result.get("status") == "GENERATED_TABLE_APPEND_PASS" and repair.get("status") in {"PASS", "WARN"} else "FAIL", "output": str(repair.get("output") or output), "insert": result, "repair": repair}


def fill_cells_for_server(
    input_path: str | Path,
    output_path: str | Path,
    *,
    table_index: int,
    cells: list[dict[str, Any]],
    color: str = "#FFE699",
    border_color: str = "#808080",
    border_width: str = "0.12 mm",
) -> dict[str, Any]:
    if not re.match(r"^#[0-9A-Fa-f]{6}$", color):
        raise ValueError("color must be #RRGGBB")
    if not re.match(r"^#[0-9A-Fa-f]{6}$", border_color):
        raise ValueError("border_color must be #RRGGBB")
    source = Path(input_path)
    output = Path(output_path)
    shutil.copy2(source, output)
    package = HwpxPackage(output)
    header = ensure_server_header(package)
    style_name = f"server_fill_{color.strip('#').lower()}_{uuid4().hex[:8]}"
    style = apply_border_fill_definitions(
        package,
        {"border_fills": {style_name: {"fill_color": color, "border_color": border_color, "border_width": border_width}}},
    )
    fill_id = style.get("border_fills", {}).get(style_name)
    found = find_table(package, table_index)
    if not fill_id or found is None:
        return {"status": "FAIL", "output": str(output), "header": header, "style": style, "error": "STYLE_OR_TABLE_NOT_FOUND"}
    entry, root, table = found
    rows = row_elements(table)
    updated = 0
    for spec in cells:
        target: ET.Element | None = None
        if spec.get("visual_row") is not None or spec.get("visual_col") is not None:
            vrow = int(spec.get("visual_row", spec.get("row", -1)))
            vcol = int(spec.get("visual_col", spec.get("col", -1)))
            for row_index, row in enumerate(rows):
                for col_index, cell in enumerate(cell_elements(row)):
                    addr = cell_visual_address(row_index, col_index, cell)
                    if addr["row"] == vrow and addr["col"] == vcol:
                        target = cell
                        break
                if target is not None:
                    break
        else:
            row_index = int(spec.get("row", -1))
            col_index = int(spec.get("col", -1))
            if 0 <= row_index < len(rows):
                row_cells = cell_elements(rows[row_index])
                if 0 <= col_index < len(row_cells):
                    target = row_cells[col_index]
        if target is not None:
            target.attrib["borderFillIDRef"] = str(fill_id)
            updated += 1
    package.write_xml(entry, root)
    package.write_package(output)
    repair = repair_for_server(output, output, strict=False)
    return {"status": "PASS" if updated == len(cells) and repair.get("status") in {"PASS", "WARN"} else "WARN", "output": str(repair.get("output") or output), "updated_count": updated, "requested_count": len(cells), "fill_id": fill_id, "header": header, "style": style, "repair": repair}


def _work_items(items: list[dict[str, Any]] | None) -> list[WorkItem]:
    if not items:
        return [
            WorkItem("Preparation", date(2026, 5, 1), date(2026, 5, 5), 100),
            WorkItem("Foundation", date(2026, 5, 6), date(2026, 5, 14), 70),
            WorkItem("Installation", date(2026, 5, 15), date(2026, 5, 26), 35),
            WorkItem("Inspection", date(2026, 5, 27), date(2026, 5, 31), 0),
        ]
    result = []
    for item in items:
        start = _parse_ymd(item.get("start"), date(2026, 5, 1))
        end = _parse_ymd(item.get("end"), start)
        result.append(WorkItem(str(item.get("name", "Work")), start, end, max(0, min(100, int(item.get("progress", 0))))))
    return result


def insert_schedule_for_server(input_path: str | Path, output_path: str | Path, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    start = _parse_ymd(payload.get("daily_start"), date(2026, 5, 1))
    report = append_work_schedule(
        Path(input_path),
        Path(output_path),
        work_items=_work_items(payload.get("items")),
        daily_start=start,
        daily_days=max(1, min(366, int(payload.get("daily_days", 31)))),
        month_count=max(1, min(24, int(payload.get("month_count", 3)))),
        title=str(payload.get("title", "Work Schedule")),
        append_to_existing_section=bool(payload.get("append_to_existing_section", True)),
        insert_at_start=bool(payload.get("insert_at_start", False)),
    )
    repair = repair_for_server(output_path, output_path, strict=False)
    return {"status": "PASS" if report.get("status") == "PASS" and repair.get("status") in {"PASS", "WARN"} else "FAIL", "output": str(repair.get("output") or output_path), "schedule": report, "repair": repair}


def insert_schedule_graph_for_server(input_path: str | Path, output_path: str | Path, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    report = run_schedule_diagram_suite(
        Path(input_path),
        Path(output_path),
        daily_start=str(payload.get("daily_start", "2026-05-01")),
        daily_days=max(1, min(366, int(payload.get("daily_days", 31)))),
        month_count=max(1, min(24, int(payload.get("month_count", 3)))),
        insert_at_start=bool(payload.get("insert_at_start", True)),
        title=str(payload.get("title", "Schedule Graph")),
    )
    repair = repair_for_server(output_path, output_path, strict=False)
    return {"status": "PASS" if report.get("status") == "PASS" and repair.get("status") in {"PASS", "WARN"} else "FAIL", "output": str(repair.get("output") or output_path), "graph": report, "repair": repair}


def run_manifest_audit(input_path: str, report_json_path: str | None) -> dict[str, Any]:
    import zipfile
    path = Path(input_path)
    if not path.exists():
        result: dict[str, Any] = {"status": "FAIL", "errors": [{"code": "INPUT_FILE_NOT_FOUND"}], "warnings": [], "operations": [{"status": "MANIFEST_FILE_NOT_FOUND"}]}
        if report_json_path:
            Path(report_json_path).write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        return result
    try:
        with zipfile.ZipFile(path) as zf:
            consistency = audit_hwpx_package_consistency(zf)
    except zipfile.BadZipFile:
        consistency = {"errors": [{"code": "BAD_ZIP"}], "warnings": []}
    errors = consistency.get("errors", [])
    warnings = consistency.get("warnings", [])
    status = "PASS" if not errors else "FAIL"
    operations = [{"status": e["code"]} for e in errors] if errors else [{"status": "MANIFEST_CONSISTENCY_PASS"}]
    result = {"status": status, "errors": errors, "warnings": warnings, "operations": operations}
    if report_json_path:
        Path(report_json_path).write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    return result


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["repair", "convert", "insert-table", "fill-cells", "schedule", "schedule-graph", "manifest-audit"])
    parser.add_argument("--input", required=True)
    parser.add_argument("--output")
    parser.add_argument("--payload-json")
    parser.add_argument("--report-json")
    parser.add_argument("--decoded-style-bridge", action="store_true")
    args = parser.parse_args()

    if args.operation == "manifest-audit":
        report = run_manifest_audit(args.input, args.report_json)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report.get("status") in {"PASS", "WARN"} else 1

    if not args.output:
        parser.error("--output is required for this operation")
    payload = json.loads(Path(args.payload_json).read_text(encoding="utf-8-sig")) if args.payload_json else {}
    if args.operation == "repair":
        report = repair_for_server(args.input, args.output)
    elif args.operation == "convert":
        report = convert_hwp_for_server(args.input, args.output, decoded_style_bridge=bool(args.decoded_style_bridge))
    elif args.operation == "insert-table":
        report = insert_table_for_server(args.input, args.output, payload.get("rows", []), section_index=int(payload.get("section_index", 0)))
    elif args.operation == "fill-cells":
        report = fill_cells_for_server(args.input, args.output, table_index=int(payload.get("table", 0)), cells=payload.get("cells", []), color=str(payload.get("color", "#FFE699")))
    elif args.operation == "schedule":
        report = insert_schedule_for_server(args.input, args.output, payload)
    else:
        report = insert_schedule_graph_for_server(args.input, args.output, payload)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("status") in {"PASS", "WARN"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
