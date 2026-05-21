"""Validation helpers for rendered HWPX artifacts."""

from __future__ import annotations

from pathlib import Path
import zipfile
import xml.etree.ElementTree as ET

from hwpx_package import HwpxValidator, decode_xml, is_xml_entry, package_has_placeholders


def package_contains_text(path: Path, values: list[str]) -> dict[str, bool]:
    haystack = []
    with zipfile.ZipFile(path) as zf:
        for name in zf.namelist():
            if not is_xml_entry(name):
                continue
            try:
                root = ET.fromstring(decode_xml(zf.read(name)).encode("utf-8"))
            except Exception:
                continue
            for elem in root.iter():
                if elem.text:
                    haystack.append(elem.text)
                if elem.tail:
                    haystack.append(elem.tail)
    text = "\n".join(haystack)
    return {value: value in text for value in values}


def validate_rendered(path: Path, expected: list[str] | None = None) -> dict:
    validation = HwpxValidator.validate_hwpx(path)
    validation["placeholder_remaining"] = package_has_placeholders(path) if validation.get("zip_ok") else None
    if expected:
        contains = package_contains_text(path, expected)
        validation["expected_values_found"] = [value for value, found in contains.items() if found]
        validation["missing_expected_values"] = [value for value, found in contains.items() if not found]
    else:
        validation["expected_values_found"] = []
        validation["missing_expected_values"] = []
    return validation
