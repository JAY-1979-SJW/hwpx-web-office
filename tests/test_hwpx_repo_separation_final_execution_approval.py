"""Tests for repo separation final execution approval gate."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.ops.gate_hwpx_repo_separation_final_execution_approval as final_gate  # noqa: E402


def _review_approved_plan_decision(tmp_path: Path) -> dict[str, object]:
    owner = final_gate.draft_gate.approval_gate.owner_review.build_owner_review_packets(report_dir=tmp_path / "owner")
    packet = next(item for item in owner["ownerReviewPackets"] if item["reviewTrack"] != "HOLD_OWNER_REVIEW")
    return {
        "packetId": packet["packetId"],
        "decision": final_gate.draft_gate.approval_gate.DECISION_REVIEW_APPROVED,
        "checks": {check: True for check in packet["requiredChecks"]},
    }


def test_01_final_gate_importable() -> None:
    assert hasattr(final_gate, "run_final_execution_approval_gate")
    assert hasattr(final_gate, "evaluate_final_execution_decision")


def test_02_default_no_final_execution_approvals(tmp_path: Path) -> None:
    result = final_gate.run_final_execution_approval_gate(report_dir=tmp_path)
    assert result["verdict"] == final_gate.PASS_VERDICT
    assert result["mode"] == "FINAL_EXECUTION_APPROVAL_GATE_NO_COMMANDS"
    assert result["summary"]["executionPlanCandidates"] == 0
    assert result["summary"]["finalExecutionApproved"] == 0
    assert result["summary"]["noExecutionCandidates"] == result["summary"]["decisions"]


def test_03_reports_are_written(tmp_path: Path) -> None:
    final_gate.run_final_execution_approval_gate(report_dir=tmp_path)
    assert (tmp_path / "final_execution_approval_summary.json").is_file()
    assert (tmp_path / "final_execution_decisions.json").is_file()
    assert (tmp_path / "final_execution_approval_summary.md").is_file()


def test_04_default_no_commands_generated(tmp_path: Path) -> None:
    result = final_gate.run_final_execution_approval_gate(report_dir=tmp_path)
    assert result["summary"]["moveCommands"] == 0
    assert result["summary"]["deleteCommands"] == 0
    assert result["summary"]["archiveCommands"] == 0
    for item in result["finalExecutionDecisions"]:
        assert item["executionAllowed"] is False
        assert item["moveCommandGenerated"] is False
        assert item["deleteCommandGenerated"] is False
        assert item["archiveCommandGenerated"] is False


def test_05_non_candidate_final_approval_is_blocked(tmp_path: Path) -> None:
    default = final_gate.run_final_execution_approval_gate(report_dir=tmp_path / "default")
    packet_id = default["finalExecutionDecisions"][0]["packetId"]
    result = final_gate.run_final_execution_approval_gate(
        report_dir=tmp_path / "blocked",
        final_decisions=[
            {
                "packetId": packet_id,
                "decision": final_gate.DECISION_APPROVE_FINAL_EXECUTION,
                "checks": {check: True for check in final_gate.REQUIRED_FINAL_CHECKS},
            }
        ],
    )
    assert result["verdict"] == final_gate.BLOCKED_VERDICT
    assert final_gate.BLOCKED_NO_EXECUTION_PLAN_CANDIDATE in result["blockedReasons"]
    assert result["summary"]["finalExecutionApproved"] == 0


def test_06_candidate_missing_final_checks_is_blocked(tmp_path: Path) -> None:
    plan_decision = _review_approved_plan_decision(tmp_path)
    result = final_gate.run_final_execution_approval_gate(
        report_dir=tmp_path / "blocked",
        plan_decisions=[plan_decision],
        final_decisions=[{"packetId": plan_decision["packetId"], "decision": final_gate.DECISION_APPROVE_FINAL_EXECUTION, "checks": {}}],
    )
    assert result["verdict"] == final_gate.BLOCKED_VERDICT
    assert final_gate.BLOCKED_MISSING_FINAL_CHECKS in result["blockedReasons"]
    assert result["summary"]["executionPlanCandidates"] == 1
    assert result["summary"]["finalExecutionApproved"] == 0


def test_07_candidate_with_all_final_checks_is_approved_without_commands(tmp_path: Path) -> None:
    plan_decision = _review_approved_plan_decision(tmp_path)
    result = final_gate.run_final_execution_approval_gate(
        report_dir=tmp_path / "approved",
        plan_decisions=[plan_decision],
        final_decisions=[
            {
                "packetId": plan_decision["packetId"],
                "decision": final_gate.DECISION_APPROVE_FINAL_EXECUTION,
                "checks": {check: True for check in final_gate.REQUIRED_FINAL_CHECKS},
            }
        ],
    )
    assert result["verdict"] == final_gate.PASS_VERDICT
    assert result["summary"]["executionPlanCandidates"] == 1
    assert result["summary"]["finalExecutionApproved"] == 1
    assert result["summary"]["moveCommands"] == 0
    assert result["finalExecutionDecisions"][0]["executionAllowed"] is False


def test_08_blocked_plan_draft_fails_final_gate(tmp_path: Path) -> None:
    owner = final_gate.draft_gate.approval_gate.owner_review.build_owner_review_packets(report_dir=tmp_path / "owner")
    hold_packet = next(item for item in owner["ownerReviewPackets"] if item["reviewTrack"] == "HOLD_OWNER_REVIEW")
    result = final_gate.run_final_execution_approval_gate(
        report_dir=tmp_path / "failed",
        plan_decisions=[
            {
                "packetId": hold_packet["packetId"],
                "decision": final_gate.draft_gate.approval_gate.DECISION_REVIEW_APPROVED,
                "checks": {check: True for check in hold_packet["requiredChecks"]},
            }
        ],
    )
    assert result["verdict"] == final_gate.FAIL_VERDICT
    assert final_gate.FAIL_EXECUTION_PLAN_DRAFT_NOT_PASS in result["failures"]


def test_09_security_contract_closed(tmp_path: Path) -> None:
    result = final_gate.run_final_execution_approval_gate(report_dir=tmp_path)
    security = result["security"]
    assert security["piiLeak"] == 0
    assert security["rawPathLeak"] == 0
    assert security["rawFilenameLeak"] == 0
    assert security["fileMoveCommandGenerated"] is False
    assert security["fileDeleteCommandGenerated"] is False
    assert security["fileArchiveCommandGenerated"] is False
    assert security["fileMovePerformed"] is False
    assert security["fileDeletePerformed"] is False


def test_10_reports_have_no_leak_patterns(tmp_path: Path) -> None:
    final_gate.run_final_execution_approval_gate(report_dir=tmp_path)
    for path in tmp_path.glob("*.json"):
        text = path.read_text(encoding="utf-8")
        assert not final_gate.ABS_PATH_RE.search(text)
        assert not final_gate.RAW_FILENAME_RE.search(text)
        assert not final_gate.PII_RE.search(text)
    text = (tmp_path / "final_execution_approval_summary.md").read_text(encoding="utf-8")
    assert not final_gate.ABS_PATH_RE.search(text)
    assert not final_gate.RAW_FILENAME_RE.search(text)
    assert not final_gate.PII_RE.search(text)


def test_11_json_reports_valid(tmp_path: Path) -> None:
    final_gate.run_final_execution_approval_gate(report_dir=tmp_path)
    json.loads((tmp_path / "final_execution_approval_summary.json").read_text(encoding="utf-8"))
    json.loads((tmp_path / "final_execution_decisions.json").read_text(encoding="utf-8"))


def test_12_execution_plan_subrun_linked(tmp_path: Path) -> None:
    final_gate.run_final_execution_approval_gate(report_dir=tmp_path)
    assert (tmp_path / "plan" / "execution_plan_draft_summary.json").is_file()


def test_13_warnings_document_gate_only_mode(tmp_path: Path) -> None:
    result = final_gate.run_final_execution_approval_gate(report_dir=tmp_path)
    assert "WARN_FINAL_EXECUTION_APPROVAL_GATE_ONLY" in result["warnings"]
    assert "WARN_NO_EXECUTION_COMMAND_GENERATED" in result["warnings"]


def test_14_unknown_packet_is_blocked(tmp_path: Path) -> None:
    result = final_gate.run_final_execution_approval_gate(
        report_dir=tmp_path,
        final_decisions=[
            {
                "packetId": "owner_review_unknown",
                "decision": final_gate.DECISION_APPROVE_FINAL_EXECUTION,
                "checks": {check: True for check in final_gate.REQUIRED_FINAL_CHECKS},
            }
        ],
    )
    assert result["verdict"] == final_gate.BLOCKED_VERDICT
    assert final_gate.BLOCKED_NO_EXECUTION_PLAN_CANDIDATE in result["blockedReasons"]
