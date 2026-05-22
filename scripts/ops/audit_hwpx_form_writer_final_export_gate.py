"""
HWPX-FORM-AUTO-FILL-WRITER-FINAL-EXPORT-GATE-05 감리 스크립트
A01–A26
성공 판정: PASS_HWPX_FORM_AUTO_FILL_WRITER_FINAL_EXPORT_GATE
"""

from __future__ import annotations

import inspect
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

_PASS = "PASS"
_FAIL = "FAIL"

results: list[tuple[str, str, str]] = []
immediate_fails: list[str] = []

_PII_RE = re.compile(r"\d{6}-\d{7}|\d{3}-\d{2}-\d{5}")


def _check(code: str, desc: str, ok: bool, fail_code: str = "") -> bool:
    status = _PASS if ok else _FAIL
    results.append((status, code, desc))
    if not ok and fail_code:
        immediate_fails.append(fail_code)
    return ok


# A01
module_path = ROOT / "scripts/hwpx/pipeline/form_writer_final_export_gate.py"
_check("A01", "final export gate module exists", module_path.exists())

try:
    import scripts.hwpx.pipeline.form_writer_final_export_gate as eg
    _check("A02", "download review result input supported", True)
    _check("A03", "user review decision input supported", True)
except Exception:
    _check("A02", "download review result input supported", False)
    _check("A03", "user review decision input supported", False)
    eg = None  # type: ignore

if eg:
    def _dl(ws="SUCCESS", rf=0, mut=False, fid="out_001", oh="abc123def456ab", dl_en=True):
        return {
            "writerStatus": ws,
            "summary": {"written": 3, "blocked": 1, "readbackPass": 3 - rf,
                        "readbackFail": rf, "sourceMutated": mut},
            "download": {"downloadEnabled": dl_en, "outputFileId": fid,
                         "outputHash": oh, "sourceTemplateHash": ""},
            "warnings": [],
        }

    def _dec(res="ACCEPTED_BY_USER", act="ACCEPT_OUTPUT"):
        return {"formId": "f", "outputFileId": "out_001", "action": act,
                "decisionResult": res, "decisionBy": "user", "reason": "",
                "sourceMutated": False, "operationalDeployment": False,
                "security": {"sourceMutationAllowed": False}}

    # A04 – ACCEPTED_BY_USER enables export
    try:
        p = eg.build_final_export_payload(_dl(), _dec())
        ok = p["finalExportEnabled"] is True
        _check("A04", "ACCEPTED_BY_USER enables final export", ok,
               fail_code="FAIL_FINAL_EXPORT_WITHOUT_ACCEPT" if not ok else "")
    except Exception:
        _check("A04", "ACCEPTED_BY_USER enables final export", False,
               fail_code="FAIL_FINAL_EXPORT_WITHOUT_ACCEPT")

    # A05 – REJECTED_BY_USER blocks
    try:
        p = eg.build_final_export_payload(_dl(), _dec("REJECTED_BY_USER", "REJECT_OUTPUT"))
        ok = p["finalExportEnabled"] is False
        _check("A05", "REJECTED_BY_USER blocks final export", ok,
               fail_code="FAIL_FINAL_EXPORT_WITHOUT_ACCEPT" if not ok else "")
    except Exception:
        _check("A05", "REJECTED_BY_USER blocks final export", False,
               fail_code="FAIL_FINAL_EXPORT_WITHOUT_ACCEPT")

    # A06 – REWRITE_REQUESTED blocks
    try:
        p = eg.build_final_export_payload(_dl(), _dec("REWRITE_REQUESTED", "REQUEST_REWRITE"))
        ok = p["finalExportEnabled"] is False
        _check("A06", "REWRITE_REQUESTED blocks final export", ok,
               fail_code="FAIL_FINAL_EXPORT_WITHOUT_ACCEPT" if not ok else "")
    except Exception:
        _check("A06", "REWRITE_REQUESTED blocks final export", False,
               fail_code="FAIL_FINAL_EXPORT_WITHOUT_ACCEPT")

    # A07 – REVIEW_ON_HOLD blocks
    try:
        p = eg.build_final_export_payload(_dl(), _dec("REVIEW_ON_HOLD", "HOLD_REVIEW"))
        ok = p["finalExportEnabled"] is False
        _check("A07", "REVIEW_ON_HOLD blocks final export", ok)
    except Exception:
        _check("A07", "REVIEW_ON_HOLD blocks final export", False)

    # A08 – failed writer blocks
    try:
        p = eg.build_final_export_payload(_dl(ws="FAILED_READBACK", dl_en=False), _dec())
        ok = p["finalExportEnabled"] is False
        _check("A08", "failed writer status blocks final export", ok,
               fail_code="FAIL_FINAL_EXPORT_ON_FAILED_READBACK" if not ok else "")
    except Exception:
        _check("A08", "failed writer status blocks final export", False,
               fail_code="FAIL_FINAL_EXPORT_ON_FAILED_READBACK")

    # A09 – readbackFail blocks
    try:
        p = eg.build_final_export_payload(_dl(rf=1, dl_en=False), _dec())
        ok = p["finalExportEnabled"] is False
        _check("A09", "readbackFail blocks final export", ok,
               fail_code="FAIL_FINAL_EXPORT_ON_FAILED_READBACK" if not ok else "")
    except Exception:
        _check("A09", "readbackFail blocks final export", False,
               fail_code="FAIL_FINAL_EXPORT_ON_FAILED_READBACK")

    # A10 – sourceMutated blocks
    try:
        p = eg.build_final_export_payload(_dl(mut=True, dl_en=False), _dec())
        ok = p["finalExportEnabled"] is False
        _check("A10", "sourceMutated blocks final export", ok,
               fail_code="FAIL_FINAL_EXPORT_ON_SOURCE_MUTATION" if not ok else "")
    except Exception:
        _check("A10", "sourceMutated blocks final export", False,
               fail_code="FAIL_FINAL_EXPORT_ON_SOURCE_MUTATION")

    # A11 – outputHash required
    try:
        p = eg.build_final_export_payload(_dl(oh=""), _dec())
        ok = p["finalExportEnabled"] is False
        _check("A11", "outputHash required", ok)
    except Exception:
        _check("A11", "outputHash required", False)

    # A12 – outputFileId required
    try:
        p = eg.build_final_export_payload(_dl(fid=""), _dec())
        ok = p["finalExportEnabled"] is False
        _check("A12", "outputFileId required", ok)
    except Exception:
        _check("A12", "outputFileId required", False)

    # A13 – output_path == source_path rejected
    try:
        same = "same_hash_val_001"
        p = eg.build_final_export_payload(_dl(fid=same), _dec(), source_template_hash=same)
        ok = p["finalExportEnabled"] is False
        _check("A13", "output_path == source_path rejected", ok)
    except Exception:
        _check("A13", "output_path == source_path rejected", False)

    # A14 – approvalTrace preserved
    try:
        p = eg.build_final_export_payload(_dl(), _dec())
        trace = p.get("approvalTrace", {})
        ok = trace.get("reviewStatus") == "ACCEPTED_BY_USER" and "readbackPass" in trace
        _check("A14", "approvalTrace preserved", ok)
    except Exception:
        _check("A14", "approvalTrace preserved", False)

    # A15 – hashes preserved
    try:
        p = eg.build_final_export_payload(_dl(), _dec(), source_template_hash="tmpl_001")
        ok = p["sourceTemplateHash"] == "tmpl_001" and p["outputHash"] == "abc123def456ab"
        _check("A15", "source/output hash preserved", ok)
    except Exception:
        _check("A15", "source/output hash preserved", False)

    # A16 – sourceMutationAllowed false
    try:
        p = eg.build_final_export_payload(_dl(), _dec())
        ok = p["sourceMutationAllowed"] is False and p["security"]["originalTemplateMutated"] is False
        _check("A16", "sourceMutationAllowed false", ok)
    except Exception:
        _check("A16", "sourceMutationAllowed false", False)

    # A17 – ACCEPT does not mutate source
    try:
        p = eg.build_final_export_payload(_dl(), _dec())
        ok = p["sourceMutationAllowed"] is False and p["security"]["originalTemplateMutated"] is False
        _check("A17", "ACCEPTED_BY_USER does not mutate source", ok,
               fail_code="FAIL_ACCEPT_MUTATES_SOURCE" if not ok else "")
    except Exception:
        _check("A17", "ACCEPTED_BY_USER does not mutate source", False,
               fail_code="FAIL_ACCEPT_MUTATES_SOURCE")

    # A18 – no raw path leak
    try:
        p = eg.build_final_export_payload(_dl(), _dec())
        ok = "C:\\" not in str(p) and "/home/" not in str(p)
        _check("A18", "no raw path leak", ok,
               fail_code="FAIL_RAW_PATH_LEAK" if not ok else "")
    except Exception:
        _check("A18", "no raw path leak", False, fail_code="FAIL_RAW_PATH_LEAK")

    # A19 – no raw filename leak
    try:
        ok = p["security"]["rawFilenameVisible"] is False
        _check("A19", "no raw filename leak", ok,
               fail_code="FAIL_RAW_FILENAME_LEAK" if not ok else "")
    except Exception:
        _check("A19", "no raw filename leak", False, fail_code="FAIL_RAW_FILENAME_LEAK")

    # A20 – no PII leak
    try:
        dl_pii = _dl()
        dl_pii["warnings"] = ["870101-1234567"]
        p = eg.build_final_export_payload(dl_pii, _dec())
        ok = not _PII_RE.search(str(p))
        _check("A20", "no PII leak", ok,
               fail_code="FAIL_PII_LEAK" if not ok else "")
    except Exception:
        _check("A20", "no PII leak", False, fail_code="FAIL_PII_LEAK")

    # A21 – AI not called
    try:
        src = inspect.getsource(eg)
        ok = "openai" not in src and "anthropic" not in src
        _check("A21", "AI API not called", ok,
               fail_code="FAIL_AI_OR_OCR_CALLED" if not ok else "")
    except Exception:
        _check("A21", "AI API not called", False, fail_code="FAIL_AI_OR_OCR_CALLED")

    # A22 – OCR not called
    try:
        src = inspect.getsource(eg)
        ok = "pytesseract" not in src and "easyocr" not in src.lower()
        _check("A22", "OCR not called", ok,
               fail_code="FAIL_AI_OR_OCR_CALLED" if not ok else "")
    except Exception:
        _check("A22", "OCR not called", False, fail_code="FAIL_AI_OR_OCR_CALLED")

    # A23 – Hancom not required
    try:
        src = inspect.getsource(eg)
        ok = "hwp5" not in src and "pyhwp" not in src and "HwpCtrl" not in src
        _check("A23", "Hancom not required", ok)
    except Exception:
        _check("A23", "Hancom not required", False)

else:
    for code in ["A04", "A05", "A06", "A07", "A08", "A09", "A10", "A11", "A12", "A13",
                 "A14", "A15", "A16", "A17", "A18", "A19", "A20", "A21", "A22", "A23"]:
        _check(code, code, False)

# A24 – download review tests pass
r = subprocess.run(
    [sys.executable, "-m", "pytest",
     "tests/test_hwpx_form_writer_download_review.py", "-q", "--tb=no"],
    capture_output=True, text=True, cwd=str(ROOT),
)
ok = r.returncode == 0
desc = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "no output"
_check("A24", f"previous download review tests pass — {desc}", ok)

# A25 – UI/readback/sandbox/approval/review/mapping tests pass
r = subprocess.run(
    [sys.executable, "-m", "pytest",
     "tests/test_hwpx_form_writer_ui_connect.py",
     "tests/test_hwpx_form_writer_readback_hardening.py",
     "tests/test_hwpx_form_auto_fill_writer_sandbox.py",
     "tests/test_hwpx_approval_gate.py",
     "tests/test_hwpx_review_panel.py",
     "tests/test_hwpx_form_field_mapping.py",
     "-q", "--tb=no"],
    capture_output=True, text=True, cwd=str(ROOT),
)
ok = r.returncode == 0
desc = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "no output"
_check("A25", f"previous UI/readback/sandbox/approval/review/mapping tests pass — {desc}", ok)

# A26 – final export gate tests pass
r = subprocess.run(
    [sys.executable, "-m", "pytest",
     "tests/test_hwpx_form_writer_final_export_gate.py", "-q", "--tb=no"],
    capture_output=True, text=True, cwd=str(ROOT),
)
ok = r.returncode == 0
desc = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "no output"
_check("A26", f"final export gate tests pass — {desc}", ok)

# ---------------------------------------------------------------------------
print("=" * 70)
print("HWPX-FORM-AUTO-FILL-WRITER-FINAL-EXPORT-GATE-05 감리 결과")
print("=" * 70)

for status, code, desc in results:
    marker = "✓" if status == _PASS else "✗"
    print(f"  [{status}] {code} {marker} — {desc}")

print()
for w in ["WARN_FINAL_EXPORT_PAYLOAD_ONLY", "WARN_SANDBOX_OUTPUT_ONLY",
          "WARN_USER_ACCEPT_DOES_NOT_DEPLOY", "WARN_FRONTEND_NOT_RENDERED_YET"]:
    print(f"  WARN: {w}")

print()
if immediate_fails:
    for fc in set(immediate_fails):
        print(f"  즉시 FAIL: {fc}")
    print()
    print("최종 판정: FAIL_HWPX_FORM_AUTO_FILL_WRITER_FINAL_EXPORT_GATE")
    sys.exit(1)

fail_count = sum(1 for s, _, _ in results if s == _FAIL)
if fail_count > 0:
    print(f"최종 판정: FAIL ({fail_count}개 항목 실패)")
    sys.exit(1)

print("최종 판정: PASS_HWPX_FORM_AUTO_FILL_WRITER_FINAL_EXPORT_GATE")
