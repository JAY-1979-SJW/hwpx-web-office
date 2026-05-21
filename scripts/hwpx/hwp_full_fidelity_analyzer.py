"""HWP OLE analysis pipeline for independent full-fidelity conversion."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import olefile

from extract_hwp_body_fields import (
    HWP_RECORD_TAGS,
    HWP_SIGNATURE,
    decompress_if_needed,
    extract_hwp_text,
    iter_records,
    read_file_header,
)
from hwp_full_fidelity_audit import build_record_audit, build_source_manifest, read_ole_metadata
from hwp_full_fidelity_coverage import build_coverage
from hwp_full_fidelity_decoders import decode_known_record
from hwp_full_fidelity_header import build_decoded_docinfo
from hwp_full_fidelity_layouts import build_body_layout, build_equation_layout, build_page_layout, build_shape_layout, build_table_layout
from hwp_to_hwpx_standalone import file_snapshot


ENGINE_VERSION = 1


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _record_name(tag_id: int) -> str:
    return HWP_RECORD_TAGS.get(tag_id, f"UNKNOWN_{tag_id}")


def _read_ole_records(ole: olefile.OleFileIO, stream_name: str, compressed: bool) -> list[dict[str, Any]]:
    raw = ole.openstream(stream_name).read()
    data = decompress_if_needed(raw, compressed)
    records = []
    for index, (tag_id, level, payload) in enumerate(iter_records(data)):
        record = {
            "index": index,
            "tag_id": tag_id,
            "tag_name": _record_name(tag_id),
            "level": level,
            "payload_size": len(payload),
            "payload_prefix_hex": payload[:32].hex(" "),
        }
        decoded = decode_known_record(tag_id, payload)
        if decoded is not None:
            record["decoded"] = decoded
        records.append(record)
    return records


def analyze_hwp(path: Path, *, include_records: bool = False) -> dict[str, Any]:
    path = Path(path).expanduser().resolve()
    snapshot = file_snapshot(path)
    if not path.exists():
        return {
            "status": "FAIL",
            "error": "INPUT_NOT_FOUND",
            "input": str(path),
            "input_info": snapshot,
        }
    if path.read_bytes()[:8] != HWP_SIGNATURE:
        return {
            "status": "FAIL",
            "error": "INPUT_NOT_HWP",
            "input": str(path),
            "input_info": snapshot,
        }

    try:
        ole = olefile.OleFileIO(str(path))
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "FAIL",
            "error": "OLE_OPEN_FAILED",
            "error_message": str(exc),
            "input": str(path),
            "input_info": snapshot,
        }

    with ole:
        header = read_file_header(ole)
        if header.get("encrypted"):
            return {
                "status": "FAIL",
                "error": "ENCRYPTED_HWP",
                "input": str(path),
                "input_info": snapshot,
                "header": header,
            }

        streams = sorted("/".join(item) for item in ole.listdir(streams=True, storages=False))
        section_names = [
            name
            for name in streams
            if name.startswith("BodyText/Section")
        ]
        docinfo_records: list[dict[str, Any]] = []
        body_records_by_section: dict[str, list[dict[str, Any]]] = {}
        counts: Counter[int] = Counter()

        if "DocInfo" in streams:
            docinfo_records = _read_ole_records(ole, "DocInfo", bool(header.get("compressed")))
            counts.update(record["tag_id"] for record in docinfo_records)
        for name in section_names:
            records = _read_ole_records(ole, name, bool(header.get("compressed")))
            body_records_by_section[name] = records
            counts.update(record["tag_id"] for record in records)

        bindata_streams = [name for name in streams if name.startswith("BinData/")]
        source_manifest = build_source_manifest(ole, snapshot, streams)
        ole_metadata = read_ole_metadata(ole)
        extraction = extract_hwp_text(path)
        decoded_docinfo = build_decoded_docinfo(docinfo_records)
        body_layout = build_body_layout(body_records_by_section)
        page_layout = build_page_layout(body_records_by_section)
        table_layout = build_table_layout(body_records_by_section)
        shape_layout = build_shape_layout(body_records_by_section)
        equation_layout = build_equation_layout(body_records_by_section)
        coverage = build_coverage(counts, bindata_streams, extraction, decoded_docinfo, body_layout, page_layout, table_layout, shape_layout, equation_layout)
        record_audit = build_record_audit(docinfo_records, body_records_by_section, bindata_streams)
        report: dict[str, Any] = {
            "status": "PASS",
            "tool": "hwp_full_fidelity_converter",
            "schema_version": ENGINE_VERSION,
            "generated_at": _iso_now(),
            "input": str(path),
            "input_info": snapshot,
            "header": header,
            "stream_count": len(streams),
            "streams": streams,
            "source_manifest": source_manifest,
            "docinfo_record_count": len(docinfo_records),
            "section_count": len(section_names),
            "record_counts": {str(tag): count for tag, count in sorted(counts.items())},
            "record_tag_names": {str(tag): _record_name(tag) for tag in sorted(counts)},
            "bindata_streams": bindata_streams,
            "ole_metadata": ole_metadata,
            "decoded_docinfo": decoded_docinfo,
            "body_layout": body_layout,
            "page_layout": page_layout,
            "table_layout": table_layout,
            "shape_layout": shape_layout,
            "equation_layout": equation_layout,
            "record_audit": record_audit,
            "text_extraction": {
                "ok": bool(extraction.get("ok")),
                "error": extraction.get("error", ""),
                "text_length": len(str(extraction.get("text") or "")),
                "section_count": len(extraction.get("sections", [])),
                "paragraph_count": sum(int(section.get("paragraphs") or 0) for section in extraction.get("sections", [])),
            },
            "coverage": coverage,
        }
        if include_records:
            report["docinfo_records"] = docinfo_records
            report["body_records"] = body_records_by_section
        return report
