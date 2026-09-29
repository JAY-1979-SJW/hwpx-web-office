#!/usr/bin/env python3
"""Compare the existing standalone HWP converter with a reference provider.

This is a development aid for improving `hwp_to_hwpx_standalone.py`. It runs
the current converter and, when available, the hwpxjs adapter on the same HWP
input, then reports text/table/BinData/object deltas. It does not change the
default converter path.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

from hwp_to_hwpx_standalone import (  # ruff: ignore[module-import-not-at-top-of-file]
    convert_hwp_to_hwpx,
    normalize_roundtrip_text,
    read_hwpx_table_grids,
)
from hwpxjs_hwp_to_hwpx import convert_with_hwpxjs, discover_hwpxjs  # ruff: ignore[module-import-not-at-top-of-file]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def safe_report_stem(path: Path, index: int | None = None) -> str:
    prefix = f"{index:04d}_" if index is not None else ""
    digest = hashlib.sha1(str(path.resolve()).encode("utf-8", errors="ignore")).hexdigest()[:10]
    safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in path.stem).strip("._")
    return f"{prefix}{safe[:80] or 'input'}_{digest}"


def normalize_text_lines(text: str) -> list[str]:
    normalized = normalize_roundtrip_text(text)
    return [line.strip() for line in normalized.splitlines() if line.strip()]


def _count_element_tags(root, tag_counts: dict[str, int]) -> tuple[int, int, int, int]:
    paragraph, table, picture, image_ref = 0, 0, 0, 0
    for elem in root.iter():
        local = local_name(elem.tag)
        tag_counts[local] = tag_counts.get(local, 0) + 1
        if local == "p":
            paragraph += 1
        elif local == "tbl":
            table += 1
        elif local == "pic":
            picture += 1
        elif local == "img":
            image_ref += 1
    return paragraph, table, picture, image_ref


def summarize_hwpx(path: Path) -> dict[str, Any]:
    path = path.expanduser().resolve()
    if not path.exists():
        return {"status": "MISSING", "path": str(path), "error": "OUTPUT_NOT_FOUND"}

    entries: list[str] = []
    section_entries: list[str] = []
    bin_entries: list[str] = []
    xml_errors: list[dict[str, str]] = []
    text_parts: list[str] = []
    tag_counts: dict[str, int] = {}
    section_count = 0
    paragraph_count = 0
    table_count = 0
    picture_count = 0
    image_ref_count = 0

    try:
        with zipfile.ZipFile(path) as zf:
            entries = sorted(zf.namelist(), key=lambda item: item.lower())
            for name in entries:
                normalized = name.replace("\\", "/")
                lower = normalized.lower()
                if lower.startswith("bindata/") and not lower.endswith("/"):
                    bin_entries.append(name)
                if lower.startswith("contents/section") and lower.endswith(".xml"):
                    section_entries.append(name)

            for name in section_entries:
                try:
                    root = ET.fromstring(zf.read(name))
                except ET.ParseError as exc:
                    xml_errors.append({"entry": name, "error": str(exc)})
                    continue
                section_count += 1
                p, tbl, pic, img = _count_element_tags(root, tag_counts)
                paragraph_count += p
                table_count += tbl
                picture_count += pic
                image_ref_count += img
                text_parts.append("".join(text for text in root.itertext() if text))
    except zipfile.BadZipFile:
        return {"status": "FAIL", "path": str(path), "error": "HWPX_NOT_ZIP"}
    except OSError as exc:
        return {"status": "FAIL", "path": str(path), "error": f"HWPX_READ_FAILED: {exc}"}

    text = normalize_roundtrip_text("\n".join(text_parts))
    text_lines = normalize_text_lines(text)
    table_report = read_hwpx_table_grids(path)
    return {
        "status": "PASS" if not xml_errors else "WARN",
        "path": str(path),
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "entry_count": len(entries),
        "section_entries": section_entries,
        "section_count": section_count,
        "paragraph_count": paragraph_count,
        "text_length": len(text),
        "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "text_line_count": len(text_lines),
        "text_lines_head": text_lines[:20],
        "text_head": text[:500],
        "_text_for_compare": text,
        "bin_data_count": len(bin_entries),
        "bin_data_entries": bin_entries[:50],
        "table_count": table_count,
        "table_shapes": table_report.get("actual_shapes", []),
        "picture_count": picture_count,
        "image_ref_count": image_ref_count,
        "tag_counts": dict(sorted(tag_counts.items())),
        "xml_errors": xml_errors,
    }


def text_delta(standalone: dict[str, Any], reference: dict[str, Any]) -> dict[str, Any]:
    source_len = int(standalone.get("text_length") or 0)
    ref_len = int(reference.get("text_length") or 0)
    ratio = ref_len / source_len if source_len else 0.0
    line_delta = compare_text_lines(
        str(standalone.get("_text_for_compare") or ""),
        str(reference.get("_text_for_compare") or ""),
    )
    return {
        "standalone_text_length": source_len,
        "reference_text_length": ref_len,
        "reference_to_standalone_ratio": ratio,
        "longer_output": "reference"
        if ref_len > source_len
        else "standalone"
        if source_len > ref_len
        else "equal",
        "line_delta": line_delta,
    }


def compare_text_lines(
    standalone_text: str, reference_text: str, *, sample_limit: int = 20
) -> dict[str, Any]:
    standalone_lines = normalize_text_lines(standalone_text)
    reference_lines = normalize_text_lines(reference_text)
    standalone_counter = Counter(standalone_lines)
    reference_counter = Counter(reference_lines)
    missing_counter = reference_counter - standalone_counter
    extra_counter = standalone_counter - reference_counter
    return {
        "standalone_line_count": len(standalone_lines),
        "reference_line_count": len(reference_lines),
        "unique_standalone_line_count": len(standalone_counter),
        "unique_reference_line_count": len(reference_counter),
        "reference_lines_missing_in_standalone_count": sum(missing_counter.values()),
        "standalone_lines_missing_in_reference_count": sum(extra_counter.values()),
        "reference_lines_missing_in_standalone_samples": list(missing_counter.elements())[
            :sample_limit
        ],
        "standalone_lines_missing_in_reference_samples": list(extra_counter.elements())[
            :sample_limit
        ],
    }


def feature_delta(standalone: dict[str, Any], reference: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "table_count",
        "bin_data_count",
        "picture_count",
        "image_ref_count",
        "paragraph_count",
        "entry_count",
    ]
    deltas = {}
    for key in keys:
        left = int(standalone.get(key) or 0)
        right = int(reference.get(key) or 0)
        deltas[key] = {
            "standalone": left,
            "reference": right,
            "delta_reference_minus_standalone": right - left,
        }
    return deltas


def public_summary(summary: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(summary)
    cleaned.pop("_text_for_compare", None)
    return cleaned


def run_compare(
    input_path: Path,
    out_dir: Path,
    *,
    reference: str = "hwpxjs",
    decoded_style_bridge: bool = True,
    timeout_sec: int = 120,
) -> dict[str, Any]:
    input_path = input_path.expanduser().resolve()
    out_dir = out_dir.expanduser().resolve()
    standalone_dir = out_dir / "standalone"
    reference_dir = out_dir / reference
    standalone_dir.mkdir(parents=True, exist_ok=True)
    reference_dir.mkdir(parents=True, exist_ok=True)
    standalone_output = standalone_dir / f"{input_path.stem}.hwpx"
    reference_output = reference_dir / f"{input_path.stem}.hwpx"

    standalone_report = convert_hwp_to_hwpx(
        input_path,
        standalone_output,
        existing_policy="overwrite",
        fidelity_policy="audit",
        embed_original=True,
        decoded_style_bridge=decoded_style_bridge,
    )

    if reference != "hwpxjs":
        reference_report = {
            "status": "SKIPPED",
            "error": f"Unsupported reference provider: {reference}",
        }
    else:
        reference_report = convert_with_hwpxjs(
            input_path, reference_output, timeout_sec=timeout_sec
        )

    standalone_summary = summarize_hwpx(standalone_output)
    reference_summary = summarize_hwpx(reference_output)
    comparison = {
        "status": "PASS"
        if standalone_summary.get("status") in {"PASS", "WARN"}
        and reference_summary.get("status") in {"PASS", "WARN"}
        else "WARN",
        "text_delta": text_delta(standalone_summary, reference_summary),
        "feature_delta": feature_delta(standalone_summary, reference_summary),
        "reference_advantages": [],
        "standalone_advantages": [],
    }
    feature = comparison["feature_delta"]
    if feature["bin_data_count"]["delta_reference_minus_standalone"] > 0:
        comparison["reference_advantages"].append("reference_contains_more_bindata")
    if (
        feature["picture_count"]["delta_reference_minus_standalone"] > 0
        or feature["image_ref_count"]["delta_reference_minus_standalone"] > 0
    ):
        comparison["reference_advantages"].append("reference_contains_more_picture_objects")
    if feature["table_count"]["delta_reference_minus_standalone"] > 0:
        comparison["reference_advantages"].append("reference_contains_more_tables")
    if feature["entry_count"]["delta_reference_minus_standalone"] < 0:
        comparison["standalone_advantages"].append("standalone_contains_more_package_entries")
    if comparison["text_delta"]["line_delta"]["reference_lines_missing_in_standalone_count"] > 0:
        comparison["reference_advantages"].append("reference_contains_text_lines_not_in_standalone")

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "tool": "hwp_conversion_reference_compare",
        "input": str(input_path),
        "reference": reference,
        "decoded_style_bridge": decoded_style_bridge,
        "hwpxjs_discovery": discover_hwpxjs() if reference == "hwpxjs" else None,
        "outputs": {
            "standalone": str(standalone_output),
            "reference": str(reference_output),
        },
        "conversion_reports": {
            "standalone": standalone_report,
            "reference": reference_report,
        },
        "summaries": {
            "standalone": public_summary(standalone_summary),
            "reference": public_summary(reference_summary),
        },
        "comparison": comparison,
    }


def collect_inputs(input_path: Path, limit: int | None = None) -> list[Path]:
    input_path = input_path.expanduser().resolve()
    if input_path.is_file():
        candidates = [input_path]
    else:
        candidates = sorted(input_path.rglob("*.hwp"), key=lambda item: str(item).lower())
    if limit is not None and limit >= 0:
        candidates = candidates[:limit]
    return candidates


def run_batch_compare(
    input_path: Path,
    out_dir: Path,
    *,
    reference: str = "hwpxjs",
    decoded_style_bridge: bool = True,
    timeout_sec: int = 120,
    limit: int | None = None,
) -> dict[str, Any]:
    inputs = collect_inputs(input_path, limit=limit)
    reports: list[dict[str, Any]] = []
    for index, hwp_path in enumerate(inputs, start=1):
        item_dir = out_dir / safe_report_stem(hwp_path, index)
        reports.append(
            run_compare(
                hwp_path,
                item_dir,
                reference=reference,
                decoded_style_bridge=decoded_style_bridge,
                timeout_sec=timeout_sec,
            )
        )

    ranked = sorted(
        reports,
        key=lambda report: (
            int(
                report
                .get("comparison", {})
                .get("text_delta", {})
                .get("line_delta", {})
                .get("reference_lines_missing_in_standalone_count", 0)
            ),
            int(
                report
                .get("comparison", {})
                .get("feature_delta", {})
                .get("picture_count", {})
                .get("delta_reference_minus_standalone", 0)
            ),
            int(
                report
                .get("comparison", {})
                .get("feature_delta", {})
                .get("table_count", {})
                .get("delta_reference_minus_standalone", 0)
            ),
        ),
        reverse=True,
    )
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "tool": "hwp_conversion_reference_compare",
        "mode": "batch" if input_path.expanduser().resolve().is_dir() else "single",
        "input": str(input_path.expanduser().resolve()),
        "reference": reference,
        "decoded_style_bridge": decoded_style_bridge,
        "input_count": len(inputs),
        "reports": reports,
        "top_gaps": [
            {
                "input": report.get("input"),
                "status": report.get("comparison", {}).get("status"),
                "missing_reference_lines": report
                .get("comparison", {})
                .get("text_delta", {})
                .get("line_delta", {})
                .get("reference_lines_missing_in_standalone_count"),
                "text_ratio": report
                .get("comparison", {})
                .get("text_delta", {})
                .get("reference_to_standalone_ratio"),
                "reference_advantages": report.get("comparison", {}).get(
                    "reference_advantages", []
                ),
                "standalone_output": report.get("outputs", {}).get("standalone"),
                "reference_output": report.get("outputs", {}).get("reference"),
            }
            for report in ranked[:20]
        ],
    }


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    comparison = report.get("comparison", {})
    feature = comparison.get("feature_delta", {})
    lines = [
        "# HWP Conversion Reference Compare",
        "",
        f"- Input: `{report.get('input')}`",
        f"- Reference: `{report.get('reference')}`",
        f"- Status: `{comparison.get('status')}`",
        "",
        "## Text",
        "",
        f"- standalone length: {comparison.get('text_delta', {}).get('standalone_text_length')}",
        f"- reference length: {comparison.get('text_delta', {}).get('reference_text_length')}",
        f"- ratio: {comparison.get('text_delta', {}).get('reference_to_standalone_ratio')}",
        "",
        "## Text Gaps",
        "",
    ]
    line_delta = comparison.get("text_delta", {}).get("line_delta", {})
    lines.extend([
        f"- reference lines missing in standalone: {line_delta.get('reference_lines_missing_in_standalone_count')}",
        f"- standalone lines missing in reference: {line_delta.get('standalone_lines_missing_in_reference_count')}",
        "",
    ])
    missing_samples = line_delta.get("reference_lines_missing_in_standalone_samples") or []
    if missing_samples:
        lines.append("### Reference-only samples")
        lines.append("")
        lines.extend(f"- `{sample}`" for sample in missing_samples[:20])
        lines.append("")
    lines.extend([
        "## Features",
        "",
    ])
    for key, value in feature.items():
        lines.append(
            f"- {key}: standalone={value.get('standalone')} reference={value.get('reference')} delta={value.get('delta_reference_minus_standalone')}"
        )
    lines.extend([
        "",
        "## Outputs",
        "",
        f"- standalone: `{report.get('outputs', {}).get('standalone')}`",
        f"- reference: `{report.get('outputs', {}).get('reference')}`",
        "",
    ])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_batch_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# HWP Conversion Reference Batch Compare",
        "",
        f"- Input: `{report.get('input')}`",
        f"- Reference: `{report.get('reference')}`",
        f"- Input count: {report.get('input_count')}",
        "",
        "## Top Gaps",
        "",
    ]
    for item in report.get("top_gaps", []):
        lines.extend([
            f"### {item.get('input')}",
            "",
            f"- missing reference lines: {item.get('missing_reference_lines')}",
            f"- text ratio: {item.get('text_ratio')}",
            f"- reference advantages: {', '.join(item.get('reference_advantages') or [])}",
            f"- standalone: `{item.get('standalone_output')}`",
            f"- reference: `{item.get('reference_output')}`",
            "",
        ])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare standalone HWP conversion against a reference provider"
    )
    parser.add_argument("input", type=Path)
    parser.add_argument(
        "--out-dir", type=Path, default=Path("tmp/hwp_conversion_reference_compare")
    )
    parser.add_argument("--reference", choices=["hwpxjs"], default="hwpxjs")
    parser.add_argument("--no-decoded-style-bridge", action="store_true")
    parser.add_argument("--timeout-sec", type=int, default=120)
    parser.add_argument(
        "--limit", type=int, help="Maximum number of HWP files to compare when input is a directory"
    )
    parser.add_argument("--report-json", type=Path)
    parser.add_argument("--report-md", type=Path)
    args = parser.parse_args()

    input_path = args.input.expanduser().resolve()
    if input_path.is_dir():
        report = run_batch_compare(
            input_path,
            args.out_dir,
            reference=args.reference,
            decoded_style_bridge=not args.no_decoded_style_bridge,
            timeout_sec=int(args.timeout_sec),
            limit=args.limit,
        )
    else:
        report = run_compare(
            input_path,
            args.out_dir,
            reference=args.reference,
            decoded_style_bridge=not args.no_decoded_style_bridge,
            timeout_sec=int(args.timeout_sec),
        )
    report_json = args.report_json or args.out_dir / "comparison_report.json"
    report_md = args.report_md or args.out_dir / "comparison_report.md"
    report_json.parent.mkdir(parents=True, exist_ok=True)
    report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if input_path.is_dir():
        write_batch_markdown(report_md, report)
        status = "PASS" if report.get("input_count", 0) else "WARN"
    else:
        write_markdown(report_md, report)
        status = str(report["comparison"]["status"])
    print(
        json.dumps(
            {"status": status, "report_json": str(report_json), "report_md": str(report_md)},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
