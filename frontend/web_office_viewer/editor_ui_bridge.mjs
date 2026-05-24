import {
  postHwpxEditorLoad,
  postLoadedEditorSave,
} from "./real_file_load_save_bridge.mjs";
import {
  commitCellText,
  enterCellEdit,
  selectCell,
} from "./cell_edit_state.mjs";

const SAFE_SAMPLE_SOURCE = "tests/fixtures/hwpx/corpus/fx_metadata_form.hwpx";

function text(value) {
  return String(value ?? "");
}

function escapeHtml(value) {
  return text(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function setStatus(root, kind, message) {
  const el = root.querySelector("[data-role='status']");
  el.dataset.status = kind;
  el.textContent = message;
}

function findActiveCell(state) {
  return state.documentModel.cells.find((cell) => cell.cellId === state.activeCellId) || null;
}

function cellLabel(cell) {
  return `R${Number(cell.row) + 1} C${Number(cell.col) + 1}`;
}

function groupedTables(state) {
  const cellsByTable = new Map();
  for (const cell of state.documentModel.cells || []) {
    if (!cellsByTable.has(cell.tableId)) cellsByTable.set(cell.tableId, []);
    cellsByTable.get(cell.tableId).push(cell);
  }
  return [...cellsByTable.entries()].map(([tableId, cells]) => ({
    tableId,
    cells: cells.sort((a, b) => (a.row - b.row) || (a.col - b.col)),
  }));
}

function renderCells(root, appState) {
  const list = root.querySelector("[data-role='cell-list']");
  const loaded = appState.loaded;
  if (!loaded) {
    list.innerHTML = "<div class='wo-empty'>No document loaded.</div>";
    return;
  }
  const parts = [];
  for (const table of groupedTables(loaded.state)) {
    parts.push(`<section class="wo-table-group"><h2>${escapeHtml(table.tableId)}</h2><div class="wo-cell-grid">`);
    for (const cell of table.cells) {
      const active = loaded.state.activeCellId === cell.cellId ? " data-active='true'" : "";
      const label = cellLabel(cell);
      parts.push(
        `<button class="wo-cell-button" type="button" data-cell-id="${escapeHtml(cell.cellId)}"${active}>` +
          `<span>${escapeHtml(label)}</span><strong>${escapeHtml(cell.text)}</strong>` +
        "</button>",
      );
    }
    parts.push("</div></section>");
  }
  list.innerHTML = parts.join("");
}

function renderInspector(root, appState) {
  const loaded = appState.loaded;
  const active = loaded ? findActiveCell(loaded.state) : null;
  root.querySelector("[data-role='cell-count']").textContent =
    loaded ? String(loaded.state.documentModel.cells.length) : "0";
  root.querySelector("[data-role='command-count']").textContent =
    loaded ? String(loaded.state.commandLog.length) : "0";
  root.querySelector("[data-role='dirty-state']").textContent =
    loaded && loaded.state.dirty ? "dirty" : "clean";

  const editor = root.querySelector("[data-role='cell-editor']");
  const input = root.querySelector("[data-role='cell-text']");
  const label = root.querySelector("[data-role='active-cell']");
  if (!active) {
    editor.dataset.enabled = "false";
    input.value = "";
    input.disabled = true;
    label.textContent = "No cell selected";
    return;
  }
  editor.dataset.enabled = "true";
  input.disabled = false;
  input.value = text(active.text);
  label.textContent = cellLabel(active);
}

function render(root, appState) {
  renderCells(root, appState);
  renderInspector(root, appState);
  root.querySelector("[data-role='save']").disabled =
    !appState.loaded || appState.loaded.state.commandLog.length === 0 || appState.busy;
  root.querySelector("[data-role='load']").disabled = appState.busy;
  root.querySelector("[data-role='commit']").disabled =
    appState.busy || !appState.loaded || !appState.loaded.state.activeCellId;
}

async function loadSample(root, appState) {
  appState.busy = true;
  render(root, appState);
  setStatus(root, "loading", "Loading sample document...");
  try {
    const loaded = await postHwpxEditorLoad({ sourcePath: SAFE_SAMPLE_SOURCE });
    appState.loaded = loaded;
    setStatus(root, "success", "Document loaded from backend.");
  } catch (error) {
    setStatus(root, "fail", error.message || "Load failed.");
  } finally {
    appState.busy = false;
    render(root, appState);
  }
}

async function saveChanges(root, appState) {
  appState.busy = true;
  render(root, appState);
  setStatus(root, "loading", "Saving command log...");
  try {
    const result = await postLoadedEditorSave({
      loaded: appState.loaded,
      requestId: `ui-${Date.now()}`,
    });
    if (result && result.verdict && result.verdict !== "PASS") {
      setStatus(root, "blocked", "Save was blocked by backend validation.");
    } else {
      appState.loaded = {
        ...appState.loaded,
        state: {
          ...appState.loaded.state,
          commandLog: [],
          undoStack: [],
          redoStack: [],
          dirty: false,
        },
      };
      setStatus(root, "success", "Backend save apply completed.");
    }
  } catch (error) {
    setStatus(root, "fail", error.message || "Save failed.");
  } finally {
    appState.busy = false;
    render(root, appState);
  }
}

export function mountWebOfficeEditor(root) {
  const appState = { loaded: null, busy: false };
  root.innerHTML = `
    <div class="web-office-editor">
      <header class="wo-appbar">
        <div>
          <h1>HWPX Web Office</h1>
          <p>Sandbox editor bridge</p>
        </div>
        <div class="wo-actions">
          <button type="button" data-role="load">Load sample</button>
          <button type="button" data-role="save" disabled>Save apply</button>
        </div>
      </header>
      <div class="wo-status" data-role="status" data-status="idle">Ready.</div>
      <main class="wo-layout">
        <section class="wo-document" data-role="cell-list"></section>
        <aside class="wo-inspector">
          <div class="wo-metrics">
            <span><b data-role="cell-count">0</b> cells</span>
            <span><b data-role="command-count">0</b> commands</span>
            <span data-role="dirty-state">clean</span>
          </div>
          <section class="wo-editor-panel" data-role="cell-editor" data-enabled="false">
            <h2 data-role="active-cell">No cell selected</h2>
            <textarea data-role="cell-text" rows="8" disabled></textarea>
            <button type="button" data-role="commit" disabled>Commit cell text</button>
          </section>
        </aside>
      </main>
    </div>`;

  root.querySelector("[data-role='load']").addEventListener("click", () => loadSample(root, appState));
  root.querySelector("[data-role='save']").addEventListener("click", () => saveChanges(root, appState));
  root.querySelector("[data-role='commit']").addEventListener("click", () => {
    if (!appState.loaded) return;
    const active = findActiveCell(appState.loaded.state);
    if (!active) return;
    const nextText = root.querySelector("[data-role='cell-text']").value;
    let state = selectCell(appState.loaded.state, active.cellId);
    state = enterCellEdit(state);
    const result = commitCellText(state, active.cellId, nextText);
    appState.loaded = { ...appState.loaded, state: result.state };
    setStatus(root, result.command ? "success" : "idle", result.command ? "Cell command appended." : "No cell change.");
    render(root, appState);
  });
  root.querySelector("[data-role='cell-list']").addEventListener("click", (event) => {
    const button = event.target.closest("[data-cell-id]");
    if (!button || !appState.loaded) return;
    appState.loaded = {
      ...appState.loaded,
      state: selectCell(appState.loaded.state, button.dataset.cellId),
    };
    setStatus(root, "idle", "Cell selected.");
    render(root, appState);
  });
  render(root, appState);
}
