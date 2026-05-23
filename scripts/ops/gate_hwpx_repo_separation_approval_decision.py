"""Approval decision gate for repo separation owner review packets.

This gate validates owner-review decisions but never grants move/delete/archive
execution. A review-only approval can be recorded only when all required checks
are present; execution approval remains blocked for a separate future plan.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.ops import build_hwpx_repo_separation_owner_review as owner_review  # noqa: E402

REPORT_DIR = ROOT / "data" / "reports" / "hwpx_repo_separation_approval_decision"

PASS_VERDICT = "PASS_HWPX_REPO_SEPARATION_APPROVAL_DECISION_GATE"
BLOCKED_VERDICT = "BLOCKED_HWPX_REPO_SEPARATION_APPROVAL_DECISION_GATE"
FAIL_VERDICT = "FAIL_HWPX_REPO_SEPARATION_APPROVAL_DECISION_GATE"

DECISION_PENDING = "PENDING"
DECISION_REVIEW_APPROVED = "APPROVE_REVIEW_ONLY"
DECISION_REJECTED = "REJECT"
DECISION_HOLD = "HOLD"

BLOCKED_UNKNOWN_PACKET = "BLOCKED_UNKNOWN_PACKET"
BLOCKED_MISSING_REQUIRED_CHECKS = "BLOCKED_MISSING_REQUIRED_CHECKS"
BLOCKED_HOLD_PACKAGE_APPROVAL = "BLOCKED_HOLD_PACKAGE_APPROVAL"
BLOCKED_EXECUTION_APPROVAL_NOT_ALLOWED = "BLOCKED_EXECUTION_APPROVAL_NOT_ALLOWED"
FAIL_OWNER_REVIEW_NOT_PASS = "FAIL_OWNER_REVIEW_NOT_PASS"
FAIL_UNSAFE_REPORT = "FAIL_UNSAFE_REPORT"

ABS_PATH_RE = owner_review.ABS_PATH_RE
RAW_FILENAME_RE = owner_review.RAW_FILENAME_RE
PII_RE = owner_review.PII_RE


def _default_decisions(packets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"packetId": packet["packetId"], "decision": DECISION_PENDING, "checks": {}} for packet in packets]


def evaluate_decision(packet: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    decision_kind = decision.get("decision", DECISION_PENDING)
    checks = decision.get("checks", {})
    execution_requested = any(
        bool(decision.get(key))
        for key in ("approvedForMove", "approvedForDelete", "approvedForArchive", "executionAllowed")
    )
    blocked: list[str] = []
    if execution_requested:
        blocked.append(BLOCKED_EXECUTION_APPROVAL_NOT_ALLOWED)
    if decision_kind == DECISION_REVIEW_APPROVED:
        missing = [check for check in packet["requiredChecks"] if checks.get(check) is not True]
        if missing:
            blocked.append(BLOCKED_MISSING_REQUIRED_CHECKS)
        if packet["reviewTrack"] == "HOLD_OWNER_REVIEW":
            blocked.append(BLOCKED_HOLD_PACKAGE_APPROVAL)
    status = "BLOCKED" if blocked else "APPROVED_REVIEW_ONLY" if decision_kind == DECISION_REVIEW_APPROVED else decision_kind
    return {
        "packetId": packet["packetId"],
        "areaId": packet["areaId"],
        "decision": decision_kind,
        "status": status,
        "blockedReasons": sorted(set(blocked)),
        "reviewApproved": status == "APPROVED_REVIEW_ONLY",
        "executionAllowed": False,
        "approvedForMove": False,
        "approvedForDelete": False,
        "approvedForArchive": False,
    }


def run_approval_decision_gate(
    report_dir: Path = REPORT_DIR,
    decisions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    owner_payload = owner_review.build_owner_review_packets(report_dir=report_dir / "owner_review_subrun")
    packets = owner_payload["ownerReviewPackets"]
    packet_by_id = {packet["packetId"]: packet for packet in packets}
    decisions = decisions if decisions is not None else _default_decisions(packets)
    results = []
    blocked = []
    for decision in decisions:
        packet_id = decision.get("packetId")
        packet = packet_by_id.get(packet_id)
        if not packet:
            results.append(
                {
                    "packetId": packet_id or "<missing>",
                    "areaId": "<unknown>",
                    "decision": decision.get("decision", DECISION_PENDING),
                    "status": "BLOCKED",
                    "blockedReasons": [BLOCKED_UNKNOWN_PACKET],
                    "reviewApproved": False,
                    "executionAllowed": False,
                    "approvedForMove": False,
                    "approvedForDelete": False,
                    "approvedForArchive": False,
                }
            )
            blocked.append(BLOCKED_UNKNOWN_PACKET)
            continue
        result = evaluate_decision(packet, decision)
        results.append(result)
        blocked.extend(result["blockedReasons"])
    failures = []
    if owner_payload["verdict"] != owner_review.PASS_VERDICT:
        failures.append(FAIL_OWNER_REVIEW_NOT_PASS)
    blocked = sorted(set(blocked))
    verdict = FAIL_VERDICT if failures else BLOCKED_VERDICT if blocked else PASS_VERDICT
    payload = {
        "schemaVersion": "hwpx_repo_separation_approval_decision_gate_v1",
        "verdict": verdict,
        "baselineHead": owner_payload["baselineHead"],
        "mode": "REVIEW_DECISION_ONLY",
        "summary": {
            "packets": len(packets),
            "decisions": len(decisions),
            "pendingDecisions": sum(1 for item in results if item["status"] == DECISION_PENDING),
            "reviewApprovedDecisions": sum(1 for item in results if item["reviewApproved"]),
            "blockedDecisions": sum(1 for item in results if item["status"] == "BLOCKED"),
            "executionAllowedDecisions": 0,
        },
        "decisionResults": results,
        "blockedReasons": blocked,
        "failures": failures,
        "security": {
            "piiLeak": 0,
            "rawPathLeak": 0,
            "rawFilenameLeak": 0,
            "fileMoveApproved": False,
            "fileDeleteApproved": False,
            "fileArchiveApproved": False,
            "fileMovePerformed": False,
            "fileDeletePerformed": False,
        },
        "warnings": [
            "WARN_REVIEW_DECISION_ONLY",
            "WARN_EXECUTION_APPROVAL_NOT_ALLOWED",
            "WARN_OWNER_REVIEW_DECISIONS_PENDING",
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
    _safe_write(report_dir / "approval_decision_summary.json", payload)
    _safe_write(report_dir / "approval_decision_results.json", payload["decisionResults"])
    lines = [
        "# HWPX Repo Separation Approval Decision Gate",
        "",
        f"- verdict: {payload['verdict']}",
        f"- baseline: {payload['baselineHead']}",
        f"- mode: {payload['mode']}",
        f"- decisions: {payload['summary']['decisions']}",
        f"- pending: {payload['summary']['pendingDecisions']}",
        f"- reviewApproved: {payload['summary']['reviewApprovedDecisions']}",
        f"- blocked: {payload['summary']['blockedDecisions']}",
        f"- executionAllowed: {payload['summary']['executionAllowedDecisions']}",
        f"- security: pii={payload['security']['piiLeak']} rawPath={payload['security']['rawPathLeak']} rawFilename={payload['security']['rawFilenameLeak']}",
        "",
        "## Guardrails",
        "- review-only decisions do not approve move/delete/archive",
        "- HOLD packages cannot be review-approved in this gate",
        "- execution approval needs a separate future plan",
    ]
    text = "\n".join(lines) + "\n"
    if not _no_leak(text):
        raise ValueError(FAIL_UNSAFE_REPORT)
    (report_dir / "approval_decision_summary.md").write_text(text, encoding="utf-8")


def _load_decisions(path: str | None) -> list[dict[str, Any]] | None:
    if not path:
        return None
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", default=str(REPORT_DIR))
    parser.add_argument("--decisions-json")
    args = parser.parse_args()
    payload = run_approval_decision_gate(
        report_dir=Path(args.report_dir),
        decisions=_load_decisions(args.decisions_json),
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["verdict"] == PASS_VERDICT else 1


if __name__ == "__main__":
    raise SystemExit(main())
