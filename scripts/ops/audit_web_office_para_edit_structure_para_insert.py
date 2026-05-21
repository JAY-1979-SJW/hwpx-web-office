"""WEB-OFFICE-PARA-EDIT-STRUCTURE-PARA-INSERT-01 준공검사 audit."""
from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

PR = Path(__file__).resolve().parents[2]
if str(PR) not in sys.path:
    sys.path.insert(0, str(PR))

AUDIT_ID = "STRUCTURE-PARA-INSERT-01"

REQUIRED_PY = [
    "scripts/hwpx/web_office/para_edit_model.py",
    "scripts/hwpx/web_office/paragraph_writer_adapter.py",
    "scripts/hwpx/web_office/paragraph_save_verify7.py",
]
REQUIRED_JS = [
    "frontend/web_office_viewer/para_edit_command.mjs",
    "frontend/web_office_viewer/para_edit_state.mjs",
    "frontend/web_office_viewer/para_edit_runtime.mjs",
    "frontend/web_office_viewer/para_edit_structure_smoke.mjs",
]
REQUIRED_TESTS = [
    "tests/test_web_office_para_edit_structure_para_insert.py",
]

JS_SMOKE = PR / "frontend/web_office_viewer/para_edit_structure_smoke.mjs"


def _find(code: str, level: str, detail: str) -> dict[str, Any]:
    return {"code": code, "level": level, "detail": detail}


def audit() -> dict[str, Any]:
    findings: list[dict] = []

    # 1. 필수 파일 존재
    for rel in REQUIRED_PY + REQUIRED_JS + REQUIRED_TESTS:
        if not (PR / rel).is_file():
            findings.append(_find("REQUIRED_FILE_MISSING", "FAIL", rel))

    # 2. CT_PARA_INSERT 선언 확인
    model_src = (PR / "scripts/hwpx/web_office/para_edit_model.py"
                 ).read_text(encoding="utf-8")
    if 'CT_PARA_INSERT = "PARA_INSERT"' not in model_src:
        findings.append(_find("CT_PARA_INSERT_MISSING_IN_MODEL", "FAIL",
                              "para_edit_model.py"))
    if '"PARA_INSERT"' not in (PR / "scripts/hwpx/web_office/"
                                      "paragraph_writer_adapter.py"
                               ).read_text(encoding="utf-8"):
        findings.append(_find("PARA_INSERT_NOT_IN_WRITER_ADAPTER", "FAIL",
                              "paragraph_writer_adapter.py"))

    # 3. V8 추가 확인
    v7_src = (PR / "scripts/hwpx/web_office/paragraph_save_verify7.py"
              ).read_text(encoding="utf-8")
    if "_verify_v8_para_struct_integrity" not in v7_src:
        findings.append(_find("V8_MISSING", "FAIL",
                              "paragraph_save_verify7.py"))

    # 4. JS smoke PASS
    r = subprocess.run(
        ["node", str(JS_SMOKE)],
        capture_output=True, text=True, timeout=30)
    if r.returncode != 0 or not r.stdout.strip():
        findings.append(_find("JS_SMOKE_ERROR", "FAIL", r.stderr[:200]))
    else:
        result = json.loads(r.stdout.strip())
        if result.get("verdict") != "PASS":
            failed = [k for k, v in result.get("checks", {}).items()
                      if not v.get("ok")]
            findings.append(_find("JS_SMOKE_FAIL", "FAIL",
                                  f"failed checks: {failed}"))

    # 5. Python 테스트 실행
    r2 = subprocess.run(
        [sys.executable, "-m", "pytest",
         "tests/test_web_office_para_edit_structure_para_insert.py",
         "-q", "--tb=short"],
        capture_output=True, text=True, timeout=60, cwd=str(PR))
    if r2.returncode != 0:
        findings.append(_find("PY_TEST_FAIL", "FAIL",
                              r2.stdout[-400:]))

    fails = [f for f in findings if f.get("level") == "FAIL"]
    verdict = "FAIL" if fails else "PASS"
    return {
        "audit": AUDIT_ID,
        "findings": findings,
        "verdict": verdict,
    }


if __name__ == "__main__":
    rep = audit()
    print(json.dumps(rep, ensure_ascii=False, indent=2))
