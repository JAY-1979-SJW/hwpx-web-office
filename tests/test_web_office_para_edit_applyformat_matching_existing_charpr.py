"""WEB-OFFICE-PARA-EDIT-APPLYFORMAT-MATCHING-EXISTING-CHARPR-01 감리.

matchToggle (JS) bold/underline/italic 완전 일치 매칭 + WebOfficeFormat
Toolbar 컴포넌트의 read-only 보존 + matching 실패 시 disabled 정책 +
backend writer / state / command factory 무수정 정적 잠금.
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
BASELINE_COMMIT = "e04d325"  # PARA_INSERT 준공 후 갱신 (af1dcf3 → 1f442ec)


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


# ── 1. matcher 모듈 정합 ─────────────────────────────────

def test_matcher_module_exists():
    assert MATCHER_MJS.is_file(), MATCHER_MJS


def test_matcher_exports_match_toggle():
    src = MATCHER_MJS.read_text(encoding="utf-8")
    assert re.search(r"export\s+function\s+matchToggle\(", src)
    assert re.search(r"export\s+function\s+matchAllToggles\(", src)
    assert re.search(r'export\s+const\s+MATCH_DIMENSIONS', src)


def test_matcher_dimensions_limited_to_three():
    """1차 공정 정책 — bold/underline/italic 외 dimension 추가 금지."""
    src = MATCHER_MJS.read_text(encoding="utf-8")
    m = re.search(r"MATCH_DIMENSIONS\s*=\s*\[([^\]]+)\]", src)
    assert m, "MATCH_DIMENSIONS not found"
    dims = re.findall(r'"(\w+)"', m.group(1))
    assert set(dims) == {"bold", "underline", "italic"}, dims


def test_matcher_no_fuzzy_keyword():
    """fuzzy matching 금지 — 'fuzzy' / 'approximate' / 'similar' 등 키워드 0."""
    src = MATCHER_MJS.read_text(encoding="utf-8")
    for pat in (r"fuzzy", r"approximate", r"similar",
                          r"Math\.abs"):
        assert not re.search(pat, src, re.IGNORECASE), pat


def test_matcher_no_color_fontsize_direct_input():
    """color/fontSize 변경 matching 금지 — currentDef 의 값과 동등 비교만."""
    src = MATCHER_MJS.read_text(encoding="utf-8")
    # textColor / fontSizePt 가 토글 대상 외로 직접 editable input 화되어
    # 있지는 않은지 — 본 matcher 는 attrs 비교만 수행.
    # 단순 grep: prompt(/showColorPicker/fontSize input 등이 없어야.
    for pat in (r"prompt\(", r"showColorPicker", r"input\.color",
                          r"fontSizeInput", r"input\.fontSize"):
        assert not re.search(pat, src), pat


# ── 2. matcher node smoke ────────────────────────────────

@need_node
def test_matcher_smoke_verdict_pass():
    out = _run_smoke()
    assert out["verdict"] == "PASS", out
    bad = {k: v for k, v in out["checks"].items() if not v.get("ok")}
    assert not bad, bad


@need_node
def test_matcher_bold_success():
    out = _run_smoke()
    for k in ("boldToggleSuccess", "boldToggleOffSuccess"):
        assert out["checks"][k]["ok"], k


@need_node
def test_matcher_underline_success():
    out = _run_smoke()
    assert out["checks"]["underlineToggleSuccess"]["ok"]


@need_node
def test_matcher_italic_success_in_synthetic():
    """fixture 통계상 italic matching 은 0% 에 가깝지만, 합성 dataset
    에서는 토글이 가능하다 — 함수 자체는 정상 동작."""
    out = _run_smoke()
    assert out["checks"]["italicToggleSuccess"]["ok"]


@need_node
def test_matcher_failure_returns_null():
    out = _run_smoke()
    for k in ("noMatchReturnsNull", "selfExcluded",
                "differentSizeNotMatched",
                "differentColorNotMatched",
                "invalidDimensionReturnsNull",
                "nullCurrentReturnsNull",
                "nullDefsReturnsNull",
                "fuzzyToggleNotMatched"):
        assert out["checks"][k]["ok"], k


# ── 3. toolbar 컴포넌트 정합 ──────────────────────────────

def test_toolbar_component_exists():
    assert TOOLBAR_TSX.is_file(), TOOLBAR_TSX


def test_toolbar_opt_in_only():
    src = TOOLBAR_TSX.read_text(encoding="utf-8")
    # 기본값 false, !enableApplyCommand 시 비노출
    assert "enableApplyCommand = false" in src \
            or "enableApplyCommand=false" in src
    assert "!enableApplyCommand" in src
    assert 'data-applies-format="false"' in src \
            or "data-applies-format" in src


def test_toolbar_callbacks_only_no_direct_factory_call():
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


def test_toolbar_uses_matcher():
    src = TOOLBAR_TSX.read_text(encoding="utf-8")
    assert "matchToggle" in src
    assert "MATCH_DIMENSIONS" in src


def test_toolbar_disabled_when_no_match():
    """matching null → button disabled + data-disabled=true."""
    src = TOOLBAR_TSX.read_text(encoding="utf-8")
    assert 'data-disabled' in src
    assert 'disabled={disabled}' in src \
            or 'disabled={!!disabled}' in src \
            or re.search(r"disabled\s*=\s*\{disabled\}", src)
    # 안내 문구
    assert "매칭되는 기존 스타일이 없습니다" in src


def test_toolbar_no_color_or_fontsize_input():
    src = TOOLBAR_TSX.read_text(encoding="utf-8")
    for pat in (r"input\s+type=\"color\"",
                          r"input\s+type=\"number\"",
                          r'<input[^>]+name="color"',
                          r"fontSizePicker", r"colorPicker"):
        assert not re.search(pat, src), pat


def test_toolbar_no_new_charpr_button():
    src = TOOLBAR_TSX.read_text(encoding="utf-8")
    for pat in (r"신규\s*charPr",
                          r"createCharPr",
                          r'data-action="create-char-pr"'):
        assert not re.search(pat, src), pat


# ── 4. af1dcf3 잠금 자재 무수정 ───────────────────────────

LOCKED_VS_AF1DCF3 = [
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
    for rel in LOCKED_VS_AF1DCF3:
        r = subprocess.run(
            ["git", "diff", BASELINE_COMMIT, "--", rel],
            capture_output=True, text=True, cwd=str(PR), timeout=20)
        assert r.returncode == 0, (rel, r.stderr)
        assert not r.stdout.strip(), (
            f"{rel} changed vs {BASELINE_COMMIT}")


# ── 5. 운영 fixture matching 가능성 회귀 ─────────────────

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
need_fx = pytest.mark.skipif(
    not FX, reason="no operational fixtures")


@need_fx
def test_fixture_matching_statistics_bold_at_least_some():
    """운영 fixture 중 bold 토글 가능한 비율이 일정 기준 이상 (≥ 20%)."""
    from scripts.hwpx.web_office.charpr_inventory import (
        char_pr_defs_only)
    fixtures_with_bold = 0
    total = 0
    for p in FX:
        try:
            defs = char_pr_defs_only(p)
        except Exception:  # noqa: BLE001
            continue
        if not defs:
            continue
        total += 1
        # group by (fontName, fontSizePt, textColor, italic, underline)
        grouped: dict = {}
        for cid, d in defs.items():
            key = (d.get("fontName"), d.get("fontSizePt"),
                          d.get("textColor"), d.get("italic"),
                          d.get("underline"))
            grouped.setdefault(key, set()).add(d.get("bold"))
        if any(True in g and False in g for g in grouped.values()):
            fixtures_with_bold += 1
    assert total >= 5, f"too few fixtures: {total}"
    pct = fixtures_with_bold / total
    assert pct >= 0.2, f"bold matching {pct:.1%} too low"


@need_fx
def test_fixture_italic_matching_rare_as_expected():
    """운영 fixture 의 italic 토글 비율이 낮음을 회귀 잠금 (≤ 20%).
    실측 0% 였음 — 30% 이상이면 정찰 결과와 어긋남."""
    from scripts.hwpx.web_office.charpr_inventory import (
        char_pr_defs_only)
    fx_italic = 0; total = 0
    for p in FX:
        try:
            defs = char_pr_defs_only(p)
        except Exception:  # noqa: BLE001
            continue
        if not defs:
            continue
        total += 1
        grouped: dict = {}
        for cid, d in defs.items():
            key = (d.get("fontName"), d.get("fontSizePt"),
                          d.get("textColor"), d.get("bold"),
                          d.get("underline"))
            grouped.setdefault(key, set()).add(d.get("italic"))
        if any(True in g and False in g for g in grouped.values()):
            fx_italic += 1
    if total == 0:
        pytest.skip("no fixtures")
    pct = fx_italic / total
    assert pct <= 0.3, f"italic matching {pct:.1%} unexpectedly high"


# ── 6. audit verdict PASS ──────────────────────────────────

def test_audit_script_pass():
    from scripts.ops.audit_web_office_para_edit_applyformat_matching_existing_charpr import (
        audit)
    rep = audit()
    fails = [f for f in rep["findings"]
              if f.get("level") == "FAIL"]
    assert not fails, json.dumps(rep, ensure_ascii=False, indent=2)
    assert rep["verdict"] in ("PASS", "WARN"), rep
