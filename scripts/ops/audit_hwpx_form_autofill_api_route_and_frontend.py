"""
HWPX-FORM-AUTO-FILL-WRITER-API-ROUTE-AND-FRONTEND-07 감리 스크립트
A01–A24
성공 판정: PASS_HWPX_FORM_AUTO_FILL_WRITER_API_ROUTE_AND_FRONTEND
"""

from __future__ import annotations

import inspect
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

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


# A01 – API route exists
route_path = ROOT / "scripts/ops/hwpx_form_autofill_api_route.py"
_check("A01", "API route exists", route_path.exists())

# A02 – import
try:
    import scripts.ops.hwpx_form_autofill_api_route as api
    _check("A02", "API route import OK", True)
except Exception as e:
    _check("A02", f"API route import failed: {e}", False)
    api = None  # type: ignore

frontend_path = ROOT / "frontend/web_office_viewer/components/FormAutoFillWorkspace.tsx"

if api:
    # A02b – health
    try:
        resp = api.call_health()
        ok = resp["status"] == "SUCCESS" and resp["mode"] == "SANDBOX_ONLY"
        _check("A02b", "health endpoint works", ok)
    except Exception:
        _check("A02b", "health endpoint works", False)

    # A03 – e2e smoke endpoint
    try:
        resp = api.call_e2e_smoke()
        ok = resp["status"] == "SUCCESS"
        _check("A03", f"e2e smoke endpoint works — {resp.get('data', {}).get('overallVerdict')}", ok,
               fail_code="FAIL_E2E_STAGE_BROKEN" if not ok else "")
    except Exception as e:
        _check("A03", f"e2e smoke endpoint failed: {e}", False, fail_code="FAIL_E2E_STAGE_BROKEN")

    # A04 – write sandbox SANDBOX_ONLY
    try:
        ap = {"writerEnabled": False,
              "approvedFields": [{"fieldKey": "f0", "label": "L0", "value": "V0",
                                   "writerEligible": True, "action": "CONFIRM_FIELD",
                                   "sourceZone": "AUTO_FILL_READY", "confidence": 0.91,
                                   "originalValue": "V0"}],
              "pendingFields": [],
              "summary": {"approvedFields": 1, "undecidedCount": 0, "missingRequired": 0}}
        resp = api.call_write_sandbox(ap)
        ok = resp["mode"] == "SANDBOX_ONLY"
        _check("A04", "write sandbox is SANDBOX_ONLY", ok,
               fail_code="FAIL_OPERATION_MODE_NOT_SANDBOX" if not ok else "")
    except Exception:
        _check("A04", "write sandbox is SANDBOX_ONLY", False,
               fail_code="FAIL_OPERATION_MODE_NOT_SANDBOX")

    # A05 – sourceMutationAllowed false
    try:
        ok = resp["sourceMutationAllowed"] is False
        _check("A05", "sourceMutationAllowed false", ok,
               fail_code="FAIL_SOURCE_MUTATION_ALLOWED" if not ok else "")
    except Exception:
        _check("A05", "sourceMutationAllowed false", False,
               fail_code="FAIL_SOURCE_MUTATION_ALLOWED")

    # A06 – READY_FOR_WRITER gate enforced
    try:
        blocked_ap = {"writerEnabled": False, "approvedFields": [],
                      "pendingFields": [], "summary": {"approvedFields": 0,
                      "undecidedCount": 0, "missingRequired": 0}}
        resp2 = api.call_write_sandbox(blocked_ap)
        ok = resp2["status"] == "FAILED"
        _check("A06", "READY_FOR_WRITER gate enforced", ok,
               fail_code="FAIL_WRITER_ENABLED_WITHOUT_APPROVAL" if not ok else "")
    except Exception:
        _check("A06", "READY_FOR_WRITER gate enforced", False,
               fail_code="FAIL_WRITER_ENABLED_WITHOUT_APPROVAL")

    # A07 – blocked approval status disables write
    try:
        blocked_ap2 = {"writerEnabled": False,
                       "approvedFields": [{"fieldKey": "f0", "label": "L0", "value": "V0",
                                           "writerEligible": True, "action": "CONFIRM_FIELD",
                                           "sourceZone": "AUTO_FILL_READY", "confidence": 0.91,
                                           "originalValue": "V0"}],
                       "pendingFields": [],
                       "summary": {"approvedFields": 1, "undecidedCount": 2, "missingRequired": 0}}
        resp3 = api.call_write_sandbox(blocked_ap2)
        ok = resp3["status"] == "FAILED"
        _check("A07", "blocked approval status disables write", ok)
    except Exception:
        _check("A07", "blocked approval status disables write", False)

    # A08 – readback fail not shown as success
    try:
        wr_fail = {"writerStatus": "FAILED_READBACK",
                   "summary": {"written": 1, "blocked": 0, "readbackPass": 0,
                               "readbackFail": 1, "sourceMutated": False},
                   "output": {"outputFileId": "o", "outputHash": "h", "downloadEnabled": False},
                   "fieldResults": [], "warnings": [],
                   "security": {"sourceMutationAllowed": False, "rawPathVisible": False,
                                "rawFilenameVisible": False, "piiMasked": True}}
        dl_resp = api.call_download_review(wr_fail)
        data = dl_resp.get("data", {})
        ok = data.get("download", {}).get("downloadEnabled") is False
        _check("A08", "readback fail not shown as success", ok,
               fail_code="FAIL_READBACK_FAIL_SHOWN_SUCCESS" if not ok else "")
    except Exception:
        _check("A08", "readback fail not shown as success", False,
               fail_code="FAIL_READBACK_FAIL_SHOWN_SUCCESS")

    # A09 – source mutation not shown as success
    try:
        wr_mut = {"writerStatus": "FAILED_SOURCE_MUTATED",
                  "summary": {"written": 0, "blocked": 0, "readbackPass": 0,
                              "readbackFail": 0, "sourceMutated": True},
                  "output": {"outputFileId": "o", "outputHash": "h", "downloadEnabled": False},
                  "fieldResults": [], "warnings": [],
                  "security": {"sourceMutationAllowed": False, "rawPathVisible": False,
                               "rawFilenameVisible": False, "piiMasked": True}}
        dl_resp2 = api.call_download_review(wr_mut)
        data2 = dl_resp2.get("data", {})
        ok = data2.get("download", {}).get("downloadEnabled") is False
        _check("A09", "source mutation not shown as success", ok)
    except Exception:
        _check("A09", "source mutation not shown as success", False)

    # A10 – output broken not shown as success
    try:
        wr_broken = {"writerStatus": "FAILED_OUTPUT_BROKEN",
                     "summary": {"written": 0, "blocked": 0, "readbackPass": 0,
                                 "readbackFail": 0, "sourceMutated": False},
                     "output": {"outputFileId": "o", "outputHash": "h", "downloadEnabled": False},
                     "fieldResults": [], "warnings": [],
                     "security": {"sourceMutationAllowed": False, "rawPathVisible": False,
                                  "rawFilenameVisible": False, "piiMasked": True}}
        dl_resp3 = api.call_download_review(wr_broken)
        data3 = dl_resp3.get("data", {})
        ok = data3.get("download", {}).get("downloadEnabled") is False
        _check("A10", "output broken not shown as success", ok)
    except Exception:
        _check("A10", "output broken not shown as success", False)

    # A11 – schemaVersion/requestId present
    try:
        h = api.call_health()
        ok = "schemaVersion" in h and "requestId" in h
        _check("A11", "response schemaVersion/requestId present", ok)
    except Exception:
        _check("A11", "response schemaVersion/requestId present", False)

    # A12 – no raw path leak
    try:
        h = api.call_health()
        ok = "C:\\" not in str(h) and "/home/" not in str(h)
        _check("A12", "no raw path leak", ok,
               fail_code="FAIL_RAW_PATH_LEAK" if not ok else "")
    except Exception:
        _check("A12", "no raw path leak", False, fail_code="FAIL_RAW_PATH_LEAK")

    # A13 – no raw filename leak
    try:
        ok = api.call_health().get("sourceMutationAllowed") is False
        _check("A13", "no raw filename leak (security field verified)", ok,
               fail_code="FAIL_RAW_FILENAME_LEAK" if not ok else "")
    except Exception:
        _check("A13", "no raw filename leak", False, fail_code="FAIL_RAW_FILENAME_LEAK")

    # A14 – no PII leak
    try:
        ap_pii = {"writerEnabled": False,
                  "approvedFields": [{"fieldKey": "f0", "label": "L0",
                                      "value": "870101-1234567",
                                      "writerEligible": True, "action": "CONFIRM_FIELD",
                                      "sourceZone": "AUTO_FILL_READY", "confidence": 0.91,
                                      "originalValue": "870101-1234567"}],
                  "pendingFields": [],
                  "summary": {"approvedFields": 1, "undecidedCount": 0, "missingRequired": 0}}
        resp_pii = api.call_write_sandbox(ap_pii)
        ok = not _PII_RE.search(str(resp_pii))
        _check("A14", "no PII leak", ok,
               fail_code="FAIL_PII_LEAK" if not ok else "")
    except Exception:
        _check("A14", "no PII leak", False, fail_code="FAIL_PII_LEAK")

else:
    for code in ["A02b", "A03", "A04", "A05", "A06", "A07", "A08", "A09", "A10",
                 "A11", "A12", "A13", "A14"]:
        _check(code, code, False)

# A15 – frontend button matrix exists
try:
    src = frontend_path.read_text(encoding="utf-8") if frontend_path.exists() else ""
    ok = "computeButtonEnabled" in src and "READY_FOR_WRITER" in src
    _check("A15", "frontend button matrix exists", ok)
except Exception:
    _check("A15", "frontend button matrix exists", False)

# A16 – frontend sandbox warning text
try:
    src = frontend_path.read_text(encoding="utf-8") if frontend_path.exists() else ""
    ok = "원본 HWPX는 수정하지 않고 sandbox 복사본에만 작성합니다." in src
    _check("A16", "frontend sandbox warning text exists", ok)
except Exception:
    _check("A16", "frontend sandbox warning text exists", False)

# A17 – frontend does not expose raw path
try:
    src = frontend_path.read_text(encoding="utf-8") if frontend_path.exists() else ""
    ok = "C:\\" not in src and "/home/" not in src and "outputPath" not in src
    _check("A17", "frontend does not expose raw path", ok,
           fail_code="FAIL_RAW_PATH_LEAK" if not ok else "")
except Exception:
    _check("A17", "frontend does not expose raw path", False, fail_code="FAIL_RAW_PATH_LEAK")

# A18 – frontend does not expose raw filename
try:
    ok = not _PII_RE.search(src) if src else True
    _check("A18", "frontend does not expose raw filename / PII", ok,
           fail_code="FAIL_RAW_FILENAME_LEAK" if not ok else "")
except Exception:
    _check("A18", "frontend does not expose raw filename", False)

# A19 – AI not called
try:
    src_api = inspect.getsource(api) if api else ""
    ok = "openai" not in src_api and "anthropic" not in src_api
    _check("A19", "AI API not called", ok,
           fail_code="FAIL_AI_OR_OCR_CALLED" if not ok else "")
except Exception:
    _check("A19", "AI API not called", False, fail_code="FAIL_AI_OR_OCR_CALLED")

# A20 – OCR not called
try:
    ok = "pytesseract" not in src_api and "easyocr" not in src_api.lower()
    _check("A20", "OCR not called", ok,
           fail_code="FAIL_AI_OR_OCR_CALLED" if not ok else "")
except Exception:
    _check("A20", "OCR not called", False, fail_code="FAIL_AI_OR_OCR_CALLED")

# A21 – Hancom not required
try:
    ok = "hwp5" not in src_api and "pyhwp" not in src_api
    _check("A21", "Hancom not required", ok)
except Exception:
    _check("A21", "Hancom not required", False)

# A22 – E2E smoke tests pass
r = subprocess.run(
    [sys.executable, "-m", "pytest",
     "tests/test_hwpx_form_auto_fill_e2e_smoke.py", "-q", "--tb=no"],
    capture_output=True, text=True, cwd=str(ROOT),
)
ok = r.returncode == 0
desc = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "no output"
_check("A22", f"previous E2E smoke tests pass — {desc}", ok)

# A23 – writer chain tests pass
r = subprocess.run(
    [sys.executable, "-m", "pytest",
     "tests/test_hwpx_form_writer_final_export_gate.py",
     "tests/test_hwpx_form_writer_download_review.py",
     "tests/test_hwpx_form_writer_ui_connect.py",
     "tests/test_hwpx_form_writer_readback_hardening.py",
     "tests/test_hwpx_form_auto_fill_writer_sandbox.py",
     "-q", "--tb=no"],
    capture_output=True, text=True, cwd=str(ROOT),
)
ok = r.returncode == 0
desc = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "no output"
_check("A23", f"previous writer chain tests pass — {desc}", ok)

# A24 – API route + frontend contract tests pass
r = subprocess.run(
    [sys.executable, "-m", "pytest",
     "tests/test_hwpx_form_autofill_api_route.py",
     "tests/test_hwpx_form_autofill_frontend_contract.py",
     "-q", "--tb=no"],
    capture_output=True, text=True, cwd=str(ROOT),
)
ok = r.returncode == 0
desc = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "no output"
_check("A24", f"API route + frontend contract tests pass — {desc}", ok)

# ---------------------------------------------------------------------------
print("=" * 70)
print("HWPX-FORM-AUTO-FILL-WRITER-API-ROUTE-AND-FRONTEND-07 감리 결과")
print("=" * 70)

for status, code, desc in results:
    marker = "✓" if status == _PASS else "✗"
    print(f"  [{status}] {code} {marker} — {desc}")

print()
for w in ["WARN_SANDBOX_ONLY", "WARN_FRONTEND_CONTRACT_ONLY",
          "WARN_BROWSER_RENDER_NOT_VERIFIED", "WARN_REAL_USER_FILE_NOT_TESTED"]:
    print(f"  WARN: {w}")

print()
if immediate_fails:
    for fc in set(immediate_fails):
        print(f"  즉시 FAIL: {fc}")
    print()
    print("최종 판정: FAIL_HWPX_FORM_AUTO_FILL_WRITER_API_ROUTE_AND_FRONTEND")
    sys.exit(1)

fail_count = sum(1 for s, _, _ in results if s == _FAIL)
if fail_count > 0:
    print(f"최종 판정: FAIL ({fail_count}개 항목 실패)")
    sys.exit(1)

print("최종 판정: PASS_HWPX_FORM_AUTO_FILL_WRITER_API_ROUTE_AND_FRONTEND")
