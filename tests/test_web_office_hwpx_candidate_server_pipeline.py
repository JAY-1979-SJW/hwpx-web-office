from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ops" / "run_hwpx_candidate_server_pipeline.ps1"


def test_candidate_server_pipeline_wraps_upload_and_background_scan() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "upload_hwpx_candidates_to_server.ps1" in text
    assert "run_web_office_hwpx_corpus_candidate_scan.py" in text
    assert "--background" in text
    assert "candidate_scan_report.json" in text
    assert "candidate_manifest_draft.json" in text
    assert "PIPELINE_SCAN_SUMMARY_JSON" in text


def test_candidate_server_pipeline_preserves_review_required_policy() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "automaticPromotionAllowed = $false" in text
    assert "promotionRequiresApproval = $true" in text
    assert "promotionRequiresApproval" in text
