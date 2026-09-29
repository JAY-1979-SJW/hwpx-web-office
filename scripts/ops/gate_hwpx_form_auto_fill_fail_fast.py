"""Fail-fast integrated gate for HWPX form auto-fill operations."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.ops import audit_hwpx_form_auto_fill_construction_work_design as construction_audit
from scripts.ops import audit_hwpx_form_auto_fill_modules as module_audit
from scripts.ops import build_hwpx_form_auto_fill_gate_dashboard as dashboard_builder
from scripts.ops import build_hwpx_repo_manifest_promotion_candidates as manifest_promotion_builder
from scripts.ops import build_hwpx_repo_separation_execution_plan_draft as execution_plan_draft
from scripts.ops import build_hwpx_repo_separation_owner_review as owner_review_builder
from scripts.ops import gate_hwpx_form_auto_fill_module_log_contract as module_log_contract
from scripts.ops import gate_hwpx_form_auto_fill_upload as upload_gate
from scripts.ops import gate_hwpx_repo_classification_contract as repo_classification_contract_gate
from scripts.ops import (
    gate_hwpx_repo_existing_file_classification as existing_file_classification_gate,
)
from scripts.ops import gate_hwpx_repo_manifest_drift_zero as manifest_drift_zero_gate
from scripts.ops import gate_hwpx_repo_new_file_classification as new_file_classification_gate
from scripts.ops import gate_hwpx_repo_separation_approval_decision as approval_decision_gate
from scripts.ops import gate_hwpx_repo_separation_execution as separation_execution_gate
from scripts.ops import (
    gate_hwpx_repo_separation_final_execution_approval as final_execution_approval_gate,
)
from scripts.ops import hwpx_form_auto_fill_module_audit_history as history
from scripts.ops import install_hwpx_form_auto_fill_persistent_gates as persistent
from scripts.ops import plan_hwpx_repo_detailed_separation as separation_plan

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
        failed_modules = [
            module_id for module_id in zone["modules"] if module_status.get(module_id) != "PASS"
        ]
        zone_results.append({
            "id": zone["id"],
            "status": "PASS" if not failed_modules else "FAIL",
            "modules": zone["modules"],
            "failedModules": failed_modules,
        })
    failed = [item for item in zone_results if item["status"] != "PASS"]
    return {
        "verdict": "PASS_HWPX_FORM_AUTO_FILL_ZONE_GATES"
        if not failed
        else "FAIL_HWPX_FORM_AUTO_FILL_ZONE_GATES",
        "summary": {
            "zonesTotal": len(zone_results),
            "zonesPassed": len(zone_results) - len(failed),
            "zonesFailed": len(failed),
        },
        "zoneResults": zone_results,
    }


def _build_uniform_stages(
    *,
    report_dir: Path,
    run_id: str,
    canonical_report_dir: bool,
    module_payload: dict[str, Any],
) -> list[tuple[str, str, str, Callable[[dict[str, Any]], dict[str, Any]]]]:
    """Stage table for the gates that share the call/step/early-return shape.

    Each entry is (payload_key, step_name, fail_code, compute(payloads)). `compute`
    receives the payloads accumulated so far, so later stages can read their
    dependencies (e.g. manifest_drift_zero needs the classification contract).
    """
    return [
        (
            "module_log_contract_payload",
            "module_log_contract",
            "FAIL_MODULE_LOG_CONTRACT",
            lambda payloads: module_log_contract.run_module_log_contract_gate(
                report_dir=_output_dir(
                    report_dir,
                    "module_log_contract",
                    Path("data") / "reports" / "hwpx_form_auto_fill_module_log_contract",
                ),
                module_payload=module_payload,
                run_id=run_id,
            ),
        ),
        (
            "repo_classification_contract_payload",
            "repo_classification_contract",
            "FAIL_REPO_CLASSIFICATION_CONTRACT",
            lambda payloads: (
                repo_classification_contract_gate.run_repo_classification_contract_gate(
                    report_dir=_output_dir(
                        report_dir,
                        "repo_classification_contract",
                        Path("data") / "reports" / "hwpx_repo_classification_contract_gate",
                    ),
                    new_files=None if canonical_report_dir else [],
                )
            ),
        ),
        (
            "manifest_promotion_payload",
            "repo_manifest_promotion_candidates",
            "FAIL_REPO_MANIFEST_PROMOTION_CANDIDATES",
            lambda payloads: manifest_promotion_builder.build_manifest_promotion_candidates(
                report_dir=_output_dir(
                    report_dir,
                    "repo_manifest_promotion_candidates",
                    Path("data") / "reports" / "hwpx_repo_manifest_promotion_candidates",
                ),
                contract_payload=payloads["repo_classification_contract_payload"],
            ),
        ),
        (
            "manifest_drift_zero_payload",
            "repo_manifest_drift_zero",
            "FAIL_REPO_MANIFEST_DRIFT_ZERO",
            lambda payloads: manifest_drift_zero_gate.run_manifest_drift_zero_gate(
                report_dir=_output_dir(
                    report_dir,
                    "repo_manifest_drift_zero",
                    Path("data") / "reports" / "hwpx_repo_manifest_drift_zero_gate",
                ),
                contract_payload=payloads["repo_classification_contract_payload"],
                promotion_payload=payloads["manifest_promotion_payload"],
            ),
        ),
        (
            "existing_file_gate_payload",
            "repo_existing_file_classification",
            "FAIL_REPO_EXISTING_FILE_CLASSIFICATION",
            lambda payloads: (
                existing_file_classification_gate.run_existing_file_classification_gate(
                    report_dir=_output_dir(
                        report_dir,
                        "existing_file_classification",
                        Path("data") / "reports" / "hwpx_repo_existing_file_classification",
                    )
                )
            ),
        ),
        (
            "new_file_gate_payload",
            "repo_new_file_classification",
            "FAIL_REPO_NEW_FILE_CLASSIFICATION",
            lambda payloads: new_file_classification_gate.run_new_file_classification_gate(
                report_dir=_output_dir(
                    report_dir,
                    "new_file_classification",
                    Path("data") / "reports" / "hwpx_repo_new_file_classification",
                ),
                new_files=None if canonical_report_dir else [],
            ),
        ),
        (
            "zone_payload",
            "zone_gates_from_module_audit",
            "FAIL_ZONE_GATE",
            lambda payloads: _evaluate_zones_from_module_audit(module_payload),
        ),
        (
            "upload_payload",
            "upload_gate",
            "FAIL_UPLOAD_GATE",
            lambda payloads: upload_gate.run_upload_gate_scenarios(
                report_dir=_output_dir(
                    report_dir,
                    "upload_gate",
                    Path("data") / "reports" / "hwpx_form_auto_fill_upload_gate",
                )
            ),
        ),
        (
            "construction_payload",
            "construction_design_audit",
            "FAIL_CONSTRUCTION_DESIGN_AUDIT",
            lambda payloads: construction_audit.audit(),
        ),
        (
            "separation_payload",
            "repo_detailed_separation_plan",
            "FAIL_REPO_DETAILED_SEPARATION_PLAN",
            lambda payloads: separation_plan.plan_detailed_separation(
                report_dir=_output_dir(
                    report_dir,
                    "detailed_separation_plan",
                    Path("data") / "reports" / "hwpx_repo_detailed_separation_plan",
                )
            ),
        ),
        (
            "execution_payload",
            "repo_separation_execution_gate",
            "FAIL_REPO_SEPARATION_EXECUTION_GATE",
            lambda payloads: separation_execution_gate.run_execution_gate(
                report_dir=_output_dir(
                    report_dir,
                    "separation_execution_gate",
                    Path("data") / "reports" / "hwpx_repo_separation_execution_gate",
                )
            ),
        ),
        (
            "owner_review_payload",
            "repo_separation_owner_review",
            "FAIL_REPO_SEPARATION_OWNER_REVIEW",
            lambda payloads: owner_review_builder.build_owner_review_packets(
                report_dir=_output_dir(
                    report_dir,
                    "separation_owner_review",
                    Path("data") / "reports" / "hwpx_repo_separation_owner_review",
                )
            ),
        ),
        (
            "approval_decision_payload",
            "repo_separation_approval_decision",
            "FAIL_REPO_SEPARATION_APPROVAL_DECISION",
            lambda payloads: approval_decision_gate.run_approval_decision_gate(
                report_dir=_output_dir(
                    report_dir,
                    "separation_approval_decision",
                    Path("data") / "reports" / "hwpx_repo_separation_approval_decision",
                )
            ),
        ),
        (
            "execution_plan_payload",
            "repo_separation_execution_plan_draft",
            "FAIL_REPO_SEPARATION_EXECUTION_PLAN_DRAFT",
            lambda payloads: execution_plan_draft.build_execution_plan_draft(
                report_dir=_output_dir(
                    report_dir,
                    "separation_execution_plan_draft",
                    Path("data") / "reports" / "hwpx_repo_separation_execution_plan_draft",
                )
            ),
        ),
        (
            "final_execution_approval_payload",
            "repo_separation_final_execution_approval",
            "FAIL_REPO_SEPARATION_FINAL_EXECUTION_APPROVAL",
            lambda payloads: final_execution_approval_gate.run_final_execution_approval_gate(
                report_dir=_output_dir(
                    report_dir,
                    "final_exec_approval",
                    Path("data") / "reports" / "hwpx_repo_separation_final_execution_approval",
                )
            ),
        ),
    ]


def run_fail_fast_gate(
    report_dir: Path = REPORT_DIR, full_module_audit: bool = True
) -> dict[str, Any]:
    report_dir.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(UTC).strftime("ff_%Y%m%dT%H%M%SZ")
    canonical_report_dir = report_dir == REPORT_DIR
    steps: list[dict[str, Any]] = []
    payloads: dict[str, Any] = {}

    persistent_payload = persistent.install_persistent_gates(
        report_dir=report_dir / "persistent_gates",
        run_smoke=not full_module_audit,
    )
    steps.append(
        _step(
            "persistent_gate_installation",
            persistent_payload["verdict"],
            "FAIL_PERSISTENT_GATE_INSTALLATION",
        )
    )
    if steps[-1]["status"] != "PASS":
        return _finish(report_dir, run_id, steps, payloads)

    if full_module_audit:
        module_payload = module_audit.run_module_audits(
            report_dir=report_dir / "module_audits",
            module_ids=None,
            timeout=300,
            combined_pytest=False,
        )
    else:
        module_payload = _module_payload_from_persistent_smoke(persistent_payload)
    payloads["module_payload"] = module_payload
    steps.append(_step("module_audits", module_payload["verdict"], "FAIL_MODULE_AUDIT"))
    history_summary = history.write_history(
        module_payload,
        report_dir=_output_dir(
            report_dir,
            "module_history",
            Path("data") / "reports" / "hwpx_form_auto_fill_module_history",
        ),
        run_id=run_id,
        append=True,
    )
    payloads["history_summary"] = history_summary
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
        return _finish(report_dir, run_id, steps, payloads)

    stages = _build_uniform_stages(
        report_dir=report_dir,
        run_id=run_id,
        canonical_report_dir=canonical_report_dir,
        module_payload=module_payload,
    )
    for key, name, fail_code, compute in stages:
        payload = compute(payloads)
        payloads[key] = payload
        steps.append(_step(name, payload["verdict"], fail_code))
        if steps[-1]["status"] != "PASS":
            return _finish(report_dir, run_id, steps, payloads)

    preliminary = _finish(report_dir, run_id, steps, payloads)
    dashboard = dashboard_builder.build_dashboard(
        preliminary,
        payloads.get("upload_payload"),
        history_summary,
        report_dir=_output_dir(
            report_dir,
            "gate_dashboard",
            Path("data") / "reports" / "hwpx_form_auto_fill_gate_dashboard",
        ),
    )
    payloads["dashboard"] = dashboard
    steps.append(_step("gate_dashboard", dashboard["verdict"], "FAIL_GATE_DASHBOARD"))
    return _finish(report_dir, run_id, steps, payloads)


def _module_payload_from_persistent_smoke(persistent_payload: dict[str, Any]) -> dict[str, Any]:
    smoke = persistent_payload.get("smokeRuns", {}).get("moduleAudit") or {}
    verdict = smoke.get("verdict")
    status = "PASS" if verdict == module_audit.PASS_VERDICT else "FAIL"
    return {
        "schemaVersion": "hwpx_form_auto_fill_module_audits_v1",
        "verdict": verdict or module_audit.FAIL_VERDICT,
        "summary": smoke.get(
            "summary", {"modulesTotal": 1, "modulesPassed": 0, "modulesFailed": 1}
        ),
        "moduleResults": [
            {
                "id": "field_mapping",
                "title": "Field mapping",
                "status": status,
                "staticStatus": status,
                "pytest": {
                    "status": status,
                    "returncode": 0 if status == "PASS" else 1,
                    "attempts": 1,
                    "durationSeconds": 0.0,
                    "summary": "reused persistent representative module audit smoke",
                },
                "missingFiles": [],
                "missingTokens": [],
                "forbiddenSourceHits": [],
                "security": {
                    "piiLeak": 0,
                    "rawPathLeak": 0,
                    "rawFilenameLeak": 0,
                },
            }
        ],
        "dirtyBaseline": {
            "documented": True,
            "trackedDirty": [],
            "untrackedCount": 0,
        },
        "warnings": [
            "WARN_SANDBOX_ONLY",
            "WARN_REAL_USER_FILE_NOT_TESTED",
            "WARN_DEPLOY_NOT_PERFORMED",
        ],
    }


def _finish(
    report_dir: Path,
    run_id: str,
    steps: list[dict[str, Any]],
    payloads: dict[str, Any],
) -> dict[str, Any]:
    module_payload = payloads.get("module_payload")
    zone_payload = payloads.get("zone_payload")
    upload_payload = payloads.get("upload_payload")
    history_summary = payloads.get("history_summary")
    separation_payload = payloads.get("separation_payload")
    execution_payload = payloads.get("execution_payload")
    owner_review_payload = payloads.get("owner_review_payload")
    approval_decision_payload = payloads.get("approval_decision_payload")
    execution_plan_payload = payloads.get("execution_plan_payload")
    final_execution_approval_payload = payloads.get("final_execution_approval_payload")
    dashboard = payloads.get("dashboard")
    module_log_contract_payload = payloads.get("module_log_contract_payload")
    repo_classification_contract_payload = payloads.get("repo_classification_contract_payload")
    manifest_promotion_payload = payloads.get("manifest_promotion_payload")
    manifest_drift_zero_payload = payloads.get("manifest_drift_zero_payload")
    existing_file_gate_payload = payloads.get("existing_file_gate_payload")
    new_file_gate_payload = payloads.get("new_file_gate_payload")

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
        "moduleLogContractSummary": (module_log_contract_payload or {}).get("summary"),
        "moduleLogContractVerdict": (module_log_contract_payload or {}).get("verdict"),
        "repoClassificationContractSummary": (repo_classification_contract_payload or {}).get(
            "summary"
        ),
        "repoClassificationContractVerdict": (repo_classification_contract_payload or {}).get(
            "verdict"
        ),
        "repoManifestPromotionSummary": (manifest_promotion_payload or {}).get("summary"),
        "repoManifestPromotionVerdict": (manifest_promotion_payload or {}).get("verdict"),
        "repoManifestDriftZeroSummary": (manifest_drift_zero_payload or {}).get("summary"),
        "repoManifestDriftZeroVerdict": (manifest_drift_zero_payload or {}).get("verdict"),
        "existingFileClassificationSummary": (existing_file_gate_payload or {}).get("summary"),
        "existingFileClassificationVerdict": (existing_file_gate_payload or {}).get("verdict"),
        "newFileClassificationSummary": (new_file_gate_payload or {}).get("summary"),
        "newFileClassificationVerdict": (new_file_gate_payload or {}).get("verdict"),
        "separationSummary": (separation_payload or {}).get("summary"),
        "separationVerdict": (separation_payload or {}).get("verdict"),
        "separationExecutionSummary": (execution_payload or {}).get("summary"),
        "separationExecutionVerdict": (execution_payload or {}).get("verdict"),
        "separationOwnerReviewSummary": (owner_review_payload or {}).get("summary"),
        "separationOwnerReviewVerdict": (owner_review_payload or {}).get("verdict"),
        "separationApprovalDecisionSummary": (approval_decision_payload or {}).get("summary"),
        "separationApprovalDecisionVerdict": (approval_decision_payload or {}).get("verdict"),
        "separationExecutionPlanSummary": (execution_plan_payload or {}).get("summary"),
        "separationExecutionPlanVerdict": (execution_plan_payload or {}).get("verdict"),
        "separationFinalExecutionApprovalSummary": (final_execution_approval_payload or {}).get(
            "summary"
        ),
        "separationFinalExecutionApprovalVerdict": (final_execution_approval_payload or {}).get(
            "verdict"
        ),
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
    lines.extend(f"- {step['status']} {step['name']} {step['verdict']}" for step in payload["steps"])
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
    parser.add_argument(
        "--smoke-only", action="store_true", help="Run representative module audit only."
    )
    args = parser.parse_args()
    payload = run_fail_fast_gate(
        report_dir=Path(args.report_dir), full_module_audit=not args.smoke_only
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["verdict"] == PASS_VERDICT else 1


if __name__ == "__main__":
    raise SystemExit(main())
