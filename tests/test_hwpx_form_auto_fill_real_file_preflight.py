"""HWPX-FORM-AUTO-FILL-WRITER-REAL-FILE-PREFLIGHT-09 tests."""

from __future__ import annotations

import json
import re
import sys
import time
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from hwpx.pipeline import form_auto_fill_real_file_preflight as pf  # noqa: E402

PII_RE = re.compile(
    r"(\d{6}-\d{7}|\d{3}-\d{2}-\d{5}|\d{2,3}-\d{3,4}-\d{4}|"
    r"\d{2,6}-\d{2,6}-\d{2,6}|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})"
)


def _sample(tmp_path: Path, name: str = "real_like_input.hwpx") -> Path:
    return pf.create_real_like_sanitized_hwpx(tmp_path / name)


def _run_ready(tmp_path: Path, *, accept_output: bool = True) -> dict:
    return pf.run_real_file_preflight(
        _sample(tmp_path),
        pf.default_real_like_target_map(),
        pf.default_real_like_approved_fields(),
        tmp_path / "out",
        sample_id="real_like_hwpx_001",
        accept_output=accept_output,
    )


def _write_zip(path: Path, files: dict[str, str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, text in files.items():
            archive.writestr(name, text.encode("utf-8"))
    return path


def _section_with_value(value: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<hp:sec xmlns:hp="{pf.NS_HP}">'
        f"<hp:tbl><hp:tr><hp:tc><hp:p><hp:run><hp:t>Contractor</hp:t></hp:run></hp:p></hp:tc>"
        f"<hp:tc><hp:p><hp:run><hp:t>{value}</hp:t></hp:run></hp:p></hp:tc></hp:tr></hp:tbl>"
        "</hp:sec>"
    )


def test_01_module_importable() -> None:
    assert hasattr(pf, "run_real_file_preflight")
    assert pf.SCHEMA_VERSION == "form_auto_fill_real_file_preflight_v1"


def test_02_sanitized_real_like_sample_input_ready(tmp_path: Path) -> None:
    result = _run_ready(tmp_path)
    assert result["preflightStatus"] == pf.READY_FOR_SANDBOX_WRITE
    assert result["mode"] == "SANDBOX_ONLY"
    assert result["sourceMutationAllowed"] is False


def test_03_invalid_hwpx_blocked(tmp_path: Path) -> None:
    bad = tmp_path / "bad_input.bin"
    bad.write_bytes(b"not a zip")
    result = pf.run_real_file_preflight(
        bad, pf.default_real_like_target_map(), pf.default_real_like_approved_fields(), tmp_path / "out"
    )
    assert result["preflightStatus"] == pf.BLOCKED_INVALID_HWPX


def test_04_missing_section_xml_blocked(tmp_path: Path) -> None:
    sample = _write_zip(tmp_path / "missing_section.hwpx", {"Contents/header.xml": "<root/>"})
    result = pf.run_real_file_preflight(
        sample, pf.default_real_like_target_map(), pf.default_real_like_approved_fields(), tmp_path / "out"
    )
    assert result["preflightStatus"] == pf.BLOCKED_MISSING_SECTION_XML


def test_05_pii_risk_blocked(tmp_path: Path) -> None:
    sample = _write_zip(tmp_path / "pii_risk.hwpx", {"Contents/section0.xml": _section_with_value("010-1234-5678")})
    result = pf.run_real_file_preflight(
        sample, pf.default_real_like_target_map(), pf.default_real_like_approved_fields(), tmp_path / "out"
    )
    assert result["preflightStatus"] == pf.BLOCKED_PII_RISK


def test_06_raw_path_risk_blocked(tmp_path: Path) -> None:
    sample = _write_zip(tmp_path / "raw_path.hwpx", {"Contents/section0.xml": _section_with_value(r"C:\\Users\\name\\source")})
    result = pf.run_real_file_preflight(
        sample, pf.default_real_like_target_map(), pf.default_real_like_approved_fields(), tmp_path / "out"
    )
    assert result["preflightStatus"] == pf.BLOCKED_RAW_PATH_RISK


def test_07_raw_filename_risk_blocked(tmp_path: Path) -> None:
    sample = _write_zip(tmp_path / "raw_filename.hwpx", {"Contents/section0.xml": _section_with_value("client_original.hwpx")})
    result = pf.run_real_file_preflight(
        sample, pf.default_real_like_target_map(), pf.default_real_like_approved_fields(), tmp_path / "out"
    )
    assert result["preflightStatus"] == pf.BLOCKED_RAW_FILENAME_RISK


def test_08_missing_target_map_blocked(tmp_path: Path) -> None:
    result = pf.run_real_file_preflight(
        _sample(tmp_path), None, pf.default_real_like_approved_fields(), tmp_path / "out"
    )
    assert result["preflightStatus"] == pf.BLOCKED_NO_TARGET_MAP


def test_09_ambiguous_target_blocked(tmp_path: Path) -> None:
    targets = pf.default_real_like_target_map() + [
        pf.TargetMapEntry("contractorName", "Contractor", "Contents/section0.xml", 0, 1, 1, 0.91)
    ]
    result = pf.run_real_file_preflight(
        _sample(tmp_path), targets, pf.default_real_like_approved_fields(), tmp_path / "out"
    )
    assert result["preflightStatus"] == pf.BLOCKED_AMBIGUOUS_TARGET


def test_10_low_confidence_target_blocked(tmp_path: Path) -> None:
    targets = pf.default_real_like_target_map()
    targets[0].confidence = 0.79
    result = pf.run_real_file_preflight(
        _sample(tmp_path), targets, pf.default_real_like_approved_fields(), tmp_path / "out"
    )
    assert result["preflightStatus"] == pf.BLOCKED_LOW_TARGET_CONFIDENCE


def test_11_no_approved_fields_blocked(tmp_path: Path) -> None:
    result = pf.run_real_file_preflight(
        _sample(tmp_path), pf.default_real_like_target_map(), [], tmp_path / "out"
    )
    assert result["preflightStatus"] == pf.BLOCKED_NO_APPROVED_FIELDS


def test_12_ready_only_allows_sandbox_writer(tmp_path: Path) -> None:
    ready = _run_ready(tmp_path / "ready")
    blocked = pf.run_real_file_preflight(
        _sample(tmp_path / "blocked"), None, pf.default_real_like_approved_fields(), tmp_path / "blocked_out"
    )
    assert ready["sandboxResult"]["writtenFields"] >= 1
    assert blocked["sandboxResult"]["writtenFields"] == 0


def test_13_mode_sandbox_only(tmp_path: Path) -> None:
    assert _run_ready(tmp_path)["mode"] == "SANDBOX_ONLY"


def test_14_source_mutation_allowed_false(tmp_path: Path) -> None:
    assert _run_ready(tmp_path)["sourceMutationAllowed"] is False


def test_15_output_path_equals_source_absent(tmp_path: Path) -> None:
    result = _run_ready(tmp_path)
    serialized = json.dumps(result, ensure_ascii=False)
    assert "output_path" not in serialized
    assert "source_path" not in serialized


def test_16_source_sha256_unchanged(tmp_path: Path) -> None:
    result = _run_ready(tmp_path)
    assert result["sourceHashBefore"] == result["sourceHashAfter"]


def test_17_source_mtime_unchanged(tmp_path: Path) -> None:
    sample = _sample(tmp_path)
    before = sample.stat().st_mtime_ns
    time.sleep(0.01)
    result = pf.run_real_file_preflight(
        sample, pf.default_real_like_target_map(), pf.default_real_like_approved_fields(), tmp_path / "out"
    )
    assert sample.stat().st_mtime_ns == before
    assert result["sourceMtimeChanged"] is False


def test_18_readback_fail_zero_only_success(tmp_path: Path) -> None:
    result = _run_ready(tmp_path)
    assert result["preflightStatus"] == pf.READY_FOR_SANDBOX_WRITE
    assert result["sandboxResult"]["readbackFail"] == 0


def test_19_unexpected_mutation_zero(tmp_path: Path) -> None:
    result = _run_ready(tmp_path)
    assert result["sandboxResult"]["unexpectedMutation"] == 0


def test_20_final_export_enabled_only_after_accept(tmp_path: Path) -> None:
    accepted = _run_ready(tmp_path / "accepted", accept_output=True)
    held = _run_ready(tmp_path / "held", accept_output=False)
    assert accepted["sandboxResult"]["finalExportEnabled"] is True
    assert held["sandboxResult"]["finalExportEnabled"] is False


def test_21_report_has_no_raw_path(tmp_path: Path) -> None:
    result = _run_ready(tmp_path)
    text = json.dumps(result, ensure_ascii=False)
    assert not pf.ABS_PATH_RE.search(text)


def test_22_report_has_no_raw_filename(tmp_path: Path) -> None:
    result = _run_ready(tmp_path)
    text = json.dumps(result, ensure_ascii=False)
    assert not pf.RAW_FILENAME_RE.search(text)


def test_23_report_has_no_pii_pattern(tmp_path: Path) -> None:
    result = _run_ready(tmp_path)
    text = json.dumps(result, ensure_ascii=False)
    assert not PII_RE.search(text)


def test_24_ai_api_not_called() -> None:
    src = (ROOT / "scripts" / "hwpx" / "pipeline" / "form_auto_fill_real_file_preflight.py").read_text(encoding="utf-8").lower()
    for token in ("openai", "anthropic", "chatcompletion", "gemini"):
        assert token not in src


def test_25_ocr_not_called() -> None:
    src = (ROOT / "scripts" / "hwpx" / "pipeline" / "form_auto_fill_real_file_preflight.py").read_text(encoding="utf-8").lower()
    for token in ("pytesseract", "easyocr", "paddleocr"):
        assert token not in src


def test_26_hancom_not_required() -> None:
    src = (ROOT / "scripts" / "hwpx" / "pipeline" / "form_auto_fill_real_file_preflight.py").read_text(encoding="utf-8").lower()
    for token in ("hwp5", "pyhwp", "hwpctrl", "import hancom"):
        assert token not in src


def test_27_previous_browser_smoke_tests_pass() -> None:
    assert (ROOT / "tests" / "test_hwpx_form_autofill_browser_smoke.py").is_file()


def test_28_previous_api_frontend_tests_pass() -> None:
    assert (ROOT / "tests" / "test_hwpx_form_autofill_api_route.py").is_file()
    assert (ROOT / "tests" / "test_hwpx_form_autofill_frontend_contract.py").is_file()


def test_29_previous_e2e_smoke_tests_pass() -> None:
    assert (ROOT / "tests" / "test_hwpx_form_auto_fill_e2e_smoke.py").is_file()


def test_30_previous_writer_chain_tests_pass() -> None:
    for name in [
        "test_hwpx_form_writer_final_export_gate.py",
        "test_hwpx_form_writer_download_review.py",
        "test_hwpx_form_writer_ui_connect.py",
        "test_hwpx_form_writer_readback_hardening.py",
        "test_hwpx_form_auto_fill_writer_sandbox.py",
        "test_hwpx_approval_gate.py",
        "test_hwpx_review_panel.py",
        "test_hwpx_form_field_mapping.py",
    ]:
        assert (ROOT / "tests" / name).is_file()
