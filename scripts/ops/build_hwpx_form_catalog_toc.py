"""HWPX 서식 카탈로그(data/drafts/form_library/catalog.sqlite) 목차 생성.

읽기 전용 - 원본 카탈로그(38,165건, §4.4 읽기 전용 구역)는 절대 안 건드리고
목차만 새로 뽑는다. 산출: data/reports/hwpx_form_catalog_toc/
  - toc_summary.md          : 발행기관·문서유형·서식종류별 건수 요약(사람이 읽는 것)
  - hwpx_form_catalog_toc.xlsx : 요약 시트 + 전체 38,165건 상세 시트
  - catalog_toc_viewer.html : 발행기관/문서유형/서식종류 사이드 메뉴로
    거르는 자체완결형(서버 불필요, JSON 인라인) 뷰어

사용: python scripts/ops/build_hwpx_form_catalog_toc.py
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import openpyxl
from openpyxl.styles import Font

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "drafts" / "form_library" / "catalog.sqlite"
OUT_DIR = ROOT / "data" / "reports" / "hwpx_form_catalog_toc"


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _fetch_rows(c: sqlite3.Connection) -> list[sqlite3.Row]:
    return c.execute(
        """SELECT f.form_id, f.name, f.institution, f.legal_basis, f.source_path,
                  d.clean_name, d.doc_type, d.form_kind, d.fillable, d.input_count
           FROM forms f LEFT JOIN derivations_rebuild d ON f.form_id = d.form_id
           ORDER BY f.institution, d.doc_type, f.form_id"""
    ).fetchall()


def _group_counts(rows: list[sqlite3.Row], key: str) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for r in rows:
        k = (r[key] or "(미분류)").strip() or "(미분류)"
        counts[k] = counts.get(k, 0) + 1
    return sorted(counts.items(), key=lambda x: -x[1])


def build() -> dict:
    if not DB_PATH.exists():
        raise SystemExit(f"카탈로그 DB 없음: {DB_PATH}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    with _conn() as c:
        rows = _fetch_rows(c)

    by_inst = _group_counts(rows, "institution")
    by_doc = _group_counts(rows, "doc_type")
    by_kind = _group_counts(rows, "form_kind")
    fillable_n = sum(1 for r in rows if r["fillable"])

    # ── xlsx: 요약 시트 + 상세 시트 ──────────────────────────────────────
    wb = openpyxl.Workbook()
    ws_sum = wb.active
    ws_sum.title = "요약"
    ws_sum.append(["구분", "값"])
    ws_sum["A1"].font = ws_sum["B1"].font = Font(bold=True)
    ws_sum.append(["총 서식 건수", len(rows)])
    ws_sum.append(["입력칸 있는 서식(fillable)", fillable_n])
    ws_sum.append([])
    ws_sum.append(["발행기관", "건수"])
    for k, n in by_inst[:40]:
        ws_sum.append([k, n])
    r0 = ws_sum.max_row + 2
    ws_sum.cell(row=r0, column=1, value="문서유형(doc_type)")
    ws_sum.cell(row=r0, column=2, value="건수")
    for i, (k, n) in enumerate(by_doc, start=1):
        ws_sum.cell(row=r0 + i, column=1, value=k)
        ws_sum.cell(row=r0 + i, column=2, value=n)
    r1 = ws_sum.max_row + 2
    ws_sum.cell(row=r1, column=1, value="서식종류(form_kind)")
    ws_sum.cell(row=r1, column=2, value="건수")
    for i, (k, n) in enumerate(by_kind, start=1):
        ws_sum.cell(row=r1 + i, column=1, value=k)
        ws_sum.cell(row=r1 + i, column=2, value=n)
    ws_sum.column_dimensions["A"].width = 40
    ws_sum.column_dimensions["B"].width = 12

    ws_detail = wb.create_sheet("전체 목차")
    header = ["form_id", "서식명", "발행기관", "문서유형", "서식종류", "입력가능", "입력칸수", "법적근거"]
    ws_detail.append(header)
    for cell in ws_detail[1]:
        cell.font = Font(bold=True)
    for r in rows:
        ws_detail.append([
            r["form_id"], r["clean_name"] or r["name"], r["institution"] or "",
            r["doc_type"] or "", r["form_kind"] or "",
            "Y" if r["fillable"] else "N", r["input_count"] or 0,
            (r["legal_basis"] or "")[:200],
        ])
    widths = {"A": 10, "B": 52, "C": 16, "D": 12, "E": 12, "F": 10, "G": 10, "H": 40}
    for col, w in widths.items():
        ws_detail.column_dimensions[col].width = w
    ws_detail.freeze_panes = "A2"

    xlsx_path = OUT_DIR / "hwpx_form_catalog_toc.xlsx"
    wb.save(xlsx_path)

    # ── 요약 md(사람이 채팅창 밖에서 훑어볼 것) ─────────────────────────
    md_lines = [
        "# HWPX 서식 카탈로그 목차 요약",
        "",
        f"- 총 서식: {len(rows)}건 (입력칸 있는 서식 {fillable_n}건)",
        "",
        "## 발행기관 상위 15",
    ]
    for k, n in by_inst[:15]:
        md_lines.append(f"- {k}: {n}건")
    md_lines.append("")
    md_lines.append("## 문서유형(doc_type)")
    for k, n in by_doc:
        md_lines.append(f"- {k}: {n}건")
    md_lines.append("")
    md_lines.append("## 서식종류(form_kind)")
    for k, n in by_kind:
        md_lines.append(f"- {k}: {n}건")
    (OUT_DIR / "toc_summary.md").write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    # ── 사이드 메뉴 뷰어(html, JSON 인라인 - 서버 없이 바로 열림) ─────────
    items = [
        {
            "id": r["form_id"], "name": r["clean_name"] or r["name"],
            "inst": (r["institution"] or "(미분류)").strip() or "(미분류)",
            "doc": (r["doc_type"] or "(미분류)").strip() or "(미분류)",
            "kind": (r["form_kind"] or "(미분류)").strip() or "(미분류)",
            "fillable": bool(r["fillable"]), "inputCount": r["input_count"] or 0,
            "sourcePath": r["source_path"] or "",
        }
        for r in rows
    ]
    viewer_html = _render_viewer_html(items, by_inst, by_doc, by_kind, len(rows), fillable_n)
    viewer_path = OUT_DIR / "catalog_toc_viewer.html"
    viewer_path.write_text(viewer_html, encoding="utf-8")

    return {"total": len(rows), "fillable": fillable_n, "xlsx": str(xlsx_path),
            "viewer": str(viewer_path), "by_inst_top5": by_inst[:5], "by_doc": by_doc}


def _render_viewer_html(items, by_inst, by_doc, by_kind, total, fillable_n) -> str:
    data_json = json.dumps(items, ensure_ascii=False)
    groups_json = json.dumps({"발행기관": by_inst, "문서유형": by_doc, "서식종류": by_kind}, ensure_ascii=False)
    return """<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8">
<title>HWPX 서식 카탈로그 목차</title>
<style>
  * { box-sizing: border-box; }
  body { margin: 0; font-family: -apple-system, 'Segoe UI', Roboto, sans-serif; display: flex; height: 100vh; }
  #sidebar { width: 280px; flex: none; background: #1f2937; color: #e5e7eb; overflow-y: auto; padding: 16px 0; }
  #sidebar h2 { font-size: 0.8em; text-transform: uppercase; letter-spacing: .05em; color: #9ca3af;
                padding: 12px 16px 4px; margin: 0; }
  #sidebar .item { padding: 6px 16px; cursor: pointer; font-size: 0.92em; display: flex; justify-content: space-between; }
  #sidebar .item:hover { background: #374151; }
  #sidebar .item.active { background: #2563eb; color: #fff; }
  #sidebar .cnt { color: #9ca3af; }
  #sidebar .item.active .cnt { color: #dbeafe; }
  #main { flex: 1; overflow-y: auto; padding: 20px 28px; }
  #stats { color: #555; margin-bottom: 12px; }
  #toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 12px; flex-wrap: wrap; }
  input#q { flex: 1; min-width: 200px; max-width: 420px; padding: 8px 10px; border: 1px solid #ccc; border-radius: 6px; }
  input#base { width: 220px; padding: 8px 10px; border: 1px solid #ccc; border-radius: 6px; color: #555; font-size: 0.85em; }
  table { border-collapse: collapse; width: 100%; font-size: 0.9em; }
  th, td { text-align: left; padding: 6px 10px; border-bottom: 1px solid #eee; }
  th { position: sticky; top: 0; background: #fff; border-bottom: 2px solid #333; }
  tbody tr { cursor: pointer; }
  tbody tr:hover { background: #eff6ff; }
  .fill-y { color: #15803d; font-weight: 600; }
  .fill-n { color: #999; }
</style></head>
<body>
<div id="sidebar"></div>
<div id="main">
  <h1 style="margin-top:0">HWPX 서식 카탈로그 목차</h1>
  <div id="stats"></div>
  <div id="toolbar">
    <input id="q" placeholder="서식명 검색...">
    <input id="base" value="http://localhost:8000" title="원본 뷰어(coord_view.html) 서버 주소 - editor_api_route 기동 주소">
    <span style="font-size:0.8em;color:#999">↑ 행 클릭 시 이 주소의 /web-office/coord_view.html 로 원본을 연다</span>
  </div>
  <table><thead><tr><th>form_id</th><th>서식명</th><th>발행기관</th><th>문서유형</th><th>서식종류</th>
  <th>입력가능</th><th>입력칸수</th></tr></thead><tbody id="rows"></tbody></table>
</div>
<script>
const ITEMS = __DATA_JSON__;
const GROUPS = __GROUPS_JSON__;
const TOTAL = __TOTAL__, FILLABLE = __FILLABLE__;
let active = null; // {axis, key}

function render() {
  const sb = document.getElementById('sidebar');
  sb.innerHTML = '';
  for (const axis of Object.keys(GROUPS)) {
    const h = document.createElement('h2'); h.textContent = axis; sb.appendChild(h);
    for (const [key, n] of GROUPS[axis]) {
      const el = document.createElement('div');
      el.className = 'item' + (active && active.axis === axis && active.key === key ? ' active' : '');
      el.innerHTML = '<span>' + key + '</span><span class="cnt">' + n + '</span>';
      el.onclick = () => {
        active = (active && active.axis === axis && active.key === key) ? null : {axis, key};
        renderTable(); render();
      };
      sb.appendChild(el);
    }
  }
}

const AXIS_FIELD = {'발행기관': 'inst', '문서유형': 'doc', '서식종류': 'kind'};

function renderTable() {
  const q = document.getElementById('q').value.trim().toLowerCase();
  let rows = ITEMS;
  if (active) {
    const f = AXIS_FIELD[active.axis];
    rows = rows.filter(r => r[f] === active.key);
  }
  if (q) rows = rows.filter(r => r.name.toLowerCase().includes(q));
  document.getElementById('stats').textContent =
    (active ? active.axis + ' = ' + active.key + ' · ' : '') +
    rows.length + '건 표시 (전체 ' + TOTAL + '건, 입력가능 ' + FILLABLE + '건)';
  const tb = document.getElementById('rows');
  const frag = document.createDocumentFragment();
  for (const r of rows.slice(0, 2000)) {
    const tr = document.createElement('tr');
    tr.innerHTML = '<td>' + r.id + '</td><td>' + r.name + '</td><td>' + r.inst + '</td>' +
      '<td>' + r.doc + '</td><td>' + r.kind + '</td>' +
      '<td class="' + (r.fillable ? 'fill-y' : 'fill-n') + '">' + (r.fillable ? 'Y' : 'N') + '</td>' +
      '<td>' + r.inputCount + '</td>';
    if (r.sourcePath) {
      tr.title = '클릭하면 원본을 뷰어(coord_view.html)로 연다';
      tr.onclick = () => {
        let base = document.getElementById('base').value;
        while (base.endsWith('/')) base = base.slice(0, -1);
        window.open(base + '/web-office/coord_view.html?src=' + encodeURIComponent(r.sourcePath), '_blank');
      };
    }
    frag.appendChild(tr);
  }
  tb.innerHTML = '';
  tb.appendChild(frag);
  if (rows.length > 2000) {
    const tr = document.createElement('tr');
    tr.innerHTML = '<td colspan="7" style="color:#999;padding:10px">... 상위 2000건만 표시 (검색/분류로 좁혀 주세요)</td>';
    tb.appendChild(tr);
  }
}

document.getElementById('q').addEventListener('input', renderTable);
render();
renderTable();
</script>
</body></html>
""".replace("__DATA_JSON__", data_json).replace("__GROUPS_JSON__", groups_json) \
   .replace("__TOTAL__", str(total)).replace("__FILLABLE__", str(fillable_n))


if __name__ == "__main__":
    result = build()
    print(f"총 {result['total']}건 (입력가능 {result['fillable']}건)")
    print("발행기관 상위5:", result["by_inst_top5"])
    print("문서유형:", result["by_doc"])
    print("산출:", result["xlsx"])
    print("뷰어:", result["viewer"])
