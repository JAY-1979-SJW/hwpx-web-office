"""Tests for unified repo classification contract gate."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.ops.gate_hwpx_repo_classification_contract as gate  # noqa: E402
import scripts.ops.gate_hwpx_repo_existing_file_classification as existing_gate  # noqa: E402
import scripts.ops.gate_hwpx_repo_new_file_classification as new_gate  # noqa: E402


def _module_manifest_with(path: str) -> dict[str, object]:
    manifest = new_gate._load_module_manifest()
    manifest["modules"] = [dict(item) for item in manifest["modules"]]
    manifest["modules"][0]["sourceFiles"] = list(manifest["modules"][0].get("sourceFiles", [])) + [path]
    return manifest


def test_01_gate_importable() -> None:
    assert hasattr(gate, "run_repo_classification_contract_gate")
    assert hasattr(gate, "evaluate_repo_classification_contract")


def test_02_real_repo_contract_passes(tmp_path: Path) -> None:
    result = gate.run_repo_classification_contract_gate(report_dir=tmp_path)
    assert result["verdict"] == gate.PASS_VERDICT
    assert result["existingVerdict"] == existing_gate.PASS_VERDICT
    assert result["newVerdict"] == new_gate.PASS_VERDICT
    assert result["summary"]["stablePathMappedFiles"] == 37
    assert result["summary"]["manifestPromotionCandidates"] == 37


def test_03_existing_failure_fails_contract(tmp_path: Path) -> None:
    result = gate.run_repo_classification_contract_gate(
        report_dir=tmp_path,
        tracked_files=["scripts/hwpx/pipeline/form_auto_fill_custom_guard.py"],
    )
    assert result["verdict"] == gate.FAIL_VERDICT
    assert new_gate.FAIL_NEW_FILE_UNASSIGNED_ZONE in result["failures"]


def test_04_new_failure_fails_contract(tmp_path: Path) -> None:
    result = gate.run_repo_classification_contract_gate(
        report_dir=tmp_path,
        new_files=["frontend/web_office_viewer/form_autofill_custom_panel.html"],
    )
    assert result["verdict"] == gate.FAIL_VERDICT
    assert new_gate.FAIL_NEW_FILE_MODULE_MANIFEST_REQUIRED in result["failures"]


def test_05_stable_mapping_candidates_are_reported(tmp_path: Path) -> None:
    result = gate.run_repo_classification_contract_gate(report_dir=tmp_path)
    assert result["summary"]["stablePathMappedFiles"] >= 1
    assert result["summary"]["manifestPromotionCandidates"] >= 1
    assert all(item["moduleId"] for item in result["stablePathMappedFiles"])
    assert all(item["moduleId"] != "field_mapping" for item in result["stablePathMappedFiles"])


def test_06_manifest_declared_new_file_reduces_failure(tmp_path: Path) -> None:
    path = "frontend/web_office_viewer/form_autofill_custom_panel.html"
    result = gate.run_repo_classification_contract_gate(
        report_dir=tmp_path,
        new_files=[path],
        module_manifest=_module_manifest_with(path),
    )
    assert result["newVerdict"] == new_gate.PASS_VERDICT


def test_07_reports_are_written(tmp_path: Path) -> None:
    gate.run_repo_classification_contract_gate(report_dir=tmp_path, tracked_files=[], new_files=[])
    assert (tmp_path / "repo_classification_contract_summary.json").is_file()
    assert (tmp_path / "stable_path_mapping_candidates.json").is_file()
    assert (tmp_path / "manifest_promotion_candidates.json").is_file()
    assert (tmp_path / "repo_classification_contract_summary.md").is_file()


def test_08_reports_have_no_leaks(tmp_path: Path) -> None:
    gate.run_repo_classification_contract_gate(report_dir=tmp_path, tracked_files=[], new_files=[])
    for path in tmp_path.iterdir():
        text = path.read_text(encoding="utf-8")
        assert not gate.inventory.ABS_PATH_RE.search(text)
        assert not gate.inventory.RAW_FILENAME_RE.search(text)
        assert not gate.inventory.PII_RE.search(text)


def test_09_json_reports_valid(tmp_path: Path) -> None:
    gate.run_repo_classification_contract_gate(report_dir=tmp_path, tracked_files=[], new_files=[])
    json.loads((tmp_path / "repo_classification_contract_summary.json").read_text(encoding="utf-8"))
    json.loads((tmp_path / "stable_path_mapping_candidates.json").read_text(encoding="utf-8"))
    json.loads((tmp_path / "manifest_promotion_candidates.json").read_text(encoding="utf-8"))
