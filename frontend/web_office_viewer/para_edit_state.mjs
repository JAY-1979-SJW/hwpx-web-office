/* PARA-EDIT BROWSER 상태기계 — Phase 3 BROWSER-01.
 *
 * EditCommand v2 모델 (para_edit_command.mjs) 위에 selection /
 * caret / range / IME composition / undo/redo 를 얹는다.
 * writer / save / output 호출은 일절 없다.
 */
import {
  makeTypeTextCommand, makeReplaceTextRangeCommand,
  makeDeleteTextRangeCommand, makeApplyFormatCommand,
  applyCommandToParagraph,
  CT_TYPE_TEXT, CT_REPLACE_TEXT_RANGE, CT_DELETE_TEXT_RANGE,
  CT_APPLY_FORMAT, CT_PARA_INSERT, CT_PARA_DELETE,
  STATUS_VALIDATED,
  // WEB-OFFICE-PARA-EDIT-STRUCTURE-PARA-INSERT-01.
  makeParaInsertCommand, allocateNewParagraphId,
  applyParaInsertToParagraphs, applyParaDeleteToParagraphs,
  // WEB-OFFICE-PARA-EDIT-STRUCTURE-PARA-DELETE-01.
  makeParaDeleteCommand, applyParaDeleteForwardToParagraphs,
  // WEB-OFFICE-P3-RUN-SPLIT-MERGE-CHARPR-GUARD-01.
  validateRunCharPrIntegrity, REASON_CHARPR_MISSING_ON_RUN,
} from "./para_edit_command.mjs";

export const SEL_NONE = "NONE";
export const SEL_CARET = "CARET";
export const SEL_TEXT_RANGE = "TEXT_RANGE";
export const SEL_COMPOSITION = "COMPOSITION";

function _uuid() {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
  });
}

function _paraText(p) { return p.runs.map((r) => r.text).join(""); }

function _findPara(state, paragraphId) {
  return state.paragraphs.find((p) => p.paragraphId === paragraphId);
}

// WEB-OFFICE-PARA-EDIT-STRUCTURE-SCOPE-BOUNDARY-REJECT-01
// body paragraph (kind=="block") 외 scope에서 PARA_INSERT/DELETE를 명시적으로 reject.
function _scopeBoundaryRejectReason(scope, cmdType) {
  const kind = scope?.kind;
  if (!kind || kind === "block") return null;
  if (kind === "cell")     return cmdType === "INSERT"
    ? "PARA_INSERT_CELL_SCOPE_NOT_SUPPORTED"
    : "PARA_DELETE_CELL_SCOPE_NOT_SUPPORTED";
  if (kind === "header")   return "HEADER_SCOPE_NOT_SUPPORTED";
  if (kind === "footer")   return "FOOTER_SCOPE_NOT_SUPPORTED";
  if (kind === "footnote") return "FOOTNOTE_SCOPE_NOT_SUPPORTED";
  if (kind === "endnote")  return "ENDNOTE_SCOPE_NOT_SUPPORTED";
  if (kind === "caption")  return "CAPTION_SCOPE_NOT_SUPPORTED";
  return "BODY_SCOPE_ONLY_SUPPORTED";
}

function _findRun(paragraph, runId) {
  return paragraph.runs.find((r) => r.runId === runId);
}

function _replaceParagraph(state, paragraphId, newPara) {
  return {
    ...state,
    paragraphs: state.paragraphs.map((p) =>
      p.paragraphId === paragraphId ? newPara : p),
  };
}

/* documentModel 은 RO-VIEW WebOfficeDocumentModel 동등 객체 (paragraphs
 * 배열 포함). state 는 불변 갱신 패턴. */
export function makeParagraphEditorState(documentModel, paragraphs) {
  return {
    documentModel,
    paragraphs: paragraphs.map((p) => ({ ...p, runs: [...p.runs] })),
    sourceDocumentHash: documentModel.sourceDocumentHash
      || documentModel.sourceRef?.sha256,
    activeParagraphId: null,
    activeRunId: null,
    caretOffset: 0,
    rangeAnchor: null,
    rangeFocus: null,
    selectionMode: SEL_NONE,
    composition: { active: false, startCaret: null,
                              accumulatedText: "" },
    undoStack: [],
    redoStack: [],
    commandLog: [],   // append-only
    dirty: false,
  };
}

export function selectParagraph(state, paragraphId) {
  const p = _findPara(state, paragraphId);
  if (!p) return state;
  return {
    ...state,
    activeParagraphId: paragraphId,
    activeRunId: p.runs[0]?.runId ?? null,
    caretOffset: 0,
    rangeAnchor: null, rangeFocus: null,
    selectionMode: SEL_CARET,
  };
}

export function setCaret(state, paragraphId, caretOffset) {
  const p = _findPara(state, paragraphId);
  if (!p) return state;
  const len = _paraText(p).length;
  const off = Math.max(0, Math.min(caretOffset, len));
  return {
    ...state,
    activeParagraphId: paragraphId,
    caretOffset: off,
    rangeAnchor: null, rangeFocus: null,
    selectionMode: SEL_CARET,
  };
}

export function setRange(state, paragraphId, anchorOffset, focusOffset) {
  const p = _findPara(state, paragraphId);
  if (!p) return state;
  const len = _paraText(p).length;
  const a = Math.max(0, Math.min(anchorOffset, len));
  const b = Math.max(0, Math.min(focusOffset, len));
  if (a === b) {
    return setCaret(state, paragraphId, a);
  }
  return {
    ...state,
    activeParagraphId: paragraphId,
    rangeAnchor: a, rangeFocus: b,
    caretOffset: b,
    selectionMode: SEL_TEXT_RANGE,
  };
}

export function clearSelection(state) {
  return {
    ...state,
    activeParagraphId: null, activeRunId: null,
    caretOffset: 0,
    rangeAnchor: null, rangeFocus: null,
    selectionMode: SEL_NONE,
  };
}

function _buildTarget(state, paragraphId) {
  const p = _findPara(state, paragraphId);
  const scope = p?.containerScope ?? null;
  const containerKind = scope?.kind ?? "block";
  let containerId = paragraphId;
  let cellCoord = null;
  if (scope?.kind === "cell") {
    containerId = `cell_t${scope.tableIndex}_r${scope.rowIndex}_c${scope.colIndex}`;
    cellCoord = { table: scope.tableIndex, row: scope.rowIndex,
                              col: scope.colIndex };
  }
  return {
    paragraphId,
    containerKind,
    containerId,
    containerScope: scope,
    cellCoord,
    sourceSha256: state.sourceDocumentHash,
  };
}

// WEB-OFFICE-P3-RUN-SPLIT-MERGE-CHARPR-GUARD-01
function _charPrGuard(paragraph) {
  if (!paragraph) return null;
  const check = validateRunCharPrIntegrity(paragraph);
  return check.valid ? null : REASON_CHARPR_MISSING_ON_RUN;
}

function _scopeMissing(state) {
  if (!state.activeParagraphId) return false;
  const p = _findPara(state, state.activeParagraphId);
  return !p || !p.containerScope;
}

function _appendCommand(state, cmd, nextPara) {
  cmd.status = STATUS_VALIDATED;
  return {
    ...(_replaceParagraph(state, cmd.target.paragraphId, nextPara)),
    undoStack: [...state.undoStack, cmd],
    redoStack: [],   // 새 명령 발생 시 redo 비움
    commandLog: [...state.commandLog, cmd],
    dirty: true,
  };
}

/* WEB-OFFICE-PARA-EDIT-STRUCTURE-PARA-INSERT-01.
 * PARA_INSERT 처럼 paragraphs 배열 자체가 변하는 command 용 append. */
function _appendCommandWithParas(state, cmd, nextParas) {
  cmd.status = STATUS_VALIDATED;
  return {
    ...state,
    paragraphs: nextParas,
    undoStack: [...state.undoStack, cmd],
    redoStack: [],
    commandLog: [...state.commandLog, cmd],
    dirty: true,
  };
}

/* caret 또는 range 모드에서 텍스트 삽입.
 * - selectionMode == TEXT_RANGE: REPLACE_TEXT_RANGE
 * - selectionMode == CARET: TYPE_TEXT
 * - composition.active: 누적만, command 미생성
 */
export function typeTextAtCaret(state, text) {
  if (!state.activeParagraphId) {
    return { state, command: null, reason: "NO_ACTIVE_PARAGRAPH" };
  }
  if (state.composition.active) {
    // composition 중에는 commandLog 잠금
    return {
      state: {
        ...state,
        composition: {
          ...state.composition,
          accumulatedText:
            (state.composition.accumulatedText ?? "") + text,
        },
      },
      command: null,
      reason: "COMPOSITION_LOCKED",
    };
  }
  if (text === "") {
    return { state, command: null, reason: "EMPTY_TEXT" };
  }
  if (_scopeMissing(state)) {
    return { state, command: null,
                  reason: "REQUIRES_REVIEW_NO_CONTAINER_SCOPE" };
  }
  const p = _findPara(state, state.activeParagraphId);
  const _cprg = _charPrGuard(p);
  if (_cprg) return { state, command: null, reason: _cprg };

  if (state.selectionMode === SEL_TEXT_RANGE
      && state.rangeAnchor !== null && state.rangeFocus !== null
      && state.rangeAnchor !== state.rangeFocus) {
    const cmd = makeReplaceTextRangeCommand({
      target: _buildTarget(state, p.paragraphId),
      paragraph: p,
      rangeAnchor: state.rangeAnchor,
      rangeFocus: state.rangeFocus,
      afterText: text,
      sourceDocumentHash: state.sourceDocumentHash,
    });
    const nextPara = applyCommandToParagraph(p, cmd);
    const a = Math.min(state.rangeAnchor, state.rangeFocus);
    return {
      state: {
        ..._appendCommand(state, cmd, nextPara),
        rangeAnchor: null, rangeFocus: null,
        caretOffset: a + text.length,
        selectionMode: SEL_CARET,
      },
      command: cmd, reason: "OK",
    };
  }

  // CARET 모드 → TYPE_TEXT
  const cmd = makeTypeTextCommand({
    target: _buildTarget(state, p.paragraphId),
    paragraph: p,
    caretOffset: state.caretOffset,
    insertText: text,
    sourceDocumentHash: state.sourceDocumentHash,
  });
  if (!cmd) {
    return { state, command: null, reason: "EMPTY_TEXT" };
  }
  const nextPara = applyCommandToParagraph(p, cmd);
  return {
    state: {
      ..._appendCommand(state, cmd, nextPara),
      caretOffset: state.caretOffset + text.length,
    },
    command: cmd, reason: "OK",
  };
}

/* WEB-OFFICE-PARA-EDIT-APPLYFORMAT-TOOLBAR-COMMAND-01.
 * 현재 selection range 의 run charPrIDRef 를 targetCharPrIDRef 로 교체
 * 하는 APPLY_FORMAT command 발급. backend writer 는 호출하지 않으며,
 * commandLog append-only 규칙을 그대로 따른다. charPrDefs 가 주어지면
 * targetCharPrIDRef ∈ defs 강제. */
export function applyFormatToSelection(
  state, targetCharPrIDRef, charPrDefs,
) {
  if (!state.activeParagraphId) {
    return { state, command: null, reason: "NO_ACTIVE_PARAGRAPH" };
  }
  if (state.composition?.active) {
    return { state, command: null, reason: "COMPOSITION_LOCKED" };
  }
  if (state.selectionMode !== SEL_TEXT_RANGE
      || state.rangeAnchor === null || state.rangeFocus === null) {
    return { state, command: null, reason: "NO_TEXT_RANGE" };
  }
  if (state.rangeAnchor === state.rangeFocus) {
    return { state, command: null, reason: "EMPTY_RANGE" };
  }
  if (_scopeMissing(state)) {
    return { state, command: null,
                  reason: "REQUIRES_REVIEW_NO_CONTAINER_SCOPE" };
  }
  if (targetCharPrIDRef === null
      || targetCharPrIDRef === undefined
      || String(targetCharPrIDRef) === "") {
    return { state, command: null,
                  reason: "TARGET_CHARPR_REQUIRED" };
  }
  const tgt = String(targetCharPrIDRef);
  if (charPrDefs && !Object.prototype.hasOwnProperty.call(
        charPrDefs, tgt)) {
    return { state, command: null,
                  reason: "TARGET_CHARPR_NOT_IN_HEADER" };
  }
  const p = _findPara(state, state.activeParagraphId);
  const _cprg = _charPrGuard(p);
  if (_cprg) return { state, command: null, reason: _cprg };
  const cmd = makeApplyFormatCommand({
    target: _buildTarget(state, p.paragraphId),
    paragraph: p,
    rangeAnchor: state.rangeAnchor,
    rangeFocus: state.rangeFocus,
    targetCharPrIDRef: tgt,
    sourceDocumentHash: state.sourceDocumentHash,
  });
  if (!cmd) {
    return { state, command: null, reason: "EMPTY_RANGE" };
  }
  const nextPara = applyCommandToParagraph(p, cmd);
  return {
    state: _appendCommand(state, cmd, nextPara),
    command: cmd, reason: "OK",
  };
}


/* TEXT_RANGE 모드에서 삭제 (REPLACE with after=""). */
export function deleteRange(state) {
  if (state.selectionMode !== SEL_TEXT_RANGE) {
    return { state, command: null, reason: "NOT_TEXT_RANGE" };
  }
  if (_scopeMissing(state)) {
    return { state, command: null,
                  reason: "REQUIRES_REVIEW_NO_CONTAINER_SCOPE" };
  }
  const p = _findPara(state, state.activeParagraphId);
  const _cprg = _charPrGuard(p);
  if (_cprg) return { state, command: null, reason: _cprg };
  const cmd = makeDeleteTextRangeCommand({
    target: _buildTarget(state, p.paragraphId),
    paragraph: p,
    rangeAnchor: state.rangeAnchor,
    rangeFocus: state.rangeFocus,
    sourceDocumentHash: state.sourceDocumentHash,
  });
  const nextPara = applyCommandToParagraph(p, cmd);
  const a = Math.min(state.rangeAnchor, state.rangeFocus);
  return {
    state: {
      ..._appendCommand(state, cmd, nextPara),
      rangeAnchor: null, rangeFocus: null,
      caretOffset: a,
      selectionMode: SEL_CARET,
    },
    command: cmd, reason: "OK",
  };
}

/* caret 직전 한 글자 삭제 (Backspace).
 * caret==0 이면 이전 paragraph 와 병합 시도 (body scope 한정). */
export function deleteBackward(state) {
  if (state.selectionMode === SEL_TEXT_RANGE) {
    return deleteRange(state);
  }
  if (state.composition.active) {
    return { state, command: null, reason: "COMPOSITION_LOCKED" };
  }
  if (!state.activeParagraphId) {
    return { state, command: null, reason: "CARET_AT_START" };
  }
  // caret==0 → paragraph merge 시도
  if (state.caretOffset === 0) {
    return mergeParagraphWithPrevious(state);
  }
  if (_scopeMissing(state)) {
    return { state, command: null,
                  reason: "REQUIRES_REVIEW_NO_CONTAINER_SCOPE" };
  }
  const p = _findPara(state, state.activeParagraphId);
  const _cprg = _charPrGuard(p);
  if (_cprg) return { state, command: null, reason: _cprg };
  const cmd = makeDeleteTextRangeCommand({
    target: _buildTarget(state, p.paragraphId),
    paragraph: p,
    rangeAnchor: state.caretOffset - 1,
    rangeFocus: state.caretOffset,
    sourceDocumentHash: state.sourceDocumentHash,
  });
  const nextPara = applyCommandToParagraph(p, cmd);
  return {
    state: {
      ..._appendCommand(state, cmd, nextPara),
      caretOffset: state.caretOffset - 1,
    },
    command: cmd, reason: "OK",
  };
}

/* IME composition 라이프사이클. composition 중에는 commandLog 잠금. */

export function startComposition(state) {
  if (!state.activeParagraphId) {
    return { ...state };
  }
  return {
    ...state,
    selectionMode: SEL_COMPOSITION,
    composition: {
      active: true,
      startCaret: state.caretOffset,
      accumulatedText: "",
    },
  };
}

export function updateComposition(state, intermediateText) {
  if (!state.composition.active) return state;
  return {
    ...state,
    composition: {
      ...state.composition,
      accumulatedText: intermediateText,
    },
  };
}

/* compositionend 시 finalText 가 빈 문자열이면 cancel 과 동등 (no command). */
export function endComposition(state, finalText) {
  if (!state.composition.active) {
    return { state, command: null, reason: "NOT_IN_COMPOSITION" };
  }
  const startCaret = state.composition.startCaret;
  // composition 해제
  const released = {
    ...state,
    selectionMode: SEL_CARET,
    composition: { active: false, startCaret: null,
                              accumulatedText: "" },
    caretOffset: startCaret,
  };
  if (!finalText) {
    return { state: released, command: null, reason: "CANCELLED" };
  }
  // 단일 TYPE_TEXT command 생성 — caret 위치를 startCaret 로 복원 후
  // typeTextAtCaret 재사용
  return typeTextAtCaret(released, finalText);
}

export function cancelComposition(state) {
  if (!state.composition.active) {
    return { ...state };
  }
  return {
    ...state,
    selectionMode: SEL_CARET,
    composition: { active: false, startCaret: null,
                              accumulatedText: "" },
    caretOffset: state.composition.startCaret ?? state.caretOffset,
  };
}

/* undo / redo */

function _applyInverseToParagraph(p, cmd) {
  return applyCommandToParagraph(p, {
    ...cmd, forward: cmd.inverse, inverse: cmd.forward,
  });
}

export function undo(state) {
  if (state.undoStack.length === 0) {
    return { state, command: null, reason: "EMPTY_UNDO" };
  }
  const cmd = state.undoStack[state.undoStack.length - 1];
  const newUndo = state.undoStack.slice(0, -1);
  // PARA_INSERT undo: paragraphs 배열 축소 (PARA_INSERT inverse = PARA_DELETE).
  if (cmd.commandType === CT_PARA_INSERT) {
    const reverted = applyParaDeleteToParagraphs(state.paragraphs, cmd);
    return {
      state: {
        ...state,
        paragraphs: reverted,
        activeParagraphId: cmd.target.paragraphId,
        caretOffset: cmd.forward.caretOffset,
        rangeAnchor: null, rangeFocus: null,
        selectionMode: SEL_CARET,
        undoStack: newUndo,
        redoStack: [...state.redoStack, cmd],
        dirty: newUndo.length > 0,
      },
      command: cmd, reason: "OK",
    };
  }
  // WEB-OFFICE-PARA-EDIT-STRUCTURE-PARA-DELETE-01:
  // PARA_DELETE undo: inverse = PARA_INSERT (re-split prevParagraph at mergeOffset).
  if (cmd.commandType === CT_PARA_DELETE) {
    // inverse 정보를 forward 로 래핑한 synthetic command 로 applyParaInsert 호출.
    const syntheticInsertCmd = { ...cmd, forward: cmd.inverse };
    const reverted = applyParaInsertToParagraphs(
      state.paragraphs, syntheticInsertCmd);
    return {
      state: {
        ...state,
        paragraphs: reverted,
        activeParagraphId: cmd.forward.paragraphId,  // cur para (restored)
        caretOffset: 0,
        rangeAnchor: null, rangeFocus: null,
        selectionMode: SEL_CARET,
        undoStack: newUndo,
        redoStack: [...state.redoStack, cmd],
        dirty: newUndo.length > 0,
      },
      command: cmd, reason: "OK",
    };
  }
  const p = _findPara(state, cmd.target.paragraphId);
  if (!p) return { state, command: null,
                                reason: "TARGET_PARAGRAPH_NOT_FOUND" };
  const reverted = _applyInverseToParagraph(p, cmd);
  return {
    state: {
      ..._replaceParagraph(state, p.paragraphId, reverted),
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
  if (cmd.commandType === CT_PARA_INSERT) {
    const nextParas = applyParaInsertToParagraphs(state.paragraphs, cmd);
    return {
      state: {
        ...state,
        paragraphs: nextParas,
        activeParagraphId: cmd.forward.newParagraphId,
        caretOffset: 0,
        rangeAnchor: null, rangeFocus: null,
        selectionMode: SEL_CARET,
        undoStack: [...state.undoStack, cmd],
        redoStack: state.redoStack.slice(0, -1),
        dirty: true,
      },
      command: cmd, reason: "OK",
    };
  }
  // WEB-OFFICE-PARA-EDIT-STRUCTURE-PARA-DELETE-01: PARA_DELETE redo.
  if (cmd.commandType === CT_PARA_DELETE) {
    const nextParas = applyParaDeleteForwardToParagraphs(
      state.paragraphs, cmd);
    return {
      state: {
        ...state,
        paragraphs: nextParas,
        activeParagraphId: cmd.forward.prevParagraphId,
        caretOffset: cmd.forward.mergeOffset,
        rangeAnchor: null, rangeFocus: null,
        selectionMode: SEL_CARET,
        undoStack: [...state.undoStack, cmd],
        redoStack: state.redoStack.slice(0, -1),
        dirty: true,
      },
      command: cmd, reason: "OK",
    };
  }
  const p = _findPara(state, cmd.target.paragraphId);
  if (!p) return { state, command: null,
                                reason: "TARGET_PARAGRAPH_NOT_FOUND" };
  const next = applyCommandToParagraph(p, cmd);
  return {
    state: {
      ..._replaceParagraph(state, p.paragraphId, next),
      undoStack: [...state.undoStack, cmd],
      redoStack: state.redoStack.slice(0, -1),
      dirty: true,
    },
    command: cmd, reason: "OK",
  };
}

/* 서버로 보낼 dry-run payload (writer 미접촉). */
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
  };
}


/* ── WEB-OFFICE-PARA-EDIT-STRUCTURE-PARA-INSERT-01 ─────────────── */

/* Enter 키 → caret 위치에서 active paragraph 를 두 paragraph 로 분할.
 *
 * - body scope (containerScope.kind="block") 한정 — cell scope 는
 *   PARA_INSERT_CELL_SCOPE_NOT_SUPPORTED reject.
 * - SEL_TEXT_RANGE 인 경우 (multi-paragraph 가능성) MULTI_PARA_RANGE_NOT_SUPPORTED.
 * - IME composition 중에는 COMPOSITION_LOCKED.
 * - 결과 state 의 activeParagraphId 는 신규 (뒤쪽) paragraph 로 이동,
 *   caretOffset 은 0.
 */
export function splitParagraphAtCaret(state) {
  if (!state.activeParagraphId) {
    return { state, command: null, reason: "NO_ACTIVE_PARAGRAPH" };
  }
  if (state.composition?.active) {
    return { state, command: null, reason: "COMPOSITION_LOCKED" };
  }
  if (state.selectionMode === SEL_TEXT_RANGE
      && state.rangeAnchor !== state.rangeFocus) {
    return { state, command: null,
                  reason: "MULTI_PARA_RANGE_NOT_SUPPORTED" };
  }
  const p = _findPara(state, state.activeParagraphId);
  if (!p) {
    return { state, command: null, reason: "TARGET_PARAGRAPH_NOT_FOUND" };
  }
  const scope = p.containerScope ?? null;
  const _insertScopeReject = _scopeBoundaryRejectReason(scope, "INSERT");
  if (_insertScopeReject) {
    return { state, command: null, reason: _insertScopeReject };
  }
  const _cprg = _charPrGuard(p);
  if (_cprg) return { state, command: null, reason: _cprg };
  const caret = state.caretOffset ?? 0;
  const newPid = allocateNewParagraphId(state.paragraphs);
  const cmd = makeParaInsertCommand({
    target: _buildTarget(state, p.paragraphId),
    paragraph: p,
    caretOffset: caret,
    newParagraphId: newPid,
    sourceDocumentHash: state.sourceDocumentHash,
  });
  const nextParas = applyParaInsertToParagraphs(state.paragraphs, cmd);
  return {
    state: {
      ..._appendCommandWithParas(state, cmd, nextParas),
      activeParagraphId: newPid,
      caretOffset: 0,
      rangeAnchor: null, rangeFocus: null,
      selectionMode: SEL_CARET,
    },
    command: cmd, reason: "OK",
  };
}

/* ── WEB-OFFICE-PARA-EDIT-STRUCTURE-PARA-DELETE-01 ─────────────────────── */

/* Backspace at caret==0: 현재 paragraph 를 이전 paragraph 로 병합.
 *
 * 허용: body scope (kind=="block"), 같은 단지 내 직전 paragraph 존재.
 * 거부: cell scope, 첫 paragraph, multi-paragraph selection,
 *       composition 중, containerScope 없음.
 */
export function mergeParagraphWithPrevious(state) {
  if (state.composition.active) {
    return { state, command: null, reason: "COMPOSITION_LOCKED" };
  }
  if (state.selectionMode === SEL_TEXT_RANGE
      && state.rangeAnchor !== state.rangeFocus) {
    return { state, command: null,
                  reason: "MULTI_PARA_RANGE_NOT_SUPPORTED" };
  }
  const curPara = _findPara(state, state.activeParagraphId);
  if (!curPara) {
    return { state, command: null, reason: "TARGET_PARAGRAPH_NOT_FOUND" };
  }
  const scope = curPara.containerScope ?? null;
  const _deleteScopeReject = _scopeBoundaryRejectReason(scope, "DELETE");
  if (_deleteScopeReject) {
    return { state, command: null, reason: _deleteScopeReject };
  }
  const _curCprg = _charPrGuard(curPara);
  if (_curCprg) return { state, command: null, reason: _curCprg };
  // 이전 paragraph 탐색 (paragraphs 배열 순서 기반)
  const curIdx = state.paragraphs.findIndex(
    (p) => p.paragraphId === state.activeParagraphId);
  if (curIdx <= 0) {
    return { state, command: null, reason: "NO_PREV_PARAGRAPH" };
  }
  const prevPara = state.paragraphs[curIdx - 1];
  const _prevCprg = _charPrGuard(prevPara);
  if (_prevCprg) return { state, command: null, reason: _prevCprg };
  // 이전 paragraph 가 다른 section (containerScope) 이면 reject
  const prevScope = prevPara.containerScope ?? null;
  if (prevScope && scope
      && prevScope.kind === "block" && scope.kind === "block"
      && prevScope.sectionIndex !== scope.sectionIndex) {
    return { state, command: null,
                  reason: "SECTION_BOUNDARY_NOT_SUPPORTED" };
  }
  const prevText = prevPara.runs.reduce((acc, r) => acc + r.text, "");
  const cmd = makeParaDeleteCommand({
    prevParagraph: prevPara,
    currentParagraph: curPara,
    sourceDocumentHash: state.sourceDocumentHash,
  });
  const nextParas = applyParaDeleteForwardToParagraphs(
    state.paragraphs, cmd);
  return {
    state: {
      ..._appendCommandWithParas(state, cmd, nextParas),
      activeParagraphId: prevPara.paragraphId,
      caretOffset: prevText.length,
      rangeAnchor: null, rangeFocus: null,
      selectionMode: SEL_CARET,
    },
    command: cmd, reason: "OK",
  };
}
