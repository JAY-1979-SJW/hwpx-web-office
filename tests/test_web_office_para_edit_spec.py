"""WEB-OFFICE-PARA-EDIT-SPEC-01 계약 테스트.

PARA-EDIT 시방서 + R-P3 별책이 시방서 검증 항목을 모두 포함하는지
잠근다. 본 테스트는 writer / 원본 HWPX 접근을 일절 하지 않는다.
"""
from __future__ import annotations
import sys
from pathlib import Path

PR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PR))

from scripts.ops.audit_web_office_para_edit_spec import (  # noqa: E402
    audit, SPEC_DOC, RISK_DOC,
    REQUIRED_SPEC_SECTIONS, REQUIRED_SPEC_TOKENS,
    REQUIRED_RISK_TOKENS,
)


def test_spec_doc_exists():
    assert SPEC_DOC.is_file()


def test_risk_update_doc_exists():
    assert RISK_DOC.is_file()


def test_required_20_sections_all_present():
    text = SPEC_DOC.read_text(encoding="utf-8")
    assert len(REQUIRED_SPEC_SECTIONS) == 20
    for sec in REQUIRED_SPEC_SECTIONS:
        assert sec in text, f"section missing: {sec}"


def test_commandtype_tokens_present():
    text = SPEC_DOC.read_text(encoding="utf-8")
    for ct in ("TYPE_TEXT", "REPLACE_TEXT_RANGE", "DELETE_TEXT_RANGE",
                          "SET_PARAGRAPH_TEXT_SAFE",
                          "SPLIT_TEXT_RUN", "MERGE_TEXT_RUNS"):
        assert ct in text, f"commandType missing: {ct}"


def test_charpr_and_parpr_preserved_policy_explicit():
    text = SPEC_DOC.read_text(encoding="utf-8")
    assert "charPrIDRef 보존" in text
    assert "parPrIDRef 보존" in text
    # 정책 토큰 (REPLACE_TEXT_RANGE multi-charPr cross 처리)
    for tok in ("ANCHOR_CHARPR", "FOCUS_CHARPR", "REQUIRES_REVIEW"):
        assert tok in text


def test_run_split_merge_policy_explicit():
    text = SPEC_DOC.read_text(encoding="utf-8")
    assert "SPLIT_TEXT_RUN" in text
    assert "MERGE_TEXT_RUNS" in text
    assert "MERGE_CHARPR_MISMATCH" in text


def test_expected_before_and_stale_session_blocked():
    text = SPEC_DOC.read_text(encoding="utf-8")
    assert "expectedBefore" in text
    assert "STALE_SESSION" in text
    assert "EXPECTED_BEFORE_MISMATCH_PARAGRAPH" in text


def test_verify7_paragraph_v1_v7_definitions():
    text = SPEC_DOC.read_text(encoding="utf-8")
    for v in ("V1_RANGE_POSITION_OK", "V2_NO_CROSS_PARAGRAPH_LEAK",
                          "V3_UNTOUCHED_RUNS_PRESERVED",
                          "V4_CHARPR_PRESERVED", "V5_PARPR_PRESERVED",
                          "V6_OUTPUT_ISOLATED", "V7_READBACK_MATCH"):
        assert v in text


def test_applied_empty_vacuous_pass_blocked_explicit():
    text = SPEC_DOC.read_text(encoding="utf-8")
    assert "applied=∅" in text
    assert "vacuous PASS" in text
    assert "DRY_RUN_NO_APPLIED" in text


def test_mvp_a_set_cell_text_scope_protected():
    text = SPEC_DOC.read_text(encoding="utf-8")
    # MVP-A 범위 보호 — SET_CELL_TEXT 그대로 유지, CELL-EDIT 무수정
    assert "SET_CELL_TEXT" in text
    assert "CELL-EDIT 코드 변경 금지" in text


def test_source_direct_modification_and_writer_forbidden():
    text = SPEC_DOC.read_text(encoding="utf-8")
    # 본 공정은 writer 호출 / output 생성 / 원본 접근 모두 금지
    for tok in ("writer 호출", "output HWPX 생성", "원본 HWPX 접근"):
        assert tok in text


def test_browser_must_not_parse_hwpx_xml_directly():
    text = SPEC_DOC.read_text(encoding="utf-8")
    assert "브라우저에서 HWPX XML 직접 파싱" in text


def test_r_p3_risk_items_present():
    text = RISK_DOC.read_text(encoding="utf-8")
    for i in range(1, 8):
        assert f"R-P3-0{i}" in text, f"missing R-P3-0{i}"


def test_phase_3_entry_conditions_present():
    text = SPEC_DOC.read_text(encoding="utf-8")
    assert "착공 조건" in text or "착공 승인 조건" in text
    assert "대표님 명시 승인" in text
    assert "89/89" in text


def test_audit_returns_pass():
    out = audit()
    assert out["verdict"] == "PASS", out


def test_no_writer_call_in_spec_audit():
    """본 공정 audit 코드는 writer 를 호출하지 않는다.

    (본 테스트 자체는 검사 토큰을 변수로 다루므로 self-탐지에서 제외.)
    """
    audit_src = (PR / "scripts/ops/audit_web_office_para_edit_spec.py"
                            ).read_text(encoding="utf-8")
    # 토큰 분할로 self-탐지 회피
    forbidden = ("apply" + "_edit_plan(", "hwpx" + "_edit_tool")
    for tok in forbidden:
        assert tok not in audit_src, f"audit has forbidden: {tok}"


def test_no_hwpx_outputs_from_this_process():
    """본 공정 산출 디렉토리에 .hwpx 파일이 없다."""
    suspect = []
    for sub in ("docs/architecture", "scripts/ops",
                            "frontend/web_office_viewer",
                            "scripts/hwpx/web_office"):
        d = PR / sub
        if d.is_dir():
            suspect.extend(d.glob("**/*.hwpx"))
    assert suspect == [], f"unexpected hwpx: {suspect}"
