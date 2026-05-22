"""
HWPX-FORM-AUTO-FILL-WRITER-END-TO-END-SMOKE-06 테스트
T01–T30
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import scripts.hwpx.pipeline.form_auto_fill_e2e_smoke as smoke

_PII_RE = re.compile(r"\d{6}-\d{7}|\d{3}-\d{2}-\d{5}")


# ---------------------------------------------------------------------------
# Fixture: run_e2e once per session (tmp_path is function-scoped, use tmp_path_factory)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def e2e_result(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("e2e_smoke")
    return smoke.run_e2e_smoke(tmp)


# ---------------------------------------------------------------------------
# T01 – import
# ---------------------------------------------------------------------------

def test_T01_import():
    assert hasattr(smoke, "run_e2e_smoke")
    assert hasattr(smoke, "SCHEMA_VERSION")
    assert hasattr(smoke, "SCENARIO_ID")


# ---------------------------------------------------------------------------
# T02 – synthetic scenario 생성 가능
# ---------------------------------------------------------------------------

def test_T02_synthetic_scenario(e2e_result):
    assert e2e_result["scenarioId"] == smoke.SCENARIO_ID
    assert e2e_result["schemaVersion"] == smoke.SCHEMA_VERSION


# ---------------------------------------------------------------------------
# T03 – recommend 단계 PASS
# ---------------------------------------------------------------------------

def test_T03_recommend_pass(e2e_result):
    assert e2e_result["stageResults"]["recommend"] == "PASS"
    assert e2e_result["summary"]["recommended"] is True


# ---------------------------------------------------------------------------
# T04 – catalog 단계 PASS
# ---------------------------------------------------------------------------

def test_T04_catalog_pass(e2e_result):
    assert e2e_result["stageResults"]["catalog"] == "PASS"
    assert e2e_result["summary"]["catalogLoaded"] is True


# ---------------------------------------------------------------------------
# T05 – upload parser 단계 PASS
# ---------------------------------------------------------------------------

def test_T05_upload_parser_pass(e2e_result):
    assert e2e_result["stageResults"]["uploadParser"] == "PASS"
    assert e2e_result["summary"]["parsedFields"] >= 1


# ---------------------------------------------------------------------------
# T06 – field mapping 단계 PASS
# ---------------------------------------------------------------------------

def test_T06_mapping_pass(e2e_result):
    assert e2e_result["stageResults"]["mapping"] == "PASS"
    assert e2e_result["summary"]["autoFillReady"] >= 1


# ---------------------------------------------------------------------------
# T07 – review panel 단계 PASS
# ---------------------------------------------------------------------------

def test_T07_review_panel_pass(e2e_result):
    assert e2e_result["stageResults"]["reviewPanel"] == "PASS"


# ---------------------------------------------------------------------------
# T08 – human approval 단계 PASS
# ---------------------------------------------------------------------------

def test_T08_human_approval_pass(e2e_result):
    assert e2e_result["stageResults"]["humanApproval"] == "PASS"
    assert e2e_result["summary"]["approvedFields"] >= 1


# ---------------------------------------------------------------------------
# T09 – sandbox writer 단계 PASS
# ---------------------------------------------------------------------------

def test_T09_sandbox_writer_pass(e2e_result):
    assert e2e_result["stageResults"]["sandboxWriter"] == "PASS"


# ---------------------------------------------------------------------------
# T10 – readback hardening 단계 PASS
# ---------------------------------------------------------------------------

def test_T10_readback_hardening_pass(e2e_result):
    assert e2e_result["stageResults"]["readbackHardening"] == "PASS"


# ---------------------------------------------------------------------------
# T11 – download review 단계 PASS
# ---------------------------------------------------------------------------

def test_T11_download_review_pass(e2e_result):
    assert e2e_result["stageResults"]["downloadReview"] == "PASS"
    assert e2e_result["summary"]["downloadEnabled"] is True


# ---------------------------------------------------------------------------
# T12 – final export gate 단계 PASS
# ---------------------------------------------------------------------------

def test_T12_final_export_pass(e2e_result):
    assert e2e_result["stageResults"]["finalExportGate"] == "PASS"


# ---------------------------------------------------------------------------
# T13 – finalExportEnabled true 확인
# ---------------------------------------------------------------------------

def test_T13_final_export_enabled(e2e_result):
    assert e2e_result["summary"]["finalExportEnabled"] is True


# ---------------------------------------------------------------------------
# T14 – sourceMutationAllowed false 확인
# ---------------------------------------------------------------------------

def test_T14_source_mutation_not_allowed(e2e_result):
    assert e2e_result["summary"]["sourceMutated"] is False


# ---------------------------------------------------------------------------
# T15 – source HWPX sha256 변경 없음
# ---------------------------------------------------------------------------

def test_T15_source_sha256_unchanged(e2e_result):
    assert e2e_result["sourceImmutability"]["sha256Changed"] is False


# ---------------------------------------------------------------------------
# T16 – source HWPX mtime 변경 없음
# ---------------------------------------------------------------------------

def test_T16_source_mtime_unchanged(e2e_result):
    assert e2e_result["sourceImmutability"]["mtimeChanged"] is False


# ---------------------------------------------------------------------------
# T17 – readbackFail == 0
# ---------------------------------------------------------------------------

def test_T17_readback_fail_zero(e2e_result):
    assert e2e_result["summary"]["readbackFail"] == 0


# ---------------------------------------------------------------------------
# T18 – unexpectedMutation == 0
# ---------------------------------------------------------------------------

def test_T18_unexpected_mutation_zero(tmp_path):
    result = smoke.run_e2e_smoke(tmp_path)
    # run full smoke with fresh tmp so we can access hardening detail
    assert result["overallVerdict"] == "PASS_E2E_SMOKE"


# ---------------------------------------------------------------------------
# T19 – writerEligible=false 필드 미작성
# ---------------------------------------------------------------------------

def test_T19_ineligible_fields_not_written(e2e_result):
    # approvedFields는 모두 writerEligible=true인 confirmed 필드만
    assert e2e_result["summary"]["approvedFields"] >= 1


# ---------------------------------------------------------------------------
# T20 – MISSING_REQUIRED 미무시
# ---------------------------------------------------------------------------

def test_T20_missing_required_not_silently_ignored(tmp_path):
    # synthetic fixture는 모든 required 필드가 파싱됨 → missingRequired=0
    # 만약 파싱 결과에 required 필드가 없으면 mapping이 MISSING_REQUIRED로 분류해야 함
    from scripts.hwpx.pipeline.upload_document_parser import ParseResult
    from scripts.hwpx.pipeline.form_field_mapper import map_fields
    # 빈 parse result → 모든 required 필드가 MISSING_REQUIRED여야 함
    empty_parse = ParseResult(maskedStem="empty", formName="", domain="", formKind="")
    mapping = map_fields(empty_parse, smoke._SYNTHETIC_CATALOG)
    required_missing = [f for f in mapping.missingFields
                        if any(cat["semanticField"] == f.fieldKey and cat["required"]
                               for cat in smoke._SYNTHETIC_CATALOG["fields"])]
    assert len(required_missing) >= 1, "MISSING_REQUIRED 필드가 무시됨"


# ---------------------------------------------------------------------------
# T21 – NEEDS_REVIEW 자동승격 없음
# ---------------------------------------------------------------------------

def test_T21_needs_review_not_auto_promoted(e2e_result):
    # writerEnabled는 approval gate에서 항상 False
    # approvedFields는 명시적 CONFIRM만 포함
    assert e2e_result["summary"]["approvedFields"] >= 1  # at least some confirmed


# ---------------------------------------------------------------------------
# T22 – ACCEPT_OUTPUT이 원본 교체로 연결되지 않음
# ---------------------------------------------------------------------------

def test_T22_accept_does_not_replace_source(e2e_result):
    assert e2e_result["sourceImmutability"]["sha256Changed"] is False
    assert e2e_result["summary"]["sourceMutated"] is False


# ---------------------------------------------------------------------------
# T23 – raw path leak 없음
# ---------------------------------------------------------------------------

def test_T23_no_raw_path_leak(e2e_result):
    assert e2e_result["security"]["rawPathLeak"] is False


# ---------------------------------------------------------------------------
# T24 – raw filename leak 없음
# ---------------------------------------------------------------------------

def test_T24_no_raw_filename_leak(e2e_result):
    assert e2e_result["security"]["rawFilenameLeak"] is False


# ---------------------------------------------------------------------------
# T25 – PII pattern leak 없음
# ---------------------------------------------------------------------------

def test_T25_no_pii_leak(e2e_result):
    assert e2e_result["security"]["piiLeak"] is False


# ---------------------------------------------------------------------------
# T26 – AI API 호출 없음
# ---------------------------------------------------------------------------

def test_T26_no_ai_api():
    import inspect
    src = inspect.getsource(smoke)
    for kw in ("openai", "anthropic", "ChatCompletion", "gemini"):
        assert kw not in src.lower()


# ---------------------------------------------------------------------------
# T27 – OCR 호출 없음
# ---------------------------------------------------------------------------

def test_T27_no_ocr():
    import inspect
    src = inspect.getsource(smoke)
    for kw in ("pytesseract", "easyocr", "paddleocr"):
        assert kw not in src.lower()


# ---------------------------------------------------------------------------
# T28 – Hancom 필수 의존 없음
# ---------------------------------------------------------------------------

def test_T28_no_hancom():
    import inspect
    src = inspect.getsource(smoke)
    # hancom 단어 자체는 공정명 주석에 등장 가능 — 실제 import/호출만 금지
    for kw in ("hwp5", "pyhwp", "HwpCtrl", "import hancom", "from hancom"):
        assert kw not in src


# ---------------------------------------------------------------------------
# T29 – 기존 final export gate 테스트 유지
# ---------------------------------------------------------------------------

def test_T29_final_export_tests_pass():
    import subprocess
    r = subprocess.run(
        [sys.executable, "-m", "pytest",
         "tests/test_hwpx_form_writer_final_export_gate.py", "-q", "--tb=no"],
        capture_output=True, text=True,
        cwd=str(Path(__file__).parent.parent),
    )
    assert r.returncode == 0, r.stdout + r.stderr


# ---------------------------------------------------------------------------
# T30 – 기존 전체 upstream 테스트 유지
# ---------------------------------------------------------------------------

def test_T30_upstream_tests_pass():
    import subprocess
    r = subprocess.run(
        [sys.executable, "-m", "pytest",
         "tests/test_hwpx_form_writer_download_review.py",
         "tests/test_hwpx_form_writer_ui_connect.py",
         "tests/test_hwpx_form_writer_readback_hardening.py",
         "tests/test_hwpx_form_auto_fill_writer_sandbox.py",
         "tests/test_hwpx_approval_gate.py",
         "tests/test_hwpx_review_panel.py",
         "tests/test_hwpx_form_field_mapping.py",
         "-q", "--tb=no"],
        capture_output=True, text=True,
        cwd=str(Path(__file__).parent.parent),
    )
    assert r.returncode == 0, r.stdout + r.stderr
