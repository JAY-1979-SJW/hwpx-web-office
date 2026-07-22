/* coordinate_renderer — HWPX lineseg 좌표 레이아웃 → 절대배치 HTML.
 *
 * 한컴이 저장한 줄별 좌표(vertpos/horzpos/size)를 그대로 절대배치해 원본
 * 배치(줄바꿈·행높이)를 재현하고, 각 줄을 run 별 charPr 조각으로 나눠
 * 원본 서식(폰트·크기·색·굵게·기울임·밑줄·자간)까지 입힌다. 문단 정렬
 * (가운데/오른쪽)도 반영. 브라우저 재-flow 없음. read-only.
 *
 * layout = { pageWidthPx, pageHeightPx, pages, lines[], boxes[], charPrDefs{} }
 *   line = { text, segments[{text,charPr}], x, y(global), w, h, align?, cell }
 *   box  = { x, y(global), w, h, border?, fill? }
 */
import { charPrToCss } from "./style_resolver.mjs";

// Wingdings 계열 PUA 화살표(한컴이 심볼폰트로 넣은 글자) → 유니코드 화살표.
// 대체 폰트에 해당 글리프가 없어 □(두부)로 깨지는 것을 방지, 원본 의도대로
// 화살표를 표시한다. (확인된 U+F0E8=오른쪽 화살표만 매핑; 필요 시 확장)
const SYM = { "": "→" };
function normSym(s) {
  return String(s ?? "").replace(/[-]/g, (c) => SYM[c] || c);
}

function esc(s) {
  // &<> 뿐 아니라 "'까지 이스케이프 — data-cell-id="…" 같은 속성 컨텍스트
  // 에서도 안전(따옴표 미이스케이프 시 속성 탈출 위험). 요소 내용에도 무해.
  return normSym(s).replace(/&/g, "&amp;")
    .replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

/* 한 줄의 서식 조각 → span 문자열. charPr 정의가 있으면 실서식(폰트/색/
 * 굵게…)을, 없으면 줄높이 기반 추정 크기를 적용한다. */
function segmentsHtml(line, defs, fallbackFs) {
  const segs = (line.segments && line.segments.length)
    ? line.segments
    : [{ text: line.text, charPr: null }];
  const inner = segs.map((sg) => {
    const def = sg.charPr != null ? defs[sg.charPr] : null;
    let css = def ? charPrToCss(def) : "";
    // charPr 에 크기가 없으면 줄높이 추정치로 보강 (텍스트 안 보이는 것 방지)
    if (!def || !def.fontSizePt) css += `font-size:${fallbackFs.toFixed(1)}px;`;
    return `<span style="${css}">${esc(sg.text)}</span>`;
  }).join("");
  // inline-block 래퍼 — autoFitLines 가 offsetWidth 로 실제 내용폭을 정확히
  // 측정(overflow:clip 과 무관)해 필요 시 가로 압축한다.
  return `<span class="co-in" style="display:inline-block">${inner}</span>`;
}

/* auto-fit — 렌더 후 호출. 각 줄의 실제 내용폭(scrollWidth)이 줄상자
 * 폭(clientWidth)을 넘으면(폰트 차/justify 미작동으로 자연폭이 넓을 때)
 * transform:scaleX 로 가로 압축해 줄상자 안에 맞춘다. 한컴의 justify
 * 압축을 브라우저 실측 기반으로 재현 — 글자가 잘리거나 셀을 넘지 않게 한다.
 * (브라우저 DOM 필요; 순수 렌더 결과에 후처리로 적용) */
export function autoFitLines(root) {
  if (!root || !root.querySelectorAll) return;
  root.querySelectorAll(".co-line").forEach((el) => {
    const inner = el.firstElementChild;   // .co-in (inline-block)
    if (!inner) return;
    inner.style.transform = "";           // 재측정 위해 초기화
    const cw = el.clientWidth;             // 줄상자 폭
    const sw = inner.offsetWidth;          // 실제 내용폭(clip 무관, 정확)
    if (cw > 0 && sw > cw + 1) {
      inner.style.transformOrigin = "left";
      inner.style.transform = `scaleX(${(cw / sw).toFixed(4)})`;
    }
  });
}

/* opts (모두 선택):
 *   editable         : true 면 셀 박스에 data-cell-id 부여(클릭 편집 대상)
 *   getCellText(id)  : 편집된 셀 텍스트(없으면 null). 편집된 셀은 원본 줄을
 *                      숨기고 이 텍스트를 박스 안에 렌더한다.
 *   truthBase        : '원본 그대로' 모드 — 페이지 배경을 한컴 실렌더
 *                      PNG(truthBase + 페이지번호)로 깔고, 우리 텍스트/
 *                      테두리는 그리지 않는다(이중 표시 방지). 셀 박스는
 *                      투명 클릭 타깃으로만 유지 → 화면은 정의상 원본과
 *                      동일하고 편집은 오버레이가 담당한다.
 */
export function renderCoordinateLayout(layout, opts = {}) {
  if (!layout) return '<p class="co-empty">레이아웃 없음.</p>';
  const W = layout.pageWidthPx, H = layout.pageHeightPx || 1;  // 0 나눗셈 가드
  const pages = layout.pages || 1;
  const defs = layout.charPrDefs || {};
  const getCellText = opts.getCellText || (() => null);
  const boxByCell = new Map();       // cellId → box (편집 텍스트 렌더 위치)
  const editedIds = new Set();       // 편집된 셀(원본 줄 숨김)
  for (const b of layout.boxes || []) {
    if (b.cellId && !boxByCell.has(b.cellId)) boxByCell.set(b.cellId, b);
  }
  for (const cid of boxByCell.keys()) {
    if (getCellText(cid) != null) editedIds.add(cid);
  }
  // 페이지별 구조(pagesDetail) 우선 — 추출기가 페이지-로컬 좌표로 복구한
  // 페이지 배열을 그대로 그린다(전역 y 슬라이싱 제거: 경계 번짐·갭 흡수류
  // 결함의 뿌리 소멸). 구버전 레이아웃(pagesDetail 없음)은 기존 슬라이싱.
  const pagesDetail = (layout.pagesDetail && layout.pagesDetail.length)
    ? layout.pagesDetail : null;
  const parts = [];
  for (let pi = 0; pi < pages; pi++) {
    const yTop = pi * H;
    const pd = pagesDetail ? pagesDetail[pi] : null;
    const pBoxes = pd ? pd.boxes
      : (layout.boxes || []).filter((b) => Math.floor(b.y / H) === pi);
    const pLines = pd ? pd.lines
      : (layout.lines || []).filter((l) => Math.floor(l.y / H) === pi);
    const localY = (y) => (pd ? y : y - yTop);
    // 페이지별 정합 판정(truthOk=false 페이지는 배경 대신 좌표 렌더 —
    // 페이지 경계가 한컴과 어긋난 페이지에서 엉뚱한 그림 위에 오버레이가
    // 얹히는 것 방지)
    const pageTruth = !!(opts.truthBase && (!pd || pd.truthOk !== false));
    const truth = pageTruth
      ? `background-image:url('${opts.truthBase}${pi + 1}');`
        + "background-size:100% 100%;"
      : "";
    parts.push(`<div class="co-page" style="width:${W}px;height:${H}px;`
      + `${truth}">`);
    for (const b of pBoxes) {
      // 한컴이 지정한 테두리만 그린다. none/미지정 변은 안 그림(한컴은
      // borderless 셀을 보이지 않게 렌더 — 안내선을 그리면 없던 박스가
      // 생겨 원본과 달라진다). 셀 편집 위치는 hover 하이라이트로 표시.
      let bd = "";
      if (b.border && !pageTruth) {
        if (b.border.l !== "none") bd += `border-left:${b.border.l};`;
        if (b.border.r !== "none") bd += `border-right:${b.border.r};`;
        // 병합 셀의 페이지 연속 조각(frag)은 위/아래 경계선을 페이지
        // 절단면에 맞게 처리 — 한컴처럼 이어지는 셀로 보이게 한다.
        if (b.border.t !== "none" && !b.frag) bd += `border-top:${b.border.t};`;
        if (b.border.b !== "none") bd += `border-bottom:${b.border.b};`;
      }
      const fill = (b.fill && !pageTruth) ? `background:${b.fill};` : "";
      const editAttr = ((opts.editable && b.cellId)
        ? ` data-cell-id="${esc(b.cellId)}"` : "")
        + (b.frag ? ' data-frag="1"' : "");
      parts.push(`<div class="co-box"${editAttr} style="left:${b.x}px;`
        + `top:${localY(b.y).toFixed(1)}px;width:${b.w}px;`
        + `height:${b.h}px;${bd}${fill}"></div>`);
    }
    for (const l of pLines) {
      if (pageTruth) break;           // 원본 배경 페이지 — 텍스트는 배경에 있음
      if (l.cellId && editedIds.has(l.cellId)) continue;  // 편집셀 원본 숨김
      const fs = Math.max(7, l.h * 0.72);
      // line-height 는 반드시 박스 높이와 같게 둔다. 더 크게 주면
      // overflow:hidden 이 글자 위/아래(받침 포함)를 세로로 잘라 문자가
      // 깨진다. 한컴 baseline 정밀 정렬은 클리핑 없는 방식으로 후속 처리.
      const al = l.align ? `text-align:${l.align};` : "";
      parts.push(`<div class="co-line" style="left:${l.x}px;`
        + `top:${localY(l.y).toFixed(1)}px;width:${l.w}px;`
        + `height:${l.h}px;line-height:${l.h}px;${al}">`
        + `${segmentsHtml(l, defs, fs)}</div>`);
    }
    // 편집된 셀 → 새 텍스트를 박스 안(좌상단)에 렌더 (첫 조각에만)
    for (const cid of editedIds) {
      const b = pd
        ? pd.boxes.find((x) => x.cellId === cid && !x.frag)
        : ((boxByCell.get(cid)
            && Math.floor(boxByCell.get(cid).y / H) === pi)
          ? boxByCell.get(cid) : null);
      if (!b) continue;
      const t = getCellText(cid);
      // 편집값은 박스 좌상단이 아니라 그 셀의 실제 텍스트 줄 위치에 —
      // rowSpan 큰 셀(결재란 왼쪽 열 등)에서 값이 위 줄에 떠 보이던 결함
      // 수리. 줄이 없는 빈 셀은 세로 중앙(한컴 기본 정렬과 유사).
      const ln0 = pd
        ? pd.lines.find((l) => l.cellId === cid)
        : null;
      const ty = ln0 ? localY(ln0.y)
        : (localY(b.y) + Math.max(2, (b.h - 16) / 2));
      const tx = ln0 ? ln0.x : (b.x + 3);
      parts.push(`<div class="co-line co-edited" style="left:${tx}px;`
        + `top:${ty.toFixed(1)}px;`
        + `width:${Math.max(10, b.x + b.w - tx - 3)}px;`
        + `height:${Math.max(12, (ln0 && ln0.h) ? ln0.h + 4 : 16)}px;`
        + `line-height:1.3;`
        + `white-space:pre-wrap;font-size:10pt">`
        + `<span class="co-in" style="display:inline-block">${esc(t)}`
        + `</span></div>`);
    }
    parts.push("</div>");
  }
  return parts.join("");
}
