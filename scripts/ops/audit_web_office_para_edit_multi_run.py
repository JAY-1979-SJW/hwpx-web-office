"""WEB-OFFICE-PARA-EDIT-MULTI-RUN-01 준공검사.

같은 문단 multi-run REPLACE / DELETE 활성화의 정적·동적 검증.

정적:
  - hwpx_paragraph_ops.apply_text_range_edit_multi_run 존재
  - POLICY_ANCHOR_CHARPR / FOCUS_CHARPR / REQUIRES_REVIEW 상수 노출
  - 단일-run apply_text_range_edit 경로 유지
  - 신규 charPr 생성 차단 신호 (NEW_CHARPR_INTRODUCED) 존재
  - 안전 가드 (UNSAFE_RUN_CHILDREN) 존재
  - TYPE_TEXT multi-run reject (TYPE_TEXT_MULTI_RUN_NOT_SUPPORTED) 존재
  - paragraph add/delete / ApplyFormat / table / image 활성화 흔적 없음
  - outputPath==sourcePath reject, source sha 보호 회로 유지
  - 본 audit 자체가 writer/원본 overwrite 호출 0건

동적 (fixture 가용 시):
  - 같은 문단 multi-run REPLACE / DELETE → V1~V7 PASS
  - cell + body 양 scope 모두 적어도 1건 PASS
  - 원본 sha/mtime 무변경, output sandbox 격리
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Any

PR = Path(__file__).resolve().parents[2]
if str(PR) not in sys.path:
    sys.path.insert(0, str(PR))

OPS = PR / "scripts/hwpx/hwpx_paragraph_ops.py"
ADAPTER = PR / "scripts/hwpx/web_office/paragraph_writer_adapter.py"
SAVE_PIPELINE = PR / "scripts/hwpx/web_office/paragraph_save_pipeline.py"

REQUIRED_OPS_PATTERNS = [
    r"def\s+apply_text_range_edit_multi_run\(",
    r"def\s+apply_text_range_edit\(",
    r"POLICY_ANCHOR_CHARPR\s*=",
    r"POLICY_FOCUS_CHARPR\s*=",
    r"POLICY_REQUIRES_REVIEW\s*=",
    r"STATUS_UNSAFE_RUN_CHILDREN\s*=",
    r"STATUS_NEW_CHARPR_INTRODUCED\s*=",
    r"_is_safe_text_run\(",
]
REQUIRED_ADAPTER_PATTERNS = [
    r"apply_text_range_edit_multi_run\(",
    r"apply_text_range_edit\(",
    r"REASON_TYPE_TEXT_MULTI_RUN_NOT_SUPPORTED",
    r"REASON_UNSAFE_RUN_CHILDREN",
    r"REASON_NEW_CHARPR_INTRODUCED",
    r"REASON_REQUIRES_REVIEW",
    r"POLICY_ANCHOR_CHARPR",
]
REQUIRED_PIPELINE_PATTERNS = [
    r"OUTPUT_EQUALS_SOURCE",
]
FORBIDDEN_ADAPTER_PATTERNS = [
    # paragraph add/delete / ApplyFormat / table/image 활성화 흔적 차단
    r"def\s+apply_paragraph_add\b",
    r"def\s+apply_paragraph_delete\b",
    r"def\s+apply_format\b",
    r"def\s+create_char_pr\b",
    r"def\s+add_table_row\b",
    r"def\s+delete_table_row\b",
    r"def\s+insert_image\b",
]
FORBIDDEN_WRITER_SYMBOLS = [
    r"apply_paragraph_edits_plan\(",
    r"save_paragraph_edits\(",
    r"create_hwpx_document\(",
    r"write_package\(",
]


def _pattern_findings(
    src: str,
    required: list[str],
    required_code: str,
    forbidden: tuple[str, ...] = (),
    forbidden_code: str = "",
) -> list[dict]:
    findings: list[dict] = []
    for pat in required:
        if not re.search(pat, src):
            findings.append({"code": required_code, "level": "FAIL", "detail": pat})
    for pat in forbidden:
        if re.search(pat, src):
            findings.append({"code": forbidden_code, "level": "FAIL", "detail": pat})
    return findings


def _check_static() -> list[dict]:
    findings: list[dict] = []
    if not OPS.is_file():
        findings.append({"code": "OPS_MISSING", "level": "FAIL", "detail": str(OPS)})
        return findings
    ops_src = OPS.read_text(encoding="utf-8")
    findings.extend(_pattern_findings(ops_src, REQUIRED_OPS_PATTERNS, "OPS_PATTERN_MISSING"))
    if not ADAPTER.is_file():
        findings.append({"code": "ADAPTER_MISSING", "level": "FAIL", "detail": str(ADAPTER)})
        return findings
    ad_src = ADAPTER.read_text(encoding="utf-8")
    findings.extend(
        _pattern_findings(
            ad_src,
            REQUIRED_ADAPTER_PATTERNS,
            "ADAPTER_PATTERN_MISSING",
            FORBIDDEN_ADAPTER_PATTERNS,
            "ADAPTER_FORBIDDEN_FEATURE",
        )
    )
    if SAVE_PIPELINE.is_file():
        sp_src = SAVE_PIPELINE.read_text(encoding="utf-8")
        findings.extend(
            _pattern_findings(sp_src, REQUIRED_PIPELINE_PATTERNS, "PIPELINE_PATTERN_MISSING")
        )
    return findings


def _check_audit_no_writer_calls() -> list[dict]:
    findings: list[dict] = []
    me = Path(__file__).read_text(encoding="utf-8")
    for sym in FORBIDDEN_WRITER_SYMBOLS:
        if re.search(sym, me):
            findings.append({"code": "AUDIT_FORBIDDEN_WRITER_CALL", "level": "FAIL", "detail": sym})
    return findings


def _load_candidate_source_rows() -> list[tuple[str]] | None:
    """corpus DB 또는 카탈로그 폴백에서 후보 source_path 목록을 가져온다."""
    db = PR / "data/recognition_corpus/corpus.sqlite3"
    if db.is_file():
        try:
            conn = sqlite3.connect(db)
            rows = conn.execute("""
                SELECT d.source_path FROM hwpx_documents d
                WHERE d.inventory_status='FOUND'
                ORDER BY d.first_seen_at LIMIT 200
            """).fetchall()
            conn.close()
        except sqlite3.Error:
            return None
        return rows
    # 레거시 corpus DB 부재 — 카탈로그 후보를 같은 형태로 공급한다.
    # 표본을 하나만 주면 조건에 맞는 문단이 없을 때 None 이 흘러가
    # 호출부가 터진다. 아래 순회가 조건 검사를 하므로 후보를 넉넉히 준다.
    from scripts.hwpx.web_office.hwpx_sample_source import catalog_candidates

    rows = [(str(p.relative_to(PR)).replace("\\", "/"),) for p in catalog_candidates(limit=200)]
    return rows or None


def _pick_multi_run(scope_kind: str):
    rows = _load_candidate_source_rows()
    if not rows:
        return None, None
    from scripts.hwpx.web_office.ro_view_importer import import_hwpx_as_ro_view

    for (sp,) in rows:
        p = PR / sp
        if not p.is_file():
            continue
        try:
            doc = import_hwpx_as_ro_view(p)
        except Exception:  # ruff: ignore[blind-except]
            continue
        for par in doc.paragraphs:
            sc = par.containerScope or {}
            if sc.get("kind") != scope_kind:
                continue
            if not par.parPrIDRef or len(par.runs) < 3:
                continue
            if not all(r.text and r.charPrIDRef for r in par.runs[:3]):
                continue
            return p, par
    return None, None


REQUIRED_V7 = (
    "V2_NO_CROSS_PARAGRAPH_LEAK",
    "V3_UNTOUCHED_RUNS_PRESERVED",
    "V4_CHARPR_PRESERVED",
    "V5_PARPR_PRESERVED",
    "V6_OUTPUT_ISOLATED",
)
REQUIRED_RB = ("V1_RANGE_POSITION_OK", "V4_CHARPR_PRESERVED", "V7_READBACK_MATCH")


def _run_one(fixture: Path, par, scenario: str) -> dict:
    from scripts.hwpx.web_office.para_edit_e2e_pipeline import (
        SCENARIO_DELETE,
        SCENARIO_REPLACE,
        run_para_edit_e2e,
    )

    r0 = par.runs[0].text
    s = max(0, len(r0) - 1)
    e = len(r0) + 1
    scn = SCENARIO_REPLACE if scenario == "REPLACE" else SCENARIO_DELETE
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / f"mr_{scenario}.hwpx"
        kw = {"replace_after": "Z"} if scenario == "REPLACE" else {}
        res = run_para_edit_e2e(
            source_path=fixture,
            output_path=out,
            scenario=scn,
            paragraph_id=par.paragraphId,
            range_anchor=s,
            range_focus=e,
            allow_writer=True,
            **kw,
        )
        return {
            "scenario": scenario,
            "outputCreated": res.get("outputCreated"),
            "rejectedCount": len(res.get("rejected") or []),
            "verify7": (res.get("verify7") or {}).get("results", {}),
            "readback": res.get("readback") or {},
            "outputInSandbox": str(out).startswith(td),
            "multiRunFlag": any(
                a.get("multiRun") is True for a in res.get("appliedPlanEdits") or []
            ),
        }


def _run_dynamic() -> dict[str, Any]:
    out: dict[str, Any] = {"ok": True, "byScope": {}}
    any_ok = False
    for scope_kind in ("cell", "block"):
        fx, par = _pick_multi_run(scope_kind)
        if fx is None:
            out["byScope"][scope_kind] = {"ok": False, "reason": "no fixture"}
            continue
        sha_b = hashlib.sha256(fx.read_bytes()).hexdigest()
        mt_b = fx.stat().st_mtime_ns
        results = []
        for scn in ("REPLACE", "DELETE"):
            results.append(_run_one(fx, par, scn))
        sha_ok = hashlib.sha256(fx.read_bytes()).hexdigest() == sha_b
        mt_ok = fx.stat().st_mtime_ns == mt_b
        out["byScope"][scope_kind] = {
            "ok": True,
            "fixture": str(fx.relative_to(PR)),
            "paragraphId": par.paragraphId,
            "containerScope": par.containerScope,
            "scenarios": results,
            "shaPreserved": sha_ok,
            "mtimePreserved": mt_ok,
        }
        any_ok = True
    out["ok"] = any_ok
    return out


def _check_dynamic(dyn: dict) -> list[dict]:
    findings: list[dict] = []
    if not dyn.get("ok"):
        findings.append({
            "code": "DYNAMIC_SKIPPED",
            "level": "WARN",
            "detail": "no fixture for either scope",
        })
        return findings
    cov = {"cell": False, "block": False}
    for scope_kind, sec in dyn["byScope"].items():
        if not sec.get("ok"):
            findings.append({
                "code": "SCOPE_FIXTURE_MISSING",
                "level": "WARN",
                "detail": scope_kind,
            })
            continue
        cov[scope_kind] = True
        for sc in sec["scenarios"]:
            name = f"{scope_kind}.{sc['scenario']}"
            if not sc["outputCreated"]:
                findings.append({"code": "OUTPUT_NOT_CREATED", "level": "FAIL", "detail": name})
                continue
            if not sc["outputInSandbox"]:
                findings.append({"code": "OUTPUT_OUTSIDE_SANDBOX", "level": "FAIL", "detail": name})
            if sc["rejectedCount"]:
                findings.append({"code": "REJECTED_NOT_EMPTY", "level": "FAIL", "detail": name})
            if not sc["multiRunFlag"]:
                findings.append({"code": "MULTI_RUN_FLAG_MISSING", "level": "FAIL", "detail": name})
            v7 = sc["verify7"]
            for k in REQUIRED_V7:
                if v7.get(k) != "PASS":
                    findings.append({
                        "code": "V7_NOT_PASS",
                        "level": "FAIL",
                        "detail": f"{name}: {k}={v7.get(k)}",
                    })
            rb = sc["readback"]
            for k in REQUIRED_RB:
                if rb.get(k) != "PASS":
                    findings.append({
                        "code": "READBACK_NOT_PASS",
                        "level": "FAIL",
                        "detail": f"{name}: {k}={rb.get(k)}",
                    })
        if sec.get("shaPreserved") is False:
            findings.append({"code": "SOURCE_SHA_TOUCHED", "level": "FAIL", "detail": scope_kind})
        if sec.get("mtimePreserved") is False:
            findings.append({"code": "SOURCE_MTIME_TOUCHED", "level": "WARN", "detail": scope_kind})
    if not any(cov.values()):
        findings.append({
            "code": "NO_SCOPE_COVERED",
            "level": "FAIL",
            "detail": "neither cell nor body fixture",
        })
    return findings


def audit() -> dict[str, Any]:
    findings: list[dict] = []
    findings.extend(_check_static())
    findings.extend(_check_audit_no_writer_calls())
    try:
        dyn = _run_dynamic()
    except Exception as e:  # ruff: ignore[blind-except]
        dyn = {"ok": False, "reason": f"dynamic raised: {e}"}
        findings.append({"code": "DYNAMIC_RAISED", "level": "FAIL", "detail": dyn["reason"]})
    findings.extend(_check_dynamic(dyn))

    fail = [f for f in findings if f["level"] == "FAIL"]
    warn = [f for f in findings if f["level"] == "WARN"]
    return {
        "audit": "WEB-OFFICE-PARA-EDIT-MULTI-RUN-01",
        "findings": findings,
        "verdict": "FAIL" if fail else ("WARN" if warn else "PASS"),
        "dynamic": dyn,
    }


if __name__ == "__main__":
    print(json.dumps(audit(), ensure_ascii=False, indent=2))
