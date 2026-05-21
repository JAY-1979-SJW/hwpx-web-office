from pathlib import Path
from zipfile import ZipFile

import hwp_native_com_batch as native


def write_hwpx(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(path, "w") as zf:
        zf.writestr("mimetype", "application/hwp+zip")
        zf.writestr("Contents/header.xml", "<root/>")
        zf.writestr("Contents/section0.xml", "<root/>")
        zf.writestr("Contents/content.hpf", "<root/>")
        zf.writestr("META-INF/container.xml", "<root/>")


def test_native_batch_stages_ascii_input_and_restores_relative_output(monkeypatch, tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    source = input_dir / "nested" / "원본.hwp"
    source.parent.mkdir(parents=True)
    source.write_bytes(bytes.fromhex("D0CF11E0A1B11AE1") + b"body")
    output_dir = tmp_path / "out"
    staging = tmp_path / "staging"

    def fake_convert(staged_input, staged_output_dir, *_args):
        staged_output = staged_output_dir / f"{staged_input.stem}.hwpx"
        write_hwpx(staged_output)
        return {
            "ok": True,
            "provider": native.HWP_CONVERSION_PROVIDER,
            "output": str(staged_output),
            "error_code": "HANCOM_CONVERSION_SUCCESS",
            "converter_json": {
                "ok": True,
                "provider": "hancom-com-powershell-v2",
                "stage": "END",
                "outputSize": staged_output.stat().st_size,
                "zipValid": True,
                "warningCount": 0,
                "errorCode": None,
                "elapsedMs": 1,
            },
        }

    monkeypatch.setattr(native, "convert_one_with_strategy", fake_convert)
    monkeypatch.setattr(
        native,
        "build_gate_report",
        lambda *_args, **_kwargs: {"status": "WARN", "machine_ok": True, "visual_review": {"status": "USER_PRESENT_REQUIRED"}},
    )

    report = native.run_batch(
        input_dir,
        output_dir,
        staging_dir=staging,
        diag_dir=tmp_path / "diag",
        report_json=tmp_path / "report.json",
        audit_jsonl=tmp_path / "audit.jsonl",
        pattern="*.hwp",
        limit=0,
        timeout_sec=1,
        save_strategy="direct",
    )

    assert report["status"] == "PASS"
    assert report["ok_count"] == 1
    assert (staging / "000001.hwp").exists()
    assert (output_dir / "nested" / "원본.hwpx").exists()
    assert report["results"][0]["native_identity_audit"]["status"] == "PASS"
    assert report["results"][0]["native_identity_audit"]["visual_review_required"] is True


def test_native_batch_skips_existing_outputs_and_writes_csv(monkeypatch, tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    source = input_dir / "forms" / "a.hwp"
    source.parent.mkdir(parents=True)
    source.write_bytes(bytes.fromhex("D0CF11E0A1B11AE1") + b"body")
    output_dir = tmp_path / "out"
    existing_output = output_dir / "forms" / "a.hwpx"
    write_hwpx(existing_output)

    def should_not_convert(*_args, **_kwargs):
        raise AssertionError("existing output should have been skipped")

    monkeypatch.setattr(native, "convert_one_with_strategy", should_not_convert)

    report = native.run_batch(
        input_dir,
        output_dir,
        staging_dir=tmp_path / "staging",
        diag_dir=tmp_path / "diag",
        report_json=tmp_path / "report.json",
        audit_jsonl=tmp_path / "audit.jsonl",
        report_csv=tmp_path / "report.csv",
        pattern="*.hwp",
        limit=0,
        timeout_sec=1,
        save_strategy="direct",
        existing_policy="skip",
    )

    assert report["status"] == "PASS"
    assert report["ok_count"] == 0
    assert report["skip_count"] == 1
    assert report["fail_count"] == 0
    assert report["results"][0]["status"] == "SKIP"
    csv_text = (tmp_path / "report.csv").read_text(encoding="utf-8-sig")
    assert "OUTPUT_EXISTS" in csv_text


def test_native_batch_dry_run_plans_without_converter(monkeypatch, tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    source = input_dir / "a.hwp"
    source.parent.mkdir(parents=True)
    source.write_bytes(bytes.fromhex("D0CF11E0A1B11AE1") + b"body")

    def should_not_convert(*_args, **_kwargs):
        raise AssertionError("dry run should not call Hancom converter")

    monkeypatch.setattr(native, "convert_one_with_strategy", should_not_convert)

    report = native.run_batch(
        input_dir,
        tmp_path / "out",
        staging_dir=tmp_path / "staging",
        diag_dir=tmp_path / "diag",
        report_json=tmp_path / "report.json",
        audit_jsonl=None,
        pattern="*.hwp",
        limit=0,
        timeout_sec=1,
        save_strategy="direct",
        dry_run=True,
    )

    assert report["status"] == "PASS"
    assert report["plan_count"] == 1
    assert report["results"][0]["status"] == "PLAN"
    assert not (tmp_path / "out" / "a.hwpx").exists()


def test_native_batch_lock_blocks_concurrent_runs(tmp_path: Path) -> None:
    lock_file = tmp_path / "worker.lock"
    with native.BatchLock(lock_file):
        try:
            with native.BatchLock(lock_file):
                raise AssertionError("second lock should not be acquired")
        except RuntimeError as exc:
            assert "BATCH_LOCK_EXISTS" in str(exc)
    assert not lock_file.exists()
