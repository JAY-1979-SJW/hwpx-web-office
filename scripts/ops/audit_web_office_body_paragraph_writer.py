"""WEB-OFFICE-BODY-PARAGRAPH-WRITER-01 준공검사.

containerScope.kind="block" + 단일 run 범위에서 TYPE_TEXT /
REPLACE_TEXT_RANGE / DELETE_TEXT_RANGE 가 V1~V7 PASS 되는지 정적·동적
으로 확인한다.

정적 신호:
  - paragraph_writer_adapter.py 가 _resolve_body_paragraph 헬퍼를 노출
  - SECTION_NOT_FOUND / BODY_BLOCK_NOT_PARAGRAPH reject 상수 존재
  - BODY_PARAGRAPH_NOT_SUPPORTED 무조건 reject 분기가 사라짐
  - multi-run / table structure / image edit 게이트는 유지

동적 신호:
  - body paragraph 단일 run fixture 1건 이상 발견
  - SCENARIO_TYPE/REPLACE/DELETE 3종 모두 outputCreated, writerActivated,
    rejected=∅, verify7 V2~V6 PASS, readback V1/V4/V7 PASS
  - 원본 sha/mtime 무변경
  - output sandbox 격리
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

ADAPTER = (PR / "scripts/hwpx/web_office/"
                  "paragraph_writer_adapter.py")

REQUIRED_ADAPTER_PATTERNS = [
    r"_resolve_body_paragraph\(",
    r"REASON_SECTION_NOT_FOUND",
    r"REASON_BODY_BLOCK_NOT_PARAGRAPH",
    r'kind == "cell"',
    # CLAUDE.md §4.2(머리말/꼬리말 텍스트 편집) 확장 후에도 cell/block
    # 게이트 자체는 유지되는지만 확인 — 정확한 튜플 내용까지 고정하지
    # 않는다(향후 정당한 kind 확장을 매번 이 정규식 때문에 막지 않게).
    r'kind not in \("cell", "block"',
    r"sectionIndex",
    r"blockIndex",
]
# 무조건 BODY_PARAGRAPH_NOT_SUPPORTED reject 분기가 제거되었어야 함
FORBIDDEN_ADAPTER_PATTERNS = [
    r"REASON_BODY_PARAGRAPH_NOT_SUPPORTED\)\)\s*\n\s*continue",
]

FORBIDDEN_WRITER_SYMBOLS = [
    r"apply_paragraph_edits_plan\(",
    r"save_paragraph_edits\(",
    r"create_hwpx_document\(",
    r"write_package\(",
]


def _check_static() -> list[dict]:
    findings: list[dict] = []
    if not ADAPTER.is_file():
        findings.append({"code": "ADAPTER_MISSING", "level": "FAIL",
                          "detail": str(ADAPTER)})
        return findings
    src = ADAPTER.read_text(encoding="utf-8")
    for pat in REQUIRED_ADAPTER_PATTERNS:
        if not re.search(pat, src):
            findings.append({"code": "ADAPTER_PATTERN_MISSING",
                              "level": "FAIL", "detail": pat})
    for pat in FORBIDDEN_ADAPTER_PATTERNS:
        if re.search(pat, src):
            findings.append({
                "code": "ADAPTER_UNCONDITIONAL_BODY_REJECT_PRESENT",
                "level": "FAIL", "detail": pat})
    # multi-run reject 는 유지되어야 한다 (회귀 잠금)
    if "REASON_MULTI_RUN_RANGE_NOT_SUPPORTED" not in src:
        findings.append({"code": "MULTI_RUN_GATE_REGRESSION",
                          "level": "FAIL",
                          "detail": "multi-run reject 코드 누락"})
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


def _pick_body_fixture() -> tuple[Path | None, Any]:
    """단일 run body paragraph 가 있는 fixture + paragraph 객체 반환."""
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
            return None, None
    else:
        # 레거시 corpus DB 부재 — 카탈로그 후보를 같은 형태로 공급한다.
        # 표본 하나만 주면 조건에 맞는 문단이 없을 때 None 이 흘러가 터진다.
        from scripts.hwpx.web_office.hwpx_sample_source import (
            catalog_candidates)
        rows = [(str(p.relative_to(PR)).replace("\\", "/"),)
                for p in catalog_candidates(limit=200)]
        if not rows:
            return None, None
    from scripts.hwpx.web_office.ro_view_importer import (  # noqa: E402
        import_hwpx_as_ro_view)
    for (sp,) in rows:
        p = PR / sp
        if not p.is_file():
            continue
        try:
            doc = import_hwpx_as_ro_view(p)
        except Exception:  # noqa: BLE001
            continue
        for par in doc.paragraphs:
            sc = par.containerScope or {}
            if (sc.get("kind") == "block" and par.parPrIDRef
                    and par.runs and par.runs[0].charPrIDRef
                    and len(par.runs) == 1
                    and len(par.text or "") >= 3):
                return p, par
    return None, None


REQUIRED_V7 = ("V2_NO_CROSS_PARAGRAPH_LEAK",
                "V3_UNTOUCHED_RUNS_PRESERVED",
                "V4_CHARPR_PRESERVED", "V5_PARPR_PRESERVED",
                "V6_OUTPUT_ISOLATED")
REQUIRED_RB = ("V1_RANGE_POSITION_OK",
                "V4_CHARPR_PRESERVED", "V7_READBACK_MATCH")


def _run_dynamic(fixture: Path, body_p: Any) -> dict[str, Any]:
    from scripts.hwpx.web_office.para_edit_e2e_pipeline import (  # noqa: E402
        run_para_edit_e2e, SCENARIO_TYPE, SCENARIO_REPLACE,
        SCENARIO_DELETE)

    sha_b = hashlib.sha256(fixture.read_bytes()).hexdigest()
    mt_b = fixture.stat().st_mtime_ns
    out: dict[str, Any] = {
        "ok": True, "fixture": str(fixture.relative_to(PR)),
        "paragraphId": body_p.paragraphId,
        "containerScope": body_p.containerScope,
        "scenarios": [],
    }
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        for scn, kw in [
            (SCENARIO_TYPE, {"insert_text": "Z"}),
            (SCENARIO_REPLACE, {"range_focus": 2, "replace_after": "RR"}),
            (SCENARIO_DELETE, {"range_focus": 2}),
        ]:
            outp = td_path / f"body_{scn}.hwpx"
            res = run_para_edit_e2e(
                source_path=fixture, output_path=outp,
                scenario=scn, paragraph_id=body_p.paragraphId,
                range_anchor=0, allow_writer=True, **kw)
            out["scenarios"].append({
                "scenario": scn,
                "outputCreated": res.get("outputCreated"),
                "writerActivated": res.get("writerActivated"),
                "rejectedCount": len(res.get("rejected") or []),
                "verify7": (res.get("verify7") or {}).get(
                    "results", {}),
                "readback": res.get("readback") or {},
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
                          "detail": dyn.get("reason",
                                                            "fixture missing")})
        return findings
    expected = {"TYPE_TEXT", "REPLACE_TEXT_RANGE",
                  "DELETE_TEXT_RANGE"}
    if {sc["scenario"] for sc in dyn["scenarios"]} != expected:
        findings.append({"code": "SCENARIO_SET_MISMATCH",
                          "level": "FAIL"})
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
                findings.append({"code": "V7_NOT_PASS",
                                  "level": "FAIL",
                                  "detail": f"{name}: {k}={v7.get(k)}"})
        rb = sc["readback"]
        for k in REQUIRED_RB:
            if rb.get(k) != "PASS":
                findings.append({"code": "READBACK_NOT_PASS",
                                  "level": "FAIL",
                                  "detail": f"{name}: {k}={rb.get(k)}"})
    if dyn.get("shaPreserved") is False:
        findings.append({"code": "SOURCE_SHA_TOUCHED",
                          "level": "FAIL"})
    if dyn.get("mtimePreserved") is False:
        findings.append({"code": "SOURCE_MTIME_TOUCHED",
                          "level": "WARN"})
    return findings


def audit() -> dict[str, Any]:
    findings: list[dict] = []
    findings.extend(_check_static())
    findings.extend(_check_audit_no_writer_calls())

    fx, body_p = _pick_body_fixture()
    if fx is None:
        dyn = {"ok": False, "reason": "no single-run body fixture"}
        findings.append({"code": "DYNAMIC_SKIPPED", "level": "WARN",
                          "detail": dyn["reason"]})
    else:
        try:
            dyn = _run_dynamic(fx, body_p)
        except Exception as e:  # noqa: BLE001
            dyn = {"ok": False, "reason": f"dynamic raised: {e}"}
            findings.append({"code": "DYNAMIC_RAISED",
                              "level": "FAIL", "detail": dyn["reason"]})
        findings.extend(_check_dynamic(dyn))

    fail = [f for f in findings if f["level"] == "FAIL"]
    warn = [f for f in findings if f["level"] == "WARN"]
    return {
        "audit": "WEB-OFFICE-BODY-PARAGRAPH-WRITER-01",
        "findings": findings,
        "verdict": "FAIL" if fail else ("WARN" if warn else "PASS"),
        "dynamic": dyn,
    }


if __name__ == "__main__":
    print(json.dumps(audit(), ensure_ascii=False, indent=2))
