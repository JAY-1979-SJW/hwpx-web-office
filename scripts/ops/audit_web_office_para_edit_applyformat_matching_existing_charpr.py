"""WEB-OFFICE-PARA-EDIT-APPLYFORMAT-MATCHING-EXISTING-CHARPR-01 준공.

existing charPr matcher + Format Toolbar 의 정적·동적 검증.
"""
from __future__ import annotations
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

MATCHER_MJS = (PR / "frontend/web_office_viewer/"
                      "format_charpr_matcher.mjs")
TOOLBAR_TSX = (PR / "frontend/web_office_viewer/components/"
                      "WebOfficeFormatToolbar.tsx")
SMOKE_JS = (PR / "frontend/web_office_viewer/"
                  "format_charpr_matcher_smoke.mjs")
BASELINE_COMMIT = "6111a9e"  # lineseg 보존 로직 준공 후 갱신 (517849c -> 6111a9e)

REQUIRED_MATCHER_PATTERNS = [
    r"export\s+function\s+matchToggle\(",
    r"export\s+function\s+matchAllToggles\(",
    r'export\s+const\s+MATCH_DIMENSIONS',
    r'"bold"', r'"underline"', r'"italic"',
    r"_attrsEqual\(",
    r"fontName", r"fontSizePt", r"textColor",
]
FORBIDDEN_MATCHER_PATTERNS = [
    r"fuzzy", r"approximate", r"similar",
    r"Math\.abs",
    r"prompt\(", r"showColorPicker",
    r"def\s+create_char_pr\b",
]
REQUIRED_TOOLBAR_PATTERNS = [
    r"export\s+function\s+WebOfficeFormatToolbar\(",
    r"matchToggle",
    r"MATCH_DIMENSIONS",
    r"enableApplyCommand",
    r"onApplyCharPr",
    r"매칭되는 기존 스타일이 없습니다",
    r"data-disabled",
    r"data-applies-format",
]
FORBIDDEN_TOOLBAR_PATTERNS = [
    r"makeApplyFormatCommand\(",
    r"applyFormatToSelection\(",
    r"save_paragraph_edits\(",
    r"apply_paragraph_edits_plan\(",
    r"create_hwpx_document\(",
    r"write_package\(",
    r"\.write_xml\(",
    r"def\s+create_char_pr\b",
    r"package\.entries\[[^\]]*header\.xml[^\]]*\]\s*=",
    # color/fontSize 직접 input 금지
    r'<input[^>]+type="color"',
    r'<input[^>]+type="number"',
    r"신규\s*charPr",
    r"createCharPr",
]

# af1dcf3 기준 잠금 자재
LOCKED_FILES_VS_BASELINE = [
    "frontend/web_office_viewer/para_edit_state.mjs",
    "frontend/web_office_viewer/para_edit_command.mjs",
    "frontend/web_office_viewer/components/WebOfficeFormatPreview.tsx",
    "frontend/web_office_viewer/para_edit_apply_format_smoke.mjs",
    "scripts/hwpx/hwpx_paragraph_ops.py",
    "scripts/hwpx/hwpx_edit_tool.py",
    "scripts/hwpx/web_office/para_edit_model.py",
    "scripts/hwpx/web_office/paragraph_edit_plan.py",
    "scripts/hwpx/web_office/paragraph_writer_adapter.py",
    "scripts/hwpx/web_office/paragraph_save_verify7.py",
    "scripts/hwpx/web_office/para_edit_e2e_pipeline.py",
    "scripts/hwpx/web_office/paragraph_save_pipeline.py",
    "scripts/hwpx/web_office/charpr_inventory.py",
    "scripts/hwpx/web_office/render_payload.py",
]

FORBIDDEN_AUDIT_WRITER_SYMBOLS = [
    r"apply_paragraph_edits_plan\(",
    r"save_paragraph_edits\(",
    r"create_hwpx_document\(",
    r"write_package\(",
    r"\.write_xml\(",
]


def _check_matcher_static() -> list[dict]:
    findings: list[dict] = []
    if not MATCHER_MJS.is_file():
        findings.append({"code": "MATCHER_MISSING", "level": "FAIL"})
        return findings
    src = MATCHER_MJS.read_text(encoding="utf-8")
    for pat in REQUIRED_MATCHER_PATTERNS:
        if not re.search(pat, src):
            findings.append({"code": "MATCHER_PATTERN_MISSING",
                              "level": "FAIL", "detail": pat})
    for pat in FORBIDDEN_MATCHER_PATTERNS:
        if re.search(pat, src, re.IGNORECASE):
            findings.append({"code": "MATCHER_FORBIDDEN_PATTERN",
                              "level": "FAIL", "detail": pat})
    return findings


def _check_toolbar_static() -> list[dict]:
    findings: list[dict] = []
    if not TOOLBAR_TSX.is_file():
        findings.append({"code": "TOOLBAR_MISSING", "level": "FAIL"})
        return findings
    src = TOOLBAR_TSX.read_text(encoding="utf-8")
    for pat in REQUIRED_TOOLBAR_PATTERNS:
        if not re.search(pat, src):
            findings.append({"code": "TOOLBAR_PATTERN_MISSING",
                              "level": "FAIL", "detail": pat})
    for pat in FORBIDDEN_TOOLBAR_PATTERNS:
        if re.search(pat, src):
            findings.append({"code": "TOOLBAR_FORBIDDEN_PATTERN",
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


def _check_audit_no_writer_calls() -> list[dict]:
    findings: list[dict] = []
    me = Path(__file__).read_text(encoding="utf-8")
    for sym in FORBIDDEN_AUDIT_WRITER_SYMBOLS:
        if re.search(sym, me):
            findings.append({"code": "AUDIT_FORBIDDEN_WRITER_CALL",
                              "level": "FAIL", "detail": sym})
    return findings


def _node_ok() -> bool:
    try:
        r = subprocess.run(["node", "--version"], capture_output=True,
                                          text=True, timeout=10)
        return r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _run_smoke() -> tuple[dict | None, str]:
    if not _node_ok():
        return None, "node not available"
    if not SMOKE_JS.is_file():
        return None, "smoke missing"
    r = subprocess.run(["node", str(SMOKE_JS)], capture_output=True,
                                      text=True, timeout=30, encoding="utf-8")
    if r.returncode != 0:
        return None, f"rc={r.returncode}: {r.stderr.strip()}"
    try:
        return json.loads(r.stdout), ""
    except json.JSONDecodeError as e:
        return None, f"json: {e}"


def _check_smoke(out: dict) -> list[dict]:
    findings: list[dict] = []
    if out.get("verdict") != "PASS":
        findings.append({"code": "SMOKE_VERDICT_NOT_PASS",
                          "level": "FAIL",
                          "detail": out.get("verdict")})
    for name, c in (out.get("checks") or {}).items():
        if not c.get("ok"):
            findings.append({"code": "SMOKE_CHECK_FAIL",
                              "level": "FAIL",
                              "detail": f"{name}: {c}"})
    return findings


def _run_fixture_stats() -> dict[str, Any]:
    """운영 fixture 의 bold/italic 매칭 가능률 통계."""
    db = PR / "data/recognition_corpus/corpus.sqlite3"
    if not db.is_file():
        return {"ok": False, "reason": "no corpus db"}
    try:
        conn = sqlite3.connect(db)
        rows = conn.execute("""
            SELECT d.source_path FROM hwpx_documents d
            WHERE d.inventory_status='FOUND'
              AND d.file_size BETWEEN 30000 AND 300000
            ORDER BY d.first_seen_at LIMIT 30
        """).fetchall()
        conn.close()
    except sqlite3.Error as e:
        return {"ok": False, "reason": str(e)}
    from scripts.hwpx.web_office.charpr_inventory import (  # noqa: E402
        char_pr_defs_only)
    total = 0; bold = 0; italic = 0; underline = 0
    for (sp,) in rows:
        p = PR / sp
        if not p.is_file():
            continue
        try:
            defs = char_pr_defs_only(p)
        except Exception:  # noqa: BLE001
            continue
        if not defs:
            continue
        total += 1
        # bold pairs
        gB: dict = {}; gI: dict = {}; gU: dict = {}
        for cid, d in defs.items():
            kB = (d.get("fontName"), d.get("fontSizePt"),
                          d.get("textColor"), d.get("italic"),
                          d.get("underline"))
            kI = (d.get("fontName"), d.get("fontSizePt"),
                          d.get("textColor"), d.get("bold"),
                          d.get("underline"))
            kU = (d.get("fontName"), d.get("fontSizePt"),
                          d.get("textColor"), d.get("bold"),
                          d.get("italic"))
            gB.setdefault(kB, set()).add(d.get("bold"))
            gI.setdefault(kI, set()).add(d.get("italic"))
            gU.setdefault(kU, set()).add(d.get("underline"))
        if any(True in g and False in g for g in gB.values()):
            bold += 1
        if any(True in g and False in g for g in gI.values()):
            italic += 1
        if any(True in g and False in g for g in gU.values()):
            underline += 1
    return {
        "ok": True,
        "totalFixtures": total,
        "boldPct": bold / total if total else 0,
        "italicPct": italic / total if total else 0,
        "underlinePct": underline / total if total else 0,
    }


def _check_fixture_stats(stats: dict) -> list[dict]:
    findings: list[dict] = []
    if not stats.get("ok"):
        findings.append({"code": "FIXTURE_STATS_SKIPPED",
                          "level": "WARN",
                          "detail": stats.get("reason")})
        return findings
    if stats["totalFixtures"] < 5:
        findings.append({"code": "FIXTURE_STATS_TOO_FEW",
                          "level": "WARN",
                          "detail": f"total={stats['totalFixtures']}"})
        return findings
    if stats["boldPct"] < 0.2:
        findings.append({"code": "BOLD_MATCH_TOO_LOW",
                          "level": "FAIL",
                          "detail": f"bold={stats['boldPct']:.1%}"})
    if stats["italicPct"] > 0.3:
        findings.append({
            "code": "ITALIC_MATCH_UNEXPECTEDLY_HIGH",
            "level": "FAIL",
            "detail": f"italic={stats['italicPct']:.1%}"})
    return findings


def audit() -> dict[str, Any]:
    findings: list[dict] = []
    findings.extend(_check_matcher_static())
    findings.extend(_check_toolbar_static())
    findings.extend(_check_locked_files())
    findings.extend(_check_audit_no_writer_calls())

    smoke, smoke_err = _run_smoke()
    if smoke is None:
        if "node not available" in smoke_err:
            findings.append({"code": "SMOKE_SKIPPED", "level": "WARN",
                              "detail": smoke_err})
        else:
            findings.append({"code": "SMOKE_RUN_FAIL",
                              "level": "FAIL", "detail": smoke_err})
    else:
        findings.extend(_check_smoke(smoke))

    stats = _run_fixture_stats()
    findings.extend(_check_fixture_stats(stats))

    fail = [f for f in findings if f["level"] == "FAIL"]
    warn = [f for f in findings if f["level"] == "WARN"]
    return {
        "audit": "WEB-OFFICE-PARA-EDIT-APPLYFORMAT-"
                          "MATCHING-EXISTING-CHARPR-01",
        "baseline": BASELINE_COMMIT,
        "findings": findings,
        "verdict": "FAIL" if fail else ("WARN" if warn else "PASS"),
        "smoke": smoke,
        "fixtureStats": stats,
    }


if __name__ == "__main__":
    print(json.dumps(audit(), ensure_ascii=False, indent=2))
