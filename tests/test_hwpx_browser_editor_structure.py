"""P11A/P12/P13 tests: HWPX browser editor product focus structure audit."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "audit_hwpx_browser_editor_structure.py"


def run_audit(tmp_path: Path) -> dict:
    out = tmp_path / "result.json"
    subprocess.run(
        [sys.executable, str(SCRIPT), "--json", str(out)],
        check=True, capture_output=True,
    )
    return json.loads(out.read_text(encoding="utf-8"))


def test_audit_status_pass(tmp_path):
    result = run_audit(tmp_path)
    assert result["status"] == "PASS", f"Expected PASS, got {result['status']}. Findings: {result['findings']}"


def test_all_arch_docs_present(tmp_path):
    result = run_audit(tmp_path)
    for doc, exists in result["arch_docs"].items():
        assert exists, f"Architecture doc missing: {doc}"


def test_editor_handlers_present(tmp_path):
    result = run_audit(tmp_path)
    for handler, exists in result["editor_handlers"].items():
        assert exists, f"Editor handler missing: {handler}"


def test_usecases_present(tmp_path):
    result = run_audit(tmp_path)
    for uc, exists in result["usecases"].items():
        assert exists, f"Usecase missing: {uc}"


def test_gates_present(tmp_path):
    result = run_audit(tmp_path)
    for gate, exists in result["gates"].items():
        assert exists, f"Gate missing: {gate}"


def test_editor_endpoint_registered(tmp_path):
    result = run_audit(tmp_path)
    assert result["editor_endpoint_registered"], "/api/hwpx/editor must be registered in EngineHttpServer"


def test_exec_gate_user_present_enforced(tmp_path):
    result = run_audit(tmp_path)
    assert result["exec_gate"]["user_present_required_enforced"], \
        "ExecutionLocationGate must enforce USER_PRESENT_REQUIRED"


def test_filetype_gate_hwpx_allowed(tmp_path):
    result = run_audit(tmp_path)
    assert result["filetype_gate"]["hwpx_allowed"], "FileTypeGate must allow .hwpx"


def test_no_fail_findings(tmp_path):
    result = run_audit(tmp_path)
    fail_findings = [f for f in result["findings"] if f["severity"] == "FAIL"]
    assert not fail_findings, f"Must have no FAIL findings, got: {fail_findings}"


def test_phase_is_p13(tmp_path):
    result = run_audit(tmp_path)
    assert result["phase"] == "P13"


def test_p12_usecases_present(tmp_path):
    result = run_audit(tmp_path)
    for uc, exists in result["p12"]["usecases"].items():
        assert exists, f"P12 usecase missing: {uc}"


def test_p12_gates_present(tmp_path):
    result = run_audit(tmp_path)
    for gate, exists in result["p12"]["gates"].items():
        assert exists, f"P12 gate missing: {gate}"


def test_p12_contracts_present(tmp_path):
    result = run_audit(tmp_path)
    for contract, exists in result["p12"]["contracts"].items():
        assert exists, f"P12 contract missing: {contract}"


def test_p12_usecase_no_http_import(tmp_path):
    result = run_audit(tmp_path)
    assert result["p12"]["usecase_no_http_import"], \
        "HwpxEditorCommandUseCase must not import http package"


def test_p12_gate_no_side_effects(tmp_path):
    result = run_audit(tmp_path)
    assert result["p12"]["gate_no_side_effects"], \
        "HwpxEditorValidationGate must have no side effects"


def test_p12_gate_raw_path_check(tmp_path):
    result = run_audit(tmp_path)
    assert result["p12"]["gate_raw_path_check"], \
        "HwpxEditorValidationGate must check for raw filesystem paths"


def test_p12_gate_forbidden_key_check(tmp_path):
    result = run_audit(tmp_path)
    assert result["p12"]["gate_forbidden_key_check"], \
        "HwpxEditorValidationGate must check for forbidden security-sensitive keys"


def test_p13_phase(tmp_path):
    result = run_audit(tmp_path)
    assert result["phase"] == "P13"


def test_p13_build_editor_command(tmp_path):
    assert run_audit(tmp_path)["p13"]["build_editor_command"], \
        "buildEditorCommand must be present in HwpxUploadPageScripts"


def test_p13_dispatch_editor_command(tmp_path):
    assert run_audit(tmp_path)["p13"]["dispatch_editor_command"], \
        "dispatchEditorCommand must be present in HwpxUploadPageScripts"


def test_p13_render_editor_command_result(tmp_path):
    assert run_audit(tmp_path)["p13"]["render_editor_command_result"], \
        "renderEditorCommandResult must be present in HwpxUploadPageScripts"


def test_p13_validate_editor_document(tmp_path):
    assert run_audit(tmp_path)["p13"]["validate_editor_document"], \
        "validateEditorDocument must be present in HwpxUploadPageScripts"


def test_p13_handler_wired_to_usecase(tmp_path):
    assert run_audit(tmp_path)["p13"]["handler_wired_to_usecase"], \
        "HwpxEditorApiHandler must reference HwpxEditorCommandUseCase"


def test_p13_handler_wired_to_command(tmp_path):
    assert run_audit(tmp_path)["p13"]["handler_wired_to_command"], \
        "HwpxEditorApiHandler must reference HwpxEditorCommand"


def test_p13_no_xml_zip_in_scripts(tmp_path):
    assert run_audit(tmp_path)["p13"]["no_xml_zip_in_scripts"], \
        "Browser scripts must not contain BinData/ or Contents/ (XML/ZIP access forbidden)"


def test_p13_dry_run_default_true(tmp_path):
    assert run_audit(tmp_path)["p13"]["dry_run_default_true"], \
        "Command dispatch must default dryRun to true"


def test_policy_flags(tmp_path):
    result = run_audit(tmp_path)
    policy = result["policy"]
    assert policy["no_endpoint_path_change"]
    assert policy["no_existing_gate_change"]
    assert policy["no_browser_hwpx_direct_access"]
    assert policy["no_hancom_auto_run"]
    assert policy["push_forbidden"]
    assert policy["db_write_forbidden"]
