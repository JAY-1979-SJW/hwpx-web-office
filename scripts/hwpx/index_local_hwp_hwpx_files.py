#!/usr/bin/env python3
"""Index local HWP/HWPX files without opening the documents.

The scanner writes CSV/JSONL records as it finds files, so long runs can be
stopped without losing the inventory collected so far.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[2]
TARGET_SUFFIXES = {".hwp", ".hwpx"}
DEFAULT_SKIP_DIR_NAMES = {
    "$recycle.bin",
    ".cache",
    ".git",
    ".gradle",
    ".m2",
    ".pytest_cache",
    ".venv",
    "__pycache__",
    "appdata",
    "cache",
    "node_modules",
    "venv",
}


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_roots() -> list[Path]:
    home = Path.home()
    candidates = [
        home / "OneDrive",
        home / "Desktop",
        home / "Documents",
        home / "Downloads",
        Path(r"C:\tmp"),
        REPO_ROOT,
    ]
    roots: list[Path] = []
    seen: set[str] = set()
    for path in candidates:
        try:
            resolved = path.expanduser().resolve()
        except OSError:
            continue
        key = os.path.normcase(str(resolved))
        if key not in seen and resolved.exists():
            roots.append(resolved)
            seen.add(key)
    return minimize_roots(roots)


def minimize_roots(roots: Iterable[Path]) -> list[Path]:
    resolved_roots: list[Path] = []
    for root in roots:
        try:
            resolved = root.expanduser().resolve()
        except OSError:
            continue
        if resolved.exists():
            resolved_roots.append(resolved)
    minimized: list[Path] = []
    for root in sorted(resolved_roots, key=lambda p: len(str(p))):
        root_key = os.path.normcase(str(root))
        if any(root_key == os.path.normcase(str(existing)) or root_key.startswith(os.path.normcase(str(existing)) + os.sep) for existing in minimized):
            continue
        minimized.append(root)
    return minimized


def is_reparse_point(path: Path) -> bool:
    try:
        attrs = path.stat(follow_symlinks=False).st_file_attributes
    except (AttributeError, OSError):
        return False
    return bool(attrs & 0x400)


def should_skip_dir(path: Path, skip_names: set[str]) -> bool:
    if path.name.lower() in skip_names:
        return True
    return is_reparse_point(path)


def iter_target_files(
    roots: Iterable[Path],
    *,
    skip_names: set[str],
    max_seconds: int,
) -> Iterable[tuple[Path, Path]]:
    started = time.monotonic()
    stack: list[tuple[Path, Path]] = []
    for root in roots:
        try:
            resolved = root.expanduser().resolve()
        except OSError:
            continue
        if resolved.exists():
            stack.append((resolved, resolved))

    while stack:
        if max_seconds > 0 and time.monotonic() - started >= max_seconds:
            return
        root, current = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            child = Path(entry.path)
                            if not should_skip_dir(child, skip_names):
                                stack.append((root, child))
                        elif entry.is_file(follow_symlinks=False):
                            path = Path(entry.path)
                            if path.suffix.lower() in TARGET_SUFFIXES:
                                yield root, path
                    except OSError:
                        continue
        except OSError:
            continue


def file_record(root: Path, path: Path) -> dict[str, Any]:
    stat = path.stat()
    try:
        relative = str(path.relative_to(root))
    except ValueError:
        relative = path.name
    return {
        "root": str(root),
        "relative": relative,
        "path": str(path),
        "name": path.name,
        "extension": path.suffix.lower(),
        "size": stat.st_size,
        "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        "modified_at_utc": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
    }


def write_summary(path: Path, summary: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


def run_inventory(
    roots: list[Path],
    *,
    out_dir: Path,
    skip_names: set[str],
    max_seconds: int,
    progress_every: int,
) -> dict[str, Any]:
    started_at = iso_now()
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "local_hwp_hwpx_inventory.csv"
    jsonl_path = out_dir / "local_hwp_hwpx_inventory.jsonl"
    summary_path = out_dir / "local_hwp_hwpx_summary.json"
    fieldnames = ["root", "relative", "path", "name", "extension", "size", "modified_at", "modified_at_utc"]
    counts: Counter[str] = Counter()
    by_root: Counter[str] = Counter()
    total_size = 0
    seen: set[str] = set()

    with csv_path.open("w", encoding="utf-8-sig", newline="") as csv_fh, jsonl_path.open("w", encoding="utf-8") as jsonl_fh:
        writer = csv.DictWriter(csv_fh, fieldnames=fieldnames)
        writer.writeheader()
        for root, path in iter_target_files(roots, skip_names=skip_names, max_seconds=max_seconds):
            key = os.path.normcase(str(path))
            if key in seen:
                continue
            seen.add(key)
            try:
                record = file_record(root, path)
            except OSError:
                continue
            writer.writerow(record)
            jsonl_fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            counts[record["extension"]] += 1
            by_root[record["root"]] += 1
            total_size += int(record["size"])
            total = counts[".hwp"] + counts[".hwpx"]
            if progress_every > 0 and total % progress_every == 0:
                csv_fh.flush()
                jsonl_fh.flush()
                print(
                    json.dumps(
                        {"event": "progress", "total": total, "hwp": counts[".hwp"], "hwpx": counts[".hwpx"]},
                        ensure_ascii=False,
                    ),
                    flush=True,
                )

    summary = {
        "status": "PASS",
        "mode": "local_hwp_hwpx_inventory",
        "started_at": started_at,
        "finished_at": iso_now(),
        "roots": [str(root) for root in roots],
        "skip_dir_names": sorted(skip_names),
        "max_seconds": max_seconds,
        "total": counts[".hwp"] + counts[".hwpx"],
        "hwp": counts[".hwp"],
        "hwpx": counts[".hwpx"],
        "total_size": total_size,
        "by_root": [{"root": root, "count": count} for root, count in sorted(by_root.items())],
        "csv": str(csv_path),
        "jsonl": str(jsonl_path),
        "summary_json": str(summary_path),
    }
    write_summary(summary_path, summary)
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", action="append", type=Path, help="Root folder to scan. Can be repeated.")
    parser.add_argument("--out-dir", type=Path, default=REPO_ROOT / "reports" / "runtime" / "local_hwp_hwpx_inventory")
    parser.add_argument("--max-seconds", type=int, default=0, help="Stop after N seconds; 0 means no time limit.")
    parser.add_argument("--progress-every", type=int, default=100)
    parser.add_argument("--include-appdata", action="store_true", help="Do not skip AppData by default.")
    parser.add_argument("--skip-dir-name", action="append", default=[], help="Extra directory name to skip.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    roots = minimize_roots(args.root) if args.root else default_roots()
    skip_names = set(DEFAULT_SKIP_DIR_NAMES)
    if args.include_appdata:
        skip_names.discard("appdata")
    skip_names.update(str(name).lower() for name in args.skip_dir_name)
    summary = run_inventory(
        roots,
        out_dir=args.out_dir,
        skip_names=skip_names,
        max_seconds=int(args.max_seconds),
        progress_every=int(args.progress_every),
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
