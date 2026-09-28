#!/usr/bin/env python3
"""Standalone HWP -> HWPX converter.

This converter does not launch Hancom Office, COM, GUI automation, or an
external conversion program. It extracts text from binary HWP BodyText records
and rebuilds a valid text-only HWPX package.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib
import json
import logging
import re
import shutil
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4
from xml.sax.saxutils import escape

THIS_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = THIS_DIR.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

from extract_hwp_body_fields import extract_hwp_text  # ruff: ignore[module-import-not-at-top-of-file]

from hwpx_element_factory import create_table_paragraph  # ruff: ignore[module-import-not-at-top-of-file]
from hwpx_package import HwpxValidator  # ruff: ignore[module-import-not-at-top-of-file]
from hwpx_spine_repair import repair_hwpx_spine  # ruff: ignore[module-import-not-at-top-of-file]

LOGGER = logging.getLogger("hwp_to_hwpx")
MIMETYPE = "application/owpml"
HPF_MEDIA_TYPE = "application/hwpml-package+xml"
HP_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"
HS_NS = "http://www.hancom.co.kr/hwpml/2011/section"
ET.register_namespace("hp", HP_NS)
ET.register_namespace("hs", HS_NS)
EXISTING_POLICIES = ("fail", "skip", "rename", "overwrite")
FIDELITY_POLICIES = ("text", "audit", "strict")
AUDIT_LEVELS = ("standard", "forensic")
MOJIBAKE_MARKERS = (
    "嫄댁",
    "踰덊",
    "쒖",
    "먯",
    "섏",
    "덈",
    "낅",
    "댁",
    "뚯",
    "쓽",
    "뺤",
)


def configure_logging(
    log_path: Path | str | None = None,
    *,
    level: str = "INFO",
    console: bool = False,
) -> Path | None:
    numeric_level = getattr(logging, str(level or "INFO").upper(), logging.INFO)
    LOGGER.setLevel(numeric_level)
    LOGGER.propagate = False
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    if not LOGGER.handlers:
        LOGGER.addHandler(logging.NullHandler())
    if log_path:
        path = Path(log_path).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        if not any(
            isinstance(handler, logging.FileHandler) and Path(handler.baseFilename) == path
            for handler in LOGGER.handlers
        ):
            file_handler = logging.FileHandler(path, encoding="utf-8")
            file_handler.setLevel(numeric_level)
            file_handler.setFormatter(formatter)
            LOGGER.addHandler(file_handler)
        return path
    if console and not any(
        isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler)
        for handler in LOGGER.handlers
    ):
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(numeric_level)
        stream_handler.setFormatter(formatter)
        LOGGER.addHandler(stream_handler)
    return None


def default_log_path(input_path: Path, output_path: Path) -> Path:
    output_path = Path(output_path)
    return (
        output_path / "hwp2hwpx.log"
        if Path(input_path).is_dir()
        else output_path.parent / "hwp2hwpx.log"
    )


def default_audit_log_path(input_path: Path, output_path: Path) -> Path:
    output_path = Path(output_path)
    return (
        output_path / "hwp2hwpx_audit.jsonl"
        if Path(input_path).is_dir()
        else output_path.parent / "hwp2hwpx_audit.jsonl"
    )


def log_result(event: str, result: dict[str, Any]) -> None:
    status = str(result.get("status") or "UNKNOWN")
    message = (
        f"{event} status={status} input={result.get('input')} output={result.get('output')} "
        f"error={result.get('error')} paragraphs={result.get('paragraph_count')}"
    )
    if status == "PASS":
        LOGGER.info(message)
    elif status == "SKIP":
        LOGGER.warning(message)
    else:
        LOGGER.error(message)


def build_conversion_gate(
    report: dict[str, Any], *, strict_quality: bool = False
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add_check(name: str, passed: bool, **details: Any) -> None:
        checks.append({"name": name, "status": "PASS" if passed else "FAIL", **details})

    input_info = report.get("input_info") if isinstance(report.get("input_info"), dict) else {}
    output_info = report.get("output_info") if isinstance(report.get("output_info"), dict) else {}
    validation = report.get("validation") if isinstance(report.get("validation"), dict) else {}
    quality = report.get("text_quality") if isinstance(report.get("text_quality"), dict) else {}
    fidelity = report.get("fidelity_gate") if isinstance(report.get("fidelity_gate"), dict) else {}
    roundtrip = (
        report.get("roundtrip_text") if isinstance(report.get("roundtrip_text"), dict) else {}
    )
    table_grid = (
        report.get("table_grid_gate") if isinstance(report.get("table_grid_gate"), dict) else {}
    )
    bridge = (
        report.get("decoded_style_bridge")
        if isinstance(report.get("decoded_style_bridge"), dict)
        else {}
    )
    visual = (
        bridge.get("visual_object_mapping")
        if isinstance(bridge.get("visual_object_mapping"), dict)
        else {}
    )
    status = str(report.get("status") or "UNKNOWN")

    add_check(
        "input_snapshot",
        bool(input_info.get("exists") and input_info.get("sha256")),
        size=input_info.get("size"),
    )
    if status == "SKIP":
        add_check("skip_reason", bool(report.get("error")), error=report.get("error"))
        add_check(
            "existing_output_snapshot",
            bool(output_info.get("exists") and output_info.get("sha256")),
            size=output_info.get("size"),
        )
    else:
        add_check(
            "output_snapshot",
            status == "PASS" and bool(output_info.get("exists") and output_info.get("sha256")),
            size=output_info.get("size"),
        )
        add_check(
            "package_validation",
            status == "PASS"
            and validation.get("zip_ok") is True
            and validation.get("xml_ok") is True,
            validation=validation,
        )
        add_check(
            "text_quality",
            quality.get("status") == "PASS",
            errors=quality.get("errors"),
            warnings=quality.get("warnings"),
        )
        if roundtrip:
            add_check("roundtrip_text", roundtrip.get("status") == "PASS", roundtrip=roundtrip)
        if table_grid:
            add_check("table_grid", table_grid.get("status") == "PASS", table_grid=table_grid)
        if visual:
            picture_records = int(visual.get("picture_record_count") or 0)
            vector_records = int(visual.get("vector_shape_record_count") or 0)
            picture_ok = (
                int(visual.get("visible_picture_count") or 0)
                >= int(visual.get("target_picture_count") or 0)
                and int(visual.get("picture_geometry_mapped_count") or 0) >= picture_records
                and int(visual.get("picture_bindata_id_mapped_count") or 0) >= picture_records
                and int(visual.get("picture_position_mapped_count") or 0) >= picture_records
                and (
                    "picture_layout_policy_mapped_count" not in visual
                    or int(visual.get("picture_layout_policy_mapped_count") or 0) >= picture_records
                )
            )
            vector_ok = (
                int(visual.get("visible_vector_shape_count") or 0) >= vector_records
                and int(visual.get("geometry_mapped_vector_shape_count") or 0) >= vector_records
                and int(visual.get("position_mapped_vector_shape_count") or 0) >= vector_records
                and (
                    "layout_policy_mapped_vector_shape_count" not in visual
                    or int(visual.get("layout_policy_mapped_vector_shape_count") or 0)
                    >= vector_records
                )
                and int(visual.get("unmapped_vector_shape_record_count") or 0) == 0
            )
            add_check(
                "visual_objects",
                visual.get("status") in {"PASS", "NO_VISUAL_OBJECTS"} and picture_ok and vector_ok,
                visual_object_mapping=visual,
            )
        if fidelity:
            add_check(
                "fidelity_policy",
                fidelity.get("status") != "FAIL",
                fidelity_status=fidelity.get("status"),
                policy=fidelity.get("policy"),
                risks=fidelity.get("risks", []),
            )
        if strict_quality:
            add_check(
                "strict_quality",
                quality.get("status") == "PASS" and not quality.get("warnings"),
                warnings=quality.get("warnings"),
            )
    add_check("result_status", status in {"PASS", "SKIP"}, status=status, error=report.get("error"))

    failed = [check["name"] for check in checks if check["status"] != "PASS"]
    return {
        "status": "PASS" if not failed else "FAIL",
        "strict_quality": strict_quality,
        "checked_at": iso_now(),
        "failed_checks": failed,
        "checks": checks,
    }


def attach_conversion_gate(
    report: dict[str, Any], *, strict_quality: bool = False
) -> dict[str, Any]:
    report["conversion_gate"] = build_conversion_gate(report, strict_quality=strict_quality)
    return report


def build_batch_gate(report: dict[str, Any]) -> dict[str, Any]:
    results = report.get("results") if isinstance(report.get("results"), list) else []
    failed_items = [
        str(item.get("input") or item.get("output") or index)
        for index, item in enumerate(results)
        if isinstance(item, dict) and item.get("status") not in {"PASS", "SKIP"}
    ]
    failed_gates = [
        str(item.get("input") or item.get("output") or index)
        for index, item in enumerate(results)
        if isinstance(item, dict)
        and isinstance(item.get("conversion_gate"), dict)
        and item["conversion_gate"].get("status") != "PASS"
    ]
    checks = [
        {
            "name": "targets_present",
            "status": "PASS" if int(report.get("target_count") or 0) > 0 else "FAIL",
            "target_count": report.get("target_count"),
        },
        {
            "name": "all_results_successful",
            "status": "PASS" if not failed_items else "FAIL",
            "failed_items": failed_items,
        },
        {
            "name": "all_item_gates_passed",
            "status": "PASS" if not failed_gates else "FAIL",
            "failed_items": failed_gates,
        },
        {
            "name": "temp_cleanup",
            "status": "PASS" if not (report.get("temp_cleanup") or {}).get("failed") else "FAIL",
            "temp_cleanup": report.get("temp_cleanup"),
        },
    ]
    failed = [check["name"] for check in checks if check["status"] != "PASS"]
    return {
        "status": "PASS" if not failed else "FAIL",
        "checked_at": iso_now(),
        "failed_checks": failed,
        "checks": checks,
    }


def attach_batch_gate(report: dict[str, Any]) -> dict[str, Any]:
    report["conversion_gate"] = build_batch_gate(report)
    return report


def repair_output_package(path: Path, *, expected_text: str = "") -> dict[str, Any]:
    """Repair package sidecars/spine and validate roundtrip text atomically."""
    path = Path(path)
    if not path.exists():
        return {"status": "FAIL", "error": "OUTPUT_NOT_FOUND", "output": str(path)}
    repaired = path.with_name(f".repair.{uuid4().hex}.hwpx")
    backup = path.with_name(f".backup.{uuid4().hex}.hwpx")
    try:
        repair_report = repair_hwpx_spine(path, repaired)
        if repair_report.get("status") != "PASS":
            safe_unlink(repaired)
            return {"status": "FAIL", "error": "HWPX_SPINE_REPAIR_FAILED", "repair": repair_report}
        validation = HwpxValidator.validate_hwpx(repaired)
        roundtrip = (
            roundtrip_text_gate(expected_text, repaired) if expected_text else {"status": "SKIPPED"}
        )
        if (
            validation.get("zip_ok") is not True
            or validation.get("xml_ok") is not True
            or roundtrip.get("status") == "FAIL"
        ):
            safe_unlink(repaired)
            return {
                "status": "FAIL",
                "error": "REPAIRED_PACKAGE_VALIDATION_FAILED",
                "repair": repair_report,
                "validation": validation,
                "roundtrip_text": roundtrip,
            }
        try:
            path.replace(backup)
            repaired.replace(path)
            safe_unlink(backup)
        except OSError:
            shutil.copy2(repaired, path)
            safe_unlink(repaired)
            safe_unlink(backup)
        return {
            "status": "PASS",
            "repair": repair_report,
            "validation": validation,
            "roundtrip_text": roundtrip,
        }
    except Exception as exc:  # ruff: ignore[blind-except]
        safe_unlink(repaired)
        if backup.exists() and not path.exists():
            try:
                backup.replace(path)
            except OSError:
                pass
        return {
            "status": "FAIL",
            "error": "HWPX_PACKAGE_REPAIR_EXCEPTION",
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        }


def build_plan_gate(report: dict[str, Any]) -> dict[str, Any]:
    items = report.get("items") if isinstance(report.get("items"), list) else []
    blocked = [
        str(item.get("input") or index)
        for index, item in enumerate(items)
        if isinstance(item, dict) and item.get("action") == "FAIL"
    ]
    checks = [
        {
            "name": "plan_built",
            "status": "PASS" if report.get("mode") == "batch_plan" else "FAIL",
            "target_count": report.get("target_count"),
        },
        {
            "name": "no_blocking_actions",
            "status": "PASS" if not blocked else "FAIL",
            "blocked_items": blocked,
        },
    ]
    failed = [check["name"] for check in checks if check["status"] != "PASS"]
    return {
        "status": "PASS" if not failed else "FAIL",
        "checked_at": iso_now(),
        "failed_checks": failed,
        "checks": checks,
    }


def attach_plan_gate(report: dict[str, Any]) -> dict[str, Any]:
    report["conversion_gate"] = build_plan_gate(report)
    return report


def stable_json_digest(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8", errors="replace"
    )
    return hashlib.sha256(payload).hexdigest()


def _audit_result_summary(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": result.get("status"),
        "input": result.get("input"),
        "output": result.get("output"),
        "error": result.get("error"),
        "input_info": result.get("input_info"),
        "output_info": result.get("output_info"),
        "validation": result.get("validation"),
        "table_reconstruction": result.get("table_reconstruction"),
        "text_quality": result.get("text_quality"),
        "roundtrip_text": result.get("roundtrip_text"),
        "table_grid_gate": result.get("table_grid_gate"),
        "fidelity_gate": result.get("fidelity_gate"),
        "identity_status": result.get("identity_status"),
        "identity_equal": result.get("identity_equal"),
        "identity_audit": result.get("identity_audit"),
        "conversion_gate": result.get("conversion_gate"),
        "paragraph_count": result.get("paragraph_count"),
        "section_count": result.get("section_count"),
        "section_paragraph_counts": result.get("section_paragraph_counts"),
        "text_length": result.get("text_length"),
        "existing_policy": result.get("existing_policy"),
        "fidelity_policy": result.get("fidelity_policy"),
    }


def build_audit_record(
    report: dict[str, Any], *, event: str, audit_level: str = "standard"
) -> dict[str, Any]:
    audit_level = audit_level if audit_level in AUDIT_LEVELS else "standard"
    record = {
        "event": event,
        "audit_level": audit_level,
        "logged_at": iso_now(),
        "job_id": report.get("job_id"),
        "status": report.get("status"),
        "mode": report.get("mode"),
        "input": report.get("input") or report.get("input_dir"),
        "output": report.get("output") or report.get("output_dir"),
        "target_count": report.get("target_count"),
        "ok_count": report.get("ok_count"),
        "skipped_count": report.get("skipped_count"),
        "fail_count": report.get("fail_count"),
        "conversion_gate": report.get("conversion_gate"),
        "report_sha256": stable_json_digest(report),
    }
    if audit_level == "forensic":
        results = report.get("results") if isinstance(report.get("results"), list) else None
        if results is None:
            record["result"] = _audit_result_summary(report)
        else:
            record["results"] = [
                _audit_result_summary(item) for item in results if isinstance(item, dict)
            ]
        record["quality_summary"] = {
            "text_quality": report.get("text_quality"),
            "roundtrip_text": report.get("roundtrip_text"),
            "table_reconstruction": report.get("table_reconstruction"),
            "table_grid_gate": report.get("table_grid_gate"),
            "fidelity_gate": report.get("fidelity_gate"),
            "validation": report.get("validation"),
            "temp_cleanup": report.get("temp_cleanup"),
        }
    return record


def write_audit_log(
    path: Path | None,
    report: dict[str, Any],
    *,
    event: str = "conversion_report",
    audit_level: str = "standard",
) -> None:
    if not path:
        return
    path = Path(path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    record = build_audit_record(report, event=event, audit_level=audit_level)
    path.open("a", encoding="utf-8").write(
        json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
    )
    LOGGER.info(
        "audit_log_written path=%s event=%s status=%s audit_level=%s",
        path,
        event,
        report.get("status"),
        audit_level,
    )


def write_forensic_item_audit(
    path: Path | None, report: dict[str, Any], *, audit_level: str = "standard"
) -> None:
    if audit_level != "forensic" or not path:
        return
    results = report.get("results")
    if not isinstance(results, list):
        return
    path = Path(path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for index, result in enumerate(results):
            if not isinstance(result, dict):
                continue
            record = build_audit_record(result, event="conversion_item", audit_level="forensic")
            record["job_id"] = report.get("job_id")
            record["item_index"] = index
            fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    LOGGER.info("audit_item_logs_written path=%s rows=%s", path, len(results))


def safe_unlink(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def cleanup_temp_files(root: Path, *, retries: int = 3, delay_sec: float = 0.1) -> dict[str, Any]:
    root = Path(root)
    removed = 0
    failed: list[str] = []
    if not root.exists():
        return {"removed": removed, "failed": failed}
    for path in root.rglob("*.tmp"):
        deleted = False
        for attempt in range(max(1, retries)):
            try:
                path.unlink()
                removed += 1
                deleted = True
                break
            except OSError:
                if attempt + 1 < retries:
                    time.sleep(delay_sec)
        if not deleted:
            failed.append(str(path))
    if removed or failed:
        LOGGER.info("temp_cleanup removed=%s failed=%s root=%s", removed, len(failed), root)
    return {"removed": removed, "failed": failed}


def file_sha256(path: Path, chunk_size: int = 1024 * 1024) -> str | None:
    try:
        digest = hashlib.sha256()
        with Path(path).open("rb") as fh:
            for chunk in iter(lambda: fh.read(chunk_size), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def file_snapshot(path: Path) -> dict[str, Any]:
    path = Path(path)
    exists = path.exists()
    return {
        "path": str(path),
        "exists": exists,
        "size": path.stat().st_size if exists else 0,
        "sha256": file_sha256(path) if exists else None,
    }


def file_detection_key(path: Path) -> str:
    snapshot = file_snapshot(path)
    return f"{snapshot.get('size')}:{snapshot.get('sha256')}"


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_now() -> str:
    return utc_now().isoformat()


def unique_output_path(output_path: Path) -> Path:
    if not output_path.exists():
        return output_path
    for index in range(1, 10000):
        candidate = output_path.with_name(f"{output_path.stem}_{index}{output_path.suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"No available output filename for {output_path}")


def resolve_existing_output(
    output_path: Path, existing_policy: str
) -> tuple[str, Path, str | None]:
    if existing_policy not in EXISTING_POLICIES:
        return "FAIL", output_path, f"INVALID_EXISTING_POLICY:{existing_policy}"
    if not output_path.exists() or existing_policy == "overwrite":
        return "WRITE", output_path, None
    if existing_policy == "fail":
        return "FAIL", output_path, "OUTPUT_EXISTS"
    if existing_policy == "skip":
        return "SKIP", output_path, "OUTPUT_EXISTS_SKIPPED"
    return "WRITE", unique_output_path(output_path), None


def split_section_paragraphs(extraction: dict[str, Any]) -> list[list[str]]:
    sections: list[list[str]] = []
    for section in extraction.get("sections", []):
        if not isinstance(section, dict):
            continue
        text = str(section.get("text") or "")
        paragraphs: list[str] = []
        for line in text.splitlines():
            normalized = " ".join(line.split())
            if normalized:
                paragraphs.append(normalized)
        if paragraphs:
            sections.append(paragraphs)
    if sections:
        return sections
    text = str(extraction.get("text") or "")
    fallback = [" ".join(line.split()) for line in text.splitlines() if line.strip()]
    return [fallback] if fallback else [[]]


def split_paragraphs(extraction: dict[str, Any]) -> list[str]:
    return [paragraph for section in split_section_paragraphs(extraction) for paragraph in section]


_TABLE_BLOCK_COPY_KEYS = (
    "source_row_count",
    "source_col_count",
    "record_index",
    "section",
    "payload_size",
    "row_cell_counts",
    "row_cell_count_total",
    "reconstruction",
    "reconstructed_row_count",
    "reconstructed_col_count",
    "mergedCells",
    "coveredCells",
)


def _normalize_table_block(block: dict[str, Any]) -> dict[str, Any] | None:
    rows = block.get("rows")
    if not (isinstance(rows, list) and rows):
        return None
    normalized: dict[str, Any] = {
        "type": "table",
        "rows": [[str(cell) for cell in row] for row in rows if isinstance(row, list)],
    }
    for key in _TABLE_BLOCK_COPY_KEYS:
        if key in block:
            normalized[key] = block.get(key)
    return normalized


def _normalize_paragraph_block(block: dict[str, Any]) -> dict[str, Any] | None:
    text = " ".join(str(block.get("text") or "").split())
    if not text:
        return None
    return {"type": "paragraph", "text": text}


def split_section_blocks(extraction: dict[str, Any]) -> list[list[dict[str, Any]]]:
    section_blocks: list[list[dict[str, Any]]] = []
    for section in extraction.get("sections", []):
        if not isinstance(section, dict):
            continue
        blocks = section.get("blocks")
        if not (isinstance(blocks, list) and blocks):
            continue
        normalized_blocks = []
        for block in blocks:
            if not isinstance(block, dict):
                continue
            normalized = None
            if block.get("type") == "table":
                normalized = _normalize_table_block(block)
            elif block.get("type") == "paragraph":
                normalized = _normalize_paragraph_block(block)
            if normalized is not None:
                normalized_blocks.append(normalized)
        if normalized_blocks:
            section_blocks.append(normalized_blocks)
    return section_blocks


def _paragraph_xml(paragraph: str) -> str:
    return f"<hp:p><hp:run><hp:t>{escape(paragraph)}</hp:t></hp:run></hp:p>"


def _table_xml(
    rows: list[list[str]], paragraph_id: int, defaults: dict[str, Any] | None = None
) -> str:
    if not rows:
        return ""
    table_defaults = {"repeatHeader": "0", "rowHeight": "1600"}
    if defaults:
        table_defaults.update(defaults)
    elem = create_table_paragraph(rows, str(paragraph_id), table_defaults)
    return ET.tostring(elem, encoding="unicode")


def build_section_xml(paragraphs: list[str], blocks: list[dict[str, Any]] | None = None) -> str:
    body = []
    if blocks:
        paragraph_id = 0
        for block in blocks:
            if block.get("type") == "table":
                rows = block.get("rows") if isinstance(block.get("rows"), list) else []
                defaults = {}
                for key in ("mergedCells", "coveredCells"):
                    if key in block:
                        defaults[key] = block.get(key)
                body.append(_table_xml(rows, paragraph_id, defaults))
            else:
                body.append(_paragraph_xml(str(block.get("text") or "")))
            paragraph_id += 1
    else:
        for paragraph in paragraphs or [""]:
            body.append(_paragraph_xml(paragraph))
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<hs:sec xmlns:hp="{HP_NS}" xmlns:hs="{HS_NS}">' + "".join(body) + "</hs:sec>"
    )


def normalize_roundtrip_text(value: str) -> str:
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[ \t\f\v]+", " ", line).strip() for line in value.split("\n")]
    return "\n".join(line for line in lines if line)


def read_hwpx_section_text(path: Path) -> dict[str, Any]:
    entries: list[str] = []
    texts: list[str] = []
    xml_errors: list[dict[str, str]] = []
    try:
        with zipfile.ZipFile(path) as zf:
            for name in sorted(zf.namelist(), key=lambda item: item.lower()):
                normalized = name.replace("\\", "/").lower()
                if not (normalized.startswith("contents/section") and normalized.endswith(".xml")):
                    continue
                entries.append(name)
                payload = zf.read(name)
                try:
                    root = ET.fromstring(payload)
                except ET.ParseError as exc:
                    xml_errors.append({"entry": name, "error": str(exc)})
                    continue
                paragraph_texts = []
                for elem in root.iter():
                    if _xml_local_name(elem.tag) != "p":
                        continue
                    paragraph_text = "".join(text for text in elem.itertext() if text)
                    if paragraph_text:
                        paragraph_texts.append(paragraph_text)
                if paragraph_texts:
                    texts.append("\n".join(paragraph_texts))
                else:
                    texts.append("\n".join(node.text for node in root.iter() if node.text))
    except zipfile.BadZipFile:
        return {"ok": False, "error": "HWPX_NOT_ZIP", "entries": [], "text": "", "xml_errors": []}
    except OSError as exc:
        return {
            "ok": False,
            "error": f"HWPX_READ_FAILED: {exc}",
            "entries": [],
            "text": "",
            "xml_errors": [],
        }
    return {
        "ok": not xml_errors,
        "error": "",
        "entries": entries,
        "text": "\n".join(texts),
        "xml_errors": xml_errors,
    }


def _xml_local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _normalized_cell_text(elem: ET.Element) -> str:
    return normalize_roundtrip_text("".join(text for text in elem.itertext() if text))


def _first_child_local(root: ET.Element, local: str) -> ET.Element | None:
    for child in list(root):
        if _xml_local_name(child.tag) == local:
            return child
    return None


def _int_or_none(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalized_table_rows(
    rows: list[list[Any]], row_count: int | None = None, col_count: int | None = None
) -> list[list[str]]:
    normalized = [
        [normalize_roundtrip_text(str(cell)) for cell in row]
        for row in rows
        if isinstance(row, list)
    ]
    effective_rows = row_count if row_count is not None and row_count >= 0 else len(normalized)
    effective_cols = (
        col_count
        if col_count is not None and col_count >= 0
        else max((len(row) for row in normalized), default=0)
    )
    grid: list[list[str]] = []
    for row_index in range(effective_rows):
        source_row = normalized[row_index] if row_index < len(normalized) else []
        grid.append([
            (source_row[col_index] if col_index < len(source_row) else "")
            for col_index in range(effective_cols)
        ])
    return grid


def _read_hwpx_table_row(tr: ET.Element, col_count: int) -> list[str]:
    row = [""] * max(col_count, 0)
    next_col = 0
    for tc in [child for child in list(tr) if _xml_local_name(child.tag) == "tc"]:
        addr = _first_child_local(tc, "cellAddr")
        span = _first_child_local(tc, "cellSpan")
        col_addr = _int_or_none(addr.attrib.get("colAddr")) if addr is not None else None
        parsed_col_span = _int_or_none(span.attrib.get("colSpan")) if span is not None else None
        col_span = max(parsed_col_span or 1, 1)
        start_col = col_addr if col_addr is not None else next_col
        if start_col >= len(row):
            row.extend([""] * (start_col - len(row) + 1))
        row[start_col] = _normalized_cell_text(tc)
        next_col = start_col + col_span
        if next_col > len(row):
            row.extend([""] * (next_col - len(row)))
    return row[:col_count] if col_count >= 0 else row


def expected_table_grids(section_blocks: list[list[dict[str, Any]]] | None) -> list[dict[str, Any]]:
    expected: list[dict[str, Any]] = []
    for section_index, blocks in enumerate(section_blocks or []):
        for block in blocks:
            if not isinstance(block, dict) or block.get("type") != "table":
                continue
            rows = block.get("rows") if isinstance(block.get("rows"), list) else []
            row_count = _int_or_none(block.get("reconstructed_row_count")) or len(rows)
            col_count = _int_or_none(block.get("reconstructed_col_count")) or max(
                (len(row) for row in rows if isinstance(row, list)), default=0
            )
            grid = _normalized_table_rows(rows, row_count, col_count)
            expected.append({
                "section_index": section_index,
                "source_section": block.get("section"),
                "record_index": block.get("record_index"),
                "row_count": len(grid),
                "col_count": max((len(row) for row in grid), default=0),
                "rows": grid,
                "non_empty_cell_texts": [cell for row in grid for cell in row if cell],
            })
    return expected


def read_hwpx_table_grids(path: Path) -> dict[str, Any]:
    entries: list[str] = []
    tables: list[dict[str, Any]] = []
    xml_errors: list[dict[str, str]] = []
    try:
        with zipfile.ZipFile(path) as zf:
            for name in sorted(zf.namelist(), key=lambda item: item.lower()):
                normalized = name.replace("\\", "/").lower()
                if not (normalized.startswith("contents/section") and normalized.endswith(".xml")):
                    continue
                entries.append(name)
                try:
                    root = ET.fromstring(zf.read(name))
                except ET.ParseError as exc:
                    xml_errors.append({"entry": name, "error": str(exc)})
                    continue
                for table in root.iter():
                    if _xml_local_name(table.tag) != "tbl":
                        continue
                    row_attr = _int_or_none(table.attrib.get("rowCnt"))
                    col_attr = _int_or_none(table.attrib.get("colCnt"))
                    physical_rows = [
                        child for child in list(table) if _xml_local_name(child.tag) == "tr"
                    ]
                    physical_col_count = max(
                        (
                            len([tc for tc in list(tr) if _xml_local_name(tc.tag) == "tc"])
                            for tr in physical_rows
                        ),
                        default=0,
                    )
                    row_count = row_attr if row_attr is not None else len(physical_rows)
                    col_count = col_attr if col_attr is not None else physical_col_count
                    rows = [_read_hwpx_table_row(tr, col_count) for tr in physical_rows]
                    grid = _normalized_table_rows(rows, row_count, col_count)
                    tables.append({
                        "entry": name,
                        "row_count": row_count,
                        "col_count": col_count,
                        "actual_row_count": len(rows),
                        "actual_col_count": max((len(row) for row in rows), default=0),
                        "physical_col_count": physical_col_count,
                        "rows": grid,
                        "non_empty_cell_texts": [cell for row in grid for cell in row if cell],
                    })
    except zipfile.BadZipFile:
        return {"ok": False, "error": "HWPX_NOT_ZIP", "entries": [], "tables": [], "xml_errors": []}
    except OSError as exc:
        return {
            "ok": False,
            "error": f"HWPX_READ_FAILED: {exc}",
            "entries": [],
            "tables": [],
            "xml_errors": [],
        }
    return {
        "ok": not xml_errors,
        "error": "",
        "entries": entries,
        "tables": tables,
        "xml_errors": xml_errors,
    }


def table_grid_gate(
    section_blocks: list[list[dict[str, Any]]] | None, output_path: Path
) -> dict[str, Any]:
    expected = expected_table_grids(section_blocks)
    actual_report = read_hwpx_table_grids(output_path)
    actual = actual_report.get("tables") if isinstance(actual_report.get("tables"), list) else []
    errors: list[str] = []
    warnings: list[str] = []
    mismatches: list[dict[str, Any]] = []
    sequence_matches: list[dict[str, Any]] = []
    if not actual_report.get("ok"):
        errors.append(str(actual_report.get("error") or "HWPX_TABLE_READ_FAILED"))
    if actual_report.get("xml_errors"):
        errors.append("HWPX_TABLE_XML_PARSE_FAILED")
    if len(expected) != len(actual):
        errors.append("HWPX_TABLE_COUNT_MISMATCH")
        mismatches.append({"kind": "table_count", "expected": len(expected), "actual": len(actual)})
    for index, expected_table in enumerate(expected[: len(actual)]):
        actual_table = actual[index]
        expected_shape = {
            "row_count": expected_table["row_count"],
            "col_count": expected_table["col_count"],
        }
        actual_shape = {
            "row_count": actual_table.get("row_count"),
            "col_count": actual_table.get("col_count"),
        }
        if expected_shape != actual_shape:
            errors.append("HWPX_TABLE_SHAPE_MISMATCH")
            mismatches.append({
                "kind": "shape",
                "index": index,
                "expected": expected_shape,
                "actual": actual_shape,
            })
        actual_rows = actual_table.get("rows")
        if expected_table["rows"] != actual_rows:
            expected_non_empty = expected_table["non_empty_cell_texts"]
            actual_non_empty = actual_table.get("non_empty_cell_texts", [])
            if expected_shape == actual_shape and expected_non_empty == actual_non_empty:
                sequence_matches.append({
                    "kind": "cell_text_sequence_match_after_span_mapping",
                    "index": index,
                    "expected_non_empty_samples": expected_non_empty[:20],
                    "actual_non_empty_samples": actual_non_empty[:20],
                })
                continue
            errors.append("HWPX_TABLE_CELL_TEXT_MISMATCH")
            mismatches.append({
                "kind": "cell_text",
                "index": index,
                "expected_non_empty_samples": expected_table["non_empty_cell_texts"][:20],
                "actual_non_empty_samples": actual_table.get("non_empty_cell_texts", [])[:20],
            })
    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": sorted(set(errors)),
        "warnings": sorted(set(warnings)),
        "expected_table_count": len(expected),
        "actual_table_count": len(actual),
        "expected_shapes": [
            {"row_count": item["row_count"], "col_count": item["col_count"]} for item in expected
        ],
        "actual_shapes": [
            {"row_count": item.get("row_count"), "col_count": item.get("col_count")}
            for item in actual
        ],
        "mismatch_count": len(mismatches),
        "mismatches": mismatches[:20],
        "sequence_match_count": len(sequence_matches),
        "sequence_matches": sequence_matches[:20],
        "section_entries": actual_report.get("entries", []),
        "xml_errors": actual_report.get("xml_errors", []),
    }


def _roundtrip_gate_errors(
    hwpx: dict[str, Any],
    *,
    source_len: int,
    target_len: int,
    length_ratio: float,
    min_ratio: float,
    missing_lines: list[str],
) -> list[str]:
    errors: list[str] = []
    if not hwpx.get("ok"):
        errors.append(str(hwpx.get("error") or "HWPX_TEXT_READ_FAILED"))
    if hwpx.get("xml_errors"):
        errors.append("HWPX_SECTION_XML_PARSE_FAILED")
    if source_len <= 0:
        errors.append("SOURCE_TEXT_EMPTY")
    if target_len <= 0:
        errors.append("HWPX_TEXT_EMPTY")
    if source_len > 0 and length_ratio < min_ratio:
        errors.append("HWPX_TEXT_LENGTH_BELOW_THRESHOLD")
    if missing_lines:
        errors.append("HWPX_TEXT_MISSING_SOURCE_LINES")
    return errors


def roundtrip_text_gate(
    source_text: str, output_path: Path, *, min_ratio: float = 0.98
) -> dict[str, Any]:
    hwpx = read_hwpx_section_text(output_path)
    source = normalize_roundtrip_text(source_text)
    target = normalize_roundtrip_text(str(hwpx.get("text") or ""))
    source_lines = [line for line in source.splitlines() if line.strip()]
    missing_lines: list[str] = []
    for line in source_lines:
        if len(line) < 2:
            continue
        if line not in target:
            missing_lines.append(line[:160])
        if len(missing_lines) >= 20:
            break
    source_len = len(source)
    target_len = len(target)
    length_ratio = target_len / source_len if source_len else 0.0
    errors = _roundtrip_gate_errors(
        hwpx,
        source_len=source_len,
        target_len=target_len,
        length_ratio=length_ratio,
        min_ratio=min_ratio,
        missing_lines=missing_lines,
    )
    warnings: list[str] = []
    exact_match = source == target
    if not exact_match and not errors:
        warnings.append("TEXT_NORMALIZATION_NOT_EXACT")
    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "warnings": warnings,
        "section_entries": hwpx.get("entries", []),
        "source_text_length": source_len,
        "hwpx_text_length": target_len,
        "length_ratio": length_ratio,
        "min_ratio": min_ratio,
        "exact_normalized_match": exact_match,
        "source_line_count": len(source_lines),
        "missing_line_count": len(missing_lines),
        "missing_line_samples": missing_lines,
        "xml_errors": hwpx.get("xml_errors", []),
    }


def build_version_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<ha:HCFVersion xmlns:ha="http://www.hancom.co.kr/hwpml/2011/app" '
        'ha:targetApplication="WORDPROCESSOR" ha:major="5" ha:minor="1" '
        'ha:micro="0" ha:buildNumber="1"/>'
    )


def build_container_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
        "<rootfiles>"
        f'<rootfile full-path="Contents/content.hpf" media-type="{HPF_MEDIA_TYPE}"/>'
        "</rootfiles>"
        "</container>"
    )


def build_settings_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<ha:HWPApplicationSetting xmlns:ha="http://www.hancom.co.kr/hwpml/2011/app" '
        'xmlns:config="urn:oasis:names:tc:opendocument:xmlns:config:1.0">'
        '<ha:CaretPosition ha:listIDRef="0" ha:paraIDRef="0" ha:pos="0"/>'
        "</ha:HWPApplicationSetting>"
    )


def build_container_rdf(section_count: int = 1) -> str:
    count = max(1, section_count)
    section_parts = "".join(
        f'<hpf:hasPart><rdf:Description rdf:about="Contents/section{index}.xml">'
        '<rdf:type rdf:resource="http://www.hancom.co.kr/schema/2011/hpf#SectionFile"/>'
        "</rdf:Description></hpf:hasPart>"
        for index in range(count)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" '
        'xmlns:hpf="http://www.hancom.co.kr/schema/2011/hpf">'
        '<rdf:Description rdf:about="Contents/content.hpf">'
        '<rdf:type rdf:resource="http://www.hancom.co.kr/schema/2011/hpf#Document"/>'
        + section_parts
        + '<hpf:hasPart><rdf:Description rdf:about="settings.xml">'
        '<rdf:type rdf:resource="http://www.hancom.co.kr/schema/2011/hpf#SettingsFile"/>'
        "</rdf:Description></hpf:hasPart>"
        "</rdf:Description>"
        "</rdf:RDF>"
    )


def build_manifest_xml() -> str:
    return build_manifest_xml_for_sections(1)


def build_manifest_xml_for_sections(section_count: int = 1, *, has_header: bool = False) -> str:
    count = max(1, section_count)
    entries = [
        ("/", HPF_MEDIA_TYPE),
        ("version.xml", "application/xml"),
        ("settings.xml", "application/xml"),
        ("Contents/content.hpf", HPF_MEDIA_TYPE),
    ]
    if has_header:
        entries.append(("Contents/header.xml", "application/xml"))
    entries.extend((f"Contents/section{index}.xml", "application/xml") for index in range(count))
    file_entries = "".join(
        f'<manifest:file-entry manifest:full-path="{path}" manifest:media-type="{media_type}"/>'
        for path, media_type in entries
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0">'
        + file_entries
        + "</manifest:manifest>"
    )


def build_content_hpf(section_count: int = 1) -> str:
    count = max(1, section_count)
    section_items = "".join(
        f'<opf:item id="section{index}" href="Contents/section{index}.xml" media-type="application/xml"/>'
        for index in range(count)
    )
    section_refs = "".join(f'<opf:itemref idref="section{index}"/>' for index in range(count))
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<opf:package xmlns:opf="http://www.idpf.org/2007/opf/" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" version="1.0">'
        "<opf:metadata><dc:title></dc:title><dc:creator></dc:creator>"
        f"<dc:format>{HPF_MEDIA_TYPE}</dc:format></opf:metadata>"
        "<opf:manifest>"
        + section_items
        + '<opf:item id="settings" href="settings.xml" media-type="application/xml"/>'
        + '<opf:item id="PrvText" href="Preview/PrvText.txt" media-type="text/plain"/>'
        "</opf:manifest>"
        "<opf:spine>" + section_refs + "</opf:spine>"
        "</opf:package>"
    )


def build_original_manifest(original_hwp_path: Path) -> dict[str, Any]:
    original_path = Path(original_hwp_path)
    original_snapshot = file_snapshot(original_path)
    return {
        "mode": "embedded_original_hwp",
        "entry_name": "Original/original.hwp",
        "original_file_name": original_path.name,
        "original_snapshot": original_snapshot,
        "preservation": {
            "byte_exact_original_embedded": bool(
                original_snapshot.get("exists") and original_snapshot.get("sha256")
            ),
            "document_layout_changed": False,
            "document_binary_properties_changed": False,
            "ai_readable_derivative_is_text_only_rebuild": True,
        },
    }


def write_stored_entry(zf: zipfile.ZipFile, name: str, data: str | bytes) -> None:
    zf.writestr(name, data, compress_type=zipfile.ZIP_STORED)


def write_directory_entry(zf: zipfile.ZipFile, name: str) -> None:
    directory = name if name.endswith("/") else f"{name}/"
    zf.writestr(directory, b"", compress_type=zipfile.ZIP_STORED)


def write_file_stored(zf: zipfile.ZipFile, source: Path, arcname: str) -> None:
    zf.writestr(arcname, Path(source).read_bytes(), compress_type=zipfile.ZIP_STORED)


def _flatten_preview_text(
    sections: list[list[str]], section_blocks: list[list[dict[str, Any]]] | None
) -> list[str]:
    if not section_blocks:
        return [paragraph for section in sections for paragraph in section]
    flattened: list[str] = []
    for blocks in section_blocks:
        for block in blocks:
            if block.get("type") == "table":
                for row in block.get("rows", []):
                    if isinstance(row, list):
                        flattened.extend(str(cell) for cell in row if str(cell))
            else:
                text = str(block.get("text") or "")
                if text:
                    flattened.append(text)
    return flattened


def write_text_hwpx(
    output_path: Path,
    paragraphs: list[str] | list[list[str]],
    metadata: dict[str, Any] | None = None,
    section_blocks: list[list[dict[str, Any]]] | None = None,
    original_hwp_path: Path | None = None,
) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if paragraphs and all(isinstance(item, list) for item in paragraphs):
        sections = paragraphs  # type: ignore[assignment]
    else:
        sections = [paragraphs]  # type: ignore[list-item]
    flattened = _flatten_preview_text(sections, section_blocks)
    preview = "\n".join(flattened)
    metadata = dict(metadata or {})
    original_manifest = None
    if original_hwp_path is not None:
        original_manifest = build_original_manifest(Path(original_hwp_path))
        metadata["original_preservation"] = original_manifest
    metadata_json = json.dumps(metadata, ensure_ascii=False, indent=2)
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_STORED) as zf:
        write_stored_entry(zf, "mimetype", MIMETYPE)
        write_directory_entry(zf, "META-INF/")
        write_directory_entry(zf, "Contents/")
        write_directory_entry(zf, "Preview/")
        if original_hwp_path is not None:
            write_directory_entry(zf, "Original/")
        write_stored_entry(zf, "META-INF/container.xml", build_container_xml())
        write_stored_entry(
            zf, "META-INF/manifest.xml", build_manifest_xml_for_sections(len(sections))
        )
        write_stored_entry(zf, "version.xml", build_version_xml())
        write_stored_entry(zf, "settings.xml", build_settings_xml())
        write_stored_entry(zf, "Contents/content.hpf", build_content_hpf(len(sections)))
        for index, section_paragraphs in enumerate(sections):
            blocks = (
                section_blocks[index] if section_blocks and index < len(section_blocks) else None
            )
            write_stored_entry(
                zf, f"Contents/section{index}.xml", build_section_xml(section_paragraphs, blocks)
            )
        write_stored_entry(zf, "Preview/PrvText.txt", preview)
        write_stored_entry(zf, "META-INF/container.rdf", build_container_rdf(len(sections)))
        write_stored_entry(zf, "Preview/ConversionReport.json", metadata_json)
        if original_hwp_path is not None:
            write_file_stored(zf, Path(original_hwp_path), "Original/original.hwp")
            write_stored_entry(
                zf,
                "Preview/OriginalManifest.json",
                json.dumps(original_manifest, ensure_ascii=False, indent=2),
            )
    return output_path


def text_quality_gate(text: str, expected_texts: list[str] | None = None) -> dict[str, Any]:
    expected_texts = expected_texts or []
    hangul_syllables = len(re.findall(r"[\uac00-\ud7a3]", text))
    hangul_jamo = len(re.findall(r"[\u3130-\u318f]", text))
    cjk_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
    replacement_chars = text.count("\ufffd")
    control_chars = sum(1 for ch in text if ord(ch) < 32 and ch not in "\r\n\t")
    marker_hits = {marker: text.count(marker) for marker in MOJIBAKE_MARKERS if marker in text}
    missing_expected = [value for value in expected_texts if value and value not in text]
    korean_signal = hangul_syllables / max(1, hangul_syllables + cjk_chars + hangul_jamo)
    errors: list[str] = []
    warnings: list[str] = []
    if not text.strip():
        errors.append("TEXT_EMPTY")
    if replacement_chars:
        errors.append("REPLACEMENT_CHAR_FOUND")
    if control_chars:
        errors.append("CONTROL_CHAR_FOUND")
    if missing_expected:
        errors.append("EXPECTED_TEXT_MISSING")
    if marker_hits:
        warnings.append("MOJIBAKE_MARKER_FOUND")
    if hangul_syllables >= 20 and korean_signal < 0.35:
        warnings.append("LOW_HANGUL_SIGNAL")
    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "warnings": warnings,
        "length": len(text),
        "hangul_syllables": hangul_syllables,
        "hangul_jamo": hangul_jamo,
        "cjk_chars": cjk_chars,
        "korean_signal": korean_signal,
        "replacement_chars": replacement_chars,
        "control_chars": control_chars,
        "mojibake_marker_hits": marker_hits,
        "expected_texts": expected_texts,
        "missing_expected_texts": missing_expected,
    }


def fidelity_gate(extraction: dict[str, Any], *, policy: str = "text") -> dict[str, Any]:
    policy = policy if policy in FIDELITY_POLICIES else "text"
    inventory = (
        extraction.get("feature_inventory")
        if isinstance(extraction.get("feature_inventory"), dict)
        else {}
    )
    risk_tags = (
        inventory.get("risk_record_tags")
        if isinstance(inventory.get("risk_record_tags"), dict)
        else {}
    )
    bindata_count = int(inventory.get("bindata_count") or 0)
    risks: list[dict[str, Any]] = []
    if risk_tags:
        risks.append({
            "code": "UNSUPPORTED_HWP_RECORDS_PRESENT",
            "message": "HWP contains records that are inventoried but not fully reconstructed in standalone text conversion.",
            "record_tags": risk_tags,
        })
    if bindata_count:
        risks.append({
            "code": "BINDATA_PRESENT",
            "message": "HWP contains embedded binary data; standalone text conversion does not preserve embedded objects yet.",
            "bindata_count": bindata_count,
            "bindata_streams": inventory.get("bindata_streams", []),
        })
    if not extraction.get("sections"):
        risks.append({
            "code": "NO_SECTIONS_FOUND",
            "message": "No BodyText sections were discovered.",
        })
    status = "PASS"
    if risks and policy == "strict":
        status = "FAIL"
    elif risks:
        status = "WARN"
    return {
        "status": status,
        "policy": policy,
        "mode": "text_only_rebuild",
        "full_fidelity": not risks,
        "risk_count": len(risks),
        "risks": risks,
        "feature_inventory": inventory,
        "supported_scope": [
            "HWP FileHeader validation",
            "compressed BodyText section decompression",
            "paragraph text extraction from PARA_TEXT records",
            "approximate HWP table text reconstruction into HWPX table nodes",
            "decoded page, page border, and footnote/endnote shape bridge into HWPX section properties",
            "multi-section text-only HWPX package generation",
            "ZIP/XML/package validation",
            "loss-risk inventory for unsupported HWP records and BinData",
        ],
        "unsupported_scope": [
            "exact original layout reconstruction",
            "exact native HWP table cell geometry, borders, spans, and dimensions",
            "images and embedded objects",
            "shape controls",
            "rich character/paragraph styles",
            "footnote/endnote body objects and equations",
        ],
    }


def apply_decoded_style_bridge(input_path: Path, output_path: Path) -> dict[str, Any]:
    """Inject decoded HWP DocInfo/body layout mappings into generated HWPX."""
    try:
        hwp_analyzer = importlib.import_module("hwp_full_fidelity_analyzer")
        hwp_package = importlib.import_module("hwp_full_fidelity_package")
    except Exception as exc:  # ruff: ignore[blind-except]
        return {
            "status": "FAIL",
            "error": "DECODED_STYLE_BRIDGE_IMPORT_FAILED",
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        }
    analysis = hwp_analyzer.analyze_hwp(Path(input_path), include_records=False)
    if analysis.get("status") != "PASS":
        return {
            "status": "FAIL",
            "error": "DECODED_STYLE_BRIDGE_ANALYSIS_FAILED",
            "analysis": analysis,
        }
    injected = hwp_package.inject_analysis_entries(Path(output_path), analysis)
    coverage = analysis.get("coverage") if isinstance(analysis.get("coverage"), dict) else {}
    return {
        "status": injected.get("status", "FAIL"),
        "analysis_status": analysis.get("status"),
        "coverage_status": coverage.get("status"),
        "full_fidelity_ready": coverage.get("full_fidelity_ready"),
        "coverage": {
            "status": coverage.get("status"),
            "full_fidelity_ready": coverage.get("full_fidelity_ready"),
            "record_coverage_ratio": coverage.get("record_coverage_ratio"),
            "decode_coverage_ratio": coverage.get("decode_coverage_ratio"),
            "covered_record_count": coverage.get("covered_record_count"),
            "decoded_record_count": coverage.get("decoded_record_count"),
            "present_record_count": coverage.get("present_record_count"),
            "supported_tags": coverage.get("supported_tags", []),
            "risk_tags": coverage.get("risk_tags", []),
            "unknown_tags": coverage.get("unknown_tags", []),
            "required_families": coverage.get("required_families", []),
            "blockers": coverage.get("blockers", []),
            "warnings": coverage.get("warnings", []),
            "document_properties_coverage": coverage.get("document_properties_coverage"),
            "id_mappings_coverage": coverage.get("id_mappings_coverage"),
            "docinfo_extension_coverage": coverage.get("docinfo_extension_coverage"),
            "bindata_stream_coverage": coverage.get("bindata_stream_coverage"),
            "fontface_coverage": coverage.get("fontface_coverage"),
            "border_fill_coverage": coverage.get("border_fill_coverage"),
            "char_shape_coverage": coverage.get("char_shape_coverage"),
            "para_shape_coverage": coverage.get("para_shape_coverage"),
            "style_coverage": coverage.get("style_coverage"),
            "paragraph_layout_coverage": coverage.get("paragraph_layout_coverage"),
            "controls_page_coverage": coverage.get("controls_page_coverage"),
            "table_coverage": coverage.get("table_coverage"),
            "shape_coverage": coverage.get("shape_coverage"),
            "numbering_coverage": coverage.get("numbering_coverage"),
            "equation_coverage": coverage.get("equation_coverage"),
            "picture_coverage": coverage.get("picture_coverage"),
            "binary_object_coverage": coverage.get("binary_object_coverage"),
            "next_decoder_targets": coverage.get("next_decoder_targets", []),
        },
        "decoded_header": injected.get("decoded_header"),
        "fontface_mapping": injected.get("fontface_mapping"),
        "body_style_mapping": injected.get("body_style_mapping"),
        "page_layout_mapping": injected.get("page_layout_mapping"),
        "table_layout_mapping": injected.get("table_layout_mapping"),
        "visual_object_mapping": injected.get("visual_object_mapping"),
        "equation_mapping": injected.get("equation_mapping"),
        "list_style_mapping": injected.get("list_style_mapping"),
        "bindata_preservation": injected.get("bindata_preservation"),
        "entries": injected.get("entries", []),
    }


def convert_hwp_to_hwpx(
    input_path: Path,
    output_path: Path,
    *,
    extractor: Callable[[Path], dict[str, Any]] = extract_hwp_text,
    expected_texts: list[str] | None = None,
    strict_quality: bool = False,
    existing_policy: str = "fail",
    fidelity_policy: str = "text",
    embed_original: bool = False,
    decoded_style_bridge: bool = False,
) -> dict[str, Any]:
    input_path = Path(input_path).expanduser().resolve()
    output_path = Path(output_path).expanduser().resolve()
    LOGGER.info(
        "file_start input=%s output=%s strict_quality=%s existing_policy=%s fidelity_policy=%s decoded_style_bridge=%s",
        input_path,
        output_path,
        strict_quality,
        existing_policy,
        fidelity_policy,
        decoded_style_bridge,
    )
    input_info = file_snapshot(input_path)
    output_action, resolved_output_path, output_error = resolve_existing_output(
        output_path, existing_policy
    )
    if output_action == "SKIP":
        return attach_conversion_gate(
            {
                "status": "SKIP",
                "input": str(input_path),
                "output": str(output_path),
                "input_info": input_info,
                "output_info": file_snapshot(output_path),
                "error": output_error,
                "mode": "text_only_rebuild",
                "existing_policy": existing_policy,
                "fidelity_policy": fidelity_policy,
            },
            strict_quality=strict_quality,
        )
    if output_action == "FAIL":
        return attach_conversion_gate(
            {
                "status": "FAIL",
                "input": str(input_path),
                "output": str(output_path),
                "input_info": input_info,
                "output_info": file_snapshot(output_path),
                "error": output_error,
                "mode": "text_only_rebuild",
                "existing_policy": existing_policy,
                "fidelity_policy": fidelity_policy,
            },
            strict_quality=strict_quality,
        )
    output_path = resolved_output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        extraction = extractor(input_path)
    except Exception as exc:  # ruff: ignore[blind-except]
        return attach_conversion_gate(
            {
                "status": "FAIL",
                "input": str(input_path),
                "output": str(output_path),
                "input_info": input_info,
                "output_info": file_snapshot(output_path),
                "error": "EXTRACTOR_EXCEPTION",
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "mode": "text_only_rebuild",
                "existing_policy": existing_policy,
                "fidelity_policy": fidelity_policy,
            },
            strict_quality=strict_quality,
        )
    if not extraction.get("ok"):
        return attach_conversion_gate(
            {
                "status": "FAIL",
                "input": str(input_path),
                "output": str(output_path),
                "input_info": input_info,
                "output_info": file_snapshot(output_path),
                "error": extraction.get("error") or "HWP_TEXT_EXTRACTION_FAILED",
                "extraction": extraction,
                "existing_policy": existing_policy,
                "fidelity_policy": fidelity_policy,
            },
            strict_quality=strict_quality,
        )

    sections = split_section_paragraphs(extraction)
    section_blocks = split_section_blocks(extraction)
    paragraphs = [paragraph for section in sections for paragraph in section]
    extracted_text = "\n".join(paragraphs)
    quality = text_quality_gate(extracted_text, expected_texts)
    fidelity = fidelity_gate(extraction, policy=fidelity_policy)
    metadata = {
        "converter": "hwp_to_hwpx_standalone",
        "converted_at": datetime.now(UTC).isoformat(),
        "input": str(input_path),
        "output": str(output_path),
        "input_info": input_info,
        "mode": "text_only_rebuild_with_decoded_style_bridge"
        if decoded_style_bridge
        else "text_only_rebuild_with_embedded_original"
        if embed_original
        else "text_only_rebuild",
        "original_preservation": build_original_manifest(input_path)
        if embed_original
        else {"enabled": False},
        "paragraph_count": len(paragraphs),
        "section_count": len(sections),
        "section_paragraph_counts": [len(section) for section in sections],
        "limitations": [
            "Text is extracted from HWP BodyText records.",
            "Original layout, embedded objects, images, tables, and rich styling are not preserved yet.",
            "Hancom Office, COM, GUI automation, and external converters are not used.",
        ],
        "hwp_header": extraction.get("header"),
        "record_counts": extraction.get("record_counts"),
        "record_tag_names": extraction.get("record_tag_names"),
        "feature_inventory": extraction.get("feature_inventory"),
        "table_reconstruction": {
            "status": "PASS" if section_blocks else "NO_TABLE_BLOCKS",
            "mode": "source_row_cell_counts"
            if any(
                block.get("reconstruction") == "source_row_cell_counts"
                for blocks in section_blocks
                for block in blocks
                if block.get("type") == "table"
            )
            else "source_grid_row_major"
            if any(
                block.get("reconstruction") == "source_grid_row_major"
                for blocks in section_blocks
                for block in blocks
                if block.get("type") == "table"
            )
            else "one_text_paragraph_per_row",
            "table_count": sum(
                1 for blocks in section_blocks for block in blocks if block.get("type") == "table"
            ),
            "table_shapes": [
                {
                    "section": block.get("section"),
                    "record_index": block.get("record_index"),
                    "source_row_count": block.get("source_row_count"),
                    "source_col_count": block.get("source_col_count"),
                    "row_cell_counts": block.get("row_cell_counts"),
                    "row_cell_count_total": block.get("row_cell_count_total"),
                    "reconstruction": block.get("reconstruction"),
                    "reconstructed_row_count": block.get(
                        "reconstructed_row_count", len(block.get("rows", []))
                    ),
                    "reconstructed_col_count": block.get(
                        "reconstructed_col_count",
                        max((len(row) for row in block.get("rows", [])), default=0),
                    ),
                    "payload_size": block.get("payload_size"),
                }
                for blocks in section_blocks
                for block in blocks
                if block.get("type") == "table"
            ],
            "exact_cell_geometry": False,
        },
        "text_quality": quality,
        "fidelity_gate": fidelity,
        "existing_policy": existing_policy,
        "fidelity_policy": fidelity_policy,
        "decoded_style_bridge": {
            "enabled": decoded_style_bridge,
            "status": "PENDING" if decoded_style_bridge else "SKIPPED",
        },
    }
    table_reconstruction = metadata["table_reconstruction"]
    temp_output = Path(tempfile.gettempdir()) / f"hwp2hwpx_{uuid4().hex}_{output_path.name}.tmp"
    write_text_hwpx(
        temp_output,
        sections,
        metadata,
        section_blocks=section_blocks or None,
        original_hwp_path=input_path if embed_original else None,
    )
    validation = HwpxValidator.validate_hwpx(temp_output)
    roundtrip = roundtrip_text_gate(extracted_text, temp_output)
    table_grid = table_grid_gate(section_blocks, temp_output)
    package_ok = validation.get("zip_ok") is True and validation.get("xml_ok") is True
    quality_ok = quality.get("status") == "PASS" and (
        not strict_quality or not quality.get("warnings")
    )
    roundtrip_ok = roundtrip.get("status") == "PASS"
    table_grid_ok = table_grid.get("status") == "PASS"
    fidelity_ok = fidelity.get("status") != "FAIL"
    ok = package_ok and quality_ok and roundtrip_ok and table_grid_ok and fidelity_ok
    if ok:
        try:
            temp_output.replace(output_path)
            validation = HwpxValidator.validate_hwpx(output_path)
            roundtrip = roundtrip_text_gate(extracted_text, output_path)
            table_grid = table_grid_gate(section_blocks, output_path)
        except OSError as exc:
            if not output_path.exists():
                try:
                    shutil.copy2(temp_output, output_path)
                    copied_validation = HwpxValidator.validate_hwpx(output_path)
                    copied_roundtrip = roundtrip_text_gate(extracted_text, output_path)
                    copied_table_grid = table_grid_gate(section_blocks, output_path)
                    if (
                        copied_validation.get("zip_ok") is True
                        and copied_validation.get("xml_ok") is True
                        and copied_roundtrip.get("status") == "PASS"
                        and copied_table_grid.get("status") == "PASS"
                    ):
                        safe_unlink(temp_output)
                        validation = copied_validation
                        roundtrip = copied_roundtrip
                        table_grid = copied_table_grid
                    else:
                        safe_unlink(output_path)
                        safe_unlink(temp_output)
                        return attach_conversion_gate(
                            {
                                "status": "FAIL",
                                "input": str(input_path),
                                "output": str(output_path),
                                "input_info": input_info,
                                "output_info": file_snapshot(output_path),
                                "error": "OUTPUT_COPY_VALIDATION_FAILED",
                                "paragraph_count": len(paragraphs),
                                "section_count": len(sections),
                                "section_paragraph_counts": [len(section) for section in sections],
                                "text_length": len(str(extraction.get("text") or "")),
                                "validation": copied_validation,
                                "table_reconstruction": table_reconstruction,
                                "text_quality": quality,
                                "roundtrip_text": copied_roundtrip,
                                "table_grid_gate": copied_table_grid,
                                "fidelity_gate": fidelity,
                                "mode": "text_only_rebuild",
                                "fidelity_policy": fidelity_policy,
                                "warnings": metadata["limitations"],
                            },
                            strict_quality=strict_quality,
                        )
                except OSError as copy_exc:
                    safe_unlink(temp_output)
                    return attach_conversion_gate(
                        {
                            "status": "FAIL",
                            "input": str(input_path),
                            "output": str(output_path),
                            "input_info": input_info,
                            "output_info": file_snapshot(output_path),
                            "error": "OUTPUT_COPY_FAILED",
                            "error_message": str(copy_exc),
                            "replace_error_message": str(exc),
                            "paragraph_count": len(paragraphs),
                            "section_count": len(sections),
                            "section_paragraph_counts": [len(section) for section in sections],
                            "text_length": len(str(extraction.get("text") or "")),
                            "validation": validation,
                            "table_reconstruction": table_reconstruction,
                            "text_quality": quality,
                            "roundtrip_text": roundtrip,
                            "table_grid_gate": table_grid,
                            "fidelity_gate": fidelity,
                            "mode": "text_only_rebuild",
                            "fidelity_policy": fidelity_policy,
                            "warnings": metadata["limitations"],
                        },
                        strict_quality=strict_quality,
                    )
            elif existing_policy == "overwrite":
                try:
                    safe_unlink(output_path)
                    temp_output.replace(output_path)
                    validation = HwpxValidator.validate_hwpx(output_path)
                    roundtrip = roundtrip_text_gate(extracted_text, output_path)
                    table_grid = table_grid_gate(section_blocks, output_path)
                except OSError as overwrite_exc:
                    try:
                        shutil.copy2(temp_output, output_path)
                        safe_unlink(temp_output)
                        validation = HwpxValidator.validate_hwpx(output_path)
                        roundtrip = roundtrip_text_gate(extracted_text, output_path)
                        table_grid = table_grid_gate(section_blocks, output_path)
                    except OSError as copy_exc:
                        safe_unlink(temp_output)
                        return attach_conversion_gate(
                            {
                                "status": "FAIL",
                                "input": str(input_path),
                                "output": str(output_path),
                                "input_info": input_info,
                                "output_info": file_snapshot(output_path),
                                "error": "OUTPUT_OVERWRITE_REPLACE_FAILED",
                                "error_message": str(copy_exc),
                                "replace_error_message": str(overwrite_exc),
                                "initial_replace_error_message": str(exc),
                                "paragraph_count": len(paragraphs),
                                "section_count": len(sections),
                                "section_paragraph_counts": [len(section) for section in sections],
                                "text_length": len(str(extraction.get("text") or "")),
                                "validation": validation,
                                "table_reconstruction": table_reconstruction,
                                "text_quality": quality,
                                "roundtrip_text": roundtrip,
                                "table_grid_gate": table_grid,
                                "fidelity_gate": fidelity,
                                "mode": "text_only_rebuild",
                                "fidelity_policy": fidelity_policy,
                                "warnings": metadata["limitations"],
                            },
                            strict_quality=strict_quality,
                        )
            else:
                safe_unlink(temp_output)
                return attach_conversion_gate(
                    {
                        "status": "FAIL",
                        "input": str(input_path),
                        "output": str(output_path),
                        "input_info": input_info,
                        "output_info": file_snapshot(output_path),
                        "error": "OUTPUT_REPLACE_FAILED",
                        "error_message": str(exc),
                        "paragraph_count": len(paragraphs),
                        "section_count": len(sections),
                        "section_paragraph_counts": [len(section) for section in sections],
                        "text_length": len(str(extraction.get("text") or "")),
                        "validation": validation,
                        "table_reconstruction": table_reconstruction,
                        "text_quality": quality,
                        "roundtrip_text": roundtrip,
                        "table_grid_gate": table_grid,
                        "fidelity_gate": fidelity,
                        "mode": "text_only_rebuild",
                        "fidelity_policy": fidelity_policy,
                        "warnings": metadata["limitations"],
                    },
                    strict_quality=strict_quality,
                )
            if not output_path.exists():
                safe_unlink(temp_output)
                return attach_conversion_gate(
                    {
                        "status": "FAIL",
                        "input": str(input_path),
                        "output": str(output_path),
                        "input_info": input_info,
                        "output_info": file_snapshot(output_path),
                        "error": "OUTPUT_REPLACE_FAILED",
                        "error_message": str(exc),
                        "paragraph_count": len(paragraphs),
                        "section_count": len(sections),
                        "section_paragraph_counts": [len(section) for section in sections],
                        "text_length": len(str(extraction.get("text") or "")),
                        "validation": validation,
                        "table_reconstruction": table_reconstruction,
                        "text_quality": quality,
                        "roundtrip_text": roundtrip,
                        "table_grid_gate": table_grid,
                        "fidelity_gate": fidelity,
                        "mode": "text_only_rebuild",
                        "fidelity_policy": fidelity_policy,
                        "warnings": metadata["limitations"],
                    },
                    strict_quality=strict_quality,
                )
    else:
        safe_unlink(temp_output)
    package_repair = {"status": "SKIPPED"}
    if ok:
        package_repair = repair_output_package(output_path, expected_text=extracted_text)
        validation = HwpxValidator.validate_hwpx(output_path)
        roundtrip = roundtrip_text_gate(extracted_text, output_path)
        table_grid = table_grid_gate(section_blocks, output_path)
        if package_repair.get("status") != "PASS":
            ok = False
        if validation.get("zip_ok") is not True or validation.get("xml_ok") is not True:
            ok = False
        if roundtrip.get("status") != "PASS":
            ok = False
        if table_grid.get("status") != "PASS":
            ok = False

    bridge_report: dict[str, Any] = {"enabled": decoded_style_bridge, "status": "SKIPPED"}
    if ok and decoded_style_bridge:
        bridge_backup = output_path.with_name(f".pre_bridge.{uuid4().hex}.hwpx")
        try:
            shutil.copy2(output_path, bridge_backup)
        except OSError:
            bridge_backup = None
        bridge_report = apply_decoded_style_bridge(input_path, output_path)
        bridge_report["enabled"] = True
        bridge_repair = repair_output_package(output_path, expected_text=extracted_text)
        bridge_report["package_repair"] = bridge_repair
        validation = HwpxValidator.validate_hwpx(output_path)
        roundtrip = roundtrip_text_gate(extracted_text, output_path)
        table_grid = table_grid_gate(section_blocks, output_path)
        if bridge_report.get("status") != "PASS":
            ok = False
        if bridge_repair.get("status") != "PASS":
            ok = False
            bridge_report.setdefault("error", "DECODED_STYLE_BRIDGE_PACKAGE_REPAIR_FAILED")
        if validation.get("zip_ok") is not True or validation.get("xml_ok") is not True:
            ok = False
            bridge_report.setdefault("error", "DECODED_STYLE_BRIDGE_PACKAGE_VALIDATION_FAILED")
        if roundtrip.get("status") != "PASS":
            ok = False
            bridge_report.setdefault("error", "DECODED_STYLE_BRIDGE_ROUNDTRIP_FAILED")
        if table_grid.get("status") != "PASS":
            ok = False
            bridge_report.setdefault("error", "DECODED_STYLE_BRIDGE_TABLE_GRID_FAILED")
        if not ok and bridge_backup and bridge_backup.exists():
            try:
                shutil.copy2(bridge_backup, output_path)
                bridge_report["rollback"] = {"status": "PASS", "source": str(bridge_backup)}
                validation = HwpxValidator.validate_hwpx(output_path)
                roundtrip = roundtrip_text_gate(extracted_text, output_path)
                table_grid = table_grid_gate(section_blocks, output_path)
            except OSError as exc:
                bridge_report["rollback"] = {"status": "FAIL", "error": str(exc)}
        if bridge_backup:
            safe_unlink(bridge_backup)
    ok = (
        ok
        and validation.get("zip_ok") is True
        and validation.get("xml_ok") is True
        and roundtrip.get("status") == "PASS"
        and table_grid.get("status") == "PASS"
    )
    return attach_conversion_gate(
        {
            "status": "PASS" if ok else "FAIL",
            "input": str(input_path),
            "output": str(output_path),
            "input_info": input_info,
            "output_info": file_snapshot(output_path),
            "paragraph_count": len(paragraphs),
            "section_count": len(sections),
            "section_paragraph_counts": [len(section) for section in sections],
            "text_length": len(str(extraction.get("text") or "")),
            "validation": validation,
            "table_reconstruction": table_reconstruction,
            "text_quality": quality,
            "roundtrip_text": roundtrip,
            "table_grid_gate": table_grid,
            "fidelity_gate": fidelity,
            "package_repair": package_repair,
            "mode": "text_only_rebuild_with_decoded_style_bridge"
            if decoded_style_bridge
            else "text_only_rebuild_with_embedded_original"
            if embed_original
            else "text_only_rebuild",
            "original_preservation": metadata.get("original_preservation"),
            "existing_policy": existing_policy,
            "fidelity_policy": fidelity_policy,
            "decoded_style_bridge": bridge_report,
            "warnings": metadata["limitations"],
        },
        strict_quality=strict_quality,
    )


def output_path_for_batch(input_file: Path, input_root: Path, output_root: Path) -> Path:
    relative = input_file.relative_to(input_root)
    return (output_root / relative).with_suffix(".hwpx")


def build_batch_plan(
    input_dir: Path,
    output_dir: Path,
    *,
    pattern: str = "*.hwp",
    existing_policy: str = "fail",
) -> dict[str, Any]:
    input_dir = Path(input_dir).expanduser().resolve()
    output_dir = Path(output_dir).expanduser().resolve()
    targets = sorted(path for path in input_dir.rglob(pattern) if path.is_file())
    items = []
    for target in targets:
        planned_output = output_path_for_batch(target, input_dir, output_dir)
        action, resolved_output, error = resolve_existing_output(planned_output, existing_policy)
        items.append({
            "input": str(target),
            "planned_output": str(planned_output),
            "resolved_output": str(resolved_output),
            "action": action,
            "error": error,
            "input_info": file_snapshot(target),
            "output_info": file_snapshot(planned_output),
        })
    action_counts: dict[str, int] = {}
    for item in items:
        action = str(item["action"])
        action_counts[action] = action_counts.get(action, 0) + 1
    return attach_plan_gate({
        "status": "PASS",
        "mode": "batch_plan",
        "input_dir": str(input_dir),
        "output_dir": str(output_dir),
        "pattern": pattern,
        "existing_policy": existing_policy,
        "target_count": len(targets),
        "action_counts": action_counts,
        "items": items,
    })


def convert_batch_target(  # ruff: ignore[too-many-arguments] -- convert_hwp_to_hwpx로 그대로 threading, 시그니처 변경은 하위 함수까지 연쇄됨
    target: Path,
    output: Path,
    *,
    expected_texts: list[str] | None,
    strict_quality: bool,
    existing_policy: str,
    fidelity_policy: str,
    embed_original: bool,
    decoded_style_bridge: bool = False,
) -> dict[str, Any]:
    try:
        result = convert_hwp_to_hwpx(
            target,
            output,
            expected_texts=expected_texts,
            strict_quality=strict_quality,
            existing_policy=existing_policy,
            fidelity_policy=fidelity_policy,
            embed_original=embed_original,
            decoded_style_bridge=decoded_style_bridge,
        )
        log_result("file_complete", result)
        return result
    except Exception as exc:  # ruff: ignore[blind-except]
        result = {
            "status": "FAIL",
            "input": str(target),
            "output": str(output),
            "input_info": file_snapshot(target),
            "output_info": file_snapshot(output),
            "error": "UNHANDLED_CONVERSION_EXCEPTION",
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "mode": "text_only_rebuild",
            "existing_policy": existing_policy,
            "fidelity_policy": fidelity_policy,
            "embed_original": embed_original,
            "decoded_style_bridge": {"enabled": decoded_style_bridge, "status": "SKIPPED"},
        }
        log_result("file_complete", result)
        return result


def convert_batch(  # ruff: ignore[too-many-arguments] -- 외부 파일(router/sdk) + CLI 호출부 다수, 시그니처 변경 보류
    input_dir: Path,
    output_dir: Path,
    *,
    expected_texts: list[str] | None = None,
    strict_quality: bool = False,
    pattern: str = "*.hwp",
    existing_policy: str = "fail",
    fidelity_policy: str = "text",
    embed_original: bool = False,
    decoded_style_bridge: bool = False,
    fail_fast: bool = False,
    workers: int = 1,
    job_id: str | None = None,
) -> dict[str, Any]:
    started = utc_now()
    resolved_job_id = job_id or uuid4().hex
    input_dir = Path(input_dir).expanduser().resolve()
    output_dir = Path(output_dir).expanduser().resolve()
    targets = sorted(path for path in input_dir.rglob(pattern) if path.is_file())
    LOGGER.info(
        "batch_start input_dir=%s output_dir=%s pattern=%s targets=%s workers=%s fail_fast=%s existing_policy=%s fidelity_policy=%s",
        input_dir,
        output_dir,
        pattern,
        len(targets),
        workers,
        fail_fast,
        existing_policy,
        fidelity_policy,
    )
    results = []
    worker_count = max(1, int(workers or 1))
    if worker_count == 1 or fail_fast:
        for target in targets:
            output = output_path_for_batch(target, input_dir, output_dir)
            result = convert_batch_target(
                target,
                output,
                expected_texts=expected_texts,
                strict_quality=strict_quality,
                existing_policy=existing_policy,
                fidelity_policy=fidelity_policy,
                embed_original=embed_original,
                decoded_style_bridge=decoded_style_bridge,
            )
            results.append(result)
            if fail_fast and result.get("status") == "FAIL":
                break
    else:
        ordered_results: list[dict[str, Any] | None] = [None] * len(targets)
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = {}
            for index, target in enumerate(targets):
                output = output_path_for_batch(target, input_dir, output_dir)
                future = executor.submit(
                    convert_batch_target,
                    target,
                    output,
                    expected_texts=expected_texts,
                    strict_quality=strict_quality,
                    existing_policy=existing_policy,
                    fidelity_policy=fidelity_policy,
                    embed_original=embed_original,
                    decoded_style_bridge=decoded_style_bridge,
                )
                futures[future] = index
            for future in as_completed(futures):
                ordered_results[futures[future]] = future.result()
        results = [result for result in ordered_results if result is not None]
    ok_count = sum(1 for result in results if result.get("status") == "PASS")
    skipped_count = sum(1 for result in results if result.get("status") == "SKIP")
    fail_count = len(results) - ok_count - skipped_count
    temp_cleanup = cleanup_temp_files(output_dir)
    report = attach_batch_gate({
        "status": "PASS" if targets and fail_count == 0 else "FAIL",
        "mode": "batch_text_only_rebuild",
        "job_id": resolved_job_id,
        "started_at": started.isoformat(),
        "finished_at": iso_now(),
        "duration_sec": round((utc_now() - started).total_seconds(), 6),
        "input_dir": str(input_dir),
        "output_dir": str(output_dir),
        "pattern": pattern,
        "target_count": len(targets),
        "ok_count": ok_count,
        "skipped_count": skipped_count,
        "fail_count": fail_count,
        "existing_policy": existing_policy,
        "fidelity_policy": fidelity_policy,
        "embed_original": embed_original,
        "decoded_style_bridge": decoded_style_bridge,
        "fail_fast": fail_fast,
        "workers": worker_count,
        "temp_cleanup": temp_cleanup,
        "results": results,
    })
    LOGGER.info(
        "batch_complete status=%s targets=%s ok=%s skipped=%s failed=%s output_dir=%s",
        report["status"],
        report["target_count"],
        report["ok_count"],
        report["skipped_count"],
        report["fail_count"],
        output_dir,
    )
    return report


def build_watch_gate(report: dict[str, Any]) -> dict[str, Any]:
    failed_results = [
        str(item.get("input") or index)
        for index, item in enumerate(
            report.get("results") if isinstance(report.get("results"), list) else []
        )
        if isinstance(item, dict) and item.get("status") not in {"PASS", "SKIP"}
    ]
    checks = [
        {
            "name": "input_directory",
            "status": "PASS" if Path(str(report.get("input_dir") or "")).is_dir() else "FAIL",
            "input_dir": report.get("input_dir"),
        },
        {
            "name": "watch_cycles",
            "status": "PASS" if int(report.get("cycle_count") or 0) > 0 else "FAIL",
            "cycle_count": report.get("cycle_count"),
        },
        {
            "name": "detected_files_processed",
            "status": "PASS" if not failed_results else "FAIL",
            "failed_items": failed_results,
        },
    ]
    failed = [check["name"] for check in checks if check["status"] != "PASS"]
    return {
        "status": "PASS" if not failed else "FAIL",
        "checked_at": iso_now(),
        "failed_checks": failed,
        "checks": checks,
    }


def attach_watch_gate(report: dict[str, Any]) -> dict[str, Any]:
    report["conversion_gate"] = build_watch_gate(report)
    return report


def detect_watch_targets(
    input_dir: Path, *, pattern: str, seen: dict[str, str]
) -> list[dict[str, Any]]:
    detections: list[dict[str, Any]] = []
    for target in sorted(path for path in input_dir.rglob(pattern) if path.is_file()):
        key = file_detection_key(target)
        target_id = str(target.resolve())
        if seen.get(target_id) == key:
            continue
        seen[target_id] = key
        detections.append({
            "detected_at": iso_now(),
            "input": str(target),
            "detection_key": key,
            "input_info": file_snapshot(target),
        })
    return detections


def convert_watch_detections(  # ruff: ignore[too-many-arguments] -- 외부 파일(hwp_realtime_audit_watch.py)에서도 호출, 시그니처 변경 보류
    detections: list[dict[str, Any]],
    input_dir: Path,
    output_dir: Path,
    *,
    expected_texts: list[str] | None,
    strict_quality: bool,
    existing_policy: str,
    fidelity_policy: str,
    embed_original: bool,
    decoded_style_bridge: bool = False,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for detection in detections:
        target = Path(str(detection["input"]))
        output = output_path_for_batch(target, input_dir, output_dir)
        result = convert_batch_target(
            target,
            output,
            expected_texts=expected_texts,
            strict_quality=strict_quality,
            existing_policy=existing_policy,
            fidelity_policy=fidelity_policy,
            embed_original=embed_original,
            decoded_style_bridge=decoded_style_bridge,
        )
        result["detected_at"] = detection.get("detected_at")
        result["detection_key"] = detection.get("detection_key")
        results.append(result)
    return results


def watch_batch(  # ruff: ignore[too-many-arguments] -- convert_batch/convert_watch_detections와 옵션 시그니처 통일, 변경 보류
    input_dir: Path,
    output_dir: Path,
    *,
    expected_texts: list[str] | None = None,
    strict_quality: bool = False,
    pattern: str = "*.hwp",
    existing_policy: str = "fail",
    fidelity_policy: str = "text",
    embed_original: bool = False,
    decoded_style_bridge: bool = False,
    interval_sec: float = 2.0,
    max_cycles: int | None = None,
    job_id: str | None = None,
) -> dict[str, Any]:
    started = utc_now()
    resolved_job_id = job_id or uuid4().hex
    input_dir = Path(input_dir).expanduser().resolve()
    output_dir = Path(output_dir).expanduser().resolve()
    seen: dict[str, str] = {}
    events: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    cycle = 0
    LOGGER.info(
        "watch_start input_dir=%s output_dir=%s pattern=%s interval_sec=%s max_cycles=%s existing_policy=%s fidelity_policy=%s",
        input_dir,
        output_dir,
        pattern,
        interval_sec,
        max_cycles,
        existing_policy,
        fidelity_policy,
    )
    while True:
        cycle += 1
        detections = detect_watch_targets(input_dir, pattern=pattern, seen=seen)
        cycle_results = convert_watch_detections(
            detections,
            input_dir,
            output_dir,
            expected_texts=expected_texts,
            strict_quality=strict_quality,
            existing_policy=existing_policy,
            fidelity_policy=fidelity_policy,
            embed_original=embed_original,
            decoded_style_bridge=decoded_style_bridge,
        )
        events.append({
            "cycle": cycle,
            "checked_at": iso_now(),
            "detected_count": len(detections),
            "detections": detections,
            "result_statuses": [item.get("status") for item in cycle_results],
        })
        results.extend(cycle_results)
        if max_cycles is not None and cycle >= max(1, int(max_cycles)):
            break
        time.sleep(max(0.1, float(interval_sec)))
    ok_count = sum(1 for result in results if result.get("status") == "PASS")
    skipped_count = sum(1 for result in results if result.get("status") == "SKIP")
    fail_count = len(results) - ok_count - skipped_count
    report = attach_watch_gate({
        "status": "PASS" if fail_count == 0 else "FAIL",
        "mode": "watch_text_only_rebuild",
        "job_id": resolved_job_id,
        "started_at": started.isoformat(),
        "finished_at": iso_now(),
        "duration_sec": round((utc_now() - started).total_seconds(), 6),
        "input_dir": str(input_dir),
        "output_dir": str(output_dir),
        "pattern": pattern,
        "cycle_count": cycle,
        "detected_count": len(results),
        "ok_count": ok_count,
        "skipped_count": skipped_count,
        "fail_count": fail_count,
        "existing_policy": existing_policy,
        "fidelity_policy": fidelity_policy,
        "embed_original": embed_original,
        "decoded_style_bridge": decoded_style_bridge,
        "interval_sec": interval_sec,
        "events": events,
        "results": results,
    })
    LOGGER.info(
        "watch_complete status=%s cycles=%s detected=%s ok=%s skipped=%s failed=%s output_dir=%s",
        report["status"],
        report["cycle_count"],
        report["detected_count"],
        report["ok_count"],
        report["skipped_count"],
        report["fail_count"],
        output_dir,
    )
    return report


def batch_csv_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    results = report.get("results") if isinstance(report, dict) else None
    if not isinstance(results, list):
        results = [report]
    rows: list[dict[str, Any]] = []
    for result in results:
        if not isinstance(result, dict):
            continue
        text_quality = (
            result.get("text_quality") if isinstance(result.get("text_quality"), dict) else {}
        )
        roundtrip = (
            result.get("roundtrip_text") if isinstance(result.get("roundtrip_text"), dict) else {}
        )
        table_reconstruction = (
            result.get("table_reconstruction")
            if isinstance(result.get("table_reconstruction"), dict)
            else {}
        )
        table_grid = (
            result.get("table_grid_gate") if isinstance(result.get("table_grid_gate"), dict) else {}
        )
        fidelity = (
            result.get("fidelity_gate") if isinstance(result.get("fidelity_gate"), dict) else {}
        )
        validation = result.get("validation") if isinstance(result.get("validation"), dict) else {}
        input_info = result.get("input_info") if isinstance(result.get("input_info"), dict) else {}
        output_info = (
            result.get("output_info") if isinstance(result.get("output_info"), dict) else {}
        )
        conversion_gate = (
            result.get("conversion_gate") if isinstance(result.get("conversion_gate"), dict) else {}
        )
        rows.append({
            "status": result.get("status"),
            "input": result.get("input"),
            "output": result.get("output"),
            "error": result.get("error"),
            "paragraph_count": result.get("paragraph_count"),
            "section_count": result.get("section_count"),
            "text_length": result.get("text_length"),
            "quality_status": text_quality.get("status"),
            "missing_expected_texts": "|".join(text_quality.get("missing_expected_texts") or []),
            "roundtrip_status": roundtrip.get("status"),
            "roundtrip_exact_match": roundtrip.get("exact_normalized_match"),
            "roundtrip_missing_line_count": roundtrip.get("missing_line_count"),
            "table_reconstruction_status": table_reconstruction.get("status"),
            "table_reconstruction_count": table_reconstruction.get("table_count"),
            "table_grid_status": table_grid.get("status"),
            "table_grid_expected_count": table_grid.get("expected_table_count"),
            "table_grid_actual_count": table_grid.get("actual_table_count"),
            "table_grid_mismatch_count": table_grid.get("mismatch_count"),
            "fidelity_status": fidelity.get("status"),
            "fidelity_policy": fidelity.get("policy"),
            "fidelity_risk_count": fidelity.get("risk_count"),
            "zip_ok": validation.get("zip_ok"),
            "xml_ok": validation.get("xml_ok"),
            "input_size": input_info.get("size"),
            "input_sha256": input_info.get("sha256"),
            "output_size": output_info.get("size"),
            "output_sha256": output_info.get("sha256"),
            "gate_status": conversion_gate.get("status"),
            "gate_failed_checks": "|".join(conversion_gate.get("failed_checks") or []),
        })
    return rows


def write_report(path: Path | None, report: dict[str, Any]) -> None:
    if not path:
        return
    path = Path(path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    LOGGER.info("report_json_written path=%s status=%s", path, report.get("status"))


def write_report_csv(path: Path | None, report: dict[str, Any]) -> None:
    if not path:
        return
    path = Path(path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = batch_csv_rows(report)
    if not rows:
        path.write_text("", encoding="utf-8-sig")
        return
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    LOGGER.info("report_csv_written path=%s rows=%s", path, len(rows))


def build_markdown_report(report: dict[str, Any]) -> str:
    gate = report.get("conversion_gate") if isinstance(report.get("conversion_gate"), dict) else {}
    lines = [
        "# HWP to HWPX Conversion Report",
        "",
        f"- Status: {report.get('status')}",
        f"- Mode: {report.get('mode')}",
        f"- Job ID: {report.get('job_id') or ''}",
        f"- Started: {report.get('started_at') or ''}",
        f"- Finished: {report.get('finished_at') or ''}",
        f"- Gate: {gate.get('status') or ''}",
        f"- Input: {report.get('input') or report.get('input_dir') or ''}",
        f"- Output: {report.get('output') or report.get('output_dir') or ''}",
        "",
    ]
    if report.get("mode") == "watch_text_only_rebuild":
        lines.extend([
            "## Realtime Detection",
            "",
            f"- Cycles: {report.get('cycle_count')}",
            f"- Detected: {report.get('detected_count')}",
            f"- Passed: {report.get('ok_count')}",
            f"- Skipped: {report.get('skipped_count')}",
            f"- Failed: {report.get('fail_count')}",
            "",
        ])
    rows = batch_csv_rows(report)
    if rows:
        lines.extend([
            "## Results",
            "",
            "| Status | Input | Output | Gate | Error |",
            "| --- | --- | --- | --- | --- |",
        ])
        for row in rows:
            lines.append(
                "| {status} | {input} | {output} | {gate} | {error} |".format(
                    status=row.get("status") or "",
                    input=row.get("input") or "",
                    output=row.get("output") or "",
                    gate=row.get("gate_status") or "",
                    error=row.get("error") or "",
                )
            )
        lines.append("")
    failed_checks = gate.get("failed_checks") if isinstance(gate.get("failed_checks"), list) else []
    if failed_checks:
        lines.extend(["## Failed Checks", "", *[f"- {item}" for item in failed_checks], ""])
    return "\n".join(lines)


def write_report_md(path: Path | None, report: dict[str, Any]) -> None:
    if not path:
        return
    path = Path(path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_markdown_report(report), encoding="utf-8")
    LOGGER.info("report_md_written path=%s status=%s", path, report.get("status"))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Standalone HWP -> text-only HWPX converter")
    parser.add_argument(
        "input", help="Input binary .hwp path, or an input directory for batch mode"
    )
    parser.add_argument("output", help="Output .hwpx path, or an output directory for batch mode")
    parser.add_argument("--report-json", help="Optional conversion report path")
    parser.add_argument("--report-csv", help="Optional CSV summary report path")
    parser.add_argument("--report-md", help="Optional Markdown summary report path")
    parser.add_argument(
        "--expected-text",
        action="append",
        default=[],
        help="Text that must be present after conversion. Can be repeated.",
    )
    parser.add_argument(
        "--strict-quality",
        action="store_true",
        help="Fail conversion when quality warnings such as mojibake markers are found.",
    )
    parser.add_argument(
        "--pattern", default="*.hwp", help="Batch mode file pattern. Default: *.hwp"
    )
    parser.add_argument(
        "--existing-policy",
        choices=EXISTING_POLICIES,
        default="fail",
        help="How to handle existing HWPX output: fail, skip, rename, or overwrite. Default: fail.",
    )
    parser.add_argument(
        "--fidelity-policy",
        choices=FIDELITY_POLICIES,
        default="text",
        help="How to handle HWP features that cannot be fully reconstructed: text, audit, or strict. Default: text.",
    )
    parser.add_argument(
        "--embed-original",
        action="store_true",
        help="Embed the byte-exact source HWP as Original/original.hwp and write Preview/OriginalManifest.json.",
    )
    parser.add_argument(
        "--decoded-style-bridge",
        action="store_true",
        help="Analyze HWP records after text conversion and inject decoded header/body style, page, and table mappings into HWPX.",
    )
    parser.add_argument(
        "--fail-fast", action="store_true", help="Stop batch conversion after the first failed file"
    )
    parser.add_argument("--workers", type=int, default=1, help="Parallel batch workers. Default: 1")
    parser.add_argument(
        "--log-file", help="Log file path. Default: hwp2hwpx.log under the output path"
    )
    parser.add_argument("--log-level", default="INFO", help="Log level. Default: INFO")
    parser.add_argument("--log-console", action="store_true", help="Also write logs to stderr")
    parser.add_argument(
        "--audit-log",
        help="Append JSONL audit log path. Default: hwp2hwpx_audit.jsonl under the output path",
    )
    parser.add_argument(
        "--audit-level",
        choices=AUDIT_LEVELS,
        default="standard",
        help="Audit detail level. Use forensic for hashes, gates, validation, and per-item batch rows.",
    )
    parser.add_argument(
        "--no-audit-log", action="store_true", help="Disable the default JSONL audit log"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Only build a batch plan; do not convert files"
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Continuously detect new or changed HWP files in an input directory",
    )
    parser.add_argument(
        "--watch-interval",
        type=float,
        default=2.0,
        help="Seconds between watch scans. Default: 2.0",
    )
    parser.add_argument(
        "--watch-max-cycles",
        type=int,
        help="Stop watch mode after this many scan cycles. Intended for smoke tests and scheduled runs.",
    )
    parser.add_argument("--job-id", help="Optional job id to include in reports and logs")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    input_path = Path(args.input)
    output_path = Path(args.output)
    log_path = Path(args.log_file) if args.log_file else default_log_path(input_path, output_path)
    audit_log_path = (
        None
        if args.no_audit_log
        else Path(args.audit_log)
        if args.audit_log
        else default_audit_log_path(input_path, output_path)
    )
    resolved_log_path = configure_logging(
        log_path, level=str(args.log_level), console=bool(args.log_console)
    )
    LOGGER.info(
        "run_start job_id=%s input=%s output=%s report_json=%s report_csv=%s report_md=%s log_file=%s audit_log=%s dry_run=%s watch=%s",
        args.job_id,
        input_path,
        output_path,
        args.report_json,
        args.report_csv,
        args.report_md,
        resolved_log_path,
        audit_log_path,
        args.dry_run,
        args.watch,
    )
    if args.watch:
        if not input_path.is_dir():
            report = attach_watch_gate({
                "status": "FAIL",
                "mode": "watch_text_only_rebuild",
                "job_id": args.job_id or uuid4().hex,
                "started_at": iso_now(),
                "finished_at": iso_now(),
                "input_dir": str(input_path),
                "output_dir": str(output_path),
                "pattern": str(args.pattern),
                "cycle_count": 0,
                "detected_count": 0,
                "ok_count": 0,
                "skipped_count": 0,
                "fail_count": 0,
                "error": "WATCH_INPUT_NOT_DIRECTORY",
                "events": [],
                "results": [],
            })
        else:
            report = watch_batch(
                input_path,
                output_path,
                expected_texts=list(args.expected_text or []),
                strict_quality=bool(args.strict_quality),
                pattern=str(args.pattern),
                existing_policy=str(args.existing_policy),
                fidelity_policy=str(args.fidelity_policy),
                embed_original=bool(args.embed_original),
                decoded_style_bridge=bool(args.decoded_style_bridge),
                interval_sec=float(args.watch_interval),
                max_cycles=int(args.watch_max_cycles) if args.watch_max_cycles else None,
                job_id=str(args.job_id) if args.job_id else None,
            )
    elif input_path.is_dir() and args.dry_run:
        report = build_batch_plan(
            input_path,
            output_path,
            pattern=str(args.pattern),
            existing_policy=str(args.existing_policy),
        )
        report["job_id"] = args.job_id or uuid4().hex
        LOGGER.info(
            "dry_run_complete job_id=%s targets=%s actions=%s",
            report["job_id"],
            report["target_count"],
            report["action_counts"],
        )
    elif input_path.is_dir():
        report = convert_batch(
            input_path,
            output_path,
            expected_texts=list(args.expected_text or []),
            strict_quality=bool(args.strict_quality),
            pattern=str(args.pattern),
            existing_policy=str(args.existing_policy),
            fidelity_policy=str(args.fidelity_policy),
            embed_original=bool(args.embed_original),
            decoded_style_bridge=bool(args.decoded_style_bridge),
            fail_fast=bool(args.fail_fast),
            workers=int(args.workers),
            job_id=str(args.job_id) if args.job_id else None,
        )
    else:
        report = convert_hwp_to_hwpx(
            input_path,
            output_path,
            expected_texts=list(args.expected_text or []),
            strict_quality=bool(args.strict_quality),
            existing_policy=str(args.existing_policy),
            fidelity_policy=str(args.fidelity_policy),
            embed_original=bool(args.embed_original),
            decoded_style_bridge=bool(args.decoded_style_bridge),
        )
        log_result("file_complete", report)
    write_report(Path(args.report_json) if args.report_json else None, report)
    write_report_csv(Path(args.report_csv) if args.report_csv else None, report)
    write_report_md(Path(args.report_md) if args.report_md else None, report)
    event = (
        "watch_report" if args.watch else "dry_run_plan" if args.dry_run else "conversion_report"
    )
    write_audit_log(audit_log_path, report, event=event, audit_level=str(args.audit_level))
    write_forensic_item_audit(audit_log_path, report, audit_level=str(args.audit_level))
    LOGGER.info(
        "run_complete status=%s log_file=%s audit_log=%s audit_level=%s gate=%s",
        report.get("status"),
        resolved_log_path,
        audit_log_path,
        args.audit_level,
        (report.get("conversion_gate") or {}).get("status"),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] in {"PASS", "SKIP"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
