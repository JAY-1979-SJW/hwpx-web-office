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
  const paraEdits = new Map();  // paragraphId → 편집된 텍스트(표 셀 아님)
  let paraBusy = false;        // 본문 문단 저장 중 표시(상태줄 용)
  // 저장 요청 직렬화 큐 — 실측(2026-07-24) 확인된 결함: 이전 저장이
  // 아직 끝나기 전(한컴 실렌더 배경 재계산은 수 초 걸림) 사용자가 다음
  // 문단을 편집·커밋하면, 예전에는 paraBusy 가드가 그 요청을 "조용히
  // 버렸다"(편집기는 이미 닫혀 텍스트 유실, 에러 표시도 없음) — 이게
  // "클릭은 되는데 저장은 안 된다" 신고의 실제 원인이었다. 이제는
  // 버리지 않고 큐에 이어 붙여 이전 저장이 끝나면 순서대로 실행한다.
  let paraSaveQueue = Promise.resolve();

  function saveParagraphText(paragraphId, newText) {
    paraSaveQueue = paraSaveQueue
      .then(() => _doSaveParagraphText(paragraphId, newText))
      .catch((e) => setStatus("fail", "문단 저장 실패: " + (e.message || e)));
    return paraSaveQueue;
  }

  // 캐럿 위치 삽입(문장 중 클릭한 지점에만 타이핑) — 문단 전체를
  // 통째로 바꾸는 REPLACE_TEXT_RANGE 대신, 그 지점에만 글자를 끼워
  // 넣는 TYPE_TEXT 를 쓴다. 실측: 서버(paragraph_writer_adapter)는
  // applyCharPrIDRef 를 안 주면 그 지점 run 의 기존 charPr 을 그대로
  // 쓰므로(신규 charPr 미생성) 여기서 서식을 계산할 필요가 없다.
  function insertAtCaret(paragraphId, caretOffset, insertText) {
    if (!insertText) return Promise.resolve();
    paraSaveQueue = paraSaveQueue
      .then(() => _doInsertAtCaret(paragraphId, caretOffset, insertText))
      .catch((e) => setStatus("fail", "문단 저장 실패: " + (e.message || e)));
    return paraSaveQueue;
  }

  // 캐럿 위치가 속한 run 의 charPrIDRef — verify7 V4(신규 charPr 도입
  // 금지) 게이트가 applyCharPrIDRef==null 을 "원본에 없던 서식"으로
  // 보고 거부하므로(실측 확인), null 을 보내면 안 되고 반드시 그
  // 위치의 실제 run 서식을 지정해야 한다.
  function _charPrAtOffset(paragraph, offset) {
    let pos = 0;
    for (const r of (paragraph.runs || [])) {
      const len = (r.text || "").length;
      if (offset <= pos + len) return r.charPrIDRef ?? null;
      pos += len;
    }
    const runs = paragraph.runs || [];
    return runs.length ? runs[runs.length - 1].charPrIDRef : null;
  }

  async function _doInsertAtCaret(paragraphId, caretOffset, insertText) {
    if (!loaded) return;
    const model = loaded.documentModel || {};
    const p = (model.paragraphs || []).find(
      (x) => x.paragraphId === paragraphId);
    const applyPr = p ? _charPrAtOffset(p, caretOffset) : null;
    paraBusy = true;
    setStatus("load", "문단 저장 중 …");
    try {
      await _runParaSaveCommand(model, {
        commandId: `pc_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
        commandType: "TYPE_TEXT",
        target: { paragraphId },
        payload: { caretOffset, insertText },
        forward: { kind: "TYPE_TEXT", paragraphId,
          caretOffset, insertText, inheritCharPrIDRef: applyPr },
        expectedBefore: "",
        sourceDocumentHash: model.sourceDocumentHash
          || (model.sourceRef && model.sourceRef.sha256),
      });
    } catch (e) {
      setStatus("fail", "문단 저장 실패: " + (e.message || e));
    } finally {
      paraBusy = false;
    }
  }

  // 본문 문단(표 밖 제목·전문 등) 저장 — 셀과 달리 undo/redo 명령 로그가
  // 없다. apply-format 과 동일하게 즉시 서버에 저장하고 sourcePath 를
  // 이어받는다(원본은 무수정, 결과는 항상 새 sandbox 사본).
  async function _doSaveParagraphText(paragraphId, newText) {
    if (!loaded) return;
    const model = loaded.documentModel || {};
    const p = (model.paragraphs || []).find(
      (x) => x.paragraphId === paragraphId);
    if (!p) { setStatus("fail", "편집 대상 문단을 찾을 수 없음"); return; }
    // 재편집 시 서버 기준값은 직전 편집 결과(이미 sourcePath 가 그
    // sandbox 사본으로 갱신돼 있음) — 원본 documentModel.text 가 아니라
    // paraEdits 에 남은 마지막 저장값을 expectedBefore 로 써야 두 번째
    // 편집부터 EXPECTED_BEFORE_MISMATCH 로 거부되지 않는다.
    const before = paraEdits.has(paragraphId)
      ? paraEdits.get(paragraphId) : (p.text || "");
    // 전체 교체는 첫 run(오프셋 0)의 charPr 을 그대로 적용 — 신규 charPr
    // 생성 없음(§4 유지). 다중 run 문단도 anchor(첫 run) 서식으로 통일.
    const applyPr = (p.runs && p.runs[0] && p.runs[0].charPrIDRef) || null;
    if (before === newText) return;   // 무변경 — 저장 안 함
    paraBusy = true;
    setStatus("load", "문단 저장 중 …");
    try {
      await _runParaSaveCommand(model, {
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
      }, { onOk: () => paraEdits.set(paragraphId, newText) });
    } catch (e) {
      setStatus("fail", "문단 저장 실패: " + (e.message || e));
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
        return;
      }
      const paragraphId = command.target.paragraphId;
      if (opts.onOk) opts.onOk();
      setStatus("ok", "문단 저장 완료(새 sandbox 사본) · 재로딩 …");
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
  }

  // 클릭 좌표 → 그 지점의 DOM 텍스트 노드/로컬 오프셋. 브라우저 자체
  // 캐럿 히트테스트를 재사용(문자 폭 직접 계산 불필요 — 실제 렌더된
  // 글꼴/자간 그대로 정확).
  function caretNodeOffsetFromPoint(x, y) {
    if (document.caretRangeFromPoint) {
      const r = document.caretRangeFromPoint(x, y);
      return r ? { node: r.startContainer, offset: r.startOffset } : null;
    }
    if (document.caretPositionFromPoint) {
      const p = document.caretPositionFromPoint(x, y);
      return p ? { node: p.offsetNode, offset: p.offset } : null;
    }
    return null;
  }

  // container(줄 div) 안에서 node/nodeOffset 이 몇 번째 글자인지 —
  // 그 줄의 data-para-offset(문단 전체 기준 이 줄의 시작 글자 수, 서버가
  // lineseg textpos 로 계산해 내려줌) 에 더하면 문단 전체 기준 캐럿
  // 오프셋이 된다.
  function textOffsetWithin(container, node, nodeOffset) {
    const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
    let total = 0, n;
    while ((n = walker.nextNode())) {
      if (n === node) return total + nodeOffset;
      total += n.textContent.length;
    }
    return total;
  }

  // 문단 전체를 통째로 바꾸는 폴백 편집기(원본 실렌더 배경 모드처럼
  // 캐럿 위치를 계산할 텍스트가 화면에 없을 때만 사용).
  function openWholeParagraphEditor(ln, pid) {
    const cur = paraEdits.has(pid) ? paraEdits.get(pid)
      : ((loaded.documentModel.paragraphs || [])
          .find((p) => p.paragraphId === pid) || {}).text || "";
    const ta = document.createElement("textarea");
    ta.className = "wo-fld";
    ta.value = cur;
    ta.style.cssText = "position:absolute;left:0;top:0;width:100%;"
      + "min-height:100%;resize:vertical;font:inherit;";
    let done = false;
    const commit = () => {
      if (done) return;
      done = true;
      const v = ta.value;
      ta.remove();
      if (v !== cur) saveParagraphText(pid, v);
      else render();
    };
    ta.addEventListener("keydown", (e) => {
      if (e.key === "Escape") { done = true; ta.remove(); render(); }
      else if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault(); commit();
      }
    });
    ta.addEventListener("blur", commit);
    ln.appendChild(ta);
    ta.focus();
    ta.select();
  }

  // 캐럿 위치 삽입 편집기 — 클릭한 그 지점에만 작은 입력창을 띄운다
  // (문단 전체를 채우지 않음). 커밋하면 그 지점에 타이핑한 글자만
  // TYPE_TEXT 로 삽입한다.
  function openCaretInsertEditor(ln, pid, caretOffset, clientX) {
    const inp = document.createElement("input");
    inp.className = "wo-caret-input";
    inp.value = "";
    const lnRect = ln.getBoundingClientRect();
    const left = Math.max(0, clientX - lnRect.left);
    inp.style.cssText = `position:absolute; left:${left}px; top:0; `
      + "min-width:14px; height:100%; border:2px solid #2d6cdf; "
      + "background:#fff; font:inherit; padding:0 1px; z-index:6; "
      + "box-sizing:border-box;";
    inp.size = 1;
    let done = false;
    const commit = () => {
      if (done) return;
      done = true;
      const v = inp.value;
      inp.remove();
      if (v) insertAtCaret(pid, caretOffset, v);
      else render();
    };
    inp.addEventListener("input", () => {
      inp.size = Math.max(1, inp.value.length);
    });
    inp.addEventListener("keydown", (e) => {
      if (e.key === "Escape") { done = true; inp.remove(); render(); }
      else if (e.key === "Enter") { e.preventDefault(); commit(); }
    });
    inp.addEventListener("blur", commit);
    ln.appendChild(inp);
    inp.focus();
  }

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
      // 서버가 만든 새 sandbox 파일을 다음 편집의 기준으로 이어받는다.
      loaded.sourcePath = d.sourcePath;
      setStatus("ok", "서식 적용 완료(새 sandbox 사본) · 재로딩 …");
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
      // 본문 문단(표 밖 제목·전문 등) 클릭 편집 — 표 셀과 별개 경로.
      // 문장 중 클릭한 정확한 지점에 캐럿을 놓고 그 자리에만 타이핑한
      // 글자를 끼워 넣는다(대표님 지적: 전에는 어디를 클릭해도 문단
      // 전체가 "박스 단위"로 통째로 편집됐다 — 실제 워드프로세서처럼
      // 캐럿 단위 삽입이 되어야 함). 원본 실렌더 배경(사진) 모드는
      // 텍스트 자체가 화면에 안 그려져 있어 캐럿 위치를 계산할 수
      // 없으므로, 그 경우만 문단 전체 편집(기존 방식)으로 폴백한다.
      sheet.querySelectorAll(".co-line[data-paragraph-id]").forEach((ln) => {
        ln.addEventListener("click", (e) => {
          if (ln.querySelector("textarea, .wo-caret-input")) return;
          const pid = ln.dataset.paragraphId;
          if (!ln.querySelector(".co-in")) {
            openWholeParagraphEditor(ln, pid);
            return;
          }
          const hit = caretNodeOffsetFromPoint(e.clientX, e.clientY);
          if (!hit || !ln.contains(hit.node)) {
            openWholeParagraphEditor(ln, pid);
            return;
          }
          const localOffset = textOffsetWithin(ln, hit.node, hit.offset);
          const baseOffset = parseInt(ln.dataset.paraOffset || "0", 10);
          openCaretInsertEditor(ln, pid, baseOffset + localOffset, e.clientX);
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
