/* coordinate_renderer — HWPX lineseg 좌표 레이아웃 → 절대배치 HTML.
 *
 * 한컴이 저장한 줄별 좌표(vertpos/horzpos/size)를 그대로 절대배치해 원본
 * 배치(줄바꿈·행높이)를 재현한다. 브라우저 재-flow 없음. read-only.
 *
 * layout = { pageWidthPx, pageHeightPx, pages, lines[], boxes[] }
 *   line = { text, x, y(global), w, h, cell }
 *   box  = { x, y(global), w, h }   (표 셀 테두리)
 */
function esc(s) {
  return String(s ?? "").replace(/&/g, "&amp;")
    .replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

export function renderCoordinateLayout(layout) {
  if (!layout) return '<p class="co-empty">레이아웃 없음.</p>';
  const W = layout.pageWidthPx, H = layout.pageHeightPx;
  const pages = layout.pages || 1;
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
      parts.push(`<div class="co-box" style="left:${b.x}px;`
        + `top:${(b.y - yTop).toFixed(1)}px;width:${b.w}px;`
        + `height:${b.h}px;${bd}"></div>`);
    }
    for (const l of layout.lines || []) {
      if (Math.floor(l.y / H) !== pi) continue;
      const fs = Math.max(7, l.h * 0.72);
      parts.push(`<div class="co-line" style="left:${l.x}px;`
        + `top:${(l.y - yTop).toFixed(1)}px;width:${l.w}px;`
        + `height:${l.h}px;line-height:${l.h}px;`
        + `font-size:${fs.toFixed(1)}px">${esc(l.text)}</div>`);
    }
    parts.push("</div>");
  }
  return parts.join("");
}
