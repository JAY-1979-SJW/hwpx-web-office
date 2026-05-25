"""Tests for Web Office monitor structure drift integration."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.ops import install_web_office_server_monitor_cron as cron_installer  # noqa: E402
from scripts.ops import verify_web_office_server_monitor as monitor  # noqa: E402


def test_structure_drift_check_passes() -> None:
    payload = monitor._check_structure_drift(ROOT)
    assert payload["ok"] is True, payload
    assert payload["verdict"] == "PASS_WEB_OFFICE_APP_STRUCTURE_DRIFT_AUDIT"


def test_monitor_attaches_structure_drift_to_healthy_payload() -> None:
    payload = {
        "schemaVersion": monitor.SCHEMA_VERSION,
        "verdict": monitor.PASS_HEALTHY,
        "health": {"ok": True},
    }
    out = monitor._attach_structure_drift(
        payload,
        project_root=ROOT,
        include_structure_drift=True,
    )
    assert out["verdict"] == monitor.PASS_HEALTHY
    assert out["structureDrift"]["ok"] is True


def test_cron_installer_includes_structure_drift_by_default() -> None:
    line = cron_installer.build_reboot_line(ROOT, port=8767, interval=30)
    assert "--include-structure-drift" in line
    assert "hwpx-web-office-monitor" in line


def test_monitor_parser_supports_include_structure_drift() -> None:
    args = monitor._build_parser().parse_args(["--once", "--include-structure-drift"])
    assert isinstance(args, argparse.Namespace)
    assert args.include_structure_drift is True
