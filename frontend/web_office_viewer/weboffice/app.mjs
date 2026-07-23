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
  let pendingEditId = null; // 재렌더 후 이어서 열 즉석 편집 대상(이동 연속)
  let selectedCellId = null;   // 서식 툴바 대상(마지막 클릭 칸)
  let fmtBusy = false;         // 서식 적용 중 중복 클릭 방지

  // 서식 툴바 — 클릭된 칸을 서식 적용 대상으로 표시하고 버튼을 켠다.
  function selectCellForFormat(id, box) {
    selectedCellId = id;
    root.querySelectorAll(".co-box.wo-fmt-selected")
      .forEach((b) => b.classList.remove("wo-fmt-selected"));
    if (box) box.classList.add("wo-fmt-selected");
    ["fmt-bold", "fmt-italic", "fmt-underline", "fmt-size", "fmt-color"]
      .forEach((r) => { $(`[data-role=${r}]`).disabled = fmtBusy; });
  }

  // 서식 적용 — 선택된 칸의 전체 텍스트 범위에 overrides 를 적용한다.
  // 서버가 charPr 해석(기존 매칭/신규 append)까지 담당(§4.1). 결과는
  // 항상 새 sandbox 파일 — 원본은 무수정, 다음 편집은 그 파일을 이어받는다.
  async function applyFormat(overrides) {
    if (!selectedCellId || !loaded || fmtBusy) return;
    const text = cell.currentText(selectedCellId);
    if (text == null) return;
    const model = loaded.documentModel || {};
    const c = (model.cells || []).find((x) => x.cellId === selectedCellId);
    const pid = c && c.paragraphs && c.paragraphs[0]
      && c.paragraphs[0].paragraphId;
    if (!pid) { setStatus("fail", "서식 대상 문단을 찾을 수 없음"); return; }
    fmtBusy = true;
    setStatus("load", "서식 적용 중 …");
    try {
      const res = await fetch("/api/web-office/apply-format", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          sourcePath: loaded.sourcePath, paragraphId: pid,
          rangeAnchor: 0, rangeFocus: text.length, overrides,
        }),
      });
      const env = await res.json();
      const d = (env && env.data) || {};
      if (!(env && env.status === "SUCCESS") || d.verdict !== "PASS") {
        const msg = (env.errors && env.errors[0] && env.errors[0].message)
          || d.verdict || "서식 적용 실패";
        setStatus("fail", "서식 적용 거부: " + msg);
        return;
      }
      // 서버가 만든 새 sandbox 파일을 다음 편집의 기준으로 이어받는다.
      loaded.sourcePath = d.sourcePath;
      setStatus("ok", "서식 적용 완료(새 sandbox 사본) · 재로딩 …");
      coordLayout = await fetchLayout(loaded.sourcePath);
      render();
      probeTruth(loaded.sourcePath);
    } catch (e) {
      setStatus("fail", "서식 적용 실패: " + (e.message || e));
    } finally {
      fmtBusy = false;
    }
  }

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
        // 편집된 셀은 원본 줄 대신 새 텍스트를 문서 텍스트로 렌더 —
        // AI fill 주입과 동일하게 '문서에 직접 기입'된 모습만 남는다.
        getCellText: (id) => (cell ? cell.getCellText(id) : null),
        truthBase,   // 가용 시 '원본 그대로'(한컴 실렌더 배경 + 편집 오버레이)
      });
      autoFitLines(sheet);
      // 문서 직접 기입 방식 — 화면에 상시 입력창을 만들지 않는다. 문서는
      // 원형 그대로 보이고, 입력칸을 클릭한 순간에만 그 칸에 즉석 편집기
      // 하나가 나타나며, 커밋하면 AI fill 주입과 동일하게 값이 문서
      // 텍스트로 렌더된다(입력 위젯 흔적 없음).
      const inputBoxes = [];
      sheet.querySelectorAll(".co-box[data-cell-id]").forEach((box) => {
        const id = box.dataset.cellId;
        const isInput = cell.isInputCell(id);   // 파서(XML) 분류 단일 진실
        box.classList.add(isInput ? "wo-input" : "wo-label");
        // 서식 툴바 대상 — 클릭된 어떤 칸(입력/라벨 무관)이든 선택 표시.
        box.addEventListener("click", () => selectCellForFormat(id, box));
        if (isInput && !box.dataset.frag) {
          const r = box.getBoundingClientRect();
          // 방향키 이동용 기하 — 같은 스크롤 상태에서 일괄 측정하므로 상대
          // 좌표계가 일관(페이지 세로 적층 → ↓ 가 다음 페이지로 이어짐).
          inputBoxes.push({
            id, box,
            x0: r.left, x1: r.right, y0: r.top, y1: r.bottom,
            cx: (r.left + r.right) / 2, cy: (r.top + r.bottom) / 2,
          });
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
      // 엑셀식 이동 — 1차: 같은 열/행(구간 겹침)에서 방향으로 가장 가까운
      // 칸, 2차(없으면): 겹침 없이 방향만 맞는 최근접 칸. 표·페이지 경계를
      // 넘어 입력칸들이 하나의 격자처럼 이어진다.
      const navFrom = (cur, dir) => {
        const horiz = dir === "left" || dir === "right";
        const sgn = (dir === "right" || dir === "down") ? 1 : -1;
        let best = null, bestKey = Infinity;
        const scan = (needOverlap) => {
          for (const g of inputBoxes) {
            if (g === cur) continue;
            const d = horiz ? (g.cx - cur.cx) * sgn : (g.cy - cur.cy) * sgn;
            if (d <= 2) continue;
            const ov = horiz
              ? Math.min(g.y1, cur.y1) - Math.max(g.y0, cur.y0)
              : Math.min(g.x1, cur.x1) - Math.max(g.x0, cur.x0);
            if (needOverlap && ov <= 0) continue;
            const perp = horiz
              ? Math.abs(g.cy - cur.cy) : Math.abs(g.cx - cur.cx);
            const key = d + perp * 4;
            if (key < bestKey) { bestKey = key; best = g; }
          }
        };
        scan(true);
        if (!best) scan(false);
        return best;
      };
      // 즉석 편집기 — 클릭된 입력칸에만 임시 <input> 하나. 커밋(Enter/이동/
      // blur)하면 편집기는 사라지고 값은 문서 텍스트로 렌더된다.
      const openEditor = (it) => {
        if (it.box.querySelector("input")) return;   // 이미 편집 중
        const inp = document.createElement("input");
        inp.className = "wo-fld";
        const ph = cell.inputLabel(it.id);
        const cur = cell.currentText(it.id);
        if (ph) {
          // 마커 칸: 항목명을 placeholder 로, 마커 원문은 값으로 노출 안 함
          inp.placeholder = ph;
          inp.title = ph;
          inp.classList.add("wo-fld-ph");
          inp.value = /\[입력필요:/.test(cur) ? "" : cur;
        } else {
          inp.value = cur;
        }
        const initial = inp.value;
        let done = false;
        const close = () => { done = true; inp.remove(); };
        const commit = (nxt) => {
          if (done) return;
          const v = inp.value;
          // 마커 보존 — 빈 값이면 마커 원문 유지(문서 훼손 방지)
          const changed = (v !== initial) && !(ph && v === "")
            && cell.setCellText(it.id, v);
          close();
          if (nxt) pendingEditId = nxt.id;
          if (changed) render();          // 값이 문서 텍스트로 렌더됨
          else if (nxt) openEditor(nxt);
        };
        inp.addEventListener("keydown", (e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            commit(navFrom(it, "down"));   // 엑셀처럼 아래 칸으로
          } else if (e.key === "Tab") {
            e.preventDefault();
            commit(navFrom(it, e.shiftKey ? "left" : "right"));
          } else if (e.key === "ArrowUp" || e.key === "ArrowDown") {
            e.preventDefault();
            commit(navFrom(it, e.key === "ArrowUp" ? "up" : "down"));
          } else if (e.key === "ArrowLeft") {
            // 캐럿이 맨 앞일 때만 칸 이동(텍스트 내 이동 보호)
            if (inp.selectionStart === 0 && inp.selectionEnd === 0) {
              e.preventDefault();
              commit(navFrom(it, "left"));
            }
          } else if (e.key === "ArrowRight") {
            if (inp.selectionStart === inp.value.length
                && inp.selectionEnd === inp.value.length) {
              e.preventDefault();
              commit(navFrom(it, "right"));
            }
          } else if (e.key === "Escape") {
            close();
          }
        });
        inp.addEventListener("blur", () => commit(null));
        // 편집기를 셀의 실제 텍스트 줄 y 에 정렬 — rowSpan 큰 셀에서
        // 편집기가 위 줄에 떠 보이던 결함 수리. 줄 없으면 세로 중앙.
        const pgIdx = [...sheet.querySelectorAll(".co-page")]
          .indexOf(it.box.closest(".co-page"));
        const pdc = (coordLayout.pagesDetail || [])[pgIdx];
        const ln0 = pdc
          ? pdc.lines.find((l) => l.cellId === it.id) : null;
        const boxTop = parseFloat(it.box.style.top) || 0;
        const boxH = parseFloat(it.box.style.height) || 0;
        if (ln0) {
          inp.style.top = Math.max(0, ln0.y - boxTop - 3) + "px";
          inp.style.height = ((ln0.h || 14) + 8) + "px";
          inp.style.bottom = "auto";
        } else if (boxH > 40) {
          inp.style.top = Math.max(0, (boxH - 24) / 2) + "px";
          inp.style.height = "24px";
          inp.style.bottom = "auto";
        }
        it.box.appendChild(inp);
        inp.focus();
        inp.select();
        inp.scrollIntoView({ block: "nearest", inline: "nearest" });
      };
      inputBoxes.forEach((it) => {
        it.box.addEventListener("click", () => openEditor(it));
      });
      // 재렌더 직후 이동 연속 — 직전 커밋이 지정한 다음 칸에서 이어서 편집
      if (pendingEditId) {
        const nxt = inputBoxes.find((b) => b.id === pendingEditId);
        pendingEditId = null;
        if (nxt) openEditor(nxt);
      }
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
    $("[data-role=aifill]").disabled = !cell;
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
    selectedCellId = null;
    ["fmt-bold", "fmt-italic", "fmt-underline", "fmt-size", "fmt-color"]
      .forEach((r) => { $(`[data-role=${r}]`).disabled = true; });
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
  // AI 자동입력 — AI 창에 HWPX 를 주는 것과 동일: 서버가 인식한 입력
  // 지점(라벨 붙은 셀)에 Claude 제안값을 로직으로 정확히 기입한다.
  // 제안일 뿐 자동 승인 아님 — 화면에서 검토·수정 후 저장은 사람이.
  $("[data-role=aifill]").addEventListener("click", async () => {
    if (!cell || !loaded) return;
    const model = loaded.documentModel || {};
    const byId = new Map();   // cellId → label (인식 필드 + 파서 라벨)
    for (const f of (model.recognizedFields || [])) {
      if (f.cellId && f.label) byId.set(f.cellId, f.label);
    }
    for (const c of (model.cells || [])) {
      if (c.isInputCell && c.inputLabel && !byId.has(c.cellId)) {
        byId.set(c.cellId, c.inputLabel);
      }
    }
    // 아직 값이 없는 칸만(이미 채운 값·라벨 원문은 보존)
    const fields = [...byId]
      .filter(([id]) => {
        const t = cell.currentText(id);
        return !t.trim() || /\[입력필요:/.test(t);
      })
      .map(([id, label]) => ({ key: id, label }));
    const paraN = (model.recognizedFields || [])
      .filter((f) => f.paragraph).length;
    if (!fields.length) {
      setStatus("ok", "AI 입력 대상 없음(모든 인식 칸에 값 있음)");
      return;
    }
    setStatus("load", `AI 값 제안 중 … (${fields.length}칸, Claude)`);
    try {
      const res = await fetch("/api/web-office/ai-fill", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ fields }),
      });
      const env = await res.json();
      const d = (env && env.data) || env || {};
      let n = 0;
      for (const p of (d.proposals || [])) {
        if (p.key && p.value && cell.setCellText(p.key, p.value)) n += 1;
      }
      render();
      renderSide();
      setStatus(n ? "ok" : "fail",
        n ? `AI 자동입력 ${n}/${fields.length}칸 — 제안값이니 검토·수정 후 저장`
          + (paraN ? ` (본문 문단 ${paraN}건은 문단편집 공정 예정)` : "")
          : "AI 제안 0건 — " + (d.error || "다시 시도"));
    } catch (e) {
      setStatus("fail", "AI 자동입력 실패: " + (e.message || e));
    }
  });
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
  // 서식 툴바 — 굵게/기울임/밑줄은 현재값을 뒤집어 보냄(토글).
  $("[data-role=fmt-bold]").addEventListener("click",
    () => applyFormat({ bold: true }));
  $("[data-role=fmt-italic]").addEventListener("click",
    () => applyFormat({ italic: true }));
  $("[data-role=fmt-underline]").addEventListener("click",
    () => applyFormat({ underline: true }));
  $("[data-role=fmt-size]").addEventListener("change", (e) => {
    const v = parseFloat(e.target.value);
    if (v > 0) applyFormat({ fontSizePt: v });
  });
  $("[data-role=fmt-color]").addEventListener("change",
    (e) => applyFormat({ textColor: e.target.value.toUpperCase() }));

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
