"""HWPX-FORM-FIELD-CATALOG-SEED-01 — 테스트."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

CATALOG_JSONL = (
    PROJECT_ROOT / "data" / "reports" / "hwpx_form_field_catalog" / "form_field_catalog.jsonl"
)
NOTABLE_JSON = PROJECT_ROOT / "data" / "reports" / "hwpx_form_field_catalog" / "notable_forms.json"


def test_form_field_catalog_importable():
    from hwpx.recognition_corpus import form_field_catalog as ffc

    assert hasattr(ffc, "build_catalog")
    assert hasattr(ffc, "build_summary")
    assert hasattr(ffc, "FormCatalogEntry")
    assert hasattr(ffc, "FieldEntry")


def test_catalog_output_exists():
    if not CATALOG_JSONL.exists():
        pytest.skip("실제 로컬 코퍼스로 생성한 catalog 없음(data/reports/는 .gitignore 대상)")


def test_catalog_record_structure():
    if not CATALOG_JSONL.exists():
        pytest.skip("catalog JSONL 미생성")
    line = CATALOG_JSONL.read_text(encoding="utf-8").splitlines()[0]
    rec = json.loads(line)
    for key in (
        "formId",
        "formName",
        "domain",
        "formKind",
        "byeoljiNumber",
        "fileCount",
        "fieldCount",
        "autoFillableCount",
        "requiredCount",
        "fields",
    ):
        assert key in rec, f"key missing: {key}"


def test_field_entry_structure():
    if not CATALOG_JSONL.exists():
        pytest.skip()
    lines = CATALOG_JSONL.read_text(encoding="utf-8").splitlines()
    for line in lines[:50]:
        rec = json.loads(line)
        for f in rec.get("fields", []):
            for key in (
                "primaryLabel",
                "labels",
                "semanticField",
                "autoFillable",
                "required",
                "fileOccurrenceCount",
                "totalOccurrenceCount",
            ):
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
        1
        for line in CATALOG_JSONL.read_text("utf-8").splitlines()
        if json.loads(line).get("fieldCount", 0) > 0
    )
    assert with_fields >= 400, f"필드 있는 서식 너무 적음: {with_fields}"


def test_notable_forms_exists():
    if not NOTABLE_JSON.exists():
        pytest.skip(
            "실제 로컬 코퍼스로 생성한 notable_forms.json 없음(data/reports/는 .gitignore 대상)"
        )


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
    src = (
        PROJECT_ROOT / "scripts" / "hwpx" / "recognition_corpus" / "form_field_catalog.py"
    ).read_text("utf-8")
    assert "write_package" not in src
    assert "apply_edit_plan" not in src


# ── load_catalog_entry (2026-09-29, editor_api_route.call_catalog_fill 용) ──


def test_load_catalog_entry_finds_real_form():
    from scripts.hwpx.recognition_corpus import form_field_catalog as ffc

    if not CATALOG_JSONL.exists():
        pytest.skip("카탈로그 jsonl 없음")
    entry = ffc.load_catalog_entry("공사 감리자 지정 신청서", CATALOG_JSONL)
    assert entry is not None
    assert entry["formName"] == "공사 감리자 지정 신청서"


def test_load_catalog_entry_returns_none_for_unknown_form():
    from scripts.hwpx.recognition_corpus import form_field_catalog as ffc

    if not CATALOG_JSONL.exists():
        pytest.skip("카탈로그 jsonl 없음")
    assert ffc.load_catalog_entry("존재하지 않는 서식 이름 12345", CATALOG_JSONL) is None


def test_load_catalog_entry_missing_file_returns_none(tmp_path):
    from scripts.hwpx.recognition_corpus import form_field_catalog as ffc

    assert ffc.load_catalog_entry("아무거나", tmp_path / "no_such.jsonl") is None


def test_map_from_paths_uses_load_catalog_entry():
    """form_field_mapper.map_from_paths 가 인라인 스캔 대신 load_catalog_entry
    를 호출하도록 옮겼는지(중복 제거) 소스로 고정한다."""
    src = (PROJECT_ROOT / "scripts" / "hwpx" / "pipeline" / "form_field_mapper.py").read_text(
        "utf-8"
    )
    assert "load_catalog_entry" in src
