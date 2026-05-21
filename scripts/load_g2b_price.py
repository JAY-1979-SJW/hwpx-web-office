"""
load_g2b_price.py  --  standard_price.db (SQLite) → haehan_ai.g2b_price (PostgreSQL)

안전 원칙:
  - TRUNCATE 없음 (notice_date 범위별 교체 방식)
  - 기존 데이터 삭제 금지 (새 데이터 notice_date에 해당하는 행만 교체)
  - DB 연결 정보는 환경변수 또는 --env-file 로 주입 (하드코딩 없음)
  - UNIQUE 제약이 없어도 안전하게 동작 (temp table DELETE+INSERT 방식)

필수 환경변수 (또는 --env-file 로 로드):
  G2B_PG_HOST, G2B_PG_PORT, G2B_PG_DB, G2B_PG_USER, G2B_PG_PASSWORD

사용:
  python load_g2b_price.py
  python load_g2b_price.py --db /path/to/standard_price.db
  python load_g2b_price.py --env-file /home/ubuntu/app/g2b/.env.g2b --dry-run
"""

import argparse, os, sqlite3, sys
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import psycopg2
import psycopg2.extras

DEFAULT_DB = Path(os.environ.get("G2B_SQLITE_PATH",
                  str(Path(__file__).parent.parent / "data" / "standard_price.db")))
BATCH      = 2_000

BIZ_TO_WORK = {
    "시설자재(건축분야)":     "건축자재",
    "시설자재(토목분야)":     "토목자재",
    "시설자재(기계설비분야)": "기계자재",
    "시설자재(전기분야)":     "전기자재",
}


# ── 유틸 ─────────────────────────────────────────────────────────────────────

def load_env_file(path: str):
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def pg_connect():
    return psycopg2.connect(
        host=os.environ["G2B_PG_HOST"],
        port=int(os.environ.get("G2B_PG_PORT", "5432")),
        dbname=os.environ["G2B_PG_DB"],
        user=os.environ["G2B_PG_USER"],
        password=os.environ["G2B_PG_PASSWORD"],
    )


def to_decimal(val):
    if val is None or val == "":
        return None
    try:
        return Decimal(str(val))
    except InvalidOperation:
        return None


def parse_date(raw) -> str | None:
    if not raw:
        return None
    raw = str(raw).strip()
    if len(raw) == 8 and raw.isdigit():
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
    if len(raw) >= 10 and raw[4] == "-":
        return raw[:10]
    return None


def derive_work_type(biz_div: str | None) -> str:
    return BIZ_TO_WORK.get(biz_div or "", "기타")


# ── SQLite 읽기 ───────────────────────────────────────────────────────────────

def iter_sqlite_rows(sqlite_path: Path):
    conn = sqlite3.connect(str(sqlite_path))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("PRAGMA table_info(g2b_price)")
    cols = {r["name"] for r in cur.fetchall()}

    def col(row, *names):
        for n in names:
            if n in cols and row[n] is not None:
                return row[n]
        return None

    cur.execute("SELECT * FROM g2b_price")
    for row in cur:
        notice_date   = parse_date(col(row, "notice_date", "ntce_dt", "acquired_at"))
        prdct_idnt_no = str(col(row, "prdct_idnt_no", "spec_code") or "").strip()
        if not notice_date or not prdct_idnt_no:
            continue
        biz_div = col(row, "biz_div", "biz_div_nm")
        yield {
            "prdct_clsfc_no": col(row, "prdct_clsfc_no", "category_code"),
            "prdct_nm":       col(row, "prdct_nm", "spec_name"),
            "prdct_idnt_no":  prdct_idnt_no,
            "unit":           col(row, "unit"),
            "price":          to_decimal(col(row, "price", "unit_price")),
            "delivery_cond":  col(row, "delivery_cond", "delivery_condition"),
            "supply_region":  col(row, "supply_region"),
            "dept_nm":        col(row, "dept_nm"),
            "officer_nm":     col(row, "officer_nm"),
            "officer_tel":    col(row, "officer_tel"),
            "notice_date":    notice_date,
            "vat_type":       col(row, "vat_type"),
            "biz_div":        biz_div,
            "work_type":      col(row, "work_type") or derive_work_type(biz_div),
        }
    conn.close()


# ── PostgreSQL row-level upsert (삭제 없음) ──────────────────────────────────
#
# 방식: temp table → UPDATE 기존 행 + INSERT 신규 행
#   1. 임시 스테이징 테이블 생성
#   2. 새 데이터 전체 삽입
#   3. 기존 행 UPDATE (prdct_idnt_no + notice_date 매칭)
#   4. 신규 행만 INSERT (기존에 없는 쌍)
#
# 장점: 기존 데이터 절대 삭제 없음 — append-or-update only

COLS = (
    "prdct_clsfc_no", "prdct_nm", "prdct_idnt_no", "unit", "price",
    "delivery_cond", "supply_region", "dept_nm", "officer_nm", "officer_tel",
    "notice_date", "vat_type", "biz_div", "work_type",
)

STAGE_INSERT = f"""
INSERT INTO _g2b_stage ({', '.join(COLS)}) VALUES %s
"""

UPDATE_SQL = """
UPDATE g2b_price g SET
    prdct_clsfc_no = s.prdct_clsfc_no,
    prdct_nm       = s.prdct_nm,
    unit           = s.unit,
    price          = s.price::numeric,
    delivery_cond  = s.delivery_cond,
    supply_region  = s.supply_region,
    dept_nm        = s.dept_nm,
    officer_nm     = s.officer_nm,
    officer_tel    = s.officer_tel,
    vat_type       = s.vat_type,
    biz_div        = s.biz_div,
    work_type      = s.work_type
FROM _g2b_stage s
WHERE g.prdct_idnt_no = s.prdct_idnt_no
  AND g.notice_date::text = s.notice_date
"""

INSERT_NEW_SQL = """
INSERT INTO g2b_price (prdct_clsfc_no, prdct_nm, prdct_idnt_no, unit, price,
    delivery_cond, supply_region, dept_nm, officer_nm, officer_tel,
    notice_date, vat_type, biz_div, work_type)
SELECT s.prdct_clsfc_no, s.prdct_nm, s.prdct_idnt_no, s.unit, s.price::numeric,
       s.delivery_cond, s.supply_region, s.dept_nm, s.officer_nm, s.officer_tel,
       s.notice_date::date, s.vat_type, s.biz_div, s.work_type
FROM _g2b_stage s
WHERE NOT EXISTS (
    SELECT 1 FROM g2b_price g
    WHERE g.prdct_idnt_no = s.prdct_idnt_no
      AND g.notice_date::text = s.notice_date
)
"""

CREATE_STAGE = """
CREATE TEMP TABLE _g2b_stage (
    prdct_clsfc_no TEXT, prdct_nm TEXT, prdct_idnt_no TEXT,
    unit TEXT, price TEXT, delivery_cond TEXT, supply_region TEXT,
    dept_nm TEXT, officer_nm TEXT, officer_tel TEXT,
    notice_date TEXT, vat_type TEXT, biz_div TEXT, work_type TEXT
)
"""


def sync(sqlite_path: Path, dry_run: bool = False):
    if not sqlite_path.exists():
        print(f"[ERROR] SQLite 없음: {sqlite_path}", file=sys.stderr)
        sys.exit(1)

    rows_all: list[tuple] = []
    for row in iter_sqlite_rows(sqlite_path):
        rows_all.append(tuple(
            str(row[c]) if row[c] is not None else None
            for c in COLS
        ))

    total_src = len(rows_all)
    print(f"[LOAD] 소스: {sqlite_path}")
    print(f"[LOAD] SQLite 유효 행: {total_src:,}")

    if dry_run:
        from collections import Counter
        dates = Counter(r[COLS.index("notice_date")] for r in rows_all)
        print("[DRY-RUN] DB 저장 없이 종료")
        for nd, cnt in sorted(dates.items()):
            print(f"  {nd}: {cnt:,}행")
        return

    pg = pg_connect()
    try:
        with pg.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM g2b_price")
            before = cur.fetchone()[0]
        print(f"[LOAD] 적재 전 g2b_price: {before:,}행")

        with pg.cursor() as cur:
            cur.execute(CREATE_STAGE)
            for i in range(0, total_src, BATCH):
                psycopg2.extras.execute_values(cur, STAGE_INSERT, rows_all[i:i + BATCH])
                print(f"  스테이징 {min(i+BATCH, total_src):,}/{total_src:,}", end="\r", flush=True)

            cur.execute(UPDATE_SQL)
            updated = cur.rowcount
            cur.execute(INSERT_NEW_SQL)
            inserted = cur.rowcount

        pg.commit()

        with pg.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM g2b_price")
            after = cur.fetchone()[0]

        print(
            f"\n[LOAD] 완료  updated={updated:,}  inserted={inserted:,}  "
            f"g2b_price {before:,} → {after:,}  (순증 {after-before:+,})"
        )
    except Exception:
        pg.rollback()
        raise
    finally:
        pg.close()


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db",       default=str(DEFAULT_DB))
    ap.add_argument("--env-file", default="")
    ap.add_argument("--dry-run",  action="store_true")
    args = ap.parse_args()

    if args.env_file:
        load_env_file(args.env_file)

    # .env.g2b의 DB_* → G2B_PG_* 자동 매핑
    for src, dst in [("DB_HOST", "G2B_PG_HOST"), ("DB_PORT", "G2B_PG_PORT"),
                     ("DB_NAME", "G2B_PG_DB"),   ("DB_USER", "G2B_PG_USER"),
                     ("DB_PASSWORD", "G2B_PG_PASSWORD")]:
        if dst not in os.environ and src in os.environ:
            os.environ[dst] = os.environ[src]

    for var in ("G2B_PG_HOST", "G2B_PG_DB", "G2B_PG_USER", "G2B_PG_PASSWORD"):
        if var not in os.environ:
            print(f"[ERROR] 환경변수 없음: {var}", file=sys.stderr)
            sys.exit(1)

    sync(Path(args.db), dry_run=args.dry_run)


if __name__ == "__main__":
    main()
