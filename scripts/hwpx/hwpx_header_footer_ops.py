"""Header/footer and page numbering operations for HWPX packages."""

from __future__ import annotations

from typing import Any
import xml.etree.ElementTree as ET

from hwpx_package import HwpxPackage, local_name


HH_NS = "http://www.hancom.co.kr/hwpml/2011/head"
HP_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"
SUPPORTED_PAGE_NUMBER_MODES = {"STATIC_TEXT", "NATIVE_DYNAMIC"}


def hh(tag: str) -> str:
    return f"{{{HH_NS}}}{tag}"


def hp(tag: str) -> str:
    return f"{{{HP_NS}}}{tag}"


def _find_first(root: ET.Element, name: str) -> ET.Element | None:
    for elem in root.iter():
        if local_name(elem.tag) == name:
            return elem
    return None


def _find_section_parent(root: ET.Element) -> ET.Element | None:
    return _find_first(root, "secPr")


def _find_or_create_section_parent(root: ET.Element) -> tuple[ET.Element, bool]:
    sec_pr = _find_section_parent(root)
    if sec_pr is not None:
        return sec_pr, False

    first_paragraph = _find_first(root, "p")
    if first_paragraph is None:
        first_paragraph = ET.Element(hp("p"))
        root.insert(0, first_paragraph)

    first_run = None
    for child in list(first_paragraph):
        if local_name(child.tag) == "run":
            first_run = child
            break
    if first_run is None:
        first_run = ET.Element(hp("run"))
        first_paragraph.insert(0, first_run)

    sec_pr = ET.Element(
        hp("secPr"),
        {
            "id": "",
            "textDirection": "HORIZONTAL",
            "spaceColumns": "1134",
            "tabStop": "8000",
        },
    )
    first_run.insert(0, sec_pr)
    return sec_pr, True


def _find_or_create_begin_num(root: ET.Element) -> tuple[ET.Element, bool]:
    begin_num = _find_first(root, "beginNum")
    if begin_num is not None:
        return begin_num, False
    begin_num = ET.Element(
        hh("beginNum"),
        {
            "page": "1",
            "footnote": "1",
            "endnote": "1",
            "pic": "1",
            "tbl": "1",
            "equation": "1",
        },
    )
    root.insert(0, begin_num)
    return begin_num, True


def _find_or_create_start_num(sec_pr: ET.Element) -> tuple[ET.Element, bool]:
    start_num = None
    for child in list(sec_pr):
        if local_name(child.tag) == "startNum":
            start_num = child
            break
    if start_num is not None:
        return start_num, False
    start_num = ET.Element(
        hp("startNum"),
        {
            "pageStartsOn": "BOTH",
            "page": "0",
            "pic": "0",
            "tbl": "0",
            "equation": "0",
        },
    )
    sec_pr.insert(0, start_num)
    return start_num, True


def _find_or_create_visibility(sec_pr: ET.Element) -> tuple[ET.Element, bool]:
    visibility = None
    for child in list(sec_pr):
        if local_name(child.tag) == "visibility":
            visibility = child
            break
    if visibility is not None:
        return visibility, False
    visibility = ET.Element(
        hp("visibility"),
        {
            "hideFirstHeader": "0",
            "hideFirstFooter": "0",
            "hideFirstMasterPage": "0",
            "border": "SHOW_ALL",
            "fill": "SHOW_ALL",
            "hideFirstPageNum": "0",
            "hideFirstEmptyLine": "0",
            "showLineNumber": "0",
        },
    )
    sec_pr.append(visibility)
    return visibility, True


def _normalize_visible_body(
    spec: dict[str, Any],
    *,
    kind: str,
    default_text: str,
    default_align: str,
    start_page: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    errors: list[dict[str, Any]] = []
    visible_key = f"visible_{kind}"
    text_key = f"{kind}_text"
    align_key = f"{kind}_align"
    visible = bool(spec.get(visible_key, False))
    body_text = str(spec.get(text_key, default_text))
    body_align = str(spec.get(align_key, default_align)).upper()
    page_number_format = str(spec.get("page_number_format", "DECIMAL")).upper()
    if body_align not in {"LEFT", "CENTER", "RIGHT"}:
        errors.append({"type": f"{kind.upper()}_ALIGN_INVALID", "value": spec.get(align_key)})
        body_align = default_align
    if page_number_format not in {"DECIMAL"}:
        errors.append({"type": "PAGE_NUMBER_FORMAT_UNSUPPORTED", "value": spec.get("page_number_format")})
        page_number_format = "DECIMAL"
    return (
        {
            visible_key: visible,
            text_key: body_text,
            align_key: body_align,
            "page_number_format": page_number_format,
            f"rendered_{kind}_text": body_text.replace("{page}", str(start_page)),
        },
        errors,
    )


def _body_id(kind: str, section_index: int) -> str:
    return f"generated-{kind}-{section_index}"


def _find_generated_body(sec_pr: ET.Element, kind: str, section_index: int) -> ET.Element | None:
    body_id = _body_id(kind, section_index)
    for child in list(sec_pr):
        if local_name(child.tag) == kind and child.attrib.get("id") == body_id:
            return child
    return None


def _create_body_paragraph(kind: str, text: str, align: str) -> ET.Element:
    body = ET.Element(
        hp(kind),
        {
            "id": "",
            "type": "BOTH_PAGE",
            "generatedBy": "office-analysis-engine",
        },
    )
    sublist = ET.SubElement(
        body,
        hp("subList"),
        {
            "id": "",
            "textDirection": "HORIZONTAL",
            "lineWrap": "BREAK",
            "vertAlign": "CENTER",
            "linkListIDRef": "0",
            "linkListNextIDRef": "0",
            "textWidth": "0",
            "textHeight": "0",
            "hasTextRef": "0",
            "hasNumRef": "0",
        },
    )
    paragraph = ET.SubElement(
        sublist,
        hp("p"),
        {
            "id": "2147483648",
            "paraPrIDRef": "0",
            "styleIDRef": "0",
            "pageBreak": "0",
            "columnBreak": "0",
            "merged": "0",
            "generatedAlign": align,
        },
    )
    run = ET.SubElement(paragraph, hp("run"), {"charPrIDRef": "0"})
    t = ET.SubElement(run, hp("t"))
    t.text = text
    linesegarray = ET.SubElement(paragraph, hp("linesegarray"))
    ET.SubElement(
        linesegarray,
        hp("lineseg"),
        {
            "textpos": "0",
            "vertpos": "0",
            "vertsize": "1000",
            "textheight": "1000",
            "baseline": "850",
            "spacing": "600",
            "horzpos": "0",
            "horzsize": "48188",
            "flags": "393216",
        },
    )
    return body


def _apply_visible_body(sec_pr: ET.Element, normalized: dict[str, Any], kind: str) -> dict[str, Any]:
    body_spec = normalized[kind]
    visible_key = f"visible_{kind}"
    text_key = f"rendered_{kind}_text"
    align_key = f"{kind}_align"
    if not body_spec[visible_key]:
        return {"status": f"VISIBLE_{kind.upper()}_NOT_REQUESTED"}
    section_index = normalized["section_index"]
    body = _find_generated_body(sec_pr, kind, section_index)
    created = body is None
    if body is None:
        body = _create_body_paragraph(kind, body_spec[text_key], body_spec[align_key])
        body.attrib["id"] = _body_id(kind, section_index)
        sec_pr.append(body)
    else:
        body.attrib["type"] = "BOTH_PAGE"
        body.attrib["generatedBy"] = "office-analysis-engine"
        text_nodes = [elem for elem in body.iter() if local_name(elem.tag) == "t"]
        if not text_nodes:
            replacement = _create_body_paragraph(kind, body_spec[text_key], body_spec[align_key])
            body.clear()
            body.attrib.update(replacement.attrib)
            body.attrib["id"] = _body_id(kind, section_index)
            for child in list(replacement):
                body.append(child)
        else:
            for index, node in enumerate(text_nodes):
                node.text = body_spec[text_key] if index == 0 else ""
    return {
        "status": f"VISIBLE_{kind.upper()}_BODY_SET_PASS",
        "created": created,
        f"{kind}_id": body.attrib.get("id"),
        "text": body_spec[text_key],
        "align": body_spec[align_key],
        "dynamic_page_field": False,
        "note": f"Generated as visible static {kind} text; native dynamic page field is deferred.",
    }


def normalize_page_numbering(spec: dict[str, Any] | None) -> dict[str, Any]:
    spec = spec or {}
    errors: list[dict[str, Any]] = []
    section_index = spec.get("section_index", 0)
    if not isinstance(section_index, int) or section_index < 0:
        errors.append({"type": "SECTION_INDEX_INVALID", "value": section_index})
        section_index = 0
    start_page = spec.get("start_page", 1)
    if not isinstance(start_page, int) or start_page < 1:
        errors.append({"type": "PAGE_START_INVALID", "value": start_page})
        start_page = 1
    page_starts_on = str(spec.get("page_starts_on", "BOTH")).upper()
    if page_starts_on not in {"BOTH", "EVEN", "ODD"}:
        errors.append({"type": "PAGE_STARTS_ON_INVALID", "value": spec.get("page_starts_on")})
        page_starts_on = "BOTH"
    page_number_mode = str(spec.get("page_number_mode", "STATIC_TEXT")).upper()
    if page_number_mode not in SUPPORTED_PAGE_NUMBER_MODES:
        errors.append({"type": "PAGE_NUMBER_MODE_UNSUPPORTED", "value": spec.get("page_number_mode")})
        page_number_mode = "STATIC_TEXT"
    elif page_number_mode == "NATIVE_DYNAMIC":
        errors.append(
            {
                "type": "NATIVE_DYNAMIC_PAGE_FIELD_UNSUPPORTED",
                "message": (
                    "No cloneable pageNumCtrl/autoNum page field sample is available. "
                    "Use page_number_mode=STATIC_TEXT until native dynamic page field structure is acquired."
                ),
            }
        )
    header, header_errors = _normalize_visible_body(
        spec,
        kind="header",
        default_text="",
        default_align="CENTER",
        start_page=start_page,
    )
    footer, footer_errors = _normalize_visible_body(
        spec,
        kind="footer",
        default_text="Page {page}",
        default_align="CENTER",
        start_page=start_page,
    )
    errors.extend(header_errors)
    errors.extend(footer_errors)
    warnings: list[dict[str, Any]] = []
    if not header["visible_header"] and not footer["visible_footer"]:
        warnings.append(
            {
                "type": "HEADER_FOOTER_BODY_GENERATION_PENDING",
                "message": "This step controls page numbering metadata only; set visible_header=true or visible_footer=true to generate body text.",
            }
        )
    return {
        "section_index": section_index,
        "start_page": start_page,
        "section_page": max(start_page - 1, 0),
        "page_starts_on": page_starts_on,
        "page_number_mode": page_number_mode,
        "hide_first_page_number": bool(spec.get("hide_first_page_number", False)),
        "hide_first_header": bool(spec.get("hide_first_header", False)),
        "hide_first_footer": bool(spec.get("hide_first_footer", False)),
        "header": header,
        "footer": footer,
        "errors": errors,
        "warnings": warnings,
    }


def inspect_page_numbering(package: HwpxPackage, section_index: int = 0) -> dict[str, Any]:
    result: dict[str, Any] = {"section_index": section_index}
    if "Contents/header.xml" in package.entries:
        root = package.read_xml("Contents/header.xml")
        begin_num = _find_first(root, "beginNum")
        result["beginNum"] = dict(begin_num.attrib) if begin_num is not None else {}
    sections = package.section_entries()
    if section_index < 0 or section_index >= len(sections):
        result["status"] = "SECTION_NOT_FOUND"
        result["section_count"] = len(sections)
        return result
    section_root = package.read_xml(sections[section_index])
    sec_pr = _find_section_parent(section_root)
    start_num = _find_first(sec_pr, "startNum") if sec_pr is not None else None
    visibility = _find_first(sec_pr, "visibility") if sec_pr is not None else None
    result.update(
        {
            "status": "PASS",
            "entry": sections[section_index],
            "startNum": dict(start_num.attrib) if start_num is not None else {},
            "visibility": dict(visibility.attrib) if visibility is not None else {},
        }
    )
    return result


def apply_page_numbering(package: HwpxPackage, spec: dict[str, Any] | None) -> dict[str, Any]:
    normalized = normalize_page_numbering(spec)
    if normalized["errors"]:
        return {"status": "PAGE_NUMBERING_INVALID", "normalized": normalized, "warnings": normalized["warnings"]}
    sections = package.section_entries()
    section_index = normalized["section_index"]
    if section_index >= len(sections):
        return {
            "status": "SECTION_NOT_FOUND",
            "section_index": section_index,
            "section_count": len(sections),
            "warnings": normalized["warnings"],
        }

    before = inspect_page_numbering(package, section_index)
    header_status = "HEADER_NOT_FOUND"
    created_begin_num = False
    if "Contents/header.xml" in package.entries:
        header_root = package.read_xml("Contents/header.xml")
        begin_num, created_begin_num = _find_or_create_begin_num(header_root)
        begin_num.attrib["page"] = str(normalized["start_page"])
        package.write_xml("Contents/header.xml", header_root)
        header_status = "HEADER_BEGIN_NUM_SET_PASS"

    section_entry = sections[section_index]
    section_root = package.read_xml(section_entry)
    sec_pr, created_section_properties = _find_or_create_section_parent(section_root)
    start_num, created_start_num = _find_or_create_start_num(sec_pr)
    start_num.attrib["pageStartsOn"] = normalized["page_starts_on"]
    start_num.attrib["page"] = str(normalized["section_page"])
    visibility, created_visibility = _find_or_create_visibility(sec_pr)
    visibility.attrib["hideFirstPageNum"] = "1" if normalized["hide_first_page_number"] else "0"
    visibility.attrib["hideFirstHeader"] = "1" if normalized["hide_first_header"] else "0"
    visibility.attrib["hideFirstFooter"] = "1" if normalized["hide_first_footer"] else "0"
    header_result = _apply_visible_body(sec_pr, normalized, "header")
    footer_result = _apply_visible_body(sec_pr, normalized, "footer")
    package.write_xml(section_entry, section_root)

    after = inspect_page_numbering(package, section_index)
    return {
        "status": "PAGE_NUMBERING_SET_PASS",
        "section_index": section_index,
        "entry": section_entry,
        "header_status": header_status,
        "created_section_properties": created_section_properties,
        "created_begin_num": created_begin_num,
        "created_start_num": created_start_num,
        "created_visibility": created_visibility,
        "visible_header": header_result,
        "visible_footer": footer_result,
        "before": before,
        "after": after,
        "normalized": normalized,
        "warnings": normalized["warnings"],
    }


__all__ = ["apply_page_numbering", "inspect_page_numbering", "normalize_page_numbering"]
