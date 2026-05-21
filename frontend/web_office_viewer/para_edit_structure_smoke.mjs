#!/usr/bin/env node
/* WEB-OFFICE-PARA-EDIT-STRUCTURE smoke (PARA-INSERT-01 + PARA-DELETE-01). */
import {
  makeParagraphEditorState, setCaret, splitParagraphAtCaret,
  mergeParagraphWithPrevious,
  undo, redo, typeTextAtCaret, setRange, deleteBackward,
  SEL_CARET, SEL_TEXT_RANGE,
} from "./para_edit_state.mjs";
import { onKeyDown } from "./para_edit_runtime.mjs";
import {
  allocateNewParagraphId, applyParaInsertToParagraphs,
  applyParaDeleteToParagraphs, makeParaInsertCommand,
  makeParaDeleteCommand, applyParaDeleteForwardToParagraphs,
} from "./para_edit_command.mjs";

const out = { task: "STRUCTURE-PARA-INSERT-01", checks: {} };
function rec(name, ok, extra) {
  out.checks[name] = { ok, ...(extra || {}) };
  if (!ok) {
    out.verdict = "FAIL"; out.failedAt = name;
    console.log(JSON.stringify(out)); process.exit(1);
  }
}

function makeState() {
  const doc = { sourceDocumentHash: "SHA1" };
  const paras = [
    { paragraphId: "100", parPrIDRef: "6",
        containerScope: { kind: "block", sectionIndex: 0,
                                    blockIndex: 0 },
        runs: [{ runId: "100_run0", text: "Hello World",
                          charPrIDRef: "11" }] },
    { paragraphId: "101", parPrIDRef: "6",
        containerScope: { kind: "block", sectionIndex: 0,
                                    blockIndex: 1 },
        runs: [{ runId: "101_run0", text: "Second paragraph",
                          charPrIDRef: "11" }] },
  ];
  return makeParagraphEditorState(doc, paras);
}

// 1. allocateNewParagraphId
let s = makeState();
rec("allocateNewParagraphId",
        allocateNewParagraphId(s.paragraphs) === "102");

// 2. split — caret = 5 in 'Hello World'
s = setCaret(s, "100", 5);
const r1 = splitParagraphAtCaret(s);
rec("splitOk", r1.reason === "OK");
rec("splitCommandType",
        r1.command?.commandType === "PARA_INSERT");
rec("splitForwardBeforeAfter",
        r1.command.forward.beforeText === "Hello"
        && r1.command.forward.afterText === " World");
rec("splitNewParagraphId",
        r1.command.forward.newParagraphId === "102");
rec("splitInheritedCharPr",
        r1.command.forward.newCharPrIDRef === "11");
rec("splitInheritedParPr",
        r1.command.forward.newParPrIDRef === "6");
rec("splitInverseIsParaDelete",
        r1.command.inverse.kind === "PARA_DELETE");

// 3. state.paragraphs grew by 1
rec("paragraphsCountIncreased",
        r1.state.paragraphs.length === 3);
rec("firstParaText",
        r1.state.paragraphs[0].runs.map(r => r.text).join("") === "Hello");
rec("secondParaText",
        r1.state.paragraphs[1].runs.map(r => r.text).join("") === " World");
rec("secondParaId",
        r1.state.paragraphs[1].paragraphId === "102");
rec("activeParaMovedToNew",
        r1.state.activeParagraphId === "102"
        && r1.state.caretOffset === 0);
rec("commandLogAppended",
        r1.state.commandLog.length === 1);

// 4. undo — paragraph count back to 2
const r2 = undo(r1.state);
rec("undoOk", r2.reason === "OK");
rec("paragraphsAfterUndo",
        r2.state.paragraphs.length === 2);
rec("originalParaRestoredText",
        r2.state.paragraphs[0].runs.map(r => r.text).join("")
        === "Hello World");
rec("undoStackEmptyAfterUndo",
        r2.state.undoStack.length === 0);
rec("redoStackHasOne",
        r2.state.redoStack.length === 1);
rec("undoMovedCaretBack",
        r2.state.activeParagraphId === "100"
        && r2.state.caretOffset === 5);

// 5. redo
const r3 = redo(r2.state);
rec("redoOk", r3.reason === "OK");
rec("paragraphsAfterRedo",
        r3.state.paragraphs.length === 3);
rec("activeParaAfterRedo",
        r3.state.activeParagraphId === "102");

// 6. caret at start (caret=0) — 빈 앞 paragraph
let s2 = setCaret(makeState(), "100", 0);
const r4 = splitParagraphAtCaret(s2);
rec("caretStartOk", r4.reason === "OK");
rec("emptyFirstPara",
        r4.state.paragraphs[0].runs.map(r => r.text).join("") === "");
rec("fullSecondPara",
        r4.state.paragraphs[1].runs.map(r => r.text).join("") === "Hello World");

// 7. caret at end (caret=11) — 빈 뒤 paragraph
let s3 = setCaret(makeState(), "100", 11);
const r5 = splitParagraphAtCaret(s3);
rec("caretEndOk", r5.reason === "OK");
rec("fullFirstParaEnd",
        r5.state.paragraphs[0].runs.map(r => r.text).join("") === "Hello World");
rec("emptySecondPara",
        r5.state.paragraphs[1].runs.map(r => r.text).join("") === "");

// 8. Enter via onKeyDown
let s4 = setCaret(makeState(), "100", 5);
const r6 = onKeyDown(s4, { key: "Enter",
                                                  preventDefault: () => {} });
rec("enterTriggersSplit", r6.reason === "OK"
        && r6.command?.commandType === "PARA_INSERT");

// 9. Shift+Enter rejected
const r7 = onKeyDown(s4, { key: "Enter", shiftKey: true,
                                                  preventDefault: () => {} });
rec("shiftEnterRejected", r7.reason === "SOFT_BREAK_NOT_SUPPORTED");

// 10. IME composition 중 Enter — onKeyDown 의 isComposing 게이트
const r8 = onKeyDown(s4, { key: "Enter", isComposing: true,
                                                  preventDefault: () => {} });
rec("enterDuringImeIgnored",
        r8.reason === "IN_COMPOSITION");

// 11. multi-paragraph selection 이 아닌 단일 paragraph 의 range Enter →
// MULTI_PARA_RANGE_NOT_SUPPORTED reject (range 가 있다면)
let s5 = setRange(makeState(), "100", 3, 7);
const r9 = splitParagraphAtCaret(s5);
rec("rangeSelectionEnterRejected",
        r9.reason === "MULTI_PARA_RANGE_NOT_SUPPORTED");

// 12. cell scope reject
const cellState = makeParagraphEditorState(
  { sourceDocumentHash: "SHA1" },
  [{ paragraphId: "200", parPrIDRef: "6",
       containerScope: { kind: "cell", tableIndex: 0,
                                  rowIndex: 0, colIndex: 0,
                                  paragraphIndex: 0 },
       runs: [{ runId: "200_r0", text: "cell text",
                        charPrIDRef: "11" }] }]);
let s6 = setCaret(cellState, "200", 4);
const r10 = splitParagraphAtCaret(s6);
rec("cellScopeRejected",
        r10.reason === "PARA_INSERT_CELL_SCOPE_NOT_SUPPORTED");

// 13. 회귀 — 기존 TYPE_TEXT 동작 보존
let s7 = setCaret(makeState(), "100", 5);
const r11 = typeTextAtCaret(s7, "X");
rec("typeTextStillWorks",
        r11.reason === "OK"
        && r11.command?.commandType === "TYPE_TEXT");

// ── PARA-DELETE-01 시나리오 ────────────────────────────────────

// 14. PARA_DELETE: Backspace at caret==0 → merge 성공
{
  // makeState() 는 "100", "200" 두 para → split "100" at 5 → "100", "201", "200"
  let st = setCaret(makeState(), "100", 5);
  const beforeCount = st.paragraphs.length;  // 2
  const ins = splitParagraphAtCaret(st);     // 3
  // 실제 신규 paragraph id 는 allocateNewParagraphId 가 발급
  const newPid14 = ins.state.activeParagraphId;
  let st2 = setCaret(ins.state, newPid14, 0);
  const r = mergeParagraphWithPrevious(st2);
  rec("paraDeleteMergeOk", r.reason === "OK",
      { got: r.reason });
  rec("paraDeleteCommandType",
      r.command?.commandType === "PARA_DELETE");
  // split +1, merge -1 → 원상 복귀 = beforeCount
  rec("paraDeleteParagraphsCount",
      r.state.paragraphs.length === beforeCount,
      { got: r.state.paragraphs.length, expected: beforeCount });
  rec("paraDeleteActiveId",
      r.state.activeParagraphId === "100");
  rec("paraDeleteCaretOffset",
      r.state.caretOffset === 5,
      { got: r.state.caretOffset });
  // 병합된 텍스트 확인 ("Hello World" split at 5 = "Hello" + " World" → merge = "Hello World")
  const mergedPara = r.state.paragraphs.find(p => p.paragraphId === "100");
  const mergedText14 = mergedPara.runs.reduce((a, rn) => a + rn.text, "");
  rec("paraDeleteMergedText",
      mergedText14 === "Hello World",
      { got: mergedText14 });
}

// 15. PARA_DELETE inverse = PARA_INSERT (undo 재분리)
{
  let st = setCaret(makeState(), "100", 5);
  const ins = splitParagraphAtCaret(st);
  const newPid15 = ins.state.activeParagraphId;
  let st2 = setCaret(ins.state, newPid15, 0);
  const del = mergeParagraphWithPrevious(st2);
  const undone = undo(del.state);
  // undo(PARA_DELETE) = re-split → 3 paragraphs ("100", newPid15, "200")
  rec("paraDeleteUndoCount",
      undone.state.paragraphs.length === 3,
      { got: undone.state.paragraphs.length });
  rec("paraDeleteUndoActiveId",
      undone.state.activeParagraphId === newPid15);
  const redone = redo(undone.state);
  // redo(PARA_DELETE) = re-merge → 2 paragraphs
  rec("paraDeleteRedoCount",
      redone.state.paragraphs.length === 2);
}

// 16. 첫 paragraph Backspace → NO_PREV_PARAGRAPH reject
{
  let st = setCaret(makeState(), "100", 0);
  const r = mergeParagraphWithPrevious(st);
  rec("paraDeleteFirstParaReject",
      r.reason === "NO_PREV_PARAGRAPH");
}

// 17. cell scope → PARA_DELETE_CELL_SCOPE_NOT_SUPPORTED
{
  const cellState = makeParagraphEditorState(
    { sourceDocumentHash: "SHA1" },
    [{ paragraphId: "200", parPrIDRef: "6",
       containerScope: { kind: "cell", tableIndex: 0,
                                  rowIndex: 0, colIndex: 0,
                                  paragraphIndex: 0 },
       runs: [{ runId: "200_r0", text: "cell text",
                        charPrIDRef: "11" }] }]);
  let sc = setCaret(cellState, "200", 0);
  const r = mergeParagraphWithPrevious(sc);
  rec("paraDeleteCellScopeReject",
      r.reason === "PARA_DELETE_CELL_SCOPE_NOT_SUPPORTED");
}

// 18. section boundary → NO_PREV_PARAGRAPH (서로 다른 sectionIndex)
{
  const twoSecState = makeParagraphEditorState(
    { sourceDocumentHash: "SHA1" },
    [
      { paragraphId: "300", parPrIDRef: "6",
          containerScope: { kind: "block", sectionIndex: 0, blockIndex: 0 },
          runs: [{ runId: "300_r0", text: "Sec0", charPrIDRef: "11" }] },
      { paragraphId: "301", parPrIDRef: "6",
          containerScope: { kind: "block", sectionIndex: 1, blockIndex: 0 },
          runs: [{ runId: "301_r0", text: "Sec1", charPrIDRef: "11" }] },
    ]);
  let ss = setCaret(twoSecState, "301", 0);
  const r = mergeParagraphWithPrevious(ss);
  rec("paraDeleteSectionBoundaryReject",
      r.reason === "SECTION_BOUNDARY_NOT_SUPPORTED",
      { got: r.reason });
}

// 19. Backspace 중간 위치 → DELETE_TEXT_RANGE (기존 동작)
{
  let st = setCaret(makeState(), "100", 3);
  const r = deleteBackward(st);
  rec("backspaceMiddleIsDeleteText",
      r.command?.commandType === "DELETE_TEXT_RANGE");
}

// 20. Backspace at 0, Enter key (onKeyDown) 연동
{
  let st = setCaret(makeState(), "100", 5);
  const ins = onKeyDown(st, { key: "Enter" });
  const newPid20 = ins.state.activeParagraphId;
  let st2 = setCaret(ins.state, newPid20, 0);
  const del = onKeyDown(st2, { key: "Backspace" });
  rec("backspaceViaOnKeyDown",
      del.command?.commandType === "PARA_DELETE",
      { got: del.command?.commandType });
}

// 21. makeParaDeleteCommand schema 검증
{
  const prev = { paragraphId: "A", parPrIDRef: "6",
                              containerScope: { kind: "block", sectionIndex: 0,
                                                        blockIndex: 0 },
                              runs: [{ runId: "A_r0", text: "Prev",
                                                charPrIDRef: "11" }] };
  const cur  = { paragraphId: "B", parPrIDRef: "6",
                              containerScope: { kind: "block", sectionIndex: 0,
                                                        blockIndex: 1 },
                              runs: [{ runId: "B_r0", text: "Cur",
                                                charPrIDRef: "11" }] };
  const cmd = makeParaDeleteCommand({
    prevParagraph: prev, currentParagraph: cur,
    sourceDocumentHash: "SH",
  });
  rec("paraDeleteCmdType",
      cmd.commandType === "PARA_DELETE");
  rec("paraDeleteCmdForwardKind",
      cmd.forward.kind === "PARA_DELETE");
  rec("paraDeleteCmdInverseKind",
      cmd.inverse.kind === "PARA_INSERT");
  rec("paraDeleteCmdMergeOffset",
      cmd.forward.mergeOffset === 4,
      { got: cmd.forward.mergeOffset });
  rec("paraDeleteCmdExpectedBefore",
      cmd.expectedBefore === "Cur");
  rec("paraDeleteCmdInverseCaretOffset",
      cmd.inverse.caretOffset === 4);
}

// 22. applyParaDeleteForwardToParagraphs 검증
{
  const paras = [
    { paragraphId: "P1", parPrIDRef: "6",
        containerScope: null,
        runs: [{ runId: "P1_r0", text: "First ", charPrIDRef: "C1" }] },
    { paragraphId: "P2", parPrIDRef: "6",
        containerScope: null,
        runs: [{ runId: "P2_r0", text: "Second", charPrIDRef: "C1" }] },
  ];
  const cmd = makeParaDeleteCommand({
    prevParagraph: paras[0], currentParagraph: paras[1],
    sourceDocumentHash: "SH",
  });
  const result = applyParaDeleteForwardToParagraphs(paras, cmd);
  rec("paraDeleteForwardCount",
      result.length === 1, { got: result.length });
  const totalText = result[0].runs.reduce((a, r) => a + r.text, "");
  rec("paraDeleteForwardText",
      totalText === "First Second", { got: totalText });
  rec("paraDeleteForwardId",
      result[0].paragraphId === "P1");
}

// ── WEB-OFFICE-PARA-EDIT-STRUCTURE-SCOPE-BOUNDARY-REJECT-01 ──────────────

function makeNonBlockState(kind) {
  return makeParagraphEditorState(
    { sourceDocumentHash: "SHA1" },
    [{ paragraphId: "NB1", parPrIDRef: "6",
       containerScope: { kind },
       runs: [{ runId: "NB1_r0", text: "text", charPrIDRef: "11" }] }]);
}

// 23. header scope PARA_INSERT reject
{
  let st = setCaret(makeNonBlockState("header"), "NB1", 2);
  const r = splitParagraphAtCaret(st);
  rec("headerScopeInsertReject",
      r.reason === "HEADER_SCOPE_NOT_SUPPORTED", { got: r.reason });
}

// 24. footer scope PARA_INSERT reject
{
  let st = setCaret(makeNonBlockState("footer"), "NB1", 2);
  const r = splitParagraphAtCaret(st);
  rec("footerScopeInsertReject",
      r.reason === "FOOTER_SCOPE_NOT_SUPPORTED", { got: r.reason });
}

// 25. unknown non-block scope PARA_INSERT reject → BODY_SCOPE_ONLY_SUPPORTED
{
  let st = setCaret(makeNonBlockState("caption"), "NB1", 2);
  const r = splitParagraphAtCaret(st);
  rec("captionScopeInsertReject",
      r.reason === "CAPTION_SCOPE_NOT_SUPPORTED", { got: r.reason });
}

// 26. header scope PARA_DELETE reject
{
  let st = setCaret(makeNonBlockState("header"), "NB1", 0);
  const r = mergeParagraphWithPrevious(st);
  rec("headerScopeDeleteReject",
      r.reason === "HEADER_SCOPE_NOT_SUPPORTED", { got: r.reason });
}

// 27. footer scope PARA_DELETE reject
{
  let st = setCaret(makeNonBlockState("footer"), "NB1", 0);
  const r = mergeParagraphWithPrevious(st);
  rec("footerScopeDeleteReject",
      r.reason === "FOOTER_SCOPE_NOT_SUPPORTED", { got: r.reason });
}

// 28. unknown scope PARA_DELETE reject → BODY_SCOPE_ONLY_SUPPORTED
{
  let st = setCaret(makeNonBlockState("unknown_kind"), "NB1", 0);
  const r = mergeParagraphWithPrevious(st);
  rec("unknownScopeDeleteReject",
      r.reason === "BODY_SCOPE_ONLY_SUPPORTED", { got: r.reason });
}

out.verdict = "PASS";
console.log(JSON.stringify(out));
