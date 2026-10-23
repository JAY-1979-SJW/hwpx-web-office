#!/usr/bin/env python3
"""Independent HWP -> HWPX full-fidelity conversion workbench.

This tool is intentionally fail-closed. It does not use Hancom Office, COM,
GUI automation, SDKs, or official converter binaries. Until every required HWP
record family is decoded and mapped to HWPX, normal conversion mode reports the
missing coverage and refuses to write a file. Use --allow-partial only for an
explicit AI-readable derivative package with the original HWP embedded.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

THIS_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = THIS_DIR.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

from hwp_to_hwpx_standalone import convert_hwp_to_hwpx
import hwp_full_fidelity_audit as hwp_audit
import hwp_full_fidelity_analyzer as hwp_analyzer
import hwp_full_fidelity_architecture as hwp_architecture
import hwp_full_fidelity_coverage as hwp_coverage
import hwp_full_fidelity_header as hwp_header
import hwp_full_fidelity_layouts as hwp_layouts
import hwp_full_fidelity_package as hwp_package
import hwp_full_fidelity_section_updates as hwp_section_updates
import hwp_full_fidelity_security as hwp_security
from hwpx_package import HwpxValidator


ENGINE_VERSION = 1
REQUIRED_RECORD_FAMILIES = hwp_coverage.REQUIRED_RECORD_FAMILIES
FULL_SUPPORTED_TAGS = hwp_coverage.FULL_SUPPORTED_TAGS
DECODED_DOCINFO_TAGS = hwp_coverage.DECODED_DOCINFO_TAGS
DECODED_BODY_LAYOUT_TAGS = hwp_coverage.DECODED_BODY_LAYOUT_TAGS
DECODED_PAGE_LAYOUT_TAGS = hwp_coverage.DECODED_PAGE_LAYOUT_TAGS
DECODED_TABLE_LAYOUT_TAGS = hwp_coverage.DECODED_TABLE_LAYOUT_TAGS
DECODED_SHAPE_LAYOUT_TAGS = hwp_coverage.DECODED_SHAPE_LAYOUT_TAGS


_iso_now = hwp_analyzer._iso_now
_record_name = hwp_analyzer._record_name
_read_ole_records = hwp_analyzer._read_ole_records
analyze_hwp = hwp_analyzer.analyze_hwp
build_original_integrity = hwp_audit.build_original_integrity
build_identity_audit = hwp_audit.build_identity_audit
build_record_audit = hwp_audit.build_record_audit
build_source_manifest = hwp_audit.build_source_manifest
read_ole_metadata = hwp_audit.read_ole_metadata
architecture_catalog = hwp_architecture.architecture_catalog
route_new_code = hwp_architecture.route_new_code
module_architecture_gate = hwp_architecture.module_architecture_gate
security_catalog = hwp_security.security_catalog
security_gate = hwp_security.security_gate
build_decoded_docinfo = hwp_header.build_decoded_docinfo
build_decoded_header_xml = hwp_header.build_decoded_header_xml
decoded_header_summary = hwp_header.decoded_header_summary
build_fontface_mapping = hwp_header.build_fontface_mapping
build_list_style_mapping = hwp_header.build_list_style_mapping
build_body_layout = hwp_layouts.build_body_layout
build_page_layout = hwp_layouts.build_page_layout
build_shape_layout = hwp_layouts.build_shape_layout
build_equation_layout = hwp_layouts.build_equation_layout
build_table_layout = hwp_layouts.build_table_layout
apply_char_shape_segments_to_paragraph = hwp_section_updates.apply_char_shape_segments_to_paragraph
apply_line_segments_to_paragraph = hwp_section_updates.apply_line_segments_to_paragraph
build_body_style_section_updates = hwp_section_updates.build_body_style_section_updates
build_page_layout_section_updates = hwp_section_updates.build_page_layout_section_updates
build_table_layout_section_updates = hwp_section_updates.build_table_layout_section_updates
build_coverage = hwp_coverage.build_coverage
next_decoder_targets = hwp_coverage.next_decoder_targets
decoder_action = hwp_coverage.decoder_action
coverage_catalog = hwp_coverage.coverage_catalog
inject_analysis_entries = hwp_package.inject_analysis_entries


def convert_full(
    input_path: Path,
    output_path: Path,
    *,
    allow_partial: bool = False,
    report_json: Path | None = None,
) -> dict[str, Any]:
    analysis = analyze_hwp(input_path, include_records=False)
    if analysis.get("status") != "PASS":
        result = {
            "status": "FAIL",
            "mode": "full_fidelity",
            "input": str(Path(input_path).expanduser().resolve()),
            "output": str(Path(output_path).expanduser().resolve()),
            "analysis": analysis,
            "error": analysis.get("error") or "ANALYSIS_FAILED",
        }
        write_report(report_json, result)
        return result

    coverage = analysis.get("coverage") if isinstance(analysis.get("coverage"), dict) else {}
    if coverage.get("full_fidelity_ready") is not True and not allow_partial:
        result = {
            "status": "FAIL",
            "mode": "full_fidelity",
            "input": analysis.get("input"),
            "output": str(Path(output_path).expanduser().resolve()),
            "error": "FULL_FIDELITY_DECODERS_INCOMPLETE",
            "message": "The independent converter refuses to write HWPX until all required HWP record families are decoded.",
            "coverage": coverage,
            "analysis": analysis,
        }
        write_report(report_json, result)
        return result

    partial = convert_hwp_to_hwpx(
        Path(input_path),
        Path(output_path),
        fidelity_policy="audit",
        embed_original=True,
        existing_policy="rename",
    )
    if partial.get("status") != "PASS":
        result = {
            "status": "FAIL",
            "mode": "partial_ai_readable_derivative",
            "input": analysis.get("input"),
            "output": partial.get("output") or str(Path(output_path).expanduser().resolve()),
            "allow_partial": allow_partial,
            "error": partial.get("error") or "PARTIAL_DERIVATIVE_CONVERSION_FAILED",
            "coverage": coverage,
            "analysis": analysis,
            "conversion": partial,
        }
        write_report(report_json, result)
        return result
    resolved_output = Path(str(partial.get("output") or output_path)).expanduser().resolve()
    injected = inject_analysis_entries(resolved_output, analysis)
    validation = HwpxValidator.validate_hwpx(resolved_output)
    identity_audit = build_identity_audit(input_path, resolved_output, analysis=analysis)
    result = {
        "status": "WARN" if coverage.get("full_fidelity_ready") is not True else partial.get("status"),
        "mode": "partial_ai_readable_derivative" if coverage.get("full_fidelity_ready") is not True else "full_fidelity",
        "identity_status": identity_audit.get("status"),
        "identity_equal": identity_audit.get("identity_equal") is True,
        "input": analysis.get("input"),
        "output": partial.get("output") or str(Path(output_path).expanduser().resolve()),
        "allow_partial": allow_partial,
        "coverage": coverage,
        "analysis": analysis,
        "conversion": partial,
        "package_analysis_entries": injected,
        "validation": validation,
        "identity_audit": identity_audit,
        "warning": "Output is not full-fidelity; it is a text/table derivative with the original HWP embedded."
        if coverage.get("full_fidelity_ready") is not True
        else "",
    }
    write_report(report_json, result)
    return result


def write_report(path: Path | None, report: dict[str, Any]) -> None:
    if not path:
        return
    resolved = Path(path).expanduser().resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Independent fail-closed HWP -> HWPX full-fidelity converter workbench")
    sub = parser.add_subparsers(dest="command", required=True)

    analyze = sub.add_parser("analyze", help="Analyze HWP records and full-fidelity coverage")
    analyze.add_argument("input", type=Path)
    analyze.add_argument("--report-json", type=Path)
    analyze.add_argument("--include-records", action="store_true")

    convert = sub.add_parser("convert", help="Convert only when full-fidelity coverage is complete")
    convert.add_argument("input", type=Path)
    convert.add_argument("output", type=Path)
    convert.add_argument("--report-json", type=Path)
    convert.add_argument("--allow-partial", action="store_true", help="Write current AI-readable derivative with original HWP embedded")

    identity = sub.add_parser("identity-audit", help="Fail-closed full-fidelity identity audit for a HWP/HWPX pair")
    identity.add_argument("input", type=Path)
    identity.add_argument("output", type=Path)
    identity.add_argument("--report-json", type=Path)
    identity.add_argument("--include-records", action="store_true")

    coverage = sub.add_parser("coverage", help="Print the decoder coverage catalog")
    coverage.add_argument("--report-json", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "analyze":
        report = analyze_hwp(args.input, include_records=bool(args.include_records))
        write_report(args.report_json, report)
    elif args.command == "convert":
        report = convert_full(
            args.input,
            args.output,
            allow_partial=bool(args.allow_partial),
            report_json=args.report_json,
        )
    elif args.command == "identity-audit":
        analysis = analyze_hwp(args.input, include_records=bool(args.include_records))
        report = build_identity_audit(args.input, args.output, analysis=analysis)
        report["analysis"] = analysis
        write_report(args.report_json, report)
    else:
        report = {
            "status": "PASS",
            "tool": "hwp_full_fidelity_converter",
            "schema_version": ENGINE_VERSION,
            "generated_at": _iso_now(),
            "required_record_families": coverage_catalog(),
            "full_supported_tags": sorted(FULL_SUPPORTED_TAGS),
            "decoded_docinfo_tags": sorted(DECODED_DOCINFO_TAGS),
            "decoded_body_layout_tags": sorted(DECODED_BODY_LAYOUT_TAGS),
            "decoded_page_layout_tags": sorted(DECODED_PAGE_LAYOUT_TAGS),
            "decoded_table_layout_tags": sorted(DECODED_TABLE_LAYOUT_TAGS),
        }
        write_report(args.report_json, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("status") in {"PASS", "WARN"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
