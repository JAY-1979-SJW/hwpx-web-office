"""
mart_price_build_reference.py
    core_price.price_reference  →  mart_price.price_reference_monthly

처리 방식: TRUNCATE + 전체 재생성 (멱등성 보장)

집계 단위:
    item_code IS NOT NULL  → (item_code, year, month)
    item_code IS NULL      → (item_name_raw, category, year, month)

primary_reference_type 우선순위:
    기준① > 기준② > 기준③ > 기준가 > 단가
    (해당 우선순위 타입이 존재하지 않으면 그 다음 순위를 선택)

산출:
    primary_reference_type   선택된 대표 타입
    primary_price            대표 타입의 평균 가격 (BIGINT)
    avg_price                전체 reference_type 평균
    min_price / max_price    전체 범위 최저/최고
    obs_count                원천 행 수

사전 조건:
    - price_db_schema_patch_v5.sql 실행 완료
        (mart_price.price_reference_monthly 테이블 존재)
    - core_price.price_reference 에 데이터 존재

주의:
    - mart_price.price_summary_monthly 는 손대지 않음
    - 본 스크립트는 오직 price_reference_monthly 만 TRUNCATE+INSERT

사용:
    python mart_price_build_reference.py --pg "host=... dbname=price_db user=..."
    python mart_price_build_reference.py --pg "..." --dry-run
"""

import argparse

import psycopg2

PASS = "PASS"
WARN = "WARN"
FAIL = "FAIL"


# ── 집계 SQL ─────────────────────────────────────────────────
# group_key:
#   item_code 있으면   'C:' || item_code
#   item_code 없으면   'N:' || item_name_raw || '||' || COALESCE(category,'')
# primary_reference_type:
#   DISTINCT ON (group_key, year, month) + priority ORDER BY 로 선택
# type_avg_price:
#   같은 (group_key, year, month, reference_type) 내 평균

BUILD_SQL = """
WITH base AS (
    SELECT
        CASE
            WHEN item_code IS NOT NULL
                THEN 'C:' || item_code
            ELSE
                'N:' || item_name_raw || '||' || COALESCE(category, '')
        END                                                     AS group_key,
        item_code,
        item_name_raw,
        item_name_std,
        category,
        unit_code,
        price_year                                              AS year,
        price_month                                             AS month,
        reference_type,
        price
    FROM core_price.price_reference
),
by_type AS (
    SELECT
        group_key,
        year,
        month,
        reference_type,
        ROUND(AVG(price))::BIGINT                               AS type_avg_price
    FROM base
    GROUP BY group_key, year, month, reference_type
),
picked AS (
    SELECT DISTINCT ON (group_key, year, month)
        group_key,
        year,
        month,
        reference_type                                          AS primary_reference_type,
        type_avg_price                                          AS primary_price
    FROM by_type
    ORDER BY
        group_key, year, month,
        CASE reference_type
            WHEN '기준①'  THEN 1
            WHEN '기준②'  THEN 2
            WHEN '기준③'  THEN 3
            WHEN '기준가' THEN 4
            WHEN '단가'   THEN 5
            ELSE 99
        END
),
agg AS (
    SELECT
        group_key,
        year,
        month,
        MAX(item_code)                                          AS item_code,
        MAX(item_name_raw)                                      AS item_name_raw,
        MAX(category)                                           AS category,
        MAX(item_name_std)                                      AS item_name_std,
        MAX(unit_code)                                          AS unit_code,
        ROUND(AVG(price))::BIGINT                               AS avg_price,
        MIN(price)                                              AS min_price,
        MAX(price)                                              AS max_price,
        COUNT(*)                                                AS obs_count
    FROM base
    GROUP BY group_key, year, month
)
INSERT INTO mart_price.price_reference_monthly
    (item_code, item_name_raw, category, item_name_std, unit_code,
     year, month,
     primary_reference_type, primary_price,
     avg_price, min_price, max_price, obs_count)
SELECT
    a.item_code,
    a.item_name_raw,
    a.category,
    a.item_name_std,
    a.unit_code,
    a.year,
    a.month,
    p.primary_reference_type,
    p.primary_price,
    a.avg_price,
    a.min_price,
    a.max_price,
    a.obs_count
FROM agg a
JOIN picked p USING (group_key, year, month)
"""


# ── 사전 통계 ────────────────────────────────────────────────

def get_src_stats(conn) -> dict:
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM core_price.price_reference")
        total = cur.fetchone()[0]

        cur.execute("""
            SELECT reference_type, COUNT(*)
            FROM core_price.price_reference
            GROUP BY reference_type
            ORDER BY reference_type
        """)
        by_type = cur.fetchall()

        cur.execute("""
            SELECT
                COUNT(*) FILTER (WHERE item_code IS NOT NULL),
                COUNT(*) FILTER (WHERE item_code IS NULL)
            FROM core_price.price_reference
        """)
        row = cur.fetchone()
        with_code = row[0]
        without_code = row[1]

        cur.execute("""
            SELECT MIN(price_year * 100 + price_month),
                   MAX(price_year * 100 + price_month)
            FROM core_price.price_reference
        """)
        row = cur.fetchone()
        date_min = row[0]
        date_max = row[1]

        cur.execute("""
            SELECT COUNT(*) FROM (
                SELECT 1
                FROM core_price.price_reference
                GROUP BY
                    CASE WHEN item_code IS NOT NULL
                         THEN 'C:' || item_code
                         ELSE 'N:' || item_name_raw || '||' || COALESCE(category,'')
                    END,
                    price_year, price_month
            ) t
        """)
        projected_rows = cur.fetchone()[0]

    return {
        "total": total,
        "by_type": by_type,
        "with_code": with_code,
        "without_code": without_code,
        "date_min": date_min,
        "date_max": date_max,
        "projected_rows": projected_rows,
    }


# ── mart 빌드 ────────────────────────────────────────────────

def build_mart(conn, dry_run: bool) -> dict:
    src = get_src_stats(conn)
    print("\n[core_price.price_reference 현황]")
    print(f"  총계: {src['total']:,}건")
    print(f"  item_code 연결: {src['with_code']:,}건 / 미연결: {src['without_code']:,}건")
    for ref, cnt in src["by_type"]:
        print(f"  {ref}: {cnt:,}건")
    if src["date_min"] and src["date_max"]:
        print(f"  기간: {src['date_min']//100}-{src['date_min']%100:02d} ~ "
              f"{src['date_max']//100}-{src['date_max']%100:02d}")
    print(f"  예상 집계 rowcount: {src['projected_rows']:,}건")

    if src["total"] == 0:
        print("[FAIL] price_reference 데이터 없음 → mart 빌드 불가")
        return {"status": FAIL}

    if dry_run:
        print("\n[dry] TRUNCATE + INSERT 건너뜀 (구조 분석만 수행)")
        return {
            "status":         PASS,
            "src_total":      src["total"],
            "projected_rows": src["projected_rows"],
        }

    print("\n[mart 빌드] TRUNCATE mart_price.price_reference_monthly ...")
    with conn.cursor() as cur:
        cur.execute("TRUNCATE mart_price.price_reference_monthly")
    conn.commit()

    print("[mart 빌드] 집계 INSERT 실행 중...")
    with conn.cursor() as cur:
        cur.execute(BUILD_SQL)
        inserted = cur.rowcount
    conn.commit()

    print(f"[mart 빌드] 완료: {inserted:,}건 삽입")
    return {
        "status":   PASS,
        "src_total": src["total"],
        "inserted": inserted,
    }


# ── 검증 ─────────────────────────────────────────────────────

def verify_mart(conn) -> dict:
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM mart_price.price_reference_monthly")
        total = cur.fetchone()[0]

        cur.execute("""
            SELECT primary_reference_type, COUNT(*)
            FROM mart_price.price_reference_monthly
            GROUP BY primary_reference_type
            ORDER BY primary_reference_type
        """)
        by_primary = cur.fetchall()

        cur.execute("""
            SELECT
                COUNT(*) FILTER (WHERE item_code IS NOT NULL),
                COUNT(*) FILTER (WHERE item_code IS NULL)
            FROM mart_price.price_reference_monthly
        """)
        row = cur.fetchone()
        with_code = row[0]
        without_code = row[1]

        cur.execute("""
            SELECT MIN(year * 100 + month), MAX(year * 100 + month)
            FROM mart_price.price_reference_monthly
        """)
        row = cur.fetchone()
        date_min = row[0]
        date_max = row[1]

        # 샘플 10건 (item_code 있는 최신월 중심)
        cur.execute("""
            SELECT
                item_code, item_name_raw, category,
                year, month,
                primary_reference_type, primary_price,
                avg_price, min_price, max_price, obs_count
            FROM mart_price.price_reference_monthly
            ORDER BY year DESC, month DESC, item_code NULLS LAST, item_name_raw
            LIMIT 10
        """)
        samples = cur.fetchall()

        # 무결성: primary_price 가 min/max 범위 안에 있는지
        cur.execute("""
            SELECT COUNT(*) FROM mart_price.price_reference_monthly
            WHERE primary_price < min_price OR primary_price > max_price
        """)
        primary_out_of_range = cur.fetchone()[0]

        # 무결성: avg_price 가 min/max 범위 안에 있는지
        cur.execute("""
            SELECT COUNT(*) FROM mart_price.price_reference_monthly
            WHERE avg_price < min_price OR avg_price > max_price
        """)
        avg_out_of_range = cur.fetchone()[0]

    return {
        "total":                total,
        "by_primary":           by_primary,
        "with_code":            with_code,
        "without_code":         without_code,
        "date_min":             date_min,
        "date_max":             date_max,
        "samples":              samples,
        "primary_out_of_range": primary_out_of_range,
        "avg_out_of_range":     avg_out_of_range,
    }


def print_verify(v: dict) -> str:
    lines = ["\n=== mart_price.price_reference_monthly 검증 ==="]
    total = v["total"]
    lines.append(f"  총계: {total:,}건")
    lines.append(f"  item_code 연결: {v['with_code']:,}건 / 미연결: {v['without_code']:,}건")

    lines.append("\n  [primary_reference_type 별 건수]")
    for ref, cnt in v["by_primary"]:
        lines.append(f"    {ref}: {cnt:,}건")

    if v["date_min"] and v["date_max"]:
        lines.append(
            f"\n  기간: {v['date_min']//100}-{v['date_min']%100:02d} ~ "
            f"{v['date_max']//100}-{v['date_max']%100:02d}"
        )

    lines.append("\n  [무결성]")
    lines.append(f"    primary_price min/max 범위 이탈: {v['primary_out_of_range']:,}건")
    lines.append(f"    avg_price     min/max 범위 이탈: {v['avg_out_of_range']:,}건")

    lines.append("\n  [샘플 10건]")
    for s in v["samples"]:
        (icode, iname, cat, yr, mo, ptype, pprc,
         avg, mn, mx, cnt) = s
        icode_s = icode if icode else "-"
        cat_s   = cat   if cat   else "-"
        iname_s = (iname or "")[:24]
        lines.append(
            f"    {yr}-{mo:02d} | {icode_s:>14s} | {iname_s:<24s} | {cat_s:<8s} | "
            f"{ptype:<6s} pri={pprc:>10,} avg={avg:>10,} "
            f"min={mn:>10,} max={mx:>10,} n={cnt}"
        )

    # 판정
    if total == 0:
        verdict = FAIL
    elif v["primary_out_of_range"] > 0 or v["avg_out_of_range"] > 0:
        verdict = WARN
    else:
        verdict = PASS

    lines.append(f"\n  판정: {verdict}")
    print("\n".join(lines))
    return verdict


# ── 기존 테이블 영향 없음 확인 ────────────────────────────────

def check_summary_untouched(conn) -> dict:
    """mart_price.price_summary_monthly 총계 + 최신 updated_at 확인.
    본 스크립트 실행 전후가 동일해야 '영향 없음'."""
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*), MAX(updated_at) FROM mart_price.price_summary_monthly")
        row = cur.fetchone()
    return {"count": row[0], "max_updated_at": row[1]}


# ── 메인 ─────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="mart_price.price_reference_monthly 배치 빌드 (전체 재생성)"
    )
    ap.add_argument("--pg",      required=True, help="PostgreSQL DSN")
    ap.add_argument("--dry-run", action="store_true", help="실행 없이 통계만 출력")
    args = ap.parse_args()

    if args.dry_run:
        print("=== DRY RUN 모드 ===")

    conn = psycopg2.connect(args.pg)
    try:
        before = check_summary_untouched(conn)
        print(f"\n[기존 price_summary_monthly] 총계={before['count']:,}건  "
              f"max(updated_at)={before['max_updated_at']}")

        result = build_mart(conn, args.dry_run)

        if not args.dry_run:
            v       = verify_mart(conn)
            verdict = print_verify(v)

            after = check_summary_untouched(conn)
            print(f"\n[기존 price_summary_monthly 재확인] 총계={after['count']:,}건  "
                  f"max(updated_at)={after['max_updated_at']}")
            untouched = (
                before["count"]           == after["count"] and
                before["max_updated_at"]  == after["max_updated_at"]
            )
            print(f"  영향 없음: {'예' if untouched else '아니오'}")

            if not untouched:
                verdict = WARN

            print(f"\n===== 최종 판정: {verdict} =====")

    finally:
        conn.close()
    print("\n완료")


if __name__ == "__main__":
    main()
