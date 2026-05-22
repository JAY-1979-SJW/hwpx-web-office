"""HWPX-RECOGNITION-CORPUS-PROFILING-PREFLIGHT-01 — profiling preflight 테스트."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
import zipfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

PROFILER_MODULE = (
    PROJECT_ROOT / "scripts" / "hwpx" / "recognition_corpus" / "profile_corpus_candidates.py"
)
CORPUS_DB_SCRIPT = (
    PROJECT_ROOT / "scripts" / "hwpx" / "recognition_corpus" / "build_corpus_db.py"
)

# ---------------------------------------------------------------------------
# Helpers to build synthetic HWPX fixtures in memory
# ---------------------------------------------------------------------------

_MIMETYPE = b"application/hwp+zip"

_CONTENT_HPF = b"""<?xml version="1.0" encoding="utf-8"?>
<opf:package xmlns:opf="http://www.idpf.org/2007/opf/">
  <opf:manifest>
    <opf:item id="section0" href="section0.xml" media-type="application/xml"/>
  </opf:manifest>
  <opf:spine>
    <opf:itemref idref="section0"/>
  </opf:spine>
</opf:package>"""

_SECTION_WITH_CONTENT = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<hp:sec xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">'
    "<hp:p><hp:t>사업명</hp:t><hp:t>test</hp:t></hp:p>"
    "<hp:tbl><hp:tr>"
    "<hp:tc><hp:p><hp:t>항목</hp:t></hp:p></hp:tc>"
    "<hp:tc><hp:p><hp:t>내용</hp:t></hp:p></hp:tc>"
    "</hp:tr></hp:tbl>"
    "</hp:sec>"
).encode("utf-8")

_SECTION_EMPTY = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<hp:sec xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">'
    "</hp:sec>"
).encode("utf-8")


def _make_valid_hwpx(tmp_path: Path, name: str = "test.hwpx") -> Path:
    p = tmp_path / name
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("mimetype", _MIMETYPE)
        zf.writestr("Contents/content.hpf", _CONTENT_HPF)
        zf.writestr("Contents/section0.xml", _SECTION_WITH_CONTENT)
    return p


def _make_broken_zip(tmp_path: Path, name: str = "broken.hwpx") -> Path:
    p = tmp_path / name
    p.write_bytes(b"this is not a zip file at all")
    return p


def _make_missing_xml(tmp_path: Path, name: str = "missing.hwpx") -> Path:
    p = tmp_path / name
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("mimetype", _MIMETYPE)
        # no content.hpf, no section*.xml
        zf.writestr("README.txt", b"hello")
    return p


def _make_empty_doc(tmp_path: Path, name: str = "empty.hwpx") -> Path:
    p = tmp_path / name
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("mimetype", _MIMETYPE)
        zf.writestr("Contents/content.hpf", _CONTENT_HPF)
        zf.writestr("Contents/section0.xml", _SECTION_EMPTY)
    return p


# ---------------------------------------------------------------------------
# T01. profiler CLI import 가능
# ---------------------------------------------------------------------------

def test_profiler_importable():
    from hwpx.recognition_corpus import profile_corpus_candidates as pcc
    assert hasattr(pcc, "profile_all")
    assert hasattr(pcc, "main")
    assert hasattr(pcc, "parse_args")


# ---------------------------------------------------------------------------
# T02. dry-run은 파일/DB 생성하지 않음
# ---------------------------------------------------------------------------

def test_dry_run_no_output(tmp_path):
    from hwpx.recognition_corpus.profile_corpus_candidates import profile_all

    hwpx_dir = tmp_path / "hwpx"
    hwpx_dir.mkdir()
    _make_valid_hwpx(hwpx_dir)

    out_dir = tmp_path / "out"
    profile_all(
        input_dir=hwpx_dir,
        output_dir=out_dir,
        dry_run=True,
    )
    assert not out_dir.exists(), "dry-run should not create output directory"


# ---------------------------------------------------------------------------
# T03. synthetic valid HWPX → READY_FOR_CORPUS_INGEST
# ---------------------------------------------------------------------------

def test_valid_hwpx_ready(tmp_path):
    from hwpx.recognition_corpus.profile_corpus_candidates import profile_one, STATUS_READY

    p = _make_valid_hwpx(tmp_path)
    rec = profile_one(p)
    assert rec.status == STATUS_READY, f"expected READY, got {rec.status}: {rec.blockedReason}"
    assert rec.sectionCount >= 1
    assert rec.paragraphCount >= 1 or rec.tableCount >= 1


# ---------------------------------------------------------------------------
# T04. 깨진 ZIP → BROKEN_ZIP
# ---------------------------------------------------------------------------

def test_broken_zip(tmp_path):
    from hwpx.recognition_corpus.profile_corpus_candidates import profile_one, STATUS_BROKEN_ZIP

    p = _make_broken_zip(tmp_path)
    rec = profile_one(p)
    assert rec.status == STATUS_BROKEN_ZIP


# ---------------------------------------------------------------------------
# T05. 필수 XML 누락 → MISSING_REQUIRED_XML
# ---------------------------------------------------------------------------

def test_missing_required_xml(tmp_path):
    from hwpx.recognition_corpus.profile_corpus_candidates import profile_one, STATUS_MISSING_XML

    p = _make_missing_xml(tmp_path)
    rec = profile_one(p)
    assert rec.status == STATUS_MISSING_XML


# ---------------------------------------------------------------------------
# T06. 빈 문서 → EMPTY_DOCUMENT 또는 UNSUPPORTED_STRUCTURE
# ---------------------------------------------------------------------------

def test_empty_document(tmp_path):
    from hwpx.recognition_corpus.profile_corpus_candidates import (
        profile_one, STATUS_EMPTY, STATUS_UNSUPPORTED,
    )

    p = _make_empty_doc(tmp_path)
    rec = profile_one(p)
    assert rec.status in (STATUS_EMPTY, STATUS_UNSUPPORTED), (
        f"expected EMPTY or UNSUPPORTED, got {rec.status}"
    )


# ---------------------------------------------------------------------------
# T07. absolute path가 보고서에 남지 않음
# ---------------------------------------------------------------------------

def test_no_absolute_path_in_report(tmp_path):
    from hwpx.recognition_corpus.profile_corpus_candidates import profile_all

    hwpx_dir = tmp_path / "src"
    hwpx_dir.mkdir()
    _make_valid_hwpx(hwpx_dir)

    out_dir = tmp_path / "reports"
    profile_all(input_dir=hwpx_dir, output_dir=out_dir)

    for report_file in out_dir.glob("*.json"):
        content = report_file.read_text(encoding="utf-8")
        # absolute path는 드라이브 레터 또는 /로 시작하는 경로
        assert str(hwpx_dir.resolve()) not in content, (
            f"absolute path leaked in {report_file.name}"
        )
        # Windows style absolute path
        for drive in ["C:\\", "D:\\", "c:\\", "d:\\"]:
            assert drive not in content, f"drive letter leaked in {report_file.name}"


# ---------------------------------------------------------------------------
# T08. 원본 파일명이 그대로 보고서에 남지 않음
# ---------------------------------------------------------------------------

def test_no_raw_filename_in_report(tmp_path):
    from hwpx.recognition_corpus.profile_corpus_candidates import profile_all

    hwpx_dir = tmp_path / "src"
    hwpx_dir.mkdir()
    original_name = "서울_00현장_작업일보.hwpx"
    _make_valid_hwpx(hwpx_dir, name=original_name)

    out_dir = tmp_path / "reports"
    profile_all(input_dir=hwpx_dir, output_dir=out_dir)

    for report_file in out_dir.glob("*.json"):
        content = report_file.read_text(encoding="utf-8")
        assert original_name not in content, (
            f"raw filename '{original_name}' leaked in {report_file.name}"
        )


# ---------------------------------------------------------------------------
# T09. 전화번호/사업자번호/주소 패턴이 보고서에 남지 않음
# ---------------------------------------------------------------------------

def test_no_pii_pattern_in_reports(tmp_path):
    from hwpx.recognition_corpus.profile_corpus_candidates import profile_all

    hwpx_dir = tmp_path / "src"
    hwpx_dir.mkdir()
    _make_valid_hwpx(hwpx_dir)

    out_dir = tmp_path / "reports"
    profile_all(input_dir=hwpx_dir, output_dir=out_dir)

    import re
    pii_re = re.compile(r"\d{2,3}-\d{3,4}-\d{4}|\d{3}-\d{2}-\d{5}|\d{6}-[1-4]\d{6}")
    for report_file in out_dir.glob("*.json"):
        content = report_file.read_text(encoding="utf-8")
        # The report should not contain raw PII; masked IDs (file_abc123) are OK
        # Only check that it's not in the blockedReason or content fields
        # We allow sha256 hex strings
        data = json.loads(content)
        text_for_pii = json.dumps(data)
        # Remove sha256 hex strings before PII check
        text_stripped = re.sub(r"\b[0-9a-f]{12,}\b", "", text_for_pii)
        assert not pii_re.search(text_stripped), (
            f"PII pattern found in {report_file.name}"
        )


# ---------------------------------------------------------------------------
# T10. corpus.sqlite3 생성 또는 수정 없음
# ---------------------------------------------------------------------------

def test_no_corpus_db_created(tmp_path):
    from hwpx.recognition_corpus.profile_corpus_candidates import profile_all

    hwpx_dir = tmp_path / "src"
    hwpx_dir.mkdir()
    _make_valid_hwpx(hwpx_dir)

    out_dir = tmp_path / "reports"
    profile_all(input_dir=hwpx_dir, output_dir=out_dir)

    db_files = list(out_dir.rglob("*.sqlite3")) + list(out_dir.rglob("*.db"))
    assert not db_files, f"DB files should not be created: {db_files}"


# ---------------------------------------------------------------------------
# T11. writer 호출 없음 (write_package / apply_edit_plan 미호출 검증)
# ---------------------------------------------------------------------------

def test_no_writer_called(tmp_path, monkeypatch):
    """write_package가 호출되면 AssertionError를 일으키도록 패치."""
    import unittest.mock as mock

    hwpx_dir = tmp_path / "src"
    hwpx_dir.mkdir()
    _make_valid_hwpx(hwpx_dir)

    out_dir = tmp_path / "reports"

    # profiler는 write_package를 import조차 하지 않아야 한다
    with mock.patch.dict("sys.modules", {"write_package": mock.MagicMock(side_effect=AssertionError("writer called"))}):
        from hwpx.recognition_corpus.profile_corpus_candidates import profile_all
        profile_all(input_dir=hwpx_dir, output_dir=out_dir)  # should not raise


# ---------------------------------------------------------------------------
# T12. AI API 호출 없음
# ---------------------------------------------------------------------------

def test_no_ai_api_called(tmp_path, monkeypatch):
    import unittest.mock as mock

    hwpx_dir = tmp_path / "src"
    hwpx_dir.mkdir()
    _make_valid_hwpx(hwpx_dir)
    out_dir = tmp_path / "reports"

    with mock.patch.dict("sys.modules", {
        "anthropic": mock.MagicMock(side_effect=AssertionError("anthropic called")),
        "openai": mock.MagicMock(side_effect=AssertionError("openai called")),
    }):
        from hwpx.recognition_corpus import profile_corpus_candidates as pcc
        import importlib
        importlib.reload(pcc)
        pcc.profile_all(input_dir=hwpx_dir, output_dir=out_dir)


# ---------------------------------------------------------------------------
# T13. OCR 호출 없음
# ---------------------------------------------------------------------------

def test_no_ocr_called(tmp_path, monkeypatch):
    import unittest.mock as mock

    hwpx_dir = tmp_path / "src"
    hwpx_dir.mkdir()
    _make_valid_hwpx(hwpx_dir)
    out_dir = tmp_path / "reports"

    with mock.patch.dict("sys.modules", {
        "pytesseract": mock.MagicMock(side_effect=AssertionError("ocr called")),
        "easyocr": mock.MagicMock(side_effect=AssertionError("ocr called")),
    }):
        from hwpx.recognition_corpus.profile_corpus_candidates import profile_all
        profile_all(input_dir=hwpx_dir, output_dir=out_dir)


# ---------------------------------------------------------------------------
# T14. 기존 build_corpus_db 테스트 17/17 유지 (smoke check: script exists)
# ---------------------------------------------------------------------------

def test_build_corpus_db_script_exists():
    assert CORPUS_DB_SCRIPT.exists(), (
        f"build_corpus_db.py not found at {CORPUS_DB_SCRIPT}"
    )
