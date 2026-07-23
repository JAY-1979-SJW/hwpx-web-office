"""WEB-OFFICE-PARA-EDIT-STRUCTURE-PARA-DELETE-CLOSEOUT-01 준공검사.

Backspace paragraph merge 기능 준공 동결의 정적 검증.
baseline: 5db3d7f / feature commit: 1f442ec
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

CLOSEOUT_DOC = (PR / "docs/architecture/"
                   "web_office_para_edit_structure_para_delete_closeout.md")
BASELINE_COMMIT = "334d665"
FEATURE_COMMIT  = "1f442ec"

DOC_REQUIRED_IN_SCOPE = [
    "CT_PARA_DELETE",
    "makeParaDeleteCommand",
    "applyParaDeleteForwardToParagraphs",
    "mergeParagraphWithPrevious",
    "deleteBackward",
    "_apply_para_delete",
    "make_para_delete_command",
    "REASON_NO_PREV_PARAGRAPH",
    "REASON_PARA_DELETE_CELL_SCOPE_NOT_SUPPORTED",
    "charPrIDRef / parPrIDRef",
    "paragraph id 제거",
    "V8",
]
DOC_REQUIRED_OUT_OF_SCOPE = [
    "table cell paragraph merge",
    "header/footer paragraph merge",
    "image/shape run special merge",
    "section break merge",
    "list/numbering merge",
    "multi-paragraph selection merge",
    "Shift+Enter soft break",
    "신규 charPr 생성",
    "header.xml mutation",
    "Excel 공정",
    "원본 HWPX 직접 수정",
    "AI 자동 입력",
]
DOC_REQUIRED_NEXT_PROCESSES = [
    "STRUCTURE-SOFT-BREAK-01",
    "STRUCTURE-PARA-DELETE-CELL-01",
    "UNDO-REDO-STACK-LIMIT-01",
]

# 5db3d7f 기준 — PARA_DELETE 기능 자재 + 인접 핵심 자재 무수정
LOCKED_FILES_VS_BASELINE = [
    "frontend/web_office_viewer/para_edit_command.mjs",
    "frontend/web_office_viewer/para_edit_state.mjs",
    "frontend/web_office_viewer/para_edit_runtime.mjs",
    "frontend/web_office_viewer/para_edit_structure_smoke.mjs",
    "scripts/hwpx/web_office/para_edit_model.py",
    "scripts/hwpx/web_office/paragraph_writer_adapter.py",
    "scripts/hwpx/web_office/paragraph_save_verify7.py",
    "scripts/hwpx/web_office/paragraph_save_pipeline.py",
    "scripts/hwpx/web_office/para_edit_e2e_pipeline.py",
    "scripts/hwpx/web_office/charpr_inventory.py",
    "scripts/hwpx/web_office/render_payload.py",
]

REQUIRED_FILES = [
    "tests/test_web_office_para_edit_structure_para_delete.py",
    "tests/test_web_office_para_edit_structure_para_insert.py",
    "frontend/web_office_viewer/para_edit_structure_smoke.mjs",
    "scripts/ops/audit_web_office_para_edit_structure_para_delete.py",
    "frontend/web_office_viewer/para_edit_command.mjs",
    "frontend/web_office_viewer/para_edit_state.mjs",
    "scripts/hwpx/web_office/para_edit_model.py",
    "scripts/hwpx/web_office/paragraph_writer_adapter.py",
    "scripts/hwpx/web_office/paragraph_save_verify7.py",
]

REQUIRED_SOURCE_PATTERNS = [
    (PR / "frontend/web_office_viewer/para_edit_command.mjs", [
        r"export\s+function\s+makeParaDeleteCommand\(",
        r"export\s+function\s+applyParaDeleteForwardToParagraphs\(",
        r'CT_PARA_DELETE\s*=\s*"PARA_DELETE"',
    ]),
    (PR / "frontend/web_office_viewer/para_edit_state.mjs", [
        r"export\s+function\s+mergeParagraphWithPrevious\(",
        r"NO_PREV_PARAGRAPH",
        r"PARA_DELETE_CELL_SCOPE_NOT_SUPPORTED",
        r"SECTION_BOUNDARY_NOT_SUPPORTED",
    ]),
    (PR / "scripts/hwpx/web_office/para_edit_model.py", [
        r'CT_PARA_DELETE\s*=\s*"PARA_DELETE"',
        r"make_para_delete_command",
        r"REASON_NO_PREV_PARAGRAPH",
    ]),
    (PR / "scripts/hwpx/web_office/paragraph_writer_adapter.py", [
        r'"PARA_DELETE"',
        r"_apply_para_delete",
        r"REASON_PARA_DELETE_CELL_SCOPE_NOT_SUPPORTED",
    ]),
    (PR / "scripts/hwpx/web_office/paragraph_save_verify7.py", [
        r"PARA_DELETE",
    ]),
]

FORBIDDEN_PATTERNS = [
    (r"_apply_para_delete_cell\b", "table cell merge 구현 금지"),
    (r"TABLE_CELL_MERGE", "table cell merge 금지 심볼"),
    (r"def\s+create_char_pr\b", "신규 charPr 생성 금지"),
    (r'package\.entries\["header\.xml"\]\s*=', "header.xml write 금지"),
]
FORBIDDEN_SCAN_TARGETS = [
    "scripts/hwpx/web_office/paragraph_writer_adapter.py",
    "scripts/hwpx/web_office/para_edit_model.py",
]


def _check_required_doc() -> list[dict]:
    findings: list[dict] = []
    if not CLOSEOUT_DOC.is_file():
        findings.append({"code": "MISSING_DOC", "level": "FAIL",
                         "detail": str(CLOSEOUT_DOC.relative_to(PR))})
        return findings
    src = CLOSEOUT_DOC.read_text(encoding="utf-8")
    for phrase in DOC_REQUIRED_IN_SCOPE:
        if phrase not in src:
            findings.append({"code": "DOC_IN_SCOPE_PHRASE_MISSING",
                             "level": "FAIL", "detail": phrase})
    for phrase in DOC_REQUIRED_OUT_OF_SCOPE:
        if phrase not in src:
            findings.append({"code": "DOC_OUT_OF_SCOPE_PHRASE_MISSING",
                             "level": "FAIL", "detail": phrase})
    for phrase in DOC_REQUIRED_NEXT_PROCESSES:
        if phrase not in src:
            findings.append({"code": "DOC_NEXT_PROCESS_MISSING",
                             "level": "FAIL", "detail": phrase})
    if BASELINE_COMMIT not in src:
        findings.append({"code": "DOC_BASELINE_MISSING",
                         "level": "FAIL", "detail": f"baseline {BASELINE_COMMIT}"})
    if FEATURE_COMMIT not in src:
        findings.append({"code": "DOC_FEATURE_COMMIT_MISSING",
                         "level": "FAIL", "detail": f"feature commit {FEATURE_COMMIT}"})
    for rel in REQUIRED_FILES:
        name = Path(rel).name
        if name not in src:
            findings.append({"code": "DOC_FILE_NOT_LISTED",
                             "level": "FAIL", "detail": name})
    return findings


def _check_required_files() -> list[dict]:
    findings: list[dict] = []
    for rel in REQUIRED_FILES:
        if not (PR / rel).is_file():
            findings.append({"code": "MISSING_FILE", "level": "FAIL", "detail": rel})
    return findings


def _check_source_patterns() -> list[dict]:
    findings: list[dict] = []
    for path, patterns in REQUIRED_SOURCE_PATTERNS:
        if not path.is_file():
            findings.append({"code": "MISSING_SOURCE_FILE", "level": "FAIL",
                             "detail": str(path.relative_to(PR))})
            continue
        src = path.read_text(encoding="utf-8")
        for pat in patterns:
            if not re.search(pat, src):
                findings.append({"code": "REQUIRED_PATTERN_MISSING",
                                 "level": "FAIL",
                                 "detail": f"{path.name}: {pat}"})
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
    except Exception as e:
        findings.append({"code": "JS_SMOKE_ERROR", "level": "FAIL",
                         "detail": str(e)})
    return findings


def _check_python_tests() -> list[dict]:
    findings: list[dict] = []
    r = subprocess.run(
        [sys.executable, "-m", "pytest",
         "tests/test_web_office_para_edit_structure_para_delete.py",
         "tests/test_web_office_para_edit_structure_para_insert.py",
         "-q", "--tb=short"],
        capture_output=True, text=True, cwd=str(PR), timeout=60)
    if r.returncode != 0:
        findings.append({"code": "PYTHON_TESTS_FAIL", "level": "FAIL",
                         "detail": r.stdout[-2000:]})
    return findings


def audit() -> dict:
    all_findings: list[dict] = []
    all_findings += _check_required_doc()
    all_findings += _check_required_files()
    all_findings += _check_source_patterns()
    all_findings += _check_forbidden_patterns()
    all_findings += _check_locked_files()
    all_findings += _check_staged_zero()
    all_findings += _check_js_smoke()
    all_findings += _check_python_tests()

    verdict = "PASS" if not all_findings else "FAIL"
    return {
        "audit": "WEB-OFFICE-PARA-EDIT-STRUCTURE-PARA-DELETE-CLOSEOUT-01",
        "baseline": BASELINE_COMMIT,
        "feature_commit": FEATURE_COMMIT,
        "verdict": verdict,
        "findings": all_findings,
    }


if __name__ == "__main__":
    import json as _json
    print(_json.dumps(audit(), indent=2, ensure_ascii=False))
