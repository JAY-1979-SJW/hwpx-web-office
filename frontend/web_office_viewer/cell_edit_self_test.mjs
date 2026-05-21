#!/usr/bin/env node
/* cell_edit_state + edit_command 자체 시나리오 검증.
 * 실패 시 비-0 종료. writer/apply 호출 없음.
 */
import {
  makeEditorState, selectCell, enterCellEdit, commitCellText,
  undo, redo, buildSaveDryRunPayload,
  MODE_CELL_SELECT, MODE_CELL_EDIT, MODE_READ_ONLY,
} from "./cell_edit_state.mjs";

function assert(cond, msg) {
  if (!cond) { console.error("ASSERT FAIL:", msg); process.exit(1); }
}

const sampleDoc = {
  sourceDocumentHash: "abc123",
  sourceRef: { sha256: "abc123" },
  tables: [{ tableId: "t_s0_000" }, { tableId: "t_s0_001" }],
  cells: [
    { cellId: "cell_t_s0_000_r0_c0", tableId: "t_s0_000",
        row: 0, col: 0, text: "라벨" },
    { cellId: "cell_t_s0_000_r0_c1", tableId: "t_s0_000",
        row: 0, col: 1, text: "기본값" },
    { cellId: "cell_t_s0_001_r2_c1", tableId: "t_s0_001",
        row: 2, col: 1, text: "" },
  ],
};

const checks = {};

// 1) selectCell
let s = makeEditorState(sampleDoc);
assert(s.editorMode === MODE_READ_ONLY, "init mode READ_ONLY");
assert(s.dirty === false, "init dirty=false");
s = selectCell(s, "cell_t_s0_000_r0_c1");
assert(s.activeCellId === "cell_t_s0_000_r0_c1", "selectCell active");
assert(s.editorMode === MODE_CELL_SELECT, "selectCell mode");
checks.selectCell = true;

// 2) enterCellEdit
s = enterCellEdit(s);
assert(s.editorMode === MODE_CELL_EDIT, "enterCellEdit mode");
checks.enterCellEdit = true;

// 3) commitCellText — 정상 변경
let r = commitCellText(s, "cell_t_s0_000_r0_c1", "신규값");
assert(r.command !== null, "command created");
assert(r.command.before === "기본값", "before captured");
assert(r.command.after === "신규값", "after captured");
assert(r.command.expectedBefore === "기본값", "expectedBefore set");
assert(r.command.sourceDocumentHash === "abc123", "sourceDocumentHash");
assert(r.command.forward.set_cells[0].value === "신규값", "forward plan");
assert(r.command.inverse.set_cells[0].value === "기본값", "inverse plan");
s = r.state;
assert(s.dirty === true, "dirty after commit");
assert(s.undoStack.length === 1, "undoStack +1");
assert(s.commandLog.length === 1, "commandLog +1");
assert(s.documentModel.cells.find((c) =>
  c.cellId === "cell_t_s0_000_r0_c1").text === "신규값",
  "forward applied to model");
checks.commitChange = true;

// 4) commitCellText — 값 동일이면 command 미생성
const r2 = commitCellText(s, "cell_t_s0_000_r0_c1", "신규값");
assert(r2.command === null, "no command when value unchanged");
assert(r2.reason === "NO_CHANGE", "reason=NO_CHANGE");
s = r2.state;
assert(s.undoStack.length === 1, "undoStack unchanged");
assert(s.commandLog.length === 1, "commandLog unchanged");
checks.noChangeNoCommand = true;

// 5) expectedBefore mismatch — 직접 makeSetCellTextCommand 로 인위 생성
import {
  makeSetCellTextCommand, applyForward,
} from "./edit_command.mjs";
const cmdMismatch = makeSetCellTextCommand({
  cellId: "cell_t_s0_000_r0_c1", tableIndex: 0,
  before: "이전값", after: "더새값",
  sourceDocumentHash: "abc123",
  expectedBefore: "절대일치하지않는값",
});
let threw = false;
try { applyForward("신규값", cmdMismatch); }
catch (e) { threw = e.message.includes("expectedBefore mismatch"); }
assert(threw, "applyForward throws on expectedBefore mismatch");
checks.expectedBeforeBlock = true;

// 6) undo
const beforeUndo = s.documentModel.cells.find((c) =>
  c.cellId === "cell_t_s0_000_r0_c1").text;
assert(beforeUndo === "신규값", "pre-undo text");
r = undo(s);
assert(r.reason === "OK", "undo OK");
s = r.state;
assert(s.documentModel.cells.find((c) =>
  c.cellId === "cell_t_s0_000_r0_c1").text === "기본값",
  "undo restored before");
assert(s.undoStack.length === 0, "undoStack empty");
assert(s.redoStack.length === 1, "redoStack +1");
assert(s.dirty === false, "dirty false after undoing all");
checks.undo = true;

// 7) redo
r = redo(s);
assert(r.reason === "OK", "redo OK");
s = r.state;
assert(s.documentModel.cells.find((c) =>
  c.cellId === "cell_t_s0_000_r0_c1").text === "신규값",
  "redo re-applied");
assert(s.undoStack.length === 1, "undoStack +1");
assert(s.redoStack.length === 0, "redoStack empty");
assert(s.dirty === true, "dirty true after redo");
checks.redo = true;

// 8) undo / empty
r = undo(s); s = r.state;          // 다시 비우기
r = undo(s);
assert(r.reason === "EMPTY_UNDO", "undo on empty stack");
checks.emptyUndo = true;

// 9) save dry-run 게이트 — empty commandLog 는 NOOP
const sFresh = makeEditorState(sampleDoc);
const noop = buildSaveDryRunPayload(sFresh);
assert(noop.status === "NOOP", "save noop on empty");
assert(noop.plan === null, "save plan null on empty");
checks.saveNoop = true;

// 10) save dry-run 게이트 — commandLog 있을 때 payload 형태
const payload = buildSaveDryRunPayload(s);
assert(payload.status === "READY_FOR_SERVER_VALIDATION",
  "save ready");
assert(payload.dryRun === true, "dryRun true");
assert(payload.sourceDocumentHash === "abc123", "hash propagated");
assert(payload.commandLog.length >= 1, "commandLog populated");
checks.savePayload = true;

// 11) commandLog append-only — undo 가 commandLog 를 줄이지 않는다
const lenBefore = s.commandLog.length;
r = undo(s); s = r.state;
assert(s.commandLog.length === lenBefore,
  "commandLog is append-only across undo");
checks.commandLogAppendOnly = true;

console.log(JSON.stringify({
  task: "WEB-OFFICE-CELL-EDIT-MVP-A-01",
  checks, verdict: "PASS",
}));
