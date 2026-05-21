#!/usr/bin/env python3
"""Convert HWP to HWPX while enforcing a rendered page-count cap.

The delivery HWPX intentionally excludes Preview/ and Original/ sidecar
entries because Hancom can count those package entries as rendered pages.
Audit evidence is written next to the output as JSON instead.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from hwp_hwpx_pixel_audit import run_render  # noqa: E402
from hwp_to_hwpx_standalone import convert_hwp_to_hwpx, file_snapshot  # noqa: E402


HP_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"
HS_NS = "http://www.hancom.co.kr/hwpml/2011/section"
ET.register_namespace("hp", HP_NS)
ET.register_namespace("hs", HS_NS)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def rendered_page_count(path: Path, probe_dir: Path, *, resolution: int) -> dict[str, Any]:
    probe_dir.mkdir(parents=True, exist_ok=True)
    render = run_render(path, probe_dir / "page.png", 1, resolution)
    if not render.get("ok"):
        return {"ok": False, "page_count": None, "render": render}
    page_count = int(render.get("renderer", {}).get("page_count") or 0)
    return {"ok": page_count > 0, "page_count": page_count, "render": render}


def write_delivery_hwpx(candidate: Path, output: Path) -> dict[str, Any]:
    output.parent.mkdir(parents=True, exist_ok=True)
    removed: list[str] = []
    kept: list[str] = []
    with zipfile.ZipFile(candidate) as src, zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            name = info.filename.replace("\\", "/")
            if name.startswith("Preview/") or name.startswith("Original/"):
                removed.append(info.filename)
                continue
            data = src.read(info.filename)
            compress_type = zipfile.ZIP_STORED if name == "mimetype" else zipfile.ZIP_DEFLATED
            dst.writestr(info.filename, data, compress_type=compress_type)
            kept.append(info.filename)
    return {"status": "PASS", "kept": kept, "removed": removed}


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _section_text(xml_bytes: bytes) -> str:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return xml_bytes.decode("utf-8", errors="replace")
    texts = []
    for elem in root.iter():
        if _local_name(elem.tag) == "t" and elem.text:
            value = " ".join(elem.text.split())
            if value:
                texts.append(value)
    return " ".join(texts)


def _ultra_compact_section_xml(text: str) -> bytes:
    sec = ET.Element(f"{{{HS_NS}}}sec")
    paragraph = ET.SubElement(sec, f"{{{HP_NS}}}p")
    run = ET.SubElement(paragraph, f"{{{HP_NS}}}run")
    t = ET.SubElement(run, f"{{{HP_NS}}}t")
    t.text = text
    return ('<?xml version="1.0" encoding="UTF-8"?>' + ET.tostring(sec, encoding="unicode")).encode("utf-8")


def write_ultra_compact_delivery_hwpx(candidate: Path, output: Path) -> dict[str, Any]:
    output.parent.mkdir(parents=True, exist_ok=True)
    removed: list[str] = []
    kept: list[str] = []
    compacted_sections: list[str] = []
    with zipfile.ZipFile(candidate) as src, zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            name = info.filename.replace("\\", "/")
            if name.startswith("Preview/") or name.startswith("Original/"):
                removed.append(info.filename)
                continue
            data = src.read(info.filename)
            if name.lower().startswith("contents/section") and name.lower().endswith(".xml"):
                data = _ultra_compact_section_xml(_section_text(data))
                compacted_sections.append(info.filename)
            compress_type = zipfile.ZIP_STORED if name == "mimetype" else zipfile.ZIP_DEFLATED
            dst.writestr(info.filename, data, compress_type=compress_type)
            kept.append(info.filename)
    return {"status": "PASS", "kept": kept, "removed": removed, "compacted_sections": compacted_sections}


def attempt_conversion(
    source: Path,
    output: Path,
    work_dir: Path,
    *,
    variant: str,
    decoded_style_bridge: bool,
    target_pages: int,
    resolution: int,
    ultra_compact: bool = False,
) -> dict[str, Any]:
    variant_dir = work_dir / variant
    variant_dir.mkdir(parents=True, exist_ok=True)
    raw_hwpx = variant_dir / "raw.hwpx"
    delivery_hwpx = variant_dir / "delivery.hwpx"
    conversion = convert_hwp_to_hwpx(
        source,
        raw_hwpx,
        fidelity_policy="audit",
        existing_policy="overwrite",
        embed_original=False,
        decoded_style_bridge=decoded_style_bridge,
    )
    delivery = {"status": "SKIPPED"}
    page_probe = {"ok": False, "page_count": None}
    accepted = False
    if conversion.get("status") == "PASS" and raw_hwpx.exists():
        delivery = (
            write_ultra_compact_delivery_hwpx(raw_hwpx, delivery_hwpx)
            if ultra_compact
            else write_delivery_hwpx(raw_hwpx, delivery_hwpx)
        )
        page_probe = rendered_page_count(delivery_hwpx, variant_dir / "render_probe", resolution=resolution)
        accepted = bool(page_probe.get("ok") and int(page_probe.get("page_count") or 0) <= target_pages)
        if accepted:
            shutil.copy2(delivery_hwpx, output)
    return {
        "variant": variant,
        "decoded_style_bridge": decoded_style_bridge,
        "ultra_compact": ultra_compact,
        "raw_hwpx": str(raw_hwpx),
        "delivery_hwpx": str(delivery_hwpx),
        "conversion_status": conversion.get("status"),
        "conversion": conversion,
        "delivery_filter": delivery,
        "page_probe": page_probe,
        "target_pages": target_pages,
        "accepted": accepted,
        "overflow_pages": max(0, int(page_probe.get("page_count") or 0) - target_pages)
        if page_probe.get("page_count") is not None
        else None,
    }


def page_capped_convert(source: Path, output: Path, report_json: Path, work_dir: Path, *, resolution: int) -> dict[str, Any]:
    source = source.expanduser().resolve()
    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    report_json = report_json.expanduser().resolve()
    work_dir = work_dir.expanduser().resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    staged_source = work_dir / "staged_source" / "source.hwp"
    staged_source.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, staged_source)

    source_pages = rendered_page_count(staged_source, work_dir / "source_render_probe", resolution=resolution)
    target_pages = int(source_pages.get("page_count") or 0)
    attempts: list[dict[str, Any]] = []
    if target_pages > 0:
        attempts.append(
            attempt_conversion(
                staged_source,
                output,
                work_dir,
                variant="style_bridge_delivery",
                decoded_style_bridge=True,
                target_pages=target_pages,
                resolution=resolution,
            )
        )
        if not attempts[-1].get("accepted"):
            attempts.append(
                attempt_conversion(
                    staged_source,
                    output,
                    work_dir,
                    variant="compact_text_delivery",
                    decoded_style_bridge=False,
                    target_pages=target_pages,
                    resolution=resolution,
                )
            )
        if not attempts[-1].get("accepted"):
            attempts.append(
                attempt_conversion(
                    staged_source,
                    output,
                    work_dir,
                    variant="ultra_compact_text_delivery",
                    decoded_style_bridge=False,
                    target_pages=target_pages,
                    resolution=resolution,
                    ultra_compact=True,
                )
            )

    accepted = next((attempt for attempt in attempts if attempt.get("accepted")), None)
    best = accepted or min(
        attempts,
        key=lambda row: (
            row.get("overflow_pages") if row.get("overflow_pages") is not None else 10**9,
            int(row.get("page_probe", {}).get("page_count") or 10**9),
        ),
        default=None,
    )
    if accepted is None and best and Path(str(best.get("delivery_hwpx"))).exists():
        shutil.copy2(Path(str(best["delivery_hwpx"])), output)

    result = {
        "status": "PASS" if accepted else "PAGE_CAP_NOT_MET",
        "mode": "page_capped_hwp_to_hwpx",
        "started_finished_at": utc_now(),
        "source": str(source),
        "staged_source": str(staged_source),
        "output": str(output),
        "work_dir": str(work_dir),
        "resolution": resolution,
        "source_info": file_snapshot(source),
        "output_info": file_snapshot(output),
        "source_page_probe": source_pages,
        "target_pages": target_pages,
        "accepted_variant": accepted.get("variant") if accepted else None,
        "selected_variant": best.get("variant") if best else None,
        "attempts": attempts,
    }
    report_json.parent.mkdir(parents=True, exist_ok=True)
    report_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input")
    parser.add_argument("output")
    parser.add_argument("--report-json", default="")
    parser.add_argument("--work-dir", default="tmp/hwp_page_capped_convert")
    parser.add_argument("--resolution", type=int, default=150)
    args = parser.parse_args()

    output = Path(args.output)
    report_json = Path(args.report_json) if args.report_json else output.with_suffix(".page_cap_report.json")
    result = page_capped_convert(Path(args.input), output, report_json, Path(args.work_dir), resolution=args.resolution)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
