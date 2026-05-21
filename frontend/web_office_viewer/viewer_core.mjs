/* WEB-OFFICE-BROWSER-VIEWER-PROTOTYPE-01
 * read-only viewer core — pure function: payload → HTML string.
 * 편집 입력 요소(input/textarea/contenteditable)·save·apply 호출은
 * 본 파일에 일절 등장하지 않는다.
 */

function escapeHtml(s) {
  return String(s ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function renderParagraph(par) {
  const text = escapeHtml(par.text || "");
  return `<div class="wo-paragraph" data-paragraph-id="${par.paragraphId}"
              data-editable="false">${text}</div>`;
}

function renderTable(tbl) {
  const cellsByRow = new Map();
  for (const c of tbl.cells || []) {
    if (c.isCoveredByMerge) continue;
    if (!cellsByRow.has(c.row)) cellsByRow.set(c.row, []);
    cellsByRow.get(c.row).push(c);
  }
  const rows = [...cellsByRow.keys()].sort((a, b) => a - b);
  const rowsHtml = rows.map((r) => {
    const cells = cellsByRow.get(r).sort((a, b) => a.col - b.col);
    const cellsHtml = cells.map((c) => {
      const rs = c.rowSpan > 1 ? ` rowspan="${c.rowSpan}"` : "";
      const cs = c.colSpan > 1 ? ` colspan="${c.colSpan}"` : "";
      const mergedCls = c.isMergedOrigin ? " wo-cell-merged-origin" : "";
      return `<td class="wo-cell${mergedCls}"
                data-cell-id="${c.cellId}"
                data-navigation-id="${c.navigationId}"
                data-row="${c.row}" data-col="${c.col}"
                data-editable="false"${rs}${cs}>${escapeHtml(c.text || "")}</td>`;
    }).join("");
    return `<tr class="wo-row" data-row="${r}">${cellsHtml}</tr>`;
  }).join("");
  const mergedAttr = tbl.hasMergedCells ? ' data-has-merged="true"' : "";
  return `<table class="wo-table" data-table-id="${tbl.tableId}"
              data-row-count="${tbl.rowCount}"
              data-col-count="${tbl.colCount}"
              data-editable="false"${mergedAttr}>${rowsHtml}</table>`;
}

function renderBlock(block, payload) {
  if (block.type === "table") {
    const tbl = (payload.tables || []).find(
      (t) => t.tableId === block.ref);
    if (tbl) return renderTable(tbl);
    return `<div class="wo-block-missing">[table missing: ${block.ref}]</div>`;
  }
  if (block.type === "paragraph") {
    const par = block.paragraph;
    if (par) return renderParagraph(par);
  }
  return `<div class="wo-block-other" data-block-id="${block.blockId}"
              data-type="${block.type}" data-editable="false"></div>`;
}

export function renderPayloadToHTML(payload, opts = {}) {
  if (!payload || payload.editable !== false) {
    throw new Error("payload missing or editable!=false — RO-VIEW only");
  }
  const docTitle = opts.title || `Document ${payload.documentId}`;
  const blocksHtml = (payload.blocks || [])
    .map((b) => renderBlock(b, payload)).join("\n");
  const warningsHtml = (payload.warnings || []).length
    ? `<ul class="wo-warnings">${(payload.warnings || []).map(
        (w) => `<li>${escapeHtml(JSON.stringify(w))}</li>`).join("")}</ul>`
    : `<div class="wo-warnings-empty">warnings: 0</div>`;

  const counts = {
    blocks: (payload.blocks || []).length,
    tables: (payload.tables || []).length,
    objects: (payload.objects || []).length,
  };
  const tablesList = (payload.tables || [])
    .map((t) => `<li data-table-id="${t.tableId}">
                              ${t.tableId} (${t.rowCount}×${t.colCount})</li>`)
    .join("");

  return `<div class="web-office-viewer" data-editable="false"
                            data-schema="${payload.schemaVersion}"
                            data-engine="${payload.engineVersion}"
                            data-payload="${payload.payloadVersion}">
  <header class="wo-toolbar" data-editable="false">
    <div class="wo-toolbar-title">${escapeHtml(docTitle)}</div>
    <div class="wo-toolbar-mode" data-mode="read-only">읽기 전용</div>
    <div class="wo-toolbar-zoom" data-zoom="100">100%</div>
  </header>
  <div class="wo-body">
    <aside class="wo-left-panel" data-editable="false">
      <h3>표 목록</h3>
      <ul class="wo-table-list">${tablesList}</ul>
    </aside>
    <main class="wo-center" data-editable="false">
      ${blocksHtml}
    </main>
    <aside class="wo-right-panel" data-editable="false">
      <h3>payload summary</h3>
      <dl>
        <dt>documentId</dt><dd>${escapeHtml(payload.documentId)}</dd>
        <dt>sha256</dt><dd>${escapeHtml(payload.sourceRef?.sha256 || "")}</dd>
        <dt>blocks</dt><dd>${counts.blocks}</dd>
        <dt>tables</dt><dd>${counts.tables}</dd>
        <dt>objects</dt><dd>${counts.objects}</dd>
      </dl>
      <h3>warnings</h3>
      ${warningsHtml}
    </aside>
  </div>
</div>`;
}
