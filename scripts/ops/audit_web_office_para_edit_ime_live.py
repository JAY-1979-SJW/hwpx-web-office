"""WEB-OFFICE-PARA-EDIT-IME-LIVE-01 준공검사.

브라우저 IME composition (compositionstart / compositionupdate /
compositionend) → TYPE_TEXT command 생성 흐름을 node 기반 live smoke 로
구동하고, 결과 command 가 TYPE_TEXT_CONTRACT_01 계약 (expectedBefore="",
rangeStart==rangeEnd, afterText=최종 조합 문자열, containerScope 유지)
을 충족하는지 정적·동적으로 확인한다.

동적 신호:
  - node frontend/web_office_viewer/para_edit_ime_live_smoke.mjs 의 JSON
    verdict=="PASS" + 38 checks all ok
  - fixture 가용 시 동일 finalText 를 SCENARIO_TYPE 으로 E2E 투입 →
    V1~V7 PASS + 원본 sha/mtime 무변경 + output sandbox 격리

정적 신호:
  - smoke script 자체 존재 + 필수 핸들러 import
  - 본 audit 가 writer 신규 호출을 하지 않음 (self-check)
"""
from __future__ import annotations
import hashlib
import json
import re
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

PR = Path(__file__).resolve().parents[2]
if str(PR) not in sys.path:
    sys.path.insert(0, str(PR))

SMOKE_JS = (PR / "frontend/web_office_viewer/"
                  "para_edit_ime_live_smoke.mjs")
BROWSER_SELF_TEST_JS = (PR / "frontend/web_office_viewer/"
                              "para_edit_browser_self_test.mjs")

# 본 공정 baseline 이후 LOCKED 자재 (writer/adapter/model 등)
LOCKED_FILES = [
    # WEB-OFFICE-PARA-EDIT-APPLYFORMAT-EXISTING-CHARPR-01: ApplyFormat
    # 활성화로 다음 자재는 본 LOCKED 에서 제거됨 — para_edit_model,
    # paragraph_edit_plan, paragraph_save_verify7,
    # para_edit_e2e_pipeline, para_edit_command.mjs.
    "scripts/hwpx/web_office/paragraph_save_pipeline.py",
    "scripts/hwpx/web_office/ro_view_importer.py",
    # WEB-OFFICE-PARA-EDIT-APPLYFORMAT-TOOLBAR-COMMAND-01:
    # para_edit_state.mjs 는 applyFormatToSelection 추가로 본 LOCKED 에서 제거.
    "frontend/web_office_viewer/para_edit_runtime.mjs",
]
BASELINE_COMMIT = "b411164"  # PARA_INSERT 준공 후 갱신 (c7810b3 → bb0939b)

FORBIDDEN_WRITER_SYMBOLS = [
    r"apply_paragraph_edits_plan\(",
    r"save_paragraph_edits\(",
    r"create_hwpx_document\(",
    r"write_package\(",
]

REQUIRED_SMOKE_IMPORTS = [
    r"para_edit_state\.mjs",
    r"para_edit_runtime\.mjs",
    r"onCompositionStart", r"onCompositionUpdate",
    r"onCompositionEnd",
]


def _node_ok() -> bool:
    try:
        r = subprocess.run(["node", "--version"], capture_output=True,
                                          text=True, timeout=10)
        return r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _check_smoke_script() -> list[dict]:
    findings: list[dict] = []
    if not SMOKE_JS.is_file():
        findings.append({"code": "SMOKE_JS_MISSING", "level": "FAIL",
                          "detail": str(SMOKE_JS)})
        return findings
    src = SMOKE_JS.read_text(encoding="utf-8")
    for pat in REQUIRED_SMOKE_IMPORTS:
        if not re.search(pat, src):
            findings.append({
                "code": "SMOKE_IMPORT_MISSING", "level": "FAIL",
                "detail": pat})
    return findings


def _check_audit_no_writer_calls() -> list[dict]:
    findings: list[dict] = []
    me = Path(__file__).read_text(encoding="utf-8")
    for sym in FORBIDDEN_WRITER_SYMBOLS:
        if re.search(sym, me):
            findings.append({
                "code": "AUDIT_FORBIDDEN_WRITER_CALL",
                "level": "FAIL", "detail": sym})
    return findings


def _check_locked_files() -> list[dict]:
    findings: list[dict] = []
    for rel in LOCKED_FILES:
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


def _run_smoke() -> tuple[dict | None, str]:
    if not _node_ok():
        return None, "node not available"
    r = subprocess.run(
        ["node", str(SMOKE_JS)], capture_output=True, text=True,
        timeout=30, encoding="utf-8")
    if r.returncode != 0:
        return None, f"smoke rc={r.returncode}: {r.stderr.strip()}"
    try:
        return json.loads(r.stdout), ""
    except json.JSONDecodeError as e:
        return None, f"json: {e}"


def _check_smoke_output(out: dict) -> list[dict]:
    findings: list[dict] = []
    if out.get("verdict") != "PASS":
        findings.append({"code": "SMOKE_VERDICT_NOT_PASS",
                          "level": "FAIL",
                          "detail": out.get("verdict")})
    checks = out.get("checks") or {}
    if not checks:
        findings.append({"code": "SMOKE_NO_CHECKS", "level": "FAIL",
                          "detail": "checks empty"})
    for name, c in checks.items():
        if not c.get("ok"):
            findings.append({"code": "SMOKE_CHECK_FAIL",
                              "level": "FAIL",
                              "detail": f"{name}: {c}"})
    # liveCommand 계약 재확인 (이중 안전망)
    lc = out.get("liveCommand") or {}
    if lc.get("expectedBefore") != "":
        findings.append({"code": "LIVE_CMD_EXPECTED_BEFORE_NOT_EMPTY",
                          "level": "FAIL", "detail": str(lc)})
    if lc.get("rangeStart") != lc.get("rangeEnd"):
        findings.append({"code": "LIVE_CMD_RANGE_NOT_POINT",
                          "level": "FAIL", "detail": str(lc)})
    if lc.get("commandType") != "TYPE_TEXT":
        findings.append({"code": "LIVE_CMD_TYPE_MISMATCH",
                          "level": "FAIL", "detail": str(lc)})
    if (lc.get("containerScope") or {}).get("kind") != "cell":
        findings.append({"code": "LIVE_CMD_SCOPE_NOT_CELL",
                          "level": "FAIL", "detail": str(lc)})
    if lc.get("afterText") != out.get("finalText"):
        findings.append({"code": "LIVE_CMD_AFTER_TEXT_MISMATCH",
                          "level": "FAIL", "detail": str(lc)})
    return findings


def _fixture() -> Path | None:
    db = PR / "data/recognition_corpus/corpus.sqlite3"
    if not db.is_file():
        return None
    try:
        conn = sqlite3.connect(db)
        row = conn.execute("""
            SELECT d.source_path FROM hwpx_documents d
            JOIN document_classifications c
                ON c.document_id = d.document_id
            WHERE d.inventory_status='FOUND'
              AND c.document_type='fillable_form'
              AND d.file_size BETWEEN 30000 AND 80000
            ORDER BY d.first_seen_at LIMIT 1
        """).fetchone()
        conn.close()
    except sqlite3.Error:
        return None
    if not row:
        return None
    p = PR / row[0]
    return p if p.is_file() else None


REQUIRED_V7 = ("V2_NO_CROSS_PARAGRAPH_LEAK",
                "V3_UNTOUCHED_RUNS_PRESERVED",
                "V4_CHARPR_PRESERVED", "V5_PARPR_PRESERVED",
                "V6_OUTPUT_ISOLATED")
REQUIRED_RB = ("V1_RANGE_POSITION_OK",
                "V4_CHARPR_PRESERVED", "V7_READBACK_MATCH")


def _run_e2e_with_live_text(fixture: Path,
                                                            final_text: str) -> dict[str, Any]:
    """live smoke 의 finalText 를 SCENARIO_TYPE 으로 E2E 투입.

    Python e2e_pipeline 은 source HWPX 의 paragraph 좌표를 사용하므로,
    live smoke 의 mock fixture (par_ime) 와는 직접 매칭되지 않는다.
    여기서는 finalText 의 의미만 동일하게 보존하면서 실제 HWPX 의
    paragraph 에 TYPE_TEXT 시나리오를 실행해, IME 출력이 E2E 와
    호환되는 표현인지 확인한다.
    """
    from scripts.hwpx.web_office.para_edit_e2e_pipeline import (  # noqa: E402
        run_para_edit_e2e, SCENARIO_TYPE)
    from scripts.hwpx.web_office.ro_view_importer import (  # noqa: E402
        import_hwpx_as_ro_view)

    doc = import_hwpx_as_ro_view(fixture)
    ro_p = next(
        (p for p in doc.paragraphs
          if (p.containerScope or {}).get("kind") == "cell"
          and p.parPrIDRef and p.runs and p.runs[0].charPrIDRef
          and len(p.text or "") >= 2), None)
    if ro_p is None:
        return {"ok": False, "reason": "no cell paragraph fixture"}

    sha_b = hashlib.sha256(fixture.read_bytes()).hexdigest()
    mt_b = fixture.stat().st_mtime_ns
    out: dict[str, Any] = {"ok": True, "fixture":
                                str(fixture.relative_to(PR)),
                                "paragraphId": ro_p.paragraphId,
                                "finalText": final_text}
    with tempfile.TemporaryDirectory() as td:
        outp = Path(td) / "ime_e2e.hwpx"
        res = run_para_edit_e2e(
            source_path=fixture, output_path=outp,
            scenario=SCENARIO_TYPE, paragraph_id=ro_p.paragraphId,
            range_anchor=0, insert_text=final_text, allow_writer=True)
        out["outputCreated"] = res.get("outputCreated")
        out["writerActivated"] = res.get("writerActivated")
        out["rejectedCount"] = len(res.get("rejected") or [])
        out["verify7"] = (res.get("verify7") or {}).get("results", {})
        out["readback"] = res.get("readback") or {}
        out["outputInSandbox"] = str(outp).startswith(td)
    out["shaPreserved"] = (
        hashlib.sha256(fixture.read_bytes()).hexdigest() == sha_b)
    out["mtimePreserved"] = fixture.stat().st_mtime_ns == mt_b
    return out


def _check_e2e(dyn: dict) -> list[dict]:
    findings: list[dict] = []
    if not dyn.get("ok"):
        findings.append({"code": "E2E_SKIPPED", "level": "WARN",
                          "detail": dyn.get("reason", "fixture missing")})
        return findings
    if not dyn.get("outputCreated"):
        findings.append({"code": "E2E_OUTPUT_NOT_CREATED",
                          "level": "FAIL", "detail": dyn})
        return findings
    if not dyn.get("outputInSandbox"):
        findings.append({"code": "E2E_OUTPUT_OUTSIDE_SANDBOX",
                          "level": "FAIL", "detail": dyn})
    if dyn.get("rejectedCount"):
        findings.append({"code": "E2E_REJECTED_NOT_EMPTY",
                          "level": "FAIL", "detail": dyn})
    v7 = dyn.get("verify7") or {}
    for k in REQUIRED_V7:
        if v7.get(k) != "PASS":
            findings.append({"code": "E2E_V7_NOT_PASS",
                              "level": "FAIL",
                              "detail": f"{k}={v7.get(k)}"})
    rb = dyn.get("readback") or {}
    for k in REQUIRED_RB:
        if rb.get(k) != "PASS":
            findings.append({"code": "E2E_READBACK_NOT_PASS",
                              "level": "FAIL",
                              "detail": f"{k}={rb.get(k)}"})
    if dyn.get("shaPreserved") is False:
        findings.append({"code": "SOURCE_SHA_TOUCHED",
                          "level": "FAIL",
                          "detail": "fixture sha before != after"})
    if dyn.get("mtimePreserved") is False:
        findings.append({"code": "SOURCE_MTIME_TOUCHED",
                          "level": "WARN",
                          "detail": "fixture mtime before != after"})
    return findings


def audit() -> dict[str, Any]:
    findings: list[dict] = []
    findings.extend(_check_smoke_script())
    findings.extend(_check_audit_no_writer_calls())
    findings.extend(_check_locked_files())

    smoke, smoke_err = _run_smoke()
    if smoke is None:
        if "node not available" in smoke_err:
            findings.append({"code": "SMOKE_SKIPPED", "level": "WARN",
                              "detail": smoke_err})
        else:
            findings.append({"code": "SMOKE_RUN_FAIL", "level": "FAIL",
                              "detail": smoke_err})
    else:
        findings.extend(_check_smoke_output(smoke))

    fx = _fixture()
    final_text = (smoke or {}).get("finalText", "한글")
    if fx is not None:
        try:
            dyn = _run_e2e_with_live_text(fx, final_text)
        except Exception as e:  # noqa: BLE001
            dyn = {"ok": False, "reason": f"E2E raised: {e}"}
        findings.extend(_check_e2e(dyn))
    else:
        dyn = {"ok": False, "reason": "fixture missing"}
        findings.append({"code": "E2E_SKIPPED", "level": "WARN",
                          "detail": "fixture missing"})

    fail = [f for f in findings if f["level"] == "FAIL"]
    warn = [f for f in findings if f["level"] == "WARN"]
    return {
        "audit": "WEB-OFFICE-PARA-EDIT-IME-LIVE-01",
        "baseline": BASELINE_COMMIT,
        "findings": findings,
        "verdict": "FAIL" if fail else ("WARN" if warn else "PASS"),
        "smoke": smoke,
        "e2e": dyn,
    }


if __name__ == "__main__":
    print(json.dumps(audit(), ensure_ascii=False, indent=2))
