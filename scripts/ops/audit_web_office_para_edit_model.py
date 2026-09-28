"""WEB-OFFICE-PARA-EDIT-MODEL-01 감사 스크립트.

Python para_edit_model + JS para_edit_command 의 정합성 + 정적 잠금
검증. writer 호출, output HWPX 생성, 원본 HWPX 접근 일절 없음.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PR))

VIEWER_DIR = PR / "frontend/web_office_viewer"
JS_SELF_TEST = VIEWER_DIR / "para_edit_self_test.mjs"

PY_FILES = [
    PR / "scripts/hwpx/web_office/para_edit_model.py",
    PR / "scripts/hwpx/web_office/para_edit_normalizer.py",
]
JS_FILES = [
    VIEWER_DIR / "para_edit_command.mjs",
    VIEWER_DIR / "para_edit_normalizer.mjs",
    VIEWER_DIR / "para_edit_self_test.mjs",
]

# 본 공정 모델은 writer 본 실행/save/output 호출 금지
FORBIDDEN_PY = [
    "from scripts.hwpx import hwpx_edit_tool",
    "import hwpx_edit_tool",
    "apply" + "_edit_plan(",
    "write_package(",
    "_save_pipeline",
    "verify7(",
]
FORBIDDEN_JS = [
    "apply" + "_edit_plan",
    "hwpx" + "_edit_tool",
    "saveButton",
    "fetch('/save",
    'fetch("/save',
]


def _check_static() -> list[dict]:
    findings = []
    for p in PY_FILES:
        if not p.is_file():
            findings.append({
                "code": "PY_FILE_MISSING",
                "level": "FAIL",
                "detail": str(p.relative_to(PR)),
            })
            continue
        src = p.read_text(encoding="utf-8")
        for tok in FORBIDDEN_PY:
            if tok in src:
                findings.append({
                    "code": "FORBIDDEN_PY_TOKEN",
                    "level": "FAIL",
                    "detail": f"{p.name}: {tok}",
                })
    for p in JS_FILES:
        if not p.is_file():
            findings.append({
                "code": "JS_FILE_MISSING",
                "level": "FAIL",
                "detail": str(p.relative_to(PR)),
            })
            continue
        src = p.read_text(encoding="utf-8")
        for tok in FORBIDDEN_JS:
            if tok in src:
                findings.append({
                    "code": "FORBIDDEN_JS_TOKEN",
                    "level": "FAIL",
                    "detail": f"{p.name}: {tok}",
                })
    return findings


def _run_js() -> dict:
    r = subprocess.run(
        ["node", str(JS_SELF_TEST)], capture_output=True, text=True, timeout=30, encoding="utf-8"
    )
    if r.returncode != 0:
        return {"ok": False, "stderr": r.stderr[:500], "stdout": r.stdout[:500]}
    try:
        last = r.stdout.strip().splitlines()[-1]
        out = json.loads(last)
    except Exception as e:  # ruff: ignore[blind-except] - 파싱 실패 사유 무관, 에러로 보고
        return {"ok": False, "stderr": f"parse: {e}"}
    return {"ok": out.get("verdict") == "PASS", "checks": out.get("checks", {})}


def _check_merge_mismatch_reject(p0) -> list[dict]:
    from scripts.hwpx.web_office.para_edit_model import (
        REASON_MERGE_CHARPR_MISMATCH,
        merge_runs,
    )

    findings = []
    try:
        merge_runs(p0, "par_p1_run0", "par_p1_run1")
        findings.append({"code": "PY_MERGE_MISMATCH_NOT_REJECTED", "level": "FAIL"})
    except ValueError as e:
        if REASON_MERGE_CHARPR_MISMATCH not in str(e):
            findings.append({"code": "PY_MERGE_REASON_WRONG", "level": "FAIL", "detail": str(e)})
    return findings


def _check_requires_review_throws(target, p0) -> list[dict]:
    from scripts.hwpx.web_office.para_edit_model import (
        POLICY_REQUIRES_REVIEW,
        REASON_REQUIRES_REVIEW,
        make_replace_text_range_command,
    )

    findings = []
    try:
        make_replace_text_range_command(
            target=target,
            paragraph=p0,
            range_anchor=1,
            range_focus=3,
            after_text="ZZ",
            source_document_hash="abc",
            policy=POLICY_REQUIRES_REVIEW,
        )
        findings.append({"code": "PY_REQUIRES_REVIEW_NOT_THROWN", "level": "FAIL"})
    except ValueError as e:
        if REASON_REQUIRES_REVIEW not in str(e):
            findings.append({
                "code": "PY_REQUIRES_REVIEW_REASON_WRONG",
                "level": "FAIL",
                "detail": str(e),
            })
    return findings


def _python_inline_audit() -> dict:
    """Python 모델 핵심 시나리오 정합."""
    from scripts.hwpx.web_office.para_edit_model import (
        Paragraph,
        ParagraphTarget,
        ParaTextRun,
        apply_command_to_paragraph,
        make_delete_text_range_command,
        make_replace_text_range_command,
        make_type_text_command,
        validate_charpr_preserved,
        validate_parpr_preserved,
    )

    findings = []
    p0 = Paragraph(
        paragraphId="par_p1",
        parPrIDRef="P1",
        runs=[
            ParaTextRun("par_p1_run0", "ab", "A"),
            ParaTextRun("par_p1_run1", "cd", "B"),
            ParaTextRun("par_p1_run2", "ef", "A"),
        ],
    )
    target = ParagraphTarget(
        paragraphId="par_p1", containerKind="block", containerId="blk_p1", sourceSha256="abc"
    )
    # TYPE_TEXT
    cmd = make_type_text_command(
        target=target, paragraph=p0, caret_offset=1, insert_text="X", source_document_hash="abc"
    )
    p1 = apply_command_to_paragraph(p0, cmd)
    if p1.text != "aXbcdef":
        findings.append({"code": "PY_TYPE_TEXT_FAIL", "level": "FAIL", "detail": p1.text})
    if not validate_parpr_preserved(p0, p1):
        findings.append({"code": "PY_PARPR_FAIL", "level": "FAIL"})
    if not validate_charpr_preserved(p0, p1):
        findings.append({"code": "PY_CHARPR_FAIL", "level": "FAIL"})

    # REPLACE single-run
    cmd2 = make_replace_text_range_command(
        target=target,
        paragraph=p0,
        range_anchor=0,
        range_focus=1,
        after_text="AB",
        source_document_hash="abc",
    )
    p2 = apply_command_to_paragraph(p0, cmd2)
    if p2.text != "ABbcdef":
        findings.append({"code": "PY_REPLACE_SINGLE_FAIL", "level": "FAIL", "detail": p2.text})

    # REPLACE multi-run ANCHOR_CHARPR
    cmd3 = make_replace_text_range_command(
        target=target,
        paragraph=p0,
        range_anchor=1,
        range_focus=5,
        after_text="ZZ",
        source_document_hash="abc",
    )
    p3 = apply_command_to_paragraph(p0, cmd3)
    if p3.text != "aZZf":
        findings.append({"code": "PY_REPLACE_MULTI_FAIL", "level": "FAIL", "detail": p3.text})

    # DELETE + inverse roundtrip
    cmd4 = make_delete_text_range_command(
        target=target, paragraph=p0, range_anchor=2, range_focus=4, source_document_hash="abc"
    )
    p4 = apply_command_to_paragraph(p0, cmd4)
    if p4.text != "abef":
        findings.append({"code": "PY_DELETE_FAIL", "level": "FAIL", "detail": p4.text})
    # inverse = REPLACE @ a=2,b=2, after="cd"
    inv_cmd = type(cmd4)(
        commandId=cmd4.commandId,
        commandType="REPLACE_TEXT_RANGE",
        target=cmd4.target,
        payload=cmd4.payload,
        forward=cmd4.inverse,
        inverse=cmd4.forward,
        expectedBefore="",
        createdAt=cmd4.createdAt,
        sourceDocumentHash=cmd4.sourceDocumentHash,
        commandGroupId=cmd4.commandGroupId,
        status=cmd4.status,
    )
    p4back = apply_command_to_paragraph(p4, inv_cmd)
    if p4back.text != "abcdef":
        findings.append({"code": "PY_DELETE_INVERSE_FAIL", "level": "FAIL", "detail": p4back.text})

    findings.extend(_check_merge_mismatch_reject(p0))
    findings.extend(_check_requires_review_throws(target, p0))

    return {"findings": findings, "ok": len(findings) == 0}


def audit() -> dict:
    findings: list[dict] = []
    findings.extend(_check_static())

    py = _python_inline_audit()
    if not py["ok"]:
        findings.extend(py["findings"])

    js = _run_js()
    if not js["ok"]:
        findings.append({"code": "JS_SELF_TEST_FAIL", "level": "FAIL", "detail": js})

    # 본 공정 디렉토리에 .hwpx 0건
    for d in [VIEWER_DIR, PR / "scripts/hwpx/web_office"]:
        if d.is_dir():
            for f in d.glob("*.hwpx"):
                findings.append({
                    "code": "UNEXPECTED_HWPX_OUTPUT",
                    "level": "FAIL",
                    "detail": str(f.relative_to(PR)),
                })

    return {
        "task": "WEB-OFFICE-PARA-EDIT-MODEL-01",
        "jsChecks": js.get("checks", {}),
        "pyOk": py["ok"],
        "findings": findings,
        "verdict": "PASS" if not findings else "FAIL",
    }


def main() -> int:
    out = audit()
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0 if out["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
