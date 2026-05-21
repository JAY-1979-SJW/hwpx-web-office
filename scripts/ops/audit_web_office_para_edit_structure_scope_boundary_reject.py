"""WEB-OFFICE-PARA-EDIT-STRUCTURE-SCOPE-BOUNDARY-REJECT-01 준공검사.

body paragraph (kind=="block") 외 scope에서 PARA_INSERT / PARA_DELETE가
명시적 reason code로 reject되는지 정적·동적 검증.
baseline: 3464f1f
"""
from __future__ import annotations
import json
import re
import subprocess
import sys
from pathlib import Path

PR = Path(__file__).resolve().parents[2]
if str(PR) not in sys.path:
    sys.path.insert(0, str(PR))

BASELINE_COMMIT = "3464f1f"

SCOPE_REASON_VALUES = [
    "HEADER_SCOPE_NOT_SUPPORTED",
    "FOOTER_SCOPE_NOT_SUPPORTED",
    "FOOTNOTE_SCOPE_NOT_SUPPORTED",
    "ENDNOTE_SCOPE_NOT_SUPPORTED",
    "CAPTION_SCOPE_NOT_SUPPORTED",
    "BODY_SCOPE_ONLY_SUPPORTED",
]

REQUIRED_SMOKE_CHECKS = [
    "headerScopeInsertReject",
    "footerScopeInsertReject",
    "captionScopeInsertReject",
    "headerScopeDeleteReject",
    "footerScopeDeleteReject",
    "unknownScopeDeleteReject",
]

LOCKED_FILES_VS_BASELINE = [
    "frontend/web_office_viewer/para_edit_command.mjs",
    "frontend/web_office_viewer/para_edit_runtime.mjs",
    "scripts/hwpx/web_office/paragraph_save_pipeline.py",
    "scripts/hwpx/web_office/para_edit_e2e_pipeline.py",
    "scripts/hwpx/web_office/charpr_inventory.py",
    "scripts/hwpx/web_office/render_payload.py",
]

FORBIDDEN_PATTERNS = [
    (r"_apply_para_delete_cell\b",          "table cell merge 구현 금지"),
    (r"TABLE_CELL_MERGE",                   "table cell merge 금지 심볼"),
    (r"def\s+create_char_pr\b",             "신규 charPr 생성 금지"),
    (r'package\.entries\["header\.xml"\]\s*=', "header.xml write 금지"),
    (r"activateHeaderEdit",                 "header 편집 활성화 금지"),
    (r"enableHeaderScope",                  "header scope 활성화 금지"),
]
FORBIDDEN_SCAN_TARGETS = [
    "scripts/hwpx/web_office/paragraph_writer_adapter.py",
    "scripts/hwpx/web_office/para_edit_model.py",
    "frontend/web_office_viewer/para_edit_state.mjs",
]


def _check_model_constants() -> list[dict]:
    findings: list[dict] = []
    path = PR / "scripts/hwpx/web_office/para_edit_model.py"
    if not path.is_file():
        findings.append({"code": "MISSING_FILE", "level": "FAIL",
                         "detail": str(path.relative_to(PR))})
        return findings
    src = path.read_text(encoding="utf-8")
    for val in SCOPE_REASON_VALUES:
        if val not in src:
            findings.append({"code": "REASON_CONSTANT_MISSING",
                             "level": "FAIL", "detail": val})
    return findings


def _check_js_helper() -> list[dict]:
    findings: list[dict] = []
    path = PR / "frontend/web_office_viewer/para_edit_state.mjs"
    src = path.read_text(encoding="utf-8")
    if "_scopeBoundaryRejectReason" not in src:
        findings.append({"code": "SCOPE_HELPER_MISSING", "level": "FAIL",
                         "detail": "_scopeBoundaryRejectReason"})
    for val in SCOPE_REASON_VALUES:
        if val not in src:
            findings.append({"code": "JS_REASON_MISSING",
                             "level": "FAIL", "detail": val})
    return findings


def _check_forbidden_patterns() -> list[dict]:
    findings: list[dict] = []
    for rel in FORBIDDEN_SCAN_TARGETS:
        path = PR / rel
        if not path.is_file():
            continue
        src = path.read_text(encoding="utf-8")
        for pat, reason in FORBIDDEN_PATTERNS:
            if re.search(pat, src):
                findings.append({"code": "FORBIDDEN_PATTERN_FOUND",
                                 "level": "FAIL",
                                 "detail": f"{path.name}: {reason}"})
    return findings


def _check_locked_files() -> list[dict]:
    findings: list[dict] = []
    for rel in LOCKED_FILES_VS_BASELINE:
        r = subprocess.run(
            ["git", "diff", BASELINE_COMMIT, "--", rel],
            capture_output=True, text=True, cwd=str(PR), timeout=20)
        if r.returncode != 0 or r.stdout.strip():
            findings.append({"code": "LOCKED_FILE_CHANGED",
                             "level": "FAIL", "detail": rel})
    return findings


def _check_staged_zero() -> list[dict]:
    findings: list[dict] = []
    r = subprocess.run(["git", "diff", "--cached", "--name-only"],
                       capture_output=True, text=True, cwd=str(PR), timeout=10)
    hwpx_staged = [
        f for f in r.stdout.strip().splitlines()
        if any(f.startswith(p) for p in (
            "frontend/web_office_viewer/", "scripts/hwpx/web_office/",
            "tests/test_web_office_", "scripts/ops/audit_web_office_",
            "docs/architecture/web_office_",
        ))
    ]
    if hwpx_staged:
        findings.append({"code": "HWPX_STAGED_FILES_PRESENT",
                         "level": "FAIL", "detail": hwpx_staged})
    return findings


def _check_js_smoke() -> list[dict]:
    findings: list[dict] = []
    smoke = PR / "frontend/web_office_viewer/para_edit_structure_smoke.mjs"
    r = subprocess.run(["node", str(smoke)],
                       capture_output=True, text=True, timeout=30)
    try:
        out = json.loads(r.stdout.strip().split("\n")[-1])
        if out.get("verdict") != "PASS":
            findings.append({"code": "JS_SMOKE_FAIL", "level": "FAIL",
                             "detail": out})
        checks = out.get("checks", {})
        for name in REQUIRED_SMOKE_CHECKS:
            if not checks.get(name, {}).get("ok"):
                findings.append({"code": "SMOKE_CHECK_FAIL",
                                 "level": "FAIL", "detail": name})
    except Exception as e:
        findings.append({"code": "JS_SMOKE_ERROR", "level": "FAIL",
                         "detail": str(e)})
    return findings


def _check_python_tests() -> list[dict]:
    findings: list[dict] = []
    r = subprocess.run(
        [sys.executable, "-m", "pytest",
         "tests/test_web_office_para_edit_structure_para_insert.py",
         "tests/test_web_office_para_edit_structure_para_delete.py",
         "-q", "--tb=short"],
        capture_output=True, text=True, cwd=str(PR), timeout=60)
    if r.returncode != 0:
        findings.append({"code": "PYTHON_TESTS_FAIL", "level": "FAIL",
                         "detail": r.stdout[-2000:]})
    return findings


def audit() -> dict:
    all_findings: list[dict] = []
    all_findings += _check_model_constants()
    all_findings += _check_js_helper()
    all_findings += _check_forbidden_patterns()
    all_findings += _check_locked_files()
    all_findings += _check_staged_zero()
    all_findings += _check_js_smoke()
    all_findings += _check_python_tests()

    verdict = "PASS" if not all_findings else "FAIL"
    return {
        "audit": "WEB-OFFICE-PARA-EDIT-STRUCTURE-SCOPE-BOUNDARY-REJECT-01",
        "baseline": BASELINE_COMMIT,
        "verdict": verdict,
        "findings": all_findings,
    }


if __name__ == "__main__":
    import json as _json
    print(_json.dumps(audit(), indent=2, ensure_ascii=False))
