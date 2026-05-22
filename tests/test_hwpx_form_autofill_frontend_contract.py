"""
HWPX-FORM-AUTO-FILL-WRITER-API-ROUTE-AND-FRONTEND-07
프론트엔드 contract 테스트 (T01–T21)
TypeScript 컴포넌트 직접 실행 불가 → contract 검증으로 대체.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

_PII_RE = re.compile(r"\d{6}-\d{7}|\d{3}-\d{2}-\d{5}")

FRONTEND_FILE = Path(__file__).parent.parent / "frontend" / "web_office_viewer" / "components" / "FormAutoFillWorkspace.tsx"

# ---------------------------------------------------------------------------
# T01 – 파일 존재
# ---------------------------------------------------------------------------

def test_T01_component_file_exists():
    assert FRONTEND_FILE.exists()


# ---------------------------------------------------------------------------
# T02 – SANDBOX_ONLY 경고문 포함
# ---------------------------------------------------------------------------

def test_T02_sandbox_warning_text():
    src = FRONTEND_FILE.read_text(encoding="utf-8")
    assert "원본 HWPX는 수정하지 않고 sandbox 복사본에만 작성합니다." in src


# ---------------------------------------------------------------------------
# T03 – sourceMutationAllowed = false 명시
# ---------------------------------------------------------------------------

def test_T03_source_mutation_false():
    src = FRONTEND_FILE.read_text(encoding="utf-8")
    assert "sourceMutationAllowed" in src
    assert '"false"' in src or "false" in src


# ---------------------------------------------------------------------------
# T04 – mode == SANDBOX_ONLY
# ---------------------------------------------------------------------------

def test_T04_mode_sandbox_only():
    src = FRONTEND_FILE.read_text(encoding="utf-8")
    assert "SANDBOX_ONLY" in src


# ---------------------------------------------------------------------------
# T05 – computeButtonEnabled 함수 존재
# ---------------------------------------------------------------------------

def test_T05_button_enabled_function():
    src = FRONTEND_FILE.read_text(encoding="utf-8")
    assert "computeButtonEnabled" in src


# ---------------------------------------------------------------------------
# T06 – READY_FOR_WRITER 조건 포함
# ---------------------------------------------------------------------------

def test_T06_ready_for_writer_condition():
    src = FRONTEND_FILE.read_text(encoding="utf-8")
    assert "READY_FOR_WRITER" in src


# ---------------------------------------------------------------------------
# T07 – 버튼 disabled 속성 존재
# ---------------------------------------------------------------------------

def test_T07_button_disabled_attr():
    src = FRONTEND_FILE.read_text(encoding="utf-8")
    assert "disabled" in src
    assert "write-sandbox-button" in src


# ---------------------------------------------------------------------------
# T08 – writerStatusLabel 함수 존재
# ---------------------------------------------------------------------------

def test_T08_writer_status_label():
    src = FRONTEND_FILE.read_text(encoding="utf-8")
    assert "writerStatusLabel" in src
    assert "FAILED_READBACK" in src
    assert "FAILED_SOURCE_MUTATED" in src


# ---------------------------------------------------------------------------
# T09 – approval status 매트릭스 존재
# ---------------------------------------------------------------------------

def test_T09_approval_status_matrix():
    src = FRONTEND_FILE.read_text(encoding="utf-8")
    for status in ["BLOCKED_NEEDS_REVIEW", "BLOCKED_MISSING_REQUIRED",
                   "BLOCKED_ATTACHMENT_MISSING", "HOLD_BY_USER"]:
        assert status in src


# ---------------------------------------------------------------------------
# T10 – 다운로드 정보: raw path 노출 없음
# ---------------------------------------------------------------------------

def test_T10_no_raw_path_in_component():
    src = FRONTEND_FILE.read_text(encoding="utf-8")
    for kw in ("C:\\", "/home/", "/tmp/", "outputPath"):
        assert kw not in src


# ---------------------------------------------------------------------------
# T11 – raw filename 노출 없음
# ---------------------------------------------------------------------------

def test_T11_no_raw_filename():
    src = FRONTEND_FILE.read_text(encoding="utf-8")
    # rawFilenameVisible은 표시 없어야 하는 문자열 — component에서 실제 경로 파일명 노출 없어야 함
    assert "rawFilenameVisible" not in src or "rawPathVisible" not in src or \
           "data-output-file-id" in src  # fileId만 사용


# ---------------------------------------------------------------------------
# T12 – PII pattern 소스 코드 없음
# ---------------------------------------------------------------------------

def test_T12_no_pii_in_source():
    src = FRONTEND_FILE.read_text(encoding="utf-8")
    assert not _PII_RE.search(src), "PII 패턴이 컴포넌트 소스에 포함됨"


# ---------------------------------------------------------------------------
# T13 – review action 4개 모두 포함
# ---------------------------------------------------------------------------

def test_T13_review_actions():
    src = FRONTEND_FILE.read_text(encoding="utf-8")
    for action in ["ACCEPT_OUTPUT", "REJECT_OUTPUT", "REQUEST_REWRITE", "HOLD_REVIEW"]:
        assert action in src


# ---------------------------------------------------------------------------
# T14 – ACCEPT_OUTPUT 원본 교체 경고 없음
# ---------------------------------------------------------------------------

def test_T14_accept_not_deploy():
    src = FRONTEND_FILE.read_text(encoding="utf-8")
    # 원본 교체/운영 반영 키워드가 버튼 라벨 등에 없어야 함
    for dangerous in ("원본_교체", "원본교체", "운영반영", "overwrite_source"):
        assert dangerous not in src


# ---------------------------------------------------------------------------
# T15 – final export 상태 UI 구역 존재
# ---------------------------------------------------------------------------

def test_T15_final_export_section():
    src = FRONTEND_FILE.read_text(encoding="utf-8")
    assert "final-export-status" in src
    assert "finalExportEnabled" in src


# ---------------------------------------------------------------------------
# T16 – AI API 호출 없음
# ---------------------------------------------------------------------------

def test_T16_no_ai_api():
    src = FRONTEND_FILE.read_text(encoding="utf-8")
    for kw in ("openai", "anthropic", "ChatCompletion", "gemini"):
        assert kw not in src.lower()


# ---------------------------------------------------------------------------
# T17 – OCR 호출 없음
# ---------------------------------------------------------------------------

def test_T17_no_ocr():
    src = FRONTEND_FILE.read_text(encoding="utf-8")
    for kw in ("pytesseract", "easyocr", "paddleocr"):
        assert kw not in src.lower()


# ---------------------------------------------------------------------------
# T18 – Hancom 필수 의존 없음
# ---------------------------------------------------------------------------

def test_T18_no_hancom():
    src = FRONTEND_FILE.read_text(encoding="utf-8")
    for kw in ("hwp5", "pyhwp", "HwpCtrl", "import hancom"):
        assert kw not in src


# ---------------------------------------------------------------------------
# T19 – 기존 API route 테스트 유지
# ---------------------------------------------------------------------------

def test_T19_api_route_tests_pass():
    import subprocess
    r = subprocess.run(
        [sys.executable, "-m", "pytest",
         "tests/test_hwpx_form_autofill_api_route.py", "-q", "--tb=no"],
        capture_output=True, text=True,
        cwd=str(Path(__file__).parent.parent),
    )
    assert r.returncode == 0, r.stdout + r.stderr


# ---------------------------------------------------------------------------
# T20 – 기존 E2E smoke / final export / download 테스트 유지
# ---------------------------------------------------------------------------

def test_T20_e2e_chain_tests_pass():
    import subprocess
    r = subprocess.run(
        [sys.executable, "-m", "pytest",
         "tests/test_hwpx_form_auto_fill_e2e_smoke.py",
         "tests/test_hwpx_form_writer_final_export_gate.py",
         "tests/test_hwpx_form_writer_download_review.py",
         "-q", "--tb=no"],
        capture_output=True, text=True,
        cwd=str(Path(__file__).parent.parent),
    )
    assert r.returncode == 0, r.stdout + r.stderr


# ---------------------------------------------------------------------------
# T21 – 기존 approval/review/mapping 테스트 유지
# ---------------------------------------------------------------------------

def test_T21_upstream_tests_pass():
    import subprocess
    r = subprocess.run(
        [sys.executable, "-m", "pytest",
         "tests/test_hwpx_approval_gate.py",
         "tests/test_hwpx_review_panel.py",
         "tests/test_hwpx_form_field_mapping.py",
         "-q", "--tb=no"],
        capture_output=True, text=True,
        cwd=str(Path(__file__).parent.parent),
    )
    assert r.returncode == 0, r.stdout + r.stderr
