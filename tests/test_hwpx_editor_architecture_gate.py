"""P13A tests: HWPX editor architecture gate."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "audit_hwpx_editor_architecture_gate.py"

# 이 테스트가 검사하는 Java 백엔드(src/main/java/com/haehan/engine/...)는
# 02 저장소 분리(2026-05-22) 이전 시절의 흔적이다 — 33(office-analysis-engine)
# 소관. 2026-09-28 완성도 감사에서 실측 확인. 02↔33 통합 결정 대기.
pytestmark = pytest.mark.skip(
    reason="Java 백엔드(src/main/java/...)는 33 저장소 소관 — 02 분리 이후 범위 밖 (02↔33 통합 결정 대기)"
)


def run_audit(tmp_path: Path) -> dict:
    out = tmp_path / "result.json"
    subprocess.run(
        [sys.executable, str(SCRIPT), "--json", str(out)],
        check=True,
        capture_output=True,
    )
    return json.loads(out.read_text(encoding="utf-8"))


def test_phase_is_p13a(tmp_path):
    assert run_audit(tmp_path)["phase"] in ("P13A", "P13B", "P14A")


def test_audit_status_not_fail(tmp_path):
    assert run_audit(tmp_path)["status"] != "FAIL", "Architecture gate must not FAIL"


def test_no_fail_findings(tmp_path):
    result = run_audit(tmp_path)
    fails = [f for f in result["findings"] if f["severity"] == "FAIL"]
    assert not fails, f"FAIL findings: {[f['rule'] for f in fails]}"


def test_p13_readiness(tmp_path):
    assert run_audit(tmp_path)["p13_readiness"] is True, "P13 readiness check failed"


def test_arch_docs_present(tmp_path):
    result = run_audit(tmp_path)
    missing = [doc for doc, ok in result["arch_docs"].items() if not ok]
    assert not missing, f"Missing architecture docs: {missing}"


def test_gate_files_present(tmp_path):
    result = run_audit(tmp_path)
    missing = [f for f, ok in result["gate_files"].items() if not ok]
    assert not missing, f"Missing gate files: {missing}"


def test_rule01_ui_command_dispatch(tmp_path):
    assert run_audit(tmp_path)["rules"]["rule01_ui_command_dispatch"], (
        "RULE-01: buildEditorCommand and dispatchEditorCommand must exist"
    )


def test_rule02_no_xml_zip_in_command_dispatch(tmp_path):
    assert run_audit(tmp_path)["rules"]["rule02_no_xml_zip_in_command_dispatch"], (
        "RULE-02: command dispatch must not access BinData/ or Contents/"
    )


def test_rule03_no_raw_path_in_view(tmp_path):
    assert run_audit(tmp_path)["rules"]["rule03_no_raw_path_in_view"], (
        "RULE-03: raw filesystem path must not appear in view/styles HTML"
    )


def test_rule05_handler_uses_usecase(tmp_path):
    assert run_audit(tmp_path)["rules"]["rule05_handler_uses_usecase"], (
        "RULE-05: HwpxEditorApiHandler must reference HwpxEditorCommandUseCase"
    )


def test_rule06_usecase_no_http_import(tmp_path):
    assert run_audit(tmp_path)["rules"]["rule06_usecase_no_http_import"], (
        "RULE-06: HwpxEditorCommandUseCase must not import http package"
    )


def test_rule07_gate_no_side_effects(tmp_path):
    assert run_audit(tmp_path)["rules"]["rule07_gate_no_side_effects"], (
        "RULE-07: HwpxEditorValidationGate must not have side effects"
    )


def test_rule09_apply_deferred_present(tmp_path):
    assert run_audit(tmp_path)["rules"]["rule09_apply_deferred_present"], (
        "RULE-09: APPLY_DEFERRED status must exist in P13"
    )


def test_rule10_endpoints_stable(tmp_path):
    assert run_audit(tmp_path)["rules"]["rule10_endpoints_stable"], (
        "RULE-10: /api/hwpx/editor endpoint must be registered"
    )


def test_rule14_gate_and_test_exist(tmp_path):
    assert run_audit(tmp_path)["rules"]["rule14_gate_and_test_exist"], (
        "RULE-14: architecture gate script and test must exist"
    )


def test_cmd_model_boundary(tmp_path):
    assert run_audit(tmp_path)["rules"]["cmd_model_boundary_ok"], (
        "HwpxEditorCommand must be in contract package without http imports"
    )


def test_policy_flags(tmp_path):
    pol = run_audit(tmp_path)["policy"]
    assert pol["no_endpoint_path_change"]
    assert pol["no_api_response_key_change"]
    assert pol["no_browser_xml_zip_direct"]
    assert pol["no_raw_path_in_ui"]
    assert pol["no_actual_apply_in_p13"]
    assert pol["push_forbidden"]
    assert pol["db_write_forbidden"]
