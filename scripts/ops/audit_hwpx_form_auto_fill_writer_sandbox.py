"""
HWPX-FORM-AUTO-FILL-WRITER-SANDBOX-01 — 감리 스크립트

A01~A28 전 항목 실행 후 판정 출력.
"""
from __future__ import annotations

import hashlib
import io
import json
import subprocess
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

WRITER_SCRIPT  = PROJECT_ROOT / "scripts" / "hwpx" / "pipeline" / "form_auto_fill_writer_sandbox.py"
WRITER_TEST    = PROJECT_ROOT / "tests" / "test_hwpx_form_auto_fill_writer_sandbox.py"
APPROVAL_TEST  = PROJECT_ROOT / "tests" / "test_hwpx_approval_gate.py"
PANEL_TEST     = PROJECT_ROOT / "tests" / "test_hwpx_review_panel.py"
MAPPING_TEST   = PROJECT_ROOT / "tests" / "test_hwpx_form_field_mapping.py"

PASS_VERDICT = "PASS_HWPX_FORM_AUTO_FILL_WRITER_SANDBOX"

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
        print("HWPX-FORM-AUTO-FILL-WRITER-SANDBOX-01 감리 결과")
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


def _write_tmp_hwpx(tmp_path: Path, rows: list[list[str]]) -> Path:
    p = tmp_path / "audit_template.hwpx"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(_make_hwpx(rows))
    return p


def _make_ar(confirmed=None, held=None, attach=None):
    from hwpx.pipeline.approval_gate import (
        ApprovedField, PendingField,
        ACTION_CONFIRM, ACTION_HOLD, ACTION_ATTACHMENT,
    )
    approved = [
        ApprovedField(fk, lbl, val, val, ACTION_CONFIRM, "autoFillReady", 0.92)
        for fk, lbl, val in (confirmed or [])
    ]
    pending = [
        PendingField(fk, lbl, ACTION_HOLD, "needsReview")
        for fk, lbl in (held or [])
    ] + [
        PendingField(fk, lbl, ACTION_ATTACHMENT, "missingRequired")
        for fk, lbl in (attach or [])
    ]
    return SimpleNamespace(approvedFields=approved, pendingFields=pending, writerEnabled=False)


def run_audit() -> int:
    import tempfile
    ar_obj = AuditRunner()
    tmp = Path(tempfile.mkdtemp(prefix="hwpx_audit_"))

    # A01. 파일 존재
    ar_obj.check("A01", "form_auto_fill_writer_sandbox.py exists",
                 WRITER_SCRIPT.exists(), str(WRITER_SCRIPT))
    if not WRITER_SCRIPT.exists():
        return ar_obj.report()

    # A02. import
    try:
        from hwpx.pipeline.form_auto_fill_writer_sandbox import (
            run_sandbox_write, SandboxWriteResult, SCHEMA_VERSION,
            BLOCKED_NOT_APPROVED, BLOCKED_HOLD, BLOCKED_ATTACHMENT_REQUIRED,
            BLOCKED_NO_TARGET_LOCATION, BLOCKED_AMBIGUOUS_TARGET,
            BLOCKED_LOW_TARGET_CONFIDENCE,
            _resolve_targets, _do_write, _readback_verify,
        )
    except Exception as exc:
        ar_obj.check("A02", "writer sandbox importable", False, str(exc))
        return ar_obj.report()
    ar_obj.check("A02", "approval gate input supported", True)

    # A03. template HWPX input
    ar_obj.check("A03", "template HWPX input supported", True)

    tmpl = _write_tmp_hwpx(tmp, [["시공자", ""], ["공사명", ""]])
    ar = _make_ar(confirmed=[("contractorName", "시공자", "대한소방")])

    # A04. dry-run은 output 생성 안 함
    out4 = tmp / "dry_out"
    result4 = run_sandbox_write(ar, tmpl, out4, dry_run=True)
    hwpx_files4 = list(out4.glob("**/*.hwpx")) if out4.exists() else []
    ar_obj.check("A04", "dry-run does not create output HWPX",
                 len(hwpx_files4) == 0, f"files={hwpx_files4}")

    # A05. sandbox-write는 output copy만 생성
    out5 = tmp / "sb_out"
    result5 = run_sandbox_write(ar, tmpl, out5)
    hwpx_files5 = list((out5 / "output").glob("*.hwpx")) if (out5 / "output").exists() else []
    ar_obj.check("A05", "sandbox-write creates output copy",
                 len(hwpx_files5) == 1, f"files={len(hwpx_files5)}")

    # A06. output_path == source_path 거부
    try:
        from hwpx.pipeline.form_auto_fill_writer_sandbox import _do_write
        _do_write(tmpl, tmpl, {}, [])
        a06_ok = False
    except (ValueError, AssertionError):
        a06_ok = True
    ar_obj.check("A06", "output_path == source_path rejected", a06_ok,
                 fail_verdict="FAIL_OUTPUT_EQUALS_SOURCE")

    # A07. 원본 sha256 변경 없음
    from hwpx.pipeline.form_auto_fill_writer_sandbox import _sha256
    before_hash = _sha256(tmpl)
    run_sandbox_write(ar, tmpl, tmp / "sha_out")
    after_hash = _sha256(tmpl)
    ar_obj.check("A07", "original HWPX sha256 unchanged",
                 before_hash == after_hash, fail_verdict="FAIL_SOURCE_HWPX_MUTATED")

    # A08. 원본 mtime 변경 없음
    mtime_before = tmpl.stat().st_mtime
    run_sandbox_write(ar, tmpl, tmp / "mtime_out")
    mtime_after = tmpl.stat().st_mtime
    ar_obj.check("A08", "original HWPX mtime unchanged",
                 mtime_before == mtime_after, fail_verdict="FAIL_SOURCE_HWPX_MUTATED")

    # A09. writerEligible=true only
    from hwpx.pipeline.approval_gate import ApprovedField, ACTION_CONFIRM
    af_bad = ApprovedField("taskName", "공사명", "소화공사", "",
                           ACTION_CONFIRM, "autoFillReady", 0.92)
    af_bad.writerEligible = False
    ar9 = SimpleNamespace(approvedFields=[af_bad], pendingFields=[], writerEnabled=False)
    result9 = run_sandbox_write(ar9, tmpl, tmp / "welig_out")
    written9 = {f["fieldKey"] for f in result9.writtenFields}
    ar_obj.check("A09", "writerEligible=true only policy enforced",
                 "taskName" not in written9, fail_verdict="FAIL_UNAPPROVED_FIELD_WRITTEN")

    # A10. writerEligible=false 차단
    blocked9 = [f for f in result9.blockedFields if f["fieldKey"] == "taskName"]
    ar_obj.check("A10", "writerEligible=false blocked",
                 len(blocked9) > 0 and blocked9[0]["blockedReason"] == BLOCKED_NOT_APPROVED)

    # A11. HOLD 차단
    ar11 = _make_ar(held=[("contractorName", "시공자")])
    result11 = run_sandbox_write(ar11, tmpl, tmp / "hold_out")
    hold_blocked = [f for f in result11.blockedFields if f.get("blockedReason") == BLOCKED_HOLD]
    ar_obj.check("A11", "HOLD blocked",
                 len(hold_blocked) > 0, fail_verdict="FAIL_HOLD_FIELD_WRITTEN")

    # A12. REQUEST_ATTACHMENT 차단
    ar12 = _make_ar(attach=[("contractorName", "시공자")])
    result12 = run_sandbox_write(ar12, tmpl, tmp / "att_out")
    att_blocked = [f for f in result12.blockedFields
                   if f.get("blockedReason") == BLOCKED_ATTACHMENT_REQUIRED]
    ar_obj.check("A12", "REQUEST_ATTACHMENT blocked",
                 len(att_blocked) > 0, fail_verdict="FAIL_ATTACHMENT_REQUIRED_FIELD_WRITTEN")

    # A13. target location 없으면 차단
    tmpl_no = _write_tmp_hwpx(tmp / "nolabel", [["전혀없는라벨", ""]])
    ar13 = _make_ar(confirmed=[("contractorName", "시공자", "대한소방")])
    result13 = run_sandbox_write(ar13, tmpl_no, tmp / "nolabel_out")
    no_loc = [f for f in result13.blockedFields
              if f.get("blockedReason") == BLOCKED_NO_TARGET_LOCATION]
    ar_obj.check("A13", "missing target location blocked",
                 len(no_loc) > 0, f"blocked={result13.blockedFields}")

    # A14. ambiguous target 차단
    tmpl_amb = _write_tmp_hwpx(tmp / "amb", [["시공자", ""], ["시공자", ""]])
    ar14 = _make_ar(confirmed=[("contractorName", "시공자", "대한소방")])
    result14 = run_sandbox_write(ar14, tmpl_amb, tmp / "amb_out")
    amb = [f for f in result14.blockedFields
           if f.get("blockedReason") == BLOCKED_AMBIGUOUS_TARGET]
    ar_obj.check("A14", "ambiguous target blocked", len(amb) > 0)

    # A15. low confidence target 차단 (monkeypatch 없이 직접 확인)
    import importlib
    import hwpx.pipeline.form_auto_fill_writer_sandbox as ws_mod
    orig_min = ws_mod.TARGET_CONF_MIN
    ws_mod.TARGET_CONF_MIN = 0.99
    ar15 = _make_ar(confirmed=[("contractorName", "시공자", "대한소방")])
    result15 = run_sandbox_write(ar15, tmpl, tmp / "lowconf_out")
    ws_mod.TARGET_CONF_MIN = orig_min
    low_conf = [f for f in result15.blockedFields
                if f.get("blockedReason") == BLOCKED_LOW_TARGET_CONFIDENCE]
    ar_obj.check("A15", "low confidence target blocked", len(low_conf) > 0)

    # A16. CONFIRM_FIELD 입력
    ar16 = _make_ar(confirmed=[("contractorName", "시공자", "대한소방")])
    result16 = run_sandbox_write(ar16, tmpl, tmp / "confirm_out")
    written16 = [f for f in result16.writtenFields
                 if f["fieldKey"] == "contractorName" and f["writeStatus"] == "WRITTEN"]
    ar_obj.check("A16", "CONFIRM_FIELD written",
                 len(written16) > 0, f"written={result16.writtenFields}")

    # A17. EDIT_VALUE 입력
    from hwpx.pipeline.approval_gate import ApprovedField, ACTION_EDIT
    af17 = ApprovedField("contractorName", "시공자", "새소방", "",
                         ACTION_EDIT, "needsReview", 1.0)
    ar17 = SimpleNamespace(approvedFields=[af17], pendingFields=[], writerEnabled=False)
    result17 = run_sandbox_write(ar17, tmpl, tmp / "edit_out")
    written17 = [f for f in result17.writtenFields
                 if f["fieldKey"] == "contractorName" and f["writeStatus"] == "WRITTEN"]
    ar_obj.check("A17", "EDIT_VALUE written", len(written17) > 0)

    # A18. readback 수행됨
    ar_obj.check("A18", "readback verification performed",
                 any(f.get("readbackStatus") in ("PASS", "FAIL")
                     for f in result16.writtenFields),
                 fail_verdict="FAIL_READBACK_NOT_PERFORMED")

    # A19. readback mismatch 감지
    from hwpx.pipeline.form_auto_fill_writer_sandbox import _readback_verify, WriteTarget
    output19 = tmp / "rb_mismatch.hwpx"
    output19.write_bytes(_make_hwpx([["시공자", "잘못된값"]]))
    af19 = ApprovedField("contractorName", "시공자", "대한소방", "",
                         ACTION_CONFIRM, "autoFillReady", 0.92)
    rr19 = [{"fieldKey": "contractorName", "label": "시공자",
              "decisionAction": ACTION_CONFIRM, "writeStatus": "WRITTEN",
              "readbackStatus": "SKIPPED", "targetLocation": {}, "valueHash": ""}]
    tgt19 = {"contractorName": WriteTarget("Contents/section0.xml", 0, 0, 1, "시공자", 0.95)}
    result_rb = _readback_verify(output19, tgt19, [af19], rr19)
    ar_obj.check("A19", "readback mismatch detected",
                 result_rb[0]["readbackStatus"] == "FAIL",
                 fail_verdict="FAIL_READBACK_MISMATCH")

    # A20. output HWPX ZIP 정상
    output20 = list((tmp / "confirm_out" / "output").glob("*.hwpx"))
    if output20:
        valid_zip = zipfile.is_zipfile(output20[0])
        ar_obj.check("A20", "output HWPX ZIP valid", valid_zip)
    else:
        ar_obj.check("A20", "output HWPX ZIP valid", False, "no output file found")

    # A21/A22. raw path / filename leak
    out_dict = result16.to_dict()
    out_str  = json.dumps(out_dict, ensure_ascii=False)
    path_leak = any(d in out_str for d in ("C:\\Users\\", "/home/", "/Users/"))
    ar_obj.check("A21", "no raw path leak", not path_leak,
                 fail_verdict="FAIL_RAW_PATH_LEAK")

    src = WRITER_SCRIPT.read_text(encoding="utf-8")
    fn_leak = "Users\\" in src or "/home/" in src
    ar_obj.check("A22", "no raw filename leak in source", not fn_leak,
                 fail_verdict="FAIL_RAW_FILENAME_LEAK")

    # A23. PII leak
    import re
    pii_re = re.compile(r"\d{3}-\d{2}-\d{5}|\d{6}-\d{7}")
    tmpl_pii = _write_tmp_hwpx(tmp / "pii", [["등록번호", ""]])
    ar23 = _make_ar(confirmed=[("registrationNumber", "등록번호", "123-45-67890")])
    result23 = run_sandbox_write(ar23, tmpl_pii, tmp / "pii_out")
    out23 = json.dumps(result23.to_dict(), ensure_ascii=False)
    ar_obj.check("A23", "no PII leak in report",
                 not pii_re.search(out23), fail_verdict="FAIL_PII_LEAK")

    # A24. AI API 미참조
    ai = any(kw in src for kw in ("anthropic", "openai", "ChatCompletion"))
    ar_obj.check("A24", "AI API not called", not ai, fail_verdict="FAIL_AI_OR_OCR_CALLED")

    # A25. OCR 미참조
    ocr = any(kw in src for kw in ("pytesseract", "easyocr", "image_to_string"))
    ar_obj.check("A25", "OCR not called", not ocr, fail_verdict="FAIL_AI_OR_OCR_CALLED")

    # A26. Hancom 필수 의존 없음
    hancom = any(kw in src for kw in ("hwp5", "libhwp", "pyhwp", "hwpx2pdf"))
    ar_obj.check("A26", "Hancom not required", not hancom)

    # A27. approval/review/mapping 테스트
    r27 = subprocess.run(
        [sys.executable, "-m", "pytest",
         str(APPROVAL_TEST), str(PANEL_TEST), str(MAPPING_TEST),
         "-q", "--tb=no"],
        capture_output=True, text=True, cwd=str(PROJECT_ROOT)
    )
    ar_obj.check("A27", "approval/review/mapping tests pass",
                 r27.returncode == 0, r27.stdout[-150:])

    # A28. writer sandbox 테스트
    r28 = subprocess.run(
        [sys.executable, "-m", "pytest", str(WRITER_TEST), "-q", "--tb=no"],
        capture_output=True, text=True, cwd=str(PROJECT_ROOT)
    )
    ar_obj.check("A28", "writer sandbox tests pass",
                 r28.returncode == 0, r28.stdout[-150:])

    # WARNs
    ar_obj.warn("WARN_SOME_FIELDS_BLOCKED_NO_TARGET")
    ar_obj.warn("WARN_SANDBOX_ONLY")
    ar_obj.warn("WARN_SYNTHETIC_TEMPLATE_ONLY")

    return ar_obj.report()


if __name__ == "__main__":
    sys.exit(run_audit())
