/* app — 모듈 배선. 뷰어(document_view) + 편집기(controllers)를 얇게 연결.
 *
 * 이 파일은 DOM 이벤트 배선과 재렌더 orchestration 만 담당한다. 렌더/편집/
 * 저장/업로드 로직은 각 모듈에 있다.
 */
import { renderDocument } from "./document_view.mjs";
import { renderCoordinateLayout, autoFitLines }
  from "./coordinate_renderer.mjs";
import { createCellEditController } from "./cell_edit_controller.mjs";
import { createSaveController } from "./save_controller.mjs";
import { createUploadController } from "./upload_controller.mjs";

const SAMPLE = "tests/fixtures/hwpx/corpus/fx_metadata_form.hwpx";
const LAYOUT_ENDPOINT = "/api/web-office/hwpx-layout";

export function mountWebOffice(root) {
  const $ = (sel) => root.querySelector(sel);
  let loaded = null, cell = null, save = null;
  let coordLayout = null;   // 한컴 좌표 기반 faithful 레이아웃

  const setStatus = (k, msg) => {
    const e = $("[data-role=status]");
    e.dataset.k = k; e.textContent = msg;
  };
  // 충실 보기(좌표 렌더러)가 유일 표시 모드 — 원본 배치 충실 재현 + 셀 직접
  // 편집. 좌표 레이아웃이 없는 문서(lineseg 미저장)만 흐름 렌더러로 폴백.
  const faithful = () => coordLayout != null;

  async function fetchLayout(sourcePath) {
    if (!sourcePath) return null;
    try {
      const res = await fetch(LAYOUT_ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sourcePath }),
      });
      const env = await res.json();
      const d = (env && env.data) || env || {};
      if ((env && env.status && env.status !== "SUCCESS")
        || d.verdict === "REJECTED" || d.error) return null;
      return d;
    } catch (_e) { return null; }
  }

  // 좌표 레이아웃에서 셀의 충실 원문(정규화 이전, 줄 순서대로) 복원. 라벨
  // 편집 prefill 에 사용 — 모델 cell.text 는 라벨 매칭용으로 정규화(공백
  // 병합·한글 사이 공백 제거)돼 있어, 그대로 편집하면 자간·공백이 소실된다.
  // 미저장/흐름 폴백 문서(cellId 라인 없음)면 null → 기존 동작 유지.
  function faithfulCellText(id) {
    if (!coordLayout || !id) return null;
    const ls = (coordLayout.lines || []).filter((l) => l.cellId === id);
    if (!ls.length) return null;
    ls.sort((a, b) => (a.y - b.y) || (a.x - b.x));
    return ls.map((l) => l.text || "").join("\n");
  }

  function render() {
    const sheet = $("[data-role=sheet]");
    if (!loaded) {
      sheet.innerHTML = '<p class="wo-empty">문서 없음.</p>';
      renderSide();
      return;
    }
    if (coordLayout) {
      // 한컴 좌표 그대로 절대배치 — 원본 배치·서식 충실 재현 + 셀 직접 편집.
      // 편집된 셀은 새 텍스트 표시(getCellText), 셀 박스 클릭 시 인라인 편집.
      sheet.innerHTML = renderCoordinateLayout(coordLayout, {
        editable: true,
        getCellText: (id) => (cell ? cell.getCellText(id) : null),
      });
      autoFitLines(sheet);
      sheet.querySelectorAll(".co-box[data-cell-id]").forEach((box) => {
        const id = box.dataset.cellId;
        const isInput = cell.isInputCell(id);   // 로드 시 빈칸 = 입력칸
        box.classList.add(isInput ? "wo-input" : "wo-label");
        if (isInput) {
          // 입력칸: 단일 클릭으로 값 입력. prefill=현재값(빈칸은 빈 입력에서
          // 시작, 이미 채운 칸은 값 유지 — 재클릭 시 빈값 커밋으로 소실 방지).
          box.addEventListener("click", () =>
            cell.startEdit(id, box, render, { prefill: true }));
        }
        // 라벨(원래 문구): 더블클릭으로만 수정. 편집된 적 있으면 현재값,
        // 아니면 충실 원문(정규화 아님)을 prefill — 자간·공백 원형 유지.
        box.addEventListener("dblclick", (e) => {
          e.preventDefault();
          const edited = cell.getCellText(id);
          const pf = edited != null ? edited : faithfulCellText(id);
          cell.startEdit(id, box, render, { prefill: true, prefillText: pf });
        });
      });
      root.classList.add("wo-faithful");
    } else {
      // 편집 모드 — 흐름 렌더러 + 셀 클릭 편집
      root.classList.remove("wo-faithful");
      sheet.innerHTML = renderDocument(loaded.renderPayload, {
        guides: true,
        getCellText: (id) => (cell ? cell.getCellText(id) : null),
        editableCell: () => true,
      });
      sheet.querySelectorAll("td[data-cell-id]").forEach((td) => {
        td.addEventListener("click",
          () => cell.startEdit(td.dataset.cellId, td, render));
      });
    }
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

  async function onLoaded(d) {
    loaded = d;
    coordLayout = null;
    cell = createCellEditController(d.documentModel);
    save = createSaveController({
      getState: () => cell.getState(),
      getSourcePath: () => loaded.sourcePath,
    });
    const sm = d.summary || {};
    setStatus("load", "좌표 레이아웃(원본 배치) 불러오는 중 …");
    render();  // 즉시 1차 렌더(레이아웃 오기 전엔 흐름/빈 화면)
    coordLayout = await fetchLayout(d.sourcePath);
    setStatus("ok",
      `불러옴 · 표 ${sm.tables ?? "?"} · 셀 ${sm.cells ?? "?"} · `
      + (coordLayout ? "원본 배치 충실 재현" : "흐름 보기") + " · 원본 무수정");
    render();  // 레이아웃 반영 재렌더
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

  // 딥링크 자동 로드: #load=<프로젝트 상대경로> — 임의 프로젝트 문서 열기.
  // (임의 디스크 업로드는 보안 홀드라 미지원; 상대경로 로드만.)
  function loadFromHash() {
    const m = /[#&]load=([^&]+)/.exec(location.hash || "");
    if (m) upload.loadSample(decodeURIComponent(m[1]));
  }
  window.addEventListener("hashchange", loadFromHash);

  render();
  loadFromHash();
  window.__weReady = true;
}
