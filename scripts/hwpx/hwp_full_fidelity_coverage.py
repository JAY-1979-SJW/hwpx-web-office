"""Fail-closed coverage policy for independent HWP full-fidelity conversion."""

from __future__ import annotations

from collections import Counter
from typing import Any

from extract_hwp_body_fields import FIDELITY_RISK_TAGS, HWP_RECORD_TAGS, TEXT_ONLY_SUPPORTED_TAGS

REQUIRED_RECORD_FAMILIES: dict[str, dict[str, Any]] = {
    "document_properties": {
        "tags": {16, 17, 27},
        "status": "partial",
        "reason": "Document start numbering and ID mappings are emitted into HWPX header/audit entries; extended metadata and compatibility settings are still incomplete.",
    },
    "docinfo_extensions": {
        "tags": {28, 30, 31, 32, 92, 94, 96, 97},
        "status": "partial",
        "reason": "DocInfo compatibility, distribution, memo, forbidden character, and track-change records are decoded into forensic audit payloads; full HWPX semantic emission is still incomplete.",
    },
    "fonts_and_styles": {
        "tags": {19, 20, 21, 22, 23, 24, 25, 26},
        "status": "partial",
        "reason": "Face names, border fills, character shapes, paragraph shapes, numbering, bullets, and styles are emitted to HWPX header XML with body references; exact style parity and all advanced attributes still require audit.",
    },
    "paragraph_layout": {
        "tags": {66, 68, 69, 70},
        "status": "partial",
        "reason": "Paragraph text, paragraph shape references, character shape runs, and line segments are mapped; range tags and exact paragraph/control correlation are still incomplete.",
    },
    "controls_and_page": {
        "tags": {71, 72, 73, 74, 75},
        "status": "partial",
        "reason": "Control headers, list headers, page definitions, footnote/endnote shape, page border fill, and visual object positioning are partially mapped; headers/footers and all control families are still incomplete.",
    },
    "tables": {
        "tags": {77},
        "status": "partial",
        "reason": "Table row/column counts, cell metrics, addresses, spans, borders, and sizing are mapped for decoded LIST_HEADER/TABLE records; complex zone border overrides and nested/control correlation still require audit.",
    },
    "drawings_and_shapes": {
        "tags": {76, 78, 79, 80, 81, 82, 83, 86},
        "status": "partial",
        "reason": "Shape components and rectangles are decoded and emitted as visible HWPX objects; remaining vector shape families and exact style attributes are still being mapped.",
    },
    "binary_objects": {
        "tags": {18, 84, 85},
        "status": "partial",
        "reason": "Embedded image BinData and picture controls are copied and emitted as HWPX resources; OLE objects and all picture effects are still being mapped.",
    },
    "equations_and_ctrl_data": {
        "tags": {87, 88},
        "status": "partial",
        "reason": "Equation editor payload formula text and metadata are decoded and preserved in audit entries; generic CTRL_DATA payloads remain pending.",
    },
}

FULL_SUPPORTED_TAGS = {67}
DECODED_DOCINFO_TAGS = {16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 28, 30, 31, 32, 92, 94, 96, 97}
DECODED_BODY_LAYOUT_TAGS = {66, 68, 69}
DECODED_PAGE_LAYOUT_TAGS = {71, 72, 73, 74, 75}
DECODED_TABLE_LAYOUT_TAGS = {77}
DECODED_SHAPE_LAYOUT_TAGS = {76, 79, 85}


def _record_name(tag_id: int) -> str:
    return HWP_RECORD_TAGS.get(tag_id, f"UNKNOWN_{tag_id}")


def coverage_catalog() -> dict[str, Any]:
    return {
        name: {
            **{key: value for key, value in spec.items() if key != "tags"},
            "tags": [
                {"tag_id": tag, "tag_name": _record_name(tag)} for tag in sorted(spec["tags"])
            ],
        }
        for name, spec in REQUIRED_RECORD_FAMILIES.items()
    }


def _build_family_rows(
    counts: Counter[int],
    present_tags: set[int],
    coverage_evidence: dict[str, Any],
    covered_tags: set[int],
    blockers: list[str],
) -> list[dict[str, Any]]:
    family_rows = []
    for name, spec in REQUIRED_RECORD_FAMILIES.items():
        tags = set(spec["tags"])
        present = sorted(tags & present_tags)
        audit_decision = _family_audit_decision(name, present, coverage_evidence)
        if not present:
            family_status = "NOT_PRESENT"
        elif audit_decision["status"] == "AUDITED":
            family_status = "AUDITED"
            covered_tags.update(present)
        elif spec["status"] == "supported":
            family_status = "SUPPORTED"
            covered_tags.update(present)
        elif spec["status"] == "partial":
            family_status = "PARTIAL"
            blockers.append(f"PARTIAL:{name}")
        else:
            family_status = "UNSUPPORTED"
            blockers.append(f"UNSUPPORTED:{name}")
        family_rows.append({
            "family": name,
            "status": family_status,
            "present_tags": [
                {"tag_id": tag, "tag_name": _record_name(tag), "count": counts[tag]}
                for tag in present
            ],
            "reason": spec["reason"],
            "audit_evidence": audit_decision["evidence"],
        })
    return family_rows


def _summarize_tag_counts(counts: Counter[int], covered_tags: set[int]) -> tuple[int, int, int]:
    present_count = sum(counts.values())
    covered_count = sum(count for tag, count in counts.items() if tag in covered_tags)
    decoded_count = sum(
        count
        for tag, count in counts.items()
        if tag in DECODED_DOCINFO_TAGS
        or tag in DECODED_BODY_LAYOUT_TAGS
        or tag in DECODED_PAGE_LAYOUT_TAGS
        or tag in DECODED_TABLE_LAYOUT_TAGS
        or tag in DECODED_SHAPE_LAYOUT_TAGS
        or tag in FULL_SUPPORTED_TAGS
    )
    return present_count, covered_count, decoded_count


def build_coverage(  # ruff: ignore[too-many-arguments] -- 28곳 이상 위치 인자 호출부(테스트 포함), 시그니처 변경 보류
    counts: Counter[int],
    bindata_streams: list[str],
    extraction: dict[str, Any],
    decoded_docinfo: dict[str, Any] | None = None,
    body_layout: dict[str, Any] | None = None,
    page_layout: dict[str, Any] | None = None,
    table_layout: dict[str, Any] | None = None,
    shape_layout: dict[str, Any] | None = None,
    equation_layout: dict[str, Any] | None = None,
) -> dict[str, Any]:
    present_tags = set(counts)
    family_rows = []
    blockers = []
    warnings = []
    covered_tags = set(FULL_SUPPORTED_TAGS)
    document_properties_coverage = build_document_properties_coverage(decoded_docinfo)
    id_mappings_coverage = build_id_mappings_coverage(decoded_docinfo)
    docinfo_extension_coverage = build_docinfo_extension_coverage(counts, decoded_docinfo)
    bindata_coverage = build_bindata_stream_coverage(bindata_streams, decoded_docinfo)
    fontface_coverage = build_fontface_coverage(decoded_docinfo)
    border_fill_coverage = build_border_fill_coverage(decoded_docinfo, page_layout, table_layout)
    char_shape_coverage = build_char_shape_coverage(decoded_docinfo, body_layout)
    para_shape_coverage = build_para_shape_coverage(decoded_docinfo, body_layout)
    style_coverage = build_style_coverage(decoded_docinfo, body_layout)
    paragraph_layout_coverage = build_paragraph_layout_coverage(counts, body_layout)
    controls_page_coverage = build_controls_page_coverage(counts, page_layout)
    table_coverage = build_table_coverage(counts, table_layout)
    shape_coverage = build_shape_coverage(counts, shape_layout)
    numbering_coverage = build_numbering_coverage(decoded_docinfo)
    equation_coverage = build_equation_coverage(counts, equation_layout)
    picture_coverage = build_picture_coverage(
        counts, bindata_streams, decoded_docinfo, shape_layout
    )
    binary_object_coverage = build_binary_object_coverage(
        counts, bindata_coverage, picture_coverage
    )
    coverage_evidence = {
        "document_properties_coverage": document_properties_coverage,
        "id_mappings_coverage": id_mappings_coverage,
        "docinfo_extension_coverage": docinfo_extension_coverage,
        "fontface_coverage": fontface_coverage,
        "border_fill_coverage": border_fill_coverage,
        "char_shape_coverage": char_shape_coverage,
        "para_shape_coverage": para_shape_coverage,
        "style_coverage": style_coverage,
        "numbering_coverage": numbering_coverage,
        "paragraph_layout_coverage": paragraph_layout_coverage,
        "controls_page_coverage": controls_page_coverage,
        "table_coverage": table_coverage,
        "shape_coverage": shape_coverage,
        "picture_coverage": picture_coverage,
        "bindata_stream_coverage": bindata_coverage,
        "binary_object_coverage": binary_object_coverage,
        "equation_coverage": equation_coverage,
    }

    family_rows.extend(
        _build_family_rows(counts, present_tags, coverage_evidence, covered_tags, blockers)
    )

    unknown_tags = sorted(tag for tag in present_tags if tag not in HWP_RECORD_TAGS)
    if unknown_tags:
        blockers.append("UNKNOWN_RECORD_TAGS")

    risk_tags = sorted(
        tag
        for tag in present_tags
        if tag in FIDELITY_RISK_TAGS or tag not in TEXT_ONLY_SUPPORTED_TAGS
    )
    if bindata_streams and bindata_coverage.get("status") != "PASS":
        blockers.append("BINDATA_STREAMS_PRESENT")
    if not extraction.get("ok"):
        blockers.append("TEXT_EXTRACTION_NOT_OK")
    if not blockers and risk_tags:
        warnings.append("RISK_TAGS_PRESENT_BUT_NOT_BLOCKING")

    present_count, covered_count, decoded_count = _summarize_tag_counts(counts, covered_tags)
    return {
        "status": "PASS" if not blockers else "FAIL",
        "full_fidelity_ready": not blockers,
        "supported_tags": [
            {"tag_id": tag, "tag_name": _record_name(tag)} for tag in sorted(covered_tags)
        ],
        "risk_tags": [
            {"tag_id": tag, "tag_name": _record_name(tag), "count": counts[tag]}
            for tag in risk_tags
        ],
        "unknown_tags": unknown_tags,
        "record_coverage_ratio": round(covered_count / max(1, present_count), 6),
        "decode_coverage_ratio": round(decoded_count / max(1, present_count), 6),
        "covered_record_count": covered_count,
        "decoded_record_count": decoded_count,
        "present_record_count": present_count,
        "required_families": family_rows,
        "document_properties_coverage": document_properties_coverage,
        "id_mappings_coverage": id_mappings_coverage,
        "docinfo_extension_coverage": docinfo_extension_coverage,
        "bindata_stream_coverage": bindata_coverage,
        "fontface_coverage": fontface_coverage,
        "border_fill_coverage": border_fill_coverage,
        "char_shape_coverage": char_shape_coverage,
        "para_shape_coverage": para_shape_coverage,
        "style_coverage": style_coverage,
        "paragraph_layout_coverage": paragraph_layout_coverage,
        "controls_page_coverage": controls_page_coverage,
        "table_coverage": table_coverage,
        "shape_coverage": shape_coverage,
        "numbering_coverage": numbering_coverage,
        "equation_coverage": equation_coverage,
        "picture_coverage": picture_coverage,
        "binary_object_coverage": binary_object_coverage,
        "blockers": blockers,
        "warnings": warnings,
        "next_decoder_targets": next_decoder_targets(
            counts,
            bindata_streams,
            {
                16: document_properties_coverage,
                17: id_mappings_coverage,
                19: fontface_coverage,
                20: border_fill_coverage,
                21: char_shape_coverage,
                23: numbering_coverage,
                25: para_shape_coverage,
                77: table_coverage,
                85: picture_coverage,
                88: equation_coverage,
            },
            bindata_coverage,
        ),
    }


def _docinfo_mapping_count(decoded_docinfo: dict[str, Any] | None, key: str) -> int | None:
    if not isinstance(decoded_docinfo, dict):
        return None
    mappings = (
        decoded_docinfo.get("id_mappings")
        if isinstance(decoded_docinfo.get("id_mappings"), dict)
        else {}
    )
    counts = mappings.get("counts") if isinstance(mappings.get("counts"), dict) else {}
    try:
        return int(counts[key])
    except (KeyError, TypeError, ValueError):
        return None


def build_document_properties_coverage(decoded_docinfo: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(decoded_docinfo, dict):
        return {"status": "NO_DECODED_DOCINFO", "mapped_field_count": 0, "missing_fields": []}
    props = (
        decoded_docinfo.get("document_properties")
        if isinstance(decoded_docinfo.get("document_properties"), dict)
        else {}
    )
    if not props:
        return {"status": "NO_DOCUMENT_PROPERTIES", "mapped_field_count": 0, "missing_fields": []}
    required_fields = [
        "section_count",
        "page_start",
        "footnote_start",
        "endnote_start",
        "picture_start",
        "table_start",
        "equation_start",
    ]
    missing_fields = [name for name in required_fields if props.get(name) is None]
    status = "PASS" if not missing_fields else "PARTIAL_DOCUMENT_PROPERTIES"
    return {
        "status": status,
        "mapped_field_count": len(required_fields) - len(missing_fields),
        "required_field_count": len(required_fields),
        "missing_fields": missing_fields,
        "begin_num": {
            "page": props.get("page_start"),
            "footnote": props.get("footnote_start"),
            "endnote": props.get("endnote_start"),
            "pic": props.get("picture_start"),
            "tbl": props.get("table_start"),
            "equation": props.get("equation_start"),
        },
        "section_count": props.get("section_count"),
    }


def build_docinfo_extension_coverage(
    counts: Counter[int], decoded_docinfo: dict[str, Any] | None
) -> dict[str, Any]:
    extension_tags = {28, 30, 31, 32, 92, 94, 96, 97}
    present = sorted(tag for tag in extension_tags if counts.get(tag, 0))
    if not present:
        return {
            "status": "NOT_PRESENT",
            "present_tags": [],
            "decoded_count": 0,
            "decode_error_count": 0,
        }
    if not isinstance(decoded_docinfo, dict):
        return {
            "status": "NO_DECODED_DOCINFO",
            "present_tags": present,
            "decoded_count": 0,
            "decode_error_count": 0,
        }
    rows = (
        decoded_docinfo.get("docinfo_extensions")
        if isinstance(decoded_docinfo.get("docinfo_extensions"), list)
        else []
    )
    decoded_by_tag: Counter[int] = Counter()
    decode_errors: list[dict[str, Any]] = []
    for row in rows:
        try:
            tag_id = int(row.get("tag_id"))
        except (TypeError, ValueError):
            continue
        decoded_by_tag[tag_id] += 1
        if row.get("decode_error"):
            decode_errors.append({
                "tag_id": tag_id,
                "tag_name": _record_name(tag_id),
                "message": row.get("message"),
            })
    missing = [tag for tag in present if decoded_by_tag.get(tag, 0) < counts.get(tag, 0)]
    status = "PASS" if not missing and not decode_errors else "PARTIAL_DOCINFO_EXTENSIONS"
    return {
        "status": status,
        "present_tags": [
            {"tag_id": tag, "tag_name": _record_name(tag), "count": counts[tag]} for tag in present
        ],
        "decoded_count": sum(decoded_by_tag.values()),
        "decode_error_count": len(decode_errors),
        "missing_decoded_tags": [
            {"tag_id": tag, "tag_name": _record_name(tag), "count": counts[tag]} for tag in missing
        ],
        "decode_errors": decode_errors[:20],
    }


def _coverage_ok(row: dict[str, Any] | None, *, absent_ok: bool = True) -> bool:
    status = (row or {}).get("status")
    if status == "PASS":
        return True
    if absent_ok and status in {
        "NOT_PRESENT",
        "NO_BORDER_FILLS",
        "NO_LIST_DEFINITIONS",
        "NO_STYLES",
        "NO_TABLES",
        "NO_PICTURES",
        "NO_BINDATA_STREAMS",
        "NO_EQUATIONS",
        "NO_BINARY_OBJECTS",
        "NO_VECTOR_SHAPES",
    }:
        return True
    return False


def _family_audit_decision(
    name: str, present: list[int], evidence: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    if not present:
        return {"status": "NOT_PRESENT", "evidence": []}
    family_checks = {
        "document_properties": ["document_properties_coverage", "id_mappings_coverage"],
        "docinfo_extensions": ["docinfo_extension_coverage"],
        "fonts_and_styles": [
            "fontface_coverage",
            "border_fill_coverage",
            "char_shape_coverage",
            "para_shape_coverage",
            "style_coverage",
            "numbering_coverage",
        ],
        "paragraph_layout": ["paragraph_layout_coverage"],
        "controls_and_page": ["controls_page_coverage"],
        "tables": ["table_coverage"],
        "drawings_and_shapes": ["shape_coverage"],
        "binary_objects": ["binary_object_coverage"],
        "equations_and_ctrl_data": ["equation_coverage"],
    }
    check_names = family_checks.get(name)
    if not check_names:
        return {"status": "PARTIAL", "evidence": []}
    rows = [
        {"name": check_name, "status": (evidence.get(check_name) or {}).get("status")}
        for check_name in check_names
    ]
    if all(_coverage_ok(evidence.get(check_name)) for check_name in check_names):
        return {"status": "AUDITED", "evidence": rows}
    return {"status": "PARTIAL", "evidence": rows}


def _id_mapping_actual_counts(decoded_docinfo: dict[str, Any]) -> dict[str, int]:
    counts = (
        decoded_docinfo.get("counts") if isinstance(decoded_docinfo.get("counts"), dict) else {}
    )
    groups = (
        decoded_docinfo.get("face_name_groups")
        if isinstance(decoded_docinfo.get("face_name_groups"), dict)
        else {}
    )
    return {
        "binary_data": int(counts.get("binary_data") or 0),
        "hangul_font": len(groups.get("hangul") or []),
        "latin_font": len(groups.get("latin") or []),
        "hanja_font": len(groups.get("hanja") or []),
        "japanese_font": len(groups.get("japanese") or []),
        "other_font": len(groups.get("other") or []),
        "symbol_font": len(groups.get("symbol") or []),
        "user_font": len(groups.get("user") or []),
        "border_fill": int(counts.get("border_fills") or 0),
        "char_shape": int(counts.get("char_shapes") or 0),
        "tab_def": int(counts.get("tab_defs") or 0),
        "numbering": int(counts.get("numberings") or 0),
        "bullet": int(counts.get("bullets") or 0),
        "para_shape": int(counts.get("para_shapes") or 0),
        "style": int(counts.get("styles") or 0),
    }


def build_id_mappings_coverage(decoded_docinfo: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(decoded_docinfo, dict):
        return {"status": "NO_DECODED_DOCINFO", "mapped_count": 0, "mismatches": []}
    mappings = (
        decoded_docinfo.get("id_mappings")
        if isinstance(decoded_docinfo.get("id_mappings"), dict)
        else {}
    )
    expected = mappings.get("counts") if isinstance(mappings.get("counts"), dict) else {}
    if not expected:
        return {"status": "NO_ID_MAPPINGS", "mapped_count": 0, "mismatches": []}
    actual = _id_mapping_actual_counts(decoded_docinfo)
    mismatches = []
    for key, actual_count in actual.items():
        if key not in expected:
            continue
        try:
            expected_count = int(expected.get(key))
        except (TypeError, ValueError):
            mismatches.append({"key": key, "expected": expected.get(key), "actual": actual_count})
            continue
        if expected_count != actual_count:
            mismatches.append({"key": key, "expected": expected_count, "actual": actual_count})
    status = "PASS" if not mismatches else "PARTIAL_ID_MAPPINGS"
    return {
        "status": status,
        "mapped_count": len(actual),
        "raw_count": mappings.get("raw_count"),
        "mismatch_count": len(mismatches),
        "mismatches": mismatches[:50],
        "actual_counts": actual,
    }


def build_fontface_coverage(decoded_docinfo: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(decoded_docinfo, dict):
        return {
            "status": "NO_DECODED_DOCINFO",
            "face_name_count": 0,
            "mapped_total": 0,
            "mismatches": [],
        }
    faces = (
        decoded_docinfo.get("face_names")
        if isinstance(decoded_docinfo.get("face_names"), list)
        else []
    )
    if not faces:
        return {"status": "NO_FONTFACES", "face_name_count": 0, "mapped_total": 0, "mismatches": []}
    groups = (
        decoded_docinfo.get("face_name_groups")
        if isinstance(decoded_docinfo.get("face_name_groups"), dict)
        else {}
    )
    mismatches = []
    mapped_total = 0
    for slot in ["hangul", "latin", "hanja", "japanese", "other", "symbol", "user"]:
        expected = _docinfo_mapping_count(decoded_docinfo, f"{slot}_font")
        group = groups.get(slot) if isinstance(groups.get(slot), list) else []
        if expected is None:
            continue
        mapped_total += len(group)
        if len(group) != expected:
            mismatches.append({"slot": slot, "expected": expected, "actual": len(group)})
    unassigned = groups.get("unassigned") if isinstance(groups.get("unassigned"), list) else []
    if mismatches or unassigned:
        status = "PARTIAL_FONTFACE_MAPPING"
    else:
        status = "PASS"
    return {
        "status": status,
        "face_name_count": len(faces),
        "mapped_total": mapped_total
        or sum(
            len(groups.get(slot) or [])
            for slot in ["hangul", "latin", "hanja", "japanese", "other", "symbol", "user"]
        ),
        "unassigned_count": len(unassigned),
        "mismatches": mismatches,
    }


def _body_text_paragraphs(body_layout: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(body_layout, dict):
        return []
    paragraphs = []
    sections = body_layout.get("sections") if isinstance(body_layout.get("sections"), list) else []
    for section in sections:
        if not isinstance(section, dict):
            continue
        for paragraph in section.get("paragraphs") or []:
            if isinstance(paragraph, dict) and paragraph.get("has_para_text"):
                paragraphs.append(paragraph)
    return paragraphs


def _known_docinfo_ids(decoded_docinfo: dict[str, Any] | None, key: str) -> set[int]:
    if not isinstance(decoded_docinfo, dict):
        return set()
    rows = decoded_docinfo.get(key) if isinstance(decoded_docinfo.get(key), list) else []
    ids = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            ids.add(int(row.get("index")))
        except (TypeError, ValueError):
            continue
    return ids


def _append_border_ref(refs: list[dict[str, Any]], source: str, value: Any, **extra: Any) -> None:
    try:
        border_fill_id = int(value)
    except (TypeError, ValueError):
        return
    refs.append({"source": source, "border_fill_id": border_fill_id, **extra})


def _resolve_border_fill_id(raw: Any, known_ids: set[int]) -> int | None:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    if value in known_ids:
        return value
    if value > 0 and value - 1 in known_ids:
        return value - 1
    return None


def _border_refs_from_docinfo(decoded_docinfo: dict[str, Any] | None) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    if not isinstance(decoded_docinfo, dict):
        return refs
    for key, source in (("char_shapes", "char_shape"), ("para_shapes", "para_shape")):
        rows = decoded_docinfo.get(key) if isinstance(decoded_docinfo.get(key), list) else []
        for row in rows:
            if isinstance(row, dict):
                _append_border_ref(
                    refs, source, row.get("border_fill_id"), record_index=row.get("index")
                )
    return refs


def _border_refs_from_page_layout(page_layout: dict[str, Any] | None) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    if not isinstance(page_layout, dict):
        return refs
    sections = page_layout.get("sections") if isinstance(page_layout.get("sections"), list) else []
    for section in sections:
        if not isinstance(section, dict):
            continue
        section_index = section.get("section_index")
        for row in section.get("page_border_fills") or []:
            if isinstance(row, dict):
                _append_border_ref(
                    refs,
                    "page_border_fill",
                    row.get("border_fill_id"),
                    section_index=section_index,
                    record_index=row.get("record_index"),
                )
    return refs


def _border_refs_from_table_layout(table_layout: dict[str, Any] | None) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    if not isinstance(table_layout, dict):
        return refs
    sections = (
        table_layout.get("sections") if isinstance(table_layout.get("sections"), list) else []
    )
    for section in sections:
        if not isinstance(section, dict):
            continue
        section_index = section.get("section_index")
        for table in section.get("tables") or []:
            if not isinstance(table, dict):
                continue
            table_index = table.get("table_index")
            decoded_table = table.get("table") if isinstance(table.get("table"), dict) else {}
            row_count = decoded_table.get("row_count")
            col_count = decoded_table.get("col_count")
            for row in table.get("list_headers") or []:
                if isinstance(row, dict):
                    cell_addr = (
                        row.get("cell_addr") if isinstance(row.get("cell_addr"), dict) else {}
                    )
                    try:
                        row_addr = int(cell_addr.get("row"))
                        col_addr = int(cell_addr.get("col"))
                        max_row = int(row_count)
                        max_col = int(col_count)
                    except (TypeError, ValueError):
                        row_addr = col_addr = max_row = max_col = None
                    if (
                        row_addr is not None
                        and col_addr is not None
                        and max_row is not None
                        and max_col is not None
                        and (row_addr >= max_row or col_addr >= max_col)
                    ):
                        continue
                    _append_border_ref(
                        refs,
                        "table_cell",
                        row.get("border_fill_id"),
                        section_index=section_index,
                        table_index=table_index,
                        record_index=row.get("record_index"),
                    )
    return refs


def build_border_fill_coverage(
    decoded_docinfo: dict[str, Any] | None,
    page_layout: dict[str, Any] | None,
    table_layout: dict[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(decoded_docinfo, dict):
        return {
            "status": "NO_DECODED_DOCINFO",
            "border_fill_count": 0,
            "referenced_border_fill_count": 0,
            "unresolved_ref_count": 0,
        }
    border_fill_ids = _known_docinfo_ids(decoded_docinfo, "border_fills")
    if not border_fill_ids:
        return {
            "status": "NO_BORDER_FILLS",
            "border_fill_count": 0,
            "referenced_border_fill_count": 0,
            "unresolved_ref_count": 0,
        }
    expected = _docinfo_mapping_count(decoded_docinfo, "border_fill")
    count_mismatch = expected is not None and expected != len(border_fill_ids)
    refs = (
        _border_refs_from_docinfo(decoded_docinfo)
        + _border_refs_from_page_layout(page_layout)
        + _border_refs_from_table_layout(table_layout)
    )
    missing_refs = [
        ref
        for ref in refs
        if _resolve_border_fill_id(ref.get("border_fill_id"), border_fill_ids) is None
    ]
    status = "PASS" if not count_mismatch and not missing_refs else "PARTIAL_BORDER_FILL_MAPPING"
    return {
        "status": status,
        "border_fill_count": len(border_fill_ids),
        "expected_border_fill_count": expected,
        "count_mismatch": count_mismatch,
        "referenced_border_fill_count": len(refs),
        "resolved_ref_count": len(refs) - len(missing_refs),
        "unresolved_ref_count": len(missing_refs),
        "unresolved_refs": missing_refs[:50],
    }


def build_para_shape_coverage(
    decoded_docinfo: dict[str, Any] | None,
    body_layout: dict[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(decoded_docinfo, dict):
        return {
            "status": "NO_DECODED_DOCINFO",
            "para_shape_count": 0,
            "referenced_text_paragraphs": 0,
            "unresolved_ref_count": 0,
        }
    shapes = (
        decoded_docinfo.get("para_shapes")
        if isinstance(decoded_docinfo.get("para_shapes"), list)
        else []
    )
    if not shapes:
        return {
            "status": "NO_PARA_SHAPES",
            "para_shape_count": 0,
            "referenced_text_paragraphs": 0,
            "unresolved_ref_count": 0,
        }
    expected = _docinfo_mapping_count(decoded_docinfo, "para_shape")
    count_mismatch = expected is not None and expected != len(shapes)
    known_ids = set()
    for row in shapes:
        if not isinstance(row, dict):
            continue
        try:
            known_ids.add(int(row.get("index")))
        except (TypeError, ValueError):
            continue
    paragraphs = _body_text_paragraphs(body_layout)
    refs = []
    missing_refs = []
    for index, paragraph in enumerate(paragraphs):
        try:
            para_shape_id = int(paragraph.get("para_shape_id"))
        except (TypeError, ValueError):
            continue
        refs.append(para_shape_id)
        if para_shape_id not in known_ids:
            missing_refs.append({"paragraph_index": index, "para_shape_id": para_shape_id})
    status = "PASS" if not count_mismatch and not missing_refs else "PARTIAL_PARA_SHAPE_MAPPING"
    return {
        "status": status,
        "para_shape_count": len(shapes),
        "expected_para_shape_count": expected,
        "count_mismatch": count_mismatch,
        "text_paragraph_count": len(paragraphs),
        "referenced_text_paragraphs": len(refs),
        "resolved_ref_count": len(refs) - len(missing_refs),
        "unresolved_ref_count": len(missing_refs),
        "unresolved_refs": missing_refs[:50],
    }


def _paragraph_char_shape_refs(paragraph: dict[str, Any]) -> list[int]:
    refs = []
    runs = (
        paragraph.get("char_shape_runs")
        if isinstance(paragraph.get("char_shape_runs"), list)
        else []
    )
    for run in runs:
        if not isinstance(run, dict):
            continue
        try:
            refs.append(int(run.get("char_shape_id")))
        except (TypeError, ValueError):
            continue
    if refs:
        return refs
    try:
        return [int(paragraph.get("first_char_shape_id"))]
    except (TypeError, ValueError):
        return []


def build_char_shape_coverage(
    decoded_docinfo: dict[str, Any] | None,
    body_layout: dict[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(decoded_docinfo, dict):
        return {
            "status": "NO_DECODED_DOCINFO",
            "char_shape_count": 0,
            "referenced_text_paragraphs": 0,
            "unresolved_ref_count": 0,
        }
    shapes = (
        decoded_docinfo.get("char_shapes")
        if isinstance(decoded_docinfo.get("char_shapes"), list)
        else []
    )
    if not shapes:
        return {
            "status": "NO_CHAR_SHAPES",
            "char_shape_count": 0,
            "referenced_text_paragraphs": 0,
            "unresolved_ref_count": 0,
        }
    expected = _docinfo_mapping_count(decoded_docinfo, "char_shape")
    count_mismatch = expected is not None and expected != len(shapes)
    known_ids = set()
    for row in shapes:
        if not isinstance(row, dict):
            continue
        try:
            known_ids.add(int(row.get("index")))
        except (TypeError, ValueError):
            continue
    paragraphs = _body_text_paragraphs(body_layout)
    ref_count = 0
    paragraph_ref_count = 0
    missing_refs = []
    for paragraph_index, paragraph in enumerate(paragraphs):
        refs = _paragraph_char_shape_refs(paragraph)
        if refs:
            paragraph_ref_count += 1
        for ref in refs:
            ref_count += 1
            if ref not in known_ids:
                missing_refs.append({"paragraph_index": paragraph_index, "char_shape_id": ref})
    status = "PASS" if not count_mismatch and not missing_refs else "PARTIAL_CHAR_SHAPE_MAPPING"
    return {
        "status": status,
        "char_shape_count": len(shapes),
        "expected_char_shape_count": expected,
        "count_mismatch": count_mismatch,
        "text_paragraph_count": len(paragraphs),
        "referenced_text_paragraphs": paragraph_ref_count,
        "referenced_char_shape_count": ref_count,
        "resolved_ref_count": ref_count - len(missing_refs),
        "unresolved_ref_count": len(missing_refs),
        "unresolved_refs": missing_refs[:50],
    }


def build_style_coverage(
    decoded_docinfo: dict[str, Any] | None, body_layout: dict[str, Any] | None
) -> dict[str, Any]:
    if not isinstance(decoded_docinfo, dict):
        return {"status": "NO_DECODED_DOCINFO", "style_count": 0, "unresolved_ref_count": 0}
    styles = (
        decoded_docinfo.get("styles") if isinstance(decoded_docinfo.get("styles"), list) else []
    )
    expected = _docinfo_mapping_count(decoded_docinfo, "style")
    if not styles and not expected:
        return {"status": "NO_STYLES", "style_count": 0, "unresolved_ref_count": 0}
    known_ids = _known_docinfo_ids(decoded_docinfo, "styles")
    count_mismatch = expected is not None and expected != len(styles)
    refs = []
    missing_refs = []
    for paragraph_index, paragraph in enumerate(_body_text_paragraphs(body_layout)):
        try:
            style_id = int(paragraph.get("style_id"))
        except (TypeError, ValueError):
            continue
        refs.append(style_id)
        if known_ids and style_id not in known_ids:
            missing_refs.append({"paragraph_index": paragraph_index, "style_id": style_id})
    status = "PASS" if not count_mismatch and not missing_refs else "PARTIAL_STYLE_MAPPING"
    return {
        "status": status,
        "style_count": len(styles),
        "expected_style_count": expected,
        "count_mismatch": count_mismatch,
        "referenced_style_count": len(refs),
        "resolved_ref_count": len(refs) - len(missing_refs),
        "unresolved_ref_count": len(missing_refs),
        "unresolved_refs": missing_refs[:50],
    }


def build_paragraph_layout_coverage(
    counts: Counter[int], body_layout: dict[str, Any] | None
) -> dict[str, Any]:
    para_header_count = int(counts.get(66, 0))
    para_text_count = int(counts.get(67, 0))
    para_char_shape_count = int(counts.get(68, 0))
    para_line_seg_count = int(counts.get(69, 0))
    para_range_tag_count = int(counts.get(70, 0))
    if not any((
        para_header_count,
        para_text_count,
        para_char_shape_count,
        para_line_seg_count,
        para_range_tag_count,
    )):
        return {
            "status": "NOT_PRESENT",
            "paragraph_count": 0,
            "text_paragraph_count": 0,
            "mismatches": [],
        }
    if not isinstance(body_layout, dict):
        return {
            "status": "NO_BODY_LAYOUT",
            "paragraph_count": 0,
            "text_paragraph_count": 0,
            "mismatches": [],
        }
    paragraph_count = int(body_layout.get("paragraph_count") or 0)
    text_paragraph_count = int(body_layout.get("text_paragraph_count") or 0)
    paragraphs = _body_text_paragraphs(body_layout)
    mismatches = []
    if paragraph_count != para_header_count:
        mismatches.append({
            "field": "paragraph_count",
            "expected": para_header_count,
            "actual": paragraph_count,
        })
    if text_paragraph_count != para_text_count:
        mismatches.append({
            "field": "text_paragraph_count",
            "expected": para_text_count,
            "actual": text_paragraph_count,
        })
    char_shape_mapped = sum(
        1
        for paragraph in paragraphs
        if paragraph.get("char_shape_runs") or paragraph.get("first_char_shape_id") is not None
    )
    line_seg_mapped = sum(1 for paragraph in paragraphs if paragraph.get("line_segments"))
    if para_char_shape_count and char_shape_mapped == 0:
        mismatches.append({
            "field": "para_char_shape_runs",
            "expected": para_char_shape_count,
            "actual": char_shape_mapped,
        })
    if para_line_seg_count and line_seg_mapped == 0:
        mismatches.append({
            "field": "para_line_segments",
            "expected": para_line_seg_count,
            "actual": line_seg_mapped,
        })
    status = "PASS" if not mismatches else "PARTIAL_PARAGRAPH_LAYOUT"
    return {
        "status": status,
        "paragraph_count": paragraph_count,
        "text_paragraph_count": text_paragraph_count,
        "para_header_record_count": para_header_count,
        "para_text_record_count": para_text_count,
        "para_char_shape_record_count": para_char_shape_count,
        "para_line_seg_record_count": para_line_seg_count,
        "para_range_tag_record_count": para_range_tag_count,
        "char_shape_mapped_paragraph_count": char_shape_mapped,
        "line_segment_mapped_paragraph_count": line_seg_mapped,
        "mismatch_count": len(mismatches),
        "mismatches": mismatches[:50],
    }


def build_controls_page_coverage(
    counts: Counter[int], page_layout: dict[str, Any] | None
) -> dict[str, Any]:
    tag_counts = {
        71: int(counts.get(71, 0)),
        72: int(counts.get(72, 0)),
        73: int(counts.get(73, 0)),
        74: int(counts.get(74, 0)),
        75: int(counts.get(75, 0)),
    }
    if not any(tag_counts.values()):
        return {"status": "NOT_PRESENT", "mismatch_count": 0, "mismatches": []}
    if not isinstance(page_layout, dict):
        return {"status": "NO_PAGE_LAYOUT", "mismatch_count": 0, "mismatches": []}
    sections = page_layout.get("sections") if isinstance(page_layout.get("sections"), list) else []
    actual = {
        71: sum(
            int(section.get("ctrl_header_count") or 0)
            for section in sections
            if isinstance(section, dict)
        ),
        72: sum(
            int(section.get("list_header_count") or 0)
            for section in sections
            if isinstance(section, dict)
        ),
        73: sum(
            int(section.get("page_definition_count") or 0)
            for section in sections
            if isinstance(section, dict)
        ),
        74: sum(
            int(section.get("footnote_shape_count") or 0)
            for section in sections
            if isinstance(section, dict)
        ),
        75: sum(
            int(section.get("page_border_fill_count") or 0)
            for section in sections
            if isinstance(section, dict)
        ),
    }
    mismatches = [
        {
            "tag_id": tag,
            "tag_name": _record_name(tag),
            "expected": expected,
            "actual": actual.get(tag, 0),
        }
        for tag, expected in tag_counts.items()
        if expected != actual.get(tag, 0)
    ]
    mapped_page_defs = int(page_layout.get("mapped_page_definition_count") or 0)
    if tag_counts[73] and mapped_page_defs <= 0:
        mismatches.append({
            "tag_id": 73,
            "tag_name": _record_name(73),
            "expected": tag_counts[73],
            "actual": mapped_page_defs,
            "field": "mapped_page_definition_count",
        })
    status = "PASS" if not mismatches else "PARTIAL_CONTROLS_PAGE"
    return {
        "status": status,
        "section_count": len(sections),
        "record_counts": {
            str(tag): {"tag_name": _record_name(tag), "count": count}
            for tag, count in tag_counts.items()
            if count
        },
        "mapped_counts": {
            str(tag): {"tag_name": _record_name(tag), "count": actual.get(tag, 0)}
            for tag, count in tag_counts.items()
            if count
        },
        "mapped_page_definition_count": mapped_page_defs,
        "mismatch_count": len(mismatches),
        "mismatches": mismatches[:50],
    }


def _table_rows_from_layout(table_layout: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(table_layout, dict):
        return []
    sections = (
        table_layout.get("sections") if isinstance(table_layout.get("sections"), list) else []
    )
    rows = []
    for section in sections:
        if not isinstance(section, dict):
            continue
        section_index = section.get("section_index")
        for table in section.get("tables") or []:
            if isinstance(table, dict):
                rows.append({**table, "_section_index": section_index})
    return rows


def _valid_row_cell_counts(row_cell_counts: Any, row_count: int, col_count: int) -> bool:
    if not isinstance(row_cell_counts, list) or len(row_cell_counts) != row_count:
        return False
    for value in row_cell_counts:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return False
        if parsed <= 0 or parsed > col_count:
            return False
    return True


def build_table_coverage(
    counts: Counter[int], table_layout: dict[str, Any] | None
) -> dict[str, Any]:
    table_record_count = int(counts.get(77, 0) or 0)
    if table_record_count <= 0:
        return {
            "status": "NO_TABLES",
            "table_record_count": 0,
            "mapped_table_count": 0,
            "missing_dimension_count": 0,
            "invalid_row_cell_count": 0,
        }
    if not isinstance(table_layout, dict):
        return {
            "status": "NO_TABLE_LAYOUT",
            "table_record_count": table_record_count,
            "mapped_table_count": 0,
            "missing_dimension_count": table_record_count,
            "invalid_row_cell_count": table_record_count,
        }
    tables = _table_rows_from_layout(table_layout)
    missing_dimensions = []
    invalid_row_cells = []
    list_header_total = 0
    mapped_list_header_total = 0
    extra_list_header_total = 0
    unmapped_cell_capacity_total = 0
    for index, table in enumerate(tables[:table_record_count]):
        decoded_table = table.get("table") if isinstance(table.get("table"), dict) else {}
        try:
            row_count = int(decoded_table.get("row_count"))
            col_count = int(decoded_table.get("col_count"))
        except (TypeError, ValueError):
            row_count = col_count = 0
        if row_count <= 0 or col_count <= 0:
            missing_dimensions.append({
                "table_index": table.get("table_index", index),
                "section_index": table.get("_section_index"),
                "record_index": table.get("record_index"),
                "row_count": decoded_table.get("row_count"),
                "col_count": decoded_table.get("col_count"),
            })
        if (
            row_count > 0
            and col_count > 0
            and not _valid_row_cell_counts(
                decoded_table.get("row_cell_counts"), row_count, col_count
            )
        ):
            invalid_row_cells.append({
                "table_index": table.get("table_index", index),
                "section_index": table.get("_section_index"),
                "record_index": table.get("record_index"),
                "row_count": row_count,
                "col_count": col_count,
                "row_cell_counts": decoded_table.get("row_cell_counts"),
            })
        list_headers = (
            table.get("list_headers") if isinstance(table.get("list_headers"), list) else []
        )
        list_header_total += len(list_headers)
        mapped_list_header_total += int(table.get("mapped_list_header_count") or 0)
        extra_list_header_total += int(table.get("extra_list_header_count") or 0)
        unmapped_cell_capacity_total += int(table.get("unmapped_cell_capacity") or 0)
    missing_layout_records = [
        {"table_index": index, "reason": "TABLE_LAYOUT_RECORD_NOT_DECODED"}
        for index in range(len(tables), table_record_count)
    ]
    status = (
        "PASS"
        if len(tables) >= table_record_count and not missing_dimensions and not invalid_row_cells
        else "PARTIAL_TABLE_MAPPING"
    )
    warnings = []
    if extra_list_header_total or unmapped_cell_capacity_total:
        warnings.append("TABLE_LIST_HEADER_CELL_IDENTITY_PARTIAL")
    return {
        "status": status,
        "table_record_count": table_record_count,
        "mapped_table_count": min(len(tables), table_record_count),
        "missing_layout_record_count": max(0, table_record_count - len(tables)),
        "missing_layout_records": missing_layout_records[:50],
        "missing_dimension_count": len(missing_dimensions),
        "missing_dimensions": missing_dimensions[:50],
        "invalid_row_cell_count": len(invalid_row_cells),
        "invalid_row_cells": invalid_row_cells[:50],
        "source_list_header_count": list_header_total,
        "mapped_list_header_count": mapped_list_header_total,
        "extra_list_header_count": extra_list_header_total,
        "unmapped_cell_capacity": unmapped_cell_capacity_total,
        "warnings": warnings,
    }


def _known_list_ids(decoded_docinfo: dict[str, Any], key: str) -> set[int]:
    rows = decoded_docinfo.get(key) if isinstance(decoded_docinfo.get(key), list) else []
    ids = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            ids.add(int(row.get("index")))
        except (TypeError, ValueError):
            continue
    return ids


def _numbering_level_count(row: dict[str, Any]) -> int:
    levels = row.get("levels") if isinstance(row.get("levels"), list) else []
    return len([level for level in levels if isinstance(level, dict)])


def _resolve_numbering_para_shape(
    row: dict[str, Any],
    numbering_ids: set[int],
    bullet_ids: set[int],
    numbering_levels: dict[int, int],
) -> dict[str, Any]:
    try:
        raw_id = int(row.get("numbering_bullet_id"))
    except (TypeError, ValueError):
        raw_id = None
    try:
        heading_type = int(row.get("heading_type") or 0)
    except (TypeError, ValueError):
        heading_type = 0
    try:
        level = int(row.get("level") or 0)
    except (TypeError, ValueError):
        level = 0
    if (raw_id is None or raw_id <= 0) and heading_type and 0 in numbering_ids:
        level_count = numbering_levels.get(0, 0)
        return {
            "status": "APPLIED" if level < level_count else "UNRESOLVED",
            "kind": "numbering",
            "id_ref": 0,
            "raw_id": raw_id,
            "level": level,
            "implicit_default": True,
            "reason": None if level < level_count else "LEVEL_OUT_OF_RANGE",
        }
    if raw_id is None or raw_id <= 0:
        return {
            "status": "NOT_APPLIED",
            "raw_id": raw_id,
            "level": level,
            "reason": "NO_NUMBERING_BULLET_ID",
        }
    for candidate in (raw_id - 1, raw_id):
        if candidate in numbering_ids:
            level_count = numbering_levels.get(candidate, 0)
            return {
                "status": "APPLIED" if level < level_count else "UNRESOLVED",
                "kind": "numbering",
                "id_ref": candidate,
                "raw_id": raw_id,
                "level": level,
                "reason": None if level < level_count else "LEVEL_OUT_OF_RANGE",
            }
    for candidate in (raw_id - 1, raw_id):
        if candidate in bullet_ids:
            return {
                "status": "APPLIED",
                "kind": "bullet",
                "id_ref": candidate,
                "raw_id": raw_id,
                "level": level,
            }
    return {"status": "UNRESOLVED", "raw_id": raw_id, "level": level, "reason": "LIST_ID_NOT_FOUND"}


def _numbering_count_mismatches(
    numberings: list[Any],
    bullets: list[Any],
    expected_numberings: int | None,
    expected_bullets: int | None,
) -> list[dict[str, Any]]:
    count_mismatches = []
    if expected_numberings is not None and expected_numberings != len(numberings):
        count_mismatches.append({
            "key": "numbering",
            "expected": expected_numberings,
            "actual": len(numberings),
        })
    if expected_bullets is not None and expected_bullets != len(bullets):
        count_mismatches.append({
            "key": "bullet",
            "expected": expected_bullets,
            "actual": len(bullets),
        })
    return count_mismatches


def _malformed_numberings(numberings: list[Any]) -> list[dict[str, Any]]:
    malformed_numberings = []
    for row in numberings:
        if not isinstance(row, dict):
            continue
        if _numbering_level_count(row) <= 0:
            malformed_numberings.append({"numbering_id": row.get("index"), "reason": "NO_LEVELS"})
    return malformed_numberings


def _resolve_numbering_references(
    para_shapes: list[Any], numbering_ids: Any, bullet_ids: Any, numbering_levels: dict[int, int]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    referenced = []
    unresolved = []
    not_applied = 0
    for row in para_shapes:
        if not isinstance(row, dict):
            continue
        if not row.get("heading_type") and not row.get("numbering_bullet_id"):
            continue
        resolved = _resolve_numbering_para_shape(row, numbering_ids, bullet_ids, numbering_levels)
        ref = {
            "para_shape_id": row.get("index"),
            "heading_type": row.get("heading_type"),
            "level": row.get("level"),
            "numbering_bullet_id": row.get("numbering_bullet_id"),
            "mapping": resolved,
        }
        referenced.append(ref)
        if resolved.get("status") == "UNRESOLVED":
            unresolved.append(ref)
        elif resolved.get("status") == "NOT_APPLIED":
            not_applied += 1
    return referenced, unresolved, not_applied


def build_numbering_coverage(decoded_docinfo: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(decoded_docinfo, dict):
        return {"status": "NO_DECODED_DOCINFO", "numbering_count": 0, "unresolved_ref_count": 0}
    numberings = (
        decoded_docinfo.get("numberings")
        if isinstance(decoded_docinfo.get("numberings"), list)
        else []
    )
    bullets = (
        decoded_docinfo.get("bullets") if isinstance(decoded_docinfo.get("bullets"), list) else []
    )
    if not numberings and not bullets:
        return {
            "status": "NO_LIST_DEFINITIONS",
            "numbering_count": 0,
            "bullet_count": 0,
            "unresolved_ref_count": 0,
        }
    expected_numberings = _docinfo_mapping_count(decoded_docinfo, "numbering")
    expected_bullets = _docinfo_mapping_count(decoded_docinfo, "bullet")
    count_mismatches = _numbering_count_mismatches(
        numberings, bullets, expected_numberings, expected_bullets
    )
    numbering_ids = _known_list_ids(decoded_docinfo, "numberings")
    bullet_ids = _known_list_ids(decoded_docinfo, "bullets")
    numbering_levels = {
        int(row.get("index")): _numbering_level_count(row)
        for row in numberings
        if isinstance(row, dict) and row.get("index") is not None
    }
    malformed_numberings = _malformed_numberings(numberings)
    para_shapes = (
        decoded_docinfo.get("para_shapes")
        if isinstance(decoded_docinfo.get("para_shapes"), list)
        else []
    )
    referenced, unresolved, not_applied = _resolve_numbering_references(
        para_shapes, numbering_ids, bullet_ids, numbering_levels
    )
    status = (
        "PASS"
        if not count_mismatches and not malformed_numberings and not unresolved
        else "PARTIAL_NUMBERING_MAPPING"
    )
    return {
        "status": status,
        "numbering_count": len(numberings),
        "expected_numbering_count": expected_numberings,
        "bullet_count": len(bullets),
        "expected_bullet_count": expected_bullets,
        "count_mismatch_count": len(count_mismatches),
        "count_mismatches": count_mismatches,
        "malformed_numbering_count": len(malformed_numberings),
        "malformed_numberings": malformed_numberings[:50],
        "referenced_para_shape_count": len(referenced),
        "applied_para_shape_count": sum(
            1 for row in referenced if row.get("mapping", {}).get("status") == "APPLIED"
        ),
        "not_applied_para_shape_count": not_applied,
        "unresolved_ref_count": len(unresolved),
        "unresolved_refs": unresolved[:50],
    }


def _equation_rows(equation_layout: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(equation_layout, dict):
        return []
    sections = (
        equation_layout.get("sections") if isinstance(equation_layout.get("sections"), list) else []
    )
    rows = []
    for section in sections:
        if not isinstance(section, dict):
            continue
        section_index = section.get("section_index")
        for row in section.get("equations") or []:
            if isinstance(row, dict):
                rows.append({**row, "section_index": section_index})
    return rows


def build_equation_coverage(
    counts: Counter[int], equation_layout: dict[str, Any] | None
) -> dict[str, Any]:
    eqedit_count = int(counts.get(88, 0) or 0)
    ctrl_data_count = int(counts.get(87, 0) or 0)
    if eqedit_count <= 0 and ctrl_data_count <= 0:
        return {
            "status": "NO_EQUATIONS",
            "eqedit_count": 0,
            "ctrl_data_count": 0,
            "preserved_equation_count": 0,
        }
    rows = _equation_rows(equation_layout)
    missing_formula = []
    for index, row in enumerate(rows[:eqedit_count]):
        if not str(row.get("formula") or "").strip():
            missing_formula.append({
                "equation_index": index,
                "section_index": row.get("section_index"),
                "record_index": row.get("record_index"),
                "payload_size": row.get("payload_size"),
            })
    missing_records = [
        {"equation_index": index, "reason": "EQEDIT_LAYOUT_RECORD_NOT_DECODED"}
        for index in range(len(rows), eqedit_count)
    ]
    status = (
        "PASS"
        if ctrl_data_count == 0 and len(rows) >= eqedit_count and not missing_formula
        else "PARTIAL_EQUATION_MAPPING"
    )
    return {
        "status": status,
        "eqedit_count": eqedit_count,
        "ctrl_data_count": ctrl_data_count,
        "preserved_equation_count": min(len(rows), eqedit_count),
        "missing_record_count": max(0, eqedit_count - len(rows)),
        "missing_records": missing_records[:50],
        "missing_formula_count": len(missing_formula),
        "missing_formula": missing_formula[:50],
        "formulas": [
            {
                "section_index": row.get("section_index"),
                "record_index": row.get("record_index"),
                "formula": row.get("formula"),
                "version": row.get("version"),
                "application": row.get("application"),
                "payload_size": row.get("payload_size"),
            }
            for row in rows[:50]
        ],
    }


def _shape_layout_pictures(shape_layout: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(shape_layout, dict):
        return []
    sections = (
        shape_layout.get("sections") if isinstance(shape_layout.get("sections"), list) else []
    )
    pictures = []
    for section in sections:
        if not isinstance(section, dict):
            continue
        for row in section.get("pictures") or []:
            if isinstance(row, dict):
                pictures.append(row)
    return pictures


def _positive_dimension(value: Any) -> bool:
    try:
        return int(value) > 0
    except (TypeError, ValueError):
        return False


def _picture_has_geometry(row: dict[str, Any]) -> bool:
    picture = row.get("picture") if isinstance(row.get("picture"), dict) else {}
    component = row.get("component") if isinstance(row.get("component"), dict) else {}
    bbox = picture.get("bbox") if isinstance(picture.get("bbox"), dict) else {}
    current_size = (
        component.get("current_size_normalized")
        if isinstance(component.get("current_size_normalized"), dict)
        else {}
    )
    return (_positive_dimension(bbox.get("width")) and _positive_dimension(bbox.get("height"))) or (
        _positive_dimension(current_size.get("width"))
        and _positive_dimension(current_size.get("height"))
    )


def _picture_has_position(row: dict[str, Any]) -> bool:
    control = row.get("control") if isinstance(row.get("control"), dict) else {}
    return isinstance(control.get("position"), dict)


def _picture_has_layout_policy(row: dict[str, Any]) -> bool:
    control = row.get("control") if isinstance(row.get("control"), dict) else {}
    return isinstance(control.get("layout"), dict)


def _bindata_picture_numeric_ids(
    bindata_streams: list[str], decoded_docinfo: dict[str, Any] | None
) -> set[int]:
    ids: set[int] = set()
    for stream in bindata_streams:
        name = str(stream).replace("\\", "/").rsplit("/", 1)[-1]
        stem = name.rsplit(".", 1)[0]
        if not stem.upper().startswith("BIN"):
            continue
        token = stem[3:]
        if not token:
            continue
        for base in (10, 16):
            try:
                ids.add(int(token, base))
            except ValueError:
                pass
    if isinstance(decoded_docinfo, dict):
        records = (
            decoded_docinfo.get("binary_data")
            if isinstance(decoded_docinfo.get("binary_data"), list)
            else []
        )
        for row in records:
            if not isinstance(row, dict):
                continue
            try:
                ids.add(int(row.get("storage_id")))
            except (TypeError, ValueError):
                continue
    return ids


def build_picture_coverage(
    counts: Counter[int],
    bindata_streams: list[str],
    decoded_docinfo: dict[str, Any] | None,
    shape_layout: dict[str, Any] | None,
) -> dict[str, Any]:
    picture_count = int(counts.get(85, 0) or 0)
    if picture_count <= 0:
        return {
            "status": "NO_PICTURES",
            "picture_record_count": 0,
            "mapped_picture_count": 0,
            "unresolved_ref_count": 0,
        }
    pictures = _shape_layout_pictures(shape_layout)
    bindata_ids = _bindata_picture_numeric_ids(bindata_streams, decoded_docinfo)
    unresolved_refs = []
    missing_geometry = []
    missing_position = []
    missing_layout_policy = []
    for index, row in enumerate(pictures[:picture_count]):
        picture = row.get("picture") if isinstance(row.get("picture"), dict) else {}
        try:
            binary_data_id = int(picture.get("binary_data_id"))
        except (TypeError, ValueError):
            binary_data_id = None
        if binary_data_id is None or binary_data_id not in bindata_ids:
            unresolved_refs.append({
                "picture_index": index,
                "record_index": row.get("record_index"),
                "binary_data_id": binary_data_id,
            })
        if not _picture_has_geometry(row):
            missing_geometry.append({
                "picture_index": index,
                "record_index": row.get("record_index"),
            })
        if not _picture_has_position(row):
            missing_position.append({
                "picture_index": index,
                "record_index": row.get("record_index"),
            })
        if not _picture_has_layout_policy(row):
            missing_layout_policy.append({
                "picture_index": index,
                "record_index": row.get("record_index"),
            })
    missing_layout_rows = [
        {"picture_index": index, "reason": "PICTURE_LAYOUT_RECORD_NOT_DECODED"}
        for index in range(len(pictures), picture_count)
    ]
    status = (
        "PASS"
        if len(pictures) >= picture_count
        and not unresolved_refs
        and not missing_geometry
        and not missing_position
        and not missing_layout_policy
        else "PARTIAL_PICTURE_MAPPING"
    )
    return {
        "status": status,
        "picture_record_count": picture_count,
        "mapped_picture_count": min(len(pictures), picture_count),
        "image_bindata_id_count": len(bindata_ids),
        "geometry_mapped_count": min(len(pictures), picture_count) - len(missing_geometry),
        "position_mapped_count": min(len(pictures), picture_count) - len(missing_position),
        "layout_policy_mapped_count": min(len(pictures), picture_count)
        - len(missing_layout_policy),
        "unresolved_ref_count": len(unresolved_refs),
        "unresolved_refs": unresolved_refs[:50],
        "missing_geometry_count": len(missing_geometry),
        "missing_geometry": missing_geometry[:50],
        "missing_position_count": len(missing_position),
        "missing_position": missing_position[:50],
        "missing_layout_policy_count": len(missing_layout_policy),
        "missing_layout_policy": missing_layout_policy[:50],
        "missing_layout_record_count": max(0, picture_count - len(pictures)),
        "missing_layout_records": missing_layout_rows[:50],
    }


def _shape_layout_rectangles(shape_layout: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(shape_layout, dict):
        return []
    rectangles = []
    sections = (
        shape_layout.get("sections") if isinstance(shape_layout.get("sections"), list) else []
    )
    for section in sections:
        if not isinstance(section, dict):
            continue
        for row in section.get("rectangles") or []:
            if isinstance(row, dict):
                rectangles.append(row)
    return rectangles


def _shape_layout_components(shape_layout: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(shape_layout, dict):
        return []
    components = []
    sections = (
        shape_layout.get("sections") if isinstance(shape_layout.get("sections"), list) else []
    )
    for section in sections:
        if not isinstance(section, dict):
            continue
        for row in section.get("components") or []:
            if isinstance(row, dict):
                components.append(row)
    return components


def _rectangle_has_geometry(row: dict[str, Any]) -> bool:
    rectangle = row.get("rectangle") if isinstance(row.get("rectangle"), dict) else {}
    component = row.get("component") if isinstance(row.get("component"), dict) else {}
    bbox = rectangle.get("bbox") if isinstance(rectangle.get("bbox"), dict) else {}
    current_size = (
        component.get("current_size_normalized")
        if isinstance(component.get("current_size_normalized"), dict)
        else {}
    )
    return (_positive_dimension(bbox.get("width")) and _positive_dimension(bbox.get("height"))) or (
        _positive_dimension(current_size.get("width"))
        and _positive_dimension(current_size.get("height"))
    )


def _rectangle_has_position(row: dict[str, Any]) -> bool:
    control = row.get("control") if isinstance(row.get("control"), dict) else {}
    return isinstance(control.get("position"), dict)


def _rectangle_has_layout_policy(row: dict[str, Any]) -> bool:
    control = row.get("control") if isinstance(row.get("control"), dict) else {}
    return isinstance(control.get("layout"), dict)


def build_shape_coverage(
    counts: Counter[int], shape_layout: dict[str, Any] | None
) -> dict[str, Any]:
    vector_tags = {78, 79, 80, 81, 82, 83, 86}
    vector_record_count = sum(int(counts.get(tag, 0) or 0) for tag in vector_tags)
    shape_component_count = int(counts.get(76, 0) or 0)
    if shape_component_count <= 0 and vector_record_count <= 0:
        return {
            "status": "NO_VECTOR_SHAPES",
            "shape_component_count": 0,
            "vector_shape_record_count": 0,
            "mapped_vector_shape_count": 0,
            "unmapped_vector_shape_record_count": 0,
        }
    if not isinstance(shape_layout, dict):
        return {
            "status": "NO_SHAPE_LAYOUT",
            "shape_component_count": shape_component_count,
            "vector_shape_record_count": vector_record_count,
            "mapped_vector_shape_count": 0,
            "unmapped_vector_shape_record_count": vector_record_count,
        }
    unsupported_vector_tags = [
        {"tag_id": tag, "tag_name": _record_name(tag), "count": int(counts.get(tag, 0) or 0)}
        for tag in sorted(vector_tags - {79})
        if counts.get(tag, 0)
    ]
    components = _shape_layout_components(shape_layout)
    rectangles = _shape_layout_rectangles(shape_layout)
    missing_geometry = []
    missing_position = []
    missing_layout_policy = []
    for index, row in enumerate(rectangles[: int(counts.get(79, 0) or 0)]):
        if not _rectangle_has_geometry(row):
            missing_geometry.append({"shape_index": index, "record_index": row.get("record_index")})
        if not _rectangle_has_position(row):
            missing_position.append({"shape_index": index, "record_index": row.get("record_index")})
        if not _rectangle_has_layout_policy(row):
            missing_layout_policy.append({
                "shape_index": index,
                "record_index": row.get("record_index"),
            })
    unmapped_vector_count = max(0, vector_record_count - len(rectangles))
    unmapped_component_count = max(0, shape_component_count - len(components))
    status = (
        "PASS"
        if not unsupported_vector_tags
        and unmapped_vector_count == 0
        and unmapped_component_count == 0
        and not missing_geometry
        and not missing_position
        and not missing_layout_policy
        else "PARTIAL_SHAPE_MAPPING"
    )
    return {
        "status": status,
        "shape_component_count": shape_component_count,
        "mapped_shape_component_count": min(len(components), shape_component_count),
        "unmapped_shape_component_count": unmapped_component_count,
        "vector_shape_record_count": vector_record_count,
        "rectangle_record_count": int(counts.get(79, 0) or 0),
        "mapped_vector_shape_count": min(len(rectangles), vector_record_count),
        "unmapped_vector_shape_record_count": unmapped_vector_count,
        "unsupported_vector_tags": unsupported_vector_tags,
        "missing_geometry_count": len(missing_geometry),
        "missing_geometry": missing_geometry[:50],
        "missing_position_count": len(missing_position),
        "missing_position": missing_position[:50],
        "missing_layout_policy_count": len(missing_layout_policy),
        "missing_layout_policy": missing_layout_policy[:50],
    }


def build_bindata_stream_coverage(
    bindata_streams: list[str],
    decoded_docinfo: dict[str, Any] | None,
) -> dict[str, Any]:
    normalized_streams = sorted({str(name).replace("\\", "/") for name in bindata_streams})
    if not normalized_streams:
        return {
            "status": "NO_BINDATA_STREAMS",
            "stream_count": 0,
            "decoded_record_count": 0,
            "matched_stream_count": 0,
            "missing_docinfo_streams": [],
        }

    records = []
    if isinstance(decoded_docinfo, dict):
        records = [
            item for item in decoded_docinfo.get("binary_data") or [] if isinstance(item, dict)
        ]
    record_streams = {
        str(item.get("stream_name") or "").replace("\\", "/")
        for item in records
        if item.get("stream_name")
    }
    numeric_records = {
        int(item["storage_id"]) for item in records if isinstance(item.get("storage_id"), int)
    }
    matched = []
    missing = []
    for stream in normalized_streams:
        numeric_id = _bindata_numeric_id(stream)
        if stream in record_streams or (numeric_id is not None and numeric_id in numeric_records):
            matched.append(stream)
        else:
            missing.append(stream)

    status = "PASS" if not missing else "PARTIAL_RECORD_STREAM_MISMATCH"
    return {
        "status": status,
        "stream_count": len(normalized_streams),
        "decoded_record_count": len(records),
        "matched_stream_count": len(matched),
        "missing_docinfo_streams": missing,
    }


def build_binary_object_coverage(
    counts: Counter[int],
    bindata_coverage: dict[str, Any] | None,
    picture_coverage: dict[str, Any] | None,
) -> dict[str, Any]:
    bindata_count = int(counts.get(18, 0) or 0)
    ole_count = int(counts.get(84, 0) or 0)
    picture_count = int(counts.get(85, 0) or 0)
    if bindata_count <= 0 and ole_count <= 0 and picture_count <= 0:
        return {
            "status": "NO_BINARY_OBJECTS",
            "bindata_record_count": 0,
            "ole_record_count": 0,
            "picture_record_count": 0,
        }
    blockers = []
    if ole_count:
        blockers.append({"kind": "OLE_OBJECTS_NOT_MAPPED", "count": ole_count})
    if bindata_count and (bindata_coverage or {}).get("status") != "PASS":
        blockers.append({
            "kind": "BINDATA_NOT_FULLY_MATCHED",
            "status": (bindata_coverage or {}).get("status"),
        })
    if picture_count and (picture_coverage or {}).get("status") != "PASS":
        blockers.append({
            "kind": "PICTURES_NOT_FULLY_MAPPED",
            "status": (picture_coverage or {}).get("status"),
        })
    status = "PASS" if not blockers else "PARTIAL_BINARY_OBJECT_MAPPING"
    return {
        "status": status,
        "bindata_record_count": bindata_count,
        "ole_record_count": ole_count,
        "picture_record_count": picture_count,
        "bindata_status": (bindata_coverage or {}).get("status"),
        "picture_status": (picture_coverage or {}).get("status"),
        "blocker_count": len(blockers),
        "blockers": blockers,
    }


def _bindata_numeric_id(stream_name: str) -> int | None:
    name = str(stream_name).replace("\\", "/").rsplit("/", 1)[-1]
    stem = name.rsplit(".", 1)[0]
    if not stem.upper().startswith("BIN"):
        return None
    digits = stem[3:]
    if not digits.isdigit():
        return None
    return int(digits)


def _priority_tag_targets(
    counts: Counter[int], coverage_by_tag: dict[int, dict[str, Any] | None]
) -> list[dict[str, Any]]:
    targets = []
    for tag in (16, 17, 19, 20, 21, 23, 24, 25, 77, 85, 88):
        if (coverage_by_tag.get(tag) or {}).get("status") == "PASS":
            continue
        count = counts.get(tag, 0)
        if count:
            targets.append({
                "tag_id": tag,
                "tag_name": _record_name(tag),
                "count": count,
                "action": decoder_action(tag),
            })
    return targets


def next_decoder_targets(
    counts: Counter[int],
    bindata_streams: list[str],
    coverage_by_tag: dict[int, dict[str, Any] | None],
    bindata_coverage: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    targets = _priority_tag_targets(counts, coverage_by_tag)
    if bindata_streams and (bindata_coverage or {}).get("status") != "PASS":
        targets.append({
            "tag_id": 18,
            "tag_name": "BIN_DATA_STREAMS",
            "count": len(bindata_streams),
            "action": "Decode BinData storage names, copy binary payloads, and emit HWPX manifest/resource references.",
        })
    return targets


def decoder_action(tag_id: int) -> str:
    actions = {
        16: "Decode document properties and emit HWPX package metadata.",
        17: "Decode ID mappings so style/resource references can be preserved.",
        18: "Decode BinData records and resource links.",
        19: "Decode face names and generate HWPX font face table.",
        20: "Decode border/fill definitions and map them to HWPX border fills.",
        21: "Decode character shape records and map charPr style references.",
        23: "Decode numbering definitions and map paragraph heading/list references.",
        24: "Decode bullet definitions and map paragraph heading/list references.",
        25: "Decode paragraph shape records and map paraPr style references.",
        77: "Decode table cell geometry, spans, borders, margins, and sizes.",
        85: "Decode picture records and bind BinData image resources.",
        88: "Decode equation editor payloads or preserve as embedded resources.",
    }
    return actions.get(tag_id, "Add decoder and HWPX writer mapping.")
