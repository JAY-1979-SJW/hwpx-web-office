"""
HWPX-FORM-AUTO-FILL-WRITER-FINAL-EXPORT-GATE-05 테스트
T01–T26
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent.parent))

import scripts.hwpx.pipeline.form_writer_final_export_gate as eg

_PII_RE = re.compile(r"\d{6}-\d{7}|\d{3}-\d{2}-\d{5}")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dl_payload(
    writer_status: str = "SUCCESS",
    readback_fail: int = 0,
    source_mutated: bool = False,
    output_file_id: str = "out_001",
    output_hash: str = "abc123def456ab",
    download_enabled: bool = True,
) -> dict:
    return {
        "schemaVersion": "form_writer_download_review_v1",
        "writerStatus": writer_status,
        "reviewStatus": "WAITING_USER_REVIEW",
        "summary": {
            "written": 3, "blocked": 1,
            "readbackPass": 3 - readback_fail,
            "readbackFail": readback_fail,
            "sourceMutated": source_mutated,
        },
        "download": {
            "downloadEnabled": download_enabled,
            "outputFileId": output_file_id,
            "outputHash": output_hash,
            "sourceTemplateHash": "",
            "displayName": "작성본_검토용.hwpx",
            "createdAt": "2026-05-23T00:00:00Z",
            "expiresAt": "2026-05-30T00:00:00Z",
        },
        "allowedReviewActions": ["ACCEPT_OUTPUT", "REJECT_OUTPUT", "REQUEST_REWRITE", "HOLD_REVIEW"],
        "security": {
            "sourceMutationAllowed": False,
            "rawPathVisible": False,
            "rawFilenameVisible": False,
            "piiMasked": True,
        },
        "warnings": [],
    }


def _decision(result: str = "ACCEPTED_BY_USER", action: str = "ACCEPT_OUTPUT") -> dict:
    return {
        "formId": "test",
        "outputFileId": "out_001",
        "action": action,
        "decisionResult": result,
        "decisionBy": "user",
        "reason": "",
        "sourceMutated": False,
        "operationalDeployment": False,
        "security": {"sourceMutationAllowed": False},
    }


# ---------------------------------------------------------------------------
# T01 – import
# ---------------------------------------------------------------------------

def test_T01_import():
    assert hasattr(eg, "build_final_export_payload")
    assert hasattr(eg, "EXPORT_READY")
    assert hasattr(eg, "BLOCKED_NOT_ACCEPTED")


# ---------------------------------------------------------------------------
# T02 – ACCEPTED_BY_USER + SUCCESS → finalExportEnabled true
# ---------------------------------------------------------------------------

def test_T02_accepted_success_enables_export():
    payload = eg.build_final_export_payload(_dl_payload(), _decision())
    assert payload["finalExportEnabled"] is True
    assert payload["exportStatus"] == eg.EXPORT_READY


# ---------------------------------------------------------------------------
# T03 – REJECTED_BY_USER → finalExportEnabled false
# ---------------------------------------------------------------------------

def test_T03_rejected_blocks_export():
    payload = eg.build_final_export_payload(
        _dl_payload(), _decision("REJECTED_BY_USER", "REJECT_OUTPUT")
    )
    assert payload["finalExportEnabled"] is False
    assert eg.BLOCKED_REJECTED in payload["exportStatus"]


# ---------------------------------------------------------------------------
# T04 – REWRITE_REQUESTED → finalExportEnabled false
# ---------------------------------------------------------------------------

def test_T04_rewrite_blocks_export():
    payload = eg.build_final_export_payload(
        _dl_payload(), _decision("REWRITE_REQUESTED", "REQUEST_REWRITE")
    )
    assert payload["finalExportEnabled"] is False
    assert eg.BLOCKED_REWRITE in payload["exportStatus"]


# ---------------------------------------------------------------------------
# T05 – REVIEW_ON_HOLD → finalExportEnabled false
# ---------------------------------------------------------------------------

def test_T05_hold_blocks_export():
    payload = eg.build_final_export_payload(
        _dl_payload(), _decision("REVIEW_ON_HOLD", "HOLD_REVIEW")
    )
    assert payload["finalExportEnabled"] is False
    assert eg.BLOCKED_HOLD in payload["exportStatus"]


# ---------------------------------------------------------------------------
# T06 – writerStatus 실패 → finalExportEnabled false
# ---------------------------------------------------------------------------

def test_T06_failed_writer_blocks_export():
    payload = eg.build_final_export_payload(
        _dl_payload(writer_status="FAILED_READBACK", download_enabled=False),
        _decision(),
    )
    assert payload["finalExportEnabled"] is False


# ---------------------------------------------------------------------------
# T07 – readbackFail > 0 → finalExportEnabled false
# ---------------------------------------------------------------------------

def test_T07_readback_fail_blocks_export():
    payload = eg.build_final_export_payload(
        _dl_payload(readback_fail=1, download_enabled=False),
        _decision(),
    )
    assert payload["finalExportEnabled"] is False


# ---------------------------------------------------------------------------
# T08 – sourceMutated true → finalExportEnabled false
# ---------------------------------------------------------------------------

def test_T08_source_mutated_blocks_export():
    payload = eg.build_final_export_payload(
        _dl_payload(source_mutated=True, download_enabled=False),
        _decision(),
    )
    assert payload["finalExportEnabled"] is False
    assert eg.BLOCKED_SOURCE_MUTATED in payload["exportStatus"]


# ---------------------------------------------------------------------------
# T09 – outputHash 없으면 finalExportEnabled false
# ---------------------------------------------------------------------------

def test_T09_missing_hash_blocks_export():
    payload = eg.build_final_export_payload(
        _dl_payload(output_hash=""),
        _decision(),
    )
    assert payload["finalExportEnabled"] is False
    assert eg.BLOCKED_HASH_MISSING in payload["exportStatus"]


# ---------------------------------------------------------------------------
# T10 – outputFileId 없으면 finalExportEnabled false
# ---------------------------------------------------------------------------

def test_T10_missing_file_id_blocks_export():
    payload = eg.build_final_export_payload(
        _dl_payload(output_file_id=""),
        _decision(),
    )
    assert payload["finalExportEnabled"] is False
    assert eg.BLOCKED_OUTPUT_ID_MISSING in payload["exportStatus"]


# ---------------------------------------------------------------------------
# T11 – output_path == source_path → finalExportEnabled false
# ---------------------------------------------------------------------------

def test_T11_output_equals_source_blocks_export():
    same = "same_hash_val_x01"
    dl = _dl_payload(output_file_id=same)
    payload = eg.build_final_export_payload(dl, _decision(), source_template_hash=same)
    assert payload["finalExportEnabled"] is False
    assert eg.BLOCKED_OUTPUT_EQUALS_SOURCE in payload["exportStatus"]


# ---------------------------------------------------------------------------
# T12 – approvalTrace 포함
# ---------------------------------------------------------------------------

def test_T12_approval_trace_included():
    payload = eg.build_final_export_payload(_dl_payload(), _decision())
    trace = payload["approvalTrace"]
    assert trace["userReviewAction"] == "ACCEPT_OUTPUT"
    assert trace["reviewStatus"] == "ACCEPTED_BY_USER"
    assert "readbackPass" in trace
    assert "writtenFieldCount" in trace


# ---------------------------------------------------------------------------
# T13 – sourceTemplateHash / outputHash 포함
# ---------------------------------------------------------------------------

def test_T13_hashes_preserved():
    payload = eg.build_final_export_payload(
        _dl_payload(), _decision(), source_template_hash="tmpl_hash_001"
    )
    assert payload["sourceTemplateHash"] == "tmpl_hash_001"
    assert payload["outputHash"] == "abc123def456ab"


# ---------------------------------------------------------------------------
# T14 – raw path 노출 없음
# ---------------------------------------------------------------------------

def test_T14_no_raw_path():
    payload = eg.build_final_export_payload(_dl_payload(), _decision())
    payload_str = str(payload)
    for kw in ("C:\\", "/home/", "/tmp/", ":\\Users\\"):
        assert kw not in payload_str
    assert payload["security"]["rawPathVisible"] is False


# ---------------------------------------------------------------------------
# T15 – raw filename 노출 없음
# ---------------------------------------------------------------------------

def test_T15_no_raw_filename():
    payload = eg.build_final_export_payload(_dl_payload(), _decision())
    assert payload["security"]["rawFilenameVisible"] is False
    # 실제 절대경로 파일명 없어야 함
    assert "소방완공검사신청서_원본.hwpx" not in str(payload)


# ---------------------------------------------------------------------------
# T16 – PII pattern 없음
# ---------------------------------------------------------------------------

def test_T16_no_pii():
    dl = _dl_payload()
    dl["warnings"] = ["사업자번호: 123-45-67890"]  # PII가 아닌 사업자번호
    payload = eg.build_final_export_payload(dl, _decision())
    # 실제 주민등록번호 패턴 없어야 함
    payload_str = str(payload)
    assert not _PII_RE.search(payload_str)


# ---------------------------------------------------------------------------
# T17 – ACCEPT → source mutation 없음
# ---------------------------------------------------------------------------

def test_T17_accept_does_not_mutate_source():
    payload = eg.build_final_export_payload(_dl_payload(), _decision())
    assert payload["sourceMutationAllowed"] is False
    assert payload["security"]["originalTemplateMutated"] is False


# ---------------------------------------------------------------------------
# T18 – sourceMutationAllowed false 유지
# ---------------------------------------------------------------------------

def test_T18_source_mutation_always_false():
    for decision in [
        _decision("ACCEPTED_BY_USER"),
        _decision("REJECTED_BY_USER", "REJECT_OUTPUT"),
    ]:
        payload = eg.build_final_export_payload(_dl_payload(), decision)
        assert payload["sourceMutationAllowed"] is False


# ---------------------------------------------------------------------------
# T19 – AI API 호출 없음
# ---------------------------------------------------------------------------

def test_T19_no_ai_api():
    import inspect
    src = inspect.getsource(eg)
    for kw in ("openai", "anthropic", "ChatCompletion", "gemini"):
        assert kw not in src.lower()


# ---------------------------------------------------------------------------
# T20 – OCR 호출 없음
# ---------------------------------------------------------------------------

def test_T20_no_ocr():
    import inspect
    src = inspect.getsource(eg)
    for kw in ("pytesseract", "easyocr", "paddleocr"):
        assert kw not in src.lower()


# ---------------------------------------------------------------------------
# T21 – Hancom 필수 의존 없음
# ---------------------------------------------------------------------------

def test_T21_no_hancom():
    import inspect
    src = inspect.getsource(eg)
    for kw in ("hwp5", "pyhwp", "HwpCtrl", "hancom"):
        assert kw not in src.lower()


# ---------------------------------------------------------------------------
# T22 – 기존 download review 테스트 유지
# ---------------------------------------------------------------------------

def test_T22_download_review_tests_pass():
    import subprocess
    r = subprocess.run(
        [sys.executable, "-m", "pytest",
         "tests/test_hwpx_form_writer_download_review.py", "-q", "--tb=no"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=str(Path(__file__).parent.parent),
    )
    assert r.returncode == 0, r.stdout + r.stderr


# ---------------------------------------------------------------------------
# T23 – 기존 UI connect 테스트 유지
# ---------------------------------------------------------------------------

def test_T23_ui_connect_tests_pass():
    import subprocess
    r = subprocess.run(
        [sys.executable, "-m", "pytest",
         "tests/test_hwpx_form_writer_ui_connect.py", "-q", "--tb=no"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=str(Path(__file__).parent.parent),
    )
    assert r.returncode == 0, r.stdout + r.stderr


# ---------------------------------------------------------------------------
# T24 – 기존 readback / sandbox 테스트 유지
# ---------------------------------------------------------------------------

def test_T24_readback_sandbox_tests_pass():
    import subprocess
    r = subprocess.run(
        [sys.executable, "-m", "pytest",
         "tests/test_hwpx_form_writer_readback_hardening.py",
         "tests/test_hwpx_form_auto_fill_writer_sandbox.py",
         "-q", "--tb=no"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=str(Path(__file__).parent.parent),
    )
    assert r.returncode == 0, r.stdout + r.stderr


# ---------------------------------------------------------------------------
# T25 – 기존 approval / review / mapping 테스트 유지
# ---------------------------------------------------------------------------

def test_T25_upstream_tests_pass():
    import subprocess
    r = subprocess.run(
        [sys.executable, "-m", "pytest",
         "tests/test_hwpx_approval_gate.py",
         "tests/test_hwpx_review_panel.py",
         "tests/test_hwpx_form_field_mapping.py",
         "-q", "--tb=no"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=str(Path(__file__).parent.parent),
    )
    assert r.returncode == 0, r.stdout + r.stderr


# ---------------------------------------------------------------------------
# T26 – finalExportId blocked 상태에서 비어 있음
# ---------------------------------------------------------------------------

def test_T26_blocked_export_has_no_final_id():
    payload = eg.build_final_export_payload(
        _dl_payload(), _decision("REJECTED_BY_USER", "REJECT_OUTPUT")
    )
    assert payload["finalExport"]["finalExportId"] == ""
    assert payload["finalExport"]["downloadEnabled"] is False
