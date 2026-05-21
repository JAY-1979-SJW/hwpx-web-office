#!/usr/bin/env python3
"""Select safety HWP samples and compare HWP/HWPX audit signals."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

THIS_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = THIS_DIR.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

import hwp_full_fidelity_converter as full
from hwp_hwp5proc_audit import run_hwp5proc_records
from hwp_to_hwpx_standalone import read_hwpx_table_grids, read_hwpx_section_text
from hwpx_package import HwpxValidator


def load_manifest(path: Path) -> list[dict[str, str]]:
    with Path(path).open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def choose_samples(rows: list[dict[str, str]], *, per_category: int, total_limit: int) -> list[dict[str, str]]:
    by_category: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_category[row.get("category", "UNKNOWN")].append(row)
    selected: list[dict[str, str]] = []
    seen: set[str] = set()
    for _category, items in sorted(by_category.items()):
        sorted_items = sorted(items, key=lambda row: int(row.get("size") or 0), reverse=True)
        candidates = sorted_items[: max(1, per_category)]
        median = sorted_items[len(sorted_items) // 2 : len(sorted_items) // 2 + 1]
        candidates += median
        candidates += sorted_items[-1:]
        for row in candidates:
            key = row.get("source_hwp") or row.get("sha256") or json.dumps(row, ensure_ascii=False)
            if key not in seen:
                selected.append(row)
                seen.add(key)
    if len(selected) < total_limit:
        for row in sorted(rows, key=lambda item: int(item.get("size") or 0), reverse=True):
            key = row.get("source_hwp") or row.get("sha256") or json.dumps(row, ensure_ascii=False)
            if key not in seen:
                selected.append(row)
                seen.add(key)
            if len(selected) >= total_limit:
                break
    return selected[:total_limit]


def converted_path_for(source_hwp: Path, source_root: Path, converted_root: Path) -> Path:
    return (converted_root / source_hwp.relative_to(source_root)).with_suffix(".hwpx")


def summarize_analysis(analysis: dict[str, Any]) -> dict[str, Any]:
    coverage = analysis.get("coverage") if isinstance(analysis.get("coverage"), dict) else {}
    record_audit = analysis.get("record_audit") if isinstance(analysis.get("record_audit"), dict) else {}
    return {
        "status": analysis.get("status"),
        "section_count": analysis.get("section_count"),
        "stream_count": analysis.get("stream_count"),
        "coverage_status": coverage.get("status"),
        "full_fidelity_ready": coverage.get("full_fidelity_ready"),
        "coverage_blockers": coverage.get("blockers", []),
        "record_coverage_ratio": coverage.get("record_coverage_ratio"),
        "decode_coverage_ratio": coverage.get("decode_coverage_ratio"),
        "next_decoder_targets": coverage.get("next_decoder_targets", [])[:12],
        "record_audit": {
            "record_count": record_audit.get("record_count"),
            "unknown_tag_count": record_audit.get("unknown_tag_count"),
            "risk_tag_count": record_audit.get("risk_tag_count"),
            "decoded_error_count": record_audit.get("decoded_error_count"),
        },
    }


def audit_pair(row: dict[str, str], *, source_root: Path, converted_root: Path, hwp5proc: Path | None) -> dict[str, Any]:
    source = Path(row["source_hwp"]).expanduser().resolve()
    hwpx = converted_path_for(source, source_root, converted_root)
    analysis = full.analyze_hwp(source, include_records=False)
    validation = HwpxValidator.validate_hwpx(hwpx)
    text_read = read_hwpx_section_text(hwpx)
    table_read = read_hwpx_table_grids(hwpx)
    hwp5 = run_hwp5proc_records(hwp5proc, source) if hwp5proc else {"status": "SKIPPED", "reason": "hwp5proc not provided"}
    summary = summarize_analysis(analysis)
    return {
        "safety_index": row.get("safety_index"),
        "category": row.get("category"),
        "original_name": row.get("original_name"),
        "size": int(row.get("size") or 0),
        "sha256": row.get("sha256"),
        "source_hwp": str(source),
        "converted_hwpx": str(hwpx),
        "analysis": summary,
        "hwpx_validation": {
            "exists": validation.get("exists"),
            "zip_ok": validation.get("zip_ok"),
            "xml_ok": validation.get("xml_ok"),
            "entry_count": validation.get("entry_count"),
            "section_entries": validation.get("section_entries"),
        },
        "hwpx_text": {
            "ok": text_read.get("ok"),
            "text_length": len(str(text_read.get("text") or "")),
            "section_entries": text_read.get("entries", []),
            "xml_errors": text_read.get("xml_errors", []),
        },
        "hwpx_tables": {
            "ok": table_read.get("ok"),
            "table_count": len(table_read.get("tables") or []),
            "shapes": [
                {"row_count": table.get("row_count"), "col_count": table.get("col_count")}
                for table in (table_read.get("tables") or [])[:20]
            ],
        },
        "hwp5proc": {
            "status": hwp5.get("status"),
            "returncode": hwp5.get("returncode"),
            "line_count": hwp5.get("line_count"),
            "stderr_tail": hwp5.get("stderr_tail"),
        },
        "hwp5proc_head": hwp5.get("head", []),
    }


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    blocker_counts: Counter[str] = Counter()
    decoder_target_counts: Counter[str] = Counter()
    category_counts: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        cat = str(row.get("category") or "UNKNOWN")
        category_counts[cat]["sample_count"] += 1
        analysis = row.get("analysis") if isinstance(row.get("analysis"), dict) else {}
        for blocker in analysis.get("coverage_blockers") or []:
            blocker_counts[str(blocker)] += 1
        for target in analysis.get("next_decoder_targets") or []:
            key = f"{target.get('tag_id')}:{target.get('tag_name')}"
            decoder_target_counts[key] += int(target.get("count") or 1)
    return {
        "sample_count": len(rows),
        "coverage_blockers": dict(blocker_counts.most_common()),
        "next_decoder_targets": [
            {"tag": key, "count": value}
            for key, value in decoder_target_counts.most_common(20)
        ],
        "categories": {cat: dict(counts) for cat, counts in sorted(category_counts.items())},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("tmp/hwp_safety_docs_20260513/safety_hwp_manifest.csv"))
    parser.add_argument("--source-root", type=Path, default=Path("tmp/hwp_safety_docs_20260513/source_hwp"))
    parser.add_argument("--converted-root", type=Path, default=Path("tmp/hwp_safety_docs_20260513/converted_hwpx"))
    parser.add_argument("--out-dir", type=Path, default=Path("tmp/hwp_safety_docs_20260513/sample_audit"))
    parser.add_argument("--hwp5proc", type=Path)
    parser.add_argument("--per-category", type=int, default=3)
    parser.add_argument("--total-limit", type=int, default=24)
    args = parser.parse_args()
    hwp5proc = args.hwp5proc
    if hwp5proc and not hwp5proc.exists():
        hwp5proc = None
    rows = choose_samples(load_manifest(args.manifest), per_category=args.per_category, total_limit=args.total_limit)
    source_root = args.source_root.expanduser().resolve()
    converted_root = args.converted_root.expanduser().resolve()
    audited = [audit_pair(row, source_root=source_root, converted_root=converted_root, hwp5proc=hwp5proc) for row in rows]
    report = {
        "status": "PASS",
        "manifest": str(args.manifest.expanduser().resolve()),
        "source_root": str(source_root),
        "converted_root": str(converted_root),
        "hwp5proc": str(hwp5proc) if hwp5proc else "",
        "aggregate": aggregate(audited),
        "samples": audited,
    }
    out_dir = args.out_dir.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "sample_audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    with (out_dir / "selected_samples.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        fieldnames = ["safety_index", "category", "original_name", "size", "sha256", "source_hwp", "converted_hwpx"]
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in audited:
            writer.writerow({key: row.get(key, "") for key in fieldnames})
    lines = ["# Safety HWP Sample Audit", "", f"- Samples: {len(audited)}", "", "## Top Decoder Targets"]
    for item in report["aggregate"]["next_decoder_targets"][:15]:
        lines.append(f"- {item['tag']}: {item['count']}")
    lines += ["", "## Coverage Blockers"]
    for key, value in report["aggregate"]["coverage_blockers"].items():
        lines.append(f"- {key}: {value}")
    (out_dir / "sample_audit.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "sample_count": len(audited), "out_dir": str(out_dir), "top_targets": report["aggregate"]["next_decoder_targets"][:5]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
