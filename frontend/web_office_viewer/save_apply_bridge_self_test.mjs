#!/usr/bin/env node
import assert from "node:assert/strict";

import { makeEditorState, selectCell, enterCellEdit, commitCellText }
  from "./cell_edit_state.mjs";
import {
  buildCellSaveApplyRequest, postCellSaveApply, CELL_SAVE_APPLY_OPERATION,
} from "./save_apply_bridge.mjs";

const sampleDoc = {
  sourceDocumentHash: "abc123",
  tables: [{ tableId: "t_s0_000" }],
  cells: [
    { cellId: "cell_t_s0_000_r0_c0", tableId: "t_s0_000",
      row: 0, col: 0, text: "before" },
  ],
};

let state = makeEditorState(sampleDoc);
assert.equal(buildCellSaveApplyRequest({
  state, sourcePath: "tests/fixtures/hwpx/corpus/fx_metadata_form.hwpx",
}).status, "NOOP");

state = selectCell(state, "cell_t_s0_000_r0_c0");
state = enterCellEdit(state);
state = commitCellText(state, "cell_t_s0_000_r0_c0", "after").state;

const payload = buildCellSaveApplyRequest({
  state,
  sourcePath: "tests/fixtures/hwpx/corpus/fx_metadata_form.hwpx",
  requestId: "front-self-test",
});
assert.equal(payload.operation, CELL_SAVE_APPLY_OPERATION);
assert.equal(payload.sourceDocumentHash, "abc123");
assert.equal(payload.commandLog.length, 1);
assert.equal(payload.commandLog[0].commandType, "SET_CELL_TEXT");

let posted = null;
const result = await postCellSaveApply({
  state,
  sourcePath: "tests/fixtures/hwpx/corpus/fx_metadata_form.hwpx",
  requestId: "front-self-test",
  fetchImpl: async (url, options) => {
    posted = { url, options };
    return {
      ok: true,
      async json() {
        return { verdict: "PASS", outputCreated: true };
      },
    };
  },
});
assert.equal(posted.url, "/api/web-office/cell-save-apply");
assert.equal(JSON.parse(posted.options.body).operation, CELL_SAVE_APPLY_OPERATION);
assert.equal(result.verdict, "PASS");

console.log(JSON.stringify({
  task: "HWPX-FRONTEND-SAVE-APPLY-BRIDGE-43",
  verdict: "PASS",
}));
