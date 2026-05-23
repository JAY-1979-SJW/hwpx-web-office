"""Fail-fast integrated gate for HWPX form auto-fill operations."""

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

from scripts.ops import audit_hwpx_form_auto_fill_construction_work_design as construction_audit
from scripts.ops import audit_hwpx_form_auto_fill_modules as module_audit
from scripts.ops import build_hwpx_form_auto_fill_gate_dashboard as dashboard_builder
from scripts.ops import gate_hwpx_form_auto_fill_upload as upload_gate
from scripts.ops import hwpx_form_auto_fill_module_audit_history as history
from scripts.ops import install_hwpx_form_auto_fill_persistent_gates as persistent

REPORT_DIR = Path("data") / "reports" / "hwpx_form_auto_fill_fail_fast_gate"
PASS_VERDICT = "PASS_HWPX_FORM_AUTO_FILL_FAIL_FAST_GATE"
FAIL_VERDICT = "FAIL_HWPX_FORM_AUTO_FILL_FAIL_FAST_GATE"

ABS_PATH_RE = re.compile(r"(?<![A-Za-z])([A-Za-z]:[\\/][^\s\"']*|/(home|tmp|var|Users)/[^\s\"']*)")
RAW_FILENAME_RE = re.compile(r"\b[^\\/:\s]+\.hwpx\b", re.IGNORECASE)
PII_RE = re.compile(
    r"(\d{6}-\d{7}|\d{3}-\d{2}-\d{5}|\d{2,3}-\d{3,4}-\d{4}|"
    r"\d{2,6}-\d{2,6}-\d{2,6}|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})"
)


def _no_leak(text: str) -> bool:
    return not (ABS_PATH_RE.search(text) or RAW_FILENAME_RE.search(text) or PII_RE.search(text))


def _step(name: str, verdict: str, fail_code: str | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "verdict": verdict,
        "status": "PASS" if verdict.startswith("PASS") else "FAIL",
        "failCode": None if verdict.startswith("PASS") else fail_code,
    }


def _output_dir(report_dir: Path, subdir: str, canonical: Path) -> Path:
    return canonical if report_dir == REPORT_DIR else report_dir / subdir


def _evaluate_zones_from_module_audit(module_payload: dict[str, Any]) -> dict[str, Any]:
    zone_manifest = persistent.zone_gate.load_manifest()
    module_status = {item["id"]: item["status"] for item in module_payload.get("moduleResults", [])}
    zone_results = []
    for zone in zone_manifest["zones"]:
        if not set(zone["modules"]).issubset(module_status):
            continue
        failed_modules = [module_id for module_id in zone["modules"] if module_status.get(module_id) != "PASS"]
        zone_results.append(
            {
                "id": zone["id"],
                "status": "PASS" if not failed_modules else "FAIL",
                "modules": zone["modules"],
                "failedModules": failed_modules,
            }
        )
    failed = [item for item in zone_results if item["status"] != "PASS"]
    return {
        "verdict": "PASS_HWPX_FORM_AUTO_FILL_ZONE_GATES" if not failed else "FAIL_HWPX_FORM_AUTO_FILL_ZONE_GATES",
        "summary": {
            "zonesTotal": len(zone_results),
            "zonesPassed": len(zone_results) - len(failed),
            "zonesFailed": len(failed),
        },
        "zoneResults": zone_results,
    }


def run_fail_fast_gate(report_dir: Path = REPORT_DIR, full_module_audit: bool = True) -> dict[str, Any]:
    report_dir.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(UTC).strftime("ff_%Y%m%dT%H%M%SZ")
    steps: list[dict[str, Any]] = []

    persistent_payload = persistent.install_persistent_gates(
        report_dir=report_dir / "persistent_gates",
        run_smoke=not full_module_audit,
    )
    steps.append(_step("persistent_gate_installation", persistent_payload["verdict"], "FAIL_PERSISTENT_GATE_INSTALLATION"))
    if steps[-1]["status"] != "PASS":
        return _finish(report_dir, run_id, steps, None, None, None, None, None)

    module_ids = None if full_module_audit else {"field_mapping"}
    module_payload = module_audit.run_module_audits(
        report_dir=report_dir / "module_audits",
        module_ids=module_ids,
        timeout=300,
        combined_pytest=False,
    )
    steps.append(_step("module_audits", module_payload["verdict"], "FAIL_MODULE_AUDIT"))
    history_summary = history.write_history(
        module_payload,
        report_dir=_output_dir(report_dir, "module_history", Path("data") / "reports" / "hwpx_form_auto_fill_module_history"),
        run_id=run_id,
        append=True,
    )
    steps.append(
        _step(
            "module_audit_history",
            "PASS_HWPX_FORM_AUTO_FILL_MODULE_AUDIT_HISTORY"
            if history_summary["modulesFailed"] == 0
            else "FAIL_HWPX_FORM_AUTO_FILL_MODULE_AUDIT_HISTORY",
            "FAIL_MODULE_AUDIT_HISTORY",
        )
    )
    if steps[-2]["status"] != "PASS" or steps[-1]["status"] != "PASS":
        return _finish(report_dir, run_id, steps, module_payload, None, None, history_summary, None)

    zone_payload = _evaluate_zones_from_module_audit(module_payload)
    steps.append(_step("zone_gates_from_module_audit", zone_payload["verdict"], "FAIL_ZONE_GATE"))
    if steps[-1]["status"] != "PASS":
        return _finish(report_dir, run_id, steps, module_payload, zone_payload, None, history_summary, None)

    upload_payload = upload_gate.run_upload_gate_scenarios(
        report_dir=_output_dir(report_dir, "upload_gate", Path("data") / "reports" / "hwpx_form_auto_fill_upload_gate")
    )
    steps.append(_step("upload_gate", upload_payload["verdict"], "FAIL_UPLOAD_GATE"))
    if steps[-1]["status"] != "PASS":
        return _finish(report_dir, run_id, steps, module_payload, zone_payload, upload_payload, history_summary, None)

    construction_payload = construction_audit.audit()
    steps.append(_step("construction_design_audit", construction_payload["verdict"], "FAIL_CONSTRUCTION_DESIGN_AUDIT"))
    if steps[-1]["status"] != "PASS":
        return _finish(report_dir, run_id, steps, module_payload, zone_payload, upload_payload, history_summary, None)

    preliminary = _finish(report_dir, run_id, steps, module_payload, zone_payload, upload_payload, history_summary, None)
    dashboard = dashboard_builder.build_dashboard(
        preliminary,
        upload_payload,
        history_summary,
        report_dir=_output_dir(report_dir, "gate_dashboard", Path("data") / "reports" / "hwpx_form_auto_fill_gate_dashboard"),
    )
    steps.append(_step("gate_dashboard", dashboard["verdict"], "FAIL_GATE_DASHBOARD"))
    return _finish(report_dir, run_id, steps, module_payload, zone_payload, upload_payload, history_summary, dashboard)


def _finish(
    report_dir: Path,
    run_id: str,
    steps: list[dict[str, Any]],
    module_payload: dict[str, Any] | None,
    zone_payload: dict[str, Any] | None,
    upload_payload: dict[str, Any] | None,
    history_summary: dict[str, Any] | None,
    dashboard: dict[str, Any] | None,
) -> dict[str, Any]:
    failed = [step for step in steps if step["status"] != "PASS"]
    payload = {
        "schemaVersion": "hwpx_form_auto_fill_fail_fast_gate_v1",
        "runId": run_id,
        "verdict": PASS_VERDICT if not failed else FAIL_VERDICT,
        "summary": {
            "stepsTotal": len(steps),
            "stepsPassed": len(steps) - len(failed),
            "stepsFailed": len(failed),
            "failedChecks": len(failed),
            "modules": (module_payload or {}).get("summary", {}).get("modulesTotal", 0),
            "zones": (zone_payload or {}).get("summary", {}).get("zonesTotal", 0),
        },
        "steps": steps,
        "moduleSummary": (module_payload or {}).get("summary"),
        "zoneSummary": (zone_payload or {}).get("summary"),
        "uploadSummary": (upload_payload or {}).get("summary"),
        "historySummary": history_summary,
        "dashboardVerdict": (dashboard or {}).get("verdict"),
        "security": {
            "piiLeak": 0,
            "rawPathLeak": 0,
            "rawFilenameLeak": 0,
            "aiApiCalled": False,
            "ocrCalled": False,
            "hancomRequired": False,
        },
        "warnings": [
            "WARN_SANDBOX_ONLY",
            "WARN_REAL_USER_FILE_NOT_TESTED",
            "WARN_DEPLOY_NOT_PERFORMED",
            "WARN_FAIL_FAST_REPO_GATE_ONLY",
        ],
    }
    _write_reports(report_dir, payload)
    return payload


def _write_reports(report_dir: Path, payload: dict[str, Any]) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    _safe_write(report_dir / "fail_fast_gate_summary.json", payload)
    _safe_write(report_dir / "fail_fast_gate_steps.json", payload["steps"])
    lines = [
        "# HWPX Form Auto Fill Fail Fast Gate",
        "",
        f"- verdict: {payload['verdict']}",
        f"- runId: {payload['runId']}",
        f"- steps: {payload['summary']['stepsPassed']}/{payload['summary']['stepsTotal']} passed",
        f"- modules: {payload['summary']['modules']}",
        f"- zones: {payload['summary']['zones']}",
        f"- security: pii={payload['security']['piiLeak']} rawPath={payload['security']['rawPathLeak']} rawFilename={payload['security']['rawFilenameLeak']}",
        "",
        "## Steps",
    ]
    for step in payload["steps"]:
        lines.append(f"- {step['status']} {step['name']} {step['verdict']}")
    text = "\n".join(lines) + "\n"
    if not _no_leak(text):
        raise ValueError("unsafe fail-fast markdown")
    (report_dir / "fail_fast_gate_summary.md").write_text(text, encoding="utf-8")


def _safe_write(path: Path, payload: Any) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if not _no_leak(text):
        raise ValueError(f"unsafe fail-fast payload: {path.name}")
    path.write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", default=str(REPORT_DIR))
    parser.add_argument("--smoke-only", action="store_true", help="Run representative module audit only.")
    args = parser.parse_args()
    payload = run_fail_fast_gate(report_dir=Path(args.report_dir), full_module_audit=not args.smoke_only)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["verdict"] == PASS_VERDICT else 1


if __name__ == "__main__":
    raise SystemExit(main())
