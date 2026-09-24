"""HWPX RO-VIEW 렌더 서비스 — 읽기전용 HTTP 래퍼.

ro_view_importer.import_hwpx_as_ro_view() + render_payload.build_render_payload()
를 그대로 호출해 얻은 payload를 HTML로 직렬화해 돌려준다. HWPX 파일 자체를
수정하는 API는 이 서비스에 없다(원본 프로젝트의 read-only 원칙 그대로 유지).

기동: uvicorn scripts.hwpx.web_office.service:app --host 0.0.0.0 --port 8090
"""
from __future__ import annotations

import html as _html
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse

from .ro_view_importer import import_hwpx_as_ro_view
from .render_payload import build_render_payload

app = FastAPI(title="hwpx-ro-view-engine")


@app.get("/health")
def health():
    return {"status": "ok"}


def _esc(s: str | None) -> str:
    return _html.escape(s or "")


def _cell_display_text(cell: dict) -> str:
    # RO_VIEW_CELL_TEXT_SPACING_01 (2026-09-01 office-analysis-engine fb3ebf5, 2026-09-24 02 이관):
    # cell['text'] 는 검색색인용 normalizedText 라 띄어쓰기가 사라진다. 02 에서는 이 값이
    # 양식 필드 역할 판정의 계약이라(importer 봉인, test_web_office_field_roles) 바꾸지 않고,
    # 화면 표시만 셀 문단(run 단위 측량, 공백 보존) 텍스트로 만든다. 문단이 비면 cell['text'].
    joined = "\n".join(p.get("text") or "" for p in cell.get("paragraphs") or [] if p.get("text"))
    return joined or (cell.get("text") or "")


def _render_table_html(table: dict, cells_by_id: dict) -> str:
    cell_by_pos: dict[tuple[int, int], dict] = {}
    for c in table["cells"]:
        cell_by_pos[(c["row"], c["col"])] = c

    rows_html = []
    for r in range(table["rowCount"]):
        cells_html = []
        for c in range(table["colCount"]):
            cell = cell_by_pos.get((r, c))
            if cell is None or cell["isCoveredByMerge"]:
                continue
            attrs = ""
            if cell["rowSpan"] > 1:
                attrs += f' rowspan="{cell["rowSpan"]}"'
            if cell["colSpan"] > 1:
                attrs += f' colspan="{cell["colSpan"]}"'
            # RO_VIEW_G2B_CLASS_ALIGN_01 (2026-09-01): g2b(호출부)의
            # ui/globals.css .doc-html-view .doc-table[td[rowspan]/[colspan]]가
            # 이미 병합 셀을 강조하는 CSS를 갖고 있다 — 별도 class 없이 속성만
            # 있으면 자동으로 적용되므로 wo-cell-merged-origin 같은 자체 class는
            # 안 넣는다(중복 스타일 방지, g2b 쪽 CSS 하나만 SoT).
            cells_html.append(f"<td{attrs}>{_esc(_cell_display_text(cell))}</td>")
        if cells_html:
            rows_html.append(f"<tr>{''.join(cells_html)}</tr>")
    merged_attr = ' data-has-merged="true"' if table["hasMergedCells"] else ""
    return f'<table class="doc-table"{merged_attr}>{"".join(rows_html)}</table>'


def _render_body_html(payload: dict) -> str:
    # RO_VIEW_G2B_CLASS_ALIGN_01: class명을 g2b DocTextViewer.tsx가 이미 쓰는
    # hwp-doc-engine 출력 규약(doc-p/doc-table, ui/globals.css .doc-html-view
    # 하위)에 맞춘다 — 이 서비스는 g2b가 <div class="doc-html-view"> 안에
    # dangerouslySetInnerHTML로 그대로 삽입하는 "본문 조각"만 돌려준다.
    # <html>/<head>/<style> 전체 문서를 주면 그 안의 <style> 텍스트가 그대로
    # 화면 텍스트로 노출된다(2026-09-01 실측 — g2b 프로덕션에서 CSS 원문이
    # 그대로 보이는 버그로 발견).
    tables_by_id = {t["tableId"]: t for t in payload["tables"]}
    parts: list[str] = []
    for b in sorted(payload["blocks"], key=lambda x: (x["sectionIndex"], x["blockIndex"])):
        if b["type"] == "paragraph" and b.get("paragraph"):
            text = _esc(b["paragraph"]["text"]).replace("\n", "<br>")
            parts.append(f'<div class="doc-p">{text}</div>')
        elif b["type"] == "table" and b["ref"] in tables_by_id:
            parts.append(_render_table_html(tables_by_id[b["ref"]], {}))
        elif b["type"] == "object":
            parts.append('<div class="doc-p" style="color:#999">[개체]</div>')
    return "\n".join(parts)


_PAGE_TEMPLATE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{{margin:0;padding:20px;font:14px -apple-system,BlinkMacSystemFont,"Noto Sans KR",sans-serif;
  color:#2b2620;background:#fff;line-height:1.65}}
.doc-p{{margin:0 0 9px}}
.doc-p:empty{{display:none}}
table.doc-table{{border-collapse:collapse;margin:14px 0 20px;width:100%;font-size:13px}}
table.doc-table td{{border:1px solid #ddd6c4;padding:7px 11px;vertical-align:top}}
table.doc-table td[rowspan],table.doc-table td[colspan]{{background:#f1e2dc}}
.wo-warn{{font-size:11px;color:#96631f;margin-top:24px;padding-top:8px;border-top:1px solid #ddd6c4}}
</style></head><body>
{body}
{warnings}
</body></html>"""


def _build_payload_from_upload(data: bytes) -> dict:
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "input.hwpx"
        src.write_bytes(data)
        try:
            doc = import_hwpx_as_ro_view(src)
        except Exception as e:  # noqa: BLE001 — 문서 손상 등도 502로 명확히 알림
            raise HTTPException(status_code=502, detail=f"HWPX 파싱 실패: {type(e).__name__}: {e}") from e
        return build_render_payload(doc)


@app.post("/render-hwpx", summary="HWPX → 읽기전용 HTML 조각 (g2b DocTextViewer용, <html>/<style> 없음)")
async def render_hwpx(file: UploadFile = File(...)):
    """g2b가 이 응답을 <div class="doc-html-view">에 dangerouslySetInnerHTML로
    그대로 삽입한다 — 전체 HTML 문서를 주면 <style> 텍스트가 화면에 그대로
    노출된다(2026-09-01 실측). 스타일은 g2b ui/globals.css의 .doc-html-view
    규칙(doc-p/doc-table, 이미 hwp-doc-engine 출력과 공유)에 맡긴다.
    """
    if not file.filename or not file.filename.lower().endswith((".hwpx",)):
        raise HTTPException(status_code=400, detail="HWPX 파일만 지원합니다")
    data = await file.read()
    payload = _build_payload_from_upload(data)
    return HTMLResponse(_render_body_html(payload))


@app.post("/render-hwpx/full-page", summary="HWPX → 완전한 HTML 문서 (단독 미리보기/디버그 전용)")
async def render_hwpx_full_page(file: UploadFile = File(...)):
    """render-hwpx와 달리 <html>/<head>/<style>을 포함한 완전한 문서를 반환한다
    — g2b iframe(호출부가 srcdoc으로 통째로 띄우는 용도) 또는 브라우저로 직접
    열어 단독 확인할 때만 쓴다. g2b의 <div> 인라인 삽입에는 이 엔드포인트를
    쓰지 않는다(위 render-hwpx 참고).
    """
    if not file.filename or not file.filename.lower().endswith((".hwpx",)):
        raise HTTPException(status_code=400, detail="HWPX 파일만 지원합니다")
    data = await file.read()
    payload = _build_payload_from_upload(data)
    body_html = _render_body_html(payload)
    warn_html = ""
    if payload.get("warnings"):
        warn_html = f'<div class="wo-warn">경고 {len(payload["warnings"])}건 (fidelity, 비치명적)</div>'
    return HTMLResponse(_PAGE_TEMPLATE.format(body=body_html, warnings=warn_html))


@app.post("/render-hwpx/payload", summary="HWPX → render payload(JSON) — 디버그/재사용용")
async def render_hwpx_payload(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith((".hwpx",)):
        raise HTTPException(status_code=400, detail="HWPX 파일만 지원합니다")
    data = await file.read()
    payload = _build_payload_from_upload(data)
    return JSONResponse(payload)
