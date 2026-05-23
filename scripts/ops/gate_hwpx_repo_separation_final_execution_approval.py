"""Final approval gate for repo separation execution candidates.

This gate can approve a reviewed execution-plan candidate for a future
separate execution step, but it never generates move/delete/archive commands.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.ops import build_hwpx_repo_separation_execution_plan_draft as draft_gate  # noqa: E402

REPORT_DIR = ROOT / "data" / "reports" / "hwpx_repo_separation_final_execution_approval"

PASS_VERDICT = "PASS_HWPX_REPO_SEPARATION_FINAL_EXECUTION_APPROVAL_GATE"
BLOCKED_VERDICT = "BLOCKED_HWPX_REPO_SEPARATION_FINAL_EXECUTION_APPROVAL_GATE"
FAIL_VERDICT = "FAIL_HWPX_REPO_SEPARATION_FINAL_EXECUTION_APPROVAL_GATE"

DECISION_PENDING = "PENDING"
DECISION_APPROVE_FINAL_EXECUTION = "APPROVE_FINAL_EXECUTION"
DECISION_REJECT = "REJECT"
DECISION_HOLD = "HOLD"

BLOCKED_NO_EXECUTION_PLAN_CANDIDATE = "BLOCKED_NO_EXECUTION_PLAN_CANDIDATE"
BLOCKED_MISSING_FINAL_CHECKS = "BLOCKED_MISSING_FINAL_CHECKS"
FAIL_EXECUTION_PLAN_DRAFT_NOT_PASS = "FAIL_EXECUTION_PLAN_DRAFT_NOT_PASS"
FAIL_EXECUTION_COMMAND_GENERATED = "FAIL_EXECUTION_COMMAND_GENERATED"
FAIL_UNSAFE_REPORT = "FAIL_UNSAFE_REPORT"

ABS_PATH_RE = draft_gate.ABS_PATH_RE
RAW_FILENAME_RE = draft_gate.RAW_FILENAME_RE
PII_RE = draft_gate.PII_RE

REQUIRED_FINAL_CHECKS = [
    "approved_execution_gate",
    "import_impact_tests",
    "owner_final_execution_approval",
    "separate_commit_for_any_move",
    "no_uncommitted_dirty_scope",
    "no_pii_raw_path_raw_filename",
]


def _default_decisions(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"packetId": item["packetId"], "decision": DECISION_PENDING, "checks": {}} for item in candidates]


def evaluate_final_execution_decision(
    candidate: dict[str, Any],
    decision: dict[str, Any],
) -> dict[str, Any]:
    decision_kind = decision.get("decision", DECISION_PENDING)
    checks = decision.get("checks", {})
    is_candidate = candidate.get("candidateStatus") == "EXECUTION_PLAN_CANDIDATE"
    blocked: list[str] = []
    final_approved = False

    if decision_kind == DECISION_APPROVE_FINAL_EXECUTION:
        if not is_candidate:
            blocked.append(BLOCKED_NO_EXECUTION_PLAN_CANDIDATE)
        missing = [check for check in REQUIRED_FINAL_CHECKS if checks.get(check) is not True]
        if missing:
            blocked.append(BLOCKED_MISSING_FINAL_CHECKS)
        final_approved = not blocked

    status = (
        "FINAL_EXECUTION_APPROVED"
        if final_approved
        else "BLOCKED"
        if blocked
        else "NO_EXECUTION_CANDIDATE"
        if not is_candidate
        else decision_kind
    )
    return {
        "packetId": candidate["packetId"],
        "areaId": candidate["areaId"],
        "decision": decision_kind,
        "status": status,
        "blockedReasons": sorted(set(blocked)),
        "executionPlanCandidate": is_candidate,
        "finalExecutionApproved": final_approved,
        "executionAllowed": False,
        "moveCommandGenerated": False,
        "deleteCommandGenerated": False,
        "archiveCommandGenerated": False,
    }


def run_final_execution_approval_gate(
    report_dir: Path = REPORT_DIR,
    plan_decisions: list[dict[str, Any]] | None = None,
    final_decisions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    draft_payload = draft_gate.build_execution_plan_draft(
        report_dir=report_dir / "plan",
        decisions=plan_decisions,
    )
    candidates = draft_payload["executionPlanCandidates"]
    by_packet = {item["packetId"]: item for item in candidates}
    final_decisions = final_decisions if final_decisions is not None else _default_decisions(candidates)
    results: list[dict[str, Any]] = []
    blocked: list[str] = []

    for decision in final_decisions:
        packet_id = decision.get("packetId")
        candidate = by_packet.get(packet_id)
        if not candidate:
            result = {
                "packetId": packet_id or "<missing>",
                "areaId": "<unknown>",
                "decision": decision.get("decision", DECISION_PENDING),
                "status": "BLOCKED",
                "blockedReasons": [BLOCKED_NO_EXECUTION_PLAN_CANDIDATE],
                "executionPlanCandidate": False,
                "finalExecutionApproved": False,
                "executionAllowed": False,
                "moveCommandGenerated": False,
                "deleteCommandGenerated": False,
                "archiveCommandGenerated": False,
            }
        else:
            result = evaluate_final_execution_decision(candidate, decision)
        results.append(result)
        blocked.extend(result["blockedReasons"])

    command_generated = any(
        item["moveCommandGenerated"] or item["deleteCommandGenerated"] or item["archiveCommandGenerated"]
        for item in results
    )
    failures: list[str] = []
    if draft_payload["verdict"] != draft_gate.PASS_VERDICT:
        failures.append(FAIL_EXECUTION_PLAN_DRAFT_NOT_PASS)
    if command_generated:
        failures.append(FAIL_EXECUTION_COMMAND_GENERATED)

    blocked = sorted(set(blocked))
    payload = {
        "schemaVersion": "hwpx_repo_separation_final_execution_approval_gate_v1",
        "verdict": FAIL_VERDICT if failures else BLOCKED_VERDICT if blocked else PASS_VERDICT,
        "baselineHead": draft_payload["baselineHead"],
        "mode": "FINAL_EXECUTION_APPROVAL_GATE_NO_COMMANDS",
        "summary": {
            "decisions": len(final_decisions),
            "executionPlanCandidates": draft_payload["summary"]["executionPlanCandidates"],
            "noExecutionCandidates": draft_payload["summary"]["noExecutionCandidates"],
            "finalExecutionApproved": sum(1 for item in results if item["finalExecutionApproved"]),
            "blockedDecisions": sum(1 for item in results if item["status"] == "BLOCKED"),
            "moveCommands": 0,
            "deleteCommands": 0,
            "archiveCommands": 0,
        },
        "finalExecutionDecisions": results,
        "blockedReasons": blocked,
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
            "WARN_FINAL_EXECUTION_APPROVAL_GATE_ONLY",
            "WARN_NO_EXECUTION_COMMAND_GENERATED",
            "WARN_SEPARATE_EXECUTION_COMMIT_REQUIRED",
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
    _safe_write(report_dir / "final_execution_approval_summary.json", payload)
    _safe_write(report_dir / "final_execution_decisions.json", payload["finalExecutionDecisions"])
    lines = [
        "# HWPX Repo Separation Final Execution Approval Gate",
        "",
        f"- verdict: {payload['verdict']}",
        f"- baseline: {payload['baselineHead']}",
        f"- mode: {payload['mode']}",
        f"- executionPlanCandidates: {payload['summary']['executionPlanCandidates']}",
        f"- finalExecutionApproved: {payload['summary']['finalExecutionApproved']}",
        f"- blockedDecisions: {payload['summary']['blockedDecisions']}",
        f"- moveCommands: {payload['summary']['moveCommands']}",
        f"- deleteCommands: {payload['summary']['deleteCommands']}",
        f"- archiveCommands: {payload['summary']['archiveCommands']}",
        f"- security: pii={payload['security']['piiLeak']} rawPath={payload['security']['rawPathLeak']} rawFilename={payload['security']['rawFilenameLeak']}",
        "",
        "## Guardrails",
        "- final approval does not move, delete, or archive files",
        "- approved candidates still require a separate execution commit",
        "- non-candidate packages remain blocked",
    ]
    text = "\n".join(lines) + "\n"
    if not _no_leak(text):
        raise ValueError(FAIL_UNSAFE_REPORT)
    (report_dir / "final_execution_approval_summary.md").write_text(text, encoding="utf-8")


def _load_json(path: str | None) -> list[dict[str, Any]] | None:
    if not path:
        return None
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", default=str(REPORT_DIR))
    parser.add_argument("--plan-decisions-json")
    parser.add_argument("--final-decisions-json")
    args = parser.parse_args()
    payload = run_final_execution_approval_gate(
        report_dir=Path(args.report_dir),
        plan_decisions=_load_json(args.plan_decisions_json),
        final_decisions=_load_json(args.final_decisions_json),
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["verdict"] == PASS_VERDICT else 1


if __name__ == "__main__":
    raise SystemExit(main())
