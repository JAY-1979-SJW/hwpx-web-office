"""Contract gate for PII-safe module audit history logs."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.ops import audit_hwpx_form_auto_fill_modules as module_audit  # ruff: ignore[module-import-not-at-top-of-file]
from scripts.ops import hwpx_form_auto_fill_module_audit_history as history  # ruff: ignore[module-import-not-at-top-of-file]

REPORT_DIR = ROOT / "data" / "reports" / "hwpx_form_auto_fill_module_log_contract"
DEFAULT_MODULE_AUDIT_REPORT = (
    ROOT / "data" / "reports" / "hwpx_form_auto_fill_module_audits" / "module_audit_summary.json"
)
PASS_VERDICT = "PASS_HWPX_FORM_AUTO_FILL_MODULE_LOG_CONTRACT"
FAIL_VERDICT = "FAIL_HWPX_FORM_AUTO_FILL_MODULE_LOG_CONTRACT"

FAIL_MISSING_MODULE_LOG = "FAIL_MISSING_MODULE_LOG"
FAIL_MISSING_REQUIRED_FIELD = "FAIL_MISSING_REQUIRED_FIELD"
FAIL_INVALID_MODULE_ZONE = "FAIL_INVALID_MODULE_ZONE"
FAIL_FAILED_MODULE_LOGGED_PASS = "FAIL_FAILED_MODULE_LOGGED_PASS"
FAIL_SECURITY_LEAK_IN_LOG = "FAIL_SECURITY_LEAK_IN_LOG"
FAIL_INVALID_SECURITY_FIELDS = "FAIL_INVALID_SECURITY_FIELDS"
FAIL_UNSAFE_REPORT = "FAIL_UNSAFE_REPORT"

REQUIRED_FIELDS = [
    "schemaVersion",
    "runId",
    "timestampUtc",
    "moduleId",
    "zone",
    "verdict",
    "status",
    "checks",
    "security",
]
REQUIRED_CHECK_FIELDS = [
    "staticStatus",
    "pytestStatus",
    "missingFiles",
    "missingTokens",
    "forbiddenSourceHits",
]
REQUIRED_SECURITY_FIELDS = ["piiLeak", "rawPathLeak", "rawFilenameLeak"]

ABS_PATH_RE = history.ABS_PATH_RE
RAW_FILENAME_RE = history.RAW_FILENAME_RE
PII_RE = history.PII_RE
TIMESTAMP_RE = re.compile(r"^\d{8}T\d{6}Z$")


def _communication_zones() -> dict[str, str]:
    manifest = json.loads(history.COMM_MANIFEST.read_text(encoding="utf-8"))
    return {item["id"]: item["zone"] for item in manifest.get("modules", [])}


def _expected_modules(module_payload: dict[str, Any] | None) -> set[str]:
    if module_payload is not None:
        return {item["id"] for item in module_payload.get("moduleResults", [])}
    manifest = module_audit.load_manifest()
    return {item["id"] for item in manifest.get("modules", [])}


def _check_required_top_fields(entry: dict[str, Any]) -> list[str]:
    return [
        f"{FAIL_MISSING_REQUIRED_FIELD}:{field}" for field in REQUIRED_FIELDS if field not in entry
    ]


def _check_zone_and_status(entry: dict[str, Any], zone_by_module: dict[str, str]) -> list[str]:
    failures: list[str] = []
    module_id = entry.get("moduleId")
    if zone_by_module.get(module_id) != entry.get("zone"):
        failures.append(FAIL_INVALID_MODULE_ZONE)
    if entry.get("status") != entry.get("verdict"):
        failures.append(FAIL_FAILED_MODULE_LOGGED_PASS)
    if entry.get("status") not in {"PASS", "FAIL"}:
        failures.append(FAIL_FAILED_MODULE_LOGGED_PASS)
    if not TIMESTAMP_RE.match(str(entry.get("timestampUtc", ""))):
        failures.append("FAIL_INVALID_TIMESTAMP")
    return failures


def _check_checks_field(entry: dict[str, Any]) -> list[str]:
    checks = entry.get("checks", {})
    if not isinstance(checks, dict):
        return [f"{FAIL_MISSING_REQUIRED_FIELD}:checks"]
    return [
        f"{FAIL_MISSING_REQUIRED_FIELD}:checks.{field}"
        for field in REQUIRED_CHECK_FIELDS
        if field not in checks
    ]


def _check_security_field(entry: dict[str, Any]) -> list[str]:
    security = entry.get("security", {})
    if not isinstance(security, dict):
        return [FAIL_INVALID_SECURITY_FIELDS]
    failures: list[str] = []
    for field in REQUIRED_SECURITY_FIELDS:
        if field not in security:
            failures.append(f"{FAIL_MISSING_REQUIRED_FIELD}:security.{field}")
        elif int(security[field]) != 0:
            failures.append(FAIL_SECURITY_LEAK_IN_LOG)
    return failures


def _validate_entry(entry: dict[str, Any], zone_by_module: dict[str, str]) -> list[str]:
    failures: list[str] = []
    failures.extend(_check_required_top_fields(entry))
    failures.extend(_check_zone_and_status(entry, zone_by_module))
    failures.extend(_check_checks_field(entry))
    failures.extend(_check_security_field(entry))
    return failures


def _no_leak(text: str) -> bool:
    return not (ABS_PATH_RE.search(text) or RAW_FILENAME_RE.search(text) or PII_RE.search(text))


def validate_module_log_contract(
    entries: list[dict[str, Any]],
    module_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    expected = _expected_modules(module_payload)
    zone_by_module = _communication_zones()
    module_ids = {entry.get("moduleId") for entry in entries}
    missing = sorted(expected - module_ids)
    failures = [FAIL_MISSING_MODULE_LOG for _ in missing]
    entry_results = []
    for entry in entries:
        entry_failures = _validate_entry(entry, zone_by_module)
        text = json.dumps(entry, ensure_ascii=False)
        if not _no_leak(text):
            entry_failures.append(FAIL_SECURITY_LEAK_IN_LOG)
        entry_results.append({
            "moduleId": entry.get("moduleId"),
            "zone": entry.get("zone"),
            "status": "PASS" if not entry_failures else "FAIL",
            "failures": sorted(set(entry_failures)),
        })
        failures.extend(entry_failures)

    failures = sorted(set(failures))
    return {
        "schemaVersion": "hwpx_form_auto_fill_module_log_contract_v1",
        "verdict": PASS_VERDICT if not failures else FAIL_VERDICT,
        "runId": entries[0].get("runId")
        if entries
        else datetime.now(UTC).strftime("run_%Y%m%dT%H%M%SZ"),
        "summary": {
            "expectedModules": len(expected),
            "loggedModules": len(module_ids),
            "missingModuleLogs": len(missing),
            "entries": len(entries),
            "entriesPassed": sum(1 for item in entry_results if item["status"] == "PASS"),
            "entriesFailed": sum(1 for item in entry_results if item["status"] != "PASS"),
        },
        "requiredFields": REQUIRED_FIELDS,
        "entryResults": entry_results,
        "missingModuleIds": missing,
        "failures": failures,
        "security": {
            "piiLeak": 0 if FAIL_SECURITY_LEAK_IN_LOG not in failures else 1,
            "rawPathLeak": 0 if FAIL_SECURITY_LEAK_IN_LOG not in failures else 1,
            "rawFilenameLeak": 0 if FAIL_SECURITY_LEAK_IN_LOG not in failures else 1,
        },
        "warnings": [
            "WARN_MODULE_LOG_CONTRACT_ONLY",
            "WARN_RUN_ID_LOGS_NOT_COMMITTED",
        ],
    }


def run_module_log_contract_gate(
    report_dir: Path = REPORT_DIR,
    module_payload: dict[str, Any] | None = None,
    entries: list[dict[str, Any]] | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    if module_payload is None:
        if DEFAULT_MODULE_AUDIT_REPORT.is_file():
            module_payload = json.loads(DEFAULT_MODULE_AUDIT_REPORT.read_text(encoding="utf-8"))
        else:
            module_payload = module_audit.run_module_audits(
                report_dir=report_dir / "module_audit_subrun",
                module_ids={"field_mapping"},
                combined_pytest=False,
            )
    if entries is None:
        entries = history.build_history_entries(module_payload, run_id=run_id)
    payload = validate_module_log_contract(entries, module_payload=module_payload)
    _write_reports(report_dir, payload)
    return payload


def _safe_write(path: Path, payload: Any) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if not _no_leak(text):
        raise ValueError(f"{FAIL_UNSAFE_REPORT}: {path.name}")
    path.write_text(text, encoding="utf-8")


def _write_reports(report_dir: Path, payload: dict[str, Any]) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    _safe_write(report_dir / "module_log_contract_summary.json", payload)
    _safe_write(report_dir / "module_log_contract_matrix.json", payload["entryResults"])
    lines = [
        "# HWPX Form Auto Fill Module Log Contract",
        "",
        f"- verdict: {payload['verdict']}",
        f"- expectedModules: {payload['summary']['expectedModules']}",
        f"- loggedModules: {payload['summary']['loggedModules']}",
        f"- missingModuleLogs: {payload['summary']['missingModuleLogs']}",
        f"- entriesPassed: {payload['summary']['entriesPassed']}",
        f"- entriesFailed: {payload['summary']['entriesFailed']}",
        f"- security: pii={payload['security']['piiLeak']} rawPath={payload['security']['rawPathLeak']} rawFilename={payload['security']['rawFilenameLeak']}",
        "",
        "## Contract",
        "- module audit history entries require moduleId, zone, verdict, runId, timestampUtc, checks, and security",
        "- module logs must not contain raw path, raw filename, or PII patterns",
        "- missing module logs fail the gate",
    ]
    text = "\n".join(lines) + "\n"
    if not _no_leak(text):
        raise ValueError(FAIL_UNSAFE_REPORT)
    (report_dir / "module_log_contract_summary.md").write_text(text, encoding="utf-8")


def _load_entries(path: str | None) -> list[dict[str, Any]] | None:
    if not path:
        return None
    content = Path(path).read_text(encoding="utf-8")
    if path.endswith(".jsonl"):
        return [json.loads(line) for line in content.splitlines() if line.strip()]
    return json.loads(content)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", default=str(REPORT_DIR))
    parser.add_argument("--entries-json")
    args = parser.parse_args()
    payload = run_module_log_contract_gate(
        report_dir=Path(args.report_dir), entries=_load_entries(args.entries_json)
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["verdict"] == PASS_VERDICT else 1


if __name__ == "__main__":
    raise SystemExit(main())
