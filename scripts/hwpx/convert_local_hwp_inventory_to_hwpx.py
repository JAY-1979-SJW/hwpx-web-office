#!/usr/bin/env python3
"""Convert HWP files listed in a local inventory CSV to HWPX via Hancom COM."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from hancom_hwp_to_hwpx_batch import HANCOM_32BIT_POWERSHELL
from hwp_native_com_batch import (
    DEFAULT_LOCK_FILE,
    DEFAULT_WORK_ROOT,
    BatchLock,
    convert_one_native,
    iso_now,
    write_csv_report,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INVENTORY = (
    REPO_ROOT
    / "reports"
    / "runtime"
    / "local_hwp_hwpx_inventory_default"
    / "local_hwp_hwpx_inventory.csv"
)
PERSISTENT_WORKER = REPO_ROOT / "scripts" / "hwp-worker" / "Convert-HwpToHwpx-PersistentBatch.ps1"


def safe_anchor(root: str) -> str:
    root = root.replace("\\", "/").strip("/")
    root = re.sub(r"[^A-Za-z0-9._가-힣-]+", "_", root)
    root = re.sub(r"_+", "_", root).strip("_")
    return root or "root"


def safe_filename(name: str, *, max_chars: int = 80) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", name)
    name = re.sub(r"_+", "_", name).strip(" ._")
    return (name or "document")[:max_chars]


def target_path_for(output_dir: Path, root: Path, relative: Path, source: Path) -> Path:
    target_root = output_dir / safe_anchor(str(root))
    candidate = (target_root / relative).with_suffix(".hwpx")
    if len(str(candidate)) < 240 and all(len(part) < 120 for part in candidate.parts):
        return candidate
    digest = hashlib.sha1(str(source).encode("utf-8", errors="replace")).hexdigest()[:16]
    name = safe_filename(source.with_suffix("").name, max_chars=70)
    return target_root / "_longpath" / f"{digest}_{name}.hwpx"


def read_inventory(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return [dict(row) for row in csv.DictReader(fh)]


def row_path(row: dict[str, str]) -> Path:
    return Path(row.get("path") or row.get("FullName") or row.get("fullName") or "")


def row_root(row: dict[str, str], path: Path) -> Path:
    root = row.get("root") or row.get("Root")
    if root:
        return Path(root)
    directory = row.get("DirectoryName") or row.get("directory")
    return Path(directory).parent if directory else path.parent


def row_relative(row: dict[str, str], root: Path, path: Path) -> Path:
    relative = row.get("relative") or row.get("Relative")
    if relative:
        return Path(relative)
    try:
        return path.relative_to(root)
    except ValueError:
        return Path(path.name)


def inventory_hwpx_peers(rows: list[dict[str, str]]) -> set[str]:
    peers: set[str] = set()
    for row in rows:
        path = row_path(row)
        if path.suffix.lower() != ".hwpx":
            continue
        peers.add(os.path.normcase(str(path.with_suffix(""))))
    return peers


def skipped_result(
    index: int, source: Path, root: Path, output: Path, reason: str, peer: Path | None = None
) -> dict[str, Any]:
    return {
        "status": "SKIP",
        "index": index,
        "input": str(source),
        "relative": str(row_relative({}, root, source)),
        "output": str(output),
        "copied": False,
        "skipped": True,
        "skip_reason": reason,
        "peer_hwpx": str(peer) if peer else "",
    }


def planned_result(index: int, source: Path, root: Path, output: Path) -> dict[str, Any]:
    return {
        "status": "PLAN",
        "index": index,
        "input": str(source),
        "relative": str(row_relative({}, root, source)),
        "output": str(output),
        "copied": False,
        "skipped": False,
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _stage_targets(
    targets: list[tuple[int, dict[str, str], Path, Path, Path]],
    batch_staging: Path,
    staged_output_dir: Path,
) -> tuple[
    list[dict[str, Any]],
    dict[str, tuple[int, dict[str, str], Path, Path, Path, Path]],
    list[dict[str, Any]],
]:
    manifest_items: list[dict[str, Any]] = []
    target_map: dict[str, tuple[int, dict[str, str], Path, Path, Path, Path]] = {}
    pre_results: list[dict[str, Any]] = []
    for local_index, row, source, root, target in targets:
        item_id = f"{local_index:06d}"
        staged_input = batch_staging / f"{item_id}.hwp"
        staged_output = staged_output_dir / f"{item_id}.hwpx"
        copy_error = ""
        for attempt in range(3):
            try:
                shutil.copy2(source, staged_input)
                copy_error = ""
                break
            except OSError as exc:
                copy_error = str(exc)
                time.sleep(2 + attempt)
        if copy_error:
            pre_results.append({
                "status": "FAIL",
                "index": local_index,
                "input": str(source),
                "relative": str(row_relative(row, root, source)),
                "output": str(target),
                "copied": False,
                "copy_error": copy_error,
                "conversion": {
                    "provider": "HANCOM_COM_32BIT_PERSISTENT_BATCH",
                    "ok": False,
                    "error_code": "STAGING_COPY_FAILED",
                    "error_message": copy_error,
                },
            })
            continue
        manifest_items.append({
            "itemId": item_id,
            "inputPath": str(staged_input),
            "outputPath": str(staged_output),
        })
        target_map[item_id] = (local_index, row, source, root, target, staged_output)
    return manifest_items, target_map, pre_results


def _run_worker_subprocess(
    manifest_path: Path,
    result_path: Path,
    diag_dir: Path,
    save_strategy: str,
    timeout_sec: int,
    targets: list[tuple[int, dict[str, str], Path, Path, Path]],
) -> tuple[subprocess.CompletedProcess | None, list[dict[str, Any]] | None]:
    strategy = "direct" if save_strategy == "auto" else save_strategy
    cmd = [
        str(HANCOM_32BIT_POWERSHELL),
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(PERSISTENT_WORKER),
        "-ManifestPath",
        str(manifest_path),
        "-ResultPath",
        str(result_path),
        "-DiagDir",
        str(diag_dir),
        "-SaveStrategy",
        strategy,
    ]
    subprocess_timeout = max(120, timeout_sec * max(1, len(targets)) + 90)
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=subprocess_timeout,
        )
    except subprocess.TimeoutExpired as exc:
        timeout_results = [
            {
                "status": "FAIL",
                "index": local_index,
                "input": str(source),
                "relative": str(row_relative(row, root, source)),
                "output": str(target),
                "copied": False,
                "error_code": "PERSISTENT_BATCH_TIMEOUT",
                "error_message": f"Persistent Hancom batch exceeded {subprocess_timeout}s",
                "stdout_tail": (exc.stdout if isinstance(exc.stdout, str) else "")[-1000:],
                "stderr_tail": (exc.stderr if isinstance(exc.stderr, str) else "")[-1000:],
            }
            for local_index, row, source, root, target in [
                (x[0], x[1], x[2], x[3], x[4]) for x in targets
            ]
        ]
        return None, timeout_results
    return proc, None


def _finalize_worker_results(
    pre_results: list[dict[str, Any]],
    target_map: dict[str, tuple[int, dict[str, str], Path, Path, Path, Path]],
    result_path: Path,
    proc: subprocess.CompletedProcess,
    batch_staging: Path,
) -> list[dict[str, Any]]:
    parsed: dict[str, Any] = {}
    if result_path.exists():
        try:
            parsed = json.loads(result_path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError:
            parsed = {}
    worker_results = parsed.get("results") if isinstance(parsed.get("results"), list) else []
    by_item_id = {
        str(item.get("itemId")): item for item in worker_results if isinstance(item, dict)
    }
    results: list[dict[str, Any]] = list(pre_results)
    for item_id, (local_index, row, source, root, target, staged_output) in target_map.items():
        worker = by_item_id.get(item_id, {})
        copied = False
        copy_error = ""
        if worker.get("ok") is True and staged_output.exists():
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(staged_output, target)
                copied = True
            except OSError as exc:
                copy_error = str(exc)
        status = "PASS" if copied and worker.get("ok") is True else "FAIL"
        results.append({
            "status": status,
            "index": local_index,
            "input": str(source),
            "relative": str(row_relative(row, root, source)),
            "staged_input": str(batch_staging / f"{item_id}.hwp"),
            "staged_output": str(staged_output),
            "output": str(target),
            "copied": copied,
            "copy_error": copy_error,
            "conversion": {
                "provider": "HANCOM_COM_32BIT_PERSISTENT_BATCH",
                "ok": worker.get("ok") is True,
                "error_code": worker.get("errorCode"),
                "error_message": worker.get("errorMessage"),
                "elapsed_ms": worker.get("elapsedMs"),
                "converter_json": worker,
                "batch_result": str(result_path),
                "returncode": proc.returncode,
                "stderr_tail": (proc.stderr or "")[-1000:],
            },
        })
    return results


def run_persistent_worker(
    targets: list[tuple[int, dict[str, str], Path, Path, Path]],
    *,
    output_dir: Path,
    staging_dir: Path,
    diag_dir: Path,
    timeout_sec: int,
    save_strategy: str,
) -> list[dict[str, Any]]:
    batch_id = uuid.uuid4().hex[:8]
    batch_staging = staging_dir / f"persistent_{batch_id}"
    staged_output_dir = batch_staging / "converted"
    batch_staging.mkdir(parents=True, exist_ok=True)
    staged_output_dir.mkdir(parents=True, exist_ok=True)
    diag_dir.mkdir(parents=True, exist_ok=True)

    manifest_items, target_map, pre_results = _stage_targets(
        targets, batch_staging, staged_output_dir
    )

    if not manifest_items:
        return pre_results

    manifest_path = batch_staging / "manifest.json"
    result_path = batch_staging / "result.json"
    write_json(manifest_path, {"batchId": batch_id, "items": manifest_items})

    proc, timeout_results = _run_worker_subprocess(
        manifest_path, result_path, diag_dir, save_strategy, timeout_sec, targets
    )
    if timeout_results is not None:
        return timeout_results

    return _finalize_worker_results(pre_results, target_map, result_path, proc, batch_staging)


@dataclass
class ConversionConfig:
    """`run_conversion` 의 묶인 설정 (원래 18개 keyword-only 인자였음)."""

    inventory_csv: Path
    output_dir: Path
    staging_dir: Path
    diag_dir: Path
    report_json: Path
    report_csv: Path | None
    audit_jsonl: Path | None
    offset: int
    limit: int
    timeout_sec: int
    save_strategy: str
    existing_policy: str
    skip_inventory_peer: bool
    root_contains: str
    dry_run: bool
    fail_fast: bool
    lock_file: Path | None
    engine: str


def _append_audit_jsonl(audit_jsonl: Path | None, result: dict[str, Any]) -> None:
    if not audit_jsonl:
        return
    audit_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with audit_jsonl.open("a", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "event": "local_hwp_inventory_conversion_item",
                    "logged_at": iso_now(),
                    "result": result,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n"
        )


@dataclass
class _ResolvedDirs:
    """`config` 의 output/staging/diag 디렉토리를 resolve() 한 결과 묶음."""

    output_dir: Path
    staging_dir: Path
    diag_dir: Path


def _result_for_row(
    index: int,
    row_target: tuple[dict[str, str], Path, Path, Path],
    peers: set[str],
    config: ConversionConfig,
    dirs: _ResolvedDirs,
) -> dict[str, Any] | None:
    """단일 행의 변환 결과를 계산한다.

    engine="persistent" 이고 즉시 처리 대상이 아니면 None 을 반환해
    지연(pending_persistent) 처리 대상임을 알린다.
    """
    row, source, root, target = row_target
    peer_key = os.path.normcase(str(source.with_suffix("")))
    peer = source.with_suffix(".hwpx")
    if config.dry_run:
        return planned_result(index, source, root, target)
    if config.skip_inventory_peer and peer_key in peers:
        return skipped_result(index, source, root, target, "INVENTORY_HWPX_PEER_EXISTS", peer)
    if target.exists() and config.existing_policy == "skip":
        return skipped_result(index, source, root, target, "OUTPUT_EXISTS")
    if target.exists() and config.existing_policy == "fail":
        return {
            "status": "FAIL",
            "index": index,
            "input": str(source),
            "relative": str(row_relative(row, root, source)),
            "output": str(target),
            "error_code": "OUTPUT_EXISTS",
            "error_message": "Output exists and existing_policy=fail",
        }
    if config.engine == "persistent":
        return None
    return convert_one_native(
        source,
        input_root=root,
        output_root=dirs.output_dir / safe_anchor(str(root)),
        staging_root=dirs.staging_dir,
        diag_dir=dirs.diag_dir,
        timeout_sec=config.timeout_sec,
        save_strategy=config.save_strategy,
        index=index,
    )


def _discover_target_rows(
    rows: list[dict[str, str]],
    output_dir: Path,
    root_filter: str,
    offset: int,
    limit: int,
) -> list[tuple[dict[str, str], Path, Path, Path]]:
    """인벤토리 행 중 .hwp 대상만 골라 (row, source, root, target) 목록을 만든다."""
    hwp_rows: list[tuple[dict[str, str], Path, Path, Path]] = []
    for row in rows:
        source = row_path(row)
        if source.suffix.lower() != ".hwp":
            continue
        root = row_root(row, source)
        if root_filter and root_filter not in str(root).lower():
            continue
        relative = row_relative(row, root, source)
        target = target_path_for(output_dir, root, relative, source)
        hwp_rows.append((row, source, root, target))
    if offset > 0:
        hwp_rows = hwp_rows[offset:]
    if limit > 0:
        hwp_rows = hwp_rows[:limit]
    return hwp_rows


def run_conversion(config: ConversionConfig) -> dict[str, Any]:
    started = iso_now()
    rows = read_inventory(config.inventory_csv)
    peers = inventory_hwpx_peers(rows) if config.skip_inventory_peer else set()
    dirs = _ResolvedDirs(
        output_dir=config.output_dir.expanduser().resolve(),
        staging_dir=config.staging_dir.expanduser().resolve(),
        diag_dir=config.diag_dir.expanduser().resolve(),
    )
    hwp_rows = _discover_target_rows(
        rows, dirs.output_dir, config.root_contains.lower(), config.offset, config.limit
    )

    results: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    with BatchLock(config.lock_file):
        pending_persistent: list[tuple[int, dict[str, str], Path, Path, Path]] = []
        for index, row_target in enumerate(hwp_rows, 1):
            result = _result_for_row(index, row_target, peers, config, dirs)
            if result is None:
                row, source, root, target = row_target
                pending_persistent.append((index, row, source, root, target))
                continue
            results.append(result)
            counts[str(result.get("status"))] += 1
            _append_audit_jsonl(config.audit_jsonl, result)
            if config.fail_fast and result.get("status") == "FAIL":
                break
        if pending_persistent:
            for result in run_persistent_worker(
                pending_persistent,
                output_dir=dirs.output_dir,
                staging_dir=dirs.staging_dir,
                diag_dir=dirs.diag_dir,
                timeout_sec=config.timeout_sec,
                save_strategy=config.save_strategy,
            ):
                results.append(result)
                counts[str(result.get("status"))] += 1
                _append_audit_jsonl(config.audit_jsonl, result)
                if config.fail_fast and result.get("status") == "FAIL":
                    break

    report = {
        "status": "PASS" if counts["FAIL"] == 0 else "FAIL",
        "mode": "local_hwp_inventory_to_hwpx",
        "started_at": started,
        "finished_at": datetime.now(UTC).isoformat(),
        "inventory_csv": str(config.inventory_csv),
        "output_dir": str(dirs.output_dir),
        "staging_dir": str(dirs.staging_dir),
        "diag_dir": str(dirs.diag_dir),
        "target_count": len(hwp_rows),
        "offset": config.offset,
        "limit": config.limit,
        "ok_count": counts["PASS"],
        "skip_count": counts["SKIP"],
        "plan_count": counts["PLAN"],
        "fail_count": counts["FAIL"],
        "existing_policy": config.existing_policy,
        "skip_inventory_peer": config.skip_inventory_peer,
        "dry_run": config.dry_run,
        "save_strategy": config.save_strategy,
        "engine": config.engine,
        "timeout_sec": config.timeout_sec,
        "report_json": str(config.report_json),
        "report_csv": str(config.report_csv) if config.report_csv else "",
        "audit_jsonl": str(config.audit_jsonl) if config.audit_jsonl else "",
        "results": results,
    }
    write_json(config.report_json, report)
    if config.report_csv:
        write_csv_report(config.report_csv, results)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory-csv", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument(
        "--output-dir", type=Path, default=REPO_ROOT / "deliverables" / "local_hwp_hwpx_converted"
    )
    parser.add_argument("--staging-dir", type=Path, default=DEFAULT_WORK_ROOT / "inventory_staging")
    parser.add_argument("--diag-dir", type=Path, default=DEFAULT_WORK_ROOT / "inventory_diag")
    parser.add_argument(
        "--report-json",
        type=Path,
        default=REPO_ROOT / "reports" / "runtime" / "local_hwp_inventory_to_hwpx_report.json",
    )
    parser.add_argument(
        "--report-csv",
        type=Path,
        default=REPO_ROOT / "reports" / "runtime" / "local_hwp_inventory_to_hwpx_report.csv",
    )
    parser.add_argument(
        "--audit-jsonl",
        type=Path,
        default=REPO_ROOT / "reports" / "runtime" / "local_hwp_inventory_to_hwpx_audit.jsonl",
    )
    parser.add_argument(
        "--offset", type=int, default=0, help="Skip this many HWP rows before processing."
    )
    parser.add_argument(
        "--limit", type=int, default=1, help="Maximum HWP files to process; 0 means all"
    )
    parser.add_argument("--timeout-sec", type=int, default=90)
    parser.add_argument("--save-strategy", choices=["direct", "haction", "auto"], default="auto")
    parser.add_argument("--existing-policy", choices=["skip", "overwrite", "fail"], default="skip")
    parser.add_argument("--no-skip-inventory-peer", action="store_true")
    parser.add_argument("--root-contains", default="")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--fail-fast", action="store_true")
    parser.add_argument(
        "--lock-file",
        type=Path,
        default=DEFAULT_LOCK_FILE.with_name("local_hwp_inventory_to_hwpx.lock"),
    )
    parser.add_argument("--engine", choices=["single", "persistent"], default="persistent")
    args = parser.parse_args()
    report = run_conversion(
        ConversionConfig(
            inventory_csv=args.inventory_csv,
            output_dir=args.output_dir,
            staging_dir=args.staging_dir,
            diag_dir=args.diag_dir,
            report_json=args.report_json,
            report_csv=args.report_csv,
            audit_jsonl=args.audit_jsonl,
            offset=int(args.offset),
            limit=int(args.limit),
            timeout_sec=int(args.timeout_sec),
            save_strategy=str(args.save_strategy),
            existing_policy=str(args.existing_policy),
            skip_inventory_peer=not bool(args.no_skip_inventory_peer),
            root_contains=str(args.root_contains),
            dry_run=bool(args.dry_run),
            fail_fast=bool(args.fail_fast),
            lock_file=args.lock_file,
            engine=str(args.engine),
        )
    )
    print(
        json.dumps(
            {
                key: report[key]
                for key in [
                    "status",
                    "target_count",
                    "ok_count",
                    "skip_count",
                    "plan_count",
                    "fail_count",
                    "report_json",
                    "report_csv",
                ]
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if report.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
