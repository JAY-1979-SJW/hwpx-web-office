/* CELL-EDIT 편집기 상태기계 (browser side).
 * activeCellId / editorMode / undoStack / redoStack / commandLog / dirty.
 * writer / apply / save 본 실행은 일절 없다.
 */
import {
  makeSetCellTextCommand, applyForward, applyInverse,
  validateAgainstCurrent, STATUS_VALIDATED,
} from "./edit_command.mjs";

export const MODE_READ_ONLY = "READ_ONLY";
export const MODE_CELL_SELECT = "CELL_SELECT";
export const MODE_CELL_EDIT = "CELL_EDIT";

/* documentModel: WebOfficeDocumentModel.to_dict() 동등 객체 (cells 배열). */
export function makeEditorState(documentModel) {
  return {
    documentModel,
    sourceDocumentHash: documentModel.sourceDocumentHash
      || documentModel.sourceRef?.sha256,
    activeCellId: null,
    editorMode: MODE_READ_ONLY,
    undoStack: [],
    redoStack: [],
    commandLog: [],   // append-only — undo 는 별도 stack
    dirty: false,
  };
}

function _findCell(state, cellId) {
  return state.documentModel.cells.find((c) => c.cellId === cellId);
}

function _tableIndexOfCell(state, cell) {
  // tables 배열에서 tableId 매칭 → index
  return state.documentModel.tables.findIndex(
    (t) => t.tableId === cell.tableId);
}

export function selectCell(state, cellId) {
  const cell = _findCell(state, cellId);
  if (!cell) return state;
  return { ...state, activeCellId: cellId,
              editorMode: MODE_CELL_SELECT };
}

export function enterCellEdit(state) {
  if (!state.activeCellId) return state;
  return { ...state, editorMode: MODE_CELL_EDIT };
}

export function cancelCellEdit(state) {
  return { ...state, editorMode: state.activeCellId
              ? MODE_CELL_SELECT : MODE_READ_ONLY };
}

/* 셀 텍스트 확정. 값이 같으면 commandLog 변화 없음. */
export function commitCellText(state, cellId, newText) {
  const cell = _findCell(state, cellId);
  if (!cell) return { state, command: null,
                                reason: "TARGET_CELL_NOT_FOUND" };
  const before = cell.text ?? "";
  if (before === newText) {
    // 동일 — command 미생성 (시방서 요구)
    return { state: cancelCellEdit(state), command: null,
                  reason: "NO_CHANGE" };
  }
  const tableIndex = _tableIndexOfCell(state, cell);
  const cmd = makeSetCellTextCommand({
    cellId, tableIndex, before, after: newText,
    sourceDocumentHash: state.sourceDocumentHash,
    expectedBefore: before,
  });
  if (!cmd) return { state: cancelCellEdit(state), command: null,
                                  reason: "NO_CHANGE" };
  // expectedBefore 일치 확인 (현재 값 = before 이므로 일치)
  if (!validateAgainstCurrent(cmd, before)) {
    return { state, command: null,
                  reason: "EXPECTED_BEFORE_MISMATCH" };
  }
  // forward 적용 (in-memory)
  const nextDoc = {
    ...state.documentModel,
    cells: state.documentModel.cells.map((c) =>
      c.cellId === cellId
        ? { ...c, text: applyForward(c.text ?? "", cmd) }
        : c),
  };
  cmd.status = STATUS_VALIDATED;
  return {
    state: {
      ...state,
      documentModel: nextDoc,
      editorMode: MODE_CELL_SELECT,
      undoStack: [...state.undoStack, cmd],
      redoStack: [],     // 새 명령 발생 시 redo 비움
      commandLog: [...state.commandLog, cmd],
      dirty: true,
    },
    command: cmd,
    reason: "OK",
  };
}

export function undo(state) {
  if (state.undoStack.length === 0) {
    return { state, command: null, reason: "EMPTY_UNDO" };
  }
  const cmd = state.undoStack[state.undoStack.length - 1];
  const cell = _findCell(state, cmd.targetId);
  if (!cell) return { state, command: null,
                                reason: "TARGET_CELL_NOT_FOUND" };
  const next = applyInverse(cell.text ?? "", cmd);
  const nextDoc = {
    ...state.documentModel,
    cells: state.documentModel.cells.map((c) =>
      c.cellId === cmd.targetId ? { ...c, text: next } : c),
  };
  const newUndo = state.undoStack.slice(0, -1);
  return {
    state: {
      ...state,
      documentModel: nextDoc,
      undoStack: newUndo,
      redoStack: [...state.redoStack, cmd],
      dirty: newUndo.length > 0,
    },
    command: cmd, reason: "OK",
  };
}

export function redo(state) {
  if (state.redoStack.length === 0) {
    return { state, command: null, reason: "EMPTY_REDO" };
  }
  const cmd = state.redoStack[state.redoStack.length - 1];
  const cell = _findCell(state, cmd.targetId);
  if (!cell) return { state, command: null,
                                reason: "TARGET_CELL_NOT_FOUND" };
  const next = applyForward(cell.text ?? "", cmd);
  const nextDoc = {
    ...state.documentModel,
    cells: state.documentModel.cells.map((c) =>
      c.cellId === cmd.targetId ? { ...c, text: next } : c),
  };
  return {
    state: {
      ...state,
      documentModel: nextDoc,
      undoStack: [...state.undoStack, cmd],
      redoStack: state.redoStack.slice(0, -1),
      dirty: true,
    },
    command: cmd, reason: "OK",
  };
}

/* commandLog → 서버 전송용 dry-run 요청 payload. writer 호출 안 함. */
export function buildSaveDryRunPayload(state) {
  if (state.commandLog.length === 0) {
    return { status: "NOOP", reason: "commandLog empty",
                  dryRun: true, plan: null };
  }
  return {
    status: "READY_FOR_SERVER_VALIDATION",
    dryRun: true,
    sourceDocumentHash: state.sourceDocumentHash,
    commandLog: state.commandLog,
    // 서버가 cell_edit_plan.build_dry_run_edit_plan 으로 검증한다.
  };
}
