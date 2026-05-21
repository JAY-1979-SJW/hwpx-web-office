from __future__ import annotations

import argparse
import csv
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


def slugify(value: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]+', "_", value).strip()
    cleaned = re.sub(r"\s+", "_", cleaned)
    return cleaned or "untitled"


def choose_extension(url: str, content_type: str, fallback: str) -> str:
    path = urllib.parse.urlparse(url).path.lower()
    suffix = Path(path).suffix
    if suffix in {".hwp", ".hwpx", ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip"}:
        return suffix
    content_type = content_type.lower()
    if "pdf" in content_type:
        return ".pdf"
    if "hwp" in content_type:
        return ".hwp"
    if "html" in content_type:
        return ".html"
    if "json" in content_type:
        return ".json"
    return fallback


def choose_extension_from_headers(url: str, headers: Any, fallback: str) -> str:
    disposition = headers.get("Content-Disposition", "")
    for pattern in (
        r"filename\*\s*=\s*[^']*''([^;]+)",
        r'filename\s*=\s*"([^"]+)"',
        r"filename\s*=\s*([^;]+)",
    ):
        match = re.search(pattern, disposition, flags=re.IGNORECASE)
        if not match:
            continue
        filename = urllib.parse.unquote(match.group(1).strip().strip('"'))
        suffix = Path(filename).suffix.lower()
        if suffix in {".hwp", ".hwpx", ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip"}:
            return suffix
    return choose_extension(url, headers.get("Content-Type", ""), fallback)


def download(url: str, output_base: Path, fallback_ext: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
            )
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = response.read()
            final_url = response.geturl()
            content_type = response.headers.get("Content-Type", "")
            extension = choose_extension_from_headers(final_url, response.headers, fallback_ext)
            output_path = output_base.with_suffix(extension)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(data)
            return {
                "status": "downloaded",
                "url": url,
                "final_url": final_url,
                "content_type": content_type,
                "path": str(output_path),
                "bytes": len(data),
                "error": "",
            }
    except Exception as exc:
        return {
            "status": "failed",
            "url": url,
            "final_url": "",
            "content_type": "",
            "path": "",
            "bytes": 0,
            "error": f"{type(exc).__name__}: {exc}",
        }


def iter_download_jobs(records: list[dict[str, Any]], output_dir: Path) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    for index, record in enumerate(records, start=1):
        agency = slugify(record.get("agency_group", "미분류"))
        document_set = slugify(record.get("document_set", f"record_{index}"))
        target_dir = output_dir / agency / f"{index:03d}_{document_set}"
        official_url = record.get("official_page_url", "")
        if official_url:
            jobs.append(
                {
                    "kind": "official_page",
                    "record": record,
                    "url": official_url,
                    "output_base": target_dir / "official_page",
                    "fallback_ext": ".html",
                }
            )
        form_url = record.get("form_link_url", "")
        if form_url and form_url.startswith("http"):
            jobs.append(
                {
                    "kind": "form_link",
                    "record": record,
                    "url": form_url,
                    "output_base": target_dir / "form",
                    "fallback_ext": ".bin",
                }
            )
    return jobs


def write_manifest(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    csv_path = path.with_suffix(".csv")
    with csv_path.open("w", encoding="utf-8-sig", newline="") as fp:
        writer = csv.DictWriter(
            fp,
            fieldnames=[
                "agency_group",
                "document_set",
                "kind",
                "status",
                "url",
                "final_url",
                "content_type",
                "path",
                "bytes",
                "error",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        default="data/agency_submission_verified_link_collection.json",
    )
    parser.add_argument(
        "--output-dir",
        default="tmp/agency_submission_verified_downloads",
    )
    parser.add_argument("--delay-seconds", type=float, default=0.5)
    args = parser.parse_args()

    source = json.loads(Path(args.input).read_text(encoding="utf-8"))
    output_dir = Path(args.output_dir)
    jobs = iter_download_jobs(source.get("records", []), output_dir)
    manifest_rows: list[dict[str, Any]] = []

    for job in jobs:
        result = download(job["url"], Path(job["output_base"]), job["fallback_ext"])
        record = job["record"]
        manifest_rows.append(
            {
                "agency_group": record.get("agency_group", ""),
                "document_set": record.get("document_set", ""),
                "kind": job["kind"],
                **result,
            }
        )
        time.sleep(args.delay_seconds)

    write_manifest(output_dir / "download_manifest.json", manifest_rows)
    downloaded = sum(1 for row in manifest_rows if row["status"] == "downloaded")
    failed = sum(1 for row in manifest_rows if row["status"] == "failed")
    print(f"jobs={len(jobs)} downloaded={downloaded} failed={failed}")
    print(f"output_dir={output_dir}")
    print(f"manifest={output_dir / 'download_manifest.json'}")


if __name__ == "__main__":
    main()
