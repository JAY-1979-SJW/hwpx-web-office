"""Contract tests for the Web Office server deploy verifier."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ops" / "deploy_web_office_to_server.ps1"


def _script_text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_deploy_verifier_exists() -> None:
    assert SCRIPT.is_file()


def test_deploy_verifier_uses_server_as_final_authority() -> None:
    text = _script_text()
    assert "ssh" in text
    assert "tar -xf" in text
    assert "verify_web_office_server_monitor.py --once" in text
    assert '"verdict":\\s*"(HEALTHY|RECOVERED)"' in text
    assert '"sandboxMode":\\s*true' in text
    assert '"sourceMutationBlocked":\\s*true' in text


def test_deploy_verifier_requires_monitor_process_and_cron() -> None:
    text = _script_text()
    assert "install_web_office_server_monitor_cron.py --port" in text
    assert "--include-structure-drift" in text
    assert "pgrep -af 'python3 scripts/ops/verify_web_office_server_monitor.py --interval'" in text
    assert "serverMonitorProcessOk" in text
    assert "serverMonitorCronOk" in text
    assert "serverMonitorIncludesStructureDriftOk" in text
    assert "hwpx-web-office-monitor" in text
    assert "monitorProcessOk" in text
    assert "monitorCronOk" in text


def test_deploy_verifier_requires_structure_drift_audit() -> None:
    text = _script_text()
    assert "audit_web_office_app_structure_drift.py" in text
    assert "PASS_WEB_OFFICE_APP_STRUCTURE_DRIFT_AUDIT" in text
    assert "serverStructureDriftOk" in text


def test_deploy_verifier_syncs_fixture_corpus_and_runs_read_audit() -> None:
    text = _script_text()
    assert "tests\\fixtures\\hwpx\\corpus" in text
    assert "scp fixture corpus" in text
    assert "audit_web_office_hwpx_read_remediation.py --no-write" in text
    assert "PASS_WEB_OFFICE_HWPX_READ_REMEDIATION_CURRENT_SCOPE" in text
    assert '"hwpxFileCount":\\s*5' in text
    assert '"unsupportedCategorySummary"' in text
    assert "serverHwpxReadRemediationAuditOk" in text
    assert "serverFixtureCorpusOk" in text
    assert "serverUnsupportedCategorySummaryOk" in text


def test_deploy_verifier_runs_backend_runtime_smoke_on_server() -> None:
    text = _script_text()
    assert "verify_web_office_editor_backend_runtime_smoke.py" in text
    assert "PASS_HWPX_EDITOR_BACKEND_RUNTIME_SMOKE" in text
    assert "serverBackendRuntimeSmokeOk" in text


def test_deploy_verifier_requires_operating_rule_documents() -> None:
    text = _script_text()
    assert "RULE-13" in text
    assert "Operational Completion Rule" in text
    assert "serverOperatingRulePresent" in text
    assert "serverBackendStandardPresent" in text


def test_deploy_verifier_blocks_dirty_local_tree_by_default() -> None:
    text = _script_text()
    assert "SkipLocalStatusCheck" in text
    assert "working tree is not clean" in text
    assert "localWorkingTreeClean" in text
