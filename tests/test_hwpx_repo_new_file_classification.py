"""Tests for new file classification gate."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.ops.gate_hwpx_repo_new_file_classification as gate  # noqa: E402


def _module_manifest_with(path: str) -> dict[str, object]:
    manifest = gate._load_module_manifest()
    manifest["modules"] = [dict(item) for item in manifest["modules"]]
    manifest["modules"][0]["sourceFiles"] = list(manifest["modules"][0].get("sourceFiles", [])) + [path]
    return manifest


def test_01_gate_importable() -> None:
    assert hasattr(gate, "run_new_file_classification_gate")
    assert hasattr(gate, "evaluate_new_files")


def test_02_declared_pipeline_file_passes(tmp_path: Path) -> None:
    path = "scripts/hwpx/pipeline/form_field_mapper_extension.py"
    result = gate.run_new_file_classification_gate(
        report_dir=tmp_path,
        new_files=[path],
        module_manifest=_module_manifest_with(path),
    )
    assert result["verdict"] == gate.PASS_VERDICT
    assert result["newFileResults"][0]["zone"] == "input_parse"
    assert result["newFileResults"][0]["moduleDeclared"] is True


def test_03_unknown_file_fails(tmp_path: Path) -> None:
    result = gate.run_new_file_classification_gate(
        report_dir=tmp_path,
        new_files=["misc/new_component.xyz"],
    )
    assert result["verdict"] == gate.FAIL_VERDICT
    assert gate.FAIL_NEW_FILE_UNKNOWN_CLASSIFICATION in result["failures"]


def test_04_unassigned_code_file_fails(tmp_path: Path) -> None:
    result = gate.run_new_file_classification_gate(
        report_dir=tmp_path,
        new_files=["scripts/custom/new_guard.py"],
    )
    assert result["verdict"] == gate.FAIL_VERDICT
    assert gate.FAIL_NEW_FILE_UNASSIGNED_ZONE in result["failures"]


def test_05_release_zone_runtime_file_requires_manifest(tmp_path: Path) -> None:
    result = gate.run_new_file_classification_gate(
        report_dir=tmp_path,
        new_files=["scripts/hwpx/pipeline/form_field_mapper_extra.py"],
    )
    assert result["verdict"] == gate.FAIL_VERDICT
    assert gate.FAIL_NEW_FILE_MODULE_MANIFEST_REQUIRED in result["failures"]


def test_06_data_report_file_is_allowed_without_module_manifest(tmp_path: Path) -> None:
    result = gate.run_new_file_classification_gate(
        report_dir=tmp_path,
        new_files=["data/reports/hwpx_demo/sample_report.json"],
    )
    assert result["verdict"] == gate.PASS_VERDICT
    assert result["newFileResults"][0]["category"] == "REPORT_DOC"


def test_07_devlog_and_reports_hold_are_ignored(tmp_path: Path) -> None:
    result = gate.run_new_file_classification_gate(
        report_dir=tmp_path,
        new_files=["docs/devlog/2026-05-23-note.md", "reports/tmp.md"],
    )
    assert result["verdict"] == gate.PASS_VERDICT
    assert result["summary"]["newFiles"] == 0
    assert result["summary"]["ignoredFiles"] == 2


def test_08_web_office_test_file_is_classified(tmp_path: Path) -> None:
    result = gate.run_new_file_classification_gate(
        report_dir=tmp_path,
        new_files=["tests/test_web_office_para_pr_defs.py"],
    )
    assert result["verdict"] == gate.PASS_VERDICT
    assert result["newFileResults"][0]["category"] == "TEST_ONLY"
    assert result["newFileResults"][0]["zone"] == "test_support"


def test_09_results_are_written(tmp_path: Path) -> None:
    gate.run_new_file_classification_gate(report_dir=tmp_path, new_files=[])
    assert (tmp_path / "new_file_classification_summary.json").is_file()
    assert (tmp_path / "new_file_classification_results.json").is_file()
    assert (tmp_path / "new_file_classification_summary.md").is_file()


def test_10_reports_have_no_leaks(tmp_path: Path) -> None:
    gate.run_new_file_classification_gate(report_dir=tmp_path, new_files=["docs/devlog/2026-05-23-note.md"])
    for path in tmp_path.iterdir():
        text = path.read_text(encoding="utf-8")
        assert not gate.inventory.ABS_PATH_RE.search(text)
        assert not gate.inventory.RAW_FILENAME_RE.search(text)
        assert not gate.inventory.PII_RE.search(text)


def test_11_json_reports_valid(tmp_path: Path) -> None:
    gate.run_new_file_classification_gate(report_dir=tmp_path, new_files=[])
    json.loads((tmp_path / "new_file_classification_summary.json").read_text(encoding="utf-8"))
    json.loads((tmp_path / "new_file_classification_results.json").read_text(encoding="utf-8"))
