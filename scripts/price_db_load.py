"""
price_db_load.py  --  KPI SQLite + KPRC JSON → PostgreSQL 적재 (staging_price)

서버 실행 전제:
  - PostgreSQL price_db 생성 및 price_db_schema.sql 적용 완료
  - KPI SQLite: ~/Downloads/kpi_pdf/result/kpi_prices.db
  - KPRC JSON : ~/Downloads/kprc_pdf/result/주요자재_가격_3년_YYYYMMDD.json (최신 1개)

사용:
  python price_db_load.py --pg "host=localhost dbname=price_db user=postgres password=..."
  python price_db_load.py --pg "..." --source kpi   # KPI만
  python price_db_load.py --pg "..." --source kprc  # KPRC만
"""

import argparse, hashlib, json, os, sqlite3, sys
from datetime import datetime
from pathlib import Path

import psycopg2
import psycopg2.extras

KPI_DB   = Path(os.environ.get("KPI_DB",  str(Path.home() / "Downloads/kpi_pdf/result/kpi_prices.db")))
KPRC_DIR = Path(os.environ.get("KPRC_DIR", str(Path.home() / "Downloads/kprc_pdf/result")))


# ── 유틸 ─────────────────────────────────────────────────────

def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def upsert_file(cur, source: str, path: Path, pub_year: int | None, pub_month: int | None) -> int:
    """raw_ingest.files 에 파일 등록 (중복 시 기존 id 반환)."""
    sha = file_sha256(path)
    cur.execute(
        """
        INSERT INTO raw_ingest.files (source, file_name, file_path, file_size, content_hash,
                                      pub_year, pub_month, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, 'parsed')
        ON CONFLICT (content_hash) DO UPDATE SET status='parsed'
        RETURNING id
        """,
        (source, path.name, str(path), path.stat().st_size, sha, pub_year, pub_month),
    )
    return cur.fetchone()[0]


# ── KPI 적재 ──────────────────────────────────────────────────

def load_kpi(pg_conn):
    if not KPI_DB.exists():
        print(f"[KPI] DB 없음: {KPI_DB}")
        return

    print(f"[KPI] 소스: {KPI_DB}")
    sqlite = sqlite3.connect(str(KPI_DB))
    sqlite.row_factory = sqlite3.Row

    cur_s = sqlite.cursor()
    cur_s.execute("SELECT COUNT(*) FROM prices")
    total = cur_s.fetchone()[0]
    print(f"[KPI] 총 {total:,}행")

    with pg_conn.cursor() as cur:
        # 파일 등록 (KPI DB 자체가 단일 파일)
        file_id = upsert_file(cur, "KPI", KPI_DB, None, None)
        pg_conn.commit()
        print(f"[KPI] file_id={file_id}")

        # staging 적재 (이미 있는 file_id 행 스킵)
        cur.execute(
            "SELECT COUNT(*) FROM staging_price.kpi_prices_raw WHERE file_id=%s", (file_id,)
        )
        already = cur.fetchone()[0]
        if already > 0:
            print(f"[KPI] 이미 적재됨 ({already:,}행) — 스킵")
            return

        BATCH = 10_000
        inserted = 0
        buf = []

        cur_s.execute(
            "SELECT 연도,월,책명,분류,품목명,단위,지역,가격 FROM prices"
        )
        for row in cur_s:
            buf.append((file_id, row["연도"], row["월"], row["책명"], row["분류"],
                        row["품목명"], row["단위"], row["지역"], row["가격"]))
            if len(buf) >= BATCH:
                psycopg2.extras.execute_values(
                    cur,
                    """INSERT INTO staging_price.kpi_prices_raw
                       (file_id,연도,월,책명,분류,품목명,단위,지역,가격)
                       VALUES %s""",
                    buf,
                )
                pg_conn.commit()
                inserted += len(buf)
                buf.clear()
                print(f"  {inserted:,}/{total:,}", end="\r", flush=True)

        if buf:
            psycopg2.extras.execute_values(
                cur,
                """INSERT INTO staging_price.kpi_prices_raw
                   (file_id,연도,월,책명,분류,품목명,단위,지역,가격)
                   VALUES %s""",
                buf,
            )
            pg_conn.commit()
            inserted += len(buf)

    sqlite.close()
    print(f"\n[KPI] 완료: {inserted:,}행 적재")


# ── KPRC 적재 ─────────────────────────────────────────────────

def load_kprc(pg_conn):
    jsons = sorted(KPRC_DIR.glob("주요자재_가격_*.json"), reverse=True)
    if not jsons:
        print(f"[KPRC] JSON 없음: {KPRC_DIR}")
        return

    latest = jsons[0]
    print(f"[KPRC] 소스: {latest.name}")
    data = json.loads(latest.read_text(encoding="utf-8"))
    rows = data.get("rows", [])
    print(f"[KPRC] 총 {len(rows):,}행")

    with pg_conn.cursor() as cur:
        file_id = upsert_file(cur, "KPRC", latest, None, None)
        pg_conn.commit()
        print(f"[KPRC] file_id={file_id}")

        cur.execute(
            "SELECT COUNT(*) FROM staging_price.kprc_prices_raw WHERE file_id=%s", (file_id,)
        )
        already = cur.fetchone()[0]
        if already > 0:
            print(f"[KPRC] 이미 적재됨 ({already:,}행) — 스킵")
            return

        BATCH = 5_000
        inserted = 0
        buf = []

        for r in rows:
            출처 = r.get("출처", "종합표")
            if 출처 not in ("차트페이지", "종합표", "종합표_연평균"):
                출처 = "종합표"
            buf.append((
                file_id, r.get("연도"), r.get("월"),
                r.get("품목명", ""), r.get("규격"), r.get("단위"),
                r.get("가격"), r.get("조사지역"), 출처,
            ))
            if len(buf) >= BATCH:
                psycopg2.extras.execute_values(
                    cur,
                    """INSERT INTO staging_price.kprc_prices_raw
                       (file_id,연도,월,품목명,규격,단위,가격,조사지역,출처)
                       VALUES %s""",
                    buf,
                )
                pg_conn.commit()
                inserted += len(buf)
                buf.clear()

        if buf:
            psycopg2.extras.execute_values(
                cur,
                """INSERT INTO staging_price.kprc_prices_raw
                   (file_id,연도,월,품목명,규격,단위,가격,조사지역,출처)
                   VALUES %s""",
                buf,
            )
            pg_conn.commit()
            inserted += len(buf)

    print(f"[KPRC] 완료: {inserted:,}행 적재")


# ── 메인 ─────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pg",     required=True, help="PostgreSQL DSN")
    ap.add_argument("--source", choices=["kpi","kprc","all"], default="all")
    args = ap.parse_args()

    conn = psycopg2.connect(args.pg)
    try:
        if args.source in ("kpi",  "all"):
            load_kpi(conn)
        if args.source in ("kprc", "all"):
            load_kprc(conn)
    finally:
        conn.close()
    print("완료")


if __name__ == "__main__":
    main()
