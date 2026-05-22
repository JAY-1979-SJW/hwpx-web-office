"""
HWPX-FORM-INDEX-AND-RECOMMEND-01 — CLI

사용법:
    python scripts/ops/run_form_recommend.py --query "소방 완공검사 신청서"
    python scripts/ops/run_form_recommend.py --query "가스 신고" --top 5
    python scripts/ops/run_form_recommend.py --build-index   # 정적 JSON 인덱스 생성
    python scripts/ops/run_form_recommend.py --stats         # 인덱스 통계
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from hwpx.recognition_corpus.form_index import FormIndex, DEFAULT_JSONL, recommend

STATIC_INDEX_PATH = (
    PROJECT_ROOT / "data" / "reports"
    / "hwpx_form_type_classification" / "form_index_static.json"
)


def cmd_recommend(query: str, top_n: int) -> int:
    idx = FormIndex.load(DEFAULT_JSONL)
    results = idx.search(query, top_n)
    if not results:
        print("추천 결과 없음.")
        return 0
    print(f"\n[추천 서식] 쿼리: {query!r}  (상위 {len(results)}개)\n")
    for i, r in enumerate(results, 1):
        byeolji = f"  [별지 제{r.byeoljiNumber}호서식]" if r.byeoljiNumber else ""
        print(f"  {i:2d}. [{r.domain}] {r.formKind} — {r.formName}{byeolji}")
        print(f"      score={r.score:.3f}  매칭: {r.matchedTokens}")
    return 0


def cmd_build_index() -> int:
    idx = FormIndex.load(DEFAULT_JSONL)
    idx.export_static_index(STATIC_INDEX_PATH)
    print(f"[build] 정적 인덱스 → {STATIC_INDEX_PATH}")
    print(f"        {STATIC_INDEX_PATH.stat().st_size // 1024} KB")
    return 0


def cmd_stats() -> int:
    idx = FormIndex.load(DEFAULT_JSONL)
    s = idx.stats()
    print(f"\n[인덱스 통계]")
    print(f"  전체 서식: {s['totalForms']}개\n")
    print("  도메인별:")
    for d, c in s["domainCounts"].items():
        print(f"    {d}: {c}")
    print("\n  서식종류별:")
    for k, c in s["formKindCounts"].items():
        print(f"    {k}: {c}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="HWPX 서식 추천 CLI")
    ap.add_argument("--query", "-q", type=str, default="")
    ap.add_argument("--top",   "-n", type=int, default=10)
    ap.add_argument("--build-index", action="store_true")
    ap.add_argument("--stats",       action="store_true")
    ap.add_argument("--json",        action="store_true", help="JSON 출력")
    args = ap.parse_args()

    if args.build_index:
        return cmd_build_index()
    if args.stats:
        return cmd_stats()
    if not args.query:
        ap.print_help()
        return 1

    if args.json:
        idx = FormIndex.load(DEFAULT_JSONL)
        results = idx.search(args.query, args.top)
        print(json.dumps([r.to_dict() for r in results], ensure_ascii=False, indent=2))
        return 0

    return cmd_recommend(args.query, args.top)


if __name__ == "__main__":
    sys.exit(main())
