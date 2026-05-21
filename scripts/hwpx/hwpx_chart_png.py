"""Small dependency-free PNG chart generator for HWPX composer jobs."""

from __future__ import annotations

import json
from pathlib import Path
import struct
import zlib
from typing import Any


Color = tuple[int, int, int]


PALETTE: list[Color] = [
    (52, 111, 204),
    (36, 150, 108),
    (220, 139, 48),
    (190, 70, 82),
    (114, 87, 180),
    (66, 151, 181),
]


def _chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def _encode_png(width: int, height: int, pixels: bytearray) -> bytes:
    raw = bytearray()
    stride = width * 3
    for y in range(height):
        raw.append(0)
        start = y * stride
        raw.extend(pixels[start : start + stride])
    return b"".join(
        [
            b"\x89PNG\r\n\x1a\n",
            _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)),
            _chunk(b"IDAT", zlib.compress(bytes(raw), level=9)),
            _chunk(b"IEND", b""),
        ]
    )


def _set_pixel(pixels: bytearray, width: int, height: int, x: int, y: int, color: Color) -> None:
    if x < 0 or y < 0 or x >= width or y >= height:
        return
    index = (y * width + x) * 3
    pixels[index : index + 3] = bytes(color)


def _fill_rect(pixels: bytearray, width: int, height: int, x0: int, y0: int, x1: int, y1: int, color: Color) -> None:
    left = max(0, min(x0, x1))
    right = min(width, max(x0, x1))
    top = max(0, min(y0, y1))
    bottom = min(height, max(y0, y1))
    for y in range(top, bottom):
        for x in range(left, right):
            _set_pixel(pixels, width, height, x, y, color)


def _draw_line(pixels: bytearray, width: int, height: int, x0: int, y0: int, x1: int, y1: int, color: Color) -> None:
    dx = abs(x1 - x0)
    sx = 1 if x0 < x1 else -1
    dy = -abs(y1 - y0)
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    x, y = x0, y0
    while True:
        _set_pixel(pixels, width, height, x, y, color)
        if x == x1 and y == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x += sx
        if e2 <= dx:
            err += dx
            y += sy


def normalize_chart_data(data: dict[str, Any]) -> dict[str, Any]:
    series = data.get("series", data.get("data", []))
    if not isinstance(series, list) or not series:
        raise ValueError("chart data requires non-empty series")
    normalized = []
    for index, item in enumerate(series):
        if isinstance(item, dict):
            label = str(item.get("label", f"item_{index + 1}"))
            value = float(item["value"])
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            label = str(item[0])
            value = float(item[1])
        else:
            raise ValueError(f"invalid chart series item at index {index}")
        if value < 0:
            raise ValueError("negative chart values are not supported")
        normalized.append({"label": label, "value": value})
    return {
        "title": str(data.get("title", "")),
        "width": int(data.get("width", 640)),
        "height": int(data.get("height", 360)),
        "series": normalized,
    }


def generate_bar_chart_png(data: dict[str, Any], output: Path) -> dict[str, Any]:
    chart = normalize_chart_data(data)
    width = max(240, min(2400, chart["width"]))
    height = max(160, min(1600, chart["height"]))
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)

    bg = (255, 255, 255)
    grid = (224, 228, 235)
    axis = (60, 64, 72)
    pixels = bytearray(bg * (width * height))
    margin_left = max(36, width // 12)
    margin_right = max(20, width // 24)
    margin_top = max(24, height // 12)
    margin_bottom = max(36, height // 8)
    plot_left = margin_left
    plot_right = width - margin_right
    plot_top = margin_top
    plot_bottom = height - margin_bottom

    for i in range(6):
        y = plot_top + round((plot_bottom - plot_top) * i / 5)
        _draw_line(pixels, width, height, plot_left, y, plot_right, y, grid)
    _draw_line(pixels, width, height, plot_left, plot_top, plot_left, plot_bottom, axis)
    _draw_line(pixels, width, height, plot_left, plot_bottom, plot_right, plot_bottom, axis)

    values = [item["value"] for item in chart["series"]]
    max_value = max(values) or 1.0
    count = len(values)
    slot = max(1, (plot_right - plot_left) / count)
    bar_width = max(6, int(slot * 0.58))
    for index, item in enumerate(chart["series"]):
        bar_height = int((plot_bottom - plot_top) * (item["value"] / max_value))
        x0 = int(plot_left + slot * index + (slot - bar_width) / 2)
        x1 = x0 + bar_width
        y0 = plot_bottom - bar_height
        color = PALETTE[index % len(PALETTE)]
        _fill_rect(pixels, width, height, x0, y0, x1, plot_bottom, color)
        _fill_rect(pixels, width, height, x0, plot_bottom + 4, x1, plot_bottom + 8, color)

    output.write_bytes(_encode_png(width, height, pixels))
    return {
        "status": "PASS",
        "output": str(output),
        "width": width,
        "height": height,
        "series_count": count,
        "max_value": max_value,
        "labels": [item["label"] for item in chart["series"]],
        "size": output.stat().st_size,
    }


def generate_bar_chart_png_from_json(data_json: Path, output: Path) -> dict[str, Any]:
    return generate_bar_chart_png(json.loads(Path(data_json).read_text(encoding="utf-8")), output)


__all__ = ["generate_bar_chart_png", "generate_bar_chart_png_from_json", "normalize_chart_data"]
