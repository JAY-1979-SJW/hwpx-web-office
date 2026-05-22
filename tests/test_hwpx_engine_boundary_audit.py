import json
import subprocess
import sys


def test_hwpx_engine_boundary_audit_runs_and_writes_json(tmp_path):
    output = tmp_path / "hwpx_engine_boundary.json"
    proc = subprocess.run(
        [sys.executable, "scripts/audit_hwpx_engine_boundaries.py", "--json", str(output)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    assert output.exists()
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["audit"] == "hwpx_engine_boundaries"
    assert data["status"] in {"PASS", "WARN", "FAIL"}
    assert "cycle_count" in data
    assert data["hwpx_file_count"] > 0
    assert "actual_value" not in proc.stdout.lower()
