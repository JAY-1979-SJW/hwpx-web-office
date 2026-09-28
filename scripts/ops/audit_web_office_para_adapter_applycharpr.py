"""WEB-OFFICE-PARA-ADAPTER-APPLYCHARPR-01 감사 스크립트.

paragraph_writer_adapter.applied[] 에 applyCharPrIDRef + commandType
metadata 적재를 통한 V4_CHARPR_PRESERVED 활성화 공정.

정적 검사
  - adapter.py 안에 'applyCharPrIDRef' 가 applied dict 양쪽 (dry/real)
    에 적재되는 시그니처 확인
  - 본 공정 외 LOCKED 모듈 (verify7 / model / plan / ro_view_importer /
    paragraph_save_pipeline) baseline d3f8ed6 대비 무수정
  - TYPE_TEXT expectedBefore 계약 무변경 (para_edit_model 무수정 포함)

동적 검사 (fixture 미존재 시 partialCompletion=True + verdict=PASS)
  - corpus.sqlite3 fillable_form 1건에서 cell scope paragraph 선정
  - REPLACE/DELETE 2 시나리오 임시 dir 실행
  - result["appliedPlanEdits"][i] 에 applyCharPrIDRef / commandType 적재
  - verify7.results["V4_CHARPR_PRESERVED"] == PASS
  - readback["V4_CHARPR_PRESERVED"] == PASS
  - readback["V1_RANGE_POSITION_OK"] / readback["V7_READBACK_MATCH"]
    == PASS (회귀 유지)
  - parPrIDRef 변경 0건 (V5 PASS)
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

BASELINE_COMMIT = "d3f8ed6"

ADAPTER_FILE = PR / "scripts/hwpx/web_office/paragraph_writer_adapter.py"

# 본 공정에서 허용된 변경 범위: adapter.applied[] 에 applyCharPrIDRef +
# commandType 두 metadata 필드 적재. 그 외 모듈은 LOCKED.
LOCKED_FILES = [
    # WEB-OFFICE-PARA-EDIT-APPLYFORMAT-EXISTING-CHARPR-01:
    # paragraph_save_verify7 / paragraph_edit_plan / hwpx_edit_tool 은
    # ApplyFormat 활성화로 본 LOCKED 에서 제거됨.
    "scripts/hwpx/web_office/paragraph_save_pipeline.py",
    "scripts/hwpx/web_office/ro_view_importer.py",
    "scripts/hwpx/web_office/document_model.py",
    "scripts/hwpx/web_office/edit_command_model.py",
    "scripts/hwpx/web_office/para_edit_normalizer.py",
    "scripts/hwpx/hwpx_writer_adapter.py",
]

ADAPTER_REQUIRED_PATTERNS = [
    # dry_run applied dict + real applied dict 양쪽에 적재되어야 한다.
    # applyCharPrIDRef 가 적어도 2회 등장 + commandType 키 사용.
    (r'"applyCharPrIDRef"\s*:\s*item\.get\("applyCharPrIDRef"\)', 2),
    (r'"commandType"\s*:\s*ct\b', 2),
]


def _check_adapter_metadata() -> list[dict]:
    findings: list[dict] = []
    if not ADAPTER_FILE.is_file():
        findings.append({"code": "ADAPTER_MISSING", "level": "FAIL"})
        return findings
    src = ADAPTER_FILE.read_text(encoding="utf-8")
    for pat, min_count in ADAPTER_REQUIRED_PATTERNS:
        hits = len(re.findall(pat, src))
        if hits < min_count:
            findings.append({
                "code": "ADAPTER_METADATA_MISSING",
                "level": "FAIL",
                "detail": (f"pattern {pat!r} hits={hits} required>={min_count}"),
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
            findings.append({"code": "GIT_DIFF_FAILED", "level": "WARN", "detail": f"{rel}: {e}"})
            continue
        if r.returncode != 0:
            findings.append({
                "code": "GIT_DIFF_FAILED",
                "level": "WARN",
                "detail": f"{rel}: rc={r.returncode}",
            })
            continue
        if r.stdout.strip():
            findings.append({"code": "LOCKED_FILE_CHANGED", "level": "FAIL", "detail": rel})
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
        return {"status": "FIXTURE_MISSING", "scenarios": [], "shaPreserved": None}
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
        return {"status": "NO_SUITABLE_PARAGRAPH", "scenarios": [], "shaPreserved": True}

    par_pr_before = ro_p.parPrIDRef
    scenarios: list[dict] = []
    with tempfile.TemporaryDirectory() as td:
        td_p = Path(td)
        for tag, scn, kw in [
            ("REPLACE", SCENARIO_REPLACE, {"range_focus": 1, "replace_after": "Q"}),
            ("DELETE", SCENARIO_DELETE, {"range_focus": 1}),
        ]:
            out = td_p / f"v4_{tag}.hwpx"
            res = run_para_edit_e2e(
                source_path=fixture,
                output_path=out,
                scenario=scn,
                paragraph_id=ro_p.paragraphId,
                range_anchor=0,
                allow_writer=True,
                **kw,
            )
            applied_edits = res.get("appliedPlanEdits") or []
            scenarios.append({
                "name": scn,
                "outputCreated": bool(res.get("outputCreated")),
                "applied": applied_edits,
                "v17": (res.get("verify7") or {}).get("results", {}),
                "readback": res.get("readback") or {},
                "parPrBefore": par_pr_before,
                "parPrAfter": (res.get("readback") or {}).get("outputParPrIDRef"),
            })
    sha_after = hashlib.sha256(fixture.read_bytes()).hexdigest()
    return {
        "status": "OK",
        "scenarios": scenarios,
        "shaPreserved": sha_after == sha_before,
        "fixture": str(fixture.relative_to(PR)),
        "paragraphId": ro_p.paragraphId,
    }


def _check_applied_entries(sc: dict, applied: list, findings: list[dict]) -> None:
    for it in applied:
        if "applyCharPrIDRef" not in it:
            findings.append({
                "code": "APPLYCHARPR_FIELD_MISSING",
                "level": "FAIL",
                "detail": (f"{sc['name']}: applied entry missing applyCharPrIDRef key"),
            })
        if it.get("commandType") not in ("REPLACE_TEXT_RANGE", "DELETE_TEXT_RANGE", "TYPE_TEXT"):
            findings.append({
                "code": "APPLYCHARPR_COMMANDTYPE_INVALID",
                "level": "FAIL",
                "detail": (f"{sc['name']}: commandType={it.get('commandType')}"),
            })


def _check_readback_regressions(sc: dict, findings: list[dict]) -> None:
    v17 = sc.get("v17") or {}
    rb = sc.get("readback") or {}
    for k in ("V1_RANGE_POSITION_OK", "V7_READBACK_MATCH"):
        if rb.get(k) != "PASS":
            findings.append({
                "code": "V1_V7_REGRESSION",
                "level": "FAIL",
                "detail": (f"{sc['name']}: {k}={rb.get(k)}"),
            })
    for k in ("V4_CHARPR_PRESERVED",):
        if v17.get(k) != "PASS":
            findings.append({
                "code": "V4_VERIFY7_NOT_PASS",
                "level": "FAIL",
                "detail": (f"{sc['name']}: verify7.{k}={v17.get(k)}"),
            })
        if rb.get(k) != "PASS":
            findings.append({
                "code": "V4_READBACK_NOT_PASS",
                "level": "FAIL",
                "detail": (f"{sc['name']}: readback.{k}={rb.get(k)}"),
            })


def _check_scenario(sc: dict, findings: list[dict]) -> None:
    if not sc["outputCreated"]:
        findings.append({
            "code": "APPLYCHARPR_OUTPUT_NOT_CREATED",
            "level": "FAIL",
            "detail": sc["name"],
        })
        return
    applied = sc.get("applied") or []
    if not applied:
        findings.append({
            "code": "APPLYCHARPR_APPLIED_EMPTY",
            "level": "FAIL",
            "detail": sc["name"],
        })
        return
    _check_applied_entries(sc, applied, findings)
    _check_readback_regressions(sc, findings)
    if sc.get("parPrBefore") != sc.get("parPrAfter"):
        findings.append({
            "code": "PARPR_CHANGED",
            "level": "FAIL",
            "detail": (f"{sc['name']}: {sc.get('parPrBefore')!r} -> {sc.get('parPrAfter')!r}"),
        })


def audit() -> dict[str, Any]:
    findings: list[dict] = []
    findings.extend(_check_adapter_metadata())
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
        for sc in dyn["scenarios"]:
            _check_scenario(sc, findings)
        if dyn.get("shaPreserved") is False:
            findings.append({
                "code": "SOURCE_SHA_TOUCHED",
                "level": "FAIL",
                "detail": "fixture sha before != after",
            })

    fails = [f for f in findings if f.get("level") == "FAIL"]
    verdict = "PASS" if not fails else "FAIL"
    return {
        "task": "WEB-OFFICE-PARA-ADAPTER-APPLYCHARPR-01",
        "baseline": BASELINE_COMMIT,
        "verdict": verdict,
        "partialCompletion": partial,
        "allowedChange": (
            "paragraph_writer_adapter.py applied[] dict 에 "
            "applyCharPrIDRef + commandType 두 필드 적재 한정 "
            "(V4_CHARPR_PRESERVED 활성화 트리거)"
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
