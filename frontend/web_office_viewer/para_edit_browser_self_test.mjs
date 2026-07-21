#!/usr/bin/env node
/* PARA-EDIT BROWSER 상태기계 자체 시나리오. 실패 시 비-0 종료. */
import {
  makeParagraphEditorState, selectParagraph,
  setCaret, setRange, clearSelection,
  typeTextAtCaret, deleteRange, deleteBackward,
  applyFormatToSelection,
  startComposition, updateComposition, endComposition,
  cancelComposition,
  undo, redo, buildSaveDryRunPayload,
  SEL_NONE, SEL_CARET, SEL_TEXT_RANGE, SEL_COMPOSITION,
} from "./para_edit_state.mjs";
import {
  onKeyDown, onCompositionStart, onCompositionUpdate,
  onCompositionEnd,
} from "./para_edit_runtime.mjs";

function assert(cond, msg) {
  if (!cond) { console.error("ASSERT FAIL:", msg); process.exit(1); }
}
function txt(p) { return p.runs.map((r) => r.text).join(""); }
function paraOf(s) {
  return s.paragraphs.find(
    (p) => p.paragraphId === s.activeParagraphId);
}

const doc = { sourceDocumentHash: "abc123",
                        sourceRef: { sha256: "abc123" } };
const paragraphs = [{
  paragraphId: "par_p1", parPrIDRef: "P1",
  runs: [
    { runId: "par_p1_run0", text: "ab", charPrIDRef: "A" },
    { runId: "par_p1_run1", text: "cd", charPrIDRef: "B" },
    { runId: "par_p1_run2", text: "ef", charPrIDRef: "A" },
  ],
  // CONTAINERSCOPE_BRIDGE_01: 모든 paragraph 는 containerScope 필수
  containerScope: { kind: "cell", tableIndex: 0, rowIndex: 0,
                                      colIndex: 0, paragraphIndex: 0, runIndex: 0 },
}];

const checks = {};

// 1) initial state
let s = makeParagraphEditorState(doc, paragraphs);
assert(s.selectionMode === SEL_NONE, "init NONE");
assert(s.dirty === false, "init not dirty");
assert(s.sourceDocumentHash === "abc123", "hash propagated");
checks.initState = true;

// 2) selectParagraph + caret
s = selectParagraph(s, "par_p1");
assert(s.activeParagraphId === "par_p1");
assert(s.selectionMode === SEL_CARET);
assert(s.caretOffset === 0);
s = setCaret(s, "par_p1", 1);
assert(s.caretOffset === 1);
checks.selectAndCaret = true;

// 3) typeTextAtCaret → TYPE_TEXT
let r = typeTextAtCaret(s, "X");
assert(r.command !== null, "command created");
assert(r.command.commandType === "TYPE_TEXT");
// WEB-OFFICE-PARA-TYPE-TEXT-CONTRACT-01: TYPE_TEXT expectedBefore="".
assert(r.command.expectedBefore === "");
assert(r.command.sourceDocumentHash === "abc123");
assert(r.command.target.paragraphId === "par_p1");
s = r.state;
assert(s.dirty === true);
assert(s.commandLog.length === 1);
assert(s.undoStack.length === 1);
assert(s.caretOffset === 2, `caret moved to 2, got ${s.caretOffset}`);
assert(txt(paraOf(s)) === "aXbcdef", `text=${txt(paraOf(s))}`);
checks.typeTextCommand = true;

// 4) range REPLACE
s = setRange(s, "par_p1", 0, 1);   // select "a"
assert(s.selectionMode === SEL_TEXT_RANGE);
r = typeTextAtCaret(s, "Z");
assert(r.command.commandType === "REPLACE_TEXT_RANGE",
  `got ${r.command.commandType}`);
assert(r.command.expectedBefore === "a");
s = r.state;
assert(s.selectionMode === SEL_CARET, "back to CARET after replace");
assert(txt(paraOf(s)) === "ZXbcdef");
checks.replaceRangeCommand = true;

// 5) deleteRange
s = setRange(s, "par_p1", 0, 2);   // select "ZX"
r = deleteRange(s);
assert(r.command.commandType === "DELETE_TEXT_RANGE");
assert(r.command.expectedBefore === "ZX");
s = r.state;
assert(txt(paraOf(s)) === "bcdef");
checks.deleteRangeCommand = true;

// 6) deleteBackward
s = setCaret(s, "par_p1", 2);
r = deleteBackward(s);
assert(r.command.commandType === "DELETE_TEXT_RANGE");
assert(r.command.expectedBefore === "c");
s = r.state;
assert(txt(paraOf(s)) === "bdef");
assert(s.caretOffset === 1);
checks.deleteBackward = true;

// 7) IME composition — start / update / end
s = setCaret(s, "par_p1", 4);   // 끝 위치
const beforeLog = s.commandLog.length;
s = onCompositionStart(s, {}).state;
assert(s.selectionMode === SEL_COMPOSITION);
assert(s.composition.active === true);
s = onCompositionUpdate(s, { data: "ㅎ" }).state;
s = onCompositionUpdate(s, { data: "한" }).state;
// 업데이트 중에는 commandLog 변화 없음
assert(s.commandLog.length === beforeLog,
  "no command during composition update");
r = onCompositionEnd(s, { data: "한글" });
assert(r.command !== null, "single command on composition end");
assert(r.command.commandType === "TYPE_TEXT");
s = r.state;
assert(s.commandLog.length === beforeLog + 1, "exactly 1 cmd added");
assert(s.composition.active === false, "composition cleared");
assert(s.selectionMode === SEL_CARET, "back to CARET");
assert(txt(paraOf(s)).endsWith("한글"), `tail: ${txt(paraOf(s))}`);
checks.imeCompositionEnd = true;

// 8) IME composition cancel
const beforeCancel = s.commandLog.length;
s = onCompositionStart(s, {}).state;
s = onCompositionUpdate(s, { data: "ㅋ" }).state;
r = onCompositionEnd(s, { data: "" });   // cancel = empty finalText
assert(r.command === null, "no command on cancel");
assert(r.reason === "CANCELLED");
s = r.state;
assert(s.commandLog.length === beforeCancel, "log unchanged on cancel");
assert(s.composition.active === false);
checks.imeCancel = true;

// 9) typeTextAtCaret during composition → 누적만, command 미생성
s = setCaret(s, "par_p1", 0);
s = onCompositionStart(s, {}).state;
r = typeTextAtCaret(s, "X");
assert(r.command === null, "no command while composition active");
assert(r.reason === "COMPOSITION_LOCKED");
s = cancelComposition(s);
checks.compositionLockBlocksTypeText = true;

// 10) undo / redo
s = makeParagraphEditorState(doc, paragraphs);
s = selectParagraph(s, "par_p1");
s = setCaret(s, "par_p1", 1);
s = typeTextAtCaret(s, "X").state;
assert(txt(paraOf(s)) === "aXbcdef");
const logLenBefore = s.commandLog.length;
r = undo(s); s = r.state;
assert(r.reason === "OK");
assert(txt(paraOf(s)) === "abcdef", "undo restored");
assert(s.undoStack.length === 0);
assert(s.redoStack.length === 1);
assert(s.dirty === false);
assert(s.commandLog.length === logLenBefore,
  "commandLog append-only across undo");
r = redo(s); s = r.state;
assert(txt(paraOf(s)) === "aXbcdef", "redo re-applied");
assert(s.undoStack.length === 1);
assert(s.redoStack.length === 0);
assert(s.dirty === true);
checks.undoRedo = true;

// 11) onKeyDown — Backspace / 일반 키
s = makeParagraphEditorState(doc, paragraphs);
s = selectParagraph(s, "par_p1");
s = setCaret(s, "par_p1", 2);
r = onKeyDown(s, { key: "Backspace", preventDefault() {} });
assert(r.command && r.command.commandType === "DELETE_TEXT_RANGE");
s = r.state;
assert(txt(paraOf(s)) === "acdef");
r = onKeyDown(s, { key: "M", preventDefault() {} });
assert(r.command && r.command.commandType === "TYPE_TEXT");
s = r.state;
assert(txt(paraOf(s)) === "aMcdef");
checks.keyboardDispatch = true;

// 12) onKeyDown 중 isComposing=true 면 무시
s = makeParagraphEditorState(doc, paragraphs);
s = selectParagraph(s, "par_p1");
const baseLen = s.commandLog.length;
r = onKeyDown(s, { key: "X", isComposing: true,
                                  preventDefault() {} });
assert(r.command === null);
assert(r.state.commandLog.length === baseLen);
checks.keyDownIgnoredDuringComposition = true;

// 13) save dry-run NOOP when log empty
const fresh = makeParagraphEditorState(doc, paragraphs);
const noop = buildSaveDryRunPayload(fresh);
assert(noop.status === "NOOP");
assert(noop.plan === null);
checks.saveDryRunNoop = true;

// 14) save dry-run payload populated
s = makeParagraphEditorState(doc, paragraphs);
s = selectParagraph(s, "par_p1");
s = setCaret(s, "par_p1", 1);
s = typeTextAtCaret(s, "X").state;
const payload = buildSaveDryRunPayload(s);
assert(payload.status === "READY_FOR_SERVER_VALIDATION");
assert(payload.dryRun === true);
assert(payload.sourceDocumentHash === "abc123");
assert(payload.commandLog.length >= 1);
checks.saveDryRunReady = true;

// 15) WEB-OFFICE-PARA-EDIT-INLINE-SCOPE-BOUNDARY-REJECT-01:
//     header/footer/footnote/endnote/caption scope 문단의 inline 편집은
//     거부. block/cell scope 는 계속 허용 (기능 회귀 방지).
function scopedParas(kind) {
  return [{
    paragraphId: "sp1", parPrIDRef: "P1",
    runs: [{ runId: "sp1_run0", text: "hello", charPrIDRef: "A" }],
    containerScope: { kind, sectionIndex: 0 },
  }];
}
function inlineTypeReason(kind) {
  let st = makeParagraphEditorState(doc, scopedParas(kind));
  st = selectParagraph(st, "sp1");
  st = setCaret(st, "sp1", 2);
  return typeTextAtCaret(st, "Z");
}
for (const [kind, reason] of [
  ["header", "HEADER_SCOPE_NOT_SUPPORTED"],
  ["footer", "FOOTER_SCOPE_NOT_SUPPORTED"],
  ["footnote", "FOOTNOTE_SCOPE_NOT_SUPPORTED"],
  ["endnote", "ENDNOTE_SCOPE_NOT_SUPPORTED"],
  ["caption", "CAPTION_SCOPE_NOT_SUPPORTED"],
]) {
  const rr = inlineTypeReason(kind);
  assert(rr.command === null, `${kind} inline typeText: no command`);
  assert(rr.reason === reason, `${kind} inline typeText rejected`);
  assert(rr.state.commandLog.length === 0, `${kind} inline: log empty`);
  assert(rr.state.dirty === false, `${kind} inline: not dirty`);
}
// deleteRange / applyFormat / deleteBackward 도 동일 scope 가드 적용
{
  let sr = makeParagraphEditorState(doc, scopedParas("footer"));
  sr = selectParagraph(sr, "sp1");
  sr = setRange(sr, "sp1", 1, 3);
  assert(deleteRange(sr).reason === "FOOTER_SCOPE_NOT_SUPPORTED",
    "footer inline deleteRange rejected");
  assert(applyFormatToSelection(sr, "A").reason
    === "FOOTER_SCOPE_NOT_SUPPORTED",
    "footer inline applyFormat rejected");
  let sb = makeParagraphEditorState(doc, scopedParas("header"));
  sb = selectParagraph(sb, "sp1");
  sb = setCaret(sb, "sp1", 2);
  assert(deleteBackward(sb).reason === "HEADER_SCOPE_NOT_SUPPORTED",
    "header inline deleteBackward rejected");
}
// block / cell scope 는 여전히 정상 발행
for (const kind of ["block", "cell"]) {
  let sa = makeParagraphEditorState(doc, scopedParas(kind));
  sa = selectParagraph(sa, "sp1");
  sa = setCaret(sa, "sp1", 2);
  const ra = typeTextAtCaret(sa, "Z");
  assert(ra.command !== null && ra.reason === "OK",
    `${kind} inline typeText still allowed`);
}
checks.inlineScopeBoundaryReject = true;

console.log(JSON.stringify({
  task: "WEB-OFFICE-PARA-EDIT-BROWSER-01",
  checks, verdict: "PASS",
}));
