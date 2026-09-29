"""WEB-OFFICE-PARA-EDIT-APPLYFORMAT-EXISTING-CHARPR-01 준공검사.

APPLY_FORMAT 1차 본공사 — 같은 문서 header.xml 의 기존 charPrIDRef 로만
교체. 신규 charPr 생성 / header.xml mutation / 원본 HWPX 직접 수정 모두
금지.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any

PR = Path(__file__).resolve().parents[2]
if str(PR) not in sys.path:
    sys.path.insert(0, str(PR))

ADAPTER = PR / "scripts/hwpx/web_office/paragraph_writer_adapter.py"
OPS = PR / "scripts/hwpx/hwpx_paragraph_ops.py"
MODEL = PR / "scripts/hwpx/web_office/para_edit_model.py"
PLAN = PR / "scripts/hwpx/web_office/paragraph_edit_plan.py"
PIPELINE = PR / "scripts/hwpx/web_office/para_edit_e2e_pipeline.py"
VERIFY7 = PR / "scripts/hwpx/web_office/paragraph_save_verify7.py"
JS_CMD = PR / "frontend/web_office_viewer/para_edit_command.mjs"

REQUIRED_PATTERNS_BY_FILE: dict[Path, list[str]] = {
    ADAPTER: [
        r'"APPLY_FORMAT"',
        r"apply_charpr_to_range_existing\(",
        r"REASON_TARGET_CHARPR_NOT_IN_HEADER",
        r"REASON_EMPTY_RANGE",
        r"_read_header_char_pr_ids\(",
        r"applyFormatExistingCharPr",
    ],
    OPS: [
        r"def\s+apply_charpr_to_range_existing\(",
        r"STATUS_TARGET_CHARPR_NOT_IN_HEADER",
        r"header_char_pr_ids",
    ],
    MODEL: [
        r"CT_APPLY_FORMAT\s*=",
        r"def\s+make_apply_format_command\(",
        r"def\s+_apply_format\(",
    ],
    PLAN: [
        r"CT_APPLY_FORMAT",
        r"targetCharPrIDRef",
    ],
    PIPELINE: [
        r"SCENARIO_APPLY_FORMAT",
        r"make_apply_format_command\(",
    ],
    VERIFY7: [
        r"APPLY_FORMAT",  # V2/V4 면제 분기
    ],
    JS_CMD: [
        r"CT_APPLY_FORMAT",
        r"makeApplyFormatCommand",
    ],
}

# 절대 도입 금지 — 신규 charPr 생성 / header.xml write 흔적
FORBIDDEN_PATTERNS_BY_FILE: dict[Path, list[str]] = {
    ADAPTER: [
        r"def\s+create_char_pr\b",
        r"package\.entries\[[^\]]*header\.xml[^\]]*\]\s*=",
        r"\.set_entry\([^)]*header\.xml",
    ],
    OPS: [
        r"def\s+create_char_pr\b",
        # ops 모듈은 header.xml write 경로 자체를 호출하지 않아야 한다.
        # (read 또는 docstring 의 단순 언급은 허용 — 실제 mutation 경로만 차단.)
        r"package\.entries\[[^\]]*header\.xml[^\]]*\]\s*=",
        r"\.set_entry\([^)]*header\.xml",
    ],
    MODEL: [
        r"def\s+create_char_pr\b",
    ],
}

# 본 audit 자체가 호출하면 안 되는 writer 류
FORBIDDEN_WRITER_SYMBOLS = [
    r"apply_paragraph_edits_plan\(",
    r"save_paragraph_edits\(",
    r"create_hwpx_document\(",
    r"write_package\(",
]


def _check_static() -> list[dict]:
    findings: list[dict] = []
    for path, patterns in REQUIRED_PATTERNS_BY_FILE.items():
        if not path.is_file():
            findings.append({
                "code": "SOURCE_MISSING",
                "level": "FAIL",
                "detail": str(path.relative_to(PR)),
            })
            continue
        src = path.read_text(encoding="utf-8")
        findings.extend({
                    "code": "REQUIRED_PATTERN_MISSING",
                    "level": "FAIL",
                    "detail": f"{path.relative_to(PR)}: {pat}",
                } for pat in patterns if not re.search(pat, src))
    for path, patterns in FORBIDDEN_PATTERNS_BY_FILE.items():
        if not path.is_file():
            continue
        src = path.read_text(encoding="utf-8")
        findings.extend({
                    "code": "FORBIDDEN_PATTERN_PRESENT",
                    "level": "FAIL",
                    "detail": f"{path.relative_to(PR)}: {pat}",
                } for pat in patterns if re.search(pat, src))
    return findings


def _check_audit_no_writer_calls() -> list[dict]:
    me = Path(__file__).read_text(encoding="utf-8")
    findings: list[dict] = [{"code": "AUDIT_FORBIDDEN_WRITER_CALL", "level": "FAIL", "detail": sym} for sym in FORBIDDEN_WRITER_SYMBOLS if re.search(sym, me)]
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


def _pick_multi(scope_kind: str):
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


def _run_dynamic() -> dict[str, Any]:
    from scripts.hwpx.web_office.charpr_inventory import paragraph_char_pr_inventory
    from scripts.hwpx.web_office.para_edit_e2e_pipeline import (
        SCENARIO_APPLY_FORMAT,
        run_para_edit_e2e,
    )

    out: dict[str, Any] = {"ok": True, "byScope": {}}
    any_ok = False
    for scope_kind in ("cell", "block"):
        fx, par = _pick_multi(scope_kind)
        if fx is None:
            out["byScope"][scope_kind] = {"ok": False, "reason": "no fixture"}
            continue
        inv = paragraph_char_pr_inventory(fx)
        entries = inv["paragraphInventory"][par.paragraphId]
        targets = [e["charPrId"] for e in entries if e["inHeader"] and e["charPrId"] is not None]
        if not targets:
            out["byScope"][scope_kind] = {"ok": False, "reason": "no target charPr"}
            continue
        tgt = targets[0]
        sha_b = hashlib.sha256(fx.read_bytes()).hexdigest()
        mt_b = fx.stat().st_mtime_ns
        with zipfile.ZipFile(fx) as z:
            header_before = z.read("Contents/header.xml")
        with tempfile.TemporaryDirectory() as td:
            outp = Path(td) / "af.hwpx"
            r0_len = len(par.runs[0].text)
            res = run_para_edit_e2e(
                source_path=fx,
                output_path=outp,
                scenario=SCENARIO_APPLY_FORMAT,
                paragraph_id=par.paragraphId,
                range_anchor=max(0, r0_len - 1),
                range_focus=r0_len + 1,
                target_char_pr_id=tgt,
                allow_writer=True,
            )
            v7 = (res.get("verify7") or {}).get("results", {})
            rb = res.get("readback") or {}
            with zipfile.ZipFile(outp) as zo:
                header_after = zo.read("Contents/header.xml")
            out["byScope"][scope_kind] = {
                "ok": True,
                "fixture": str(fx.relative_to(PR)),
                "paragraphId": par.paragraphId,
                "targetCharPrId": tgt,
                "outputCreated": res.get("outputCreated"),
                "rejectedCount": len(res.get("rejected") or []),
                "verify7": v7,
                "readback": rb,
                "outputInSandbox": str(outp).startswith(td),
                "headerUnchanged": header_after == header_before,
            }
        out["byScope"][scope_kind]["shaPreserved"] = (
            hashlib.sha256(fx.read_bytes()).hexdigest() == sha_b
        )
        out["byScope"][scope_kind]["mtimePreserved"] = fx.stat().st_mtime_ns == mt_b
        any_ok = True
    out["ok"] = any_ok
    return out


def _check_required_keys(name: str, section: dict, keys: list[str], code: str) -> list[dict]:
    return [
        {"code": code, "level": "FAIL", "detail": f"{name}: {k}={section.get(k)}"}
        for k in keys
        if section.get(k) != "PASS"
    ]


def _check_dynamic_scope(scope_kind: str, sec: dict) -> list[dict]:
    findings: list[dict] = []
    if not sec.get("ok"):
        findings.append({"code": "SCOPE_FIXTURE_MISSING", "level": "WARN", "detail": scope_kind})
        return findings
    name = f"{scope_kind}.APPLY_FORMAT"
    if not sec["outputCreated"]:
        findings.append({"code": "OUTPUT_NOT_CREATED", "level": "FAIL", "detail": name})
        return findings
    if not sec["outputInSandbox"]:
        findings.append({"code": "OUTPUT_OUTSIDE_SANDBOX", "level": "FAIL", "detail": name})
    if sec["rejectedCount"]:
        findings.append({"code": "REJECTED_NOT_EMPTY", "level": "FAIL", "detail": name})
    if not sec["headerUnchanged"]:
        findings.append({"code": "HEADER_XML_CHANGED", "level": "FAIL", "detail": name})
    findings.extend(_check_required_keys(name, sec["verify7"], REQUIRED_V7, "V7_NOT_PASS"))
    findings.extend(_check_required_keys(name, sec["readback"], REQUIRED_RB, "READBACK_NOT_PASS"))
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
        findings.extend(_check_dynamic_scope(scope_kind, sec))
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
        "audit": "WEB-OFFICE-PARA-EDIT-APPLYFORMAT-EXISTING-CHARPR-01",
        "findings": findings,
        "verdict": "FAIL" if fail else ("WARN" if warn else "PASS"),
        "dynamic": dyn,
    }


if __name__ == "__main__":
    print(json.dumps(audit(), ensure_ascii=False, indent=2))
