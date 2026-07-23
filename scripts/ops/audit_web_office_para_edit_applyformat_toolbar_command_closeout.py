"""WEB-OFFICE-PARA-EDIT-APPLYFORMAT-TOOLBAR-COMMAND-CLOSEOUT-01 준공검사.

ApplyFormat toolbar command 부분 준공 동결의 정적 검증.
"""
from __future__ import annotations
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

PR = Path(__file__).resolve().parents[2]
if str(PR) not in sys.path:
    sys.path.insert(0, str(PR))

CLOSEOUT_DOC = (PR / "docs/architecture/"
                   "web_office_para_edit_applyformat_toolbar_command_closeout.md")
BASELINE_COMMIT = "b992ad6"  # 중첩표 읽기/쓰기 대칭 준공 후 갱신 (f119308 → b992ad6)

DOC_REQUIRED_IN_SCOPE = [
    "applyFormatToSelection",
    "enableApplyCommand",
    "onApplyCharPr",
    "read-only mode",
    "commandLog append-only",
    "undoStack", "redoStack",
    "paragraph.text 무변경",
    "inverse.restoreSegments", "_applyFormatInverse",
    "buildSaveDryRunPayload",
    "node smoke",
    "para_edit_apply_format_smoke.mjs",
    "makeApplyFormatCommand",
    "COMPOSITION_LOCKED", "NO_TEXT_RANGE", "EMPTY_RANGE",
    "TARGET_CHARPR_NOT_IN_HEADER",
]
DOC_REQUIRED_OUT_OF_SCOPE = [
    "신규 charPr 생성",
    "header.xml charPr 추가",
    "bold/italic/color/fontSize 직접 버튼",
    "matching charPr 알고리즘",
    "backend writer 직접 호출",
    "save pipeline 재설계",
    "paragraph add/delete",
    "table structure edit",
    "image/stamp/signature",
    "AI 자동 입력",
    "원본 HWPX 직접 수정",
    "multi-paragraph selection",
]
DOC_REQUIRED_NEXT_PROCESSES = [
    "APPLYFORMAT-MATCHING-PREFLIGHT-01",
    "APPLYFORMAT-MATCHING-EXISTING-CHARPR-01",
    "APPLYFORMAT-FAUX-BOLD-TOOLBAR-01",
    "APPLYFORMAT-NEW-CHARPR-PREFLIGHT-01",
    "PARA-EDIT-STRUCTURE-PREFLIGHT-01",
]

# 7795857 시점 핵심 시공 자재 — 본 closeout 에서 기능 변경 금지
LOCKED_FILES_VS_BASELINE = [
    "frontend/web_office_viewer/para_edit_state.mjs",
    "frontend/web_office_viewer/para_edit_command.mjs",
    "frontend/web_office_viewer/components/WebOfficeFormatPreview.tsx",
    "frontend/web_office_viewer/para_edit_apply_format_smoke.mjs",
    # backend 측 — 본 공정에서도 무수정
    "scripts/hwpx/hwpx_paragraph_ops.py",
    "scripts/hwpx/hwpx_edit_tool.py",
    "scripts/hwpx/web_office/para_edit_model.py",
    "scripts/hwpx/web_office/paragraph_edit_plan.py",
    "scripts/hwpx/web_office/paragraph_writer_adapter.py",
    "scripts/hwpx/web_office/paragraph_save_verify7.py",
    "scripts/hwpx/web_office/para_edit_e2e_pipeline.py",
    "scripts/hwpx/web_office/paragraph_save_pipeline.py",
    "scripts/hwpx/web_office/charpr_inventory.py",
    "scripts/hwpx/web_office/render_payload.py",
    "frontend/web_office_viewer/para_edit_runtime.mjs",
]

# 회귀 자재 — 모두 존재해야 한다
REQUIRED_TESTS = [
    "tests/test_web_office_para_edit_applyformat_toolbar_command.py",
    "tests/test_web_office_para_edit_applyformat_toolbar_preview.py",
    "tests/test_web_office_para_edit_applyformat_existing_charpr.py",
    "tests/test_web_office_para_edit_applyformat_existing_charpr_closeout.py",
    "tests/test_web_office_para_edit_format_charpr_inventory.py",
    "tests/test_web_office_para_edit_content_closeout.py",
    "tests/test_web_office_para_edit_e2e_full_closeout.py",
    "tests/test_web_office_para_edit_ime_live.py",
]
REQUIRED_JS_SMOKES = [
    "frontend/web_office_viewer/para_edit_apply_format_smoke.mjs",
    "frontend/web_office_viewer/para_edit_browser_self_test.mjs",
    "frontend/web_office_viewer/para_edit_ime_live_smoke.mjs",
]

# 활성화 신호 — 본 commit 의 핵심 패턴이 자재에 살아 있어야 한다
REQUIRED_SOURCE_PATTERNS = [
    (PR / "frontend/web_office_viewer/para_edit_state.mjs",
      [r"export\s+function\s+applyFormatToSelection\(",
        r"COMPOSITION_LOCKED",
        r"TARGET_CHARPR_NOT_IN_HEADER"]),
    (PR / "frontend/web_office_viewer/para_edit_command.mjs",
      [r'k === "APPLY_FORMAT"',
        r"function\s+_applyFormat\(",
        r"function\s+_applyFormatInverse\("]),
    (PR / "frontend/web_office_viewer/components/"
        "WebOfficeFormatPreview.tsx",
      [r"enableApplyCommand",
        r"onApplyCharPr",
        r"readOnlyMode\s*=\s*!enableApplyCommand"]),
]

# 차단 범위가 코드에 우발 활성화된 흔적 없음
FORBIDDEN_SOURCE_PATTERNS = [
    (r"def\s+create_char_pr\b", "신규 charPr 생성 함수 우발 도입"),
    (r"package\.entries\[[^\]]*header\.xml[^\]]*\]\s*=",
      "header.xml write 경로 우발 도입"),
    (r"save_paragraph_edits\(", "backend save 직접 호출 우발 도입"),
    (r"apply_paragraph_edits_plan\(",
      "backend apply 직접 호출 우발 도입"),
    (r"create_hwpx_document\(", "writer 직접 호출 우발 도입"),
    (r"write_package\(", "writer 직접 호출 우발 도입"),
]
FORBIDDEN_SCAN_TARGETS = [
    "frontend/web_office_viewer/para_edit_state.mjs",
    "frontend/web_office_viewer/para_edit_command.mjs",
    "frontend/web_office_viewer/components/WebOfficeFormatPreview.tsx",
    "frontend/web_office_viewer/para_edit_apply_format_smoke.mjs",
]

FORBIDDEN_AUDIT_WRITER_SYMBOLS = [
    r"apply_paragraph_edits_plan\(",
    r"save_paragraph_edits\(",
    r"create_hwpx_document\(",
    r"write_package\(",
    r"\.write_xml\(",
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
                          "level": "FAIL",
                          "detail": f"baseline {BASELINE_COMMIT}"})
    # 회귀 자재 인용 검증
    for rel in REQUIRED_TESTS + REQUIRED_JS_SMOKES:
        name = Path(rel).name
        if name not in src:
            findings.append({"code": "DOC_FILE_NOT_LISTED",
                              "level": "FAIL", "detail": name})
    return findings


def _check_required_files() -> list[dict]:
    findings: list[dict] = []
    for rel in REQUIRED_TESTS + REQUIRED_JS_SMOKES:
        if not (PR / rel).is_file():
            findings.append({"code": "MISSING_FILE", "level": "FAIL",
                              "detail": rel})
    return findings


def _check_locked_files() -> list[dict]:
    findings: list[dict] = []
    for rel in LOCKED_FILES_VS_BASELINE:
        try:
            r = subprocess.run(
                ["git", "diff", BASELINE_COMMIT, "--", rel],
                capture_output=True, text=True, cwd=str(PR), timeout=20)
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            findings.append({"code": "GIT_DIFF_FAILED", "level": "WARN",
                              "detail": f"{rel}: {e}"})
            continue
        if r.returncode != 0:
            findings.append({"code": "GIT_DIFF_RC", "level": "WARN",
                              "detail": f"{rel}: rc={r.returncode}"})
            continue
        if r.stdout.strip():
            findings.append({"code": "LOCKED_FILE_CHANGED",
                              "level": "FAIL", "detail": rel})
    return findings


def _check_required_source_patterns() -> list[dict]:
    findings: list[dict] = []
    for path, patterns in REQUIRED_SOURCE_PATTERNS:
        if not path.is_file():
            findings.append({"code": "SOURCE_MISSING", "level": "FAIL",
                              "detail": str(path.relative_to(PR))})
            continue
        src = path.read_text(encoding="utf-8")
        for pat in patterns:
            if not re.search(pat, src):
                findings.append({"code": "REQUIRED_PATTERN_MISSING",
                                  "level": "FAIL",
                                  "detail":
                                      f"{path.relative_to(PR)}: {pat}"})
    return findings


def _check_forbidden_source_patterns() -> list[dict]:
    findings: list[dict] = []
    for rel in FORBIDDEN_SCAN_TARGETS:
        p = PR / rel
        if not p.is_file():
            continue
        src = p.read_text(encoding="utf-8")
        for pat, label in FORBIDDEN_SOURCE_PATTERNS:
            if re.search(pat, src):
                findings.append({"code": "FORBIDDEN_PATTERN_PRESENT",
                                  "level": "FAIL",
                                  "detail":
                                      f"{rel}: {label} ({pat})"})
    return findings


def _check_audit_no_writer_calls() -> list[dict]:
    findings: list[dict] = []
    me = Path(__file__).read_text(encoding="utf-8")
    for sym in FORBIDDEN_AUDIT_WRITER_SYMBOLS:
        if re.search(sym, me):
            findings.append({"code": "AUDIT_FORBIDDEN_WRITER_CALL",
                              "level": "FAIL", "detail": sym})
    return findings


def audit() -> dict[str, Any]:
    findings: list[dict] = []
    findings.extend(_check_required_doc())
    findings.extend(_check_required_files())
    findings.extend(_check_locked_files())
    findings.extend(_check_required_source_patterns())
    findings.extend(_check_forbidden_source_patterns())
    findings.extend(_check_audit_no_writer_calls())
    fail = [f for f in findings if f["level"] == "FAIL"]
    warn = [f for f in findings if f["level"] == "WARN"]
    return {
        "audit": "WEB-OFFICE-PARA-EDIT-APPLYFORMAT-"
                          "TOOLBAR-COMMAND-CLOSEOUT-01",
        "baseline": BASELINE_COMMIT,
        "findings": findings,
        "verdict": "FAIL" if fail else ("WARN" if warn else "PASS"),
    }


if __name__ == "__main__":
    print(json.dumps(audit(), ensure_ascii=False, indent=2))
