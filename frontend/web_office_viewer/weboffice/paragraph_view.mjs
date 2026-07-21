/* paragraph_view — 문단/run → HTML 문자열.
 *
 * 순수 렌더. style_resolver 로 charPr/paraPr 를 CSS 로 변환해 원본 서식
 * 유지. 편집/DOM 무접촉.
 */
import { charPrToCss, paraPrToCss } from "./style_resolver.mjs";

export function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

/* runs → 서식 적용된 span 문자열 */
export function renderRuns(runs, charPrDefs) {
  if (!runs || !runs.length) return "";
  return runs.map((r) =>
    `<span style="${charPrToCss(charPrDefs[r.charPrIDRef])}">`
    + `${escapeHtml(r.text)}</span>`).join("");
}

/* 본문 문단 → div (paraPr 적용) */
export function renderBodyParagraph(paragraph, styles) {
  const charPrDefs = styles.charPrDefs || {};
  const paraPrDefs = styles.paraPrDefs || {};
  const inner = renderRuns(paragraph.runs, charPrDefs)
    || escapeHtml(paragraph.text || "");
  const css = paraPrToCss(paraPrDefs[paragraph.parPrIDRef]);
  return `<div class="wo-body-para" style="${css}">`
    + `${inner || "&nbsp;"}</div>`;
}

/* 셀 안의 문단들 → div 목록. textOverride 가 주어지면(편집된 셀) 그
 * 텍스트를 첫 문단 서식으로 단일 렌더한다. */
export function renderCellParagraphs(cell, styles, textOverride) {
  const charPrDefs = styles.charPrDefs || {};
  const paraPrDefs = styles.paraPrDefs || {};
  const firstPar = cell.paragraphs && cell.paragraphs[0];
  const firstParPr = firstPar ? firstPar.parPrIDRef : null;
  const firstCharPr = firstPar && firstPar.runs && firstPar.runs[0]
    ? firstPar.runs[0].charPrIDRef : null;

  if (textOverride != null) {
    const css = paraPrToCss(paraPrDefs[firstParPr])
      + charPrToCss(charPrDefs[firstCharPr]);
    return `<div class="wo-cp" style="${css}">`
      + `${escapeHtml(textOverride)}</div>`;
  }
  const paras = cell.paragraphs || [];
  if (!paras.length) {
    return `<div class="wo-cp" style="${paraPrToCss(paraPrDefs[firstParPr])}">`
      + `${escapeHtml(cell.text || "")}</div>`;
  }
  return paras.map((p) => {
    const inner = renderRuns(p.runs, charPrDefs);
    return `<div class="wo-cp" style="${paraPrToCss(paraPrDefs[p.parPrIDRef])}">`
      + `${inner || "&nbsp;"}</div>`;
  }).join("");
}
