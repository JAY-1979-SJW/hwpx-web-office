"""HWPX-FORM-AUTO-FILL-WRITER-REAL-LIKE-SANDBOX-BATCH-10 tests."""

from __future__ import annotations

import json
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from hwpx.pipeline import form_auto_fill_real_file_preflight as pf  # noqa: E402
from hwpx.pipeline import form_auto_fill_real_like_sandbox_batch as batch  # noqa: E402

PII_RE = re.compile(
    r"(\d{6}-\d{7}|\d{3}-\d{2}-\d{5}|\d{2,3}-\d{3,4}-\d{4}|"
    r"\d{2,6}-\d{2,6}-\d{2,6}|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})"
)


def _fixtures(tmp_path: Path, count: int) -> Path:
    return batch.create_batch_fixture_dir(tmp_path / "fixtures", count)


def _run(tmp_path: Path, count: int, limit: int) -> dict:
    return batch.run_real_like_sandbox_batch(
        _fixtures(tmp_path, count),
        tmp_path / "out",
        limit=limit,
        sandbox_only=True,
        mask_pii=True,
        fail_on_source_mutation=True,
        fail_on_readback_fail=True,
        fail_on_unexpected_mutation=True,
    )


def _write_zip(path: Path, files: dict[str, str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, text in files.items():
            archive.writestr(name, text.encode("utf-8"))
    return path


def _section(value: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<hp:sec xmlns:hp="{pf.NS_HP}">'
        f"<hp:tbl><hp:tr><hp:tc><hp:p><hp:run><hp:t>Contractor</hp:t></hp:run></hp:p></hp:tc>"
        f"<hp:tc><hp:p><hp:run><hp:t>{value}</hp:t></hp:run></hp:p></hp:tc></hp:tr></hp:tbl>"
        "</hp:sec>"
    )


def _stub_result(status: str = batch.STATUS_SANDBOX_WRITE_PASS, **overrides) -> dict:
    result = {
        "schemaVersion": pf.SCHEMA_VERSION,
        "sampleId": "stub_sample",
        "mode": "SANDBOX_ONLY",
        "preflightStatus": pf.READY_FOR_SANDBOX_WRITE,
        "sourceMutationAllowed": False,
        "sourceHashBefore": "hash_before_001",
        "sourceHashAfter": "hash_before_001",
        "sourceMtimeChanged": False,
        "structure": {"zipValid": True, "sectionXmlValid": True, "tableCount": 1, "cellCount": 2, "paragraphCount": 2},
        "targetMap": {"resolvedTargets": 1, "ambiguousTargets": 0, "lowConfidenceTargets": 0},
        "sandboxResult": {
            "writtenFields": 1,
            "readbackPass": 1,
            "readbackFail": 0,
            "unexpectedMutation": 0,
            "finalExportEnabled": True,
        },
        "security": {
            "piiLeak": False,
            "rawPathLeak": False,
            "rawFilenameLeak": False,
            "aiCalled": False,
            "ocrCalled": False,
            "hancomRequired": False,
        },
        "warnings": [],
    }
    if status == batch.STATUS_FAILED_READBACK:
        result["sandboxResult"]["readbackFail"] = 1
        result["sandboxResult"]["readbackPass"] = 0
    if status == batch.STATUS_FAILED_UNEXPECTED_MUTATION:
        result["sandboxResult"]["unexpectedMutation"] = 1
    if status == batch.STATUS_FAILED_SOURCE_MUTATED:
        result["sourceHashAfter"] = "hash_after_002"
    for key, value in overrides.items():
        result[key] = value
    return result


def test_01_batch_runner_importable() -> None:
    assert hasattr(batch, "run_real_like_sandbox_batch")
    assert batch.SCHEMA_VERSION == "form_auto_fill_real_like_sandbox_batch_v1"


def test_02_limit_1_supported(tmp_path: Path) -> None:
    result = _run(tmp_path, count=1, limit=1)
    assert result["summary"]["processed"] == 1
    assert result["overallVerdict"] == batch.PASS_REAL_LIKE_SANDBOX_BATCH


def test_03_limit_5_supported(tmp_path: Path) -> None:
    result = _run(tmp_path, count=5, limit=5)
    assert result["summary"]["processed"] == 5
    assert result["summary"]["writtenFiles"] == 5


def test_04_limit_10_supported(tmp_path: Path) -> None:
    result = _run(tmp_path, count=10, limit=10)
    assert result["summary"]["processed"] == 10
    assert result["summary"]["writtenFiles"] == 10


def test_05_missing_input_dir_fails_safely(tmp_path: Path) -> None:
    result = batch.run_real_like_sandbox_batch(
        tmp_path / "missing", tmp_path / "out", limit=1, sandbox_only=True
    )
    assert result["overallVerdict"] == batch.FAIL_NO_INPUT_FILES
    assert result["summary"]["processed"] == 0


def test_06_pii_file_blocked(tmp_path: Path) -> None:
    input_dir = tmp_path / "fixtures"
    _write_zip(input_dir / "pii_case.hwpx", {"Contents/section0.xml": _section("010-1234-5678")})
    result = batch.run_real_like_sandbox_batch(input_dir, tmp_path / "out", limit=1, sandbox_only=True)
    assert result["blockedResults"][0]["blockedReason"] == pf.BLOCKED_PII_RISK


def test_07_invalid_hwpx_blocked(tmp_path: Path) -> None:
    input_dir = tmp_path / "fixtures"
    input_dir.mkdir()
    (input_dir / "invalid_case.hwpx").write_bytes(b"not a zip")
    result = batch.run_real_like_sandbox_batch(input_dir, tmp_path / "out", limit=1, sandbox_only=True)
    assert result["blockedResults"][0]["blockedReason"] == pf.BLOCKED_INVALID_HWPX


def test_08_missing_target_map_blocked(tmp_path: Path) -> None:
    input_dir = _fixtures(tmp_path, 1)
    sample = next(input_dir.glob("*.hwpx"))
    sample_id = batch._sample_id(1, sample)
    result = batch.run_real_like_sandbox_batch(
        input_dir, tmp_path / "out", limit=1, sandbox_only=True,
        target_map_by_sample={sample_id: None},
    )
    assert result["blockedResults"][0]["blockedReason"] == pf.BLOCKED_NO_TARGET_MAP


def test_09_ambiguous_target_blocked(tmp_path: Path) -> None:
    input_dir = _fixtures(tmp_path, 1)
    sample = next(input_dir.glob("*.hwpx"))
    sample_id = batch._sample_id(1, sample)
    targets = pf.default_real_like_target_map() + [
        pf.TargetMapEntry("contractorName", "Contractor", "Contents/section0.xml", 0, 1, 1, 0.91)
    ]
    result = batch.run_real_like_sandbox_batch(
        input_dir, tmp_path / "out", limit=1, sandbox_only=True,
        target_map_by_sample={sample_id: targets},
    )
    assert result["blockedResults"][0]["blockedReason"] == pf.BLOCKED_AMBIGUOUS_TARGET


def test_10_low_confidence_target_blocked(tmp_path: Path) -> None:
    input_dir = _fixtures(tmp_path, 1)
    sample = next(input_dir.glob("*.hwpx"))
    sample_id = batch._sample_id(1, sample)
    targets = pf.default_real_like_target_map()
    targets[0].confidence = 0.79
    result = batch.run_real_like_sandbox_batch(
        input_dir, tmp_path / "out", limit=1, sandbox_only=True,
        target_map_by_sample={sample_id: targets},
    )
    assert result["blockedResults"][0]["blockedReason"] == pf.BLOCKED_LOW_TARGET_CONFIDENCE


def test_11_ready_only_written(tmp_path: Path) -> None:
    input_dir = tmp_path / "fixtures"
    batch.create_batch_fixture_dir(input_dir, 1)
    _write_zip(input_dir / "pii_case.hwpx", {"Contents/section0.xml": _section("010-1234-5678")})
    result = batch.run_real_like_sandbox_batch(input_dir, tmp_path / "out", limit=2, sandbox_only=True)
    assert result["summary"]["writtenFiles"] == 1
    assert result["summary"]["blockedFiles"] == 1


def test_12_sandbox_only_mode(tmp_path: Path) -> None:
    assert _run(tmp_path, 1, 1)["mode"] == "SANDBOX_ONLY"


def test_13_output_path_equals_source_absent(tmp_path: Path) -> None:
    text = json.dumps(_run(tmp_path, 1, 1), ensure_ascii=False)
    assert "output_path" not in text
    assert "source_path" not in text


def test_14_file_source_sha_unchanged(tmp_path: Path) -> None:
    result = _run(tmp_path, 3, 3)
    assert all(not row["sourceHashChanged"] for row in result["fileResults"])


def test_15_file_source_mtime_unchanged(tmp_path: Path) -> None:
    result = _run(tmp_path, 3, 3)
    assert all(not row["sourceMtimeChanged"] for row in result["fileResults"])


def test_16_readback_fail_makes_batch_fail(tmp_path: Path) -> None:
    input_dir = _fixtures(tmp_path, 1)
    result = batch.run_real_like_sandbox_batch(
        input_dir, tmp_path / "out", limit=1, sandbox_only=True,
        preflight_runner=lambda *args: _stub_result(batch.STATUS_FAILED_READBACK),
    )
    assert result["overallVerdict"] == batch.FAIL_READBACK_FAILURE_DETECTED


def test_17_unexpected_mutation_makes_batch_fail(tmp_path: Path) -> None:
    input_dir = _fixtures(tmp_path, 1)
    result = batch.run_real_like_sandbox_batch(
        input_dir, tmp_path / "out", limit=1, sandbox_only=True,
        preflight_runner=lambda *args: _stub_result(batch.STATUS_FAILED_UNEXPECTED_MUTATION),
    )
    assert result["overallVerdict"] == batch.FAIL_UNEXPECTED_MUTATION_DETECTED


def test_18_source_mutation_makes_batch_fail(tmp_path: Path) -> None:
    input_dir = _fixtures(tmp_path, 1)
    result = batch.run_real_like_sandbox_batch(
        input_dir, tmp_path / "out", limit=1, sandbox_only=True,
        preflight_runner=lambda *args: _stub_result(batch.STATUS_FAILED_SOURCE_MUTATED),
    )
    assert result["overallVerdict"] == batch.FAIL_SOURCE_MUTATION_DETECTED


def test_19_blocked_file_not_written(tmp_path: Path) -> None:
    input_dir = tmp_path / "fixtures"
    _write_zip(input_dir / "pii_case.hwpx", {"Contents/section0.xml": _section("010-1234-5678")})
    result = batch.run_real_like_sandbox_batch(input_dir, tmp_path / "out", limit=1, sandbox_only=True)
    assert result["blockedResults"][0]["writtenFields"] == 0


def test_20_blocked_reason_recorded(tmp_path: Path) -> None:
    input_dir = tmp_path / "fixtures"
    _write_zip(input_dir / "pii_case.hwpx", {"Contents/section0.xml": _section("010-1234-5678")})
    result = batch.run_real_like_sandbox_batch(input_dir, tmp_path / "out", limit=1, sandbox_only=True)
    assert result["blockedResults"][0]["blockedReason"] == pf.BLOCKED_PII_RISK


def test_21_final_export_enabled_after_accept_only(tmp_path: Path) -> None:
    accepted = _run(tmp_path / "accepted", 1, 1)
    held = batch.run_real_like_sandbox_batch(
        _fixtures(tmp_path / "held", 1), tmp_path / "held_out", limit=1,
        sandbox_only=True, accept_output=False,
    )
    assert accepted["fileResults"][0]["finalExportEnabled"] is True
    assert held["fileResults"][0]["finalExportEnabled"] is False


def test_22_report_has_no_raw_path(tmp_path: Path) -> None:
    result = _run(tmp_path, 2, 2)
    batch.write_batch_reports(result, tmp_path / "reports")
    text = json.dumps(result, ensure_ascii=False)
    assert not pf.ABS_PATH_RE.search(text)


def test_23_report_has_no_raw_filename(tmp_path: Path) -> None:
    result = _run(tmp_path, 2, 2)
    batch.write_batch_reports(result, tmp_path / "reports")
    text = json.dumps(result, ensure_ascii=False)
    assert not pf.RAW_FILENAME_RE.search(text)


def test_24_report_has_no_pii(tmp_path: Path) -> None:
    result = _run(tmp_path, 2, 2)
    batch.write_batch_reports(result, tmp_path / "reports")
    text = json.dumps(result, ensure_ascii=False)
    assert not PII_RE.search(text)


def test_25_ai_api_not_called() -> None:
    src = (ROOT / "scripts" / "hwpx" / "pipeline" / "form_auto_fill_real_like_sandbox_batch.py").read_text(encoding="utf-8").lower()
    for token in ("openai", "anthropic", "chatcompletion", "gemini"):
        assert token not in src


def test_26_ocr_not_called() -> None:
    src = (ROOT / "scripts" / "hwpx" / "pipeline" / "form_auto_fill_real_like_sandbox_batch.py").read_text(encoding="utf-8").lower()
    for token in ("pytesseract", "easyocr", "paddleocr"):
        assert token not in src


def test_27_hancom_not_required() -> None:
    src = (ROOT / "scripts" / "hwpx" / "pipeline" / "form_auto_fill_real_like_sandbox_batch.py").read_text(encoding="utf-8").lower()
    for token in ("hwp5", "pyhwp", "hwpctrl", "import hancom"):
        assert token not in src


def test_28_previous_real_file_preflight_test_exists() -> None:
    assert (ROOT / "tests" / "test_hwpx_form_auto_fill_real_file_preflight.py").is_file()


def test_29_previous_browser_smoke_test_exists() -> None:
    assert (ROOT / "tests" / "test_hwpx_form_autofill_browser_smoke.py").is_file()


def test_30_previous_api_frontend_tests_exist() -> None:
    assert (ROOT / "tests" / "test_hwpx_form_autofill_api_route.py").is_file()
    assert (ROOT / "tests" / "test_hwpx_form_autofill_frontend_contract.py").is_file()


def test_31_previous_e2e_smoke_test_exists() -> None:
    assert (ROOT / "tests" / "test_hwpx_form_auto_fill_e2e_smoke.py").is_file()


def test_32_previous_writer_chain_tests_exist() -> None:
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

