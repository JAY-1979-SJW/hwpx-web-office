"""
HWPX-FORM-AUTO-FILL-WRITER-DOWNLOAD-AND-USER-REVIEW-04 테스트
T01–T25
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import scripts.hwpx.pipeline.form_writer_download_review as dr

_PII_RE = re.compile(r"\d{6}-\d{7}|\d{3}-\d{2}-\d{5}")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ui_result(
    status: str = "SUCCESS",
    readback_fail: int = 0,
    source_mutated: bool = False,
    output_file_id: str = "sandbox_001",
    output_hash: str = "abc123def45678",
) -> dict:
    return {
        "schemaVersion": "form_writer_ui_result_v1",
        "writerStatus": status,
        "summary": {
            "written": 3,
            "blocked": 0,
            "readbackPass": 3 - readback_fail,
            "readbackFail": readback_fail,
            "sourceMutated": source_mutated,
        },
        "output": {
            "outputFileId": output_file_id,
            "outputHash": output_hash,
            "downloadEnabled": status == "SUCCESS" and readback_fail == 0 and not source_mutated,
        },
        "fieldResults": [],
        "warnings": [],
        "security": {
            "sourceMutationAllowed": False,
            "rawPathVisible": False,
            "rawFilenameVisible": False,
            "piiMasked": True,
        },
    }


def _decision_dict(action: str = "ACCEPT_OUTPUT") -> dict:
    return {
        "formId": "test_form",
        "outputFileId": "sandbox_001",
        "action": action,
        "decisionBy": "user",
        "reason": "테스트 결정",
    }


# ---------------------------------------------------------------------------
# T01 – import
# ---------------------------------------------------------------------------

def test_T01_import():
    assert hasattr(dr, "build_download_payload")
    assert hasattr(dr, "apply_review_decision")
    assert hasattr(dr, "apply_review_decision_from_dict")
    assert hasattr(dr, "ReviewDecision")


# ---------------------------------------------------------------------------
# T02 – SUCCESS → downloadEnabled true
# ---------------------------------------------------------------------------

def test_T02_success_enables_download():
    payload = dr.build_download_payload(_ui_result())
    assert payload["download"]["downloadEnabled"] is True
    assert payload["reviewStatus"] == dr.REVIEW_WAITING


# ---------------------------------------------------------------------------
# T03 – readbackFail > 0 → downloadEnabled false
# ---------------------------------------------------------------------------

def test_T03_readback_fail_disables_download():
    payload = dr.build_download_payload(_ui_result(readback_fail=1))
    assert payload["download"]["downloadEnabled"] is False
    assert dr.BLOCKED_READBACK_FAILED in payload["download"]["blockedReason"]


# ---------------------------------------------------------------------------
# T04 – sourceMutated true → downloadEnabled false
# ---------------------------------------------------------------------------

def test_T04_source_mutated_disables_download():
    payload = dr.build_download_payload(_ui_result(source_mutated=True))
    assert payload["download"]["downloadEnabled"] is False
    assert dr.BLOCKED_SOURCE_MUTATED in payload["download"]["blockedReason"]


# ---------------------------------------------------------------------------
# T05 – writerStatus FAILED_READBACK → downloadEnabled false
# ---------------------------------------------------------------------------

def test_T05_failed_readback_status_disables_download():
    payload = dr.build_download_payload(_ui_result(status="FAILED_READBACK"))
    assert payload["download"]["downloadEnabled"] is False


# ---------------------------------------------------------------------------
# T06 – outputHash 없으면 downloadEnabled false
# ---------------------------------------------------------------------------

def test_T06_missing_hash_disables_download():
    payload = dr.build_download_payload(_ui_result(output_hash=""))
    assert payload["download"]["downloadEnabled"] is False
    assert dr.BLOCKED_HASH_MISSING in payload["download"]["blockedReason"]


# ---------------------------------------------------------------------------
# T07 – outputFileId 없으면 downloadEnabled false
# ---------------------------------------------------------------------------

def test_T07_missing_file_id_disables_download():
    payload = dr.build_download_payload(_ui_result(output_file_id=""))
    assert payload["download"]["downloadEnabled"] is False
    assert dr.BLOCKED_OUTPUT_ID_MISSING in payload["download"]["blockedReason"]


# ---------------------------------------------------------------------------
# T08 – output_path == source_path → downloadEnabled false
# ---------------------------------------------------------------------------

def test_T08_output_equals_source_disables_download():
    # outputFileId와 sourceTemplateHash가 같으면 차단
    same_hash = "same_hash_value_01"
    payload = dr.build_download_payload(
        _ui_result(output_file_id=same_hash),
        source_template_hash=same_hash,
    )
    assert payload["download"]["downloadEnabled"] is False
    assert dr.BLOCKED_OUTPUT_EQUALS_SOURCE in payload["download"]["blockedReason"]


# ---------------------------------------------------------------------------
# T09 – raw path payload 미노출
# ---------------------------------------------------------------------------

def test_T09_no_raw_path_in_payload():
    payload = dr.build_download_payload(_ui_result())
    payload_str = str(payload)
    for kw in ("C:\\", "/home/", "/tmp/", ":\\Users\\"):
        assert kw not in payload_str


# ---------------------------------------------------------------------------
# T10 – raw filename payload 미노출
# ---------------------------------------------------------------------------

def test_T10_no_raw_filename_in_payload():
    payload = dr.build_download_payload(
        _ui_result(),
        display_name="작성본_검토용.hwpx",
    )
    # displayName은 허용(사용자 표시용), 하지만 실제 파일 시스템 경로 노출 금지
    assert payload["security"]["rawFilenameVisible"] is False
    # 실제 파일 절대경로 같은 것은 없어야 함
    payload_str = str(payload)
    assert "소방완공검사신청서_2024_원본.hwpx" not in payload_str


# ---------------------------------------------------------------------------
# T11 – PII payload 미노출
# ---------------------------------------------------------------------------

def test_T11_no_pii_in_payload():
    ui = _ui_result()
    ui["fieldResults"] = [{"fieldKey": "f0", "value": "870101-1234567", "readbackStatus": "READBACK_PASS"}]
    payload = dr.build_download_payload(ui)
    payload_str = str(payload)
    assert not _PII_RE.search(payload_str), "PII 원문이 download payload에 노출됨"


# ---------------------------------------------------------------------------
# T12 – ACCEPT_OUTPUT 처리
# ---------------------------------------------------------------------------

def test_T12_accept_output():
    payload = dr.build_download_payload(_ui_result())
    result = dr.apply_review_decision_from_dict(payload, _decision_dict("ACCEPT_OUTPUT"))
    assert result["decisionResult"] == dr.DECISION_ACCEPTED
    assert result["action"] == "ACCEPT_OUTPUT"


# ---------------------------------------------------------------------------
# T13 – REJECT_OUTPUT 처리
# ---------------------------------------------------------------------------

def test_T13_reject_output():
    payload = dr.build_download_payload(_ui_result())
    result = dr.apply_review_decision_from_dict(payload, _decision_dict("REJECT_OUTPUT"))
    assert result["decisionResult"] == dr.DECISION_REJECTED


# ---------------------------------------------------------------------------
# T14 – REQUEST_REWRITE 처리
# ---------------------------------------------------------------------------

def test_T14_request_rewrite():
    payload = dr.build_download_payload(_ui_result())
    result = dr.apply_review_decision_from_dict(payload, _decision_dict("REQUEST_REWRITE"))
    assert result["decisionResult"] == dr.DECISION_REWRITE


# ---------------------------------------------------------------------------
# T15 – HOLD_REVIEW 처리
# ---------------------------------------------------------------------------

def test_T15_hold_review():
    payload = dr.build_download_payload(_ui_result())
    result = dr.apply_review_decision_from_dict(payload, _decision_dict("HOLD_REVIEW"))
    assert result["decisionResult"] == dr.DECISION_HOLD


# ---------------------------------------------------------------------------
# T16 – ACCEPT_OUTPUT이 원본 수정으로 연결되지 않음
# ---------------------------------------------------------------------------

def test_T16_accept_does_not_mutate_source():
    payload = dr.build_download_payload(_ui_result())
    result = dr.apply_review_decision_from_dict(payload, _decision_dict("ACCEPT_OUTPUT"))
    assert result["sourceMutated"] is False
    assert result["operationalDeployment"] is False
    assert result["security"]["sourceMutationAllowed"] is False


# ---------------------------------------------------------------------------
# T17 – allowedReviewActions 정확
# ---------------------------------------------------------------------------

def test_T17_allowed_review_actions():
    payload = dr.build_download_payload(_ui_result())
    actions = set(payload["allowedReviewActions"])
    expected = {"ACCEPT_OUTPUT", "REJECT_OUTPUT", "REQUEST_REWRITE", "HOLD_REVIEW"}
    assert actions == expected


# ---------------------------------------------------------------------------
# T17b – downloadEnabled false이면 allowedReviewActions 비어 있음
# ---------------------------------------------------------------------------

def test_T17b_blocked_download_no_actions():
    payload = dr.build_download_payload(_ui_result(readback_fail=1))
    assert payload["allowedReviewActions"] == []


# ---------------------------------------------------------------------------
# T18 – sourceMutationAllowed false 유지
# ---------------------------------------------------------------------------

def test_T18_source_mutation_always_false():
    for ui in [_ui_result(), _ui_result(status="FAILED_READBACK")]:
        p = dr.build_download_payload(ui)
        assert p["security"]["sourceMutationAllowed"] is False


# ---------------------------------------------------------------------------
# T19 – AI API 호출 없음
# ---------------------------------------------------------------------------

def test_T19_no_ai_api():
    import inspect
    src = inspect.getsource(dr)
    for kw in ("openai", "anthropic", "ChatCompletion", "gemini"):
        assert kw not in src.lower()


# ---------------------------------------------------------------------------
# T20 – OCR 호출 없음
# ---------------------------------------------------------------------------

def test_T20_no_ocr():
    import inspect
    src = inspect.getsource(dr)
    for kw in ("pytesseract", "easyocr", "paddleocr"):
        assert kw not in src.lower()


# ---------------------------------------------------------------------------
# T21 – Hancom 필수 의존 없음
# ---------------------------------------------------------------------------

def test_T21_no_hancom():
    import inspect
    src = inspect.getsource(dr)
    for kw in ("hwp5", "pyhwp", "HwpCtrl", "hancom"):
        assert kw not in src.lower()


# ---------------------------------------------------------------------------
# T22 – 기존 UI connect 테스트 유지
# ---------------------------------------------------------------------------

def test_T22_ui_connect_tests_pass():
    import subprocess
    r = subprocess.run(
        [sys.executable, "-m", "pytest",
         "tests/test_hwpx_form_writer_ui_connect.py", "-q", "--tb=no"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=str(Path(__file__).parent.parent),
    )
    assert r.returncode == 0, r.stdout + r.stderr


# ---------------------------------------------------------------------------
# T23 – 기존 readback / sandbox 테스트 유지
# ---------------------------------------------------------------------------

def test_T23_readback_sandbox_tests_pass():
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
# T24 – 기존 approval / review / mapping 테스트 유지
# ---------------------------------------------------------------------------

def test_T24_upstream_tests_pass():
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
# T25 – 잘못된 action → ValueError
# ---------------------------------------------------------------------------

def test_T25_invalid_action_raises():
    with pytest.raises(ValueError, match="Invalid review action"):
        dr.ReviewDecision(
            formId="f", outputFileId="o", action="INVALID_ACTION"
        )
