"""
collect_g2b_openapi.py — 조달청 PriceInfoService 서버 직접 수집기
  raw_ingest.g2b_price_raw → staging_price.g2b_price_normalized

섹션 코드:
  FCLTY_MTR_BILDNG   시설공통자재(건축)
  FCLTY_MTR_ENGRK    시설공통자재(토목)
  FCLTY_MTR_MCHN     시설공통자재(기계설비)
  FCLTY_MTR_ELCTY    시설공통자재(전기·정보통신)
  FCLTY_MTR_TOTAL    시설공통자재(종합)  ← 404 가능, skip 처리
  CNSTTY_CLASS       공종분류및세부공종
  NET_RESOURCE       자원분류및순수자원

필수 환경변수 (또는 --env-file):
  G2B_API_KEY   또는   NARA_PRICE_API_KEY
  G2B_PG_HOST / G2B_PG_DB / G2B_PG_USER / G2B_PG_PASSWORD
  (또는 DB_HOST / DB_NAME / DB_USER / DB_PASSWORD)

실행:
  python3 collect_g2b_openapi.py --section NET_RESOURCE --dry-run
  python3 collect_g2b_openapi.py --section FCLTY_MTR_BILDNG --pages 3
  python3 collect_g2b_openapi.py                   # 전체 수집
  python3 collect_g2b_openapi.py --env-file /home/ubuntu/app/g2b/.env.g2b
"""

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlencode

import psycopg2
import psycopg2.extras

# ── 상수 ─────────────────────────────────────────────────────────────────────

BASE_URL   = "https://apis.data.go.kr/1230000/ao/PriceInfoService"
NUM_ROWS   = 500
SLEEP_SEC  = 0.25
RETRY_WAIT = 5.0

# 섹션 정의: (endpoint, biz_div, mapper_key, optional=404 허용)
SECTIONS: dict[str, dict] = {
    "FCLTY_MTR_BILDNG": {
        "endpoint": "getPriceInfoListFcltyCmmnMtrilBildng",
        "biz_div":  "시설자재(건축분야)",
        "mapper":   "fclty_mtr",
    },
    "FCLTY_MTR_ENGRK": {
        "endpoint": "getPriceInfoListFcltyCmmnMtrilEngrk",
        "biz_div":  "시설자재(토목분야)",
        "mapper":   "fclty_mtr",
    },
    "FCLTY_MTR_MCHN": {
        "endpoint": "getPriceInfoListFcltyCmmnMtrilMchnEqp",
        "biz_div":  "시설자재(기계설비분야)",
        "mapper":   "fclty_mtr",
    },
    "FCLTY_MTR_ELCTY": {
        "endpoint": "getPriceInfoListFcltyCmmnMtrilElctyIrmc",
        "biz_div":  "시설자재(전기분야)",
        "mapper":   "fclty_mtr",
    },
    "FCLTY_MTR_TOTAL": {
        "endpoint": "getPriceInfoListFcltyCmmnMtrilTotal",
        "biz_div":  "시설자재(종합)",
        "mapper":   "fclty_mtr",
        "optional": True,   # 404 발생 시 skip
    },
    "CNSTTY_CLASS": {
        "endpoint": "getCnsttyClsfcInfoList",
        "biz_div":  "공종분류",
        "mapper":   "cnstty_class",
    },
    "NET_RESOURCE": {
        "endpoint": "getNetRsceinfoList",
        "biz_div":  "순수자원",
        "mapper":   "net_resource",
    },
}


# ── 유틸 ─────────────────────────────────────────────────────────────────────

def load_env_file(path: str) -> None:
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def mask(key: str) -> str:
    """API 키 마스킹: 앞 4자만 노출."""
    return key[:4] + "****" if key else "(없음)"


def parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    raw = raw.strip()
    try:
        if len(raw) >= 10 and raw[4] == "-":
            return date.fromisoformat(raw[:10])
        if len(raw) == 8 and raw.isdigit():
            return date(int(raw[:4]), int(raw[4:6]), int(raw[6:8]))
    except (ValueError, TypeError):
        pass
    return None


def to_bigint(val) -> int | None:
    if val is None or val == "":
        return None
    try:
        d = Decimal(str(val).replace(",", ""))
        return int(d)
    except (InvalidOperation, ValueError):
        return None


def source_key(section_code: str, page_no: int, run_date: str) -> str:
    raw = f"{section_code}:p{page_no}:{run_date}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


# ── API 호출 ──────────────────────────────────────────────────────────────────

def fetch_page(api_key: str, endpoint: str, page: int, retries: int = 3) -> dict:
    params = urlencode({
        "ServiceKey": api_key,
        "pageNo":     page,
        "numOfRows":  NUM_ROWS,
        "type":       "json",
    })
    url = f"{BASE_URL}/{endpoint}?{params}"
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read().decode("utf-8")
                return json.loads(body)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = RETRY_WAIT * (attempt + 1)
                print(f"  [WARN] 429 rate-limit — {wait:.0f}s 대기", flush=True)
                time.sleep(wait)
            elif e.code == 404:
                raise RuntimeError(f"404: endpoint 없음 ({endpoint})")
            else:
                raise
    raise RuntimeError(f"최대 재시도 초과 ({endpoint} p{page})")


def extract_items(data: dict) -> tuple[list[dict], int]:
    try:
        body  = data["response"]["body"]
        total = int(body.get("totalCount", 0))
        items = body.get("items") or []
        if isinstance(items, dict):
            items = items.get("item", [])
        if isinstance(items, dict):
            items = [items]
        return (items if isinstance(items, list) else []), total
    except (KeyError, TypeError):
        return [], 0


# ── 섹션별 필드 매퍼 ─────────────────────────────────────────────────────────

def map_fclty_mtr(item: dict, section_code: str, biz_div: str) -> dict | None:
    """시설공통자재 4개 분야 + 종합."""
    item_code = str(item.get("prdctIdntNo") or "").strip()
    if not item_code:
        return None
    return {
        "section_code":       section_code,
        "biz_div":            biz_div,
        "category_code":      item.get("prdctClsfcNo"),
        "category_name":      item.get("prdctClsfcNoNm"),
        "item_code":          item_code,
        "item_name":          item.get("krnPrdctNm") or item.get("prdctClsfcNoNm"),
        "spec_name":          None,
        "unit_raw":           item.get("unit"),
        "price_value":        to_bigint(item.get("prce")),
        "material_cost":      None,
        "labor_cost":         None,
        "expense_cost":       None,
        "total_cost":         None,
        "delivery_condition": item.get("dlvryCndtnNm"),
        "supply_region":      item.get("splyJrsdctRgnNm") or "",
        "vat_type":           item.get("vatYnNm"),
        "notice_date":        parse_date(item.get("nticeDt")),
    }


def map_net_resource(item: dict, section_code: str, biz_div: str) -> dict | None:
    """자원분류및순수자원 — notice_date 없음 → 수집월 1일."""
    item_code = str(item.get("netRsceCd") or "").strip()
    if not item_code:
        return None
    today = date.today()
    return {
        "section_code":       section_code,
        "biz_div":            (item.get("lvlRsceClsfcNm1") or "").strip() or biz_div,
        "category_code":      (item.get("rsceTyExtrnlCd") or "").strip() or None,
        "category_name":      (item.get("lvlRsceClsfcNm2") or "").strip() or None,
        "item_code":          item_code,
        "item_name":          item.get("rsceNm"),
        "spec_name":          item.get("rsceSpecNm"),
        "unit_raw":           item.get("unit"),
        "price_value":        to_bigint(item.get("lbrcst")),
        "material_cost":      to_bigint(item.get("mtrlcst")),
        "labor_cost":         to_bigint(item.get("lbrcst")),
        "expense_cost":       to_bigint(item.get("expns")),
        "total_cost":         to_bigint(item.get("tot")),
        "delivery_condition": None,
        "supply_region":      "",
        "vat_type":           None,
        "notice_date":        date(today.year, today.month, 1),
    }


def map_cnstty_class(item: dict, section_code: str, biz_div: str) -> dict | None:
    """공종분류및세부공종 — 실제 필드: qtyCalcCtyclcd, LvlqtyCalcCtyclCd1~5."""
    item_code = (item.get("qtyCalcCtyclcd") or "").strip()
    if not item_code:
        return None

    today = date.today()
    return {
        "section_code":       section_code,
        "biz_div":            (item.get("cnstwkDivNm") or "").strip() or biz_div,
        "category_code":      (item.get("LvlqtyCalcCtyclCd1") or "").strip() or None,
        "category_name":      item.get("LvlqtyCalcCtyclNm1"),
        "item_code":          item_code,
        "item_name":          item.get("qtyCalcCtyclNm"),
        "spec_name":          item.get("spec"),
        "unit_raw":           item.get("unit"),
        "price_value":        None,
        "material_cost":      None,
        "labor_cost":         None,
        "expense_cost":       None,
        "total_cost":         None,
        "delivery_condition": None,
        "supply_region":      "",
        "vat_type":           None,
        "notice_date":        date(today.year, today.month, 1),
    }


MAPPERS = {
    "fclty_mtr":   map_fclty_mtr,
    "net_resource": map_net_resource,
    "cnstty_class": map_cnstty_class,
}


# ── PostgreSQL ────────────────────────────────────────────────────────────────

def pg_connect() -> psycopg2.extensions.connection:
    return psycopg2.connect(
        host=os.environ["G2B_PG_HOST"],
        port=int(os.environ.get("G2B_PG_PORT", "5432")),
        dbname=os.environ["G2B_PG_DB"],
        user=os.environ["G2B_PG_USER"],
        password=os.environ["G2B_PG_PASSWORD"],
    )


def save_raw(cur, *, endpoint: str, section_code: str, page: int,
             params_dict: dict, response: dict, run_date: str) -> int | None:
    """raw 1페이지 저장. 이미 있으면 기존 id 반환."""
    sk = source_key(section_code, page, run_date)
    items, _ = extract_items(response)
    notice_dates = list({
        str(it.get("nticeDt") or "")
        for it in items if it.get("nticeDt")
    })
    nd_raw = notice_dates[0] if len(notice_dates) == 1 else (
        ",".join(sorted(notice_dates)[:3]) if notice_dates else None
    )

    # 인증키 제거 후 저장
    safe_params = {k: v for k, v in params_dict.items() if k != "ServiceKey"}

    cur.execute("""
        INSERT INTO raw_ingest.g2b_price_raw
            (endpoint_name, section_code, page_no, request_params,
             response_body, source_key, notice_date_raw, item_count)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (source_key) DO NOTHING
        RETURNING id
    """, (
        endpoint, section_code, page,
        json.dumps(safe_params, ensure_ascii=False),
        json.dumps(response, ensure_ascii=False),
        sk, nd_raw, len(items),
    ))
    row = cur.fetchone()
    return row[0] if row else None  # None = 이미 존재 (skip)


NORM_COLS = (
    "raw_row_id", "source_system", "section_code", "biz_div",
    "category_code", "category_name", "item_code", "item_name", "spec_name",
    "unit_raw", "price_value", "material_cost", "labor_cost", "expense_cost",
    "total_cost", "delivery_condition", "supply_region", "vat_type", "notice_date",
)


def save_normalized(cur, raw_row_id: int, rows: list[dict]) -> tuple[int, int]:
    """normalized upsert. (section_code, item_code, notice_date, supply_region) 충돌 시 UPDATE."""
    ins = upd = 0
    for r in rows:
        vals = (
            raw_row_id, "G2B",
            r["section_code"], r["biz_div"],
            r["category_code"], r["category_name"],
            r["item_code"], r["item_name"], r["spec_name"],
            r["unit_raw"], r["price_value"],
            r["material_cost"], r["labor_cost"], r["expense_cost"],
            r["total_cost"], r["delivery_condition"],
            r["supply_region"], r["vat_type"], r["notice_date"],
        )
        cur.execute("""
            INSERT INTO staging_price.g2b_price_normalized
                (raw_row_id, source_system, section_code, biz_div,
                 category_code, category_name, item_code, item_name, spec_name,
                 unit_raw, price_value, material_cost, labor_cost, expense_cost,
                 total_cost, delivery_condition, supply_region, vat_type, notice_date)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (section_code, item_code, notice_date, supply_region) DO UPDATE SET
                raw_row_id         = EXCLUDED.raw_row_id,
                biz_div            = EXCLUDED.biz_div,
                category_code      = EXCLUDED.category_code,
                category_name      = EXCLUDED.category_name,
                item_name          = EXCLUDED.item_name,
                spec_name          = EXCLUDED.spec_name,
                unit_raw           = EXCLUDED.unit_raw,
                price_value        = EXCLUDED.price_value,
                material_cost      = EXCLUDED.material_cost,
                labor_cost         = EXCLUDED.labor_cost,
                expense_cost       = EXCLUDED.expense_cost,
                total_cost         = EXCLUDED.total_cost,
                delivery_condition = EXCLUDED.delivery_condition,
                vat_type           = EXCLUDED.vat_type,
                acquired_at        = now()
        """, vals)
        if cur.rowcount == 1:
            ins += 1
        else:
            upd += 1
    return ins, upd


def save_reject(cur, section_code: str, raw_row_id: int | None,
                item: dict, msg: str) -> None:
    cur.execute("""
        INSERT INTO staging_price.g2b_reject_log
            (section_code, raw_row_id, raw_item, error_msg)
        VALUES (%s, %s, %s, %s)
    """, (section_code, raw_row_id,
          json.dumps(item, ensure_ascii=False), msg))


# ── raw 재적재 ───────────────────────────────────────────────────────────────

def rebuild_from_raw(pg: psycopg2.extensions.connection,
                     section_code: str | None = None) -> dict:
    """raw_ingest.g2b_price_raw 기준으로 normalized 재생성.
    - TRUNCATE normalized (section_code 지정 시 해당 섹션만 DELETE)
    - raw 페이지를 순서대로 읽어 mapper 적용 후 INSERT
    """
    with pg.cursor() as cur:
        if section_code:
            cur.execute(
                "DELETE FROM staging_price.g2b_price_normalized WHERE section_code = %s",
                (section_code,),
            )
            deleted = cur.rowcount
            cur.execute(
                "SELECT id, section_code, page_no, response_body FROM raw_ingest.g2b_price_raw "
                "WHERE section_code = %s ORDER BY page_no",
                (section_code,),
            )
        else:
            cur.execute("TRUNCATE staging_price.g2b_price_normalized")
            deleted = -1
            cur.execute(
                "SELECT id, section_code, page_no, response_body FROM raw_ingest.g2b_price_raw "
                "ORDER BY section_code, page_no"
            )
        raw_rows = cur.fetchall()
    pg.commit()

    print(f"[REBUILD] raw 페이지 {len(raw_rows)}개  삭제={deleted if deleted >= 0 else 'TRUNCATE'}")

    total_ins = total_upd = total_rej = 0
    counts: dict[str, dict] = {}

    for raw_id, sc, page_no, response_body in raw_rows:
        cfg = SECTIONS.get(sc)
        if not cfg:
            print(f"  [SKIP] 알 수 없는 섹션: {sc}")
            continue
        mapper  = MAPPERS[cfg["mapper"]]
        biz_div = cfg["biz_div"]

        items, _ = extract_items(response_body)
        norm_rows, rej_items = [], []
        for it in items:
            try:
                r = mapper(it, sc, biz_div)
                if r is None:
                    rej_items.append((it, "필수 필드 누락"))
                else:
                    norm_rows.append(r)
            except Exception as ex:
                rej_items.append((it, str(ex)))

        with pg.cursor() as cur:
            p_ins, p_upd = save_normalized(cur, raw_id, norm_rows)
            for it, msg in rej_items:
                save_reject(cur, sc, raw_id, it, msg)
        pg.commit()

        total_ins += p_ins
        total_upd += p_upd
        total_rej += len(rej_items)
        c = counts.setdefault(sc, {"ins": 0, "upd": 0, "rej": 0})
        c["ins"] += p_ins
        c["upd"] += p_upd
        c["rej"] += len(rej_items)

        print(f"  [{sc}] p{page_no}  ins={p_ins}  upd={p_upd}  rej={len(rej_items)}",
              end="\r", flush=True)

    print()
    print(f"[REBUILD] 완료  ins={total_ins:,}  upd={total_upd:,}  rej={total_rej}")
    return {"ins": total_ins, "upd": total_upd, "rej": total_rej, "by_section": counts}


# ── 섹션 수집 ────────────────────────────────────────────────────────────────

def collect_section(api_key: str, pg: psycopg2.extensions.connection,
                    section_code: str, max_pages: int | None,
                    dry_run: bool, run_date: str) -> dict:
    cfg       = SECTIONS[section_code]
    endpoint  = cfg["endpoint"]
    biz_div   = cfg["biz_div"]
    mapper    = MAPPERS[cfg["mapper"]]
    optional  = cfg.get("optional", False)

    print(f"\n[{section_code}] {biz_div}")

    try:
        first = fetch_page(api_key, endpoint, 1)
    except RuntimeError as e:
        if optional and "404" in str(e):
            print(f"  [SKIP] {e}")
            return {"section": section_code, "status": "skipped", "total_api": 0,
                    "raw_saved": 0, "norm_ins": 0, "norm_upd": 0, "rejected": 0}
        print(f"  [ERROR] {e}")
        return {"section": section_code, "status": "error", "total_api": 0,
                "raw_saved": 0, "norm_ins": 0, "norm_upd": 0, "rejected": 0}

    items0, total_count = extract_items(first)
    total_pages = max(1, (total_count + NUM_ROWS - 1) // NUM_ROWS)
    if max_pages:
        total_pages = min(total_pages, max_pages)
    print(f"  totalCount={total_count:,}  pages={total_pages}")

    if dry_run:
        sample = items0[:1]
        print(f"  [DRY-RUN] 샘플 item: {json.dumps(sample, ensure_ascii=False)[:300]}")
        mapped = mapper(sample[0], section_code, biz_div) if sample else {}
        print(f"  [DRY-RUN] 매핑 결과: {mapped}")
        return {"section": section_code, "status": "dry-run", "total_api": total_count,
                "raw_saved": 0, "norm_ins": 0, "norm_upd": 0, "rejected": 0}

    total_api = raw_saved = norm_ins = norm_upd = rejected = 0
    params_dict = {"pageNo": 1, "numOfRows": NUM_ROWS, "type": "json"}

    for page in range(1, total_pages + 1):
        try:
            data = first if page == 1 else fetch_page(api_key, endpoint, page)
            items, _ = extract_items(data)
        except Exception as e:
            print(f"\n  [WARN] p{page} 실패: {e}")
            continue

        params_dict["pageNo"] = page

        with pg.cursor() as cur:
            raw_id = save_raw(
                cur, endpoint=endpoint, section_code=section_code,
                page=page, params_dict=params_dict,
                response=data, run_date=run_date,
            )
            if raw_id is None:
                print(f"  p{page} raw 중복 skip", end="\r", flush=True)
                total_api += len(items)
                pg.commit()
                if page < total_pages:
                    time.sleep(SLEEP_SEC)
                continue

            norm_rows = []
            for it in items:
                try:
                    r = mapper(it, section_code, biz_div)
                    if r is None:
                        save_reject(cur, section_code, raw_id, it, "필수 필드 누락")
                        rejected += 1
                    else:
                        norm_rows.append(r)
                except Exception as ex:
                    save_reject(cur, section_code, raw_id, it, str(ex))
                    rejected += 1

            p_ins, p_upd = save_normalized(cur, raw_id, norm_rows)
            pg.commit()

        total_api += len(items)
        raw_saved += 1
        norm_ins  += p_ins
        norm_upd  += p_upd

        print(f"  p{page}/{total_pages}  api={len(items)}"
              f"  ins={p_ins}  upd={p_upd}  rej={rejected}",
              end="\r", flush=True)
        if page < total_pages:
            time.sleep(SLEEP_SEC)

    print(f"  완료  api={total_api:,}  raw={raw_saved}  "
          f"ins={norm_ins:,}  upd={norm_upd:,}  rej={rejected}")
    return {
        "section":   section_code,
        "status":    "ok",
        "total_api": total_api,
        "raw_saved": raw_saved,
        "norm_ins":  norm_ins,
        "norm_upd":  norm_upd,
        "rejected":  rejected,
    }


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="조달청 PriceInfoService 서버 수집기")
    ap.add_argument("--env-file",         default="")
    ap.add_argument("--section",          choices=list(SECTIONS), default=None,
                    help="특정 섹션만 수집 (미지정=전체)")
    ap.add_argument("--pages",            type=int, default=None,
                    help="섹션당 최대 페이지 (테스트용)")
    ap.add_argument("--dry-run",          action="store_true")
    ap.add_argument("--rebuild-from-raw", action="store_true",
                    help="API 재호출 없이 raw_ingest 기준 normalized 재생성")
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

    pg = pg_connect()

    # ── rebuild-from-raw 모드 ─────────────────────────────────────────────────
    if args.rebuild_from_raw:
        print(f"[REBUILD] raw_ingest 기준 재생성  section={args.section or '전체'}")
        result = rebuild_from_raw(pg, section_code=args.section)
        pg.close()

        print("\n" + "=" * 60)
        for sc, c in result["by_section"].items():
            print(f"  {sc:<22} ins={c['ins']:>7,}  upd={c['upd']:>7,}  rej={c['rej']:>5}")
        print("=" * 60)
        return

    # ── 일반 API 수집 모드 ────────────────────────────────────────────────────
    api_key = os.environ.get("G2B_API_KEY") or os.environ.get("NARA_PRICE_API_KEY")
    if not api_key:
        print("[ERROR] G2B_API_KEY 또는 NARA_PRICE_API_KEY 없음", file=sys.stderr)
        sys.exit(1)

    run_date = date.today().strftime("%Y%m%d")
    print(f"[COLLECT] 시작  run_date={run_date}  api_key={mask(api_key)}"
          f"  dry_run={args.dry_run}")

    if args.dry_run:
        pg.close()
        pg = None

    sections = [args.section] if args.section else list(SECTIONS)
    results  = []

    for sc in sections:
        r = collect_section(
            api_key, pg, sc,
            max_pages=args.pages,
            dry_run=args.dry_run,
            run_date=run_date,
        )
        results.append(r)
        time.sleep(SLEEP_SEC)

    if pg:
        pg.close()

    # 최종 요약
    print("\n" + "=" * 60)
    print(f"{'섹션':<22} {'상태':<10} {'API':>7} {'raw':>5} {'ins':>7} {'upd':>7} {'rej':>5}")
    print("-" * 60)
    for r in results:
        print(f"{r['section']:<22} {r['status']:<10} "
              f"{r['total_api']:>7,} {r['raw_saved']:>5} "
              f"{r['norm_ins']:>7,} {r['norm_upd']:>7,} {r['rejected']:>5}")
    print("=" * 60)

    total_ins = sum(r["norm_ins"] for r in results)
    total_upd = sum(r["norm_upd"] for r in results)
    total_api = sum(r["total_api"] for r in results)
    print(f"[COLLECT] 전체  api={total_api:,}  ins={total_ins:,}  upd={total_upd:,}")


if __name__ == "__main__":
    main()
