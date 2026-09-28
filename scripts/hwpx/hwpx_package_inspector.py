"""Inspect HWPX ZIP/XML package structure without Hancom automation.

This tool intentionally records package metadata and XML structure counts only.
It does not persist document body text.
"""

from __future__ import annotations

import argparse
import json
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

IMAGE_EXTENSIONS = {".bmp", ".gif", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".wmf", ".emf"}


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def _is_xml_entry(name: str) -> bool:
    lower = name.lower()
    return lower.endswith(".xml") or lower.endswith(".hpf") or lower.endswith(".rdf")


def _is_section_entry(name: str) -> bool:
    lower = name.replace("\\", "/").lower()
    return lower.startswith("contents/section") and lower.endswith(".xml")


def _is_bindata_entry(name: str) -> bool:
    normalized = name.replace("\\", "/")
    return normalized.lower().startswith("bindata/")


def _is_image_entry(name: str) -> bool:
    return Path(name).suffix.lower() in IMAGE_EXTENSIONS


def _read_text_from_zip(zf: zipfile.ZipFile, entry: str) -> str:
    raw = zf.read(entry)
    for encoding in ("utf-8", "utf-16", "cp949"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _element_image_hits(elem: ET.Element) -> int:
    hits = 0
    for value in elem.attrib.values():
        value_lower = value.lower()
        if "bindata" in value_lower or any(ext in value_lower for ext in IMAGE_EXTENSIONS):
            hits += 1
    if elem.text and re.search(r"BinData|\.png|\.jpg|\.jpeg|\.bmp|\.gif", elem.text, re.I):
        hits += 1
    return hits


def _scan_xml_root(root: ET.Element, result: dict) -> int:
    image_hits = 0
    for elem in root.iter():
        local = _local_name(elem.tag).lower()
        if elem.text and elem.text.strip():
            result["text_node_count"] += 1
        if local in {"tbl", "table"} or "tbl" in local or "table" in local:
            result["table_candidate_count"] += 1
        image_hits += _element_image_hits(elem)
    return image_hits


def _scan_xml_entries(zf: zipfile.ZipFile, xml_entries: list[str], result: dict) -> int:
    image_count = 0
    for entry in xml_entries:
        try:
            text = _read_text_from_zip(zf, entry)
            root = ET.fromstring(text.encode("utf-8"))
        except Exception as exc:  # ruff: ignore[blind-except] - metadata report, not strict parser
            result["xml_parse_errors"].append({"entry": entry, "error": str(exc)})
            continue
        image_count += _scan_xml_root(root, result)
    return image_count


def inspect_hwpx(path: Path) -> dict:
    path = Path(path)
    result = {
        "file": str(path),
        "size": path.stat().st_size if path.exists() else None,
        "zip_ok": False,
        "entry_count": 0,
        "xml_entries": [],
        "section_entries": [],
        "bindata_entries": [],
        "has_mimetype": False,
        "has_settings": False,
        "has_header": False,
        "text_node_count": 0,
        "table_candidate_count": 0,
        "image_candidate_count": 0,
        "xml_parse_errors": [],
        "entries": [],
    }

    if not path.exists():
        result["error"] = "FILE_NOT_FOUND"
        return result

    try:
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            result["zip_ok"] = True
            result["entry_count"] = len(names)
            result["entries"] = [
                {
                    "name": info.filename,
                    "size": info.file_size,
                    "compressed_size": info.compress_size,
                }
                for info in zf.infolist()
            ]
            result["xml_entries"] = [name for name in names if _is_xml_entry(name)]
            result["section_entries"] = [name for name in names if _is_section_entry(name)]
            result["bindata_entries"] = [name for name in names if _is_bindata_entry(name)]
            lower_names = {name.lower() for name in names}
            result["has_mimetype"] = "mimetype" in lower_names
            result["has_settings"] = any(name.endswith("settings.xml") for name in lower_names)
            result["has_header"] = any(name.endswith("header.xml") for name in lower_names)

            image_count = 0
            for entry in result["bindata_entries"]:
                if _is_image_entry(entry):
                    image_count += 1

            image_count += _scan_xml_entries(zf, result["xml_entries"], result)

            result["image_candidate_count"] = image_count
    except zipfile.BadZipFile:
        result["error"] = "BAD_ZIP"
    except Exception as exc:  # ruff: ignore[blind-except]
        result["error"] = str(exc)

    return result


def write_inspection(result: dict, out_path: Path | None) -> None:
    if not out_path:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    txt_path = out_path.with_suffix(".txt")
    lines = [
        f"file={result.get('file')}",
        f"size={result.get('size')}",
        f"zip_ok={result.get('zip_ok')}",
        f"entry_count={result.get('entry_count')}",
        f"xml_entries={len(result.get('xml_entries', []))}",
        f"section_entries={len(result.get('section_entries', []))}",
        f"bindata_entries={len(result.get('bindata_entries', []))}",
        f"text_node_count={result.get('text_node_count')}",
        f"table_candidate_count={result.get('table_candidate_count')}",
        f"image_candidate_count={result.get('image_candidate_count')}",
    ]
    txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect HWPX ZIP/XML package structure.")
    parser.add_argument("--input", required=True, help="Input HWPX path")
    parser.add_argument("--out", help="Output JSON path")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = inspect_hwpx(Path(args.input))
    write_inspection(result, Path(args.out) if args.out else None)
    return 0 if result.get("zip_ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
