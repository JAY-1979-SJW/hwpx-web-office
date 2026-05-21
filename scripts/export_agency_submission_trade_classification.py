from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any


def render_trade_classification(index: dict[str, Any]) -> str:
    lines: list[str] = [
        "# 공종별 시공사 제출서류 분류표",
        "",
        f"- 생성일: {date.today().isoformat()}",
        f"- 원본 인덱스: `{index.get('source', '')}`",
        f"- 공종 수: {index.get('trade_count', 0)}",
        "",
        "## 전체 공종",
        "",
        "| 번호 | 공종 | 대표 기관/분류 | 대표 제출처 | 서류 수 |",
        "|---:|---|---|---|---:|",
    ]

    for number, trade in enumerate(index.get("trades", []), start=1):
        lines.append(
            "| "
            + " | ".join(
                [
                    str(number),
                    trade["trade_name"],
                    ", ".join(trade.get("agencies", [])[:4]),
                    ", ".join(trade.get("submit_to", [])[:5]),
                    str(trade.get("document_count", 0)),
                ]
            )
            + " |"
        )

    for number, trade in enumerate(index.get("trades", []), start=1):
        lines.extend(
            [
                "",
                f"## {number}. {trade['trade_name']}",
                "",
                f"- 별칭: {', '.join(trade.get('aliases', []))}",
                f"- 기관/분류: {', '.join(trade.get('agencies', []))}",
                f"- 제출처: {', '.join(trade.get('submit_to', []))}",
                "",
                "### 대표 서류",
                "",
            ]
        )
        for document in trade.get("documents", []):
            lines.append(f"- {document}")

        lines.extend(["", "### 탐색 키워드", ""])
        lines.append(", ".join(trade.get("keywords", [])) or "-")

        fields = trade.get("fields", [])
        if fields:
            lines.extend(["", "### 주요 입력 필드", ""])
            lines.append(", ".join(fields))

    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/agency_submission_trade_index.json")
    parser.add_argument("--output", default="docs/agency_submission_trade_classification.md")
    args = parser.parse_args()

    index_path = Path(args.input)
    output_path = Path(args.output)
    index = json.loads(index_path.read_text(encoding="utf-8"))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_trade_classification(index), encoding="utf-8")
    print(f"wrote {output_path}")
    print(f"trade_count={index.get('trade_count', 0)}")


if __name__ == "__main__":
    main()
