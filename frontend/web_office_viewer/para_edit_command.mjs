/* EditCommand v2 — Phase 3 PARA-EDIT 모델 (browser side).
 * Python `para_edit_model.py` 와 정합. writer/apply/save 호출 없음.
 */

export const CT_SET_CELL_TEXT = "SET_CELL_TEXT";
export const CT_TYPE_TEXT = "TYPE_TEXT";
export const CT_REPLACE_TEXT_RANGE = "REPLACE_TEXT_RANGE";
export const CT_DELETE_TEXT_RANGE = "DELETE_TEXT_RANGE";
export const CT_SET_PARAGRAPH_TEXT_SAFE = "SET_PARAGRAPH_TEXT_SAFE";
export const CT_SPLIT_TEXT_RUN = "SPLIT_TEXT_RUN";
export const CT_MERGE_TEXT_RUNS = "MERGE_TEXT_RUNS";
// WEB-OFFICE-PARA-EDIT-APPLYFORMAT-EXISTING-CHARPR-01.
export const CT_APPLY_FORMAT = "APPLY_FORMAT";
// WEB-OFFICE-PARA-EDIT-STRUCTURE-PARA-INSERT-01.
export const CT_PARA_INSERT = "PARA_INSERT";
// WEB-OFFICE-PARA-EDIT-STRUCTURE-PARA-DELETE-01: 사용자 command (Backspace at start).
export const CT_PARA_DELETE = "PARA_DELETE";

export const POLICY_ANCHOR_CHARPR = "ANCHOR_CHARPR";
export const POLICY_FOCUS_CHARPR = "FOCUS_CHARPR";
export const POLICY_REQUIRES_REVIEW = "REQUIRES_REVIEW";

export const REASON_MERGE_CHARPR_MISMATCH = "MERGE_CHARPR_MISMATCH";
export const REASON_EXPECTED_BEFORE_MISMATCH =
  "EXPECTED_BEFORE_MISMATCH_PARAGRAPH";
export const REASON_STALE_SESSION = "STALE_SESSION";
export const REASON_REQUIRES_REVIEW = "REQUIRES_REVIEW";
// WEB-OFFICE-P3-RUN-SPLIT-MERGE-CHARPR-GUARD-01
export const REASON_CHARPR_MISSING_ON_RUN = "CHARPR_MISSING_ON_RUN";
export const REASON_CHARPR_SPLIT_SOURCE_MISSING = "CHARPR_SPLIT_SOURCE_MISSING";
// WEB-OFFICE-P3-EMPTY-PARAGRAPH-WRITER-GUARD-01
export const REASON_EMPTY_PARA_ID_MISSING = "EMPTY_PARA_ID_MISSING";
export const REASON_EMPTY_PARA_PR_MISSING = "EMPTY_PARA_PR_MISSING";
export const REASON_EMPTY_RUN_CHARPR_MISSING = "EMPTY_RUN_CHARPR_MISSING";
export const REASON_PARAGRAPH_COUNT_DECREASED = "PARAGRAPH_COUNT_DECREASED";

export const STATUS_PENDING = "PENDING";
export const STATUS_VALIDATED = "VALIDATED";
export const STATUS_REJECTED = "REJECTED";

function _uuid() {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
  });
}

function _paragraphText(p) {
  return p.runs.map((r) => r.text).join("");
}

function _nextRunId(p) {
  const existing = new Set(p.runs.map((r) => r.runId));
  let n = 0;
  for (;;) {
    const cand = `${p.paragraphId}_run${n}`;
    if (!existing.has(cand)) return cand;
    n++;
  }
}

function _locateOffset(p, off) {
  let pos = 0;
  for (const r of p.runs) {
    const end = pos + r.text.length;
    if (off <= end) return { runId: r.runId, offset: off - pos };
    pos = end;
  }
  const last = p.runs[p.runs.length - 1];
  return { runId: last.runId, offset: last.text.length };
}

// WEB-OFFICE-P3-RUN-SPLIT-MERGE-CHARPR-GUARD-01
export function validateRunCharPrIntegrity(paragraph) {
  const missingRunIds = [];
  for (const r of paragraph.runs) {
    if (r.charPrIDRef === null || r.charPrIDRef === undefined
        || r.charPrIDRef === "") {
      missingRunIds.push(r.runId);
    }
  }
  return { valid: missingRunIds.length === 0, missingRunIds };
}

// WEB-OFFICE-P3-EMPTY-PARAGRAPH-WRITER-GUARD-01
export function validateEmptyParagraphIntegrity(paragraph) {
  const issues = [];
  if (!paragraph.paragraphId) issues.push(REASON_EMPTY_PARA_ID_MISSING);
  if (!paragraph.parPrIDRef) issues.push(REASON_EMPTY_PARA_PR_MISSING);
  for (const r of (paragraph.runs ?? [])) {
    if (r.charPrIDRef === null || r.charPrIDRef === undefined
        || r.charPrIDRef === "") {
      issues.push(REASON_EMPTY_RUN_CHARPR_MISSING);
      break;
    }
  }
  return { valid: issues.length === 0, issues };
}

export function validateParagraphCountPreserved(beforeParas, afterParas) {
  if (afterParas.length < beforeParas.length) {
    return {
      valid: false,
      reason: REASON_PARAGRAPH_COUNT_DECREASED,
      before: beforeParas.length, after: afterParas.length,
    };
  }
  return { valid: true };
}

export function splitRun(p, runId, offset) {
  const idx = p.runs.findIndex((r) => r.runId === runId);
  if (idx < 0) throw new Error(`run not found: ${runId}`);
  const t = p.runs[idx];
  if (offset <= 0 || offset >= t.text.length) return { p, info: null };
  if (t.charPrIDRef === null || t.charPrIDRef === undefined
      || t.charPrIDRef === "") {
    throw new Error(REASON_CHARPR_SPLIT_SOURCE_MISSING);
  }
  const left = { runId: t.runId, text: t.text.slice(0, offset),
                          charPrIDRef: t.charPrIDRef };
  const newRightId = _nextRunId(p);
  const right = { runId: newRightId, text: t.text.slice(offset),
                            charPrIDRef: t.charPrIDRef };
  const runs = [...p.runs.slice(0, idx), left, right,
                          ...p.runs.slice(idx + 1)];
  return {
    p: { paragraphId: p.paragraphId, parPrIDRef: p.parPrIDRef,
              containerScope: p.containerScope ?? null, runs },
    info: { leftRunId: left.runId, rightRunId: right.runId, offset },
  };
}

export function mergeRuns(p, leftId, rightId) {
  const li = p.runs.findIndex((r) => r.runId === leftId);
  const ri = p.runs.findIndex((r) => r.runId === rightId);
  if (li < 0 || ri < 0) throw new Error("run not found in mergeRuns");
  if (ri !== li + 1) throw new Error("runs not adjacent");
  if (p.runs[li].charPrIDRef !== p.runs[ri].charPrIDRef) {
    throw new Error(REASON_MERGE_CHARPR_MISMATCH);
  }
  const merged = {
    runId: p.runs[li].runId,
    text: p.runs[li].text + p.runs[ri].text,
    charPrIDRef: p.runs[li].charPrIDRef,
  };
  const runs = [...p.runs.slice(0, li), merged, ...p.runs.slice(ri + 1)];
  return { paragraphId: p.paragraphId, parPrIDRef: p.parPrIDRef,
                  containerScope: p.containerScope ?? null, runs };
}

export function normalizeParagraph(p) {
  let runs = p.runs.filter((r) => r.text !== "");
  if (runs.length === 0) {
    const charPr = p.runs[0]?.charPrIDRef ?? null;
    return {
      paragraphId: p.paragraphId, parPrIDRef: p.parPrIDRef,
      containerScope: p.containerScope ?? null,
      runs: [{
        runId: p.runs[0]?.runId ?? `${p.paragraphId}_run0`,
        text: "", charPrIDRef: charPr,
      }],
    };
  }
  const merged = [runs[0]];
  for (let i = 1; i < runs.length; i++) {
    const prev = merged[merged.length - 1];
    if (prev.charPrIDRef === runs[i].charPrIDRef) {
      merged[merged.length - 1] = {
        runId: prev.runId, charPrIDRef: prev.charPrIDRef,
        text: prev.text + runs[i].text,
      };
    } else merged.push(runs[i]);
  }
  return { paragraphId: p.paragraphId, parPrIDRef: p.parPrIDRef,
              containerScope: p.containerScope ?? null,
              runs: merged };
}

/* command factories */

export function makeTypeTextCommand({
  target, paragraph, caretOffset, insertText,
  sourceDocumentHash, commandGroupId,
}) {
  if (insertText === "") return null;
  const cp = _locateOffset(paragraph, caretOffset);
  const inheritPr = paragraph.runs.find(
    (r) => r.runId === cp.runId)?.charPrIDRef ?? null;
  const scope = target?.containerScope ?? null;
  return {
    commandId: _uuid(), commandType: CT_TYPE_TEXT,
    target, payload: { caretOffset, insertText },
    // WEB-OFFICE-PARA-TYPE-TEXT-CONTRACT-01 — 빈 range slice 기준 정렬.
    forward: { kind: "TYPE_TEXT", paragraphId: paragraph.paragraphId,
                      caretOffset,
                      rangeAnchor: caretOffset,
                      rangeFocus: caretOffset,
                      rangeStart: caretOffset,
                      rangeEnd: caretOffset,
                      insertText, afterText: insertText,
                      inheritCharPrIDRef: inheritPr,
                      containerScope: scope },
    inverse: { kind: "DELETE_TEXT_RANGE",
                      paragraphId: paragraph.paragraphId,
                      rangeAnchor: caretOffset,
                      rangeFocus: caretOffset + insertText.length,
                      deletedText: insertText,
                      deletedCharPrIDRef: inheritPr,
                      containerScope: scope },
    expectedBefore: "",
    createdAt: new Date().toISOString(),
    sourceDocumentHash,
    commandGroupId: commandGroupId ?? _uuid(),
    status: STATUS_PENDING,
  };
}

export function makeReplaceTextRangeCommand({
  target, paragraph, rangeAnchor, rangeFocus, afterText,
  sourceDocumentHash, policy = POLICY_ANCHOR_CHARPR, commandGroupId,
}) {
  const a = Math.min(rangeAnchor, rangeFocus);
  const b = Math.max(rangeAnchor, rangeFocus);
  const before = _paragraphText(paragraph).slice(a, b);
  if (before === afterText) {
    throw new Error("before == after — no command should be created");
  }
  const anchorCp = _locateOffset(paragraph, a);
  const focusCp = _locateOffset(paragraph, b);
  const anchorPr = paragraph.runs.find(
    (r) => r.runId === anchorCp.runId)?.charPrIDRef ?? null;
  const focusPr = paragraph.runs.find(
    (r) => r.runId === focusCp.runId)?.charPrIDRef ?? null;
  const multi = anchorPr !== focusPr;
  if (multi && policy === POLICY_REQUIRES_REVIEW) {
    throw new Error(REASON_REQUIRES_REVIEW);
  }
  const applyPr = policy === POLICY_FOCUS_CHARPR ? focusPr : anchorPr;
  const scope = target?.containerScope ?? null;
  return {
    commandId: _uuid(), commandType: CT_REPLACE_TEXT_RANGE,
    target,
    payload: { rangeAnchor: a, rangeFocus: b, afterText, policy },
    forward: { kind: "REPLACE_TEXT_RANGE",
                      paragraphId: paragraph.paragraphId,
                      rangeAnchor: a, rangeFocus: b,
                      afterText, applyCharPrIDRef: applyPr, policy,
                      containerScope: scope },
    inverse: { kind: "REPLACE_TEXT_RANGE",
                      paragraphId: paragraph.paragraphId,
                      rangeAnchor: a, rangeFocus: a + afterText.length,
                      afterText: before, applyCharPrIDRef: anchorPr, policy,
                      containerScope: scope },
    expectedBefore: before,
    createdAt: new Date().toISOString(),
    sourceDocumentHash,
    commandGroupId: commandGroupId ?? _uuid(),
    status: STATUS_PENDING,
  };
}

export function makeDeleteTextRangeCommand({
  target, paragraph, rangeAnchor, rangeFocus,
  sourceDocumentHash, commandGroupId,
}) {
  const a = Math.min(rangeAnchor, rangeFocus);
  const b = Math.max(rangeAnchor, rangeFocus);
  if (a === b) throw new Error("empty range");
  const deleted = _paragraphText(paragraph).slice(a, b);
  const anchorCp = _locateOffset(paragraph, a);
  const anchorPr = paragraph.runs.find(
    (r) => r.runId === anchorCp.runId)?.charPrIDRef ?? null;
  const scope = target?.containerScope ?? null;
  return {
    commandId: _uuid(), commandType: CT_DELETE_TEXT_RANGE,
    target,
    payload: { rangeAnchor: a, rangeFocus: b },
    forward: { kind: "DELETE_TEXT_RANGE",
                      paragraphId: paragraph.paragraphId,
                      rangeAnchor: a, rangeFocus: b,
                      deletedText: deleted, deletedCharPrIDRef: anchorPr,
                      containerScope: scope },
    inverse: { kind: "REPLACE_TEXT_RANGE",
                      paragraphId: paragraph.paragraphId,
                      rangeAnchor: a, rangeFocus: a,
                      afterText: deleted, applyCharPrIDRef: anchorPr,
                      policy: POLICY_ANCHOR_CHARPR,
                      containerScope: scope },
    expectedBefore: deleted,
    createdAt: new Date().toISOString(),
    sourceDocumentHash,
    commandGroupId: commandGroupId ?? _uuid(),
    status: STATUS_PENDING,
  };
}

// WEB-OFFICE-PARA-EDIT-APPLYFORMAT-EXISTING-CHARPR-01.
// 같은 문서 header.xml 에 이미 존재하는 charPrIDRef 로만 교체. 신규
// charPr 생성 금지 (검증은 server-side writer 에서 수행).
export function makeApplyFormatCommand({
  target, paragraph, rangeAnchor, rangeFocus, targetCharPrIDRef,
  sourceDocumentHash, commandGroupId,
}) {
  const a = Math.min(rangeAnchor, rangeFocus);
  const b = Math.max(rangeAnchor, rangeFocus);
  if (a === b) return null;  // NOOP
  const text = _paragraphText(paragraph);
  const before = text.slice(a, b);
  // before run charPr 분포 (inverse 복원 자료)
  const beforeSegments = [];
  let pos = 0;
  for (const r of paragraph.runs) {
    const rs = pos; const re_ = pos + r.text.length;
    if (rs >= b) break;
    if (re_ <= a || rs === re_) { pos = re_; continue; }
    beforeSegments.push({
      segmentStart: Math.max(rs, a),
      segmentEnd: Math.min(re_, b),
      charPrIDRef: r.charPrIDRef,
    });
    pos = re_;
  }
  const scope = target?.containerScope ?? null;
  return {
    commandId: _uuid(), commandType: CT_APPLY_FORMAT,
    target,
    payload: { rangeAnchor: a, rangeFocus: b,
                          targetCharPrIDRef: String(targetCharPrIDRef) },
    forward: { kind: "APPLY_FORMAT",
                      paragraphId: paragraph.paragraphId,
                      rangeAnchor: a, rangeFocus: b,
                      rangeStart: a, rangeEnd: b,
                      targetCharPrIDRef: String(targetCharPrIDRef),
                      beforeSegments,
                      containerScope: scope },
    inverse: { kind: "APPLY_FORMAT_INVERSE",
                      paragraphId: paragraph.paragraphId,
                      rangeAnchor: a, rangeFocus: b,
                      restoreSegments: beforeSegments,
                      containerScope: scope },
    expectedBefore: before,
    createdAt: new Date().toISOString(),
    sourceDocumentHash,
    commandGroupId: commandGroupId ?? _uuid(),
    status: STATUS_PENDING,
  };
}

/* apply / validate */

export function applyCommandToParagraph(p, cmd) {
  const k = cmd.forward.kind;
  if (k === "TYPE_TEXT") return _applyTypeText(p, cmd.forward);
  if (k === "REPLACE_TEXT_RANGE") return _applyReplace(p, cmd.forward);
  if (k === "DELETE_TEXT_RANGE") {
    return _applyReplace(p, { ...cmd.forward, afterText: "",
                                              applyCharPrIDRef: cmd.forward.deletedCharPrIDRef });
  }
  if (k === "SPLIT_TEXT_RUN") {
    return splitRun(p, cmd.forward.runId, cmd.forward.offset).p;
  }
  if (k === "MERGE_TEXT_RUNS") {
    return mergeRuns(p, cmd.forward.leftRunId, cmd.forward.rightRunId);
  }
  if (k === "APPLY_FORMAT") return _applyFormat(p, cmd.forward);
  if (k === "APPLY_FORMAT_INVERSE") {
    return _applyFormatInverse(p, cmd.forward);
  }
  throw new Error(`unknown forward kind: ${k}`);
}

/* APPLY_FORMAT_INVERSE — restoreSegments 의 각 segment 에 대해
 * 원래 charPrIDRef 를 복원. paragraph.text 무변경. */
function _applyFormatInverse(p, fwd) {
  const segs = fwd.restoreSegments || [];
  // 각 segment 를 순차 적용 — segment 단위 작은 APPLY_FORMAT 호출과
  // 동등.
  let pp = p;
  for (const seg of segs) {
    pp = _applyFormat(pp, {
      rangeAnchor: seg.segmentStart,
      rangeFocus: seg.segmentEnd,
      targetCharPrIDRef: seg.charPrIDRef ?? "",
    });
  }
  return pp;
}

/* WEB-OFFICE-PARA-EDIT-APPLYFORMAT-TOOLBAR-COMMAND-01.
 * paragraph.text 는 변경하지 않고, [rangeAnchor, rangeFocus) 안의 run
 * segment 의 charPrIDRef 를 targetCharPrIDRef 로 교체한다. */
function _applyFormat(p, fwd) {
  const a = fwd.rangeAnchor; const b = fwd.rangeFocus;
  const target = String(fwd.targetCharPrIDRef);
  // 끝/시작에서 split
  const endCp = _locateOffset(p, b);
  let pp = splitRun(p, endCp.runId, endCp.offset).p;
  const startCp = _locateOffset(pp, a);
  pp = splitRun(pp, startCp.runId, startCp.offset).p;
  const newRuns = []; let pos = 0;
  for (const r of pp.runs) {
    const rs = pos; const re_ = pos + r.text.length;
    if (rs >= a && re_ <= b && r.text) {
      newRuns.push({
        runId: r.runId, text: r.text, charPrIDRef: target,
      });
    } else {
      newRuns.push(r);
    }
    pos = re_;
  }
  return { paragraphId: pp.paragraphId, parPrIDRef: pp.parPrIDRef,
              containerScope: pp.containerScope ?? null,
              runs: newRuns };
}

function _applyTypeText(p, fwd) {
  const cp = _locateOffset(p, fwd.caretOffset);
  const split = splitRun(p, cp.runId, cp.offset);
  const pp = split.p;
  // find insertion index by walking text
  let pos = 0; let insertAt = 0;
  for (let i = 0; i < pp.runs.length; i++) {
    if (pos === fwd.caretOffset) { insertAt = i; break; }
    pos += pp.runs[i].text.length;
    insertAt = i + 1;
  }
  const newRun = { runId: _nextRunId(pp), text: fwd.insertText,
                          charPrIDRef: fwd.inheritCharPrIDRef };
  const runs = [...pp.runs.slice(0, insertAt), newRun,
                          ...pp.runs.slice(insertAt)];
  return normalizeParagraph({ paragraphId: pp.paragraphId,
                                                  parPrIDRef: pp.parPrIDRef,
                                                  containerScope: pp.containerScope ?? null,
                                                  runs });
}

function _applyReplace(p, fwd) {
  const { rangeAnchor: a, rangeFocus: b, afterText: after } = fwd;
  const applyPr = fwd.applyCharPrIDRef;
  // split at b then at a
  const endCp = _locateOffset(p, b);
  let pp = splitRun(p, endCp.runId, endCp.offset).p;
  const startCp = _locateOffset(pp, a);
  pp = splitRun(pp, startCp.runId, startCp.offset).p;
  // remove runs fully inside [a,b], insert after at a position
  const newRuns = []; let pos = 0; let inserted = false;
  const tryInsert = () => {
    if (inserted) return;
    if (after) {
      newRuns.push({ runId: _nextRunId(pp), text: after,
                                  charPrIDRef: applyPr });
    }
    inserted = true;
  };
  for (const r of pp.runs) {
    const runStart = pos; const runEnd = pos + r.text.length;
    // run 시작이 a 를 지나는 시점에 우선 insert (empty range 도 처리)
    if (!inserted && runStart >= a) tryInsert();
    if (runEnd <= a || runStart >= b) {
      newRuns.push(r);
    } else {
      tryInsert();
    }
    pos = runEnd;
  }
  if (!inserted) tryInsert();
  return normalizeParagraph({ paragraphId: pp.paragraphId,
                                                  parPrIDRef: pp.parPrIDRef,
                                                  containerScope: pp.containerScope ?? null,
                                                  runs: newRuns });
}

export function validateExpectedBefore(cmd, paragraph) {
  if (cmd.commandType === CT_TYPE_TEXT) {
    // WEB-OFFICE-PARA-TYPE-TEXT-CONTRACT-01 — 빈 range slice 기준.
    const co = cmd.forward?.caretOffset ?? 0;
    const text = _paragraphText(paragraph);
    if (cmd.expectedBefore !== "") return false;
    if (co < 0 || co > text.length) return false;
    return text.slice(co, co) === cmd.expectedBefore;
  }
  if (cmd.commandType === CT_REPLACE_TEXT_RANGE
      || cmd.commandType === CT_DELETE_TEXT_RANGE) {
    const { rangeAnchor: a, rangeFocus: b } = cmd.forward;
    return _paragraphText(paragraph).slice(a, b) === cmd.expectedBefore;
  }
  return true;
}

export function validateCharPrPreserved(before, after) {
  const orig = new Set(before.runs.map((r) => r.charPrIDRef)
                                .filter((x) => x !== null && x !== undefined));
  const post = new Set(after.runs.map((r) => r.charPrIDRef)
                                .filter((x) => x !== null && x !== undefined));
  for (const v of post) if (!orig.has(v)) return false;
  return true;
}

export function validateParPrPreserved(before, after) {
  return before.parPrIDRef === after.parPrIDRef;
}


/* ── WEB-OFFICE-PARA-EDIT-STRUCTURE-PARA-INSERT-01 ─────────────── */

/* paragraphs 배열에서 max(paragraphId 의 정수 부분) + 1 을 새 id 로
 * 반환. corpus 통계상 paragraph id 는 sparse 정수 — max+1 정책으로
 * 충돌 회피. paragraphId 가 비정수면 자체 카운터로 fallback. */
export function allocateNewParagraphId(paragraphs) {
  let maxId = -1;
  for (const p of paragraphs) {
    const n = parseInt(p.paragraphId, 10);
    if (Number.isFinite(n) && n > maxId) maxId = n;
  }
  return maxId >= 0 ? String(maxId + 1) : "1";
}

export function makeParaInsertCommand({
  target, paragraph, caretOffset, newParagraphId,
  sourceDocumentHash, commandGroupId,
}) {
  const full = _paragraphText(paragraph);
  if (caretOffset < 0 || caretOffset > full.length) {
    throw new Error(
      `caretOffset ${caretOffset} out of range [0, ${full.length}]`);
  }
  const before = full.slice(0, caretOffset);
  const after = full.slice(caretOffset);
  const cp = _locateOffset(paragraph, caretOffset);
  const inheritPr = paragraph.runs.find(
    (r) => r.runId === cp.runId)?.charPrIDRef ?? null;
  const scope = target?.containerScope ?? null;
  return {
    commandId: _uuid(), commandType: CT_PARA_INSERT,
    target, payload: { caretOffset, newParagraphId },
    forward: { kind: "PARA_INSERT",
                      paragraphId: paragraph.paragraphId,
                      caretOffset,
                      newParagraphId,
                      newParPrIDRef: paragraph.parPrIDRef ?? null,
                      newCharPrIDRef: inheritPr,
                      beforeText: before,
                      afterText: after,
                      containerScope: scope },
    inverse: { kind: "PARA_DELETE",
                      paragraphId: newParagraphId,
                      mergeIntoParagraphId: paragraph.paragraphId,
                      mergedText: after,
                      originalCaretOffset: caretOffset,
                      containerScope: scope },
    expectedBefore: full,
    createdAt: new Date().toISOString(),
    sourceDocumentHash,
    commandGroupId: commandGroupId ?? _uuid(),
    status: STATUS_PENDING,
  };
}

/* paragraphs 배열에 PARA_INSERT forward 적용 — original paragraph 를
 * 두 paragraph 로 split. returns 새 paragraphs 배열. */
export function applyParaInsertToParagraphs(paragraphs, cmd) {
  const fwd = cmd.forward;
  const idx = paragraphs.findIndex(
    (p) => p.paragraphId === fwd.paragraphId);
  if (idx < 0) {
    throw new Error(
      `PARA_INSERT: paragraph ${fwd.paragraphId} not found`);
  }
  const orig = paragraphs[idx];
  // run 단위로 caret 좌/우 분할
  const beforeRuns = []; const afterRuns = [];
  let pos = 0;
  for (const r of orig.runs) {
    const rs = pos; const re_ = pos + r.text.length;
    if (re_ <= fwd.caretOffset) {
      beforeRuns.push({ ...r });
    } else if (rs >= fwd.caretOffset) {
      afterRuns.push({ ...r });
    } else {
      const lo = fwd.caretOffset - rs;
      beforeRuns.push({ ...r, text: r.text.slice(0, lo) });
      afterRuns.push({ ...r, runId: `${fwd.newParagraphId}_run0`,
                                            text: r.text.slice(lo) });
    }
    pos = re_;
  }
  // 빈 paragraph 면 빈 run 1개 발급
  const firstRuns = beforeRuns.length > 0 ? beforeRuns : [{
    runId: `${orig.paragraphId}_run0`, text: "",
    charPrIDRef: fwd.newCharPrIDRef,
  }];
  const secondRuns = afterRuns.length > 0 ? afterRuns : [{
    runId: `${fwd.newParagraphId}_run0`, text: "",
    charPrIDRef: fwd.newCharPrIDRef,
  }];
  const firstPara = {
    paragraphId: orig.paragraphId,
    parPrIDRef: orig.parPrIDRef,
    containerScope: orig.containerScope ?? null,
    runs: firstRuns,
  };
  const secondPara = {
    paragraphId: fwd.newParagraphId,
    parPrIDRef: fwd.newParPrIDRef,
    containerScope: orig.containerScope ?? null,
    runs: secondRuns,
  };
  return [
    ...paragraphs.slice(0, idx),
    firstPara, secondPara,
    ...paragraphs.slice(idx + 1),
  ];
}

/* PARA_INSERT inverse 적용 — secondPara 를 제거하고 firstPara 와 합침. */
export function applyParaDeleteToParagraphs(paragraphs, cmd) {
  const inv = cmd.inverse;
  const newIdx = paragraphs.findIndex(
    (p) => p.paragraphId === inv.paragraphId);
  const origIdx = paragraphs.findIndex(
    (p) => p.paragraphId === inv.mergeIntoParagraphId);
  if (newIdx < 0 || origIdx < 0) {
    throw new Error(
      `PARA_DELETE inverse: paragraph not found`);
  }
  const secondPara = paragraphs[newIdx];
  const firstPara = paragraphs[origIdx];
  // first 의 마지막 run 이 빈 텍스트이면 제거 (split 시 발급된 empty run)
  const firstRuns = [...firstPara.runs];
  if (firstRuns.length > 1
      && firstRuns[firstRuns.length - 1].text === "") {
    firstRuns.pop();
  }
  // second 의 첫 run 이 빈 텍스트이면 제거
  const secondRuns = [...secondPara.runs];
  if (secondRuns.length > 1 && secondRuns[0].text === "") {
    secondRuns.shift();
  } else if (secondRuns.length === 1 && secondRuns[0].text === "") {
    secondRuns.length = 0;
  }
  const merged = {
    paragraphId: firstPara.paragraphId,
    parPrIDRef: firstPara.parPrIDRef,
    containerScope: firstPara.containerScope ?? null,
    runs: [...firstRuns, ...secondRuns],
  };
  // second paragraph 위치/순서 무관 — 둘 다 제거하고 merged 삽입
  const result = paragraphs.filter(
    (_, i) => i !== newIdx && i !== origIdx);
  // 원 위치는 firstPara 의 자리 (origIdx) 보존
  const insertAt = Math.min(newIdx, origIdx);
  return [
    ...result.slice(0, insertAt),
    merged,
    ...result.slice(insertAt),
  ];
}

/* ── WEB-OFFICE-PARA-EDIT-STRUCTURE-PARA-DELETE-01 ─────────────────────── */

/* Backspace at paragraph start → 이전 paragraph 로 병합.
 *
 * forward  : PARA_DELETE (currentParagraphId 제거, prevParagraphId 로 병합)
 * inverse  : PARA_INSERT (prevParagraphId 를 mergeOffset 위치에서 재분할)
 */
export function makeParaDeleteCommand({
  prevParagraph, currentParagraph,
  sourceDocumentHash, commandGroupId,
}) {
  const prevText = _paragraphText(prevParagraph);
  const curText  = _paragraphText(currentParagraph);
  const scope = currentParagraph.containerScope ?? null;
  // mergeOffset = 병합 후 caret 위치 = prevParagraph 기존 텍스트 길이
  const mergeOffset = prevText.length;
  // 이전 paragraph 의 마지막 run charPr 상속 (없으면 null)
  const lastRun = prevParagraph.runs[prevParagraph.runs.length - 1] ?? null;
  const inheritPr = lastRun?.charPrIDRef ?? null;
  return {
    commandId: _uuid(),
    commandType: CT_PARA_DELETE,
    target: {
      paragraphId: currentParagraph.paragraphId,
      containerScope: scope,
    },
    payload: {
      prevParagraphId: prevParagraph.paragraphId,
      mergeOffset,
    },
    forward: {
      kind: "PARA_DELETE",
      paragraphId: currentParagraph.paragraphId,
      prevParagraphId: prevParagraph.paragraphId,
      mergedText: curText,
      mergeOffset,
      containerScope: scope,
    },
    inverse: {
      kind: "PARA_INSERT",
      paragraphId: prevParagraph.paragraphId,
      caretOffset: mergeOffset,
      newParagraphId: currentParagraph.paragraphId,
      newParPrIDRef: currentParagraph.parPrIDRef ?? null,
      newCharPrIDRef: inheritPr,
      beforeText: prevText,
      afterText: curText,
      containerScope: scope,
    },
    expectedBefore: curText,
    createdAt: new Date().toISOString(),
    sourceDocumentHash,
    commandGroupId: commandGroupId ?? _uuid(),
    status: STATUS_PENDING,
  };
}

/* paragraphs 배열에 PARA_DELETE forward 적용 — currentParagraph 를 제거하고
 * prevParagraph 의 끝으로 병합. returns 새 paragraphs 배열. */
export function applyParaDeleteForwardToParagraphs(paragraphs, cmd) {
  const fwd = cmd.forward;
  const curIdx  = paragraphs.findIndex(
    (p) => p.paragraphId === fwd.paragraphId);
  const prevIdx = paragraphs.findIndex(
    (p) => p.paragraphId === fwd.prevParagraphId);
  if (curIdx < 0 || prevIdx < 0) {
    throw new Error(`PARA_DELETE forward: paragraph not found`);
  }
  const curPara  = paragraphs[curIdx];
  const prevPara = paragraphs[prevIdx];
  // prev 의 마지막 run 이 빈 텍스트면 제거 (split 잔재)
  const prevRuns = [...prevPara.runs];
  if (prevRuns.length > 1
      && prevRuns[prevRuns.length - 1].text === "") {
    prevRuns.pop();
  }
  // cur 의 첫 run 이 빈 텍스트면 제거
  const curRuns = [...curPara.runs];
  if (curRuns.length > 1 && curRuns[0].text === "") {
    curRuns.shift();
  } else if (curRuns.length === 1 && curRuns[0].text === "") {
    curRuns.length = 0;
  }
  const merged = {
    paragraphId: prevPara.paragraphId,
    parPrIDRef: prevPara.parPrIDRef,
    containerScope: prevPara.containerScope ?? null,
    runs: [...prevRuns, ...curRuns],
  };
  return [
    ...paragraphs.slice(0, prevIdx),
    merged,
    ...paragraphs.slice(prevIdx + 1).filter(
      (p) => p.paragraphId !== fwd.paragraphId),
  ];
}
