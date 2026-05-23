"""Tests for zero-tolerance manifest drift gate."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.ops.gate_hwpx_repo_classification_contract as contract_gate  # noqa: E402
import scripts.ops.gate_hwpx_repo_manifest_drift_zero as gate  # noqa: E402


def test_01_gate_importable() -> None:
    assert hasattr(gate, "run_manifest_drift_zero_gate")
    assert hasattr(gate, "evaluate_manifest_drift_zero_gate")


def test_02_real_repo_zero_gate_passes(tmp_path: Path) -> None:
    result = gate.run_manifest_drift_zero_gate(report_dir=tmp_path)
    assert result["verdict"] == gate.PASS_VERDICT
    assert result["summary"]["stablePathMappedFiles"] == 0
    assert result["summary"]["manifestPromotionCandidates"] == 0


def test_03_stable_path_mapping_detected_fails() -> None:
    contract_payload = {
        "verdict": contract_gate.PASS_VERDICT,
        "summary": {"stablePathMappedFiles": 1},
    }
    promotion_payload = {
        "verdict": "PASS_HWPX_REPO_MANIFEST_PROMOTION_CANDIDATES",
        "summary": {"manifestPromotionCandidates": 0, "modulesAffected": 0, "sourceCandidates": 0, "testCandidates": 0, "auditCandidates": 0},
    }
    result = gate.evaluate_manifest_drift_zero_gate(contract_payload=contract_payload, promotion_payload=promotion_payload)
    assert result["verdict"] == gate.FAIL_VERDICT
    assert gate.FAIL_STABLE_PATH_MAPPING_DETECTED in result["failures"]


def test_04_manifest_promotion_candidate_detected_fails() -> None:
    contract_payload = {
        "verdict": contract_gate.PASS_VERDICT,
        "summary": {"stablePathMappedFiles": 0},
    }
    promotion_payload = {
        "verdict": "PASS_HWPX_REPO_MANIFEST_PROMOTION_CANDIDATES",
        "summary": {"manifestPromotionCandidates": 2, "modulesAffected": 1, "sourceCandidates": 1, "testCandidates": 1, "auditCandidates": 0},
    }
    result = gate.evaluate_manifest_drift_zero_gate(contract_payload=contract_payload, promotion_payload=promotion_payload)
    assert result["verdict"] == gate.FAIL_VERDICT
    assert gate.FAIL_MANIFEST_PROMOTION_CANDIDATE_DETECTED in result["failures"]


def test_05_reports_are_written(tmp_path: Path) -> None:
    gate.run_manifest_drift_zero_gate(report_dir=tmp_path)
    assert (tmp_path / "manifest_drift_zero_summary.json").is_file()
    assert (tmp_path / "manifest_drift_zero_summary.md").is_file()


def test_06_reports_have_no_leaks(tmp_path: Path) -> None:
    gate.run_manifest_drift_zero_gate(report_dir=tmp_path)
    for path in tmp_path.iterdir():
        text = path.read_text(encoding="utf-8")
        assert not contract_gate.inventory.ABS_PATH_RE.search(text)
        assert not contract_gate.inventory.RAW_FILENAME_RE.search(text)
        assert not contract_gate.inventory.PII_RE.search(text)


def test_07_json_report_valid(tmp_path: Path) -> None:
    gate.run_manifest_drift_zero_gate(report_dir=tmp_path)
    json.loads((tmp_path / "manifest_drift_zero_summary.json").read_text(encoding="utf-8"))
