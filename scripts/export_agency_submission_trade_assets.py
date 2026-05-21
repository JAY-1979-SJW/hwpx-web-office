from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any


def slugify(value: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]+', "_", value).strip()
    cleaned = re.sub(r"\s+", "_", cleaned)
    return cleaned or "untitled"


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def render_trade_markdown(trade: dict[str, Any]) -> str:
    lines = [
        f"# {trade['trade_name']} 제출서류",
        "",
        f"- 별칭: {', '.join(trade.get('aliases', []))}",
        f"- 기관/분류: {', '.join(trade.get('agencies', []))}",
        f"- 제출처: {', '.join(trade.get('submit_to', []))}",
        f"- 서류 수: {trade.get('document_count', 0)}",
        "",
        "## 대표 서류",
        "",
    ]
    for document in trade.get("documents", []):
        lines.append(f"- {document}")

    lines.extend(["", "## 탐색 키워드", ""])
    lines.append(", ".join(trade.get("keywords", [])) or "-")

    if trade.get("fields"):
        lines.extend(["", "## 주요 입력 필드", ""])
        lines.append(", ".join(trade.get("fields", [])))

    if trade.get("subcategories"):
        lines.extend(["", "## 하위 분류", ""])
        lines.append("| 하위분류 | 단계 | 대표 서류 | 구조 패턴 |")
        lines.append("|---|---|---|---|")
        for subcategory in trade["subcategories"]:
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(subcategory.get("name", "")),
                        ", ".join(subcategory.get("phase", [])),
                        ", ".join(subcategory.get("documents", [])),
                        ", ".join(subcategory.get("structure_patterns", [])),
                    ]
                )
                + " |"
            )

    if trade.get("sources"):
        lines.extend(["", "## 출처", ""])
        for source in trade["sources"]:
            lines.append(f"- {source}")

    return "\n".join(lines) + "\n"


def write_trade_csv(path: Path, trades: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fp:
        writer = csv.DictWriter(
            fp,
            fieldnames=[
                "trade_name",
                "document",
                "agencies",
                "submit_to",
                "keywords",
                "fields",
            ],
        )
        writer.writeheader()
        for trade in trades:
            for document in trade.get("documents", []):
                writer.writerow(
                    {
                        "trade_name": trade["trade_name"],
                        "document": document,
                        "agencies": "; ".join(trade.get("agencies", [])),
                        "submit_to": "; ".join(trade.get("submit_to", [])),
                        "keywords": "; ".join(trade.get("keywords", [])),
                        "fields": "; ".join(trade.get("fields", [])),
                    }
                )


def write_lookup_csv(path: Path, index: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fp:
        writer = csv.DictWriter(
            fp,
            fieldnames=["term", "match_type", "value", "trade_name", "trade_id"],
        )
        writer.writeheader()
        for term, hits in index.get("term_index", {}).items():
            for hit in hits:
                writer.writerow(
                    {
                        "term": term,
                        "match_type": hit["type"],
                        "value": hit["value"],
                        "trade_name": hit["trade_name"],
                        "trade_id": hit["trade_id"],
                    }
                )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/agency_submission_trade_index.json")
    parser.add_argument("--docs-dir", default="docs/agency_submission_trades")
    parser.add_argument("--data-dir", default="data/agency_submission_trades")
    parser.add_argument("--csv-output", default="data/agency_submission_trade_documents.csv")
    parser.add_argument("--lookup-csv-output", default="data/agency_submission_trade_lookup.csv")
    args = parser.parse_args()

    index = json.loads(Path(args.input).read_text(encoding="utf-8"))
    docs_dir = Path(args.docs_dir)
    data_dir = Path(args.data_dir)
    trades = index.get("trades", [])
    docs_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)

    for number, trade in enumerate(trades, start=1):
        prefix = f"{number:02d}_{slugify(trade['trade_name'])}"
        (docs_dir / f"{prefix}.md").write_text(render_trade_markdown(trade), encoding="utf-8")
        write_json(data_dir / f"{prefix}.json", trade)

    write_trade_csv(Path(args.csv_output), trades)
    write_lookup_csv(Path(args.lookup_csv_output), index)
    print(f"wrote {len(trades)} trade markdown files to {docs_dir}")
    print(f"wrote {len(trades)} trade json files to {data_dir}")
    print(f"wrote {args.csv_output}")
    print(f"wrote {args.lookup_csv_output}")


if __name__ == "__main__":
    main()
