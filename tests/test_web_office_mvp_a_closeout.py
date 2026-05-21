"""WEB-OFFICE-MVP-A-PARTIAL-CLOSEOUT-RISK-LEDGER-01 계약 테스트.

closeout 문서 + 위험대장이 시방서의 필수 섹션·토큰·금지 항목을 정확히
포함하는지 잠근다. 본 테스트는 writer/원본 HWPX 접근을 일절 하지 않는다.
"""
from __future__ import annotations
import sys
from pathlib import Path

PR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PR))

from scripts.ops.audit_web_office_mvp_a_closeout import (  # noqa: E402
    audit, CLOSEOUT_DOC, RISK_DOC,
    REQUIRED_CLOSEOUT_SECTIONS, REQUIRED_CLOSEOUT_TOKENS,
    REQUIRED_RISK_TOKENS, MVP_A_COMMIT,
)


def test_closeout_doc_exists():
    assert CLOSEOUT_DOC.is_file()


def test_risk_ledger_doc_exists():
    assert RISK_DOC.is_file()


def test_closeout_required_sections_all_present():
    text = CLOSEOUT_DOC.read_text(encoding="utf-8")
    for sec in REQUIRED_CLOSEOUT_SECTIONS:
        assert sec in text, f"section missing: {sec}"


def test_closeout_required_tokens_all_present():
    text = CLOSEOUT_DOC.read_text(encoding="utf-8")
    for tok in REQUIRED_CLOSEOUT_TOKENS:
        assert tok in text, f"token missing: {tok}"


def test_risk_ledger_required_tokens_all_present():
    text = RISK_DOC.read_text(encoding="utf-8")
    for tok in REQUIRED_RISK_TOKENS:
        assert tok in text, f"risk token missing: {tok}"


def test_set_cell_text_only_scope_explicit():
    text = CLOSEOUT_DOC.read_text(encoding="utf-8")
    assert "SET_CELL_TEXT" in text
    assert "SET_CELL_TEXT only" in text or "SET_CELL_TEXT 단독" in text \
              or "단일 값" in text


def test_para_edit_marked_as_unsupported():
    text = CLOSEOUT_DOC.read_text(encoding="utf-8")
    # PARA-EDIT 가 비지원 표에 포함됨
    assert "문단 run 편집" in text
    assert "Phase 3 PARA-EDIT" in text or "Phase 3" in text


def test_table_ops_marked_as_unsupported():
    text = CLOSEOUT_DOC.read_text(encoding="utf-8")
    assert "표 행/열 추가" in text
    assert "셀 병합" in text


def test_image_stamp_signature_marked_as_unsupported():
    text = CLOSEOUT_DOC.read_text(encoding="utf-8")
    for tok in ("이미지", "도장", "서명"):
        assert tok in text, f"missing: {tok}"


def test_source_direct_modification_forbidden_explicit():
    text = CLOSEOUT_DOC.read_text(encoding="utf-8")
    assert "원본 직접 수정" in text
    assert "outputPath == sourcePath" in text


def test_verify7_v1_v7_gate_explicit():
    text = CLOSEOUT_DOC.read_text(encoding="utf-8")
    assert "verify7 V1~V7" in text
    # V4_SOURCE_HASH_OK 등 게이트 일부 명시 (안전 게이트 표 안에)
    assert "V4_SOURCE_HASH_OK" in text


def test_phase_3_entry_conditions_explicit():
    text = CLOSEOUT_DOC.read_text(encoding="utf-8")
    assert "Phase 3 PARA-EDIT 착공 조건" in text
    assert "대표님 명시 승인" in text
    assert "73/73" in text or "73 회귀" in text or "73건" in text


def test_mvp_a_commit_anchor_present():
    text = CLOSEOUT_DOC.read_text(encoding="utf-8")
    assert MVP_A_COMMIT in text


def test_risk_ledger_has_min_8_mvp_a_items_open_or_mitigated():
    text = RISK_DOC.read_text(encoding="utf-8")
    # R-MA-01 ~ R-MA-08 최소
    for i in range(1, 9):
        assert f"R-MA-0{i}" in text, f"missing R-MA-0{i}"


def test_audit_returns_pass():
    out = audit()
    assert out["verdict"] == "PASS", out


def test_no_hwpx_outputs_created_by_this_process():
    """본 closeout 공정은 .hwpx 파일을 만들지 않는다."""
    suspect = []
    for sub in ("docs/architecture", "scripts/ops",
                            "frontend/web_office_viewer",
                            "scripts/hwpx/web_office"):
        d = PR / sub
        if d.is_dir():
            suspect.extend(d.glob("**/*.hwpx"))
    assert suspect == [], f"unexpected hwpx: {suspect}"
