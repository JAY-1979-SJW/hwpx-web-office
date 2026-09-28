"""Batch SANDBOX_ONLY runner for sanitized real-like HWPX samples.

HWPX-FORM-AUTO-FILL-WRITER-REAL-LIKE-SANDBOX-BATCH-10

The batch runner only accepts sanitized real-like samples. It records file-level
immutability and security summaries without storing raw paths, raw filenames, or
raw field values in reports.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from hwpx.pipeline import form_auto_fill_real_file_preflight as pf
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    ROOT = Path(__file__).resolve().parents[3]
    sys.path.insert(0, str(ROOT / "scripts"))
    from hwpx.pipeline import form_auto_fill_real_file_preflight as pf

SCHEMA_VERSION = "form_auto_fill_real_like_sandbox_batch_v1"
MODE = "SANDBOX_ONLY"

STATUS_SANDBOX_WRITE_PASS = "SANDBOX_WRITE_PASS"
STATUS_FAILED_READBACK = "FAILED_READBACK"
STATUS_FAILED_UNEXPECTED_MUTATION = "FAILED_UNEXPECTED_MUTATION"
STATUS_FAILED_SOURCE_MUTATED = "FAILED_SOURCE_MUTATED"
STATUS_FAILED_OUTPUT_BROKEN = "FAILED_OUTPUT_BROKEN"

PASS_REAL_LIKE_SANDBOX_BATCH = "PASS_REAL_LIKE_SANDBOX_BATCH"
WARN_SOME_FILES_BLOCKED = "WARN_SOME_FILES_BLOCKED"
FAIL_SOURCE_MUTATION_DETECTED = "FAIL_SOURCE_MUTATION_DETECTED"
FAIL_READBACK_FAILURE_DETECTED = "FAIL_READBACK_FAILURE_DETECTED"
FAIL_UNEXPECTED_MUTATION_DETECTED = "FAIL_UNEXPECTED_MUTATION_DETECTED"
FAIL_SECURITY_LEAK_DETECTED = "FAIL_SECURITY_LEAK_DETECTED"
FAIL_NO_INPUT_FILES = "FAIL_NO_INPUT_FILES"
FAIL_OPERATION_MODE_NOT_SANDBOX = "FAIL_OPERATION_MODE_NOT_SANDBOX"

WARNINGS = [
    "WARN_REAL_LIKE_SANITIZED_SAMPLE_ONLY",
    "WARN_SANDBOX_ONLY",
    "WARN_REAL_USER_FILE_NOT_TESTED",
    "WARN_DEPLOY_NOT_PERFORMED",
]


@dataclass
class BatchOptions:
    input_dir: Path
    output_dir: Path
    limit: int
    sandbox_only: bool = True
    mask_pii: bool = True
    fail_on_source_mutation: bool = True
    fail_on_readback_fail: bool = True
    fail_on_unexpected_mutation: bool = True
    accept_output: bool = True


PreflightRunner = Callable[
    [Path, list[pf.TargetMapEntry] | None, list[Any], Path, str, bool], dict[str, Any]
]


def _sample_id(index: int, sample_path: Path) -> str:
    digest = hashlib.sha256(f"{index}:{sample_path.name}".encode()).hexdigest()[:10]
    return f"real_like_{index:03d}_{digest}"


def _list_candidates(input_dir: Path, limit: int) -> list[Path]:
    if not input_dir.is_dir() or limit <= 0:
        return []
    return sorted(
        path for path in input_dir.iterdir() if path.is_file() and path.suffix.lower() == ".hwpx"
    )[:limit]


def _security_counts(result: dict[str, Any]) -> dict[str, int]:
    sec = result.get("security", {})
    return {
        "piiLeak": 1 if sec.get("piiLeak") else 0,
        "rawPathLeak": 1 if sec.get("rawPathLeak") else 0,
        "rawFilenameLeak": 1 if sec.get("rawFilenameLeak") else 0,
    }


def _file_status(preflight_result: dict[str, Any]) -> str:
    status = preflight_result.get("preflightStatus", "")
    sandbox = preflight_result.get("sandboxResult", {})
    if status != pf.READY_FOR_SANDBOX_WRITE:
        return status
    if preflight_result.get("sourceHashBefore") != preflight_result.get("sourceHashAfter"):
        return STATUS_FAILED_SOURCE_MUTATED
    if preflight_result.get("sourceMtimeChanged"):
        return STATUS_FAILED_SOURCE_MUTATED
    if sandbox.get("readbackFail", 0) > 0:
        return STATUS_FAILED_READBACK
    if sandbox.get("unexpectedMutation", 0) > 0:
        return STATUS_FAILED_UNEXPECTED_MUTATION
    return STATUS_SANDBOX_WRITE_PASS


def _file_result(preflight_result: dict[str, Any], status: str) -> dict[str, Any]:
    sandbox = preflight_result.get("sandboxResult", {})
    return {
        "sampleId": preflight_result.get("sampleId", ""),
        "status": status,
        "sourceHashChanged": preflight_result.get("sourceHashBefore")
        != preflight_result.get("sourceHashAfter"),
        "sourceMtimeChanged": bool(preflight_result.get("sourceMtimeChanged")),
        "writtenFields": int(sandbox.get("writtenFields", 0)),
        "readbackPass": int(sandbox.get("readbackPass", 0)),
        "readbackFail": int(sandbox.get("readbackFail", 0)),
        "unexpectedMutation": int(sandbox.get("unexpectedMutation", 0)),
        "finalExportEnabled": bool(sandbox.get("finalExportEnabled", False)),
    }


def _blocked_result(preflight_result: dict[str, Any], status: str) -> dict[str, Any]:
    return {
        "sampleId": preflight_result.get("sampleId", ""),
        "status": status,
        "blockedReason": status,
        "writtenFields": int(preflight_result.get("sandboxResult", {}).get("writtenFields", 0)),
    }


def _blank_summary(total: int, processed: int) -> dict[str, int]:
    return {
        "totalCandidates": total,
        "processed": processed,
        "ready": 0,
        "writtenFiles": 0,
        "blockedFiles": 0,
        "failedFiles": 0,
        "readbackFail": 0,
        "unexpectedMutation": 0,
        "sourceMutation": 0,
        "piiLeak": 0,
        "rawPathLeak": 0,
        "rawFilenameLeak": 0,
    }


def _verdict(summary: dict[str, int], blocked_files: int, sandbox_only: bool) -> str:
    if not sandbox_only:
        return FAIL_OPERATION_MODE_NOT_SANDBOX
    if summary["processed"] < 1:
        return FAIL_NO_INPUT_FILES
    if summary["sourceMutation"] > 0:
        return FAIL_SOURCE_MUTATION_DETECTED
    if summary["readbackFail"] > 0:
        return FAIL_READBACK_FAILURE_DETECTED
    if summary["unexpectedMutation"] > 0:
        return FAIL_UNEXPECTED_MUTATION_DETECTED
    if summary["piiLeak"] or summary["rawPathLeak"] or summary["rawFilenameLeak"]:
        return FAIL_SECURITY_LEAK_DETECTED
    if blocked_files > 0:
        return WARN_SOME_FILES_BLOCKED
    return PASS_REAL_LIKE_SANDBOX_BATCH


def run_real_like_sandbox_batch(  # ruff: ignore[too-many-arguments] -- 여러 곳(테스트·ops·API 라우트)에서 키워드 인자로 호출, 시그니처 변경 보류
    input_dir: Path,
    output_dir: Path,
    limit: int,
    sandbox_only: bool = True,
    mask_pii: bool = True,
    fail_on_source_mutation: bool = True,
    fail_on_readback_fail: bool = True,
    fail_on_unexpected_mutation: bool = True,
    accept_output: bool = True,
    target_map_by_sample: dict[str, list[pf.TargetMapEntry] | None] | None = None,
    approved_fields_by_sample: dict[str, list[Any]] | None = None,
    preflight_runner: PreflightRunner | None = None,
) -> dict[str, Any]:
    """Run batch preflight and sandbox write for sanitized real-like samples."""
    options = BatchOptions(
        input_dir=Path(input_dir),
        output_dir=Path(output_dir),
        limit=limit,
        sandbox_only=sandbox_only,
        mask_pii=mask_pii,
        fail_on_source_mutation=fail_on_source_mutation,
        fail_on_readback_fail=fail_on_readback_fail,
        fail_on_unexpected_mutation=fail_on_unexpected_mutation,
        accept_output=accept_output,
    )
    target_map_by_sample = target_map_by_sample or {}
    approved_fields_by_sample = approved_fields_by_sample or {}
    preflight_runner = preflight_runner or _default_preflight_runner

    candidates = _list_candidates(options.input_dir, options.limit)
    summary = _blank_summary(total=len(candidates), processed=len(candidates))
    file_results: list[dict[str, Any]] = []
    blocked_results: list[dict[str, Any]] = []
    warnings = list(WARNINGS)

    if not options.sandbox_only:
        warnings.append("FAIL_OPERATION_MODE_NOT_SANDBOX")

    for index, sample_path in enumerate(candidates, start=1):
        sample_id = _sample_id(index, sample_path)
        target_map = target_map_by_sample.get(sample_id, pf.default_real_like_target_map())
        approved_fields = approved_fields_by_sample.get(
            sample_id, pf.default_real_like_approved_fields()
        )
        sample_output_dir = options.output_dir / "sandbox_outputs" / sample_id
        preflight = preflight_runner(
            sample_path,
            target_map,
            approved_fields,
            sample_output_dir,
            sample_id,
            options.accept_output,
        )
        status = _file_status(preflight)
        result_row = _file_result(preflight, status)
        security = _security_counts(preflight)

        summary["piiLeak"] += security["piiLeak"]
        summary["rawPathLeak"] += security["rawPathLeak"]
        summary["rawFilenameLeak"] += security["rawFilenameLeak"]
        summary["readbackFail"] += result_row["readbackFail"]
        summary["unexpectedMutation"] += result_row["unexpectedMutation"]
        if result_row["sourceHashChanged"] or result_row["sourceMtimeChanged"]:
            summary["sourceMutation"] += 1

        if preflight.get("preflightStatus") == pf.READY_FOR_SANDBOX_WRITE:
            summary["ready"] += 1

        if status == STATUS_SANDBOX_WRITE_PASS:
            summary["writtenFiles"] += 1
            file_results.append(result_row)
        elif status.startswith("BLOCKED_"):
            summary["blockedFiles"] += 1
            blocked_row = _blocked_result(preflight, status)
            blocked_results.append(blocked_row)
            file_results.append(result_row)
        else:
            summary["failedFiles"] += 1
            file_results.append(result_row)

    if summary["blockedFiles"] > 0:
        warnings.append("WARN_SOME_FILES_BLOCKED")

    overall = _verdict(summary, summary["blockedFiles"], options.sandbox_only)
    return {
        "schemaVersion": SCHEMA_VERSION,
        "mode": MODE if options.sandbox_only else "BLOCKED_NON_SANDBOX",
        "batchLimit": limit,
        "overallVerdict": overall,
        "summary": summary,
        "fileResults": file_results,
        "blockedResults": blocked_results,
        "warnings": warnings,
    }


def _default_preflight_runner(
    sample_path: Path,
    target_map: list[pf.TargetMapEntry] | None,
    approved_fields: list[Any],
    output_dir: Path,
    sample_id: str,
    accept_output: bool,
) -> dict[str, Any]:
    return pf.run_real_file_preflight(
        sample_path,
        target_map,
        approved_fields,
        output_dir,
        sample_id=sample_id,
        accept_output=accept_output,
    )


def write_batch_reports(batch: dict[str, Any], output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    reports = {
        "batch_summary.json": batch,
        "file_results.json": batch.get("fileResults", []),
        "blocked_results.json": batch.get("blockedResults", []),
        "security_scan_result.json": {
            "piiLeak": batch.get("summary", {}).get("piiLeak", 0),
            "rawPathLeak": batch.get("summary", {}).get("rawPathLeak", 0),
            "rawFilenameLeak": batch.get("summary", {}).get("rawFilenameLeak", 0),
            "aiCalled": 0,
            "ocrCalled": 0,
            "hancomRequired": False,
        },
    }
    written: dict[str, Path] = {}
    for name, payload in reports.items():
        path = output_dir / name
        _write_safe_json(path, payload)
        written[name] = path

    md = [
        "# HWPX Form Auto Fill Real-Like Sandbox Batch",
        "",
        f"- verdict: {batch.get('overallVerdict', '')}",
        f"- mode: {batch.get('mode', '')}",
        f"- batchLimit: {batch.get('batchLimit', 0)}",
        f"- processed: {batch.get('summary', {}).get('processed', 0)}",
        f"- writtenFiles: {batch.get('summary', {}).get('writtenFiles', 0)}",
        f"- blockedFiles: {batch.get('summary', {}).get('blockedFiles', 0)}",
        f"- readbackFail: {batch.get('summary', {}).get('readbackFail', 0)}",
        f"- unexpectedMutation: {batch.get('summary', {}).get('unexpectedMutation', 0)}",
        f"- sourceMutation: {batch.get('summary', {}).get('sourceMutation', 0)}",
    ]
    md_path = output_dir / "batch_summary.md"
    md_path.write_text("\n".join(md) + "\n", encoding="utf-8")
    written["batch_summary.md"] = md_path
    return written


def _write_safe_json(path: Path, payload: Any) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if _contains_report_leak(text):
        raise ValueError(f"unsafe batch report payload: {path.name}")
    path.write_text(text, encoding="utf-8")


def _contains_report_leak(text: str) -> bool:
    return bool(
        pf.ABS_PATH_RE.search(text) or pf.RAW_FILENAME_RE.search(text) or pf.PII_RE.search(text)
    )


def create_batch_fixture_dir(directory: Path, count: int) -> Path:
    """Create sanitized real-like fixtures in a temporary directory."""
    directory.mkdir(parents=True, exist_ok=True)
    for index in range(1, count + 1):
        pf.create_real_like_sanitized_hwpx(directory / f"sanitized_{index:03d}.hwpx")
    return directory


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run real-like SANDBOX_ONLY HWPX batch")
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--limit", type=int, required=True)
    parser.add_argument("--sandbox-only", action="store_true", required=True)
    parser.add_argument("--mask-pii", action="store_true", required=True)
    parser.add_argument("--fail-on-source-mutation", action="store_true", required=True)
    parser.add_argument("--fail-on-readback-fail", action="store_true", required=True)
    parser.add_argument("--fail-on-unexpected-mutation", action="store_true", required=True)
    args = parser.parse_args(argv)

    batch = run_real_like_sandbox_batch(
        input_dir=Path(args.input_dir),
        output_dir=Path(args.output_dir),
        limit=args.limit,
        sandbox_only=args.sandbox_only,
        mask_pii=args.mask_pii,
        fail_on_source_mutation=args.fail_on_source_mutation,
        fail_on_readback_fail=args.fail_on_readback_fail,
        fail_on_unexpected_mutation=args.fail_on_unexpected_mutation,
    )
    write_batch_reports(batch, Path(args.output_dir))
    print(json.dumps(batch, ensure_ascii=False, indent=2))
    return (
        0
        if batch["overallVerdict"] in {PASS_REAL_LIKE_SANDBOX_BATCH, WARN_SOME_FILES_BLOCKED}
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
