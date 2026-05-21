#!/usr/bin/env python3
"""Batch wrapper for page-capped HWP to HWPX conversion."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from hwp_page_capped_convert import page_capped_convert  # noqa: E402


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def output_path_for(source: Path, input_dir: Path, output_dir: Path) -> Path:
    return (output_dir / source.relative_to(input_dir)).with_suffix(".hwpx")


def row_summary(result: dict[str, Any]) -> dict[str, Any]:
    attempts = result.get("attempts") if isinstance(result.get("attempts"), list) else []
    selected = next((row for row in attempts if row.get("variant") == result.get("selected_variant")), None)
    page_probe = selected.get("page_probe") if isinstance(selected, dict) and isinstance(selected.get("page_probe"), dict) else {}
    return {
        "status": result.get("status"),
        "source": result.get("source"),
        "output": result.get("output"),
        "target_pages": result.get("target_pages"),
        "selected_variant": result.get("selected_variant"),
        "accepted_variant": result.get("accepted_variant"),
        "hwpx_page_count": page_probe.get("page_count"),
        "overflow_pages": max(0, int(page_probe.get("page_count") or 0) - int(result.get("target_pages") or 0))
        if page_probe.get("page_count") is not None
        else None,
        "source_size": result.get("source_info", {}).get("size") if isinstance(result.get("source_info"), dict) else None,
        "output_size": result.get("output_info", {}).get("size") if isinstance(result.get("output_info"), dict) else None,
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8-sig")
        return
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def run_batch(
    input_dir: Path,
    output_dir: Path,
    report_json: Path,
    report_csv: Path,
    work_dir: Path,
    *,
    limit: int,
    pattern: str,
    resolution: int,
) -> dict[str, Any]:
    input_dir = input_dir.expanduser().resolve()
    output_dir = output_dir.expanduser().resolve()
    work_dir = work_dir.expanduser().resolve()
    targets = sorted(path for path in input_dir.rglob(pattern) if path.is_file())
    if limit > 0:
        targets = targets[:limit]
    results: list[dict[str, Any]] = []
    for index, source in enumerate(targets, 1):
        output = output_path_for(source, input_dir, output_dir)
        item_report = work_dir / f"item_{index:03d}" / "report.json"
        item_work = work_dir / f"item_{index:03d}" / "work"
        try:
            result = page_capped_convert(source, output, item_report, item_work, resolution=resolution)
        except Exception as exc:  # noqa: BLE001
            result = {
                "status": "ERROR",
                "source": str(source),
                "output": str(output),
                "error": repr(exc),
                "target_pages": None,
                "attempts": [],
            }
            item_report.parent.mkdir(parents=True, exist_ok=True)
            item_report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        result["index"] = index
        result["relative"] = str(source.relative_to(input_dir))
        result["item_report"] = str(item_report)
        results.append(result)
        write_csv(report_csv, [row_summary(row) for row in results])

    ok_count = sum(1 for row in results if row.get("status") == "PASS")
    fail_count = len(results) - ok_count
    report = {
        "status": "PASS" if results and fail_count == 0 else "PARTIAL",
        "mode": "page_capped_batch",
        "started_finished_at": utc_now(),
        "input_dir": str(input_dir),
        "output_dir": str(output_dir),
        "work_dir": str(work_dir),
        "pattern": pattern,
        "limit": limit,
        "target_count": len(targets),
        "ok_count": ok_count,
        "fail_count": fail_count,
        "resolution": resolution,
        "report_json": str(report_json),
        "report_csv": str(report_csv),
        "summary_rows": [row_summary(row) for row in results],
        "results": results,
    }
    report_json.parent.mkdir(parents=True, exist_ok=True)
    report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(report_csv, report["summary_rows"])
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_dir")
    parser.add_argument("output_dir")
    parser.add_argument("--report-json", default="tmp/hwp_page_capped_batch/report.json")
    parser.add_argument("--report-csv", default="tmp/hwp_page_capped_batch/summary.csv")
    parser.add_argument("--work-dir", default="tmp/hwp_page_capped_batch/work")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--pattern", default="*.hwp")
    parser.add_argument("--resolution", type=int, default=150)
    args = parser.parse_args()
    result = run_batch(
        Path(args.input_dir),
        Path(args.output_dir),
        Path(args.report_json),
        Path(args.report_csv),
        Path(args.work_dir),
        limit=args.limit,
        pattern=args.pattern,
        resolution=args.resolution,
    )
    print(json.dumps({k: v for k, v in result.items() if k != "results"}, ensure_ascii=False, indent=2))
    return 0 if result.get("status") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
