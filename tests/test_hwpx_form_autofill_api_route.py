"""
HWPX-FORM-AUTO-FILL-WRITER-API-ROUTE-AND-FRONTEND-07
API route 테스트 (T01–T21)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import scripts.ops.hwpx_form_autofill_api_route as api

_PII_RE = re.compile(r"\d{6}-\d{7}|\d{3}-\d{2}-\d{5}")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _approval_ready(n: int = 3) -> dict:
    return {
        "writerEnabled": False,
        "approvedFields": [
            {"fieldKey": f"f{i}", "label": f"L{i}", "value": f"V{i}",
             "writerEligible": True, "action": "CONFIRM_FIELD",
             "sourceZone": "AUTO_FILL_READY", "confidence": 0.91,
             "originalValue": f"V{i}"}
            for i in range(n)
        ],
        "pendingFields": [],
        "summary": {"approvedFields": n, "pendingFields": 0,
                    "undecidedCount": 0, "missingRequired": 0},
    }


def _approval_blocked() -> dict:
    ap = _approval_ready()
    ap["summary"]["undecidedCount"] = 2
    return ap


def _writer_result(readback_fail: int = 0, source_mutated: bool = False) -> dict:
    return {
        "writerStatus": "SUCCESS" if not source_mutated and readback_fail == 0 else "FAILED_READBACK",
        "summary": {"written": 2, "blocked": 0, "readbackPass": 2 - readback_fail,
                    "readbackFail": readback_fail, "sourceMutated": source_mutated},
        "output": {"outputFileId": "out_001", "outputHash": "abc123def4",
                   "downloadEnabled": True},
        "fieldResults": [], "warnings": [],
        "security": {"sourceMutationAllowed": False, "rawPathVisible": False,
                     "rawFilenameVisible": False, "piiMasked": True},
    }


def _dl_payload(download_enabled: bool = True) -> dict:
    return {
        "schemaVersion": "form_writer_download_review_v1",
        "writerStatus": "SUCCESS",
        "summary": {"written": 2, "blocked": 0, "readbackPass": 2,
                    "readbackFail": 0, "sourceMutated": False},
        "download": {"downloadEnabled": download_enabled, "outputFileId": "out_001",
                     "outputHash": "abc123def4", "sourceTemplateHash": ""},
        "warnings": [],
        "security": {"sourceMutationAllowed": False, "rawPathVisible": False,
                     "rawFilenameVisible": False, "piiMasked": True},
    }


def _decision() -> dict:
    return {"formId": "f", "outputFileId": "out_001", "action": "ACCEPT_OUTPUT",
            "decisionResult": "ACCEPTED_BY_USER", "decisionBy": "user", "reason": "",
            "sourceMutated": False, "operationalDeployment": False,
            "security": {"sourceMutationAllowed": False}}


# ---------------------------------------------------------------------------
# T01 – import
# ---------------------------------------------------------------------------

def test_T01_import():
    assert hasattr(api, "call_health")
    assert hasattr(api, "call_e2e_smoke")
    assert hasattr(api, "call_write_sandbox")
    assert hasattr(api, "SCHEMA_VERSION")
    assert hasattr(api, "MODE")


# ---------------------------------------------------------------------------
# T02 – health endpoint 응답
# ---------------------------------------------------------------------------

def test_T02_health():
    resp = api.call_health()
    assert resp["status"] == "SUCCESS"
    assert resp["mode"] == "SANDBOX_ONLY"
    assert resp["data"]["pipelineReady"] is True


# ---------------------------------------------------------------------------
# T03 – e2e-smoke endpoint SUCCESS 응답
# ---------------------------------------------------------------------------

def test_T03_e2e_smoke():
    resp = api.call_e2e_smoke()
    assert resp["status"] == "SUCCESS"
    assert resp["data"]["overallVerdict"] == "PASS_E2E_SMOKE"


# ---------------------------------------------------------------------------
# T04 – 모든 응답에 schemaVersion/requestId/mode/sourceMutationAllowed 포함
# ---------------------------------------------------------------------------

def test_T04_response_schema():
    for resp in [api.call_health(), api.call_write_sandbox(_approval_ready())]:
        assert "schemaVersion" in resp
        assert "requestId" in resp
        assert "mode" in resp
        assert "sourceMutationAllowed" in resp
        assert resp["schemaVersion"] == api.SCHEMA_VERSION


# ---------------------------------------------------------------------------
# T05 – mode == SANDBOX_ONLY
# ---------------------------------------------------------------------------

def test_T05_mode_sandbox_only():
    for resp in [api.call_health(), api.call_write_sandbox(_approval_ready()),
                 api.call_e2e_smoke()]:
        assert resp["mode"] == "SANDBOX_ONLY"


# ---------------------------------------------------------------------------
# T06 – sourceMutationAllowed == false
# ---------------------------------------------------------------------------

def test_T06_source_mutation_false():
    for resp in [api.call_health(), api.call_write_sandbox(_approval_ready())]:
        assert resp["sourceMutationAllowed"] is False


# ---------------------------------------------------------------------------
# T07 – write-sandbox: READY_FOR_WRITER 조건 없으면 차단
# ---------------------------------------------------------------------------

def test_T07_write_sandbox_blocked():
    resp = api.call_write_sandbox(_approval_blocked())
    assert resp["status"] == "FAILED"
    assert any("WRITER_BLOCKED" in e["code"] for e in resp["errors"])


# ---------------------------------------------------------------------------
# T08 – readbackFail > 0이면 SUCCESS로 표시하지 않음
# ---------------------------------------------------------------------------

def test_T08_readback_fail_not_success():
    dl = api.call_download_review(_writer_result(readback_fail=1))
    # download_review에서 readback_fail=1이면 downloadEnabled=false
    dl_data = dl.get("data", {})
    download = dl_data.get("download", {})
    assert download.get("downloadEnabled") is False


# ---------------------------------------------------------------------------
# T09 – sourceMutated true이면 실패로 표시
# ---------------------------------------------------------------------------

def test_T09_source_mutated_failure():
    dl = api.call_download_review(_writer_result(source_mutated=True))
    dl_data = dl.get("data", {})
    download = dl_data.get("download", {})
    assert download.get("downloadEnabled") is False


# ---------------------------------------------------------------------------
# T10 – raw path 응답 노출 없음
# ---------------------------------------------------------------------------

def test_T10_no_raw_path():
    resp = api.call_health()
    resp_str = str(resp)
    for kw in ("C:\\", "/home/", "/tmp/"):
        assert kw not in resp_str


# ---------------------------------------------------------------------------
# T11 – raw filename 응답 노출 없음
# ---------------------------------------------------------------------------

def test_T11_no_raw_filename():
    resp = api.call_write_sandbox(_approval_ready())
    assert resp["sourceMutationAllowed"] is False
    # security 필드 확인
    data = resp.get("data", {})
    ui_payload = data.get("uiPayload", {})
    assert ui_payload.get("security", {}).get("rawFilenameVisible") is False


# ---------------------------------------------------------------------------
# T12 – PII pattern 응답 leak 없음
# ---------------------------------------------------------------------------

def test_T12_no_pii():
    ap = _approval_ready()
    ap["approvedFields"][0]["value"] = "870101-1234567"  # PII 주입
    resp = api.call_write_sandbox(ap)
    assert not _PII_RE.search(str(resp)), "PII 원문이 API 응답에 노출됨"


# ---------------------------------------------------------------------------
# T13 – write-sandbox READY_FOR_WRITER일 때 SUCCESS
# ---------------------------------------------------------------------------

def test_T13_write_sandbox_success():
    resp = api.call_write_sandbox(_approval_ready())
    assert resp["status"] == "SUCCESS"
    assert resp["data"]["mode"] == "SANDBOX_ONLY"
    assert resp["data"]["sourceMutationAllowed"] is False


# ---------------------------------------------------------------------------
# T14 – download-review call 가능
# ---------------------------------------------------------------------------

def test_T14_download_review():
    resp = api.call_download_review(_writer_result())
    assert resp["status"] == "SUCCESS"
    data = resp.get("data", {})
    assert data.get("download", {}).get("downloadEnabled") is True


# ---------------------------------------------------------------------------
# T15 – final-export ACCEPTED_BY_USER이면 SUCCESS
# ---------------------------------------------------------------------------

def test_T15_final_export_success():
    resp = api.call_final_export(_dl_payload(), _decision())
    assert resp["status"] == "SUCCESS"
    assert resp["data"]["finalExportEnabled"] is True


# ---------------------------------------------------------------------------
# T16 – final-export REJECTED이면 FAILED
# ---------------------------------------------------------------------------

def test_T16_final_export_rejected():
    dec = _decision()
    dec["decisionResult"] = "REJECTED_BY_USER"
    dec["action"] = "REJECT_OUTPUT"
    resp = api.call_final_export(_dl_payload(), dec)
    assert resp["status"] == "FAILED"


# ---------------------------------------------------------------------------
# T17 – AI API 호출 없음
# ---------------------------------------------------------------------------

def test_T17_no_ai_api():
    import inspect
    src = inspect.getsource(api)
    for kw in ("openai", "anthropic", "ChatCompletion", "gemini"):
        assert kw not in src.lower()


# ---------------------------------------------------------------------------
# T18 – OCR 호출 없음
# ---------------------------------------------------------------------------

def test_T18_no_ocr():
    import inspect
    src = inspect.getsource(api)
    for kw in ("pytesseract", "easyocr", "paddleocr"):
        assert kw not in src.lower()


# ---------------------------------------------------------------------------
# T19 – Hancom 필수 의존 없음
# ---------------------------------------------------------------------------

def test_T19_no_hancom():
    import inspect
    src = inspect.getsource(api)
    for kw in ("hwp5", "pyhwp", "HwpCtrl", "import hancom", "from hancom"):
        assert kw not in src


# ---------------------------------------------------------------------------
# T20 – 기존 E2E smoke 테스트 유지
# ---------------------------------------------------------------------------

def test_T20_e2e_smoke_tests_pass():
    import subprocess
    r = subprocess.run(
        [sys.executable, "-m", "pytest",
         "tests/test_hwpx_form_auto_fill_e2e_smoke.py", "-q", "--tb=no"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=str(Path(__file__).parent.parent),
    )
    assert r.returncode == 0, r.stdout + r.stderr


# ---------------------------------------------------------------------------
# T21 – 기존 전체 upstream 테스트 유지
# ---------------------------------------------------------------------------

def test_T21_upstream_tests_pass():
    import subprocess
    r = subprocess.run(
        [sys.executable, "-m", "pytest",
         "tests/test_hwpx_form_writer_final_export_gate.py",
         "tests/test_hwpx_form_writer_download_review.py",
         "tests/test_hwpx_form_writer_ui_connect.py",
         "tests/test_hwpx_form_writer_readback_hardening.py",
         "tests/test_hwpx_form_auto_fill_writer_sandbox.py",
         "-q", "--tb=no"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=str(Path(__file__).parent.parent),
    )
    assert r.returncode == 0, r.stdout + r.stderr
