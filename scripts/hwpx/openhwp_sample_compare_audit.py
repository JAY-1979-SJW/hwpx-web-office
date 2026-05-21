#!/usr/bin/env python3
"""Compare current Python HWP extraction, generated HWPX, and OpenHWP parsing."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

THIS_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = THIS_DIR.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

from extract_hwp_body_fields import extract_hwp_text
from hwp_full_fidelity_converter import analyze_hwp
from hwp_to_hwpx_standalone import read_hwpx_section_text, read_hwpx_table_grids, roundtrip_text_gate
from hwpx_package import HwpxValidator
from openhwp_rust_probe import run_probe


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def normalize_compare_text(value: object) -> str:
    text = str(value or "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def fnv1a64_text(text: str) -> str:
    value = 0xCBF29CE484222325
    for byte in text.encode("utf-8"):
        value ^= byte
        value = (value * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    return f"{value:016x}"


def length_ratio(a: int, b: int) -> float:
    if max(a, b) == 0:
        return 1.0
    return round(min(a, b) / max(a, b), 6)


def token_overlap(left: str, right: str) -> float:
    left_tokens = {token for token in re.split(r"\W+", left) if len(token) >= 2}
    right_tokens = {token for token in re.split(r"\W+", right) if len(token) >= 2}
    if not left_tokens and not right_tokens:
        return 1.0
    if not left_tokens or not right_tokens:
        return 0.0
    return round(len(left_tokens & right_tokens) / len(left_tokens | right_tokens), 6)


def summarize_analysis(analysis: dict[str, Any]) -> dict[str, Any]:
    coverage = analysis.get("coverage") if isinstance(analysis.get("coverage"), dict) else {}
    record_audit = analysis.get("record_audit") if isinstance(analysis.get("record_audit"), dict) else {}
    return {
        "status": analysis.get("status"),
        "coverage_status": coverage.get("status"),
        "full_fidelity_ready": coverage.get("full_fidelity_ready"),
        "record_coverage_ratio": coverage.get("record_coverage_ratio"),
        "decode_coverage_ratio": coverage.get("decode_coverage_ratio"),
        "coverage_blockers": coverage.get("blockers", []),
        "next_decoder_targets": coverage.get("next_decoder_targets", [])[:12],
        "record_audit": {
            "record_count": record_audit.get("record_count"),
            "unknown_tag_count": record_audit.get("unknown_tag_count"),
            "risk_tag_count": record_audit.get("risk_tag_count"),
            "decoded_error_count": record_audit.get("decoded_error_count"),
        },
    }


def compare_one(row: dict[str, str], *, openhwp_root: Path, openhwp_target_dir: Path | None = None, timeout_sec: int) -> dict[str, Any]:
    source = Path(row["source_hwp"]).expanduser().resolve()
    hwpx = Path(row["converted_hwpx"]).expanduser().resolve()
    py = extract_hwp_text(source)
    py_text = normalize_compare_text(py.get("text"))
    hwpx_text_read = read_hwpx_section_text(hwpx)
    hwpx_text = normalize_compare_text(hwpx_text_read.get("text"))
    table_read = read_hwpx_table_grids(hwpx)
    roundtrip = roundtrip_text_gate(py_text, hwpx)
    validation = HwpxValidator.validate_hwpx(hwpx)
    probe_kwargs: dict[str, Any] = {"openhwp_root": openhwp_root, "timeout_sec": timeout_sec}
    if openhwp_target_dir is not None:
        probe_kwargs["target_dir"] = openhwp_target_dir
    openhwp = run_probe(source, **probe_kwargs)
    openhwp_text_head = normalize_compare_text(openhwp.get("text_head"))
    openhwp_text_len = int(openhwp.get("text_length") or 0)
    analysis = analyze_hwp(source, include_records=False)
    py_len = len(py_text)
    hwpx_len = len(hwpx_text)
    openhwp_parse_ok = openhwp.get("status") == "PASS"
    py_hwpx_equal = fnv1a64_text(py_text) == fnv1a64_text(hwpx_text)
    openhwp_head_in_python = bool(openhwp_text_head and openhwp_text_head in py_text)
    return {
        "safety_index": row.get("safety_index"),
        "category": row.get("category"),
        "original_name": row.get("original_name"),
        "source_hwp": str(source),
        "converted_hwpx": str(hwpx),
        "size": int(row.get("size") or 0),
        "sha256": row.get("sha256"),
        "python_extract": {
            "ok": py.get("ok"),
            "error": py.get("error"),
            "section_count": len(py.get("sections") or []),
            "text_length": py_len,
            "text_fnv1a64": fnv1a64_text(py_text),
            "table_count": ((py.get("feature_inventory") or {}).get("table_count") if isinstance(py.get("feature_inventory"), dict) else None),
        },
        "hwpx_output": {
            "exists": validation.get("exists"),
            "zip_ok": validation.get("zip_ok"),
            "xml_ok": validation.get("xml_ok"),
            "text_ok": hwpx_text_read.get("ok"),
            "text_length": hwpx_len,
            "text_fnv1a64": fnv1a64_text(hwpx_text),
            "table_count": len(table_read.get("tables") or []),
        },
        "openhwp": {
            "status": openhwp.get("status"),
            "error": openhwp.get("error"),
            "message": openhwp.get("message"),
            "version": openhwp.get("version"),
            "section_count": openhwp.get("section_count"),
            "paragraph_count": openhwp.get("paragraph_count"),
            "text_length": openhwp_text_len,
            "text_line_count": openhwp.get("text_line_count"),
            "text_fnv1a64": openhwp.get("text_fnv1a64"),
            "text_head": openhwp.get("text_head"),
            "stderr_tail": openhwp.get("stderr_tail"),
        },
        "comparison": {
            "python_hwpx_text_equal": py_hwpx_equal,
            "python_hwpx_roundtrip_status": roundtrip.get("status"),
            "python_hwpx_roundtrip_missing_line_count": roundtrip.get("missing_line_count"),
            "python_hwpx_length_ratio": length_ratio(py_len, hwpx_len),
            "python_hwpx_token_overlap": token_overlap(py_text, hwpx_text),
            "openhwp_parse_ok": openhwp_parse_ok,
            "openhwp_python_length_ratio": length_ratio(openhwp_text_len, py_len),
            "openhwp_head_in_python_text": openhwp_head_in_python,
            "risk": "OPENHWP_TEXT_SHORTER" if openhwp_parse_ok and openhwp_text_len < max(20, py_len // 2) else "",
        },
        "analysis": summarize_analysis(analysis),
    }


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    blockers: Counter[str] = Counter()
    targets: Counter[str] = Counter()
    categories: Counter[str] = Counter()
    for row in rows:
        categories[str(row.get("category") or "UNKNOWN")] += 1
        analysis = row.get("analysis") if isinstance(row.get("analysis"), dict) else {}
        for blocker in analysis.get("coverage_blockers") or []:
            blockers[str(blocker)] += 1
        for target in analysis.get("next_decoder_targets") or []:
            targets[f"{target.get('tag_id')}:{target.get('tag_name')}"] += int(target.get("count") or 1)
    return {
        "sample_count": len(rows),
        "python_hwpx_text_equal_count": sum(1 for row in rows if (row.get("comparison") or {}).get("python_hwpx_text_equal")),
        "python_hwpx_roundtrip_pass_count": sum(1 for row in rows if (row.get("comparison") or {}).get("python_hwpx_roundtrip_status") == "PASS"),
        "openhwp_pass_count": sum(1 for row in rows if (row.get("openhwp") or {}).get("status") == "PASS"),
        "openhwp_fail_count": sum(1 for row in rows if (row.get("openhwp") or {}).get("status") != "PASS"),
        "openhwp_text_shorter_count": sum(1 for row in rows if (row.get("comparison") or {}).get("risk") == "OPENHWP_TEXT_SHORTER"),
        "coverage_blockers": dict(blockers.most_common()),
        "next_decoder_targets": [{"tag": key, "count": count} for key, count in targets.most_common(20)],
        "categories": dict(sorted(categories.items())),
    }


def write_outputs(report: dict[str, Any], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "openhwp_compare_audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    fieldnames = [
        "safety_index",
        "category",
        "original_name",
        "size",
        "python_text_length",
        "hwpx_text_length",
        "openhwp_status",
        "openhwp_text_length",
        "python_hwpx_text_equal",
        "python_hwpx_roundtrip_status",
        "openhwp_python_length_ratio",
        "risk",
    ]
    with (out_dir / "openhwp_compare_audit.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in report["samples"]:
            comparison = row.get("comparison") or {}
            writer.writerow(
                {
                    "safety_index": row.get("safety_index"),
                    "category": row.get("category"),
                    "original_name": row.get("original_name"),
                    "size": row.get("size"),
                    "python_text_length": (row.get("python_extract") or {}).get("text_length"),
                    "hwpx_text_length": (row.get("hwpx_output") or {}).get("text_length"),
                    "openhwp_status": (row.get("openhwp") or {}).get("status"),
                    "openhwp_text_length": (row.get("openhwp") or {}).get("text_length"),
                    "python_hwpx_text_equal": comparison.get("python_hwpx_text_equal"),
                    "python_hwpx_roundtrip_status": comparison.get("python_hwpx_roundtrip_status"),
                    "openhwp_python_length_ratio": comparison.get("openhwp_python_length_ratio"),
                    "risk": comparison.get("risk"),
                }
            )
    lines = ["# OpenHWP Sample Compare Audit", ""]
    agg = report["aggregate"]
    lines += [
        f"- Samples: {agg['sample_count']}",
        f"- Python/HWPX text equal: {agg['python_hwpx_text_equal_count']}",
        f"- Python/HWPX roundtrip pass: {agg['python_hwpx_roundtrip_pass_count']}",
        f"- OpenHWP pass: {agg['openhwp_pass_count']}",
        f"- OpenHWP fail: {agg['openhwp_fail_count']}",
        f"- OpenHWP shorter than Python extraction: {agg['openhwp_text_shorter_count']}",
        "",
        "## Next Decoder Targets",
    ]
    for item in agg["next_decoder_targets"][:15]:
        lines.append(f"- {item['tag']}: {item['count']}")
    lines += ["", "## Coverage Blockers"]
    for key, value in agg["coverage_blockers"].items():
        lines.append(f"- {key}: {value}")
    (out_dir / "openhwp_compare_audit.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=Path, default=Path("tmp/hwp_safety_docs_20260513/sample_audit/selected_samples.csv"))
    parser.add_argument("--openhwp-root", type=Path, default=Path("tmp/oss_openhwp"))
    parser.add_argument("--openhwp-target-dir", type=Path)
    parser.add_argument("--out-dir", type=Path, default=Path("tmp/hwp_safety_docs_20260513/openhwp_compare_audit"))
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--timeout-sec", type=int, default=180)
    args = parser.parse_args(argv)
    rows = load_rows(args.samples)
    if args.limit:
        rows = rows[: max(1, int(args.limit))]
    samples = [
        compare_one(row, openhwp_root=args.openhwp_root, openhwp_target_dir=args.openhwp_target_dir, timeout_sec=int(args.timeout_sec))
        for row in rows
    ]
    report = {
        "status": "PASS",
        "samples_csv": str(args.samples.expanduser().resolve()),
        "openhwp_root": str(args.openhwp_root.expanduser().resolve()),
        "aggregate": aggregate(samples),
        "samples": samples,
    }
    write_outputs(report, args.out_dir.expanduser().resolve())
    print(json.dumps({"status": "PASS", "out_dir": str(args.out_dir), "aggregate": report["aggregate"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
