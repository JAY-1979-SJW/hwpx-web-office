"""HWPX-GENERIC-FORMAT-RECOGNITION-AUDIT-01 단위 테스트.

감사 스크립트의 핵심 함수만 검증.
원본 fixture 수정 없음. apply_edit_plan 호출 없음.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


def _import_audit():
    sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "local"))
    import importlib
    if "hwpx_generic_format_recognition_audit" in sys.modules:
        return importlib.reload(sys.modules["hwpx_generic_format_recognition_audit"])
    return importlib.import_module("hwpx_generic_format_recognition_audit")


# ── T01: 모듈 import ────────────────────────────────────────────────────────

def test_audit_module_importable():
    mod = _import_audit()
    assert callable(mod._read_raw_xml)
    assert callable(mod._audit_raw_xml)
    assert callable(mod._audit_parser_coverage)
    assert callable(mod._decide_doc_verdict)
    assert callable(mod.run_audit)


# ── T02: _read_raw_xml 정상 동작 ────────────────────────────────────────────

def test_read_raw_xml_returns_bytes():
    mod = _import_audit()
    p = PROJECT_ROOT / "tests/fixtures/hwpx/gantt/fx_gantt_like_basic.hwpx"
    header, sections = mod._read_raw_xml(p)
    assert isinstance(header, bytes)
    assert len(header) > 0
    assert isinstance(sections, list)
    assert all(isinstance(s, bytes) for s in sections)
    assert len(sections) >= 1


# ── T03: _audit_raw_xml ground truth 추출 ───────────────────────────────────

def test_audit_raw_xml_extracts_truth():
    mod = _import_audit()
    p = PROJECT_ROOT / "tests/fixtures/hwpx/gantt/fx_gantt_like_basic.hwpx"
    header, sections = mod._read_raw_xml(p)
    truth = mod._audit_raw_xml(header, sections)
    assert truth["table_count"] > 0
    assert truth["table_cell_count"] > 0
    assert truth["charPr_count"] > 0
    assert truth["paraPr_count"] > 0


# ── T04: _audit_parser_coverage 비율 계산 ───────────────────────────────────

def test_parser_coverage_returns_ratios():
    mod = _import_audit()
    p = PROJECT_ROOT / "tests/fixtures/hwpx/gantt/fx_gantt_like_basic.hwpx"
    header, sections = mod._read_raw_xml(p)
    truth = mod._audit_raw_xml(header, sections)
    cov = mod._audit_parser_coverage(p, truth)
    assert "ratios" in cov
    assert "text_ratio" in cov["ratios"]
    assert 0 <= cov["ratios"]["text_ratio"] <= 1
    assert 0 <= cov["ratios"]["verticalAlign_ratio"] <= 1


# ── T05: _decide_doc_verdict 결함 식별 ──────────────────────────────────────

def test_decide_doc_verdict_halign_resolved():
    mod = _import_audit()
    p = PROJECT_ROOT / "tests/fixtures/hwpx/gantt/fx_gantt_like_basic.hwpx"
    header, sections = mod._read_raw_xml(p)
    truth = mod._audit_raw_xml(header, sections)
    cov = mod._audit_parser_coverage(p, truth)
    verdict, issues = mod._decide_doc_verdict(cov, truth)
    # HWPX-RECOGNITION-HALIGN-RESOLVER-01 이후: paraPr.align이 cell.horizontalAlign에 연결됨
    halign_issues = [i for i in issues if i.startswith("HALIGN_NOT_LINKED")]
    assert halign_issues == [], f"HALIGN_NOT_LINKED 잔존: {issues}"
    assert cov["ratios"]["horizontalAlign_ratio"] > 0.5


# ── T06: _decide_doc_verdict CHAR_STYLE 미지원 식별 ─────────────────────────

# ── T05b: LOW_TEXT 원인 분류 (HWPX-RECOGNITION-LOW-TEXT-RESOLVER-01) ──────────

def test_gantt_empty_classified_as_expected_template_empty():
    mod = _import_audit()
    p = PROJECT_ROOT / "tests/fixtures/hwpx/gantt/fx_gantt_like_template_empty.hwpx"
    header, sections = mod._read_raw_xml(p)
    truth = mod._audit_raw_xml(header, sections)
    cov = mod._audit_parser_coverage(p, truth)
    verdict, issues = mod._decide_doc_verdict(cov, truth)
    # 빈 템플릿: 공정표 빈셀 비중이 크고 객체 존재 → EXPECTED_TEMPLATE_EMPTY
    assert verdict == "WARN_EXPECTED_TEMPLATE_EMPTY", \
        f"gantt_empty은 빈 템플릿 분류되어야 함, 실제={verdict}, issues={issues}"
    assert any("LOW_TEXT_EXPECTED_EMPTY_TEMPLATE" in i for i in issues)
    assert not any("LOW_TEXT_PARSER_GAP" in i for i in issues), \
        "빈 템플릿은 parser gap이 아님"


def test_gantt_partial_classified_as_expected_template_empty():
    mod = _import_audit()
    p = PROJECT_ROOT / "tests/fixtures/hwpx/gantt/fx_gantt_like_partial_filled.hwpx"
    header, sections = mod._read_raw_xml(p)
    truth = mod._audit_raw_xml(header, sections)
    cov = mod._audit_parser_coverage(p, truth)
    verdict, issues = mod._decide_doc_verdict(cov, truth)
    assert verdict == "WARN_EXPECTED_TEMPLATE_EMPTY"


def test_expected_template_empty_is_not_fail_or_blocker():
    """빈 템플릿은 절대 FAIL/BLOCKER로 분류되면 안 된다."""
    mod = _import_audit()
    for fx in ["fx_gantt_like_template_empty.hwpx", "fx_gantt_like_partial_filled.hwpx"]:
        p = PROJECT_ROOT / f"tests/fixtures/hwpx/gantt/{fx}"
        header, sections = mod._read_raw_xml(p)
        truth = mod._audit_raw_xml(header, sections)
        cov = mod._audit_parser_coverage(p, truth)
        verdict, _ = mod._decide_doc_verdict(cov, truth)
        assert not verdict.startswith("FAIL")
        assert not verdict.startswith("BLOCKER")


def test_gantt_basic_remains_pass_after_low_text_classification():
    """gantt_basic은 text_ratio>=0.5이므로 PASS 유지."""
    mod = _import_audit()
    p = PROJECT_ROOT / "tests/fixtures/hwpx/gantt/fx_gantt_like_basic.hwpx"
    header, sections = mod._read_raw_xml(p)
    truth = mod._audit_raw_xml(header, sections)
    cov = mod._audit_parser_coverage(p, truth)
    verdict, issues = mod._decide_doc_verdict(cov, truth)
    assert verdict == "PASS_RECOGNITION_READY", f"verdict={verdict}, issues={issues}"


def test_low_text_parser_gap_classification_when_no_schedule_like_table():
    """공정표 후보가 없는데 text_ratio가 낮으면 PARSER_GAP으로 분류돼야 한다."""
    mod = _import_audit()
    cov = {
        "parser_cellCount": 50,
        "parser_tableCount": 1,
        "cells_with_normalizedText": 10,
        "cells_empty": 40,
        "cells_with_fillColor": 0,
        "cells_with_borderSummary": 0,
        "cells_with_verticalAlign": 0,
        "cells_with_horizontalAlign": 0,
        "cells_with_fontSizePt": 0,
        "cells_with_fontFace": 0,
        "cells_with_fontName": 0,
        "cells_with_bold": 0, "cells_with_italic": 0,
        "cells_with_underline": 0, "cells_with_textColor": 0,
        "cells_with_nested_table": 0,
        "ratios": {"text_ratio": 0.2, "horizontalAlign_ratio": 0.0,
                   "fillColor_ratio": 0.0, "fontFace_ratio": 0.0},
        "table_count_match": True,
        "cell_count_match": True,
        "scheduleLikeTableCount": 0,
        "scheduleLikeCellSum": 0,
        "scheduleLikeEmptySum": 0,
        "parser_objectCount": 0,
        "parser_binDataCount": 0,
    }
    truth = {
        "table_count": 1, "table_cell_count": 50,
        "charPr_with_bold": 0, "charPr_with_italic": 0,
        "charPr_with_underline": 0, "charPr_with_textColor": 0,
        "paraPr_with_align": 0, "borderFill_with_fillBrush": 0,
        "nested_table_count": 0, "image_count": 0,
        "shape_count": 0, "binData_count": 0,
    }
    verdict, issues = mod._decide_doc_verdict(cov, truth)
    assert verdict == "WARN_LOW_TEXT_PARSER_GAP"
    assert any("LOW_TEXT_PARSER_GAP" in i for i in issues)


def test_decide_doc_verdict_char_style_and_fontface_resolved():
    mod = _import_audit()
    p = PROJECT_ROOT / "tests/fixtures/hwpx/gantt/fx_gantt_like_basic.hwpx"
    header, sections = mod._read_raw_xml(p)
    truth = mod._audit_raw_xml(header, sections)
    cov = mod._audit_parser_coverage(p, truth)
    verdict, issues = mod._decide_doc_verdict(cov, truth)
    # CHAR_STYLE_MISSING / FONTFACE_ID_ONLY 모두 해제된 상태
    assert not any("CHAR_STYLE_MISSING" in i for i in issues), f"CHAR_STYLE_MISSING 잔존: {issues}"
    assert not any("FONTFACE_ID_ONLY" in i for i in issues), f"FONTFACE_ID_ONLY 잔존: {issues}"
    # fontName이 실제로 해석되어 노출됨
    assert cov["cells_with_fontName"] > 0


# ── T07: verdict 분류 정확성 ────────────────────────────────────────────────

def test_verdict_classification():
    mod = _import_audit()
    valid_verdicts = {
        "PASS_RECOGNITION_READY",
        "WARN_STYLE_INCOMPLETE",
        "WARN_OBJECT_MODEL_MISSING",
        "WARN_NESTED_TABLE_INCOMPLETE",
        "FAIL_STRUCTURE_MISMATCH",
        "BLOCKER_EDIT_UNSAFE",
    }
    p = PROJECT_ROOT / "tests/fixtures/hwpx/gantt/fx_gantt_like_basic.hwpx"
    header, sections = mod._read_raw_xml(p)
    truth = mod._audit_raw_xml(header, sections)
    cov = mod._audit_parser_coverage(p, truth)
    verdict, _ = mod._decide_doc_verdict(cov, truth)
    assert verdict in valid_verdicts


# ── T08: 감사 스크립트는 편집 호출 없음 ────────────────────────────────────

def test_audit_script_no_edit_calls():
    import re
    src_path = PROJECT_ROOT / "scripts" / "local" / "hwpx_generic_format_recognition_audit.py"
    src = src_path.read_text(encoding="utf-8")
    for pat in (r"(?<!#)\bapply_edit_plan\s*\(",
                r"(?<!#)\bfill_schedule_bars\s*\(",
                r"(?<!#)\bwrite_package\s*\(",
                r"(?<!#)\brepair_for_server\s*\("):
        assert not re.search(pat, src), f"forbidden call in audit: {pat}"


# ── T09: 원본 fixture 수정 없음 ─────────────────────────────────────────────

@pytest.mark.parametrize("fx_path", [
    "tests/fixtures/hwpx/gantt/fx_gantt_like_basic.hwpx",
    "tests/fixtures/hwpx/corpus/fx_metadata_form.hwpx",
])
def test_audit_does_not_modify_fixtures(fx_path):
    mod = _import_audit()
    path = PROJECT_ROOT / fx_path
    mtime_before = path.stat().st_mtime
    header, sections = mod._read_raw_xml(path)
    truth = mod._audit_raw_xml(header, sections)
    mod._audit_parser_coverage(path, truth)
    mtime_after = path.stat().st_mtime
    assert mtime_before == mtime_after
