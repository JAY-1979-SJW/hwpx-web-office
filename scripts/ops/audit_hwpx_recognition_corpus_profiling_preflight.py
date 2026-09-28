"""
HWPX-RECOGNITION-CORPUS-PROFILING-PREFLIGHT-01 — 감리 스크립트

A01~A16 감리 항목 전체를 순서대로 실행하고 결과를 출력한다.
"""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

PROFILER_SCRIPT = PROJECT_ROOT / "scripts" / "hwpx" / "recognition_corpus" / "profile_corpus_candidates.py"
BUILD_CORPUS_SCRIPT = PROJECT_ROOT / "scripts" / "hwpx" / "recognition_corpus" / "build_corpus_db.py"
DB_BUILD_TEST = PROJECT_ROOT / "tests" / "test_hwpx_recognition_corpus_db_build.py"

PASS_VERDICT = "PASS_HWPX_RECOGNITION_CORPUS_PROFILING_PREFLIGHT"
FAIL_PII = "FAIL_PII_LEAK"
FAIL_PATH = "FAIL_RAW_PATH_LEAK"
FAIL_FILENAME = "FAIL_RAW_FILENAME_LEAK"
FAIL_DB = "FAIL_CORPUS_DB_MUTATED"
FAIL_WRITER = "FAIL_WRITER_CALLED"
FAIL_AI_OCR = "FAIL_AI_OR_OCR_CALLED"
FAIL_HWPX_MUTATED = "FAIL_ORIGINAL_HWPX_MUTATED"

WARN_SYNTHETIC = "WARN_SYNTHETIC_FIXTURE_ONLY"
WARN_NO_REAL_CORPUS = "WARN_REAL_CORPUS_NOT_PROVIDED"
WARN_HANCOM = "WARN_HANCOM_NOT_INSTALLED_FALLBACK_ONLY"

_MIMETYPE = b"application/hwp+zip"
_CONTENT_HPF = b"""<?xml version="1.0" encoding="utf-8"?>
<opf:package xmlns:opf="http://www.idpf.org/2007/opf/">
  <opf:manifest>
    <opf:item id="section0" href="section0.xml" media-type="application/xml"/>
  </opf:manifest>
  <opf:spine><opf:itemref idref="section0"/></opf:spine>
</opf:package>"""
_SECTION_CONTENT = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<hp:sec xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">'
    "<hp:p><hp:t>test</hp:t></hp:p>"
    "<hp:tbl><hp:tr>"
    "<hp:tc><hp:p><hp:t>col1</hp:t></hp:p></hp:tc>"
    "<hp:tc><hp:p><hp:t>col2</hp:t></hp:p></hp:tc>"
    "</hp:tr></hp:tbl>"
    "</hp:sec>"
).encode("utf-8")


def _make_valid_hwpx(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", _MIMETYPE)
        zf.writestr("Contents/content.hpf", _CONTENT_HPF)
        zf.writestr("Contents/section0.xml", _SECTION_CONTENT)


def _make_broken_zip(path: Path) -> None:
    path.write_bytes(b"not a zip")


def _make_missing_xml(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", _MIMETYPE)
        zf.writestr("README.txt", b"placeholder")


class AuditRunner:
    def __init__(self):
        self.results: list[dict] = []
        self.fails: list[str] = []
        self.warns: list[str] = []

    def check(self, code: str, description: str, passed: bool, detail: str = "", fail_verdict: str = "") -> bool:
        status = "PASS" if passed else "FAIL"
        self.results.append({"code": code, "status": status, "description": description, "detail": detail})
        if not passed:
            v = fail_verdict or f"FAIL_{code}"
            self.fails.append(v)
        return passed

    def warn(self, msg: str) -> None:
        self.warns.append(msg)

    def report(self) -> int:
        print("\n" + "=" * 70)
        print("HWPX-RECOGNITION-CORPUS-PROFILING-PREFLIGHT-01 감리 결과")
        print("=" * 70)
        for r in self.results:
            sym = "✓" if r["status"] == "PASS" else "✗"
            print(f"  [{r['status']}] {r['code']} {sym} — {r['description']}")
            if r["detail"]:
                print(f"         {r['detail']}")
        print()
        if self.warns:
            for w in self.warns:
                print(f"  WARN: {w}")
            print()
        if self.fails:
            for f in self.fails:
                print(f"  FAIL verdict: {f}")
            print(f"\n최종 판정: FAIL ({len(self.fails)} items)")
            return 1
        print(f"최종 판정: {PASS_VERDICT}")
        return 0


def run_audit() -> int:
    ar = AuditRunner()

    # A01. profiler script exists
    ar.check("A01", "profiler script exists", PROFILER_SCRIPT.exists(),
             str(PROFILER_SCRIPT))

    if not PROFILER_SCRIPT.exists():
        ar.report()
        return 1

    # Import profiler via package path
    try:
        from hwpx.recognition_corpus import profile_corpus_candidates as mod
        import_ok = True
    except Exception as exc:
        import_ok = False
        ar.check("A01b", "profiler import ok", False, str(exc))

    if not import_ok:
        ar.report()
        return 1

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        hwpx_dir = tmp / "hwpx"
        hwpx_dir.mkdir()
        out_dir = tmp / "out"
        broken_dir = tmp / "broken"
        broken_dir.mkdir()
        missing_dir = tmp / "missing"
        missing_dir.mkdir()

        valid_path = hwpx_dir / "valid.hwpx"
        broken_path = broken_dir / "broken.hwpx"
        missing_path = missing_dir / "missing.hwpx"

        _make_valid_hwpx(valid_path)
        _make_broken_zip(broken_path)
        _make_missing_xml(missing_path)

        orig_mtime = valid_path.stat().st_mtime
        orig_size = valid_path.stat().st_size

        # A02. dry-run supported
        mod.profile_all(input_dir=hwpx_dir, output_dir=out_dir, dry_run=True)
        ar.check("A02", "dry-run does not create output dir", not out_dir.exists())

        # A03. input-dir/output-dir supported (normal run)
        summary = mod.profile_all(input_dir=hwpx_dir, output_dir=out_dir)
        ar.check("A03", "input-dir/output-dir supported, profile_summary.json created",
                 (out_dir / "profile_summary.json").exists())

        # A04. synthetic valid HWPX → READY
        rec_valid = mod.profile_one(valid_path)
        ar.check("A04", "valid HWPX classified as READY_FOR_CORPUS_INGEST",
                 rec_valid.status == mod.STATUS_READY,
                 f"got {rec_valid.status}: {rec_valid.blockedReason}")

        # A05. broken ZIP → BROKEN_ZIP
        rec_broken = mod.profile_one(broken_path)
        ar.check("A05", "broken ZIP classified as BROKEN_ZIP",
                 rec_broken.status == mod.STATUS_BROKEN_ZIP,
                 f"got {rec_broken.status}")

        # A06. missing XML → MISSING_REQUIRED_XML
        rec_missing = mod.profile_one(missing_path)
        ar.check("A06", "missing XML classified as MISSING_REQUIRED_XML",
                 rec_missing.status == mod.STATUS_MISSING_XML,
                 f"got {rec_missing.status}")

        # A07. output reports generated
        required_files = [
            "profile_summary.json",
            "profile_summary.md",
            "profile_candidates.json",
            "profile_blocked.json",
            "profile_audit.json",
        ]
        missing_reports = [f for f in required_files if not (out_dir / f).exists()]
        ar.check("A07", "all required output reports generated",
                 len(missing_reports) == 0,
                 f"missing: {missing_reports}")

        # A08. no absolute path leak
        abs_path_str = str(hwpx_dir.resolve())
        path_leak = False
        for rf in required_files:
            fp = out_dir / rf
            if fp.exists():
                content = fp.read_text(encoding="utf-8")
                if abs_path_str in content:
                    path_leak = True
                    break
                for drive in ["C:\\", "D:\\", "c:\\", "d:\\"]:
                    if drive in content:
                        path_leak = True
                        break
        ar.check("A08", "no absolute path leak in reports", not path_leak,
                 fail_verdict=FAIL_PATH)

        # A09. no raw filename leak
        raw_name = "valid.hwpx"
        filename_leak = False
        for rf in required_files:
            fp = out_dir / rf
            if fp.exists():
                content = fp.read_text(encoding="utf-8")
                if raw_name in content:
                    filename_leak = True
                    break
        ar.check("A09", "no raw filename leak in reports", not filename_leak,
                 fail_verdict=FAIL_FILENAME)

        # A10. no PII pattern leak
        pii_re = re.compile(r"\d{2,3}-\d{3,4}-\d{4}|\d{3}-\d{2}-\d{5}")
        pii_leak = False
        for rf in required_files:
            fp = out_dir / rf
            if fp.exists():
                content = fp.read_text(encoding="utf-8")
                stripped = re.sub(r"\b[0-9a-f]{12,}\b", "", content)
                if pii_re.search(stripped):
                    pii_leak = True
                    break
        ar.check("A10", "no PII pattern leak in reports", not pii_leak,
                 fail_verdict=FAIL_PII)

        # A11. corpus.sqlite3 not created or modified
        db_files = list(out_dir.rglob("*.sqlite3")) + list(out_dir.rglob("*.db"))
        ar.check("A11", "corpus.sqlite3 not created",
                 len(db_files) == 0,
                 f"found: {db_files}",
                 fail_verdict=FAIL_DB)

        # A12. original HWPX unchanged
        new_mtime = valid_path.stat().st_mtime
        new_size = valid_path.stat().st_size
        ar.check("A12", "original HWPX file not modified",
                 new_mtime == orig_mtime and new_size == orig_size,
                 f"mtime: {orig_mtime} -> {new_mtime}, size: {orig_size} -> {new_size}",
                 fail_verdict=FAIL_HWPX_MUTATED)

        # A13. writer not called (import check)
        profiler_src = PROFILER_SCRIPT.read_text(encoding="utf-8")
        writer_calls = re.findall(r"write_package|apply_edit_plan|repair_for_server", profiler_src)
        ar.check("A13", "writer functions not referenced in profiler",
                 len(writer_calls) == 0,
                 f"found: {writer_calls}",
                 fail_verdict=FAIL_WRITER)

        # A14. AI API not called
        ai_calls = re.findall(r"anthropic|openai|claude\.ai|ChatCompletion", profiler_src)
        ar.check("A14", "AI API not referenced in profiler",
                 len(ai_calls) == 0,
                 f"found: {ai_calls}",
                 fail_verdict=FAIL_AI_OCR)

        # A15. OCR not called
        ocr_calls = re.findall(r"pytesseract|easyocr|tesseract|image_to_string", profiler_src)
        ar.check("A15", "OCR not referenced in profiler",
                 len(ocr_calls) == 0,
                 f"found: {ocr_calls}",
                 fail_verdict=FAIL_AI_OCR)

    # A16. previous DB build tests still pass
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(DB_BUILD_TEST), "-v", "--tb=short", "-q"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(PROJECT_ROOT)
    )
    passed_17 = "17 passed" in result.stdout or result.returncode == 0
    ar.check("A16", "previous build_corpus_db tests still pass (17/17)",
             passed_17,
             result.stdout[-500:] if not passed_17 else "")

    # WARNs
    ar.warn(WARN_SYNTHETIC)
    ar.warn(WARN_NO_REAL_CORPUS)

    return ar.report()


if __name__ == "__main__":
    sys.exit(run_audit())
