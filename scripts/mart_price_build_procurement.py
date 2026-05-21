"""
mart_price_build_procurement.py  --  G2B 조달단가 월별 mart 빌드

Source : staging_price.g2b_price_normalized
Target : mart_price.procurement_price_monthly
Sections: FCLTY_MTR_BILDNG · FCLTY_MTR_ENGRK · FCLTY_MTR_MCHN · FCLTY_MTR_ELCTY · NET_RESOURCE
Excluded: CNSTTY_CLASS

집계 규칙:
  기준 단위  : (section_code, item_code, year, month, supply_region)
  primary_price : 해당 월 내 최신 notice_date 기준 단가
  avg/min/max   : price_value NULL 제외 집계
  obs_count     : 해당 월 유효 관측 수

실행:
  python mart_price_build_procurement.py --env-file /home/ubuntu/app/g2b/.env.g2b
  python mart_price_build_procurement.py --env-file ... --dry-run
"""

import argparse, os, sys
from datetime import datetime

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    print("[ERROR] psycopg2 없음: pip install psycopg2-binary", file=sys.stderr)
    sys.exit(1)

INCLUDE_SECTIONS = [
    "FCLTY_MTR_BILDNG",
    "FCLTY_MTR_ENGRK",
    "FCLTY_MTR_MCHN",
    "FCLTY_MTR_ELCTY",
    "NET_RESOURCE",
]

# ── SQL ───────────────────────────────────────────────────────────────────────

BUILD_SQL = """
WITH ranked AS (
    SELECT *,
           ROW_NUMBER() OVER (
               PARTITION BY section_code, item_code, supply_region,
                            EXTRACT(YEAR  FROM notice_date),
                            EXTRACT(MONTH FROM notice_date)
               ORDER BY notice_date DESC
           ) AS rn
    FROM staging_price.g2b_price_normalized
    WHERE section_code = ANY(%(sections)s)
      AND price_value IS NOT NULL
),
primary_rows AS (
    SELECT
        section_code,
        item_code,
        supply_region,
        EXTRACT(YEAR  FROM notice_date)::SMALLINT AS year,
        EXTRACT(MONTH FROM notice_date)::SMALLINT AS month,
        price_value   AS primary_price,
        item_name     AS item_name_raw,
        category_code,
        category_name,
        unit_raw,
        biz_div       AS price_section
    FROM ranked
    WHERE rn = 1
),
agg AS (
    SELECT
        section_code,
        item_code,
        supply_region,
        EXTRACT(YEAR  FROM notice_date)::SMALLINT AS year,
        EXTRACT(MONTH FROM notice_date)::SMALLINT AS month,
        AVG(price_value)::BIGINT  AS avg_price,
        MIN(price_value)          AS min_price,
        MAX(price_value)          AS max_price,
        COUNT(*)                  AS obs_count
    FROM staging_price.g2b_price_normalized
    WHERE section_code = ANY(%(sections)s)
      AND price_value IS NOT NULL
    GROUP BY section_code, item_code, supply_region,
             EXTRACT(YEAR  FROM notice_date),
             EXTRACT(MONTH FROM notice_date)
)
INSERT INTO mart_price.procurement_price_monthly (
    source_system, section_code, price_section,
    item_code, item_name_raw,
    category_code, category_name, unit_raw,
    year, month, supply_region,
    primary_price, avg_price, min_price, max_price, obs_count, updated_at
)
SELECT
    'G2B',
    a.section_code,
    p.price_section,
    a.item_code,
    p.item_name_raw,
    p.category_code,
    p.category_name,
    p.unit_raw,
    a.year,
    a.month,
    a.supply_region,
    p.primary_price,
    a.avg_price,
    a.min_price,
    a.max_price,
    a.obs_count,
    NOW()
FROM agg a
JOIN primary_rows p
  ON  a.section_code  = p.section_code
  AND a.item_code     = p.item_code
  AND a.supply_region = p.supply_region
  AND a.year          = p.year
  AND a.month         = p.month
ON CONFLICT (source_system, section_code, item_code, year, month, supply_region)
DO UPDATE SET
    price_section = EXCLUDED.price_section,
    item_name_raw = EXCLUDED.item_name_raw,
    category_code = EXCLUDED.category_code,
    category_name = EXCLUDED.category_name,
    unit_raw      = EXCLUDED.unit_raw,
    primary_price = EXCLUDED.primary_price,
    avg_price     = EXCLUDED.avg_price,
    min_price     = EXCLUDED.min_price,
    max_price     = EXCLUDED.max_price,
    obs_count     = EXCLUDED.obs_count,
    updated_at    = NOW()
"""

DRY_RUN_SQL = """
WITH ranked AS (
    SELECT *,
           ROW_NUMBER() OVER (
               PARTITION BY section_code, item_code, supply_region,
                            EXTRACT(YEAR  FROM notice_date),
                            EXTRACT(MONTH FROM notice_date)
               ORDER BY notice_date DESC
           ) AS rn
    FROM staging_price.g2b_price_normalized
    WHERE section_code = ANY(%(sections)s)
      AND price_value IS NOT NULL
)
SELECT
    section_code,
    COUNT(*)                                            AS source_rows,
    COUNT(DISTINCT (item_code, supply_region))          AS distinct_items,
    COUNT(DISTINCT (EXTRACT(YEAR FROM notice_date),
                    EXTRACT(MONTH FROM notice_date)))   AS distinct_months,
    COUNT(DISTINCT supply_region)                       AS distinct_regions,
    MIN(notice_date)                                    AS earliest,
    MAX(notice_date)                                    AS latest
FROM staging_price.g2b_price_normalized
WHERE section_code = ANY(%(sections)s)
  AND price_value IS NOT NULL
GROUP BY section_code
ORDER BY section_code
"""


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
        host=os.environ.get("G2B_PG_HOST")     or os.environ.get("DB_HOST"),
        dbname=os.environ.get("G2B_PG_DB")     or os.environ.get("DB_NAME"),
        user=os.environ.get("G2B_PG_USER")     or os.environ.get("DB_USER"),
        password=os.environ.get("G2B_PG_PASSWORD") or os.environ.get("DB_PASSWORD"),
        port=int(os.environ.get("G2B_PG_PORT") or os.environ.get("DB_PORT", 5432)),
        connect_timeout=10,
    )


# ── 빌드 ─────────────────────────────────────────────────────────────────────

def run_dry_run(pg):
    with pg.cursor() as cur:
        cur.execute(DRY_RUN_SQL, {"sections": INCLUDE_SECTIONS})
        rows = cur.fetchall()
    print("\n[DRY-RUN] normalized 소스 요약:")
    print(f"  {'section_code':<25} {'rows':>8} {'items':>8} {'months':>7} {'regions':>7} {'earliest':>12} {'latest':>12}")
    total_rows = 0
    for r in rows:
        section, src, items, months, regions, earliest, latest = r
        print(f"  {section:<25} {src:>8,} {items:>8,} {months:>7} {regions:>7} {str(earliest):>12} {str(latest):>12}")
        total_rows += src
    print(f"  {'합계':<25} {total_rows:>8,}")
    print("\n[DRY-RUN] mart 미생성 — --dry-run 제거 후 재실행")


def run_build(pg):
    with pg.cursor() as cur:
        # 멱등 재빌드: TRUNCATE 후 INSERT
        cur.execute("TRUNCATE mart_price.procurement_price_monthly")
        print(f"[BUILD] mart TRUNCATE 완료")

        cur.execute(BUILD_SQL, {"sections": INCLUDE_SECTIONS})
        inserted = cur.rowcount
    pg.commit()
    print(f"[BUILD] INSERT 완료  rows={inserted:,}")
    return inserted


def validate(pg):
    with pg.cursor() as cur:
        # 섹션별 rowcount
        cur.execute("""
            SELECT section_code, COUNT(*) AS rows,
                   COUNT(DISTINCT item_code)   AS items,
                   COUNT(DISTINCT supply_region) AS regions,
                   MIN(year*100+month)::TEXT AS earliest_ym,
                   MAX(year*100+month)::TEXT AS latest_ym
            FROM mart_price.procurement_price_monthly
            GROUP BY section_code
            ORDER BY section_code
        """)
        section_rows = cur.fetchall()

        # 최신월 샘플 10건
        cur.execute("""
            SELECT section_code, item_code, item_name_raw, year, month,
                   supply_region, primary_price, avg_price, obs_count
            FROM mart_price.procurement_price_monthly
            WHERE year = (SELECT MAX(year) FROM mart_price.procurement_price_monthly)
              AND month = (SELECT MAX(month) FROM mart_price.procurement_price_monthly
                           WHERE year = (SELECT MAX(year) FROM mart_price.procurement_price_monthly))
            ORDER BY section_code, item_code
            LIMIT 10
        """)
        samples = cur.fetchall()

        # spot check: 단일 item_code 월별 추이
        cur.execute("""
            SELECT item_code, item_name_raw
            FROM mart_price.procurement_price_monthly
            WHERE section_code = 'FCLTY_MTR_BILDNG'
            GROUP BY item_code, item_name_raw
            HAVING COUNT(DISTINCT year*100+month) >= 2
            ORDER BY item_code
            LIMIT 1
        """)
        spot_item = cur.fetchone()

        spot_rows = []
        if spot_item:
            cur.execute("""
                SELECT year, month, supply_region, primary_price, avg_price, min_price, max_price, obs_count
                FROM mart_price.procurement_price_monthly
                WHERE section_code = 'FCLTY_MTR_BILDNG' AND item_code = %s
                ORDER BY year, month, supply_region
            """, (spot_item[0],))
            spot_rows = cur.fetchall()

    # 섹션별 출력
    print("\n[VALIDATE] 섹션별 rowcount:")
    print(f"  {'section_code':<25} {'rows':>8} {'items':>8} {'regions':>8} {'earliest':>10} {'latest':>10}")
    total = 0
    for r in section_rows:
        sc, rows, items, regions, earliest, latest = r
        print(f"  {sc:<25} {rows:>8,} {items:>8,} {regions:>8} {earliest:>10} {latest:>10}")
        total += rows
    print(f"  {'합계':<25} {total:>8,}")

    # 최신월 샘플
    if samples:
        latest_ym = f"{samples[0][3]}-{samples[0][4]:02d}"
        print(f"\n[VALIDATE] 최신월 샘플 ({latest_ym}):")
        for s in samples:
            sc, ic, nm, yr, mo, reg, pri, avg, obs = s
            reg_disp = reg if reg else '(전국)'
            print(f"  {sc:<20} {ic} {str(nm)[:30]:<32} region={reg_disp:<8} pri={pri:>10,} avg={avg:>10,} obs={obs}")

    # spot check
    if spot_item and spot_rows:
        print(f"\n[VALIDATE] spot check  item_code={spot_item[0]}  {spot_item[1]}")
        for r in spot_rows:
            yr, mo, reg, pri, avg, mn, mx, obs = r
            reg_disp = reg if reg else '(전국)'
            print(f"  {yr}-{mo:02d}  {reg_disp:<10} pri={pri:>10,}  avg={avg:>10,}  min={mn:>10,}  max={mx:>10,}  obs={obs}")


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="G2B 조달단가 월별 mart 빌드")
    ap.add_argument("--env-file", default="", help=".env 파일 경로")
    ap.add_argument("--dry-run",  action="store_true", help="소스 요약만 출력, mart 미생성")
    args = ap.parse_args()

    if args.env_file:
        load_env_file(args.env_file)

    pg = pg_connect()
    print(f"[MART BUILD] 시작  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"[MART BUILD] 대상 섹션: {', '.join(INCLUDE_SECTIONS)}")
    print(f"[MART BUILD] 제외 섹션: CNSTTY_CLASS")

    try:
        if args.dry_run:
            run_dry_run(pg)
        else:
            inserted = run_build(pg)
            validate(pg)
            print(f"\n[MART BUILD] 완료  총 {inserted:,}행 → mart_price.procurement_price_monthly")
    finally:
        pg.close()


if __name__ == "__main__":
    main()
