"""P9E audit tests: HwpxDownloadExportUseCase boundary readiness."""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

# 이 테스트가 검사하는 Java 백엔드(HwpxDownloadExportUseCase.java 등)는 02
# 저장소 분리(2026-05-22) 이전 시절의 흔적이다 — 33(office-analysis-engine)
# 소관. 2026-09-28 완성도 감사에서 실측 확인(11개 중 8개가 이 이유로 FAIL,
# 나머지 3개도 파일이 없어 공허하게 통과하는 정적 검사라 파일 전체를 skip
# 처리). 02↔33 통합 결정 대기.
pytestmark = pytest.mark.skip(
    reason="Java 백엔드(src/main/java/...)는 33 저장소 소관 — 02 분리 이후 범위 밖 (02↔33 통합 결정 대기)"
)


def run_audit(tmp_path):
    output = tmp_path / "hwpx_download_export_usecase.json"
    subprocess.run(
        [sys.executable, "scripts/audit_hwpx_download_export_usecase.py", "--json", str(output)],
        text=True,
        capture_output=True,
        check=True,
    )
    return json.loads(output.read_text(encoding="utf-8"))


def test_audit_status_is_pass_or_warn(tmp_path):
    result = run_audit(tmp_path)
    assert result["status"] in {"PASS", "WARN"}, (
        f"Expected PASS or WARN, got: {result['status']}\nFindings: {result['findings']}"
    )


def test_usecase_and_result_files_exist(tmp_path):
    result = run_audit(tmp_path)
    assert result["usecase"]["exists"], "HwpxDownloadExportUseCase.java must exist"
    assert result["result"]["exists"], "HwpxDownloadExportResult.java must exist"


def test_output_artifact_gate_present(tmp_path):
    result = run_audit(tmp_path)
    assert result["gate_presence"]["OutputArtifactGate"], "OutputArtifactGate.java must exist"


def test_usecase_no_http_import(tmp_path):
    result = run_audit(tmp_path)
    assert result["usecase"]["no_http_import"], (
        "HwpxDownloadExportUseCase must not import from http package"
    )


def test_usecase_uses_output_artifact_gate(tmp_path):
    result = run_audit(tmp_path)
    assert result["usecase"]["uses_output_artifact_gate"], (
        "HwpxDownloadExportUseCase must reference OutputArtifactGate"
    )


def test_usecase_uses_sanitize_download_name(tmp_path):
    result = run_audit(tmp_path)
    assert result["usecase"]["uses_sanitize_download_name"], (
        "HwpxDownloadExportUseCase must call sanitizeDownloadName"
    )


def test_usecase_uses_new_artifact_id(tmp_path):
    result = run_audit(tmp_path)
    assert result["usecase"]["uses_new_artifact_id"], (
        "HwpxDownloadExportUseCase must call newArtifactId"
    )


def test_js_functions_preserved(tmp_path):
    result = run_audit(tmp_path)
    js = result["js_functions_preserved"]
    assert js["downloadBlob"], "downloadBlob JS function must be present"
    assert js["downloadRawBlob"], "downloadRawBlob JS function must be present"
    assert js["downloadDraftJson"], "downloadDraftJson JS function must be present"
    assert js["outputArtifactSanitizeName"], (
        "outputArtifactSanitizeName JS function must be present"
    )
    assert js["outputArtifactRawPathGuard"], (
        "outputArtifactRawPathGuard JS function must be present"
    )


def test_handler_wiring_complete(tmp_path):
    """P9F: handler must be wired and use safe filename + artifact ID header."""
    result = run_audit(tmp_path)
    wiring = result["handler_wiring"]
    assert wiring["editor_handler_wired"], "editor handler must reference HwpxDownloadExportUseCase"
    assert wiring["uses_safe_filename"], "handler must use exportResult.safeFilename()"
    assert wiring["uses_artifact_id_header"], "handler must set X-Hwpx-Editor-Artifact-Id"
    assert wiring["raw_path_guarded"], "handler must guard raw paths via isRawPathGuarded()"


def test_phase_is_p9f(tmp_path):
    result = run_audit(tmp_path)
    assert result["phase"] == "P9F"


def test_policy_flags_set(tmp_path):
    result = run_audit(tmp_path)
    policy = result["policy"]
    assert policy["no_endpoint_path_change"]
    assert policy["no_api_response_key_change"]
    assert policy["no_gate_logic_change"]
    assert policy["push_forbidden"]
