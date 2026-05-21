import json
from pathlib import Path
from zipfile import ZipFile

import hwp_to_hwpx_sdk as sdk
from hwpx_package import package_contains


def test_sdk_convert_file_uses_options_and_extractor(tmp_path: Path) -> None:
    input_path = tmp_path / "source.hwp"
    output_path = tmp_path / "source.hwpx"
    input_path.write_bytes(b"fake fixture; extractor is injected")
    options = sdk.HwpToHwpxOptions.from_values(
        expected_texts=["Body A"],
        strict_quality=True,
        existing_policy="fail",
        embed_original=True,
    )

    def extractor(path: Path) -> dict:
        assert path == input_path.resolve()
        return {
            "ok": True,
            "text": "Body A",
            "sections": [{"name": "BodyText/Section0", "text": "Body A"}],
        }

    report = sdk.convert_file(input_path, output_path, options=options, extractor=extractor)

    assert report["status"] == "PASS"
    assert report["existing_policy"] == "fail"
    assert report["mode"] == "text_only_rebuild_with_embedded_original"
    assert report["text_quality"]["expected_texts"] == ["Body A"]
    assert package_contains(output_path, ["Body A"]) == {"Body A": True}
    with ZipFile(output_path) as zf:
        assert zf.read("Original/original.hwp") == input_path.read_bytes()


def test_sdk_convert_file_writes_log_when_configured(tmp_path: Path) -> None:
    input_path = tmp_path / "source.hwp"
    output_path = tmp_path / "source.hwpx"
    log_path = tmp_path / "sdk.log"
    input_path.write_bytes(b"fake fixture; extractor is injected")
    options = sdk.HwpToHwpxOptions.from_values(log_path=log_path)

    def extractor(_path: Path) -> dict:
        return {
            "ok": True,
            "text": "Body A",
            "sections": [{"name": "BodyText/Section0", "text": "Body A"}],
        }

    report = sdk.convert_file(input_path, output_path, options=options, extractor=extractor)

    assert report["status"] == "PASS"
    assert "sdk_file_complete" in log_path.read_text(encoding="utf-8")


def test_sdk_convert_file_writes_audit_log_when_configured(tmp_path: Path) -> None:
    input_path = tmp_path / "source.hwp"
    output_path = tmp_path / "source.hwpx"
    audit_path = tmp_path / "logs" / "audit.jsonl"
    input_path.write_bytes(b"fake")
    options = sdk.HwpToHwpxOptions.from_values(audit_log_path=audit_path)

    report = sdk.convert_file(
        input_path,
        output_path,
        options=options,
        extractor=lambda _path: {"ok": True, "text": "Body A", "sections": [{"text": "Body A"}]},
    )

    rows = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
    assert report["status"] == "PASS"
    assert rows[0]["event"] == "sdk_file_conversion"
    assert rows[0]["conversion_gate"]["status"] == "PASS"


def test_sdk_forensic_audit_log_includes_result_details(tmp_path: Path) -> None:
    input_path = tmp_path / "source.hwp"
    output_path = tmp_path / "source.hwpx"
    audit_path = tmp_path / "logs" / "audit.jsonl"
    input_path.write_bytes(b"fake")
    options = sdk.HwpToHwpxOptions.from_values(audit_log_path=audit_path, audit_level="forensic")

    report = sdk.convert_file(
        input_path,
        output_path,
        options=options,
        extractor=lambda _path: {"ok": True, "text": "Body A", "sections": [{"text": "Body A"}]},
    )

    row = json.loads(audit_path.read_text(encoding="utf-8").splitlines()[0])
    assert report["status"] == "PASS"
    assert row["audit_level"] == "forensic"
    assert row["result"]["output_info"]["sha256"] == report["output_info"]["sha256"]


def test_sdk_convert_directory_invokes_callback(monkeypatch, tmp_path: Path) -> None:
    options = sdk.HwpToHwpxOptions.from_values(
        expected_texts=["건축법"],
        existing_policy="skip",
        pattern="**/*.hwp",
        fail_fast=True,
        workers=5,
        job_id="sdk-job",
    )
    called = {}

    def fake_batch(input_dir, output_dir, **kwargs):
        called.update({"input_dir": input_dir, "output_dir": output_dir, **kwargs})
        return {
            "status": "PASS",
            "results": [
                {"status": "PASS", "input": "a.hwp", "output": "a.hwpx"},
                {"status": "SKIP", "input": "b.hwp", "output": "b.hwpx"},
            ],
        }

    monkeypatch.setattr(sdk.core, "convert_batch", fake_batch)
    seen = []

    report = sdk.convert_directory(tmp_path / "in", tmp_path / "out", options=options, on_result=seen.append)

    assert report["status"] == "PASS"
    assert called["expected_texts"] == ["건축법"]
    assert called["existing_policy"] == "skip"
    assert called["pattern"] == "**/*.hwp"
    assert called["fail_fast"] is True
    assert called["workers"] == 5
    assert called["job_id"] == "sdk-job"
    assert [row["status"] for row in seen] == ["PASS", "SKIP"]


def test_sdk_plan_directory_uses_core_plan(monkeypatch, tmp_path: Path) -> None:
    options = sdk.HwpToHwpxOptions.from_values(pattern="**/*.hwp", existing_policy="skip")
    called = {}

    def fake_plan(input_dir, output_dir, **kwargs):
        called.update({"input_dir": input_dir, "output_dir": output_dir, **kwargs})
        return {"status": "PASS", "mode": "batch_plan", "target_count": 0}

    monkeypatch.setattr(sdk.core, "build_batch_plan", fake_plan)

    report = sdk.plan_directory(tmp_path / "in", tmp_path / "out", options=options)

    assert report["mode"] == "batch_plan"
    assert called["pattern"] == "**/*.hwp"
    assert called["existing_policy"] == "skip"


def test_sdk_convert_auto_dispatches_to_directory(monkeypatch, tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    called = {}

    def fake_convert_directory(self, input_path, output_path, *, options=None, on_result=None):
        called["input_path"] = input_path
        called["output_path"] = output_path
        return {"status": "PASS", "mode": "batch_text_only_rebuild"}

    monkeypatch.setattr(sdk.HwpToHwpxConverter, "convert_directory", fake_convert_directory)

    report = sdk.convert_auto(input_dir, tmp_path / "out")

    assert report["mode"] == "batch_text_only_rebuild"
    assert called["input_path"] == input_dir


def test_sdk_write_reports_delegates_to_core(monkeypatch, tmp_path: Path) -> None:
    converter = sdk.HwpToHwpxConverter()
    calls = {}
    report = {"status": "PASS"}

    def fake_json(path, data):
        calls["json"] = (path, data)

    def fake_csv(path, data):
        calls["csv"] = (path, data)

    monkeypatch.setattr(sdk.core, "write_report", fake_json)
    monkeypatch.setattr(sdk.core, "write_report_csv", fake_csv)

    converter.write_reports(report, json_path=tmp_path / "report.json", csv_path=tmp_path / "report.csv")

    assert calls["json"][0] == tmp_path / "report.json"
    assert calls["json"][1] == report
    assert calls["csv"][0] == tmp_path / "report.csv"
    assert calls["csv"][1] == report


def test_sdk_rejects_invalid_existing_policy() -> None:
    options = sdk.HwpToHwpxOptions.from_values(existing_policy="bad")

    try:
        sdk.HwpToHwpxConverter(options)
    except sdk.HwpToHwpxSdkError as exc:
        assert "Invalid existing_policy" in str(exc)
    else:
        raise AssertionError("expected HwpToHwpxSdkError")


def test_sdk_rejects_invalid_workers() -> None:
    options = sdk.HwpToHwpxOptions(workers=0)

    try:
        sdk.HwpToHwpxConverter(options)
    except sdk.HwpToHwpxSdkError as exc:
        assert "workers" in str(exc)
    else:
        raise AssertionError("expected HwpToHwpxSdkError")
