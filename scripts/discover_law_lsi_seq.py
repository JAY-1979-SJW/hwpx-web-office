from __future__ import annotations

import argparse
import csv
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path


LAW_URL = "https://www.law.go.kr/%EB%B2%95%EB%A0%B9/"


def fetch_text(url: str) -> tuple[str, str]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124",
            "Referer": "https://www.law.go.kr/",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        data = response.read()
        return response.geturl(), data.decode("utf-8", errors="replace")


def discover(name: str) -> dict[str, str]:
    url = LAW_URL + urllib.parse.quote(name.replace(" ", ""))
    final_url, text = fetch_text(url)
    patterns = [
        r"lsiSeq\s*[:=]\s*[\"']?(\d+)",
        r"lsInfoP\.do\?[^\"'>]*lsiSeq=(\d+)",
        r"lsiSeq=(\d+)",
    ]
    lsi_seq = ""
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            lsi_seq = match.group(1)
            break
    title_match = re.search(r"<title>(.*?)</title>", text, flags=re.DOTALL | re.IGNORECASE)
    page_title = re.sub(r"\s+", " ", title_match.group(1)).strip() if title_match else ""
    return {
        "law_name": name,
        "requested_url": url,
        "final_url": final_url,
        "lsi_seq": lsi_seq,
        "page_title": page_title,
        "html_bytes": str(len(text.encode("utf-8"))),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("law_names", nargs="+")
    parser.add_argument("--output", default="tmp/law_lsi_seq_discovery.json")
    args = parser.parse_args()

    rows = []
    for name in args.law_names:
        try:
            rows.append(discover(name))
        except Exception as exc:
            rows.append(
                {
                    "law_name": name,
                    "requested_url": "",
                    "final_url": "",
                    "lsi_seq": "",
                    "page_title": "",
                    "html_bytes": "0",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with output.with_suffix(".csv").open("w", encoding="utf-8-sig", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=sorted({key for row in rows for key in row}))
        writer.writeheader()
        writer.writerows(rows)
    for row in rows:
        print(f"{row['law_name']}\t{row.get('lsi_seq', '')}\t{row.get('error', '')}")


if __name__ == "__main__":
    main()
