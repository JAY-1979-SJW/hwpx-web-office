"""Text and paragraph operations for template-first HWPX editing."""

from __future__ import annotations

import copy
import html
from typing import Any

from hwpx_package import HwpxPackage, local_name, text_nodes
from hwpx_element_factory import append_generated_paragraph as append_generated_paragraph_to_package


def replace_placeholders(package: HwpxPackage, mapping: dict[str, Any]) -> dict:
    replacements = []
    for entry in package.xml_entries():
        xml_text = package.read_text(entry)
        next_text = xml_text
        entry_replacements = 0
        for key, value in mapping.items():
            token = "{{" + key + "}}"
            escaped = html.escape(str(value), quote=False)
            count = next_text.count(token)
            if count:
                next_text = next_text.replace(token, escaped)
                entry_replacements += count
        if entry_replacements:
            package.write_xml(entry, next_text)
            replacements.append({"entry": entry, "count": entry_replacements})
    return {"status": "PASS" if replacements else "NO_PLACEHOLDER_FOUND", "replacements": replacements}


def inject_placeholders(package: HwpxPackage, placeholders: list[str]) -> dict:
    for entry in package.section_entries() or package.xml_entries():
        try:
            root = package.read_xml(entry)
        except Exception:
            continue
        nodes = text_nodes(root)
        if not nodes:
            continue
        injected = []
        for elem, placeholder in zip(nodes, placeholders):
            elem.text = "{{" + placeholder + "}}"
            injected.append(placeholder)
        if injected:
            package.write_xml(entry, root)
            return {"status": "PASS", "entry": entry, "placeholders": injected}
    return {"status": "NO_TEXT_NODE_FOUND", "entry": None, "placeholders": []}


def append_paragraph(package: HwpxPackage, text: str, style: str | None = None) -> dict:
    del style  # style cloning is intentionally deferred.
    for entry in package.section_entries():
        try:
            root = package.read_xml(entry)
        except Exception as exc:  # noqa: BLE001
            return {"status": "XML_PARSE_ERROR", "entry": entry, "error": str(exc)}

        parent_map = {child: parent for parent in root.iter() for child in list(parent)}
        for elem in root.iter():
            name = local_name(elem.tag).lower()
            if name not in {"p", "para"}:
                continue
            parent = parent_map.get(elem)
            if parent is None:
                continue
            clone = copy.deepcopy(elem)
            nodes = text_nodes(clone)
            if not nodes:
                for descendant in clone.iter():
                    if descendant is not clone:
                        descendant.text = text
                        break
            else:
                first = True
                for node in nodes:
                    node.text = text if first else ""
                    first = False
            parent.append(clone)
            package.write_xml(entry, root)
            return {"status": "PASS", "entry": entry, "cloned_tag": local_name(elem.tag)}
    return {"status": "PARAGRAPH_APPEND_PENDING", "reason": "paragraph_node_not_found"}


def append_generated_paragraph(
    package: HwpxPackage,
    text: str,
    section_index: int = 0,
    style_refs: dict[str, str] | None = None,
) -> dict:
    return append_generated_paragraph_to_package(package, text, section_index, style_refs)
