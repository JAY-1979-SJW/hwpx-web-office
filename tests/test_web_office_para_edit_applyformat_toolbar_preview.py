"""WEB-OFFICE-PARA-EDIT-APPLYFORMAT-TOOLBAR-PREVIEW-01 감리.

read-only toolbar preview — payload additive 검증 + 컴포넌트 정적 잠금
+ dc9e6ad 회귀 + writer/command/save 호출 0건 확인.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

PR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PR))

from scripts.hwpx.web_office.charpr_inventory import char_pr_defs_only  # ruff: ignore[module-import-not-at-top-of-file]
from scripts.hwpx.web_office.render_payload import build_render_payload  # ruff: ignore[module-import-not-at-top-of-file]
from scripts.hwpx.web_office.ro_view_importer import import_hwpx_as_ro_view  # ruff: ignore[module-import-not-at-top-of-file]

PREVIEW_TSX = PR / "frontend/web_office_viewer/components/WebOfficeFormatPreview.tsx"
BASELINE_COMMIT = "b992ad6"  # 중첩표 읽기/쓰기 대칭 준공 후 갱신 (f119308 → b992ad6)


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _fixture() -> Path | None:
    db = PR / "data/recognition_corpus/corpus.sqlite3"
    if not db.is_file():
        return None
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


FIXTURE = _fixture()
need_fx = pytest.mark.skipif(FIXTURE is None, reason="fixture missing")


# ── 1. payload additive — char_pr_defs=None 시 문서 styles 기본 노출 ─────


@need_fx
def test_payload_baseline_exposes_document_style_defs():
    doc = import_hwpx_as_ro_view(FIXTURE)
    payload = build_render_payload(doc)
    assert "styles" in payload, payload.keys()
    assert payload["styles"].get("charPrDefs")


# ── 2. payload additive — char_pr_defs 전달 시 styles.charPrDefs ─


@need_fx
def test_payload_with_defs_exposes_styles_char_pr_defs():
    doc = import_hwpx_as_ro_view(FIXTURE)
    defs = char_pr_defs_only(FIXTURE)
    payload = build_render_payload(doc, char_pr_defs=defs)
    assert "styles" in payload
    cpr = payload["styles"].get("charPrDefs") or {}
    assert len(cpr) > 0
    sample = next(iter(cpr.values()))
    for field in (
        "charPrId",
        "fontName",
        "fontSizePt",
        "textColor",
        "bold",
        "italic",
        "underline",
        "fontFace",
        "height",
        "fontRef",
        "ratio",
        "relSz",
        "underlineDef",
        "strikeout",
        "strikeoutDef",
    ):
        assert field in sample, field


# ── 3. 기존 payload key 보존 ───────────────────────────────────


@need_fx
def test_existing_payload_keys_preserved():
    doc = import_hwpx_as_ro_view(FIXTURE)
    payload_baseline = build_render_payload(doc)
    payload_with_defs = build_render_payload(doc, char_pr_defs=char_pr_defs_only(FIXTURE))
    for key in (
        "schemaVersion",
        "engineVersion",
        "payloadVersion",
        "documentId",
        "sourceRef",
        "editable",
        "pages",
        "blocks",
        "tables",
        "objects",
        "warnings",
    ):
        assert key in payload_baseline
        assert key in payload_with_defs


# ── 4. preview 컴포넌트 파일 존재 + read-only 표식 ────────────


def test_preview_component_file_exists():
    assert PREVIEW_TSX.is_file(), PREVIEW_TSX


def test_preview_component_marked_read_only():
    """WEB-OFFICE-PARA-EDIT-APPLYFORMAT-TOOLBAR-COMMAND-01: 컴포넌트가
    data-read-only / data-applies-format 속성을 지원해 read-only 기본
    + command-mode opt-in 양쪽을 표식한다.
    """
    src = PREVIEW_TSX.read_text(encoding="utf-8")
    assert "data-read-only" in src
    assert "data-applies-format" in src
    # 기본값은 read-only 유지 (enableApplyCommand 기본값 false)
    assert (
        "enableApplyCommand = false" in src
        or "enableApplyCommand=false" in src
        or "readOnlyMode = !enableApplyCommand" in src
    )


# ── 5. preview 컴포넌트에 command/writer 호출 0건 ───────────────


def test_preview_component_has_no_command_or_writer_calls():
    src = PREVIEW_TSX.read_text(encoding="utf-8")
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
        r"commandLog\.push\(",
        r"commandLog\s*=",
    ]
    for pat in forbidden:
        assert not re.search(pat, src), pat


# ── 6. preview 가 필수 표시 필드를 가지는지 ───────────────────


def test_preview_component_displays_required_fields():
    src = PREVIEW_TSX.read_text(encoding="utf-8")
    for needed in (
        "charPrDefs",
        "currentCharPrId",
        "activeRuns",
        "fontName",
        "fontSizePt",
        "textColor",
        "bold",
        "italic",
        "underline",
    ):
        assert needed in src, needed


# ── 7. dc9e6ad LOCKED 자재 무수정 ─────────────────────────────

# WEB-OFFICE-PARA-EDIT-APPLYFORMAT-TOOLBAR-COMMAND-01: para_edit_state /
# para_edit_command 는 applyFormatToSelection + _applyFormat 추가로 본
# LOCKED 에서 제거됨 (허용 범위: ApplyFormat command 발급 + in-memory
# 적용 한정).
LOCKED_FILES = [
    "scripts/hwpx/hwpx_paragraph_ops.py",
    "scripts/hwpx/hwpx_edit_tool.py",
    "scripts/hwpx/web_office/para_edit_model.py",
    "scripts/hwpx/web_office/paragraph_edit_plan.py",
    "scripts/hwpx/web_office/paragraph_writer_adapter.py",
    "scripts/hwpx/web_office/paragraph_save_verify7.py",
    "scripts/hwpx/web_office/para_edit_e2e_pipeline.py",
    "scripts/hwpx/web_office/paragraph_save_pipeline.py",
    "scripts/hwpx/web_office/charpr_inventory.py",
    "frontend/web_office_viewer/para_edit_runtime.mjs",
]


def test_locked_files_unchanged_vs_baseline():
    if (
        subprocess.run(["git", "cat-file", "-e", BASELINE_COMMIT], capture_output=True).returncode
        != 0
    ):
        pytest.skip(
            f"baseline commit {BASELINE_COMMIT} not reachable in this branch's history (extracted branch)"
        )
    for rel in LOCKED_FILES:
        r = subprocess.run(
            ["git", "diff", BASELINE_COMMIT, "--", rel],
            capture_output=True,
            text=True,
            cwd=str(PR),
            timeout=20,
        )
        assert r.returncode == 0, (rel, r.stderr)
        assert not r.stdout.strip(), f"{rel} changed vs {BASELINE_COMMIT}"


# ── 8. 원본 sha/mtime 무변경 ─────────────────────────────────


@need_fx
def test_payload_build_does_not_modify_source():
    sha_b = _sha(FIXTURE)
    mt_b = FIXTURE.stat().st_mtime_ns
    doc = import_hwpx_as_ro_view(FIXTURE)
    for _ in range(3):
        build_render_payload(doc, char_pr_defs=char_pr_defs_only(FIXTURE))
    assert _sha(FIXTURE) == sha_b
    assert FIXTURE.stat().st_mtime_ns == mt_b


# ── 9. audit verdict PASS ──────────────────────────────────


def test_audit_script_pass():
    from scripts.ops.audit_web_office_para_edit_applyformat_toolbar_preview import audit

    rep = audit()
    fails = [f for f in rep["findings"] if f.get("level") == "FAIL"]
    assert not fails, json.dumps(rep, ensure_ascii=False, indent=2)
    assert rep["verdict"] in ("PASS", "WARN"), rep
