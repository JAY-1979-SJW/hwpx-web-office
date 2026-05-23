"""Tests for repo separation execution plan draft."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.ops.build_hwpx_repo_separation_execution_plan_draft as draft  # noqa: E402


def test_01_draft_importable() -> None:
    assert hasattr(draft, "build_execution_plan_draft")
    assert hasattr(draft, "_candidate_for_decision")


def test_02_default_no_execution_candidates(tmp_path: Path) -> None:
    result = draft.build_execution_plan_draft(report_dir=tmp_path)
    assert result["verdict"] == draft.PASS_VERDICT
    assert result["mode"] == "DRY_RUN_EXECUTION_PLAN_DRAFT"
    assert result["summary"]["reviewApprovedDecisions"] == 0
    assert result["summary"]["executionPlanCandidates"] == 0
    assert result["summary"]["noExecutionCandidates"] == result["summary"]["decisions"]


def test_03_reports_are_written(tmp_path: Path) -> None:
    draft.build_execution_plan_draft(report_dir=tmp_path)
    assert (tmp_path / "execution_plan_draft_summary.json").is_file()
    assert (tmp_path / "execution_plan_candidates.json").is_file()
    assert (tmp_path / "execution_plan_draft_summary.md").is_file()


def test_04_no_commands_generated(tmp_path: Path) -> None:
    result = draft.build_execution_plan_draft(report_dir=tmp_path)
    assert result["summary"]["moveCommands"] == 0
    assert result["summary"]["deleteCommands"] == 0
    assert result["summary"]["archiveCommands"] == 0
    for item in result["executionPlanCandidates"]:
        assert item["moveCommandGenerated"] is False
        assert item["deleteCommandGenerated"] is False
        assert item["archiveCommandGenerated"] is False
        assert item["executionAllowed"] is False


def test_05_review_approved_non_hold_becomes_candidate(tmp_path: Path) -> None:
    owner = draft.approval_gate.owner_review.build_owner_review_packets(report_dir=tmp_path / "owner")
    packet = next(item for item in owner["ownerReviewPackets"] if item["reviewTrack"] != "HOLD_OWNER_REVIEW")
    checks = {check: True for check in packet["requiredChecks"]}
    result = draft.build_execution_plan_draft(
        report_dir=tmp_path / "draft",
        decisions=[{"packetId": packet["packetId"], "decision": draft.approval_gate.DECISION_REVIEW_APPROVED, "checks": checks}],
    )
    assert result["verdict"] == draft.PASS_VERDICT
    assert result["summary"]["executionPlanCandidates"] == 1
    assert result["executionPlanCandidates"][0]["candidateStatus"] == "EXECUTION_PLAN_CANDIDATE"
    assert result["executionPlanCandidates"][0]["executionAllowed"] is False


def test_06_blocked_approval_blocks_draft(tmp_path: Path) -> None:
    owner = draft.approval_gate.owner_review.build_owner_review_packets(report_dir=tmp_path / "owner")
    packet = next(item for item in owner["ownerReviewPackets"] if item["reviewTrack"] == "HOLD_OWNER_REVIEW")
    checks = {check: True for check in packet["requiredChecks"]}
    result = draft.build_execution_plan_draft(
        report_dir=tmp_path / "draft",
        decisions=[{"packetId": packet["packetId"], "decision": draft.approval_gate.DECISION_REVIEW_APPROVED, "checks": checks}],
    )
    assert result["verdict"] == draft.FAIL_VERDICT
    assert draft.FAIL_APPROVAL_DECISION_NOT_PASS in result["failures"]


def test_07_target_layouts_are_safe_and_planned(tmp_path: Path) -> None:
    result = draft.build_execution_plan_draft(report_dir=tmp_path)
    for item in result["executionPlanCandidates"]:
        assert item["targetLayout"].startswith("planned/")
        assert not item["targetLayout"].startswith("/")
        assert ":" not in item["targetLayout"]


def test_08_security_contract_closed(tmp_path: Path) -> None:
    result = draft.build_execution_plan_draft(report_dir=tmp_path)
    security = result["security"]
    assert security["piiLeak"] == 0
    assert security["rawPathLeak"] == 0
    assert security["rawFilenameLeak"] == 0
    assert security["fileMoveCommandGenerated"] is False
    assert security["fileDeleteCommandGenerated"] is False
    assert security["fileArchiveCommandGenerated"] is False
    assert security["fileMovePerformed"] is False
    assert security["fileDeletePerformed"] is False


def test_09_reports_have_no_leak_patterns(tmp_path: Path) -> None:
    draft.build_execution_plan_draft(report_dir=tmp_path)
    for path in tmp_path.glob("*.json"):
        text = path.read_text(encoding="utf-8")
        assert not draft.ABS_PATH_RE.search(text)
        assert not draft.RAW_FILENAME_RE.search(text)
        assert not draft.PII_RE.search(text)
    text = (tmp_path / "execution_plan_draft_summary.md").read_text(encoding="utf-8")
    assert not draft.ABS_PATH_RE.search(text)
    assert not draft.RAW_FILENAME_RE.search(text)
    assert not draft.PII_RE.search(text)


def test_10_json_reports_valid(tmp_path: Path) -> None:
    draft.build_execution_plan_draft(report_dir=tmp_path)
    json.loads((tmp_path / "execution_plan_draft_summary.json").read_text(encoding="utf-8"))
    json.loads((tmp_path / "execution_plan_candidates.json").read_text(encoding="utf-8"))


def test_11_approval_decision_subrun_linked(tmp_path: Path) -> None:
    draft.build_execution_plan_draft(report_dir=tmp_path)
    assert (tmp_path / "approval_decision_subrun" / "approval_decision_summary.json").is_file()


def test_12_warnings_document_dry_run_only(tmp_path: Path) -> None:
    result = draft.build_execution_plan_draft(report_dir=tmp_path)
    assert "WARN_DRY_RUN_EXECUTION_PLAN_ONLY" in result["warnings"]
    assert "WARN_NO_EXECUTION_COMMAND_GENERATED" in result["warnings"]
