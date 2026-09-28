import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from hwpx_composer import compose_hwpx
from hwpx_document_builder import document
from hwpx_job_schema import validate_compose_job


def test_compose_hwpx_includes_write_gate_and_audit_log(tmp_path: Path) -> None:
    output = tmp_path / "composed.hwpx"
    audit_log = tmp_path / "logs" / "write_audit.jsonl"
    job = {
        "template": "smoke-test.hwpx",
        "output": str(output),
        "paragraphs": [{"text": "write gate paragraph"}],
        "expected_values": ["write gate paragraph"],
        "write_audit_log": {"enabled": True, "path": str(audit_log)},
        "validate": True,
    }

    report = compose_hwpx(job)

    rows = [json.loads(line) for line in audit_log.read_text(encoding="utf-8").splitlines()]
    assert report["status"] == "PASS"
    assert report["write_gate"]["status"] == "PASS"
    assert report["write_gate"]["failed_checks"] == []
    assert report["write_audit_log"] == str(audit_log.resolve())
    assert rows[0]["event"] == "hwpx_write"
    assert rows[0]["write_gate"]["status"] == "PASS"


def test_document_builder_supports_write_audit_log(tmp_path: Path) -> None:
    output = tmp_path / "builder.hwpx"
    audit_log = tmp_path / "builder_audit.jsonl"

    report = (
        document("smoke-test.hwpx", output)
        .paragraph("builder write gate paragraph")
        .expect("builder write gate paragraph")
        .write_audit_log(audit_log)
        .compose()
    )

    assert report["status"] == "PASS"
    assert report["write_gate"]["status"] == "PASS"
    assert Path(report["write_audit_log"]) == audit_log.resolve()
    assert audit_log.exists()


def test_compose_schema_rejects_invalid_audit_log_shape() -> None:
    report = validate_compose_job(
        {
            "template": "smoke-test.hwpx",
            "output": "out.hwpx",
            "write_audit_log": {"enabled": "yes"},
        },
        require_template_exists=False,
    )

    assert report["status"] == "FAIL"
    assert any(error["code"] == "AUDIT_LOG_ENABLED_NOT_BOOLEAN" for error in report["errors"])


def test_compose_hwpx_schema_failure_still_reports_write_gate(tmp_path: Path) -> None:
    audit_log = tmp_path / "schema_fail.jsonl"
    report = compose_hwpx({
        "template": str(tmp_path / "missing.hwpx"),
        "output": str(tmp_path / "missing_out.hwpx"),
        "write_audit_log": str(audit_log),
    })

    row = json.loads(audit_log.read_text(encoding="utf-8").splitlines()[0])
    assert report["status"] == "FAIL"
    assert report["write_gate"]["status"] == "FAIL"
    assert "schema_valid" in report["write_gate"]["failed_checks"]
    assert row["write_gate"]["status"] == "FAIL"
