/* app — 모듈 배선. 뷰어(document_view) + 편집기(controllers)를 얇게 연결.
 *
 * 이 파일은 DOM 이벤트 배선과 재렌더 orchestration 만 담당한다. 렌더/편집/
 * 저장/업로드 로직은 각 모듈에 있다.
 */
import { renderDocument } from "./document_view.mjs";
import { createCellEditController } from "./cell_edit_controller.mjs";
import { createSaveController } from "./save_controller.mjs";
import { createUploadController } from "./upload_controller.mjs";

const SAMPLE = "tests/fixtures/hwpx/corpus/fx_metadata_form.hwpx";

export function mountWebOffice(root) {
  const $ = (sel) => root.querySelector(sel);
  let loaded = null, cell = null, save = null;

  const setStatus = (k, msg) => {
    const e = $("[data-role=status]");
    e.dataset.k = k; e.textContent = msg;
  };
  const guides = () => $("[data-role=guides]").checked;

  function render() {
    const sheet = $("[data-role=sheet]");
    if (!loaded) {
      sheet.innerHTML = '<p class="wo-empty">문서 없음.</p>';
      renderSide();
      return;
    }
    sheet.innerHTML = renderDocument(loaded.renderPayload, {
      guides: guides(),
      getCellText: (id) => (cell ? cell.getCellText(id) : null),
      editableCell: () => true,
    });
    sheet.querySelectorAll("td[data-cell-id]").forEach((td) => {
      td.addEventListener("click",
        () => cell.startEdit(td.dataset.cellId, td, render));
    });
    renderSide();
  }

  function renderSide() {
    $("[data-role=metrics]").innerHTML = cell
      ? `<span>cells <b>${cell.cellCount()}</b></span>`
        + `<span>편집 <b>${cell.commandLog().length}</b></span>`
        + `<span>dirty <b>${cell.dirty()}</b></span>`
      : "<span>cells <b>0</b></span>";
    const log = cell ? cell.commandLog() : [];
    $("[data-role=log]").innerHTML = log.length
      ? log.map((c) =>
        `<li><span class="wo-ct">${c.commandType}</span> `
        + `<span class="wo-muted">${(c.before || "").slice(0, 12)}`
        + `→${(c.after || "").slice(0, 12)}</span></li>`).join("")
      : '<li class="wo-muted">편집 없음</li>';
    $("[data-role=save]").disabled = !(cell && cell.commandLog().length > 0);
    $("[data-role=undo]").disabled = !(cell && cell.canUndo());
    $("[data-role=redo]").disabled = !(cell && cell.canRedo());
    $("[data-role=download]").disabled = !(save && save.lastOutput());
  }

  function onLoaded(d) {
    loaded = d;
    cell = createCellEditController(d.documentModel);
    save = createSaveController({
      getState: () => cell.getState(),
      getSourcePath: () => loaded.sourcePath,
    });
    const sm = d.summary || {};
    setStatus("ok",
      `불러옴 · 표 ${sm.tables ?? "?"} · 셀 ${sm.cells ?? "?"} · 원본 무수정`);
    render();
  }

  const upload = createUploadController({ onLoaded, setStatus });

  $("[data-role=pick]").addEventListener("click",
    () => $("[data-role=file]").click());
  $("[data-role=file]").addEventListener("change",
    (e) => upload.upload(e.target.files[0]));
  $("[data-role=sample]").addEventListener("click",
    () => upload.loadSample(SAMPLE));
  $("[data-role=undo]").addEventListener("click",
    () => cell && cell.undo(render));
  $("[data-role=redo]").addEventListener("click",
    () => cell && cell.redo(render));
  $("[data-role=guides]").addEventListener("change", render);
  $("[data-role=save]").addEventListener("click", async () => {
    if (!cell) return;
    setStatus("load", "저장 중(sandbox 사본 + readback 검증) …");
    const r = await save.save();
    if (!r.ok) setStatus("fail", "저장 거부: " + r.code);
    else setStatus("ok",
      "저장 완료 — verify7 통과 · 원본 무수정 · 편집본 다운로드 가능.");
    renderSide();
  });
  $("[data-role=download]").addEventListener("click", () => {
    const u = save && save.downloadUrl();
    if (u) window.location = u;
  });

  const drop = $("[data-role=drop]");
  ["dragenter", "dragover"].forEach((ev) =>
    drop.addEventListener(ev, (e) => {
      e.preventDefault(); drop.classList.add("wo-over");
    }));
  ["dragleave", "drop"].forEach((ev) =>
    drop.addEventListener(ev, (e) => {
      e.preventDefault(); drop.classList.remove("wo-over");
    }));
  drop.addEventListener("drop", (e) => {
    const f = e.dataTransfer && e.dataTransfer.files
      && e.dataTransfer.files[0];
    if (f) upload.upload(f);
  });

  render();
  window.__weReady = true;
}
