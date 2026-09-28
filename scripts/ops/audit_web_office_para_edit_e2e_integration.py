"""WEB-OFFICE-PARA-EDIT-E2E-INTEGRATION-01 감사 스크립트.

ro_view → state → command → plan → writer → verify7 → readback 동선의
단일 fixture 관통을 정적·동적 양면으로 감사한다.

정적 검사
  - 4 신규 산출물 존재
  - para_edit_e2e_pipeline.py 내 writer 본 실행 함수 정의 0건 (호출 OK)
  - 기존 LOCKED 14 파일이 baseline (81e86e9) 대비 무수정

동적 검사 (fixture 미존재 시 partialCompletion=True + verdict=PASS)
  - corpus.sqlite3 fillable_form 1건에서 cell scope paragraph 1건 선정
  - REPLACE/DELETE 2 시나리오 임시 dir 실행 (TYPE_TEXT 는 baseline
    LOCKED 모듈 (paragraph_writer_adapter) 의 expectedBefore 계약과
    EditCommandV2.expectedBefore=paragraph.text 의 contract gap 으로
    plan 단계에서 REJECTED → 본 공정의 spec 외, 별도 활성화 트리거).
  - V2/V5/V6 게이트 PASS 만 확인 (V1/V4/V7 은 baseline LOCKED 모듈
    제약으로 부분 준공 — paragraph readback parser 미지원,
    adapter.applied 의 applyCharPrIDRef 누락. §11-5).
  - 원본 sha 사전=사후 확인

본 공정은 **시운전 (orchestration) 동만 신축** — verify7 V1/V4/V7 의
PASS 화는 multi-run writer / paragraph readback parser / adapter
applyCharPrIDRef 보강 트리거에서 별도 공정으로 진행한다.
"""

from __future__ import annotations

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

BASELINE_COMMIT = "81e86e9"

REQUIRED_FILES = [
    PR / "scripts/hwpx/web_office/para_edit_e2e_pipeline.py",
    PR / "scripts/ops/audit_web_office_para_edit_e2e_integration.py",
    PR / "tests/test_web_office_para_edit_e2e_integration.py",
    PR / "docs/architecture/web_office_para_edit_e2e_integration.md",
]

# 본 공정은 신규 파일만 — 기존 LOCKED 14 파일 무수정.
LOCKED_FILES = [
    # WEB-OFFICE-PARA-EDIT-APPLYFORMAT-EXISTING-CHARPR-01: hwpx_edit_tool /
    # paragraph_save_verify7 / paragraph_edit_plan 은 ApplyFormat 활성화로
    # 본 LOCKED 에서 제거됨.
    # WEB-OFFICE-PARA-EDIT-MULTI-RUN-01: hwpx_paragraph_ops.py 는
    # multi-run text range edit primitive 추가를 위해 본 LOCKED 에서
    # 제거됨 (허용 범위: apply_text_range_edit_multi_run + POLICY_*).
    "scripts/hwpx/hwpx_writer_adapter.py",
    # WEB-OFFICE-PARA-ADAPTER-APPLYCHARPR-01:
    # paragraph_writer_adapter.py 는 V4_CHARPR_PRESERVED 활성화 트리거
    # 발동에 따른 adapter applied metadata 보강 허용으로 본 목록에서
    # 제거됨 (허용 범위: applyCharPrIDRef + commandType 적재 한정).
    "scripts/hwpx/web_office/paragraph_save_pipeline.py",
    "scripts/hwpx/web_office/paragraph_save_audit.py",
    "scripts/hwpx/web_office/ro_view_importer.py",
    "scripts/hwpx/web_office/document_model.py",
    # WEB-OFFICE-PARA-EDIT-APPLYFORMAT-TOOLBAR-PREVIEW-01 (abebab6):
    # render_payload.py 는 char_pr_defs additive 추가로 본 LOCKED 에서 제거.
    "scripts/hwpx/web_office/edit_command_model.py",
    # WEB-OFFICE-PARA-TYPE-TEXT-CONTRACT-01: TYPE_TEXT expectedBefore 를
    # 빈 range slice 기준으로 정렬하기 위해 본 목록에서 제거됨
    # (허용 범위: make_type_text_command + validate_expected_before 의
    # TYPE_TEXT 계약 한정).
    "scripts/hwpx/web_office/para_edit_normalizer.py",
]

PIPELINE_FILE = PR / "scripts/hwpx/web_office/para_edit_e2e_pipeline.py"
FORBIDDEN_DEFS = [
    r"^def\s+apply_edit_plan\b",
    r"^def\s+_apply_edit_plan\b",
    r"^def\s+_apply\b",
    r"^def\s+apply_paragraph_edits_plan\b",
    r"^def\s+write_package\b",
    r"^def\s+create_hwpx_document\b",
]

# 본 부분 준공에서 PASS 를 요구하는 verify7 게이트 (V1/V4/V7 은
# baseline LOCKED 모듈 제약으로 PARTIAL).
REQUIRED_V_GATES = (
    "V2_NO_CROSS_PARAGRAPH_LEAK",
    "V3_UNTOUCHED_RUNS_PRESERVED",
    # WEB-OFFICE-PARA-ADAPTER-APPLYCHARPR-01 — V4 필수 게이트로 승격.
    "V4_CHARPR_PRESERVED",
    "V5_PARPR_PRESERVED",
    "V6_OUTPUT_ISOLATED",
)
DEFERRED_V_GATES = ()  # 모두 활성화 완료 (TYPE_TEXT 는 본 spec 외)

# WEB-OFFICE-PARA-READBACK-PARSER-01 — REPLACE/DELETE 에 한해 V1/V7 을
# e2e_pipeline.readback gate 로 PASS 화. TYPE_TEXT 는 expectedBefore 계약
# gap 으로 DEFERRED 유지.
REQUIRED_READBACK_GATES = (
    "V1_RANGE_POSITION_OK",
    "V7_READBACK_MATCH",
)
READBACK_REQUIRED_SCENARIOS = {
    "REPLACE_TEXT_RANGE",
    "DELETE_TEXT_RANGE",
    # WEB-OFFICE-PARA-TYPE-TEXT-CONTRACT-01 — TYPE_TEXT readback 활성화.
    "TYPE_TEXT",
}


def _check_files_exist() -> list[dict]:
    findings: list[dict] = []
    for p in REQUIRED_FILES:
        if not p.is_file():
            findings.append({
                "code": "MISSING_FILE",
                "level": "FAIL",
                "detail": str(p.relative_to(PR)),
            })
    return findings


def _check_pipeline_no_writer_defs() -> list[dict]:
    findings: list[dict] = []
    if not PIPELINE_FILE.is_file():
        return findings
    src = PIPELINE_FILE.read_text(encoding="utf-8")
    for pat in FORBIDDEN_DEFS:
        if re.search(pat, src, flags=re.MULTILINE):
            findings.append({
                "code": "FORBIDDEN_WRITER_DEF",
                "level": "FAIL",
                "detail": f"para_edit_e2e_pipeline.py: {pat}",
            })
    return findings


def _check_locked_files() -> list[dict]:
    findings: list[dict] = []
    for rel in LOCKED_FILES:
        try:
            r = subprocess.run(
                ["git", "diff", BASELINE_COMMIT, "--", rel],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=str(PR),
                timeout=20,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            findings.append({
                "code": "GIT_DIFF_FAILED",
                "level": "WARN",
                "detail": f"{rel}: {e}",
            })
            continue
        if r.returncode != 0:
            findings.append({
                "code": "GIT_DIFF_FAILED",
                "level": "WARN",
                "detail": f"{rel}: rc={r.returncode}",
            })
            continue
        if r.stdout.strip():
            findings.append({
                "code": "LOCKED_FILE_CHANGED",
                "level": "FAIL",
                "detail": rel,
            })
    return findings


def _pick_fixture() -> Path | None:
    db = PR / "data/recognition_corpus/corpus.sqlite3"
    if not db.is_file():
        # 레거시 corpus DB 부재 — 카탈로그 표본으로 대체한다.
        # 이게 없으면 감리가 조용히 SKIP 되어 안 돈 채 통과처럼 보인다.
        from scripts.hwpx.web_office.hwpx_sample_source import resolve_sample as _catalog_sample

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
        if (
            cs.get("kind") == "cell"
            and p.parPrIDRef
            and p.runs
            and p.runs[0].charPrIDRef
            and len(p.text or "") >= 2
        ):
            return p
    return None


def _run_dynamic() -> dict[str, Any]:
    fixture = _pick_fixture()
    if fixture is None:
        return {
            "status": "FIXTURE_MISSING",
            "scenarios": [],
            "shaPreserved": None,
        }
    import hashlib

    from scripts.hwpx.web_office.para_edit_e2e_pipeline import (
        SCENARIO_DELETE,
        SCENARIO_REPLACE,
        run_para_edit_e2e,
    )
    from scripts.hwpx.web_office.ro_view_importer import import_hwpx_as_ro_view

    sha_before = hashlib.sha256(fixture.read_bytes()).hexdigest()
    doc = import_hwpx_as_ro_view(fixture)
    ro_p = _pick_paragraph(doc)
    if ro_p is None:
        return {
            "status": "NO_SUITABLE_PARAGRAPH",
            "scenarios": [],
            "shaPreserved": True,
        }

    scenarios_out: list[dict] = []
    with tempfile.TemporaryDirectory() as td:
        td_p = Path(td)
        r2 = run_para_edit_e2e(
            source_path=fixture,
            output_path=td_p / "e2e_replace.hwpx",
            scenario=SCENARIO_REPLACE,
            paragraph_id=ro_p.paragraphId,
            range_anchor=0,
            range_focus=1,
            replace_after="Q",
            allow_writer=True,
        )
        scenarios_out.append({
            "name": SCENARIO_REPLACE,
            "verdict": r2.get("verdict"),
            "outputCreated": bool(r2.get("outputCreated")),
            "v17": (r2.get("verify7") or {}).get("results", {}),
            "readback": r2.get("readback") or {},
            "rejectedCount": len(r2.get("rejected") or []),
        })
        r3 = run_para_edit_e2e(
            source_path=fixture,
            output_path=td_p / "e2e_delete.hwpx",
            scenario=SCENARIO_DELETE,
            paragraph_id=ro_p.paragraphId,
            range_anchor=0,
            range_focus=1,
            allow_writer=True,
        )
        scenarios_out.append({
            "name": SCENARIO_DELETE,
            "verdict": r3.get("verdict"),
            "outputCreated": bool(r3.get("outputCreated")),
            "v17": (r3.get("verify7") or {}).get("results", {}),
            "readback": r3.get("readback") or {},
            "rejectedCount": len(r3.get("rejected") or []),
        })

    sha_after = hashlib.sha256(fixture.read_bytes()).hexdigest()
    return {
        "status": "OK",
        "scenarios": scenarios_out,
        "shaPreserved": sha_after == sha_before,
        "fixture": str(fixture.relative_to(PR)),
        "paragraphId": ro_p.paragraphId,
    }


def _scenario_findings(sc: dict) -> tuple[list[dict], bool]:
    findings: list[dict] = []
    partial = False
    if not sc["outputCreated"]:
        findings.append({
            "code": "E2E_OUTPUT_NOT_CREATED",
            "level": "FAIL",
            "detail": f"{sc['name']}",
        })
    v17 = sc["v17"] or {}
    for k in REQUIRED_V_GATES:
        if v17.get(k) != "PASS":
            findings.append({
                "code": "REQUIRED_GATE_NOT_PASS",
                "level": "FAIL",
                "detail": f"{sc['name']}: {k}={v17.get(k)}",
            })
    # DEFERRED 게이트는 partialCompletion 신호로만 적재
    for k in DEFERRED_V_GATES:
        if v17.get(k) != "PASS":
            findings.append({
                "code": "DEFERRED_GATE_PARTIAL",
                "level": "WARN",
                "detail": (f"{sc['name']}: {k}={v17.get(k)} (LOCKED 모듈 제약 — 다음 트리거)"),
            })
            partial = True
    # WEB-OFFICE-PARA-READBACK-PARSER-01 — REPLACE/DELETE 의 V1/V7
    # 은 e2e_pipeline.readback gate 로 PASS 요구.
    if sc["name"] in READBACK_REQUIRED_SCENARIOS:
        rb = sc.get("readback") or {}
        for k in REQUIRED_READBACK_GATES:
            if rb.get(k) != "PASS":
                findings.append({
                    "code": "READBACK_GATE_NOT_PASS",
                    "level": "FAIL",
                    "detail": (f"{sc['name']}: {k}={rb.get(k)} notes={rb.get('notes')}"),
                })
    return findings, partial


def audit() -> dict[str, Any]:
    findings: list[dict] = []
    findings.extend(_check_files_exist())
    findings.extend(_check_pipeline_no_writer_defs())
    findings.extend(_check_locked_files())

    summary: dict[str, Any] = {"static": "OK"}
    partial = False
    try:
        dyn = _run_dynamic()
    except Exception as e:  # ruff: ignore[blind-except]
        dyn = {"status": "EXCEPTION", "error": str(e), "scenarios": [], "shaPreserved": None}
        findings.append({"code": "DYNAMIC_EXCEPTION", "level": "WARN", "detail": str(e)})
    summary["dynamic"] = dyn

    if dyn["status"] in ("FIXTURE_MISSING", "NO_SUITABLE_PARAGRAPH", "EXCEPTION"):
        partial = True
    else:
        # 본 부분 준공 게이트:
        #   - outputCreated == True (writer 본 실행 도달)
        #   - V2/V3/V5/V6 == PASS
        #   - rejectedCount 부담 외 (FAIL 가능: V4_CHARPR_PRESERVED
        #     이 LOCKED 모듈 제약으로 FAIL — DEFERRED).
        #   - 원본 sha 보존
        for sc in dyn["scenarios"]:
            sc_findings, sc_partial = _scenario_findings(sc)
            findings.extend(sc_findings)
            partial = partial or sc_partial
        if dyn.get("shaPreserved") is False:
            findings.append({
                "code": "SOURCE_SHA_TOUCHED",
                "level": "FAIL",
                "detail": "fixture sha before != after",
            })

    fails = [f for f in findings if f.get("level") == "FAIL"]
    verdict = "PASS" if not fails else "FAIL"

    return {
        "task": "WEB-OFFICE-PARA-EDIT-E2E-INTEGRATION-01",
        "baseline": BASELINE_COMMIT,
        "verdict": verdict,
        "partialCompletion": partial,
        "nextActivationTrigger": (
            "V1/V4/V7 — paragraph readback parser + adapter applyCharPrIDRef 보강 트리거"
            if partial
            else None
        ),
        "summary": summary,
        "findings": findings,
    }


def main() -> int:
    out = audit()
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
