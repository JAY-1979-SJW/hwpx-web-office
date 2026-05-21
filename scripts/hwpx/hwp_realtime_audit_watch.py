#!/usr/bin/env python3
"""Realtime HWP conversion watcher with per-cycle audit logging."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from uuid import uuid4
from typing import Any

import hwp_to_hwpx_standalone as core
import hwp_full_fidelity_converter as full
import hwp_hwp5proc_audit
import openhwp_rust_probe


def summarize_results(results: list[dict[str, Any]]) -> dict[str, int]:
    ok_count = sum(1 for result in results if result.get("status") == "PASS")
    skipped_count = sum(1 for result in results if result.get("status") == "SKIP")
    fail_count = len(results) - ok_count - skipped_count
    identity_pass_count = sum(1 for result in results if result.get("identity_status") == "PASS")
    identity_fail_count = sum(1 for result in results if result.get("identity_status") == "FAIL")
    hwp5proc_pass_count = sum(1 for result in results if result.get("hwp5proc_status") == "PASS")
    hwp5proc_fail_count = sum(1 for result in results if result.get("hwp5proc_status") == "FAIL")
    hwp5proc_warn_count = sum(1 for result in results if result.get("hwp5proc_status") == "WARN")
    openhwp_pass_count = sum(1 for result in results if result.get("openhwp_status") == "PASS")
    openhwp_fail_count = sum(1 for result in results if result.get("openhwp_status") == "FAIL")
    return {
        "ok_count": ok_count,
        "skipped_count": skipped_count,
        "fail_count": fail_count,
        "identity_pass_count": identity_pass_count,
        "identity_fail_count": identity_fail_count,
        "hwp5proc_pass_count": hwp5proc_pass_count,
        "hwp5proc_warn_count": hwp5proc_warn_count,
        "hwp5proc_fail_count": hwp5proc_fail_count,
        "openhwp_pass_count": openhwp_pass_count,
        "openhwp_fail_count": openhwp_fail_count,
    }


def attach_identity_audit(result: dict[str, Any], *, require_identity: bool) -> dict[str, Any]:
    audited = dict(result)
    input_value = audited.get("input")
    output_value = audited.get("output")
    if not input_value or not output_value:
        audited["identity_status"] = "SKIPPED"
        audited["identity_audit"] = {"status": "SKIPPED", "reason": "INPUT_OR_OUTPUT_MISSING"}
        return audited
    try:
        analysis = full.analyze_hwp(Path(str(input_value)), include_records=False)
        identity = full.build_identity_audit(Path(str(input_value)), Path(str(output_value)), analysis=analysis)
    except Exception as exc:  # noqa: BLE001
        identity = {
            "status": "FAIL",
            "mode": "full_fidelity_identity_audit",
            "error": "IDENTITY_AUDIT_EXCEPTION",
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "identity_equal": False,
        }
    audited["identity_status"] = identity.get("status")
    audited["identity_equal"] = identity.get("identity_equal") is True
    audited["identity_audit"] = identity
    if require_identity and identity.get("status") != "PASS":
        audited["status"] = "FAIL"
        audited["error"] = "IDENTITY_AUDIT_FAILED"
    return audited


def attach_openhwp_audit(
    result: dict[str, Any],
    *,
    openhwp_root: Path | None,
    require_openhwp: bool,
) -> dict[str, Any]:
    audited = dict(result)
    if not openhwp_root:
        audited["openhwp_status"] = "SKIPPED"
        audited["openhwp_audit"] = {"enabled": False, "status": "SKIPPED", "reason": "OPENHWP_NOT_CONFIGURED"}
        return audited
    input_value = audited.get("input")
    if not input_value:
        audit = {"enabled": True, "status": "SKIPPED", "reason": "INPUT_MISSING"}
    else:
        try:
            audit = openhwp_rust_probe.run_probe(Path(str(input_value)), openhwp_root=openhwp_root)
            audit["enabled"] = True
        except Exception as exc:  # noqa: BLE001
            audit = {
                "enabled": True,
                "status": "FAIL",
                "error": "OPENHWP_PROBE_EXCEPTION",
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            }
    audited["openhwp_status"] = audit.get("status")
    audited["openhwp_audit"] = audit
    if require_openhwp and audit.get("status") != "PASS":
        audited["status"] = "FAIL"
        audited["error"] = "OPENHWP_AUDIT_FAILED"
    return audited


def build_realtime_report(
    *,
    job_id: str,
    started_at: str,
    input_dir: Path,
    output_dir: Path,
    pattern: str,
    existing_policy: str,
    fidelity_policy: str,
    embed_original: bool,
    require_identity: bool,
    hwp5proc: Path | None,
    require_hwp5proc: bool,
    openhwp_root: Path | None,
    require_openhwp: bool,
    interval_sec: float,
    cycle_count: int,
    events: list[dict[str, Any]],
    results: list[dict[str, Any]],
    final: bool,
) -> dict[str, Any]:
    counts = summarize_results(results)
    status = "PASS" if counts["fail_count"] == 0 else "FAIL"
    report = core.attach_watch_gate(
        {
            "status": status,
            "mode": "watch_text_only_rebuild",
            "job_id": job_id,
            "started_at": started_at,
            "finished_at": core.iso_now() if final else "",
            "duration_sec": round((core.utc_now() - core.datetime.fromisoformat(started_at)).total_seconds(), 6),
            "input_dir": str(input_dir),
            "output_dir": str(output_dir),
            "pattern": pattern,
            "cycle_count": cycle_count,
            "detected_count": len(results),
            **counts,
            "existing_policy": existing_policy,
            "fidelity_policy": fidelity_policy,
            "embed_original": embed_original,
            "identity_audit": {
                "enabled": True,
                "require_identity": require_identity,
                "identity_pass_count": counts["identity_pass_count"],
                "identity_fail_count": counts["identity_fail_count"],
            },
            "hwp5proc_audit": {
                "enabled": bool(hwp5proc),
                "hwp5proc": str(hwp5proc) if hwp5proc else "",
                "require_hwp5proc": require_hwp5proc,
                "hwp5proc_pass_count": counts["hwp5proc_pass_count"],
                "hwp5proc_warn_count": counts["hwp5proc_warn_count"],
                "hwp5proc_fail_count": counts["hwp5proc_fail_count"],
            },
            "openhwp_audit": {
                "enabled": bool(openhwp_root),
                "openhwp_root": str(openhwp_root) if openhwp_root else "",
                "require_openhwp": require_openhwp,
                "openhwp_pass_count": counts["openhwp_pass_count"],
                "openhwp_fail_count": counts["openhwp_fail_count"],
            },
            "interval_sec": interval_sec,
            "events": events,
            "results": results,
            "realtime": {
                "active": not final,
                "last_cycle": cycle_count,
                "last_checked_at": events[-1]["checked_at"] if events else "",
            },
        }
    )
    return report


def write_cycle_audit(
    audit_log: Path | None,
    report: dict[str, Any],
    cycle_results: list[dict[str, Any]],
    *,
    cycle: int,
    audit_level: str,
) -> None:
    if not audit_log:
        return
    cycle_report = dict(report)
    cycle_report["results"] = cycle_results
    cycle_report["target_count"] = len(cycle_results)
    counts = summarize_results(cycle_results)
    cycle_report.update(counts)
    core.write_audit_log(audit_log, cycle_report, event="realtime_watch_cycle", audit_level=audit_level)
    if audit_level == "forensic":
        resolved = Path(audit_log).expanduser().resolve()
        resolved.parent.mkdir(parents=True, exist_ok=True)
        for index, result in enumerate(cycle_results):
            item = dict(result)
            item["job_id"] = report.get("job_id")
            item["mode"] = "watch_text_only_rebuild"
            record = core.build_audit_record(item, event="realtime_conversion_item", audit_level="forensic")
            record["cycle"] = cycle
            record["item_index"] = index
            resolved.open("a", encoding="utf-8").write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def run_realtime_watch(
    input_dir: Path,
    output_dir: Path,
    *,
    pattern: str = "*.hwp",
    existing_policy: str = "skip",
    fidelity_policy: str = "audit",
    embed_original: bool = True,
    strict_quality: bool = False,
    require_identity: bool = False,
    hwp5proc: Path | None = None,
    require_hwp5proc: bool = False,
    openhwp_root: Path | None = None,
    require_openhwp: bool = False,
    interval_sec: float = 2.0,
    max_cycles: int | None = None,
    audit_log: Path | None = None,
    audit_level: str = "standard",
    summary_json: Path | None = None,
    summary_md: Path | None = None,
    job_id: str | None = None,
) -> dict[str, Any]:
    resolved_job_id = job_id or f"realtime-{uuid4().hex}"
    input_dir = Path(input_dir).expanduser().resolve()
    output_dir = Path(output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    started_at = core.utc_now().isoformat()
    seen: dict[str, str] = {}
    events: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    cycle = 0

    while True:
        cycle += 1
        detections = core.detect_watch_targets(input_dir, pattern=pattern, seen=seen)
        cycle_results = core.convert_watch_detections(
            detections,
            input_dir,
            output_dir,
            expected_texts=[],
            strict_quality=strict_quality,
            existing_policy=existing_policy,
            fidelity_policy=fidelity_policy,
            embed_original=embed_original,
        )
        cycle_results = [attach_identity_audit(result, require_identity=require_identity) for result in cycle_results]
        cycle_results = [
            hwp_hwp5proc_audit.attach_hwp5proc_audit(result, hwp5proc=hwp5proc, require_hwp5proc=require_hwp5proc)
            for result in cycle_results
        ]
        cycle_results = [
            attach_openhwp_audit(result, openhwp_root=openhwp_root, require_openhwp=require_openhwp)
            for result in cycle_results
        ]
        events.append(
            {
                "cycle": cycle,
                "checked_at": core.iso_now(),
                "detected_count": len(detections),
                "converted_count": len(cycle_results),
                "result_statuses": [result.get("status") for result in cycle_results],
                "detections": detections,
            }
        )
        results.extend(cycle_results)
        final = max_cycles is not None and cycle >= max(1, int(max_cycles))
        report = build_realtime_report(
            job_id=resolved_job_id,
            started_at=started_at,
            input_dir=input_dir,
            output_dir=output_dir,
            pattern=pattern,
            existing_policy=existing_policy,
            fidelity_policy=fidelity_policy,
            embed_original=embed_original,
            require_identity=require_identity,
            hwp5proc=hwp5proc,
            require_hwp5proc=require_hwp5proc,
            openhwp_root=openhwp_root,
            require_openhwp=require_openhwp,
            interval_sec=interval_sec,
            cycle_count=cycle,
            events=events,
            results=results,
            final=final,
        )
        write_cycle_audit(audit_log, report, cycle_results, cycle=cycle, audit_level=audit_level)
        core.write_report(summary_json, report)
        core.write_report_md(summary_md, report)
        if final:
            return report
        time.sleep(max(0.1, float(interval_sec)))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--pattern", default="*.hwp")
    parser.add_argument("--existing-policy", choices=core.EXISTING_POLICIES, default="skip")
    parser.add_argument("--fidelity-policy", choices=core.FIDELITY_POLICIES, default="audit")
    parser.add_argument("--no-embed-original", action="store_true")
    parser.add_argument("--strict-quality", action="store_true")
    parser.add_argument("--require-identity", action="store_true", help="Treat full-fidelity identity audit failures as conversion failures")
    parser.add_argument("--hwp5proc", type=Path, help="Optional hwp5proc.exe path for realtime source record audits")
    parser.add_argument("--require-hwp5proc", action="store_true", help="Treat hwp5proc audit failures as conversion failures")
    parser.add_argument("--openhwp-root", type=Path, help="Optional OpenHWP checkout root for Rust parser audits")
    parser.add_argument("--require-openhwp", action="store_true", help="Treat OpenHWP parser audit failures as conversion failures")
    parser.add_argument("--interval-sec", type=float, default=2.0)
    parser.add_argument("--max-cycles", type=int)
    parser.add_argument("--audit-log", type=Path)
    parser.add_argument("--audit-level", choices=core.AUDIT_LEVELS, default="standard")
    parser.add_argument("--summary-json", type=Path)
    parser.add_argument("--summary-md", type=Path)
    parser.add_argument("--log-file", type=Path)
    parser.add_argument("--log-level", default="INFO")
    parser.add_argument("--log-console", action="store_true")
    parser.add_argument("--job-id")
    args = parser.parse_args()

    log_path = args.log_file or Path(args.output_dir) / "hwp_realtime_audit_watch.log"
    core.configure_logging(log_path, level=str(args.log_level), console=bool(args.log_console))
    report = run_realtime_watch(
        args.input_dir,
        args.output_dir,
        pattern=str(args.pattern),
        existing_policy=str(args.existing_policy),
        fidelity_policy=str(args.fidelity_policy),
        embed_original=not bool(args.no_embed_original),
        strict_quality=bool(args.strict_quality),
        require_identity=bool(args.require_identity),
        hwp5proc=args.hwp5proc,
        require_hwp5proc=bool(args.require_hwp5proc),
        openhwp_root=args.openhwp_root,
        require_openhwp=bool(args.require_openhwp),
        interval_sec=float(args.interval_sec),
        max_cycles=int(args.max_cycles) if args.max_cycles else None,
        audit_log=args.audit_log,
        audit_level=str(args.audit_level),
        summary_json=args.summary_json,
        summary_md=args.summary_md,
        job_id=args.job_id,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
