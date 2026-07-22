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
  return normSym(s).replace(/&/g, "&amp;")
    .replace(/</g, "&lt;").replace(/>/g, "&gt;");
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
  const parts = [];
  for (let pi = 0; pi < pages; pi++) {
    const yTop = pi * H;
    parts.push(`<div class="co-page" style="width:${W}px;height:${H}px">`);
    for (const b of layout.boxes || []) {
      if (Math.floor(b.y / H) !== pi) continue;
      let bd;
      if (b.border) {
        const g = "0.6px solid #e2e6ea";  // 없는 변은 옅은 안내선
        bd = `border-left:${b.border.l === "none" ? g : b.border.l};`
          + `border-right:${b.border.r === "none" ? g : b.border.r};`
          + `border-top:${b.border.t === "none" ? g : b.border.t};`
          + `border-bottom:${b.border.b === "none" ? g : b.border.b};`;
      } else {
        bd = "border:0.6px solid #e2e6ea;";
      }
      const fill = b.fill ? `background:${b.fill};` : "";
      const editAttr = (opts.editable && b.cellId)
        ? ` data-cell-id="${esc(b.cellId)}"` : "";
      parts.push(`<div class="co-box"${editAttr} style="left:${b.x}px;`
        + `top:${(b.y - yTop).toFixed(1)}px;width:${b.w}px;`
        + `height:${b.h}px;${bd}${fill}"></div>`);
    }
    for (const l of layout.lines || []) {
      if (Math.floor(l.y / H) !== pi) continue;
      if (l.cellId && editedIds.has(l.cellId)) continue;  // 편집셀 원본 숨김
      const fs = Math.max(7, l.h * 0.72);
      // line-height 는 반드시 박스 높이와 같게 둔다. 더 크게 주면
      // overflow:hidden 이 글자 위/아래(받침 포함)를 세로로 잘라 문자가
      // 깨진다. 한컴 baseline 정밀 정렬은 클리핑 없는 방식으로 후속 처리.
      const al = l.align ? `text-align:${l.align};` : "";
      parts.push(`<div class="co-line" style="left:${l.x}px;`
        + `top:${(l.y - yTop).toFixed(1)}px;width:${l.w}px;`
        + `height:${l.h}px;line-height:${l.h}px;${al}">`
        + `${segmentsHtml(l, defs, fs)}</div>`);
    }
    // 편집된 셀 → 새 텍스트를 박스 안(좌상단)에 렌더
    for (const cid of editedIds) {
      const b = boxByCell.get(cid);
      if (!b || Math.floor(b.y / H) !== pi) continue;
      const t = getCellText(cid);
      parts.push(`<div class="co-line co-edited" style="left:${b.x + 3}px;`
        + `top:${(b.y - yTop + 2).toFixed(1)}px;width:${Math.max(10, b.w - 6)}px;`
        + `height:${Math.max(12, b.h - 4)}px;line-height:1.3;`
        + `white-space:pre-wrap;font-size:10pt">`
        + `<span class="co-in" style="display:inline-block">${esc(t)}`
        + `</span></div>`);
    }
    parts.push("</div>");
  }
  return parts.join("");
}
