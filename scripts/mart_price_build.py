"""
mart_price_build.py  --  core_price.price_observation → mart_price.price_summary_monthly

처리 방식: TRUNCATE + 전체 재생성 (멱등성 보장)

집계 로직:
  1. price_observation 을 (item_id, year, month, source) 로 그룹화
     → avg_price (지역 간 평균), min_price, max_price, obs_count
  2. LAG 윈도우 함수로 전월(MoM) / 전년 동월(YoY) 가격 계산
  3. 변동률(%) = (현재 - 이전) / 이전 × 100
  4. 결과를 price_summary_monthly 에 일괄 삽입

사전 조건:
  - price_db_schema_patch_v2.sql 실행 완료 (avg/min/max/obs_count 컬럼 존재)
  - core_price.price_observation 에 데이터 존재

사용:
  python mart_price_build.py --pg "host=... dbname=price_db user=..."
  python mart_price_build.py --pg "..." --dry-run
"""

import argparse

import psycopg2
import psycopg2.extras

PASS = "PASS"
WARN = "WARN"
FAIL = "FAIL"

# ── 집계 + 전월/전년비 SQL ────────────────────────────────────
# region_id = NULL : 품목×소스 단위 지역 간 집계 레코드
# LAG는 이전 관측값(반드시 이전 월은 아님)을 반환; 데이터 공백이 있으면 최근 관측값 기준

BUILD_SQL = """
WITH base AS (
    SELECT
        item_id,
        year,
        month,
        source,
        ROUND(AVG(price))::BIGINT                                               AS avg_price,
        MIN(price)                                                               AS min_price,
        MAX(price)                                                               AS max_price,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price)::BIGINT              AS median_price,
        COUNT(*)                                                                 AS obs_count
    FROM core_price.price_observation
    GROUP BY item_id, year, month, source
),
with_prev AS (
    SELECT
        *,
        LAG(avg_price) OVER (
            PARTITION BY item_id, source
            ORDER BY year, month
        )                                                                        AS price_prev_month,
        LAG(avg_price, 12) OVER (
            PARTITION BY item_id, source
            ORDER BY year, month
        )                                                                        AS price_prev_year
    FROM base
)
INSERT INTO mart_price.price_summary_monthly
    (item_id, region_id, year, month, source,
     price, avg_price, min_price, max_price, obs_count,
     price_prev_month, price_prev_year,
     mom_change_pct, yoy_change_pct)
SELECT
    item_id,
    NULL                                                                         AS region_id,
    year,
    month,
    source,
    avg_price                                                                    AS price,
    avg_price,
    min_price,
    max_price,
    obs_count,
    price_prev_month,
    price_prev_year,
    CASE
        WHEN price_prev_month IS NOT NULL AND price_prev_month > 0
        THEN ROUND(
            ((avg_price - price_prev_month)::NUMERIC / price_prev_month * 100), 2
        )
    END                                                                          AS mom_change_pct,
    CASE
        WHEN price_prev_year IS NOT NULL AND price_prev_year > 0
        THEN ROUND(
            ((avg_price - price_prev_year)::NUMERIC / price_prev_year * 100), 2
        )
    END                                                                          AS yoy_change_pct
FROM with_prev
"""


# ── 사전 통계 ─────────────────────────────────────────────────

def get_obs_stats(conn) -> dict:
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM core_price.price_observation")
        total = cur.fetchone()[0]

        cur.execute("""
            SELECT source, COUNT(*)
            FROM core_price.price_observation
            GROUP BY source
            ORDER BY source
        """)
        by_src = cur.fetchall()

        cur.execute("""
            SELECT COUNT(DISTINCT item_id)
            FROM core_price.price_observation
        """)
        distinct_items = cur.fetchone()[0]

        cur.execute("""
            SELECT MIN(year * 100 + month), MAX(year * 100 + month)
            FROM core_price.price_observation
        """)
        row = cur.fetchone()
        date_min = row[0]
        date_max = row[1]

    return {
        "total": total,
        "by_source": by_src,
        "distinct_items": distinct_items,
        "date_min": date_min,
        "date_max": date_max,
    }


# ── mart 빌드 ─────────────────────────────────────────────────

def build_mart(conn, dry_run: bool) -> dict:
    obs = get_obs_stats(conn)
    print(f"\n[price_observation 현황]")
    print(f"  총계: {obs['total']:,}건, 고유 품목: {obs['distinct_items']:,}건")
    for src, cnt in obs["by_source"]:
        print(f"  {src}: {cnt:,}건")
    if obs["date_min"] and obs["date_max"]:
        print(f"  기간: {obs['date_min']//100}-{obs['date_min']%100:02d} ~ "
              f"{obs['date_max']//100}-{obs['date_max']%100:02d}")

    if obs["total"] == 0:
        print("[FAIL] price_observation 데이터 없음 → mart 빌드 불가")
        return {"status": FAIL}

    if dry_run:
        print("\n[dry] TRUNCATE + INSERT 건너뜀")
        return {"status": PASS, "obs_total": obs["total"]}

    print("\n[mart 빌드] TRUNCATE...")
    with conn.cursor() as cur:
        cur.execute("TRUNCATE mart_price.price_summary_monthly")
    conn.commit()

    print("[mart 빌드] 집계 INSERT 실행 중...")
    with conn.cursor() as cur:
        cur.execute(BUILD_SQL)
        inserted = cur.rowcount
    conn.commit()

    print(f"[mart 빌드] 완료: {inserted:,}건 삽입")
    return {"status": PASS, "obs_total": obs["total"], "inserted": inserted}


# ── 5단계: 검증 ──────────────────────────────────────────────

def verify_mart(conn) -> dict:
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM mart_price.price_summary_monthly")
        total = cur.fetchone()[0]

        cur.execute("""
            SELECT source, COUNT(*)
            FROM mart_price.price_summary_monthly
            GROUP BY source
            ORDER BY source
        """)
        by_src = cur.fetchall()

        cur.execute("""
            SELECT COUNT(*) FROM mart_price.price_summary_monthly
            WHERE mom_change_pct IS NOT NULL
        """)
        mom_ok = cur.fetchone()[0]

        cur.execute("""
            SELECT COUNT(*) FROM mart_price.price_summary_monthly
            WHERE yoy_change_pct IS NOT NULL
        """)
        yoy_ok = cur.fetchone()[0]

        cur.execute("""
            SELECT COUNT(DISTINCT item_id)
            FROM mart_price.price_summary_monthly
        """)
        distinct_items = cur.fetchone()[0]

        cur.execute("""
            SELECT MIN(year * 100 + month), MAX(year * 100 + month)
            FROM mart_price.price_summary_monthly
        """)
        row = cur.fetchone()

    return {
        "total":         total,
        "by_source":     by_src,
        "mom_ok":        mom_ok,
        "yoy_ok":        yoy_ok,
        "distinct_items": distinct_items,
        "date_min":      row[0],
        "date_max":      row[1],
    }


def print_verify(v: dict) -> str:
    lines = ["\n=== [5단계] mart_price.price_summary_monthly 검증 ==="]
    total = v["total"]
    lines.append(f"  총계: {total:,}건")
    lines.append(f"  고유 품목 수: {v['distinct_items']:,}건")

    lines.append("\n  [source별 건수]")
    for src, cnt in v["by_source"]:
        lines.append(f"    {src}: {cnt:,}건")

    lines.append(f"\n  전월비 계산 가능: {v['mom_ok']:,}건")
    lines.append(f"  전년비 계산 가능: {v['yoy_ok']:,}건")

    if v["date_min"] and v["date_max"]:
        lines.append(
            f"  기간: {v['date_min']//100}-{v['date_min']%100:02d} ~ "
            f"{v['date_max']//100}-{v['date_max']%100:02d}"
        )

    if total == 0:
        verdict = FAIL
    elif v["mom_ok"] == 0 and v["yoy_ok"] == 0:
        verdict = WARN
    else:
        verdict = PASS

    lines.append(f"\n  판정: {verdict}")
    print("\n".join(lines))
    return verdict


# ── 메인 ─────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="mart_price.price_summary_monthly 배치 빌드 (전체 재생성)"
    )
    ap.add_argument("--pg",      required=True, help="PostgreSQL DSN")
    ap.add_argument("--dry-run", action="store_true", help="실행 없이 통계만 출력")
    args = ap.parse_args()

    if args.dry_run:
        print("=== DRY RUN 모드 ===")

    conn = psycopg2.connect(args.pg)
    try:
        result = build_mart(conn, args.dry_run)

        if not args.dry_run:
            v        = verify_mart(conn)
            verdict  = print_verify(v)
            final    = verdict
            print(f"\n===== 최종 판정: {final} =====")

    finally:
        conn.close()
    print("\n완료")


if __name__ == "__main__":
    main()
