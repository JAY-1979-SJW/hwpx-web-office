"""HWPX 서식 카탈로그(data/drafts/form_library/catalog.sqlite) 목차 생성.

읽기 전용 - 원본 카탈로그(38,165건, §4.4 읽기 전용 구역)는 절대 안 건드리고
목차만 새로 뽑는다. 산출: data/reports/hwpx_form_catalog_toc/
  - toc_summary.md          : 발행기관·문서유형·서식종류별 건수 요약(사람이 읽는 것)
  - hwpx_form_catalog_toc.xlsx : 요약 시트 + 전체 38,165건 상세 시트

사용: python scripts/ops/build_hwpx_form_catalog_toc.py
"""
from __future__ import annotations

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
        """SELECT f.form_id, f.name, f.institution, f.legal_basis,
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

    return {"total": len(rows), "fillable": fillable_n, "xlsx": str(xlsx_path),
            "by_inst_top5": by_inst[:5], "by_doc": by_doc}


if __name__ == "__main__":
    result = build()
    print(f"총 {result['total']}건 (입력가능 {result['fillable']}건)")
    print("발행기관 상위5:", result["by_inst_top5"])
    print("문서유형:", result["by_doc"])
    print("산출:", result["xlsx"])
