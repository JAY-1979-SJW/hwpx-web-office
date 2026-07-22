/* table_view — 표(RenderTable) → HTML 문자열.
 *
 * 테두리(borderFill 4변)·병합셀(rowspan/colspan)·셀 여백·표 실측폭 +
 * 셀 내 문단 서식을 반영한다. 편집 가능 셀에는 data-cell-id 를 부여하되,
 * 편집 로직 자체는 편집기 계층(cell_edit_controller)이 담당한다.
 */
import { huToPx, borderFillToCss, cellMarginToCss } from "./style_resolver.mjs";
import { renderCellParagraphs, escapeHtml } from "./paragraph_view.mjs";

/* opts:
 *   guides       : 박스 안내선 표시 (기본 true)
 *   getCellText  : (cellId) => string|null  편집된 셀 텍스트 override
 *   editableCell : (cell) => bool           data-cell-id 부여 여부
 */
const _VALIGN = { TOP: "top", CENTER: "middle", BOTTOM: "bottom" };

// 셀 실측 크기(cellSz)로 열별 폭 배열 도출. colSpan==1 셀 기준, 최대폭 채택.
function _columnWidths(table, cols) {
  const colW = new Array(cols).fill(0);
  for (const c of table.cells) {
    if (c.isCoveredByMerge || (c.colSpan || 1) !== 1) continue;
    const w = c.cellSize && parseFloat(c.cellSize.width);
    if (w > 0 && c.col < cols && w > colW[c.col]) colW[c.col] = w;
  }
  return colW;
}
// 행별 높이(rowSpan==1 셀의 cellSz.height 최대치, HWPUNIT).
function _rowHeights(byRow) {
  const h = {};
  for (const [r, cells] of byRow) {
    let mx = 0;
    for (const c of cells) {
      if ((c.rowSpan || 1) !== 1) continue;
      const v = c.cellSize && parseFloat(c.cellSize.height);
      if (v > mx) mx = v;
    }
    h[r] = mx;
  }
  return h;
}

export function renderTable(table, styles, opts = {}) {
  const guides = opts.guides !== false;
  const getCellText = opts.getCellText || (() => null);
  const editableCell = opts.editableCell || (() => true);

  const widthPx = huToPx(table.tableSize && table.tableSize.width);
  const widthCss = widthPx ? `width:${Math.round(widthPx)}px;` : "width:100%;";
  const cols = table.visualColCount || table.colCount || 1;

  const byRow = new Map();
  for (const c of table.cells) {
    if (c.isCoveredByMerge) continue;
    if (!byRow.has(c.row)) byRow.set(c.row, []);
    byRow.get(c.row).push(c);
  }
  const rows = [...byRow.keys()].sort((a, b) => a - b);

  // 실측 열폭 → colgroup 비율(%). 미지 열은 평균으로 채우고 합계 100%로
  // 정규화(오버플로 방지). 데이터 전무 시 균등.
  const colW = _columnWidths(table, cols);
  const known = colW.filter((w) => w > 0);
  const avg = known.length
    ? known.reduce((a, b) => a + b, 0) / known.length : 1;
  for (let i = 0; i < cols; i++) if (colW[i] <= 0) colW[i] = avg;
  const totalW = colW.reduce((a, b) => a + b, 0);
  const rowH = _rowHeights(byRow);

  let html = `<table class="wo-table${guides ? " wo-guides" : ""}"`
    + ` data-table-id="${escapeHtml(table.tableId)}"`
    + ` style="${widthCss}max-width:100%">`;
  html += "<colgroup>";
  for (let i = 0; i < cols; i++) {
    const w = totalW > 0
      ? ((colW[i] / totalW) * 100).toFixed(3)
      : (100 / cols).toFixed(3);
    html += `<col style="width:${w}%">`;
  }
  html += "</colgroup><tbody>";
  for (const r of rows) {
    const hPx = huToPx(rowH[r]);
    const trStyle = hPx > 0 ? ` style="height:${Math.round(hPx)}px"` : "";
    html += `<tr${trStyle}>`;
    for (const c of byRow.get(r).slice().sort((a, b) => a.col - b.col)) {
      const rs = c.rowSpan > 1 ? ` rowspan="${c.rowSpan}"` : "";
      const cs = c.colSpan > 1 ? ` colspan="${c.colSpan}"` : "";
      const idAttr = editableCell(c)
        ? ` data-cell-id="${escapeHtml(c.cellId)}"` : "";
      const va = _VALIGN[c.vertAlign] || "middle";
      const style = borderFillToCss(c.borderFill, { guides })
        + cellMarginToCss(c.cellMargin)
        + `vertical-align:${va};`;
      const nestedT = opts.nestedTables && opts.nestedTables.get(c.cellId);
      const content = nestedT
        ? renderTable(nestedT, styles, opts)                   // 중첩표를 셀 안에 렌더
        : renderCellParagraphs(c, styles, getCellText(c.cellId));
      html += `<td${idAttr}${rs}${cs} style="${style}">${content}</td>`;
    }
    html += "</tr>";
  }
  return html + "</tbody></table>";
}
