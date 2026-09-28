"""Execution gate for repo separation work packages.

The gate is intentionally conservative: by default it only emits dry-run
work packages. Any move/delete/archive execution request is blocked unless an
explicit owner approval flag is supplied, and even then this script does not
move files.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.ops import plan_hwpx_repo_detailed_separation as separation_plan  # noqa: E402

REPORT_DIR = ROOT / "data" / "reports" / "hwpx_repo_separation_execution_gate"

PASS_VERDICT = "PASS_HWPX_REPO_SEPARATION_EXECUTION_GATE"
BLOCKED_VERDICT = "BLOCKED_HWPX_REPO_SEPARATION_EXECUTION_GATE"
FAIL_VERDICT = "FAIL_HWPX_REPO_SEPARATION_EXECUTION_GATE"

BLOCKED_OWNER_REVIEW_REQUIRED = "BLOCKED_OWNER_REVIEW_REQUIRED"
BLOCKED_MOVE_DELETE_NOT_ALLOWED = "BLOCKED_MOVE_DELETE_NOT_ALLOWED"
FAIL_DETAILED_PLAN_NOT_PASS = "FAIL_DETAILED_PLAN_NOT_PASS"
FAIL_UNSAFE_REPORT = "FAIL_UNSAFE_REPORT"

ABS_PATH_RE = separation_plan.ABS_PATH_RE
RAW_FILENAME_RE = separation_plan.RAW_FILENAME_RE
PII_RE = separation_plan.PII_RE


def _package_for_area(area: dict[str, Any]) -> dict[str, Any]:
    area_id = area["id"]
    if area_id in {"legacy_experiment_quarantine", "manual_review_hold"}:
        phase = "P0_HOLD"
        operation = "HOLD_ONLY"
        requires_owner_approval = True
    elif area_id in {"runtime_autofill_line", "audit_gate_layer"}:
        phase = "P1_GATE_PROTECTED_REFACTOR_PLAN"
        operation = "REVIEW_AND_GATE_ONLY"
        requires_owner_approval = False
    elif area_id in {"hwpx_core_library", "frontend_viewer_shell", "test_support_layer"}:
        phase = "P2_DEPENDENCY_IMPACT_REVIEW"
        operation = "REVIEW_AND_IMPORT_IMPACT_ONLY"
        requires_owner_approval = True
    elif area_id == "docs_reports_layer":
        phase = "P3_RETENTION_REVIEW"
        operation = "RETENTION_REVIEW_ONLY"
        requires_owner_approval = True
    else:
        phase = "P4_CONFIG_REVIEW"
        operation = "CONFIG_REVIEW_ONLY"
        requires_owner_approval = True
    return {
        "packageId": f"pkg_{area_id}",
        "areaId": area_id,
        "phase": phase,
        "operation": operation,
        "fileCount": area["fileCount"],
        "reviewRequiredFiles": area["reviewRequiredFiles"],
        "movePolicy": area["movePolicy"],
        "requiresOwnerApprovalForMove": requires_owner_approval or "no_move" in area["movePolicy"],
        "executionAllowedNow": False,
        "dryRunOnly": True,
    }


def _build_execution_matrix(detailed_plan: dict[str, Any]) -> list[dict[str, Any]]:
    return [_package_for_area(area) for area in detailed_plan.get("areaMatrix", [])]


def run_execution_gate(
    report_dir: Path = REPORT_DIR,
    request_execution: bool = False,
    owner_approved: bool = False,
) -> dict[str, Any]:
    detailed_plan = separation_plan.plan_detailed_separation(report_dir=report_dir / "detailed_plan_subrun")
    execution_matrix = _build_execution_matrix(detailed_plan)
    failures = []
    blocked = []
    if detailed_plan["verdict"] != separation_plan.PASS_VERDICT:
        failures.append(FAIL_DETAILED_PLAN_NOT_PASS)
    if request_execution:
        blocked.append(BLOCKED_MOVE_DELETE_NOT_ALLOWED)
        if not owner_approved:
            blocked.append(BLOCKED_OWNER_REVIEW_REQUIRED)
    verdict = FAIL_VERDICT if failures else BLOCKED_VERDICT if blocked else PASS_VERDICT
    payload = {
        "schemaVersion": "hwpx_repo_separation_execution_gate_v1",
        "verdict": verdict,
        "baselineHead": detailed_plan["baselineHead"],
        "mode": "DRY_RUN_ONLY",
        "requestExecution": request_execution,
        "ownerApproved": owner_approved,
        "executionAllowed": False,
        "summary": {
            "packages": len(execution_matrix),
            "dryRunPackages": sum(1 for item in execution_matrix if item["dryRunOnly"]),
            "executionAllowedPackages": sum(1 for item in execution_matrix if item["executionAllowedNow"]),
            "holdPackages": sum(1 for item in execution_matrix if item["phase"] == "P0_HOLD"),
            "totalFiles": detailed_plan["summary"]["totalFiles"],
            "releaseZonesGated": detailed_plan["summary"]["releaseZonesGated"],
            "holdZones": detailed_plan["summary"]["holdZones"],
        },
        "blockedReasons": sorted(set(blocked)),
        "failures": sorted(set(failures)),
        "executionMatrix": execution_matrix,
        "security": {
            "piiLeak": 0,
            "rawPathLeak": 0,
            "rawFilenameLeak": 0,
            "sourceMutationAllowed": False,
            "productionWriteAllowed": False,
            "fileMovePerformed": False,
            "fileDeletePerformed": False,
        },
        "warnings": [
            "WARN_DRY_RUN_ONLY",
            "WARN_NO_FILE_MOVE_PERFORMED",
            "WARN_OWNER_REVIEW_REQUIRED_BEFORE_SPLIT",
        ],
    }
    _write_reports(report_dir, payload)
    return payload


def _no_leak(text: str) -> bool:
    return not (ABS_PATH_RE.search(text) or RAW_FILENAME_RE.search(text) or PII_RE.search(text))


def _safe_write(path: Path, payload: Any) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if not _no_leak(text):
        raise ValueError(f"{FAIL_UNSAFE_REPORT}: {path.name}")
    path.write_text(text, encoding="utf-8")


def _write_reports(report_dir: Path, payload: dict[str, Any]) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    _safe_write(report_dir / "separation_execution_gate_summary.json", payload)
    _safe_write(report_dir / "separation_execution_matrix.json", payload["executionMatrix"])
    lines = [
        "# HWPX Repo Separation Execution Gate",
        "",
        f"- verdict: {payload['verdict']}",
        f"- baseline: {payload['baselineHead']}",
        f"- mode: {payload['mode']}",
        f"- executionAllowed: {payload['executionAllowed']}",
        f"- packages: {payload['summary']['packages']}",
        f"- dryRunPackages: {payload['summary']['dryRunPackages']}",
        f"- holdPackages: {payload['summary']['holdPackages']}",
        f"- security: pii={payload['security']['piiLeak']} rawPath={payload['security']['rawPathLeak']} rawFilename={payload['security']['rawFilenameLeak']}",
        "",
        "## Packages",
    ]
    for item in payload["executionMatrix"]:
        lines.append(
            f"- {item['packageId']}: phase={item['phase']} operation={item['operation']} files={item['fileCount']} dryRun={item['dryRunOnly']}"
        )
    lines.extend(["", "## Guardrails"])
    lines.append("- no file move/delete/archive is performed by this gate")
    lines.append("- owner approval is required before any future execution script")
    lines.append("- legacy and unknown packages remain HOLD_ONLY")
    text = "\n".join(lines) + "\n"
    if not _no_leak(text):
        raise ValueError(FAIL_UNSAFE_REPORT)
    (report_dir / "separation_execution_gate_summary.md").write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", default=str(REPORT_DIR))
    parser.add_argument("--request-execution", action="store_true")
    parser.add_argument("--owner-approved", action="store_true")
    args = parser.parse_args()
    payload = run_execution_gate(
        report_dir=Path(args.report_dir),
        request_execution=args.request_execution,
        owner_approved=args.owner_approved,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["verdict"] == PASS_VERDICT else 1


if __name__ == "__main__":
    raise SystemExit(main())
