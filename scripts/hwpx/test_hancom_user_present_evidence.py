import json
from argparse import Namespace
from pathlib import Path
from zipfile import ZipFile

from hancom_provider_promotion_gate import read_promotion_evidence, validate_promotion_evidence
from hancom_user_present_evidence import build_promotion_evidence, run


HWP_OLE_SIGNATURE = bytes.fromhex("D0CF11E0A1B11AE1")


def write_minimal_hwpx(path: Path) -> None:
    with ZipFile(path, "w") as zf:
        zf.writestr("mimetype", "application/hwp+zip")
        zf.writestr("Contents/section0.xml", "<root><p>ok</p></root>")


def successful_user_present_result(input_path: Path, output_path: Path) -> dict[str, object]:
    return {
        "ok": True,
        "provider": "HANCOM_USER_PRESENT_GUI",
        "stage": "OUTPUT_CHECK_DONE",
        "status": "USER_PRESENT_OUTPUT_VALID",
        "input_path": str(input_path),
        "output_path": str(output_path),
        "output_exists": True,
        "output_size": output_path.stat().st_size,
        "zip_valid": True,
        "zip_entries": 2,
        "zip_error": None,
    }


def write_hwp_signature_fixture(path: Path) -> None:
    path.write_bytes(HWP_OLE_SIGNATURE + b"placeholder")


def test_build_promotion_evidence_from_successful_user_present_result(tmp_path: Path) -> None:
    input_path = tmp_path / "source.hwp"
    output_path = tmp_path / "source.hwpx"
    write_hwp_signature_fixture(input_path)
    write_minimal_hwpx(output_path)

    evidence = build_promotion_evidence(
        successful_user_present_result(input_path, output_path),
        execution_approved=True,
    )
    gate = validate_promotion_evidence(evidence, "user_present")

    assert evidence["provider"] == "user_present"
    assert evidence["one_file_success"] is True
    assert evidence["input_validation"]["hwp_binary_signature_ok"] is True
    assert evidence["output_validation"]["zip_ok"] is True
    assert evidence["output_validation"]["xml_ok"] is True
    assert gate["status"] == "PASS"
    assert gate["promotable"] is True


def test_build_promotion_evidence_keeps_approval_explicit(tmp_path: Path) -> None:
    input_path = tmp_path / "source.hwp"
    output_path = tmp_path / "source.hwpx"
    write_hwp_signature_fixture(input_path)
    write_minimal_hwpx(output_path)

    evidence = build_promotion_evidence(
        successful_user_present_result(input_path, output_path),
        execution_approved=False,
    )
    gate = validate_promotion_evidence(evidence, "user_present")

    assert evidence["one_file_success"] is True
    assert gate["status"] == "FAIL"
    assert "EXECUTION_APPROVED_NOT_TRUE" in gate["errors"]


def test_build_promotion_evidence_rejects_fake_hwp_input(tmp_path: Path) -> None:
    input_path = tmp_path / "source.hwp"
    output_path = tmp_path / "source.hwpx"
    input_path.write_bytes(b"hwp-placeholder")
    write_minimal_hwpx(output_path)

    evidence = build_promotion_evidence(
        successful_user_present_result(input_path, output_path),
        execution_approved=True,
    )
    gate = validate_promotion_evidence(evidence, "user_present")

    assert evidence["one_file_success"] is False
    assert evidence["input_validation"]["status"] == "FAIL"
    assert gate["status"] == "FAIL"
    assert "ONE_FILE_SUCCESS_NOT_TRUE" in gate["errors"]


def test_run_writes_user_present_promotion_evidence_json(tmp_path: Path) -> None:
    input_path = tmp_path / "source.hwp"
    output_path = tmp_path / "source.hwpx"
    result_path = tmp_path / "user_present_result.json"
    evidence_path = tmp_path / "promotion_evidence.json"
    write_hwp_signature_fixture(input_path)
    write_minimal_hwpx(output_path)
    result_path.write_text(
        json.dumps(successful_user_present_result(input_path, output_path), ensure_ascii=False),
        encoding="utf-8",
    )

    result = run(
        Namespace(
            result_json=str(result_path),
            evidence_json=str(evidence_path),
            execution_approved=True,
            input_path=None,
            output_path=None,
        )
    )
    gate = validate_promotion_evidence(read_promotion_evidence(evidence_path), "user_present")

    assert result["status"] == "PASS"
    assert evidence_path.exists()
    assert gate["status"] == "PASS"
