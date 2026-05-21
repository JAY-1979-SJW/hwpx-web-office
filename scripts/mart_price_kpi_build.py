"""
mart_price_kpi_build.py  --  G2B 조달단가 월별 KPI 빌드 (운영 기준선)

방식:
  TEMP TABLE 분리 실행. 각 단계를 물리화(materialization)하여 mart 테이블
  반복 스캔을 차단. 각 단계에 ANALYZE + 인덱스 추가로 최종 JOIN 최적화.
  (단일 대형 CTE 방식은 PG12+ CTE 인라인화로 인해 사용 금지.)

단계:
  1. _kpi_item_bounds    — 아이템별 IQR 경계 + 구 섹션×월 IQR
  2. _kpi_flagged        — 이중 이상치 플래그 + valid_obs_count
  3. _kpi_norm_stats     — normalized → 월별 median / stddev
  4. _kpi_rolling        — clean 행 기준 rolling 3m/6m
  5. 최종 INSERT (TRUNCATE + JOIN 4 TEMP)

실행:
  python3 mart_price_kpi_build.py --env-file /home/ubuntu/app/g2b/.env.g2b
  python3 mart_price_kpi_build.py --env-file ... --dry-run

exit code:
  0  PASS   — 빌드 성공 + mart=kpi rowcount 일치
  1  WARN   — 빌드 성공했으나 rowcount 불일치 (재검증 필요)
  2  FAIL   — 예외/연결 실패/rowcount=0
"""

import argparse, os, sys, time
from datetime import datetime

try:
    import psycopg2
except ImportError:
    print("[ERROR] psycopg2 없음: pip install psycopg2-binary", file=sys.stderr)
    sys.exit(1)

# ── 상수 ─────────────────────────────────────────────────────────────────────

INCLUDE_SECTIONS = [
    "FCLTY_MTR_BILDNG",
    "FCLTY_MTR_ENGRK",
    "FCLTY_MTR_MCHN",
    "FCLTY_MTR_ELCTY",
    "NET_RESOURCE",
]

ITEM_LEVEL_MIN_OBS  = 3
FALLBACK_LOWER_PCT  = 0.02
FALLBACK_UPPER_PCT  = 0.98
GRADE_A_MIN_VALID   = 3
GRADE_B_MIN_VALID   = 2
GRADE_C_MIN_VALID   = 1


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
        host=os.environ.get("G2B_PG_HOST")      or os.environ.get("DB_HOST"),
        dbname=os.environ.get("G2B_PG_DB")      or os.environ.get("DB_NAME"),
        user=os.environ.get("G2B_PG_USER")      or os.environ.get("DB_USER"),
        password=os.environ.get("G2B_PG_PASSWORD") or os.environ.get("DB_PASSWORD"),
        port=int(os.environ.get("G2B_PG_PORT")  or os.environ.get("DB_PORT", 5432)),
        connect_timeout=10,
    )


def log(msg: str):
    """[KPI BUILD] 접두사 고정 출력."""
    print(f"[KPI BUILD] {msg}", flush=True)


def run_step(cur, label: str, sql: str, params=None):
    t0 = time.time()
    cur.execute(sql, params)
    elapsed = time.time() - t0
    rowcount = cur.rowcount if cur.rowcount >= 0 else None
    cnt_msg = f"rows={rowcount:,}" if rowcount is not None else "rows=-"
    print(f"[KPI BUILD]   step={label:<28} elapsed={elapsed:>6.2f}s  {cnt_msg}", flush=True)
    return elapsed, rowcount


# ── 단계 1: 아이템별 IQR 경계 + 구 섹션×월 IQR ──────────────────────────────

STEP1_SQL = """
-- 1a. 아이템 자체 IQR (obs >= ITEM_LEVEL_MIN_OBS)
CREATE TEMP TABLE _kpi_item_stats AS
SELECT source_system, section_code, item_code, supply_region,
       COUNT(*)                                                     AS obs_count,
       PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY primary_price)  AS q1,
       PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY primary_price)  AS q3
FROM mart_price.procurement_price_monthly
WHERE section_code = ANY(%(sections)s) AND primary_price IS NOT NULL
GROUP BY source_system, section_code, item_code, supply_region;

CREATE INDEX ON _kpi_item_stats (section_code, item_code, supply_region);
ANALYZE _kpi_item_stats;

-- 1b. 섹션 전체 P2/P98 (단일 포인트 fallback)
CREATE TEMP TABLE _kpi_section_fallback AS
SELECT section_code,
       PERCENTILE_CONT(%(fallback_lower)s) WITHIN GROUP (ORDER BY primary_price) AS p_lower,
       PERCENTILE_CONT(%(fallback_upper)s) WITHIN GROUP (ORDER BY primary_price) AS p_upper
FROM mart_price.procurement_price_monthly
WHERE section_code = ANY(%(sections)s) AND primary_price IS NOT NULL
GROUP BY section_code;

ANALYZE _kpi_section_fallback;

-- 1c. 섹션×월 IQR (구 이상치, 비교용)
CREATE TEMP TABLE _kpi_section_month_iqr AS
SELECT source_system, section_code, year, month,
       PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY primary_price) AS q1,
       PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY primary_price) AS q3
FROM mart_price.procurement_price_monthly
WHERE section_code = ANY(%(sections)s) AND primary_price IS NOT NULL
GROUP BY source_system, section_code, year, month;

CREATE INDEX ON _kpi_section_month_iqr (source_system, section_code, year, month);
ANALYZE _kpi_section_month_iqr;

-- 1d. 아이템 최종 경계 (IQR or fallback)
CREATE TEMP TABLE _kpi_item_bounds AS
SELECT h.source_system, h.section_code, h.item_code, h.supply_region,
       h.obs_count,
       CASE WHEN h.obs_count >= %(item_min_obs)s
            THEN GREATEST(0, h.q1 - 1.5*(h.q3 - h.q1))
            ELSE f.p_lower END AS lower_bound,
       CASE WHEN h.obs_count >= %(item_min_obs)s
            THEN h.q3 + 1.5*(h.q3 - h.q1)
            ELSE f.p_upper END AS upper_bound
FROM _kpi_item_stats h
JOIN _kpi_section_fallback f ON h.section_code = f.section_code;

CREATE INDEX ON _kpi_item_bounds (source_system, section_code, item_code, supply_region);
ANALYZE _kpi_item_bounds;
"""

# ── 단계 2: 이중 이상치 플래그 + valid_obs_count ─────────────────────────────

STEP2_SQL = """
-- 2a. 이중 플래그 부착
CREATE TEMP TABLE _kpi_flagged AS
SELECT m.*,
       CASE WHEN m.primary_price IS NULL                              THEN FALSE
            WHEN m.primary_price < smb.q1 - 1.5*(smb.q3 - smb.q1)  THEN TRUE
            WHEN m.primary_price > smb.q3 + 1.5*(smb.q3 - smb.q1)  THEN TRUE
            ELSE FALSE END AS is_outlier_old,
       CASE WHEN m.primary_price IS NULL          THEN TRUE
            WHEN m.primary_price < ib.lower_bound THEN TRUE
            WHEN m.primary_price > ib.upper_bound THEN TRUE
            ELSE FALSE END AS is_outlier_item
FROM mart_price.procurement_price_monthly m
JOIN _kpi_section_month_iqr smb
  ON  m.source_system = smb.source_system AND m.section_code = smb.section_code
  AND m.year = smb.year AND m.month = smb.month
JOIN _kpi_item_bounds ib
  ON  m.source_system = ib.source_system AND m.section_code = ib.section_code
  AND m.item_code = ib.item_code AND m.supply_region = ib.supply_region
WHERE m.section_code = ANY(%(sections)s);

CREATE INDEX ON _kpi_flagged (source_system, section_code, item_code, supply_region, year, month);
CREATE INDEX ON _kpi_flagged (section_code, item_code, supply_region) WHERE NOT is_outlier_item;
ANALYZE _kpi_flagged;

-- 2b. 아이템별 valid_obs_count (신 플래그 기준)
CREATE TEMP TABLE _kpi_valid_counts AS
SELECT source_system, section_code, item_code, supply_region,
       COUNT(*)                                     AS obs_count,
       COUNT(*) FILTER (WHERE NOT is_outlier_item)  AS valid_obs_count
FROM _kpi_flagged
GROUP BY source_system, section_code, item_code, supply_region;

CREATE INDEX ON _kpi_valid_counts (source_system, section_code, item_code, supply_region);
ANALYZE _kpi_valid_counts;
"""

# ── 단계 3: normalized → 월별 median / stddev ─────────────────────────────────

STEP3_SQL = """
CREATE TEMP TABLE _kpi_norm_stats AS
SELECT section_code, item_code, supply_region,
       EXTRACT(YEAR  FROM notice_date)::SMALLINT AS year,
       EXTRACT(MONTH FROM notice_date)::SMALLINT AS month,
       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price_value)::BIGINT AS median_price,
       STDDEV_POP(price_value)::BIGINT AS stddev_price
FROM staging_price.g2b_price_normalized
WHERE section_code = ANY(%(sections)s) AND price_value IS NOT NULL
GROUP BY section_code, item_code, supply_region,
         EXTRACT(YEAR FROM notice_date), EXTRACT(MONTH FROM notice_date);

CREATE INDEX ON _kpi_norm_stats (section_code, item_code, supply_region, year, month);
ANALYZE _kpi_norm_stats;
"""

# ── 단계 4: clean 행 기준 rolling 3m / 6m ─────────────────────────────────────

STEP4_SQL = """
CREATE TEMP TABLE _kpi_rolling AS
SELECT source_system, section_code, item_code, supply_region, year, month,
       primary_price AS latest_price,
       LAG(primary_price) OVER w AS prev_price,
       AVG(primary_price) OVER (
           PARTITION BY source_system, section_code, item_code, supply_region
           ORDER BY year, month
           ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
       )::BIGINT AS recent_3m_avg,
       AVG(primary_price) OVER (
           PARTITION BY source_system, section_code, item_code, supply_region
           ORDER BY year, month
           ROWS BETWEEN 5 PRECEDING AND CURRENT ROW
       )::BIGINT AS recent_6m_avg
FROM _kpi_flagged
WHERE NOT is_outlier_item AND primary_price IS NOT NULL
WINDOW w AS (
    PARTITION BY source_system, section_code, item_code, supply_region
    ORDER BY year, month
);

CREATE INDEX ON _kpi_rolling (source_system, section_code, item_code, supply_region, year, month);
ANALYZE _kpi_rolling;
"""

# ── 단계 5: 최종 INSERT ────────────────────────────────────────────────────────

STEP5_TRUNCATE = "TRUNCATE mart_price.procurement_price_kpi_monthly"

STEP5_INSERT = """
INSERT INTO mart_price.procurement_price_kpi_monthly (
    source_system, section_code, item_code, supply_region, year, month,
    avg_price, median_price, min_price, max_price, stddev_price,
    recent_3m_avg, recent_6m_avg, latest_price, price_mom_change,
    is_outlier,
    is_outlier_item,
    obs_count, valid_obs_count, outlier_excluded_count,
    confidence_grade,
    updated_at
)
SELECT
    f.source_system, f.section_code, f.item_code, f.supply_region, f.year, f.month,
    f.avg_price,
    COALESCE(ns.median_price, f.avg_price),
    f.min_price,
    f.max_price,
    ns.stddev_price,
    r.recent_3m_avg,
    r.recent_6m_avg,
    COALESCE(r.latest_price, f.primary_price),
    CASE WHEN r.prev_price IS NOT NULL AND r.prev_price > 0
         THEN ROUND(
             ((COALESCE(r.latest_price, f.primary_price) - r.prev_price)::NUMERIC / r.prev_price) * 100,
             2)
         ELSE NULL END,
    f.is_outlier_old,
    f.is_outlier_item,
    vc.obs_count,
    vc.valid_obs_count,
    vc.obs_count - vc.valid_obs_count,
    CASE
        WHEN f.is_outlier_item                    THEN 'D'
        WHEN vc.valid_obs_count >= %(grade_a)s    THEN 'A'
        WHEN vc.valid_obs_count >= %(grade_b)s    THEN 'B'
        WHEN vc.valid_obs_count >= %(grade_c)s    THEN 'C'
        ELSE                                           'D'
    END,
    NOW()
FROM _kpi_flagged f
JOIN _kpi_valid_counts vc
  ON  f.source_system = vc.source_system AND f.section_code = vc.section_code
  AND f.item_code = vc.item_code AND f.supply_region = vc.supply_region
LEFT JOIN _kpi_norm_stats ns
  ON  f.section_code = ns.section_code AND f.item_code = ns.item_code
  AND f.supply_region = ns.supply_region AND f.year = ns.year AND f.month = ns.month
LEFT JOIN _kpi_rolling r
  ON  f.source_system = r.source_system AND f.section_code = r.section_code
  AND f.item_code = r.item_code AND f.supply_region = r.supply_region
  AND f.year = r.year AND f.month = r.month
ON CONFLICT (source_system, section_code, item_code, year, month, supply_region)
DO UPDATE SET
    avg_price               = EXCLUDED.avg_price,
    median_price            = EXCLUDED.median_price,
    min_price               = EXCLUDED.min_price,
    max_price               = EXCLUDED.max_price,
    stddev_price            = EXCLUDED.stddev_price,
    recent_3m_avg           = EXCLUDED.recent_3m_avg,
    recent_6m_avg           = EXCLUDED.recent_6m_avg,
    latest_price            = EXCLUDED.latest_price,
    price_mom_change        = EXCLUDED.price_mom_change,
    is_outlier              = EXCLUDED.is_outlier,
    is_outlier_item         = EXCLUDED.is_outlier_item,
    obs_count               = EXCLUDED.obs_count,
    valid_obs_count         = EXCLUDED.valid_obs_count,
    outlier_excluded_count  = EXCLUDED.outlier_excluded_count,
    confidence_grade        = EXCLUDED.confidence_grade,
    updated_at              = NOW()
"""

STEP5_CLEANUP = """
DROP TABLE IF EXISTS _kpi_item_stats, _kpi_section_fallback,
    _kpi_section_month_iqr, _kpi_item_bounds,
    _kpi_flagged, _kpi_valid_counts,
    _kpi_norm_stats, _kpi_rolling;
"""


# ── 검증 쿼리 ─────────────────────────────────────────────────────────────────

VALIDATE_OUTLIER_SQL = """
SELECT section_code,
       COUNT(*)                                                          AS total,
       COUNT(*) FILTER (WHERE is_outlier)                               AS old_outlier,
       ROUND(COUNT(*) FILTER (WHERE is_outlier)::NUMERIC/COUNT(*)*100,1) AS old_pct,
       COUNT(*) FILTER (WHERE is_outlier_item)                          AS new_outlier,
       ROUND(COUNT(*) FILTER (WHERE is_outlier_item)::NUMERIC/COUNT(*)*100,1) AS new_pct,
       COUNT(*) FILTER (WHERE is_outlier AND NOT is_outlier_item)       AS false_pos_reduced
FROM mart_price.procurement_price_kpi_monthly
WHERE section_code = ANY(%s)
GROUP BY section_code ORDER BY section_code
"""

VALIDATE_GRADE_SQL = """
SELECT section_code, confidence_grade,
       COUNT(*) AS cnt,
       ROUND(COUNT(*)::NUMERIC/SUM(COUNT(*)) OVER (PARTITION BY section_code)*100,1) AS pct
FROM mart_price.procurement_price_kpi_monthly
WHERE section_code = ANY(%s)
GROUP BY section_code, confidence_grade
ORDER BY section_code, confidence_grade
"""

VALIDATE_FP_SQL = """
SELECT item_code, year, month, supply_region, latest_price,
       is_outlier AS old_flag, is_outlier_item AS new_flag,
       confidence_grade, obs_count, valid_obs_count
FROM mart_price.procurement_price_kpi_monthly
WHERE section_code = 'FCLTY_MTR_BILDNG' AND item_code = '23075579'
ORDER BY year, month, supply_region
"""

VALIDATE_SPOT_SQL = """
SELECT year, month, supply_region, latest_price, median_price,
       recent_3m_avg, recent_6m_avg, price_mom_change,
       is_outlier AS old_flag, is_outlier_item AS new_flag,
       confidence_grade, obs_count, valid_obs_count
FROM mart_price.procurement_price_kpi_monthly
WHERE section_code = 'FCLTY_MTR_BILDNG' AND item_code = '10023392'
ORDER BY year, month, supply_region
"""


# ── 빌드 ─────────────────────────────────────────────────────────────────────

def run_build(pg, dry_run: bool = False):
    params = {
        "sections":       INCLUDE_SECTIONS,
        "fallback_lower": FALLBACK_LOWER_PCT,
        "fallback_upper": FALLBACK_UPPER_PCT,
        "item_min_obs":   ITEM_LEVEL_MIN_OBS,
        "grade_a":        GRADE_A_MIN_VALID,
        "grade_b":        GRADE_B_MIN_VALID,
        "grade_c":        GRADE_C_MIN_VALID,
    }

    total_start = time.time()
    cur = pg.cursor()

    if dry_run:
        log("DRY-RUN: 단계 1 SELECT-only 실행계획 확인")
        run_step(cur, "1a item_stats(probe)", """
            SELECT COUNT(*) FROM (
                SELECT section_code, item_code, supply_region, COUNT(*) AS obs_count,
                       PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY primary_price) AS q1,
                       PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY primary_price) AS q3
                FROM mart_price.procurement_price_monthly
                WHERE section_code = ANY(%(sections)s) AND primary_price IS NOT NULL
                GROUP BY section_code, item_code, supply_region
            ) t
        """, params)
        run_step(cur, "1b section_fallback(probe)", """
            SELECT COUNT(*) FROM (
                SELECT section_code,
                       PERCENTILE_CONT(%(fallback_lower)s) WITHIN GROUP (ORDER BY primary_price) AS p_lower,
                       PERCENTILE_CONT(%(fallback_upper)s) WITHIN GROUP (ORDER BY primary_price) AS p_upper
                FROM mart_price.procurement_price_monthly
                WHERE section_code = ANY(%(sections)s) AND primary_price IS NOT NULL
                GROUP BY section_code
            ) t
        """, params)
        run_step(cur, "1c section_month(probe)", """
            SELECT COUNT(*) FROM (
                SELECT section_code, year, month,
                       PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY primary_price) AS q1,
                       PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY primary_price) AS q3
                FROM mart_price.procurement_price_monthly
                WHERE section_code = ANY(%(sections)s) AND primary_price IS NOT NULL
                GROUP BY section_code, year, month
            ) t
        """, params)
        log("DRY-RUN 종료 — 실제 빌드는 --dry-run 제거")
        pg.rollback()
        cur.close()
        return None

    log("STEP 1 — 아이템 IQR 경계 계산")
    run_step(cur, "1 item_bounds", STEP1_SQL, params)
    pg.commit()

    log("STEP 2 — 이중 이상치 플래그 + valid_obs_count")
    run_step(cur, "2 flagged+valid", STEP2_SQL, params)
    pg.commit()

    log("STEP 3 — normalized → median/stddev")
    run_step(cur, "3 norm_stats", STEP3_SQL, params)
    pg.commit()

    log("STEP 4 — rolling 3m/6m")
    run_step(cur, "4 rolling", STEP4_SQL, params)
    pg.commit()

    log("STEP 5 — 최종 INSERT")
    cur.execute(STEP5_TRUNCATE)
    _, inserted = run_step(cur, "5 INSERT", STEP5_INSERT, params)
    pg.commit()

    cur.execute(STEP5_CLEANUP)
    pg.commit()

    total_elapsed = time.time() - total_start
    log(f"BUILD 완료  rows={inserted:,}  total_elapsed={total_elapsed:.2f}s")
    cur.close()
    return inserted


# ── 검증 ─────────────────────────────────────────────────────────────────────

def validate(pg):
    """검증 결과를 dict로 반환 — 호출측에서 verdict 판정에 사용."""
    with pg.cursor() as cur:
        cur.execute(VALIDATE_OUTLIER_SQL, (INCLUDE_SECTIONS,))
        outlier_rows = cur.fetchall()
        cur.execute(VALIDATE_GRADE_SQL, (INCLUDE_SECTIONS,))
        grade_rows = cur.fetchall()
        cur.execute(VALIDATE_FP_SQL)
        fp_rows = cur.fetchall()
        cur.execute(VALIDATE_SPOT_SQL)
        spot_rows = cur.fetchall()
        cur.execute("SELECT COUNT(*) FROM mart_price.procurement_price_monthly WHERE section_code=ANY(%s)",
                    (INCLUDE_SECTIONS,))
        mart_cnt = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM mart_price.procurement_price_kpi_monthly")
        kpi_cnt = cur.fetchone()[0]

    log("VALIDATE — 구/신 이상치 비율 비교")
    print(f"[KPI BUILD]   {'section':<22} {'total':>7} {'old%':>6} {'new%':>6} {'fp_reduced':>11}", flush=True)
    g_t = g_o = g_n = g_fp = 0
    for r in outlier_rows:
        sc, tot, old_o, _old_p, new_o, _new_p, fp = r
        old_p = round(old_o / tot * 100, 1) if tot else 0
        new_p = round(new_o / tot * 100, 1) if tot else 0
        print(f"[KPI BUILD]   {sc:<22} {tot:>7,} {old_p:>5.1f}% {new_p:>5.1f}% {fp:>11,}", flush=True)
        g_t += tot; g_o += old_o; g_n += new_o; g_fp += fp
    sum_old = round(g_o / g_t * 100, 1) if g_t else 0
    sum_new = round(g_n / g_t * 100, 1) if g_t else 0
    print(f"[KPI BUILD]   {'TOTAL':<22} {g_t:>7,} {sum_old:>5.1f}% {sum_new:>5.1f}% {g_fp:>11,}", flush=True)

    log("VALIDATE — confidence_grade 분포")
    prev = None
    for r in grade_rows:
        sc, grade, cnt, pct = r
        if sc != prev:
            print(f"[KPI BUILD]   [{sc}]", flush=True)
            prev = sc
        print(f"[KPI BUILD]     {grade}: {cnt:>7,} ({float(pct):>5.1f}%)", flush=True)

    rowcount_match = (mart_cnt == kpi_cnt)
    match_msg = "OK" if rowcount_match else f"MISMATCH (mart={mart_cnt:,} kpi={kpi_cnt:,})"
    log(f"VALIDATE — mart_rowcount={mart_cnt:,} kpi_rowcount={kpi_cnt:,} match={match_msg}")

    log("VALIDATE — 오탐 개선 sample (item=23075579 건설자재 고가)")
    if fp_rows:
        print(f"[KPI BUILD]   {'YM':<8} {'region':<8} {'price':>12} {'old':>4} {'new':>4} grade", flush=True)
        for r in fp_rows:
            _ic, yr, mo, reg, lp, old_f, new_f, grade, _obs, _valid = r
            reg_d = (reg or '전국')[:8]
            print(f"[KPI BUILD]   {yr}-{mo:02d}   {reg_d:<8} {lp:>12,} {'T' if old_f else 'F':>4} {'T' if new_f else 'F':>4} {grade}", flush=True)

    log("VALIDATE — spot check (item=10023392 육각볼트 M6*20)")
    if spot_rows:
        print(f"[KPI BUILD]   {'YM':<8} {'reg':<6} {'latest':>10} {'3m_avg':>10} {'mom%':>7} {'old':>4} {'new':>4} grade", flush=True)
        for r in spot_rows:
            yr, mo, reg, lp, _med, r3, _r6, mom, old_f, new_f, grade, _obs, _valid = r
            reg_d = (reg or '전국')[:6]
            mom_s = f"{float(mom):+.2f}" if mom else "  N/A"
            print(f"[KPI BUILD]   {yr}-{mo:02d}   {reg_d:<6} {lp:>10,} {(r3 or 0):>10,} {mom_s:>7} {'T' if old_f else 'F':>4} {'T' if new_f else 'F':>4} {grade}", flush=True)

    return {
        "mart_cnt":      mart_cnt,
        "kpi_cnt":       kpi_cnt,
        "rowcount_match": rowcount_match,
        "outlier_pct_old": sum_old,
        "outlier_pct_new": sum_new,
    }


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="G2B 조달단가 월별 KPI 빌드 (운영 기준선)")
    ap.add_argument("--env-file", default="")
    ap.add_argument("--dry-run",  action="store_true")
    args = ap.parse_args()

    if args.env_file:
        load_env_file(args.env_file)

    started_at = datetime.now()
    log(f"start  ts={started_at.strftime('%Y-%m-%dT%H:%M:%S')}  mode={'dry-run' if args.dry_run else 'build'}")
    log(f"params  outlier=item_IQR(obs>={ITEM_LEVEL_MIN_OBS}) fallback=P{int(FALLBACK_LOWER_PCT*100)}/P{int(FALLBACK_UPPER_PCT*100)}  grade A>={GRADE_A_MIN_VALID} B>={GRADE_B_MIN_VALID} C>={GRADE_C_MIN_VALID}")
    log(f"sections={','.join(INCLUDE_SECTIONS)}")

    try:
        pg = pg_connect()
    except Exception as e:
        log(f"FATAL  pg_connect failed: {e}")
        log("verdict=FAIL  reason=pg_connect_failed")
        sys.exit(2)

    exit_code = 0
    try:
        inserted = run_build(pg, dry_run=args.dry_run)
        if args.dry_run:
            log("verdict=PASS(dry-run)")
            return

        if not inserted or inserted <= 0:
            log(f"verdict=FAIL  reason=zero_rows  inserted={inserted}")
            exit_code = 2
            return

        result = validate(pg)
        total_elapsed = (datetime.now() - started_at).total_seconds()

        if result["rowcount_match"]:
            verdict, exit_code = "PASS", 0
        else:
            verdict, exit_code = "WARN", 1

        log("=" * 60)
        log(f"summary  inserted={inserted:,}  mart={result['mart_cnt']:,}  kpi={result['kpi_cnt']:,}  rowcount_match={result['rowcount_match']}")
        log(f"summary  outlier_pct old={result['outlier_pct_old']}%  new={result['outlier_pct_new']}%")
        log(f"summary  total_elapsed={total_elapsed:.2f}s")
        log(f"verdict={verdict}  exit_code={exit_code}")
    except Exception as e:
        log(f"FATAL  exception: {type(e).__name__}: {e}")
        log("verdict=FAIL  reason=exception")
        exit_code = 2
        try:
            pg.rollback()
        except Exception:
            pass
    finally:
        try:
            pg.close()
        except Exception:
            pass
        sys.exit(exit_code)


if __name__ == "__main__":
    main()
