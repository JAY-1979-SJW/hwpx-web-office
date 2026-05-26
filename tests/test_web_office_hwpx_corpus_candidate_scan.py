from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest

from scripts.ops.run_web_office_hwpx_corpus_candidate_scan import (
    build_background_command,
    parse_args,
    run_scan,
)


def _minimal_hwpx_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        info = zipfile.ZipInfo("mimetype")
        info.compress_type = zipfile.ZIP_STORED
        zf.writestr(info, b"application/hwp+zip")
        zf.writestr(
            "META-INF/container.xml",
            b'<?xml version="1.0" encoding="UTF-8"?>'
            b'<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
            b'<rootfiles><rootfile full-path="Contents/content.hpf" '
            b'media-type="application/hwpml-package+xml"/></rootfiles></container>',
        )
        zf.writestr(
            "Contents/content.hpf",
            b'<?xml version="1.0" encoding="UTF-8"?>'
            b'<opf:package xmlns:opf="http://www.idpf.org/2007/opf/" version="1.0">'
            b'<opf:manifest><opf:item id="section0" href="section0.xml" '
            b'media-type="application/xml"/></opf:manifest>'
            b'<opf:spine><opf:itemref idref="section0"/></opf:spine></opf:package>',
        )
        zf.writestr(
            "Contents/section0.xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" '
            'xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">'
            '<hp:p><hp:run><hp:t>plain text</hp:t></hp:run></hp:p>'
            '</hs:sec>',
        )
    return buf.getvalue()


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_empty_candidate_root_writes_review_reports(tmp_path: Path) -> None:
    root = tmp_path / "empty"
    root.mkdir()
    report_dir = tmp_path / "reports"
    args = parse_args(["--candidate-root", str(root), "--report-dir", str(report_dir)])

    report = run_scan(args)

    assert report["verdict"] == "PASS"
    assert report["promotionRequiresApproval"] is True
    assert report["scanCounters"]["scanned"] == 0
    assert (report_dir / "candidate_scan_report.json").exists()
    assert (report_dir / "candidate_manifest_draft.json").exists()
    assert (report_dir / "candidate_scan_summary.md").exists()


def test_candidate_manifest_is_sanitized_and_not_promoted(tmp_path: Path) -> None:
    root = tmp_path / "candidates"
    raw_file = root / "customer-secret-name.hwpx"
    raw_file.parent.mkdir(parents=True)
    raw_file.write_bytes(_minimal_hwpx_bytes())
    report_dir = tmp_path / "reports"
    args = parse_args(["--candidate-root", str(root), "--report-dir", str(report_dir)])

    run_scan(args)

    manifest_text = (report_dir / "candidate_manifest_draft.json").read_text(encoding="utf-8")
    manifest = json.loads(manifest_text)
    assert "customer-secret-name.hwpx" not in manifest_text
    assert str(raw_file) not in manifest_text
    assert manifest["promotionPolicy"]["automaticPromotionAllowed"] is False
    assert manifest["promotionPolicy"]["requiresUserApproval"] is True
    assert manifest["candidates"]
    assert manifest["candidates"][0]["copyIntoCheckedInCorpusAllowed"] is False
    assert manifest["candidates"][0]["promotionStatus"] == "REVIEW_REQUIRED"


def test_candidate_scan_report_has_fixed_claim_boundary(tmp_path: Path) -> None:
    root = tmp_path / "candidates"
    root.mkdir()
    report_dir = tmp_path / "reports"
    args = parse_args(["--candidate-root", str(root), "--report-dir", str(report_dir)])

    run_scan(args)

    report = _read_json(report_dir / "candidate_scan_report.json")
    assert report["claimBoundary"] == (
        "Basic HWPX read is verified; full compatibility and UI fidelity remain open."
    )
    assert report["finalStatus"] == "CANDIDATE_SCAN_PASS_REVIEW_REQUIRED"
    assert str(tmp_path) not in json.dumps(report, ensure_ascii=False)


def test_background_command_runs_child_mode(tmp_path: Path) -> None:
    args = parse_args(
        [
            "--candidate-root",
            str(tmp_path / "candidates"),
            "--report-dir",
            str(tmp_path / "reports"),
            "--background",
        ]
    )

    command = build_background_command(args)

    assert "--background-child" in command
    assert "--background" not in command
    assert "--candidate-root" in command
    assert "--report-dir" in command
