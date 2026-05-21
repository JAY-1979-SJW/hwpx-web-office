"""WEB-OFFICE-PARA-EDIT-APPLYFORMAT-FONTSIZE-MATCHING-EXISTING-CHARPR-01.

matchAxisChange("fontSizePt", v) + extractAxisValues + Format Toolbar
fontSize dropdown 정합 검증. bold/underline/italic 회귀 + dropdown
candidate enabling + 운영 fixture 통계 회귀.
"""
from __future__ import annotations
import json
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

PR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PR))

MATCHER_MJS = (PR / "frontend/web_office_viewer/"
                      "format_charpr_matcher.mjs")
TOOLBAR_TSX = (PR / "frontend/web_office_viewer/components/"
                      "WebOfficeFormatToolbar.tsx")
SMOKE_JS = (PR / "frontend/web_office_viewer/"
                  "format_charpr_matcher_smoke.mjs")
BASELINE_COMMIT = "619f2e0"  # PARA_INSERT 준공 후 갱신 (8098944 → 1f442ec)


def _node_ok() -> bool:
    try:
        r = subprocess.run(["node", "--version"], capture_output=True,
                                          text=True, timeout=10)
        return r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


NODE_OK = _node_ok()
need_node = pytest.mark.skipif(not NODE_OK, reason="node not available")


def _run_smoke() -> dict:
    r = subprocess.run(["node", str(SMOKE_JS)], capture_output=True,
                                      text=True, timeout=30, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


# ── 1. matcher 모듈 확장 검증 ────────────────────────────

def test_matcher_exports_match_axis_change():
    src = MATCHER_MJS.read_text(encoding="utf-8")
    assert re.search(r"export\s+function\s+matchAxisChange\(", src)
    assert re.search(
        r'export\s+const\s+MATCH_AXIS_CHANGE_DIMENSIONS', src)
    assert re.search(r"export\s+function\s+extractAxisValues\(", src)


def test_axis_enum_includes_fontsizept():
    """fontSizePt 가 axis enum 에 포함되어 있어야 한다.
    (이후 공정에서 textColor / fontName 도 추가될 수 있음.)"""
    src = MATCHER_MJS.read_text(encoding="utf-8")
    m = re.search(
        r"MATCH_AXIS_CHANGE_DIMENSIONS\s*=\s*\[([^\]]+)\]", src)
    assert m, "MATCH_AXIS_CHANGE_DIMENSIONS not found"
    dims = re.findall(r'"(\w+)"', m.group(1))
    assert "fontSizePt" in dims, dims


def test_matcher_no_fuzzy_keyword():
    src = MATCHER_MJS.read_text(encoding="utf-8")
    for pat in (r"\bfuzzy\b", r"\bapproximate\b", r"\bsimilar\b",
                          r"Math\.abs"):
        assert not re.search(pat, src, re.IGNORECASE), pat


# ── 2. matcher smoke ────────────────────────────────────

@need_node
def test_matcher_smoke_verdict_pass():
    out = _run_smoke()
    assert out["verdict"] == "PASS", out
    bad = {k: v for k, v in out["checks"].items() if not v.get("ok")}
    assert not bad, bad


@need_node
def test_matcher_smoke_fontsize_success_and_failure():
    out = _run_smoke()
    for k in ("fontSizeMatchingSuccess",
                "fontSizeMatchingFailure",
                "fontSizeNoopReturnsNull",
                "heightMismatchExcluded",
                "axisChangeSelfExcluded"):
        assert out["checks"][k]["ok"], k


@need_node
def test_matcher_smoke_other_axes_rejected():
    """fontName 은 여전히 미허용. textColor 는 후속 공정에서 활성화."""
    out = _run_smoke()
    assert out["checks"]["axisFontNameRejected1stWave"]["ok"]


@need_node
def test_matcher_smoke_extract_axis_values():
    out = _run_smoke()
    for k in ("extractAxisValuesShape",
                "extractAxisValuesSorted",
                "extractAxisValuesCurrentMarked",
                "extractAxisValuesMatch12",
                "extractAxisValuesMatch14",
                "extractAxisValuesEnabled12",
                "extractAxisValuesRejectColor",
                "extractAxisValuesDedup"):
        assert out["checks"][k]["ok"], k


@need_node
def test_matcher_smoke_toggle_regression_preserved():
    """기존 bold/underline/italic matchToggle 회귀 유지."""
    out = _run_smoke()
    for k in ("boldToggleSuccess", "boldToggleOffSuccess",
                "underlineToggleSuccess", "italicToggleSuccess",
                "noMatchReturnsNull", "selfExcluded",
                "differentSizeNotMatched",
                "differentColorNotMatched",
                "fuzzyToggleNotMatched"):
        assert out["checks"][k]["ok"], k


# ── 3. toolbar fontSize dropdown 정합 ─────────────────────

def test_toolbar_has_fontsize_dropdown():
    src = TOOLBAR_TSX.read_text(encoding="utf-8")
    assert "FontSizeDropdown" in src
    assert "extractAxisValues" in src
    assert '"fontSizePt"' in src or "'fontSizePt'" in src
    # <select> 사용
    assert re.search(r"<select\b", src)


def test_toolbar_no_font_name_dropdown_or_html_color_input():
    """HTML color input / 외부 ColorPicker / 외부 font picker 는 계속 금지.
    (textColor / fontName 의 extractAxisValues 는 COLOR / FONTNAME 공정
    에서 활성화됨.)"""
    src = TOOLBAR_TSX.read_text(encoding="utf-8")
    forbidden = [
        r'<input[^>]+type="color"',
        r"ColorPicker", r"colorPicker",
        r"FontPicker", r"systemFonts", r"fontList",
    ]
    for pat in forbidden:
        assert not re.search(pat, src), pat


def test_toolbar_no_direct_factory_or_writer_calls():
    src = TOOLBAR_TSX.read_text(encoding="utf-8")
    forbidden = [
        r"makeApplyFormatCommand\(",
        r"applyFormatToSelection\(",
        r"save_paragraph_edits\(",
        r"apply_paragraph_edits_plan\(",
        r"create_hwpx_document\(",
        r"write_package\(",
        r"\.write_xml\(",
        r"def\s+create_char_pr\b",
        r"package\.entries\[[^\]]*header\.xml[^\]]*\]\s*=",
    ]
    for pat in forbidden:
        assert not re.search(pat, src), pat


def test_toolbar_dropdown_disabled_policy():
    """후보 없으면 select 자체 disabled."""
    src = TOOLBAR_TSX.read_text(encoding="utf-8")
    # candidates.length === 0 → disabled
    assert re.search(r"candidates\.length\s*===?\s*0", src)
    assert re.search(r"disabled=\{", src)


def test_toolbar_opt_in_default_false():
    src = TOOLBAR_TSX.read_text(encoding="utf-8")
    assert "enableApplyCommand = false" in src \
            or "enableApplyCommand=false" in src
    assert "!enableApplyCommand" in src


# ── 4. 8098944 잠금 자재 무수정 (backend / state / preview 외) ──

LOCKED_VS_8098944 = [
    # state/command/preview/smoke 는 무수정
    "frontend/web_office_viewer/para_edit_state.mjs",
    "frontend/web_office_viewer/para_edit_command.mjs",
    "frontend/web_office_viewer/components/WebOfficeFormatPreview.tsx",
    "frontend/web_office_viewer/para_edit_apply_format_smoke.mjs",
    # backend 무수정
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


def test_locked_files_unchanged_vs_baseline():
    for rel in LOCKED_VS_8098944:
        r = subprocess.run(
            ["git", "diff", BASELINE_COMMIT, "--", rel],
            capture_output=True, text=True, cwd=str(PR), timeout=20)
        assert r.returncode == 0, (rel, r.stderr)
        assert not r.stdout.strip(), (
            f"{rel} changed vs {BASELINE_COMMIT}")


# ── 5. 운영 fixture 통계 회귀: fontSize matching ≥ 90% ─────

def _fixtures(limit: int = 30) -> list[Path]:
    db = PR / "data/recognition_corpus/corpus.sqlite3"
    if not db.is_file():
        return []
    try:
        conn = sqlite3.connect(db)
        rows = conn.execute(f"""
            SELECT d.source_path FROM hwpx_documents d
            WHERE d.inventory_status='FOUND'
              AND d.file_size BETWEEN 30000 AND 300000
            ORDER BY d.first_seen_at LIMIT {limit}
        """).fetchall()
        conn.close()
    except sqlite3.Error:
        return []
    return [PR / r[0] for r in rows if (PR / r[0]).is_file()]


FX = _fixtures(30)
need_fx = pytest.mark.skipif(not FX, reason="no operational fixtures")


@need_fx
def test_fixture_fontsize_matching_at_least_90_pct():
    from scripts.hwpx.web_office.charpr_inventory import (
        char_pr_defs_only)
    matched = 0; total = 0
    for p in FX:
        try:
            defs = char_pr_defs_only(p)
        except Exception:  # noqa: BLE001
            continue
        if not defs:
            continue
        total += 1
        # group by (fontName, textColor, bold, italic, underline) —
        # within group, count distinct fontSizePt
        grp: dict = {}
        for cid, d in defs.items():
            key = (d.get("fontName"), d.get("textColor"),
                          d.get("bold"), d.get("italic"),
                          d.get("underline"))
            grp.setdefault(key, set()).add(d.get("fontSizePt"))
        if any(len({s for s in g if s is not None}) >= 2
                  for g in grp.values()):
            matched += 1
    assert total >= 5, f"too few fixtures: {total}"
    pct = matched / total
    assert pct >= 0.9, f"fontSize matching {pct:.1%} < 90%"


# ── 6. audit verdict PASS ──────────────────────────────────

def test_audit_script_pass():
    from scripts.ops.audit_web_office_para_edit_applyformat_fontsize_matching_existing_charpr import (
        audit)
    rep = audit()
    fails = [f for f in rep["findings"]
              if f.get("level") == "FAIL"]
    assert not fails, json.dumps(rep, ensure_ascii=False, indent=2)
    assert rep["verdict"] in ("PASS", "WARN"), rep
