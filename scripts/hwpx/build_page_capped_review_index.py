#!/usr/bin/env python3
"""Build a local HTML review index for page-capped HWPX conversions."""

from __future__ import annotations

import argparse
import csv
import html
from pathlib import Path


def file_url(path: str) -> str:
    return Path(path).resolve().as_uri()


def risk_label(row: dict[str, str]) -> tuple[str, str]:
    variant = row.get("selected_variant", "")
    target = int(row.get("target_pages") or 0)
    actual = int(row.get("hwpx_page_count") or 0)
    if variant == "style_bridge_delivery":
        return "상", "good"
    if variant == "compact_text_delivery" and actual == target:
        return "중상", "ok"
    if variant == "compact_text_delivery":
        return "중", "warn"
    return "낮음", "bad"


def build_html(rows: list[dict[str, str]], output: Path) -> None:
    cards = []
    for idx, row in enumerate(rows, 1):
        quality, klass = risk_label(row)
        source = row.get("source", "")
        converted = row.get("output", "")
        source_name = Path(source).name
        converted_name = Path(converted).name
        target = row.get("target_pages", "")
        actual = row.get("hwpx_page_count", "")
        variant = row.get("selected_variant", "")
        cards.append(
            f"""
            <tr class="{klass}">
              <td>{idx}</td>
              <td><span class="pill {klass}">{html.escape(quality)}</span></td>
              <td>{html.escape(row.get("status", ""))}</td>
              <td>{html.escape(target)} -> {html.escape(actual)}</td>
              <td>{html.escape(variant)}</td>
              <td class="name">{html.escape(source_name)}</td>
              <td><a href="{file_url(source)}">HWP 원본</a></td>
              <td><a href="{file_url(converted)}">HWPX 변환본</a></td>
            </tr>
            """
        )
    total = len(rows)
    variants: dict[str, int] = {}
    for row in rows:
        variants[row.get("selected_variant", "")] = variants.get(row.get("selected_variant", ""), 0) + 1
    variant_text = ", ".join(f"{html.escape(k)} {v}개" for k, v in sorted(variants.items()))
    doc = f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <title>HWPX 변환 검토 인덱스</title>
  <style>
    body {{ font-family: Segoe UI, Malgun Gothic, sans-serif; margin: 24px; color: #1f2933; }}
    h1 {{ font-size: 22px; margin: 0 0 8px; }}
    .summary {{ margin: 0 0 18px; color: #52606d; }}
    table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
    th, td {{ border: 1px solid #d9e2ec; padding: 8px; vertical-align: top; }}
    th {{ background: #f0f4f8; text-align: left; position: sticky; top: 0; }}
    tr.good {{ background: #f0fff4; }}
    tr.ok {{ background: #f8fff0; }}
    tr.warn {{ background: #fffbea; }}
    tr.bad {{ background: #fff5f5; }}
    .pill {{ display: inline-block; min-width: 42px; text-align: center; border-radius: 4px; padding: 2px 6px; font-weight: 600; }}
    .pill.good {{ background: #2f855a; color: white; }}
    .pill.ok {{ background: #5f9f2f; color: white; }}
    .pill.warn {{ background: #b7791f; color: white; }}
    .pill.bad {{ background: #c53030; color: white; }}
    .name {{ max-width: 520px; word-break: break-all; }}
    a {{ color: #1a56db; }}
  </style>
</head>
<body>
  <h1>HWPX 변환 검토 인덱스</h1>
  <p class="summary">총 {total}개. 장수 초과 0개. 변환 방식: {variant_text}</p>
  <table>
    <thead>
      <tr>
        <th>#</th>
        <th>품질</th>
        <th>상태</th>
        <th>장수</th>
        <th>변환 방식</th>
        <th>파일명</th>
        <th>원본</th>
        <th>변환본</th>
      </tr>
    </thead>
    <tbody>
      {''.join(cards)}
    </tbody>
  </table>
</body>
</html>
"""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(doc, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary-csv", default="tmp/hwp_page_capped_batch_v3/summary.csv")
    parser.add_argument("--output", default="tmp/hwp_page_capped_batch_v3/review_index.html")
    args = parser.parse_args()
    with Path(args.summary_csv).open(encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    build_html(rows, Path(args.output))
    print(Path(args.output).resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
