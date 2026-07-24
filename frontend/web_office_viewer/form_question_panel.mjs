/* 서식 질문 패널 — 채움 파이프라인의 브라우저 앞단 (독립).
 *
 * app.mjs(메인 편집기, 병행 세션 작업 영역)를 건드리지 않는 독립 패널이다.
 * 기존 백엔드 엔드포인트만 쓴다:
 *
 *   POST /api/web-office/hwpx-load        문서 로드(문단·run·charPr·해시)
 *   POST /api/web-office/fill-plan        채움 계획(autoFill/questions/skipped)
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
                  answers: {} };

  const status = el("p", { "data-testid": "panel-status" }, "서식 경로를 입력하세요.");
  const relInput = el("input", { "data-testid": "source-path",
    placeholder: "data/drafts/form_library/.../서식.hwpx", size: "60" });
  const loadBtn = el("button", { "data-testid": "load-btn",
    onClick: () => loadForm() }, "① 계획 불러오기");
  const body = el("div", { "data-testid": "plan-body" });
  const fillBtn = el("button", { "data-testid": "fill-btn", disabled: "true",
    onClick: () => applyFill() }, "② 채워서 파일 만들기");
  const result = el("div", { "data-testid": "fill-result" });

  root.append(
    el("h2", {}, "서식 자동채움 — 질문 패널"),
    el("p", { style: "color:#b45309" },
      "원본은 수정하지 않고 sandbox 사본에만 씁니다."),
    el("div", {}, relInput, " ", loadBtn),
    status, body, fillBtn, result);

  async function loadForm() {
    state.rel = relInput.value.trim();
    if (!state.rel) { status.textContent = "경로가 비었습니다."; return; }
    status.textContent = "불러오는 중…";
    const loaded = await post("hwpx-load",
      { operation: "HWPX_EDITOR_LOAD", sourcePath: state.rel });
    if (loaded.status !== "SUCCESS") {
      status.textContent = "로드 실패: " + (loaded.errors?.[0]?.code || "?");
      return;
    }
    state.docModel = loaded.data.documentModel;
    state.hash = loaded.data.sourceDocumentHash;
    const plan = await post("fill-plan", { sourcePath: state.rel, profile: {} });
    state.plan = plan.data || plan;
    state.answers = initialAnswers(state.plan);
    renderPlan();
  }

  function renderPlan() {
    const { auto, ask, sensitive, skipped } = partitionPlan(state.plan);
    body.replaceChildren();
    status.textContent =
      `자동채움 ${auto.length} · 질문 ${ask.length} · 확인필요 ${sensitive.length} · 제외 ${skipped.length}`;

    const section = (title, items, opts = {}) => {
      const wrap = el("section", { "data-testid": opts.testid,
        "data-count": String(items.length) });
      wrap.append(el("h3", {}, `${title} (${items.length})`));
      for (const it of items) {
        const pid = it.paragraphId;
        const input = el("input", {
          "data-testid": `field-${pid}`, "data-paragraph-id": pid,
          value: state.answers[pid] || "",
          onInput: (e) => { state.answers[pid] = e.target.value; },
        });
        const tag = opts.sensitive
          ? el("span", { style: "color:#b91c1c" }, " [민감 — 확인]") : null;
        wrap.append(el("div", {},
          el("label", {}, it.label || pid), " ", input, tag,
          it.question ? el("small", { style: "color:#6b7280" },
            " " + it.question) : null));
      }
      return wrap;
    };

    body.append(
      section("자동채움 가능", auto, { testid: "sec-auto" }),
      section("확인 필요(민감)", sensitive, { testid: "sec-sensitive",
        sensitive: true }),
      section("질문 — 답변 입력", ask, { testid: "sec-ask" }));
    fillBtn.disabled = false;
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
