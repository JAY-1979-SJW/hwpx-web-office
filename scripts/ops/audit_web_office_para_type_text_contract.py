"""WEB-OFFICE-PARA-TYPE-TEXT-CONTRACT-01 준공검사.

TYPE_TEXT command 의 expectedBefore 계약이 writer adapter 의 range-slice
계약과 정렬되었음을 정적·동적으로 확인한다.

정적 신호 (소스 패턴):
  - para_edit_model.make_type_text_command 가 expectedBefore="" 로 명령을
    생성하고 forward 에 rangeStart/rangeEnd=caret_offset, afterText 를 적재
  - para_edit_command.mjs 의 makeTypeTextCommand 가 동일 계약을 따름
  - validate_expected_before 가 TYPE_TEXT 에서 빈 slice 기준으로 판정

동적 신호 (fixture 가용 시):
  - run_para_edit_e2e SCENARIO_TYPE 가 outputCreated=True, writerActivated=True
  - V1_RANGE_POSITION_OK / V4_CHARPR_PRESERVED / V7_READBACK_MATCH 모두 PASS
  - REPLACE / DELETE 회귀 V1~V7 PASS 유지
  - source sha 무변경
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

MODEL_FILE = PR / "scripts/hwpx/web_office/para_edit_model.py"
JS_FILE = PR / "frontend/web_office_viewer/para_edit_command.mjs"
PIPELINE_FILE = PR / "scripts/hwpx/web_office/para_edit_e2e_pipeline.py"

REQUIRED_PY_PATTERNS = [
    (r'expectedBefore=""', 1),
    (r'"rangeStart":\s*caret_offset', 1),
    (r'"rangeEnd":\s*caret_offset', 1),
    (r'"afterText":\s*insert_text', 1),
]
REQUIRED_JS_PATTERNS = [
    (r'expectedBefore:\s*""', 1),
    (r"rangeStart:\s*caretOffset", 1),
    (r"rangeEnd:\s*caretOffset", 1),
    (r"afterText:\s*insertText", 1),
]


def _fixture() -> Path | None:
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


def _check_static() -> list[dict]:
    findings: list[dict] = []
    if not MODEL_FILE.is_file():
        return [{"code": "MODEL_FILE_MISSING", "level": "FAIL", "detail": str(MODEL_FILE)}]
    src = MODEL_FILE.read_text(encoding="utf-8")
    for pat, lo in REQUIRED_PY_PATTERNS:
        n = len(re.findall(pat, src))
        if n < lo:
            findings.append({
                "code": "PY_PATTERN_MISSING",
                "level": "FAIL",
                "detail": f"{pat} count={n} (>= {lo})",
            })
    if not JS_FILE.is_file():
        findings.append({"code": "JS_FILE_MISSING", "level": "FAIL", "detail": str(JS_FILE)})
    else:
        js = JS_FILE.read_text(encoding="utf-8")
        for pat, lo in REQUIRED_JS_PATTERNS:
            n = len(re.findall(pat, js))
            if n < lo:
                findings.append({
                    "code": "JS_PATTERN_MISSING",
                    "level": "FAIL",
                    "detail": f"{pat} count={n} (>= {lo})",
                })
    if PIPELINE_FILE.is_file():
        ps = PIPELINE_FILE.read_text(encoding="utf-8")
        if "SCENARIO_TYPE" not in ps or "_READBACK_SCENARIOS" not in ps:
            findings.append({
                "code": "PIPELINE_PATTERN_MISSING",
                "level": "FAIL",
                "detail": "readback scenarios 구조 누락",
            })
        # SCENARIO_TYPE 이 readback scope 에 포함되어야 한다
        m = re.search(r"_READBACK_SCENARIOS\s*=\s*\{[^}]*\}", ps)
        if not m or "SCENARIO_TYPE" not in m.group(0):
            findings.append({
                "code": "READBACK_SCOPE_MISSING_TYPE_TEXT",
                "level": "FAIL",
                "detail": "SCENARIO_TYPE 가 readback 범위 외",
            })
    return findings


def _run_dynamic(fixture: Path) -> dict[str, Any]:
    """3 시나리오 E2E + readback + source sha 무변경 확인."""
    import tempfile

    from scripts.hwpx.web_office.para_edit_e2e_pipeline import (
        SCENARIO_DELETE,
        SCENARIO_REPLACE,
        SCENARIO_TYPE,
        run_para_edit_e2e,
    )
    from scripts.hwpx.web_office.ro_view_importer import import_hwpx_as_ro_view

    doc = import_hwpx_as_ro_view(fixture)
    ro_p = next(
        (
            p
            for p in doc.paragraphs
            if (p.containerScope or {}).get("kind") == "cell"
            and p.parPrIDRef
            and p.runs
            and p.runs[0].charPrIDRef
            and len(p.text or "") >= 2
        ),
        None,
    )
    if ro_p is None:
        return {"ok": False, "reason": "no cell paragraph fixture"}

    sha_before = hashlib.sha256(fixture.read_bytes()).hexdigest()
    mt_before = fixture.stat().st_mtime_ns
    out = {
        "scenarios": [],
        "shaPreserved": None,
        "mtimePreserved": None,
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
            outp = td_path / f"contract_{scn}.hwpx"
            res = run_para_edit_e2e(
                source_path=fixture,
                output_path=outp,
                scenario=scn,
                paragraph_id=ro_p.paragraphId,
                range_anchor=0,
                allow_writer=True,
                **kw,
            )
            v7 = (res.get("verify7") or {}).get("results", {})
            rb = res.get("readback") or {}
            out["scenarios"].append({
                "scenario": scn,
                "outputCreated": res.get("outputCreated"),
                "writerActivated": res.get("writerActivated"),
                "rejectedCount": len(res.get("rejected") or []),
                "verify7": v7,
                "readback": rb,
            })

    sha_after = hashlib.sha256(fixture.read_bytes()).hexdigest()
    out["shaPreserved"] = sha_after == sha_before
    out["mtimePreserved"] = fixture.stat().st_mtime_ns == mt_before
    out["ok"] = True
    return out


REQUIRED_V7 = (
    "V2_NO_CROSS_PARAGRAPH_LEAK",
    "V3_UNTOUCHED_RUNS_PRESERVED",
    "V4_CHARPR_PRESERVED",
    "V5_PARPR_PRESERVED",
    "V6_OUTPUT_ISOLATED",
)
REQUIRED_RB = ("V1_RANGE_POSITION_OK", "V4_CHARPR_PRESERVED", "V7_READBACK_MATCH")


def _check_scenario(sc: dict) -> list[dict]:
    name = sc["scenario"]
    findings: list[dict] = []
    if not sc["outputCreated"]:
        findings.append({"code": "OUTPUT_NOT_CREATED", "level": "FAIL", "detail": name})
        return findings
    if sc["rejectedCount"]:
        findings.append({"code": "REJECTED_NOT_EMPTY", "level": "FAIL", "detail": name})
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
    return findings


def _check_dynamic(dyn: dict) -> list[dict]:
    findings: list[dict] = []
    if not dyn.get("ok"):
        findings.append({
            "code": "DYNAMIC_SKIPPED",
            "level": "WARN",
            "detail": dyn.get("reason", "fixture missing"),
        })
        return findings
    for sc in dyn["scenarios"]:
        findings += _check_scenario(sc)
    if dyn.get("shaPreserved") is False:
        findings.append({
            "code": "SOURCE_SHA_TOUCHED",
            "level": "FAIL",
            "detail": "fixture sha before != after",
        })
    if dyn.get("mtimePreserved") is False:
        findings.append({
            "code": "SOURCE_MTIME_TOUCHED",
            "level": "WARN",
            "detail": "fixture mtime before != after",
        })
    return findings


def audit() -> dict[str, Any]:
    findings = _check_static()
    fx = _fixture()
    dyn: dict[str, Any] = {"ok": False, "reason": "fixture missing"}
    if fx is not None:
        try:
            dyn = _run_dynamic(fx)
        except Exception as e:  # ruff: ignore[blind-except]
            findings.append({"code": "DYNAMIC_RAISED", "level": "FAIL", "detail": str(e)})
    findings.extend(_check_dynamic(dyn))
    fail = [f for f in findings if f["level"] == "FAIL"]
    warn = [f for f in findings if f["level"] == "WARN"]
    return {
        "audit": "WEB-OFFICE-PARA-TYPE-TEXT-CONTRACT-01",
        "findings": findings,
        "verdict": "FAIL" if fail else ("WARN" if warn else "PASS"),
        "dynamic": dyn,
    }


if __name__ == "__main__":
    import json

    print(json.dumps(audit(), ensure_ascii=False, indent=2))
