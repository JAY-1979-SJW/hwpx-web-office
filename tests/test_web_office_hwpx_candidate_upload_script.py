from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ops" / "upload_hwpx_candidates_to_server.ps1"


def test_candidate_upload_script_exists_and_uses_hash_remote_names() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "Get-FileHash" in text
    assert "$remoteName" in text
    assert ".hwpx" in text
    assert "originalFileNameStored = $false" in text


def test_candidate_upload_script_keeps_review_required_policy() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "promotionRequiresApproval = $true" in text
    assert 'promotionStatus = "REVIEW_REQUIRED"' in text
    assert "data/local_corpus_candidates" in text

