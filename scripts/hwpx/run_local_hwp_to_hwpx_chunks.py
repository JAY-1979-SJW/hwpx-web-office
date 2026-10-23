#!/usr/bin/env python3
"""Run local HWP -> HWPX conversion in resumable chunks."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
CONVERTER = REPO_ROOT / "scripts" / "hwpx" / "convert_local_hwp_inventory_to_hwpx.py"
DEFAULT_INVENTORY = (
    REPO_ROOT
    / "reports"
    / "runtime"
    / "local_hwp_hwpx_inventory_default"
    / "local_hwp_hwpx_inventory.csv"
)
DEFAULT_RUN_DIR = REPO_ROOT / "reports" / "runtime" / "local_hwp_inventory_to_hwpx_full_run"


def iso_now() -> str:
    return datetime.now(UTC).isoformat()


def count_hwp_rows(inventory_csv: Path, root_contains: str) -> int:
    root_filter = root_contains.lower()
    count = 0
    with inventory_csv.open("r", encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            ext = (row.get("extension") or row.get("Extension") or "").lower()
            root = row.get("root") or row.get("Root") or ""
            if ext == ".hwp" and (not root_filter or root_filter in root.lower()):
                count += 1
    return count


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def run_chunk(
    *,
    inventory_csv: Path,
    run_dir: Path,
    offset: int,
    limit: int,
    timeout_sec: int,
    root_contains: str,
) -> dict[str, Any]:
    chunk_name = f"chunk_{offset:06d}_{limit:03d}"
    report_json = run_dir / f"{chunk_name}.json"
    report_csv = run_dir / f"{chunk_name}.csv"
    audit_jsonl = run_dir / f"{chunk_name}.jsonl"
    cmd = [
        sys.executable,
        str(CONVERTER),
        "--inventory-csv",
        str(inventory_csv),
        "--offset",
        str(offset),
        "--limit",
        str(limit),
        "--no-skip-inventory-peer",
        "--timeout-sec",
        str(timeout_sec),
        "--save-strategy",
        "auto",
        "--existing-policy",
        "skip",
        "--engine",
        "persistent",
        "--report-json",
        str(report_json),
        "--report-csv",
        str(report_csv),
        "--audit-jsonl",
        str(audit_jsonl),
    ]
    if root_contains:
        cmd.extend(["--root-contains", root_contains])
    started = iso_now()
    proc = subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    finished = iso_now()
    report = read_json(report_json)
    return {
        "offset": offset,
        "limit": limit,
        "started_at": started,
        "finished_at": finished,
        "returncode": proc.returncode,
        "stdout_tail": (proc.stdout or "")[-2000:],
        "stderr_tail": (proc.stderr or "")[-2000:],
        "report_json": str(report_json),
        "report_csv": str(report_csv),
        "audit_jsonl": str(audit_jsonl),
        "status": report.get("status", "MISSING_REPORT"),
        "target_count": report.get("target_count", 0),
        "ok_count": report.get("ok_count", 0),
        "skip_count": report.get("skip_count", 0),
        "fail_count": report.get("fail_count", 0),
    }


def run_all(args: argparse.Namespace) -> dict[str, Any]:
    inventory_csv: Path = args.inventory_csv.resolve()
    run_dir: Path = args.run_dir.resolve()
    chunk_size = int(args.chunk_size)
    start_offset = int(args.start_offset)
    stop_offset = int(args.stop_offset)
    timeout_sec = int(args.timeout_sec)
    root_contains = str(args.root_contains)
    continue_on_fail = bool(args.continue_on_fail)
    ignore_state = bool(args.ignore_state)
    run_dir.mkdir(parents=True, exist_ok=True)
    state_path = run_dir / "full_run_state.json"
    summary_path = run_dir / "full_run_summary.json"
    log_path = run_dir / "full_run_chunks.jsonl"
    total_hwp = count_hwp_rows(inventory_csv, root_contains)
    final_offset = min(stop_offset, total_hwp) if stop_offset > 0 else total_hwp
    state = {} if ignore_state else read_json(state_path)
    offset = max(start_offset, int(state.get("next_offset", start_offset) or start_offset))
    started_at = state.get("started_at") or iso_now()
    totals = {
        "target_count": int(state.get("target_count", 0) or 0),
        "ok_count": int(state.get("ok_count", 0) or 0),
        "skip_count": int(state.get("skip_count", 0) or 0),
        "fail_count": int(state.get("fail_count", 0) or 0),
    }
    chunks: list[dict[str, Any]] = []

    while offset < final_offset:
        limit = min(chunk_size, final_offset - offset)
        chunk = run_chunk(
            inventory_csv=inventory_csv,
            run_dir=run_dir,
            offset=offset,
            limit=limit,
            timeout_sec=timeout_sec,
            root_contains=root_contains,
        )
        chunks.append(chunk)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(chunk, ensure_ascii=False, sort_keys=True) + "\n")
        for key in totals:
            totals[key] += int(chunk.get(key, 0) or 0)
        chunk_passed = chunk.get("status") == "PASS"
        if chunk_passed or continue_on_fail:
            offset += limit
        state = {
            "status": "RUNNING",
            "started_at": started_at,
            "updated_at": iso_now(),
            "inventory_csv": str(inventory_csv),
            "run_dir": str(run_dir),
            "chunk_size": chunk_size,
            "total_hwp": total_hwp,
            "start_offset": start_offset,
            "stop_offset": final_offset,
            "next_offset": offset,
            **totals,
            "last_chunk": chunk,
        }
        write_json(state_path, state)
        if not chunk_passed and not continue_on_fail:
            break

    status = "PASS" if offset >= final_offset and totals["fail_count"] == 0 else "FAIL"
    summary = {
        "status": status,
        "mode": "local_hwp_to_hwpx_full_chunk_run",
        "started_at": started_at,
        "finished_at": iso_now(),
        "inventory_csv": str(inventory_csv),
        "run_dir": str(run_dir),
        "chunk_size": chunk_size,
        "total_hwp": total_hwp,
        "start_offset": start_offset,
        "stop_offset": final_offset,
        "next_offset": offset,
        **totals,
        "state_json": str(state_path),
        "chunks_jsonl": str(log_path),
        "recent_chunks": chunks[-5:],
    }
    write_json(summary_path, summary)
    state = {**summary, "summary_json": str(summary_path)}
    write_json(state_path, state)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory-csv", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN_DIR)
    parser.add_argument("--chunk-size", type=int, default=200)
    parser.add_argument("--start-offset", type=int, default=0)
    parser.add_argument(
        "--stop-offset", type=int, default=0, help="Exclusive stop offset; 0 means all HWP rows."
    )
    parser.add_argument("--timeout-sec", type=int, default=150)
    parser.add_argument("--root-contains", default="")
    parser.add_argument("--continue-on-fail", action="store_true")
    parser.add_argument("--ignore-state", action="store_true")
    args = parser.parse_args()
    summary = run_all(args)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
