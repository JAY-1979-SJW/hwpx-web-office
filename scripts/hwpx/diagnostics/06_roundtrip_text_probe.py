#!/usr/bin/env python3
"""Compare extracted HWP text with text read back from the converted HWPX."""

from __future__ import annotations

import argparse
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from hwp_diag_common import exit_code, print_report, status_from_errors, utc_now, write_report
from extract_hwp_body_fields import extract_hwp_text


SECTION_RE = re.compile(r"^contents/section\d+\.xml$", re.IGNORECASE)


def xml_local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def normalize_text(value: str) -> str:
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[ \t\f\v]+", " ", line).strip() for line in value.split("\n")]
    lines = [line for line in lines if line]
    return "\n".join(lines)


def read_hwpx_section_text(hwpx_path: Path) -> dict:
    entries: list[str] = []
    texts: list[str] = []
    xml_errors: list[dict[str, str]] = []
    with zipfile.ZipFile(hwpx_path) as zf:
        for name in sorted(zf.namelist(), key=lambda item: item.lower()):
            if not SECTION_RE.match(name.replace("\\", "/")):
                continue
            entries.append(name)
            payload = zf.read(name)
            try:
                root = ET.fromstring(payload)
            except ET.ParseError as exc:
                xml_errors.append({"entry": name, "error": str(exc)})
                continue
            paragraph_texts: list[str] = []
            for elem in root.iter():
                if xml_local_name(elem.tag) != "p":
                    continue
                paragraph_text = "".join(text for text in elem.itertext() if text)
                if paragraph_text:
                    paragraph_texts.append(paragraph_text)
            if paragraph_texts:
                texts.append("\n".join(paragraph_texts))
            else:
                chunks = [node.text for node in root.iter() if node.text]
                texts.append("\n".join(chunks))
    return {
        "entries": entries,
        "text": "\n".join(texts),
        "xml_errors": xml_errors,
    }


def sample_missing_lines(source_lines: list[str], target: str, *, limit: int = 20) -> list[str]:
    missing: list[str] = []
    for line in source_lines:
        if len(line) < 2:
            continue
        if line not in target:
            missing.append(line[:160])
        if len(missing) >= limit:
            break
    return missing


def check_roundtrip_text(input_path: Path, hwpx_path: Path, min_ratio: float) -> dict:
    input_path = Path(input_path).expanduser().resolve()
    hwpx_path = Path(hwpx_path).expanduser().resolve()
    errors: list[str] = []
    warnings: list[str] = []
    if not hwpx_path.exists():
        errors.append("HWPX_NOT_FOUND")
        hwpx = {"entries": [], "text": "", "xml_errors": []}
    else:
        try:
            hwpx = read_hwpx_section_text(hwpx_path)
        except zipfile.BadZipFile:
            errors.append("HWPX_NOT_ZIP")
            hwpx = {"entries": [], "text": "", "xml_errors": []}

    extraction = extract_hwp_text(input_path)
    if not extraction.get("ok"):
        errors.append(str(extraction.get("error") or "HWP_EXTRACTION_FAILED"))

    source_text = normalize_text(str(extraction.get("text") or ""))
    target_text = normalize_text(str(hwpx.get("text") or ""))
    source_len = len(source_text)
    target_len = len(target_text)
    length_ratio = (target_len / source_len) if source_len else 0.0
    exact_match = source_text == target_text
    source_lines = [line for line in source_text.splitlines() if line.strip()]
    missing_lines = sample_missing_lines(source_lines, target_text)

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
    if not exact_match and not missing_lines and not errors:
        warnings.append("TEXT_NORMALIZATION_NOT_EXACT")

    return {
        "status": status_from_errors(errors, warnings),
        "tool": "06_roundtrip_text_probe",
        "checked_at": utc_now(),
        "input": str(input_path),
        "hwpx": str(hwpx_path),
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
        "errors": errors,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("hwpx", type=Path)
    parser.add_argument("--min-ratio", type=float, default=0.98)
    parser.add_argument("--report-json", type=Path)
    args = parser.parse_args()
    report = check_roundtrip_text(args.input, args.hwpx, args.min_ratio)
    write_report(args.report_json, report)
    print_report(report)
    return exit_code(report)


if __name__ == "__main__":
    raise SystemExit(main())
