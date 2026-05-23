"""Tests for repo separation approval decision gate."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.ops.gate_hwpx_repo_separation_approval_decision as decision_gate  # noqa: E402


def test_01_decision_gate_importable() -> None:
    assert hasattr(decision_gate, "run_approval_decision_gate")
    assert hasattr(decision_gate, "evaluate_decision")


def test_02_default_pending_decisions_pass(tmp_path: Path) -> None:
    result = decision_gate.run_approval_decision_gate(report_dir=tmp_path)
    assert result["verdict"] == decision_gate.PASS_VERDICT
    assert result["mode"] == "REVIEW_DECISION_ONLY"
    assert result["summary"]["decisions"] == result["summary"]["pendingDecisions"]
    assert result["summary"]["executionAllowedDecisions"] == 0


def test_03_reports_are_written(tmp_path: Path) -> None:
    decision_gate.run_approval_decision_gate(report_dir=tmp_path)
    assert (tmp_path / "approval_decision_summary.json").is_file()
    assert (tmp_path / "approval_decision_results.json").is_file()
    assert (tmp_path / "approval_decision_summary.md").is_file()


def test_04_review_approval_requires_all_checks(tmp_path: Path) -> None:
    owner = decision_gate.owner_review.build_owner_review_packets(report_dir=tmp_path / "owner")
    packet = next(item for item in owner["ownerReviewPackets"] if item["reviewTrack"] != "HOLD_OWNER_REVIEW")
    result = decision_gate.run_approval_decision_gate(
        report_dir=tmp_path / "decision",
        decisions=[{"packetId": packet["packetId"], "decision": decision_gate.DECISION_REVIEW_APPROVED, "checks": {}}],
    )
    assert result["verdict"] == decision_gate.BLOCKED_VERDICT
    assert decision_gate.BLOCKED_MISSING_REQUIRED_CHECKS in result["blockedReasons"]


def test_05_review_approval_with_checks_is_review_only(tmp_path: Path) -> None:
    owner = decision_gate.owner_review.build_owner_review_packets(report_dir=tmp_path / "owner")
    packet = next(item for item in owner["ownerReviewPackets"] if item["reviewTrack"] != "HOLD_OWNER_REVIEW")
    checks = {check: True for check in packet["requiredChecks"]}
    result = decision_gate.run_approval_decision_gate(
        report_dir=tmp_path / "decision",
        decisions=[{"packetId": packet["packetId"], "decision": decision_gate.DECISION_REVIEW_APPROVED, "checks": checks}],
    )
    assert result["verdict"] == decision_gate.PASS_VERDICT
    assert result["summary"]["reviewApprovedDecisions"] == 1
    assert result["decisionResults"][0]["executionAllowed"] is False
    assert result["decisionResults"][0]["approvedForMove"] is False


def test_06_hold_package_approval_blocked(tmp_path: Path) -> None:
    owner = decision_gate.owner_review.build_owner_review_packets(report_dir=tmp_path / "owner")
    packet = next(item for item in owner["ownerReviewPackets"] if item["reviewTrack"] == "HOLD_OWNER_REVIEW")
    checks = {check: True for check in packet["requiredChecks"]}
    result = decision_gate.run_approval_decision_gate(
        report_dir=tmp_path / "decision",
        decisions=[{"packetId": packet["packetId"], "decision": decision_gate.DECISION_REVIEW_APPROVED, "checks": checks}],
    )
    assert result["verdict"] == decision_gate.BLOCKED_VERDICT
    assert decision_gate.BLOCKED_HOLD_PACKAGE_APPROVAL in result["blockedReasons"]


def test_07_execution_approval_is_blocked(tmp_path: Path) -> None:
    owner = decision_gate.owner_review.build_owner_review_packets(report_dir=tmp_path / "owner")
    packet = owner["ownerReviewPackets"][0]
    result = decision_gate.run_approval_decision_gate(
        report_dir=tmp_path / "decision",
        decisions=[{"packetId": packet["packetId"], "decision": decision_gate.DECISION_PENDING, "approvedForMove": True}],
    )
    assert result["verdict"] == decision_gate.BLOCKED_VERDICT
    assert decision_gate.BLOCKED_EXECUTION_APPROVAL_NOT_ALLOWED in result["blockedReasons"]


def test_08_unknown_packet_blocked(tmp_path: Path) -> None:
    result = decision_gate.run_approval_decision_gate(
        report_dir=tmp_path,
        decisions=[{"packetId": "missing_packet", "decision": decision_gate.DECISION_PENDING}],
    )
    assert result["verdict"] == decision_gate.BLOCKED_VERDICT
    assert decision_gate.BLOCKED_UNKNOWN_PACKET in result["blockedReasons"]


def test_09_security_contract_closed(tmp_path: Path) -> None:
    result = decision_gate.run_approval_decision_gate(report_dir=tmp_path)
    security = result["security"]
    assert security["piiLeak"] == 0
    assert security["rawPathLeak"] == 0
    assert security["rawFilenameLeak"] == 0
    assert security["fileMoveApproved"] is False
    assert security["fileDeleteApproved"] is False
    assert security["fileArchiveApproved"] is False
    assert security["fileMovePerformed"] is False
    assert security["fileDeletePerformed"] is False


def test_10_reports_have_no_leak_patterns(tmp_path: Path) -> None:
    decision_gate.run_approval_decision_gate(report_dir=tmp_path)
    for path in tmp_path.glob("*.json"):
        text = path.read_text(encoding="utf-8")
        assert not decision_gate.ABS_PATH_RE.search(text)
        assert not decision_gate.RAW_FILENAME_RE.search(text)
        assert not decision_gate.PII_RE.search(text)
    text = (tmp_path / "approval_decision_summary.md").read_text(encoding="utf-8")
    assert not decision_gate.ABS_PATH_RE.search(text)
    assert not decision_gate.RAW_FILENAME_RE.search(text)
    assert not decision_gate.PII_RE.search(text)


def test_11_json_reports_valid(tmp_path: Path) -> None:
    decision_gate.run_approval_decision_gate(report_dir=tmp_path)
    json.loads((tmp_path / "approval_decision_summary.json").read_text(encoding="utf-8"))
    json.loads((tmp_path / "approval_decision_results.json").read_text(encoding="utf-8"))


def test_12_owner_review_subrun_linked(tmp_path: Path) -> None:
    decision_gate.run_approval_decision_gate(report_dir=tmp_path)
    assert (tmp_path / "owner_review_subrun" / "owner_review_summary.json").is_file()
