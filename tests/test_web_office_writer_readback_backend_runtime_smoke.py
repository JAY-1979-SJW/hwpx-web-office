from __future__ import annotations

import sys
from pathlib import Path

PR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PR))

from scripts.ops.verify_web_office_editor_backend_runtime_smoke import (  # noqa: E402
    PASS_VERDICT,
    run_runtime_smoke,
)


def test_backend_runtime_smoke_passes_over_real_http(tmp_path):
    payload = run_runtime_smoke(project_root=PR, runtime_output_dir=tmp_path)
    assert payload["verdict"] == PASS_VERDICT, payload
    checks = payload["checks"]
    for key, value in checks.items():
        assert value is True, f"{key} failed: {payload}"
    assert payload["output"]["outputFileName"] == "runtime-smoke-46.hwpx"
