"""WEB-OFFICE-CELL-EDIT-MVP-A-01 감사 스크립트.

Python 측 EditCommand 모델 + dry-run plan 정합성, JS 측 셀 편집 상태기계
(node 자체 검증 실행) 양쪽을 검증한다. writer/apply 호출 0건을 정적으로
잠근다.
"""
from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path

PR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PR))

VIEWER_DIR = PR / "frontend/web_office_viewer"
SELF_TEST_JS = VIEWER_DIR / "cell_edit_self_test.mjs"

PY_FILES = [
    PR / "scripts/hwpx/web_office/edit_command_model.py",
    PR / "scripts/hwpx/web_office/cell_edit_plan.py",
]
JS_FILES = [
    VIEWER_DIR / "edit_command.mjs",
    VIEWER_DIR / "cell_edit_state.mjs",
    VIEWER_DIR / "cell_edit_self_test.mjs",
    VIEWER_DIR / "components/WebOfficeCellEditor.tsx",
]

# 본 공정 산출물 어디서든 등장하면 안 되는 토큰 (writer 본 실행 금지).
FORBIDDEN_TOKENS_PY = [
    "from scripts.hwpx import hwpx_edit_tool",
    "import hwpx_edit_tool", "apply_edit_plan(",
    "hwpx_writer_adapter", "write_package(",
]
FORBIDDEN_TOKENS_JS = [
    "apply_edit_plan", "hwpx_edit_tool", "write_package",
    "/save", "saveButton", "fetch('/save",
]


def _check_static_forbidden() -> list[dict]:
    findings: list[dict] = []
    for p in PY_FILES:
        if not p.is_file():
            findings.append({"code": "PY_FILE_MISSING", "level": "FAIL",
                                      "detail": str(p.relative_to(PR))})
            continue
        src = p.read_text(encoding="utf-8")
        for tok in FORBIDDEN_TOKENS_PY:
            if tok in src:
                findings.append({"code": "FORBIDDEN_PY_TOKEN",
                                          "level": "FAIL",
                                          "detail": f"{p.name}: {tok}"})
    for p in JS_FILES:
        if not p.is_file():
            findings.append({"code": "JS_FILE_MISSING", "level": "FAIL",
                                      "detail": str(p.relative_to(PR))})
            continue
        src = p.read_text(encoding="utf-8")
        for tok in FORBIDDEN_TOKENS_JS:
            if tok in src:
                findings.append({"code": "FORBIDDEN_JS_TOKEN",
                                          "level": "FAIL",
                                          "detail": f"{p.name}: {tok}"})
    return findings


def _run_js_self_test() -> dict:
    r = subprocess.run(["node", str(SELF_TEST_JS)],
                                      capture_output=True, text=True,
                                      timeout=30, encoding="utf-8")
    if r.returncode != 0:
        return {"ok": False, "stderr": r.stderr[:500],
                    "stdout": r.stdout[:500]}
    try:
        out = json.loads(r.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError) as e:
        return {"ok": False, "stderr": f"parse: {e}",
                    "stdout": r.stdout[:500]}
    return {"ok": out.get("verdict") == "PASS",
                "checks": out.get("checks", {})}


def _python_unit_audit() -> dict:
    """Python EditCommand 모델 핵심 시나리오를 인라인 검증."""
    from scripts.hwpx.web_office.edit_command_model import (
        make_set_cell_text_command, apply_forward, apply_inverse, COMMAND_TYPE_SET_CELL_TEXT,
    )
    from scripts.hwpx.web_office.cell_edit_plan import (
        build_dry_run_edit_plan, SAVE_DRY_RUN_NOOP,
        SAVE_DRY_RUN_READY, SAVE_DRY_RUN_REJECTED,
    )

    findings = []
    cell_id = "cell_t_s0_001_r2_c1"
    src_hash = "abc"
    cmd = make_set_cell_text_command(
        cell_id=cell_id, table_index=1,
        before="구값", after="새값", source_document_hash=src_hash)
    if cmd.commandType != COMMAND_TYPE_SET_CELL_TEXT:
        findings.append({"code": "CMD_TYPE", "level": "FAIL"})
    if cmd.forward["set_cells"][0]["row"] != 2:
        findings.append({"code": "CMD_FORWARD_ROW", "level": "FAIL"})
    if cmd.forward["set_cells"][0]["col"] != 1:
        findings.append({"code": "CMD_FORWARD_COL", "level": "FAIL"})
    if cmd.inverse["set_cells"][0]["value"] != "구값":
        findings.append({"code": "CMD_INVERSE_VALUE", "level": "FAIL"})
    # before == after 시 ValueError
    try:
        make_set_cell_text_command(cell_id=cell_id, table_index=1,
                                                              before="x", after="x",
                                                              source_document_hash=src_hash)
        findings.append({"code": "NO_CHANGE_NOT_BLOCKED",
                                  "level": "FAIL"})
    except ValueError:
        pass

    # expectedBefore mismatch → apply_forward raises
    try:
        apply_forward("다른값", cmd)
        findings.append({"code": "EXPECTED_BEFORE_NOT_ENFORCED",
                                  "level": "FAIL"})
    except ValueError:
        pass

    # forward / inverse 왕복
    nxt = apply_forward("구값", cmd)
    if nxt != "새값":
        findings.append({"code": "APPLY_FORWARD_BAD", "level": "FAIL"})
    back = apply_inverse("새값", cmd)
    if back != "구값":
        findings.append({"code": "APPLY_INVERSE_BAD", "level": "FAIL"})

    # build_dry_run_edit_plan — NOOP
    doc = {"cells": [{"cellId": cell_id, "text": "구값"}]}
    r = build_dry_run_edit_plan([], doc, src_hash)
    if r["status"] != SAVE_DRY_RUN_NOOP:
        findings.append({"code": "EMPTY_PLAN_NOT_NOOP", "level": "FAIL"})

    # build_dry_run_edit_plan — READY
    r = build_dry_run_edit_plan([cmd], doc, src_hash)
    if r["status"] != SAVE_DRY_RUN_READY:
        findings.append({"code": "PLAN_NOT_READY", "level": "FAIL"})
    if r["plan"]["set_cells"][0]["value"] != "새값":
        findings.append({"code": "PLAN_VALUE_BAD", "level": "FAIL"})
    if r["dryRun"] is not True:
        findings.append({"code": "DRY_RUN_FLAG_NOT_TRUE",
                                  "level": "FAIL"})

    # sourceDocumentHash mismatch → REJECTED
    cmd_other = make_set_cell_text_command(
        cell_id=cell_id, table_index=1,
        before="구값", after="다른새값",
        source_document_hash="WRONG")
    r = build_dry_run_edit_plan([cmd_other], doc, src_hash)
    if r["status"] != SAVE_DRY_RUN_REJECTED:
        findings.append({"code": "HASH_MISMATCH_NOT_REJECTED",
                                  "level": "FAIL"})

    # expectedBefore mismatch (현재 셀 값이 다르면 reject)
    cmd2 = make_set_cell_text_command(
        cell_id=cell_id, table_index=1,
        before="존재하지않는기준", after="결과",
        source_document_hash=src_hash)
    r = build_dry_run_edit_plan([cmd2], doc, src_hash)
    if r["status"] != SAVE_DRY_RUN_REJECTED:
        findings.append({"code": "EXPECTED_BEFORE_NOT_REJECTED",
                                  "level": "FAIL"})

    return {"findings": findings,
                "ok": len(findings) == 0}


def audit() -> dict:
    findings: list[dict] = []
    findings.extend(_check_static_forbidden())

    py = _python_unit_audit()
    if not py["ok"]:
        findings.extend(py["findings"])

    js = _run_js_self_test()
    if not js["ok"]:
        findings.append({"code": "JS_SELF_TEST_FAIL", "level": "FAIL",
                                  "detail": js})

    # 본 공정이 만든 .hwpx 출력 산출물 0건
    for d in [VIEWER_DIR, PR / "scripts/hwpx/web_office"]:
        leaks = list(d.glob("*.hwpx"))
        if leaks:
            findings.append({"code": "UNEXPECTED_HWPX_OUTPUT",
                                      "level": "FAIL",
                                      "detail": [str(p) for p in leaks]})

    return {
        "task": "WEB-OFFICE-CELL-EDIT-MVP-A-01",
        "jsChecks": js.get("checks", {}),
        "pyChecksOk": py["ok"],
        "findings": findings,
        "verdict": "PASS" if not findings else "FAIL",
    }


def main() -> int:
    out = audit()
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0 if out["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
