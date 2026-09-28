"""
HWPX-FORM-AUTO-FILL-WRITER-DOWNLOAD-AND-USER-REVIEW-04 감리 스크립트
A01–A24
성공 판정: PASS_HWPX_FORM_AUTO_FILL_WRITER_DOWNLOAD_AND_USER_REVIEW
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
_WARN = "WARN"

results: list[tuple[str, str, str]] = []
immediate_fails: list[str] = []

_PII_RE = re.compile(r"\d{6}-\d{7}|\d{3}-\d{2}-\d{5}")


def _check(code: str, desc: str, ok: bool, fail_code: str = "", warn: bool = False) -> bool:
    status = _PASS if ok else (_WARN if warn else _FAIL)
    results.append((status, code, desc))
    if not ok and fail_code and not warn:
        immediate_fails.append(fail_code)
    return ok


# ---------------------------------------------------------------------------
# A01 – module exists
# ---------------------------------------------------------------------------
module_path = ROOT / "scripts/hwpx/pipeline/form_writer_download_review.py"
_check("A01", "download review module exists", module_path.exists())

# ---------------------------------------------------------------------------
# A02 – import
# ---------------------------------------------------------------------------
try:
    import scripts.hwpx.pipeline.form_writer_download_review as dr
    _check("A02", "writer UI result input supported", True)
except Exception:
    _check("A02", "writer UI result input supported", False)
    dr = None  # type: ignore

if dr:
    def _ui(status="SUCCESS", rf=0, mutated=False, fid="out_001", oh="abc123def456"):
        return {
            "writerStatus": status,
            "summary": {"written": 2, "blocked": 0, "readbackPass": 2 - rf,
                        "readbackFail": rf, "sourceMutated": mutated},
            "output": {"outputFileId": fid, "outputHash": oh, "downloadEnabled": True},
            "fieldResults": [], "warnings": [],
            "security": {"sourceMutationAllowed": False, "rawPathVisible": False,
                         "rawFilenameVisible": False, "piiMasked": True},
        }

    def _dd(action="ACCEPT_OUTPUT"):
        return {"formId": "f", "outputFileId": "out_001", "action": action,
                "decisionBy": "user", "reason": "감리"}

    # A03 – SUCCESS enables download
    try:
        p = dr.build_download_payload(_ui())
        ok = p["download"]["downloadEnabled"] is True
        _check("A03", "SUCCESS enables download", ok,
               fail_code="FAIL_DOWNLOAD_ENABLED_ON_FAILED_READBACK" if not ok else "")
    except Exception:
        _check("A03", "SUCCESS enables download", False)

    # A04 – readbackFail disables download
    try:
        p = dr.build_download_payload(_ui(rf=1))
        ok = p["download"]["downloadEnabled"] is False
        _check("A04", "readbackFail disables download", ok,
               fail_code="FAIL_DOWNLOAD_ENABLED_ON_FAILED_READBACK" if not ok else "")
    except Exception:
        _check("A04", "readbackFail disables download", False,
               fail_code="FAIL_DOWNLOAD_ENABLED_ON_FAILED_READBACK")

    # A05 – sourceMutated disables download
    try:
        p = dr.build_download_payload(_ui(mutated=True))
        ok = p["download"]["downloadEnabled"] is False
        _check("A05", "sourceMutated disables download", ok,
               fail_code="FAIL_DOWNLOAD_ENABLED_ON_SOURCE_MUTATION" if not ok else "")
    except Exception:
        _check("A05", "sourceMutated disables download", False,
               fail_code="FAIL_DOWNLOAD_ENABLED_ON_SOURCE_MUTATION")

    # A06 – failed writer status disables download
    try:
        p = dr.build_download_payload(_ui(status="FAILED_READBACK"))
        ok = p["download"]["downloadEnabled"] is False
        _check("A06", "failed writer status disables download", ok,
               fail_code="FAIL_DOWNLOAD_ENABLED_ON_FAILED_READBACK" if not ok else "")
    except Exception:
        _check("A06", "failed writer status disables download", False,
               fail_code="FAIL_DOWNLOAD_ENABLED_ON_FAILED_READBACK")

    # A07 – outputHash required
    try:
        p = dr.build_download_payload(_ui(oh=""))
        ok = p["download"]["downloadEnabled"] is False
        _check("A07", "outputHash required", ok)
    except Exception:
        _check("A07", "outputHash required", False)

    # A08 – outputFileId required
    try:
        p = dr.build_download_payload(_ui(fid=""))
        ok = p["download"]["downloadEnabled"] is False
        _check("A08", "outputFileId required", ok)
    except Exception:
        _check("A08", "outputFileId required", False)

    # A09 – output_path == source_path rejected
    try:
        same = "same_hash_val_x01"
        p = dr.build_download_payload(_ui(fid=same), source_template_hash=same)
        ok = p["download"]["downloadEnabled"] is False
        _check("A09", "output_path == source_path rejected", ok,
               fail_code="FAIL_DOWNLOAD_ENABLED_ON_FAILED_READBACK" if not ok else "")
    except Exception:
        _check("A09", "output_path == source_path rejected", False)

    # A10 – raw path not exposed
    try:
        p = dr.build_download_payload(_ui())
        ok = "C:\\" not in str(p) and "/home/" not in str(p)
        _check("A10", "raw path not exposed", ok,
               fail_code="FAIL_RAW_PATH_LEAK" if not ok else "")
    except Exception:
        _check("A10", "raw path not exposed", False, fail_code="FAIL_RAW_PATH_LEAK")

    # A11 – raw filename not exposed
    try:
        ok = p["security"]["rawFilenameVisible"] is False
        _check("A11", "raw filename not exposed", ok,
               fail_code="FAIL_RAW_FILENAME_LEAK" if not ok else "")
    except Exception:
        _check("A11", "raw filename not exposed", False, fail_code="FAIL_RAW_FILENAME_LEAK")

    # A12 – PII not exposed
    try:
        ui_pii = _ui()
        ui_pii["fieldResults"] = [{"value": "870101-1234567"}]
        p = dr.build_download_payload(ui_pii)
        ok = not _PII_RE.search(str(p))
        _check("A12", "PII not exposed", ok,
               fail_code="FAIL_PII_LEAK" if not ok else "")
    except Exception:
        _check("A12", "PII not exposed", False, fail_code="FAIL_PII_LEAK")

    # A13 – ACCEPT_OUTPUT supported
    try:
        p = dr.build_download_payload(_ui())
        r = dr.apply_review_decision_from_dict(p, _dd("ACCEPT_OUTPUT"))
        ok = r["decisionResult"] == dr.DECISION_ACCEPTED
        _check("A13", "ACCEPT_OUTPUT supported", ok)
    except Exception:
        _check("A13", "ACCEPT_OUTPUT supported", False)

    # A14 – REJECT_OUTPUT supported
    try:
        p = dr.build_download_payload(_ui())
        r = dr.apply_review_decision_from_dict(p, _dd("REJECT_OUTPUT"))
        ok = r["decisionResult"] == dr.DECISION_REJECTED
        _check("A14", "REJECT_OUTPUT supported", ok)
    except Exception:
        _check("A14", "REJECT_OUTPUT supported", False)

    # A15 – REQUEST_REWRITE supported
    try:
        p = dr.build_download_payload(_ui())
        r = dr.apply_review_decision_from_dict(p, _dd("REQUEST_REWRITE"))
        ok = r["decisionResult"] == dr.DECISION_REWRITE
        _check("A15", "REQUEST_REWRITE supported", ok)
    except Exception:
        _check("A15", "REQUEST_REWRITE supported", False)

    # A16 – HOLD_REVIEW supported
    try:
        p = dr.build_download_payload(_ui())
        r = dr.apply_review_decision_from_dict(p, _dd("HOLD_REVIEW"))
        ok = r["decisionResult"] == dr.DECISION_HOLD
        _check("A16", "HOLD_REVIEW supported", ok)
    except Exception:
        _check("A16", "HOLD_REVIEW supported", False)

    # A17 – ACCEPT_OUTPUT does not mutate source
    try:
        p = dr.build_download_payload(_ui())
        r = dr.apply_review_decision_from_dict(p, _dd("ACCEPT_OUTPUT"))
        ok = r["sourceMutated"] is False and r["operationalDeployment"] is False
        ok2 = r["security"]["sourceMutationAllowed"] is False
        _check("A17", "ACCEPT_OUTPUT does not mutate source", ok and ok2,
               fail_code="FAIL_ACCEPT_MUTATES_SOURCE" if not (ok and ok2) else "")
    except Exception:
        _check("A17", "ACCEPT_OUTPUT does not mutate source", False,
               fail_code="FAIL_ACCEPT_MUTATES_SOURCE")

    # A18 – sourceMutationAllowed false
    try:
        p = dr.build_download_payload(_ui())
        ok = p["security"]["sourceMutationAllowed"] is False
        _check("A18", "sourceMutationAllowed false", ok)
    except Exception:
        _check("A18", "sourceMutationAllowed false", False)

    # A19 – AI API not called
    try:
        src = inspect.getsource(dr)
        ok = "openai" not in src and "anthropic" not in src
        _check("A19", "AI API not called", ok,
               fail_code="FAIL_AI_OR_OCR_CALLED" if not ok else "")
    except Exception:
        _check("A19", "AI API not called", False, fail_code="FAIL_AI_OR_OCR_CALLED")

    # A20 – OCR not called
    try:
        src = inspect.getsource(dr)
        ok = "pytesseract" not in src and "easyocr" not in src.lower()
        _check("A20", "OCR not called", ok,
               fail_code="FAIL_AI_OR_OCR_CALLED" if not ok else "")
    except Exception:
        _check("A20", "OCR not called", False, fail_code="FAIL_AI_OR_OCR_CALLED")

    # A21 – Hancom not required
    try:
        src = inspect.getsource(dr)
        ok = "hwp5" not in src and "pyhwp" not in src and "HwpCtrl" not in src
        _check("A21", "Hancom not required", ok)
    except Exception:
        _check("A21", "Hancom not required", False)

else:
    for code, desc in [
        ("A03", "SUCCESS enables download"), ("A04", "readbackFail disables download"),
        ("A05", "sourceMutated disables download"), ("A06", "failed writer status disables download"),
        ("A07", "outputHash required"), ("A08", "outputFileId required"),
        ("A09", "output_path == source_path rejected"), ("A10", "raw path not exposed"),
        ("A11", "raw filename not exposed"), ("A12", "PII not exposed"),
        ("A13", "ACCEPT_OUTPUT supported"), ("A14", "REJECT_OUTPUT supported"),
        ("A15", "REQUEST_REWRITE supported"), ("A16", "HOLD_REVIEW supported"),
        ("A17", "ACCEPT_OUTPUT does not mutate source"), ("A18", "sourceMutationAllowed false"),
        ("A19", "AI API not called"), ("A20", "OCR not called"), ("A21", "Hancom not required"),
    ]:
        _check(code, desc, False)

# A22 – previous UI connect tests pass
r = subprocess.run(
    [sys.executable, "-m", "pytest",
     "tests/test_hwpx_form_writer_ui_connect.py", "-q", "--tb=no"],
    capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(ROOT),
)
ok = r.returncode == 0
desc = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "no output"
_check("A22", f"previous UI connect tests pass — {desc}", ok)

# A23 – readback/sandbox/approval/review/mapping tests pass
r = subprocess.run(
    [sys.executable, "-m", "pytest",
     "tests/test_hwpx_form_writer_readback_hardening.py",
     "tests/test_hwpx_form_auto_fill_writer_sandbox.py",
     "tests/test_hwpx_approval_gate.py",
     "tests/test_hwpx_review_panel.py",
     "tests/test_hwpx_form_field_mapping.py",
     "-q", "--tb=no"],
    capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(ROOT),
)
ok = r.returncode == 0
desc = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "no output"
_check("A23", f"previous readback/sandbox/approval/review/mapping tests pass — {desc}", ok)

# A24 – download review tests pass
r = subprocess.run(
    [sys.executable, "-m", "pytest",
     "tests/test_hwpx_form_writer_download_review.py", "-q", "--tb=no"],
    capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(ROOT),
)
ok = r.returncode == 0
desc = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "no output"
_check("A24", f"download review tests pass — {desc}", ok)

# ---------------------------------------------------------------------------
# 결과 출력
# ---------------------------------------------------------------------------
print("=" * 70)
print("HWPX-FORM-AUTO-FILL-WRITER-DOWNLOAD-AND-USER-REVIEW-04 감리 결과")
print("=" * 70)

for status, code, desc in results:
    marker = "✓" if status == _PASS else ("△" if status == _WARN else "✗")
    print(f"  [{status}] {code} {marker} — {desc}")

print()
for w in ["WARN_SANDBOX_ONLY", "WARN_DOWNLOAD_PAYLOAD_ONLY",
          "WARN_FRONTEND_NOT_RENDERED_YET", "WARN_USER_ACCEPT_DOES_NOT_DEPLOY"]:
    print(f"  WARN: {w}")

print()
if immediate_fails:
    for fc in set(immediate_fails):
        print(f"  즉시 FAIL: {fc}")
    print()
    print("최종 판정: FAIL_HWPX_FORM_AUTO_FILL_WRITER_DOWNLOAD_AND_USER_REVIEW")
    sys.exit(1)

fail_count = sum(1 for s, _, _ in results if s == _FAIL)
if fail_count > 0:
    print(f"최종 판정: FAIL ({fail_count}개 항목 실패)")
    sys.exit(1)

print("최종 판정: PASS_HWPX_FORM_AUTO_FILL_WRITER_DOWNLOAD_AND_USER_REVIEW")
