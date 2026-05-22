"""HWPX-WEB-OFFICE-EDITOR-DEEP-ARCHITECTURE-01 계약 테스트.

설계서가 시방서의 필수 섹션·repo 연결점·MVP/Phase·라이선스 결정·
writer 금지 문구를 포함하는지 검증한다. 본 테스트는 writer 호출 또는
원본 HWPX 접근을 일절 하지 않는다.
"""
from __future__ import annotations
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.ops.audit_hwpx_web_office_architecture import (  # noqa: E402
    audit,
    ARCH_DOC,
    OSR_DOC,
)


def test_architecture_doc_exists():
    assert ARCH_DOC.is_file(), f"missing: {ARCH_DOC}"


def test_open_source_review_doc_exists():
    assert OSR_DOC.is_file(), f"missing: {OSR_DOC}"


def test_audit_returns_pass():
    result = audit()
    assert result["verdict"] == "PASS", (
        f"audit findings: {result['findings']}")
    assert result["fail_count"] == 0
    assert result["warn_count"] == 0


def test_arch_doc_lists_existing_repo_modules():
    text = ARCH_DOC.read_text(encoding="utf-8")
    must_have = [
        "parser_engine", "hwpx_edit_tool", "ai_proposal_contract",
        "fill_review_contract", "verify_e2e_input_precision",
        "auto_fill_master",
    ]
    for token in must_have:
        assert token in text, f"repo module token missing: {token}"


def test_arch_doc_has_open_source_decisions():
    osr = OSR_DOC.read_text(encoding="utf-8")
    # 채택/보류/배제 verdict + 라이선스 컬럼 모두 존재
    for v in ("채택", "보류", "배제"):
        assert v in osr
    for col in ("라이선스", "결정"):
        assert col in osr


def test_arch_doc_has_mvp_and_phase_roadmap():
    text = ARCH_DOC.read_text(encoding="utf-8")
    assert "Phase 0" in text and "Phase 10" in text
    assert "MVP-A" in text and "MVP-B" in text
    assert "부분 준공" in text


def test_arch_doc_writer_execution_forbidden_note():
    text = ARCH_DOC.read_text(encoding="utf-8")
    # 시방서 금지 — writer 실행 / 원본 수정 / 출력 생성 금지 문구
    forbid_tokens = ["writer 실행", "원본 HWPX", "출력 HWPX", "금지"]
    for tok in forbid_tokens:
        assert tok in text, f"forbid-note token missing: {tok}"


def test_arch_doc_hancom_full_compat_not_primary():
    text = ARCH_DOC.read_text(encoding="utf-8")
    # "한컴 완전 호환은 1차 목표가 아니" 류 명시 (시방서 전제 조항)
    assert "한컴" in text
    assert "1차" in text
    assert ("완전 호환" in text) or ("호환" in text)


def test_no_output_hwpx_generated_in_repo_by_this_doc():
    """본 공정 결과로 새 .hwpx 산출물이 docs/architecture 아래에
    생성되지 않았는지 확인."""
    arch_dir = PROJECT_ROOT / "docs/architecture"
    hwpx_files = list(arch_dir.glob("*.hwpx"))
    assert hwpx_files == [], f"unexpected hwpx in arch dir: {hwpx_files}"
