"""HWPX-CORPUS-PROFILER-LOCAL-INVENTORY-01 회귀 테스트."""
from __future__ import annotations

import io
import json
import sys
import zipfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "local"))

from hwpx_corpus_profiler import parse_args, run_profiler  # noqa: E402


def _minimal_hwpx_bytes(*, with_table: bool = False, broken_mimetype: bool = False) -> bytes:
    """본 테스트용 최소 HWPX 패키지 (한컴 호환성보다는 profiler가 잘 읽는지가 목적)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        info = zipfile.ZipInfo("mimetype")
        info.compress_type = zipfile.ZIP_STORED
        mt = b"application/hwp+zip" if not broken_mimetype else b"text/plain"
        zf.writestr(info, mt)
        zf.writestr("version.xml",
                    b'<?xml version="1.0" encoding="UTF-8"?>'
                    b'<ha:HCFVersion xmlns:ha="http://www.hancom.co.kr/hwpml/2011/app" '
                    b'ha:targetApplication="WORDPROCESSOR" ha:major="5" ha:minor="1" ha:micro="0" ha:buildNumber="1"/>',
                    compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr("META-INF/container.xml",
                    b'<?xml version="1.0" encoding="UTF-8"?>'
                    b'<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                    b'<rootfiles><rootfile full-path="Contents/content.hpf" '
                    b'media-type="application/hwpml-package+xml"/></rootfiles></container>',
                    compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr("Contents/content.hpf",
                    b'<?xml version="1.0" encoding="UTF-8"?>'
                    b'<opf:package xmlns:opf="http://www.idpf.org/2007/opf/" version="1.0">'
                    b'<opf:manifest>'
                    b'<opf:item id="header" href="header.xml" media-type="application/xml"/>'
                    b'<opf:item id="section0" href="section0.xml" media-type="application/xml"/>'
                    b'</opf:manifest>'
                    b'<opf:spine><opf:itemref idref="header"/><opf:itemref idref="section0"/></opf:spine>'
                    b'</opf:package>',
                    compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr("Contents/header.xml",
                    b'<?xml version="1.0" encoding="UTF-8"?>'
                    b'<hh:head xmlns:hh="http://www.hancom.co.kr/hwpml/2011/head">'
                    b'<hh:charPr id="5" height="1000"/>'
                    b'<hh:paraPr id="3"/>'
                    b'<hh:borderFill id="1"/>'
                    b'</hh:head>',
                    compress_type=zipfile.ZIP_DEFLATED)
        if with_table:
            section_xml = (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" '
                'xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">'
                '<hp:p paraPrIDRef="3"><hp:run charPrIDRef="5"><hp:t>공정표 문서 제목</hp:t></hp:run></hp:p>'
                '<hp:p paraPrIDRef="3"><hp:run charPrIDRef="5">'
                '<hp:tbl rowCnt="3" colCnt="4">'
                '<hp:tr>'
                '<hp:tc><hp:cellSpan colSpan="1" rowSpan="1"/><hp:subList><hp:p><hp:run><hp:t>공종</hp:t></hp:run></hp:p></hp:subList></hp:tc>'
                '<hp:tc><hp:cellSpan colSpan="1" rowSpan="1"/><hp:subList><hp:p><hp:run><hp:t>작업명</hp:t></hp:run></hp:p></hp:subList></hp:tc>'
                '<hp:tc><hp:cellSpan colSpan="1" rowSpan="1"/><hp:subList><hp:p><hp:run><hp:t>시작일</hp:t></hp:run></hp:p></hp:subList></hp:tc>'
                '<hp:tc><hp:cellSpan colSpan="1" rowSpan="1"/><hp:subList><hp:p><hp:run><hp:t>종료일</hp:t></hp:run></hp:p></hp:subList></hp:tc>'
                '</hp:tr>'
                '<hp:tr>'
                '<hp:tc><hp:cellSpan colSpan="1" rowSpan="1"/><hp:subList><hp:p><hp:run><hp:t>철근</hp:t></hp:run></hp:p></hp:subList></hp:tc>'
                '<hp:tc><hp:cellSpan colSpan="1" rowSpan="1"/><hp:subList><hp:p><hp:run><hp:t>배근</hp:t></hp:run></hp:p></hp:subList></hp:tc>'
                '<hp:tc><hp:cellSpan colSpan="1" rowSpan="1"/><hp:subList><hp:p><hp:run><hp:t>2026-05-01</hp:t></hp:run></hp:p></hp:subList></hp:tc>'
                '<hp:tc><hp:cellSpan colSpan="1" rowSpan="1"/><hp:subList><hp:p><hp:run><hp:t>2026-05-10</hp:t></hp:run></hp:p></hp:subList></hp:tc>'
                '</hp:tr>'
                '<hp:tr>'
                '<hp:tc><hp:cellSpan colSpan="2" rowSpan="1"/><hp:subList><hp:p><hp:run><hp:t>병합</hp:t></hp:run></hp:p></hp:subList></hp:tc>'
                '<hp:tc><hp:cellSpan colSpan="1" rowSpan="1"/><hp:subList><hp:p><hp:run/></hp:p></hp:subList></hp:tc>'
                '<hp:tc><hp:cellSpan colSpan="1" rowSpan="1"/><hp:subList><hp:p><hp:run/></hp:p></hp:subList></hp:tc>'
                '</hp:tr>'
                '</hp:tbl>'
                '</hp:run></hp:p>'
                '</hs:sec>'
            )
        else:
            section_xml = (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" '
                'xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">'
                '<hp:p><hp:run><hp:t>plain text</hp:t></hp:run></hp:p>'
                '</hs:sec>'
            )
        zf.writestr("Contents/section0.xml", section_xml.encode("utf-8"),
                    compress_type=zipfile.ZIP_DEFLATED)
    return buf.getvalue()


def _write_hwpx(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


# ──────────────────────────────────────────────────────────────────────────────


def test_empty_root_scan_produces_reports(tmp_path):
    root = tmp_path / "empty"
    root.mkdir()
    out = tmp_path / "out"
    args = parse_args(["--root", str(root), "--out", str(out), "--max-files", "10"])
    result = run_profiler(args)
    assert result["status"] == "PASS"
    assert result["scanned"] == 0
    assert (out / "summary.md").exists()
    assert (out / "inventory.jsonl").exists()


def test_single_valid_hwpx_scan(tmp_path):
    root = tmp_path / "corpus"
    _write_hwpx(root / "ok.hwpx", _minimal_hwpx_bytes(with_table=True))
    out = tmp_path / "out"
    args = parse_args(["--root", str(root), "--out", str(out), "--max-files", "10"])
    result = run_profiler(args)
    assert result["status"] == "PASS"
    assert result["scanned"] == 1
    assert result["zip_ok"] == 1
    assert result["tables"] >= 1
    inv = _read_jsonl(out / "inventory.jsonl")
    assert inv and inv[0]["status"] == "PASS"


def test_broken_zip_handled(tmp_path):
    root = tmp_path / "corpus"
    root.mkdir()
    (root / "broken.hwpx").write_bytes(b"NOT A ZIP")
    out = tmp_path / "out"
    args = parse_args(["--root", str(root), "--out", str(out), "--max-files", "10"])
    result = run_profiler(args)
    assert result["status"] == "PASS"  # 전체 스캔 계속
    fails = _read_jsonl(out / "parse_failures.jsonl")
    assert any(f["stage"] == "ZIP_OPEN" for f in fails)


def test_broken_mimetype_recorded_as_warning(tmp_path):
    root = tmp_path / "corpus"
    _write_hwpx(root / "weird.hwpx", _minimal_hwpx_bytes(broken_mimetype=True))
    out = tmp_path / "out"
    args = parse_args(["--root", str(root), "--out", str(out), "--max-files", "10"])
    run_profiler(args)
    pkg = _read_jsonl(out / "package_summary.jsonl")
    assert pkg
    assert any("unexpected mimetype" in w for w in pkg[0].get("warnings", []))


def test_table_catalog_generated(tmp_path):
    root = tmp_path / "corpus"
    _write_hwpx(root / "table.hwpx", _minimal_hwpx_bytes(with_table=True))
    out = tmp_path / "out"
    args = parse_args(["--root", str(root), "--out", str(out), "--max-files", "10"])
    run_profiler(args)
    catalog = _read_jsonl(out / "table_catalog.jsonl")
    assert catalog
    rec = catalog[0]
    assert rec["rowCount"] == 3 and rec["colCount"] == 4
    assert rec["mergedCellCount"] >= 1


def test_header_dictionary_generated(tmp_path):
    root = tmp_path / "corpus"
    _write_hwpx(root / "table.hwpx", _minimal_hwpx_bytes(with_table=True))
    out = tmp_path / "out"
    args = parse_args(["--root", str(root), "--out", str(out), "--max-files", "10"])
    run_profiler(args)
    csv_path = out / "header_dictionary.csv"
    assert csv_path.exists()
    text = csv_path.read_text(encoding="utf-8-sig")
    assert "공종" in text or "작업명" in text


def test_schedule_candidate_detected(tmp_path):
    root = tmp_path / "corpus"
    _write_hwpx(root / "공정표_5월.hwpx", _minimal_hwpx_bytes(with_table=True))
    out = tmp_path / "out"
    args = parse_args(["--root", str(root), "--out", str(out), "--max-files", "10"])
    run_profiler(args)
    sch = _read_jsonl(out / "schedule_candidates.jsonl")
    assert sch, "schedule candidate should be detected from filename + headers"
    assert any(s["autoEditGate"] in ("REVIEW_REQUIRED", "AUTO_EDIT_PLAN_ALLOWED", "PARSE_ONLY") for s in sch)


def test_scan_continues_after_failure(tmp_path):
    root = tmp_path / "corpus"
    _write_hwpx(root / "a.hwpx", _minimal_hwpx_bytes(with_table=True))
    (root / "b.hwpx").write_bytes(b"BROKEN")
    _write_hwpx(root / "c.hwpx", _minimal_hwpx_bytes(with_table=True))
    out = tmp_path / "out"
    args = parse_args(["--root", str(root), "--out", str(out), "--max-files", "10"])
    result = run_profiler(args)
    assert result["scanned"] == 3
    assert result["zip_ok"] == 2
    assert result["failures"] >= 1


def test_anonymize_paths_removes_relative_paths(tmp_path):
    root = tmp_path / "corpus"
    _write_hwpx(root / "secret.hwpx", _minimal_hwpx_bytes())
    out = tmp_path / "out"
    args = parse_args(["--root", str(root), "--out", str(out), "--max-files", "5"])
    run_profiler(args)
    inv = _read_jsonl(out / "inventory.jsonl")
    assert inv and inv[0]["relativePath"] == ""
    assert inv[0]["pathHash"]


def test_no_anonymize_keeps_relative_paths(tmp_path):
    root = tmp_path / "corpus"
    _write_hwpx(root / "visible.hwpx", _minimal_hwpx_bytes())
    out = tmp_path / "out"
    args = parse_args(["--root", str(root), "--out", str(out), "--no-anonymize-paths"])
    run_profiler(args)
    inv = _read_jsonl(out / "inventory.jsonl")
    assert inv and inv[0]["relativePath"] == "visible.hwpx"


def test_jsonl_csv_outputs_are_well_formed(tmp_path):
    root = tmp_path / "corpus"
    _write_hwpx(root / "a.hwpx", _minimal_hwpx_bytes(with_table=True))
    out = tmp_path / "out"
    args = parse_args(["--root", str(root), "--out", str(out), "--max-files", "5"])
    run_profiler(args)
    # JSONL: every line is valid JSON
    for name in ("inventory.jsonl", "package_summary.jsonl", "parse_summary.jsonl",
                 "table_catalog.jsonl", "schedule_candidates.jsonl", "parse_failures.jsonl"):
        path = out / name
        assert path.exists(), name
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                json.loads(line)  # raises on malformed
    # JSON
    fc = json.loads((out / "fixture_candidates.json").read_text(encoding="utf-8"))
    assert isinstance(fc, list)
    # CSV exists
    for name in ("inventory.csv", "parse_summary.csv", "header_dictionary.csv"):
        assert (out / name).exists(), name
