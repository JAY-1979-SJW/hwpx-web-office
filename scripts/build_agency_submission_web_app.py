from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


HTML_TEMPLATE = r"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>기관 제출서류 입력자료 관리</title>
  <style>
    :root {
      --bg: #f6f7f9;
      --panel: #ffffff;
      --line: #d8dde5;
      --text: #17202a;
      --muted: #657386;
      --accent: #1f6feb;
      --accent-weak: #e9f1ff;
      --ok: #147d4f;
      --warn: #a15c00;
      --danger: #b42318;
      --shadow: 0 1px 2px rgba(15, 23, 42, 0.08);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 14px/1.5 "Segoe UI", "Malgun Gothic", system-ui, sans-serif;
    }
    header {
      position: sticky;
      top: 0;
      z-index: 10;
      background: var(--panel);
      border-bottom: 1px solid var(--line);
      padding: 14px 18px;
    }
    .topbar {
      display: flex;
      align-items: center;
      gap: 14px;
      min-height: 38px;
    }
    h1 {
      margin: 0;
      font-size: 20px;
      font-weight: 700;
      white-space: nowrap;
    }
    .summary {
      display: flex;
      gap: 8px;
      margin-left: auto;
      flex-wrap: wrap;
      justify-content: flex-end;
    }
    .pill {
      border: 1px solid var(--line);
      background: #fff;
      border-radius: 999px;
      padding: 5px 10px;
      color: var(--muted);
      font-size: 12px;
    }
    .pill strong { color: var(--text); }
    .layout {
      display: grid;
      grid-template-columns: 360px minmax(0, 1fr);
      gap: 14px;
      padding: 14px;
      height: calc(100vh - 67px);
    }
    aside, main {
      min-height: 0;
      background: var(--panel);
      border: 1px solid var(--line);
      box-shadow: var(--shadow);
    }
    aside {
      display: grid;
      grid-template-rows: auto auto minmax(0, 1fr);
    }
    .filters {
      padding: 12px;
      border-bottom: 1px solid var(--line);
      display: grid;
      gap: 8px;
    }
    input, select, button, textarea {
      font: inherit;
    }
    input, select, textarea {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 8px 9px;
      background: #fff;
      color: var(--text);
    }
    .filter-row {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
    }
    .toolbar {
      display: flex;
      gap: 8px;
      padding: 10px 12px;
      border-bottom: 1px solid var(--line);
      align-items: center;
    }
    button {
      border: 1px solid var(--line);
      background: #fff;
      color: var(--text);
      border-radius: 6px;
      padding: 7px 10px;
      cursor: pointer;
    }
    button.primary {
      background: var(--accent);
      border-color: var(--accent);
      color: #fff;
    }
    button:hover { border-color: var(--accent); }
    .doc-list {
      overflow: auto;
    }
    .doc-item {
      width: 100%;
      text-align: left;
      border: 0;
      border-bottom: 1px solid var(--line);
      border-radius: 0;
      padding: 10px 12px;
      background: #fff;
      display: grid;
      gap: 5px;
    }
    .doc-item.active {
      background: var(--accent-weak);
      box-shadow: inset 3px 0 0 var(--accent);
    }
    .doc-title {
      font-weight: 650;
      line-height: 1.35;
    }
    .doc-meta {
      display: flex;
      flex-wrap: wrap;
      gap: 5px;
      color: var(--muted);
      font-size: 12px;
    }
    .doc-meta span {
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 1px 7px;
      background: #fff;
    }
    main {
      overflow: auto;
      padding: 18px;
    }
    .detail-head {
      display: grid;
      gap: 8px;
      border-bottom: 1px solid var(--line);
      padding-bottom: 14px;
      margin-bottom: 14px;
    }
    .detail-title {
      margin: 0;
      font-size: 22px;
      line-height: 1.35;
    }
    .meta-grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 8px;
    }
    .metric {
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 9px;
      background: #fbfcfe;
      min-height: 58px;
    }
    .metric label {
      display: block;
      color: var(--muted);
      font-size: 12px;
      margin-bottom: 3px;
    }
    .metric strong {
      font-size: 15px;
    }
    .tabs {
      display: flex;
      gap: 6px;
      border-bottom: 1px solid var(--line);
      margin-bottom: 14px;
    }
    .tab {
      border-radius: 6px 6px 0 0;
      border-bottom: 0;
      padding: 8px 12px;
    }
    .tab.active {
      background: var(--accent);
      border-color: var(--accent);
      color: #fff;
    }
    .panel { display: none; }
    .panel.active { display: block; }
    .section {
      margin-bottom: 18px;
    }
    .section h3 {
      margin: 0 0 8px;
      font-size: 16px;
    }
    .checklist {
      display: grid;
      gap: 6px;
    }
    .check-row {
      display: grid;
      grid-template-columns: 26px minmax(180px, 300px) minmax(0, 1fr);
      gap: 8px;
      align-items: start;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 8px;
      background: #fff;
    }
    .check-row input[type="checkbox"] {
      width: 18px;
      height: 18px;
      margin: 2px 0 0;
    }
    .check-row .label {
      font-weight: 600;
      word-break: keep-all;
      overflow-wrap: anywhere;
    }
    .check-row.done {
      background: #f1fbf6;
      border-color: #b7e4cd;
    }
    .value-input {
      min-height: 34px;
    }
    .progress {
      height: 10px;
      background: #e8edf3;
      border-radius: 999px;
      overflow: hidden;
    }
    .progress > div {
      height: 100%;
      width: 0%;
      background: var(--ok);
    }
    .body-text {
      white-space: pre-wrap;
      word-break: keep-all;
      overflow-wrap: anywhere;
      background: #fbfcfe;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 12px;
      max-height: 520px;
      overflow: auto;
    }
    .empty {
      color: var(--muted);
      padding: 40px;
      text-align: center;
    }
    .paths {
      display: grid;
      gap: 6px;
      color: var(--muted);
      font-size: 12px;
    }
    @media (max-width: 900px) {
      .layout {
        grid-template-columns: 1fr;
        height: auto;
      }
      aside { min-height: 420px; }
      .meta-grid { grid-template-columns: 1fr 1fr; }
      .check-row { grid-template-columns: 24px 1fr; }
      .check-row textarea { grid-column: 2; }
    }
  </style>
</head>
<body>
  <header>
    <div class="topbar">
      <h1>기관 제출서류 입력자료 관리</h1>
      <div class="summary" id="summary"></div>
    </div>
  </header>
  <div class="layout">
    <aside>
      <div class="filters">
        <input id="search" placeholder="문서명, 공종, 제출처, 입력항목, 첨부서류 검색" />
        <div class="filter-row">
          <select id="tradeFilter"></select>
          <select id="phaseFilter"></select>
        </div>
        <div class="filter-row">
          <select id="priorityFilter">
            <option value="">전체 우선순위</option>
            <option value="높음">높음</option>
            <option value="중간">중간</option>
            <option value="보통">보통</option>
          </select>
          <select id="statusFilter">
            <option value="">전체 상태</option>
            <option value="complete">입력 완료</option>
            <option value="incomplete">미완료</option>
          </select>
        </div>
      </div>
      <div class="toolbar">
        <button id="resetFilters">필터 초기화</button>
        <button id="importState">입력값 불러오기</button>
        <button id="exportState">입력값 내보내기</button>
        <button id="exportMissing">누락자료 생성</button>
        <input id="importFile" type="file" accept="application/json,.json" style="display:none" />
      </div>
      <div class="doc-list" id="docList"></div>
    </aside>
    <main id="detail"></main>
  </div>

  <script id="catalog-data" type="application/json">__CATALOG_JSON__</script>
  <script id="body-data" type="application/json">__BODY_JSON__</script>
  <script>
    const catalog = JSON.parse(document.getElementById('catalog-data').textContent);
    const bodyRows = JSON.parse(document.getElementById('body-data').textContent);
    const bodyByNo = new Map(bodyRows.map(row => [String(row.no), row]));
    const storageKey = 'agencySubmissionInputState.v1';
    const state = JSON.parse(localStorage.getItem(storageKey) || '{}');
    let selectedNo = String(catalog[0]?.문서번호 || '');
    let activeTab = 'input';

    const $ = id => document.getElementById(id);
    const norm = value => String(value || '').replace(/\s+/g, '').toLowerCase();
    const save = () => localStorage.setItem(storageKey, JSON.stringify(state));
    const keyFor = (no, type, idx) => `${no}:${type}:${idx}`;

    function getItems(row, key) {
      return Array.isArray(row[key]) ? row[key] : [];
    }

    function completion(row) {
      const no = String(row.문서번호);
      const fields = getItems(row, '입력해야_할_내용');
      const docs = getItems(row, '요구_또는_첨부서류');
      const total = fields.length + docs.length;
      if (!total) return 100;
      let done = 0;
      fields.forEach((_, i) => {
        const value = state[keyFor(no, 'fieldValue', i)] || '';
        if (String(value).trim()) done++;
      });
      docs.forEach((_, i) => {
        if (state[keyFor(no, 'attachment', i)]) done++;
      });
      return Math.round((done / total) * 100);
    }

    function setState(key, value) {
      if (value === false || value === '') delete state[key];
      else state[key] = value;
      save();
      renderSummary();
      renderList();
      renderDetail();
    }

    function unique(values) {
      return [...new Set(values.filter(Boolean))].sort((a, b) => a.localeCompare(b, 'ko'));
    }

    function initFilters() {
      const trades = unique(catalog.map(row => row.공종));
      const phases = unique(catalog.map(row => row.제출시점));
      $('tradeFilter').innerHTML = '<option value="">전체 공종</option>' + trades.map(v => `<option>${escapeHtml(v)}</option>`).join('');
      $('phaseFilter').innerHTML = '<option value="">전체 제출시점</option>' + phases.map(v => `<option>${escapeHtml(v)}</option>`).join('');
      ['search', 'tradeFilter', 'phaseFilter', 'priorityFilter', 'statusFilter'].forEach(id => {
        $(id).addEventListener('input', () => {
          const rows = filteredRows();
          if (rows.length && !rows.some(row => String(row.문서번호) === selectedNo)) selectedNo = String(rows[0].문서번호);
          renderAll();
        });
      });
      $('resetFilters').addEventListener('click', () => {
        ['search', 'tradeFilter', 'phaseFilter', 'priorityFilter', 'statusFilter'].forEach(id => $(id).value = '');
        renderAll();
      });
      $('exportState').addEventListener('click', () => {
        const payload = JSON.stringify({ exportedAt: new Date().toISOString(), values: state }, null, 2);
        const blob = new Blob([payload], { type: 'application/json;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = '기관제출서류_사용자입력값.json';
        a.click();
        URL.revokeObjectURL(url);
      });
      $('importState').addEventListener('click', () => $('importFile').click());
      $('importFile').addEventListener('change', event => {
        const file = event.target.files && event.target.files[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = () => {
          try {
            const payload = JSON.parse(String(reader.result || '{}'));
            const values = payload.values && typeof payload.values === 'object' ? payload.values : payload;
            Object.keys(state).forEach(key => delete state[key]);
            Object.assign(state, values);
            save();
            renderAll();
            alert('입력값을 불러왔습니다.');
          } catch (error) {
            alert('JSON 파일을 읽지 못했습니다: ' + error.message);
          }
        };
        reader.readAsText(file, 'utf-8');
        event.target.value = '';
      });
      $('exportMissing').addEventListener('click', () => {
        const report = buildMissingReport();
        const blob = new Blob([report], { type: 'text/markdown;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = '기관제출서류_누락자료요청서.md';
        a.click();
        URL.revokeObjectURL(url);
      });
    }

    function filteredRows() {
      const q = norm($('search').value);
      const trade = $('tradeFilter').value;
      const phase = $('phaseFilter').value;
      const priority = $('priorityFilter').value;
      const status = $('statusFilter').value;
      return catalog.filter(row => {
        if (trade && row.공종 !== trade) return false;
        if (phase && row.제출시점 !== phase) return false;
        if (priority && row.우선순위 !== priority) return false;
        const done = completion(row) === 100;
        if (status === 'complete' && !done) return false;
        if (status === 'incomplete' && done) return false;
        if (q) {
          const hay = norm([
            row.문서명, row.공종, row.제출처, row.제출시점,
            ...getItems(row, '입력해야_할_내용'),
            ...getItems(row, '요구_또는_첨부서류')
          ].join(' '));
          if (!hay.includes(q)) return false;
        }
        return true;
      });
    }

    function renderSummary() {
      const total = catalog.length;
      const complete = catalog.filter(row => completion(row) === 100).length;
      const avg = Math.round(catalog.reduce((sum, row) => sum + completion(row), 0) / Math.max(total, 1));
      const fields = catalog.reduce((sum, row) => sum + getItems(row, '입력해야_할_내용').length, 0);
      const docs = catalog.reduce((sum, row) => sum + getItems(row, '요구_또는_첨부서류').length, 0);
      $('summary').innerHTML = `
        <span class="pill">문서 <strong>${total}</strong></span>
        <span class="pill">완료 <strong>${complete}</strong></span>
        <span class="pill">평균 완료율 <strong>${avg}%</strong></span>
        <span class="pill">입력항목 <strong>${fields}</strong></span>
        <span class="pill">요구서류 <strong>${docs}</strong></span>
      `;
    }

    function renderList() {
      const rows = filteredRows();
      $('docList').innerHTML = rows.map(row => {
        const no = String(row.문서번호);
        const pct = completion(row);
        return `
          <button class="doc-item ${no === selectedNo ? 'active' : ''}" data-no="${escapeAttr(no)}">
            <div class="doc-title">${escapeHtml(row.문서번호)}. ${escapeHtml(row.문서명)}</div>
            <div class="doc-meta">
              <span>${escapeHtml(row.공종)}</span>
              <span>${escapeHtml(row.제출시점)}</span>
              <span>${escapeHtml(row.우선순위)}</span>
              <span>${pct}%</span>
            </div>
            <div class="progress"><div style="width:${pct}%"></div></div>
          </button>
        `;
      }).join('') || '<div class="empty">검색 결과가 없습니다.</div>';
      document.querySelectorAll('.doc-item').forEach(button => {
        button.addEventListener('click', () => {
          selectedNo = button.dataset.no;
          renderAll();
        });
      });
    }

    function renderDetail() {
      const row = catalog.find(item => String(item.문서번호) === selectedNo) || filteredRows()[0];
      if (!row) {
        $('detail').innerHTML = '<div class="empty">문서를 선택하세요.</div>';
        return;
      }
      selectedNo = String(row.문서번호);
      const pct = completion(row);
      const body = bodyByNo.get(selectedNo) || {};
      $('detail').innerHTML = `
        <div class="detail-head">
          <h2 class="detail-title">${escapeHtml(row.문서번호)}. ${escapeHtml(row.문서명)}</h2>
          <div class="meta-grid">
            <div class="metric"><label>공종</label><strong>${escapeHtml(row.공종)}</strong></div>
            <div class="metric"><label>제출처</label><strong>${escapeHtml(row.제출처)}</strong></div>
            <div class="metric"><label>제출시점</label><strong>${escapeHtml(row.제출시점)}</strong></div>
            <div class="metric"><label>완료율</label><strong>${pct}%</strong><div class="progress"><div style="width:${pct}%"></div></div></div>
          </div>
          <div class="paths">
            <div>원본 HWP: ${escapeHtml(row.원본파일)}</div>
            <div>본문 텍스트: ${escapeHtml(row.본문텍스트)}</div>
          </div>
        </div>
        <div class="tabs">
          ${tabButton('input', '입력값')}
          ${tabButton('docs', '요구서류')}
          ${tabButton('body', '본문')}
          ${tabButton('rules', '검증')}
        </div>
        <section class="panel ${activeTab === 'input' ? 'active' : ''}" id="panel-input">
          <div class="section">
            <h3>사용자가 제공해야 할 입력값</h3>
            <div class="checklist">${renderFieldRows(row)}</div>
          </div>
          <div class="section">
            <h3>자동입력 가능 공통값</h3>
            <div class="checklist">${renderSimpleList(getItems(row, '자동입력_가능_공통값'))}</div>
          </div>
        </section>
        <section class="panel ${activeTab === 'docs' ? 'active' : ''}" id="panel-docs">
          <div class="section">
            <h3>요구 또는 첨부서류</h3>
            <div class="checklist">${renderAttachmentRows(row)}</div>
          </div>
        </section>
        <section class="panel ${activeTab === 'body' ? 'active' : ''}" id="panel-body">
          <div class="section">
            <h3>본문에서 확인된 입력 라벨</h3>
            <div class="checklist">${renderSimpleList(getItems(row, '본문에서_확인된_입력라벨'))}</div>
          </div>
          <div class="section">
            <h3>본문에서 확인된 첨부 문구</h3>
            <div class="checklist">${renderSimpleList(getItems(row, '본문에서_확인된_첨부문구'))}</div>
          </div>
          <div class="section">
            <h3>본문 텍스트 미리보기</h3>
            <div class="body-text">${escapeHtml((body.text || '').slice(0, 12000))}</div>
          </div>
        </section>
        <section class="panel ${activeTab === 'rules' ? 'active' : ''}" id="panel-rules">
          <div class="section">
            <h3>입력 검증 기준</h3>
            <div class="checklist">${renderSimpleList(getItems(row, '입력검증기준'))}</div>
          </div>
        </section>
      `;
      document.querySelectorAll('.tab').forEach(btn => {
        btn.addEventListener('click', () => {
          activeTab = btn.dataset.tab;
          renderDetail();
        });
      });
      document.querySelectorAll('[data-field-index]').forEach(input => {
        input.addEventListener('input', event => {
          const key = keyFor(selectedNo, 'fieldValue', event.target.dataset.fieldIndex);
          setState(key, event.target.value);
        });
      });
      document.querySelectorAll('[data-attachment-index]').forEach(input => {
        input.addEventListener('change', event => {
          const key = keyFor(selectedNo, 'attachment', event.target.dataset.attachmentIndex);
          setState(key, event.target.checked);
        });
      });
    }

    function tabButton(id, label) {
      return `<button class="tab ${activeTab === id ? 'active' : ''}" data-tab="${id}">${label}</button>`;
    }

    function renderFieldRows(row) {
      const no = String(row.문서번호);
      return getItems(row, '입력해야_할_내용').map((field, i) => {
        const key = keyFor(no, 'fieldValue', i);
        const value = state[key] || '';
        return `
          <div class="check-row ${value ? 'done' : ''}">
            <input type="checkbox" disabled ${value ? 'checked' : ''} />
            <div class="label">${escapeHtml(field)}</div>
            <textarea class="value-input" rows="1" data-field-index="${i}" placeholder="자료 입력 또는 메모">${escapeHtml(value)}</textarea>
          </div>
        `;
      }).join('');
    }

    function renderAttachmentRows(row) {
      const no = String(row.문서번호);
      return getItems(row, '요구_또는_첨부서류').map((doc, i) => {
        const key = keyFor(no, 'attachment', i);
        const checked = !!state[key];
        return `
          <label class="check-row ${checked ? 'done' : ''}">
            <input type="checkbox" data-attachment-index="${i}" ${checked ? 'checked' : ''} />
            <div class="label">${escapeHtml(doc)}</div>
            <div></div>
          </label>
        `;
      }).join('');
    }

    function renderSimpleList(items) {
      return items.length
        ? items.map(item => `<div class="check-row"><div></div><div class="label">${escapeHtml(item)}</div><div></div></div>`).join('')
        : '<div class="empty">항목 없음</div>';
    }

    function renderAll() {
      renderSummary();
      renderList();
      renderDetail();
    }

    function buildMissingReport() {
      const lines = [
        '# 기관 제출서류 누락자료 요청서',
        '',
        `- 생성일: ${new Date().toLocaleString('ko-KR')}`,
        `- 대상 문서: ${catalog.length}개`,
        '',
      ];
      let docCount = 0;
      let missingFieldCount = 0;
      let missingAttachmentCount = 0;
      catalog.forEach(row => {
        const no = String(row.문서번호);
        const missingFields = getItems(row, '입력해야_할_내용').filter((_, i) => {
          return !String(state[keyFor(no, 'fieldValue', i)] || '').trim();
        });
        const missingAttachments = getItems(row, '요구_또는_첨부서류').filter((_, i) => {
          return !state[keyFor(no, 'attachment', i)];
        });
        if (!missingFields.length && !missingAttachments.length) return;
        docCount++;
        missingFieldCount += missingFields.length;
        missingAttachmentCount += missingAttachments.length;
        lines.push(`## ${row.문서번호}. ${row.문서명}`);
        lines.push('');
        lines.push(`- 공종: ${row.공종}`);
        lines.push(`- 제출처: ${row.제출처}`);
        lines.push(`- 제출시점: ${row.제출시점}`);
        lines.push(`- 완료율: ${completion(row)}%`);
        lines.push('');
        if (missingFields.length) {
          lines.push('### 미입력 항목');
          missingFields.forEach((item, idx) => lines.push(`${idx + 1}. ${item}`));
          lines.push('');
        }
        if (missingAttachments.length) {
          lines.push('### 미확인 첨부/필요서류');
          missingAttachments.forEach((item, idx) => lines.push(`${idx + 1}. ${item}`));
          lines.push('');
        }
      });
      lines.splice(4, 0, `- 누락 문서: ${docCount}개`, `- 미입력 항목: ${missingFieldCount}개`, `- 미확인 첨부/필요서류: ${missingAttachmentCount}개`, '');
      if (!docCount) {
        lines.push('모든 입력값과 첨부서류 체크가 완료되었습니다.');
      }
      return lines.join('\n');
    }

    function escapeHtml(value) {
      return String(value ?? '').replace(/[&<>"']/g, ch => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
      }[ch]));
    }
    function escapeAttr(value) { return escapeHtml(value); }

    initFilters();
    renderAll();
  </script>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package-dir", default="deliverables/기관제출서류_기관별확장_로컬패키지")
    args = parser.parse_args()
    package_dir = ROOT / args.package_dir
    catalog = json.loads(
        (package_dir / "06_전체요구사항정리" / "문서별_요구서류_입력사항_전체정리.json").read_text(
            encoding="utf-8"
        )
    )
    body = json.loads((package_dir / "04_본문추출" / "본문기반_입력항목.json").read_text(encoding="utf-8"))
    out_dir = package_dir / "07_웹앱"
    out_dir.mkdir(parents=True, exist_ok=True)
    html = HTML_TEMPLATE.replace(
        "__CATALOG_JSON__",
        json.dumps(catalog, ensure_ascii=False).replace("</", "<\\/"),
    ).replace(
        "__BODY_JSON__",
        json.dumps(body, ensure_ascii=False).replace("</", "<\\/"),
    )
    out_path = out_dir / "index.html"
    out_path.write_text(html, encoding="utf-8")
    print(f"output={out_path}")
    print(f"documents={len(catalog)}")
    print(f"body_rows={len(body)}")


if __name__ == "__main__":
    main()
