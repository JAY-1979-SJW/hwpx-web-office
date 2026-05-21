import json
from pathlib import Path

from hancom_provider_promotion_gate import read_promotion_evidence, validate_promotion_evidence


def valid_evidence(output_path: Path, provider: str = "official_converter") -> dict:
    return {
        "provider": provider,
        "input_path": "sample.hwp",
        "output_path": str(output_path),
        "one_file_success": True,
        "execution_approved": True,
        "verified_at": "2026-05-10T00:00:00Z",
        "output_validation": {
            "status": "PASS",
            "zip_ok": True,
            "xml_ok": True,
        },
    }


def test_promotion_gate_reports_not_provided() -> None:
    result = validate_promotion_evidence(None, "official_converter")

    assert result["status"] == "NOT_PROVIDED"
    assert result["promotable"] is False
    assert result["warnings"]


def test_read_promotion_evidence_handles_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"

    result = validate_promotion_evidence(read_promotion_evidence(missing), "official_converter")

    assert result["status"] == "FAIL"
    assert "PROMOTION_EVIDENCE_NOT_FOUND" in result["errors"]


def test_promotion_gate_requires_success_approval_and_valid_output(tmp_path: Path) -> None:
    output = tmp_path / "sample.hwpx"
    output.write_bytes(b"placeholder")
    evidence = valid_evidence(output)

    result = validate_promotion_evidence(evidence, "official_converter")

    assert result["status"] == "PASS"
    assert result["promotable"] is True


def test_promotion_gate_rejects_provider_mismatch(tmp_path: Path) -> None:
    output = tmp_path / "sample.hwpx"
    output.write_bytes(b"placeholder")
    evidence = valid_evidence(output, provider="com")

    result = validate_promotion_evidence(evidence, "official_converter")

    assert result["status"] == "FAIL"
    assert "PROVIDER_MISMATCH:com!=official_converter" in result["errors"]


def test_read_promotion_evidence_loads_json_object(tmp_path: Path) -> None:
    output = tmp_path / "sample.hwpx"
    output.write_bytes(b"placeholder")
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps(valid_evidence(output)), encoding="utf-8")

    evidence = read_promotion_evidence(path)
    result = validate_promotion_evidence(evidence, "official_converter")

    assert evidence["_path"] == str(path.resolve())
    assert result["promotable"] is True
