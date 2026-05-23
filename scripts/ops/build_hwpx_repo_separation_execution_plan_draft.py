"""Build a dry-run execution plan draft from separation approval decisions."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.ops import gate_hwpx_repo_separation_approval_decision as approval_gate  # noqa: E402

REPORT_DIR = ROOT / "data" / "reports" / "hwpx_repo_separation_execution_plan_draft"

PASS_VERDICT = "PASS_HWPX_REPO_SEPARATION_EXECUTION_PLAN_DRAFT"
FAIL_VERDICT = "FAIL_HWPX_REPO_SEPARATION_EXECUTION_PLAN_DRAFT"
FAIL_APPROVAL_DECISION_NOT_PASS = "FAIL_APPROVAL_DECISION_NOT_PASS"
FAIL_EXECUTION_COMMAND_GENERATED = "FAIL_EXECUTION_COMMAND_GENERATED"
FAIL_UNSAFE_REPORT = "FAIL_UNSAFE_REPORT"

ABS_PATH_RE = approval_gate.ABS_PATH_RE
RAW_FILENAME_RE = approval_gate.RAW_FILENAME_RE
PII_RE = approval_gate.PII_RE

TARGET_LAYOUT = {
    "runtime_autofill_line": "planned/autofill/runtime",
    "hwpx_core_library": "planned/hwpx/core",
    "frontend_viewer_shell": "planned/frontend/viewer",
    "audit_gate_layer": "planned/ops/gates",
    "test_support_layer": "planned/tests/support",
    "docs_reports_layer": "planned/docs/reports",
    "legacy_experiment_quarantine": "planned/hold/legacy",
    "config_root_layer": "planned/config/root",
    "manual_review_hold": "planned/hold/manual",
}


def _candidate_for_decision(decision: dict[str, Any]) -> dict[str, Any]:
    approved = decision.get("reviewApproved") is True
    area_id = decision["areaId"]
    return {
        "packetId": decision["packetId"],
        "areaId": area_id,
        "candidateStatus": "EXECUTION_PLAN_CANDIDATE" if approved else "NO_EXECUTION_CANDIDATE",
        "targetLayout": TARGET_LAYOUT.get(area_id, "planned/hold/unclassified"),
        "reviewApproved": approved,
        "executionAllowed": False,
        "moveCommandGenerated": False,
        "deleteCommandGenerated": False,
        "archiveCommandGenerated": False,
        "requiredNextChecks": [
            "approved_execution_gate",
            "import_impact_tests",
            "owner_final_execution_approval",
            "separate_commit_for_any_move",
        ],
    }


def build_execution_plan_draft(
    report_dir: Path = REPORT_DIR,
    decisions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    approval_payload = approval_gate.run_approval_decision_gate(
        report_dir=report_dir / "approval_decision_subrun",
        decisions=decisions,
    )
    candidates = [_candidate_for_decision(item) for item in approval_payload["decisionResults"]]
    command_generated = any(
        item["moveCommandGenerated"] or item["deleteCommandGenerated"] or item["archiveCommandGenerated"]
        for item in candidates
    )
    failures = []
    if approval_payload["verdict"] != approval_gate.PASS_VERDICT:
        failures.append(FAIL_APPROVAL_DECISION_NOT_PASS)
    if command_generated:
        failures.append(FAIL_EXECUTION_COMMAND_GENERATED)
    payload = {
        "schemaVersion": "hwpx_repo_separation_execution_plan_draft_v1",
        "verdict": PASS_VERDICT if not failures else FAIL_VERDICT,
        "baselineHead": approval_payload["baselineHead"],
        "mode": "DRY_RUN_EXECUTION_PLAN_DRAFT",
        "summary": {
            "decisions": approval_payload["summary"]["decisions"],
            "reviewApprovedDecisions": approval_payload["summary"]["reviewApprovedDecisions"],
            "executionPlanCandidates": sum(1 for item in candidates if item["candidateStatus"] == "EXECUTION_PLAN_CANDIDATE"),
            "noExecutionCandidates": sum(1 for item in candidates if item["candidateStatus"] == "NO_EXECUTION_CANDIDATE"),
            "moveCommands": 0,
            "deleteCommands": 0,
            "archiveCommands": 0,
        },
        "executionPlanCandidates": candidates,
        "failures": failures,
        "security": {
            "piiLeak": 0,
            "rawPathLeak": 0,
            "rawFilenameLeak": 0,
            "fileMoveCommandGenerated": False,
            "fileDeleteCommandGenerated": False,
            "fileArchiveCommandGenerated": False,
            "fileMovePerformed": False,
            "fileDeletePerformed": False,
        },
        "warnings": [
            "WARN_DRY_RUN_EXECUTION_PLAN_ONLY",
            "WARN_NO_EXECUTION_COMMAND_GENERATED",
            "WARN_SEPARATE_APPROVED_EXECUTION_GATE_REQUIRED",
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
    _safe_write(report_dir / "execution_plan_draft_summary.json", payload)
    _safe_write(report_dir / "execution_plan_candidates.json", payload["executionPlanCandidates"])
    lines = [
        "# HWPX Repo Separation Execution Plan Draft",
        "",
        f"- verdict: {payload['verdict']}",
        f"- baseline: {payload['baselineHead']}",
        f"- mode: {payload['mode']}",
        f"- reviewApproved: {payload['summary']['reviewApprovedDecisions']}",
        f"- executionPlanCandidates: {payload['summary']['executionPlanCandidates']}",
        f"- noExecutionCandidates: {payload['summary']['noExecutionCandidates']}",
        f"- moveCommands: {payload['summary']['moveCommands']}",
        f"- deleteCommands: {payload['summary']['deleteCommands']}",
        f"- archiveCommands: {payload['summary']['archiveCommands']}",
        f"- security: pii={payload['security']['piiLeak']} rawPath={payload['security']['rawPathLeak']} rawFilename={payload['security']['rawFilenameLeak']}",
        "",
        "## Guardrails",
        "- this draft does not generate move/delete/archive commands",
        "- execution candidates require a separate approved execution gate",
        "- no package can execute directly from review approval",
    ]
    text = "\n".join(lines) + "\n"
    if not _no_leak(text):
        raise ValueError(FAIL_UNSAFE_REPORT)
    (report_dir / "execution_plan_draft_summary.md").write_text(text, encoding="utf-8")


def _load_decisions(path: str | None) -> list[dict[str, Any]] | None:
    if not path:
        return None
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", default=str(REPORT_DIR))
    parser.add_argument("--decisions-json")
    args = parser.parse_args()
    payload = build_execution_plan_draft(
        report_dir=Path(args.report_dir),
        decisions=_load_decisions(args.decisions_json),
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["verdict"] == PASS_VERDICT else 1


if __name__ == "__main__":
    raise SystemExit(main())
