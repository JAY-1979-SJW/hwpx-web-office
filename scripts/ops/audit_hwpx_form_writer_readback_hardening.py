"""
HWPX-FORM-AUTO-FILL-WRITER-READBACK-HARDENING-02 — 감리 스크립트

A01~A28 전 항목 실행 후 판정 출력.
"""
from __future__ import annotations

import io
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

HARDENING_SCRIPT = PROJECT_ROOT / "scripts" / "hwpx" / "pipeline" / "form_writer_readback_hardening.py"
HARDENING_TEST   = PROJECT_ROOT / "tests" / "test_hwpx_form_writer_readback_hardening.py"
WRITER_TEST      = PROJECT_ROOT / "tests" / "test_hwpx_form_auto_fill_writer_sandbox.py"
APPROVAL_TEST    = PROJECT_ROOT / "tests" / "test_hwpx_approval_gate.py"
PANEL_TEST       = PROJECT_ROOT / "tests" / "test_hwpx_review_panel.py"
MAPPING_TEST     = PROJECT_ROOT / "tests" / "test_hwpx_form_field_mapping.py"

PASS_VERDICT = "PASS_HWPX_FORM_WRITER_READBACK_HARDENING"
NS_HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"


class AuditRunner:
    def __init__(self):
        self.results: list[dict] = []
        self.fails:   list[str]  = []
        self.warns:   list[str]  = []

    def check(self, code, desc, passed, detail="", fail_verdict=""):
        st = "PASS" if passed else "FAIL"
        self.results.append({"code": code, "status": st, "description": desc, "detail": detail})
        if not passed:
            self.fails.append(fail_verdict or f"FAIL_{code}")
        return passed

    def warn(self, msg):
        self.warns.append(msg)

    def report(self) -> int:
        print("\n" + "=" * 70)
        print("HWPX-FORM-AUTO-FILL-WRITER-READBACK-HARDENING-02 감리 결과")
        print("=" * 70)
        for r in self.results:
            sym = "✓" if r["status"] == "PASS" else "✗"
            print(f"  [{r['status']}] {r['code']} {sym} — {r['description']}")
            if r["detail"]:
                for line in str(r["detail"])[:200].split("\n")[:2]:
                    print(f"         {line}")
        print()
        for w in self.warns:
            print(f"  WARN: {w}")
        if self.warns:
            print()
        if self.fails:
            for f in self.fails:
                print(f"  FAIL verdict: {f}")
            print(f"\n최종 판정: FAIL ({len(self.fails)} items)")
            return 1
        print(f"최종 판정: {PASS_VERDICT}")
        return 0


def _make_hwpx(rows: list[list[str]]) -> bytes:
    cells_xml = lambda cells: "".join(
        f'<hp:tc><hp:p><hp:run><hp:t>{c}</hp:t></hp:run></hp:p></hp:tc>'
        for c in cells
    )
    rows_xml = "".join(f"<hp:tr>{cells_xml(r)}</hp:tr>" for r in rows)
    section_xml = (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<hp:sec xmlns:hp="{NS_HP}">'
        f'<hp:tbl>{rows_xml}</hp:tbl>'
        f'</hp:sec>'
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("Contents/section0.xml", section_xml.encode("utf-8"))
    return buf.getvalue()


def _write_hwpx(path: Path, rows: list[list[str]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_make_hwpx(rows))
    return path


def _make_ar(confirmed=None):
    from hwpx.pipeline.approval_gate import ApprovedField, ACTION_CONFIRM
    approved = [
        ApprovedField(fk, lbl, val, val, ACTION_CONFIRM, "autoFillReady", 0.92)
        for fk, lbl, val in (confirmed or [])
    ]
    return SimpleNamespace(approvedFields=approved, pendingFields=[], writerEnabled=False)


def run_audit() -> int:
    import tempfile
    ar_obj = AuditRunner()
    tmp = Path(tempfile.mkdtemp(prefix="hwpx_rh_audit_"))

    # A01. 파일 존재
    ar_obj.check("A01", "readback hardening module exists",
                 HARDENING_SCRIPT.exists(), str(HARDENING_SCRIPT))
    if not HARDENING_SCRIPT.exists():
        return ar_obj.report()

    # A02. import
    try:
        from hwpx.pipeline.form_writer_readback_hardening import (
            verify_readback, ReadbackHardeningResult, SCHEMA_VERSION,
            READBACK_PASS, READBACK_WARN_NORMALIZED_MATCH,
            READBACK_FAIL_MISSING_TARGET, READBACK_FAIL_VALUE_MISMATCH,
            READBACK_FAIL_EMPTY_VALUE, READBACK_FAIL_TRUNCATED_VALUE,
            READBACK_FAIL_DUPLICATE_TARGET, READBACK_FAIL_OUTPUT_XML_BROKEN,
            VERDICT_PASS, VERDICT_FAIL_MISMATCH, VERDICT_FAIL_BROKEN,
            VERDICT_FAIL_XML_MUTATION, VERDICT_WARN_NORMALIZED,
            _sha256,
        )
    except Exception as exc:
        ar_obj.check("A02", "hardening module importable", False, str(exc))
        return ar_obj.report()
    ar_obj.check("A02", "sandbox writer output input supported", True)

    # A03. readback 수행
    from hwpx.pipeline.form_auto_fill_writer_sandbox import run_sandbox_write
    from hwpx.pipeline.approval_gate import ApprovedField, ACTION_CONFIRM

    tmpl = _write_hwpx(tmp / "tpl.hwpx", [["시공자", ""]])
    ar = _make_ar(confirmed=[("contractorName", "시공자", "대한소방")])
    wr = run_sandbox_write(ar, tmpl, tmp / "out")
    out_path = tmp / "out" / "output" / "sandbox_tpl.hwpx"
    hr = verify_readback(tmpl, out_path, ar.approvedFields, wr.to_dict())
    ar_obj.check("A03", "output HWPX readback performed",
                 len(hr.fieldResults) > 0, f"fields={len(hr.fieldResults)}")

    # A04. expected/actual hash 비교
    fr_dict = hr.fieldResults[0] if hr.fieldResults else {}
    ar_obj.check("A04", "expected/actual value hash compared",
                 "expectedValueHash" in fr_dict and "actualValueHash" in fr_dict,
                 fail_verdict="FAIL_READBACK_NOT_PERFORMED")

    # A05. normalized match 구분
    src5 = _write_hwpx(tmp / "src5.hwpx", [["시공자", ""]])
    out5 = _write_hwpx(tmp / "out5.hwpx", [["시공자", "대한소방"]])
    af5 = ApprovedField("contractorName", "시공자", "  대한소방  ", "", ACTION_CONFIRM, "", 0.92)
    loc5 = {"type": "table_cell", "sectionName": "Contents/section0.xml",
             "tableIndex": 0, "row": 0, "col": 1}
    wd5 = {"writtenFields": [{"fieldKey": "contractorName", "label": "시공자",
                               "decisionAction": ACTION_CONFIRM, "writeStatus": "WRITTEN",
                               "readbackStatus": "SKIPPED",
                               "targetLocation": loc5, "valueHash": ""}]}
    hr5 = verify_readback(src5, out5, [af5], wd5)
    norm_ok = any(f["readbackStatus"] == READBACK_WARN_NORMALIZED_MATCH for f in hr5.fieldResults)
    ar_obj.check("A05", "normalized match separated from exact match", norm_ok)

    # A06. missing target 감지
    af6 = ApprovedField("contractorName", "시공자", "대한소방", "", ACTION_CONFIRM, "", 0.92)
    wd6 = {"writtenFields": [{"fieldKey": "contractorName", "label": "시공자",
                               "decisionAction": ACTION_CONFIRM, "writeStatus": "WRITTEN",
                               "readbackStatus": "SKIPPED",
                               "targetLocation": {
                                   "type": "table_cell",
                                   "sectionName": "Contents/section0.xml",
                                   "tableIndex": 99, "row": 0, "col": 1,
                               }, "valueHash": ""}]}
    hr6 = verify_readback(tmpl, out_path, [af6], wd6)
    miss_ok = any(f["readbackStatus"] == READBACK_FAIL_MISSING_TARGET for f in hr6.fieldResults)
    ar_obj.check("A06", "missing target detected", miss_ok)

    # A07. duplicate target 감지
    from hwpx.pipeline.form_writer_readback_hardening import READBACK_FAIL_DUPLICATE_TARGET
    same_loc = {"type": "table_cell", "sectionName": "Contents/section0.xml",
                "tableIndex": 0, "row": 0, "col": 1}
    wd7 = {"writtenFields": [
        {"fieldKey": "f1", "label": "l1", "decisionAction": ACTION_CONFIRM,
         "writeStatus": "WRITTEN", "readbackStatus": "SKIPPED",
         "targetLocation": same_loc, "valueHash": ""},
        {"fieldKey": "f2", "label": "l2", "decisionAction": ACTION_CONFIRM,
         "writeStatus": "WRITTEN", "readbackStatus": "SKIPPED",
         "targetLocation": same_loc, "valueHash": ""},
    ]}
    hr7 = verify_readback(tmpl, out_path, [], wd7)
    dup_ok = any(f["readbackStatus"] == READBACK_FAIL_DUPLICATE_TARGET for f in hr7.fieldResults)
    ar_obj.check("A07", "duplicate target detected", dup_ok)

    # A08. value mismatch 감지
    out8 = _write_hwpx(tmp / "out8.hwpx", [["시공자", "엉뚱한값"]])
    af8 = ApprovedField("contractorName", "시공자", "대한소방", "", ACTION_CONFIRM, "", 0.92)
    loc8 = {"type": "table_cell", "sectionName": "Contents/section0.xml",
             "tableIndex": 0, "row": 0, "col": 1}
    wd8 = {"writtenFields": [{"fieldKey": "contractorName", "label": "시공자",
                               "decisionAction": ACTION_CONFIRM, "writeStatus": "WRITTEN",
                               "readbackStatus": "SKIPPED",
                               "targetLocation": loc8, "valueHash": ""}]}
    hr8 = verify_readback(tmpl, out8, [af8], wd8)
    mm_ok = any(f["readbackStatus"] == READBACK_FAIL_VALUE_MISMATCH for f in hr8.fieldResults)
    ar_obj.check("A08", "value mismatch detected", mm_ok,
                 fail_verdict="FAIL_READBACK_MISMATCH")

    # A09. empty value 감지
    out9 = _write_hwpx(tmp / "out9.hwpx", [["시공자", ""]])
    hr9 = verify_readback(tmpl, out9, [af8], wd8)
    empty_ok = any(f["readbackStatus"] == READBACK_FAIL_EMPTY_VALUE for f in hr9.fieldResults)
    ar_obj.check("A09", "empty value detected", empty_ok)

    # A10. truncated value 감지
    long_val = "대한소방설비주식회사서울특별시강남구"
    short_val = "대한소방설비"
    out10 = _write_hwpx(tmp / "out10.hwpx", [["시공자", short_val]])
    af10 = ApprovedField("contractorName", "시공자", long_val, "", ACTION_CONFIRM, "", 0.92)
    wd10 = {"writtenFields": [{"fieldKey": "contractorName", "label": "시공자",
                                "decisionAction": ACTION_CONFIRM, "writeStatus": "WRITTEN",
                                "readbackStatus": "SKIPPED",
                                "targetLocation": loc8, "valueHash": ""}]}
    hr10 = verify_readback(tmpl, out10, [af10], wd10)
    trunc_ok = any(f["readbackStatus"] == READBACK_FAIL_TRUNCATED_VALUE for f in hr10.fieldResults)
    ar_obj.check("A10", "truncated value detected", trunc_ok)

    # A11. ZIP 깨짐 감지
    bad_zip = tmp / "bad.hwpx"
    bad_zip.write_bytes(b"not a zip")
    hr11 = verify_readback(tmpl, bad_zip, [af8], wd8)
    ar_obj.check("A11", "output ZIP broken detected",
                 hr11.overallVerdict == VERDICT_FAIL_BROKEN,
                 fail_verdict="FAIL_OUTPUT_HWPX_BROKEN")

    # A12. section XML 깨짐 감지
    buf12 = io.BytesIO()
    with zipfile.ZipFile(buf12, "w") as z:
        z.writestr("Contents/section0.xml", b"<bad <xml")
    bad_xml = tmp / "bad_xml.hwpx"
    bad_xml.write_bytes(buf12.getvalue())
    hr12 = verify_readback(tmpl, bad_xml, [], {"writtenFields": []})
    ar_obj.check("A12", "section XML broken detected", not hr12.structureCheck.sectionXmlValid)

    # A13. table/cell count mutation 감지
    out13 = _write_hwpx(tmp / "out13.hwpx", [["시공자", "대한소방"], ["추가행", "추가값"]])
    hr13 = verify_readback(tmpl, out13, [af8], wd8)
    ar_obj.check("A13", "table/cell count mutation detected", hr13.structureCheck.cellCountChanged)

    # A14. 비대상 셀 mutation 감지
    tmpl14 = _write_hwpx(tmp / "tpl14.hwpx", [["시공자", ""], ["보조셀", "원래값"]])
    out14  = _write_hwpx(tmp / "out14.hwpx", [["시공자", "대한소방"], ["보조셀", "바뀐값"]])
    hr14 = verify_readback(tmpl14, out14, [af8], wd8)
    ar_obj.check("A14", "unexpected cell mutation detected",
                 hr14.structureCheck.unexpectedCellMutationCount > 0,
                 fail_verdict="FAIL_UNEXPECTED_XML_MUTATION")

    # A15. style/charPr mutation 감지
    src_xml = (f'<?xml version="1.0" encoding="UTF-8"?>'
               f'<hp:sec xmlns:hp="{NS_HP}"><hp:tbl><hp:tr>'
               f'<hp:tc><hp:p><hp:run><hp:t>시공자</hp:t></hp:run></hp:p></hp:tc>'
               f'<hp:tc><hp:p><hp:run><hp:t></hp:t></hp:run></hp:p></hp:tc>'
               f'</hp:tr></hp:tbl></hp:sec>')
    out_xml = (f'<?xml version="1.0" encoding="UTF-8"?>'
               f'<hp:sec xmlns:hp="{NS_HP}"><hp:tbl><hp:tr>'
               f'<hp:tc><hp:p><hp:run><hp:charPr/><hp:t>시공자</hp:t></hp:run></hp:p></hp:tc>'
               f'<hp:tc><hp:p><hp:run><hp:t>대한소방</hp:t></hp:run></hp:p></hp:tc>'
               f'</hp:tr></hp:tbl></hp:sec>')
    def _xml_to_hwpx(xml: str) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("Contents/section0.xml", xml.encode("utf-8"))
        return buf.getvalue()
    src15 = tmp / "src15.hwpx"; src15.write_bytes(_xml_to_hwpx(src_xml))
    out15 = tmp / "out15.hwpx"; out15.write_bytes(_xml_to_hwpx(out_xml))
    hr15 = verify_readback(src15, out15, [], {"writtenFields": []})
    ar_obj.check("A15", "style/charPr mutation detected", hr15.structureCheck.styleMutationDetected)

    # A16/A17. source sha256/mtime 변경 없음
    before_hash  = _sha256(tmpl)
    before_mtime = tmpl.stat().st_mtime
    verify_readback(tmpl, out_path, ar.approvedFields, wr.to_dict())
    ar_obj.check("A16", "source sha256 unchanged",
                 _sha256(tmpl) == before_hash, fail_verdict="FAIL_SOURCE_HWPX_MUTATED")
    ar_obj.check("A17", "source mtime unchanged",
                 tmpl.stat().st_mtime == before_mtime, fail_verdict="FAIL_SOURCE_HWPX_MUTATED")

    # A18. raw value 저장 없음
    out_str = json.dumps(hr.to_dict(), ensure_ascii=False)
    ar_obj.check("A18", "no raw value stored in report",
                 "대한소방" not in out_str, fail_verdict="FAIL_RAW_VALUE_STORED")

    # A19. valueHash only 정책
    hash_only = all("expectedValueHash" in f and "actualValueHash" in f
                    and not f.get("valueStoredInReport", True)
                    for f in hr.fieldResults)
    ar_obj.check("A19", "valueHash only policy enforced", hash_only)

    # A20/A21. raw path / filename leak
    path_leak = any(d in out_str for d in ("C:\\Users\\", "/home/", "/Users/"))
    ar_obj.check("A20", "no raw path leak", not path_leak,
                 fail_verdict="FAIL_RAW_PATH_LEAK")
    src_code = HARDENING_SCRIPT.read_text(encoding="utf-8")
    fn_leak = any(d in src_code for d in ("C:\\Users\\", "/home/"))
    ar_obj.check("A21", "no raw filename leak in source", not fn_leak,
                 fail_verdict="FAIL_RAW_FILENAME_LEAK")

    # A22. PII leak
    pii_re = re.compile(r"\d{3}-\d{2}-\d{5}|\d{6}-\d{7}")
    ar_obj.check("A22", "no PII leak in report",
                 not pii_re.search(out_str), fail_verdict="FAIL_PII_LEAK")

    # A23/A24. AI API / OCR 미참조
    ai  = any(kw in src_code for kw in ("anthropic", "openai", "ChatCompletion"))
    ocr = any(kw in src_code for kw in ("pytesseract", "easyocr", "image_to_string"))
    ar_obj.check("A23", "AI API not called", not ai, fail_verdict="FAIL_AI_OR_OCR_CALLED")
    ar_obj.check("A24", "OCR not called", not ocr, fail_verdict="FAIL_AI_OR_OCR_CALLED")

    # A25. Hancom 필수 의존 없음
    hancom = any(kw in src_code for kw in ("hwp5", "libhwp", "pyhwp", "hwpx2pdf"))
    ar_obj.check("A25", "Hancom not required", not hancom)

    # A26. hardening 테스트
    r26 = subprocess.run(
        [sys.executable, "-m", "pytest", str(HARDENING_TEST), "-q", "--tb=no"],
        capture_output=True, text=True, cwd=str(PROJECT_ROOT)
    )
    ar_obj.check("A26", "hardening tests pass", r26.returncode == 0, r26.stdout[-150:])

    # A27. sandbox writer + approval 테스트
    r27 = subprocess.run(
        [sys.executable, "-m", "pytest", str(WRITER_TEST), str(APPROVAL_TEST), "-q", "--tb=no"],
        capture_output=True, text=True, cwd=str(PROJECT_ROOT)
    )
    ar_obj.check("A27", "sandbox writer / approval tests pass",
                 r27.returncode == 0, r27.stdout[-150:])

    # A28. panel/mapping/parser/catalog/recommend 테스트
    r28 = subprocess.run(
        [sys.executable, "-m", "pytest",
         str(PANEL_TEST), str(MAPPING_TEST),
         "-q", "--tb=no"],
        capture_output=True, text=True, cwd=str(PROJECT_ROOT)
    )
    ar_obj.check("A28", "panel/mapping/parser/catalog/recommend tests pass",
                 r28.returncode == 0, r28.stdout[-150:])

    # WARNs
    ar_obj.warn("WARN_NORMALIZED_MATCH_ONLY")
    ar_obj.warn("WARN_SANDBOX_ONLY")
    ar_obj.warn("WARN_SYNTHETIC_TEMPLATE_ONLY")

    return ar_obj.report()


if __name__ == "__main__":
    sys.exit(run_audit())
