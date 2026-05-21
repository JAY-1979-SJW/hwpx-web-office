"""
price_db_migrate_reference.py  --  KPI 비지리 행 → core_price.price_reference

처리 흐름:
  staging_price.kpi_prices_raw WHERE 지역 IN (기준①②③, 기준가, 단가)
  → core_price.price_reference

  - item_master / item_alias 매핑 재사용 (기존 KPI alias 조회)
  - standardization_rules.json 단위 표준화 재사용
  - 미해소 항목은 item_code=NULL 로 적재 + unresolved 목록 출력
  - 멱등성: ON CONFLICT (source_type, source_file_id, item_name_raw,
                          reference_type, price_year, price_month) DO NOTHING

사전 조건:
  - price_db_schema_patch_v2.sql 실행 완료 (price_reference 테이블 존재)
  - price_db_migrate_core.py 실행 완료 (item_master / item_alias 존재)

사용:
  python price_db_migrate_reference.py --pg "host=... dbname=price_db user=..."
  python price_db_migrate_reference.py --pg "..." --dry-run
  python price_db_migrate_reference.py --pg "..." --analyze   # 구조 분석만 출력
"""

import argparse
import json
from pathlib import Path

import psycopg2
import psycopg2.extras

DEFAULT_RULES = Path(__file__).parent.parent / "db" / "standardization_rules.json"

PASS = "PASS"
WARN = "WARN"
FAIL = "FAIL"


# ── 규칙 로드 ────────────────────────────────────────────────

def load_rules(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# ── 1단계: 비지리 행 구조 분석 ──────────────────────────────

def analyze_non_geo(conn, non_geo: list) -> dict:
    """staging_price.kpi_prices_raw 비지리 행 분포 분석."""
    report = {}

    with conn.cursor() as cur:
        # 전체 건수
        cur.execute("""
            SELECT COUNT(*) FROM staging_price.kpi_prices_raw
            WHERE 지역 = ANY(%s) AND 가격 IS NOT NULL
        """, (non_geo,))
        report["total_rows"] = cur.fetchone()[0]

        # reference_type 분포
        cur.execute("""
            SELECT 지역 AS reference_type, COUNT(*) AS cnt
            FROM staging_price.kpi_prices_raw
            WHERE 지역 = ANY(%s) AND 가격 IS NOT NULL
            GROUP BY 지역
            ORDER BY cnt DESC
        """, (non_geo,))
        report["by_reference_type"] = cur.fetchall()

        # 상위 품목
        cur.execute("""
            SELECT 품목명, COUNT(*) AS cnt
            FROM staging_price.kpi_prices_raw
            WHERE 지역 = ANY(%s) AND 가격 IS NOT NULL
            GROUP BY 품목명
            ORDER BY cnt DESC
            LIMIT 20
        """, (non_geo,))
        report["top_items"] = cur.fetchall()

        # 상위 단위
        cur.execute("""
            SELECT 단위, COUNT(*) AS cnt
            FROM staging_price.kpi_prices_raw
            WHERE 지역 = ANY(%s) AND 가격 IS NOT NULL
            GROUP BY 단위
            ORDER BY cnt DESC
            LIMIT 15
        """, (non_geo,))
        report["top_units"] = cur.fetchall()

        # source_file 분포
        cur.execute("""
            SELECT f.file_name, COUNT(*) AS cnt
            FROM staging_price.kpi_prices_raw r
            JOIN raw_ingest.files f ON f.id = r.file_id
            WHERE r.지역 = ANY(%s) AND r.가격 IS NOT NULL
            GROUP BY f.file_name
            ORDER BY cnt DESC
            LIMIT 10
        """, (non_geo,))
        report["top_files"] = cur.fetchall()

        # 연도 분포
        cur.execute("""
            SELECT 연도, COUNT(*) AS cnt
            FROM staging_price.kpi_prices_raw
            WHERE 지역 = ANY(%s) AND 가격 IS NOT NULL
            GROUP BY 연도
            ORDER BY 연도
        """, (non_geo,))
        report["by_year"] = cur.fetchall()

    return report


def print_analysis(report: dict) -> str:
    lines = []
    lines.append("\n=== [1단계] KPI 비지리 행 구조 분석 ===")
    total = report["total_rows"]
    lines.append(f"  총 비지리 행 수: {total:,}건")

    lines.append("\n  [reference_type 분포]")
    for ref_type, cnt in report["by_reference_type"]:
        lines.append(f"    {ref_type}: {cnt:,}건")

    lines.append("\n  [연도 분포]")
    for year, cnt in report["by_year"]:
        lines.append(f"    {year}: {cnt:,}건")

    lines.append("\n  [상위 품목 (Top 20)]")
    for item, cnt in report["top_items"]:
        lines.append(f"    {item}: {cnt:,}건")

    lines.append("\n  [상위 단위 (Top 15)]")
    for unit, cnt in report["top_units"]:
        lines.append(f"    {unit}: {cnt:,}건")

    lines.append("\n  [source_file 분포 (Top 10)]")
    for fname, cnt in report["top_files"]:
        lines.append(f"    {fname}: {cnt:,}건")

    verdict = PASS if total > 0 else WARN
    lines.append(f"\n  판정: {verdict}")
    output = "\n".join(lines)
    print(output)
    return verdict


# ── item_alias 매핑 로드 ──────────────────────────────────────

def fetch_item_map(conn) -> dict:
    """{(alias_name, alias_spec_or_None, source): (item_code, item_name_std)}"""
    result = {}
    with conn.cursor() as cur:
        cur.execute("""
            SELECT a.alias_name, a.alias_spec, a.source, m.item_code, m.item_name
            FROM core_price.item_alias a
            JOIN core_price.item_master m ON m.id = a.item_id
        """)
        for alias_name, alias_spec, src, item_code, item_name in cur.fetchall():
            result[(alias_name, alias_spec, src)] = (item_code, item_name)
    return result


# ── 3단계: 참조 가격 승격 ────────────────────────────────────

def migrate_reference(conn, rules: dict, dry_run: bool):
    non_geo  = rules["kpi_non_geographic_regions"]
    std_unit = rules["unit_std"]

    item_map = fetch_item_map(conn)

    with conn.cursor() as cur:
        cur.execute("""
            SELECT r.품목명, r.단위, r.지역, r.연도, r.월, r.가격, r.분류, r.file_id
            FROM staging_price.kpi_prices_raw r
            WHERE r.지역 = ANY(%s) AND r.가격 IS NOT NULL
            ORDER BY r.연도, r.월, r.품목명
        """, (non_geo,))
        rows = cur.fetchall()

    stats      = {"total": len(rows), "ok": 0, "unresolved_item": 0}
    unresolved = set()
    buf        = []

    for (품목명, 단위, 지역, 연도, 월, 가격, 분류, file_id) in rows:
        unit_code = std_unit.get(단위, 단위) if 단위 else None
        if not unit_code:
            unit_code = None

        # item_master 조회 (KPI alias → item_code)
        item_code     = None
        item_name_std = None
        match = item_map.get((품목명, None, "KPI"))
        if match:
            item_code, item_name_std = match
        else:
            unresolved.add(품목명)
            stats["unresolved_item"] += 1

        buf.append((
            "KPI",          # source_type
            file_id,        # source_file_id
            item_code,      # item_code (None=미해소)
            품목명,          # item_name_raw
            item_name_std,  # item_name_std
            None,           # spec
            단위,            # unit_raw
            unit_code,      # unit_code
            지역,            # reference_type (기준① 등)
            int(연도),       # price_year
            int(월),         # price_month
            int(가격),       # price
            지역,            # region_raw (보존)
            분류,            # category
        ))
        stats["ok"] += 1

    if dry_run:
        print(f"\n[dry] price_reference 적재 예정: {stats['ok']:,}건")
        print(f"[dry] item_code 미해소: {stats['unresolved_item']:,}건 ({len(unresolved)}품목)")
        if unresolved:
            preview = sorted(unresolved)[:10]
            print(f"[dry] 미해소 품목 예시: {preview}")
        return stats, unresolved

    BATCH = 5_000
    total_inserted = 0
    for i in range(0, len(buf), BATCH):
        chunk = buf[i : i + BATCH]
        with conn.cursor() as cur:
            psycopg2.extras.execute_values(
                cur,
                """INSERT INTO core_price.price_reference
                   (source_type, source_file_id, item_code, item_name_raw, item_name_std,
                    spec, unit_raw, unit_code, reference_type, price_year, price_month,
                    price, region_raw, category)
                   VALUES %s
                   ON CONFLICT (source_type, source_file_id, item_name_raw,
                                reference_type, price_year, price_month)
                   DO NOTHING""",
                chunk,
            )
        conn.commit()
        total_inserted += len(chunk)
        print(f"  {total_inserted:,}/{len(buf):,}건 완료...", end="\r", flush=True)

    print()
    stats["inserted"] = total_inserted
    return stats, unresolved


# ── 5단계: 검증 ──────────────────────────────────────────────

def verify_reference(conn) -> dict:
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

        cur.execute("SELECT COUNT(*) FROM core_price.price_reference WHERE item_code IS NULL")
        unresolved_cnt = cur.fetchone()[0]

        cur.execute("SELECT COUNT(DISTINCT item_name_raw) FROM core_price.price_reference")
        distinct_items = cur.fetchone()[0]

        cur.execute("""
            SELECT COUNT(DISTINCT item_name_raw)
            FROM core_price.price_reference
            WHERE item_code IS NULL
        """)
        unresolved_items = cur.fetchone()[0]

    return {
        "total":           total,
        "by_type":         by_type,
        "unresolved_rows": unresolved_cnt,
        "distinct_items":  distinct_items,
        "unresolved_items": unresolved_items,
    }


def print_verify(v: dict) -> str:
    lines = ["\n=== [5단계] price_reference 검증 ==="]
    total = v["total"]
    lines.append(f"  총 적재: {total:,}건")
    lines.append(f"  고유 품목 수: {v['distinct_items']:,}건")
    lines.append(f"  item_code 미해소 행: {v['unresolved_rows']:,}건")
    lines.append(f"  item_code 미해소 품목: {v['unresolved_items']:,}건")

    lines.append("\n  [reference_type 분포]")
    for ref_type, cnt in v["by_type"]:
        pct = cnt / total * 100 if total else 0
        lines.append(f"    {ref_type}: {cnt:,}건 ({pct:.1f}%)")

    unresolved_pct = v["unresolved_rows"] / total * 100 if total else 0
    if unresolved_pct > 20:
        verdict = WARN
    elif total == 0:
        verdict = FAIL
    else:
        verdict = PASS
    lines.append(f"\n  판정: {verdict}")
    print("\n".join(lines))
    return verdict


# ── 메인 ─────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="KPI 비지리 행 → core_price.price_reference 마이그레이션"
    )
    ap.add_argument("--pg",      required=True, help="PostgreSQL DSN")
    ap.add_argument("--rules",   default=str(DEFAULT_RULES), help="표준화 규칙 JSON 경로")
    ap.add_argument("--dry-run", action="store_true", help="적재 없이 건수만 출력")
    ap.add_argument("--analyze", action="store_true", help="비지리 행 구조 분석만 출력")
    args = ap.parse_args()

    rules   = load_rules(Path(args.rules))
    non_geo = rules["kpi_non_geographic_regions"]

    if args.dry_run:
        print("=== DRY RUN 모드 ===")

    conn = psycopg2.connect(args.pg)
    try:
        # 1단계: 분석
        print("\n[1단계] 비지리 행 분포 분석...")
        analysis = analyze_non_geo(conn, non_geo)
        analyze_verdict = print_analysis(analysis)

        if args.analyze:
            return

        # 3단계: 승격
        print("\n[3단계] price_reference 적재 시작...")
        stats, unresolved = migrate_reference(conn, rules, args.dry_run)

        print(f"\n[적재 결과]")
        print(f"  staging 입력:        {stats['total']:,}건")
        print(f"  price_reference 적재: {stats['ok']:,}건")
        print(f"  item_code 미해소:     {stats['unresolved_item']:,}건 ({len(unresolved)}품목)")

        # 5단계: 검증
        if not args.dry_run:
            v = verify_reference(conn)
            verify_verdict = print_verify(v)

            if unresolved:
                print(f"\n[unresolved 품목 목록 ({len(unresolved)}건)]")
                for item in sorted(unresolved)[:50]:
                    print(f"  - {item}")
                if len(unresolved) > 50:
                    print(f"  ... 외 {len(unresolved) - 50}건")

            final = FAIL if verify_verdict == FAIL else (
                WARN if (analyze_verdict == WARN or verify_verdict == WARN) else PASS
            )
            print(f"\n===== 최종 판정: {final} =====")

    finally:
        conn.close()
    print("\n완료")


if __name__ == "__main__":
    main()
