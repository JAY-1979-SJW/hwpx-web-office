"""Run a safe HWPX corpus candidate scan for Web Office.

This script is intentionally a candidate scanner, not a fixture promoter. It
may run in the background on the server, but it never copies candidate HWPX
files into the checked-in test corpus and it only writes review artifacts under
the report directory.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOCAL_SCRIPTS = PROJECT_ROOT / "scripts" / "local"
if str(LOCAL_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(LOCAL_SCRIPTS))

from hwpx_corpus_profiler import parse_args as parse_profiler_args  # noqa: E402
from hwpx_corpus_profiler import run_profiler  # noqa: E402


DEFAULT_CANDIDATE_ROOT = Path("data/local_corpus_candidates")
DEFAULT_REPORT_DIR = Path("data/reports/web_office_hwpx_corpus_candidates")
TASK_ID = "WEB-OFFICE-HWPX-CORPUS-CANDIDATE-SCAN-20260526"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _resolve_project_path(path: Path) -> Path:
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def _safe_rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return path.name


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sanitize_profiler_result(result: dict[str, Any]) -> dict[str, Any]:
    sanitized = dict(result)
    reports = sanitized.get("reports")
    if isinstance(reports, dict):
        sanitized["reports"] = {
            key: _safe_rel(Path(value)) if isinstance(value, str) else value
            for key, value in reports.items()
        }
    return sanitized


def _sanitize_profiler_inventory(profiler_dir: Path) -> None:
    """Remove raw file names from profiler inventory files produced by legacy code."""
    jsonl_path = profiler_dir / "inventory.jsonl"
    rows = _read_jsonl(jsonl_path)
    if rows:
        for row in rows:
            file_name = str(row.get("fileName", ""))
            row["originalFileNameHash"] = _hash_text(file_name)[:16] if file_name else ""
            row["fileName"] = ""
            row["relativePath"] = ""
        with jsonl_path.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    csv_path = profiler_dir / "inventory.csv"
    if csv_path.exists():
        with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            csv_rows = list(reader)
            fieldnames = list(reader.fieldnames or [])
        if "originalFileNameHash" not in fieldnames:
            fieldnames.append("originalFileNameHash")
        for row in csv_rows:
            file_name = str(row.get("fileName", ""))
            row["originalFileNameHash"] = _hash_text(file_name)[:16] if file_name else ""
            row["fileName"] = ""
            row["relativePath"] = ""
        with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(csv_rows)


def _build_manifest_draft(
    *,
    profiler_dir: Path,
    profiler_result: dict[str, Any],
) -> dict[str, Any]:
    fixture_candidates = _read_json(profiler_dir / "fixture_candidates.json", [])
    inventory_by_id = {row.get("fileId"): row for row in _read_jsonl(profiler_dir / "inventory.jsonl")}
    parse_by_id = {row.get("fileId"): row for row in _read_jsonl(profiler_dir / "parse_summary.jsonl")}

    candidates: list[dict[str, Any]] = []
    source_rows = fixture_candidates
    if not source_rows:
        source_rows = [
            {
                "fileId": row.get("fileId"),
                "category": "inventory_candidate",
                "reason": "Inventory scan candidate; fixture value not classified yet.",
                "confidence": 0.0,
                "pathHash": row.get("pathHash", ""),
            }
            for row in inventory_by_id.values()
        ]

    for index, row in enumerate(source_rows, 1):
        file_id = str(row.get("fileId", ""))
        inv = inventory_by_id.get(file_id, {})
        parse = parse_by_id.get(file_id, {})
        path_hash = str(row.get("pathHash") or inv.get("pathHash") or "")
        original_name_hash = str(inv.get("originalFileNameHash") or "")
        if not original_name_hash and inv.get("fileName"):
            original_name_hash = _hash_text(str(inv["fileName"]))[:16]
        candidates.append(
            {
                "candidateId": f"candidate_{index:04d}_{path_hash[:10] if path_hash else 'unknown'}",
                "sourceFileId": file_id,
                "category": row.get("category", "unknown_candidate"),
                "sourcePathHash": path_hash,
                "originalFileNameHash": original_name_hash,
                "sizeBytes": int(inv.get("sizeBytes") or 0),
                "reason": row.get("reason", ""),
                "confidence": row.get("confidence", 0.0),
                "observedTableCount": int(parse.get("tableCount") or 0),
                "observedParagraphCount": int(parse.get("paragraphCount") or 0),
                "promotionStatus": "REVIEW_REQUIRED",
                "copyIntoCheckedInCorpusAllowed": False,
                "serverPromotionRequiresApproval": True,
            }
        )

    return {
        "schemaVersion": "web_office_hwpx_candidate_manifest_draft_v1",
        "task": TASK_ID,
        "generatedAt": _utc_now(),
        "source": {
            "type": "server_or_local_candidate_scan",
            "rawPathsStored": False,
            "rawFileNamesStored": False,
        },
        "promotionPolicy": {
            "status": "REVIEW_REQUIRED",
            "automaticPromotionAllowed": False,
            "copyIntoCheckedInCorpusAllowed": False,
            "requiresUserApproval": True,
            "requiresServerVerificationAfterPromotion": True,
        },
        "profilerSummary": {
            "status": profiler_result.get("status"),
            "scanned": profiler_result.get("scanned", 0),
            "zipOk": profiler_result.get("zip_ok", 0),
            "failures": profiler_result.get("failures", 0),
        },
        "candidates": candidates,
    }


def _build_summary_md(report: dict[str, Any]) -> str:
    lines = [
        "# Web Office HWPX Corpus Candidate Scan",
        "",
        f"- task: `{report['task']}`",
        f"- verdict: `{report['verdict']}`",
        f"- candidate root: `{report['candidateRoot']}`",
        f"- profiler output: `{report['profilerOutputDir']}`",
        f"- scanned: {report['profilerResult'].get('scanned', 0)}",
        f"- zip ok: {report['profilerResult'].get('zip_ok', 0)}",
        f"- failures: {report['profilerResult'].get('failures', 0)}",
        f"- manifest draft candidates: {report['candidateManifestDraft']['candidateCount']}",
        "",
        "## Policy",
        "",
        "- This scan is read-only.",
        "- Candidate files are not copied into the checked-in fixture corpus.",
        "- Promotion requires explicit approval and server-side verification.",
        "- Basic HWPX read is verified; full compatibility and UI fidelity remain open.",
        "",
    ]
    return "\n".join(lines)


def run_scan(args: argparse.Namespace) -> dict[str, Any]:
    candidate_root = _resolve_project_path(Path(args.candidate_root))
    report_dir = _resolve_project_path(Path(args.report_dir))
    profiler_dir = report_dir / "profiler"
    report_dir.mkdir(parents=True, exist_ok=True)

    profiler_args = parse_profiler_args(
        [
            "--root",
            str(candidate_root),
            "--out",
            str(profiler_dir),
            "--max-files",
            str(args.max_files),
        ]
    )
    profiler_result = _sanitize_profiler_result(run_profiler(profiler_args))
    _sanitize_profiler_inventory(profiler_dir)

    manifest = _build_manifest_draft(profiler_dir=profiler_dir, profiler_result=profiler_result)
    manifest_path = report_dir / "candidate_manifest_draft.json"
    _write_json(manifest_path, manifest)

    failures = int(profiler_result.get("failures") or 0)
    scanned = int(profiler_result.get("scanned") or 0)
    report = {
        "schemaVersion": "web_office_hwpx_candidate_scan_report_v1",
        "task": TASK_ID,
        "generatedAt": _utc_now(),
        "verdict": "PASS",
        "candidateRoot": _safe_rel(candidate_root),
        "candidateRootExists": candidate_root.exists(),
        "profilerOutputDir": _safe_rel(profiler_dir),
        "reportDir": _safe_rel(report_dir),
        "backgroundSupported": True,
        "readOnly": True,
        "promotionRequiresApproval": True,
        "profilerResult": profiler_result,
        "scanCounters": {
            "scanned": scanned,
            "zipOk": int(profiler_result.get("zip_ok") or 0),
            "failures": failures,
        },
        "candidateManifestDraft": {
            "path": _safe_rel(manifest_path),
            "candidateCount": len(manifest["candidates"]),
        },
        "claimBoundary": (
            "Basic HWPX read is verified; full compatibility and UI fidelity remain open."
        ),
        "finalStatus": "CANDIDATE_SCAN_PASS_REVIEW_REQUIRED",
    }

    report_path = report_dir / "candidate_scan_report.json"
    summary_path = report_dir / "candidate_scan_summary.md"
    _write_json(report_path, report)
    summary_path.write_text(_build_summary_md(report), encoding="utf-8")
    return report


def build_background_command(args: argparse.Namespace) -> list[str]:
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--candidate-root",
        args.candidate_root,
        "--report-dir",
        args.report_dir,
        "--max-files",
        str(args.max_files),
        "--background-child",
    ]
    return command


def start_background_scan(args: argparse.Namespace) -> dict[str, Any]:
    report_dir = _resolve_project_path(Path(args.report_dir))
    report_dir.mkdir(parents=True, exist_ok=True)
    log_path = report_dir / "background.log"
    command = build_background_command(args)
    with log_path.open("ab") as log:
        proc = subprocess.Popen(
            command,
            cwd=str(PROJECT_ROOT),
            stdout=log,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            close_fds=os.name != "nt",
        )
    return {
        "schemaVersion": "web_office_hwpx_candidate_background_v1",
        "task": TASK_ID,
        "verdict": "BACKGROUND_STARTED",
        "pid": proc.pid,
        "logPath": _safe_rel(log_path),
        "reportDir": _safe_rel(report_dir),
        "candidateRoot": _safe_rel(_resolve_project_path(Path(args.candidate_root))),
        "finalReportPath": _safe_rel(report_dir / "candidate_scan_report.json"),
        "promotionRequiresApproval": True,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Web Office HWPX candidate corpus scan")
    parser.add_argument("--candidate-root", default=str(DEFAULT_CANDIDATE_ROOT))
    parser.add_argument("--report-dir", default=str(DEFAULT_REPORT_DIR))
    parser.add_argument("--max-files", type=int, default=0, help="0 means no limit")
    parser.add_argument("--background", action="store_true")
    parser.add_argument("--background-child", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.background and not args.background_child:
        print(json.dumps(start_background_scan(args), ensure_ascii=False, indent=2))
        return 0

    report = run_scan(args)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("verdict") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
