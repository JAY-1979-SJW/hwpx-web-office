"""
collect_g2b_std_price.py  --  조달청 시설공통자재 단가 수집 → standard_price.db (SQLite)

API: 나라장터 PriceInfoService (가격정보현황서비스 v1.1)
  Base: https://apis.data.go.kr/1230000/ao/PriceInfoService
  엔드포인트 4개 (분야별):
    /getPriceInfoListFcltyCmmnMtrilBildng   건축
    /getPriceInfoListFcltyCmmnMtrilEngrk    토목
    /getPriceInfoListFcltyCmmnMtrilMchnEqp  기계설비
    /getPriceInfoListFcltyCmmnMtrilElctyIrmc 전기·정보통신

실행:
  G2B_API_KEY=xxx python collect_g2b_std_price.py
  python collect_g2b_std_price.py --env-file /home/ubuntu/app/g2b/.env.g2b
  python collect_g2b_std_price.py --pages 5 --dry-run          # 테스트 (각 분야 5페이지)
  python collect_g2b_std_price.py --category bildng             # 건축만
"""

import argparse, json, os, sqlite3, sys, time, urllib.request
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode

DEFAULT_DB = Path(os.environ.get("G2B_SQLITE_PATH",
                  str(Path(__file__).parent.parent / "data" / "standard_price.db")))
BASE_URL   = "https://apis.data.go.kr/1230000/ao/PriceInfoService"
NUM_ROWS   = 500
SLEEP_SEC  = 0.3   # 연속 호출 간격
RETRY_WAIT = 5.0   # 429 발생 시 대기

CATEGORIES = {
    "bildng":  ("getPriceInfoListFcltyCmmnMtrilBildng",  "시설자재(건축분야)",   "건축자재"),
    "engrk":   ("getPriceInfoListFcltyCmmnMtrilEngrk",   "시설자재(토목분야)",   "토목자재"),
    "mchn":    ("getPriceInfoListFcltyCmmnMtrilMchnEqp",  "시설자재(기계설비분야)", "기계자재"),
    "elcty":   ("getPriceInfoListFcltyCmmnMtrilElctyIrmc","시설자재(전기분야)",   "전기자재"),
}

DDL = """
CREATE TABLE IF NOT EXISTS g2b_price (
    prdct_clsfc_no  TEXT,
    prdct_nm        TEXT,
    prdct_idnt_no   TEXT    NOT NULL,
    unit            TEXT,
    price           REAL,
    delivery_cond   TEXT,
    supply_region   TEXT,
    dept_nm         TEXT,
    officer_nm      TEXT,
    officer_tel     TEXT,
    notice_date     TEXT    NOT NULL,
    vat_type        TEXT,
    biz_div         TEXT,
    work_type       TEXT,
    fetched_at      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now')),
    PRIMARY KEY (prdct_idnt_no, notice_date)
);
CREATE TABLE IF NOT EXISTS collect_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at      TEXT,
    category    TEXT,
    total_api   INTEGER,
    inserted    INTEGER,
    updated     INTEGER,
    status      TEXT,
    note        TEXT
);
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


def parse_date(raw: str | None) -> str | None:
    """YYYY-MM-DD HH:MM:SS 또는 YYYYMMDD → YYYY-MM-DD."""
    if not raw:
        return None
    raw = raw.strip()
    if len(raw) >= 10 and raw[4] == "-":
        return raw[:10]
    if len(raw) == 8 and raw.isdigit():
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
    return None


def to_real(val) -> float | None:
    if val is None or val == "":
        return None
    try:
        return float(str(val).replace(",", ""))
    except (ValueError, TypeError):
        return None


# ── API 호출 ──────────────────────────────────────────────────────────────────

def fetch_page(api_key: str, operation: str, page: int, retries: int = 3) -> dict:
    params = urlencode({
        "ServiceKey": api_key,
        "pageNo":     page,
        "numOfRows":  NUM_ROWS,
        "type":       "json",
    })
    url = f"{BASE_URL}/{operation}?{params}"
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = RETRY_WAIT * (attempt + 1)
                print(f"\n  [WARN] 429 rate limit — {wait:.0f}s 대기", flush=True)
                time.sleep(wait)
            elif e.code == 404:
                raise RuntimeError(f"404: 엔드포인트 없음 {operation}") from e
            else:
                raise
    raise RuntimeError(f"최대 재시도 초과 ({operation} p{page})")


def extract_items(data: dict) -> tuple[list[dict], int]:
    try:
        body = data["response"]["body"]
        total = int(body.get("totalCount", 0))
        items = body.get("items") or []
        if isinstance(items, dict):
            items = items.get("item", [])
        if isinstance(items, dict):
            items = [items]
        return (items if isinstance(items, list) else []), total
    except (KeyError, TypeError):
        return [], 0


def row_from_item(item: dict, biz_div: str, work_type: str) -> dict | None:
    notice_date   = parse_date(item.get("nticeDt"))
    prdct_idnt_no = str(item.get("prdctIdntNo") or "").strip()
    if not notice_date or not prdct_idnt_no:
        return None
    return {
        "prdct_clsfc_no": item.get("prdctClsfcNo"),
        "prdct_nm":       item.get("krnPrdctNm") or item.get("prdctClsfcNoNm"),
        "prdct_idnt_no":  prdct_idnt_no,
        "unit":           item.get("unit"),
        "price":          to_real(item.get("prce")),
        "delivery_cond":  item.get("dlvryCndtnNm"),
        "supply_region":  item.get("splyJrsdctRgnNm"),
        "dept_nm":        item.get("invstDeptNm"),
        "officer_nm":     item.get("invstOfclNm"),
        "officer_tel":    item.get("invstDeptTelNo"),
        "notice_date":    notice_date,
        "vat_type":       item.get("vatYnNm"),
        "biz_div":        biz_div,
        "work_type":      work_type,
    }


# ── SQLite 저장 ───────────────────────────────────────────────────────────────

def open_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.executescript(DDL)
    # 기존 테이블에 fetched_at 없으면 추가
    cols = {r[1] for r in conn.execute("PRAGMA table_info(g2b_price)")}
    if "fetched_at" not in cols:
        conn.execute("ALTER TABLE g2b_price ADD COLUMN fetched_at TEXT")
    conn.commit()
    return conn


def upsert_rows(conn: sqlite3.Connection, rows: list[dict]) -> tuple[int, int]:
    inserted = updated = 0
    cur = conn.cursor()
    for r in rows:
        cur.execute(
            "SELECT rowid FROM g2b_price WHERE prdct_idnt_no=? AND notice_date=?",
            (r["prdct_idnt_no"], r["notice_date"]),
        )
        if cur.fetchone():
            cur.execute("""
                UPDATE g2b_price SET
                    prdct_clsfc_no=?, prdct_nm=?, unit=?, price=?,
                    delivery_cond=?, supply_region=?, dept_nm=?,
                    officer_nm=?, officer_tel=?, vat_type=?, biz_div=?,
                    work_type=?, fetched_at=strftime('%Y-%m-%dT%H:%M:%S','now')
                WHERE prdct_idnt_no=? AND notice_date=?
            """, (
                r["prdct_clsfc_no"], r["prdct_nm"], r["unit"], r["price"],
                r["delivery_cond"], r["supply_region"], r["dept_nm"],
                r["officer_nm"], r["officer_tel"], r["vat_type"], r["biz_div"],
                r["work_type"], r["prdct_idnt_no"], r["notice_date"],
            ))
            updated += 1
        else:
            cur.execute("""
                INSERT INTO g2b_price (
                    prdct_clsfc_no, prdct_nm, prdct_idnt_no, unit, price,
                    delivery_cond, supply_region, dept_nm, officer_nm, officer_tel,
                    notice_date, vat_type, biz_div, work_type
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                r["prdct_clsfc_no"], r["prdct_nm"], r["prdct_idnt_no"], r["unit"], r["price"],
                r["delivery_cond"], r["supply_region"], r["dept_nm"], r["officer_nm"], r["officer_tel"],
                r["notice_date"], r["vat_type"], r["biz_div"], r["work_type"],
            ))
            inserted += 1
    conn.commit()
    return inserted, updated


def write_log(conn, *, category, total_api, inserted, updated, status, note=""):
    conn.execute(
        "INSERT INTO collect_log (run_at,category,total_api,inserted,updated,status,note) VALUES (?,?,?,?,?,?,?)",
        (datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"), category, total_api, inserted, updated, status, note),
    )
    conn.commit()


# ── 분야별 수집 ───────────────────────────────────────────────────────────────

def collect_category(api_key: str, conn: sqlite3.Connection,
                     category: str, max_pages: int | None, dry_run: bool) -> dict:
    operation, biz_div, work_type = CATEGORIES[category]
    print(f"\n[{category.upper()}] {biz_div}  ({operation})")

    try:
        first = fetch_page(api_key, operation, 1)
    except Exception as e:
        print(f"  [ERROR] {e}")
        return {"category": category, "total_api": 0, "inserted": 0, "updated": 0, "status": "error"}

    items0, total_count = extract_items(first)
    total_pages = (total_count + NUM_ROWS - 1) // NUM_ROWS
    if max_pages:
        total_pages = min(total_pages, max_pages)
    print(f"  totalCount={total_count:,}  pages={total_pages}")

    if dry_run:
        print(f"  [DRY-RUN] 샘플: {json.dumps(items0[:1], ensure_ascii=False)[:200]}")
        return {"category": category, "total_api": total_count, "inserted": 0, "updated": 0, "status": "dry-run"}

    total_ins = total_upd = total_api = 0
    for page in range(1, total_pages + 1):
        try:
            data   = first if page == 1 else fetch_page(api_key, operation, page)
            items, _ = extract_items(data)
        except Exception as e:
            print(f"\n  [WARN] p{page} 실패: {e}")
            continue

        rows = [row_from_item(it, biz_div, work_type) for it in items]
        rows = [r for r in rows if r]
        ins, upd = upsert_rows(conn, rows)
        total_ins  += ins
        total_upd  += upd
        total_api  += len(items)
        print(f"  p{page}/{total_pages}  api={len(items)}  ins={ins}  upd={upd}", end="\r", flush=True)
        if page < total_pages:
            time.sleep(SLEEP_SEC)

    write_log(conn, category=category, total_api=total_api,
              inserted=total_ins, updated=total_upd, status="success")
    print(f"  완료  api={total_api:,}  ins={total_ins:,}  upd={total_upd:,}")
    return {"category": category, "total_api": total_api, "inserted": total_ins, "updated": total_upd, "status": "ok"}


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db",       default=str(DEFAULT_DB))
    ap.add_argument("--env-file", default="")
    ap.add_argument("--pages",    type=int, default=None, help="각 분야 최대 페이지 수 (테스트용)")
    ap.add_argument("--category", choices=list(CATEGORIES.keys()),
                    default=None, help="특정 분야만 수집 (미지정=전체)")
    ap.add_argument("--dry-run",  action="store_true")
    args = ap.parse_args()

    if args.env_file:
        load_env_file(args.env_file)

    api_key = os.environ.get("G2B_API_KEY") or os.environ.get("NARA_PRICE_API_KEY")
    if not api_key:
        print("[ERROR] G2B_API_KEY 또는 NARA_PRICE_API_KEY 환경변수 없음", file=sys.stderr)
        sys.exit(1)

    db_path = Path(args.db)
    conn = open_db(db_path)
    before = conn.execute("SELECT COUNT(*) FROM g2b_price").fetchone()[0]
    print(f"[COLLECT] 시작  db={db_path}  기존={before:,}행  dry_run={args.dry_run}")

    cats = [args.category] if args.category else list(CATEGORIES.keys())
    results = []
    for cat in cats:
        r = collect_category(api_key, conn, cat, max_pages=args.pages, dry_run=args.dry_run)
        results.append(r)
        time.sleep(SLEEP_SEC)

    after = conn.execute("SELECT COUNT(*) FROM g2b_price").fetchone()[0]
    conn.close()

    total_ins = sum(r["inserted"] for r in results)
    total_upd = sum(r["updated"] for r in results)
    print(f"\n[COLLECT] 전체 완료  ins={total_ins:,}  upd={total_upd:,}  SQLite {before:,} → {after:,}  (순증 {after-before:+,})")


if __name__ == "__main__":
    main()
