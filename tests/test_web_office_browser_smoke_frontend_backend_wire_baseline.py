from __future__ import annotations

import json
import subprocess
from pathlib import Path


PR = Path(__file__).resolve().parents[1]
VIEWER = PR / "frontend" / "web_office_viewer"


def test_frontend_backend_wire_node_self_test_passes():
    result = subprocess.run(
        ["node", str(VIEWER / "real_file_load_save_bridge_self_test.mjs")],
        cwd=PR,
        capture_output=True,
        text=True,
        timeout=30,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["task"] == "HWPX-EDITOR-FRONTEND-BACKEND-WIRE-47"
    assert payload["verdict"] == "PASS"


def test_frontend_uses_only_backend_editor_api_routes():
    load_src = (VIEWER / "real_file_load_save_bridge.mjs").read_text(encoding="utf-8")
    save_src = (VIEWER / "save_apply_bridge.mjs").read_text(encoding="utf-8")
    assert '"/api/web-office/hwpx-load"' in load_src
    assert '"/api/web-office/cell-save-apply"' in save_src
    assert "unwrapBackendLoadResponse" in load_src
    assert "unwrapBackendSaveApplyResponse" in save_src


def test_frontend_bridge_has_no_direct_hwpx_writer_or_filesystem_logic():
    combined = "\n".join([
        (VIEWER / "real_file_load_save_bridge.mjs").read_text(encoding="utf-8"),
        (VIEWER / "save_apply_bridge.mjs").read_text(encoding="utf-8"),
    ])
    forbidden = [
        "apply_edit_plan",
        "save_cell_edits",
        "import_hwpx_as_ro_view",
        "outputPath",
        "outputDir",
        "fs.",
        "writeFile",
        "createWriteStream",
        "HwpxPackage",
    ]
    for token in forbidden:
        assert token not in combined, f"forbidden frontend token: {token}"
