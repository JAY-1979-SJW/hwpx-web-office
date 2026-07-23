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
  // 클릭 편집 가능 칸 분류 — 파서(서버)가 정확 분류한 isEditable 을
  // 단일 진실로 사용한다(비헤더+비병합커버 — 텍스트 유무는 안 봄).
  // isInputCell(AI 자동입력 대상, 빈칸 전용)과는 목적이 다르다: 이미
  // 값이 있는 칸도 사람은 클릭해 고치거나 지울 수 있어야 한다.
  // 서버 필드가 없는 구버전 payload 만 프런트 휴리스틱으로 폴백.
  // header 원시 속성은 "0"(문자열)도 오므로 truthy 검사 금지 —
  // 정규화 불리언(headerCell) 또는 명시 "1"/"true" 만 헤더로 본다.
  const _isHeader = (c) => c.headerCell === true
    || c.header === "1" || c.header === "true";
  const _legacyEditable = (c) => !_isHeader(c) && !c.isCoveredByMerge;
  const inputCells = new Set(
    (documentModel.cells || [])
      .filter((c) => (typeof c.isEditable === "boolean")
        ? c.isEditable : _legacyEditable(c))
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
    // 마커 문서([입력필요: ...])의 필드 라벨 — placeholder 표시용.
    inputLabel(cellId) {
      const c = cellOf(cellId);
      return (c && c.inputLabel) ? c.inputLabel : null;
    },
    // 상시 입력필드용 — 셀의 현재 텍스트(편집 반영값)
    currentText(cellId) {
      const c = cellOf(cellId);
      return c ? (c.text || "") : "";
    },
    // 상시 입력필드용 직접 커밋 — 값이 바뀐 경우에만 command 생성.
    // (DOM 재구축 없이 필드가 값을 유지하므로 rerender 는 호출자가 결정)
    setCellText(cellId, value) {
      const cell = cellOf(cellId);
      if (!cell) return false;
      if ((cell.text || "") === value) return false;
      state = enterCellEdit(selectCell(state, cellId));
      const r = commitCellText(state, cellId, value);
      state = r.state;
      if (r.command) editedIds.add(cellId);
      return !!r.command;
    },
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
