"""HWPX-UPLOAD-PARSER-01 — 테스트."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

DRAFTS = PROJECT_ROOT / "data" / "drafts"


def test_parser_importable():
    from hwpx.pipeline import upload_document_parser as up
    assert hasattr(up, "parse_hwpx")
    assert hasattr(up, "parse_batch")
    assert hasattr(up, "ExtractedField")
    assert hasattr(up, "ParseResult")


def test_parser_no_write_package():
    src = (PROJECT_ROOT / "scripts" / "hwpx" / "pipeline" / "upload_document_parser.py").read_text("utf-8")
    assert "write_package" not in src
    assert "apply_edit_plan" not in src


def test_parse_result_structure():
    """존재하는 파일 파싱 시 구조 검증."""
    files = list(DRAFTS.rglob("*.hwpx"))
    if not files:
        pytest.skip("data/drafts 없음")
    from hwpx.pipeline.upload_document_parser import parse_hwpx
    r = parse_hwpx(files[10])  # smoke test
    d = r.to_dict()
    for key in ("maskedStem", "formName", "domain", "formKind",
                "fieldCount", "extractedFields", "warnings"):
        assert key in d, f"key missing: {key}"
    assert isinstance(d["extractedFields"], list)


def test_extracted_field_structure():
    files = list(DRAFTS.rglob("*.hwpx"))
    if not files:
        pytest.skip()
    from hwpx.pipeline.upload_document_parser import parse_hwpx
    for f in files[50:60]:
        r = parse_hwpx(f)
        for ef in r.extractedFields:
            d = ef.to_dict()
            for key in ("fieldKey", "value", "confidence", "sourceLabel",
                        "location", "extractMethod"):
                assert key in d, f"key missing: {key}"
            assert 0 < d["confidence"] <= 1.0
            assert d["extractMethod"] in ("horizontal", "vertical", "paragraph")


def test_no_pii_in_output():
    pii_re = re.compile(r"\d{2,3}-\d{3,4}-\d{4}|\d{3}-\d{2}-\d{5}")
    files = list(DRAFTS.rglob("*.hwpx"))[:100]
    if not files:
        pytest.skip()
    from hwpx.pipeline.upload_document_parser import parse_hwpx
    for f in files:
        r = parse_hwpx(f)
        out = json.dumps(r.to_dict(), ensure_ascii=False)
        assert not pii_re.search(out), f"PII in output for {f.name}: {out[:200]}"


def test_no_absolute_path_in_output():
    files = list(DRAFTS.rglob("*.hwpx"))[:20]
    if not files:
        pytest.skip()
    from hwpx.pipeline.upload_document_parser import parse_hwpx
    for f in files:
        r = parse_hwpx(f)
        out = json.dumps(r.to_dict(), ensure_ascii=False)
        for drive in ("C:\\Users\\", "/home/", "/Users/"):
            assert drive not in out, f"path leak: {out[:100]}"


def test_bad_zip_handled_gracefully():
    import tempfile
    from hwpx.pipeline.upload_document_parser import parse_hwpx
    with tempfile.NamedTemporaryFile(suffix=".hwpx", delete=False) as tmp:
        tmp.write(b"not a zip")
        tmp_path = Path(tmp.name)
    try:
        r = parse_hwpx(tmp_path)
        assert "bad_zip" in r.warnings
    finally:
        tmp_path.unlink(missing_ok=True)


def test_nonexistent_file_handled():
    from hwpx.pipeline.upload_document_parser import parse_hwpx
    r = parse_hwpx(Path("nonexistent_file.hwpx"))
    assert "file_not_found" in r.warnings


def test_confidence_minimum():
    """추출된 모든 필드의 confidence >= MIN_CONFIDENCE."""
    from hwpx.pipeline.upload_document_parser import parse_hwpx, MIN_CONFIDENCE
    files = list(DRAFTS.rglob("*.hwpx"))[:50]
    if not files:
        pytest.skip()
    for f in files:
        r = parse_hwpx(f)
        for ef in r.extractedFields:
            assert ef.confidence >= MIN_CONFIDENCE, (
                f"confidence {ef.confidence} < {MIN_CONFIDENCE} in {f.name}: {ef.fieldKey}={ef.value}"
            )


def test_parse_batch():
    files = list(DRAFTS.rglob("*.hwpx"))[:5]
    if not files:
        pytest.skip()
    from hwpx.pipeline.upload_document_parser import parse_batch
    results = parse_batch(files)
    assert len(results) == len(files)
    for r in results:
        assert hasattr(r, "extractedFields")
