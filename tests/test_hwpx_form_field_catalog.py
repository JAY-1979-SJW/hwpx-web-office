"""HWPX-FORM-FIELD-CATALOG-SEED-01 — 테스트."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

CATALOG_JSONL = (
    PROJECT_ROOT / "data" / "reports"
    / "hwpx_form_field_catalog" / "form_field_catalog.jsonl"
)
NOTABLE_JSON = (
    PROJECT_ROOT / "data" / "reports"
    / "hwpx_form_field_catalog" / "notable_forms.json"
)


def test_form_field_catalog_importable():
    from hwpx.recognition_corpus import form_field_catalog as ffc
    assert hasattr(ffc, "build_catalog")
    assert hasattr(ffc, "build_summary")
    assert hasattr(ffc, "FormCatalogEntry")
    assert hasattr(ffc, "FieldEntry")


def test_catalog_output_exists():
    assert CATALOG_JSONL.exists(), f"form_field_catalog.jsonl 없음"


def test_catalog_record_structure():
    if not CATALOG_JSONL.exists():
        pytest.skip("catalog JSONL 미생성")
    line = CATALOG_JSONL.read_text(encoding="utf-8").splitlines()[0]
    rec = json.loads(line)
    for key in ("formId", "formName", "domain", "formKind", "byeoljiNumber",
                "fileCount", "fieldCount", "autoFillableCount", "requiredCount", "fields"):
        assert key in rec, f"key missing: {key}"


def test_field_entry_structure():
    if not CATALOG_JSONL.exists():
        pytest.skip()
    lines = CATALOG_JSONL.read_text(encoding="utf-8").splitlines()
    for line in lines[:50]:
        rec = json.loads(line)
        for f in rec.get("fields", []):
            for key in ("primaryLabel", "labels", "semanticField", "autoFillable",
                        "required", "fileOccurrenceCount", "totalOccurrenceCount"):
                assert key in f, f"field key missing: {key}"
            assert isinstance(f["autoFillable"], bool)
            assert isinstance(f["required"], bool)
            assert isinstance(f["labels"], list)


def test_autofillable_implies_semantic_field():
    """autoFillable=True 이면 반드시 semanticField가 있어야 한다."""
    if not CATALOG_JSONL.exists():
        pytest.skip()
    for line in CATALOG_JSONL.read_text(encoding="utf-8").splitlines():
        rec = json.loads(line)
        for f in rec.get("fields", []):
            if f["autoFillable"]:
                assert f["semanticField"], (
                    f"autoFillable=True but no semanticField in form={rec['formName']}, label={f['primaryLabel']}"
                )


def test_catalog_has_sufficient_coverage():
    """936개 이상 서식에 필드 존재."""
    if not CATALOG_JSONL.exists():
        pytest.skip()
    with_fields = sum(
        1 for line in CATALOG_JSONL.read_text("utf-8").splitlines()
        if json.loads(line).get("fieldCount", 0) > 0
    )
    assert with_fields >= 400, f"필드 있는 서식 너무 적음: {with_fields}"


def test_notable_forms_exists():
    assert NOTABLE_JSON.exists(), "notable_forms.json 없음"


def test_no_pii_in_catalog():
    import re
    if not CATALOG_JSONL.exists():
        pytest.skip()
    pii_re = re.compile(r"\d{2,3}-\d{3,4}-\d{4}|\d{3}-\d{2}-\d{5}")
    for line in CATALOG_JSONL.read_text("utf-8").splitlines()[:200]:
        assert not pii_re.search(line), f"PII in catalog: {line[:100]}"


def test_no_absolute_path_in_catalog():
    if not CATALOG_JSONL.exists():
        pytest.skip()
    for line in CATALOG_JSONL.read_text("utf-8").splitlines()[:200]:
        for drive in ("C:\\Users\\", "D:\\Users\\", "/home/", "/Users/"):
            assert drive not in line, f"path leak: {line[:100]}"


def test_catalog_module_no_write_package():
    src = (PROJECT_ROOT / "scripts" / "hwpx" / "recognition_corpus" / "form_field_catalog.py").read_text("utf-8")
    assert "write_package" not in src
    assert "apply_edit_plan" not in src
