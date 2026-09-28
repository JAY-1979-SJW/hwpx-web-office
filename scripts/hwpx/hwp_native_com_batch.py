#!/usr/bin/env python3
"""Native Hancom COM HWP -> HWPX batch converter with staging and audit.

This path uses Hancom Office SaveAs through the existing 32-bit COM worker.
It stages each source HWP to an ASCII path first because the 32-bit worker can
fail INPUT_NOT_FOUND on long/non-ASCII OneDrive paths.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import socket
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from hancom_hwp_to_hwpx_batch import HWP_CONVERSION_PROVIDER, convert_one_with_strategy
from hancom_visual_verification_gate import build_gate_report
from hwp_to_hwpx_standalone import file_snapshot
from hwpx_package import HwpxValidator

DEFAULT_WORK_ROOT = Path(os.environ.get("TEMP", "tmp")) / "hwp_native_com_batch"
DEFAULT_LOCK_FILE = DEFAULT_WORK_ROOT / "hwp_native_com_batch.lock"


def iso_now() -> str:
    return datetime.now(UTC).isoformat()


def output_path_for(source: Path, input_root: Path, output_root: Path) -> Path:
    return (output_root / source.relative_to(input_root)).with_suffix(".hwpx")


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    tmp_path.write_text(text, encoding="utf-8")
    try_replace_or_direct_write(tmp_path, path, text, encoding="utf-8")


def try_replace_or_direct_write(tmp_path: Path, path: Path, text: str, *, encoding: str) -> None:
    for _attempt in range(10):
        try:
            tmp_path.replace(path)
            return
        except PermissionError:
            time.sleep(0.1)
    path.write_text(text, encoding=encoding)
    try:
        tmp_path.unlink()
    except OSError:
        pass


def write_csv_report(path: Path, results: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    fields = [
        "index",
        "status",
        "relative",
        "input",
        "output",
        "copied",
        "skipped",
        "error_code",
        "error_message",
        "audit_status",
    ]
    with tmp_path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for item in results:
            conversion = item.get("conversion") if isinstance(item.get("conversion"), dict) else {}
            audit = (
                item.get("native_identity_audit")
                if isinstance(item.get("native_identity_audit"), dict)
                else {}
            )
            writer.writerow({
                "index": item.get("index", ""),
                "status": item.get("status", ""),
                "relative": item.get("relative", ""),
                "input": item.get("input", ""),
                "output": item.get("output", ""),
                "copied": item.get("copied", ""),
                "skipped": item.get("skipped", ""),
                "error_code": item.get("error_code")
                or item.get("skip_reason")
                or conversion.get("error_code", ""),
                "error_message": item.get("error_message") or conversion.get("error_message", ""),
                "audit_status": audit.get("status", ""),
            })
    for _attempt in range(10):
        try:
            tmp_path.replace(path)
            return
        except PermissionError:
            time.sleep(0.1)
    path.write_text(tmp_path.read_text(encoding="utf-8-sig"), encoding="utf-8-sig")
    try:
        tmp_path.unlink()
    except OSError:
        pass


class BatchLock:
    def __init__(self, path: Path | None) -> None:
        self.path = path
        self._fd: int | None = None

    def __enter__(self) -> BatchLock:
        if self.path is None:
            return self
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "pid": os.getpid(),
            "host": socket.gethostname(),
            "started_at": iso_now(),
        }
        try:
            self._fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(
                self._fd, json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
            )
        except FileExistsError as exc:
            raise RuntimeError(f"BATCH_LOCK_EXISTS: {self.path}") from exc
        return self

    def __exit__(self, *_exc: object) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None
        if self.path is not None:
            for _attempt in range(10):
                try:
                    self.path.unlink()
                    return
                except FileNotFoundError:
                    return
                except PermissionError:
                    time.sleep(0.1)


def native_identity_audit(
    *,
    source: Path,
    staged_input: Path,
    output: Path,
    conversion: dict[str, Any],
    visual_ack: bool = False,
) -> dict[str, Any]:
    validation = HwpxValidator.validate_hwpx(output)
    visual_gate = (
        build_gate_report(output, None, visual_ack, "automated-native-com-batch")
        if output.exists()
        else {
            "status": "FAIL",
            "machine_ok": False,
            "reason": "OUTPUT_NOT_FOUND",
        }
    )
    converter_json = (
        conversion.get("converter_json")
        if isinstance(conversion.get("converter_json"), dict)
        else {}
    )
    blockers: list[str] = []
    warnings: list[str] = []
    if conversion.get("provider") != HWP_CONVERSION_PROVIDER:
        blockers.append("NATIVE_PROVIDER_NOT_HANCOM_COM")
    if conversion.get("ok") is not True:
        blockers.append(str(conversion.get("error_code") or "NATIVE_CONVERSION_FAILED"))
    if converter_json.get("ok") is not True:
        blockers.append(str(converter_json.get("errorCode") or "NATIVE_WORKER_NOT_OK"))
    if validation.get("zip_ok") is not True:
        blockers.append("HWPX_ZIP_INVALID")
    if validation.get("xml_ok") is not True:
        blockers.append("HWPX_XML_INVALID")
    if visual_gate.get("machine_ok") is not True:
        blockers.append("HWPX_MACHINE_VISUAL_GATE_FAILED")
    if visual_gate.get("visual_review", {}).get("status") != "PASS":
        warnings.append("VISUAL_REVIEW_REQUIRED")
    return {
        "status": "PASS" if not blockers else "FAIL",
        "mode": "native_hancom_com_identity_audit",
        "identity_basis": "Hancom Office native SaveAs HWPX plus machine validation",
        "identity_equal_machine": not blockers,
        "visual_review_required": "VISUAL_REVIEW_REQUIRED" in warnings,
        "source": str(source),
        "staged_input": str(staged_input),
        "output": str(output),
        "source_info": file_snapshot(source),
        "staged_input_info": file_snapshot(staged_input),
        "output_info": file_snapshot(output),
        "provider": conversion.get("provider"),
        "conversion_ok": conversion.get("ok") is True,
        "conversion_error_code": conversion.get("error_code"),
        "worker": {
            "ok": converter_json.get("ok"),
            "provider": converter_json.get("provider"),
            "stage": converter_json.get("stage"),
            "output_size": converter_json.get("outputSize"),
            "zip_valid": converter_json.get("zipValid"),
            "warning_count": converter_json.get("warningCount"),
            "error_code": converter_json.get("errorCode"),
            "elapsed_ms": converter_json.get("elapsedMs"),
        },
        "validation": validation,
        "visual_gate": visual_gate,
        "blockers": blockers,
        "warnings": warnings,
    }


def convert_one_native(  # ruff: ignore[too-many-arguments] - 다른 파일(convert_local_hwp_inventory_to_hwpx.py)에서도 호출, 시그니처 변경 보류
    source: Path,
    *,
    input_root: Path,
    output_root: Path,
    staging_root: Path,
    diag_dir: Path,
    timeout_sec: int,
    save_strategy: str,
    index: int,
) -> dict[str, Any]:
    relative = source.relative_to(input_root)
    staged_input = staging_root / f"{index:06d}.hwp"
    staged_output_dir = staging_root / "converted"
    target_output = output_path_for(source, input_root, output_root)
    staged_input.parent.mkdir(parents=True, exist_ok=True)
    staged_output_dir.mkdir(parents=True, exist_ok=True)
    target_output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, staged_input)
    conversion = convert_one_with_strategy(
        staged_input,
        staged_output_dir,
        timeout_sec,
        "convert",
        diag_dir,
        save_strategy,
    )
    staged_output = Path(str(conversion.get("output") or ""))
    copied = False
    copy_error = ""
    if conversion.get("ok") and staged_output.exists():
        try:
            shutil.copy2(staged_output, target_output)
            copied = True
        except OSError as exc:
            copy_error = str(exc)
            conversion["ok"] = False
            conversion["error_code"] = "OUTPUT_COPY_FAILED"
            conversion["error_message"] = copy_error
    audit = native_identity_audit(
        source=source,
        staged_input=staged_input,
        output=target_output,
        conversion=conversion,
    )
    status = "PASS" if copied and audit.get("status") == "PASS" else "FAIL"
    return {
        "status": status,
        "index": index,
        "input": str(source),
        "relative": str(relative),
        "staged_input": str(staged_input),
        "staged_output": str(staged_output) if staged_output else "",
        "output": str(target_output),
        "copied": copied,
        "copy_error": copy_error,
        "conversion": conversion,
        "native_identity_audit": audit,
    }


def skipped_existing_result(
    source: Path,
    *,
    input_root: Path,
    output_root: Path,
    index: int,
) -> dict[str, Any]:
    relative = source.relative_to(input_root)
    target_output = output_path_for(source, input_root, output_root)
    return {
        "status": "SKIP",
        "index": index,
        "input": str(source),
        "relative": str(relative),
        "output": str(target_output),
        "copied": False,
        "skipped": True,
        "skip_reason": "OUTPUT_EXISTS",
        "output_info": file_snapshot(target_output),
    }


def planned_result(
    source: Path,
    *,
    input_root: Path,
    output_root: Path,
    index: int,
) -> dict[str, Any]:
    relative = source.relative_to(input_root)
    target_output = output_path_for(source, input_root, output_root)
    return {
        "status": "PLAN",
        "index": index,
        "input": str(source),
        "relative": str(relative),
        "output": str(target_output),
        "copied": False,
        "skipped": False,
        "source_info": file_snapshot(source),
    }


def run_batch(
    input_dir: Path,
    output_dir: Path,
    *,
    staging_dir: Path,
    diag_dir: Path,
    report_json: Path,
    audit_jsonl: Path | None,
    pattern: str,
    limit: int,
    timeout_sec: int,
    save_strategy: str,
    existing_policy: str = "overwrite",
    report_csv: Path | None = None,
    lock_file: Path | None = None,
    fail_fast: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    if existing_policy not in {"skip", "overwrite", "fail"}:
        raise ValueError(f"unsupported existing_policy: {existing_policy}")
    started = iso_now()
    input_dir = Path(input_dir).expanduser().resolve()
    output_dir = Path(output_dir).expanduser().resolve()
    staging_dir = Path(staging_dir).expanduser().resolve()
    diag_dir = Path(diag_dir).expanduser().resolve()
    report_json = Path(report_json).expanduser().resolve()
    audit_jsonl = Path(audit_jsonl).expanduser().resolve() if audit_jsonl else None
    report_csv = Path(report_csv).expanduser().resolve() if report_csv else None
    lock_file = Path(lock_file).expanduser().resolve() if lock_file else None
    with BatchLock(lock_file):
        targets = sorted(path for path in input_dir.rglob(pattern) if path.is_file())
        if limit > 0:
            targets = targets[:limit]
        results: list[dict[str, Any]] = []
        for index, source in enumerate(targets, 1):
            target_output = output_path_for(source, input_dir, output_dir)
            if dry_run:
                result = planned_result(
                    source, input_root=input_dir, output_root=output_dir, index=index
                )
            elif target_output.exists() and existing_policy == "skip":
                result = skipped_existing_result(
                    source, input_root=input_dir, output_root=output_dir, index=index
                )
            elif target_output.exists() and existing_policy == "fail":
                result = {
                    "status": "FAIL",
                    "index": index,
                    "input": str(source),
                    "relative": str(source.relative_to(input_dir)),
                    "output": str(target_output),
                    "copied": False,
                    "skipped": False,
                    "error_code": "OUTPUT_EXISTS",
                    "error_message": "Output already exists and existing_policy=fail",
                    "output_info": file_snapshot(target_output),
                }
            else:
                result = convert_one_native(
                    source,
                    input_root=input_dir,
                    output_root=output_dir,
                    staging_root=staging_dir,
                    diag_dir=diag_dir,
                    timeout_sec=timeout_sec,
                    save_strategy=save_strategy,
                    index=index,
                )
            results.append(result)
            if audit_jsonl:
                audit_jsonl.parent.mkdir(parents=True, exist_ok=True)
                with audit_jsonl.open("a", encoding="utf-8") as fh:
                    fh.write(
                        json.dumps(
                            {
                                "event": "native_hancom_com_conversion_item",
                                "logged_at": iso_now(),
                                "result": result,
                            },
                            ensure_ascii=False,
                            sort_keys=True,
                        )
                        + "\n"
                    )
            if fail_fast and result.get("status") == "FAIL":
                break
    ok_count = sum(1 for item in results if item.get("status") == "PASS")
    skip_count = sum(1 for item in results if item.get("status") == "SKIP")
    plan_count = sum(1 for item in results if item.get("status") == "PLAN")
    fail_count = sum(1 for item in results if item.get("status") == "FAIL")
    status = "PASS" if targets and fail_count == 0 and not dry_run else "FAIL"
    if dry_run:
        status = "PASS"
    report = {
        "status": status,
        "mode": "native_hancom_com_batch",
        "started_at": started,
        "finished_at": iso_now(),
        "input_dir": str(input_dir),
        "output_dir": str(output_dir),
        "staging_dir": str(staging_dir),
        "diag_dir": str(diag_dir),
        "pattern": pattern,
        "target_count": len(targets),
        "ok_count": ok_count,
        "skip_count": skip_count,
        "plan_count": plan_count,
        "fail_count": fail_count,
        "provider": HWP_CONVERSION_PROVIDER,
        "save_strategy": save_strategy,
        "timeout_sec": timeout_sec,
        "existing_policy": existing_policy,
        "fail_fast": fail_fast,
        "dry_run": dry_run,
        "report_json": str(report_json),
        "report_csv": str(report_csv) if report_csv else "",
        "audit_jsonl": str(audit_jsonl) if audit_jsonl else "",
        "lock_file": str(lock_file) if lock_file else "",
        "results": results,
    }
    atomic_write_json(report_json, report)
    if report_csv:
        write_csv_report(report_csv, results)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--staging-dir", type=Path, default=DEFAULT_WORK_ROOT / "staging")
    parser.add_argument("--diag-dir", type=Path, default=DEFAULT_WORK_ROOT / "diag")
    parser.add_argument(
        "--report-json", type=Path, default=Path("tmp/hwp_native_com_batch_report.json")
    )
    parser.add_argument("--audit-jsonl", type=Path)
    parser.add_argument("--report-csv", type=Path)
    parser.add_argument("--lock-file", type=Path, default=DEFAULT_LOCK_FILE)
    parser.add_argument("--pattern", default="*.hwp")
    parser.add_argument(
        "--limit", type=int, default=1, help="Maximum files to convert; 0 means all"
    )
    parser.add_argument("--timeout-sec", type=int, default=90)
    parser.add_argument("--save-strategy", choices=["direct", "haction", "auto"], default="direct")
    parser.add_argument("--existing-policy", choices=["skip", "overwrite", "fail"], default="skip")
    parser.add_argument("--fail-fast", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    report = run_batch(
        args.input_dir,
        args.output_dir,
        staging_dir=args.staging_dir,
        diag_dir=args.diag_dir,
        report_json=args.report_json,
        audit_jsonl=args.audit_jsonl,
        pattern=str(args.pattern),
        limit=int(args.limit),
        timeout_sec=int(args.timeout_sec),
        save_strategy=str(args.save_strategy),
        existing_policy=str(args.existing_policy),
        report_csv=args.report_csv,
        lock_file=args.lock_file,
        fail_fast=bool(args.fail_fast),
        dry_run=bool(args.dry_run),
    )
    print(
        json.dumps(
            {
                key: report[key]
                for key in [
                    "status",
                    "mode",
                    "target_count",
                    "ok_count",
                    "skip_count",
                    "plan_count",
                    "fail_count",
                    "report_json",
                    "report_csv",
                ]
                if key in report
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if report.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
