from pathlib import Path

import hwp_hwp5proc_audit as audit


def test_hwp5proc_audit_skips_when_not_configured(tmp_path: Path) -> None:
    source = tmp_path / "a.hwp"
    source.write_bytes(b"hwp")

    report = audit.audit_hwp5proc_records(None, source)

    assert report["status"] == "SKIPPED"
    assert report["enabled"] is False


def test_attach_hwp5proc_audit_can_fail_closed(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "a.hwp"
    source.write_bytes(b"hwp")
    tool = tmp_path / "hwp5proc.exe"
    tool.write_text("", encoding="utf-8")

    def fake_audit(_tool, _source):
        return {"enabled": True, "status": "FAIL", "reason": "BROKEN"}

    monkeypatch.setattr(audit, "audit_hwp5proc_records", fake_audit)

    result = audit.attach_hwp5proc_audit(
        {"status": "PASS", "input": str(source)},
        hwp5proc=tool,
        require_hwp5proc=True,
    )

    assert result["status"] == "FAIL"
    assert result["error"] == "HWP5PROC_AUDIT_FAILED"
    assert result["hwp5proc_status"] == "FAIL"
