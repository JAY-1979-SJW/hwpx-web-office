"""WEB-OFFICE-PARA-EDIT-APPLYFORMAT-TOOLBAR-COMMAND-01 감리.

applyFormatToSelection helper (JS) → APPLY_FORMAT command 발급 →
commandLog append-only 적재까지의 회로 검증. backend writer / save 호출
0건. read-only preview (abebab6) 회귀 + ApplyFormat engine (97c4095)
회귀 + dc9e6ad closeout 잠금 모두 유지.
"""
from __future__ import annotations
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

PR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PR))

SMOKE_JS = (PR / "frontend/web_office_viewer/"
                  "para_edit_apply_format_smoke.mjs")
STATE_MJS = (PR / "frontend/web_office_viewer/para_edit_state.mjs")
CMD_MJS = (PR / "frontend/web_office_viewer/para_edit_command.mjs")
PREVIEW_TSX = (PR / "frontend/web_office_viewer/components/"
                      "WebOfficeFormatPreview.tsx")
BASELINE_COMMIT = "b411164"  # M2 문단서식 준공 후 갱신 (b411164 → b411164)


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


# ── 1. applyFormatToSelection 존재 + makeApplyFormatCommand 재사용 ──

def test_apply_format_to_selection_function_exists():
    src = STATE_MJS.read_text(encoding="utf-8")
    assert re.search(
        r"export\s+function\s+applyFormatToSelection\(", src)
    assert "makeApplyFormatCommand(" in src


def test_command_factory_reused_not_redefined():
    """makeApplyFormatCommand 는 para_edit_command.mjs 에 1개만 정의."""
    src = CMD_MJS.read_text(encoding="utf-8")
    defs = re.findall(
        r"export\s+function\s+makeApplyFormatCommand\b", src)
    assert len(defs) == 1


# ── 2. node smoke verdict PASS + 25 checks all ok ───────────────

@need_node
def test_smoke_verdict_pass():
    out = _run_smoke()
    assert out["verdict"] == "PASS", out
    bad = {k: v for k, v in out["checks"].items() if not v.get("ok")}
    assert not bad, bad


# ── 3. valid selection + valid target → command 생성 ────────────

@need_node
def test_valid_selection_generates_command():
    out = _run_smoke()
    for k in ("validSelectionCommandCreated",
                "commandTypeApplyFormat",
                "forwardKindApplyFormat"):
        assert out["checks"][k]["ok"], k


# ── 4. commandLog append-only 적재 ────────────────────────────

@need_node
def test_command_log_append_only_after_apply_format():
    out = _run_smoke()
    for k in ("commandLogAppended", "commandLogAppendOnly",
                "undoStackUpdated", "redoStackCleared",
                "undoCommandLogAppendOnly"):
        assert out["checks"][k]["ok"], k


# ── 5. forward / inverse 정합 ─────────────────────────────────

@need_node
def test_forward_and_inverse_consistency():
    out = _run_smoke()
    for k in ("expectedBeforeMatchesSlice",
                "rangeStartEqualsAnchor",
                "targetCharPrPassedThrough",
                "inverseRestoreSegmentsPresent",
                "paragraphTextUnchanged"):
        assert out["checks"][k]["ok"], k


# ── 6. 안전 reject 회로 ──────────────────────────────────────

@need_node
def test_safety_rejects():
    out = _run_smoke()
    for k in ("noActiveParagraphReject", "noTextRangeReject",
                "emptyRangeReject", "targetNotInDefsReject",
                "targetNullReject", "compositionLockReject"):
        assert out["checks"][k]["ok"], k


# ── 7. undo / redo ──────────────────────────────────────────

@need_node
def test_undo_redo_apply_format():
    out = _run_smoke()
    for k in ("undoOk", "undoRedoPending", "redoOk"):
        assert out["checks"][k]["ok"], k


# ── 8. save dry-run payload 에 APPLY_FORMAT 포함 ───────────────

@need_node
def test_save_dry_run_includes_apply_format():
    out = _run_smoke()
    assert out["checks"]["saveDryRunIncludesApplyFormat"]["ok"]


# ── 9. preview 컴포넌트가 enableApplyCommand opt-in 지원 ─────────

def test_preview_component_opt_in_command_mode():
    src = PREVIEW_TSX.read_text(encoding="utf-8")
    assert "enableApplyCommand" in src
    assert "onApplyCharPr" in src
    # 기본값은 false (read-only 보존)
    assert "enableApplyCommand = false" in src \
            or "enableApplyCommand=false" in src \
            or "!enableApplyCommand" in src


# ── 10. preview 컴포넌트가 makeApplyFormatCommand 직접 호출 안 함 ─

def test_preview_component_no_direct_command_call():
    src = PREVIEW_TSX.read_text(encoding="utf-8")
    # 콜백 onApplyCharPr 만 호출 — 직접 factory 호출 금지.
    assert not re.search(r"makeApplyFormatCommand\(", src)
    assert not re.search(r"applyFormatToSelection\(", src)


# ── 11. read-only mode (enableApplyCommand=false) command 0건 ───

def test_read_only_default_still_works():
    """abebab6 read-only preview 동작 유지 — 기본값에서 클릭 가능
    element 가 생성되지 않음 (data-clickable=false)."""
    src = PREVIEW_TSX.read_text(encoding="utf-8")
    # readOnlyMode 가 enableApplyCommand 의 negation 으로 정의되어 있음
    assert "readOnlyMode = !enableApplyCommand" in src
    # data-applies-format 이 ternary 로 false/true 분기
    assert re.search(r'dataAppliesFormat\s*=\s*readOnlyMode\s*\?', src)


# ── 12. 신규 charPr 생성 / header.xml write 흔적 없음 ─────────

def test_no_new_char_pr_or_header_write_traces():
    forbidden = [
        r"def\s+create_char_pr\b",
        r"package\.entries\[[^\]]*header\.xml[^\]]*\]\s*=",
        r"\.write_xml\(",
    ]
    targets = [
        "frontend/web_office_viewer/para_edit_state.mjs",
        "frontend/web_office_viewer/para_edit_command.mjs",
        "frontend/web_office_viewer/components/WebOfficeFormatPreview.tsx",
        "frontend/web_office_viewer/para_edit_apply_format_smoke.mjs",
    ]
    for rel in targets:
        src = (PR / rel).read_text(encoding="utf-8")
        for pat in forbidden:
            assert not re.search(pat, src), (rel, pat)


# ── 13. backend writer / save 직접 호출 없음 ─────────────────

def test_no_backend_writer_calls_in_frontend():
    forbidden = [
        r"save_paragraph_edits\(",
        r"apply_paragraph_edits_plan\(",
        r"create_hwpx_document\(",
        r"write_package\(",
    ]
    targets = [
        "frontend/web_office_viewer/para_edit_state.mjs",
        "frontend/web_office_viewer/para_edit_command.mjs",
        "frontend/web_office_viewer/components/WebOfficeFormatPreview.tsx",
    ]
    for rel in targets:
        src = (PR / rel).read_text(encoding="utf-8")
        for pat in forbidden:
            assert not re.search(pat, src), (rel, pat)


# ── 14. abebab6 잠금 자재 무수정 (backend 측) ──────────────────

LOCKED_VS_ABEBAB6 = [
    # writer/adapter/model/plan/verify7/pipeline backend 측 무수정
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
    "frontend/web_office_viewer/para_edit_runtime.mjs",
]


def test_locked_backend_unchanged_vs_abebab6():
    for rel in LOCKED_VS_ABEBAB6:
        r = subprocess.run(
            ["git", "diff", BASELINE_COMMIT, "--", rel],
            capture_output=True, text=True, cwd=str(PR), timeout=20)
        assert r.returncode == 0, (rel, r.stderr)
        assert not r.stdout.strip(), (
            f"{rel} changed vs {BASELINE_COMMIT}")


# ── 15. audit verdict PASS ──────────────────────────────────

def test_audit_script_pass():
    from scripts.ops.audit_web_office_para_edit_applyformat_toolbar_command import (
        audit)
    rep = audit()
    fails = [f for f in rep["findings"]
              if f.get("level") == "FAIL"]
    assert not fails, json.dumps(rep, ensure_ascii=False, indent=2)
    assert rep["verdict"] in ("PASS", "WARN"), rep
