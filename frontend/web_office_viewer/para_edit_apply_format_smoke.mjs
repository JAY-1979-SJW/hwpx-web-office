#!/usr/bin/env node
/* WEB-OFFICE-PARA-EDIT-APPLYFORMAT-TOOLBAR-COMMAND-01 — node smoke.
 *
 * applyFormatToSelection 의 정책/회로/commandLog 적재를 자체 검증한다.
 * backend writer 호출 0건 (browser side state machine 만 호출).
 */
import {
  makeParagraphEditorState, selectParagraph, setRange, setCaret,
  applyFormatToSelection,
  startComposition, cancelComposition,
  undo, redo, buildSaveDryRunPayload,
} from "./para_edit_state.mjs";

const result = { task: "WEB-OFFICE-PARA-EDIT-APPLYFORMAT-"
                                  + "TOOLBAR-COMMAND-01",
                          checks: {} };

function rec(name, ok, extra) {
  result.checks[name] = { ok, ...(extra || {}) };
  if (!ok) {
    result.verdict = "FAIL";
    result.failedAt = name;
    console.log(JSON.stringify(result));
    process.exit(1);
  }
}

const SCOPE = { kind: "cell", tableIndex: 0, rowIndex: 0,
                          colIndex: 0, paragraphIndex: 0, runIndex: 0 };
const paragraphs = [{
  paragraphId: "par_x", parPrIDRef: "P1",
  containerScope: SCOPE,
  runs: [
    { runId: "par_x_run0", text: "abc", charPrIDRef: "10" },
    { runId: "par_x_run1", text: "DEF", charPrIDRef: "20" },
    { runId: "par_x_run2", text: "ghi", charPrIDRef: "10" },
  ],
}];
const doc = { sourceDocumentHash: "sha-af",
                        sourceRef: { sha256: "sha-af" } };
const charPrDefs = {
  "10": { charPrId: "10", fontName: "굴림", bold: false },
  "20": { charPrId: "20", fontName: "굴림", bold: true },
  "30": { charPrId: "30", fontName: "굴림", italic: true },
};

let s = makeParagraphEditorState(doc, paragraphs);

// 1. 선택 없음 → reject
let r = applyFormatToSelection(s, "20", charPrDefs);
rec("noActiveParagraphReject",
        r.command === null && r.reason === "NO_ACTIVE_PARAGRAPH");

// 2. CARET 만 있고 TEXT_RANGE 아님 → reject
s = selectParagraph(s, "par_x");
s = setCaret(s, "par_x", 1);
r = applyFormatToSelection(s, "20", charPrDefs);
rec("noTextRangeReject",
        r.command === null && r.reason === "NO_TEXT_RANGE");

// 3. empty range (anchor == focus) → setRange 가 caret 로 강등 → reject
s = setRange(s, "par_x", 2, 2);
r = applyFormatToSelection(s, "20", charPrDefs);
rec("emptyRangeReject", r.command === null
        && (r.reason === "EMPTY_RANGE"
              || r.reason === "NO_TEXT_RANGE"));

// 4. valid TEXT_RANGE + valid target → command 생성
s = setRange(s, "par_x", 0, 5);  // "abcDE" cross-run
const logLen0 = s.commandLog.length;
r = applyFormatToSelection(s, "30", charPrDefs);
rec("validSelectionCommandCreated", r.command !== null
        && r.reason === "OK");
rec("commandTypeApplyFormat",
        r.command?.commandType === "APPLY_FORMAT");
rec("forwardKindApplyFormat",
        r.command?.forward?.kind === "APPLY_FORMAT");
rec("expectedBeforeMatchesSlice",
        r.command?.expectedBefore === "abcDE");
rec("rangeStartEqualsAnchor",
        r.command?.forward?.rangeStart === 0
        && r.command?.forward?.rangeEnd === 5);
rec("targetCharPrPassedThrough",
        r.command?.forward?.targetCharPrIDRef === "30");
rec("inverseRestoreSegmentsPresent",
        Array.isArray(r.command?.inverse?.restoreSegments)
        && r.command.inverse.restoreSegments.length >= 2);
s = r.state;
rec("commandLogAppended",
        s.commandLog.length === logLen0 + 1);
rec("commandLogAppendOnly",
        s.commandLog[s.commandLog.length - 1] === r.command);
rec("undoStackUpdated",
        s.undoStack[s.undoStack.length - 1] === r.command);
rec("redoStackCleared", s.redoStack.length === 0);
rec("dirtyTrue", s.dirty === true);
// paragraph.text 무변경
const txtAfter = s.paragraphs[0].runs.map((r2) => r2.text).join("");
rec("paragraphTextUnchanged", txtAfter === "abcDEFghi");

// 5. target charPrId 가 defs 에 없으면 reject
s = setRange(s, "par_x", 0, 3);
r = applyFormatToSelection(s, "9999", charPrDefs);
rec("targetNotInDefsReject", r.command === null
        && r.reason === "TARGET_CHARPR_NOT_IN_HEADER");

// 6. target null → reject
r = applyFormatToSelection(s, null, charPrDefs);
rec("targetNullReject", r.command === null
        && r.reason === "TARGET_CHARPR_REQUIRED");

// 7. composition 중에는 reject
s = startComposition(s);
r = applyFormatToSelection(s, "20", charPrDefs);
rec("compositionLockReject", r.command === null
        && r.reason === "COMPOSITION_LOCKED");
s = cancelComposition(s);

// 8. defs 미전달 (undefined) → defs 체크 skip, 다른 정합 통과 시 OK
s = setRange(s, "par_x", 1, 4);
r = applyFormatToSelection(s, "20", undefined);
rec("defsOmittedNoCheck", r.command !== null && r.reason === "OK");
s = r.state;

// 9. undo / redo 정합
const logBeforeUndo = s.commandLog.length;
const ru = undo(s); s = ru.state;
rec("undoOk", ru.reason === "OK");
rec("undoCommandLogAppendOnly",
        s.commandLog.length === logBeforeUndo);
rec("undoRedoPending", s.redoStack.length === 1);
const rrd = redo(s); s = rrd.state;
rec("redoOk", rrd.reason === "OK");

// 10. save dry-run payload 포함
const payload = buildSaveDryRunPayload(s);
rec("saveDryRunIncludesApplyFormat",
        payload.status === "READY_FOR_SERVER_VALIDATION"
        && payload.commandLog.some(
            (c) => c.commandType === "APPLY_FORMAT"));

result.verdict = "PASS";
console.log(JSON.stringify(result));
