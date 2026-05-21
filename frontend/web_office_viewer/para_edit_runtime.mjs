/* DOM 이벤트 핸들러 어댑터 — 브라우저에서 사용.
 *
 * 본 파일의 함수들은 DOM event-like 객체를 받아 para_edit_state 의
 * 순수 함수를 호출한다. writer / save / output 호출 없음.
 */
import {
  typeTextAtCaret, setCaret, setRange,
  startComposition, updateComposition, endComposition,
  cancelComposition, deleteBackward, deleteRange,
  undo, redo,
  // WEB-OFFICE-PARA-EDIT-STRUCTURE-PARA-INSERT-01.
  splitParagraphAtCaret,
} from "./para_edit_state.mjs";

/* keydown 이벤트 핸들러. ev = { key, isComposing?, preventDefault? }. */
export function onKeyDown(state, ev) {
  // composition 중 keydown 은 무시 (브라우저 표준 동작 모방)
  if (ev.isComposing) {
    return { state, command: null, reason: "IN_COMPOSITION" };
  }
  if (ev.key === "Backspace") {
    if (ev.preventDefault) ev.preventDefault();
    return deleteBackward(state);
  }
  if (ev.key === "Delete") {
    // Delete (caret 우측 1 글자) — caret+1 까지의 range 로 delete
    if (state.selectionMode === "TEXT_RANGE") return deleteRange(state);
    const r = setRange(state, state.activeParagraphId,
                                          state.caretOffset, state.caretOffset + 1);
    return deleteRange(r);
  }
  if (ev.key === "z" && (ev.ctrlKey || ev.metaKey) && !ev.shiftKey) {
    if (ev.preventDefault) ev.preventDefault();
    return undo(state);
  }
  if ((ev.key === "y" && (ev.ctrlKey || ev.metaKey))
      || (ev.key === "z" && (ev.ctrlKey || ev.metaKey)
          && ev.shiftKey)) {
    if (ev.preventDefault) ev.preventDefault();
    return redo(state);
  }
  // WEB-OFFICE-PARA-EDIT-STRUCTURE-PARA-INSERT-01: Enter → paragraph split.
  if (ev.key === "Enter") {
    if (ev.shiftKey) {
      // Shift+Enter (soft break) 는 1차 공정에서 미지원.
      if (ev.preventDefault) ev.preventDefault();
      return { state, command: null,
                      reason: "SOFT_BREAK_NOT_SUPPORTED" };
    }
    if (ev.ctrlKey || ev.metaKey) {
      // Ctrl/Meta+Enter 는 본 공정에서 무시 (커스텀 단축키 후속).
      return { state, command: null, reason: "UNHANDLED_KEY" };
    }
    if (ev.preventDefault) ev.preventDefault();
    return splitParagraphAtCaret(state);
  }
  // 일반 인쇄 가능한 문자
  if (ev.key && ev.key.length === 1 && !ev.ctrlKey && !ev.metaKey) {
    if (ev.preventDefault) ev.preventDefault();
    return typeTextAtCaret(state, ev.key);
  }
  return { state, command: null, reason: "UNHANDLED_KEY" };
}

/* compositionstart 핸들러 */
export function onCompositionStart(state, _ev) {
  return { state: startComposition(state), command: null,
              reason: "COMPOSITION_STARTED" };
}

/* compositionupdate 핸들러 */
export function onCompositionUpdate(state, ev) {
  return {
    state: updateComposition(state, ev.data ?? ""),
    command: null,
    reason: "COMPOSITION_UPDATING",
  };
}

/* compositionend 핸들러 — 단일 command 생성 또는 cancel */
export function onCompositionEnd(state, ev) {
  return endComposition(state, ev.data ?? "");
}

/* 셀렉션 변경 (브라우저 selectionchange 등에서 호출) */
export function onSelectionChange(state, paragraphId, anchorOff, focusOff) {
  if (anchorOff === focusOff) {
    return setCaret(state, paragraphId, anchorOff);
  }
  return setRange(state, paragraphId, anchorOff, focusOff);
}

/* DOM 마운트 시 listener 부착 — 브라우저 전용. Node 테스트에서는 호출
 * 하지 않는다. element 는 contenteditable 가 아니어야 한다 — 본 단지는
 * commandLog 경로로만 입력을 받는다. */
export function attachParagraphEditorListeners(element, getState,
                                                                                        setStateFn) {
  if (typeof element.addEventListener !== "function") return;
  // 보안 어서션 — contenteditable 직접 저장 금지
  if (element.getAttribute &&
      element.getAttribute("contenteditable") === "true") {
    throw new Error(
      "paragraph editor element must NOT be contenteditable=true");
  }
  const dispatch = (fn, ev) => {
    const r = fn(getState(), ev);
    setStateFn(r.state);
    return r;
  };
  element.addEventListener("keydown", (e) => dispatch(onKeyDown, e));
  element.addEventListener("compositionstart",
                                                      (e) => dispatch(onCompositionStart, e));
  element.addEventListener("compositionupdate",
                                                      (e) => dispatch(onCompositionUpdate, e));
  element.addEventListener("compositionend",
                                                      (e) => dispatch(onCompositionEnd, e));
}
