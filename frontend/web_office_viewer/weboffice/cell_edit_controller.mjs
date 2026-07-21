/* cell_edit_controller — 인라인 셀 편집 제어 (cell_edit_state 위).
 *
 * 편집은 EditCommand 로만 포착(원본 무수정). 뷰(table_view)는 순수 렌더라,
 * 편집 override 는 getCellText 콜백으로 주입한다.
 */
import {
  makeEditorState, selectCell, enterCellEdit, cancelCellEdit,
  commitCellText, undo, redo,
} from "../cell_edit_state.mjs";

export function createCellEditController(documentModel) {
  let state = makeEditorState(documentModel);
  const editedIds = new Set();

  const cellOf = (id) =>
    state.documentModel.cells.find((c) => c.cellId === id);

  return {
    getState: () => state,
    editedIds,
    // 편집된 셀만 현재 텍스트 반환(뷰 override), 그 외 null → 원본 문단 렌더
    getCellText(cellId) {
      if (!editedIds.has(cellId)) return null;
      const c = cellOf(cellId);
      return c ? c.text : "";
    },
    startEdit(cellId, tdEl, rerender) {
      const cell = cellOf(cellId);
      if (!cell) return;
      state = enterCellEdit(selectCell(state, cellId));
      const inp = document.createElement("input");
      inp.className = "wo-cell-inp";
      inp.value = cell.text || "";
      tdEl.classList.add("wo-editing");
      tdEl.innerHTML = "";
      tdEl.appendChild(inp);
      inp.focus();
      inp.select();
      let done = false;
      const commit = () => {
        if (done) return;
        done = true;
        const r = commitCellText(state, cellId, inp.value);
        state = r.state;
        if (r.command) editedIds.add(cellId);
        rerender();
      };
      inp.addEventListener("keydown", (e) => {
        if (e.key === "Enter") { e.preventDefault(); commit(); }
        else if (e.key === "Escape") {
          done = true; state = cancelCellEdit(state); rerender();
        }
      });
      inp.addEventListener("blur", commit);
    },
    undo(rerender) {
      const r = undo(state);
      if (r.command) { state = r.state; rerender(); }
    },
    redo(rerender) {
      const r = redo(state);
      if (r.command) {
        state = r.state; editedIds.add(r.command.targetId); rerender();
      }
    },
    canUndo: () => state.undoStack.length > 0,
    canRedo: () => state.redoStack.length > 0,
    commandLog: () => state.commandLog,
    dirty: () => state.dirty,
    cellCount: () => state.documentModel.cells.length,
  };
}
