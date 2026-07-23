export const CELL_SAVE_APPLY_OPERATION = "CELL_SAVE_APPLY";
export const DEFAULT_CELL_SAVE_ENDPOINT = "/api/web-office/cell-save-apply";

export function unwrapBackendSaveApplyResponse(body) {
  if (body && body.status === "SUCCESS" && body.data) return body.data;
  return body;
}

export function buildCellSaveApplyRequest({
  state,
  sourcePath,
  requestId,
  dryRunOnly = false,
}) {
  if (!state || !Array.isArray(state.commandLog)) {
    throw new Error("state.commandLog is required");
  }
  if (state.commandLog.length === 0) {
    return { status: "NOOP", reason: "commandLog empty" };
  }
  if (!sourcePath || typeof sourcePath !== "string") {
    throw new Error("sourcePath is required");
  }
  return {
    operation: CELL_SAVE_APPLY_OPERATION,
    requestId,
    sourcePath,
    sourceDocumentHash: state.sourceDocumentHash,
    dryRunOnly,
    commandLog: state.commandLog,
    // 대표님 지시(2026-07-24 정책 개정) — 검증 통과 결과를 원본 파일에
    // 직접 반영한다(sandbox 사본 체이닝 대신).
    editInPlace: true,
  };
}

export async function postCellSaveApply({
  state,
  sourcePath,
  endpoint = DEFAULT_CELL_SAVE_ENDPOINT,
  requestId,
  dryRunOnly = false,
  fetchImpl = globalThis.fetch,
}) {
  const payload = buildCellSaveApplyRequest({
    state, sourcePath, requestId, dryRunOnly,
  });
  if (payload.status === "NOOP") return payload;
  if (typeof fetchImpl !== "function") {
    throw new Error("fetch implementation is required");
  }
  const response = await fetchImpl(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const body = await response.json();
  if (!response.ok) {
    const detail = body && (body.reason || body.errors?.[0]?.message)
      ? (body.reason || body.errors[0].message)
      : response.statusText;
    throw new Error(`cell save apply failed: ${detail}`);
  }
  return unwrapBackendSaveApplyResponse(body);
}
