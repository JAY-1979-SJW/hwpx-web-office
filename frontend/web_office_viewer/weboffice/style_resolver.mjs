/* style_resolver — HWPX 스타일 정의(charPr/paraPr/borderFill) → CSS 문자열.
 *
 * 순수 함수 모듈. DOM/편집/네트워크 무접촉. 원본 서식(폰트·크기·색·굵게·
 * 기울임·밑줄·취소선·자간·첨자 / 정렬·줄간격·들여쓰기 / 셀 테두리·여백)을
 * 최대한 유지한다. 픽셀 동일은 아님(HTML 근사) — 별도 좌표 렌더러 영역.
 */

/* ── 단위 ─────────────────────────────────────────────── */
// HWPUNIT = 1/7200 inch. 96dpi 기준 px = v/7200*96 = v*0.013333…
export const HWPUNIT_TO_PX = 96 / 7200;
export function huToPx(value) {
  const n = parseFloat(value);
  return Number.isFinite(n) ? n * HWPUNIT_TO_PX : 0;
}
export function mmToPx(text) {
  const m = /([\d.]+)\s*mm/.exec(text || "");
  return m ? parseFloat(m[1]) * 3.7795 : 0;
}

function _truthy(v) {
  return !(v === undefined || v === null || v === false
    || v === "0" || v === 0 || v === "NONE" || v === "");
}

/* ── 폰트 ─────────────────────────────────────────────── */
// 폰트명 계열 추정 → 적절한 fallback stack. 실 폰트 설치 환경(예: 한컴
// 설치 PC)에서는 지정한 fontName 그대로 렌더된다.
export function fontFamily(name) {
  if (!name) return "";
  const serif = /바탕|명조|Batang|Myeongjo|serif/i.test(name);
  const tail = serif
    ? "'함초롬바탕','바탕','Batang',serif"
    : "'맑은 고딕','함초롬돋움','돋움','Dotum',sans-serif";
  return `font-family:'${name}',${tail};`;
}

/* ── charPr → CSS ─────────────────────────────────────── */
export function charPrToCss(def) {
  if (!def) return "font-size:10pt;";
  let s = fontFamily(def.fontName);
  if (def.fontSizePt) s += `font-size:${def.fontSizePt}pt;`;
  if (def.textColor && def.textColor.toLowerCase() !== "#000000") {
    s += `color:${def.textColor};`;
  }
  if (def.bold) s += "font-weight:700;";
  if (def.italic) s += "font-style:italic;";
  const deco = [];
  if (def.underline) deco.push("underline");
  if (_truthy(def.strikeout)) deco.push("line-through");
  if (deco.length) s += `text-decoration:${deco.join(" ")};`;
  const sp = def.spacing && parseFloat(def.spacing.hangul || "0");
  if (sp) s += `letter-spacing:${(sp / 100).toFixed(3)}em;`;
  const off = def.offset && parseFloat(def.offset.hangul || "0");
  if (off > 0) s += "vertical-align:super;font-size:0.8em;";
  else if (off < 0) s += "vertical-align:sub;font-size:0.8em;";
  return s;
}

/* ── paraPr → CSS (정렬·줄간격·들여쓰기/여백) ──────────── */
export function paraPrToCss(def) {
  if (!def) return "text-align:left;";
  let s = "";
  const h = def.align && def.align.horizontal;
  const al = h === "RIGHT" ? "right"
    : h === "CENTER" ? "center"
    : (h === "JUSTIFY" || h === "DISTRIBUTE") ? "justify"
    : "left";
  s += `text-align:${al};`;
  const ls = def.lineSpacing;
  if (ls && ls.type === "PERCENT" && ls.value) {
    s += `line-height:${(parseFloat(ls.value) / 100).toFixed(2)};`;
  }
  const m = def.margin;
  if (m) {
    const L = huToPx(m.left && m.left.value);
    const R = huToPx(m.right && m.right.value);
    const IN = huToPx(m.intent && m.intent.value);
    if (L > 0) s += `padding-left:${Math.round(L)}px;`;
    if (R > 0) s += `padding-right:${Math.round(R)}px;`;
    if (IN) s += `text-indent:${Math.round(IN)}px;`;
  }
  return s;
}

/* ── borderFill → 셀 테두리 CSS ───────────────────────── */
function _sideCss(side, guides) {
  if (side && side.type && side.type !== "NONE") {
    const w = Math.max(0.8, mmToPx(side.width)).toFixed(2);
    return `${w}px solid ${side.color || "#333"}`;
  }
  return guides ? "1px solid #ccd3da" : "none";
}
export function borderFillToCss(borderFill, opts = {}) {
  const guides = opts.guides !== false;
  const s = (borderFill && borderFill.sides) || {};
  return `border-left:${_sideCss(s.leftBorder, guides)};`
    + `border-right:${_sideCss(s.rightBorder, guides)};`
    + `border-top:${_sideCss(s.topBorder, guides)};`
    + `border-bottom:${_sideCss(s.bottomBorder, guides)};`;
}

/* ── cellMargin → padding CSS ─────────────────────────── */
export function cellMarginToCss(cellMargin) {
  if (!cellMargin) return "padding:2px 5px;";
  const p = (v) => Math.max(2, Math.round(huToPx(v)));
  return `padding:${p(cellMargin.top)}px ${p(cellMargin.right)}px `
    + `${p(cellMargin.bottom)}px ${p(cellMargin.left)}px;`;
}
