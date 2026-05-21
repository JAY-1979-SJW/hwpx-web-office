/* EditCommand v1 (browser side) — CELL-EDIT MVP-A.
 * forward/inverse 동반 + expectedBefore 검증. writer/apply 호출은 일절 없다.
 */

export const CT_SET_CELL_TEXT = "SET_CELL_TEXT";
export const STATUS_PENDING = "PENDING";
export const STATUS_VALIDATED = "VALIDATED";
export const STATUS_REJECTED = "REJECTED";

function _uuid() {
  // node + 브라우저 양쪽에서 동작하는 단순 UUIDv4
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
  });
}

function _coordFromCellId(cellId) {
  if (!cellId.startsWith("cell_")) {
    throw new Error(`invalid cellId: ${cellId}`);
  }
  const rest = cellId.slice("cell_".length);
  const cIdx = rest.lastIndexOf("_c");
  const rIdx = rest.lastIndexOf("_r", cIdx);
  if (cIdx < 0 || rIdx < 0) {
    throw new Error(`unparseable cellId: ${cellId}`);
  }
  const tableId = rest.slice(0, rIdx);
  const row = parseInt(rest.slice(rIdx + 2, cIdx), 10);
  const col = parseInt(rest.slice(cIdx + 2), 10);
  return { tableId, row, col };
}

/* SET_CELL_TEXT 명령 생성. before === after 면 null 반환 (no-command). */
export function makeSetCellTextCommand({
  cellId, tableIndex, before, after,
  sourceDocumentHash, expectedBefore,
}) {
  if (before === after) return null;
  const { row, col } = _coordFromCellId(cellId);
  const expected = expectedBefore != null ? expectedBefore : before;
  return {
    commandId: _uuid(),
    commandType: CT_SET_CELL_TEXT,
    targetId: cellId,
    targetKind: "cell",
    before, after, expectedBefore: expected,
    forward: { set_cells: [{ table: tableIndex, row, col, value: after }] },
    inverse: { set_cells: [{ table: tableIndex, row, col, value: before }] },
    createdAt: new Date().toISOString(),
    sourceDocumentHash,
    status: STATUS_PENDING,
  };
}

export function validateAgainstCurrent(command, currentValue) {
  return command.expectedBefore === currentValue;
}

export function applyForward(currentValue, command) {
  if (!validateAgainstCurrent(command, currentValue)) {
    throw new Error(
      `expectedBefore mismatch: expected=${JSON.stringify(command.expectedBefore)} got=${JSON.stringify(currentValue)}`);
  }
  return command.after;
}

export function applyInverse(currentValue, command) {
  if (currentValue !== command.after) {
    throw new Error(
      `inverse cannot apply: current=${JSON.stringify(currentValue)} after=${JSON.stringify(command.after)}`);
  }
  return command.before;
}
