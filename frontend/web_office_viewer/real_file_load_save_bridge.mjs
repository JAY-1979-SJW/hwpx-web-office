import { makeEditorState } from "./cell_edit_state.mjs";
import {
  buildCellSaveApplyRequest,
  postCellSaveApply,
} from "./save_apply_bridge.mjs";

export const HWPX_EDITOR_LOAD_OPERATION = "HWPX_EDITOR_LOAD";
export const DEFAULT_HWPX_LOAD_ENDPOINT = "/api/web-office/hwpx-load";

export function unwrapBackendLoadResponse(body) {
  if (body && body.status === "SUCCESS" && body.data) return body.data;
  return body;
}

export function buildHwpxEditorLoadRequest({ sourcePath }) {
  if (!sourcePath || typeof sourcePath !== "string") {
    throw new Error("sourcePath is required");
  }
  return {
    operation: HWPX_EDITOR_LOAD_OPERATION,
    sourcePath,
  };
}

export function createEditorStateFromLoadResponse(response) {
  if (!response || response.verdict !== "PASS") {
    throw new Error("load response must be PASS");
  }
  if (!response.documentModel || !Array.isArray(response.documentModel.cells)) {
    throw new Error("load response documentModel.cells is required");
  }
  const state = makeEditorState(response.documentModel);
  return {
    sourcePath: response.sourcePath,
    renderPayload: response.renderPayload,
    summary: response.summary,
    state,
  };
}

export async function postHwpxEditorLoad({
  sourcePath,
  endpoint = DEFAULT_HWPX_LOAD_ENDPOINT,
  fetchImpl = globalThis.fetch,
}) {
  if (typeof fetchImpl !== "function") {
    throw new Error("fetch implementation is required");
  }
  const payload = buildHwpxEditorLoadRequest({ sourcePath });
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
    throw new Error(`hwpx editor load failed: ${detail}`);
  }
  return createEditorStateFromLoadResponse(unwrapBackendLoadResponse(body));
}

export function buildSaveRequestFromLoadedEditor({
  loaded,
  requestId,
  dryRunOnly = false,
}) {
  if (!loaded || !loaded.state) {
    throw new Error("loaded editor state is required");
  }
  return buildCellSaveApplyRequest({
    state: loaded.state,
    sourcePath: loaded.sourcePath,
    requestId,
    dryRunOnly,
  });
}

export async function postLoadedEditorSave({
  loaded,
  requestId,
  dryRunOnly = false,
  endpoint,
  fetchImpl,
}) {
  if (!loaded || !loaded.state) {
    throw new Error("loaded editor state is required");
  }
  return postCellSaveApply({
    state: loaded.state,
    sourcePath: loaded.sourcePath,
    requestId,
    dryRunOnly,
    endpoint,
    fetchImpl,
  });
}
