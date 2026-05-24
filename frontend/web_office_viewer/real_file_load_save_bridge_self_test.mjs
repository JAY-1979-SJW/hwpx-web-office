#!/usr/bin/env node
import assert from "node:assert/strict";

import {
  commitCellText,
  enterCellEdit,
  selectCell,
} from "./cell_edit_state.mjs";
import {
  buildHwpxEditorLoadRequest,
  buildSaveRequestFromLoadedEditor,
  createEditorStateFromLoadResponse,
  postHwpxEditorLoad,
  postLoadedEditorSave,
} from "./real_file_load_save_bridge.mjs";

const sourcePath = "tests/fixtures/hwpx/corpus/fx_metadata_form.hwpx";
const loadResponse = {
  verdict: "PASS",
  sourcePath,
  documentModel: {
    sourceDocumentHash: "sha-load-44",
    sourceRef: { sha256: "sha-load-44" },
    tables: [{ tableId: "t_s0_000" }],
    cells: [
      { cellId: "cell_t_s0_000_r3_c0", tableId: "t_s0_000",
        row: 3, col: 0, text: "before", header: "0", headerCell: false },
      { cellId: "cell_t_s0_000_r0_c0", tableId: "t_s0_000",
        row: 0, col: 0, text: "header", header: "1", headerCell: true },
    ],
  },
  renderPayload: { editable: false, sourceRef: { sha256: "sha-load-44", path: sourcePath } },
  summary: { cells: 2, headerCells: 1 },
};

assert.deepEqual(
  buildHwpxEditorLoadRequest({ sourcePath }),
  { operation: "HWPX_EDITOR_LOAD", sourcePath },
);

const loaded = createEditorStateFromLoadResponse(loadResponse);
assert.equal(loaded.sourcePath, sourcePath);
assert.equal(loaded.state.sourceDocumentHash, "sha-load-44");
assert.equal(loaded.summary.headerCells, 1);

let state = selectCell(loaded.state, "cell_t_s0_000_r3_c0");
state = enterCellEdit(state);
state = commitCellText(state, "cell_t_s0_000_r3_c0", "after").state;
const edited = { ...loaded, state };
const savePayload = buildSaveRequestFromLoadedEditor({
  loaded: edited,
  requestId: "load-save-44",
});
assert.equal(savePayload.operation, "CELL_SAVE_APPLY");
assert.equal(savePayload.sourcePath, sourcePath);
assert.equal(savePayload.commandLog.length, 1);
assert.equal(savePayload.commandLog[0].after, "after");

const loadedViaPost = await postHwpxEditorLoad({
  sourcePath,
  fetchImpl: async (_url, options) => {
    assert.equal(JSON.parse(options.body).operation, "HWPX_EDITOR_LOAD");
    return { ok: true, async json() { return loadResponse; } };
  },
});
assert.equal(loadedViaPost.state.documentModel.cells.length, 2);

const saveResult = await postLoadedEditorSave({
  loaded: edited,
  requestId: "load-save-44",
  fetchImpl: async (_url, options) => {
    const body = JSON.parse(options.body);
    assert.equal(body.operation, "CELL_SAVE_APPLY");
    assert.equal(body.commandLog[0].after, "after");
    return { ok: true, async json() { return { verdict: "PASS" }; } };
  },
});
assert.equal(saveResult.verdict, "PASS");

console.log(JSON.stringify({
  task: "HWPX-EDITOR-REAL-FILE-LOAD-SAVE-44",
  verdict: "PASS",
}));
