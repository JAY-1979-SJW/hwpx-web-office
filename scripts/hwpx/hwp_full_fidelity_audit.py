"""Audit, metadata, and source-preservation helpers for HWP full-fidelity work."""

from __future__ import annotations

import hashlib
import importlib
import json
import zipfile
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import olefile
from extract_hwp_body_fields import FIDELITY_RISK_TAGS, HWP_RECORD_TAGS, TEXT_ONLY_SUPPORTED_TAGS

OLE_METADATA_FIELDS = [
    "title",
    "subject",
    "author",
    "keywords",
    "comments",
    "template",
    "last_saved_by",
    "revision_number",
    "total_edit_time",
    "last_printed",
    "create_time",
    "last_saved_time",
    "num_pages",
    "num_words",
    "num_chars",
    "creating_application",
    "security",
    "codepage",
    "category",
    "presentation_target",
    "bytes",
    "lines",
    "paragraphs",
    "slides",
    "notes",
    "hidden_slides",
    "mm_clips",
    "scale_crop",
    "heading_pairs",
    "titles_of_parts",
    "manager",
    "company",
    "links_dirty",
    "chars_with_spaces",
    "shared_doc",
    "link_base",
    "hlinks",
    "hlinks_changed",
    "version",
    "dig_sig",
    "content_type",
    "content_status",
    "language",
    "doc_version",
]
RECORD_AUDIT_SAMPLE_LIMIT = 5
IDENTITY_PREVIEW_ENTRIES = [
    "Preview/DecodedDocInfo.json",
    "Preview/DocumentMetadata.json",
    "Preview/FullFidelityCoverage.json",
    "Preview/RecordAudit.json",
    "Preview/SourceManifest.json",
    "Preview/OriginalIntegrity.json",
    "Preview/ListStyleMapping.json",
    "Preview/BinDataPreservation.json",
    "Preview/BodyStyleMapping.json",
    "Preview/PageLayoutMapping.json",
    "Preview/TableLayoutMapping.json",
    "Preview/VisualObjectMapping.json",
]


def _record_name(tag_id: int) -> str:
    return HWP_RECORD_TAGS.get(tag_id, f"UNKNOWN_{tag_id}")


def _json_safe_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, bytes):
        return {"size": len(value), "hex_prefix": value[:32].hex(" ")}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        return [_json_safe_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe_value(item) for key, item in value.items()}
    return str(value)


def read_ole_metadata(ole: olefile.OleFileIO) -> dict[str, Any]:
    try:
        metadata = ole.get_metadata()
    except Exception as exc:  # ruff: ignore[blind-except]
        return {"status": "FAIL", "error": type(exc).__name__, "message": str(exc)}
    fields: dict[str, Any] = {}
    present = []
    for name in OLE_METADATA_FIELDS:
        value = getattr(metadata, name, None)
        safe = _json_safe_value(value)
        fields[name] = safe
        if safe not in (None, "", [], {}):
            present.append(name)
    return {
        "status": "PASS",
        "present_fields": present,
        "present_field_count": len(present),
        "fields": fields,
    }


def _source_stream_kind(name: str) -> str:
    if name == "FileHeader":
        return "header"
    if name == "DocInfo":
        return "docinfo"
    if name.startswith("BodyText/"):
        return "body_text"
    if name.startswith("BinData/"):
        return "binary_data"
    if name.startswith("DocOptions/"):
        return "doc_options"
    if name.startswith("Scripts/"):
        return "script"
    if name.startswith("Prv"):
        return "preview"
    if "SummaryInformation" in name:
        return "summary_information"
    return "other"


def build_source_manifest(
    ole: olefile.OleFileIO, input_info: dict[str, Any], streams: list[str]
) -> dict[str, Any]:
    try:
        storages = sorted("/".join(item) for item in ole.listdir(streams=False, storages=True))
    except Exception:  # ruff: ignore[blind-except]
        storages = []

    entries: list[dict[str, Any]] = []
    unreadable: list[dict[str, str]] = []
    total_stream_bytes = 0
    for name in streams:
        try:
            raw = ole.openstream(name).read()
        except Exception as exc:  # ruff: ignore[blind-except]
            unreadable.append({"name": name, "error": type(exc).__name__, "message": str(exc)})
            continue
        total_stream_bytes += len(raw)
        entries.append({
            "name": name,
            "kind": _source_stream_kind(name),
            "size": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
        })

    return {
        "status": "PASS" if not unreadable else "WARN",
        "input_info": input_info,
        "stream_count": len(streams),
        "hashed_stream_count": len(entries),
        "storage_count": len(storages),
        "total_stream_bytes": total_stream_bytes,
        "streams": entries,
        "storages": storages,
        "unreadable_streams": unreadable,
        "unreadable_stream_count": len(unreadable),
    }


def build_original_integrity(
    output_path: Path, entries: dict[str, bytes], source_manifest: dict[str, Any]
) -> dict[str, Any]:
    input_info = (
        source_manifest.get("input_info")
        if isinstance(source_manifest.get("input_info"), dict)
        else {}
    )
    expected_sha = input_info.get("sha256")
    expected_size = input_info.get("size")
    source_path = str(input_info.get("path") or "")
    entry_name = "Original/original.hwp"
    package_name = Path(output_path).name
    source_name = Path(source_path).name if source_path else ""

    result: dict[str, Any] = {
        "entry_name": entry_name,
        "source_file_name": source_name,
        "package_file_name": package_name,
        "file_name_changed": bool(source_name and source_name != package_name),
        "expected": {
            "path": source_path,
            "size": expected_size,
            "sha256": expected_sha,
        },
    }
    payload = entries.get(entry_name)
    if payload is None:
        result.update({
            "status": "FAIL",
            "error": "EMBEDDED_ORIGINAL_NOT_FOUND",
            "byte_exact_original_embedded": False,
        })
        return result

    embedded = {
        "size": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }
    size_match = expected_size == embedded["size"]
    sha_match = expected_sha == embedded["sha256"]
    result.update({
        "status": "PASS" if size_match and sha_match else "FAIL",
        "embedded": embedded,
        "size_match": size_match,
        "sha256_match": sha_match,
        "byte_exact_original_embedded": size_match and sha_match,
    })
    return result


def _record_audit_sample(stream: str, record: dict[str, Any]) -> dict[str, Any]:
    sample: dict[str, Any] = {
        "stream": stream,
        "index": record.get("index"),
        "level": record.get("level"),
        "payload_size": record.get("payload_size"),
        "payload_prefix_hex": record.get("payload_prefix_hex", ""),
    }
    decoded = record.get("decoded")
    if isinstance(decoded, dict):
        if "decode_error" in decoded:
            sample["decode_error"] = decoded.get("decode_error")
            sample["decode_message"] = decoded.get("message", "")
        else:
            sample["decoded_keys"] = sorted(str(key) for key in decoded.keys())[:12]
    return sample


def build_record_audit(
    docinfo_records: list[dict[str, Any]],
    body_records_by_section: dict[str, list[dict[str, Any]]],
    bindata_streams: list[str],
) -> dict[str, Any]:
    records_by_stream: list[tuple[str, list[dict[str, Any]]]] = [("DocInfo", docinfo_records)]
    records_by_stream.extend(sorted(body_records_by_section.items()))

    counts: Counter[int] = Counter()
    decoded_counts: Counter[int] = Counter()
    unknown_samples: dict[int, list[dict[str, Any]]] = {}
    risk_samples: dict[int, list[dict[str, Any]]] = {}
    decoded_error_count = 0

    for stream, records in records_by_stream:
        for record in records:
            tag_id = int(record.get("tag_id", -1))
            counts[tag_id] += 1
            decoded = record.get("decoded")
            if isinstance(decoded, dict):
                decoded_counts[tag_id] += 1
                if "decode_error" in decoded:
                    decoded_error_count += 1
            if tag_id not in HWP_RECORD_TAGS:
                samples = unknown_samples.setdefault(tag_id, [])
                if len(samples) < RECORD_AUDIT_SAMPLE_LIMIT:
                    samples.append(_record_audit_sample(stream, record))
            if tag_id in FIDELITY_RISK_TAGS or tag_id not in TEXT_ONLY_SUPPORTED_TAGS:
                samples = risk_samples.setdefault(tag_id, [])
                if len(samples) < RECORD_AUDIT_SAMPLE_LIMIT:
                    samples.append(_record_audit_sample(stream, record))

    def tag_rows(sample_map: dict[int, list[dict[str, Any]]]) -> list[dict[str, Any]]:
        return [
            {
                "tag_id": tag_id,
                "tag_name": _record_name(tag_id),
                "count": counts[tag_id],
                "samples": sample_map.get(tag_id, []),
            }
            for tag_id in sorted(sample_map)
        ]

    decoded_tags = [
        {
            "tag_id": tag_id,
            "tag_name": _record_name(tag_id),
            "decoded_count": decoded_counts[tag_id],
            "record_count": counts[tag_id],
        }
        for tag_id in sorted(decoded_counts)
    ]
    return {
        "status": "PASS",
        "sample_limit_per_tag": RECORD_AUDIT_SAMPLE_LIMIT,
        "record_count": sum(counts.values()),
        "tag_count": len(counts),
        "decoded_record_count": sum(decoded_counts.values()),
        "decoded_tag_count": len(decoded_counts),
        "decoded_error_count": decoded_error_count,
        "decoded_tags": decoded_tags,
        "unknown_record_count": sum(counts[tag_id] for tag_id in unknown_samples),
        "unknown_tag_count": len(unknown_samples),
        "unknown_tags": tag_rows(unknown_samples),
        "risk_record_count": sum(counts[tag_id] for tag_id in risk_samples),
        "risk_tag_count": len(risk_samples),
        "risk_tags": tag_rows(risk_samples),
        "bindata_stream_count": len(bindata_streams),
        "bindata_streams": bindata_streams,
    }


def _read_json_entry(entries: dict[str, bytes], name: str) -> dict[str, Any]:
    payload = entries.get(name)
    if payload is None:
        return {"status": "MISSING", "entry": name}
    try:
        parsed = json.loads(payload.decode("utf-8"))
    except Exception as exc:  # ruff: ignore[blind-except]
        return {
            "status": "FAIL",
            "entry": name,
            "error": type(exc).__name__,
            "message": str(exc),
        }
    if isinstance(parsed, dict):
        return {"status": "PASS", "entry": name, "data": parsed}
    return {"status": "FAIL", "entry": name, "error": "JSON_ROOT_NOT_OBJECT"}


def _json_data(entry_report: dict[str, Any]) -> dict[str, Any]:
    data = entry_report.get("data")
    return data if isinstance(data, dict) else {}


def _mapping_summary(name: str, report: dict[str, Any]) -> dict[str, Any]:
    data = _json_data(report)
    if not data:
        return {
            "name": name,
            "status": report.get("status", "MISSING"),
            "reason": "MAPPING_REPORT_MISSING",
        }
    status = str(data.get("status") or "PASS")
    failures = []
    for key, value in data.items():
        if key.endswith("_failed") and value:
            failures.append(key)
        if key.endswith("_mismatch_count") and int(value or 0) > 0:
            failures.append(key)
    return {
        "name": name,
        "status": "FAIL" if status == "FAIL" or failures else status,
        "failure_keys": failures,
        "summary": {
            key: value
            for key, value in data.items()
            if key.endswith("_count") or key in {"status", "reason", "updated_section_count"}
        },
    }


def _resolve_analysis(input_path: Path, analysis: dict[str, Any] | None) -> dict[str, Any]:
    if analysis is not None:
        return analysis
    try:
        analyze_hwp = importlib.import_module("hwp_full_fidelity_analyzer").analyze_hwp
        return analyze_hwp(input_path, include_records=False)
    except Exception as exc:  # ruff: ignore[blind-except]
        return {
            "status": "FAIL",
            "error": "ANALYSIS_EXCEPTION",
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        }


def _resolve_output_validation(input_path: Path, output_path: Path) -> tuple[Any, Any, Any]:
    try:
        file_snapshot = importlib.import_module("hwp_to_hwpx_standalone").file_snapshot
        HwpxValidator = importlib.import_module("hwpx_package").HwpxValidator
        input_info = file_snapshot(input_path)
        output_info = file_snapshot(output_path)
        validation = (
            HwpxValidator.validate_hwpx(output_path)
            if output_path.exists()
            else {"zip_ok": False, "xml_ok": False, "error": "OUTPUT_NOT_FOUND"}
        )
    except Exception as exc:  # ruff: ignore[blind-except]
        input_info = {"path": str(input_path), "exists": input_path.exists()}
        output_info = {"path": str(output_path), "exists": output_path.exists()}
        validation = {
            "zip_ok": False,
            "xml_ok": False,
            "error": "VALIDATION_EXCEPTION",
            "error_type": type(exc).__name__,
            "message": str(exc),
        }
    return input_info, output_info, validation


def _extract_output_package(output_path: Path, validation: dict[str, Any]) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    entries: dict[str, bytes] = {}
    entry_names: list[str] = []
    if not output_path.exists():
        blockers.append("OUTPUT_NOT_FOUND")
    elif validation.get("zip_ok") is not True:
        blockers.append("HWPX_ZIP_INVALID")
    elif validation.get("xml_ok") is not True:
        blockers.append("HWPX_XML_INVALID")

    if output_path.exists():
        try:
            with zipfile.ZipFile(output_path, "r") as zf:
                entry_names = [name.replace("\\", "/") for name in zf.namelist()]
                entries = {name.replace("\\", "/"): zf.read(name) for name in zf.namelist()}
        except Exception as exc:  # ruff: ignore[blind-except]
            blockers.append("HWPX_PACKAGE_READ_FAILED")
            warnings.append(f"{type(exc).__name__}: {exc}")

    missing_entries = [name for name in IDENTITY_PREVIEW_ENTRIES if name not in entries]
    if missing_entries:
        blockers.append("FULL_FIDELITY_PREVIEW_EVIDENCE_MISSING")
    return {
        "blockers": blockers,
        "warnings": warnings,
        "entries": entries,
        "entry_names": entry_names,
        "missing_entries": missing_entries,
    }


def _check_original_integrity(
    output_path: Path, entries: dict[str, bytes], analysis: dict[str, Any], input_info: Any
) -> tuple[list[str], dict[str, Any]]:
    source_manifest = (
        analysis.get("source_manifest") if isinstance(analysis.get("source_manifest"), dict) else {}
    )
    if not source_manifest:
        source_manifest = {"input_info": input_info}
    elif not isinstance(source_manifest.get("input_info"), dict):
        source_manifest = {**source_manifest, "input_info": input_info}
    original_integrity = build_original_integrity(output_path, entries, source_manifest)
    blockers = []
    if original_integrity.get("byte_exact_original_embedded") is not True:
        blockers.append("EMBEDDED_ORIGINAL_NOT_BYTE_EXACT")
    return blockers, original_integrity


def _check_coverage(
    entries: dict[str, bytes], analysis: dict[str, Any]
) -> tuple[list[str], dict[str, Any]]:
    coverage_report = _read_json_entry(entries, "Preview/FullFidelityCoverage.json")
    coverage = _json_data(coverage_report) or (
        analysis.get("coverage") if isinstance(analysis.get("coverage"), dict) else {}
    )
    blockers = []
    if analysis.get("status") != "PASS":
        blockers.append("SOURCE_ANALYSIS_NOT_PASS")
    if coverage.get("full_fidelity_ready") is not True:
        blockers.append("FULL_FIDELITY_COVERAGE_INCOMPLETE")
    return blockers, coverage


def _check_conversion_mode(entries: dict[str, bytes]) -> list[str]:
    conversion_report = _read_json_entry(entries, "Preview/ConversionReport.json")
    conversion_data = _json_data(conversion_report)
    original_preservation = (
        conversion_data.get("original_preservation")
        if isinstance(conversion_data.get("original_preservation"), dict)
        else {}
    )
    preservation = (
        original_preservation.get("preservation")
        if isinstance(original_preservation.get("preservation"), dict)
        else {}
    )
    blockers = []
    if preservation.get("ai_readable_derivative_is_text_only_rebuild") is True:
        blockers.append("TEXT_ONLY_DERIVATIVE_OUTPUT")
    if str(conversion_data.get("mode") or "").startswith("text_only_rebuild"):
        blockers.append("CONVERSION_MODE_NOT_FULL_FIDELITY")
    return blockers


def _check_mappings(entries: dict[str, bytes]) -> tuple[list[str], list[dict[str, Any]]]:
    mapping_reports = [
        _mapping_summary("body_style", _read_json_entry(entries, "Preview/BodyStyleMapping.json")),
        _mapping_summary(
            "page_layout", _read_json_entry(entries, "Preview/PageLayoutMapping.json")
        ),
        _mapping_summary(
            "table_layout", _read_json_entry(entries, "Preview/TableLayoutMapping.json")
        ),
        _mapping_summary("list_style", _read_json_entry(entries, "Preview/ListStyleMapping.json")),
    ]
    failed_mappings = [item["name"] for item in mapping_reports if item.get("status") == "FAIL"]
    blockers = ["HWPX_MAPPING_AUDIT_FAILED"] if failed_mappings else []
    return blockers, mapping_reports


def _check_record_audit(
    entries: dict[str, bytes], analysis: dict[str, Any]
) -> tuple[list[str], dict[str, Any]]:
    record_audit = _json_data(_read_json_entry(entries, "Preview/RecordAudit.json")) or (
        analysis.get("record_audit") if isinstance(analysis.get("record_audit"), dict) else {}
    )
    blockers = []
    if int(record_audit.get("unknown_tag_count") or 0) > 0:
        blockers.append("UNKNOWN_HWP_RECORDS_PRESENT")
    if int(record_audit.get("decoded_error_count") or 0) > 0:
        blockers.append("HWP_RECORD_DECODE_ERRORS_PRESENT")
    return blockers, record_audit


def build_identity_audit(
    input_path: Path,
    output_path: Path,
    *,
    analysis: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Fail-closed source/output equivalence audit.

    PASS means the output has enough evidence to be treated as full-fidelity.
    Current text-only derivative packages should fail this gate by design.
    """

    input_path = Path(input_path).expanduser().resolve()
    output_path = Path(output_path).expanduser().resolve()
    blockers: list[str] = []
    warnings: list[str] = []

    analysis = _resolve_analysis(input_path, analysis)
    input_info, output_info, validation = _resolve_output_validation(input_path, output_path)

    package = _extract_output_package(output_path, validation)
    blockers.extend(package["blockers"])
    warnings.extend(package["warnings"])
    entries = package["entries"]
    entry_names = package["entry_names"]
    missing_entries = package["missing_entries"]

    integrity_blockers, original_integrity = _check_original_integrity(
        output_path, entries, analysis, input_info
    )
    blockers.extend(integrity_blockers)

    coverage_blockers, coverage = _check_coverage(entries, analysis)
    blockers.extend(coverage_blockers)
    blockers.extend(_check_conversion_mode(entries))

    mapping_blockers, mapping_reports = _check_mappings(entries)
    blockers.extend(mapping_blockers)

    record_audit_blockers, record_audit = _check_record_audit(entries, analysis)
    blockers.extend(record_audit_blockers)

    blocker_counts = dict(Counter(blockers))
    return {
        "status": "PASS" if not blockers else "FAIL",
        "mode": "full_fidelity_identity_audit",
        "input": str(input_path),
        "output": str(output_path),
        "input_info": input_info,
        "output_info": output_info,
        "validation": validation,
        "source_analysis_status": analysis.get("status"),
        "coverage_status": coverage.get("status"),
        "full_fidelity_ready": coverage.get("full_fidelity_ready") is True,
        "coverage_blockers": coverage.get("blockers", []),
        "identity_equal": not blockers,
        "blocker_count": len(blockers),
        "blockers": sorted(blocker_counts),
        "blocker_counts": blocker_counts,
        "warnings": warnings,
        "required_preview_entries": IDENTITY_PREVIEW_ENTRIES,
        "missing_preview_entries": missing_entries,
        "package_entry_count": len(entry_names),
        "original_integrity": original_integrity,
        "mapping_reports": mapping_reports,
        "record_audit_summary": {
            "record_count": record_audit.get("record_count", 0),
            "unknown_tag_count": record_audit.get("unknown_tag_count", 0),
            "risk_tag_count": record_audit.get("risk_tag_count", 0),
            "decoded_error_count": record_audit.get("decoded_error_count", 0),
        },
        "text_only_derivative": "TEXT_ONLY_DERIVATIVE_OUTPUT" in blocker_counts
        or "CONVERSION_MODE_NOT_FULL_FIDELITY" in blocker_counts,
    }
