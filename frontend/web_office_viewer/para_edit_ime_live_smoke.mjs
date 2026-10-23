#!/usr/bin/env node
/* WEB-OFFICE-PARA-EDIT-IME-LIVE-01 — browser IME live smoke.
 *
 * compositionstart / compositionupdate / compositionend 흐름을 실제
 * para_edit_state + para_edit_runtime 자재로 구동해 TYPE_TEXT command
 * 1건 생성, expectedBefore="", rangeStart==rangeEnd, afterText=최종
 * 조합 문자열, containerScope 유지, undo/redo, commandLog append-only
 * 의 동적 신호를 한 번에 수집해 JSON 으로 출력한다.
 *
 * 본 스크립트는 신규 writer 자재를 만들지 않는다 — 기존 state machine
 * 호출만 수행한다 (§11-6).
 */
import {
  makeParagraphEditorState, selectParagraph, setCaret,
  typeTextAtCaret, undo, redo,
  SEL_COMPOSITION, SEL_CARET,
} from "./para_edit_state.mjs";
import {
  onCompositionStart, onCompositionUpdate, onCompositionEnd,
} from "./para_edit_runtime.mjs";

const result = { task: "WEB-OFFICE-PARA-EDIT-IME-LIVE-01", checks: {} };

function rec(name, ok, extra) {
  result.checks[name] = { ok, ...(extra || {}) };
  if (!ok) {
    result.verdict = "FAIL";
    result.failedAt = name;
    console.log(JSON.stringify(result));
    process.exit(1);
  }
}

const doc = { sourceDocumentHash: "ime-live-sha",
                        sourceRef: { sha256: "ime-live-sha" } };
const SCOPE = { kind: "cell", tableIndex: 0, rowIndex: 0,
                          colIndex: 0, paragraphIndex: 0, runIndex: 0 };
const paragraphs = [{
  paragraphId: "par_ime", parPrIDRef: "P1",
  containerScope: SCOPE,
  runs: [
    { runId: "par_ime_run0", text: "기존텍스트", charPrIDRef: "C1" },
  ],
}];

// ── 1. fixture 정합 ────────────────────────────────────────────────
rec("fixtureSingleRun", paragraphs[0].runs.length === 1);
rec("fixtureContainerScopeCell",
        paragraphs[0].containerScope?.kind === "cell");
rec("fixtureCharPr", paragraphs[0].runs[0].charPrIDRef === "C1");
rec("fixtureParPr", paragraphs[0].parPrIDRef === "P1");

// ── 2. compositionstart → COMPOSITION 모드 진입 ────────────────────
let s = makeParagraphEditorState(doc, paragraphs);
s = selectParagraph(s, "par_ime");
s = setCaret(s, "par_ime", 5);  // "기존텍스트" 끝
const logLen0 = s.commandLog.length;
s = onCompositionStart(s, {}).state;
rec("compositionStartMode", s.selectionMode === SEL_COMPOSITION);
rec("compositionStartActive", s.composition.active === true);
rec("compositionStartNoCommand", s.commandLog.length === logLen0);

// ── 3. compositionupdate × 3 — command 0건 ─────────────────────────
const updates = ["ㅎ", "한", "한그"];
for (const data of updates) {
  s = onCompositionUpdate(s, { data }).state;
}
rec("compositionUpdateNoCommand", s.commandLog.length === logLen0,
      { commandLogLen: s.commandLog.length });
rec("compositionUpdateAccumulated",
        s.composition.accumulatedText === "한그");

// ── 4. compositionend — 정확히 TYPE_TEXT 1건 생성 ──────────────────
const finalText = "한글";
const r1 = onCompositionEnd(s, { data: finalText });
s = r1.state;
rec("compositionEndCommandCreated", r1.command !== null);
rec("compositionEndCommandType",
        r1.command?.commandType === "TYPE_TEXT");
rec("compositionEndCommandCount",
        s.commandLog.length === logLen0 + 1,
        { commandLogLen: s.commandLog.length });
rec("compositionEndClearActive",
        s.composition.active === false
        && s.selectionMode === SEL_CARET);

const cmd = r1.command;
rec("typeTextExpectedBeforeEmpty", cmd.expectedBefore === "");
rec("typeTextRangeStartEqEnd",
        cmd.forward.rangeStart === cmd.forward.rangeEnd);
rec("typeTextRangeAtCaret",
        cmd.forward.rangeStart === 5
        && cmd.forward.caretOffset === 5);
rec("typeTextAfterTextEqFinal",
        cmd.forward.afterText === finalText);
rec("typeTextInsertTextEqFinal",
        cmd.forward.insertText === finalText);
rec("typeTextContainerScopeCell",
        cmd.target?.containerScope?.kind === "cell");
rec("typeTextContainerScopePreserved",
        cmd.target?.containerScope?.tableIndex === 0
        && cmd.target?.containerScope?.rowIndex === 0
        && cmd.target?.containerScope?.colIndex === 0);
rec("typeTextInverseDeleteRange",
        cmd.inverse?.kind === "DELETE_TEXT_RANGE");
rec("typeTextInverseRangeFocus",
        cmd.inverse?.rangeAnchor === 5
        && cmd.inverse?.rangeFocus === 5 + finalText.length);
rec("typeTextSourceHash",
        cmd.sourceDocumentHash === "ime-live-sha");
rec("paragraphTextAppended",
        s.paragraphs[0].runs.map((r) => r.text).join("")
        === "기존텍스트한글");

// ── 5. undo — TYPE_TEXT 되돌림 (commandLog append-only) ────────────
const logBeforeUndo = s.commandLog.length;
const ru = undo(s); s = ru.state;
rec("undoOk", ru.reason === "OK");
rec("undoTextReverted",
        s.paragraphs[0].runs.map((r) => r.text).join("")
        === "기존텍스트");
rec("undoCommandLogAppendOnly",
        s.commandLog.length === logBeforeUndo,
        { commandLogLen: s.commandLog.length });
rec("undoStackEmpty", s.undoStack.length === 0);
rec("undoRedoPending", s.redoStack.length === 1);

// ── 6. redo — TYPE_TEXT 재적용 ─────────────────────────────────────
const rr = redo(s); s = rr.state;
rec("redoOk", rr.reason === "OK");
rec("redoTextReApplied",
        s.paragraphs[0].runs.map((r) => r.text).join("")
        === "기존텍스트한글");
rec("redoUndoStack", s.undoStack.length === 1);
rec("redoRedoEmpty", s.redoStack.length === 0);

// ── 7. compositionend 빈 finalText (cancel) — command 0건 ──────────
s = onCompositionStart(s, {}).state;
s = onCompositionUpdate(s, { data: "ㅂ" }).state;
const cancelLogLen = s.commandLog.length;
const rc = onCompositionEnd(s, { data: "" });
rec("cancelNoCommand", rc.command === null);
rec("cancelReasonCancelled", rc.reason === "CANCELLED");
rec("cancelLogUnchanged",
        rc.state.commandLog.length === cancelLogLen);

// ── 8. compositionupdate 중 typeTextAtCaret 잠금 ───────────────────
s = makeParagraphEditorState(doc, paragraphs);
s = selectParagraph(s, "par_ime");
s = setCaret(s, "par_ime", 0);
s = onCompositionStart(s, {}).state;
const lockLogLen = s.commandLog.length;
const rl = typeTextAtCaret(s, "외부키");
rec("compositionLocksTypeText", rl.command === null
        && rl.reason === "COMPOSITION_LOCKED");
rec("compositionLockedLogUnchanged",
        rl.state.commandLog.length === lockLogLen);

// ── 9. emit live command snapshot (Python E2E 투입용) ──────────────
result.liveCommand = {
  commandType: cmd.commandType,
  expectedBefore: cmd.expectedBefore,
  caretOffset: cmd.forward.caretOffset,
  rangeStart: cmd.forward.rangeStart,
  rangeEnd: cmd.forward.rangeEnd,
  afterText: cmd.forward.afterText,
  insertText: cmd.forward.insertText,
  inheritCharPrIDRef: cmd.forward.inheritCharPrIDRef,
  containerScope: cmd.target.containerScope,
  sourceDocumentHash: cmd.sourceDocumentHash,
  paragraphId: cmd.target.paragraphId,
  inverse: {
    kind: cmd.inverse.kind,
    rangeAnchor: cmd.inverse.rangeAnchor,
    rangeFocus: cmd.inverse.rangeFocus,
  },
};
result.finalText = finalText;
result.verdict = "PASS";
console.log(JSON.stringify(result));
