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
import { charPrToCss } from "./style_resolver.mjs";

const SAMPLE = "tests/fixtures/hwpx/corpus/fx_metadata_form.hwpx";
const LAYOUT_ENDPOINT = "/api/web-office/hwpx-layout";
const TRUTH_ENDPOINT = "/api/web-office/truth-page";

export function mountWebOffice(root) {
  const $ = (sel) => root.querySelector(sel);
  let loaded = null, cell = null, save = null;
  let coordLayout = null;   // 한컴 좌표 기반 faithful 레이아웃
  let truthBase = null;     // '원본 그대로' 모드 — 한컴 실렌더 배경 URL 접두
  let selectedCellId = null;   // 서식 툴바 대상(마지막 클릭 칸)
  let paraSelTarget = null;    // 서식 툴바 대상(흐름 상자 안 텍스트 선택)
                                // {paragraphId, start, end} — 있으면 셀
                                // 선택보다 우선.
  let fmtBusy = false;         // 서식 적용 중 중복 클릭 방지
  const paraEdits = new Map();  // paragraphId → 편집된 텍스트(표 셀 아님)
  let paraBusy = false;        // 본문 문단 저장 중 표시(상태줄 용)
  // 저장 요청 직렬화 큐 — 실측(2026-07-24) 확인된 결함: 이전 저장이
  // 아직 끝나기 전(한컴 실렌더 배경 재계산은 수 초 걸림) 사용자가 다음
  // 문단을 편집·커밋하면, 예전에는 paraBusy 가드가 그 요청을 "조용히
  // 버렸다"(편집기는 이미 닫혀 텍스트 유실, 에러 표시도 없음) — 이게
  // "클릭은 되는데 저장은 안 된다" 신고의 실제 원인이었다. 이제는
  // 버리지 않고 큐에 이어 붙여 이전 저장이 끝나면 순서대로 실행한다.
  let paraSaveQueue = Promise.resolve();

  // cell 컨트롤러를 loaded.documentModel(최신 sourceDocumentHash 포함)
  // 기준으로 재구성한다 — 문단 저장·서식 적용처럼 파일을 바꾸는 다른
  // 편집 뒤에도 표 셀 저장이 SOURCE_HASH_MISMATCH 로 거부되지 않게
  // 한다. 미저장 셀 편집(commandLog)이 있으면 재구성하지 않는다(재구성
  // 하면 그 편집이 유실됨 — 유실보다는 다음 저장이 거부되는 편이 안전).
  function resyncCellControllerIfIdle() {
    if (cell && cell.commandLog().length === 0
        && loaded && loaded.documentModel) {
      cell = createCellEditController(loaded.documentModel);
      save = createSaveController({
        getState: () => cell.getState(),
        getSourcePath: () => loaded.sourcePath,
      });
    }
  }

  // 원본 run 단위 서식을 편집 상자 안에 그대로 재현한다(대표님 지시:
  // "원본 서식을 그대로 유지"). 한 문단/셀 안에 서로 다른 서식(굵게 구간
  // + 일반 구간처럼)이 섞여 있어도, 지금까지는 "대표 서식 하나"만 상자
  // 전체에 입혀 그 구분이 화면에서 사라졌었다 — runs 배열(문서모델의
  // charPrIDRef 별 텍스트 조각)을 그대로 span 으로 나눠 넣으면 편집
  // 전 상태는 원본과 서식까지 동일하게 보인다. textContent 대신 DOM
  // span 을 직접 만들어 삽입(문자열 조립 아님 — 이스케이프 문제 없음).
  function renderRunSpans(container, runs, defs) {
    container.textContent = "";
    for (const r of runs) {
      const span = document.createElement("span");
      span.textContent = r.text;
      const def = defs ? defs[r.charPrIDRef] : null;
      if (def) span.setAttribute("style", charPrToCss(def));
      container.appendChild(span);
    }
  }

  function saveParagraphText(paragraphId, newText) {
    paraSaveQueue = paraSaveQueue
      .then(() => _doSaveParagraphText(paragraphId, newText))
      .catch((e) => setStatus("fail", "문단 저장 실패: " + (e.message || e)));
    return paraSaveQueue;
  }

  // 본문 문단(표 밖 제목·전문 등) 저장 — 셀과 달리 undo/redo 명령 로그가
  // 없다. apply-format 과 동일하게 즉시 서버에 저장하고 sourcePath 를
  // 이어받는다(원본은 무수정, 결과는 항상 새 sandbox 사본).
  async function _doSaveParagraphText(paragraphId, newText) {
    if (!loaded) return false;
    const model = loaded.documentModel || {};
    const p = (model.paragraphs || []).find(
      (x) => x.paragraphId === paragraphId);
    if (!p) { setStatus("fail", "편집 대상 문단을 찾을 수 없음"); return false; }
    // 재편집 시 서버 기준값은 직전 편집 결과(이미 sourcePath 가 그
    // sandbox 사본으로 갱신돼 있음) — 원본 documentModel.text 가 아니라
    // paraEdits 에 남은 마지막 저장값을 expectedBefore 로 써야 두 번째
    // 편집부터 EXPECTED_BEFORE_MISMATCH 로 거부되지 않는다.
    const before = paraEdits.has(paragraphId)
      ? paraEdits.get(paragraphId) : (p.text || "");
    // 전체 교체는 첫 run(오프셋 0)의 charPr 을 그대로 적용 — 신규 charPr
    // 생성 없음(§4 유지). 다중 run 문단도 anchor(첫 run) 서식으로 통일.
    const applyPr = (p.runs && p.runs[0] && p.runs[0].charPrIDRef) || null;
    if (before === newText) return true;   // 무변경 — 저장 안 함(이미 반영됨)
    paraBusy = true;
    setStatus("load", "문단 저장 중 …");
    try {
      return !!(await _runParaSaveCommand(model, {
        commandId: `pc_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
        commandType: "REPLACE_TEXT_RANGE",
        target: { paragraphId },
        payload: { rangeAnchor: 0, rangeFocus: before.length,
          afterText: newText, policy: "ANCHOR_CHARPR" },
        forward: { kind: "REPLACE_TEXT_RANGE", paragraphId,
          rangeAnchor: 0, rangeFocus: before.length,
          afterText: newText, applyCharPrIDRef: applyPr,
          policy: "ANCHOR_CHARPR" },
        expectedBefore: before,
        sourceDocumentHash: model.sourceDocumentHash
          || (model.sourceRef && model.sourceRef.sha256),
      }, { onOk: () => paraEdits.set(paragraphId, newText) }));
    } catch (e) {
      setStatus("fail", "문단 저장 실패: " + (e.message || e));
      return false;
    } finally {
      paraBusy = false;
    }
  }

  // 두 편집 경로(전체 교체/캐럿 삽입) 공용 — 요청 전송 + 결과 반영 +
  // 재로딩. 서버는 command 개별 sourceDocumentHash 를 검증한다(요청
  // 최상위 필드가 아니라) — para_save_apply_bridge._hydrate_command.
  async function _runParaSaveCommand(model, command, opts = {}) {
    const res = await fetch("/api/web-office/para-save-apply", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        operation: "PARA_SAVE_APPLY",
        sourcePath: loaded.sourcePath,
        sourceDocumentHash: model.sourceDocumentHash
          || (model.sourceRef && model.sourceRef.sha256),
        dryRunOnly: false,
        commandLog: [command],
        // 대표님 지시(2026-07-24 정책 개정) — 원본 직접 수정.
        editInPlace: true,
      }),
    });
    const env = await res.json();
      const d = (env && env.data) || {};
      const okVerdicts = new Set(["PASS", "PARTIAL"]);
      if (!(env && env.status === "SUCCESS") || !okVerdicts.has(d.verdict)) {
        const msg = (env.errors && env.errors[0] && env.errors[0].message)
          || (d.rejected && d.rejected[0] && d.rejected[0].reason)
          || d.verdict || "문단 저장 실패";
        setStatus("fail", "문단 저장 거부: " + msg);
        return false;
      }
      const paragraphId = command.target.paragraphId;
      if (opts.onOk) opts.onOk();
      setStatus("ok", (d.editedInPlace
        ? "문단 저장 완료(원본 파일에 반영됨)"
        : "문단 저장 완료(새 sandbox 사본)") + " · 재로딩 …");
      // writer 가 이제 편집된 문단의 lineseg 를 보존(줄 수 증가 추정 시만
      // 근사 보정)하므로, 새 레이아웃을 다시 물어보면 그 문단의 실제 줄
      // 좌표가 나온다 — 더 이상 "편집 전 좌표를 계속 쓰는" 임시방편이
      // 필요 없다(실측 확인: 재요청 시 해당 paragraphId 줄 정상 반환).
      // documentModel/sourcePath 도 함께 갱신 — 다음 편집이
      // SOURCE_HASH_MISMATCH 로 거부되지 않게 한다.
      if (d.sourcePath) {
        try {
          const res2 = await fetch("/api/web-office/hwpx-load", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ operation: "HWPX_EDITOR_LOAD",
              sourcePath: d.sourcePath }),
          });
          const env2 = await res2.json();
          const d2 = (env2 && env2.data) || {};
          if (env2 && env2.status === "SUCCESS" && d2.verdict === "PASS") {
            loaded.sourcePath = d2.sourcePath;
            loaded.documentModel = d2.documentModel;
          } else {
            loaded.sourcePath = d.sourcePath;   // 최소한 체이닝은 유지
          }
        } catch (_e) {
          loaded.sourcePath = d.sourcePath;
        }
      }
      // cell 컨트롤러 재동기화 — 실측(2026-07-24)으로 발견한 결함: 문단
      // 저장이 sourceDocumentHash 를 바꿔도(원본이 갱신됨) cell 컨트롤러는
      // 최초 로드 시점의 documentModel(구 hash)을 그대로 들고 있어, 그
      // 뒤에 표 셀을 편집·저장하면 서버가 SOURCE_HASH_MISMATCH 로 거부
      // 한다("문단 먼저 고치고 표 셀 고치면 셀 저장이 안 되는" 결함).
      // 미저장 셀 편집(commandLog)이 있으면 재구성 시 유실되므로, 그때는
      // 건드리지 않는다(다음 셀 저장이 거부되는 게 편집 유실보다 안전).
      resyncCellControllerIfIdle();
      // 이 문단은 이제 실제 좌표로 다시 그려질 것이므로 클라이언트 캐시
      // 오버레이는 걷어낸다("덧방" 제거) — 아래 재로딩된 좌표가 진실.
      paraEdits.delete(paragraphId);
      // truthBase(한컴 실렌더 배경 URL) 를 먼저 비운다 — 안 비우면 아래
      // render() 가 "이전 파일"의 낡은 사진을 그대로 보여준다(실측
      // 확인: 연속 저장 시 두 번째부터 화면이 안 바뀌는 것처럼 보이던
      // 결함 — probeTruth 가 새 사진을 못 구해오면(한컴 렌더 실패
      // → 404, 설계상 정상 폴백 신호) truthBase 가 영영 갱신 안 돼
      // 화면이 그 이전 상태에 멈춰 있었다). 좌표 렌더러는 항상 최신
      // documentModel 기준으로 정확하므로, truthBase 없이 먼저
      // 보여주고 사진은 준비되면 probeTruth 가 덮어씌운다.
      truthBase = null;
      coordLayout = await fetchLayout(loaded.sourcePath);
      render();
      probeTruth(loaded.sourcePath);
      return true;
  }

  // 상시 편집 가능한 문단 흐름 상자(대표님 지시, 2026-07-24: "워드
  // 프로그램으로 개발해") — 페이지마다 본문 문단들을 클릭 없이도 항상
  // contentEditable 상태인 하나의 흐름 상자로 묶는다. 브라우저 자체
  // 텍스트 흐름 엔진을 그대로 빌려 쓰므로:
  //   · 클릭 즉시 타이핑(팝업 없음)
  //   · 화살표/Home/End 키 이동은 브라우저 기본 동작 — 별도 구현 불필요
  //   · 문단이 늘어나면 같은 상자 안 뒤 문단들이 즉시 아래로 밀림(정상
  //     블록 흐름이라 절대좌표 재계산 없이 공짜로 됨)
  // 한계(명시): 표가 문단들 사이에 끼어 있으면 표는 여전히 절대좌표라
  // 겹칠 수 있다(이번 범위는 본문 문단 전용). 한컴의 정확한 조판
  // 알고리즘(자간·justify 압축)을 재구현한 것도 아니다 — 브라우저
  // 자체 렌더링 기반 근사.
  function mountAlwaysOnParagraphFlow(sheet) {
    sheet.querySelectorAll(".co-page").forEach((page) => {
      const lines = [...page.querySelectorAll(".co-line[data-paragraph-id]")];
      if (!lines.length) return;
      const order = [];
      const firstLineOf = new Map();
      for (const l of lines) {
        const pid = l.dataset.paragraphId;
        if (!firstLineOf.has(pid)) { firstLineOf.set(pid, l); order.push(pid); }
      }
      const pageRect = page.getBoundingClientRect();
      const tops = order.map((pid) =>
        firstLineOf.get(pid).getBoundingClientRect().top - pageRect.top);
      // 표 시작 y 목록(오름차순) — 문단 사이에 표가 끼어 있으면(표 호스트
      // 문단은 자체 텍스트가 없어 order 에 안 잡히는 게 흔함) 그 표 앞뒤
      // 문단을 같은 흐름상자 하나에 넣을 수 없다. 표는 흐름상자 DOM 밖의
      // 별도 절대배치 요소라, 한 상자 안에 표 앞뒤 문단을 함께 두면
      // (일반 블록 흐름이라) 표가 차지하는 세로 공간이 전혀 반영 안 돼
      // 뒤 문단이 표가 없는 것처럼 바짝 붙어 표 위에 겹쳐 그려지는
      // 결함이 있었다(실사례: Playwright 실측 — 표 입력칸 클릭이 항상
      // 그 표 뒤에 있어야 할 문단의 흐름상자에 가로채임). 표를 사이에 두고
      // 흐름상자를 별도로 쪼개, 뒤쪽 상자는 자기 문단의 실제 원본 위치에
      // 새로 절대배치한다(표 공간을 건너뛰는 효과).
      const tableTops = [...page.querySelectorAll(".co-box[data-cell-id]")]
        .map((b) => b.getBoundingClientRect().top - pageRect.top)
        .sort((a, b) => a - b);
      const segments = [];
      let segStart = 0;
      for (let i = 0; i < order.length - 1; i++) {
        const hasTableBetween = tableTops.some(
          (tt) => tt > tops[i] + 1 && tt < tops[i + 1] - 1);
        if (hasTableBetween) {
          segments.push([segStart, i]);
          segStart = i + 1;
        }
      }
      segments.push([segStart, order.length - 1]);

      for (const [segFrom, segTo] of segments) {
        const segOrder = order.slice(segFrom, segTo + 1);
        let minX = Infinity, minY = Infinity, maxW = 0;
        for (const pid of segOrder) {
          const r = firstLineOf.get(pid).getBoundingClientRect();
          minX = Math.min(minX, r.left - pageRect.left);
          minY = Math.min(minY, r.top - pageRect.top);
          maxW = Math.max(maxW,
            parseFloat(firstLineOf.get(pid).style.width) || r.width);
        }
        const flow = document.createElement("div");
        flow.className = "wo-flowbox";
        flow.contentEditable = "true";
        flow.spellcheck = false;
        // background:#fff 필수 — 원본 실렌더 배경(사진) 모드는 텍스트가
        // .co-page 의 배경 사진 픽셀 자체라 DOM visibility 로 못 가린다.
        // 불투명 배경으로 그 아래 사진 글자를 완전히 덮어야 이중 노출
        // (사진 원문 + 편집 상자 겹쳐 보임)이 안 생긴다.
        flow.style.cssText = `position:absolute; left:${minX}px; `
          + `top:${minY}px; width:${maxW}px; z-index:4; outline:none; `
          + "background:#fff;";
        const origText = new Map();
        // 각 문단이 원본에서 차지하던 세로 슬롯(다음 문단 시작 Y 까지의
        // 간격, 세그먼트의 마지막 문단은 표 시작 지점까지)을 min-height
        // 로 줘서, 안 고친 문단은 원본과 거의 같은 위치를 유지하고 뒤
        // 표 등과 안 겹치게 한다. 실제로 늘어나면(줄 수 증가) min-height
        // 를 넘어서며 자연스럽게 뒤 문단을 밀어낸다.
        for (let i = segFrom; i <= segTo; i++) {
          const pid = order[i];
          const l = firstLineOf.get(pid);
          // data-font-css(렌더러가 실제 charPr 에서 뽑은 대표 서식)를
          // 우선 쓴다 — "원본 실렌더 배경" 모드는 .co-in > span 자체가
          // 없어(사진 위 투명 클릭 타깃만 존재) 예전 span 샘플링은 늘
          // 빈 문자열로 떨어져 편집 상자가 원본보다 작은 기본 크기로
          // 그려지는 결함이 있었다(실사례: "10-3." 문단이 목록 다른
          // 항목보다 큰 서식이라 편집 상자 덮개가 사진 글자를 다 못
          // 가려 겹쳐 보임).
          const fontCss = l.dataset.fontCss
            || (l.querySelector(".co-in > span")?.getAttribute("style") || "");
          const srcPara = (loaded.documentModel.paragraphs || [])
            .find((p) => p.paragraphId === pid);
          const cur = paraEdits.has(pid) ? paraEdits.get(pid)
            : (srcPara && srcPara.text) || "";
          origText.set(pid, cur);
          const d = document.createElement("div");
          d.dataset.paragraphId = pid;
          // 편집 전(원본 그대로)이면 run 단위 서식을 그대로 재현 —
          // 편집 후엔 어느 run 이 늘어났는지 알 수 없어(REPLACE_TEXT_RANGE
          // 는 anchor-run 서식으로 전체 통일) 대표 서식 하나로 되돌아간다
          // (백엔드 저장 정책과 동일 원칙: 전체 교체는 anchor charPr).
          if (!paraEdits.has(pid) && srcPara && srcPara.runs
              && srcPara.runs.length > 1 && coordLayout.charPrDefs) {
            renderRunSpans(d, srcPara.runs, coordLayout.charPrDefs);
          } else {
            d.textContent = cur;
          }
          let slot = (i < segTo)
            ? Math.max(0, tops[i + 1] - tops[i])
            : (parseFloat(l.style.height) || 20);
          const nextTableTop = tableTops.find((tt) => tt > tops[i] + 1);
          if (nextTableTop != null) {
            slot = Math.min(slot, Math.max(0, nextTableTop - tops[i]));
          }
          d.style.cssText = "white-space:pre-wrap; word-break:break-word; "
            + `overflow-wrap:anywhere; min-height:${slot}px;` + fontCss;
          flow.appendChild(d);
        }

        let syncing = false;
        const syncAndSave = () => {
          if (syncing) return;
          syncing = true;
          try {
            for (const d of [...flow.querySelectorAll("[data-paragraph-id]")]) {
              const pid = d.dataset.paragraphId;
              const before = origText.get(pid);
              const now = d.textContent;
              if (now !== before) {
                // origText 는 저장이 실제로 성공했을 때만 갱신한다 —
                // 거부(REJECTED)된 뒤에도 낙관적으로 먼저 갱신해버리면,
                // 실패한 편집이 "이미 반영됨"으로 착각돼 다음 blur 에서
                // 다시 시도되지 않고 조용히 유실된다(코드 검증 중 발견).
                saveParagraphText(pid, now).then((ok) => {
                  if (ok) origText.set(pid, now);
                });
              }
            }
          } finally {
            syncing = false;
          }
        };
        flow.addEventListener("blur", syncAndSave);
        flow.addEventListener("keydown", (e) => {
          // 문단 분할(PARA_INSERT)은 이번 범위 밖 — Enter 는 새 문단을
          // 만들지 않고 지금까지 바뀐 문단들을 저장하는 커밋으로 취급.
          if (e.key === "Enter") { e.preventDefault(); syncAndSave(); }
        });
        flow.addEventListener("mouseup", updateParaSelFromSelection);
        flow.addEventListener("keyup", updateParaSelFromSelection);
        page.appendChild(flow);
      }
      lines.forEach((l) => { l.style.visibility = "hidden"; });
    });
  }

  // 흐름 상자 안 텍스트 선택 → 서식 버튼 대상(paragraphId + 문자 범위)
  // 갱신. 선택이 비어있거나 흐름 상자 밖이면 해제.
  function updateParaSelFromSelection() {
    const clearAndDisable = () => {
      paraSelTarget = null;
      // 셀이 별도로 선택돼 있으면(selectCellForFormat) 그 서식 버튼
      // 상태를 건드리지 않는다 — 흐름 상자 선택 해제와 무관한 대상.
      if (!selectedCellId) {
        ["fmt-bold", "fmt-italic", "fmt-underline", "fmt-size", "fmt-color"]
          .forEach((r) => { $(`[data-role=${r}]`).disabled = true; });
      }
    };
    const sel = window.getSelection();
    if (!sel || sel.rangeCount === 0) { clearAndDisable(); return; }
    const range = sel.getRangeAt(0);
    const startEl = (range.startContainer.nodeType === 1
      ? range.startContainer : range.startContainer.parentElement);
    const pdiv = startEl && startEl.closest
      ? startEl.closest("[data-paragraph-id]") : null;
    if (!pdiv || !pdiv.closest(".wo-flowbox")) { clearAndDisable(); return; }
    const startOff = _localTextOffset(pdiv, range.startContainer, range.startOffset);
    const endOff = _localTextOffset(pdiv, range.endContainer, range.endOffset);
    if (startOff === endOff) { clearAndDisable(); return; }
    paraSelTarget = { paragraphId: pdiv.dataset.paragraphId,
      start: Math.min(startOff, endOff), end: Math.max(startOff, endOff) };
    ["fmt-bold", "fmt-italic", "fmt-underline", "fmt-size", "fmt-color"]
      .forEach((r) => { $(`[data-role=${r}]`).disabled = fmtBusy; });
  }

  function _localTextOffset(container, node, nodeOffset) {
    const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
    let total = 0, n;
    while ((n = walker.nextNode())) {
      if (n === node) return total + nodeOffset;
      total += n.textContent.length;
    }
    return total;
  }

  // 서식 툴바 — 클릭된 칸을 서식 적용 대상으로 표시하고 버튼을 켠다.
  function selectCellForFormat(id, box) {
    selectedCellId = id;
    // 흐름 상자 쪽 텍스트 선택은 셀 클릭보다 오래된 상태일 수 있다 —
    // 지우지 않으면 applyFormat 이 우선순위상 그 낡은 선택을 계속 쓰게
    // 되어 방금 클릭한 셀이 아니라 엉뚱한 문단에 서식이 적용된다
    // (코드 검증 중 발견).
    paraSelTarget = null;
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
    if (!loaded || fmtBusy) return;
    // 흐름 상자 안 텍스트 선택이 있으면 그 문단·범위 우선(대표님 지시:
    // "선택 영역 지정 후 서식 버튼 적용"), 없으면 기존 셀 전체 서식 경로.
    let pid, rangeAnchor, rangeFocus;
    if (paraSelTarget) {
      pid = paraSelTarget.paragraphId;
      rangeAnchor = paraSelTarget.start;
      rangeFocus = paraSelTarget.end;
    } else {
      if (!selectedCellId) return;
      const text = cell.currentText(selectedCellId);
      if (text == null) return;
      const model = loaded.documentModel || {};
      const c = (model.cells || []).find((x) => x.cellId === selectedCellId);
      pid = c && c.paragraphs && c.paragraphs[0]
        && c.paragraphs[0].paragraphId;
      rangeAnchor = 0;
      rangeFocus = text.length;
    }
    if (!pid) { setStatus("fail", "서식 대상 문단을 찾을 수 없음"); return; }
    fmtBusy = true;
    setStatus("load", "서식 적용 중 …");
    try {
      const res = await fetch("/api/web-office/apply-format", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          sourcePath: loaded.sourcePath, paragraphId: pid,
          rangeAnchor, rangeFocus, overrides,
          // 대표님 지시(2026-07-24 정책 개정) — 원본 직접 수정.
          editInPlace: true,
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
      // editInPlace 면 원본 그대로, 아니면 서버가 만든 새 sandbox 파일을
      // 다음 편집의 기준으로 이어받는다.
      loaded.sourcePath = d.sourcePath;
      setStatus("ok", (d.editedInPlace
        ? "서식 적용 완료(원본 파일에 반영됨)"
        : "서식 적용 완료(새 sandbox 사본)") + " · 재로딩 …");
      // documentModel 도 함께 갱신 — 문단 저장과 동일한 이유(실측으로
      // 발견한 결함: 서식 적용도 sourceDocumentHash 를 바꾸는데 여기서는
      // documentModel 을 아예 안 갱신해, 그 뒤 표 셀 저장이
      // SOURCE_HASH_MISMATCH 로 거부됐다).
      try {
        const res2 = await fetch("/api/web-office/hwpx-load", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ operation: "HWPX_EDITOR_LOAD",
            sourcePath: d.sourcePath }),
        });
        const env2 = await res2.json();
        const d2 = (env2 && env2.data) || {};
        if (env2 && env2.status === "SUCCESS" && d2.verdict === "PASS") {
          loaded.sourcePath = d2.sourcePath;
          loaded.documentModel = d2.documentModel;
        }
      } catch (_e) { /* sourcePath 체이닝은 이미 반영됨 — 무시 */ }
      resyncCellControllerIfIdle();
      // truthBase 선-초기화 — saveParagraphText 와 동일 이유(이전 파일의
      // 낡은 실렌더 사진이 새 파일 렌더에도 그대로 남아, probeTruth 가
      // 실패(404, 정상 폴백 신호)하면 화면이 그 이전 상태에 영영
      // 멈춰 있던 결함).
      truthBase = null;
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
        getParaText: (id) => (paraEdits.has(id) ? paraEdits.get(id) : null),
        // 대표님 지시(2026-07-24: "한컴 원본 밑그림을 사용하고 화면에
        // 노출 안되게") — probeTruth 는 그대로 돌려 한컴 실측 정렬
        // (snap_layout_to_truth, 쪽수 정합 확인)은 계속 활용하되, 그
        // 사진 자체를 배경으로 그리지는 않는다(truthBase 를 렌더러에
        // 안 넘김). 사진을 화면에 노출하면 우리 근사 렌더링(폰트 대체·
        // 좌표 추정)과 실제 한컴 픽셀이 어긋나는 지점마다 "원문이 편집
        // 상자 밖으로 삐져나와 보이는" 결함이 반복 발생했다("10-3."
        // 문단, 결재란 표 등 실사례) — 사진을 아예 안 그리면 이 결함
        // 부류 전체가 원천 차단된다. 대신 우리 자체 CSS 렌더(테두리·
        // 채움·charPr 기반 서식)만으로 그린다.
        truthBase: null,
      });
      autoFitLines(sheet);
      // 상시 캐럿 편집(대표님 지시, 2026-07-24: "전체 문서를 어떤것이든
      // 캐럿 방식으로") — 표 셀도 문단과 동일하게 클릭 즉시 그 자리에서
      // 캐럿으로 끼워쓰는 방식으로 통일한다. 팝업형 <input> 은 없고, 칸의
      // 실제 텍스트 자리에 contentEditable 상자가 상시 존재한다. 단, 저장
      // 트리거는 문단과 다르게 유지(대표님 선택) — blur 는 로컬
      // commandLog 에만 쌓고(cell.setCellText, 기존과 동일), 서버 반영은
      // 여러 칸 편집 후 "저장(sandbox)" 버튼을 눌러야 한다(일괄 검토 후
      // 저장하고 싶을 때 유리).
      const cellFlowBoxes = [];
      sheet.querySelectorAll(".co-box[data-cell-id]").forEach((box) => {
        if (box.dataset.frag) return;   // 병합 셀의 다음 페이지 조각은 스킵
        const id = box.dataset.cellId;
        const isInput = cell.isInputCell(id);   // 파서(XML) 분류 단일 진실
        box.classList.add(isInput ? "wo-input" : "wo-label");
        // 서식 툴바 대상 — 클릭된 어떤 칸(입력/라벨 무관)이든 선택 표시.
        box.addEventListener("click", () => selectCellForFormat(id, box));

        const ph = isInput ? cell.inputLabel(id) : null;
        let cur, cellEdited;
        if (isInput) {
          const raw = cell.currentText(id);
          // 마커 칸([입력필요: ...])은 마커 원문을 값으로 노출하지 않고
          // 빈 값에서 시작 — placeholder 로만 항목명을 보여준다.
          const isMarker = ph && /\[입력필요:/.test(raw);
          const edited = cell.getCellText(id);
          // "입력칸"이어도 원본에 이미 서식·줄바꿈이 있는 기본값이 채워진
          // 경우가 있다(예: "문서번호 : 0000-000 호" — 라벨+값이 서로
          // 다른 charPr 로 한 칸에 같이 들어있음, "국토교통부장관"/
          // "교육관리기관의 장" — 원래 두 줄인데 모델 cell.text 는
          // 정규화 과정에서 줄바꿈 없이 한 문자열로 합쳐 놓음). 아직
          // 사용자가 고친 적 없으면(edited == null) faithfulCellText
          // (줄 순서·개행 원형 보존)를 raw 보다 우선 — 실사례: 안 그러면
          // 두 줄이 한 줄로 붙어 박스 폭 기준으로 엉뚱한 지점에서
          // 줄바꿈돼 "국토교통부장관교육관리기 / 관의장"처럼 보임.
          cur = isMarker ? "" : (edited != null ? raw
            : (faithfulCellText(id) || raw));
          cellEdited = isMarker || edited != null;
        } else {
          // 라벨(원래 문구): 편집된 적 있으면 현재값, 아니면 충실 원문
          // (정규화 아님)을 prefill — 자간·공백 원형 유지.
          const edited = cell.getCellText(id);
          cur = edited != null ? edited : (faithfulCellText(id) || "");
          cellEdited = edited != null;
        }

        const d = document.createElement("div");
        d.contentEditable = "true";
        d.spellcheck = false;
        d.className = "wo-cell-flow";
        d.dataset.cellId = id;
        // 원본 그대로(미편집) 라벨 칸은 run 단위 서식을 그대로 재현한다
        // (대표님 지시: "원본 서식을 그대로 유지") — 한 칸 안에 서식이
        // 섞여 있어도(예: "문서번호 : "+"0000-000 "+"호" 가 서로 다른
        // charPr) 이제 그 구분이 편집 상자 화면에도 그대로 보인다.
        const srcCell = (loaded.documentModel.cells || [])
          .find((c) => c.cellId === id);
        const srcRuns = srcCell && srcCell.paragraphs
          && srcCell.paragraphs[0] && srcCell.paragraphs[0].runs;
        if (!cellEdited && srcRuns && srcRuns.length > 1
            && coordLayout.charPrDefs) {
          renderRunSpans(d, srcRuns, coordLayout.charPrDefs);
        } else {
          d.textContent = cur;
        }
        // 대표님 지시(2026-07-24: "완전히 제거, 원본처럼 빈 칸으로") —
        // 빈 입력칸 안내 문구(주황색 placeholder)를 없앤다. 실제 원본
        // 문서는 이 칸들이 그냥 빈칸이라, 안내 문구가 라벨 옆에 겹쳐
        // 보이는 게 "표가 원본과 다르다"는 인상을 줬다. 어떤 칸이
        // 입력칸인지는 hover(.wo-input CSS)로만 알 수 있게 남긴다.
        const fontCss = box.dataset.fontCss || "";
        // 편집 상자 위치·크기 — 한컴이 저장한 실제 좌표(lineseg)를 그대로
        // 쓴다(대표님 지시: "한컴 문서 좌표대로 폰트 위치도 동일해야").
        // 사진 배경을 껐으므로(이전 턴) 더 이상 "사진 삐져나옴" 걱정 없이
        // 정밀 좌표로 되돌릴 수 있다. 단, 첫 줄 하나만 보면(과거 결함)
        // 세로쓰기·여러 줄 칸("결재" 6글자 세로쓰기)에서 상자가 실제 내용의
        // 일부 크기로만 잡혀 표가 뒤틀리므로, 이 셀의 모든 줄을 모아
        // 바운딩박스(좌상단 min, 우하단 max)로 잡는다 — 정확한 좌표 기반
        // 이면서도 다중 줄/세로쓰기 모두 안전하다.
        const pgIdx = [...sheet.querySelectorAll(".co-page")]
          .indexOf(box.closest(".co-page"));
        const pdc = (coordLayout.pagesDetail || [])[pgIdx];
        const cellLines = pdc
          ? pdc.lines.filter((l) => l.cellId === id) : [];
        const boxTop = parseFloat(box.style.top) || 0;
        const boxLeft = parseFloat(box.style.left) || 0;
        const boxW = parseFloat(box.style.width) || 0;
        const boxH = parseFloat(box.style.height) || 0;
        let top, left, width, minHeight;
        if (cellLines.length) {
          const yMin = Math.min(...cellLines.map((l) => l.y));
          const yMax = Math.max(...cellLines.map((l) => l.y + l.h));
          const xMin = Math.min(...cellLines.map((l) => l.x));
          top = Math.max(0, yMin - boxTop - 1);
          left = Math.max(0, xMin - boxLeft - 1);
          width = Math.max(10, boxW - (xMin - boxLeft) - 2);
          minHeight = Math.max(14, yMax - yMin) + 4;
        } else {
          top = 1; left = 2;
          width = Math.max(10, boxW - 4);
          minHeight = Math.max(14, boxH - 2);
        }
        d.style.cssText = `position:absolute; left:${left}px; `
          + `top:${top}px; width:${width}px; `
          + `min-height:${minHeight}px; `
          + "background:#fff; outline:none; z-index:5; "
          + "white-space:pre-wrap; word-break:break-word; "
          + `overflow-wrap:anywhere;${fontCss}`;
        const origVal = cur;
        const commit = () => {
          const v = d.textContent;
          // 마커 보존 — 빈 값이면 마커 원문 유지(문서 훼손 방지)
          const changed = (v !== origVal) && !(ph && v === "")
            && cell.setCellText(id, v);
          if (changed) render();   // 값이 문서 텍스트로 렌더됨(재렌더)
        };
        d.addEventListener("blur", commit);
        d.addEventListener("keydown", (e) => {
          if (e.key === "Enter") { e.preventDefault(); commit(); focusNav(id, "down"); }
          else if (e.key === "Tab") {
            e.preventDefault(); commit();
            focusNav(id, e.shiftKey ? "left" : "right");
          } else if (e.key === "ArrowUp" || e.key === "ArrowDown") {
            e.preventDefault(); commit();
            focusNav(id, e.key === "ArrowUp" ? "up" : "down");
          } else if (e.key === "Escape") {
            d.textContent = origVal; d.blur();
          }
        });
        box.appendChild(d);
        cellFlowBoxes.push({ id, el: d });
      });
      // 엑셀식 이동 — 1차: 같은 열/행(구간 겹침)에서 방향으로 가장 가까운
      // 칸, 2차(없으면): 겹침 없이 방향만 맞는 최근접 칸. 표·페이지 경계를
      // 넘어 편집 상자들이 하나의 격자처럼 이어진다.
      const cellGeom = cellFlowBoxes.map((it) => {
        const r = it.el.getBoundingClientRect();
        return { ...it, x0: r.left, x1: r.right, y0: r.top, y1: r.bottom,
          cx: (r.left + r.right) / 2, cy: (r.top + r.bottom) / 2 };
      });
      function focusNav(fromId, dir) {
        const cur = cellGeom.find((g) => g.id === fromId);
        if (!cur) return;
        const horiz = dir === "left" || dir === "right";
        const sgn = (dir === "right" || dir === "down") ? 1 : -1;
        let best = null, bestKey = Infinity;
        const scan = (needOverlap) => {
          for (const g of cellGeom) {
            if (g === cur) continue;
            const d2 = horiz ? (g.cx - cur.cx) * sgn : (g.cy - cur.cy) * sgn;
            if (d2 <= 2) continue;
            const ov = horiz
              ? Math.min(g.y1, cur.y1) - Math.max(g.y0, cur.y0)
              : Math.min(g.x1, cur.x1) - Math.max(g.x0, cur.x0);
            if (needOverlap && ov <= 0) continue;
            const perp = horiz
              ? Math.abs(g.cy - cur.cy) : Math.abs(g.cx - cur.cx);
            const key = d2 + perp * 4;
            if (key < bestKey) { bestKey = key; best = g; }
          }
        };
        scan(true);
        if (!best) scan(false);
        if (best) {
          best.el.focus();
          const range = document.createRange();
          range.selectNodeContents(best.el);
          const sel = window.getSelection();
          sel.removeAllRanges(); sel.addRange(range);
          best.el.scrollIntoView({ block: "nearest", inline: "nearest" });
        }
      }
      // 본문 문단(표 밖 제목·전문 등) — 대표님 지시(2026-07-24: "워드
      // 프로그램으로 개발해") 반영. 클릭해야 열리는 팝업형 편집기 대신,
      // 페이지마다 문단들을 하나의 상시 편집 가능한 흐름 상자(contentEditable,
      // 실제 브라우저 텍스트 흐름)로 묶어 렌더한다 — 클릭 즉시 타이핑,
      // 화살표/Home/End 키 이동은 브라우저 기본 동작 그대로 무료로 따라오고,
      // 문단이 늘어나면 같은 상자 안 뒤 문단들이 즉시 아래로 밀린다.
      mountAlwaysOnParagraphFlow(sheet);
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

  // 한컴 실측 정합 확인(대표님 지시, 2026-07-24: "한컴 원본 밑그림을
  // 사용하고 화면에 노출 안되게") — 한컴 실렌더 페이지(서버 캐시)는
  // snap_layout_to_truth 좌표 스냅·쪽수 정합 검증에만 쓰고, 사진 자체를
  // 화면 배경으로 노출하지는 않는다(truthBase 는 render() 에 더 이상
  // 안 넘김 — 사진과 우리 근사 렌더링의 미세한 어긋남이 "원문이 편집
  // 상자 밖으로 삐져나와 보이는" 결함 부류의 원인이었다). 첫 문서는
  // 서버에서 한컴 조판(수 초)이 돌 수 있어 비동기 프로브 후 재렌더한다.
  // 404(한컴 미설치 서비스 환경)면 좌표 렌더 그대로 — 무중단 폴백.
  async function probeTruth(sourcePath) {
    truthBase = null;
    if (!sourcePath) return;
    const base = `${TRUTH_ENDPOINT}?src=${encodeURIComponent(sourcePath)}&page=`;
    try {
      const res = await fetch(base + "1", { method: "GET" });
      if (res.ok) {
        // 실측 준비됨 → 레이아웃 재요청: 서버가 truth 격자선에 정합등록+
        // 스냅한 좌표(truthAligned)를 내려준다 — 화면엔 이 스냅된 좌표로
        // 우리 자체 렌더만 그리고, 사진 자체는 그리지 않는다.
        const aligned = await fetchLayout(loaded && loaded.sourcePath);
        if (aligned) coordLayout = aligned;
        const hp = aligned && aligned.hancomPages;
        if (hp && aligned.pages !== hp) {
          setStatus("ok", ($("[data-role=status]").textContent || "")
            + ` · 한컴 정합 보류(쪽수 ${aligned.pages}≠한컴 ${hp})`);
          render();
          return;
        }
        truthBase = base;   // 화면엔 안 씀 — 정합 확인됐다는 내부 표시만
        setStatus("ok", ($("[data-role=status]").textContent || "")
          + " · 한컴 정합 확인"
          + (aligned && aligned.truthAligned ? "(스냅됨)" : ""));
        render();
      }
    } catch (_e) { /* 폴백 유지 */ }
  }

  async function onLoaded(d) {
    loaded = d;
    coordLayout = null;
    truthBase = null;
    selectedCellId = null;
    paraSelTarget = null;
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
    setStatus("load", "저장 중(검증 통과 후 원본 반영) …");
    const r = await save.save();
    if (!r.ok) setStatus("fail", "저장 거부: " + r.code);
    else setStatus("ok", r.editedInPlace
      ? "저장 완료 — verify7 통과 · 원본 파일에 반영됨."
      : "저장 완료 — verify7 통과 · 원본 무수정 · 편집본 다운로드 가능.");
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
