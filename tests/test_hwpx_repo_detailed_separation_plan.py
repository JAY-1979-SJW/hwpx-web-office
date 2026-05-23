"""Tests for repo detailed separation planning and gate linkage."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.ops.plan_hwpx_repo_detailed_separation as separation  # noqa: E402


def test_01_planner_importable() -> None:
    assert hasattr(separation, "plan_detailed_separation")
    assert hasattr(separation, "_build_module_gate_matrix")


def test_02_plan_writes_reports(tmp_path: Path) -> None:
    result = separation.plan_detailed_separation(report_dir=tmp_path)
    assert result["verdict"] == separation.PASS_VERDICT
    assert (tmp_path / "detailed_separation_plan.json").is_file()
    assert (tmp_path / "detailed_separation_matrix.json").is_file()
    assert (tmp_path / "zone_separation_matrix.json").is_file()
    assert (tmp_path / "gate_module_link_matrix.json").is_file()
    assert (tmp_path / "detailed_separation_summary.md").is_file()


def test_03_expected_separation_areas_present(tmp_path: Path) -> None:
    result = separation.plan_detailed_separation(report_dir=tmp_path)
    area_ids = {area["id"] for area in result["areaMatrix"]}
    for expected in [
        "runtime_autofill_line",
        "hwpx_core_library",
        "frontend_viewer_shell",
        "audit_gate_layer",
        "test_support_layer",
        "docs_reports_layer",
        "legacy_experiment_quarantine",
        "config_root_layer",
        "manual_review_hold",
    ]:
        assert expected in area_ids


def test_04_runtime_line_is_protected_by_gates(tmp_path: Path) -> None:
    result = separation.plan_detailed_separation(report_dir=tmp_path)
    runtime = next(area for area in result["areaMatrix"] if area["id"] == "runtime_autofill_line")
    assert runtime["fileCount"] > 0
    assert runtime["action"] == "protect_with_module_audit_and_zone_gate"
    assert runtime["movePolicy"] == "no_move_until_gate_green"


def test_05_release_zones_have_gates(tmp_path: Path) -> None:
    result = separation.plan_detailed_separation(report_dir=tmp_path)
    gate_matrix = result["gateModuleLinkMatrix"]
    assert gate_matrix["allReleaseZonesGated"] is True
    assert set(separation.RELEASE_ZONES).issubset(set(gate_matrix["zoneGateIds"]))


def test_06_all_audited_modules_have_communication(tmp_path: Path) -> None:
    result = separation.plan_detailed_separation(report_dir=tmp_path)
    gate_matrix = result["gateModuleLinkMatrix"]
    assert gate_matrix["allModulesHaveCommunication"] is True
    assert gate_matrix["allZoneModulesKnown"] is True
    assert not gate_matrix["linkErrors"]


def test_07_module_contracts_are_sandbox_only(tmp_path: Path) -> None:
    result = separation.plan_detailed_separation(report_dir=tmp_path)
    gate_matrix = result["gateModuleLinkMatrix"]
    assert not gate_matrix["unsafeModules"]
    for module in gate_matrix["modules"]:
        assert module["safeContract"] is True
        assert module["hasCommunication"] is True
        assert module["hasZoneGate"] is True


def test_08_legacy_and_unknown_are_hold_only(tmp_path: Path) -> None:
    result = separation.plan_detailed_separation(report_dir=tmp_path)
    legacy = next(area for area in result["areaMatrix"] if area["id"] == "legacy_experiment_quarantine")
    unknown = next(area for area in result["areaMatrix"] if area["id"] == "manual_review_hold")
    assert unknown["fileCount"] == result["summary"]["unknownReviewRequiredFiles"]
    assert legacy["movePolicy"] == "no_move_no_delete_without_owner_approval"
    assert unknown["movePolicy"] == "no_move_no_delete_without_owner_approval"
    assert "manual_review_required" in {legacy["gatePolicy"], unknown["gatePolicy"]}


def test_09_security_contract_blocks_unsafe_modes(tmp_path: Path) -> None:
    result = separation.plan_detailed_separation(report_dir=tmp_path)
    security = result["security"]
    assert security["piiLeak"] == 0
    assert security["rawPathLeak"] == 0
    assert security["rawFilenameLeak"] == 0
    assert security["aiApiAllowed"] is False
    assert security["ocrAllowed"] is False
    assert security["hancomRequired"] is False
    assert security["sourceMutationAllowed"] is False
    assert security["productionWriteAllowed"] is False


def test_10_reports_have_no_leak_patterns(tmp_path: Path) -> None:
    separation.plan_detailed_separation(report_dir=tmp_path)
    for path in tmp_path.glob("*.json"):
        text = path.read_text(encoding="utf-8")
        assert not separation.ABS_PATH_RE.search(text)
        assert not separation.RAW_FILENAME_RE.search(text)
        assert not separation.PII_RE.search(text)
    text = (tmp_path / "detailed_separation_summary.md").read_text(encoding="utf-8")
    assert not separation.ABS_PATH_RE.search(text)
    assert not separation.RAW_FILENAME_RE.search(text)
    assert not separation.PII_RE.search(text)


def test_11_zone_matrix_marks_non_release_zones_hold(tmp_path: Path) -> None:
    result = separation.plan_detailed_separation(report_dir=tmp_path)
    for row in result["zoneSeparationMatrix"]:
        if row["zone"] in separation.RELEASE_ZONES:
            assert row["splitReadiness"] == "GATED"
        else:
            assert row["splitReadiness"] == "HOLD_FOR_REVIEW"


def test_12_plan_is_classification_only(tmp_path: Path) -> None:
    result = separation.plan_detailed_separation(report_dir=tmp_path)
    assert result["scope"] == "tracked_files_only_classification_no_move"
    assert "WARN_CLASSIFICATION_ONLY_NO_FILE_MOVE" in result["warnings"]
