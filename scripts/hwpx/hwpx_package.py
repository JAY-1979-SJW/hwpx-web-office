"""Shared HWPX package, XML, validation, and file IO helpers."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any
import re
import zipfile
import xml.etree.ElementTree as ET


def local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def is_xml_entry(name: str) -> bool:
    lower = name.lower()
    return lower.endswith(".xml") or lower.endswith(".hpf") or lower.endswith(".rdf")


def is_section_entry(name: str) -> bool:
    normalized = name.replace("\\", "/").lower()
    return normalized.startswith("contents/section") and normalized.endswith(".xml")


def normalize_entry_name(name: str, *, base_entry: str | None = None) -> str:
    normalized = name.replace("\\", "/")
    if normalized.startswith("../"):
        if base_entry:
            base = Path(base_entry.replace("\\", "/")).parent
            normalized = str((base / normalized).as_posix())
        else:
            normalized = normalized[3:]
    while normalized.startswith("./"):
        normalized = normalized[2:]
    parts: list[str] = []
    for part in normalized.split("/"):
        if not part or part == ".":
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    return "/".join(parts)


def decode_xml(raw: bytes) -> str:
    for encoding in ("utf-8", "utf-16", "cp949"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def detect_text_encoding(raw: bytes) -> dict[str, Any]:
    for encoding in ("utf-8", "utf-8-sig", "utf-16", "cp949"):
        try:
            text = raw.decode(encoding)
            return {"encoding": encoding, "decode_ok": True, "text": text}
        except UnicodeDecodeError:
            continue
    return {"encoding": "utf-8-replace", "decode_ok": False, "text": raw.decode("utf-8", errors="replace")}


MOJIBAKE_PATTERNS = (
    "臾몄",
    "媛먮",
    "?낅젰",
    "?꾩슂",
    "?쒓",
    "踰덊",
    "二쇱",
    "瑜?",
)


def text_quality_report(text: str, *, max_examples: int = 8) -> dict[str, Any]:
    replacement_count = text.count("\ufffd")
    control_count = sum(1 for ch in text if ord(ch) < 32 and ch not in "\r\n\t")
    mojibake_hits = []
    for pattern in MOJIBAKE_PATTERNS:
        count = text.count(pattern)
        if count:
            mojibake_hits.append({"pattern": pattern, "count": count})
    examples = []
    for pattern in MOJIBAKE_PATTERNS:
        index = text.find(pattern)
        if index >= 0:
            start = max(index - 20, 0)
            end = min(index + len(pattern) + 40, len(text))
            examples.append({"pattern": pattern, "context": text[start:end]})
            if len(examples) >= max_examples:
                break
    return {
        "ok": replacement_count == 0 and control_count == 0 and not mojibake_hits,
        "length": len(text),
        "replacement_char_count": replacement_count,
        "control_char_count": control_count,
        "mojibake_hit_count": sum(item["count"] for item in mojibake_hits),
        "mojibake_hits": mojibake_hits,
        "examples": examples,
    }


def audit_text_bytes(raw: bytes) -> dict[str, Any]:
    decoded = detect_text_encoding(raw)
    quality = text_quality_report(str(decoded["text"]))
    return {
        "encoding": decoded["encoding"],
        "decode_ok": decoded["decode_ok"],
        "quality": quality,
    }


def audit_hwpx_encoding(path: Path) -> dict[str, Any]:
    path = Path(path)
    result: dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
        "status": "FAIL",
        "checked_entries": 0,
        "problem_entries": [],
        "encoding_counts": {},
    }
    if not path.exists():
        result["error"] = "FILE_NOT_FOUND"
        return result
    try:
        with zipfile.ZipFile(path) as zf:
            for name in zf.namelist():
                if not is_xml_entry(name):
                    continue
                audit = audit_text_bytes(zf.read(name))
                result["checked_entries"] += 1
                encoding = audit["encoding"]
                result["encoding_counts"][encoding] = result["encoding_counts"].get(encoding, 0) + 1
                if not audit["decode_ok"] or not audit["quality"]["ok"]:
                    result["problem_entries"].append(
                        {
                            "entry": name,
                            "encoding": encoding,
                            "decode_ok": audit["decode_ok"],
                            "quality": audit["quality"],
                        }
                    )
    except zipfile.BadZipFile:
        result["error"] = "BAD_ZIP"
        return result
    result["status"] = "PASS" if result["checked_entries"] and not result["problem_entries"] else "FAIL"
    return result


def serialize_xml(root: ET.Element) -> str:
    return ET.tostring(root, encoding="unicode", short_empty_elements=True)


def text_nodes(root: ET.Element) -> list[ET.Element]:
    return [elem for elem in root.iter() if elem.text and elem.text.strip()]


class HwpxPackage:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.entries: dict[str, bytes] = {}
        self.infos: dict[str, zipfile.ZipInfo] = {}
        self.open_package(self.path)

    def open_package(self, path: Path) -> None:
        with zipfile.ZipFile(path) as zf:
            self.entries = {name: zf.read(name) for name in zf.namelist()}
            self.infos = {info.filename: info for info in zf.infolist()}

    def list_entries(self) -> list[str]:
        return list(self.entries)

    def xml_entries(self) -> list[str]:
        return [name for name in self.entries if is_xml_entry(name)]

    def section_entries(self) -> list[str]:
        def section_key(name: str) -> tuple[int, str]:
            match = re.search(r"section(\d+)\.xml$", name.replace("\\", "/").lower())
            return (int(match.group(1)) if match else 999999, name.lower())

        return sorted([name for name in self.entries if is_section_entry(name)], key=section_key)

    def read_xml(self, entry: str) -> ET.Element:
        return ET.fromstring(decode_xml(self.entries[entry]).encode("utf-8"))

    def read_text(self, entry: str) -> str:
        return decode_xml(self.entries[entry])

    def write_xml(self, entry: str, xml: str | ET.Element) -> None:
        xml_text = serialize_xml(xml) if isinstance(xml, ET.Element) else xml
        self.entries[entry] = xml_text.encode("utf-8")

    def set_entry(self, entry: str, data: bytes) -> None:
        self.entries[entry] = data

    def copy_package_to(self, output: Path) -> Path:
        return self.write_package(output)

    def write_package(self, output: Path) -> Path:
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output, "w") as zf:
            for name, data in self.entries.items():
                info = self.infos.get(name)
                if info:
                    new_info = zipfile.ZipInfo(filename=name, date_time=info.date_time)
                    # 원본의 compress_type을 그대로 보존 (0=STORED, 8=DEFLATED).
                    # 이전 `info.compress_type or ZIP_DEFLATED` 코드는 STORED(0)을
                    # falsy로 평가해 mimetype 같은 무압축 entry를 강제 압축했고,
                    # 그러면 HWPX/EPUB 규격 위반으로 한컴이 파일을 거부함.
                    new_info.compress_type = info.compress_type
                    new_info.external_attr = info.external_attr
                    zf.writestr(new_info, data)
                else:
                    zf.writestr(name, data, compress_type=zipfile.ZIP_DEFLATED)
        return output


class HwpxValidator:
    @staticmethod
    def validate_entries(entries: dict[str, bytes], label: str = "<memory>") -> dict[str, Any]:
        encoded = io.BytesIO()
        with zipfile.ZipFile(encoded, "w") as writer:
            for name, data in entries.items():
                writer.writestr(name, data, compress_type=zipfile.ZIP_DEFLATED)
        size = encoded.tell()
        encoded.seek(0)
        result: dict[str, Any] = {
            "path": label,
            "exists": True,
            "size": size,
            "zip_ok": False,
            "entry_count": 0,
            "xml_ok": False,
            "xml_entries": 0,
            "section_entries": 0,
            "has_mimetype": False,
            "xml_errors": [],
        }
        try:
            with zipfile.ZipFile(encoded) as zf:
                names = zf.namelist()
                result["zip_ok"] = True
                result["entry_count"] = len(names)
                result["has_mimetype"] = any(name.lower() == "mimetype" for name in names)
                xml_names = [name for name in names if is_xml_entry(name)]
                result["xml_entries"] = len(xml_names)
                result["section_entries"] = len([name for name in names if is_section_entry(name)])
                encoding_check = {
                    "path": label,
                    "exists": True,
                    "status": "PASS",
                    "checked_entries": 0,
                    "problem_entries": [],
                    "encoding_counts": {},
                }
                for name in xml_names:
                    raw = zf.read(name)
                    try:
                        ET.fromstring(decode_xml(raw).encode("utf-8"))
                    except Exception as exc:  # noqa: BLE001
                        result["xml_errors"].append({"entry": name, "error": str(exc)})
                    audit = audit_text_bytes(raw)
                    encoding_check["checked_entries"] += 1
                    encoding_check["encoding_counts"][audit["encoding"]] = encoding_check["encoding_counts"].get(audit["encoding"], 0) + 1
                    if not audit["decode_ok"] or not audit["quality"]["ok"]:
                        encoding_check["status"] = "FAIL"
                        encoding_check["problem_entries"].append({"entry": name, **audit})
                result["xml_ok"] = not result["xml_errors"]
                result["package_consistency"] = audit_hwpx_package_consistency(zf)
                result["encoding_check"] = encoding_check
        except zipfile.BadZipFile:
            result["error"] = "BAD_ZIP"
        except Exception as exc:  # noqa: BLE001
            result["error"] = str(exc)
        return result

    @staticmethod
    def validate_hwpx(path: Path) -> dict[str, Any]:
        path = Path(path)
        result: dict[str, Any] = {
            "path": str(path),
            "exists": path.exists(),
            "size": path.stat().st_size if path.exists() else 0,
            "zip_ok": False,
            "entry_count": 0,
            "xml_ok": False,
            "xml_entries": 0,
            "section_entries": 0,
            "has_mimetype": False,
            "xml_errors": [],
        }
        if not path.exists():
            return result
        try:
            with zipfile.ZipFile(path) as zf:
                names = zf.namelist()
                result["zip_ok"] = True
                result["entry_count"] = len(names)
                result["has_mimetype"] = any(name.lower() == "mimetype" for name in names)
                xml_names = [name for name in names if is_xml_entry(name)]
                result["xml_entries"] = len(xml_names)
                result["section_entries"] = len([name for name in names if is_section_entry(name)])
                for name in xml_names:
                    try:
                        ET.fromstring(decode_xml(zf.read(name)).encode("utf-8"))
                    except Exception as exc:  # noqa: BLE001
                        result["xml_errors"].append({"entry": name, "error": str(exc)})
                result["xml_ok"] = not result["xml_errors"]
                result["package_consistency"] = audit_hwpx_package_consistency(zf)
        except zipfile.BadZipFile:
            result["error"] = "BAD_ZIP"
        except Exception as exc:  # noqa: BLE001
            result["error"] = str(exc)
        if result["zip_ok"]:
            result["encoding_check"] = audit_hwpx_encoding(path)
        return result


def _find_child(root: ET.Element, name: str) -> ET.Element | None:
    for child in root.iter():
        if local_name(child.tag) == name:
            return child
    return None


def _content_manifest(content_root: ET.Element) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    manifest = _find_child(content_root, "manifest")
    spine = _find_child(content_root, "spine")
    items = []
    itemrefs = []
    if manifest is not None:
        for child in list(manifest):
            if local_name(child.tag) == "item":
                items.append(
                    {
                        "id": child.attrib.get("id", ""),
                        "href": child.attrib.get("href", ""),
                        "media_type": child.attrib.get("media-type", ""),
                    }
                )
    if spine is not None:
        for child in list(spine):
            if local_name(child.tag) == "itemref":
                itemrefs.append({"idref": child.attrib.get("idref", "")})
    return items, itemrefs


def _container_rootfiles(container_root: ET.Element) -> list[dict[str, str]]:
    rootfiles = []
    for child in container_root.iter():
        if local_name(child.tag) == "rootfile":
            rootfiles.append(
                {
                    "full_path": child.attrib.get("full-path", ""),
                    "media_type": child.attrib.get("media-type", ""),
                }
            )
    return rootfiles


def _xml_binary_refs(zf: zipfile.ZipFile, names: set[str]) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    for entry in sorted(name for name in names if is_xml_entry(name)):
        try:
            root = ET.fromstring(decode_xml(zf.read(entry)).encode("utf-8"))
        except Exception:
            continue
        for elem in root.iter():
            for attr, value in elem.attrib.items():
                if attr.endswith("binaryItemIDRef") or local_name(attr) == "binaryItemIDRef":
                    refs.append({"entry": entry, "id": value})
    return refs


def audit_hwpx_package_consistency(zf: zipfile.ZipFile) -> dict[str, Any]:
    names = set(zf.namelist())
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    required_entries = ["mimetype", "Contents/content.hpf", "META-INF/container.xml"]
    recommended_entries = ["version.xml", "settings.xml", "META-INF/manifest.xml"]

    missing_required = [entry for entry in required_entries if entry not in names]
    missing_recommended = [entry for entry in recommended_entries if entry not in names]
    if missing_required:
        errors.append({"code": "REQUIRED_ENTRY_MISSING", "entries": missing_required})
    if missing_recommended:
        warnings.append({"code": "RECOMMENDED_ENTRY_MISSING", "entries": missing_recommended})

    section_entries = sorted(name for name in names if is_section_entry(name))
    if not section_entries:
        errors.append({"code": "SECTION_ENTRY_MISSING"})

    manifest_items: list[dict[str, str]] = []
    spine_itemrefs: list[dict[str, str]] = []
    href_to_entry: dict[str, str] = {}
    id_to_entry: dict[str, str] = {}
    rootfiles: list[dict[str, str]] = []

    if "META-INF/container.xml" in names:
        try:
            container_root = ET.fromstring(decode_xml(zf.read("META-INF/container.xml")).encode("utf-8"))
            rootfiles = _container_rootfiles(container_root)
            content_rootfiles = [item for item in rootfiles if item["full_path"] == "Contents/content.hpf"]
            if not content_rootfiles:
                errors.append({"code": "CONTAINER_CONTENT_ROOTFILE_MISSING"})
            for item in rootfiles:
                full_path = item["full_path"]
                if full_path and full_path not in names:
                    warnings.append({"code": "CONTAINER_ROOTFILE_TARGET_MISSING", "entry": full_path})
        except Exception as exc:  # noqa: BLE001
            errors.append({"code": "CONTAINER_XML_PARSE_ERROR", "error": str(exc)})

    if "Contents/content.hpf" in names:
        try:
            content_root = ET.fromstring(decode_xml(zf.read("Contents/content.hpf")).encode("utf-8"))
            manifest_items, spine_itemrefs = _content_manifest(content_root)
            for item in manifest_items:
                href = item["href"]
                entry = normalize_entry_name(href, base_entry="Contents/content.hpf") if href else ""
                href_to_entry[href] = entry
                if item["id"]:
                    id_to_entry[item["id"]] = entry
                if href and entry not in names:
                    errors.append({"code": "MANIFEST_TARGET_MISSING", "id": item["id"], "href": href, "entry": entry})
            manifest_entries = set(href_to_entry.values())
            required_manifest_entries = [
                name
                for name in names
                if name.lower() == "settings.xml"
                or is_section_entry(name)
                or name.replace("\\", "/").lower().startswith("bindata/")
            ]
            missing_manifest_entries = sorted(entry for entry in required_manifest_entries if entry not in manifest_entries)
            if missing_manifest_entries:
                errors.append({"code": "PACKAGE_ENTRY_NOT_IN_CONTENT_MANIFEST", "entries": missing_manifest_entries})
            manifest_ids = set(id_to_entry)
            for itemref in spine_itemrefs:
                idref = itemref["idref"]
                if idref and idref not in manifest_ids:
                    errors.append({"code": "SPINE_IDREF_NOT_IN_MANIFEST", "idref": idref})
            section_manifest_ids = {item["id"] for item in manifest_items if is_section_entry(id_to_entry.get(item["id"], ""))}
            spine_ids = {item["idref"] for item in spine_itemrefs}
            missing_spine_sections = sorted(id_ for id_ in section_manifest_ids if id_ and id_ not in spine_ids)
            if missing_spine_sections:
                errors.append({"code": "SECTION_NOT_IN_SPINE", "ids": missing_spine_sections})
        except Exception as exc:  # noqa: BLE001
            errors.append({"code": "CONTENT_HPF_PARSE_ERROR", "error": str(exc)})

    binary_refs = _xml_binary_refs(zf, names)
    for ref in binary_refs:
        target = id_to_entry.get(ref["id"])
        if not target:
            errors.append({"code": "BINARY_REF_ID_NOT_IN_MANIFEST", "id": ref["id"], "entry": ref["entry"]})
        elif target not in names:
            errors.append({"code": "BINARY_REF_TARGET_MISSING", "id": ref["id"], "target": target, "entry": ref["entry"]})
        elif not target.replace("\\", "/").lower().startswith("bindata/"):
            warnings.append({"code": "BINARY_REF_TARGET_NOT_BINDATA", "id": ref["id"], "target": target, "entry": ref["entry"]})

    return {
        "status": "FAIL" if errors else ("WARN" if warnings else "PASS"),
        "errors": errors,
        "warnings": warnings,
        "required_entries": {entry: entry in names for entry in required_entries},
        "recommended_entries": {entry: entry in names for entry in recommended_entries},
        "section_entry_count": len(section_entries),
        "manifest_item_count": len(manifest_items),
        "spine_itemref_count": len(spine_itemrefs),
        "container_rootfile_count": len(rootfiles),
        "binary_ref_count": len(binary_refs),
    }


def package_contains(path: Path, values: list[str]) -> dict[str, bool]:
    result = {value: False for value in values}
    with zipfile.ZipFile(path) as zf:
        for name in zf.namelist():
            if not is_xml_entry(name):
                continue
            text = decode_xml(zf.read(name))
            for value in values:
                if value in text:
                    result[value] = True
    return result


def package_has_placeholders(path: Path) -> bool:
    with zipfile.ZipFile(path) as zf:
        return any(is_xml_entry(name) and "{{" in decode_xml(zf.read(name)) for name in zf.namelist())


def read_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(path: Path, data: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def unique_path(path: Path) -> Path:
    path = Path(path)
    if not path.exists():
        return path
    index = 1
    while True:
        candidate = path.parent / f"{path.stem}_{index:03d}{path.suffix}"
        if not candidate.exists():
            return candidate
        index += 1
