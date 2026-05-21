#!/usr/bin/env node
/* PARA-EDIT v2 모델 자체 시나리오. 실패 시 비-0 종료. */
import {
  makeTypeTextCommand, makeReplaceTextRangeCommand,
  makeDeleteTextRangeCommand,
  applyCommandToParagraph, normalizeParagraph,
  splitRun, mergeRuns,
  validateExpectedBefore, validateCharPrPreserved,
  validateParPrPreserved,
  REASON_MERGE_CHARPR_MISMATCH, REASON_REQUIRES_REVIEW,
  POLICY_REQUIRES_REVIEW, POLICY_FOCUS_CHARPR,
} from "./para_edit_command.mjs";
import {
  makeParagraphEditorState, selectParagraph, setCaret,
  typeTextAtCaret,
} from "./para_edit_state.mjs";

function assert(cond, msg) {
  if (!cond) { console.error("ASSERT FAIL:", msg); process.exit(1); }
}
function paraText(p) { return p.runs.map((r) => r.text).join(""); }

const target = {
  paragraphId: "par_p1", containerKind: "block",
  containerId: "blk_p1", sourceSha256: "abc",
};
const hash = "abc";
const checks = {};

// fixture paragraph: "ab|cd|ef" with 3 runs charPr A/B/A
const p0 = {
  paragraphId: "par_p1", parPrIDRef: "P1",
  runs: [
    { runId: "par_p1_run0", text: "ab", charPrIDRef: "A" },
    { runId: "par_p1_run1", text: "cd", charPrIDRef: "B" },
    { runId: "par_p1_run2", text: "ef", charPrIDRef: "A" },
  ],
};
assert(paraText(p0) === "abcdef", "fixture text");

// 1) TYPE_TEXT 단일 run 안 (offset 1, run0 → split)
let cmd = makeTypeTextCommand({
  target, paragraph: p0, caretOffset: 1, insertText: "X",
  sourceDocumentHash: hash,
});
assert(cmd && cmd.commandType === "TYPE_TEXT", "TYPE_TEXT created");
assert(cmd.forward.inheritCharPrIDRef === "A", "inherit charPr A");
assert(cmd.inverse.kind === "DELETE_TEXT_RANGE", "inverse=DELETE");
let p1 = applyCommandToParagraph(p0, cmd);
assert(paraText(p1) === "aXbcdef", `apply TYPE_TEXT → ${paraText(p1)}`);
assert(validateParPrPreserved(p0, p1), "parPr preserved");
assert(validateCharPrPreserved(p0, p1), "charPr preserved");
// inverse 적용으로 원본 복원 (in-memory test: 직접 inverse forward 적용)
let inverseCmd = { ...cmd, forward: cmd.inverse, inverse: cmd.forward };
let p1back = applyCommandToParagraph(p1, inverseCmd);
assert(paraText(p1back) === "abcdef", `inverse → ${paraText(p1back)}`);
checks.typeTextSingleRun = true;

// 2) TYPE_TEXT 빈 문자열 → null
const noopCmd = makeTypeTextCommand({
  target, paragraph: p0, caretOffset: 1, insertText: "",
  sourceDocumentHash: hash,
});
assert(noopCmd === null, "empty insert → null");
checks.typeTextEmptyNull = true;

// 3) REPLACE_TEXT_RANGE 단일 run 안 (offset 0..1, "ab" → "AB")
cmd = makeReplaceTextRangeCommand({
  target, paragraph: p0, rangeAnchor: 0, rangeFocus: 1,
  afterText: "AB", sourceDocumentHash: hash,
});
assert(cmd.expectedBefore === "a", `expectedBefore=${cmd.expectedBefore}`);
let p2 = applyCommandToParagraph(p0, cmd);
assert(paraText(p2) === "ABbcdef", `REPLACE in-run → ${paraText(p2)}`);
assert(validateCharPrPreserved(p0, p2));
checks.replaceInRun = true;

// 4) REPLACE multi-run cross with default ANCHOR_CHARPR
cmd = makeReplaceTextRangeCommand({
  target, paragraph: p0, rangeAnchor: 1, rangeFocus: 5,
  afterText: "ZZ", sourceDocumentHash: hash,
});
let p3 = applyCommandToParagraph(p0, cmd);
// "abcdef"[1:5] = "bcde" 제거 후 "ZZ" 삽입 → "a" + "ZZ" + "f"
assert(paraText(p3) === "aZZf", `multi-run REPLACE → ${paraText(p3)}`);
assert(validateCharPrPreserved(p0, p3),
  "multi REPLACE preserved subset");
checks.replaceMultiRunAnchor = true;

// 5) REPLACE multi-run (anchor in A-run, focus in B-run) with
//    REQUIRES_REVIEW → throws. range [1, 3) anchor=run0(A) focus=run1(B)
let threw = false;
try {
  makeReplaceTextRangeCommand({
    target, paragraph: p0, rangeAnchor: 1, rangeFocus: 3,
    afterText: "ZZ", sourceDocumentHash: hash,
    policy: POLICY_REQUIRES_REVIEW,
  });
} catch (e) { threw = e.message.includes(REASON_REQUIRES_REVIEW); }
assert(threw, "REQUIRES_REVIEW throws");
checks.requiresReviewBlocked = true;

// 6) DELETE_TEXT_RANGE 단일 run 안 (offset 2..4, "cd" 제거)
cmd = makeDeleteTextRangeCommand({
  target, paragraph: p0, rangeAnchor: 2, rangeFocus: 4,
  sourceDocumentHash: hash,
});
assert(cmd.expectedBefore === "cd", "delete expectedBefore");
assert(cmd.inverse.kind === "REPLACE_TEXT_RANGE", "delete inverse=REPLACE");
let p4 = applyCommandToParagraph(p0, cmd);
assert(paraText(p4) === "abef", `DELETE → ${paraText(p4)}`);
// inverse 복원
let invDel = { ...cmd, forward: cmd.inverse, inverse: cmd.forward };
let p4back = applyCommandToParagraph(p4, invDel);
assert(paraText(p4back) === "abcdef", `delete inverse → ${paraText(p4back)}`);
checks.deleteRange = true;

// 7) split_run 단일
const sr = splitRun(p0, "par_p1_run1", 1);  // "cd" → "c"|"d"
assert(sr.info !== null);
assert(sr.p.runs.length === 4);
assert(sr.p.runs[1].text === "c" && sr.p.runs[2].text === "d");
assert(sr.p.runs[1].charPrIDRef === "B"
  && sr.p.runs[2].charPrIDRef === "B");
checks.splitRun = true;

// 8) merge_runs — same charPr 인접
const fusable = {
  paragraphId: "par_p1", parPrIDRef: "P1",
  runs: [
    { runId: "par_p1_run0", text: "ab", charPrIDRef: "A" },
    { runId: "par_p1_run1", text: "cd", charPrIDRef: "A" },
  ],
};
const merged = mergeRuns(fusable, "par_p1_run0", "par_p1_run1");
assert(merged.runs.length === 1);
assert(merged.runs[0].text === "abcd");
checks.mergeSameCharPr = true;

// 9) merge mismatch — different charPr
threw = false;
try {
  mergeRuns(p0, "par_p1_run0", "par_p1_run1");
} catch (e) { threw = e.message.includes(REASON_MERGE_CHARPR_MISMATCH); }
assert(threw, "merge mismatch reject");
checks.mergeMismatchReject = true;

// 10) normalizeParagraph — 빈 run 제거 + 인접 merge
const ugly = {
  paragraphId: "par_p1", parPrIDRef: "P1",
  runs: [
    { runId: "par_p1_run0", text: "a", charPrIDRef: "A" },
    { runId: "par_p1_run1", text: "", charPrIDRef: "B" },
    { runId: "par_p1_run2", text: "b", charPrIDRef: "A" },
    { runId: "par_p1_run3", text: "c", charPrIDRef: "A" },
  ],
};
const norm = normalizeParagraph(ugly);
// 빈 run(B) 제거 후 a/b/c 모두 charPr A 라 인접 merge → 단일 run "abc"
assert(norm.runs.length === 1, `norm runs=${norm.runs.length}`);
assert(norm.runs[0].text === "abc" && norm.runs[0].charPrIDRef === "A");
checks.normalizeMergeAdjacent = true;

// 11) normalizeParagraph 빈 paragraph → 빈 run 1개 유지
const emptyP = {
  paragraphId: "par_p1", parPrIDRef: "P1",
  runs: [{ runId: "par_p1_run0", text: "", charPrIDRef: "A" }],
};
const ne = normalizeParagraph(emptyP);
assert(ne.runs.length === 1 && ne.runs[0].text === "",
  "empty para keeps single empty run");
checks.emptyParaKept = true;

// 12) validateExpectedBefore mismatch
const mismatch = makeReplaceTextRangeCommand({
  target, paragraph: p0, rangeAnchor: 0, rangeFocus: 1,
  afterText: "Z", sourceDocumentHash: hash,
});
// paragraph 가 바뀐 상태에서는 expectedBefore 일치 안 함
const mutated = { ...p0,
  runs: [{ runId: "par_p1_run0", text: "X", charPrIDRef: "A" },
                ...p0.runs.slice(1)] };
assert(!validateExpectedBefore(mismatch, mutated),
  "validateExpectedBefore catches mismatch");
checks.expectedBeforeMismatch = true;

// 13) containerScope propagation — cell scope on target → command target /
//      forward / inverse 모두에 containerScope 동일하게 전사.
const cellScope = {
  kind: "cell", tableIndex: 0, rowIndex: 1, colIndex: 2,
  paragraphIndex: 0, runIndex: 0,
};
const cellTarget = {
  paragraphId: "par_p1", containerKind: "cell",
  containerId: "cell_t0_r1_c2", sourceSha256: "abc",
  containerScope: cellScope,
};
const cellCmd = makeTypeTextCommand({
  target: cellTarget, paragraph: p0, caretOffset: 0, insertText: "X",
  sourceDocumentHash: hash,
});
assert(cellCmd && cellCmd.target.containerScope &&
  cellCmd.target.containerScope.kind === "cell",
  "command.target.containerScope.kind == cell");
assert(cellCmd.forward.containerScope === cellTarget.containerScope,
  "forward.containerScope === target.containerScope");
assert(cellCmd.inverse.containerScope === cellTarget.containerScope,
  "inverse.containerScope === target.containerScope");
checks.containerScopePropagation = true;

// 14) REPLACE / DELETE 도 forward/inverse 에 containerScope 전사
const cellReplace = makeReplaceTextRangeCommand({
  target: cellTarget, paragraph: p0, rangeAnchor: 0, rangeFocus: 1,
  afterText: "Q", sourceDocumentHash: hash,
});
assert(cellReplace.forward.containerScope === cellScope);
assert(cellReplace.inverse.containerScope === cellScope);
const cellDelete = makeDeleteTextRangeCommand({
  target: cellTarget, paragraph: p0, rangeAnchor: 0, rangeFocus: 1,
  sourceDocumentHash: hash,
});
assert(cellDelete.forward.containerScope === cellScope);
assert(cellDelete.inverse.containerScope === cellScope);
checks.containerScopePropagationReplaceDelete = true;

// 15) block containerScope 도 command 생성 PASS
const blockScope = { kind: "block", sectionIndex: 0, blockIndex: 0,
                                          paragraphIndex: 0 };
const blockTarget = {
  paragraphId: "par_p1", containerKind: "block",
  containerId: "par_p1", sourceSha256: "abc",
  containerScope: blockScope,
};
const blockCmd = makeTypeTextCommand({
  target: blockTarget, paragraph: p0, caretOffset: 0, insertText: "Y",
  sourceDocumentHash: hash,
});
assert(blockCmd && blockCmd.target.containerScope.kind === "block",
  "block scope command created");
assert(blockCmd.forward.containerScope === blockScope);
checks.blockContainerScopeAccepted = true;

// 16) state 레벨: containerScope 없는 paragraph 에서 TYPE_TEXT 시도 →
//       REQUIRES_REVIEW_NO_CONTAINER_SCOPE 차단
{
  const docNoScope = { sourceDocumentHash: "h0",
                                          sourceRef: { sha256: "h0" } };
  const paragraphsNoScope = [{
    paragraphId: "par_x1", parPrIDRef: "P1",
    runs: [{ runId: "par_x1_run0", text: "ab", charPrIDRef: "A" }],
    // containerScope 없음 (의도적)
  }];
  let st = makeParagraphEditorState(docNoScope, paragraphsNoScope);
  st = selectParagraph(st, "par_x1");
  st = setCaret(st, "par_x1", 1);
  const tr = typeTextAtCaret(st, "Z");
  assert(tr.command === null,
    "no command when containerScope missing");
  assert(tr.reason === "REQUIRES_REVIEW_NO_CONTAINER_SCOPE",
    `reason=${tr.reason}`);
  checks.requiresReviewWhenNoContainerScope = true;
}

// 17) state 레벨: containerScope 있는 paragraph 면 정상 발행
{
  const docWithScope = { sourceDocumentHash: "h1",
                                              sourceRef: { sha256: "h1" } };
  const paragraphsWithScope = [{
    paragraphId: "par_y1", parPrIDRef: "P1",
    runs: [{ runId: "par_y1_run0", text: "ab", charPrIDRef: "A" }],
    containerScope: { kind: "cell", tableIndex: 0, rowIndex: 0,
                                      colIndex: 0, paragraphIndex: 0, runIndex: 0 },
  }];
  let st2 = makeParagraphEditorState(docWithScope, paragraphsWithScope);
  st2 = selectParagraph(st2, "par_y1");
  st2 = setCaret(st2, "par_y1", 1);
  const tr2 = typeTextAtCaret(st2, "Z");
  assert(tr2.command !== null,
    "command created with containerScope");
  assert(tr2.command.target.containerKind === "cell",
    `containerKind from scope: ${tr2.command.target.containerKind}`);
  assert(tr2.command.target.containerScope.kind === "cell");
  assert(tr2.command.forward.containerScope.kind === "cell");
  checks.stateLevelContainerScopeWired = true;
}

console.log(JSON.stringify({
  task: "WEB-OFFICE-PARA-EDIT-MODEL-01",
  checks, verdict: "PASS",
}));
