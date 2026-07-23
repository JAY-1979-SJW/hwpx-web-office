"""WEB-OFFICE-PARA-EDIT-APPLYFORMAT-COLOR-MATCHING-EXISTING-CHARPR-01.

textColor exact matching + ColorPalette swatch UI 검증.
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
BASELINE_COMMIT = "6111a9e"  # lineseg 보존 로직 준공 후 갱신 (517849c -> 6111a9e)


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


# ── 1. matcher 확장 ──────────────────────────────────────

def test_axis_enum_extended_with_text_color():
    """textColor 가 axis enum 에 포함. fontName 은 후속 공정에서 추가됨."""
    src = MATCHER_MJS.read_text(encoding="utf-8")
    m = re.search(
        r"MATCH_AXIS_CHANGE_DIMENSIONS\s*=\s*\[([^\]]+)\]", src)
    assert m, "MATCH_AXIS_CHANGE_DIMENSIONS not found"
    dims = re.findall(r'"(\w+)"', m.group(1))
    assert "textColor" in dims, dims
    assert "fontSizePt" in dims, dims


def test_matcher_textcolor_branch_exists():
    src = MATCHER_MJS.read_text(encoding="utf-8")
    assert re.search(r'axis\s*===?\s*"textColor"', src)


def test_matcher_no_fuzzy_color_distance():
    src = MATCHER_MJS.read_text(encoding="utf-8")
    for pat in (r"\bfuzzy\b", r"\bapproximate\b", r"\bsimilar\b",
                          r"Math\.abs", r"\bhsv\b", r"\bhsl\b",
                          r"colorDistance", r"deltaE"):
        assert not re.search(pat, src, re.IGNORECASE), pat


# ── 2. smoke verdict + color checks ────────────────────

@need_node
def test_smoke_verdict_pass():
    out = _run_smoke()
    assert out["verdict"] == "PASS", out
    bad = {k: v for k, v in out["checks"].items() if not v.get("ok")}
    assert not bad, bad


@need_node
def test_smoke_color_matching_success_and_failure():
    out = _run_smoke()
    for k in ("colorMatchingBlackToRed",
                "colorMatchingBlackToBlue",
                "colorMatchingRedToBlack",
                "colorMatchingNotFound",
                "colorMatchingNoopReturnsNull",
                "colorMatchingDifferentSizeRejected",
                "colorMatchingDifferentBoldRejected",
                "colorMatchingExactOnly"):
        assert out["checks"][k]["ok"], k


@need_node
def test_smoke_extract_axis_values_color():
    out = _run_smoke()
    for k in ("extractAxisValuesColorIsArray",
                "extractAxisValuesColorDedup",
                "extractAxisValuesColorCurrent",
                "extractAxisValuesColorEnabled",
                "extractAxisValuesColorDisabledForOtherSize"):
        assert out["checks"][k]["ok"], k


@need_node
def test_smoke_fontname_still_rejected():
    out = _run_smoke()
    assert out["checks"]["fontNameStillRejected"]["ok"]
    assert out["checks"]["axisFontNameRejected1stWave"]["ok"]


@need_node
def test_smoke_fontsize_and_toggle_regression():
    """fontSize matching + bold/underline/italic 회귀 보존."""
    out = _run_smoke()
    for k in ("fontSizeMatchingSuccess",
                "fontSizeMatchingFailure",
                "fontSizeNoopReturnsNull",
                "boldToggleSuccess",
                "underlineToggleSuccess",
                "italicToggleSuccess",
                "fuzzyToggleNotMatched"):
        assert out["checks"][k]["ok"], k


# ── 3. ColorPalette UI ────────────────────────────────

def test_toolbar_has_color_palette_component():
    src = TOOLBAR_TSX.read_text(encoding="utf-8")
    assert "ColorPalette" in src
    assert 'extractAxisValues' in src
    assert '"textColor"' in src or "'textColor'" in src
    # swatch button 사용
    assert "wo-color-swatch" in src


def test_toolbar_no_color_picker_or_html_color_input():
    """<input type="color"> / 외부 ColorPicker / +색상추가 금지."""
    src = TOOLBAR_TSX.read_text(encoding="utf-8")
    forbidden = [
        r'<input[^>]+type="color"',
        r"ColorPicker",
        r"colorPicker",
        r'react-color',
        r"새\s*색상\s*추가",
        r"createColor\(",
        # WEB-OFFICE-PARA-EDIT-APPLYFORMAT-FONTNAME-MATCHING-EXISTING-CHARPR-01
        # 이후 FontNameDropdown 활성화. 1차 color 공정에서만 금지였음.
    ]
    for pat in forbidden:
        assert not re.search(pat, src), pat


def test_toolbar_color_palette_disabled_policy():
    src = TOOLBAR_TSX.read_text(encoding="utf-8")
    # data-disabled + disabled prop + current 처리
    assert re.search(r'data-disabled', src)
    assert "wo-color-empty" in src
    assert "현재 문서에 같은 속성 조합의 기존 색상 스타일이 없습니다" in src


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


# ── 4. c3bc92b 잠금 자재 무수정 (backend / state / preview / 등) ─

LOCKED_VS_C3BC92B = [
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


def test_locked_files_unchanged_vs_baseline():
    for rel in LOCKED_VS_C3BC92B:
        r = subprocess.run(
            ["git", "diff", BASELINE_COMMIT, "--", rel],
            capture_output=True, text=True, cwd=str(PR), timeout=20)
        assert r.returncode == 0, (rel, r.stderr)
        assert not r.stdout.strip(), (
            f"{rel} changed vs {BASELINE_COMMIT}")


# ── 5. 운영 fixture 통계 회귀 ──────────────────────────

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
def test_fixture_color_matching_fixture_level_at_least_80_pct():
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
        grp: dict = {}
        for cid, d in defs.items():
            key = (d.get("fontName"), d.get("fontSizePt"),
                          d.get("bold"), d.get("italic"),
                          d.get("underline"))
            grp.setdefault(key, set()).add(d.get("textColor"))
        if any(len({c for c in g if c is not None}) >= 2
                  for g in grp.values()):
            matched += 1
    assert total >= 5, f"too few fixtures: {total}"
    pct = matched / total
    assert pct >= 0.8, f"color fixture-level {pct:.1%} < 80%"


@need_fx
def test_fixture_per_charpr_enabled_color_avg_at_least_015():
    from scripts.hwpx.web_office.charpr_inventory import (
        char_pr_defs_only)
    all_avgs: list[float] = []
    for p in FX:
        try:
            defs = char_pr_defs_only(p)
        except Exception:  # noqa: BLE001
            continue
        if not defs:
            continue
        grp: dict = {}
        for cid, d in defs.items():
            key = (d.get("fontName"), d.get("fontSizePt"),
                          d.get("bold"), d.get("italic"),
                          d.get("underline"))
            grp.setdefault(key, set()).add(d.get("textColor"))
        for cid, d in defs.items():
            c0 = d.get("textColor")
            key = (d.get("fontName"), d.get("fontSizePt"),
                          d.get("bold"), d.get("italic"),
                          d.get("underline"))
            others = {c for c in grp.get(key, set())
                                if c is not None and c != c0}
            all_avgs.append(len(others))
    if not all_avgs:
        pytest.skip("no defs")
    avg = sum(all_avgs) / len(all_avgs)
    assert avg >= 0.15, f"per-charPr enabled color avg {avg:.3f} < 0.15"


# ── 6. audit verdict PASS ──────────────────────────────────

def test_audit_script_pass():
    from scripts.ops.audit_web_office_para_edit_applyformat_color_matching_existing_charpr import (
        audit)
    rep = audit()
    fails = [f for f in rep["findings"]
              if f.get("level") == "FAIL"]
    assert not fails, json.dumps(rep, ensure_ascii=False, indent=2)
    assert rep["verdict"] in ("PASS", "WARN"), rep
