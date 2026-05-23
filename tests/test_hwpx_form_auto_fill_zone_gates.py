"""Tests for HWPX form auto-fill zone gates."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.ops.gate_hwpx_form_auto_fill_zones as zone_gate  # noqa: E402


def test_01_zone_manifest_exists() -> None:
    assert zone_gate.MANIFEST.is_file()


def test_02_zone_manifest_valid_json() -> None:
    json.loads(zone_gate.MANIFEST.read_text(encoding="utf-8"))


def test_03_expected_zones_exist() -> None:
    manifest = zone_gate.load_manifest()
    zone_ids = {zone["id"] for zone in manifest["zones"]}
    for expected in [
        "input_parse",
        "review_approval",
        "writer_readback",
        "download_export",
        "batch_api_browser",
        "closeout_security",
    ]:
        assert expected in zone_ids


def test_04_zone_modules_exist_in_module_manifest() -> None:
    zone_manifest = zone_gate.load_manifest()
    module_manifest = zone_gate.module_audit.load_manifest()
    module_ids = {module["id"] for module in module_manifest["modules"]}
    for zone in zone_manifest["zones"]:
        assert zone["modules"]
        assert set(zone["modules"]).issubset(module_ids)


def test_05_runner_importable() -> None:
    assert hasattr(zone_gate, "run_zone_gates")
    assert hasattr(zone_gate, "gate_zone")


def test_06_single_zone_gate_passes(tmp_path: Path) -> None:
    result = zone_gate.run_zone_gates(report_dir=tmp_path, zone_ids={"input_parse"}, timeout=120)
    assert result["verdict"] == zone_gate.PASS_VERDICT
    assert result["summary"]["zonesTotal"] == 1
    assert result["zoneResults"][0]["id"] == "input_parse"


def test_07_report_files_written(tmp_path: Path) -> None:
    zone_gate.run_zone_gates(report_dir=tmp_path, zone_ids={"review_approval"}, timeout=120)
    assert (tmp_path / "zone_gate_summary.json").is_file()
    assert (tmp_path / "zone_gate_results.json").is_file()
    assert (tmp_path / "zone_gate_summary.md").is_file()


def test_08_report_has_no_leak_patterns(tmp_path: Path) -> None:
    zone_gate.run_zone_gates(report_dir=tmp_path, zone_ids={"closeout_security"}, timeout=120)
    text = (tmp_path / "zone_gate_summary.json").read_text(encoding="utf-8")
    assert not zone_gate.ABS_PATH_RE.search(text)
    assert not zone_gate.RAW_FILENAME_RE.search(text)
    assert not zone_gate.PII_RE.search(text)
