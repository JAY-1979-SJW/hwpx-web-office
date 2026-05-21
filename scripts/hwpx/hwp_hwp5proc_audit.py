"""Optional hwp5proc-backed audit helpers for HWP source files."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Iterable


DEFAULT_RECORD_STREAMS = ("DocInfo", "BodyText/Section0")


def run_hwp5proc_records(
    hwp5proc: Path,
    source: Path,
    *,
    stream: str = "BodyText/Section0",
    limit_lines: int = 200,
    timeout_sec: float = 30.0,
) -> dict[str, Any]:
    command = [str(hwp5proc), "records", str(source), stream]
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_sec,
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "FAIL",
            "stream": stream,
            "error": type(exc).__name__,
            "message": str(exc),
            "command": command,
        }
    lines = (proc.stdout or "").splitlines()
    return {
        "status": "PASS" if proc.returncode in {0, 1} and lines else "FAIL",
        "stream": stream,
        "returncode": proc.returncode,
        "line_count": len(lines),
        "head": lines[:limit_lines],
        "stderr_tail": (proc.stderr or "")[-1000:],
        "command": command,
    }


def audit_hwp5proc_records(
    hwp5proc: Path | None,
    source: Path,
    *,
    streams: Iterable[str] = DEFAULT_RECORD_STREAMS,
    limit_lines: int = 80,
    timeout_sec: float = 30.0,
) -> dict[str, Any]:
    if not hwp5proc:
        return {"enabled": False, "status": "SKIPPED", "reason": "HWP5PROC_NOT_CONFIGURED"}
    hwp5proc = Path(hwp5proc).expanduser().resolve()
    if not hwp5proc.exists():
        return {
            "enabled": False,
            "status": "SKIPPED",
            "reason": "HWP5PROC_NOT_FOUND",
            "hwp5proc": str(hwp5proc),
        }
    source = Path(source).expanduser().resolve()
    if not source.exists():
        return {
            "enabled": True,
            "status": "FAIL",
            "reason": "SOURCE_NOT_FOUND",
            "hwp5proc": str(hwp5proc),
            "source": str(source),
        }
    results = [
        run_hwp5proc_records(
            hwp5proc,
            source,
            stream=stream,
            limit_lines=limit_lines,
            timeout_sec=timeout_sec,
        )
        for stream in streams
    ]
    pass_count = sum(1 for row in results if row.get("status") == "PASS")
    fail_count = len(results) - pass_count
    if pass_count == len(results):
        status = "PASS"
    elif pass_count:
        status = "WARN"
    else:
        status = "FAIL"
    return {
        "enabled": True,
        "status": status,
        "hwp5proc": str(hwp5proc),
        "source": str(source),
        "stream_count": len(results),
        "pass_count": pass_count,
        "fail_count": fail_count,
        "streams": results,
    }


def attach_hwp5proc_audit(
    result: dict[str, Any],
    *,
    hwp5proc: Path | None,
    require_hwp5proc: bool = False,
) -> dict[str, Any]:
    audited = dict(result)
    input_value = audited.get("input")
    if not input_value:
        audit = {"enabled": bool(hwp5proc), "status": "SKIPPED", "reason": "INPUT_MISSING"}
    else:
        audit = audit_hwp5proc_records(hwp5proc, Path(str(input_value)))
    audited["hwp5proc_status"] = audit.get("status")
    audited["hwp5proc_audit"] = audit
    if require_hwp5proc and audit.get("status") != "PASS":
        audited["status"] = "FAIL"
        audited["error"] = "HWP5PROC_AUDIT_FAILED"
    return audited
