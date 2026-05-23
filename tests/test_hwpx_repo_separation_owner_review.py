"""Tests for repo separation owner review packet generation."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.ops.build_hwpx_repo_separation_owner_review as owner_review  # noqa: E402


def test_01_owner_review_importable() -> None:
    assert hasattr(owner_review, "build_owner_review_packets")
    assert hasattr(owner_review, "_packet_for_package")


def test_02_owner_review_packets_pass(tmp_path: Path) -> None:
    result = owner_review.build_owner_review_packets(report_dir=tmp_path)
    assert result["verdict"] == owner_review.PASS_VERDICT
    assert result["mode"] == "OWNER_REVIEW_PENDING"
    assert result["summary"]["packets"] >= 8


def test_03_reports_are_written(tmp_path: Path) -> None:
    owner_review.build_owner_review_packets(report_dir=tmp_path)
    assert (tmp_path / "owner_review_summary.json").is_file()
    assert (tmp_path / "owner_review_packets.json").is_file()
    assert (tmp_path / "owner_review_summary.md").is_file()


def test_04_all_packets_pending(tmp_path: Path) -> None:
    result = owner_review.build_owner_review_packets(report_dir=tmp_path)
    assert result["summary"]["packets"] == result["summary"]["pendingPackets"]
    assert result["summary"]["approvedPackets"] == 0
    for packet in result["ownerReviewPackets"]:
        assert packet["approvalStatus"] == "PENDING_OWNER_REVIEW"


def test_05_no_packet_approves_execution(tmp_path: Path) -> None:
    result = owner_review.build_owner_review_packets(report_dir=tmp_path)
    for packet in result["ownerReviewPackets"]:
        assert packet["executionAllowed"] is False
        assert packet["approvedForMove"] is False
        assert packet["approvedForDelete"] is False
        assert packet["approvedForArchive"] is False
        assert packet["dryRunOnly"] is True


def test_06_hold_packets_exist(tmp_path: Path) -> None:
    result = owner_review.build_owner_review_packets(report_dir=tmp_path)
    hold_packets = [packet for packet in result["ownerReviewPackets"] if packet["reviewTrack"] == "HOLD_OWNER_REVIEW"]
    assert len(hold_packets) == 2
    assert {packet["areaId"] for packet in hold_packets} == {
        "legacy_experiment_quarantine",
        "manual_review_hold",
    }


def test_07_required_checks_are_present(tmp_path: Path) -> None:
    result = owner_review.build_owner_review_packets(report_dir=tmp_path)
    for packet in result["ownerReviewPackets"]:
        checks = set(packet["requiredChecks"])
        assert "confirm_package_owner" in checks
        assert "confirm_gate_green" in checks
        assert "confirm_no_file_move_delete_archive_without_explicit_approval" in checks


def test_08_security_contract_closed(tmp_path: Path) -> None:
    result = owner_review.build_owner_review_packets(report_dir=tmp_path)
    security = result["security"]
    assert security["piiLeak"] == 0
    assert security["rawPathLeak"] == 0
    assert security["rawFilenameLeak"] == 0
    assert security["fileMoveApproved"] is False
    assert security["fileDeleteApproved"] is False
    assert security["fileArchiveApproved"] is False
    assert security["fileMovePerformed"] is False
    assert security["fileDeletePerformed"] is False


def test_09_reports_have_no_leak_patterns(tmp_path: Path) -> None:
    owner_review.build_owner_review_packets(report_dir=tmp_path)
    for path in tmp_path.glob("*.json"):
        text = path.read_text(encoding="utf-8")
        assert not owner_review.ABS_PATH_RE.search(text)
        assert not owner_review.RAW_FILENAME_RE.search(text)
        assert not owner_review.PII_RE.search(text)
    text = (tmp_path / "owner_review_summary.md").read_text(encoding="utf-8")
    assert not owner_review.ABS_PATH_RE.search(text)
    assert not owner_review.RAW_FILENAME_RE.search(text)
    assert not owner_review.PII_RE.search(text)


def test_10_json_reports_valid(tmp_path: Path) -> None:
    owner_review.build_owner_review_packets(report_dir=tmp_path)
    json.loads((tmp_path / "owner_review_summary.json").read_text(encoding="utf-8"))
    json.loads((tmp_path / "owner_review_packets.json").read_text(encoding="utf-8"))


def test_11_execution_gate_subrun_linked(tmp_path: Path) -> None:
    owner_review.build_owner_review_packets(report_dir=tmp_path)
    assert (tmp_path / "execution_gate_subrun" / "separation_execution_gate_summary.json").is_file()


def test_12_no_failures(tmp_path: Path) -> None:
    result = owner_review.build_owner_review_packets(report_dir=tmp_path)
    assert result["failures"] == []
