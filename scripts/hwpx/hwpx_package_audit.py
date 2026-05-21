"""Package completeness audit for generated HWPX artifacts.

This module is a quality gate above the focused writer modules. It does not
mutate packages. It inspects the ZIP/XML package, package manifest/spine,
document metadata, preview text, image entries, and expected text values.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from hwpx_image_ops import bindata_image_entries, image_inventory
from hwpx_manifest_ops import inspect_package_manifest
from hwpx_metadata_ops import CONTAINER_ENTRY, CONTENT_HPF_ENTRY, inspect_document_metadata
from hwpx_package import HwpxPackage, HwpxValidator, read_json, write_csv, write_json
from hwpx_page_layout_ops import inspect_page_layout
from hwpx_header_footer_ops import inspect_page_numbering
from hwpx_preview_ops import PREVIEW_TEXT_ENTRY, inspect_preview_text
from hwpx_section_ops import inspect_sections
from hwpx_validation import validate_rendered


def _load_expected_values(path: Path | None, inline_values: list[str] | None = None) -> list[str]:
    values = [str(value) for value in inline_values or []]
    if not path:
        return values
    data = read_json(path)
    if isinstance(data, list):
        values.extend(str(value) for value in data)
    elif isinstance(data, dict):
        expected = data.get("expected_values", data.get("expected", []))
        if isinstance(expected, list):
            values.extend(str(value) for value in expected)
    return values


def _check(name: str, status: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"name": name, "status": status}
    if details:
        result.update(details)
    return result


def _status_from_checks(checks: list[dict[str, Any]]) -> str:
    if any(check.get("status") == "FAIL" for check in checks):
        return "FAIL"
    if any(check.get("status") == "WARN" for check in checks):
        return "WARN"
    return "PASS"


def _xml_text_by_entry(package: HwpxPackage) -> dict[str, str]:
    result = {}
    for entry in package.xml_entries():
        try:
            result[entry] = package.read_text(entry)
        except Exception:  # noqa: BLE001
            result[entry] = ""
    return result


def audit_hwpx_package(
    path: Path,
    *,
    expected_values: list[str] | None = None,
    strict: bool = False,
) -> dict[str, Any]:
    path = Path(path)
    expected_values = expected_values or []
    validation = validate_rendered(path, expected_values)
    base = HwpxValidator.validate_hwpx(path)
    checks: list[dict[str, Any]] = [
        _check("file_exists", "PASS" if base.get("exists") else "FAIL", {"size": base.get("size", 0)}),
        _check("zip_open", "PASS" if base.get("zip_ok") else "FAIL", {"entry_count": base.get("entry_count", 0)}),
        _check("xml_parse", "PASS" if base.get("xml_ok") else "FAIL", {"xml_errors": base.get("xml_errors", [])}),
        _check("section_entries", "PASS" if base.get("section_entries", 0) > 0 else "FAIL", {"count": base.get("section_entries", 0)}),
    ]
    if expected_values:
        checks.append(
            _check(
                "expected_values",
                "PASS" if not validation.get("missing_expected_values") else "FAIL",
                {
                    "expected_count": len(expected_values),
                    "found": validation.get("expected_values_found", []),
                    "missing": validation.get("missing_expected_values", []),
                },
            )
        )
    checks.append(
        _check(
            "placeholder_remaining",
            "PASS" if not validation.get("placeholder_remaining") else "WARN",
            {"placeholder_remaining": validation.get("placeholder_remaining")},
        )
    )

    if not base.get("zip_ok"):
        return {
            "file": str(path),
            "status": _status_from_checks(checks),
            "strict": strict,
            "validation": validation,
            "checks": checks,
        }

    package = HwpxPackage(path)
    entries = package.list_entries()
    normalized = {entry.replace("\\", "/").lower(): entry for entry in entries}
    content_exists = CONTENT_HPF_ENTRY.lower() in normalized
    container_exists = CONTAINER_ENTRY.lower() in normalized
    preview_exists = PREVIEW_TEXT_ENTRY.lower() in normalized

    manifest = inspect_package_manifest(package)
    metadata = inspect_document_metadata(package)
    preview = inspect_preview_text(package)
    sections = inspect_sections(package)
    section_count = len(package.section_entries())
    page_layouts = [inspect_page_layout(package, index) for index in range(section_count)]
    page_numberings = [inspect_page_numbering(package, index) for index in range(section_count)]
    images = image_inventory(package.entries, _xml_text_by_entry(package))
    bindata_images = bindata_image_entries(entries)

    required_status = "FAIL" if strict else "WARN"
    checks.extend(
        [
            _check("content_hpf", "PASS" if content_exists else required_status, {"entry": CONTENT_HPF_ENTRY}),
            _check("container_xml", "PASS" if container_exists else required_status, {"entry": CONTAINER_ENTRY}),
            _check("manifest_spine", "PASS" if manifest.get("status") == "PASS" else required_status, manifest),
            _check("metadata", "PASS" if metadata.get("status") == "PASS" else required_status, metadata),
            _check("preview_text", "PASS" if preview.get("status") == "PASS" else required_status, preview),
            _check("sections_inspect", "PASS" if sections.get("status") == "PASS" else "FAIL", sections),
        ]
    )

    return {
        "file": str(path),
        "status": _status_from_checks(checks),
        "strict": strict,
        "summary": {
            "size": base.get("size", 0),
            "entry_count": base.get("entry_count", 0),
            "xml_entries": base.get("xml_entries", 0),
            "section_entries": base.get("section_entries", 0),
            "content_hpf": content_exists,
            "container_xml": container_exists,
            "preview_text": preview_exists,
            "bindata_images": len(bindata_images),
            "image_reference_count": sum(item.get("reference_count", 0) for item in images),
        },
        "validation": validation,
        "manifest": manifest,
        "metadata": metadata,
        "preview": preview,
        "sections": sections,
        "page_layouts": page_layouts,
        "page_numberings": page_numberings,
        "images": images,
        "checks": checks,
    }


def audit_many(
    paths: list[Path],
    *,
    expected_values: list[str] | None = None,
    strict: bool = False,
) -> dict[str, Any]:
    results = [audit_hwpx_package(path, expected_values=expected_values, strict=strict) for path in paths]
    return {
        "status": "PASS" if results and all(item["status"] == "PASS" for item in results) else _status_from_checks(results),
        "file_count": len(results),
        "pass_count": sum(1 for item in results if item["status"] == "PASS"),
        "warn_count": sum(1 for item in results if item["status"] == "WARN"),
        "fail_count": sum(1 for item in results if item["status"] == "FAIL"),
        "results": results,
    }


def audit_csv_rows(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for result in results:
        summary = result.get("summary", {})
        validation = result.get("validation", {})
        rows.append(
            {
                "file": result.get("file"),
                "status": result.get("status"),
                "size": summary.get("size"),
                "entry_count": summary.get("entry_count"),
                "xml_entries": summary.get("xml_entries"),
                "section_entries": summary.get("section_entries"),
                "content_hpf": summary.get("content_hpf"),
                "container_xml": summary.get("container_xml"),
                "preview_text": summary.get("preview_text"),
                "bindata_images": summary.get("bindata_images"),
                "missing_expected_values": ";".join(validation.get("missing_expected_values", [])),
                "placeholder_remaining": validation.get("placeholder_remaining"),
            }
        )
    return rows


def command_audit(args: argparse.Namespace) -> int:
    expected = _load_expected_values(Path(args.expected_json) if args.expected_json else None, args.expected)
    report = audit_hwpx_package(Path(args.input), expected_values=expected, strict=bool(args.strict))
    if args.out_json:
        write_json(Path(args.out_json), report)
    if args.out_csv:
        write_csv(Path(args.out_csv), audit_csv_rows([report]))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] in {"PASS", "WARN"} else 1


def command_batch(args: argparse.Namespace) -> int:
    input_dir = Path(args.input_dir)
    paths = sorted(input_dir.glob(args.glob))
    if args.limit:
        paths = paths[: args.limit]
    expected = _load_expected_values(Path(args.expected_json) if args.expected_json else None, args.expected)
    report = audit_many(paths, expected_values=expected, strict=bool(args.strict))
    if args.out_json:
        write_json(Path(args.out_json), report)
    if args.out_csv:
        write_csv(Path(args.out_csv), audit_csv_rows(report["results"]))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] in {"PASS", "WARN"} else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit HWPX package completeness")
    sub = parser.add_subparsers(dest="command", required=True)

    audit = sub.add_parser("audit", help="Audit one HWPX package")
    audit.add_argument("--input", required=True)
    audit.add_argument("--expected", action="append", default=[])
    audit.add_argument("--expected-json")
    audit.add_argument("--strict", action="store_true")
    audit.add_argument("--out-json")
    audit.add_argument("--out-csv")
    audit.set_defaults(func=command_audit)

    batch = sub.add_parser("batch", help="Audit HWPX packages in a directory")
    batch.add_argument("--input-dir", required=True)
    batch.add_argument("--glob", default="*.hwpx")
    batch.add_argument("--limit", type=int)
    batch.add_argument("--expected", action="append", default=[])
    batch.add_argument("--expected-json")
    batch.add_argument("--strict", action="store_true")
    batch.add_argument("--out-json")
    batch.add_argument("--out-csv")
    batch.set_defaults(func=command_batch)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
