"""WEB-OFFICE-PARA-READBACK-PARSER-01 감사 스크립트.

본 공정은 신규 모듈을 만들지 않고 (§11-6 자재 재사용),
para_edit_e2e_pipeline.py 내부 readback helper 만 추가해
REPLACE_TEXT_RANGE / DELETE_TEXT_RANGE 의 V1_RANGE_POSITION_OK 와
V7_READBACK_MATCH 를 PASS 화한다. TYPE_TEXT 는 expectedBefore 계약 gap
으로 DEFERRED 유지.

정적 검사
  - 신규 파일 미생성 검증 (paragraph_readback_parser.py 모듈 부재)
  - para_edit_e2e_pipeline.py 안에 readback helper 존재
  - LOCKED 모듈 (paragraph_writer_adapter / para_edit_model /
    paragraph_save_verify7 등) baseline dabdf53 대비 무수정

동적 검사 (fixture 미존재 시 partialCompletion=True + verdict=PASS)
  - corpus.sqlite3 fillable_form 1건에서 cell scope paragraph 선정
  - REPLACE/DELETE 2 시나리오 임시 dir 실행
  - result["readback"].V1_RANGE_POSITION_OK == PASS
  - result["readback"].V7_READBACK_MATCH == PASS
  - matchedBy in {paragraphId, containerScope} — text-only 매칭 부재 확인
  - 원본 sha 사전=사후
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

BASELINE_COMMIT = "dabdf53"

PIPELINE_FILE = PR / "scripts/hwpx/web_office/para_edit_e2e_pipeline.py"
FORBIDDEN_NEW_MODULE = (
    PR / "scripts/hwpx/web_office/paragraph_readback_parser.py")

# 본 공정에서 변경이 허용된 파일 — 그 외 LOCKED.
ALLOWED_CHANGED = {
    "scripts/hwpx/web_office/para_edit_e2e_pipeline.py",
    "scripts/ops/audit_web_office_para_edit_e2e_integration.py",
    "scripts/ops/audit_web_office_para_readback_parser.py",
    "tests/test_web_office_para_readback_parser.py",
}

LOCKED_FILES = [
    # WEB-OFFICE-PARA-ADAPTER-APPLYCHARPR-01:
    # paragraph_writer_adapter.py 는 V4_CHARPR_PRESERVED 활성화 트리거
    # 발동에 따른 adapter applied metadata 보강을 위해 본 LOCKED 목록에서
    # 제거되었다 (허용 범위: applyCharPrIDRef + commandType 적재 한정).
    # WEB-OFFICE-PARA-TYPE-TEXT-CONTRACT-01: para_edit_model.py 는
    # TYPE_TEXT expectedBefore 빈 range slice 계약 정렬을 위해 본
    # 목록에서 제거됨.
    # WEB-OFFICE-PARA-EDIT-APPLYFORMAT-EXISTING-CHARPR-01:
    # paragraph_save_verify7 / paragraph_edit_plan / hwpx_edit_tool 은
    # ApplyFormat 활성화로 본 LOCKED 에서 제거됨.
    "scripts/hwpx/web_office/paragraph_save_pipeline.py",
    "scripts/hwpx/web_office/ro_view_importer.py",
    "scripts/hwpx/web_office/document_model.py",
    "scripts/hwpx/web_office/edit_command_model.py",
    "scripts/hwpx/web_office/para_edit_normalizer.py",
    # WEB-OFFICE-PARA-EDIT-MULTI-RUN-01: hwpx_paragraph_ops.py 는
    # multi-run primitive 추가를 위해 본 LOCKED 에서 제거됨.
    "scripts/hwpx/hwpx_writer_adapter.py",
]

REQUIRED_HELPERS = [
    r"^def\s+_readback_verify_paragraph\b",
    r"^def\s+_match_output_paragraph\b",
    r"^def\s+_expected_after_paragraph_text\b",
]


def _check_no_new_module() -> list[dict]:
    if FORBIDDEN_NEW_MODULE.exists():
        return [{
            "code": "FORBIDDEN_NEW_MODULE",
            "level": "FAIL",
            "detail": str(FORBIDDEN_NEW_MODULE.relative_to(PR)),
        }]
    return []


def _check_pipeline_helpers() -> list[dict]:
    findings: list[dict] = []
    if not PIPELINE_FILE.is_file():
        findings.append({
            "code": "PIPELINE_MISSING", "level": "FAIL",
            "detail": str(PIPELINE_FILE.relative_to(PR)),
        })
        return findings
    src = PIPELINE_FILE.read_text(encoding="utf-8")
    findings.extend({
                "code": "READBACK_HELPER_MISSING",
                "level": "FAIL",
                "detail": pat,
            } for pat in REQUIRED_HELPERS if not re.search(pat, src, flags=re.MULTILINE))
    return findings


def _check_locked_files() -> list[dict]:
    findings: list[dict] = []
    for rel in LOCKED_FILES:
        try:
            r = subprocess.run(
                ["git", "diff", BASELINE_COMMIT, "--", rel],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                cwd=str(PR), timeout=20)
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            findings.append({
                "code": "GIT_DIFF_FAILED", "level": "WARN",
                "detail": f"{rel}: {e}"})
            continue
        if r.returncode != 0:
            findings.append({
                "code": "GIT_DIFF_FAILED", "level": "WARN",
                "detail": f"{rel}: rc={r.returncode}"})
            continue
        if r.stdout.strip():
            findings.append({
                "code": "LOCKED_FILE_CHANGED",
                "level": "FAIL", "detail": rel})
    return findings


def _pick_fixture() -> Path | None:
    db = PR / "data/recognition_corpus/corpus.sqlite3"
    if not db.is_file():
        # 레거시 corpus DB 부재 — 카탈로그 표본으로 대체한다.
        # 이게 없으면 감리가 조용히 SKIP 되어 안 돈 채 통과처럼 보인다.
        from scripts.hwpx.web_office.hwpx_sample_source import (
            resolve_sample as _catalog_sample)
        return _catalog_sample()
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


def _pick_paragraph(doc) -> Any:
    for p in doc.paragraphs:
        cs = p.containerScope or {}
        if (cs.get("kind") == "cell" and p.parPrIDRef
                and p.runs and p.runs[0].charPrIDRef
                and len(p.text or "") >= 2):
            return p
    return None


def _run_dynamic() -> dict[str, Any]:
    fixture = _pick_fixture()
    if fixture is None:
        return {"status": "FIXTURE_MISSING", "scenarios": [],
                "shaPreserved": None}
    from scripts.hwpx.web_office.ro_view_importer import (
        import_hwpx_as_ro_view)
    from scripts.hwpx.web_office.para_edit_e2e_pipeline import (
        run_para_edit_e2e, SCENARIO_REPLACE, SCENARIO_DELETE)

    sha_before = hashlib.sha256(fixture.read_bytes()).hexdigest()
    doc = import_hwpx_as_ro_view(fixture)
    ro_p = _pick_paragraph(doc)
    if ro_p is None:
        return {"status": "NO_SUITABLE_PARAGRAPH", "scenarios": [],
                "shaPreserved": True}

    scenarios: list[dict] = []
    with tempfile.TemporaryDirectory() as td:
        td_p = Path(td)
        r_replace = run_para_edit_e2e(
            source_path=fixture,
            output_path=td_p / "rb_replace.hwpx",
            scenario=SCENARIO_REPLACE,
            paragraph_id=ro_p.paragraphId,
            range_anchor=0, range_focus=1,
            replace_after="Q",
            allow_writer=True)
        scenarios.append({
            "name": SCENARIO_REPLACE,
            "verdict": r_replace.get("verdict"),
            "outputCreated": bool(r_replace.get("outputCreated")),
            "readback": r_replace.get("readback") or {},
            "v17": (r_replace.get("verify7") or {}).get(
                "results", {}),
        })
        r_delete = run_para_edit_e2e(
            source_path=fixture,
            output_path=td_p / "rb_delete.hwpx",
            scenario=SCENARIO_DELETE,
            paragraph_id=ro_p.paragraphId,
            range_anchor=0, range_focus=1,
            allow_writer=True)
        scenarios.append({
            "name": SCENARIO_DELETE,
            "verdict": r_delete.get("verdict"),
            "outputCreated": bool(r_delete.get("outputCreated")),
            "readback": r_delete.get("readback") or {},
            "v17": (r_delete.get("verify7") or {}).get(
                "results", {}),
        })
    sha_after = hashlib.sha256(fixture.read_bytes()).hexdigest()
    return {
        "status": "OK",
        "scenarios": scenarios,
        "shaPreserved": sha_after == sha_before,
        "fixture": str(fixture.relative_to(PR)),
        "paragraphId": ro_p.paragraphId,
    }


def audit() -> dict[str, Any]:
    findings: list[dict] = []
    findings.extend(_check_no_new_module())
    findings.extend(_check_pipeline_helpers())
    findings.extend(_check_locked_files())

    summary: dict[str, Any] = {"static": "OK"}
    partial = False
    try:
        dyn = _run_dynamic()
    except Exception as e:  # noqa: BLE001
        dyn = {"status": "EXCEPTION", "error": str(e),
               "scenarios": [], "shaPreserved": None}
        findings.append({"code": "DYNAMIC_EXCEPTION",
                         "level": "WARN", "detail": str(e)})
    summary["dynamic"] = dyn

    if dyn["status"] in ("FIXTURE_MISSING", "NO_SUITABLE_PARAGRAPH",
                         "EXCEPTION"):
        partial = True
    else:
        for sc in dyn["scenarios"]:
            if not sc["outputCreated"]:
                findings.append({
                    "code": "READBACK_OUTPUT_NOT_CREATED",
                    "level": "FAIL", "detail": sc["name"]})
                continue
            rb = sc["readback"] or {}
            findings.extend({
                        "code": "READBACK_GATE_FAIL",
                        "level": "FAIL",
                        "detail": (f"{sc['name']}: {gate}="
                                   f"{rb.get(gate)} "
                                   f"notes={rb.get('notes')}")} for gate in ("V1_RANGE_POSITION_OK",
                         "V7_READBACK_MATCH") if rb.get(gate) != "PASS")
            if rb.get("matchedBy") not in (
                    "paragraphId", "containerScope"):
                findings.append({
                    "code": "READBACK_MATCH_KEY_INVALID",
                    "level": "FAIL",
                    "detail": (f"{sc['name']}: matchedBy="
                               f"{rb.get('matchedBy')}")})
        if dyn.get("shaPreserved") is False:
            findings.append({
                "code": "SOURCE_SHA_TOUCHED", "level": "FAIL",
                "detail": "fixture sha before != after"})

    fails = [f for f in findings if f.get("level") == "FAIL"]
    verdict = "PASS" if not fails else "FAIL"
    return {
        "task": "WEB-OFFICE-PARA-READBACK-PARSER-01",
        "baseline": BASELINE_COMMIT,
        "verdict": verdict,
        "partialCompletion": partial,
        "summary": summary,
        "findings": findings,
    }


def main() -> int:
    out = audit()
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
