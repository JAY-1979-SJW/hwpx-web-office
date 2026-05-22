"""HWPX-PARSER-ENGINE-V2-ARCHITECTURE-01: 아키텍처 문서 계약 테스트.

문서가 존재하고 필수 계약 항목을 포함하는지 검증한다.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOCS_ARCH = PROJECT_ROOT / "docs" / "architecture"
DOCS_CONTRACTS = PROJECT_ROOT / "docs" / "contracts"
DOCS_REPORTS = PROJECT_ROOT / "docs" / "reports"

CONTRACT_DOC = DOCS_CONTRACTS / "hwpx_parser_engine_v2_contract.md"
ARCH_DOC = DOCS_ARCH / "hwpx_parser_engine_v2_architecture.md"
STRUCT_VS_SEMANTIC = DOCS_ARCH / "document_structure_vs_semantic_analysis.md"
SLOT_DETECTOR = DOCS_ARCH / "hwpx_input_slot_detector_design.md"
MODULE_SPLIT = DOCS_ARCH / "hwpx_parser_v2_module_split_plan.md"
FIXTURE_EXPECT = DOCS_REPORTS / "hwpx_parser_v2_fixture_expectations_20260517.md"
AUDIT_SCRIPT = PROJECT_ROOT / "scripts" / "ops" / "audit_hwpx_parser_engine_v2_architecture.py"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.exists() else ""


# ── 1. 계약 문서 — schemaVersion v2 ──────────────────────────────────────────

def test_contract_doc_exists():
    assert CONTRACT_DOC.exists(), f"계약 문서 없음: {CONTRACT_DOC}"


def test_contract_schema_version_v2():
    src = _read(CONTRACT_DOC)
    assert 'schemaVersion' in src and 'v2' in src, "schemaVersion v2 미정의"


# ── 2. 계약 — blocks[] ───────────────────────────────────────────────────────

def test_contract_blocks_defined():
    src = _read(CONTRACT_DOC)
    assert "blocks[]" in src or "## blocks" in src, "blocks[] 계약 미정의"


def test_contract_blocks_fields():
    src = _read(CONTRACT_DOC)
    for field in ["blockIndex", "sectionIndex", "type", "tableId", "orderKey"]:
        assert field in src, f"blocks[] 필드 미정의: {field}"


# ── 3. 계약 — tables[] ──────────────────────────────────────────────────────

def test_contract_tables_defined():
    src = _read(CONTRACT_DOC)
    assert "tables[]" in src or "## tables" in src, "tables[] 계약 미정의"


def test_contract_tables_fields():
    src = _read(CONTRACT_DOC)
    for field in ["tableId", "layoutGuess", "confidence", "hasMergedCells",
                  "hasNestedTables", "headerTexts", "inputSlotHints"]:
        assert field in src, f"tables[] 필드 미정의: {field}"


# ── 4. 계약 — cells[] ───────────────────────────────────────────────────────

def test_contract_cells_defined():
    src = _read(CONTRACT_DOC)
    assert "cells[]" in src or "## cells" in src, "cells[] 계약 미정의"


def test_contract_cells_fields():
    src = _read(CONTRACT_DOC)
    for field in ["cellId", "rowSpan", "colSpan", "isMergedOrigin",
                  "isCoveredByMerge", "normalizedText", "isLikelyLabel",
                  "isLikelyInputSlot", "borderFillIDRef", "fillColor"]:
        assert field in src, f"cells[] 필드 미정의: {field}"


# ── 5. 계약 — styles ────────────────────────────────────────────────────────

def test_contract_styles_defined():
    src = _read(CONTRACT_DOC)
    assert "styles" in src and ("charPr" in src or "borderFill" in src), \
        "styles 계약 미정의"


# ── 6. 계약 — inputSlotCandidates ───────────────────────────────────────────

def test_contract_input_slot_candidates_defined():
    src = _read(CONTRACT_DOC)
    assert "inputSlotCandidates" in src, "inputSlotCandidates 계약 미정의"


def test_contract_slot_fields():
    src = _read(CONTRACT_DOC)
    for field in ["slotId", "source", "labelText", "fieldGuess", "confidence"]:
        assert field in src, f"inputSlotCandidates 필드 미정의: {field}"


# ── 7. 구조 vs 의미 분석 경계 ────────────────────────────────────────────────

def test_structure_vs_semantic_doc_exists():
    assert STRUCT_VS_SEMANTIC.exists(), f"구조/의미 경계 문서 없음: {STRUCT_VS_SEMANTIC}"


def test_structure_vs_semantic_boundary_defined():
    src = _read(STRUCT_VS_SEMANTIC)
    assert "구조 분석" in src, "구조 분석 정의 없음"
    assert "의미 분석" in src, "의미 분석 정의 없음"


def test_structure_vs_semantic_confidence_policy():
    src = _read(STRUCT_VS_SEMANTIC)
    assert "confidence" in src.lower(), "confidence 임계값 정책 미정의"


# ── 8. fixture expectation 문서 ──────────────────────────────────────────────

def test_fixture_expectation_doc_exists():
    assert FIXTURE_EXPECT.exists(), f"fixture expectation 문서 없음: {FIXTURE_EXPECT}"


def test_fixture_expectation_covers_all_fixtures():
    src = _read(FIXTURE_EXPECT)
    for fx in ["fx_many_tables_page_marker", "fx_metadata_form",
               "fx_stamp_approval_legal", "fx_nested_legal_complex"]:
        assert fx in src, f"fixture 기대값 미정의: {fx}"


# ── 9. audit script 실행 가능 ────────────────────────────────────────────────

def test_audit_script_exists():
    assert AUDIT_SCRIPT.exists(), f"감사 스크립트 없음: {AUDIT_SCRIPT}"


def test_audit_script_passes():
    result = subprocess.run(
        [sys.executable, str(AUDIT_SCRIPT)],
        capture_output=True, text=True
    )
    assert result.returncode == 0, \
        f"audit FAIL:\n{result.stdout}\n{result.stderr}"


# ── 10. 추가: 아키텍처 문서 read-only 원칙 ──────────────────────────────────

def test_architecture_doc_exists():
    assert ARCH_DOC.exists(), f"아키텍처 문서 없음: {ARCH_DOC}"


def test_architecture_readonly_principle():
    src = _read(ARCH_DOC)
    assert "read-only" in src or "읽기 전용" in src, "read-only 원칙 미정의"


def test_architecture_forbidden_ops_stated():
    src = _read(ARCH_DOC)
    for forbidden in ["apply_edit_plan", "write_package", "OCR"]:
        assert forbidden in src, f"금지 항목 미정의: {forbidden}"


# ── 11. 모듈 분리 계획 ─────────────────────────────────────────────────────

def test_module_split_plan_exists():
    assert MODULE_SPLIT.exists(), f"모듈 분리 계획 없음: {MODULE_SPLIT}"


def test_module_split_covers_all_modules():
    src = _read(MODULE_SPLIT)
    for mod in ["package_reader", "table_parser", "layout_classifier",
                "input_slot_detector", "parser_contract"]:
        assert mod in src, f"모듈 계획 미정의: {mod}"


# ── 12. input slot detector 설계 ────────────────────────────────────────────

def test_slot_detector_design_exists():
    assert SLOT_DETECTOR.exists(), f"slot detector 설계 없음: {SLOT_DETECTOR}"


def test_slot_detector_rules_defined():
    src = _read(SLOT_DETECTOR)
    for rule in ["label_right", "label_below", "schedule_bar_range", "ignore"]:
        assert rule in src, f"탐지 규칙 미정의: {rule}"
