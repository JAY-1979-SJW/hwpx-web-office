"""
mart_price_reference_api.py
    mart_price.price_reference_monthly 읽기 전용 API (FastAPI)

엔드포인트:
    GET /health
    GET /api/v1/mart/price-reference-monthly

필터(쿼리 파라미터):
    year                    (int)
    month                   (int, 1~12)
    item_code               (str, exact)
    item_name_raw           (str, ILIKE '%q%')
    category                (str, exact)
    primary_reference_type  (str in 기준①|기준②|기준③|기준가|단가)

페이지네이션:
    page          (int ≥ 1, default 1)
    page_size     (int 1~500, default 50)

정렬: year DESC, month DESC, item_code NULLS LAST, item_name_raw

응답:
    {
      "total": int,
      "page": int,
      "page_size": int,
      "total_pages": int,
      "items": [
        {
          "item_code": str|null,
          "item_name_raw": str,
          "category": str|null,
          "item_name_std": str|null,
          "unit_code": str|null,
          "year": int,
          "month": int,
          "primary_reference_type": str,
          "primary_price": int,
          "avg_price": int,
          "min_price": int,
          "max_price": int,
          "obs_count": int
        }, ...
      ]
    }

원칙:
    - read-only (SELECT only)
    - mart_price.price_reference_monthly 이외 테이블 접근 없음
    - DB 접속은 ConnectionPool(min=1, max=8) 재사용

사용:
    PG_DSN="host=... dbname=price_db user=..." \
        python mart_price_reference_api.py --host 0.0.0.0 --port 8090
    또는
    python mart_price_reference_api.py \
        --pg "host=... dbname=price_db user=..." --host 0.0.0.0 --port 8090
"""

import argparse
import os
from contextlib import contextmanager
from typing import Optional

import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool

from fastapi import FastAPI, HTTPException, Query
import uvicorn


# ── 상수 ─────────────────────────────────────────────────────

ALLOWED_REF_TYPES = {"기준①", "기준②", "기준③", "기준가", "단가"}

SELECT_COLUMNS = (
    "item_code, item_name_raw, category, item_name_std, unit_code, "
    "year, month, primary_reference_type, primary_price, "
    "avg_price, min_price, max_price, obs_count"
)

ORDER_BY = (
    "ORDER BY year DESC, month DESC, "
    "item_code IS NULL, item_code ASC, item_name_raw ASC"
)


# ── 전역 상태 ────────────────────────────────────────────────

_pool: Optional[ThreadedConnectionPool] = None


def init_pool(dsn: str, minconn: int = 1, maxconn: int = 8) -> None:
    global _pool
    _pool = ThreadedConnectionPool(minconn, maxconn, dsn=dsn)


@contextmanager
def get_conn():
    if _pool is None:
        raise RuntimeError("connection pool not initialized")
    conn = _pool.getconn()
    try:
        # 읽기 전용 세션으로 강제
        conn.set_session(readonly=True, autocommit=True)
        yield conn
    finally:
        _pool.putconn(conn)


# ── FastAPI 앱 ───────────────────────────────────────────────

app = FastAPI(
    title="mart_price.price_reference_monthly Read API",
    version="1.0.0",
    description="KPI 참조가격 월별 집계 읽기 전용 조회 API",
)


@app.get("/health")
def health():
    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"db unreachable: {e!r}")


def _build_where(
    year: Optional[int],
    month: Optional[int],
    item_code: Optional[str],
    item_name_raw: Optional[str],
    category: Optional[str],
    primary_reference_type: Optional[str],
) -> tuple[str, list]:
    clauses: list[str] = []
    params: list = []

    if year is not None:
        clauses.append("year = %s")
        params.append(year)
    if month is not None:
        clauses.append("month = %s")
        params.append(month)
    if item_code is not None:
        clauses.append("item_code = %s")
        params.append(item_code)
    if item_name_raw is not None:
        clauses.append("item_name_raw ILIKE %s")
        params.append(f"%{item_name_raw}%")
    if category is not None:
        clauses.append("category = %s")
        params.append(category)
    if primary_reference_type is not None:
        clauses.append("primary_reference_type = %s")
        params.append(primary_reference_type)

    where_sql = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    return where_sql, params


@app.get("/api/v1/mart/price-reference-monthly")
def list_price_reference_monthly(
    year: Optional[int] = Query(None, ge=2000, le=2100),
    month: Optional[int] = Query(None, ge=1, le=12),
    item_code: Optional[str] = Query(None, max_length=64),
    item_name_raw: Optional[str] = Query(None, max_length=200),
    category: Optional[str] = Query(None, max_length=64),
    primary_reference_type: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
):
    if primary_reference_type is not None and primary_reference_type not in ALLOWED_REF_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"primary_reference_type must be one of {sorted(ALLOWED_REF_TYPES)}",
        )

    where_sql, params = _build_where(
        year, month, item_code, item_name_raw, category, primary_reference_type
    )

    offset = (page - 1) * page_size

    count_sql = f"SELECT COUNT(*) FROM mart_price.price_reference_monthly {where_sql}"
    data_sql = (
        f"SELECT {SELECT_COLUMNS} "
        f"FROM mart_price.price_reference_monthly "
        f"{where_sql} {ORDER_BY} "
        f"LIMIT %s OFFSET %s"
    )

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(count_sql, params)
            total = cur.fetchone()[0]
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(data_sql, (*params, page_size, offset))
            rows = cur.fetchall()

    total_pages = (total + page_size - 1) // page_size if page_size else 0
    return {
        "total":       total,
        "page":        page,
        "page_size":   page_size,
        "total_pages": total_pages,
        "items":       [dict(r) for r in rows],
    }


# ── 엔트리포인트 ─────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="mart_price.price_reference_monthly 읽기 전용 API (FastAPI)"
    )
    ap.add_argument("--pg",   default=os.environ.get("PG_DSN"),
                    help="PostgreSQL DSN (없으면 PG_DSN env)")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8090)
    args = ap.parse_args()

    if not args.pg:
        raise SystemExit("ERROR: --pg 또는 PG_DSN 환경변수 필요")

    init_pool(args.pg)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
