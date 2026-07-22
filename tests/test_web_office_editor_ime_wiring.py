"""편집기 한글 IME 배선 회귀 — composition 이벤트가 연결되어 있는가.

배경(실측으로 확인된 결함):
    weboffice_edit.html 은 para_edit_runtime 에서 onKeyDown 만 import 했고
    compositionstart/update/end 는 연결하지 않았다. 그 결과
      · keydown 은 isComposing 을 보고 무시하고(reason=IN_COMPOSITION)
      · compositionend 는 아무도 처리하지 않아
    한글이 한 글자도 입력되지 않았다. 브라우저에서 IME 이벤트 순서를
    그대로 재현해 확인한 결과 명령 로그가 '편집 없음' 이었다.

    한글로 작성하는 관공서 서식에서 한글 입력 불가는 치명적이라
    배선 자체를 정적으로 감시한다.

왜 모듈 테스트로는 못 잡나:
    para_edit_runtime.mjs 의 핸들러 3종은 처음부터 정상이었다. 빠진 것은
    '페이지가 그것을 addEventListener 로 물리는 일' 이었다. 모듈만 보는
    테스트는 이 구멍을 통과시킨다.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EDITOR = PROJECT_ROOT / "frontend" / "web_office_viewer" / "weboffice_edit.html"
RUNTIME = PROJECT_ROOT / "frontend" / "web_office_viewer" / "para_edit_runtime.mjs"

COMPOSITION_HANDLERS = ["onCompositionStart", "onCompositionUpdate",
                        "onCompositionEnd"]
COMPOSITION_EVENTS = ["compositionstart", "compositionupdate", "compositionend"]


@pytest.fixture(scope="module")
def editor_src() -> str:
    assert EDITOR.is_file(), f"편집기 페이지 없음: {EDITOR}"
    return EDITOR.read_text(encoding="utf-8")


def test_runtime_exports_composition_handlers():
    src = RUNTIME.read_text(encoding="utf-8")
    for name in COMPOSITION_HANDLERS:
        assert re.search(rf"export\s+function\s+{name}\b", src), (
            f"para_edit_runtime.mjs 가 {name} 을 export 하지 않는다")


@pytest.mark.parametrize("handler", COMPOSITION_HANDLERS)
def test_editor_imports_composition_handler(editor_src, handler):
    assert handler in editor_src, (
        f"weboffice_edit.html 이 {handler} 를 import 하지 않는다 — "
        "한글 IME 입력이 통째로 죽는다")


@pytest.mark.parametrize("event", COMPOSITION_EVENTS)
def test_editor_wires_composition_event(editor_src, event):
    """import 만으로는 부족하다 — 실제로 리스너로 물려 있어야 한다."""
    assert re.search(rf"[\"']{event}[\"']", editor_src), (
        f"weboffice_edit.html 이 {event} 를 리스너로 연결하지 않는다")


def test_composition_handlers_feed_the_same_state_pipeline(editor_src):
    """composition 핸들러도 keydown 과 같은 경로(state·lastReason·renderAll)를
    타야 한다. 다른 경로로 빠지면 실행취소·검증에 잡히지 않는다."""
    m = re.search(r"compositionstart[\s\S]{0,900}?renderAll\(\)", editor_src)
    assert m, "composition 배선이 renderAll 경로를 타지 않는다"
    block = m.group(0)
    assert "state=r.state" in block.replace(" ", ""), (
        "composition 결과가 state 에 반영되지 않는다")
    assert "lastReason" in block, "composition 결과 사유가 기록되지 않는다"


def test_sheet_is_not_contenteditable(editor_src):
    """§4 — contenteditable 직접 저장 금지. 입력은 commandLog 경로로만 받는다."""
    sheet = re.search(r'<div[^>]*data-role="sheet"[^>]*>', editor_src)
    assert sheet, "sheet 엘리먼트를 찾을 수 없다"
    assert 'contenteditable="true"' not in sheet.group(0), (
        "sheet 가 contenteditable 이면 명령 경로를 우회해 저장된다")
