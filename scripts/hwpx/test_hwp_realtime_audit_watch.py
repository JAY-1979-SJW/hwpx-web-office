import json
from pathlib import Path

import hwp_hwp5proc_audit
import hwp_to_hwpx_standalone as core
import openhwp_rust_probe
from hwp_realtime_audit_watch import run_realtime_watch


def test_realtime_watch_writes_cycle_audit_and_summaries(monkeypatch, tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    audit_log = tmp_path / "audit.jsonl"
    summary_json = tmp_path / "summary.json"
    summary_md = tmp_path / "summary.md"
    input_dir.mkdir()
    (input_dir / "a.hwp").write_bytes(b"a")

    def fake_target(target, output, **_kwargs):
        core.write_text_hwpx(output, [target.stem], original_hwp_path=target)
        return {
            "status": "PASS",
            "input": str(target),
            "output": str(output),
            "conversion_gate": {"status": "PASS", "failed_checks": []},
        }

    monkeypatch.setattr(core, "convert_batch_target", fake_target)

    report = run_realtime_watch(
        input_dir,
        output_dir,
        interval_sec=0.1,
        max_cycles=1,
        audit_log=audit_log,
        audit_level="forensic",
        summary_json=summary_json,
        summary_md=summary_md,
        job_id="rt-1",
    )

    assert report["status"] == "PASS"
    assert report["job_id"] == "rt-1"
    assert report["cycle_count"] == 1
    assert report["detected_count"] == 1
    assert report["identity_audit"]["enabled"] is True
    assert report["identity_audit"]["identity_fail_count"] == 1
    assert report["hwp5proc_audit"]["enabled"] is False
    assert report["openhwp_audit"]["enabled"] is False
    assert report["results"][0]["identity_status"] == "FAIL"
    assert (output_dir / "a.hwpx").exists()
    assert summary_json.exists()
    assert summary_md.exists()
    assert json.loads(summary_json.read_text(encoding="utf-8"))["ok_count"] == 1
    assert "Realtime Detection" in summary_md.read_text(encoding="utf-8")

    rows = [json.loads(line) for line in audit_log.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert [row["event"] for row in rows] == ["realtime_watch_cycle", "realtime_conversion_item"]
    assert rows[0]["job_id"] == "rt-1"
    assert rows[0]["ok_count"] == 1
    assert rows[1]["result"]["status"] == "PASS"
    assert rows[1]["result"]["identity_status"] == "FAIL"
    assert rows[1]["cycle"] == 1


def test_realtime_watch_can_require_identity(monkeypatch, tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    (input_dir / "a.hwp").write_bytes(b"a")

    def fake_target(target, output, **_kwargs):
        core.write_text_hwpx(output, [target.stem], original_hwp_path=target)
        return {
            "status": "PASS",
            "input": str(target),
            "output": str(output),
            "conversion_gate": {"status": "PASS", "failed_checks": []},
        }

    monkeypatch.setattr(core, "convert_batch_target", fake_target)

    report = run_realtime_watch(
        input_dir,
        output_dir,
        interval_sec=0.1,
        max_cycles=1,
        require_identity=True,
    )

    assert report["status"] == "FAIL"
    assert report["fail_count"] == 1
    assert report["results"][0]["error"] == "IDENTITY_AUDIT_FAILED"


def test_realtime_watch_attaches_hwp5proc_audit(monkeypatch, tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    source = input_dir / "a.hwp"
    source.write_bytes(b"a")
    hwp5proc = tmp_path / "hwp5proc.exe"
    hwp5proc.write_text("", encoding="utf-8")

    def fake_target(target, output, **_kwargs):
        core.write_text_hwpx(output, [target.stem], original_hwp_path=target)
        return {
            "status": "PASS",
            "input": str(target),
            "output": str(output),
            "conversion_gate": {"status": "PASS", "failed_checks": []},
        }

    def fake_hwp5proc_audit(result, *, hwp5proc, require_hwp5proc=False):
        audited = dict(result)
        audited["hwp5proc_status"] = "PASS"
        audited["hwp5proc_audit"] = {
            "enabled": True,
            "status": "PASS",
            "hwp5proc": str(hwp5proc),
            "source": audited["input"],
        }
        return audited

    monkeypatch.setattr(core, "convert_batch_target", fake_target)
    monkeypatch.setattr(hwp_hwp5proc_audit, "attach_hwp5proc_audit", fake_hwp5proc_audit)

    report = run_realtime_watch(
        input_dir,
        output_dir,
        interval_sec=0.1,
        max_cycles=1,
        hwp5proc=hwp5proc,
    )

    assert report["status"] == "PASS"
    assert report["hwp5proc_audit"]["enabled"] is True
    assert report["hwp5proc_audit"]["hwp5proc_pass_count"] == 1
    assert report["results"][0]["hwp5proc_status"] == "PASS"


def test_realtime_watch_attaches_openhwp_audit(monkeypatch, tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    (input_dir / "a.hwp").write_bytes(b"a")
    openhwp_root = tmp_path / "oss_openhwp"
    openhwp_root.mkdir()

    def fake_target(target, output, **_kwargs):
        core.write_text_hwpx(output, [target.stem], original_hwp_path=target)
        return {
            "status": "PASS",
            "input": str(target),
            "output": str(output),
            "conversion_gate": {"status": "PASS", "failed_checks": []},
        }

    def fake_openhwp_probe(input_path, **_kwargs):
        return {
            "enabled": True,
            "status": "PASS",
            "input": str(input_path),
            "version": "5.1.0.1",
            "section_count": 1,
            "paragraph_count": 1,
            "text_length": 1,
        }

    monkeypatch.setattr(core, "convert_batch_target", fake_target)
    monkeypatch.setattr(openhwp_rust_probe, "run_probe", fake_openhwp_probe)

    report = run_realtime_watch(
        input_dir,
        output_dir,
        interval_sec=0.1,
        max_cycles=1,
        openhwp_root=openhwp_root,
    )

    assert report["status"] == "PASS"
    assert report["openhwp_audit"]["enabled"] is True
    assert report["openhwp_audit"]["openhwp_pass_count"] == 1
    assert report["results"][0]["openhwp_status"] == "PASS"
