"""
HWPX-FORM-INDEX-AND-RECOMMEND-01 — FastAPI 서버

실행:
    python scripts/ops/form_recommend_server.py
    uvicorn scripts.ops.form_recommend_server:app --reload --port 8765

엔드포인트:
    GET /api/form-recommend?q=소방+완공검사&top=10
    GET /api/form-stats
    GET /api/form-index.json  (정적 인덱스 다운로드)
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from hwpx.recognition_corpus.form_index import FormIndex, DEFAULT_JSONL

app = FastAPI(title="HWPX 서식 추천 API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

_index: FormIndex | None = None

def _get_index() -> FormIndex:
    global _index
    if _index is None:
        _index = FormIndex.load(DEFAULT_JSONL)
    return _index


@app.get("/api/form-recommend")
def form_recommend(
    q:   str = Query(...,  description="검색 쿼리 (예: 소방 완공검사 신청서)"),
    top: int = Query(10,   description="반환 개수", ge=1, le=50),
):
    """키워드 쿼리로 서식 추천."""
    results = _get_index().search(q, top)
    return {
        "query":   q,
        "total":   len(results),
        "results": [r.to_dict() for r in results],
    }


@app.get("/api/form-stats")
def form_stats():
    """인덱스 통계 (도메인별/서식종류별 파일 수)."""
    return _get_index().stats()


STATIC_JSON = (
    PROJECT_ROOT / "data" / "reports"
    / "hwpx_form_type_classification" / "form_index_static.json"
)

@app.get("/api/form-index.json")
def form_index_json():
    """JS fetch용 경량 정적 인덱스."""
    if not STATIC_JSON.exists():
        _get_index().export_static_index(STATIC_JSON)
    return FileResponse(str(STATIC_JSON), media_type="application/json")


@app.get("/health")
def health():
    return {"status": "ok", "indexLoaded": _index is not None}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("form_recommend_server:app", host="127.0.0.1", port=8765, reload=False)
