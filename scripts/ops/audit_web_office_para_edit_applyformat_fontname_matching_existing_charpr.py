"""WEB-OFFICE-PARA-EDIT-APPLYFORMAT-FONTNAME-MATCHING-EXISTING-CHARPR-01.

fontName exact matching (fontFace identity 면제) + FontNameDropdown UI
의 정적·동적 검증.
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
BASELINE_COMMIT = "334d665"

REQUIRED_MATCHER_PATTERNS = [
    r"export\s+function\s+matchAxisChange\(",
    r"export\s+function\s+extractAxisValues\(",
    r'export\s+const\s+MATCH_AXIS_CHANGE_DIMENSIONS',
    r'"fontName"',
    r'axis\s*===?\s*"fontName"',
    r'axis\s*===?\s*"textColor"',
    r'axis\s*===?\s*"fontSizePt"',
    r"export\s+function\s+matchToggle\(",
]
FORBIDDEN_MATCHER_PATTERNS = [
    r"\bfuzzy\b", r"\bapproximate\b", r"\bsimilar\b",
    r"\balias\b", r"\blevenshtein\b",
    r"\bhsv\b", r"\bhsl\b",
    r"colorDistance", r"deltaE",
    r"Math\.abs",
]
REQUIRED_TOOLBAR_PATTERNS = [
    r"FontNameDropdown",
    r"ColorPalette",          # color 회귀
    r"FontSizeDropdown",      # fontSize 회귀
    r"extractAxisValues",
    r'"fontName"',
    r"wo-fn-empty",
    r"<select\b",
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
    # 외부 font picker / 시스템 fontList
    r"FontPicker", r"systemFonts", r"fontList",
    r"react-fontpicker", r"google-fonts",
    # alias 추천 / 신규 추가
    r"새\s*폰트\s*추가",
    r"createFont",
    r"aliasRecommend",
    # color 차단 유지
    r'<input[^>]+type="color"',
    r"ColorPicker", r"colorPicker",
]

# 86c030d 기준 잠금 (backend / state / preview / smoke 무수정)
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
            findings.append({"code": "MATCHER_FORBIDDEN",
                              "level": "FAIL", "detail": pat})
    # axis enum 정확히 3개
    m = re.search(
        r"MATCH_AXIS_CHANGE_DIMENSIONS\s*=\s*\[([^\]]+)\]", src)
    if m:
        dims = set(re.findall(r'"(\w+)"', m.group(1)))
        if dims != {"fontSizePt", "textColor", "fontName"}:
            findings.append({"code": "AXIS_ENUM_DEVIATION",
                              "level": "FAIL",
                              "detail": f"dims={sorted(dims)}"})
    # fontName 분기에서 fontFace 가 비교 키에 포함되지 않아야 한다
    fb = re.search(
        r'axis\s*===?\s*"fontName"[\s\S]{0,2000}?return\s+null;', src)
    if fb:
        ok_m = re.search(r'otherKeys\s*=\s*\[([^\]]+)\]', fb.group(0))
        if ok_m:
            keys = re.findall(r'"(\w+)"', ok_m.group(1))
            if "fontFace" in keys:
                findings.append({
                    "code": "FONTFACE_IN_FONTNAME_IDENTITY",
                    "level": "FAIL",
                    "detail":
                        f"fontFace must be excluded: {keys}"})
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
            findings.append({"code": "TOOLBAR_FORBIDDEN",
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
    required = ("fontNameMatchingDotumToDotumChe",
                          "fontNameMatchingFontFaceIgnored",
                          "fontNameAliasNotAutoMatched",
                          "extractAxisValuesFontNameCurrent",
                          "axisChangeDimensionsThree")
    for k in required:
        if k not in (out.get("checks") or {}):
            findings.append({"code": "SMOKE_CHECK_MISSING",
                              "level": "FAIL", "detail": k})
    return findings


def _run_fixture_stats() -> dict[str, Any]:
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
    matched = 0; total = 0
    per_avg: list[float] = []
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
        grp: dict = {}
        for cid, d in defs.items():
            key = (d.get("fontSizePt"), d.get("textColor"),
                          d.get("bold"), d.get("italic"),
                          d.get("underline"))
            grp.setdefault(key, set()).add(d.get("fontName"))
        if any(len({n for n in g if n is not None}) >= 2
                  for g in grp.values()):
            matched += 1
        for cid, d in defs.items():
            nm = d.get("fontName")
            key = (d.get("fontSizePt"), d.get("textColor"),
                          d.get("bold"), d.get("italic"),
                          d.get("underline"))
            others = {n for n in grp.get(key, set())
                                if n is not None and n != nm}
            per_avg.append(len(others))
    return {
        "ok": True,
        "totalFixtures": total,
        "fontNameFixturePct": matched / total if total else 0,
        "perCharPrAvgFontName":
            sum(per_avg) / len(per_avg) if per_avg else 0,
    }


def _check_fixture_stats(stats: dict) -> list[dict]:
    findings: list[dict] = []
    if not stats.get("ok"):
        findings.append({"code": "FIXTURE_STATS_SKIPPED",
                          "level": "WARN",
                          "detail": stats.get("reason")})
        return findings
    if stats["totalFixtures"] < 5:
        findings.append({"code": "FIXTURE_TOO_FEW",
                          "level": "WARN",
                          "detail": str(stats["totalFixtures"])})
        return findings
    if stats["fontNameFixturePct"] < 0.9:
        findings.append({"code": "FONTNAME_FIXTURE_PCT_TOO_LOW",
                          "level": "FAIL",
                          "detail":
                              f"{stats['fontNameFixturePct']:.1%}"})
    if stats["perCharPrAvgFontName"] < 0.5:
        findings.append({"code": "PER_CHARPR_AVG_TOO_LOW",
                          "level": "FAIL",
                          "detail":
                              f"{stats['perCharPrAvgFontName']:.3f}"})
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
                          "FONTNAME-MATCHING-EXISTING-CHARPR-01",
        "baseline": BASELINE_COMMIT,
        "findings": findings,
        "verdict": "FAIL" if fail else ("WARN" if warn else "PASS"),
        "smoke": smoke,
        "fixtureStats": stats,
    }


if __name__ == "__main__":
    print(json.dumps(audit(), ensure_ascii=False, indent=2))
