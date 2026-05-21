#!/usr/bin/env python3
"""Render HWP/HWPX pairs with Hancom and compare raster pixels."""

from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
import subprocess
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops


REPO_ROOT = Path(__file__).resolve().parents[2]
PS32 = Path(r"C:\Windows\SysWOW64\WindowsPowerShell\v1.0\powershell.exe")
RENDER_SCRIPT = REPO_ROOT / "scripts" / "hwpx" / "hancom_render_to_image.ps1"


def read_report(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    results = data.get("results")
    if results is None and data.get("input") and data.get("output"):
        results = [data]
    if results is None and data.get("source") and data.get("output"):
        results = [{"input": data.get("source"), "output": data.get("output")}]
    if not isinstance(results, list):
        raise ValueError(f"results array not found: {path}")
    pairs: list[dict[str, Any]] = []
    for index, row in enumerate(results, 1):
        source = Path(str(row.get("input") or row.get("source") or ""))
        converted = Path(str(row.get("output") or ""))
        if source.exists() and converted.exists():
            pairs.append({"index": index, "source": source, "converted": converted})
    return pairs


def run_render(input_path: Path, output_path: Path, page: int, resolution: int) -> dict[str, Any]:
    command = [
        str(PS32),
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(RENDER_SCRIPT),
        "-InputPath",
        str(input_path),
        "-OutputPath",
        str(output_path),
        "-Page",
        str(page),
        "-Resolution",
        str(resolution),
    ]
    completed = subprocess.run(command, cwd=REPO_ROOT, text=True, capture_output=True, timeout=180)
    if completed.returncode != 0:
        return {
            "ok": False,
            "returncode": completed.returncode,
            "stdout": completed.stdout[-4000:],
            "stderr": completed.stderr[-4000:],
        }
    lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    payload = json.loads(lines[-1])
    return {"ok": True, "renderer": payload}


def padded_rgb(path: Path, size: tuple[int, int] | None = None) -> Image.Image:
    image = Image.open(path).convert("RGB")
    if size is None or image.size == size:
        return image
    canvas = Image.new("RGB", size, "white")
    canvas.paste(image, (0, 0))
    return canvas


def compare_images(left_path: Path, right_path: Path, threshold: int) -> dict[str, Any]:
    left_raw = Image.open(left_path).convert("RGB")
    right_raw = Image.open(right_path).convert("RGB")
    width = max(left_raw.width, right_raw.width)
    height = max(left_raw.height, right_raw.height)
    left = padded_rgb(left_path, (width, height))
    right = padded_rgb(right_path, (width, height))
    diff = ImageChops.difference(left, right)
    hist = diff.histogram()
    total_channels = width * height * 3
    abs_sum = sum((value % 256) * count for value, count in enumerate(hist))
    sq_sum = sum(((value % 256) * (value % 256)) * count for value, count in enumerate(hist))
    extrema = diff.getextrema()
    max_diff = max(channel[1] for channel in extrema)

    changed = 0
    pixels = diff.get_flattened_data() if hasattr(diff, "get_flattened_data") else diff.getdata()
    for pixel in pixels:
        if max(pixel) > threshold:
            changed += 1

    total_pixels = width * height
    changed_ratio = changed / total_pixels if total_pixels else 1.0
    mean_abs = abs_sum / total_channels if total_channels else 255.0
    rms = math.sqrt(sq_sum / total_channels) if total_channels else 255.0
    size_equal = left_raw.size == right_raw.size
    pixel_match_ratio = 1.0 - changed_ratio
    score = max(0.0, min(100.0, pixel_match_ratio * 100.0))
    if not size_equal:
        score = min(score, 90.0)
    return {
        "left_size": list(left_raw.size),
        "right_size": list(right_raw.size),
        "canvas_size": [width, height],
        "size_equal": size_equal,
        "threshold": threshold,
        "total_pixels": total_pixels,
        "changed_pixels": changed,
        "changed_ratio": changed_ratio,
        "pixel_match_ratio": pixel_match_ratio,
        "mean_abs_diff": mean_abs,
        "rms_diff": rms,
        "max_channel_diff": max_diff,
        "pixel_score": score,
    }


def page_count_gate(hwp_render: dict[str, Any], hwpx_render: dict[str, Any]) -> dict[str, Any]:
    hwp_pages = int(hwp_render.get("renderer", {}).get("page_count") or 0)
    hwpx_pages = int(hwpx_render.get("renderer", {}).get("page_count") or 0)
    overflow = hwpx_pages > hwp_pages if hwp_pages > 0 and hwpx_pages > 0 else True
    return {
        "status": "FAIL" if overflow else "PASS",
        "hwp_page_count": hwp_pages,
        "hwpx_page_count": hwpx_pages,
        "overflow": overflow,
        "overflow_pages": max(0, hwpx_pages - hwp_pages),
        "overflow_ratio": (hwpx_pages / hwp_pages) if hwp_pages > 0 else None,
        "rule": "HWPX page count must not exceed HWP page count",
    }


def audit(report_json: Path, output_dir: Path, limit: int, page: int, resolution: int, threshold: int) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    pairs = read_report(report_json)[:limit]
    rows: list[dict[str, Any]] = []
    for item in pairs:
        pair_dir = output_dir / f"pair_{item['index']:03d}"
        staged = pair_dir / "staged"
        rendered = pair_dir / "rendered"
        staged.mkdir(parents=True, exist_ok=True)
        rendered.mkdir(parents=True, exist_ok=True)
        staged_hwp = staged / "source.hwp"
        staged_hwpx = staged / "converted.hwpx"
        shutil.copy2(item["source"], staged_hwp)
        shutil.copy2(item["converted"], staged_hwpx)

        hwp_render = run_render(staged_hwp, rendered / "hwp.png", page, resolution)
        hwpx_render = run_render(staged_hwpx, rendered / "hwpx.png", page, resolution)
        row: dict[str, Any] = {
            "index": item["index"],
            "source": str(item["source"]),
            "converted": str(item["converted"]),
            "staged_hwp": str(staged_hwp),
            "staged_hwpx": str(staged_hwpx),
            "hwp_render": hwp_render,
            "hwpx_render": hwpx_render,
        }
        if hwp_render.get("ok") and hwpx_render.get("ok"):
            hwp_png = Path(hwp_render["renderer"]["output"])
            hwpx_png = Path(hwpx_render["renderer"]["output"])
            row["hwp_png"] = str(hwp_png)
            row["hwpx_png"] = str(hwpx_png)
            row["page_count_gate"] = page_count_gate(hwp_render, hwpx_render)
            row["pixel_compare"] = compare_images(hwp_png, hwpx_png, threshold)
            if row["page_count_gate"]["status"] != "PASS":
                row["status"] = "PAGE_OVERFLOW"
            elif row["pixel_compare"]["pixel_score"] >= 99.0:
                row["status"] = "PASS"
            else:
                row["status"] = "DIFF"
        else:
            row["status"] = "RENDER_FAIL"
        rows.append(row)

    scores = [
        row["pixel_compare"]["pixel_score"]
        for row in rows
        if isinstance(row.get("pixel_compare"), dict)
    ]
    summary = {
        "status": "PASS" if rows and all(row.get("status") == "PASS" for row in rows) else "DIFF_OR_FAIL",
        "mode": "hancom_print_to_image_pixel_audit",
        "report_json": str(report_json),
        "output_dir": str(output_dir),
        "requested_limit": limit,
        "audited_count": len(rows),
        "page": page,
        "resolution": resolution,
        "threshold": threshold,
        "score_min": min(scores) if scores else None,
        "score_avg": sum(scores) / len(scores) if scores else None,
        "score_max": max(scores) if scores else None,
        "rows": rows,
    }
    (output_dir / "pixel_audit_report.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    with (output_dir / "pixel_audit_summary.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "index",
                "status",
                "hwp_page_count",
                "hwpx_page_count",
                "overflow_pages",
                "overflow_ratio",
                "pixel_score",
                "changed_ratio",
                "changed_pixels",
                "total_pixels",
                "mean_abs_diff",
                "rms_diff",
                "max_channel_diff",
                "hwp_png",
                "hwpx_png",
            ],
        )
        writer.writeheader()
        for row in rows:
            compare = row.get("pixel_compare") if isinstance(row.get("pixel_compare"), dict) else {}
            page_gate = row.get("page_count_gate") if isinstance(row.get("page_count_gate"), dict) else {}
            writer.writerow(
                {
                    "index": row.get("index"),
                    "status": row.get("status"),
                    "hwp_page_count": page_gate.get("hwp_page_count"),
                    "hwpx_page_count": page_gate.get("hwpx_page_count"),
                    "overflow_pages": page_gate.get("overflow_pages"),
                    "overflow_ratio": page_gate.get("overflow_ratio"),
                    "pixel_score": compare.get("pixel_score"),
                    "changed_ratio": compare.get("changed_ratio"),
                    "changed_pixels": compare.get("changed_pixels"),
                    "total_pixels": compare.get("total_pixels"),
                    "mean_abs_diff": compare.get("mean_abs_diff"),
                    "rms_diff": compare.get("rms_diff"),
                    "max_channel_diff": compare.get("max_channel_diff"),
                    "hwp_png": row.get("hwp_png"),
                    "hwpx_png": row.get("hwpx_png"),
                }
            )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-json", default="tmp/hwp_final_document_table_audit_v34/conversion_report.json")
    parser.add_argument("--output-dir", default="tmp/hwp_pixel_audit_v1")
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--resolution", type=int, default=150)
    parser.add_argument("--threshold", type=int, default=3)
    args = parser.parse_args()

    result = audit(
        Path(args.report_json),
        Path(args.output_dir),
        args.limit,
        args.page,
        args.resolution,
        args.threshold,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
