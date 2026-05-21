"""
item_master_boost_kpi_reference.py
──────────────────────────────────
price_reference에서 item_code IS NULL 인 (item_name_raw, category) 조합을
KPI_REFERENCE scope의 신규 item_master + item_alias로 등록한다.

핵심 원칙
  - 신규 item_master.source = 'KPI_REFERENCE' (기존 KPI/KPRC/BOTH와 분리)
  - item_code prefix: KPI-REF-NNNNN
  - item_alias.source = 'KPI', alias_spec = category (충돌 방지)
  - fragment 패턴은 신규 생성 금지 (unresolved 유지)
  - 멱등성: 알리아스 유일 제약 + item_code prefix 기반 seq 증분

사용:
  python scripts/item_master_boost_kpi_reference.py --pg "host=... dbname=price_db user=..."
  python scripts/item_master_boost_kpi_reference.py --pg "..." --dry-run
"""

import argparse
import json
import re
from pathlib import Path

import psycopg2
import psycopg2.extras

RULES_PATH = Path(__file__).parent.parent / "db" / "kpi_reference_mapping_rules.json"


def load_fragment_filter(rules: dict):
    ff = rules["fragment_filter"]
    exact = set(ff["exact_match"])
    regexes = [(re.compile(p["pattern"]), p["reason"]) for p in ff["regex_patterns"]]
    return exact, regexes


def _alpha_ratio(s: str) -> float:
    if not s:
        return 0.0
    alpha = sum(1 for c in s if c.isalpha() or "가" <= c <= "힣")
    return alpha / len(s)


def is_fragment(name: str, exact: set, regexes: list):
    if name is None:
        return True, "null"
    s = name.strip()
    if len(s) < 2:
        return True, "too_short"
    if s in exact:
        return True, "unit_label"
    for pat, reason in regexes:
        if pat.search(s):
            return True, reason
    if s.count(",") >= 2:
        return True, "many_commas"
    if s.count("(") != s.count(")"):
        return True, "unbalanced_paren"
    if len(s) >= 3 and _alpha_ratio(s) < 0.3:
        return True, "low_alpha"
    return False, ""


def main():
    ap = argparse.ArgumentParser(
        description="KPI 비지리 참조가격 품목 → item_master/item_alias 보강"
    )
    ap.add_argument("--pg", required=True)
    ap.add_argument("--rules", default=str(RULES_PATH))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    rules = json.loads(Path(args.rules).read_text(encoding="utf-8"))
    exact, regexes = load_fragment_filter(rules)
    scope = rules["scope"]
    code_prefix = scope["item_code_prefix"]

    conn = psycopg2.connect(args.pg)
    try:
        with conn.cursor() as cur:
            # (name, category) 그룹화 - unresolved
            cur.execute("""
                SELECT item_name_raw,
                       category,
                       COUNT(*) AS row_cnt
                FROM core_price.price_reference
                WHERE item_code IS NULL
                  AND category IS NOT NULL
                  AND item_name_raw IS NOT NULL
                GROUP BY item_name_raw, category
            """)
            groups = cur.fetchall()

            # 이미 생성된 KPI_REFERENCE alias 로드 (멱등성)
            cur.execute("""
                SELECT a.alias_name, a.alias_spec
                FROM core_price.item_alias a
                JOIN core_price.item_master m ON m.id = a.item_id
                WHERE m.source = 'KPI_REFERENCE'
            """)
            existing = {(n, s) for n, s in cur.fetchall()}

            # 다음 seq 계산
            cur.execute(f"""
                SELECT COALESCE(MAX(SUBSTRING(item_code FROM {len(code_prefix) + 1})::INT), 0)
                FROM core_price.item_master
                WHERE item_code LIKE %s
            """, (code_prefix + "%",))
            next_seq = (cur.fetchone()[0] or 0) + 1

        stats = {
            "input_groups":  len(groups),
            "fragment":      0,
            "filter_reasons": {},
            "already_exists": 0,
            "to_insert":     0,
        }

        master_rows = []
        for (name, cat, cnt) in groups:
            frag, reason = is_fragment(name, exact, regexes)
            if frag:
                stats["fragment"] += 1
                stats["filter_reasons"][reason] = stats["filter_reasons"].get(reason, 0) + 1
                continue
            if (name, cat) in existing:
                stats["already_exists"] += 1
                continue
            master_rows.append((f"{code_prefix}{next_seq:05d}", name, cat, "KPI_REFERENCE"))
            next_seq += 1

        stats["to_insert"] = len(master_rows)

        print(f"\n=== item_master_boost_kpi_reference ===")
        print(f"  입력 (name, category) 그룹: {stats['input_groups']:,}")
        print(f"  fragment 제외:              {stats['fragment']:,}")
        for r, c in sorted(stats["filter_reasons"].items(), key=lambda x: -x[1]):
            print(f"    {r:<18s}: {c:,}")
        print(f"  이미 존재 (skip):           {stats['already_exists']:,}")
        print(f"  신규 생성 예정:             {stats['to_insert']:,}")

        if args.dry_run:
            if master_rows:
                print(f"\n  [dry] 샘플 5건:")
                for row in master_rows[:5]:
                    print(f"    {row}")
            return

        # item_master INSERT
        with conn.cursor() as cur:
            psycopg2.extras.execute_values(
                cur,
                """INSERT INTO core_price.item_master
                    (item_code, item_name, category, source)
                   VALUES %s
                   ON CONFLICT (item_code) DO NOTHING""",
                master_rows,
            )
        conn.commit()

        # 방금 삽입된 (또는 이미 있던) KPI_REFERENCE master의 id 매핑
        # (같은 (item_name, category)는 유일성 보장 안됨 → item_code가 신뢰 키)
        codes = [row[0] for row in master_rows]
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, item_name, category, item_code
                FROM core_price.item_master
                WHERE item_code = ANY(%s)
            """, (codes,))
            inserted = cur.fetchall()

        # item_alias INSERT
        alias_rows = [(mid, name, cat, "KPI") for (mid, name, cat, code) in inserted]
        with conn.cursor() as cur:
            psycopg2.extras.execute_values(
                cur,
                """INSERT INTO core_price.item_alias
                    (item_id, alias_name, alias_spec, source)
                   VALUES %s
                   ON CONFLICT (alias_name, alias_spec, source) DO NOTHING""",
                alias_rows,
            )
        conn.commit()

        # 검증 쿼리
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM core_price.item_master WHERE source='KPI_REFERENCE'")
            total_ref_master = cur.fetchone()[0]
            cur.execute("""
                SELECT COUNT(*) FROM core_price.item_alias a
                JOIN core_price.item_master m ON m.id=a.item_id
                WHERE m.source='KPI_REFERENCE'
            """)
            total_ref_alias = cur.fetchone()[0]

        print(f"\n  === BOOST 최종 요약 ===")
        print(f"  [1] 신규 item_master 생성 시도:   {len(master_rows):,}")
        print(f"  [2] fragment 제외 건수:           {stats['fragment']:,}")
        for r, c in sorted(stats["filter_reasons"].items(), key=lambda x: -x[1]):
            print(f"        - {r:<18s}: {c:,}")
        print(f"  [5] KPI_REFERENCE 전용 품목 수:   {total_ref_master:,}  (alias {total_ref_alias:,})")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
