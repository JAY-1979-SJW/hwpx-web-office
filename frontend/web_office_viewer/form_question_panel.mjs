/* 서식 질문 패널 — 채움 파이프라인의 브라우저 앞단 (독립).
 *
 * app.mjs(메인 편집기, 병행 세션 작업 영역)를 건드리지 않는 독립 패널이다.
 * 기존 백엔드 엔드포인트만 쓴다:
 *
 *   POST /api/web-office/hwpx-load        문서 로드(문단·run·charPr·해시)
 *   POST /api/web-office/fill-plan        채움 계획(autoFill/questions/skipped)
 *   POST /api/web-office/ai-fill          문맥 포함 AI 해석(ai_fill_dry_run)
 *   POST /api/web-office/catalog-fill     참조 서식 + corpus 카탈로그 매칭(AI 없음)
 *   POST /api/web-office/para-save-apply  paragraphId 겨냥 기입 → sandbox 저장
 *   GET  /api/web-office/download/{name}  결과 다운로드
 *
 * 흐름: 로드 → 계획 → (자동채움 확인 + 질문 답변) → 기입 → 다운로드.
 *
 * §4 준수: 원본 무수정(서버가 sandbox 사본에만 씀). AI/OCR 직접 호출 없음.
 * 민감칸은 requiresConfirmation — 사용자가 반드시 확인해야 채운다.
 *
 * 이 파일의 순수 로직(buildFillCommands 등)은 DOM 없이 테스트된다
 * (form_question_panel_self_test.mjs).
 */

// ── 순수 로직 (테스트 대상) ────────────────────────────────────────────────

/** documentModel.paragraphs → { paragraphId: 첫 run charPrIDRef } */
export function charPrIndex(documentModel) {
  const idx = {};
  for (const p of (documentModel?.paragraphs || [])) {
    const runs = p.runs || [];
    idx[p.paragraphId] = runs.length ? (runs[0].charPrIDRef ?? null) : null;
  }
  return idx;
}

/**
 * 채움 계획 + 사용자 답변 → para-save-apply 용 commandLog.
 *
 * answers: { paragraphId: value } — 자동채움 확정값 + 질문 답변을 합친 것.
 * 빈 값은 건너뛴다(지어내지 않는다). paragraphId 가 문서에 없으면 제외.
 *
 * 각 명령은 빈 칸 [0,0] 삽입(TYPE_TEXT). charPrIDRef 는 원본 run 것을
 * 상속한다(신규 charPr 생성 안 함).
 */
export function buildFillCommands(answers, documentModel, sourceHash) {
  const chIdx = charPrIndex(documentModel);
  const cmds = [];
  for (const [pid, raw] of Object.entries(answers || {})) {
    const value = (raw ?? "").toString();
    if (value === "") continue;               // 빈 값은 안 채움
    if (!(pid in chIdx)) continue;            // 문서에 없는 칸은 제외
    const inherit = chIdx[pid];
    cmds.push({
      commandId: cryptoRandomId(),
      commandType: "TYPE_TEXT",
      target: { paragraphId: pid },
      paragraphId: pid,
      payload: { caretOffset: 0, insertText: value },
      forward: {
        kind: "TYPE_TEXT", paragraphId: pid, caretOffset: 0,
        rangeAnchor: 0, rangeFocus: 0, rangeStart: 0, rangeEnd: 0,
        insertText: value, afterText: value, inheritCharPrIDRef: inherit,
      },
      inverse: {
        kind: "DELETE_TEXT_RANGE", paragraphId: pid,
        rangeAnchor: 0, rangeFocus: value.length, deletedText: value,
      },
      expectedBefore: "", sourceDocumentHash: sourceHash, status: "PENDING",
    });
  }
  return cmds;
}

/**
 * 계획을 화면 구역으로 나눈다. 민감칸/미확인 자동채움은 '확인 필요'로
 * 올려 실수 자동확정을 막는다(§4 원칙 2).
 */
export function partitionPlan(plan) {
  const auto = [], ask = [], sensitive = [];
  for (const a of (plan?.autoFill || [])) {
    (a.requiresConfirmation ? sensitive : auto).push(a);
  }
  for (const q of (plan?.questions || [])) {
    (q.requiresConfirmation ? sensitive : ask).push(q);
  }
  return { auto, ask, sensitive, skipped: plan?.skipped || [] };
}

/** confidence·suggested 를 초기값으로: 자동채움은 value, 질문은 suggested. */
export function initialAnswers(plan) {
  const out = {};
  for (const a of (plan?.autoFill || [])) {
    if (a.paragraphId && a.value) out[a.paragraphId] = a.value;
  }
  for (const q of (plan?.questions || [])) {
    if (q.paragraphId && q.suggested) out[q.paragraphId] = q.suggested;
  }
  return out;
}

/**
 * "AI에게 아는 정보"를 한 줄씩 파싱: "항목: 값" → { 항목: 값 }.
 * 콜론(: 또는 ：)로 나누고, 값이 있는 줄만. 사용자가 아는 것만 넣는다.
 */
export function parseSourceLines(text) {
  const src = {};
  for (const line of (text || "").split(/\r?\n/)) {
    const m = line.match(/^\s*(.+?)\s*[:：]\s*(.+?)\s*$/);
    if (m && m[2].trim()) src[m[1].trim()] = m[2].trim();
  }
  return src;
}

/**
 * /ai-fill 제안을 답변에 병합. proposals(신청인 칸)만 반영하고
 * heldForThirdParty(제3자 칸)는 절대 자동 채우지 않는다(§4 원칙 3).
 * 기존 답변이 있으면 덮지 않는다(사용자 입력 우선).
 */
export function applyAiProposals(answers, aiResult, planItems) {
  const out = { ...(answers || {}) };
  const byLabel = {};
  for (const it of (planItems || [])) {
    if (it.label && it.paragraphId) byLabel[it.label] = it.paragraphId;
  }
  const heldLabels = new Set(
    (aiResult?.heldForThirdParty || []).map((h) => h.label));
  for (const p of (aiResult?.proposals || [])) {
    if (heldLabels.has(p.label)) continue;        // 제3자 칸 방어
    const pid = p.key || byLabel[p.label];
    if (!pid) continue;
    if (out[pid]) continue;                       // 사용자 입력 우선
    out[pid] = p.value;
  }
  return out;
}

/**
 * 이 계획을 화면에 그릴 때 만들 입력 행 목록(순수). 서식이 바뀌면 이
 * 목록이 통째로 바뀐다 — 그걸 테스트로 고정한다. renderPlan 이 이걸 쓴다.
 */
export function planFieldRows(plan, answers) {
  const { auto, ask, sensitive } = partitionPlan(plan);
  const rows = [];
  const push = (items, section, isSensitive) => {
    for (const it of items) {
      if (!it.paragraphId) continue;
      rows.push({
        section, paragraphId: it.paragraphId,
        label: it.label || it.paragraphId,
        value: (answers || {})[it.paragraphId] || "",
        sensitive: !!isSensitive,
        question: it.question || "",
      });
    }
  };
  push(auto, "auto", false);
  push(sensitive, "sensitive", true);
  push(ask, "ask", false);
  return rows;
}

/**
 * 민원인/관계자 셀 좌표 집합. 뷰어에서 색으로 구분한다.
 * applicant(민원인)=자동채움+질문, office(관계자)=skipped. key="ti:row:col".
 */
export function roleCellMap(plan) {
  const map = {};
  const mark = (items, role) => {
    for (const it of (items || [])) {
      if (it.tableIndex == null) continue;
      map[`${it.tableIndex}:${it.row}:${it.col}`] = role;
    }
  };
  mark(plan?.autoFill, "applicant");
  mark(plan?.questions, "applicant");
  mark(plan?.skipped, "office");
  return map;
}

/**
 * 좌표 렌더러(.co-box[data-cell-id]) 색칠용 — cellId → 역할.
 *
 * 좌표 레이아웃의 cellId 는 `cell_t_s{sec}_{tbl:03d}_r{row}_c{col}` 이고,
 * 채움계획 항목의 paragraphId 는 `par_t_s..._r..._c..._p{n}` 이라 서로
 * 같은 셀 네임스페이스다(coordinate_layout._cell_id ↔ ro_view_importer).
 * paragraphId 에서 `par_`→`cell_`, 끝의 `_p{n}` 제거로 cellId 를 얻는다.
 */
export function roleByCellId(plan) {
  const map = {};
  const mark = (items, role) => {
    for (const it of (items || [])) {
      const pid = it.paragraphId;
      const m = pid && /^par_(t_s\d+_\d+_r\d+_c\d+)_p\d+$/.exec(pid);
      if (!m) continue;
      map["cell_" + m[1]] = role;
    }
  };
  mark(plan?.autoFill, "applicant");
  mark(plan?.questions, "applicant");
  mark(plan?.skipped, "office");
  return map;
}

function cryptoRandomId() {
  // 브라우저: crypto.randomUUID, node/테스트: 폴백
  try {
    if (typeof crypto !== "undefined" && crypto.randomUUID) {
      return crypto.randomUUID();
    }
  } catch { /* noop */ }
  return "cmd_" + Math.random().toString(36).slice(2, 14);
}

// ── DOM 배선 (브라우저에서만 동작, 테스트는 순수 로직만) ────────────────────

const API = "/api/web-office";

// 이미 개발된 뷰어(다른 창)를 연결한다 — 한컴 lineseg 좌표 레이아웃을
// 페이지마다 .co-page 로 "끊어서" 원본 배치 그대로 그리는 충실 렌더러.
// coordinate_renderer/style_resolver 만 의존하며 app.mjs(병행 세션 작업
// 영역)는 건드리지 않는다(둘 다 read-only import).
let _coordRenderer = null;
async function loadCoordRenderer() {
  if (_coordRenderer) return _coordRenderer;
  try {
    const mod = await import("./weboffice/coordinate_renderer.mjs");
    _coordRenderer = { render: mod.renderCoordinateLayout,
                       autoFit: mod.autoFitLines };
  } catch { _coordRenderer = null; }
  return _coordRenderer;
}

// 한컴 좌표 레이아웃(pageWidthPx/HeightPx/pages/pagesDetail…)을 받는다.
// app.mjs 와 동일한 엔드포인트·재시도. 명시 거부(REJECTED)는 재시도 안 함.
async function fetchLayout(sourcePath) {
  if (!sourcePath) return null;
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      const env = await post("hwpx-layout", { sourcePath });
      const d = (env && env.data) || env || {};
      if ((env && env.status && env.status !== "SUCCESS")
        || d.verdict === "REJECTED" || d.error) return null;
      return d;
    } catch {
      if (attempt < 2) await new Promise((r) => setTimeout(r, 1000));
    }
  }
  return null;
}

async function post(ep, body) {
  const r = await fetch(`${API}/${ep}`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return r.json();
}

function el(tag, attrs = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") e.className = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2).toLowerCase(), v);
    else if (k === "value") e.value = v;
    else e.setAttribute(k, v);
  }
  for (const kid of kids) if (kid != null) e.append(kid);
  return e;
}

function mountPanel(root) {
  const state = { rel: null, docModel: null, hash: null, plan: null,
                  renderPayload: null, layout: null, answers: {} };

  const viewer = el("div", { "data-testid": "viewer", class: "wo-sheet" });
  // 창 크기가 바뀌면 페이지를 다시 뷰어 폭에 맞춘다.
  window.addEventListener("resize", () => fitPages());
  const catBar = el("div", { "data-testid": "category-bar" });
  const formList = el("div", { "data-testid": "form-list" });
  const status = el("p", { "data-testid": "panel-status" }, "카테고리를 고르세요.");
  const relInput = el("input", { "data-testid": "source-path",
    placeholder: "data/drafts/form_library/.../서식.hwpx", size: "60" });
  const loadBtn = el("button", { "data-testid": "load-btn",
    onClick: () => loadForm() }, "① 계획 불러오기");
  // AI 대화 입력 박스 — renderPlan 밖에 두어 서식 재렌더에도 유지된다
  // (예전엔 renderPlan 안에서 매번 새로 만들어 입력이 사라졌다).
  const aiText = el("textarea", { "data-testid": "ai-source", rows: "4", cols: "50",
    placeholder: "아는 정보를 한 줄씩:\n상호: 가나다전기\n대표자: 홍길동\n전화번호: 02-0000-0000" });
  const aiBtn = el("button", { "data-testid": "ai-fill-btn",
    onClick: () => askAi(aiText.value) }, "AI에게 값 받기");
  const aiNote = el("small", { "data-testid": "ai-note", style: "color:#6b7280" }, "");
  // 카탈로그 매칭 — 예전에 채운 hwpx(참조 서식)에서 값을 직접 뽑아온다.
  // AI 호출 없음(upload_document_parser 규칙 기반 파서 + corpus 카탈로그).
  const catalogRefInput = el("input", { "data-testid": "catalog-ref-path",
    placeholder: "data/drafts/form_library/.../예전에_채운_서식.hwpx", size: "60" });
  const catalogBtn = el("button", { "data-testid": "catalog-fill-btn",
    onClick: () => askCatalog(catalogRefInput.value) }, "참조 서식으로 채우기");
  const aiBox = el("section", { "data-testid": "sec-ai", hidden: "true" },
    el("h3", {}, "② AI 대화 입력 (선택)"),
    el("div", {}, aiText), aiBtn, " ", aiNote,
    el("div", { style: "margin-top:8px" },
      el("div", {}, catalogRefInput), catalogBtn));

  const body = el("div", { "data-testid": "plan-body" });
  const fillBtn = el("button", { "data-testid": "fill-btn", disabled: "true",
    onClick: () => applyFill() }, "③ 채워서 파일 만들기");
  const result = el("div", { "data-testid": "fill-result" });

  const legend = el("p", { "data-testid": "role-legend",
    style: "font-size:13px" },
    el("span", { style: "background:#e8f0ff;padding:1px 6px;border:1px solid #2d6cdf" },
      "민원인 입력칸"), " ",
    el("span", { style: "background:#f0f0f0;padding:1px 6px;border:1px solid #9aa" },
      "관계자(관공서) 칸"));

  root.append(
    el("h2", {}, "서식 자동채움 — 질문 패널"),
    el("p", { style: "color:#b45309" },
      "원본은 수정하지 않고 sandbox 사본에만 씁니다."),
    el("h3", {}, "서식 카테고리"), catBar, formList,
    el("h3", {}, "또는 경로 직접 입력"),
    el("div", {}, relInput, " ", loadBtn),
    status, legend,
    el("h3", {}, "서식 미리보기 (뷰어)"), viewer,
    aiBox, body, fillBtn, result);

  loadCategories();

  /** 서식을 새로 열기 전에 이전 서식의 화면 흔적을 모두 지운다. */
  function resetForNewForm() {
    body.replaceChildren();
    result.replaceChildren();
    viewer.replaceChildren();
    aiBox.setAttribute("hidden", "true");
    aiText.value = "";
    catalogRefInput.value = "";
    aiNote.textContent = "";
    fillBtn.disabled = true;
    state.docModel = null; state.plan = null; state.hash = null;
    state.renderPayload = null; state.layout = null; state.answers = {};
  }

  /** 충실 뷰어로 서식을 그린다 — 원본 좌표대로 페이지를 끊어(.co-page)
   * 배치 그대로 재현 + 민원인/관계자 셀 색 구분. */
  async function renderViewer() {
    const cr = await loadCoordRenderer();
    viewer.replaceChildren();
    if (!cr || !state.layout) {
      viewer.textContent = state.layout === null
        ? "(원본 배치 레이아웃을 받지 못했습니다 — 미리보기 생략)"
        : "(뷰어 모듈 없음 — 미리보기 생략)";
      return;
    }
    const printBtn = el("button", { "data-testid": "print-a4",
      onClick: () => printFaithful() }, "🖨 인쇄 / PDF 저장");
    // read-only 미리보기: editable 끔(클릭 편집은 메인 편집기 담당).
    const html = cr.render(state.layout, { editable: false });
    const scaler = el("div", { class: "co-scaler" });
    const sheet = el("div", { class: "co-sheet", "data-testid": "co-sheet" });
    sheet.innerHTML = html;
    scaler.append(sheet);
    viewer.append(el("div", { class: "wo-a4-toolbar" }, printBtn), scaler);
    colorCells(roleByCellId(state.plan));   // co-box 셀 역할 색
    cr.autoFit(sheet);                        // 줄 가로압축(한컴 justify 재현)
    requestAnimationFrame(fitPages);          // 페이지를 뷰어 폭에 맞춤
  }

  /** 원본 픽셀 크기의 페이지들을 뷰어 폭에 맞춰 균일 축소(가로 스크롤 제거).
   * 페이지는 세로로 쌓이고(원본대로 끊김), 페이지 사이만 세로 스크롤. */
  function fitPages() {
    const sheet = viewer.querySelector('[data-testid="co-sheet"]');
    if (!sheet || !state.layout) return;
    const pw = state.layout.pageWidthPx || 0;
    if (!pw) return;
    sheet.style.width = pw + "px";
    sheet.style.transform = "none";
    const natH = sheet.offsetHeight;
    const avail = viewer.clientWidth - 20;
    const s = Math.min(avail / pw, 1.5);      // 폭에 맞춤(과확대 상한 1.5)
    sheet.style.transformOrigin = "top left";
    sheet.style.transform = `scale(${s})`;
    const scaler = sheet.parentElement;
    scaler.style.width = pw * s + "px";
    scaler.style.height = natH * s + "px";
    scaler.style.margin = "0 auto";
  }

  /** 충실 페이지(.co-page)를 새 창에서 인쇄(=PDF). 원본 픽셀 배치 그대로,
   * 페이지 경계에서 끊어 인쇄한다. */
  function printFaithful() {
    const sheet = viewer.querySelector('[data-testid="co-sheet"]');
    if (!sheet) return;
    const w = window.open("", "_blank");
    if (!w) return;
    w.document.write(
      "<!doctype html><meta charset='utf-8'><title>인쇄</title><style>" +
      "@page{margin:0;}body{margin:0;"
      + "font-family:'함초롬바탕','바탕','Malgun Gothic',serif;}" +
      ".co-page{position:relative;background:#fff;overflow:clip;"
      + "page-break-after:always;margin:0 auto;}" +
      ".co-line{position:absolute;white-space:pre;overflow:clip;"
      + "overflow-clip-margin:3px;}" +
      ".co-box{position:absolute;}" +
      ".co-in{display:inline-block;}" +
      ".co-box[data-fill-role='applicant']{background:rgba(45,108,223,.12);}" +
      ".co-box[data-fill-role='office']{background:rgba(120,120,120,.12);}" +
      "</style>" + sheet.innerHTML +
      "<script>window.onload=function(){window.print();};</script>");
    w.document.close();
  }

  /** 민원인/관계자 셀 색 — read-only 충실 렌더는 co-box 에 cellId 를 안
   * 실으므로, 레이아웃 데이터의 셀 박스 좌표로 반투명 틴트를 각 .co-page
   * 에 직접 오버레이한다(원본 텍스트/테두리 위에 얹지 않게 맨 뒤로 깐다). */
  function colorCells(rolesById) {
    const pages = viewer.querySelectorAll(".co-page");
    if (!pages.length) return;
    const tint = (role) => role === "applicant"
      ? "rgba(45,108,223,.13)" : "rgba(120,120,120,.13)";
    const put = (pageEl, b, role) => {
      const t = document.createElement("div");
      t.className = "co-role";
      t.setAttribute("data-fill-role", role);
      t.style.cssText = "position:absolute;pointer-events:none;left:"
        + `${b.x}px;top:${b.y}px;width:${b.w}px;height:${b.h}px;`
        + `background:${tint(role)};`;
      pageEl.insertBefore(t, pageEl.firstChild);   // 텍스트·테두리 뒤로
    };
    const pd = state.layout.pagesDetail;
    if (pd && pd.length) {
      for (let pi = 0; pi < pages.length && pi < pd.length; pi++) {
        for (const b of (pd[pi].boxes || [])) {
          const role = b.cellId && rolesById[b.cellId];
          if (role && !b.frag) put(pages[pi], b, role);
        }
      }
    } else {                                        // 구버전: 전역 y 슬라이싱
      const H = state.layout.pageHeightPx || 1;
      for (const b of (state.layout.boxes || [])) {
        const role = b.cellId && rolesById[b.cellId];
        if (!role || b.frag) continue;
        const pi = Math.floor(b.y / H);
        if (pages[pi]) put(pages[pi], { ...b, y: b.y - pi * H }, role);
      }
    }
  }

  async function loadCategories() {
    const r = await fetch(`${API}/catalog-categories`).then((x) => x.json());
    const cats = (r.data || r).categories || [];
    catBar.replaceChildren();
    for (const c of cats) {
      catBar.append(el("button", {
        "data-testid": `cat-${c.domain}`,
        onClick: () => loadCategory(c.domain),
      }, `${c.domain} (${c.count})`));
    }
  }

  async function loadCategory(domain) {
    status.textContent = `${domain} 서식 불러오는 중…`;
    const r = await post("catalog-by-category", { domain, limit: 30 });
    const results = (r.data || r).results || [];
    formList.replaceChildren(el("p", {},
      `${domain}: ${results.length}개`));
    for (const f of results) {
      const rel = f.sourcePath || f.source_path;
      formList.append(el("div", {},
        el("button", {
          "data-testid": "pick-form",
          onClick: () => { relInput.value = rel || ""; loadForm(); },
        }, f.name || rel)));
    }
  }

  async function loadForm() {
    const rel = relInput.value.trim();
    resetForNewForm();                 // 이전 서식 화면·상태 완전 초기화
    state.rel = rel;
    if (!state.rel) { status.textContent = "경로가 비었습니다."; return; }
    status.textContent = "불러오는 중…";
    const loaded = await post("hwpx-load",
      { operation: "HWPX_EDITOR_LOAD", sourcePath: state.rel });
    if (loaded.status !== "SUCCESS") {
      status.textContent = "로드 실패: " + (loaded.errors?.[0]?.code || "?");
      return;
    }
    state.docModel = loaded.data.documentModel;
    state.renderPayload = loaded.data.renderPayload;
    state.hash = loaded.data.sourceDocumentHash;
    const plan = await post("fill-plan", { sourcePath: state.rel, profile: {} });
    state.plan = plan.data || plan;
    state.answers = initialAnswers(state.plan);
    aiBox.removeAttribute("hidden");
    renderPlan();
    // 원본 배치 좌표 레이아웃을 받아 충실 뷰어로 페이지를 끊어 그린다.
    status.textContent += " · 원본 배치 불러오는 중…";
    state.layout = await fetchLayout(state.rel);
    renderViewer();          // 충실 렌더(.co-page) + 민원인/관계자 역할 색
  }

  function renderPlan() {
    const { auto, ask, sensitive, skipped } = partitionPlan(state.plan);
    status.textContent =
      `자동채움 ${auto.length} · 질문 ${ask.length} · 확인필요 ${sensitive.length} · 제외 ${skipped.length}`;

    // 서식이 바뀌면 이 행 목록이 통째로 바뀐다(planFieldRows). body 를
    // 비우고 새 행으로 다시 그린다.
    body.replaceChildren();
    body.setAttribute("data-source", state.rel || "");
    const bySection = { auto: [], sensitive: [], ask: [] };
    for (const row of planFieldRows(state.plan, state.answers)) {
      bySection[row.section].push(row);
    }
    const titles = { auto: "자동채움 가능", sensitive: "확인 필요(민감)",
                     ask: "질문 — 답변 입력" };
    for (const key of ["auto", "sensitive", "ask"]) {
      const rows = bySection[key];
      const wrap = el("section", { "data-testid": `sec-${key}`,
        "data-count": String(rows.length) });
      wrap.append(el("h3", {}, `${titles[key]} (${rows.length})`));
      for (const row of rows) {
        const pid = row.paragraphId;
        const input = el("input", {
          "data-testid": `field-${pid}`, "data-paragraph-id": pid,
          value: row.value,
          onInput: (e) => { state.answers[pid] = e.target.value; },
        });
        wrap.append(el("div", {},
          el("label", {}, row.label), " ", input,
          row.sensitive ? el("span", { style: "color:#b91c1c" },
            " [민감 — 확인]") : null,
          row.question ? el("small", { style: "color:#6b7280" },
            " " + row.question) : null));
      }
      body.append(wrap);
    }
    fillBtn.disabled = false;
  }

  async function askAi(text) {
    const source = parseSourceLines(text);
    if (!Object.keys(source).length || !state.plan) { return; }
    const { ask, sensitive } = partitionPlan(state.plan);
    const items = [...ask, ...sensitive, ...(state.plan.autoFill || [])];
    const fields = items.map((f) => ({ key: f.paragraphId, label: f.label,
      subject: f.subject, sensitive: f.requiresConfirmation }));
    // sourcePath 를 실으면 서버가 ai_fill_dry_run(문맥 포함 해석 + 비창조·
    // 주소 검증)을 쓴다 — fields 는 이 경로에서 서버가 documentModel 로
    // 다시 만들어 쓰므로 클라이언트 값은 무시된다(호환을 위해 계속 보냄).
    const r = await post("ai-fill", { fields, sourceData: source, sourcePath: state.rel });
    const ai = r.data || r;
    state.answers = applyAiProposals(state.answers, ai, items);
    const held = (ai.heldForThirdParty || []).length;
    const rejected = (ai.rejected || []).length;
    aiNote.textContent = `제안 ${(ai.proposals || []).length} 반영` +
      (held ? ` · 제3자 칸 ${held} 보호(자동 안 채움)` : "") +
      (rejected ? ` · 검증 실패 ${rejected}건(비창조/주소 등)` : "");
    renderPlan();      // 답변 반영해 다시 그림 (AI 박스는 body 밖이라 유지)
  }

  /** 참조 서식(예전에 채운 hwpx)에서 corpus 카탈로그로 값을 매칭해 채운다.
   * AI 호출 없음 — upload_document_parser(규칙 기반) + 카탈로그 매칭. */
  async function askCatalog(referencePath) {
    const ref = (referencePath || "").trim();
    if (!ref || !state.plan || !state.rel) { return; }
    const { ask, sensitive } = partitionPlan(state.plan);
    const items = [...ask, ...sensitive, ...(state.plan.autoFill || [])];
    const r = await post("catalog-fill",
      { referencePath: ref, sourcePath: state.rel });
    const cat = r.data || r;
    if (r.status !== "SUCCESS") {
      aiNote.textContent = "카탈로그 매칭 실패: " +
        (r.errors?.[0]?.message || r.errors?.[0]?.code || "?");
      return;
    }
    state.answers = applyAiProposals(state.answers, cat, items);
    const missing = cat.missingCount || 0;
    aiNote.textContent = `카탈로그 매칭: 제안 ${(cat.proposals || []).length}건 반영` +
      (missing ? ` · 누락 ${missing}건` : "");
    renderPlan();
  }

  async function applyFill() {
    const cmds = buildFillCommands(state.answers, state.docModel, state.hash);
    if (!cmds.length) { result.textContent = "채울 값이 없습니다."; return; }
    result.textContent = `${cmds.length}칸 기입 중…`;
    const out = await post("para-save-apply", {
      operation: "PARA_SAVE_APPLY", sourcePath: state.rel,
      sourceDocumentHash: state.hash, commandLog: cmds });
    const d = out.data || out;
    const name = d.outputFileName;
    result.replaceChildren(
      el("p", { "data-testid": "result-verdict" },
        `결과: ${d.verdict} · 기입 ${d.acceptedCount ?? "?"} · 반려 ${(d.rejected||[]).length}`),
      name ? el("a", { "data-testid": "download-link",
        href: `${API}/download/${encodeURIComponent(name)}` }, "채워진 파일 다운로드")
           : el("span", {}, "출력 없음"));
  }
}

if (typeof document !== "undefined") {
  const root = document.getElementById("panel-root");
  if (root) mountPanel(root);
}
