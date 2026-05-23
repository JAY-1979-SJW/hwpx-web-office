"""Tests for dry-run repo separation execution gate."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.ops.gate_hwpx_repo_separation_execution as execution_gate  # noqa: E402


def test_01_execution_gate_importable() -> None:
    assert hasattr(execution_gate, "run_execution_gate")
    assert hasattr(execution_gate, "_build_execution_matrix")


def test_02_default_dry_run_passes(tmp_path: Path) -> None:
    result = execution_gate.run_execution_gate(report_dir=tmp_path)
    assert result["verdict"] == execution_gate.PASS_VERDICT
    assert result["mode"] == "DRY_RUN_ONLY"
    assert result["executionAllowed"] is False
    assert result["summary"]["packages"] >= 8


def test_03_reports_are_written(tmp_path: Path) -> None:
    execution_gate.run_execution_gate(report_dir=tmp_path)
    assert (tmp_path / "separation_execution_gate_summary.json").is_file()
    assert (tmp_path / "separation_execution_matrix.json").is_file()
    assert (tmp_path / "separation_execution_gate_summary.md").is_file()


def test_04_all_packages_are_dry_run_only(tmp_path: Path) -> None:
    result = execution_gate.run_execution_gate(report_dir=tmp_path)
    for package in result["executionMatrix"]:
        assert package["dryRunOnly"] is True
        assert package["executionAllowedNow"] is False
    assert result["summary"]["executionAllowedPackages"] == 0


def test_05_legacy_and_unknown_are_hold_only(tmp_path: Path) -> None:
    result = execution_gate.run_execution_gate(report_dir=tmp_path)
    by_area = {item["areaId"]: item for item in result["executionMatrix"]}
    assert by_area["legacy_experiment_quarantine"]["operation"] == "HOLD_ONLY"
    assert by_area["manual_review_hold"]["operation"] == "HOLD_ONLY"
    assert by_area["legacy_experiment_quarantine"]["phase"] == "P0_HOLD"
    assert by_area["manual_review_hold"]["phase"] == "P0_HOLD"


def test_06_runtime_and_gate_layer_are_review_only(tmp_path: Path) -> None:
    result = execution_gate.run_execution_gate(report_dir=tmp_path)
    by_area = {item["areaId"]: item for item in result["executionMatrix"]}
    assert by_area["runtime_autofill_line"]["operation"] == "REVIEW_AND_GATE_ONLY"
    assert by_area["audit_gate_layer"]["operation"] == "REVIEW_AND_GATE_ONLY"


def test_07_execution_request_is_blocked_without_owner(tmp_path: Path) -> None:
    result = execution_gate.run_execution_gate(report_dir=tmp_path, request_execution=True)
    assert result["verdict"] == execution_gate.BLOCKED_VERDICT
    assert execution_gate.BLOCKED_OWNER_REVIEW_REQUIRED in result["blockedReasons"]
    assert execution_gate.BLOCKED_MOVE_DELETE_NOT_ALLOWED in result["blockedReasons"]
    assert result["security"]["fileMovePerformed"] is False
    assert result["security"]["fileDeletePerformed"] is False


def test_08_execution_request_still_does_not_move_with_owner(tmp_path: Path) -> None:
    result = execution_gate.run_execution_gate(
        report_dir=tmp_path,
        request_execution=True,
        owner_approved=True,
    )
    assert result["verdict"] == execution_gate.BLOCKED_VERDICT
    assert execution_gate.BLOCKED_OWNER_REVIEW_REQUIRED not in result["blockedReasons"]
    assert execution_gate.BLOCKED_MOVE_DELETE_NOT_ALLOWED in result["blockedReasons"]
    assert result["executionAllowed"] is False


def test_09_security_contract_is_closed(tmp_path: Path) -> None:
    result = execution_gate.run_execution_gate(report_dir=tmp_path)
    security = result["security"]
    assert security["piiLeak"] == 0
    assert security["rawPathLeak"] == 0
    assert security["rawFilenameLeak"] == 0
    assert security["sourceMutationAllowed"] is False
    assert security["productionWriteAllowed"] is False


def test_10_reports_have_no_leak_patterns(tmp_path: Path) -> None:
    execution_gate.run_execution_gate(report_dir=tmp_path)
    for path in tmp_path.glob("*.json"):
        text = path.read_text(encoding="utf-8")
        assert not execution_gate.ABS_PATH_RE.search(text)
        assert not execution_gate.RAW_FILENAME_RE.search(text)
        assert not execution_gate.PII_RE.search(text)
    text = (tmp_path / "separation_execution_gate_summary.md").read_text(encoding="utf-8")
    assert not execution_gate.ABS_PATH_RE.search(text)
    assert not execution_gate.RAW_FILENAME_RE.search(text)
    assert not execution_gate.PII_RE.search(text)


def test_11_json_reports_are_valid(tmp_path: Path) -> None:
    execution_gate.run_execution_gate(report_dir=tmp_path)
    json.loads((tmp_path / "separation_execution_gate_summary.json").read_text(encoding="utf-8"))
    json.loads((tmp_path / "separation_execution_matrix.json").read_text(encoding="utf-8"))


def test_12_detailed_plan_is_linked(tmp_path: Path) -> None:
    result = execution_gate.run_execution_gate(report_dir=tmp_path)
    assert result["summary"]["releaseZonesGated"] == 6
    assert result["summary"]["holdZones"] >= 1
    assert (tmp_path / "detailed_plan_subrun" / "detailed_separation_plan.json").is_file()
