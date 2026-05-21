"""Write gate and audit logging for composed HWPX artifacts."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_write_audit_log_path(output_path: Path) -> Path:
    return Path(output_path).with_suffix(".hwpx_write_audit.jsonl")


def _check(name: str, passed: bool, **details: Any) -> dict[str, Any]:
    return {"name": name, "status": "PASS" if passed else "FAIL", **details}


def build_write_gate(report: dict[str, Any], output_path: Path) -> dict[str, Any]:
    validation = report.get("validation") if isinstance(report.get("validation"), dict) else {}
    schema = report.get("schema") if isinstance(report.get("schema"), dict) else {}
    expected_values = report.get("expected_values") if isinstance(report.get("expected_values"), list) else []
    warnings = report.get("warnings") if isinstance(report.get("warnings"), list) else []
    failed_steps = report.get("failed_steps") if isinstance(report.get("failed_steps"), list) else []
    output_path = Path(output_path)
    output_exists = output_path.exists()
    output_size = output_path.stat().st_size if output_exists else 0

    checks = [
        _check("schema_valid", schema.get("status") == "PASS", errors=schema.get("errors", [])),
        _check("output_written", output_exists and output_size > 0, output=str(output_path), size=output_size),
        _check("package_zip_valid", validation.get("zip_ok") is True, zip_ok=validation.get("zip_ok")),
        _check("package_xml_valid", validation.get("xml_ok") is True, xml_ok=validation.get("xml_ok")),
        _check("no_failed_steps", not failed_steps, failed_steps=failed_steps),
        _check("no_placeholders_remaining", validation.get("placeholder_remaining") is False, placeholder_remaining=validation.get("placeholder_remaining")),
        _check(
            "expected_values_present",
            not validation.get("missing_expected_values"),
            expected_count=len(expected_values),
            missing_expected_values=validation.get("missing_expected_values", []),
        ),
    ]
    failed = [check["name"] for check in checks if check["status"] != "PASS"]
    return {
        "status": "PASS" if not failed else "FAIL",
        "checked_at": utc_now_iso(),
        "output": str(output_path),
        "failed_checks": failed,
        "warning_count": len(warnings),
        "checks": checks,
    }


def write_write_audit_log(path: Path | None, report: dict[str, Any], *, event: str = "hwpx_write") -> str | None:
    if not path:
        return None
    path = Path(path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "event": event,
        "logged_at": utc_now_iso(),
        "status": report.get("status"),
        "template": report.get("template"),
        "output": report.get("output"),
        "step_count": len(report.get("steps", []) if isinstance(report.get("steps"), list) else []),
        "warning_count": len(report.get("warnings", []) if isinstance(report.get("warnings"), list) else []),
        "failed_step_count": len(report.get("failed_steps", []) if isinstance(report.get("failed_steps"), list) else []),
        "write_gate": report.get("write_gate"),
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    return str(path)


def resolve_audit_log_path(job: dict[str, Any], output_path: Path) -> Path | None:
    spec = job.get("write_audit_log", job.get("audit_log"))
    if spec is None:
        return None
    if isinstance(spec, bool):
        return default_write_audit_log_path(output_path) if spec else None
    if isinstance(spec, str):
        return Path(spec)
    if isinstance(spec, dict):
        if spec.get("enabled") is False:
            return None
        if spec.get("path"):
            return Path(str(spec["path"]))
        return default_write_audit_log_path(output_path)
    return None

