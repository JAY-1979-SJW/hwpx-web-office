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
const TRUTH_ENDPOINT = "/api/web-office/truth-page";

export function mountWebOffice(root) {
  const $ = (sel) => root.querySelector(sel);
  let loaded = null, cell = null, save = null;
  let coordLayout = null;   // 한컴 좌표 기반 faithful 레이아웃
  let truthBase = null;     // '원본 그대로' 모드 — 한컴 실렌더 배경 URL 접두

  const setStatus = (k, msg) => {
    const e = $("[data-role=status]");
    e.dataset.k = k; e.textContent = msg;
  };
  // 충실 보기(좌표 렌더러)가 유일 표시 모드 — 원본 배치 충실 재현 + 셀 직접
  // 편집. 좌표 레이아웃이 없는 문서(lineseg 미저장)만 흐름 렌더러로 폴백.
  const faithful = () => coordLayout != null;

  async function fetchLayout(sourcePath) {
    if (!sourcePath) return null;
    // 서버 재기동 순간 등 일시 실패 시 짧게 재시도 — 실패로 흐름(blob)
    // 폴백에 떨어지면 "서식이 뭉개진" 화면이 되므로 충실 보기를 우선 확보.
    for (let attempt = 0; attempt < 3; attempt++) {
      try {
        const res = await fetch(LAYOUT_ENDPOINT, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ sourcePath }),
        });
        const env = await res.json();
        const d = (env && env.data) || env || {};
        if ((env && env.status && env.status !== "SUCCESS")
          || d.verdict === "REJECTED" || d.error) return null;  // 명시 거부는 재시도 안 함
        return d;
      } catch (_e) {
        if (attempt < 2) {
          await new Promise((r) => setTimeout(r, 1200 * (attempt + 1)));
        }
      }
    }
    return null;
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
        // 입력칸은 상시 필드가 값을 표시하므로 렌더러 오버레이 제외(이중
        // 표시 방지). 라벨 편집만 렌더러 오버레이 경로 사용.
        getCellText: (id) => (cell && !cell.isInputCell(id)
          ? cell.getCellText(id) : null),
        truthBase,   // 가용 시 '원본 그대로'(한컴 실렌더 배경 + 편집 오버레이)
      });
      autoFitLines(sheet);
      // 상시 입력필드 — XML 에서 입력칸(로드 시 빈 셀)을 이미 알므로,
      // 클릭 시 생성이 아니라 로드 즉시 모든 입력칸에 실제 <input> 을
      // 배치한다(커서 대기·Tab 이동·Enter 다음 칸). 문서 순서(페이지→
      // 위→왼쪽)로 tabindex 를 매겨 폼처럼 채워내려갈 수 있다.
      // 색칠 셀 배제 — 유채색 채움(간트 진행바·차트 칸)만 입력칸에서
      // 제외한다. 무채색 연회색(#F2F2F2 등)은 일반 셀 배경이므로 유지.
      // 판정: RGB 채도(chroma = max-min) > 12 이면 유채색.
      const _chromatic = (hex) => {
        const m = /^#?([0-9a-f]{6})$/i.exec(String(hex || ""));
        if (!m) return false;
        const v = parseInt(m[1], 16);
        const r = (v >> 16) & 255, g = (v >> 8) & 255, b = v & 255;
        return (Math.max(r, g, b) - Math.min(r, g, b)) > 12;
      };
      const filledIds = new Set();
      for (const pdp of (coordLayout.pagesDetail || [])) {
        for (const b of pdp.boxes) {
          if (b.cellId && _chromatic(b.fill)) filledIds.add(b.cellId);
        }
      }
      const inputBoxes = [];
      sheet.querySelectorAll(".co-box[data-cell-id]").forEach((box) => {
        const id = box.dataset.cellId;
        const isInput = cell.isInputCell(id)
          && !filledIds.has(id);   // 로드 시 빈칸 + 무채움 = 입력칸
        box.classList.add(isInput ? "wo-input" : "wo-label");
        if (isInput && !box.dataset.frag) {
          const r = box.getBoundingClientRect();
          inputBoxes.push({ id, box, top: r.top, left: r.left });
        }
        // 라벨(원래 문구): 더블클릭으로만 수정. 편집된 적 있으면 현재값,
        // 아니면 충실 원문(정규화 아님)을 prefill — 자간·공백 원형 유지.
        if (!isInput) {
          box.addEventListener("dblclick", (e) => {
            e.preventDefault();
            const edited = cell.getCellText(id);
            const pf = edited != null ? edited : faithfulCellText(id);
            cell.startEdit(id, box, render,
              { prefill: true, prefillText: pf });
          });
        }
      });
      inputBoxes.sort((a, b) => (a.top - b.top) || (a.left - b.left));
      inputBoxes.forEach((it, idx) => {
        const inp = document.createElement("input");
        inp.className = "wo-fld";
        inp.tabIndex = idx + 1;
        inp.value = cell.currentText(it.id);
        inp.addEventListener("change", () => {
          if (cell.setCellText(it.id, inp.value)) renderSide();
        });
        inp.addEventListener("keydown", (e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            inp.dispatchEvent(new Event("change"));
            const nxt = sheet.querySelector(
              `.wo-fld[tabindex="${idx + 2}"]`);
            if (nxt) nxt.focus();
            else inp.blur();
          } else if (e.key === "Escape") {
            inp.value = cell.currentText(it.id);
            inp.blur();
          }
        });
        it.box.appendChild(inp);
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

  // '원본 그대로' 배경 준비 — 한컴 실렌더 페이지(서버 캐시). 첫 문서는
  // 서버에서 한컴 조판(수 초)이 돌 수 있어 비동기 프로브 후 재렌더한다.
  // 404(한컴 미설치 서비스 환경)면 좌표 렌더 그대로 — 무중단 폴백.
  async function probeTruth(sourcePath) {
    truthBase = null;
    if (!sourcePath) return;
    const base = `${TRUTH_ENDPOINT}?src=${encodeURIComponent(sourcePath)}&page=`;
    try {
      const res = await fetch(base + "1", { method: "GET" });
      if (res.ok) {
        // 배경 준비됨 → 레이아웃 재요청: 서버가 truth 격자선에 정합등록+
        // 스냅한 오버레이 좌표(truthAligned)를 내려준다.
        const aligned = await fetchLayout(loaded && loaded.sourcePath);
        if (aligned) coordLayout = aligned;
        // 안전 가드 — 한컴 쪽수와 우리 쪽수가 다르면 배경-오버레이 페이지
        // 대응이 어긋나므로 배경 모드를 켜지 않는다(좌표 렌더 유지).
        const hp = aligned && aligned.hancomPages;
        if (hp && aligned.pages !== hp) {
          truthBase = null;
          setStatus("ok", ($("[data-role=status]").textContent || "")
            + ` · 원본배경 보류(쪽수 ${aligned.pages}≠한컴 ${hp})`);
          render();
          return;
        }
        truthBase = base;
        setStatus("ok", ($("[data-role=status]").textContent || "")
          + " · 원본 실렌더 배경"
          + (aligned && aligned.truthAligned ? "(정렬)" : ""));
        render();
      }
    } catch (_e) { /* 폴백 유지 */ }
  }

  async function onLoaded(d) {
    loaded = d;
    coordLayout = null;
    truthBase = null;
    cell = createCellEditController(d.documentModel);
    save = createSaveController({
      getState: () => cell.getState(),
      getSourcePath: () => loaded.sourcePath,
    });
    const sm = d.summary || {};
    setStatus("load", "좌표 레이아웃(원본 배치) 불러오는 중 …");
    render();  // 즉시 1차 렌더(레이아웃 오기 전엔 흐름/빈 화면)
    coordLayout = await fetchLayout(d.sourcePath);
    // 자가진단 배지 — 서버가 로드마다 품질(물림/겹침)을 계산해 보낸다.
    // 이상 시 상태줄에 즉시 표기해 조용한 품질 저하를 없앤다.
    let q = "";
    const qual = coordLayout && coordLayout.quality;
    if (qual && !qual.ok) {
      q = ` · ⚠ 품질주의(물림 ${qual.cellOverflow}`
        + `·max ${qual.cellOverflowMaxPx}px`
        + (qual.bodyOverlap ? `·겹침 ${qual.bodyOverlap}` : "") + ")";
    } else if (qual) {
      q = " · 품질 ✓";
    }
    setStatus(qual && !qual.ok ? "fail" : "ok",
      `불러옴 · 표 ${sm.tables ?? "?"} · 셀 ${sm.cells ?? "?"} · `
      + (coordLayout ? "원본 배치 충실 재현" : "흐름 보기")
      + " · 원본 무수정" + q);
    render();  // 레이아웃 반영 재렌더
    probeTruth(d.sourcePath);   // 원본 실렌더 배경(가용 시 재렌더)
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
