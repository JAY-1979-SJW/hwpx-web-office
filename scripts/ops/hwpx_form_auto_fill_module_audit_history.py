"""PII-safe module audit history helpers for HWPX form auto-fill gates."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPORT_DIR = Path("data") / "reports" / "hwpx_form_auto_fill_module_history"
COMM_MANIFEST = Path("scripts") / "ops" / "hwpx_form_auto_fill_module_communication_manifest.json"
ABS_PATH_RE = re.compile(r"(?<![A-Za-z])([A-Za-z]:[\\/][^\s\"']*|/(home|tmp|var|Users)/[^\s\"']*)")
RAW_FILENAME_RE = re.compile(r"\b[^\\/:\s]+\.hwpx\b", re.IGNORECASE)
PII_RE = re.compile(
    r"(\d{6}-\d{7}|\d{3}-\d{2}-\d{5}|\d{2,3}-\d{3,4}-\d{4}|"
    r"\d{2,6}-\d{2,6}-\d{2,6}|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})"
)


def _no_leak(text: str) -> bool:
    return not (ABS_PATH_RE.search(text) or RAW_FILENAME_RE.search(text) or PII_RE.search(text))


def _safe_summary(text: str) -> str:
    text = ABS_PATH_RE.sub("<abs-path>", text)
    text = RAW_FILENAME_RE.sub("<hwpx-file>", text)
    text = PII_RE.sub("<masked>", text)
    return text


def _module_zones(manifest_path: Path = COMM_MANIFEST) -> dict[str, str]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return {item["id"]: item["zone"] for item in manifest.get("modules", [])}


def build_history_entries(module_payload: dict[str, Any], run_id: str | None = None) -> list[dict[str, Any]]:
    """Convert module audit results to append-only safe history records."""
    run_id = run_id or datetime.now(UTC).strftime("run_%Y%m%dT%H%M%SZ")
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    zones = _module_zones()
    entries = []
    for item in module_payload.get("moduleResults", []):
        pytest = item.get("pytest", {})
        security = item.get("security", {})
        checks = {
            "staticStatus": item.get("staticStatus"),
            "pytestStatus": pytest.get("status"),
            "missingFiles": len(item.get("missingFiles", [])),
            "missingTokens": len(item.get("missingTokens", [])),
            "forbiddenSourceHits": len(item.get("forbiddenSourceHits", [])),
        }
        safe_security = {
            "piiLeak": security.get("piiLeak", 0),
            "rawPathLeak": security.get("rawPathLeak", 0),
            "rawFilenameLeak": security.get("rawFilenameLeak", 0),
        }
        entries.append(
            {
                "schemaVersion": "hwpx_form_auto_fill_module_audit_history_v1",
                "runId": run_id,
                "timestampUtc": timestamp,
                "moduleId": item.get("id"),
                "zone": zones.get(item.get("id"), "unknown"),
                "verdict": item.get("status"),
                "status": item.get("status"),
                "staticStatus": item.get("staticStatus"),
                "pytestStatus": pytest.get("status"),
                "durationSeconds": pytest.get("durationSeconds"),
                "attempts": pytest.get("attempts"),
                "summary": _safe_summary(str(pytest.get("summary", ""))),
                "checks": checks,
                "security": safe_security,
                "missingFiles": checks["missingFiles"],
                "missingTokens": checks["missingTokens"],
                "forbiddenSourceHits": checks["forbiddenSourceHits"],
                "piiLeak": safe_security["piiLeak"],
                "rawPathLeak": safe_security["rawPathLeak"],
                "rawFilenameLeak": safe_security["rawFilenameLeak"],
            }
        )
    return entries


def write_history(
    module_payload: dict[str, Any],
    report_dir: Path = REPORT_DIR,
    run_id: str | None = None,
    append: bool = True,
) -> dict[str, Any]:
    report_dir.mkdir(parents=True, exist_ok=True)
    entries = build_history_entries(module_payload, run_id=run_id)
    history_path = report_dir / "module_audit_history.jsonl"
    mode = "a" if append and history_path.exists() else "w"
    with history_path.open(mode, encoding="utf-8") as handle:
        for entry in entries:
            line = json.dumps(entry, ensure_ascii=False)
            if not _no_leak(line):
                raise ValueError("unsafe module history entry")
            handle.write(line + "\n")

    summary = {
        "schemaVersion": "hwpx_form_auto_fill_module_audit_history_summary_v1",
        "runId": entries[0]["runId"] if entries else run_id,
        "entriesWritten": len(entries),
        "modulesPassed": sum(1 for entry in entries if entry["status"] == "PASS"),
        "modulesFailed": sum(1 for entry in entries if entry["status"] != "PASS"),
        "piiLeak": sum(int(entry["piiLeak"]) for entry in entries),
        "rawPathLeak": sum(int(entry["rawPathLeak"]) for entry in entries),
        "rawFilenameLeak": sum(int(entry["rawFilenameLeak"]) for entry in entries),
    }
    text = json.dumps(summary, ensure_ascii=False, indent=2)
    if not _no_leak(text):
        raise ValueError("unsafe module history summary")
    (report_dir / "module_audit_history_summary.json").write_text(text, encoding="utf-8")
    return summary
