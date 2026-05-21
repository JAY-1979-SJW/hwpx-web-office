from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


def normalize(value: str) -> str:
    return re.sub(r"\s+", "", value).lower()


def load_index(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def search(index: dict[str, Any], query: str) -> list[dict[str, Any]]:
    normalized_query = normalize(query)
    if not normalized_query:
        return []

    direct_hits = index.get("term_index", {}).get(normalized_query, [])
    scored: dict[str, dict[str, Any]] = {}

    for hit in direct_hits:
        trade_id = hit["trade_id"]
        scored.setdefault(
            trade_id,
            {"trade_id": trade_id, "trade_name": hit["trade_name"], "score": 0, "matches": []},
        )
        scored[trade_id]["score"] += 100
        scored[trade_id]["matches"].append(hit)

    for trade in index.get("trades", []):
        haystacks = {
            "document": trade.get("documents", []),
            "keyword": trade.get("keywords", []),
            "field": trade.get("fields", []),
            "agency": trade.get("agencies", []),
            "submit_to": trade.get("submit_to", []),
        }
        for match_type, values in haystacks.items():
            for value in values:
                normalized_value = normalize(str(value))
                if normalized_query not in normalized_value:
                    continue
                trade_id = trade["trade_id"]
                scored.setdefault(
                    trade_id,
                    {
                        "trade_id": trade_id,
                        "trade_name": trade["trade_name"],
                        "score": 0,
                        "matches": [],
                    },
                )
                scored[trade_id]["score"] += 10
                scored[trade_id]["matches"].append(
                    {
                        "type": match_type,
                        "value": value,
                        "trade_id": trade_id,
                        "trade_name": trade["trade_name"],
                    }
                )

    results = sorted(scored.values(), key=lambda item: (-item["score"], item["trade_name"]))
    for result in results:
        result["matches"] = dedupe_matches(result["matches"])[:20]
    return results


def dedupe_matches(matches: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, str]] = []
    for match in matches:
        key = (match["type"], match["value"])
        if key in seen:
            continue
        seen.add(key)
        out.append(match)
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("query")
    parser.add_argument("--index", default="data/agency_submission_trade_index.json")
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--format", choices=["text", "json", "markdown"], default="text")
    args = parser.parse_args()

    index = load_index(Path(args.index))
    results = search(index, args.query)[: args.limit]
    if args.format == "json":
        json.dump(
            {"query": args.query, "count": len(results), "results": results},
            sys.stdout,
            ensure_ascii=False,
            indent=2,
        )
        print()
        return

    if not results:
        print("검색 결과 없음")
        return

    if args.format == "markdown":
        print(f"# 검색 결과: {args.query}")
        print("")
        for result in results:
            print(f"## {result['trade_name']}")
            print("")
            print(f"- 점수: {result['score']}")
            print("- 일치 항목:")
            for match in result["matches"][:8]:
                print(f"  - {match['type']}: {match['value']}")
            print("")
        return

    for result in results:
        print(f"[{result['trade_name']}] score={result['score']}")
        for match in result["matches"][:8]:
            print(f"  - {match['type']}: {match['value']}")


if __name__ == "__main__":
    main()
