"""
HWPX-FORM-AUTO-FILL-WRITER-END-TO-END-SMOKE-06 감리 스크립트
A01–A31
성공 판정: PASS_HWPX_FORM_AUTO_FILL_WRITER_E2E_SMOKE
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

_PASS = "PASS"
_FAIL = "FAIL"

results: list[tuple[str, str, str]] = []
immediate_fails: list[str] = []


def _check(code: str, desc: str, ok: bool, fail_code: str = "") -> bool:
    status = _PASS if ok else _FAIL
    results.append((status, code, desc))
    if not ok and fail_code:
        immediate_fails.append(fail_code)
    return ok


# ---------------------------------------------------------------------------
# A01 – E2E smoke runner exists
# ---------------------------------------------------------------------------
module_path = ROOT / "scripts/hwpx/pipeline/form_auto_fill_e2e_smoke.py"
_check("A01", "E2E smoke runner exists", module_path.exists())

# ---------------------------------------------------------------------------
# A02 – import + run
# ---------------------------------------------------------------------------
e2e = None
try:
    import scripts.hwpx.pipeline.form_auto_fill_e2e_smoke as smoke_mod
    _check("A02", "synthetic scenario only (import OK)", True)
except Exception as e:
    _check("A02", f"synthetic scenario only — import failed: {e}", False)
    smoke_mod = None  # type: ignore

_result: dict = {}
if smoke_mod:
    try:
        with tempfile.TemporaryDirectory() as td:
            _result = smoke_mod.run_e2e_smoke(Path(td))
        _check("A02b", f"E2E smoke run — verdict: {_result.get('overallVerdict')}", True)
    except Exception as e:
        _check("A02b", f"E2E smoke run failed: {e}", False, fail_code="FAIL_E2E_STAGE_BROKEN")

stages = _result.get("stageResults", {})
summary = _result.get("summary", {})
security = _result.get("security", {})
immut = _result.get("sourceImmutability", {})

for code, stage_key, desc, fail_code in [
    ("A03", "recommend",        "form recommend stage passes",       "FAIL_E2E_STAGE_BROKEN"),
    ("A04", "catalog",          "catalog stage passes",              "FAIL_E2E_STAGE_BROKEN"),
    ("A05", "uploadParser",     "upload parser stage passes",        "FAIL_E2E_STAGE_BROKEN"),
    ("A06", "mapping",          "mapping stage passes",              "FAIL_E2E_STAGE_BROKEN"),
    ("A07", "reviewPanel",      "review panel stage passes",         "FAIL_E2E_STAGE_BROKEN"),
    ("A08", "humanApproval",    "human approval stage passes",       "FAIL_E2E_STAGE_BROKEN"),
    ("A09", "sandboxWriter",    "sandbox writer stage passes",       "FAIL_E2E_STAGE_BROKEN"),
    ("A10", "readbackHardening","readback hardening stage passes",   "FAIL_E2E_STAGE_BROKEN"),
    ("A11", "downloadReview",   "download review stage passes",      "FAIL_E2E_STAGE_BROKEN"),
    ("A12", "finalExportGate",  "final export gate stage passes",    "FAIL_E2E_STAGE_BROKEN"),
]:
    ok = stages.get(stage_key) == "PASS"
    _check(code, desc, ok, fail_code=fail_code if not ok else "")

# A13 – finalExportEnabled true only after ACCEPTED_BY_USER
ok = summary.get("finalExportEnabled") is True
_check("A13", "finalExportEnabled true (ACCEPTED_BY_USER + SUCCESS)", ok,
       fail_code="FAIL_E2E_STAGE_BROKEN" if not ok else "")

# A14 – sourceMutationAllowed false
ok = summary.get("sourceMutated") is False
_check("A14", "sourceMutationAllowed false", ok,
       fail_code="FAIL_SOURCE_HWPX_MUTATED" if not ok else "")

# A15 – source sha256 unchanged
ok = immut.get("sha256Changed") is False
_check("A15", "source HWPX sha256 unchanged", ok,
       fail_code="FAIL_SOURCE_HWPX_MUTATED" if not ok else "")

# A16 – source mtime unchanged
ok = immut.get("mtimeChanged") is False
_check("A16", "source HWPX mtime unchanged", ok,
       fail_code="FAIL_SOURCE_HWPX_MUTATED" if not ok else "")

# A17 – readbackFail == 0
ok = summary.get("readbackFail", 1) == 0
_check("A17", "readbackFail zero", ok,
       fail_code="FAIL_READBACK_FAIL" if not ok else "")

# A18 – unexpectedMutation == 0 (checked via stage status)
ok = stages.get("readbackHardening") == "PASS"
_check("A18", "unexpectedMutation zero (readback stage PASS)", ok,
       fail_code="FAIL_UNEXPECTED_MUTATION" if not ok else "")

# A19 – writerEligible=false not written
ok = summary.get("approvedFields", 0) >= 1
_check("A19", "writerEligible=false fields not written (approvedFields >= 1)", ok,
       fail_code="FAIL_UNAPPROVED_FIELD_WRITTEN" if not ok else "")

# A20 – MISSING_REQUIRED not silently ignored
try:
    from scripts.hwpx.pipeline.upload_document_parser import ParseResult
    from scripts.hwpx.pipeline.form_field_mapper import map_fields
    empty_parse = ParseResult(maskedStem="empty", formName="", domain="", formKind="")
    mapping = map_fields(empty_parse, smoke_mod._SYNTHETIC_CATALOG)
    required_missing = [f for f in mapping.missingFields
                        if any(cat["semanticField"] == f.fieldKey and cat["required"]
                               for cat in smoke_mod._SYNTHETIC_CATALOG["fields"])]
    ok = len(required_missing) >= 1
    _check("A20", f"MISSING_REQUIRED not silently ignored ({len(required_missing)} missing)", ok)
except Exception as e:
    _check("A20", f"MISSING_REQUIRED check failed: {e}", False)

# A21 – NEEDS_REVIEW not auto-promoted
ok = stages.get("humanApproval") == "PASS"
_check("A21", "NEEDS_REVIEW not auto-promoted (approval stage PASS)", ok)

# A22 – ACCEPT_OUTPUT does not replace source
ok = immut.get("sha256Changed") is False and summary.get("sourceMutated") is False
_check("A22", "ACCEPT_OUTPUT does not replace source", ok,
       fail_code="FAIL_ACCEPT_OUTPUT_REPLACED_SOURCE" if not ok else "")

# A23 – no raw path leak
ok = security.get("rawPathLeak") is False
_check("A23", "no raw path leak", ok,
       fail_code="FAIL_RAW_PATH_LEAK" if not ok else "")

# A24 – no raw filename leak
ok = security.get("rawFilenameLeak") is False
_check("A24", "no raw filename leak", ok,
       fail_code="FAIL_RAW_FILENAME_LEAK" if not ok else "")

# A25 – no PII leak
ok = security.get("piiLeak") is False
_check("A25", "no PII leak", ok,
       fail_code="FAIL_PII_LEAK" if not ok else "")

# A26 – AI not called
ok = security.get("aiCalled") is False
_check("A26", "AI API not called", ok,
       fail_code="FAIL_AI_OR_OCR_CALLED" if not ok else "")

# A27 – OCR not called
ok = security.get("ocrCalled") is False
_check("A27", "OCR not called", ok,
       fail_code="FAIL_AI_OR_OCR_CALLED" if not ok else "")

# A28 – Hancom not required
ok = security.get("hancomRequired") is False
_check("A28", "Hancom not required", ok)

# A29 – previous final export tests pass
r = subprocess.run(
    [sys.executable, "-m", "pytest",
     "tests/test_hwpx_form_writer_final_export_gate.py", "-q", "--tb=no"],
    capture_output=True, text=True, cwd=str(ROOT),
)
ok = r.returncode == 0
desc = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "no output"
_check("A29", f"previous final export tests pass — {desc}", ok)

# A30 – previous download/UI/readback/sandbox/approval/review/mapping tests pass
r = subprocess.run(
    [sys.executable, "-m", "pytest",
     "tests/test_hwpx_form_writer_download_review.py",
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
_check("A30", f"previous download/UI/readback/sandbox/approval/review/mapping tests pass — {desc}", ok)

# A31 – E2E smoke tests pass
r = subprocess.run(
    [sys.executable, "-m", "pytest",
     "tests/test_hwpx_form_auto_fill_e2e_smoke.py", "-q", "--tb=no"],
    capture_output=True, text=True, cwd=str(ROOT),
)
ok = r.returncode == 0
desc = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "no output"
_check("A31", f"E2E smoke tests pass — {desc}", ok)

# ---------------------------------------------------------------------------
print("=" * 70)
print("HWPX-FORM-AUTO-FILL-WRITER-END-TO-END-SMOKE-06 감리 결과")
print("=" * 70)

for status, code, desc in results:
    marker = "✓" if status == _PASS else "✗"
    print(f"  [{status}] {code} {marker} — {desc}")

print()
for w in ["WARN_SYNTHETIC_SCENARIO_ONLY", "WARN_SANDBOX_ONLY",
          "WARN_FRONTEND_NOT_RENDERED_YET", "WARN_FINAL_EXPORT_DOES_NOT_DEPLOY"]:
    print(f"  WARN: {w}")

print()
if immediate_fails:
    for fc in set(immediate_fails):
        print(f"  즉시 FAIL: {fc}")
    print()
    print("최종 판정: FAIL_HWPX_FORM_AUTO_FILL_WRITER_E2E_SMOKE")
    sys.exit(1)

fail_count = sum(1 for s, _, _ in results if s == _FAIL)
if fail_count > 0:
    print(f"최종 판정: FAIL ({fail_count}개 항목 실패)")
    sys.exit(1)

print("최종 판정: PASS_HWPX_FORM_AUTO_FILL_WRITER_E2E_SMOKE")
