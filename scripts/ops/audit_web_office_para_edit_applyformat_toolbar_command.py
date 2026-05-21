"""WEB-OFFICE-PARA-EDIT-APPLYFORMAT-TOOLBAR-COMMAND-01 준공검사.

applyFormatToSelection helper (JS) → APPLY_FORMAT command 발급 →
commandLog append-only 적재 회로의 정적·동적 검증.
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

STATE_MJS = PR / "frontend/web_office_viewer/para_edit_state.mjs"
CMD_MJS = PR / "frontend/web_office_viewer/para_edit_command.mjs"
PREVIEW_TSX = (PR / "frontend/web_office_viewer/components/"
                      "WebOfficeFormatPreview.tsx")
SMOKE_JS = (PR / "frontend/web_office_viewer/"
                  "para_edit_apply_format_smoke.mjs")
BASELINE_COMMIT = "98d64ed"  # PARA_INSERT 준공 후 갱신 (abebab6 → 1f442ec)

REQUIRED_STATE_PATTERNS = [
    r"export\s+function\s+applyFormatToSelection\(",
    r"makeApplyFormatCommand\(",
    r"CT_APPLY_FORMAT",
    r"COMPOSITION_LOCKED",
    r"NO_TEXT_RANGE",
    r"EMPTY_RANGE",
    r"TARGET_CHARPR_NOT_IN_HEADER",
    r"_appendCommand\(",
]
REQUIRED_CMD_PATTERNS = [
    r'k === "APPLY_FORMAT"',
    r'k === "APPLY_FORMAT_INVERSE"',
    r"function\s+_applyFormat\(",
    r"function\s+_applyFormatInverse\(",
]
REQUIRED_PREVIEW_PATTERNS = [
    r"enableApplyCommand",
    r"onApplyCharPr",
    r"readOnlyMode\s*=\s*!enableApplyCommand",
    r"data-clickable",
]

# preview / state / command 가 절대 호출/도입하지 말아야 하는 패턴
FORBIDDEN_PREVIEW_PATTERNS = [
    # preview 컴포넌트는 backend writer/save 또는 factory 를 직접 호출 X
    r"makeApplyFormatCommand\(",
    r"applyFormatToSelection\(",
    r"save_paragraph_edits\(",
    r"apply_paragraph_edits_plan\(",
    r"write_package\(",
    r"\.write_xml\(",
    r"def\s+create_char_pr\b",
    r"package\.entries\[[^\]]*header\.xml[^\]]*\]\s*=",
]
FORBIDDEN_FRONTEND_BACKEND_CALLS = [
    r"save_paragraph_edits\(",
    r"apply_paragraph_edits_plan\(",
    r"create_hwpx_document\(",
    r"write_package\(",
]

# abebab6 baseline 시점에 잠금된 backend 자재 — 본 공정에서 무수정
LOCKED_FILES_VS_BASELINE = [
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

FORBIDDEN_AUDIT_WRITER_SYMBOLS = [
    r"apply_paragraph_edits_plan\(",
    r"save_paragraph_edits\(",
    r"create_hwpx_document\(",
    r"write_package\(",
    r"\.write_xml\(",
]


def _check_required_state() -> list[dict]:
    findings: list[dict] = []
    if not STATE_MJS.is_file():
        findings.append({"code": "STATE_MJS_MISSING", "level": "FAIL"})
        return findings
    src = STATE_MJS.read_text(encoding="utf-8")
    for pat in REQUIRED_STATE_PATTERNS:
        if not re.search(pat, src):
            findings.append({"code": "STATE_PATTERN_MISSING",
                              "level": "FAIL", "detail": pat})
    return findings


def _check_required_command() -> list[dict]:
    findings: list[dict] = []
    if not CMD_MJS.is_file():
        findings.append({"code": "CMD_MJS_MISSING", "level": "FAIL"})
        return findings
    src = CMD_MJS.read_text(encoding="utf-8")
    for pat in REQUIRED_CMD_PATTERNS:
        if not re.search(pat, src):
            findings.append({"code": "CMD_PATTERN_MISSING",
                              "level": "FAIL", "detail": pat})
    # makeApplyFormatCommand 1개만 정의되어야 한다 (factory 재정의 금지)
    defs = re.findall(
        r"export\s+function\s+makeApplyFormatCommand\b", src)
    if len(defs) != 1:
        findings.append({"code": "CMD_FACTORY_REDEFINED",
                          "level": "FAIL",
                          "detail": f"makeApplyFormatCommand defs={len(defs)}"})
    return findings


def _check_required_preview() -> list[dict]:
    findings: list[dict] = []
    if not PREVIEW_TSX.is_file():
        findings.append({"code": "PREVIEW_TSX_MISSING",
                          "level": "FAIL"})
        return findings
    src = PREVIEW_TSX.read_text(encoding="utf-8")
    for pat in REQUIRED_PREVIEW_PATTERNS:
        if not re.search(pat, src):
            findings.append({"code": "PREVIEW_PATTERN_MISSING",
                              "level": "FAIL", "detail": pat})
    for pat in FORBIDDEN_PREVIEW_PATTERNS:
        if re.search(pat, src):
            findings.append({"code": "PREVIEW_FORBIDDEN_CALL",
                              "level": "FAIL", "detail": pat})
    return findings


def _check_no_backend_call_in_frontend() -> list[dict]:
    findings: list[dict] = []
    for rel in [
        "frontend/web_office_viewer/para_edit_state.mjs",
        "frontend/web_office_viewer/para_edit_command.mjs",
        "frontend/web_office_viewer/components/WebOfficeFormatPreview.tsx",
        "frontend/web_office_viewer/para_edit_apply_format_smoke.mjs",
    ]:
        p = PR / rel
        if not p.is_file():
            continue
        src = p.read_text(encoding="utf-8")
        for pat in FORBIDDEN_FRONTEND_BACKEND_CALLS:
            if re.search(pat, src):
                findings.append({"code": "BACKEND_CALL_IN_FRONTEND",
                                  "level": "FAIL",
                                  "detail": f"{rel}: {pat}"})
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


def _check_audit_no_writer_calls() -> list[dict]:
    findings: list[dict] = []
    me = Path(__file__).read_text(encoding="utf-8")
    for sym in FORBIDDEN_AUDIT_WRITER_SYMBOLS:
        if re.search(sym, me):
            findings.append({"code": "AUDIT_FORBIDDEN_WRITER_CALL",
                              "level": "FAIL", "detail": sym})
    return findings


def _node_ok() -> bool:
    try:
        r = subprocess.run(["node", "--version"], capture_output=True,
                                          text=True, timeout=10)
        return r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _run_smoke() -> tuple[dict | None, str]:
    if not _node_ok():
        return None, "node not available"
    if not SMOKE_JS.is_file():
        return None, "smoke script missing"
    r = subprocess.run(
        ["node", str(SMOKE_JS)], capture_output=True, text=True,
        timeout=30, encoding="utf-8")
    if r.returncode != 0:
        return None, f"smoke rc={r.returncode}: {r.stderr.strip()}"
    try:
        return json.loads(r.stdout), ""
    except json.JSONDecodeError as e:
        return None, f"json: {e}"


def _check_smoke(out: dict) -> list[dict]:
    findings: list[dict] = []
    if out.get("verdict") != "PASS":
        findings.append({"code": "SMOKE_VERDICT_NOT_PASS",
                          "level": "FAIL",
                          "detail": out.get("verdict")})
    checks = out.get("checks") or {}
    for name, c in checks.items():
        if not c.get("ok"):
            findings.append({"code": "SMOKE_CHECK_FAIL",
                              "level": "FAIL",
                              "detail": f"{name}: {c}"})
    if len(checks) < 20:
        findings.append({"code": "SMOKE_FEW_CHECKS",
                          "level": "WARN",
                          "detail": f"checks={len(checks)}"})
    return findings


def audit() -> dict[str, Any]:
    findings: list[dict] = []
    findings.extend(_check_required_state())
    findings.extend(_check_required_command())
    findings.extend(_check_required_preview())
    findings.extend(_check_no_backend_call_in_frontend())
    findings.extend(_check_locked_files())
    findings.extend(_check_audit_no_writer_calls())
    smoke, smoke_err = _run_smoke()
    if smoke is None:
        if "node not available" in smoke_err:
            findings.append({"code": "SMOKE_SKIPPED", "level": "WARN",
                              "detail": smoke_err})
        else:
            findings.append({"code": "SMOKE_RUN_FAIL", "level": "FAIL",
                              "detail": smoke_err})
    else:
        findings.extend(_check_smoke(smoke))
    fail = [f for f in findings if f["level"] == "FAIL"]
    warn = [f for f in findings if f["level"] == "WARN"]
    return {
        "audit": "WEB-OFFICE-PARA-EDIT-APPLYFORMAT-"
                          "TOOLBAR-COMMAND-01",
        "baseline": BASELINE_COMMIT,
        "findings": findings,
        "verdict": "FAIL" if fail else ("WARN" if warn else "PASS"),
        "smoke": smoke,
    }


if __name__ == "__main__":
    print(json.dumps(audit(), ensure_ascii=False, indent=2))
