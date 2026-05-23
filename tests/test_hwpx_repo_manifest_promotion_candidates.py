"""Tests for repo manifest promotion candidate builder."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.ops.build_hwpx_repo_manifest_promotion_candidates as builder  # noqa: E402
import scripts.ops.gate_hwpx_repo_classification_contract as contract_gate  # noqa: E402


def test_01_builder_importable() -> None:
    assert hasattr(builder, "build_manifest_promotion_candidates")
    assert hasattr(builder, "evaluate_manifest_promotion_candidates")


def test_02_real_repo_candidates_pass(tmp_path: Path) -> None:
    result = builder.build_manifest_promotion_candidates(report_dir=tmp_path)
    assert result["verdict"] == builder.PASS_VERDICT
    assert result["contractVerdict"] == contract_gate.PASS_VERDICT
    assert result["summary"]["stablePathMappedFiles"] == 24
    assert result["summary"]["manifestPromotionCandidates"] == 24


def test_03_target_key_routing() -> None:
    assert builder._promotion_target_key("tests/test_hwpx_form_field_mapping.py") == "testFiles"
    assert builder._promotion_target_key("scripts/ops/audit_hwpx_form_field_mapping.py") == "auditFiles"
    assert builder._promotion_target_key("scripts/hwpx/pipeline/form_field_mapper.py") == "sourceFiles"


def test_04_unresolved_candidate_fails() -> None:
    contract_payload = {
        "verdict": contract_gate.PASS_VERDICT,
        "summary": {"trackedFiles": 1, "stablePathMappedFiles": 1},
        "existingFileResults": [
            {
                "safePath": "misc/custom.txt",
                "category": "ACTIVE_AUTOFILL",
                "separationPlan": "keep_active",
            }
        ],
        "manifestPromotionCandidates": [
            {
                "safePath": "misc/custom.txt",
                "zone": "input_parse",
                "moduleId": None,
            }
        ],
    }
    result = builder.evaluate_manifest_promotion_candidates(contract_payload=contract_payload)
    assert result["verdict"] == builder.FAIL_VERDICT
    assert builder.FAIL_PROMOTION_TARGET_UNRESOLVED in result["failures"]


def test_05_reports_are_written(tmp_path: Path) -> None:
    builder.build_manifest_promotion_candidates(report_dir=tmp_path)
    assert (tmp_path / "manifest_promotion_candidates_summary.json").is_file()
    assert (tmp_path / "manifest_promotion_candidates.json").is_file()
    assert (tmp_path / "manifest_promotion_module_breakdown.json").is_file()
    assert (tmp_path / "manifest_promotion_candidates_summary.md").is_file()


def test_06_field_mapping_candidates_removed_after_promotion(tmp_path: Path) -> None:
    result = builder.build_manifest_promotion_candidates(report_dir=tmp_path)
    assert "field_mapping" not in result["moduleBreakdown"]
    assert "api_batch" not in result["moduleBreakdown"]
    assert set(result["moduleBreakdown"]) == {"user_flow_closeout"}


def test_07_reports_have_no_leaks(tmp_path: Path) -> None:
    builder.build_manifest_promotion_candidates(report_dir=tmp_path)
    for path in tmp_path.iterdir():
        text = path.read_text(encoding="utf-8")
        assert not builder.inventory.ABS_PATH_RE.search(text)
        assert not builder.inventory.RAW_FILENAME_RE.search(text)
        assert not builder.inventory.PII_RE.search(text)


def test_08_json_reports_valid(tmp_path: Path) -> None:
    builder.build_manifest_promotion_candidates(report_dir=tmp_path)
    json.loads((tmp_path / "manifest_promotion_candidates_summary.json").read_text(encoding="utf-8"))
    json.loads((tmp_path / "manifest_promotion_candidates.json").read_text(encoding="utf-8"))
    json.loads((tmp_path / "manifest_promotion_module_breakdown.json").read_text(encoding="utf-8"))
