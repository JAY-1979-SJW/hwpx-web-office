"""
price_db_migrate_core.py  --  staging_price → core_price 1차 마이그레이션

처리 흐름:
  1. unit_master    : KPI+KPRC 단위 표준화 후 삽입
  2. region_master  : KPI 지리적 지역 + KPRC 조사지역 표준화 후 삽입
  3. item_master    : KPRC 25품목 + KPI 지리적지역 816품목 (교차매칭 2건은 BOTH)
  4. item_alias     : 소스 원본명 → item_master 역매핑
  5. price_observation : KPRC 월별 + KPI 지리적지역 행만 승격

제외 대상:
  - KPI 비지리적 지역 행 (기준①②·기준가·단가)
  - KPRC 연평균 행 (월=NULL)
  - 단위/지역 표준화 실패 행 → unresolved_report에 기록

사용:
  python price_db_migrate_core.py --pg "host=gongmu-db dbname=price_db user=gongmu password=..."
  python price_db_migrate_core.py --pg "..." --rules /path/to/standardization_rules.json
  python price_db_migrate_core.py --pg "..." --dry-run   # 적재 없이 통계만 출력
"""

import argparse, json, os, sys
from pathlib import Path
from datetime import datetime

import psycopg2
import psycopg2.extras

DEFAULT_RULES = Path(__file__).parent.parent / "db" / "standardization_rules.json"
RULES_ENV = Path(os.environ.get("STD_RULES", str(DEFAULT_RULES)))


# ── 규칙 로드 ─────────────────────────────────────────────────

def load_rules(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# ── 1. unit_master ────────────────────────────────────────────

def build_unit_master(conn, rules: dict, dry_run: bool) -> dict[str, int]:
    """표준화된 단위 전체를 unit_master에 삽입. {unit_name: id} 반환."""
    std = rules["unit_std"]
    grp = rules["unit_group"]

    # staging에 나타나는 원본 단위 수집
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT 단위 FROM staging_price.kpi_prices_raw")
        kpi_units = {r[0] for r in cur.fetchall() if r[0]}
        cur.execute("SELECT DISTINCT 단위 FROM staging_price.kprc_prices_raw")
        kprc_units = {r[0] for r in cur.fetchall() if r[0]}

    all_raw = kpi_units | kprc_units
    std_units: set[str] = set()
    for raw in all_raw:
        s = std.get(raw, raw)  # 규칙 없으면 원본 유지
        if s:
            std_units.add(s)

    unit_id: dict[str, int] = {}
    if dry_run:
        print(f"[dry] unit_master: {len(std_units)}개")
        for u in sorted(std_units):
            unit_id[u] = -1
        return unit_id  # dry-run: dict만 반환

    with conn.cursor() as cur:
        for u in sorted(std_units):
            g = grp.get(u, "기타")
            cur.execute(
                """INSERT INTO core_price.unit_master (unit_name, unit_group)
                   VALUES (%s, %s) ON CONFLICT (unit_name) DO NOTHING RETURNING id""",
                (u, g),
            )
            row = cur.fetchone()
            if row:
                unit_id[u] = row[0]
            else:
                cur.execute("SELECT id FROM core_price.unit_master WHERE unit_name=%s", (u,))
                unit_id[u] = cur.fetchone()[0]
    conn.commit()
    print(f"[unit_master] {len(unit_id)}개 삽입/확인")
    return unit_id


# ── 2. region_master ──────────────────────────────────────────

def build_region_master(conn, rules: dict, dry_run: bool) -> dict[str, int]:
    """표준화된 지역을 region_master에 삽입. {region_name: id} 반환."""
    std = rules["region_std"]
    grp = rules["region_group"]
    non_geo = set(rules["kpi_non_geographic_regions"])

    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT 지역 FROM staging_price.kpi_prices_raw WHERE 지역 IS NOT NULL")
        kpi_regions = {r[0] for r in cur.fetchall()} - non_geo
        cur.execute("SELECT DISTINCT 조사지역 FROM staging_price.kprc_prices_raw WHERE 조사지역 IS NOT NULL")
        kprc_regions = {r[0] for r in cur.fetchall()}

    all_raw = kpi_regions | kprc_regions
    std_regions: set[str] = set()
    unresolved_regions: set[str] = set()
    for raw in all_raw:
        s = std.get(raw)
        if s:
            std_regions.add(s)
        else:
            unresolved_regions.add(raw)

    region_id: dict[str, int] = {}
    if dry_run:
        print(f"[dry] region_master: {len(std_regions)}개, unresolved: {unresolved_regions}")
        for r in sorted(std_regions):
            region_id[r] = -1
        return region_id, unresolved_regions  # dry-run도 tuple 반환

    with conn.cursor() as cur:
        for r in sorted(std_regions):
            g = grp.get(r, "기타")
            cur.execute(
                """INSERT INTO core_price.region_master (region_name, region_group)
                   VALUES (%s, %s) ON CONFLICT (region_name) DO NOTHING RETURNING id""",
                (r, g),
            )
            row = cur.fetchone()
            if row:
                region_id[r] = row[0]
            else:
                cur.execute("SELECT id FROM core_price.region_master WHERE region_name=%s", (r,))
                region_id[r] = cur.fetchone()[0]
    conn.commit()
    if unresolved_regions:
        print(f"[region_master] unresolved: {unresolved_regions}")
    print(f"[region_master] {len(region_id)}개 삽입/확인, unresolved {len(unresolved_regions)}개")
    return region_id, unresolved_regions


# ── 3+4. item_master + item_alias ────────────────────────────

def build_item_master(conn, rules: dict, unit_id: dict, dry_run: bool):
    """
    KPRC 25품목 + KPI 지리적지역 816품목 → item_master + item_alias.
    교차매칭(kpi_kprc_name_match)된 항목은 BOTH source로 통합.
    반환: (item_id_map, unresolved_items)
      item_id_map: {(source, alias_name, alias_spec): item_master_id}
    """
    cross_match = rules.get("kpi_kprc_name_match", {})  # kprc_name → kpi_name (same)
    std_unit = rules["unit_std"]
    non_geo = set(rules["kpi_non_geographic_regions"])

    with conn.cursor() as cur:
        # KPRC 품목
        cur.execute("""
            SELECT DISTINCT 품목명, 규격, 단위
            FROM staging_price.kprc_prices_raw
            ORDER BY 품목명, 규격
        """)
        kprc_items = cur.fetchall()  # [(품목명, 규격, 단위), ...]

        # KPI 품목 (지리적 지역 + 가격 있음)
        cur.execute("""
            SELECT DISTINCT 품목명, 단위, 분류
            FROM staging_price.kpi_prices_raw
            WHERE 지역 NOT IN %s AND 가격 IS NOT NULL
            ORDER BY 품목명
        """, (tuple(non_geo),))
        kpi_items = cur.fetchall()  # [(품목명, 단위, 분류), ...]

    # KPRC 품목명 집합
    kprc_names = {row[0] for row in kprc_items}

    # item_master 삽입 결과
    item_id_map: dict = {}   # {(source, alias_name, alias_spec): item_master_id}
    seq = [0]

    def next_code():
        seq[0] += 1
        return f"MAT-{seq[0]:05d}"

    rows_to_insert = []  # [(item_code, item_name, category, spec, unit_name, source)]

    # -- KPRC items 먼저
    for (품목명, 규격, 단위) in kprc_items:
        src = "BOTH" if 품목명 in cross_match else "KPRC"
        u_std = std_unit.get(단위, 단위) if 단위 else None
        rows_to_insert.append((next_code(), 품목명, None, 규격, u_std, src, 품목명, 규격, "KPRC"))

    # -- KPI items (KPRC에서 이미 나온 품목명은 alias만 추가)
    kprc_master_name = {row[0] for row in kprc_items}
    for (품목명, 단위, 분류) in kpi_items:
        if 품목명 in kprc_master_name:
            # 이미 KPRC로 등록됨 → alias만 추가 (item_master 새 행 불필요)
            rows_to_insert.append((None, 품목명, 분류, None, None, None, 품목명, None, "KPI"))
        else:
            u_std = std_unit.get(단위, 단위) if 단위 else None
            rows_to_insert.append((next_code(), 품목명, 분류, None, u_std, "KPI", 품목명, None, "KPI"))

    if dry_run:
        new_items = [r for r in rows_to_insert if r[0] is not None]
        alias_only = [r for r in rows_to_insert if r[0] is None]
        print(f"[dry] item_master: {len(new_items)}건 삽입 예정, alias-only: {len(alias_only)}건")
        return {}, set()

    # 실제 삽입
    with conn.cursor() as cur:
        # 기존 item_master 로드 (이미 삽입된 경우 스킵)
        cur.execute("SELECT MAX(id) FROM core_price.item_master")
        max_id = cur.fetchone()[0] or 0

        # KPRC 기준으로 먼저 삽입
        for row in rows_to_insert:
            code, name, cat, spec, unit_name, src, alias_name, alias_spec, alias_src = row

            if code is None:
                # alias-only: item_master에서 해당 품목 ID 찾기
                cur.execute("SELECT id FROM core_price.item_master WHERE item_name=%s", (name,))
                r = cur.fetchone()
                if r:
                    mid = r[0]
                    # alias 추가
                    cur.execute("""
                        INSERT INTO core_price.item_alias (item_id, alias_name, alias_spec, source)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (alias_name, alias_spec, source) DO NOTHING
                    """, (mid, alias_name, alias_spec, alias_src))
                    item_id_map[("KPI", alias_name, alias_spec)] = mid
                continue

            # item_master 삽입
            uid = unit_id.get(unit_name) if unit_name else None
            cur.execute("""
                INSERT INTO core_price.item_master
                       (item_code, item_name, category, spec, unit_id, source)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (item_code) DO NOTHING
                RETURNING id
            """, (code, name, cat, spec, uid, src))
            r = cur.fetchone()
            if r:
                mid = r[0]
            else:
                cur.execute("SELECT id FROM core_price.item_master WHERE item_code=%s", (code,))
                mid = cur.fetchone()[0]

            item_id_map[(alias_src, alias_name, alias_spec)] = mid

            # item_alias 삽입
            cur.execute("""
                INSERT INTO core_price.item_alias (item_id, alias_name, alias_spec, source)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (alias_name, alias_spec, source) DO NOTHING
            """, (mid, alias_name, alias_spec, alias_src))

    conn.commit()

    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM core_price.item_master")
        im_cnt = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM core_price.item_alias")
        ia_cnt = cur.fetchone()[0]
    print(f"[item_master] {im_cnt}개, [item_alias] {ia_cnt}개")
    return item_id_map, set()


# ── 5. price_observation ──────────────────────────────────────

def load_price_observation(conn, rules: dict, unit_id: dict, region_id: dict,
                           item_id_map: dict, dry_run: bool) -> dict:
    std_unit   = rules["unit_std"]
    std_region = rules["region_std"]
    non_geo    = set(rules["kpi_non_geographic_regions"])

    stats = {"kpi_ok": 0, "kpi_skip": 0, "kprc_ok": 0, "kprc_skip": 0}
    BATCH = 5_000

    with conn.cursor() as cur:
        # -- KPRC (월 IS NOT NULL 행만)
        cur.execute("""
            SELECT r.품목명, r.규격, r.단위, r.조사지역, r.연도, r.월, r.가격, f.id
            FROM staging_price.kprc_prices_raw r
            JOIN raw_ingest.files f ON f.id = r.file_id
            WHERE r.월 IS NOT NULL AND r.가격 IS NOT NULL
        """)
        kprc_rows = cur.fetchall()

    buf = []
    for (품목명, 규격, 단위, 조사지역, 연도, 월, 가격, file_id) in kprc_rows:
        iid = item_id_map.get(("KPRC", 품목명, 규격))
        if iid is None:
            stats["kprc_skip"] += 1
            continue
        reg_std = std_region.get(조사지역, 조사지역) if 조사지역 else None
        rid = region_id.get(reg_std) if reg_std else None
        buf.append((iid, rid, int(연도), int(월), int(가격), "KPRC", 연도, 월, file_id))
        stats["kprc_ok"] += 1

    if not dry_run and buf:
        with conn.cursor() as cur:
            psycopg2.extras.execute_values(
                cur,
                """INSERT INTO core_price.price_observation
                   (item_id, region_id, year, month, price, source, pub_year, pub_month, file_id)
                   VALUES %s
                   ON CONFLICT (item_id, region_id, year, month, source) DO NOTHING""",
                buf,
            )
        conn.commit()
        buf.clear()

    # -- KPI (지리적 지역 행만)
    with conn.cursor() as cur:
        cur.execute("""
            SELECT r.품목명, r.단위, r.지역, r.연도, r.월, r.가격, f.id
            FROM staging_price.kpi_prices_raw r
            JOIN raw_ingest.files f ON f.id = r.file_id
            WHERE r.지역 NOT IN %s AND r.가격 IS NOT NULL
        """, (tuple(non_geo),))

        inserted = 0
        for (품목명, 단위, 지역, 연도, 월, 가격, file_id) in cur:
            iid = item_id_map.get(("KPI", 품목명, None))
            if iid is None:
                # BOTH 소스(KPRC에서 등록된) 확인
                iid = item_id_map.get(("KPRC", 품목명, None))
            if iid is None:
                stats["kpi_skip"] += 1
                continue

            reg_std = std_region.get(지역) if 지역 else None
            if reg_std is None:
                stats["kpi_skip"] += 1
                continue
            rid = region_id.get(reg_std)
            if rid is None:
                stats["kpi_skip"] += 1
                continue

            buf.append((iid, rid, int(연도), int(월), int(가격), "KPI", 연도, 월, file_id))
            stats["kpi_ok"] += 1

            if len(buf) >= BATCH:
                if not dry_run:
                    with conn.cursor() as cur2:
                        psycopg2.extras.execute_values(
                            cur2,
                            """INSERT INTO core_price.price_observation
                               (item_id, region_id, year, month, price, source,
                                pub_year, pub_month, file_id)
                               VALUES %s
                               ON CONFLICT (item_id, region_id, year, month, source) DO NOTHING""",
                            buf,
                        )
                    conn.commit()
                buf.clear()
                print(f"  KPI {stats['kpi_ok']:,}건 진행 중...", end="\r", flush=True)

    if buf and not dry_run:
        with conn.cursor() as cur:
            psycopg2.extras.execute_values(
                cur,
                """INSERT INTO core_price.price_observation
                   (item_id, region_id, year, month, price, source, pub_year, pub_month, file_id)
                   VALUES %s
                   ON CONFLICT (item_id, region_id, year, month, source) DO NOTHING""",
                buf,
            )
        conn.commit()

    return stats


# ── 검증 ─────────────────────────────────────────────────────

def verify(conn) -> dict:
    result = {}
    with conn.cursor() as cur:
        for tbl, col, label in [
            ("core_price.item_master",       None, "item_master"),
            ("core_price.item_alias",        None, "item_alias"),
            ("core_price.unit_master",       None, "unit_master"),
            ("core_price.region_master",     None, "region_master"),
            ("core_price.price_observation", None, "price_obs_total"),
        ]:
            cur.execute(f"SELECT COUNT(*) FROM {tbl}")
            result[label] = cur.fetchone()[0]

        cur.execute("""
            SELECT source, COUNT(*) FROM core_price.price_observation GROUP BY source
        """)
        result["obs_by_source"] = dict(cur.fetchall())

        cur.execute("""
            SELECT COUNT(DISTINCT item_id) FROM core_price.price_observation
        """)
        result["obs_distinct_items"] = cur.fetchone()[0]
    return result


# ── 메인 ─────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pg",    required=True)
    ap.add_argument("--rules", default=str(RULES_ENV))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    rules = load_rules(Path(args.rules))
    print(f"규칙 파일: {args.rules}")
    if args.dry_run:
        print("=== DRY RUN 모드 ===")

    conn = psycopg2.connect(args.pg)
    try:
        print("\n[1] unit_master")
        uid_map = build_unit_master(conn, rules, args.dry_run)

        print("\n[2] region_master")
        rid_map, unresolved_regions = build_region_master(conn, rules, args.dry_run)

        print("\n[3+4] item_master + item_alias")
        iid_map, unresolved_items = build_item_master(conn, rules, uid_map, args.dry_run)

        print("\n[5] price_observation")
        stats = load_price_observation(conn, rules, uid_map, rid_map, iid_map, args.dry_run)

        print(f"\n  KPI  승격: {stats['kpi_ok']:,}건, 제외: {stats['kpi_skip']:,}건")
        print(f"  KPRC 승격: {stats['kprc_ok']:,}건, 제외: {stats['kprc_skip']:,}건")

        if not args.dry_run:
            print("\n[검증]")
            v = verify(conn)
            for k, val in v.items():
                print(f"  {k}: {val}")

        if unresolved_regions:
            print(f"\n[unresolved 지역] {sorted(unresolved_regions)}")
        if unresolved_items:
            print(f"[unresolved 품목] {len(unresolved_items)}건")

    finally:
        conn.close()
    print("\n완료")


if __name__ == "__main__":
    main()
