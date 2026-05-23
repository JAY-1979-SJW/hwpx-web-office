"""Tests for repo-wide HWPX inventory classification."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.ops.classify_hwpx_repo_inventory as inventory  # noqa: E402


def test_01_classifier_importable() -> None:
    assert hasattr(inventory, "classify_repo")
    assert hasattr(inventory, "classify_file")


def test_02_classifies_known_active_autofill_file() -> None:
    item = inventory.classify_file("scripts/hwpx/pipeline/form_auto_fill_writer_sandbox.py")
    assert item["category"] == "ACTIVE_AUTOFILL"
    assert item["zone"] == "writer_readback"


def test_03_classifies_known_frontend_file() -> None:
    item = inventory.classify_file("frontend/web_office_viewer/components/WebOfficeViewer.tsx")
    assert item["category"] == "FRONTEND_VIEWER"
    assert item["zone"] == "browser_ui"


def test_04_classifies_gate_file() -> None:
    item = inventory.classify_file("scripts/ops/gate_hwpx_form_auto_fill_fail_fast.py")
    assert item["category"] == "AUDIT_GATE"
    assert item["zone"] == "closeout_security"


def test_05_classifies_test_file() -> None:
    item = inventory.classify_file("tests/test_hwpx_form_field_mapping.py")
    assert item["category"] == "TEST_ONLY"
    assert item["zone"] == "input_parse"


def test_06_safe_path_masks_sensitive_patterns() -> None:
    masked = inventory.safe_path("docs/devlog/2026-05-23-sample.hwpx")
    assert "<date>" in masked
    assert "<hwpx-file>" in masked
    assert not inventory.PII_RE.search(masked)
    assert not inventory.RAW_FILENAME_RE.search(masked)


def test_07_classify_repo_writes_reports(tmp_path: Path) -> None:
    result = inventory.classify_repo(report_dir=tmp_path)
    assert result["verdict"] == inventory.PASS_VERDICT
    assert result["summary"]["totalFiles"] > 100
    assert (tmp_path / "repo_inventory.json").is_file()
    assert (tmp_path / "repo_inventory_files.json").is_file()
    assert (tmp_path / "repo_inventory_summary.md").is_file()


def test_08_expected_categories_present(tmp_path: Path) -> None:
    result = inventory.classify_repo(report_dir=tmp_path)
    categories = result["summary"]["categories"]
    for expected in [
        "ACTIVE_AUTOFILL",
        "ACTIVE_HWPX_CORE",
        "FRONTEND_VIEWER",
        "AUDIT_GATE",
        "TEST_ONLY",
        "REPORT_DOC",
        "LEGACY_EXPERIMENT",
    ]:
        assert categories.get(expected, 0) > 0


def test_09_expected_zones_present(tmp_path: Path) -> None:
    result = inventory.classify_repo(report_dir=tmp_path)
    zones = result["summary"]["zones"]
    for expected in [
        "input_parse",
        "review_approval",
        "writer_readback",
        "download_export",
        "batch_api_browser",
        "closeout_security",
        "browser_ui",
        "hwpx_core",
        "docs_reports",
    ]:
        assert zones.get(expected, 0) > 0


def test_10_reports_have_no_leaks(tmp_path: Path) -> None:
    inventory.classify_repo(report_dir=tmp_path)
    for path in tmp_path.iterdir():
        text = path.read_text(encoding="utf-8")
        assert not inventory.ABS_PATH_RE.search(text)
        assert not inventory.RAW_FILENAME_RE.search(text)
        assert not inventory.PII_RE.search(text)


def test_11_report_json_is_valid(tmp_path: Path) -> None:
    inventory.classify_repo(report_dir=tmp_path)
    json.loads((tmp_path / "repo_inventory.json").read_text(encoding="utf-8"))
    json.loads((tmp_path / "repo_inventory_files.json").read_text(encoding="utf-8"))
    json.loads((tmp_path / "repo_inventory_summary.json").read_text(encoding="utf-8"))


def test_12_classification_is_no_move_plan(tmp_path: Path) -> None:
    result = inventory.classify_repo(report_dir=tmp_path)
    assert result["separationRecommendations"]["phase1NoMove"].startswith("classification only")
    assert "do not move or delete" in result["separationRecommendations"]["phase1NoMove"]

