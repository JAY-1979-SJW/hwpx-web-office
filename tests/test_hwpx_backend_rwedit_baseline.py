"""Backend HWPX read/write/edit baseline runner contract."""
from __future__ import annotations

import json

from scripts.ops.verify_hwpx_backend_rwedit_baseline import verify


def test_backend_rwedit_baseline_passes():
    result = verify()
    assert result["verdict"] == "PASS", json.dumps(
        result, ensure_ascii=False, indent=2)
    assert result["paragraph"]["verdict"] == "PASS"
    assert result["cell"]["verdict"] == "PASS"
    assert result["findings"] == []
