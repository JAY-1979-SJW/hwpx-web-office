"""WEB-OFFICE-PARA-EDIT-APPLYFORMAT-FONTNAME-MATCHING-EXISTING-CHARPR-01.

fontName exact matching + fontFace 정합 면제 + FontNameDropdown UI 검증.
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
BASELINE_COMMIT = "98d64ed"  # PARA_INSERT 준공 후 갱신 (86c030d → 1f442ec)


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

def test_axis_enum_includes_three_dimensions():
    src = MATCHER_MJS.read_text(encoding="utf-8")
    m = re.search(
        r"MATCH_AXIS_CHANGE_DIMENSIONS\s*=\s*\[([^\]]+)\]", src)
    assert m, "MATCH_AXIS_CHANGE_DIMENSIONS not found"
    dims = set(re.findall(r'"(\w+)"', m.group(1)))
    assert dims == {"fontSizePt", "textColor", "fontName"}, dims


def test_matcher_fontname_branch_exists():
    src = MATCHER_MJS.read_text(encoding="utf-8")
    assert re.search(r'axis\s*===?\s*"fontName"', src)


def test_matcher_fontname_excludes_fontface_from_identity():
    """fontName 분기의 비교 키 목록에 fontFace 가 들어 있지 않아야 한다.
    (corpus 실측 fontFace ↔ fontName 1:n 다대다)"""
    src = MATCHER_MJS.read_text(encoding="utf-8")
    # fontName 분기 코드 블록 찾기 (axis === "fontName" 다음 줄들)
    m = re.search(
        r'axis\s*===?\s*"fontName"[\s\S]{0,2000}?return\s+null;',
        src)
    assert m, "fontName branch not found"
    branch = m.group(0)
    # otherKeys 리스트에 fontFace 가 없어야 한다
    other_m = re.search(
        r'otherKeys\s*=\s*\[([^\]]+)\]', branch)
    if other_m:
        keys = re.findall(r'"(\w+)"', other_m.group(1))
        assert "fontFace" not in keys, (
            f"fontFace must be excluded from fontName identity: {keys}")


def test_matcher_no_fuzzy_alias_or_levenshtein():
    src = MATCHER_MJS.read_text(encoding="utf-8")
    for pat in (r"\bfuzzy\b", r"\bapproximate\b", r"\bsimilar\b",
                          r"\balias\b", r"\blevenshtein\b",
                          r"colorDistance", r"\bhsv\b", r"\bhsl\b",
                          r"Math\.abs"):
        assert not re.search(pat, src, re.IGNORECASE), pat


# ── 2. matcher node smoke ────────────────────────────────

@need_node
def test_smoke_verdict_pass():
    out = _run_smoke()
    assert out["verdict"] == "PASS", out
    bad = {k: v for k, v in out["checks"].items() if not v.get("ok")}
    assert not bad, bad


@need_node
def test_smoke_fontname_success_and_failure():
    out = _run_smoke()
    for k in ("fontNameMatchingDotumToDotumChe",
                "fontNameMatchingDotumToBatang",
                "fontNameMatchingNotFound",
                "fontNameMatchingNoopReturnsNull",
                "fontNameMatchingDifferentSizeRejected"):
        assert out["checks"][k]["ok"], k


@need_node
def test_smoke_fontname_face_ignored():
    """fontFace 가 달라도 fontName + 6축 일치하면 매칭됨."""
    out = _run_smoke()
    assert out["checks"]["fontNameMatchingFontFaceIgnored"]["ok"]
    assert out["checks"][
        "extractAxisValuesFontNameFontFaceIgnored"]["ok"]


@need_node
def test_smoke_fontname_alias_not_auto_matched():
    out = _run_smoke()
    assert out["checks"]["fontNameAliasNotAutoMatched"]["ok"]


@need_node
def test_smoke_extract_axis_values_fontname():
    out = _run_smoke()
    for k in ("extractAxisValuesFontNameArray",
                "extractAxisValuesFontNameDedup",
                "extractAxisValuesFontNameCurrent",
                "extractAxisValuesFontNameEnabled",
                "extractAxisValuesFontNameDisabledForOtherSize"):
        assert out["checks"][k]["ok"], k


@need_node
def test_smoke_fontsize_color_toggle_regression_preserved():
    """fontSize + textColor + bold/underline/italic 회귀 보존."""
    out = _run_smoke()
    for k in ("fontSizeMatchingSuccess",
                "fontSizeMatchingFailure",
                "colorMatchingBlackToRed",
                "colorMatchingBlackToBlue",
                "colorMatchingNotFound",
                "boldToggleSuccess",
                "underlineToggleSuccess",
                "italicToggleSuccess",
                "fuzzyToggleNotMatched"):
        assert out["checks"][k]["ok"], k


# ── 3. FontNameDropdown UI ────────────────────────────

def test_toolbar_has_fontname_dropdown():
    src = TOOLBAR_TSX.read_text(encoding="utf-8")
    assert "FontNameDropdown" in src
    assert 'extractAxisValues' in src
    assert '"fontName"' in src or "'fontName'" in src
    assert re.search(r"<select\b", src)


def test_toolbar_no_external_font_picker_or_systemfontlist():
    src = TOOLBAR_TSX.read_text(encoding="utf-8")
    forbidden = [
        r"FontPicker",
        r"systemFonts",
        r"fontList",
        r"react-fontpicker",
        r"google-fonts",
        # alias 추천 UI / + 폰트 추가
        r"새\s*폰트\s*추가",
        r"createFont",
        r"aliasRecommend",
    ]
    for pat in forbidden:
        assert not re.search(pat, src), pat


def test_toolbar_dropdown_disabled_policy():
    src = TOOLBAR_TSX.read_text(encoding="utf-8")
    assert "FontName" in src
    assert "현재 문서에 같은 속성 조합의 기존 폰트 스타일이 없습니다" in src
    assert "wo-fn-empty" in src


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


# ── 4. 86c030d 잠금 자재 무수정 ───────────────────────────

LOCKED_VS_86C030D = [
    # state/command/preview/smoke 는 무수정
    "frontend/web_office_viewer/para_edit_state.mjs",
    "frontend/web_office_viewer/para_edit_command.mjs",
    "frontend/web_office_viewer/components/WebOfficeFormatPreview.tsx",
    "frontend/web_office_viewer/para_edit_apply_format_smoke.mjs",
    # backend
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
    for rel in LOCKED_VS_86C030D:
        r = subprocess.run(
            ["git", "diff", BASELINE_COMMIT, "--", rel],
            capture_output=True, text=True, cwd=str(PR), timeout=20)
        assert r.returncode == 0, (rel, r.stderr)
        assert not r.stdout.strip(), (
            f"{rel} changed vs {BASELINE_COMMIT}")


# ── 5. 운영 fixture 통계 회귀 ───────────────────────

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
def test_fixture_fontname_matching_at_least_90_pct():
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
            key = (d.get("fontSizePt"), d.get("textColor"),
                          d.get("bold"), d.get("italic"),
                          d.get("underline"))
            grp.setdefault(key, set()).add(d.get("fontName"))
        if any(len({n for n in g if n is not None}) >= 2
                  for g in grp.values()):
            matched += 1
    assert total >= 5, f"too few fixtures: {total}"
    pct = matched / total
    assert pct >= 0.9, f"fontName fixture-level {pct:.1%} < 90%"


@need_fx
def test_fixture_per_charpr_avg_fontname_at_least_05():
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
            key = (d.get("fontSizePt"), d.get("textColor"),
                          d.get("bold"), d.get("italic"),
                          d.get("underline"))
            grp.setdefault(key, set()).add(d.get("fontName"))
        for cid, d in defs.items():
            nm = d.get("fontName")
            key = (d.get("fontSizePt"), d.get("textColor"),
                          d.get("bold"), d.get("italic"),
                          d.get("underline"))
            others = {n for n in grp.get(key, set())
                                if n is not None and n != nm}
            all_avgs.append(len(others))
    if not all_avgs:
        pytest.skip("no defs")
    avg = sum(all_avgs) / len(all_avgs)
    assert avg >= 0.5, f"per-charPr fontName avg {avg:.3f} < 0.5"


# ── 6. audit verdict PASS ──────────────────────────────────

def test_audit_script_pass():
    from scripts.ops.audit_web_office_para_edit_applyformat_fontname_matching_existing_charpr import (
        audit)
    rep = audit()
    fails = [f for f in rep["findings"]
              if f.get("level") == "FAIL"]
    assert not fails, json.dumps(rep, ensure_ascii=False, indent=2)
    assert rep["verdict"] in ("PASS", "WARN"), rep
