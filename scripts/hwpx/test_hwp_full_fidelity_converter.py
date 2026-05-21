from collections import Counter
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile
import xml.etree.ElementTree as ET

import hwp_full_fidelity_converter as full
import hwp_full_fidelity_package as full_package


def test_architecture_router_classifies_new_code_destinations() -> None:
    routed = full.route_new_code("add schema gate router for module classification")

    assert routed["status"] == "PASS"
    assert routed["recommended_module"] == "architecture"
    assert routed["recommended_path"].endswith("hwp_full_fidelity_architecture.py")

    gate = full.module_architecture_gate(
        "add table cell metric section xml update",
        ["scripts/hwpx/hwp_full_fidelity_converter.py"],
    )

    assert gate["status"] == "FAIL"
    assert gate["route"]["recommended_module"] == "section_updates"


def test_security_gate_blocks_forbidden_conversion_dependencies() -> None:
    routed = full.route_new_code("add security gate for network download prevention")
    assert routed["recommended_module"] == "security"

    blocked = full.security_gate(
        "download document and run Hancom COM automation through subprocess",
        ["scripts/hwpx/hwp_full_fidelity_converter.py"],
    )
    assert blocked["status"] == "FAIL"
    assert {hit["key"] for hit in blocked["forbidden_hits"]} >= {"network_dependency", "hancom_runtime", "shell_execution"}

    archive_gate = full.security_gate(
        "rewrite zip preview entries with path traversal guard",
        ["scripts/hwpx/hwp_full_fidelity_package.py"],
    )
    assert archive_gate["status"] == "PASS"
    assert archive_gate["sensitive_hits"][0]["owner_in_planned_paths"] is True


def test_architecture_router_covers_hwpx_document_editor_modules() -> None:
    schema_route = full.route_new_code("add HWPX editor compose job schema validation")
    assert schema_route["recommended_module"] == "hwpx_editor_schema"
    assert schema_route["recommended_path"].endswith("hwpx_job_schema.py")

    table_gate = full.module_architecture_gate(
        "add HWPX document editor table merge operation",
        ["scripts/hwpx/hwpx_table_merge_ops.py"],
    )
    assert table_gate["status"] == "PASS"
    assert table_gate["route"]["recommended_module"] == "hwpx_editor_table_ops"

    wrong_gate = full.module_architecture_gate(
        "add HWPX editor visible image operation",
        ["scripts/hwpx/hwp_full_fidelity_converter.py"],
    )
    assert wrong_gate["status"] == "FAIL"
    assert wrong_gate["route"]["recommended_module"] == "hwpx_editor_image_ops"


def test_build_coverage_fails_closed_for_style_and_table_records() -> None:
    coverage = full.build_coverage(
        Counter({67: 2, 21: 1, 25: 1, 77: 1}),
        [],
        {"ok": True, "text": "body"},
    )

    assert coverage["status"] == "FAIL"
    assert coverage["full_fidelity_ready"] is False
    assert "PARTIAL:fonts_and_styles" in coverage["blockers"]
    assert "PARTIAL:tables" in coverage["blockers"]
    assert coverage["record_coverage_ratio"] < 1
    assert coverage["decode_coverage_ratio"] > coverage["record_coverage_ratio"]
    assert [row["tag_id"] for row in coverage["next_decoder_targets"]] == [21, 25, 77]


def test_build_coverage_treats_document_properties_as_audited() -> None:
    decoded = {
        "document_properties": {
            "section_count": 1,
            "page_start": 3,
            "footnote_start": 4,
            "endnote_start": 5,
            "picture_start": 6,
            "table_start": 7,
            "equation_start": 8,
        }
    }

    coverage = full.build_coverage(Counter({16: 1}), [], {"ok": True, "text": "body"}, decoded)

    assert coverage["document_properties_coverage"]["status"] == "PASS"
    assert coverage["document_properties_coverage"]["mapped_field_count"] == 7
    assert all(row["tag_id"] != 16 for row in coverage["next_decoder_targets"])


def test_build_coverage_keeps_incomplete_document_properties_as_next_target() -> None:
    decoded = {"document_properties": {"section_count": 1, "page_start": 3}}

    coverage = full.build_coverage(Counter({16: 1}), [], {"ok": True, "text": "body"}, decoded)

    assert coverage["document_properties_coverage"]["status"] == "PARTIAL_DOCUMENT_PROPERTIES"
    assert "table_start" in coverage["document_properties_coverage"]["missing_fields"]
    assert any(row["tag_id"] == 16 for row in coverage["next_decoder_targets"])


def test_docinfo_extension_tags_are_known_and_audited() -> None:
    records = [
        {"index": 0, "tag_id": 30, "tag_name": "COMPATIBLE_DOCUMENT", "decoded": full.decode_known_record(30, b"\x02\x00\x00\x00")},
        {"index": 1, "tag_id": 31, "tag_name": "LAYOUT_COMPATIBILITY", "decoded": full.decode_known_record(31, b"\x00" * 20)},
        {"index": 2, "tag_id": 32, "tag_name": "TRACK_CHANGE", "decoded": full.decode_known_record(32, b"\x03\x00\x00\x00" + b"\x00" * 1028)},
        {"index": 3, "tag_id": 92, "tag_name": "MEMO_SHAPE", "decoded": full.decode_known_record(92, b"\x00" * 22)},
        {"index": 4, "tag_id": 94, "tag_name": "FORBIDDEN_CHAR", "decoded": full.decode_known_record(94, b"\x00" * 4)},
    ]
    decoded = full.build_decoded_docinfo(records)

    coverage = full.build_coverage(Counter({30: 1, 31: 1, 32: 1, 92: 1, 94: 1}), [], {"ok": True, "text": "body"}, decoded)

    assert coverage["unknown_tags"] == []
    assert "UNKNOWN_RECORD_TAGS" not in coverage["blockers"]
    assert coverage["docinfo_extension_coverage"]["status"] == "PASS"
    assert coverage["docinfo_extension_coverage"]["decoded_count"] == 5
    assert "PARTIAL:docinfo_extensions" not in coverage["blockers"]
    assert any(row["family"] == "docinfo_extensions" and row["status"] == "AUDITED" for row in coverage["required_families"])


def test_build_coverage_treats_id_mappings_as_audited() -> None:
    decoded = {
        "id_mappings": {
            "raw_count": 18,
            "counts": {
                "binary_data": 1,
                "hangul_font": 1,
                "latin_font": 1,
                "border_fill": 1,
                "char_shape": 1,
                "tab_def": 1,
                "numbering": 1,
                "bullet": 0,
                "para_shape": 1,
                "style": 1,
            },
        },
        "binary_data": [{"index": 0}],
        "face_name_groups": {"hangul": [{"index": 0}], "latin": [{"index": 1}]},
        "border_fills": [{"index": 0}],
        "char_shapes": [{"index": 0}],
        "tab_defs": [{"index": 0}],
        "numberings": [{"index": 0}],
        "bullets": [],
        "para_shapes": [{"index": 0}],
        "styles": [{"index": 0}],
        "counts": {
            "binary_data": 1,
            "border_fills": 1,
            "char_shapes": 1,
            "tab_defs": 1,
            "numberings": 1,
            "bullets": 0,
            "para_shapes": 1,
            "styles": 1,
        },
    }

    coverage = full.build_coverage(Counter({17: 1}), [], {"ok": True, "text": "body"}, decoded)

    assert coverage["id_mappings_coverage"]["status"] == "PASS"
    assert coverage["id_mappings_coverage"]["mismatch_count"] == 0
    assert all(row["tag_id"] != 17 for row in coverage["next_decoder_targets"])


def test_build_coverage_keeps_mismatched_id_mappings_as_next_target() -> None:
    decoded = {
        "id_mappings": {"counts": {"char_shape": 2}},
        "char_shapes": [{"index": 0}],
        "counts": {"char_shapes": 1},
    }

    coverage = full.build_coverage(Counter({17: 1}), [], {"ok": True, "text": "body"}, decoded)

    assert coverage["id_mappings_coverage"]["status"] == "PARTIAL_ID_MAPPINGS"
    assert coverage["id_mappings_coverage"]["mismatches"] == [{"key": "char_shape", "expected": 2, "actual": 1}]
    assert any(row["tag_id"] == 17 for row in coverage["next_decoder_targets"])


def test_build_coverage_treats_matched_bindata_streams_as_audited() -> None:
    coverage = full.build_coverage(
        Counter({18: 1}),
        ["BinData/BIN0001.png"],
        {"ok": True, "text": "body"},
        {"binary_data": [{"storage_id": 1, "extension": "png", "stream_name": "BinData/BIN0001.png"}]},
    )

    assert coverage["bindata_stream_coverage"]["status"] == "PASS"
    assert coverage["bindata_stream_coverage"]["matched_stream_count"] == 1
    assert "BINDATA_STREAMS_PRESENT" not in coverage["blockers"]
    assert all(row["tag_id"] != 18 for row in coverage["next_decoder_targets"])


def test_build_coverage_keeps_unmatched_bindata_streams_as_next_target() -> None:
    coverage = full.build_coverage(
        Counter({18: 1}),
        ["BinData/BIN0002.png"],
        {"ok": True, "text": "body"},
        {"binary_data": [{"storage_id": 1, "extension": "png", "stream_name": "BinData/BIN0001.png"}]},
    )

    assert coverage["bindata_stream_coverage"]["status"] == "PARTIAL_RECORD_STREAM_MISMATCH"
    assert coverage["bindata_stream_coverage"]["missing_docinfo_streams"] == ["BinData/BIN0002.png"]
    assert "BINDATA_STREAMS_PRESENT" in coverage["blockers"]
    assert any(row["tag_id"] == 18 for row in coverage["next_decoder_targets"])


def test_docinfo_groups_face_names_by_id_mapping_language_slots() -> None:
    records = [
        {
            "tag_id": 17,
            "decoded": {
                "counts": {
                    "binary_data": 0,
                    "hangul_font": 2,
                    "latin_font": 1,
                    "hanja_font": 0,
                    "japanese_font": 0,
                    "other_font": 0,
                    "symbol_font": 0,
                    "user_font": 0,
                }
            },
        },
        {"tag_id": 19, "decoded": {"name": "HangulA"}},
        {"tag_id": 19, "decoded": {"name": "HangulB"}},
        {"tag_id": 19, "decoded": {"name": "LatinA"}},
    ]

    decoded = full.build_decoded_docinfo(records)
    mapping = full.build_fontface_mapping(decoded)
    coverage = full.build_coverage(Counter({17: 1, 19: 3}), [], {"ok": True, "text": "body"}, decoded)

    assert [row["name"] for row in decoded["face_name_groups"]["hangul"]] == ["HangulA", "HangulB"]
    assert [row["name"] for row in decoded["face_name_groups"]["latin"]] == ["LatinA"]
    assert decoded["face_name_groups"]["latin"][0]["language_index"] == 0
    assert mapping["status"] == "PASS"
    assert coverage["fontface_coverage"]["status"] == "PASS"
    assert all(row["tag_id"] != 19 for row in coverage["next_decoder_targets"])


def test_build_coverage_treats_resolved_para_shape_refs_as_audited() -> None:
    decoded = {
        "id_mappings": {"counts": {"para_shape": 2}},
        "para_shapes": [{"index": 0}, {"index": 1}],
    }
    body_layout = {
        "sections": [
            {
                "paragraphs": [
                    {"has_para_text": True, "para_shape_id": 0},
                    {"has_para_text": True, "para_shape_id": 1},
                ]
            }
        ]
    }

    coverage = full.build_coverage(Counter({25: 2, 66: 2}), [], {"ok": True, "text": "body"}, decoded, body_layout)

    assert coverage["para_shape_coverage"]["status"] == "PASS"
    assert coverage["para_shape_coverage"]["resolved_ref_count"] == 2
    assert coverage["para_shape_coverage"]["unresolved_ref_count"] == 0
    assert all(row["tag_id"] != 25 for row in coverage["next_decoder_targets"])


def test_build_coverage_keeps_unresolved_para_shape_refs_as_next_target() -> None:
    decoded = {
        "id_mappings": {"counts": {"para_shape": 1}},
        "para_shapes": [{"index": 0}],
    }
    body_layout = {"sections": [{"paragraphs": [{"has_para_text": True, "para_shape_id": 3}]}]}

    coverage = full.build_coverage(Counter({25: 1, 66: 1}), [], {"ok": True, "text": "body"}, decoded, body_layout)

    assert coverage["para_shape_coverage"]["status"] == "PARTIAL_PARA_SHAPE_MAPPING"
    assert coverage["para_shape_coverage"]["unresolved_refs"] == [{"paragraph_index": 0, "para_shape_id": 3}]
    assert any(row["tag_id"] == 25 for row in coverage["next_decoder_targets"])


def test_build_coverage_treats_resolved_char_shape_refs_as_audited() -> None:
    decoded = {
        "id_mappings": {"counts": {"char_shape": 3}},
        "char_shapes": [{"index": 0}, {"index": 1}, {"index": 2}],
    }
    body_layout = {
        "sections": [
            {
                "paragraphs": [
                    {
                        "has_para_text": True,
                        "first_char_shape_id": 0,
                        "char_shape_runs": [
                            {"start_pos": 0, "char_shape_id": 1},
                            {"start_pos": 2, "char_shape_id": 2},
                        ],
                    }
                ]
            }
        ]
    }

    coverage = full.build_coverage(Counter({21: 3, 66: 1, 68: 1}), [], {"ok": True, "text": "body"}, decoded, body_layout)

    assert coverage["char_shape_coverage"]["status"] == "PASS"
    assert coverage["char_shape_coverage"]["resolved_ref_count"] == 2
    assert coverage["char_shape_coverage"]["unresolved_ref_count"] == 0
    assert all(row["tag_id"] != 21 for row in coverage["next_decoder_targets"])


def test_build_coverage_keeps_unresolved_char_shape_refs_as_next_target() -> None:
    decoded = {
        "id_mappings": {"counts": {"char_shape": 1}},
        "char_shapes": [{"index": 0}],
    }
    body_layout = {"sections": [{"paragraphs": [{"has_para_text": True, "first_char_shape_id": 4}]}]}

    coverage = full.build_coverage(Counter({21: 1, 66: 1, 68: 1}), [], {"ok": True, "text": "body"}, decoded, body_layout)

    assert coverage["char_shape_coverage"]["status"] == "PARTIAL_CHAR_SHAPE_MAPPING"
    assert coverage["char_shape_coverage"]["unresolved_refs"] == [{"paragraph_index": 0, "char_shape_id": 4}]
    assert any(row["tag_id"] == 21 for row in coverage["next_decoder_targets"])


def test_body_style_mapping_audits_para_pr_refs_against_decoded_docinfo() -> None:
    section_xml = b'''<hp:sec xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph"><hp:p><hp:run><hp:t>body</hp:t></hp:run></hp:p></hp:sec>'''
    updates, report = full.build_body_style_section_updates(
        {"Contents/section0.xml": section_xml},
        {"sections": [{"paragraphs": [{"has_para_text": True, "para_shape_id": 1}]}]},
        {"para_shapes": [{"index": 1}]},
    )

    assert report["applied_para_pr_refs"] == 1
    assert report["unresolved_para_pr_ref_count"] == 0
    assert 'paraPrIDRef="1"' in updates["Contents/section0.xml"].decode("utf-8")


def test_body_style_mapping_audits_char_pr_refs_against_decoded_docinfo() -> None:
    section_xml = b'''<hp:sec xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph"><hp:p><hp:run><hp:t>body</hp:t></hp:run></hp:p></hp:sec>'''
    updates, report = full.build_body_style_section_updates(
        {"Contents/section0.xml": section_xml},
        {
            "sections": [
                {
                    "paragraphs": [
                        {
                            "has_para_text": True,
                            "first_char_shape_id": 1,
                            "char_shape_runs": [
                                {"start_pos": 0, "char_shape_id": 1},
                                {"start_pos": 2, "char_shape_id": 2},
                            ],
                        }
                    ]
                }
            ]
        },
        {"char_shapes": [{"index": 1}, {"index": 2}]},
    )

    section_text = updates["Contents/section0.xml"].decode("utf-8")
    assert report["applied_char_pr_refs"] == 2
    assert report["unresolved_char_pr_ref_count"] == 0
    assert 'charPrIDRef="1"' in section_text
    assert 'charPrIDRef="2"' in section_text


def test_build_coverage_treats_resolved_border_fill_refs_as_audited() -> None:
    decoded = {
        "id_mappings": {"counts": {"border_fill": 3}},
        "border_fills": [{"index": 0}, {"index": 1}, {"index": 2}],
        "char_shapes": [{"index": 0, "border_fill_id": 1}],
        "para_shapes": [{"index": 0, "border_fill_id": 2}],
    }
    page_layout = {"sections": [{"section_index": 0, "page_border_fills": [{"border_fill_id": 1}]}]}
    table_layout = {"sections": [{"section_index": 0, "tables": [{"table_index": 0, "list_headers": [{"border_fill_id": 2}]}]}]}

    coverage = full.build_coverage(Counter({20: 3}), [], {"ok": True, "text": "body"}, decoded, None, page_layout, table_layout)

    assert coverage["border_fill_coverage"]["status"] == "PASS"
    assert coverage["border_fill_coverage"]["resolved_ref_count"] == 4
    assert coverage["border_fill_coverage"]["unresolved_ref_count"] == 0
    assert all(row["tag_id"] != 20 for row in coverage["next_decoder_targets"])


def test_border_fill_audit_accepts_hwp_one_based_terminal_refs() -> None:
    decoded = {
        "id_mappings": {"counts": {"border_fill": 2}},
        "border_fills": [{"index": 0}, {"index": 1}],
        "para_shapes": [{"index": 0, "border_fill_id": 2}],
    }

    coverage = full.build_coverage(Counter({20: 2}), [], {"ok": True, "text": "body"}, decoded)
    xml_text = full.build_decoded_header_xml({**decoded, "counts": {"border_fills": 2}})

    assert coverage["border_fill_coverage"]["status"] == "PASS"
    assert 'borderFillIDRef="1"' in xml_text


def test_build_coverage_keeps_unresolved_border_fill_refs_as_next_target() -> None:
    decoded = {
        "id_mappings": {"counts": {"border_fill": 1}},
        "border_fills": [{"index": 0}],
        "para_shapes": [{"index": 0, "border_fill_id": 9}],
    }

    coverage = full.build_coverage(Counter({20: 1}), [], {"ok": True, "text": "body"}, decoded)

    assert coverage["border_fill_coverage"]["status"] == "PARTIAL_BORDER_FILL_MAPPING"
    assert coverage["border_fill_coverage"]["unresolved_refs"] == [{"source": "para_shape", "border_fill_id": 9, "record_index": 0}]
    assert any(row["tag_id"] == 20 for row in coverage["next_decoder_targets"])


def test_build_coverage_treats_resolved_pictures_as_audited() -> None:
    decoded = {
        "binary_data": [
            {"index": 0, "storage_id": 10, "extension": "png", "stream_name": "BinData/BIN000A.png"},
        ]
    }
    shape_layout = {
        "sections": [
            {
                "pictures": [
                    {
                        "record_index": 4,
                        "picture": {"binary_data_id": 10, "bbox": {"width": 3000, "height": 2000}},
                        "component": {"current_size_normalized": {"width": 3000, "height": 2000}},
                        "control": {
                            "position": {"horizontal_offset": 10, "vertical_offset": 20, "width": 3000, "height": 2000},
                            "layout": {"text_wrap": "SQUARE", "text_flow": "BOTH_SIDES"},
                        },
                    }
                ]
            }
        ]
    }

    coverage = full.build_coverage(Counter({85: 1}), ["BinData/BIN000A.png"], {"ok": True, "text": "body"}, decoded, None, None, None, shape_layout)

    assert coverage["picture_coverage"]["status"] == "PASS"
    assert coverage["picture_coverage"]["unresolved_ref_count"] == 0
    assert coverage["picture_coverage"]["geometry_mapped_count"] == 1
    assert coverage["picture_coverage"]["position_mapped_count"] == 1
    assert coverage["picture_coverage"]["layout_policy_mapped_count"] == 1
    assert all(row["tag_id"] != 85 for row in coverage["next_decoder_targets"])


def test_build_coverage_keeps_unresolved_pictures_as_next_target() -> None:
    shape_layout = {
        "sections": [
            {
                "pictures": [
                    {
                        "record_index": 4,
                        "picture": {"binary_data_id": 99, "bbox": {"width": 3000, "height": 2000}},
                        "control": {"position": {"width": 3000, "height": 2000}},
                    }
                ]
            }
        ]
    }

    coverage = full.build_coverage(Counter({85: 1}), ["BinData/BIN0001.png"], {"ok": True, "text": "body"}, {}, None, None, None, shape_layout)

    assert coverage["picture_coverage"]["status"] == "PARTIAL_PICTURE_MAPPING"
    assert coverage["picture_coverage"]["unresolved_ref_count"] == 1
    assert coverage["picture_coverage"]["missing_layout_policy_count"] == 1
    assert any(row["tag_id"] == 85 for row in coverage["next_decoder_targets"])


def test_build_coverage_treats_decoded_table_shapes_as_audited() -> None:
    table_layout = {
        "sections": [
            {
                "section_index": 0,
                "tables": [
                    {
                        "table_index": 0,
                        "record_index": 2,
                        "table": {"row_count": 2, "col_count": 3, "row_cell_counts": [3, 2]},
                        "list_headers": [{"record_index": 3}, {"record_index": 4}],
                        "mapped_list_header_count": 2,
                    }
                ],
            }
        ]
    }

    coverage = full.build_coverage(Counter({77: 1}), [], {"ok": True, "text": "body"}, None, None, None, table_layout)

    assert coverage["table_coverage"]["status"] == "PASS"
    assert coverage["table_coverage"]["table_record_count"] == 1
    assert coverage["table_coverage"]["mapped_table_count"] == 1
    assert coverage["table_coverage"]["invalid_row_cell_count"] == 0
    assert all(row["tag_id"] != 77 for row in coverage["next_decoder_targets"])


def test_build_coverage_keeps_invalid_table_shapes_as_next_target() -> None:
    table_layout = {
        "sections": [
            {
                "section_index": 0,
                "tables": [
                    {
                        "table_index": 0,
                        "record_index": 2,
                        "table": {"row_count": 2, "col_count": 3, "row_cell_counts": [3]},
                    }
                ],
            }
        ]
    }

    coverage = full.build_coverage(Counter({77: 1}), [], {"ok": True, "text": "body"}, None, None, None, table_layout)

    assert coverage["table_coverage"]["status"] == "PARTIAL_TABLE_MAPPING"
    assert coverage["table_coverage"]["invalid_row_cell_count"] == 1
    assert any(row["tag_id"] == 77 for row in coverage["next_decoder_targets"])


def test_build_coverage_audits_table_shape_and_binary_families_together() -> None:
    decoded = {
        "binary_data": [{"index": 0, "storage_id": 1, "extension": "png", "stream_name": "BinData/BIN0001.png"}],
    }
    table_layout = {
        "sections": [
            {
                "section_index": 0,
                "tables": [
                    {
                        "table_index": 0,
                        "record_index": 2,
                        "table": {"row_count": 1, "col_count": 1, "row_cell_counts": [1]},
                        "list_headers": [{"record_index": 3}],
                        "mapped_list_header_count": 1,
                    }
                ],
            }
        ]
    }
    shape_layout = {
        "shape_component_count": 2,
        "rectangle_count": 1,
        "picture_count": 1,
        "sections": [
            {
                "components": [
                    {"record_index": 4, "component": {"current_size_normalized": {"width": 100, "height": 100}}},
                    {"record_index": 6, "component": {"current_size_normalized": {"width": 300, "height": 200}}},
                ],
                "rectangles": [
                    {
                        "record_index": 5,
                        "rectangle": {"bbox": {"width": 100, "height": 100}},
                        "component": {"current_size_normalized": {"width": 100, "height": 100}},
                        "control": {"position": {"width": 100, "height": 100}, "layout": {"text_wrap": "SQUARE"}},
                    }
                ],
                "pictures": [
                    {
                        "record_index": 7,
                        "picture": {"binary_data_id": 1, "bbox": {"width": 300, "height": 200}},
                        "component": {"current_size_normalized": {"width": 300, "height": 200}},
                        "control": {"position": {"width": 300, "height": 200}, "layout": {"text_wrap": "SQUARE"}},
                    }
                ],
            }
        ],
    }

    coverage = full.build_coverage(
        Counter({18: 1, 76: 2, 77: 1, 79: 1, 85: 1}),
        ["BinData/BIN0001.png"],
        {"ok": True, "text": "body"},
        decoded,
        None,
        None,
        table_layout,
        shape_layout,
    )

    family_status = {row["family"]: row["status"] for row in coverage["required_families"]}
    assert family_status["tables"] == "AUDITED"
    assert family_status["drawings_and_shapes"] == "AUDITED"
    assert family_status["binary_objects"] == "AUDITED"
    assert coverage["shape_coverage"]["status"] == "PASS"
    assert coverage["binary_object_coverage"]["status"] == "PASS"
    assert "PARTIAL:tables" not in coverage["blockers"]
    assert "PARTIAL:drawings_and_shapes" not in coverage["blockers"]
    assert "PARTIAL:binary_objects" not in coverage["blockers"]


def test_build_coverage_treats_resolved_numberings_as_audited() -> None:
    decoded = {
        "id_mappings": {"counts": {"numbering": 1, "bullet": 0}},
        "numberings": [{"index": 0, "levels": [{"level": 1}, {"level": 2}]}],
        "bullets": [],
        "para_shapes": [{"index": 0, "heading_type": 1, "level": 1, "numbering_bullet_id": 0}],
    }

    coverage = full.build_coverage(Counter({23: 1}), [], {"ok": True, "text": "body"}, decoded)

    assert coverage["numbering_coverage"]["status"] == "PASS"
    assert coverage["numbering_coverage"]["applied_para_shape_count"] == 1
    assert coverage["numbering_coverage"]["unresolved_ref_count"] == 0
    assert all(row["tag_id"] != 23 for row in coverage["next_decoder_targets"])


def test_build_coverage_keeps_unresolved_numberings_as_next_target() -> None:
    decoded = {
        "id_mappings": {"counts": {"numbering": 1}},
        "numberings": [{"index": 0, "levels": [{"level": 1}]}],
        "para_shapes": [{"index": 0, "heading_type": 1, "level": 3, "numbering_bullet_id": 2}],
    }

    coverage = full.build_coverage(Counter({23: 1}), [], {"ok": True, "text": "body"}, decoded)

    assert coverage["numbering_coverage"]["status"] == "PARTIAL_NUMBERING_MAPPING"
    assert coverage["numbering_coverage"]["unresolved_ref_count"] == 1
    assert any(row["tag_id"] == 23 for row in coverage["next_decoder_targets"])


def test_build_coverage_audits_style_paragraph_and_page_families_together() -> None:
    decoded = {
        "id_mappings": {
            "counts": {
                "hangul_font": 1,
                "latin_font": 0,
                "hanja_font": 0,
                "japanese_font": 0,
                "other_font": 0,
                "symbol_font": 0,
                "user_font": 0,
                "border_fill": 1,
                "char_shape": 1,
                "para_shape": 1,
                "style": 1,
                "numbering": 0,
                "bullet": 0,
            }
        },
        "face_names": [{"index": 0, "name": "Base"}],
        "face_name_groups": {"hangul": [{"index": 0}]},
        "border_fills": [{"index": 0}],
        "char_shapes": [{"index": 0}],
        "para_shapes": [{"index": 0, "border_fill_id": 0}],
        "styles": [{"index": 0}],
    }
    body_layout = {
        "paragraph_count": 1,
        "text_paragraph_count": 1,
        "sections": [
            {
                "paragraphs": [
                    {
                        "has_para_text": True,
                        "para_shape_id": 0,
                        "style_id": 0,
                        "first_char_shape_id": 0,
                        "char_shape_runs": [{"start_pos": 0, "char_shape_id": 0}],
                        "line_segments": [{"text_pos": 0}],
                    }
                ]
            }
        ],
    }
    page_layout = {
        "mapped_page_definition_count": 1,
        "sections": [
            {
                "section_index": 0,
                "page_definition_count": 1,
                "page_border_fill_count": 1,
                "footnote_shape_count": 0,
                "ctrl_header_count": 1,
                "list_header_count": 1,
                "page_definition": {"width": 100, "height": 200},
                "page_border_fills": [{"border_fill_id": 0}],
            }
        ],
    }

    coverage = full.build_coverage(
        Counter({19: 1, 20: 1, 21: 1, 25: 1, 26: 1, 66: 1, 67: 1, 68: 1, 69: 1, 71: 1, 72: 1, 73: 1, 75: 1}),
        [],
        {"ok": True, "text": "body"},
        decoded,
        body_layout,
        page_layout,
    )

    family_status = {row["family"]: row["status"] for row in coverage["required_families"]}
    assert family_status["fonts_and_styles"] == "AUDITED"
    assert family_status["paragraph_layout"] == "AUDITED"
    assert family_status["controls_and_page"] == "AUDITED"
    assert coverage["style_coverage"]["status"] == "PASS"
    assert coverage["paragraph_layout_coverage"]["status"] == "PASS"
    assert coverage["controls_page_coverage"]["status"] == "PASS"
    assert "PARTIAL:fonts_and_styles" not in coverage["blockers"]
    assert "PARTIAL:paragraph_layout" not in coverage["blockers"]
    assert "PARTIAL:controls_and_page" not in coverage["blockers"]


def test_decode_eqedit_extracts_formula_text() -> None:
    formula = "`=`51.1 root {3} of {N}"
    version = "Equation Version 60"
    app = "HYhwpEQ"
    payload = (
        b"\x00\x00\x00\x00"
        + len(formula).to_bytes(2, "little")
        + b"\x44\x00"
        + formula.encode("utf-16le")
        + bytes.fromhex("14 05 00 00 00 00 00 00 57 00 00 00")
        + len(version).to_bytes(2, "little")
        + version.encode("utf-16le")
        + len(app).to_bytes(2, "little")
        + app.encode("utf-16le")
    )

    decoded = full.decode_known_record(88, payload)

    assert decoded["formula"] == formula
    assert decoded["version"] == version
    assert decoded["application"] == app


def test_build_coverage_treats_preserved_eqedit_as_audited() -> None:
    equation_layout = {
        "sections": [
            {
                "section_index": 0,
                "equations": [
                    {
                        "record_index": 7,
                        "formula": "`=`51.1 root {3} of {N}",
                        "version": "Equation Version 60",
                        "application": "HYhwpEQ",
                        "payload_size": 122,
                    }
                ],
            }
        ]
    }

    coverage = full.build_coverage(Counter({88: 1}), [], {"ok": True, "text": "body"}, None, None, None, None, None, equation_layout)

    assert coverage["equation_coverage"]["status"] == "PASS"
    assert coverage["equation_coverage"]["preserved_equation_count"] == 1
    assert all(row["tag_id"] != 88 for row in coverage["next_decoder_targets"])


def test_build_coverage_keeps_unpreserved_eqedit_as_next_target() -> None:
    equation_layout = {"sections": [{"section_index": 0, "equations": [{"record_index": 7, "formula": "", "payload_size": 122}]}]}

    coverage = full.build_coverage(Counter({88: 1}), [], {"ok": True, "text": "body"}, None, None, None, None, None, equation_layout)

    assert coverage["equation_coverage"]["status"] == "PARTIAL_EQUATION_MAPPING"
    assert coverage["equation_coverage"]["missing_formula_count"] == 1
    assert any(row["tag_id"] == 88 for row in coverage["next_decoder_targets"])


def test_page_and_table_mapping_audit_border_fill_refs_against_decoded_docinfo() -> None:
    page_xml = b'''<hp:sec xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph"><hp:p><hp:run><hp:t>body</hp:t></hp:run></hp:p></hp:sec>'''
    table_xml = b'''<hp:sec xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph"><hp:p><hp:run><hp:tbl rowCnt="1" colCnt="1"><hp:tr><hp:tc><hp:subList textWidth="0" textHeight="0" /><hp:cellMargin left="0" right="0" top="0" bottom="0" /></hp:tc></hp:tr></hp:tbl></hp:run></hp:p></hp:sec>'''
    decoded = {"border_fills": [{"index": 4}, {"index": 7}]}

    _updates, page_report = full.build_page_layout_section_updates(
        {"Contents/section0.xml": page_xml},
        {
            "sections": [
                {
                    "section_index": 0,
                    "page_definition": {"width": 100, "height": 200, "margins": {}},
                    "page_border_fills": [{"border_fill_id": 4}],
                }
            ]
        },
        decoded,
    )
    _updates, table_report = full.build_table_layout_section_updates(
        {"Contents/section0.xml": table_xml},
        {
            "sections": [
                {
                    "section_index": 0,
                    "tables": [
                        {
                            "table": {"row_count": 1, "col_count": 1, "row_cell_counts": [1]},
                            "list_headers": [{"border_fill_id": 7}],
                        }
                    ],
                }
            ]
        },
        decoded,
    )

    assert page_report["applied_page_border_fill_count"] == 1
    assert page_report["unresolved_page_border_fill_ref_count"] == 0
    assert table_report["applied_cell_borders"] == 1
    assert table_report["unresolved_cell_border_ref_count"] == 0


def test_table_mapping_skips_out_of_range_cell_border_refs() -> None:
    table_xml = b'''<hp:sec xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph"><hp:p><hp:run><hp:tbl rowCnt="1" colCnt="1"><hp:tr><hp:tc><hp:subList textWidth="0" textHeight="0" /><hp:cellMargin left="0" right="0" top="0" bottom="0" /></hp:tc></hp:tr></hp:tbl></hp:run></hp:p></hp:sec>'''

    updates, report = full.build_table_layout_section_updates(
        {"Contents/section0.xml": table_xml},
        {
            "sections": [
                {
                    "section_index": 0,
                    "tables": [
                        {
                            "table": {"row_count": 1, "col_count": 1, "row_cell_counts": [1]},
                            "list_headers": [{"cell_addr": {"row": 99, "col": 99}, "cell_span": {"row": 1, "col": 1}, "border_fill_id": 7167}],
                        }
                    ],
                }
            ]
        },
        {"border_fills": [{"index": 0}]},
    )

    section_text = updates["Contents/section0.xml"].decode("utf-8")
    assert report["applied_cell_borders"] == 0
    assert report["unresolved_cell_border_ref_count"] == 0
    assert "7167" not in section_text


def test_docinfo_decoders_parse_core_records() -> None:
    doc_props = (
        (2).to_bytes(2, "little")
        + (1).to_bytes(2, "little")
        + (3).to_bytes(2, "little")
        + (4).to_bytes(2, "little")
        + (5).to_bytes(2, "little")
        + (6).to_bytes(2, "little")
        + (7).to_bytes(2, "little")
        + (8).to_bytes(4, "little")
        + (9).to_bytes(4, "little")
        + (10).to_bytes(4, "little")
    )
    mappings = b"".join(index.to_bytes(4, "little", signed=True) for index in range(18))
    char_shape = (
        b"".join(index.to_bytes(2, "little") for index in range(7))
        + bytes([100] * 7)
        + bytes([0] * 7)
        + bytes([100] * 7)
        + bytes([0] * 7)
        + (1000).to_bytes(4, "little", signed=True)
        + (0x2).to_bytes(4, "little")
        + bytes([0, 0])
        + bytes.fromhex("11 22 33 00") * 4
        + (1).to_bytes(2, "little")
    )
    para_shape = (
        (0x4).to_bytes(4, "little")
        + (1).to_bytes(4, "little", signed=True) * 5
        + (160).to_bytes(4, "little", signed=True)
        + (0).to_bytes(2, "little") * 3
        + (0).to_bytes(2, "little", signed=True) * 4
        + (0).to_bytes(4, "little")
        + (0).to_bytes(4, "little")
        + (160).to_bytes(4, "little", signed=True)
    )
    numbering_level = (
        (8).to_bytes(4, "little")
        + (0).to_bytes(2, "little")
        + (50).to_bytes(2, "little")
        + (0xFFFFFFFF).to_bytes(4, "little")
        + (3).to_bytes(2, "little")
        + "^1.".encode("utf-16le")
    )
    bullet = (1).to_bytes(4, "little") + (7).to_bytes(4, "little") + (1).to_bytes(2, "little") + "-".encode("utf-16le")

    assert full.decode_document_properties(doc_props)["section_count"] == 2
    assert full.decode_id_mappings(mappings)["counts"]["style"] == 14
    binary_data = full.decode_binary_data(
        (0x0111).to_bytes(2, "little")
        + (7).to_bytes(2, "little")
        + (3).to_bytes(2, "little")
        + "png".encode("utf-16le")
    )
    assert binary_data["data_type"] == "EMBEDDING"
    assert binary_data["compression"] == "COMPRESS"
    assert binary_data["state"] == "ACCESS_SUCCESS"
    assert binary_data["storage_id"] == 7
    assert binary_data["extension"] == "png"
    assert binary_data["stream_name"] == "BinData/BIN0007.png"
    assert binary_data["manifest_id"] == "BIN0007"
    face_name = full.decode_face_name(
        bytes([0xE0])
        + (4).to_bytes(2, "little")
        + "Main".encode("utf-16le")
        + bytes([1])
        + (3).to_bytes(2, "little")
        + "Alt".encode("utf-16le")
        + bytes([0, 1, 2, 3, 0, 0, 0, 0, 0, 0])
        + (4).to_bytes(2, "little")
        + "Base".encode("utf-16le")
    )
    assert face_name["name"] == "Main"
    assert face_name["alternate_type_name"] == "TTF"
    assert face_name["alternate_name"] == "Alt"
    assert face_name["type_info_names"][:4] == ["UNKNOWN", "TTF", "HFT", "BOTH"]
    assert face_name["font_type"] == "TTF"
    assert face_name["base_font"] == "Base"
    assert full.decode_char_shape(char_shape)["bold"] is True
    assert full.decode_char_shape(char_shape)["text_color"]["hex"] == "#112233"
    assert full.decode_numbering(numbering_level * 7)["levels"][0]["text"] == "^1."
    assert full.decode_numbering(numbering_level * 7)["level_count"] == 7
    assert full.decode_bullet(bullet)["bullet_char"] == "-"
    border_fill = full.decode_border_fill(
        ((1 << 0) | (1 << 1) | (2 << 2) | (7 << 5) | (1 << 8) | (1 << 10) | (1 << 11) | (1 << 12)).to_bytes(2, "little")
        + bytes([0, 2, 7, 10])
        + bytes([0, 1, 10, 15])
        + bytes.fromhex("11 11 11 00 22 22 22 00 33 33 33 00 44 44 44 00")
        + bytes([2, 3])
        + bytes.fromhex("55 55 55 00")
        + (1).to_bytes(4, "little")
        + bytes.fromhex("aa aa aa 00 bb bb bb 00")
        + (5).to_bytes(4, "little", signed=True)
        + (0).to_bytes(4, "little")
    )
    assert border_fill["three_d"] is True
    assert border_fill["shadow"] is True
    assert border_fill["borders"]["left"]["type"] == "SOLID"
    assert border_fill["borders"]["right"]["type"] == "DASH"
    assert border_fill["borders"]["top"]["type"] == "DOUBLE_SLIM"
    assert border_fill["borders"]["bottom"]["width"] == "5.0 mm"
    assert border_fill["slash"]["type"] == "CENTER"
    assert border_fill["back_slash"]["type"] == "ALL"
    assert border_fill["diagonal_type_name"] == "DASH"
    assert border_fill["diagonal_width_name"] == "0.2 mm"
    assert border_fill["fill"]["solid"]["pattern_name"] == "CROSS"
    assert full.decode_para_shape(para_shape)["align"] == 1
    assert full.decode_para_header((3).to_bytes(4, "little") + b"\x00" * 4 + (2).to_bytes(2, "little") + bytes([1, 0]) + (1).to_bytes(2, "little") + b"\x00" * 8)["para_shape_id"] == 2
    ctrl_properties = 1 | (2 << 3) | (2 << 8) | (1 << 14) | (5 << 21) | (2 << 24)
    ctrl_header = full.decode_ctrl_header(
        b" gso"
        + ctrl_properties.to_bytes(4, "little")
        + (200).to_bytes(4, "little", signed=True)
        + (100).to_bytes(4, "little", signed=True)
        + (3000).to_bytes(4, "little", signed=True)
        + (2000).to_bytes(4, "little", signed=True)
        + (7).to_bytes(4, "little", signed=True)
        + (10).to_bytes(2, "little") * 4
        + (99).to_bytes(4, "little")
    )
    assert ctrl_header["position"]["horizontal_offset"] == 100
    assert ctrl_header["position"]["vertical_offset"] == 200
    assert ctrl_header["position"]["width"] == 3000
    assert ctrl_header["position"]["height"] == 2000
    assert ctrl_header["layout"]["treat_as_char"] is True
    assert ctrl_header["layout"]["allow_overlap"] is True
    assert ctrl_header["layout"]["vert_rel_to"] == "PARA"
    assert ctrl_header["layout"]["horz_rel_to"] == "COLUMN"
    assert ctrl_header["layout"]["raw_text_wrap"] == "IN_FRONT_OF_TEXT"
    assert ctrl_header["layout"]["text_wrap"] == "TOP_AND_BOTTOM"
    assert ctrl_header["layout"]["text_flow"] == "RIGHT_ONLY"
    assert full.decode_para_char_shape((0).to_bytes(4, "little") + (7).to_bytes(4, "little"))["first_char_shape_id"] == 7
    list_header = full.decode_list_header(
        (1).to_bytes(4, "little")
        + (32).to_bytes(4, "little")
        + (2).to_bytes(2, "little")
        + (3).to_bytes(2, "little")
        + (4).to_bytes(2, "little")
        + (1).to_bytes(2, "little")
        + (1200).to_bytes(4, "little", signed=True)
        + (800).to_bytes(4, "little", signed=True)
        + (10).to_bytes(2, "little", signed=True) * 4
        + (9).to_bytes(2, "little")
    )
    assert list_header["cell_addr"] == {"col": 2, "row": 3}
    assert list_header["cell_span"] == {"col": 4, "row": 1}
    assert list_header["border_fill_id"] == 9
    page_def = full.decode_page_def(
        (59528).to_bytes(4, "little", signed=True)
        + (84188).to_bytes(4, "little", signed=True)
        + (5669).to_bytes(4, "little", signed=True) * 3
        + (2834).to_bytes(4, "little", signed=True)
        + (0).to_bytes(4, "little", signed=True) * 4
    )
    assert page_def["orientation"] == "portrait"
    assert page_def["margins"]["left"] == 5669
    page_border_fill = full.decode_page_border_fill(
        (0x7).to_bytes(4, "little")
        + (2).to_bytes(2, "little")
        + (1417).to_bytes(4, "little", signed=True)
        + (1418).to_bytes(4, "little", signed=True)
        + (1419).to_bytes(4, "little", signed=True)
        + (1420).to_bytes(4, "little", signed=True)
    )
    assert page_border_fill["border_fill_id"] == 2
    assert page_border_fill["text_border"] == "CONTENT"
    assert page_border_fill["header_inside"] is True
    assert page_border_fill["footer_inside"] is True
    assert page_border_fill["margins"]["bottom"] == 1420
    footnote_shape = full.decode_footnote_shape(
        ((2 << 10) | (1 << 12) | (1 << 13)).to_bytes(4, "little")
        + "*".encode("utf-16le")
        + "[".encode("utf-16le")
        + "]".encode("utf-16le")
        + (3).to_bytes(2, "little")
        + (100).to_bytes(2, "little")
        + (20).to_bytes(2, "little")
        + (30).to_bytes(2, "little")
        + (40).to_bytes(2, "little")
        + bytes([2, 3])
        + bytes.fromhex("11 22 33 00")
    )
    assert footnote_shape["number_format"] == "DIGIT"
    assert footnote_shape["numbering_type"] == "ON_PAGE"
    assert footnote_shape["superscript"] is True
    assert footnote_shape["beneath_text"] is True
    assert footnote_shape["user_char"] == "*"
    assert footnote_shape["prefix_char"] == "["
    assert footnote_shape["suffix_char"] == "]"
    assert footnote_shape["start_number"] == 3
    assert footnote_shape["space_between"] == 40
    assert footnote_shape["separator_line_type"] == "DASH"
    assert footnote_shape["separator_line_width"] == "0.2 mm"
    assert footnote_shape["separator_line_color"]["hex"] == "#112233"
    table = full.decode_table(
        (0).to_bytes(4, "little")
        + (2).to_bytes(2, "little")
        + (3).to_bytes(2, "little")
        + (0).to_bytes(2, "little")
        + (141).to_bytes(2, "little", signed=True) * 4
        + (1).to_bytes(2, "little")
        + (2).to_bytes(2, "little")
        + (99).to_bytes(2, "little")
    )
    assert table["row_count"] == 2
    assert table["col_count"] == 3
    assert table["cell_count_capacity"] == 6
    assert table["row_cell_counts"] == [1, 2]
    assert table["row_cell_count_total"] == 3
    assert table["table_zone_u16"] == [99]
    rectangle = full.decode_shape_component_rectangle(
        bytes([12])
        + (0).to_bytes(4, "little", signed=True)
        + (0).to_bytes(4, "little", signed=True)
        + (2000).to_bytes(4, "little", signed=True)
        + (0).to_bytes(4, "little", signed=True)
        + (2000).to_bytes(4, "little", signed=True)
        + (1000).to_bytes(4, "little", signed=True)
        + (0).to_bytes(4, "little", signed=True)
        + (1000).to_bytes(4, "little", signed=True)
    )
    assert rectangle["round_ratio"] == 12
    assert rectangle["bbox"] == {"left": 0, "top": 0, "right": 2000, "bottom": 1000, "width": 2000, "height": 1000}
    fixed_point_rectangle = full.decode_shape_component_rectangle(
        bytes([0])
        + (0).to_bytes(4, "little", signed=True)
        + (0).to_bytes(4, "little", signed=True)
        + (2000 * 256).to_bytes(4, "little", signed=True)
        + (0).to_bytes(4, "little", signed=True)
        + (2000 * 256).to_bytes(4, "little", signed=True)
        + (1000 * 256).to_bytes(4, "little", signed=True)
        + (0).to_bytes(4, "little", signed=True)
        + (1000 * 256).to_bytes(4, "little", signed=True)
    )
    assert fixed_point_rectangle["bbox"]["width"] == 2000
    assert fixed_point_rectangle["bbox"]["height"] == 1000
    picture = full.decode_picture(
        (0).to_bytes(4, "little")
        + (0).to_bytes(4, "little", signed=True)
        + (0).to_bytes(4, "little")
        + (0).to_bytes(4, "little", signed=True)
        + (0).to_bytes(4, "little", signed=True)
        + (3000).to_bytes(4, "little", signed=True)
        + (0).to_bytes(4, "little", signed=True)
        + (3000).to_bytes(4, "little", signed=True)
        + (2000).to_bytes(4, "little", signed=True)
        + (0).to_bytes(4, "little", signed=True)
        + (2000).to_bytes(4, "little", signed=True)
        + (0).to_bytes(4, "little", signed=True) * 4
        + (0).to_bytes(2, "little") * 4
        + bytes([0, 0, 0])
        + (7).to_bytes(2, "little")
        + bytes([0])
    )
    assert picture["binary_data_id"] == 7
    assert picture["bbox"]["width"] == 3000
    assert picture["bbox"]["height"] == 2000


def test_build_record_audit_tracks_unknown_and_risk_record_samples() -> None:
    audit = full.build_record_audit(
        [
            {
                "index": 0,
                "tag_id": 999,
                "tag_name": "UNKNOWN_999",
                "level": 0,
                "payload_size": 3,
                "payload_prefix_hex": "01 02 03",
            }
        ],
        {
            "BodyText/Section0": [
                {
                    "index": 1,
                    "tag_id": 71,
                    "tag_name": "CTRL_HEADER",
                    "level": 1,
                    "payload_size": 8,
                    "payload_prefix_hex": "aa bb cc dd",
                    "decoded": {"ctrl_id": "tbl "},
                }
            ]
        },
        ["BinData/BIN0001.jpg"],
    )

    assert audit["status"] == "PASS"
    assert audit["record_count"] == 2
    assert audit["unknown_tag_count"] == 1
    assert audit["unknown_tags"][0]["tag_id"] == 999
    assert audit["unknown_tags"][0]["samples"][0]["stream"] == "DocInfo"
    assert audit["unknown_tags"][0]["samples"][0]["payload_prefix_hex"] == "01 02 03"
    assert audit["risk_tag_count"] == 2
    assert [row["tag_id"] for row in audit["risk_tags"]] == [71, 999]
    assert audit["risk_tags"][0]["samples"][0]["decoded_keys"] == ["ctrl_id"]
    assert audit["bindata_stream_count"] == 1


def test_build_source_manifest_hashes_ole_streams() -> None:
    class FakeOle:
        def __init__(self) -> None:
            self.data = {
                "FileHeader": b"header",
                "BodyText/Section0": b"body",
                "BinData/BIN0001.png": b"image",
            }

        def listdir(self, streams: bool = True, storages: bool = False) -> list[list[str]]:
            if storages:
                return [["BodyText"], ["BinData"]]
            if streams:
                return [name.split("/") for name in self.data]
            return []

        def openstream(self, name: str) -> BytesIO:
            return BytesIO(self.data[name])

    manifest = full.build_source_manifest(
        FakeOle(),
        {"path": "source.hwp", "sha256": "source-sha"},
        ["FileHeader", "BodyText/Section0", "BinData/BIN0001.png"],
    )

    assert manifest["status"] == "PASS"
    assert manifest["stream_count"] == 3
    assert manifest["hashed_stream_count"] == 3
    assert manifest["storage_count"] == 2
    assert manifest["streams"][0]["kind"] == "header"
    assert manifest["streams"][1]["kind"] == "body_text"
    assert manifest["streams"][2]["kind"] == "binary_data"
    assert manifest["streams"][1]["sha256"] == "230d8358dc8e8890b4c58deeb62912ee2f20357ae92a5cc861b98e68fe31acb5"
    assert manifest["unreadable_stream_count"] == 0


def test_build_original_integrity_verifies_embedded_original() -> None:
    integrity = full.build_original_integrity(
        Path("renamed.hwpx"),
        {"Original/original.hwp": b"fake"},
        {
            "input_info": {
                "path": "source.hwp",
                "size": 4,
                "sha256": "b5d54c39e66671c9731b9f471e585d8262cd4f54963f0c93082d8dcf334d4c78",
            }
        },
    )

    assert integrity["status"] == "PASS"
    assert integrity["byte_exact_original_embedded"] is True
    assert integrity["sha256_match"] is True
    assert integrity["size_match"] is True
    assert integrity["file_name_changed"] is True
    assert integrity["source_file_name"] == "source.hwp"
    assert integrity["package_file_name"] == "renamed.hwpx"


def test_copy_bindata_report_matches_docinfo_records(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "source.hwp"
    source.write_bytes(b"fake-hwp")

    class FakeOle:
        def __init__(self, _path: str) -> None:
            self.data = {
                "BinData/BIN0001.png": b"png",
                "BinData/BIN0002.gif": b"gif",
            }

        def __enter__(self) -> "FakeOle":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def listdir(self, streams: bool = True, storages: bool = False) -> list[list[str]]:
            if streams:
                return [name.split("/") for name in self.data]
            return []

        def openstream(self, name: str) -> BytesIO:
            return BytesIO(self.data[name])

    monkeypatch.setattr(full_package.olefile, "OleFileIO", FakeOle)

    updates, report = full_package._copy_bindata_from_source(
        source,
        {
            "binary_data": [
                {"index": 0, "data_type": "EMBEDDING", "storage_id": 1, "extension": "png", "stream_name": "BinData/BIN0001.png"},
                {"index": 1, "data_type": "EMBEDDING", "storage_id": 2, "extension": "gif", "stream_name": "BinData/BIN0002.gif"},
            ]
        },
    )

    assert report["status"] == "PASS"
    assert report["bindata_count"] == 2
    assert report["docinfo_binary_data_count"] == 2
    assert report["docinfo_matched_count"] == 2
    assert report["missing_docinfo_stream_count"] == 0
    assert report["items"][0]["manifest_id"] == "BIN0001"
    assert report["items"][0]["docinfo"]["storage_id"] == 1
    assert updates["BinData/BIN0001.png"] == b"png"


def test_visual_section_updates_emit_all_bindata_images_as_pictures() -> None:
    section_xml = b'''<hs:sec xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph" xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section"><hp:p id="0"><hp:run><hp:t>body</hp:t></hp:run></hp:p></hs:sec>'''

    updates, report = full_package.build_visual_section_updates(
        {"Contents/section0.xml": section_xml},
        {
            "status": "PASS",
            "bindata_count": 2,
            "items": [
                {"entry": "BinData/BIN0001.png", "size": 3, "sha256": "a", "media_type": "image/png"},
                {"entry": "BinData/BIN0002.gif", "size": 4, "sha256": "b", "media_type": "image/gif"},
            ],
        },
        {"record_counts": {"85": 2}},
    )

    xml_text = updates["Contents/section0.xml"].decode("utf-8")
    assert report["status"] == "PASS"
    assert report["image_bindata_count"] == 2
    assert report["target_picture_count"] == 2
    assert report["visible_picture_count"] == 2
    assert report["picture_record_count"] == 2
    assert xml_text.count("<hp:pic") == 2
    assert 'binaryItemIDRef="BIN0001"' in xml_text
    assert 'binaryItemIDRef="BIN0002"' in xml_text


def test_visual_section_updates_reuses_bindata_to_cover_picture_records() -> None:
    section_xml = b'''<hs:sec xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph" xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section"><hp:p id="0"><hp:run><hp:t>body</hp:t></hp:run></hp:p></hs:sec>'''

    updates, report = full_package.build_visual_section_updates(
        {"Contents/section0.xml": section_xml},
        {
            "status": "PASS",
            "bindata_count": 1,
            "items": [{"entry": "BinData/BIN0001.png", "size": 3, "sha256": "a", "media_type": "image/png"}],
        },
        {"record_counts": {"85": 3}},
    )

    xml_text = updates["Contents/section0.xml"].decode("utf-8")
    assert report["target_picture_count"] == 3
    assert report["visible_picture_count"] == 3
    assert report["items"][2]["reused_bindata"] is True
    assert xml_text.count("<hp:pic") == 3


def test_visual_section_updates_maps_picture_bindata_id_and_geometry() -> None:
    section_xml = b'''<hs:sec xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph" xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section"><hp:p id="0"><hp:run><hp:t>body</hp:t></hp:run></hp:p></hs:sec>'''

    updates, report = full_package.build_visual_section_updates(
        {"Contents/section0.xml": section_xml},
        {
            "status": "PASS",
            "bindata_count": 2,
            "items": [
                {"entry": "BinData/BIN0001.png", "size": 3, "sha256": "a", "media_type": "image/png"},
                {"entry": "BinData/BIN000A.png", "size": 4, "sha256": "b", "media_type": "image/png"},
            ],
        },
        {
            "record_counts": {"85": 1},
            "shape_layout": {
                "sections": [
                    {
                        "pictures": [
                            {
                                "record_index": 5,
                                "control_record_index": 4,
                                "control": {
                                    "position": {"horizontal_offset": 120, "vertical_offset": 240, "width": 3000, "height": 2000, "z_order": 1},
                                    "layout": {
                                        "treat_as_char": False,
                                        "flow_with_text": True,
                                        "allow_overlap": True,
                                        "vert_rel_to": "PAPER",
                                        "horz_rel_to": "COLUMN",
                                        "text_wrap": "SQUARE",
                                        "text_flow": "RIGHT_ONLY",
                                    },
                                },
                                "component_record_index": 4,
                                "picture": {
                                    "binary_data_id": 10,
                                    "bbox": {"left": 0, "top": 0, "right": 3000, "bottom": 2000, "width": 3000, "height": 2000},
                                },
                            }
                        ]
                    }
                ]
            },
        },
    )

    xml_text = updates["Contents/section0.xml"].decode("utf-8")
    assert report["picture_geometry_mapped_count"] == 1
    assert report["picture_bindata_id_mapped_count"] == 1
    assert report["picture_position_mapped_count"] == 1
    assert report["picture_layout_policy_mapped_count"] == 1
    assert report["items"][0]["entry"] == "BinData/BIN000A.png"
    assert 'binaryItemIDRef="BIN000A"' in xml_text
    assert 'zOrder="1"' in xml_text
    assert 'textWrap="SQUARE"' in xml_text
    assert 'textFlow="RIGHT_ONLY"' in xml_text
    assert 'treatAsChar="0"' in xml_text
    assert 'flowWithText="1"' in xml_text
    assert 'allowOverlap="1"' in xml_text
    assert 'vertRelTo="PAPER"' in xml_text
    assert 'horzRelTo="COLUMN"' in xml_text
    assert '<hp:sz width="3000" widthRelTo="ABSOLUTE" height="2000"' in xml_text
    assert 'horzOffset="120"' in xml_text
    assert 'vertOffset="240"' in xml_text


def test_visual_section_updates_emit_rectangle_shapes() -> None:
    section_xml = b'''<hs:sec xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph" xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section"><hp:p id="0"><hp:run><hp:t>body</hp:t></hp:run></hp:p></hs:sec>'''

    updates, report = full_package.build_visual_section_updates(
        {"Contents/section0.xml": section_xml},
        {"status": "NO_BINDATA_STREAMS", "bindata_count": 0, "items": []},
        {
            "record_counts": {"79": 2},
            "shape_layout": {
                "sections": [
                    {
                        "rectangles": [
                            {
                                "record_index": 10,
                                "control_record_index": 8,
                                "control": {
                                    "position": {"horizontal_offset": 100, "vertical_offset": 200, "width": 2000, "height": 1000, "z_order": 4},
                                    "layout": {
                                        "treat_as_char": False,
                                        "flow_with_text": False,
                                        "allow_overlap": True,
                                        "vert_rel_to": "PAGE",
                                        "horz_rel_to": "PARA",
                                        "text_wrap": "IN_FRONT_OF_TEXT",
                                        "text_flow": "BOTH_SIDES",
                                    },
                                    "margins": {"left": 11, "right": 12, "top": 13, "bottom": 14},
                                },
                                "component_record_index": 9,
                                "rectangle": {
                                    "round_ratio": 12,
                                    "points": [{"x": 0, "y": 0}, {"x": 2000, "y": 0}, {"x": 2000, "y": 1000}, {"x": 0, "y": 1000}],
                                    "bbox": {"left": 0, "top": 0, "right": 2000, "bottom": 1000, "width": 2000, "height": 1000},
                                },
                            },
                            {
                                "record_index": 11,
                                "component_record_index": 10,
                                "rectangle": {
                                    "round_ratio": 0,
                                    "points": [{"x": 50, "y": 60}, {"x": 350, "y": 60}, {"x": 350, "y": 260}, {"x": 50, "y": 260}],
                                    "bbox": {"left": 50, "top": 60, "right": 350, "bottom": 260, "width": 300, "height": 200},
                                },
                            },
                        ]
                    }
                ]
            },
        },
    )

    xml_text = updates["Contents/section0.xml"].decode("utf-8")
    assert report["status"] == "PASS"
    assert report["vector_shape_record_count"] == 2
    assert report["visible_vector_shape_count"] == 2
    assert report["geometry_mapped_vector_shape_count"] == 2
    assert report["position_mapped_vector_shape_count"] == 1
    assert report["layout_policy_mapped_vector_shape_count"] == 1
    assert report["unmapped_vector_shape_record_count"] == 0
    assert xml_text.count("<hp:rect") == 2
    assert 'ratio="12"' in xml_text
    assert 'zOrder="4"' in xml_text
    assert 'textWrap="IN_FRONT_OF_TEXT"' in xml_text
    assert 'treatAsChar="0"' in xml_text
    assert 'allowOverlap="1"' in xml_text
    assert 'vertRelTo="PAGE"' in xml_text
    assert '<hp:outMargin left="11" right="12" top="13" bottom="14"' in xml_text
    assert '<hp:orgSz width="2000" height="1000"' in xml_text
    assert '<hp:orgSz width="300" height="200"' in xml_text
    assert 'horzOffset="100"' in xml_text
    assert 'vertOffset="200"' in xml_text


def test_convert_full_refuses_to_write_when_decoders_are_incomplete(monkeypatch, tmp_path: Path) -> None:
    input_path = tmp_path / "source.hwp"
    output_path = tmp_path / "source.hwpx"
    report_path = tmp_path / "report.json"
    input_path.write_bytes(b"fake")

    monkeypatch.setattr(
        full,
        "analyze_hwp",
        lambda *_args, **_kwargs: {
            "status": "PASS",
            "input": str(input_path),
            "coverage": {
                "full_fidelity_ready": False,
                "blockers": ["UNSUPPORTED:fonts_and_styles"],
            },
            "ole_metadata": {
                "status": "PASS",
                "present_field_count": 2,
                "present_fields": ["title", "author"],
                "fields": {"title": "Source title", "author": "Writer"},
            },
            "record_audit": {
                "status": "PASS",
                "record_count": 2,
                "unknown_tag_count": 0,
                "risk_tag_count": 1,
                "decoded_error_count": 0,
                "risk_tags": [{"tag_id": 77, "tag_name": "TABLE", "count": 1, "samples": []}],
            },
            "source_manifest": {
                "status": "PASS",
                "input_info": {
                    "path": str(input_path),
                    "size": 4,
                    "sha256": "b5d54c39e66671c9731b9f471e585d8262cd4f54963f0c93082d8dcf334d4c78",
                },
                "stream_count": 3,
                "hashed_stream_count": 3,
                "storage_count": 1,
                "unreadable_stream_count": 0,
                "streams": [
                    {"name": "FileHeader", "kind": "header", "size": 8, "sha256": "header-sha"},
                    {"name": "DocInfo", "kind": "docinfo", "size": 16, "sha256": "docinfo-sha"},
                    {"name": "BodyText/Section0", "kind": "body_text", "size": 24, "sha256": "body-sha"},
                ],
            },
            "body_layout": {
                "sections": [
                    {
                        "paragraphs": [
                            {
                                "has_para_text": True,
                                "para_shape_id": 9,
                                "style_id": 3,
                                "first_char_shape_id": 5,
                                "char_shape_runs": [
                                    {"start_pos": 0, "char_shape_id": 5},
                                    {"start_pos": 2, "char_shape_id": 7},
                                ],
                                "line_segments": [
                                    {
                                        "text_pos": 0,
                                        "line_vertical_pos": 10,
                                        "line_height": 1200,
                                        "text_height": 1000,
                                        "baseline": 850,
                                        "line_spacing": 200,
                                        "column_start": 0,
                                        "segment_width": 5000,
                                        "flags": 1,
                                    }
                                ],
                            }
                        ]
                    }
                ]
            },
            "page_layout": {
                "sections": [
                    {
                        "section_index": 0,
                        "page_definition": {
                            "width": 59528,
                            "height": 84188,
                            "landscape": "NARROWLY",
                            "margins": {"left": 5669, "right": 5669, "top": 5669, "bottom": 2834, "header": 0, "footer": 0, "gutter": 0},
                        },
                    }
                ]
            },
            "page_layout": {
                "sections": [
                    {
                        "section_index": 0,
                        "page_definition": {
                            "width": 59528,
                            "height": 84188,
                            "landscape": "NARROWLY",
                            "margins": {"left": 5669, "right": 5669, "top": 5669, "bottom": 2834, "header": 0, "footer": 0, "gutter": 0},
                        },
                    }
                ]
            },
            "table_layout": {
                "sections": [
                    {
                        "section_index": 0,
                        "tables": [
                            {
                                "record_index": 1,
                                "table": {
                                    "row_count": 1,
                                    "col_count": 1,
                                    "cell_spacing": 0,
                                    "margins": {"left": 141, "right": 141, "top": 141, "bottom": 141},
                                },
                                "list_headers": [
                                    {
                                        "text_width": 1234,
                                        "text_height": 567,
                                        "margins": {"left": 10, "right": 11, "top": 12, "bottom": 13},
                                    }
                                ],
                            }
                        ],
                    }
                ]
            },
            "table_layout": {
                "sections": [
                    {
                        "section_index": 0,
                        "tables": [
                            {
                                "record_index": 1,
                                "table": {
                                    "row_count": 1,
                                    "col_count": 1,
                                    "cell_spacing": 0,
                                    "margins": {"left": 141, "right": 141, "top": 141, "bottom": 141},
                                },
                                "list_headers": [
                                    {
                                        "text_width": 1234,
                                        "text_height": 567,
                                        "margins": {"left": 10, "right": 11, "top": 12, "bottom": 13},
                                    }
                                ],
                            }
                        ],
                    }
                ]
            },
            "table_layout": {
                "sections": [
                    {
                        "section_index": 0,
                        "tables": [
                            {
                                "record_index": 1,
                                "table": {
                                    "row_count": 1,
                                    "col_count": 1,
                                    "cell_spacing": 0,
                                    "margins": {"left": 141, "right": 141, "top": 141, "bottom": 141},
                                },
                                "list_headers": [
                                    {
                                        "text_width": 1234,
                                        "text_height": 567,
                                        "margins": {"left": 10, "right": 11, "top": 12, "bottom": 13},
                                    }
                                ],
                            }
                        ],
                    }
                ]
            },
        },
    )

    report = full.convert_full(input_path, output_path, report_json=report_path)

    assert report["status"] == "FAIL"
    assert report["error"] == "FULL_FIDELITY_DECODERS_INCOMPLETE"
    assert not output_path.exists()
    assert report_path.exists()


def test_convert_full_allows_explicit_partial_derivative(monkeypatch, tmp_path: Path) -> None:
    input_path = tmp_path / "source.hwp"
    output_path = tmp_path / "source.hwpx"
    input_path.write_bytes(b"fake")

    monkeypatch.setattr(
        full,
        "analyze_hwp",
        lambda *_args, **_kwargs: {
            "status": "PASS",
            "input": str(input_path),
            "coverage": {
                "full_fidelity_ready": False,
                "blockers": ["UNSUPPORTED:fonts_and_styles"],
            },
            "ole_metadata": {
                "status": "PASS",
                "present_field_count": 2,
                "present_fields": ["title", "author"],
                "fields": {"title": "Source title", "author": "Writer"},
            },
            "record_audit": {
                "status": "PASS",
                "record_count": 2,
                "unknown_tag_count": 0,
                "risk_tag_count": 1,
                "decoded_error_count": 0,
                "risk_tags": [{"tag_id": 77, "tag_name": "TABLE", "count": 1, "samples": []}],
            },
            "source_manifest": {
                "status": "PASS",
                "stream_count": 3,
                "hashed_stream_count": 3,
                "storage_count": 1,
                "unreadable_stream_count": 0,
                "streams": [
                    {"name": "FileHeader", "kind": "header", "size": 8, "sha256": "header-sha"},
                    {"name": "DocInfo", "kind": "docinfo", "size": 16, "sha256": "docinfo-sha"},
                    {"name": "BodyText/Section0", "kind": "body_text", "size": 24, "sha256": "body-sha"},
                ],
            },
            "body_layout": {
                "sections": [
                    {
                        "paragraphs": [
                            {
                                "has_para_text": True,
                                "para_shape_id": 9,
                                "style_id": 3,
                                "first_char_shape_id": 5,
                                "char_shape_runs": [
                                    {"start_pos": 0, "char_shape_id": 5},
                                    {"start_pos": 2, "char_shape_id": 7},
                                ],
                                "line_segments": [
                                    {
                                        "text_pos": 0,
                                        "line_vertical_pos": 10,
                                        "line_height": 1200,
                                        "text_height": 1000,
                                        "baseline": 850,
                                        "line_spacing": 200,
                                        "column_start": 0,
                                        "segment_width": 5000,
                                        "flags": 1,
                                    }
                                ],
                            }
                        ]
                    }
                ]
            },
            "page_layout": {
                "sections": [
                    {
                        "section_index": 0,
                        "page_definition": {
                            "width": 59528,
                            "height": 84188,
                            "landscape": "NARROWLY",
                            "margins": {
                                "left": 5669,
                                "right": 5669,
                                "top": 5669,
                                "bottom": 2834,
                                "header": 0,
                                "footer": 0,
                                "gutter": 0,
                            },
                        },
                    }
                ]
            },
            "table_layout": {
                "sections": [
                    {
                        "section_index": 0,
                        "tables": [
                            {
                                "record_index": 1,
                                "table": {
                                    "row_count": 1,
                                    "col_count": 1,
                                    "cell_spacing": 0,
                                    "margins": {"left": 141, "right": 141, "top": 141, "bottom": 141},
                                },
                                "list_headers": [
                                    {
                                        "text_width": 1234,
                                        "text_height": 567,
                                        "margins": {"left": 10, "right": 11, "top": 12, "bottom": 13},
                                    }
                                ],
                            }
                        ],
                    }
                ]
            },
        },
    )
    monkeypatch.setattr(
        full,
        "convert_hwp_to_hwpx",
        lambda *_args, **_kwargs: make_fake_partial_output(output_path),
    )
    monkeypatch.setattr(full.HwpxValidator, "validate_hwpx", staticmethod(lambda _path: {"zip_ok": True, "xml_ok": True}))

    report = full.convert_full(input_path, output_path, allow_partial=True)

    assert report["status"] == "WARN"
    assert report["mode"] == "partial_ai_readable_derivative"
    assert report["identity_status"] == "FAIL"
    assert report["identity_equal"] is False
    assert "FULL_FIDELITY_COVERAGE_INCOMPLETE" in report["identity_audit"]["blockers"]
    assert report["allow_partial"] is True
    assert "not full-fidelity" in report["warning"]
    assert report["package_analysis_entries"]["body_style_mapping"]["split_char_shape_runs"] == 2
    assert report["package_analysis_entries"]["body_style_mapping"]["line_segment_arrays"] == 1
    assert report["package_analysis_entries"]["body_style_mapping"]["line_segments"] == 1
    assert set(report["package_analysis_entries"]["entries"]) == {
        "Preview/DecodedDocInfo.json",
        "Preview/DocumentMetadata.json",
        "Preview/FullFidelityCoverage.json",
        "Preview/RecordAudit.json",
        "Preview/SourceManifest.json",
        "Preview/OriginalIntegrity.json",
        "Preview/FontFaceMapping.json",
        "Preview/ListStyleMapping.json",
        "Preview/EquationMapping.json",
        "Preview/BinDataPreservation.json",
        "Preview/BodyStyleMapping.json",
        "Preview/PageLayoutMapping.json",
        "Preview/TableLayoutMapping.json",
        "Preview/VisualObjectMapping.json",
        "Contents/header.xml",
        "Contents/content.hpf",
        "Contents/section0.xml",
    }
    with ZipFile(output_path) as zf:
        assert "Preview/DecodedDocInfo.json" in zf.namelist()
        assert "Preview/DocumentMetadata.json" in zf.namelist()
        assert "Preview/FullFidelityCoverage.json" in zf.namelist()
        assert "Preview/RecordAudit.json" in zf.namelist()
        assert "Preview/SourceManifest.json" in zf.namelist()
        assert "Preview/OriginalIntegrity.json" in zf.namelist()
        assert "Preview/ListStyleMapping.json" in zf.namelist()
        assert "Preview/BinDataPreservation.json" in zf.namelist()
        assert "Preview/BodyStyleMapping.json" in zf.namelist()
        assert "Preview/PageLayoutMapping.json" in zf.namelist()
        assert "Preview/TableLayoutMapping.json" in zf.namelist()
        assert "Preview/VisualObjectMapping.json" in zf.namelist()
        assert "Contents/header.xml" in zf.namelist()
        assert "Source title" in zf.read("Preview/DocumentMetadata.json").decode("utf-8")
        assert "risk_tag_count" in zf.read("Preview/RecordAudit.json").decode("utf-8")
        assert "BodyText/Section0" in zf.read("Preview/SourceManifest.json").decode("utf-8")
        assert "byte_exact_original_embedded" in zf.read("Preview/OriginalIntegrity.json").decode("utf-8")
        content_hpf = zf.read("Contents/content.hpf").decode("utf-8")
        assert "Contents/header.xml" in content_hpf
        assert 'idref="header"' in content_hpf
        assert 'idref="section0"' in content_hpf
        section_xml = zf.read("Contents/section0.xml").decode("utf-8")
        assert 'paraPrIDRef="9"' in section_xml
        assert 'styleIDRef="3"' in section_xml
        assert 'charPrIDRef="5"' in section_xml
        assert 'charPrIDRef="7"' in section_xml
        assert "<hp:t>bo</hp:t>" in section_xml
        assert "<hp:t>dy</hp:t>" in section_xml
        assert "<hp:lineSegArray>" in section_xml
        assert 'textpos="0"' in section_xml
        assert 'vertsize="1200"' in section_xml
        assert 'horzsize="5000"' in section_xml
        assert 'width="59528"' in section_xml
        assert 'height="84188"' in section_xml
        assert 'left="5669"' in section_xml
        assert 'textWidth="1234"' in section_xml
        assert 'textHeight="567"' in section_xml
        assert '<hp:cellMargin left="10" right="11" top="12" bottom="13"' in section_xml


def test_identity_audit_fails_closed_for_text_only_derivative(tmp_path: Path) -> None:
    input_path = tmp_path / "source.hwp"
    output_path = tmp_path / "source.hwpx"
    input_path.write_bytes(b"fake")
    with ZipFile(output_path, "w") as zf:
        zf.writestr("mimetype", "application/vnd.hancom.hwpml")
        zf.writestr("Original/original.hwp", b"fake")
        zf.writestr("Contents/section0.xml", "<sec><p>body</p></sec>")
        zf.writestr(
            "Preview/ConversionReport.json",
            """{
              "mode": "text_only_rebuild_with_embedded_original",
              "original_preservation": {
                "preservation": {
                  "ai_readable_derivative_is_text_only_rebuild": true
                }
              }
            }""",
        )

    audit = full.build_identity_audit(
        input_path,
        output_path,
        analysis={
            "status": "PASS",
            "coverage": {"status": "FAIL", "full_fidelity_ready": False, "blockers": ["UNSUPPORTED:fonts_and_styles"]},
            "source_manifest": {
                "input_info": {
                    "path": str(input_path),
                    "size": 4,
                    "sha256": "b5d54c39e66671c9731b9f471e585d8262cd4f54963f0c93082d8dcf334d4c78",
                }
            },
            "record_audit": {"record_count": 1, "unknown_tag_count": 0, "risk_tag_count": 1, "decoded_error_count": 0},
        },
    )

    assert audit["status"] == "FAIL"
    assert audit["identity_equal"] is False
    assert audit["original_integrity"]["byte_exact_original_embedded"] is True
    assert "TEXT_ONLY_DERIVATIVE_OUTPUT" in audit["blockers"]
    assert "CONVERSION_MODE_NOT_FULL_FIDELITY" in audit["blockers"]
    assert "FULL_FIDELITY_COVERAGE_INCOMPLETE" in audit["blockers"]
    assert "FULL_FIDELITY_PREVIEW_EVIDENCE_MISSING" in audit["blockers"]


def test_build_decoded_header_xml_maps_docinfo_styles() -> None:
    decoded_docinfo = {
        "document_properties": {"page_start": 3, "footnote_start": 4, "endnote_start": 5, "picture_start": 6, "table_start": 7, "equation_start": 8},
        "binary_data": [{"index": 0, "data_type": "EMBEDDING", "storage_id": 1, "extension": "png", "stream_name": "BinData/BIN0001.png"}],
        "face_names": [{"index": 0, "name": "TestFont"}],
        "border_fills": [
            {
                "index": 0,
                "three_d": True,
                "shadow": True,
                "slash": {"type": "CENTER", "crooked": True, "is_counter": False},
                "back_slash": {"type": "ALL", "crooked": False, "is_counter": True},
                "border_types": [0, 2, 7, 10],
                "border_widths": [1, 2, 3, 4],
                "border_colors": [{"hex": "#111111"}, {"hex": "#222222"}, {"hex": "#333333"}, {"hex": "#444444"}],
                "diagonal_type_name": "DASH",
                "diagonal_width_name": "0.2 mm",
                "diagonal_color": {"hex": "#555555"},
                "fill": {"solid": {"background": {"hex": "#ffffff"}, "pattern": {"hex": "#000000"}, "pattern_type": 5}},
            }
        ],
        "char_shapes": [
            {
                "index": 0,
                "face_ids": {"hangul": 1, "latin": 2, "hanja": 3, "japanese": 4, "other": 5, "symbol": 6, "user": 7},
                "ratios": {"hangul": 95, "latin": 105},
                "spacings": {"hangul": -5, "latin": 3},
                "relative_sizes": {"hangul": 110, "latin": 90},
                "offsets": {"hangul": 2, "latin": -2},
                "base_size_hwpunit": 1200,
                "text_color": {"hex": "#123456"},
                "shade_color": {"hex": "#ffffff"},
                "bold": True,
                "italic": True,
                "underline_type": 1,
                "underline_color": {"hex": "#112233"},
                "strikeout_type": 1,
                "strikeout_color": {"hex": "#223344"},
                "shadow_offset_x": 3,
                "shadow_offset_y": 4,
                "shadow_color": {"hex": "#334455"},
                "border_fill_id": 0,
            }
        ],
        "para_shapes": [
            {
                "index": 0,
                "align": 3,
                "line_spacing": 180,
                "line_spacing_type": 0,
                "line_break_latin": 1,
                "line_break_hangul": 1,
                "margins": {"left": 10, "right": 20, "indent": 30, "before": 40, "after": 50},
                "border_fill_id": 0,
                "border_spacing": {"left": 1, "right": 2, "top": 3, "bottom": 4},
                "heading_type": 1,
                "level": 2,
                "numbering_bullet_id": 1,
            }
        ],
        "numberings": [{"index": 0, "levels": [{"level": 1, "text": "^1.", "text_offset": 50, "char_shape_id": 4294967295, "num_format": "DIGIT"}]}],
        "bullets": [{"index": 0, "bullet_char": "-", "char_shape_id": 0}],
        "styles": [{"index": 0, "name": "본문", "english_name": "Body", "style_type": 0, "para_shape_id": 0, "char_shape_id": 0}],
    }

    root = ET.fromstring(full.build_decoded_header_xml(decoded_docinfo).encode("utf-8"))
    xml_text = ET.tostring(root, encoding="unicode")

    assert root.tag.endswith("head")
    assert "TestFont" in xml_text
    assert '<hh:borderFill id="0" threeD="1" shadow="1"' in xml_text
    assert '<hh:slash type="CENTER" Crooked="1" isCounter="0"' in xml_text
    assert '<hh:backSlash type="ALL" Crooked="0" isCounter="1"' in xml_text
    assert '<hh:leftBorder type="SOLID" width="0.12 mm" color="#111111"' in xml_text
    assert '<hh:rightBorder type="DASH" width="0.15 mm" color="#222222"' in xml_text
    assert '<hh:topBorder type="DOUBLE_SLIM" width="0.2 mm" color="#333333"' in xml_text
    assert '<hh:diagonal type="DASH" width="0.2 mm" color="#555555"' in xml_text
    assert '<hc:winBrush faceColor="#FFFFFF" hatchColor="#000000" alpha="0" hatchStyle="CROSS"' in xml_text
    assert "height=\"1200\"" in xml_text
    assert "textColor=\"#123456\"" in xml_text
    assert '<hh:fontRef hangul="1" latin="2" hanja="3" japanese="4" other="5" symbol="6" user="7"' in xml_text
    assert '<hh:ratio hangul="95" latin="105"' in xml_text
    assert '<hh:spacing hangul="-5" latin="3"' in xml_text
    assert '<hh:relSz hangul="110" latin="90"' in xml_text
    assert '<hh:offset hangul="2" latin="-2"' in xml_text
    assert '<hh:underline type="BOTTOM" shape="SOLID" color="#112233"' in xml_text
    assert '<hh:strikeout shape="SOLID" color="#223344"' in xml_text
    assert '<hh:shadow type="DROP" color="#334455" offsetX="3" offsetY="4"' in xml_text
    assert "horizontal=\"CENTER\"" in xml_text
    assert '<hh:breakSetting breakLatinWord="HYPHENATION" breakNonLatinWord="BREAK_WORD"' in xml_text
    assert '<hh:intent value="30" unit="HWPUNIT"' in xml_text
    assert '<hh:left value="10" unit="HWPUNIT"' in xml_text
    assert '<hh:lineSpacing type="PERCENT" value="180" unit="HWPUNIT"' in xml_text
    assert '<hh:border borderFillIDRef="0" offsetLeft="1" offsetRight="2" offsetTop="3" offsetBottom="4"' in xml_text
    assert '<hh:autoSpacing eAsianEng="0" eAsianNum="0"' in xml_text
    assert "<hh:numbering" in xml_text
    assert "^1." in xml_text
    assert "<hh:bullet" in xml_text
    assert "<hh:heading" in xml_text
    assert "idRef=\"0\"" in xml_text
    assert "level=\"2\"" in xml_text
    mapping = full.build_list_style_mapping(decoded_docinfo)
    assert mapping["applied_para_shape_count"] == 1
    assert mapping["referenced_para_shapes"][0]["mapping"]["kind"] == "numbering"
    assert full.decoded_header_summary({"counts": {"binary_data": 1}})["binary_data"] == 1
    assert "name=\"본문\"" in xml_text


def test_page_layout_updates_emit_page_border_fill() -> None:
    section_xml = b'''<hp:sec xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph"><hp:p><hp:run><hp:t>body</hp:t></hp:run></hp:p></hp:sec>'''

    updates, report = full.build_page_layout_section_updates(
        {"Contents/section0.xml": section_xml},
        {
            "sections": [
                {
                    "section_index": 0,
                    "page_definition": {
                        "width": 59528,
                        "height": 84188,
                        "landscape": "NARROWLY",
                        "margins": {"left": 5669, "right": 5669, "top": 5669, "bottom": 2834, "header": 0, "footer": 0, "gutter": 0},
                    },
                    "footnote_shapes": [
                        {
                            "number_format": "DIGIT",
                            "user_char": "*",
                            "prefix_char": "",
                            "suffix_char": ")",
                            "superscript": True,
                            "separator_length": 100,
                            "separator_line_type": "DASH",
                            "separator_line_width": "0.2 mm",
                            "separator_line_color": {"hex": "#112233"},
                            "space_between": 40,
                            "space_below": 30,
                            "space_above": 20,
                            "numbering_type": "ON_PAGE",
                            "endnote_numbering_type": "ON_SECTION",
                            "start_number": 3,
                            "placement_raw": 2,
                            "beneath_text": False,
                        },
                        {
                            "number_format": "ROMAN_SMALL",
                            "user_char": "",
                            "prefix_char": "[",
                            "suffix_char": "]",
                            "superscript": False,
                            "separator_length": 0,
                            "separator_line_type": "SOLID",
                            "separator_line_width": "0.12 mm",
                            "separator_line_color": {"hex": "#000000"},
                            "space_between": 0,
                            "space_below": 567,
                            "space_above": 850,
                            "numbering_type": "CONTINUOUS",
                            "endnote_numbering_type": "ON_SECTION",
                            "start_number": 1,
                            "placement_raw": 1,
                            "beneath_text": True,
                        },
                    ],
                    "page_border_fills": [
                        {
                            "type": "BOTH",
                            "border_fill_id": 4,
                            "text_border": "CONTENT",
                            "header_inside": True,
                            "footer_inside": False,
                            "fill_area": "PAPER",
                            "margins": {"left": 1417, "right": 1418, "top": 1419, "bottom": 1420},
                        }
                    ],
                }
            ]
        },
    )

    xml_text = updates["Contents/section0.xml"].decode("utf-8")
    assert report["applied_footnote_shape_count"] == 1
    assert report["applied_endnote_shape_count"] == 1
    assert report["applied_page_border_fill_count"] == 1
    assert '<hp:footNotePr><hp:autoNumFormat type="DIGIT" userChar="*" prefixChar="" suffixChar=")" supscript="1"' in xml_text
    assert '<hp:noteLine length="100" type="DASH" width="0.2 mm" color="#112233"' in xml_text
    assert '<hp:numbering type="ON_PAGE" newNum="3"' in xml_text
    assert '<hp:placement place="RIGHT_MOST_COLUMN" beneathText="0"' in xml_text
    assert '<hp:endNotePr><hp:autoNumFormat type="ROMAN_SMALL" userChar="" prefixChar="[" suffixChar="]" supscript="0"' in xml_text
    assert '<hp:placement place="END_OF_SECTION" beneathText="1"' in xml_text
    assert '<hp:pageBorderFill type="BOTH" borderFillIDRef="4" textBorder="CONTENT" headerInside="1" footerInside="0" fillArea="PAPER">' in xml_text
    assert '<hp:offset left="1417" right="1418" top="1419" bottom="1420"' in xml_text


def test_table_layout_uses_row_cell_counts_for_cell_metric_mapping() -> None:
    section_xml = b'''<hp:sec xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph"><hp:p><hp:run><hp:tbl rowCnt="2" colCnt="2"><hp:tr><hp:tc><hp:subList textWidth="0" textHeight="0" /><hp:cellMargin left="0" right="0" top="0" bottom="0" /></hp:tc><hp:tc><hp:subList textWidth="0" textHeight="0" /><hp:cellMargin left="0" right="0" top="0" bottom="0" /></hp:tc></hp:tr><hp:tr><hp:tc><hp:subList textWidth="0" textHeight="0" /><hp:cellMargin left="0" right="0" top="0" bottom="0" /></hp:tc><hp:tc><hp:subList textWidth="0" textHeight="0" /><hp:cellMargin left="0" right="0" top="0" bottom="0" /></hp:tc></hp:tr></hp:tbl></hp:run></hp:p></hp:sec>'''
    updates, report = full.build_table_layout_section_updates(
        {"Contents/section0.xml": section_xml},
        {
            "sections": [
                {
                    "section_index": 0,
                    "tables": [
                        {
                            "record_index": 1,
                            "table": {
                                "row_count": 2,
                                "col_count": 2,
                                "cell_spacing": 0,
                                "margins": {},
                                "row_cell_counts": [1, 1],
                                "row_cell_count_total": 2,
                            },
                            "list_headers": [
                                {
                                    "text_width": 111,
                                    "text_height": 222,
                                    "margins": {"left": 10, "right": 11, "top": 12, "bottom": 13},
                                    "cell_addr": {"row": 0, "col": 0},
                                    "cell_span": {"row": 1, "col": 2},
                                    "border_fill_id": 7,
                                },
                                {
                                    "text_width": 333,
                                    "text_height": 444,
                                    "margins": {"left": 20, "right": 21, "top": 22, "bottom": 23},
                                    "cell_addr": {"row": 1, "col": 0},
                                    "cell_span": {"row": 1, "col": 2},
                                    "border_fill_id": 8,
                                },
                            ],
                        }
                    ],
                }
            ]
        },
    )

    assert report["sections"][0]["tables"][0]["cell_mapping_policy"] == "row_cell_counts"
    assert report["sections"][0]["tables"][0]["applied_cell_metrics"] == 2
    assert report["sections"][0]["tables"][0]["applied_cell_sizes"] == 2
    assert report["sections"][0]["tables"][0]["applied_cell_addr_spans"] == 2
    assert report["sections"][0]["tables"][0]["applied_exact_cell_addrs"] == 2
    assert report["sections"][0]["tables"][0]["applied_exact_cell_spans"] == 2
    assert report["sections"][0]["tables"][0]["applied_cell_borders"] == 2
    assert report["sections"][0]["tables"][0]["applied_inferred_col_spans"] == 2
    assert report["sections"][0]["tables"][0]["removed_covered_cells"] == 2
    xml_text = updates["Contents/section0.xml"].decode("utf-8")
    assert xml_text.index('textWidth="111"') < xml_text.index('textWidth="333"')
    assert xml_text.count('textWidth="333"') == 1
    assert 'textHeight="444"' in xml_text
    assert '<hp:cellSz width="132" height="247"' in xml_text
    assert '<hp:cellSz width="374" height="489"' in xml_text
    assert 'rowAddr="0" colAddr="0"' in xml_text
    assert 'rowAddr="1" colAddr="0"' in xml_text
    assert 'colSpan="2"' in xml_text
    assert 'borderFillIDRef="7"' in xml_text
    assert 'borderFillIDRef="8"' in xml_text
    assert xml_text.count("<hp:cellSpan") == 2


def make_fake_partial_output(output_path: Path) -> dict:
    with ZipFile(output_path, "w") as zf:
        zf.writestr("mimetype", "application/vnd.hancom.hwpml")
        zf.writestr("Original/original.hwp", b"fake")
        zf.writestr(
            "Contents/section0.xml",
            '<hp:sec xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph"><hp:p><hp:run><hp:t>body</hp:t></hp:run></hp:p><hp:p><hp:run><hp:tbl rowCnt="1" colCnt="1"><hp:tr><hp:tc><hp:subList textWidth="0" textHeight="0"><hp:p><hp:run><hp:t>cell</hp:t></hp:run></hp:p></hp:subList><hp:cellMargin left="0" right="0" top="0" bottom="0" /></hp:tc></hp:tr></hp:tbl></hp:run></hp:p></hp:sec>',
        )
        zf.writestr(
            "Contents/content.hpf",
            """<?xml version="1.0" encoding="UTF-8"?>
<opf:package xmlns:opf="http://www.idpf.org/2007/opf">
  <opf:manifest><opf:item id="section0" href="Contents/section0.xml" media-type="application/xml"/></opf:manifest>
</opf:package>""",
        )
    return {
        "status": "PASS",
        "output": str(output_path),
        "mode": "text_only_rebuild_with_embedded_original",
    }
