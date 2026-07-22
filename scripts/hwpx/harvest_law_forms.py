"""법제처 국가법령정보 별표서식 메타데이터 수집기 (Phase 1 — 파일 없이 목록만).

open.law.go.kr OpenAPI(licbyl)로 전 별표/서식/별지 메타데이터를 페이지네이션으로 수집.
- 별표일련번호를 고유키로 완벽 중복제거.
- HWP 다운로드 링크·법령·부처·서식명 등 메타 확보.
- 결과를 JSONL 인덱스로 저장(다음 단계: HWP 다운로드 → 변환 → 카탈로그).

인증: OC(사용자 지정 인증키) — 환경변수 LAW_OC 또는 --oc.
예의: 호출 간 지연(rate limit) 준수.
"""
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = PROJECT_ROOT / "data" / "drafts" / "form_library"
API = "https://www.law.go.kr/DRF/lawSearch.do"
HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.law.go.kr/",
           "Accept": "application/json"}
KND_NAME = {1: "별표", 2: "서식", 3: "별지", 4: "별도", 5: "부록"}


def _log(m): print(m, flush=True)


def fetch_page(oc: str, knd: int, page: int, display: int = 100,
               retries: int = 3) -> dict:
    params = {"OC": oc, "target": "licbyl", "type": "JSON",
              "knd": str(knd), "display": str(display), "page": str(page)}
    url = API + "?" + urllib.parse.urlencode(params)
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"fetch failed p{page}: {last}")


def harvest(oc: str, knds: list[int], *, delay: float = 0.3,
            display: int = 100) -> dict:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    index_path = OUT_DIR / "law_forms_index.jsonl"
    seen: set[str] = set()   # 별표일련번호
    total_written = 0
    dup = 0
    t0 = time.time()

    with index_path.open("w", encoding="utf-8") as out:
        for knd in knds:
            first = fetch_page(oc, knd, 1, display)
            body = first.get("licBylSearch", {})
            total = int(body.get("totalCnt", 0) or 0)
            pages = (total + display - 1) // display
            _log(f"[{KND_NAME.get(knd, knd)}] 총 {total}건 · {pages}페이지")
            for page in range(1, pages + 1):
                data = first if page == 1 else fetch_page(oc, knd, page, display)
                rows = data.get("licBylSearch", {}).get("licbyl", [])
                if isinstance(rows, dict):
                    rows = [rows]
                for r in rows:
                    sid = str(r.get("별표일련번호") or "")
                    if not sid or sid in seen:
                        dup += 1
                        continue
                    seen.add(sid)
                    rec = {
                        "seq": sid,
                        "kind": r.get("별표종류"),
                        "name": r.get("별표명"),
                        "num": r.get("별표번호"),
                        "lawName": r.get("관련법령명"),
                        "lawId": r.get("관련법령ID"),
                        "ministry": r.get("소관부처명"),
                        "hwpLink": r.get("별표서식파일링크"),
                        "pdfLink": r.get("별표서식PDF파일링크"),
                        "promulDate": r.get("공포일자"),
                    }
                    out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    total_written += 1
                if page % 20 == 0:
                    el = time.time() - t0
                    _log(f"  [{KND_NAME.get(knd, knd)}] {page}/{pages}p · "
                         f"수집 {total_written} · 중복 {dup} · [{el:.0f}s]")
                time.sleep(delay)

    el = time.time() - t0
    stats = {"uniqueForms": total_written, "duplicates": dup,
             "kinds": [KND_NAME.get(k, k) for k in knds],
             "elapsedSec": round(el, 1), "index": str(index_path)}
    (OUT_DIR / "law_forms_harvest_stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    _log(f"[done] 고유 {total_written}건 · 중복 {dup} · {el/60:.1f}분")
    _log(f"[index] {index_path}")
    return stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--oc", default=os.environ.get("LAW_OC", ""))
    ap.add_argument("--knd", default="2,3",
                    help="쉼표구분: 1별표 2서식 3별지 4별도 5부록 (기본 서식+별지)")
    ap.add_argument("--delay", type=float, default=0.3)
    args = ap.parse_args()
    if not args.oc:
        raise SystemExit("OC 필요: --oc 또는 LAW_OC 환경변수")
    knds = [int(x) for x in args.knd.split(",") if x.strip()]
    harvest(args.oc, knds, delay=args.delay)


if __name__ == "__main__":
    main()
