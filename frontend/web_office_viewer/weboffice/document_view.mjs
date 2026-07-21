/* document_view — RenderPayload → 문서 HTML (읽기순서 조립).
 *
 * payload.blocks 를 문서 순서대로 순회하며 문단/표 블록을 렌더한다
 * (blocks 는 importer 가 문서 실제 순서로 배열 — WEB-OFFICE-RO-VIEW-
 * BLOCK-READING-ORDER-01). 순수 렌더: 편집 상태는 opts 콜백으로만 주입.
 */
import { renderBodyParagraph } from "./paragraph_view.mjs";
import { renderTable } from "./table_view.mjs";

/* opts:
 *   guides       : 박스 안내선 (기본 true)
 *   getCellText  : (cellId) => string|null  편집 override
 *   editableCell : (cell) => bool
 */
export function renderDocument(payload, opts = {}) {
  if (!payload) return '<p class="wo-empty">문서 없음.</p>';
  const styles = payload.styles || {};
  const tableById = new Map();
  for (const t of payload.tables || []) tableById.set(t.tableId, t);

  const parts = [];
  for (const b of payload.blocks || []) {
    if (b.type === "table" && b.ref && tableById.has(b.ref)) {
      parts.push(renderTable(tableById.get(b.ref), styles, opts));
    } else if (b.type === "paragraph" && b.paragraph) {
      parts.push(renderBodyParagraph(b.paragraph, styles));
    } else {
      parts.push(`<div class="wo-block-other" data-type="${b.type}"></div>`);
    }
  }
  return parts.join("") || '<p class="wo-empty">표시할 내용 없음.</p>';
}
