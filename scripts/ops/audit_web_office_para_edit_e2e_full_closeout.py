"""WEB-OFFICE-PARA-EDIT-E2E-FULL-CLOSEOUT-01 정식 준공검사.

cell containerScope · 단일 run 범위에서 PARA-EDIT E2E (TYPE_TEXT /
REPLACE_TEXT_RANGE / DELETE_TEXT_RANGE / SET_CELL_TEXT) 가 V1~V7 PASS
상태임을 정적·동적으로 확인한다.

본 공정은 신규 writer 기능을 시공하지 않는다. 따라서 본 audit 는
새로운 HWPX output 을 만들지 않고, 기존 자재의 존재·구조·게이트만
정적으로 검증하며, 동적 신호는 fixture 가용 시 sandbox tmp_path 안에서만
수집한다.
"""
from __future__ import annotations
import hashlib
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any

PR = Path(__file__).resolve().parents[2]
if str(PR) not in sys.path:
    sys.path.insert(0, str(PR))

CLOSEOUT_DOC = (PR / "docs/architecture/"
                   "web_office_para_edit_e2e_full_closeout.md")

REQUIRED_DOCS = [
    CLOSEOUT_DOC,
    PR / "docs/architecture/web_office_para_edit_risk_ledger_update.md",
    PR / "docs/architecture/web_office_para_edit_e2e_integration.md",
    PR / "docs/architecture/web_office_para_edit_spec.md",
]

# 본 공정은 시방서 + audit + test 만 신축. 기존 자재 무수정 잠금.
LOCKED_FILES = [
    # WEB-OFFICE-PARA-EDIT-APPLYFORMAT-EXISTING-CHARPR-01:
    # para_edit_model / paragraph_edit_plan / paragraph_save_verify7 /
    # para_edit_e2e_pipeline / para_edit_command.mjs 는 ApplyFormat
    # 활성화로 본 LOCKED 에서 제거됨.
    "scripts/hwpx/web_office/paragraph_save_pipeline.py",
    "scripts/hwpx/web_office/ro_view_importer.py",
    "scripts/hwpx/web_office/document_model.py",
    "scripts/hwpx/web_office/edit_command_model.py",
    "scripts/hwpx/web_office/para_edit_normalizer.py",
    # WEB-OFFICE-PARA-EDIT-APPLYFORMAT-TOOLBAR-COMMAND-01:
    # para_edit_state.mjs 는 applyFormatToSelection 추가로 본 LOCKED 에서 제거.
]
BASELINE_COMMIT = "56dc073"

# 안전 게이트가 코드에 존재하는지 정적 검증
SAFETY_GATE_PATTERNS = {
    PR / "scripts/hwpx/web_office/paragraph_save_pipeline.py": [
        r"OUTPUT_EQUALS_SOURCE",
    ],
    PR / "scripts/hwpx/web_office/paragraph_writer_adapter.py": [
        r"BODY_PARAGRAPH_NOT_SUPPORTED",
        r"MULTI_RUN_RANGE_NOT_SUPPORTED",
        r"REASON_CHARPR_MISMATCH",
        r"REASON_EXPECTED_BEFORE_MISMATCH",
    ],
    PR / "scripts/hwpx/web_office/para_edit_e2e_pipeline.py": [
        r"_READBACK_SCENARIOS",
        r"SCENARIO_TYPE",
        r"SCENARIO_REPLACE",
        r"SCENARIO_DELETE",
        r"applied=∅",  # vacuous PASS 차단 신호
    ],
}

# 문서에 등기되어야 하는 키 문구 — 준공 범위 잠금
DOC_REQUIRED_PHRASES = [
    "SET_CELL_TEXT", "TYPE_TEXT", "REPLACE_TEXT_RANGE",
    "DELETE_TEXT_RANGE",
    "V1_RANGE_POSITION_OK", "V2_NO_CROSS_PARAGRAPH_LEAK",
    "V3_UNTOUCHED_RUNS_PRESERVED", "V4_CHARPR_PRESERVED",
    "V5_PARPR_PRESERVED", "V6_OUTPUT_ISOLATED",
    "V7_READBACK_MATCH",
    "MULTI_RUN_RANGE_NOT_SUPPORTED",
    "BODY_PARAGRAPH_NOT_SUPPORTED",
    "OUTPUT_EQUALS_SOURCE",
    "cell containerScope",
    "단일 run",
    "RISK-LEDGER",
]

# 본 공정에서 신규 생성을 금지하는 writer 함수들 — 본 audit 자체에서도
# 우발적으로 import / 호출되지 않음을 보장
FORBIDDEN_WRITER_SYMBOLS = [
    r"apply_paragraph_edits_plan\(",
    r"save_paragraph_edits\(",
    r"create_hwpx_document\(",
    r"write_package\(",
]


def _check_required_docs() -> list[dict]:
    findings: list[dict] = []
    for p in REQUIRED_DOCS:
        if not p.is_file():
            findings.append({
                "code": "MISSING_DOC", "level": "FAIL",
                "detail": str(p.relative_to(PR))})
    return findings


def _check_closeout_doc_phrases() -> list[dict]:
    findings: list[dict] = []
    if not CLOSEOUT_DOC.is_file():
        return findings
    src = CLOSEOUT_DOC.read_text(encoding="utf-8")
    for phrase in DOC_REQUIRED_PHRASES:
        if phrase not in src:
            findings.append({
                "code": "DOC_PHRASE_MISSING", "level": "FAIL",
                "detail": phrase})
    return findings


def _check_safety_gate_patterns() -> list[dict]:
    findings: list[dict] = []
    for path, patterns in SAFETY_GATE_PATTERNS.items():
        if not path.is_file():
            findings.append({"code": "SAFETY_FILE_MISSING",
                              "level": "FAIL",
                              "detail": str(path.relative_to(PR))})
            continue
        src = path.read_text(encoding="utf-8")
        for pat in patterns:
            if not re.search(pat, src):
                findings.append({
                    "code": "SAFETY_GATE_PATTERN_MISSING",
                    "level": "FAIL",
                    "detail": f"{path.relative_to(PR)}: {pat}"})
    return findings


def _check_audit_no_writer_calls() -> list[dict]:
    """본 audit 모듈 자체가 writer 호출/import 를 하지 않음을 보장."""
    findings: list[dict] = []
    me = Path(__file__).read_text(encoding="utf-8")
    for sym in FORBIDDEN_WRITER_SYMBOLS:
        if re.search(sym, me):
            findings.append({
                "code": "AUDIT_FORBIDDEN_WRITER_CALL",
                "level": "FAIL", "detail": sym})
    return findings


def _check_locked_files() -> list[dict]:
    """본 공정 baseline 이후 LOCKED 파일이 무수정인지 확인."""
    import subprocess  # noqa: WPS433
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
            findings.append({"code": "GIT_DIFF_RC",
                              "level": "WARN",
                              "detail": f"{rel}: rc={r.returncode}"})
            continue
        if r.stdout.strip():
            findings.append({"code": "LOCKED_FILE_CHANGED",
                              "level": "FAIL", "detail": rel})
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


def _run_dynamic_e2e(fixture: Path) -> dict[str, Any]:
    import tempfile  # noqa: WPS433
    from scripts.hwpx.web_office.para_edit_e2e_pipeline import (  # noqa: E402
        run_para_edit_e2e, SCENARIO_TYPE, SCENARIO_REPLACE,
        SCENARIO_DELETE)
    from scripts.hwpx.web_office.ro_view_importer import (  # noqa: E402
        import_hwpx_as_ro_view)

    doc = import_hwpx_as_ro_view(fixture)
    ro_p = next(
        (p for p in doc.paragraphs
          if (p.containerScope or {}).get("kind") == "cell"
          and p.parPrIDRef and p.runs and p.runs[0].charPrIDRef
          and len(p.text or "") >= 2),
        None)
    if ro_p is None:
        return {"ok": False, "reason": "no cell paragraph fixture"}

    sha_b = hashlib.sha256(fixture.read_bytes()).hexdigest()
    mt_b = fixture.stat().st_mtime_ns
    out: dict[str, Any] = {
        "ok": True, "scenarios": [],
        "paragraphId": ro_p.paragraphId,
        "fixture": str(fixture.relative_to(PR)),
    }

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        for scn, kw in [
            (SCENARIO_TYPE, {"insert_text": "T"}),
            (SCENARIO_REPLACE, {"range_focus": 1, "replace_after": "R"}),
            (SCENARIO_DELETE, {"range_focus": 1}),
        ]:
            outp = td_path / f"closeout_{scn}.hwpx"
            res = run_para_edit_e2e(
                source_path=fixture, output_path=outp,
                scenario=scn, paragraph_id=ro_p.paragraphId,
                range_anchor=0, allow_writer=True, **kw)
            v7 = (res.get("verify7") or {}).get("results", {})
            rb = res.get("readback") or {}
            out["scenarios"].append({
                "scenario": scn,
                "outputCreated": res.get("outputCreated"),
                "writerActivated": res.get("writerActivated"),
                "rejectedCount": len(res.get("rejected") or []),
                "verify7": v7, "readback": rb,
                "outputInSandbox": str(outp).startswith(str(td_path)),
            })

    out["shaPreserved"] = (
        hashlib.sha256(fixture.read_bytes()).hexdigest() == sha_b)
    out["mtimePreserved"] = fixture.stat().st_mtime_ns == mt_b
    return out


def _check_dynamic(dyn: dict) -> list[dict]:
    findings: list[dict] = []
    if not dyn.get("ok"):
        findings.append({"code": "DYNAMIC_SKIPPED", "level": "WARN",
                          "detail": dyn.get("reason", "fixture missing")})
        return findings
    expected_scns = {"TYPE_TEXT", "REPLACE_TEXT_RANGE",
                      "DELETE_TEXT_RANGE"}
    actual = {sc["scenario"] for sc in dyn["scenarios"]}
    if actual != expected_scns:
        findings.append({"code": "SCENARIO_SET_MISMATCH",
                          "level": "FAIL",
                          "detail": f"actual={sorted(actual)}"})
    for sc in dyn["scenarios"]:
        name = sc["scenario"]
        if not sc["outputCreated"]:
            findings.append({"code": "OUTPUT_NOT_CREATED",
                              "level": "FAIL", "detail": name})
            continue
        if not sc.get("outputInSandbox"):
            findings.append({"code": "OUTPUT_OUTSIDE_SANDBOX",
                              "level": "FAIL", "detail": name})
        if sc["rejectedCount"]:
            findings.append({"code": "REJECTED_NOT_EMPTY",
                              "level": "FAIL", "detail": name})
        v7 = sc["verify7"]
        for k in REQUIRED_V7:
            if v7.get(k) != "PASS":
                findings.append({"code": "V7_NOT_PASS", "level": "FAIL",
                                  "detail": f"{name}: {k}={v7.get(k)}"})
        rb = sc["readback"]
        for k in REQUIRED_RB:
            if rb.get(k) != "PASS":
                findings.append({"code": "READBACK_NOT_PASS",
                                  "level": "FAIL",
                                  "detail": f"{name}: {k}={rb.get(k)}"})
    if dyn.get("shaPreserved") is False:
        findings.append({"code": "SOURCE_SHA_TOUCHED", "level": "FAIL",
                          "detail": "fixture sha before != after"})
    if dyn.get("mtimePreserved") is False:
        findings.append({"code": "SOURCE_MTIME_TOUCHED", "level": "WARN",
                          "detail": "fixture mtime before != after"})
    return findings


def audit() -> dict[str, Any]:
    findings: list[dict] = []
    findings.extend(_check_required_docs())
    findings.extend(_check_closeout_doc_phrases())
    findings.extend(_check_safety_gate_patterns())
    findings.extend(_check_audit_no_writer_calls())
    findings.extend(_check_locked_files())

    fx = _fixture()
    dyn: dict[str, Any] = {"ok": False, "reason": "fixture missing"}
    if fx is not None:
        try:
            dyn = _run_dynamic_e2e(fx)
        except Exception as e:  # noqa: BLE001
            findings.append({"code": "DYNAMIC_RAISED", "level": "FAIL",
                              "detail": str(e)})
    findings.extend(_check_dynamic(dyn))

    fail = [f for f in findings if f["level"] == "FAIL"]
    warn = [f for f in findings if f["level"] == "WARN"]
    return {
        "audit": "WEB-OFFICE-PARA-EDIT-E2E-FULL-CLOSEOUT-01",
        "baseline": BASELINE_COMMIT,
        "findings": findings,
        "verdict": "FAIL" if fail else ("WARN" if warn else "PASS"),
        "dynamic": dyn,
    }


if __name__ == "__main__":
    import json
    print(json.dumps(audit(), ensure_ascii=False, indent=2))
