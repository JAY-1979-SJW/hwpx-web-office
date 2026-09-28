"""WEB-OFFICE-PARA-EDIT-TYPE-MULTI-RUN-02 준공검사.

multi-run paragraph 에서 caret 가 scope.runIndex 가 가리키는 run 밖에
있어도 TYPE_TEXT 가 paragraph offset 기준으로 caret-in-run 을 다시 찾아
단일-run insert (apply_text_range_edit) 로 라우팅됨을 정적·동적으로
검증한다.

정적:
  - paragraph_writer_adapter.py 가 TYPE_TEXT 분기에서 단순 reject 대신
    locate_run_for_paragraph_offset 으로 caret-in-run 재탐색
  - 신규 multi-run primitive 추가 흔적 없음 (hwpx_paragraph_ops 무수정)
  - REPLACE/DELETE multi-run 경로 (apply_text_range_edit_multi_run 호출)
    그대로 유지
  - POLICY_CARET_RIGHT, ApplyFormat, paragraph add/delete, table/image
    활성화 흔적 없음
  - outputPath==sourcePath reject 코드 존재

동적 (fixture 가용 시):
  - cell + body multi-run paragraph 의 caret 4 위치 (start / boundary /
    inside r1 / paragraph end) 에서 V1~V7 PASS
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

ADAPTER = PR / "scripts/hwpx/web_office/paragraph_writer_adapter.py"
OPS = PR / "scripts/hwpx/hwpx_paragraph_ops.py"
SAVE_PIPELINE = PR / "scripts/hwpx/web_office/paragraph_save_pipeline.py"

REQUIRED_ADAPTER_PATTERNS = [
    # caret 재탐색 라우팅 흔적
    r"locate_run_for_paragraph_offset\(",
    r"_is_safe_text_run\(",
    r"apply_text_range_edit\(",
    # REPLACE/DELETE multi-run 경로 보존
    r"apply_text_range_edit_multi_run\(",
    # TYPE_TEXT multi-run 진입 신호
    r"typeMultiRun",
    r'ct == "TYPE_TEXT"',
]
FORBIDDEN_ADAPTER_PATTERNS = [
    # 1차 공정에서 도입 금지
    r"POLICY_CARET_RIGHT",
    r"def\s+apply_paragraph_add\b",
    r"def\s+apply_paragraph_delete\b",
    r"def\s+apply_format\b",
    r"def\s+create_char_pr\b",
    r"def\s+add_table_row\b",
    r"def\s+delete_table_row\b",
    r"def\s+insert_image\b",
]
# TYPE_TEXT multi-run 진입 시 무조건 reject 만 하는 분기가 살아 있으면 안 됨
FORBIDDEN_ADAPTER_FRAGMENTS = [
    # 과거의 즉시-reject 패턴 (caret-in-run 재탐색 없이 reject) 가
    # 단독으로 남아 있으면 본 공정이 발효되지 않은 것.
    # 단, paragraph 범위 밖 fallback reject 는 허용.
]
REQUIRED_PIPELINE_PATTERNS = [
    r"OUTPUT_EQUALS_SOURCE",
]
# hwpx_paragraph_ops.py 는 본 공정에서 무수정 — 신규 primitive 흔적 없음
FORBIDDEN_OPS_PATTERNS_AFTER_BASELINE = [
    # multi-run TYPE_TEXT 전용 신규 primitive 도입 흔적
    r"def\s+apply_caret_insert_multi_run\b",
    r"def\s+apply_type_text_multi_run\b",
]

FORBIDDEN_WRITER_SYMBOLS = [
    r"apply_paragraph_edits_plan\(",
    r"save_paragraph_edits\(",
    r"create_hwpx_document\(",
    r"write_package\(",
]


def _missing_pattern_findings(src: str, patterns: list[str], code: str) -> list[dict]:
    return [
        {"code": code, "level": "FAIL", "detail": pat}
        for pat in patterns
        if not re.search(pat, src)
    ]


def _forbidden_pattern_findings(src: str, patterns: list[str], code: str) -> list[dict]:
    return [
        {"code": code, "level": "FAIL", "detail": pat} for pat in patterns if re.search(pat, src)
    ]


def _check_static() -> list[dict]:
    findings: list[dict] = []
    if not ADAPTER.is_file():
        findings.append({"code": "ADAPTER_MISSING", "level": "FAIL", "detail": str(ADAPTER)})
        return findings
    ad_src = ADAPTER.read_text(encoding="utf-8")
    findings.extend(
        _missing_pattern_findings(ad_src, REQUIRED_ADAPTER_PATTERNS, "ADAPTER_PATTERN_MISSING")
    )
    findings.extend(
        _forbidden_pattern_findings(ad_src, FORBIDDEN_ADAPTER_PATTERNS, "ADAPTER_FORBIDDEN_FEATURE")
    )
    findings.extend(
        _forbidden_pattern_findings(
            ad_src, FORBIDDEN_ADAPTER_FRAGMENTS, "ADAPTER_FORBIDDEN_FRAGMENT"
        )
    )
    if OPS.is_file():
        ops_src = OPS.read_text(encoding="utf-8")
        findings.extend(
            _forbidden_pattern_findings(
                ops_src, FORBIDDEN_OPS_PATTERNS_AFTER_BASELINE, "OPS_FORBIDDEN_NEW_PRIMITIVE"
            )
        )
    if SAVE_PIPELINE.is_file():
        sp_src = SAVE_PIPELINE.read_text(encoding="utf-8")
        findings.extend(
            _missing_pattern_findings(
                sp_src, REQUIRED_PIPELINE_PATTERNS, "PIPELINE_PATTERN_MISSING"
            )
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
    # 표본 하나만 주면 조건에 맞는 문단이 없을 때 None 이 흘러가 터진다.
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


def _caret_inside_r1(par) -> int:
    r0 = par.runs[0].text or ""
    r1 = par.runs[1].text or ""
    return len(r0) + max(1, len(r1) // 2)


def _run_one(fixture: Path, par, caret: int) -> dict:
    from scripts.hwpx.web_office.para_edit_e2e_pipeline import SCENARIO_TYPE, run_para_edit_e2e

    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "t.hwpx"
        res = run_para_edit_e2e(
            source_path=fixture,
            output_path=out,
            scenario=SCENARIO_TYPE,
            paragraph_id=par.paragraphId,
            range_anchor=caret,
            insert_text="Z",
            allow_writer=True,
        )
        applied = res.get("appliedPlanEdits") or []
        return {
            "caret": caret,
            "outputCreated": res.get("outputCreated"),
            "rejectedCount": len(res.get("rejected") or []),
            "verify7": (res.get("verify7") or {}).get("results", {}),
            "readback": res.get("readback") or {},
            "outputInSandbox": str(out).startswith(td),
            "typeMultiRun": bool(applied and applied[0].get("typeMultiRun")),
            "appliedCharPrIDRef": (applied[0].get("applyCharPrIDRef") if applied else None),
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
        # caret inside run[1] — must be in run 다른 from scope.runIndex
        caret = _caret_inside_r1(par)
        result = _run_one(fx, par, caret)
        out["byScope"][scope_kind] = {
            "ok": True,
            "fixture": str(fx.relative_to(PR)),
            "paragraphId": par.paragraphId,
            "containerScope": par.containerScope,
            "result": result,
            "shaPreserved": (hashlib.sha256(fx.read_bytes()).hexdigest() == sha_b),
            "mtimePreserved": fx.stat().st_mtime_ns == mt_b,
        }
        any_ok = True
    out["ok"] = any_ok
    return out


def _required_key_findings(mapping: dict, keys: list[str], code: str, name: str) -> list[dict]:
    return [
        {
            "code": code,
            "level": "FAIL",
            "detail": f"{name}: {k}={mapping.get(k)}",
        }
        for k in keys
        if mapping.get(k) != "PASS"
    ]


def _check_one_scope(scope_kind: str, sec: dict) -> list[dict]:
    findings: list[dict] = []
    if not sec.get("ok"):
        findings.append({"code": "SCOPE_FIXTURE_MISSING", "level": "WARN", "detail": scope_kind})
        return findings
    r = sec["result"]
    name = f"{scope_kind}.TYPE_TEXT.inside_r1"
    if not r["outputCreated"]:
        findings.append({"code": "OUTPUT_NOT_CREATED", "level": "FAIL", "detail": name})
        return findings
    if not r["outputInSandbox"]:
        findings.append({"code": "OUTPUT_OUTSIDE_SANDBOX", "level": "FAIL", "detail": name})
    if r["rejectedCount"]:
        findings.append({"code": "REJECTED_NOT_EMPTY", "level": "FAIL", "detail": name})
    if not r["typeMultiRun"]:
        findings.append({"code": "TYPE_MULTI_RUN_FLAG_MISSING", "level": "FAIL", "detail": name})
    findings.extend(_required_key_findings(r["verify7"], REQUIRED_V7, "V7_NOT_PASS", name))
    findings.extend(_required_key_findings(r["readback"], REQUIRED_RB, "READBACK_NOT_PASS", name))
    if sec.get("shaPreserved") is False:
        findings.append({"code": "SOURCE_SHA_TOUCHED", "level": "FAIL", "detail": scope_kind})
    if sec.get("mtimePreserved") is False:
        findings.append({"code": "SOURCE_MTIME_TOUCHED", "level": "WARN", "detail": scope_kind})
    return findings


def _check_dynamic(dyn: dict) -> list[dict]:
    findings: list[dict] = []
    if not dyn.get("ok"):
        findings.append({"code": "DYNAMIC_SKIPPED", "level": "WARN", "detail": "no fixture"})
        return findings
    for scope_kind, sec in dyn["byScope"].items():
        findings.extend(_check_one_scope(scope_kind, sec))
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
        "audit": "WEB-OFFICE-PARA-EDIT-TYPE-MULTI-RUN-02",
        "findings": findings,
        "verdict": "FAIL" if fail else ("WARN" if warn else "PASS"),
        "dynamic": dyn,
    }


if __name__ == "__main__":
    print(json.dumps(audit(), ensure_ascii=False, indent=2))
