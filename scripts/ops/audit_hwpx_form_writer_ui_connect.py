"""
HWPX-FORM-AUTO-FILL-WRITER-UI-CONNECT-03 감리 스크립트
A01–A25
성공 판정: PASS_HWPX_FORM_AUTO_FILL_WRITER_UI_CONNECT
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent

_PASS = "PASS"
_FAIL = "FAIL"
_WARN = "WARN"

results: list[tuple[str, str, str]] = []
immediate_fails: list[str] = []


def _check(code: str, desc: str, ok: bool, fail_code: str = "", warn: bool = False) -> bool:
    status = _PASS if ok else (_WARN if warn else _FAIL)
    results.append((status, code, desc))
    if not ok and fail_code and not warn:
        immediate_fails.append(fail_code)
    return ok


# ---------------------------------------------------------------------------
# A01 – module exists
# ---------------------------------------------------------------------------
module_path = ROOT / "scripts/hwpx/pipeline/form_writer_ui_connect.py"
_check("A01", "UI connect module exists", module_path.exists())

# ---------------------------------------------------------------------------
# A02 – import and approval gate result supported
# ---------------------------------------------------------------------------
try:
    sys.path.insert(0, str(ROOT))
    import scripts.hwpx.pipeline.form_writer_ui_connect as uc
    _check("A02", "approval gate result input supported", True)
except Exception:
    _check("A02", "approval gate result input supported", False)
    uc = None  # type: ignore

if uc:
    def _ap_ready(n=3):
        return {
            "writerEnabled": False,
            "approvedFields": [
                {"fieldKey": f"f{i}", "label": f"L{i}", "value": f"V{i}", "writerEligible": True}
                for i in range(n)
            ],
            "pendingFields": [],
            "summary": {"approvedFields": n, "pendingFields": 0, "undecidedCount": 0, "missingRequired": 0},
        }

    def _sandbox_res(written=2, readback_fail=0, mutated=False):
        return {
            "sourceMutated": mutated,
            "outputHash": "abc123",
            "outputPathMasked": "masked001",
            "writtenFields": [{"fieldKey": f"f{i}", "valueHash": "h" * 16} for i in range(written)],
            "blockedFields": [],
            "warnings": [],
            "summary": {"approvedFields": written, "written": written, "blocked": 0,
                        "readbackPass": written - readback_fail, "readbackFail": readback_fail},
        }

    # A03 – READY_FOR_WRITER enables button
    try:
        p = uc.build_ui_connect_payload(_ap_ready())
        ok = p["approvalStatus"] == uc.STATUS_READY and p["button"]["enabled"] is True
        _check("A03", "READY_FOR_WRITER enables button", ok,
               fail_code="FAIL_WRITER_ENABLED_WITHOUT_APPROVAL" if not ok else "")
    except Exception:
        _check("A03", "READY_FOR_WRITER enables button", False)

    # A04 – blocked statuses disable button
    try:
        ap_block = _ap_ready()
        ap_block["summary"]["undecidedCount"] = 1
        p = uc.build_ui_connect_payload(ap_block)
        ok = p["button"]["enabled"] is False
        _check("A04", "blocked statuses disable button", ok)
    except Exception:
        _check("A04", "blocked statuses disable button", False)

    # A05 – missing required disables button
    try:
        ap_miss = _ap_ready()
        ap_miss["summary"]["missingRequired"] = 1
        p = uc.build_ui_connect_payload(ap_miss)
        ok = p["button"]["enabled"] is False
        _check("A05", "missing required disables button", ok)
    except Exception:
        _check("A05", "missing required disables button", False)

    # A06 – needs review disables button
    try:
        ap_rev = _ap_ready()
        ap_rev["summary"]["undecidedCount"] = 2
        p = uc.build_ui_connect_payload(ap_rev)
        ok = p["button"]["enabled"] is False
        _check("A06", "needs review disables button", ok)
    except Exception:
        _check("A06", "needs review disables button", False)

    # A07 – attachment missing disables button
    try:
        ap_att = _ap_ready()
        ap_att["pendingFields"].append({"fieldKey": "fa", "action": "REQUEST_ATTACHMENT"})
        p = uc.build_ui_connect_payload(ap_att)
        ok = p["button"]["enabled"] is False
        _check("A07", "attachment missing disables button", ok)
    except Exception:
        _check("A07", "attachment missing disables button", False)

    # A08 – writerEligible false leaves count=0
    try:
        with tempfile.TemporaryDirectory() as td:
            tpath = Path(td) / "t.hwpx"
            tpath.write_bytes(b"PK\x03\x04")
            ap_noelig = _ap_ready()
            for f in ap_noelig["approvedFields"]:
                f["writerEligible"] = False
            req = uc.build_sandbox_write_request(ap_noelig, tpath, Path(td) / "out")
            ok = req.get("eligibleFieldCount", -1) == 0
        _check("A08", "writerEligible false disables write", ok)
    except Exception:
        _check("A08", "writerEligible false disables write", False)

    # A09 – SANDBOX_ONLY mode enforced
    try:
        p = uc.build_ui_connect_payload(_ap_ready())
        ok = p["button"]["mode"] == "SANDBOX_ONLY"
        _check("A09", "SANDBOX_ONLY mode enforced", ok,
               fail_code="FAIL_OPERATION_MODE_NOT_SANDBOX" if not ok else "")
    except Exception:
        _check("A09", "SANDBOX_ONLY mode enforced", False, fail_code="FAIL_OPERATION_MODE_NOT_SANDBOX")

    # A10 – sourceMutationAllowed false
    try:
        p = uc.build_ui_connect_payload(_ap_ready())
        ok = p["security"]["sourceMutationAllowed"] is False
        _check("A10", "sourceMutationAllowed false", ok,
               fail_code="FAIL_SOURCE_MUTATION_ALLOWED" if not ok else "")
    except Exception:
        _check("A10", "sourceMutationAllowed false", False, fail_code="FAIL_SOURCE_MUTATION_ALLOWED")

    # A11 – output_path == source_path rejected
    try:
        with tempfile.TemporaryDirectory() as td:
            tpath = Path(td) / "t.hwpx"
            tpath.write_bytes(b"PK\x03\x04")
            raised = False
            try:
                uc.build_sandbox_write_request(_ap_ready(), tpath, Path(td))
            except ValueError:
                raised = True
        _check("A11", "output_path == source_path rejected", raised,
               fail_code="FAIL_OUTPUT_EQUALS_SOURCE_ALLOWED" if not raised else "")
    except Exception:
        _check("A11", "output_path == source_path rejected", False,
               fail_code="FAIL_OUTPUT_EQUALS_SOURCE_ALLOWED")

    # A12 – sandbox writer request payload generated
    try:
        with tempfile.TemporaryDirectory() as td:
            tpath = Path(td) / "t.hwpx"
            tpath.write_bytes(b"PK\x03\x04")
            req = uc.build_sandbox_write_request(_ap_ready(3), tpath, Path(td) / "out")
            ok = req.get("allowed") is True and req.get("mode") == "SANDBOX_ONLY"
        _check("A12", "sandbox writer request payload generated", ok)
    except Exception:
        _check("A12", "sandbox writer request payload generated", False)

    # A13 – writer result payload generated
    try:
        result = uc.build_ui_result_payload(_sandbox_res())
        ok = result.get("schemaVersion") == uc.SCHEMA_VERSION_RESULT
        _check("A13", "writer result payload generated", ok)
    except Exception:
        _check("A13", "writer result payload generated", False)

    # A14 – readback fail shown as failure
    try:
        result = uc.build_ui_result_payload(
            _sandbox_res(readback_fail=1),
            {"overallVerdict": "FAIL_READBACK_MISMATCH", "sourceMutated": False,
             "outputHash": "", "fieldResults": [], "warnings": [],
             "summary": {"writtenFields": 1, "readbackPass": 0, "normalizedMatch": 0,
                         "readbackFail": 1, "unexpectedMutation": 0}},
        )
        ok = result["writerStatus"] == uc.WRITER_FAILED_READBACK
        ok2 = result["output"]["downloadEnabled"] is False
        _check("A14", "readback fail shown as failure", ok and ok2,
               fail_code="FAIL_READBACK_FAIL_SHOWN_SUCCESS" if not (ok and ok2) else "")
    except Exception:
        _check("A14", "readback fail shown as failure", False,
               fail_code="FAIL_READBACK_FAIL_SHOWN_SUCCESS")

    # A15 – source mutation shown as failure
    try:
        result = uc.build_ui_result_payload(_sandbox_res(mutated=True))
        ok = result["writerStatus"] == uc.WRITER_FAILED_MUTATED
        _check("A15", "source mutation shown as failure", ok)
    except Exception:
        _check("A15", "source mutation shown as failure", False)

    # A16 – output broken shown as failure
    try:
        result = uc.build_ui_result_payload(
            _sandbox_res(),
            {"overallVerdict": "FAIL_OUTPUT_HWPX_BROKEN", "sourceMutated": False,
             "outputHash": "", "fieldResults": [], "warnings": [],
             "summary": {"writtenFields": 1, "readbackPass": 0, "normalizedMatch": 0,
                         "readbackFail": 0, "unexpectedMutation": 0}},
        )
        ok = result["writerStatus"] == uc.WRITER_FAILED_BROKEN
        _check("A16", "output broken shown as failure", ok)
    except Exception:
        _check("A16", "output broken shown as failure", False)

    # A17 – no raw path leak
    try:
        with tempfile.TemporaryDirectory() as td:
            tpath = Path(td) / "secret_form.hwpx"
            tpath.write_bytes(b"PK\x03\x04")
            req = uc.build_sandbox_write_request(_ap_ready(), tpath, Path(td) / "out")
            ok = str(tpath) not in str(req)
        _check("A17", "no raw path leak", ok,
               fail_code="FAIL_RAW_PATH_LEAK" if not ok else "")
    except Exception:
        _check("A17", "no raw path leak", False, fail_code="FAIL_RAW_PATH_LEAK")

    # A18 – no raw filename leak
    try:
        with tempfile.TemporaryDirectory() as td:
            tpath = Path(td) / "소방완공검사신청서_2024.hwpx"
            tpath.write_bytes(b"PK\x03\x04")
            req = uc.build_sandbox_write_request(_ap_ready(), tpath, Path(td) / "out")
            ok = "소방완공검사신청서_2024.hwpx" not in str(req)
        _check("A18", "no raw filename leak", ok,
               fail_code="FAIL_RAW_FILENAME_LEAK" if not ok else "")
    except Exception:
        _check("A18", "no raw filename leak", False, fail_code="FAIL_RAW_FILENAME_LEAK")

    # A19 – no PII leak
    import re as _re
    _PII_RE = _re.compile(r"\d{6}-\d{7}|\d{3}-\d{2}-\d{5}")
    try:
        sb = _sandbox_res()
        sb["writtenFields"][0]["value"] = "870101-1234567"
        result = uc.build_ui_result_payload(sb)
        ok = not _PII_RE.search(str(result))
        _check("A19", "no PII leak", ok,
               fail_code="FAIL_PII_LEAK" if not ok else "")
    except Exception:
        _check("A19", "no PII leak", False, fail_code="FAIL_PII_LEAK")

    # A20 – AI API not called
    try:
        import inspect
        src = inspect.getsource(uc)
        ok = "openai" not in src and "anthropic" not in src
        _check("A20", "AI API not called", ok,
               fail_code="FAIL_AI_OR_OCR_CALLED" if not ok else "")
    except Exception:
        _check("A20", "AI API not called", False, fail_code="FAIL_AI_OR_OCR_CALLED")

    # A21 – OCR not called
    try:
        src = inspect.getsource(uc)
        ok = "pytesseract" not in src and "easyocr" not in src.lower()
        _check("A21", "OCR not called", ok,
               fail_code="FAIL_AI_OR_OCR_CALLED" if not ok else "")
    except Exception:
        _check("A21", "OCR not called", False, fail_code="FAIL_AI_OR_OCR_CALLED")

    # A22 – Hancom not required
    try:
        src = inspect.getsource(uc)
        ok = "hwp5" not in src and "pyhwp" not in src and "HwpCtrl" not in src
        _check("A22", "Hancom not required", ok)
    except Exception:
        _check("A22", "Hancom not required", False)

else:
    for code, desc in [
        ("A03", "READY_FOR_WRITER enables button"),
        ("A04", "blocked statuses disable button"),
        ("A05", "missing required disables button"),
        ("A06", "needs review disables button"),
        ("A07", "attachment missing disables button"),
        ("A08", "writerEligible false disables write"),
        ("A09", "SANDBOX_ONLY mode enforced"),
        ("A10", "sourceMutationAllowed false"),
        ("A11", "output_path == source_path rejected"),
        ("A12", "sandbox writer request payload generated"),
        ("A13", "writer result payload generated"),
        ("A14", "readback fail shown as failure"),
        ("A15", "source mutation shown as failure"),
        ("A16", "output broken shown as failure"),
        ("A17", "no raw path leak"),
        ("A18", "no raw filename leak"),
        ("A19", "no PII leak"),
        ("A20", "AI API not called"),
        ("A21", "OCR not called"),
        ("A22", "Hancom not required"),
    ]:
        _check(code, desc, False)

# A23 – previous readback tests pass
r = subprocess.run(
    [sys.executable, "-m", "pytest",
     "tests/test_hwpx_form_writer_readback_hardening.py", "-q", "--tb=no"],
    capture_output=True, text=True, cwd=str(ROOT),
)
ok = r.returncode == 0
desc = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "no output"
_check("A23", f"previous readback tests pass — {desc}", ok)

# A24 – previous sandbox writer tests pass
r = subprocess.run(
    [sys.executable, "-m", "pytest",
     "tests/test_hwpx_form_auto_fill_writer_sandbox.py", "-q", "--tb=no"],
    capture_output=True, text=True, cwd=str(ROOT),
)
ok = r.returncode == 0
desc = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "no output"
_check("A24", f"previous sandbox writer tests pass — {desc}", ok)

# A25 – previous approval/review/mapping tests pass
r = subprocess.run(
    [sys.executable, "-m", "pytest",
     "tests/test_hwpx_approval_gate.py",
     "tests/test_hwpx_review_panel.py",
     "tests/test_hwpx_form_field_mapping.py",
     "-q", "--tb=no"],
    capture_output=True, text=True, cwd=str(ROOT),
)
ok = r.returncode == 0
desc = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "no output"
_check("A25", f"previous approval/review/mapping tests pass — {desc}", ok)

# ---------------------------------------------------------------------------
# 결과 출력
# ---------------------------------------------------------------------------
print("=" * 70)
print("HWPX-FORM-AUTO-FILL-WRITER-UI-CONNECT-03 감리 결과")
print("=" * 70)

warns: list[str] = []
for status, code, desc in results:
    marker = "✓" if status == _PASS else ("△" if status == _WARN else "✗")
    print(f"  [{status}] {code} {marker} — {desc}")
    if status == _WARN:
        warns.append(desc)

print()
for w in ["WARN_SANDBOX_ONLY", "WARN_UI_PAYLOAD_ONLY", "WARN_FRONTEND_NOT_RENDERED_YET"]:
    print(f"  WARN: {w}")

print()
if immediate_fails:
    for fc in set(immediate_fails):
        print(f"  즉시 FAIL: {fc}")
    print()
    print("최종 판정: FAIL_HWPX_FORM_AUTO_FILL_WRITER_UI_CONNECT")
    sys.exit(1)

fail_count = sum(1 for s, _, _ in results if s == _FAIL)
if fail_count > 0:
    print(f"최종 판정: FAIL ({fail_count}개 항목 실패)")
    sys.exit(1)

print("최종 판정: PASS_HWPX_FORM_AUTO_FILL_WRITER_UI_CONNECT")
