from __future__ import annotations

import sys
import zipfile
from pathlib import Path
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent))

from hwpx_spine_repair import repair_hwpx_spine


def test_repair_hwpx_spine_replaces_header_itemref_with_section(tmp_path: Path) -> None:
    source = tmp_path / "bad.hwpx"
    output = tmp_path / "fixed.hwpx"
    content = """<?xml version="1.0" encoding="UTF-8"?>
<opf:package xmlns:opf="http://www.idpf.org/2007/opf" version="3.0">
  <opf:manifest>
    <opf:item id="section0" href="Contents/section0.xml" media-type="application/xml" />
    <opf:item id="header" href="Contents/header.xml" media-type="application/xml" />
  </opf:manifest>
  <opf:spine><opf:itemref idref="header" /></opf:spine>
</opf:package>
"""
    with zipfile.ZipFile(source, "w") as zf:
        zf.writestr("mimetype", "application/vnd.hancom.hwpml")
        zf.writestr("Contents/content.hpf", content)
        zf.writestr("Contents/header.xml", "<head />")
        zf.writestr("Contents/section0.xml", "<sec />")

    report = repair_hwpx_spine(source, output)
    with zipfile.ZipFile(output) as zf:
        names = set(zf.namelist())
        root = ET.fromstring(zf.read("Contents/content.hpf"))
        mimetype = zf.read("mimetype").decode("utf-8")
        container_xml = zf.read("META-INF/container.xml").decode("utf-8")
    refs = [child.attrib.get("idref") for child in root.iter() if child.tag.rsplit("}", 1)[-1] == "itemref"]
    manifest_items = {
        child.attrib.get("id"): child.attrib.get("href")
        for child in root.iter()
        if child.tag.rsplit("}", 1)[-1] == "item"
    }

    assert report["status"] == "PASS"
    assert report["mimetype"] == "application/owpml"
    assert mimetype == "application/owpml"
    assert refs == ["header", "section0"]
    assert manifest_items["header"] == "Contents/header.xml"
    assert manifest_items["section0"] == "Contents/section0.xml"
    assert manifest_items["settings"] == "settings.xml"
    assert "settings.xml" in names
    assert "META-INF/container.rdf" in names
    assert "META-INF/manifest.xml" in names
    assert 'full-path="Contents/content.hpf"' in container_xml
