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
  // 로드 시점 빈 셀 = 입력칸(값 채우는 칸). 값 채운 뒤에도 입력칸으로 유지
  // 하려고 원본 기준으로 스냅샷(편집으로 텍스트가 바뀌어도 분류 불변).
  const inputCells = new Set(
    (documentModel.cells || [])
      .filter((c) => !((c.text || "").trim()))
      .map((c) => c.cellId));

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
    // 로드 시점 빈 셀 = 입력칸(라벨 아님). 값 채운 뒤에도 true 유지.
    isInputCell: (cellId) => inputCells.has(cellId),
    startEdit(cellId, tdEl, rerender, opts = {}) {
      const cell = cellOf(cellId);
      if (!cell) return;
      state = enterCellEdit(selectCell(state, cellId));
      const inp = document.createElement("input");
      inp.className = "wo-cell-inp";
      // 라벨(원래 문구) 보호: 기본은 빈 입력에서 시작(값만 입력). 원래 문구를
      // 수정하려면 prefill:true(더블클릭)로 기존 텍스트를 불러온다.
      // prefillText 가 명시되면 그 값을 우선 사용 — 라벨은 정규화된 cell.text
      // 대신 충실 원문(자간·공백 원형)을 넣어, 편집 시 미편집 부분이 정규화
      // 텍스트로 덮여 자간·공백이 소실되는 것을 방지한다.
      inp.value = (opts.prefillText != null)
        ? opts.prefillText
        : (opts.prefill ? (cell.text || "") : "");
      const initial = inp.value;   // 열림 시점 값 — 무변경 blur 는 편집 아님
      tdEl.classList.add("wo-editing");
      tdEl.innerHTML = "";
      tdEl.appendChild(inp);
      inp.focus();
      inp.select();
      let done = false;
      const commit = () => {
        if (done) return;
        done = true;
        // 열렸으나 그대로면(prefill 이 정규화≠충실이어도) 편집 아님 — command
        // 미생성·원본 무변경. (commitCellText 의 before 는 정규화 cell.text 라
        // 여기서 initial 대비로 무변경을 판정해야 충실 prefill 과 어긋나지 않음)
        if (inp.value === initial) {
          state = cancelCellEdit(state); rerender(); return;
        }
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
