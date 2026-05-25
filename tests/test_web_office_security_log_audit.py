"""Tests for the read-only Web Office security log audit."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.ops import audit_web_office_security_logs as audit_mod  # noqa: E402


def test_security_log_audit_runs_read_only() -> None:
    payload = audit_mod.audit(project_root=ROOT, tail_lines=20, include_journal=False)
    assert payload["verdict"] in {audit_mod.PASS_VERDICT, audit_mod.WARN_VERDICT}
    assert payload["scope"] == "read_only_log_audit_no_firewall_change"
    assert payload["summary"]["logsChecked"] == len(audit_mod.DEFAULT_LOG_CANDIDATES)


def test_security_patterns_cover_auth_and_runtime_signals() -> None:
    required = {
        "failed_password",
        "invalid_user",
        "authentication_failure",
        "http_4xx_5xx",
        "structure_drift_detected",
        "monitor_down",
    }
    assert required.issubset(set(audit_mod.SUSPICIOUS_PATTERNS))


def test_security_log_audit_does_not_change_firewall_policy() -> None:
    source = (ROOT / "scripts/ops/audit_web_office_security_logs.py").read_text(encoding="utf-8")
    forbidden = ["ufw allow", "ufw deny", "iptables", "firewall-cmd", "nft add"]
    for token in forbidden:
        assert token not in source


def test_pattern_count_detects_suspicious_samples() -> None:
    sample = (
        "Failed password for invalid user admin from 203.0.113.10\n"
        '"GET /bad HTTP/1.1" 404 10\n'
        '{"verdict": "STRUCTURE_DRIFT_DETECTED"}\n'
    )
    counts = audit_mod._count_patterns(sample)
    assert counts["failed_password"] == 1
    assert counts["invalid_user"] == 1
    assert counts["http_4xx_5xx"] == 1
    assert counts["structure_drift_detected"] == 1
