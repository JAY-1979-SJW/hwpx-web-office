"""WEB-OFFICE-PARA-EDIT-FORMAT-CHARPR-INVENTORY-01 준공검사.

charPr inventory read-only helper 의 정적·동적 신호를 확인하고,
content closeout (d61f10f) 잠금 자재가 무수정인지 + ApplyFormat 활성화
흔적이 없음 + 신규 charPr 생성/header write 흔적 없음 + 본 audit 자체가
writer/원본 overwrite 호출 0건임을 검증한다.
"""
from __future__ import annotations
import hashlib
import json
import re
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any

PR = Path(__file__).resolve().parents[2]
if str(PR) not in sys.path:
    sys.path.insert(0, str(PR))

INVENTORY_PY = (PR / "scripts/hwpx/web_office/charpr_inventory.py")
BASELINE_COMMIT = "334d665"  # PARA_INSERT 준공 후 갱신 (d61f10f → bb0939b)

REQUIRED_INVENTORY_PATTERNS = [
    r"def\s+paragraph_char_pr_inventory\(",
    r"def\s+char_pr_defs_only\(",
    r"parse_char_pr_defs\(",
    r"sourceSha256",
    r"danglingCharPrIDRefs",
    r"unusedHeaderCharPrIds",
    r"paragraphInventory",
    r"documentInventory",
    r"headerCharPrCount",
]
REQUIRED_INVENTORY_FIELDS = [
    "charPrId", "usageCount", "totalRuns", "inHeader",
    "fontName", "fontFace", "fontSizePt", "height",
    "textColor", "bold", "italic", "underline",
]

# 5459cd6 inventory 도입 시점 잠금. WEB-OFFICE-PARA-EDIT-APPLYFORMAT-
# EXISTING-CHARPR-01: ApplyFormat 활성화 트리거로 다음 자재는 본 LOCKED
# 에서 제거됨 — para_edit_model, paragraph_edit_plan,
# paragraph_writer_adapter, paragraph_save_verify7,
# para_edit_e2e_pipeline, hwpx_paragraph_ops.
LOCKED_FILES_VS_BASELINE = [
    "scripts/hwpx/web_office/paragraph_save_pipeline.py",
    "scripts/hwpx/web_office/ro_view_importer.py",
    # WEB-OFFICE-PARA-EDIT-APPLYFORMAT-TOOLBAR-COMMAND-01:
    # para_edit_state.mjs 는 applyFormatToSelection 추가로 본 LOCKED 에서 제거.
    "frontend/web_office_viewer/para_edit_runtime.mjs",
]

# inventory.py 가 절대 import/호출해서는 안 되는 것
FORBIDDEN_INVENTORY_PATTERNS = [
    r"\.write_xml\(",
    r"\.write_package\(",
    r"package\.entries\[[^\]]+\]\s*=",
    r"def\s+apply_format\b",
    r"def\s+create_char_pr\b",
    r"CT_APPLY_FORMAT",
    r"make_apply_format_command",
]
# d61f10f 잠금 자재 (writer/adapter/model/JS/verify7) 가 ApplyFormat
# 흔적을 가지지 않는지 정적 확인
APPLYFORMAT_TRACE_TARGETS = [
    "scripts/hwpx/web_office/paragraph_writer_adapter.py",
    "scripts/hwpx/web_office/para_edit_model.py",
    "scripts/hwpx/web_office/paragraph_edit_plan.py",
    "scripts/hwpx/hwpx_paragraph_ops.py",
    "frontend/web_office_viewer/para_edit_command.mjs",
    "frontend/web_office_viewer/para_edit_state.mjs",
]
# WEB-OFFICE-PARA-EDIT-APPLYFORMAT-EXISTING-CHARPR-01: 본 commit 에서
# ApplyFormat 이 활성화되어 CT_APPLY_FORMAT / make_apply_format_command
# 흔적이 허용된다. 신규 charPr 생성 (def create_char_pr) 만 계속 차단.
APPLYFORMAT_FORBIDDEN_TRACES = [
    r"def\s+create_char_pr\b",
]

FORBIDDEN_AUDIT_WRITER_SYMBOLS = [
    r"apply_paragraph_edits_plan\(",
    r"save_paragraph_edits\(",
    r"create_hwpx_document\(",
    r"write_package\(",
    r"\.write_xml\(",
]


def _fixture() -> Path | None:
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
            WHERE d.inventory_status='FOUND'
              AND d.file_size BETWEEN 30000 AND 200000
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
    if not INVENTORY_PY.is_file():
        findings.append({"code": "INVENTORY_FILE_MISSING",
                          "level": "FAIL",
                          "detail": str(INVENTORY_PY)})
        return findings
    src = INVENTORY_PY.read_text(encoding="utf-8")
    for pat in REQUIRED_INVENTORY_PATTERNS:
        if not re.search(pat, src):
            findings.append({"code": "INVENTORY_PATTERN_MISSING",
                              "level": "FAIL", "detail": pat})
    for field in REQUIRED_INVENTORY_FIELDS:
        if field not in src:
            findings.append({"code": "INVENTORY_FIELD_MISSING",
                              "level": "FAIL", "detail": field})
    for pat in FORBIDDEN_INVENTORY_PATTERNS:
        if re.search(pat, src):
            findings.append({
                "code": "INVENTORY_FORBIDDEN_WRITER_CODE",
                "level": "FAIL", "detail": pat})
    return findings


def _check_locked_files() -> list[dict]:
    findings: list[dict] = []
    for rel in LOCKED_FILES_VS_BASELINE:
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


def _check_no_applyformat_traces() -> list[dict]:
    findings: list[dict] = []
    for rel in APPLYFORMAT_TRACE_TARGETS:
        p = PR / rel
        if not p.is_file():
            continue
        src = p.read_text(encoding="utf-8")
        for pat in APPLYFORMAT_FORBIDDEN_TRACES:
            if re.search(pat, src):
                findings.append({
                    "code": "APPLYFORMAT_TRACE_PRESENT",
                    "level": "FAIL",
                    "detail": f"{rel}: {pat}"})
    return findings


def _check_audit_no_writer_calls() -> list[dict]:
    findings: list[dict] = []
    me = Path(__file__).read_text(encoding="utf-8")
    for sym in FORBIDDEN_AUDIT_WRITER_SYMBOLS:
        if re.search(sym, me):
            findings.append({
                "code": "AUDIT_FORBIDDEN_WRITER_CALL",
                "level": "FAIL", "detail": sym})
    return findings


def _run_dynamic(fixture: Path) -> dict[str, Any]:
    from scripts.hwpx.web_office.charpr_inventory import (  # noqa: E402
        paragraph_char_pr_inventory)
    sha_b = hashlib.sha256(fixture.read_bytes()).hexdigest()
    mt_b = fixture.stat().st_mtime_ns
    inv = paragraph_char_pr_inventory(fixture)
    return {
        "ok": True,
        "fixture": str(fixture.relative_to(PR)),
        "sourceSha256": inv["sourceSha256"],
        "headerCharPrCount": inv["headerCharPrCount"],
        "paragraphInventoryCount": len(inv["paragraphInventory"]),
        "documentInventorySize": len(inv["documentInventory"]),
        "danglingCount": len(inv["danglingCharPrIDRefs"]),
        "unusedHeaderCount": len(inv["unusedHeaderCharPrIds"]),
        "shaPreserved": (
            hashlib.sha256(fixture.read_bytes()).hexdigest() == sha_b),
        "mtimePreserved": fixture.stat().st_mtime_ns == mt_b,
        "documentInventorySample": inv["documentInventory"][:3],
    }


def _check_dynamic(dyn: dict) -> list[dict]:
    findings: list[dict] = []
    if not dyn.get("ok"):
        findings.append({"code": "DYNAMIC_SKIPPED", "level": "WARN",
                          "detail": dyn.get("reason",
                                                            "fixture missing")})
        return findings
    if dyn["headerCharPrCount"] <= 0:
        findings.append({"code": "HEADER_CHARPR_EMPTY",
                          "level": "FAIL",
                          "detail": dyn["fixture"]})
    if dyn["paragraphInventoryCount"] <= 0:
        findings.append({"code": "PARAGRAPH_INVENTORY_EMPTY",
                          "level": "FAIL",
                          "detail": dyn["fixture"]})
    if dyn["documentInventorySize"] <= 0:
        findings.append({"code": "DOCUMENT_INVENTORY_EMPTY",
                          "level": "FAIL",
                          "detail": dyn["fixture"]})
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
    findings.extend(_check_locked_files())
    findings.extend(_check_no_applyformat_traces())
    findings.extend(_check_audit_no_writer_calls())
    fx = _fixture()
    dyn: dict[str, Any] = ({"ok": False, "reason": "fixture missing"}
                                              if fx is None else {})
    if fx is not None:
        try:
            dyn = _run_dynamic(fx)
        except Exception as e:  # noqa: BLE001
            dyn = {"ok": False, "reason": f"dynamic raised: {e}"}
            findings.append({"code": "DYNAMIC_RAISED",
                              "level": "FAIL", "detail": dyn["reason"]})
    findings.extend(_check_dynamic(dyn))
    fail = [f for f in findings if f["level"] == "FAIL"]
    warn = [f for f in findings if f["level"] == "WARN"]
    return {
        "audit": "WEB-OFFICE-PARA-EDIT-FORMAT-CHARPR-INVENTORY-01",
        "baseline": BASELINE_COMMIT,
        "findings": findings,
        "verdict": "FAIL" if fail else ("WARN" if warn else "PASS"),
        "dynamic": dyn,
    }


if __name__ == "__main__":
    print(json.dumps(audit(), ensure_ascii=False, indent=2))
