"""Tests for existing governed file classification gate."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.ops.gate_hwpx_repo_existing_file_classification as gate  # noqa: E402
import scripts.ops.gate_hwpx_repo_new_file_classification as new_file_gate  # noqa: E402


def _module_manifest_with(path: str) -> dict[str, object]:
    manifest = new_file_gate._load_module_manifest()
    manifest["modules"] = [dict(item) for item in manifest["modules"]]
    manifest["modules"][0]["sourceFiles"] = list(manifest["modules"][0].get("sourceFiles", [])) + [path]
    return manifest


def test_01_gate_importable() -> None:
    assert hasattr(gate, "run_existing_file_classification_gate")
    assert hasattr(gate, "evaluate_existing_files")


def test_02_real_repo_governed_scope_passes(tmp_path: Path) -> None:
    result = gate.run_existing_file_classification_gate(report_dir=tmp_path)
    assert result["verdict"] == gate.PASS_VERDICT
    assert result["summary"]["governedFiles"] > 0
    assert result["summary"]["failedFiles"] == 0


def test_03_unknown_governed_file_fails(tmp_path: Path) -> None:
    result = gate.run_existing_file_classification_gate(
        report_dir=tmp_path,
        tracked_files=["app/backend/routes/hwpx_form_unknown.py"],
    )
    assert result["verdict"] == gate.FAIL_VERDICT
    assert new_file_gate.FAIL_NEW_FILE_UNKNOWN_CLASSIFICATION in result["failures"]


def test_04_unassigned_governed_code_file_fails(tmp_path: Path) -> None:
    result = gate.run_existing_file_classification_gate(
        report_dir=tmp_path,
        tracked_files=["scripts/hwpx/pipeline/form_auto_fill_custom_guard.py"],
    )
    assert result["verdict"] == gate.FAIL_VERDICT
    assert new_file_gate.FAIL_NEW_FILE_UNASSIGNED_ZONE in result["failures"]


def test_05_release_zone_governed_file_requires_manifest(tmp_path: Path) -> None:
    result = gate.run_existing_file_classification_gate(
        report_dir=tmp_path,
        tracked_files=["frontend/web_office_viewer/form_autofill_custom_panel.html"],
    )
    assert result["verdict"] == gate.FAIL_VERDICT
    assert gate.FAIL_EXISTING_FILE_MODULE_UNRESOLVED in result["failures"]


def test_06_release_zone_governed_file_with_manifest_passes(tmp_path: Path) -> None:
    path = "frontend/web_office_viewer/form_autofill_custom_panel.html"
    result = gate.run_existing_file_classification_gate(
        report_dir=tmp_path,
        tracked_files=[path],
        module_manifest=_module_manifest_with(path),
    )
    assert result["verdict"] == gate.PASS_VERDICT
    assert result["summary"]["passedFiles"] == 1


def test_07_reports_are_written(tmp_path: Path) -> None:
    gate.run_existing_file_classification_gate(report_dir=tmp_path, tracked_files=[])
    assert (tmp_path / "existing_file_classification_summary.json").is_file()
    assert (tmp_path / "existing_file_classification_results.json").is_file()
    assert (tmp_path / "existing_file_classification_summary.md").is_file()


def test_08_reports_have_no_leaks(tmp_path: Path) -> None:
    gate.run_existing_file_classification_gate(report_dir=tmp_path, tracked_files=[])
    for path in tmp_path.iterdir():
        text = path.read_text(encoding="utf-8")
        assert not gate.inventory.ABS_PATH_RE.search(text)
        assert not gate.inventory.RAW_FILENAME_RE.search(text)
        assert not gate.inventory.PII_RE.search(text)


def test_09_json_reports_valid(tmp_path: Path) -> None:
    gate.run_existing_file_classification_gate(report_dir=tmp_path, tracked_files=[])
    json.loads((tmp_path / "existing_file_classification_summary.json").read_text(encoding="utf-8"))
    json.loads((tmp_path / "existing_file_classification_results.json").read_text(encoding="utf-8"))
