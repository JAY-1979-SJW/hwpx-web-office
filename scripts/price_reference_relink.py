"""
price_reference_relink.py
─────────────────────────
core_price.price_reference.item_code IS NULL 행을 item_alias 기준으로 재연결한다.
통제형: source_type='KPI' 필터 + pass2 unit 가드 + 오매핑 샘플 리포트.

매칭 순서 (kpi_reference_mapping_rules.json의 relink_strategy)
  pass 1 : (alias_name = item_name_raw, alias_spec = category, source='KPI')
           → KPI_REFERENCE 카탈로그 매칭. unit 가드 없음.
  pass 2 : (alias_name = item_name_raw, alias_spec IS NULL,  source='KPI')
           → 기존 KPI 지리 품목과 이름만 일치. unit_raw가 item_master의
             unit_master.unit_name과 일치(또는 양쪽 NULL)할 때만 허용.

특징
  - UPDATE 전용: item_code/item_name_std만 갱신
  - source_type='KPI' 필터: KPRC reference 행은 건드리지 않음
  - 멱등성: WHERE p.item_code IS NULL 필터로 재실행 안전
  - 오매핑 방지:
      * pass 1-2 모두 실패 시 NULL 유지
      * pass 2 unit 불일치 시 NULL 유지 (rejected 샘플 출력)
      * 이미 연결된 행 중 unit 불일치 의심 샘플 별도 출력

사용:
  python scripts/price_reference_relink.py --pg "host=... dbname=price_db user=..."
  python scripts/price_reference_relink.py --pg "..." --dry-run
"""

import argparse

import psycopg2


UPDATE_PASS1 = """
UPDATE core_price.price_reference p
SET    item_code     = m.item_code,
       item_name_std = m.item_name
FROM   core_price.item_alias a
JOIN   core_price.item_master m ON m.id = a.item_id
WHERE  p.item_code   IS NULL
  AND  p.source_type = 'KPI'
  AND  a.source      = 'KPI'
  AND  a.alias_name  = p.item_name_raw
  AND  a.alias_spec  = p.category
"""

UPDATE_PASS2_GUARDED = """
UPDATE core_price.price_reference p
SET    item_code     = m.item_code,
       item_name_std = m.item_name
FROM   core_price.item_alias a
JOIN   core_price.item_master m ON m.id = a.item_id
LEFT  JOIN core_price.unit_master u ON u.id = m.unit_id
WHERE  p.item_code   IS NULL
  AND  p.source_type = 'KPI'
  AND  a.source      = 'KPI'
  AND  a.alias_name  = p.item_name_raw
  AND  a.alias_spec  IS NULL
  AND  (
        (p.unit_raw IS NULL AND u.unit_name IS NULL)
        OR
        TRIM(u.unit_name) = TRIM(p.unit_raw)
       )
  AND  (
        SELECT COUNT(*)
        FROM   core_price.item_alias      a2
        JOIN   core_price.item_master     m2 ON m2.id = a2.item_id
        LEFT JOIN core_price.unit_master  u2 ON u2.id = m2.unit_id
        WHERE  a2.source     = 'KPI'
          AND  a2.alias_name = p.item_name_raw
          AND  a2.alias_spec IS NULL
          AND  (
                (p.unit_raw IS NULL AND u2.unit_name IS NULL)
                OR TRIM(u2.unit_name) = TRIM(p.unit_raw)
               )
       ) = 1
"""

# dry-run / 후보 집계
COUNT_PASS1 = """
SELECT COUNT(*)
FROM   core_price.price_reference p
JOIN   core_price.item_alias a
  ON   a.source='KPI' AND a.alias_name=p.item_name_raw AND a.alias_spec = p.category
WHERE  p.item_code IS NULL AND p.source_type='KPI'
"""

COUNT_PASS2_CANDIDATES = """
SELECT COUNT(*)
FROM   core_price.price_reference p
JOIN   core_price.item_alias a
  ON   a.source='KPI' AND a.alias_name=p.item_name_raw AND a.alias_spec IS NULL
WHERE  p.item_code IS NULL AND p.source_type='KPI'
  AND  NOT EXISTS (
        SELECT 1 FROM core_price.item_alias a1
        WHERE a1.source='KPI'
          AND a1.alias_name = p.item_name_raw
          AND a1.alias_spec = p.category
       )
"""

COUNT_PASS2_ACCEPTED = """
SELECT COUNT(*)
FROM   core_price.price_reference p
JOIN   core_price.item_alias a
  ON   a.source='KPI' AND a.alias_name=p.item_name_raw AND a.alias_spec IS NULL
JOIN   core_price.item_master m ON m.id=a.item_id
LEFT JOIN core_price.unit_master u ON u.id=m.unit_id
WHERE  p.item_code IS NULL AND p.source_type='KPI'
  AND  (
        (p.unit_raw IS NULL AND u.unit_name IS NULL)
        OR TRIM(u.unit_name) = TRIM(p.unit_raw)
       )
  AND  NOT EXISTS (
        SELECT 1 FROM core_price.item_alias a1
        WHERE a1.source='KPI'
          AND a1.alias_name = p.item_name_raw
          AND a1.alias_spec = p.category
       )
  AND  (
        SELECT COUNT(*)
        FROM   core_price.item_alias      a2
        JOIN   core_price.item_master     m2 ON m2.id = a2.item_id
        LEFT JOIN core_price.unit_master  u2 ON u2.id = m2.unit_id
        WHERE  a2.source='KPI'
          AND  a2.alias_name = p.item_name_raw
          AND  a2.alias_spec IS NULL
          AND  (
                (p.unit_raw IS NULL AND u2.unit_name IS NULL)
                OR TRIM(u2.unit_name) = TRIM(p.unit_raw)
               )
       ) = 1
"""

COUNT_PASS2_REJECTED = """
SELECT COUNT(*)
FROM   core_price.price_reference p
JOIN   core_price.item_alias a
  ON   a.source='KPI' AND a.alias_name=p.item_name_raw AND a.alias_spec IS NULL
JOIN   core_price.item_master m ON m.id=a.item_id
LEFT JOIN core_price.unit_master u ON u.id=m.unit_id
WHERE  p.item_code IS NULL AND p.source_type='KPI'
  AND  NOT (
        (p.unit_raw IS NULL AND u.unit_name IS NULL)
        OR TRIM(u.unit_name) = TRIM(p.unit_raw)
       )
  AND  NOT EXISTS (
        SELECT 1 FROM core_price.item_alias a1
        WHERE a1.source='KPI'
          AND a1.alias_name = p.item_name_raw
          AND a1.alias_spec = p.category
       )
"""

SAMPLE_PASS2_REJECTED = """
SELECT p.item_name_raw, p.category, p.unit_raw,
       m.item_code, m.item_name, u.unit_name AS master_unit,
       COUNT(*) AS row_cnt
FROM   core_price.price_reference p
JOIN   core_price.item_alias a
  ON   a.source='KPI' AND a.alias_name=p.item_name_raw AND a.alias_spec IS NULL
JOIN   core_price.item_master m ON m.id=a.item_id
LEFT JOIN core_price.unit_master u ON u.id=m.unit_id
WHERE  p.item_code IS NULL AND p.source_type='KPI'
  AND  NOT (
        (p.unit_raw IS NULL AND u.unit_name IS NULL)
        OR TRIM(u.unit_name) = TRIM(p.unit_raw)
       )
GROUP BY p.item_name_raw, p.category, p.unit_raw, m.item_code, m.item_name, u.unit_name
ORDER BY row_cnt DESC
LIMIT 10
"""

# 이미 연결된 행 중 unit_raw ↔ item_master unit 불일치 의심 샘플
SAMPLE_EXISTING_UNIT_MISMATCH = """
SELECT p.item_name_raw, p.category, p.unit_raw,
       m.item_code, m.item_name, u.unit_name AS master_unit, m.source,
       COUNT(*) AS row_cnt
FROM   core_price.price_reference p
JOIN   core_price.item_master m ON m.item_code = p.item_code
LEFT JOIN core_price.unit_master u ON u.id = m.unit_id
WHERE  p.item_code   IS NOT NULL
  AND  p.source_type = 'KPI'
  AND  p.unit_raw    IS NOT NULL
  AND  u.unit_name   IS NOT NULL
  AND  TRIM(u.unit_name) <> TRIM(p.unit_raw)
GROUP BY p.item_name_raw, p.category, p.unit_raw, m.item_code, m.item_name, u.unit_name, m.source
ORDER BY row_cnt DESC
LIMIT 10
"""


def snapshot(cur) -> dict:
    cur.execute("""
        SELECT COUNT(*) FROM core_price.price_reference WHERE source_type='KPI'
    """)
    total = cur.fetchone()[0]
    cur.execute("""
        SELECT COUNT(*) FROM core_price.price_reference
        WHERE source_type='KPI' AND item_code IS NULL
    """)
    null_cnt = cur.fetchone()[0]
    cur.execute("""
        SELECT COUNT(DISTINCT item_name_raw) FROM core_price.price_reference
        WHERE source_type='KPI' AND item_code IS NULL
    """)
    null_items = cur.fetchone()[0]
    return {"total": total, "null": null_cnt, "null_items": null_items}


def kpi_reference_master_count(cur) -> int:
    cur.execute("SELECT COUNT(*) FROM core_price.item_master WHERE source='KPI_REFERENCE'")
    return cur.fetchone()[0]


def print_samples(cur):
    print("\n  [4-a] pass2 unit 가드 기각 샘플 (자동 연결 보류 → unresolved)")
    cur.execute(SAMPLE_PASS2_REJECTED)
    rows = cur.fetchall()
    if not rows:
        print("    (해당 없음)")
    else:
        print(f"    {'item_name_raw':<24s} {'category':<14s} {'unit_raw':<10s} "
              f"{'→ master_unit':<14s} {'item_code':<12s} cnt")
        for r in rows:
            name, cat, u_raw, code, mname, mu, cnt = r
            print(f"    {str(name)[:24]:<24s} {str(cat)[:14]:<14s} "
                  f"{str(u_raw)[:10]:<10s} {str(mu)[:14]:<14s} "
                  f"{str(code)[:12]:<12s} {cnt:,}")

    print("\n  [4-b] 기존 연결 중 unit 불일치 의심 샘플 (수동 재검토 권장)")
    cur.execute(SAMPLE_EXISTING_UNIT_MISMATCH)
    rows = cur.fetchall()
    if not rows:
        print("    (해당 없음)")
    else:
        print(f"    {'item_name_raw':<24s} {'unit_raw':<10s} "
              f"{'master_unit':<12s} {'src':<14s} {'item_code':<12s} cnt")
        for r in rows:
            name, cat, u_raw, code, mname, mu, src, cnt = r
            print(f"    {str(name)[:24]:<24s} {str(u_raw)[:10]:<10s} "
                  f"{str(mu)[:12]:<12s} {str(src)[:14]:<14s} "
                  f"{str(code)[:12]:<12s} {cnt:,}")


def verdict_from_ratio(pct: float) -> str:
    if pct <= 10:
        return "PASS (stretch 목표 달성)"
    if pct <= 15:
        return "PASS (최소 목표 달성)"
    if pct <= 50:
        return "WARN (부분 개선, 목표 미달)"
    return "FAIL (개선 불충분)"


def main():
    ap = argparse.ArgumentParser(description="price_reference.item_code 재연결 (통제형)")
    ap.add_argument("--pg",      required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    conn = psycopg2.connect(args.pg)
    try:
        with conn.cursor() as cur:
            before = snapshot(cur)
            ref_master_before = kpi_reference_master_count(cur)

        print("\n=== price_reference_relink (통제형) ===")
        print(f"  [전] source_type=KPI 총 {before['total']:,}건, "
              f"NULL {before['null']:,}건 "
              f"({before['null']/before['total']*100 if before['total'] else 0:.2f}%, "
              f"미해소 품목 {before['null_items']:,})")
        print(f"  [전] KPI_REFERENCE 전용 품목: {ref_master_before:,}")

        if args.dry_run:
            with conn.cursor() as cur:
                cur.execute(COUNT_PASS1)
                p1 = cur.fetchone()[0]
                cur.execute(COUNT_PASS2_CANDIDATES)
                p2_cand = cur.fetchone()[0]
                cur.execute(COUNT_PASS2_ACCEPTED)
                p2_ok = cur.fetchone()[0]
                cur.execute(COUNT_PASS2_REJECTED)
                p2_rej = cur.fetchone()[0]
            print(f"\n  [dry] pass1 예상 매칭:           {p1:,}")
            print(f"  [dry] pass2 후보:                {p2_cand:,}")
            print(f"  [dry]   - unit 가드 통과:        {p2_ok:,}")
            print(f"  [dry]   - unit 가드 기각:        {p2_rej:,}")

            with conn.cursor() as cur:
                print_samples(cur)

            projected_null = before["null"] - p1 - p2_ok
            projected_pct = projected_null / before["total"] * 100 if before["total"] else 0
            print(f"\n  [dry] 예상 후 NULL: {projected_null:,} ({projected_pct:.2f}%)  "
                  f"→ {verdict_from_ratio(projected_pct)}")
            return

        # pass 1
        with conn.cursor() as cur:
            cur.execute(UPDATE_PASS1)
            updated1 = cur.rowcount
        conn.commit()
        print(f"\n  [pass1] (name, category) 매칭 업데이트:       {updated1:,}건")

        # pass 2 (unit-guarded)
        with conn.cursor() as cur:
            cur.execute(UPDATE_PASS2_GUARDED)
            updated2 = cur.rowcount
        conn.commit()
        print(f"  [pass2] (name, NULL) + unit 가드 업데이트:   {updated2:,}건")

        with conn.cursor() as cur:
            after = snapshot(cur)
            ref_master_after = kpi_reference_master_count(cur)
            cur.execute(COUNT_PASS2_REJECTED)
            remaining_rejected = cur.fetchone()[0]

        reduced = before["null"] - after["null"]
        null_pct_before = before["null"] / before["total"] * 100 if before["total"] else 0
        null_pct_after  = after["null"]  / after["total"]  * 100 if after["total"]  else 0

        # 최종 보고
        print("\n  === RELINK 최종 요약 ===")
        print(f"  [3] NULL 비율 개선")
        print(f"        전:  {before['null']:,} / {before['total']:,}  ({null_pct_before:.2f}%)")
        print(f"        후:  {after['null']:,} / {after['total']:,}  ({null_pct_after:.2f}%)")
        print(f"        개선: {reduced:,}건 "
              f"({(null_pct_before - null_pct_after):.2f}%p)")
        print(f"        판정: {verdict_from_ratio(null_pct_after)}")

        print(f"\n  [5] KPI_REFERENCE 전용 품목:    {ref_master_after:,}")
        print(f"  [잔여] unit 가드 기각(unresolved): {remaining_rejected:,}")

        with conn.cursor() as cur:
            print_samples(cur)

        print("\n  ※ BOOST 보고의 [1] 신규 item_master 생성 건수, "
              "[2] fragment 제외 건수는 boost 스크립트 실행 시 출력된다.")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
