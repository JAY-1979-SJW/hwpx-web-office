"""WEB-OFFICE-PARA-EDIT-STRUCTURE-PARA-DELETE-01 준공검사 audit.

baseline: 66f5870
"""

import json
import subprocess
import sys
from pathlib import Path

PR = Path(__file__).resolve().parents[2]
if str(PR) not in sys.path:
    sys.path.insert(0, str(PR))

BASELINE_COMMIT = "66f5870"

REQUIRED_FILES = [
    "frontend/web_office_viewer/para_edit_command.mjs",
    "frontend/web_office_viewer/para_edit_state.mjs",
    "frontend/web_office_viewer/para_edit_runtime.mjs",
    "frontend/web_office_viewer/para_edit_structure_smoke.mjs",
    "scripts/hwpx/web_office/para_edit_model.py",
    "scripts/hwpx/web_office/paragraph_writer_adapter.py",
    "scripts/hwpx/web_office/paragraph_save_verify7.py",
]

LOCKED_FILES_VS_BASELINE = [
    # PARA_DELETE 공정에서 수정 불필요한 자재
    "scripts/hwpx/web_office/paragraph_save_pipeline.py",
    "scripts/hwpx/web_office/para_edit_e2e_pipeline.py",
    "scripts/hwpx/web_office/charpr_inventory.py",
    "scripts/hwpx/web_office/render_payload.py",
    "frontend/web_office_viewer/components/WebOfficeFormatToolbar.tsx",
    "frontend/web_office_viewer/format_charpr_matcher.mjs",
]


def _check_required_files() -> list[dict]:
    findings = []
    for rel in REQUIRED_FILES:
        if not (PR / rel).exists():
            findings.append({"code": "REQUIRED_FILE_MISSING", "file": rel, "level": "FAIL"})
    return findings


def _check_model_constants(model_src: str) -> list[dict]:
    findings = []
    if 'CT_PARA_DELETE = "PARA_DELETE"' not in model_src:
        findings.append({"code": "CT_PARA_DELETE_MISSING", "level": "FAIL"})
    if "CT_PARA_DELETE" not in model_src.split("PARA_COMMAND_TYPES")[1][:200]:
        findings.append({"code": "CT_PARA_DELETE_NOT_IN_PARA_COMMAND_TYPES", "level": "FAIL"})
    if "make_para_delete_command" not in model_src:
        findings.append({"code": "MAKE_PARA_DELETE_COMMAND_MISSING", "level": "FAIL"})
    return findings


def _check_adapter_support(adapter_src: str) -> list[dict]:
    findings = []
    if '"PARA_DELETE"' not in adapter_src:
        findings.append({"code": "PARA_DELETE_NOT_IN_ADAPTER", "level": "FAIL"})
    if "_apply_para_delete" not in adapter_src:
        findings.append({"code": "APPLY_PARA_DELETE_MISSING", "level": "FAIL"})
    return findings


def _check_js_implementation(cmd_src: str, state_src: str) -> list[dict]:
    findings = []
    for sym, src, name in [
        ("makeParaDeleteCommand", cmd_src, "command"),
        ("applyParaDeleteForwardToParagraphs", cmd_src, "command"),
        ("mergeParagraphWithPrevious", state_src, "state"),
    ]:
        if sym not in src:
            findings.append({"code": f"{sym.upper()}_MISSING", "file": name, "level": "FAIL"})
    return findings


def _check_safety_gate(adapter_src: str) -> list[dict]:
    findings = []
    for sym in ["_apply_para_delete_cell", "TABLE_CELL_MERGE"]:
        if sym in adapter_src:
            findings.append({"code": "FORBIDDEN_CELL_MERGE_FOUND", "symbol": sym, "level": "FAIL"})
    if "def create_char_pr" in adapter_src:
        findings.append({"code": "FORBIDDEN_CREATE_CHARPR", "level": "FAIL"})
    return findings


def _check_verify7(verify_src: str) -> list[dict]:
    findings = []
    if "PARA_DELETE" not in verify_src:
        findings.append({"code": "V8_PARA_DELETE_MISSING_IN_VERIFY7", "level": "FAIL"})
    return findings


def _check_locked_files_unchanged() -> list[dict]:
    findings = []
    for rel in LOCKED_FILES_VS_BASELINE:
        r = subprocess.run(
            ["git", "diff", BASELINE_COMMIT, "--", rel],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(PR),
            timeout=20,
        )
        if r.returncode != 0 or r.stdout.strip():
            findings.append({"code": "LOCKED_FILE_CHANGED", "detail": rel, "level": "FAIL"})
    return findings


def _check_js_smoke() -> list[dict]:
    findings = []
    smoke = PR / "frontend/web_office_viewer/para_edit_structure_smoke.mjs"
    r = subprocess.run(
        ["node", str(smoke)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    try:
        out = json.loads(r.stdout.strip().split("\n")[-1])
        if out.get("verdict") != "PASS":
            findings.append({"code": "JS_SMOKE_FAIL", "detail": out, "level": "FAIL"})
    except Exception as e:  # ruff: ignore[blind-except] -- 스모크 출력 파싱 실패를 finding으로 보고하고 계속
        findings.append({"code": "JS_SMOKE_ERROR", "detail": str(e), "level": "FAIL"})
    return findings


def _check_python_tests() -> list[dict]:
    findings = []
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_web_office_para_edit_structure_para_delete.py",
            "-q",
            "--tb=short",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(PR),
        timeout=120,
    )
    if r.returncode != 0:
        findings.append({"code": "PYTHON_TESTS_FAIL", "detail": r.stdout[-2000:], "level": "FAIL"})
    return findings


def audit() -> dict:
    findings = []
    findings.extend(_check_required_files())

    model_src = (PR / "scripts/hwpx/web_office/para_edit_model.py").read_text(encoding="utf-8")
    findings.extend(_check_model_constants(model_src))

    adapter_src = (PR / "scripts/hwpx/web_office/paragraph_writer_adapter.py").read_text(
        encoding="utf-8"
    )
    findings.extend(_check_adapter_support(adapter_src))

    cmd_src = (PR / "frontend/web_office_viewer/para_edit_command.mjs").read_text(encoding="utf-8")
    state_src = (PR / "frontend/web_office_viewer/para_edit_state.mjs").read_text(encoding="utf-8")
    findings.extend(_check_js_implementation(cmd_src, state_src))

    findings.extend(_check_safety_gate(adapter_src))

    verify_src = (PR / "scripts/hwpx/web_office/paragraph_save_verify7.py").read_text(
        encoding="utf-8"
    )
    findings.extend(_check_verify7(verify_src))

    findings.extend(_check_locked_files_unchanged())
    findings.extend(_check_js_smoke())
    findings.extend(_check_python_tests())

    verdict = "PASS" if not findings else "FAIL"
    return {
        "audit": "WEB-OFFICE-PARA-EDIT-STRUCTURE-PARA-DELETE-01",
        "baseline": BASELINE_COMMIT,
        "verdict": verdict,
        "findings": findings,
    }


if __name__ == "__main__":
    import json as _json

    print(_json.dumps(audit(), indent=2, ensure_ascii=False))
