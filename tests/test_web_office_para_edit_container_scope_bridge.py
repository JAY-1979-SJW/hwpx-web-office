"""WEB-OFFICE-PARA-EDIT-CONTAINERSCOPE-BRIDGE-01 계약 테스트.

브라우저 상태기계의 _buildTarget 재배선 + EditCommand v2 forward/inverse
containerScope 전사 + paragraph_edit_plan target.containerScope 우선 분기
를 검증한다. writer / output / 원본 HWPX 접근 없음.
"""
from __future__ import annotations
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

PR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PR))
sys.path.insert(0, str(PR / "scripts/hwpx"))

from scripts.hwpx.web_office.para_edit_model import (  # noqa: E402
    Paragraph, ParaTextRun, ParagraphTarget,
    make_type_text_command, make_replace_text_range_command,
    make_delete_text_range_command,
)
from scripts.hwpx.web_office.paragraph_edit_plan import (  # noqa: E402
    build_dry_run_paragraph_plan, _container_scope_from_target,
)
from scripts.hwpx.hwpx_edit_tool import validate_edit_plan  # noqa: E402


CELL_SCOPE = {
    "kind": "cell", "tableIndex": 0, "rowIndex": 1, "colIndex": 2,
    "paragraphIndex": 0, "runIndex": 0,
}
BLOCK_SCOPE = {
    "kind": "block", "sectionIndex": 0, "blockIndex": 3,
    "paragraphIndex": 0,
}
SRC_HASH = "abc123"


def _cell_target() -> ParagraphTarget:
    return ParagraphTarget(
        paragraphId="par_p1", containerKind="cell",
        containerId="cell_t0_r1_c2", sourceSha256=SRC_HASH,
        cellCoord={"table": 0, "row": 1, "col": 2},
        containerScope=dict(CELL_SCOPE))


def _block_target() -> ParagraphTarget:
    return ParagraphTarget(
        paragraphId="par_p1", containerKind="block",
        containerId="par_p1", sourceSha256=SRC_HASH,
        containerScope=dict(BLOCK_SCOPE))


def _para() -> Paragraph:
    return Paragraph(
        paragraphId="par_p1", parPrIDRef="P1",
        runs=[ParaTextRun("par_p1_run0", "ab", "A"),
                      ParaTextRun("par_p1_run1", "cd", "B")])


# ── 1. TYPE_TEXT containerScope 전사 ────────────────────────────

def test_type_text_target_forward_inverse_container_scope_cell():
    cmd = make_type_text_command(
        target=_cell_target(), paragraph=_para(),
        caret_offset=1, insert_text="X",
        source_document_hash=SRC_HASH,
        container_scope=dict(CELL_SCOPE))
    assert cmd is not None
    assert cmd.target["containerScope"] == CELL_SCOPE
    assert cmd.forward["containerScope"] == CELL_SCOPE
    assert cmd.inverse["containerScope"] == CELL_SCOPE


# ── 2. REPLACE 동일 ─────────────────────────────────────────────

def test_replace_target_forward_inverse_container_scope_cell():
    cmd = make_replace_text_range_command(
        target=_cell_target(), paragraph=_para(),
        range_anchor=0, range_focus=1, after_text="Q",
        source_document_hash=SRC_HASH,
        container_scope=dict(CELL_SCOPE))
    assert cmd.target["containerScope"] == CELL_SCOPE
    assert cmd.forward["containerScope"] == CELL_SCOPE
    assert cmd.inverse["containerScope"] == CELL_SCOPE


# ── 3. DELETE 동일 ──────────────────────────────────────────────

def test_delete_target_forward_inverse_container_scope_cell():
    cmd = make_delete_text_range_command(
        target=_cell_target(), paragraph=_para(),
        range_anchor=0, range_focus=1,
        source_document_hash=SRC_HASH,
        container_scope=dict(CELL_SCOPE))
    assert cmd.target["containerScope"] == CELL_SCOPE
    assert cmd.forward["containerScope"] == CELL_SCOPE
    assert cmd.inverse["containerScope"] == CELL_SCOPE


# ── 4. container_scope kwarg 미지정 시 기존 호출자 무손상 ────────

def test_factories_backward_compat_without_container_scope():
    target = ParagraphTarget(
        paragraphId="par_p1", containerKind="block",
        containerId="par_p1", sourceSha256=SRC_HASH)
    cmd = make_type_text_command(
        target=target, paragraph=_para(),
        caret_offset=0, insert_text="X",
        source_document_hash=SRC_HASH)
    assert cmd is not None
    # target.containerScope 기본값 None
    assert cmd.target.get("containerScope") is None
    assert cmd.forward.get("containerScope") is None
    assert cmd.inverse.get("containerScope") is None


# ── 5. plan 변환: cell scope ────────────────────────────────────

def test_plan_cell_container_scope_propagated():
    para = _para()
    cmd = make_type_text_command(
        target=_cell_target(), paragraph=para,
        caret_offset=0, insert_text="X",
        source_document_hash=SRC_HASH,
        container_scope=dict(CELL_SCOPE))
    res = build_dry_run_paragraph_plan(
        [cmd], {para.paragraphId: para}, SRC_HASH)
    items = (res.get("plan") or {}).get("paragraph_edits", [])
    assert len(items) == 1
    assert items[0]["containerScope"]["kind"] == "cell"
    assert items[0]["containerScope"]["tableIndex"] == 0
    assert items[0]["containerScope"]["rowIndex"] == 1
    assert items[0]["containerScope"]["colIndex"] == 2


# ── 6. plan 변환: block scope ───────────────────────────────────

def test_plan_block_container_scope_propagated():
    para = _para()
    cmd = make_type_text_command(
        target=_block_target(), paragraph=para,
        caret_offset=0, insert_text="X",
        source_document_hash=SRC_HASH,
        container_scope=dict(BLOCK_SCOPE))
    res = build_dry_run_paragraph_plan(
        [cmd], {para.paragraphId: para}, SRC_HASH)
    items = (res.get("plan") or {}).get("paragraph_edits", [])
    assert len(items) == 1
    assert items[0]["containerScope"]["kind"] == "block"


# ── 7. plan + validate_edit_plan: cell PASS ─────────────────────

def test_validate_edit_plan_cell_pass():
    para = _para()
    cmd = make_type_text_command(
        target=_cell_target(), paragraph=para,
        caret_offset=0, insert_text="X",
        source_document_hash=SRC_HASH,
        container_scope=dict(CELL_SCOPE))
    res = build_dry_run_paragraph_plan(
        [cmd], {para.paragraphId: para}, SRC_HASH)
    items = (res.get("plan") or {}).get("paragraph_edits", [])
    v = validate_edit_plan({"paragraph_edits": items})
    assert v["status"] == "PASS", v


# ── 8. plan + validate_edit_plan: block PASS ────────────────────

def test_validate_edit_plan_block_pass():
    para = _para()
    cmd = make_type_text_command(
        target=_block_target(), paragraph=para,
        caret_offset=0, insert_text="X",
        source_document_hash=SRC_HASH,
        container_scope=dict(BLOCK_SCOPE))
    res = build_dry_run_paragraph_plan(
        [cmd], {para.paragraphId: para}, SRC_HASH)
    items = (res.get("plan") or {}).get("paragraph_edits", [])
    v = validate_edit_plan({"paragraph_edits": items})
    assert v["status"] == "PASS", v


# ── 9. derive helper: target.containerScope 우선 ────────────────

def test_container_scope_from_target_prefers_explicit_scope():
    # legacy cellCoord 와 다른 값을 갖는 explicit scope 가 우선
    target = {
        "containerKind": "cell",
        "cellCoord": {"table": 9, "row": 9, "col": 9},
        "containerScope": dict(CELL_SCOPE),
    }
    out = _container_scope_from_target(target)
    assert out["tableIndex"] == 0  # explicit 값 우선
    assert out["rowIndex"] == 1
    assert out["colIndex"] == 2


# ── 10. derive helper: target.containerScope 없으면 legacy fallback

def test_container_scope_from_target_legacy_fallback():
    target = {
        "containerKind": "cell",
        "cellCoord": {"table": 4, "row": 5, "col": 6},
    }
    out = _container_scope_from_target(target)
    assert out["kind"] == "cell"
    assert out["tableIndex"] == 4
    assert out["rowIndex"] == 5
    assert out["colIndex"] == 6
    assert out["paragraphIndex"] == 0
    assert out["runIndex"] == 0


# ── 11. writer adapter dry-run: block plan → BODY_PARAGRAPH_NOT_SUPPORTED

def test_writer_adapter_rejects_block_paragraph_dry_run():
    # adapter 호출 — mutation 없이 in-memory dry-run 만, output 미생성.
    fx = (PR / "data/recognition_corpus/_test_fixtures/"
                  "writer_para_plan_fixture.hwpx")
    if not fx.is_file():
        pytest.skip("fixture not present")
    from scripts.hwpx.hwpx_package import HwpxPackage
    from scripts.hwpx.web_office.paragraph_writer_adapter import (
        apply_paragraph_edits_plan, REASON_BODY_PARAGRAPH_NOT_SUPPORTED,
    )
    sha_before = hashlib.sha256(fx.read_bytes()).hexdigest()
    pkg = HwpxPackage.load(fx)
    item = {
        "commandId": "c1", "paragraphId": "par_p1",
        "runId": "par_p1_run0",
        "rangeStart": 0, "rangeEnd": 0,
        "rangeAnchor": 0, "rangeFocus": 0,
        "afterText": "X", "expectedBefore": "",
        "commandType": "TYPE_TEXT",
        "sourceDocumentHash": "ignored",
        "containerScope": dict(BLOCK_SCOPE),
    }
    res = apply_paragraph_edits_plan(
        pkg, [item], source_document_hash="ignored", dry_run=True)
    # WEB-OFFICE-BODY-PARAGRAPH-WRITER-01: body scope 자체로는 reject 되지
    # 않는다. 본 dry-run 은 sourceDocumentHash 미일치 또는 paragraph 좌표
    # 부정확으로 reject 될 수 있으나 BODY_PARAGRAPH_NOT_SUPPORTED 는 아님.
    rejs = res.get("rejected", [])
    for r in rejs:
        assert r.get("reason") != REASON_BODY_PARAGRAPH_NOT_SUPPORTED, r
    # 원본 무변경
    assert hashlib.sha256(fx.read_bytes()).hexdigest() == sha_before


# ── 12. 정적: 본 공정 산출물에 writer 토큰 없음 ─────────────────

def test_static_no_writer_tokens_in_targets():
    targets = [
        PR / "frontend/web_office_viewer/para_edit_state.mjs",
        PR / "frontend/web_office_viewer/para_edit_command.mjs",
        PR / "frontend/web_office_viewer/para_edit_self_test.mjs",
        PR / "scripts/hwpx/web_office/para_edit_model.py",
        PR / "scripts/hwpx/web_office/paragraph_edit_plan.py",
    ]
    forbidden = ["hwpx" + "_edit_tool", "apply" + "_edit_plan",
                          "create_hwpx_document(", "write_package("]
    for p in targets:
        src = p.read_text(encoding="utf-8")
        for tok in forbidden:
            assert tok not in src, f"{p.name}: {tok}"


# ── 13. audit script returns PASS ───────────────────────────────

def test_audit_script_pass():
    from scripts.ops.audit_web_office_para_edit_container_scope_bridge \
        import audit
    rep = audit()
    # FAIL 사유 없음 — WARN 만 허용
    fails = [f for f in rep["findings"]
                      if f.get("level") == "FAIL"]
    assert not fails, json.dumps(rep, ensure_ascii=False, indent=2)
    assert rep["verdict"] == "PASS"


# ── 14. JS self_test subprocess (node 가용 시) ───────────────────

def _node_available() -> bool:
    try:
        r = subprocess.run(["node", "--version"], capture_output=True,
                                          text=True, encoding="utf-8", errors="replace", timeout=10)
        return r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


@pytest.mark.skipif(not _node_available(),
                                      reason="node not available")
def test_js_self_test_new_checks_pass():
    self_test = (PR / "frontend/web_office_viewer/"
                                "para_edit_self_test.mjs")
    r = subprocess.run(["node", str(self_test)],
                                      capture_output=True, text=True,
                                      timeout=30, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    last = r.stdout.strip().splitlines()[-1]
    parsed = json.loads(last)
    checks = parsed.get("checks", {})
    for key in ("containerScopePropagation",
                          "requiresReviewWhenNoContainerScope",
                          "blockContainerScopeAccepted"):
        assert checks.get(key), key
