"""Preview text generation for HWPX packages."""

from __future__ import annotations

from typing import Any

from hwpx_metadata_ops import inspect_document_metadata
from hwpx_package import HwpxPackage, local_name


PREVIEW_TEXT_ENTRY = "Preview/PrvText.txt"


def _clean(value: str) -> str:
    return " ".join(value.split())


def _section_text(package: HwpxPackage) -> list[str]:
    values: list[str] = []
    for entry in package.section_entries():
        try:
            root = package.read_xml(entry)
        except Exception:
            continue
        values.extend(_clean(elem.text) for elem in root.iter() if local_name(elem.tag) == "t" and elem.text and elem.text.strip())
    return values


def _metadata_text(package: HwpxPackage) -> list[str]:
    report = inspect_document_metadata(package)
    if report.get("status") != "PASS":
        return []
    values: list[str] = [_clean(str(value)) for value in report.get("metadata", {}).values() if value]
    values.extend(_clean(str(value)) for value in report.get("meta", {}).values() if value)
    return values


def build_preview_text(package: HwpxPackage, spec: dict[str, Any] | None = None) -> dict[str, Any]:
    spec = spec or {}
    if spec.get("enabled") is False:
        return {"status": "SKIPPED"}
    include_metadata = bool(spec.get("include_metadata", True))
    max_chars = spec.get("max_chars", 4000)
    if not isinstance(max_chars, int) or max_chars < 1:
        return {"status": "PREVIEW_MAX_CHARS_INVALID", "value": max_chars}

    values: list[str] = []
    if include_metadata:
        values.extend(_metadata_text(package))
    values.extend(_section_text(package))

    seen = set()
    deduped = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            deduped.append(value)
    text = "\n".join(deduped)
    truncated = len(text) > max_chars
    if truncated:
        text = text[:max_chars]
    package.set_entry(PREVIEW_TEXT_ENTRY, text.encode("utf-8"))
    return {
        "status": "PREVIEW_TEXT_SET_PASS",
        "entry": PREVIEW_TEXT_ENTRY,
        "include_metadata": include_metadata,
        "source_text_count": len(values),
        "unique_text_count": len(deduped),
        "length": len(text),
        "truncated": truncated,
        "preview": text[:300],
    }


def inspect_preview_text(package: HwpxPackage) -> dict[str, Any]:
    if PREVIEW_TEXT_ENTRY not in package.entries:
        return {"status": "PREVIEW_TEXT_NOT_FOUND", "entry": PREVIEW_TEXT_ENTRY}
    text = package.entries[PREVIEW_TEXT_ENTRY].decode("utf-8", errors="replace")
    return {
        "status": "PASS",
        "entry": PREVIEW_TEXT_ENTRY,
        "length": len(text),
        "line_count": len([line for line in text.splitlines() if line.strip()]),
        "preview": text[:300],
    }


__all__ = ["PREVIEW_TEXT_ENTRY", "build_preview_text", "inspect_preview_text"]
