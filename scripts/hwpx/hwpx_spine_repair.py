"""Repair generated HWPX packages into a Hancom-openable package shape.

The generated section XML can contain valid UTF-8 Korean text while Hancom
still reports a damaged document if the surrounding package metadata is too
minimal.  This module repairs both the OPF spine and the OCF/HWPX sidecar files
that Hancom expects to find in normal HWPX output.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import zipfile
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET


OPF_NS = "http://www.idpf.org/2007/opf/"
OCF_NS = "urn:oasis:names:tc:opendocument:xmlns:container"
RDF_NS = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
HPF_NS = "http://www.hancom.co.kr/schema/2011/hpf"
HPF_MEDIA_TYPE = "application/hwpml-package+xml"
HWPX_MIMETYPE = "application/owpml"
ET.register_namespace("opf", OPF_NS)


def _opf(tag: str) -> str:
    return f"{{{OPF_NS}}}{tag}"


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _section_sort_key(name: str) -> tuple[int, str]:
    stem = Path(name.replace("\\", "/")).stem
    digits = "".join(ch for ch in stem if ch.isdigit())
    return (int(digits) if digits else 999999, name.lower())


def _manifest_id(entry: str) -> str:
    normalized = entry.replace("\\", "/")
    lower = normalized.lower()
    if lower == "contents/header.xml":
        return "header"
    if lower == "settings.xml":
        return "settings"
    match = re.match(r"contents/section(\d+)\.xml$", lower)
    if match:
        return f"section{match.group(1)}"
    if lower == "preview/prvtext.txt":
        return "PrvText"
    stem = Path(normalized).stem.replace(" ", "_").replace("-", "_")
    text = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in stem)
    return text or "item"


def _manifest_href(entry: str) -> str:
    normalized = entry.replace("\\", "/")
    if normalized.startswith("BinData/"):
        return "../" + normalized
    return normalized


def _media_type(entry: str) -> str:
    lower = entry.lower()
    if lower.endswith(".xml"):
        return "application/xml"
    if lower.endswith(".txt"):
        return "text/plain"
    if lower.endswith(".png"):
        return "image/png"
    if lower.endswith(".jpg") or lower.endswith(".jpeg"):
        return "image/jpeg"
    if lower.endswith(".gif"):
        return "image/gif"
    if lower.endswith(".bmp"):
        return "image/bmp"
    return "application/octet-stream"


def _xml_declaration(body: str) -> str:
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + body


def _version_xml() -> str:
    return _xml_declaration(
        '<ha:HCFVersion xmlns:ha="http://www.hancom.co.kr/hwpml/2011/app" '
        'ha:targetApplication="WORDPROCESSOR" ha:major="5" ha:minor="1" '
        'ha:micro="0" ha:buildNumber="1"/>'
    )


def _settings_xml() -> str:
    return _xml_declaration(
        '<ha:HWPApplicationSetting xmlns:ha="http://www.hancom.co.kr/hwpml/2011/app" '
        'xmlns:config="urn:oasis:names:tc:opendocument:xmlns:config:1.0">'
        '<ha:CaretPosition ha:listIDRef="0" ha:paraIDRef="0" ha:pos="0"/>'
        "</ha:HWPApplicationSetting>"
    )


def _container_xml() -> str:
    return _xml_declaration(
        '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
        "<rootfiles>"
        f'<rootfile full-path="Contents/content.hpf" media-type="{HPF_MEDIA_TYPE}"/>'
        "</rootfiles>"
        "</container>"
    )


def _manifest_xml(section_entries: list[str], has_header: bool) -> str:
    entries = [
        ('/', HPF_MEDIA_TYPE),
        ('version.xml', 'application/xml'),
        ('settings.xml', 'application/xml'),
        ('Contents/content.hpf', HPF_MEDIA_TYPE),
    ]
    if has_header:
        entries.append(('Contents/header.xml', 'application/xml'))
    entries.extend((entry.replace("\\", "/"), 'application/xml') for entry in sorted(section_entries, key=_section_sort_key))
    file_entries = "".join(
        f'<manifest:file-entry manifest:full-path="{html.escape(path, quote=True)}" manifest:media-type="{media_type}"/>'
        for path, media_type in entries
    )
    return _xml_declaration(
        '<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0">'
        + file_entries
        + '</manifest:manifest>'
    )


def _container_rdf(section_entries: list[str], has_header: bool) -> str:
    document_parts = []
    if has_header:
        document_parts.append(
            '<hpf:hasPart><rdf:Description rdf:about="Contents/header.xml">'
            '<rdf:type rdf:resource="http://www.hancom.co.kr/schema/2011/hpf#HeaderFile"/>'
            "</rdf:Description></hpf:hasPart>"
        )
    for entry in sorted(section_entries, key=_section_sort_key):
        escaped = html.escape(entry.replace("\\", "/"), quote=True)
        document_parts.append(
            f'<hpf:hasPart><rdf:Description rdf:about="{escaped}">'
            '<rdf:type rdf:resource="http://www.hancom.co.kr/schema/2011/hpf#SectionFile"/>'
            "</rdf:Description></hpf:hasPart>"
        )
    document_parts.append(
        '<hpf:hasPart><rdf:Description rdf:about="settings.xml">'
        '<rdf:type rdf:resource="http://www.hancom.co.kr/schema/2011/hpf#SettingsFile"/>'
        "</rdf:Description></hpf:hasPart>"
    )
    return _xml_declaration(
        f'<rdf:RDF xmlns:rdf="{RDF_NS}" xmlns:hpf="{HPF_NS}">'
        '<rdf:Description rdf:about="Contents/content.hpf">'
        '<rdf:type rdf:resource="http://www.hancom.co.kr/schema/2011/hpf#Document"/>'
        + "".join(document_parts)
        + "</rdf:Description>"
        "</rdf:RDF>"
    )


def _spine_refs(root: ET.Element) -> list[dict[str, str]]:
    refs = []
    for elem in root.iter():
        if _local_name(elem.tag) != "itemref":
            continue
        refs.append(dict(elem.attrib))
    return refs


def _content_hpf_repaired(
    xml_text: str,
    section_entries: list[str],
    has_header: bool,
    bindata_entries: list[str],
    has_preview_text: bool,
) -> tuple[str, dict[str, Any]]:
    try:
        before_refs = _spine_refs(ET.fromstring(xml_text.encode("utf-8")))
    except ET.ParseError:
        before_refs = []

    root = ET.Element(
        _opf("package"),
        {
            "version": "1.0",
        },
    )
    metadata = ET.SubElement(root, _opf("metadata"))
    ET.register_namespace("dc", "http://purl.org/dc/elements/1.1/")
    dc_ns = "http://purl.org/dc/elements/1.1/"
    ET.SubElement(metadata, f"{{{dc_ns}}}title")
    ET.SubElement(metadata, f"{{{dc_ns}}}creator")
    ET.SubElement(metadata, f"{{{dc_ns}}}format").text = HPF_MEDIA_TYPE
    manifest = ET.SubElement(root, _opf("manifest"))

    content_entries = []
    if has_header:
        content_entries.append("Contents/header.xml")
    content_entries.extend(sorted(section_entries, key=_section_sort_key))
    content_entries.append("settings.xml")
    if has_preview_text:
        content_entries.append("Preview/PrvText.txt")
    content_entries.extend(sorted(bindata_entries))

    seen_ids: set[str] = set()
    for entry in content_entries:
        item_id = _manifest_id(entry)
        base_id = item_id
        suffix = 1
        while item_id in seen_ids:
            suffix += 1
            item_id = f"{base_id}_{suffix}"
        seen_ids.add(item_id)
        ET.SubElement(
            manifest,
            _opf("item"),
            {"id": item_id, "href": _manifest_href(entry), "media-type": _media_type(entry)},
        )

    spine = ET.SubElement(root, _opf("spine"))
    after_refs = []
    if has_header:
        ref = {"idref": "header", "linear": "yes"}
        ET.SubElement(spine, _opf("itemref"), ref)
        after_refs.append(ref)
    section_ids = []
    for entry in sorted(section_entries, key=_section_sort_key):
        section_id = _manifest_id(entry)
        section_ids.append(section_id)
        ref = {"idref": section_id}
        ET.SubElement(spine, _opf("itemref"), ref)
        after_refs.append(ref)

    xml_out = _xml_declaration(ET.tostring(root, encoding="unicode", short_empty_elements=True))
    return xml_out, {
        "before_spine_refs": before_refs,
        "after_spine_refs": after_refs,
        "section_entries": section_entries,
        "section_ids": section_ids,
        "has_header": has_header,
        "bindata_entries": bindata_entries,
    }


def _ordered_names(names: list[str], section_entries: list[str]) -> list[str]:
    priority = [
        "mimetype",
        "META-INF/",
        "Contents/",
        "Preview/",
        "version.xml",
        "settings.xml",
        "META-INF/container.xml",
        "META-INF/manifest.xml",
        "Contents/content.hpf",
        "Contents/header.xml",
        *sorted(section_entries, key=_section_sort_key),
        "Preview/PrvText.txt",
        "META-INF/container.rdf",
    ]
    seen = set()
    ordered = []
    for name in priority:
        if name in names or name in {"mimetype", "version.xml", "settings.xml", "META-INF/container.rdf", "Contents/content.hpf", "META-INF/container.xml", "META-INF/manifest.xml"}:
            if name not in seen:
                ordered.append(name)
                seen.add(name)
    for name in names:
        if name not in seen:
            ordered.append(name)
            seen.add(name)
    return ordered


def repair_hwpx_spine(input_path: Path, output_path: Path) -> dict[str, Any]:
    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(input_path, "r") as src:
        names = src.namelist()
        section_entries = [
            name
            for name in names
            if name.replace("\\", "/").lower().startswith("contents/section")
            and name.replace("\\", "/").lower().endswith(".xml")
        ]
        if "Contents/content.hpf" not in names:
            return {"status": "FAIL", "input": str(input_path), "output": str(output_path), "error": "CONTENT_HPF_NOT_FOUND"}
        if not section_entries:
            return {"status": "FAIL", "input": str(input_path), "output": str(output_path), "error": "SECTION_XML_NOT_FOUND"}
        content_text = src.read("Contents/content.hpf").decode("utf-8", errors="replace")
        has_header = "Contents/header.xml" in names
        has_preview_text = "Preview/PrvText.txt" in names
        bindata_entries = [
            name
            for name in names
            if name.replace("\\", "/").lower().startswith("bindata/")
        ]
        repaired_content, repair = _content_hpf_repaired(
            content_text,
            section_entries,
            has_header,
            bindata_entries,
            has_preview_text,
        )
        generated_entries = {
            "mimetype": HWPX_MIMETYPE.encode("utf-8"),
            "version.xml": _version_xml().encode("utf-8"),
            "settings.xml": _settings_xml().encode("utf-8"),
            "META-INF/container.xml": _container_xml().encode("utf-8"),
            "META-INF/container.rdf": _container_rdf(section_entries, has_header).encode("utf-8"),
            "META-INF/manifest.xml": _manifest_xml(section_entries, has_header).encode("utf-8"),
            "Contents/content.hpf": repaired_content.encode("utf-8"),
        }
        all_names = list(dict.fromkeys(["META-INF/", "Contents/", "Preview/", *names, *generated_entries]))
        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_STORED) as dst:
            for name in _ordered_names(all_names, section_entries):
                normalized = name.replace("\\", "/").lower()
                if normalized.endswith("/"):
                    data = b""
                elif name in generated_entries:
                    data = generated_entries[name]
                else:
                    data = src.read(name)
                dst.writestr(name, data, compress_type=zipfile.ZIP_STORED)
    return {
        "status": "PASS",
        "input": str(input_path),
        "output": str(output_path),
        "mimetype": HWPX_MIMETYPE,
        "hancom_package_files": [
            "version.xml",
            "settings.xml",
            "META-INF/container.xml",
            "META-INF/container.rdf",
            "META-INF/manifest.xml",
        ],
        **repair,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair HWPX content.hpf spine to point to section XML entries")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--report-json")
    args = parser.parse_args()
    report = repair_hwpx_spine(Path(args.input), Path(args.output))
    if args.report_json:
        Path(args.report_json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report_json).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
