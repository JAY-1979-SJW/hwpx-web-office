"""WEB-OFFICE-PARA-EDIT-BROWSER-01 계약 테스트.

JS 브라우저 상태기계 + runtime + React 컴포넌트의 정적/실행 잠금.
writer/output/원본 접근 0건 정적 잠금.
"""
from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path
import pytest

PR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PR))

from scripts.ops.audit_web_office_para_edit_browser import (  # noqa: E402
    audit, JS_FILES, SELF_TEST, FORBIDDEN_JS,
)


def _node_ok() -> bool:
    try:
        r = subprocess.run(["node", "--version"], capture_output=True,
                                          text=True, timeout=10)
        return r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


NODE_OK = _node_ok()


def test_all_js_files_exist():
    for p in JS_FILES:
        assert p.is_file(), f"missing: {p}"


def test_no_forbidden_writer_tokens_in_js_modules():
    for p in JS_FILES:
        src = p.read_text(encoding="utf-8")
        for tok in FORBIDDEN_JS:
            assert tok not in src, f"{p.name} has forbidden: {tok}"


def test_paragraph_editor_component_is_not_contenteditable_true():
    src = (PR / "frontend/web_office_viewer/components/"
                      "WebOfficeParagraphEditor.tsx").read_text(
        encoding="utf-8")
    # contenteditable=false 데이터 어트리뷰트 명시
    assert 'data-contenteditable="false"' in src
    # contenteditable={true} 또는 contenteditable="true" 부재
    assert 'contentEditable={true' not in src
    assert 'contenteditable="true"' not in src


@pytest.mark.skipif(not NODE_OK, reason="node not available")
def test_js_self_test_all_scenarios_pass():
    r = subprocess.run(["node", str(SELF_TEST)],
                                      capture_output=True, text=True,
                                      timeout=30, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    last = r.stdout.strip().splitlines()[-1]
    out = json.loads(last)
    assert out["verdict"] == "PASS"
    expected = [
        "initState", "selectAndCaret",
        "typeTextCommand", "replaceRangeCommand",
        "deleteRangeCommand", "deleteBackward",
        "imeCompositionEnd", "imeCancel",
        "compositionLockBlocksTypeText",
        "undoRedo", "keyboardDispatch",
        "keyDownIgnoredDuringComposition",
        "saveDryRunNoop", "saveDryRunReady",
    ]
    for k in expected:
        assert out["checks"].get(k) is True, f"check missing: {k}"


def test_audit_returns_pass():
    out = audit()
    assert out["verdict"] == "PASS", json.dumps(out, ensure_ascii=False,
                                                                              indent=2)[:2000]


def test_no_hwpx_output_in_viewer_dir():
    leaks = list((PR / "frontend/web_office_viewer").glob("*.hwpx"))
    assert leaks == []


def test_mvp_a_set_cell_text_module_untouched():
    """MVP-A 모듈은 본 공정에서 변경 0건이어야 한다 — 토큰 무손상."""
    cell_state = (PR / "frontend/web_office_viewer/"
                                      "cell_edit_state.mjs").read_text(encoding="utf-8")
    assert "MODE_CELL_EDIT" in cell_state
    assert "commitCellText" in cell_state
    cell_cmd = (PR / "frontend/web_office_viewer/"
                                  "edit_command.mjs").read_text(encoding="utf-8")
    assert "CT_SET_CELL_TEXT" in cell_cmd


def test_browser_runtime_attach_rejects_contenteditable_true():
    """runtime 의 attach 함수는 contenteditable=true element 에 부착
    되면 throw 해야 한다 (정적 검증)."""
    src = (PR / "frontend/web_office_viewer/"
                      "para_edit_runtime.mjs").read_text(encoding="utf-8")
    assert "contenteditable=true" in src or "contenteditable" in src
    assert "must NOT be contenteditable=true" in src
