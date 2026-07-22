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
/* 표 셀 텍스트를 감싼 '컨테이너 문단'은 표 내용을 그대로 중복 출력한다.
 * (importer 가 표를 담은 non-editable 문단의 text 에 셀 텍스트를 평탄화해 넣음)
 * 표와 문자 대부분이 겹치는 비편집 문단은 렌더에서 제외해 중복을 없앤다. */
function _tableCharSet(payload) {
  const set = new Set();
  for (const t of payload.tables || []) {
    for (const c of t.cells || []) {
      for (const ch of (c.text || "").replace(/\s/g, "")) set.add(ch);
    }
  }
  return set;
}
function _isTableDuplicate(paragraph, tableChars) {
  if (!paragraph) return false;
  if (paragraph.editable !== false) return false;      // 편집 가능 본문은 보존
  const p = (paragraph.text || "").replace(/\s/g, "");
  if (p.length < 40) return false;                      // 짧은 문단 보존
  const uniq = new Set(p);
  if (uniq.size === 0) return false;
  let inTable = 0;
  for (const ch of uniq) if (tableChars.has(ch)) inTable++;
  return inTable / uniq.size >= 0.9;                    // 90%+ 문자가 표에 존재 → 중복
}

/* 중첩표 탐지 — 부모 셀 텍스트가 다른 표의 전체 내용과 정확히 일치하면
 * (importer 가 중첩표를 셀에 평탄화하면서 별도 표로도 추출한 경우),
 * 그 표를 부모 셀 안에서 렌더하고 최상위에서는 제외한다. → run-on 중복 제거. */
function _stripFlow(s) { return (s || "").replace(/[\s→⭢⇒]/g, ""); }
function _computeNested(payload) {
  const tables = payload.tables || [];
  const sigs = tables.map((t) => ({
    id: t.tableId,
    sig: _stripFlow((t.cells || []).map((c) => c.text || "").join("")),
  }));
  const byCellId = new Map();
  const nestedIds = new Set();
  for (const t of tables) {
    for (const c of t.cells || []) {
      if (c.isCoveredByMerge) continue;
      const ct = _stripFlow(c.text || "");
      if (ct.length < 12) continue;
      const hit = sigs.find((s) => s.id !== t.tableId
        && s.sig.length >= 12 && s.sig === ct && !nestedIds.has(s.id));
      if (hit) { byCellId.set(c.cellId, hit.id); nestedIds.add(hit.id); }
    }
  }
  return { byCellId, nestedIds };
}

export function renderDocument(payload, opts = {}) {
  if (!payload) return '<p class="wo-empty">문서 없음.</p>';
  const styles = payload.styles || {};
  const tableById = new Map();
  for (const t of payload.tables || []) tableById.set(t.tableId, t);
  const tableChars = _tableCharSet(payload);

  // 중첩표: 부모 셀 안에서 렌더 → renderTable 에 nestedTables 맵 전달, 최상위 제외
  const nested = _computeNested(payload);
  const nestedTables = new Map();
  for (const [cid, tid] of nested.byCellId) nestedTables.set(cid, tableById.get(tid));
  const opts2 = { ...opts, nestedTables };

  const parts = [];
  for (const b of payload.blocks || []) {
    if (b.type === "table" && b.ref && tableById.has(b.ref)) {
      if (nested.nestedIds.has(b.ref)) continue;                // 중첩표는 부모 셀에서 렌더
      parts.push(renderTable(tableById.get(b.ref), styles, opts2));
    } else if (b.type === "paragraph" && b.paragraph) {
      if (_isTableDuplicate(b.paragraph, tableChars)) continue;  // 중복 컨테이너 문단 제외
      parts.push(renderBodyParagraph(b.paragraph, styles));
    } else {
      parts.push(`<div class="wo-block-other" data-type="${b.type}"></div>`);
    }
  }
  return parts.join("") || '<p class="wo-empty">표시할 내용 없음.</p>';
}
