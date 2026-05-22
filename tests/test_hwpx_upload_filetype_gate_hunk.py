import json
import subprocess
import sys


def test_hwpx_upload_filetype_gate_hunk_audit_runs(tmp_path):
    output = tmp_path / "hwpx_upload_filetype_gate_hunk.json"
    proc = subprocess.run(
        [sys.executable, "scripts/audit_hwpx_upload_filetype_gate_hunk.py", "--json", str(output)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    assert output.exists()
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["audit"] == "hwpx_upload_filetype_upload_gate_hunk"
    assert data["phase"] == "P8E"
    assert data["status"] in {"PASS", "WARN", "FAIL"}
    assert data["handler"]["path"].endswith("HwpxUploadHandler.java")
    assert data["policy"]["no_handler_body_commit"] is True
    assert data["gate_scope"]["ExecutionLocationGate"] == "excluded"
    assert data["gate_scope"]["OutputArtifactGate"] == "excluded"
    assert "actual_value" not in proc.stdout.lower()


def test_p8e_reports_hunk_split_decision():
    import importlib.util
    import sys as _sys
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "audit_hwpx_upload_filetype_gate_hunk",
        Path("scripts/audit_hwpx_upload_filetype_gate_hunk.py"),
    )
    module = importlib.util.module_from_spec(spec)
    _sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    data = module.audit()
    assert data["hunk_split"]["possible"] is False
    assert data["hunk_split"]["commit_handler_body"] is False
    assert data["signals"]["worktree"]["accept_hwpx"] is True
