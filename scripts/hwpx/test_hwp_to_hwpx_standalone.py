import json
from pathlib import Path
from zipfile import ZipFile

import hwp_to_hwpx_standalone as standalone
from hwp_to_hwpx_standalone import (
    batch_csv_rows,
    build_audit_record,
    build_conversion_gate,
    build_markdown_report,
    build_batch_plan,
    configure_logging,
    convert_batch,
    convert_hwp_to_hwpx,
    file_snapshot,
    fidelity_gate,
    roundtrip_text_gate,
    repair_output_package,
    split_section_blocks,
    table_grid_gate,
    split_paragraphs,
    split_section_paragraphs,
    text_quality_gate,
    watch_batch,
    write_audit_log,
    write_forensic_item_audit,
    write_report_md,
    write_report_csv,
    write_text_hwpx,
)
from extract_hwp_body_fields import parse_table_record_payload
from extract_hwp_body_fields import reconstruct_table_rows
from hwpx_package import HwpxValidator, package_contains


def test_split_paragraphs_prefers_section_text() -> None:
    extraction = {
        "text": "fallback",
        "sections": [
            {"text": "first paragraph\n\nsecond paragraph"},
            {"text": "third   paragraph"},
        ],
    }

    assert split_paragraphs(extraction) == ["first paragraph", "second paragraph", "third paragraph"]
    assert split_section_paragraphs(extraction) == [["first paragraph", "second paragraph"], ["third paragraph"]]


def test_split_section_blocks_preserves_detected_table_blocks() -> None:
    extraction = {
        "sections": [
            {
                "blocks": [
                    {"type": "paragraph", "text": "intro"},
                    {"type": "table", "rows": [["cell a"], ["cell b"]], "source_row_count": 12, "source_col_count": 4},
                ]
            }
        ]
    }

    assert split_section_blocks(extraction) == [
        [
            {"type": "paragraph", "text": "intro"},
            {"type": "table", "rows": [["cell a"], ["cell b"]], "source_row_count": 12, "source_col_count": 4},
        ]
    ]


def test_parse_table_record_payload_reads_source_row_and_col_counts() -> None:
    payload = (
        b"\x00\x00\x00\x00"
        + (2).to_bytes(2, "little")
        + (4).to_bytes(2, "little")
        + b"\x00" * 10
        + (1).to_bytes(2, "little")
        + (3).to_bytes(2, "little")
    )

    parsed = parse_table_record_payload(payload)

    assert parsed["source_row_count"] == 2
    assert parsed["source_col_count"] == 4
    assert parsed["row_cell_counts"] == [1, 3]
    assert parsed["row_cell_count_total"] == 4
    assert parsed["payload_size"] == len(payload)


def test_reconstruct_table_rows_uses_source_grid_row_major() -> None:
    rows, mode, defaults = reconstruct_table_rows(["a", "b", "c", "d", "e"], 2, 3)

    assert mode == "source_grid_row_major"
    assert rows == [["a", "b", "c"], ["d", "e", ""]]
    assert defaults == {}


def test_reconstruct_table_rows_preserves_overflow_in_last_cell() -> None:
    rows, mode, defaults = reconstruct_table_rows(["a", "b", "c", "d"], 1, 3)

    assert mode == "source_grid_row_major"
    assert rows == [["a", "b", "c\nd"]]
    assert defaults == {}


def test_reconstruct_table_rows_uses_row_cell_counts_for_merged_cells() -> None:
    rows, mode, defaults = reconstruct_table_rows(["head", "left", "mid", "right"], 2, 4, [1, 3])

    assert mode == "source_row_cell_counts"
    assert rows == [["head", "", "", ""], ["left", "", "mid", "right"]]
    assert defaults["mergedCells"] == {"0,0": {"colSpan": 4, "rowSpan": 1}, "1,0": {"colSpan": 2, "rowSpan": 1}}
    assert defaults["coveredCells"] == ["0,1", "0,2", "0,3", "1,1"]


def test_write_text_hwpx_creates_valid_package(tmp_path: Path) -> None:
    output = tmp_path / "out.hwpx"
    hello = "\uc548\ub155\ud558\uc138\uc694"
    title = "HWPX standalone conversion"

    write_text_hwpx(output, [hello, title])
    validation = HwpxValidator.validate_hwpx(output)

    assert validation["zip_ok"] is True
    assert validation["xml_ok"] is True
    assert validation["section_entries"] == 1
    assert package_contains(output, [hello, title]) == {
        hello: True,
        title: True,
    }


def test_write_text_hwpx_uses_hancom_owpml_package_markers(tmp_path: Path) -> None:
    output = tmp_path / "hancom_markers.hwpx"

    write_text_hwpx(output, ["한컴 호환 본문"])

    with ZipFile(output) as zf:
        mimetype = zf.read("mimetype").decode("utf-8")
        content = zf.read("Contents/content.hpf").decode("utf-8")
        container = zf.read("META-INF/container.xml").decode("utf-8")
        manifest = zf.read("META-INF/manifest.xml").decode("utf-8")
        compression = {info.filename: info.compress_type for info in zf.infolist()}

    assert mimetype == "application/owpml"
    assert 'version="1.0"' in content
    assert "application/hwpml-package+xml" in content
    assert 'full-path="Contents/content.hpf"' in container
    assert 'manifest:full-path="/"' in manifest
    assert compression["mimetype"] == 0
    assert compression["Contents/section0.xml"] == 0
    assert "META-INF/" in compression
    assert "Contents/" in compression
    assert "Preview/" in compression


def test_repair_output_package_uses_short_temp_names(monkeypatch, tmp_path: Path) -> None:
    output_dir = tmp_path / ("long_" + "\uac00" * 40)
    output_dir.mkdir()
    output = output_dir / (("\ubb38\uc11c_" + "\uac00" * 80) + ".hwpx")
    write_text_hwpx(output, ["hello"])
    seen: dict[str, str] = {}

    def fake_repair(input_path: Path, repaired_path: Path) -> dict[str, object]:
        seen["repaired_name"] = repaired_path.name
        assert input_path == output
        repaired_path.write_bytes(input_path.read_bytes())
        return {"status": "PASS", "input": str(input_path), "output": str(repaired_path)}

    monkeypatch.setattr(standalone, "repair_hwpx_spine", fake_repair)

    report = repair_output_package(output, expected_text="hello")

    assert report["status"] == "PASS"
    assert seen["repaired_name"].startswith(".repair.")
    assert len(seen["repaired_name"]) < 50
    assert output.exists()


def test_write_text_hwpx_can_embed_byte_exact_original_hwp(tmp_path: Path) -> None:
    output = tmp_path / "out.hwpx"
    original = tmp_path / "source.hwp"
    original.write_bytes(b"original hwp bytes")

    write_text_hwpx(output, ["AI readable text"], original_hwp_path=original)

    with ZipFile(output) as zf:
        names = set(zf.namelist())
        manifest = json.loads(zf.read("Preview/OriginalManifest.json").decode("utf-8"))
        embedded = zf.read("Original/original.hwp")

    assert "Original/original.hwp" in names
    assert embedded == original.read_bytes()
    assert manifest["original_file_name"] == "source.hwp"
    assert manifest["original_snapshot"]["sha256"] == file_snapshot(original)["sha256"]
    assert manifest["preservation"]["byte_exact_original_embedded"] is True


def test_write_text_hwpx_preserves_multiple_sections(tmp_path: Path) -> None:
    output = tmp_path / "multi.hwpx"

    write_text_hwpx(output, [["section one"], ["section two"]])
    validation = HwpxValidator.validate_hwpx(output)

    assert validation["zip_ok"] is True
    assert validation["xml_ok"] is True
    assert validation["section_entries"] == 2
    with ZipFile(output) as zf:
        assert "Contents/section0.xml" in zf.namelist()
        assert "Contents/section1.xml" in zf.namelist()


def test_write_text_hwpx_can_reconstruct_table_blocks(tmp_path: Path) -> None:
    output = tmp_path / "table.hwpx"

    write_text_hwpx(output, [["intro", "cell a", "cell b"]], section_blocks=[[{"type": "paragraph", "text": "intro"}, {"type": "table", "rows": [["cell a"], ["cell b"]]}]])

    validation = HwpxValidator.validate_hwpx(output)
    with ZipFile(output) as zf:
        section_xml = zf.read("Contents/section0.xml").decode("utf-8")

    assert validation["zip_ok"] is True
    assert validation["xml_ok"] is True
    assert "<hp:tbl" in section_xml
    assert package_contains(output, ["intro", "cell a", "cell b"]) == {"intro": True, "cell a": True, "cell b": True}


def test_write_text_hwpx_uses_source_grid_table_shape(tmp_path: Path) -> None:
    output = tmp_path / "table_shape.hwpx"
    blocks = [[{"type": "table", "rows": [["a", "b", "c"], ["d", "e", ""]], "source_row_count": 2, "source_col_count": 3}]]

    write_text_hwpx(output, [["a", "b", "c", "d", "e"]], section_blocks=blocks)

    with ZipFile(output) as zf:
        section_xml = zf.read("Contents/section0.xml").decode("utf-8")
    assert 'rowCnt="2"' in section_xml
    assert 'colCnt="3"' in section_xml


def test_table_grid_gate_passes_for_generated_table_block(tmp_path: Path) -> None:
    output = tmp_path / "table_grid.hwpx"
    blocks = [[{"type": "table", "rows": [["a", "b", "c"], ["d", "e", ""]], "reconstructed_row_count": 2, "reconstructed_col_count": 3}]]
    write_text_hwpx(output, [["a", "b", "c", "d", "e"]], section_blocks=blocks)

    gate = table_grid_gate(blocks, output)

    assert gate["status"] == "PASS"
    assert gate["expected_shapes"] == [{"row_count": 2, "col_count": 3}]
    assert gate["actual_shapes"] == [{"row_count": 2, "col_count": 3}]


def test_table_grid_gate_fails_on_shape_mismatch(tmp_path: Path) -> None:
    output = tmp_path / "table_grid_bad.hwpx"
    actual_blocks = [[{"type": "table", "rows": [["a", "b"], ["c", "d"]], "reconstructed_row_count": 2, "reconstructed_col_count": 2}]]
    expected_blocks = [[{"type": "table", "rows": [["a", "b"], ["c", "d"]], "reconstructed_row_count": 1, "reconstructed_col_count": 4}]]
    write_text_hwpx(output, [["a", "b", "c", "d"]], section_blocks=actual_blocks)

    gate = table_grid_gate(expected_blocks, output)

    assert gate["status"] == "FAIL"
    assert "HWPX_TABLE_SHAPE_MISMATCH" in gate["errors"]


def test_table_grid_gate_accepts_span_remapped_text_sequence(tmp_path: Path) -> None:
    output = tmp_path / "table_grid_span_sequence.hwpx"
    actual_blocks = [[{"type": "table", "rows": [["a", "b", "", "c"]], "reconstructed_row_count": 1, "reconstructed_col_count": 4}]]
    expected_blocks = [[{"type": "table", "rows": [["a", "", "b", "c"]], "reconstructed_row_count": 1, "reconstructed_col_count": 4}]]
    write_text_hwpx(output, [["a", "b", "c"]], section_blocks=actual_blocks)

    gate = table_grid_gate(expected_blocks, output)

    assert gate["status"] == "PASS"
    assert gate["warnings"] == []
    assert gate["mismatch_count"] == 0
    assert gate["sequence_match_count"] == 1


def test_convert_hwp_to_hwpx_uses_extractor_and_writes_reportable_package(tmp_path: Path) -> None:
    input_path = tmp_path / "source.hwp"
    output_path = tmp_path / "source.hwpx"
    input_path.write_bytes(b"fake fixture; extractor is injected")

    def extractor(path: Path) -> dict:
        assert path == input_path.resolve()
        return {
            "ok": True,
            "text": "Body A\nBody B",
            "sections": [
                {"name": "BodyText/Section0", "text": "Body A"},
                {"name": "BodyText/Section1", "text": "Body B"},
            ],
            "header": {"compressed": True},
            "record_counts": {67: 2},
            "feature_inventory": {"section_count": 2, "bindata_count": 0, "risk_record_tags": {}},
        }

    report = convert_hwp_to_hwpx(input_path, output_path, extractor=extractor, expected_texts=["Body A"])

    assert report["status"] == "PASS"
    assert report["paragraph_count"] == 2
    assert report["section_count"] == 2
    assert report["section_paragraph_counts"] == [1, 1]
    assert report["text_quality"]["status"] == "PASS"
    assert report["text_quality"]["missing_expected_texts"] == []
    assert report["roundtrip_text"]["status"] == "PASS"
    assert report["roundtrip_text"]["exact_normalized_match"] is True
    assert report["table_reconstruction"]["status"] == "NO_TABLE_BLOCKS"
    assert report["table_grid_gate"]["status"] == "PASS"
    assert report["table_grid_gate"]["expected_table_count"] == 0
    with ZipFile(output_path) as zf:
        conversion_report = json.loads(zf.read("Preview/ConversionReport.json").decode("utf-8"))
    assert conversion_report["mode"] == "text_only_rebuild"
    assert conversion_report["paragraph_count"] == 2
    assert conversion_report["section_count"] == 2
    assert conversion_report["text_quality"]["status"] == "PASS"
    assert report["input_info"]["size"] == input_path.stat().st_size
    assert report["input_info"]["sha256"] == file_snapshot(input_path)["sha256"]
    assert report["output_info"]["size"] == output_path.stat().st_size
    assert report["output_info"]["sha256"] == file_snapshot(output_path)["sha256"]
    assert report["conversion_gate"]["status"] == "PASS"
    assert report["conversion_gate"]["failed_checks"] == []
    assert report["fidelity_gate"]["status"] == "PASS"


def test_convert_hwp_to_hwpx_reports_embedded_original_when_requested(tmp_path: Path) -> None:
    input_path = tmp_path / "source.hwp"
    output_path = tmp_path / "source.hwpx"
    input_path.write_bytes(b"fake fixture; extractor is injected")

    def extractor(_path: Path) -> dict:
        return {
            "ok": True,
            "text": "Body A",
            "sections": [{"name": "BodyText/Section0", "text": "Body A"}],
            "feature_inventory": {"section_count": 1, "bindata_count": 0, "risk_record_tags": {}},
        }

    report = convert_hwp_to_hwpx(input_path, output_path, extractor=extractor, embed_original=True)

    assert report["status"] == "PASS"
    assert report["mode"] == "text_only_rebuild_with_embedded_original"
    assert report["original_preservation"]["entry_name"] == "Original/original.hwp"
    assert report["original_preservation"]["original_snapshot"]["sha256"] == file_snapshot(input_path)["sha256"]
    with ZipFile(output_path) as zf:
        assert zf.read("Original/original.hwp") == input_path.read_bytes()


def test_convert_hwp_to_hwpx_can_apply_decoded_style_bridge(monkeypatch, tmp_path: Path) -> None:
    input_path = tmp_path / "source.hwp"
    output_path = tmp_path / "source.hwpx"
    input_path.write_bytes(b"fake fixture; extractor is injected")
    calls = []

    def extractor(_path: Path) -> dict:
        return {
            "ok": True,
            "text": "Body A",
            "sections": [{"name": "BodyText/Section0", "text": "Body A"}],
            "feature_inventory": {"section_count": 1, "bindata_count": 0, "risk_record_tags": {}},
        }

    def fake_bridge(source: Path, output: Path) -> dict:
        calls.append((source, output))
        with ZipFile(output, "a") as zf:
            zf.writestr("Contents/header.xml", "<head/>")
            zf.writestr("Preview/BodyStyleMapping.json", "{}")
        return {
            "status": "PASS",
            "decoded_header": {"char_properties": 1, "para_properties": 1},
            "body_style_mapping": {"status": "PASS", "applied_text_paragraphs": 1},
            "entries": ["Contents/header.xml", "Preview/BodyStyleMapping.json"],
        }

    monkeypatch.setattr("hwp_to_hwpx_standalone.apply_decoded_style_bridge", fake_bridge)

    report = convert_hwp_to_hwpx(
        input_path,
        output_path,
        extractor=extractor,
        decoded_style_bridge=True,
    )

    assert report["status"] == "PASS"
    assert report["mode"] == "text_only_rebuild_with_decoded_style_bridge"
    assert report["decoded_style_bridge"]["status"] == "PASS"
    assert calls == [(input_path.resolve(), output_path.resolve())]
    with ZipFile(output_path) as zf:
        assert "Contents/header.xml" in zf.namelist()
        assert "Preview/BodyStyleMapping.json" in zf.namelist()


def test_conversion_gate_checks_visual_object_quality() -> None:
    gate = build_conversion_gate(
        {
            "status": "PASS",
            "input_info": {"exists": True, "sha256": "in", "size": 10},
            "output_info": {"exists": True, "sha256": "out", "size": 20},
            "validation": {"zip_ok": True, "xml_ok": True},
            "text_quality": {"status": "PASS", "errors": [], "warnings": []},
            "roundtrip_text": {"status": "PASS"},
            "table_grid_gate": {"status": "PASS"},
            "fidelity_gate": {"status": "WARN", "policy": "audit", "risks": []},
            "decoded_style_bridge": {
                "visual_object_mapping": {
                    "status": "PASS",
                    "target_picture_count": 2,
                    "visible_picture_count": 2,
                    "picture_record_count": 2,
                    "picture_geometry_mapped_count": 2,
                    "picture_bindata_id_mapped_count": 2,
                    "picture_position_mapped_count": 2,
                    "picture_layout_policy_mapped_count": 2,
                    "vector_shape_record_count": 1,
                    "visible_vector_shape_count": 1,
                    "geometry_mapped_vector_shape_count": 1,
                    "position_mapped_vector_shape_count": 1,
                    "layout_policy_mapped_vector_shape_count": 1,
                    "unmapped_vector_shape_record_count": 0,
                }
            },
        }
    )

    assert gate["status"] == "PASS"
    assert "visual_objects" not in gate["failed_checks"]

    failed = build_conversion_gate(
        {
            "status": "PASS",
            "input_info": {"exists": True, "sha256": "in", "size": 10},
            "output_info": {"exists": True, "sha256": "out", "size": 20},
            "validation": {"zip_ok": True, "xml_ok": True},
            "text_quality": {"status": "PASS", "errors": [], "warnings": []},
            "decoded_style_bridge": {
                "visual_object_mapping": {
                    "status": "PASS",
                    "target_picture_count": 1,
                    "visible_picture_count": 1,
                    "picture_record_count": 1,
                    "picture_geometry_mapped_count": 1,
                    "picture_bindata_id_mapped_count": 0,
                    "picture_position_mapped_count": 1,
                    "picture_layout_policy_mapped_count": 1,
                    "vector_shape_record_count": 0,
                    "visible_vector_shape_count": 0,
                    "geometry_mapped_vector_shape_count": 0,
                    "position_mapped_vector_shape_count": 0,
                    "layout_policy_mapped_vector_shape_count": 0,
                    "unmapped_vector_shape_record_count": 0,
                }
            },
        }
    )

    assert "visual_objects" in failed["failed_checks"]


def test_roundtrip_text_gate_fails_when_hwpx_omits_source_text(tmp_path: Path) -> None:
    output = tmp_path / "out.hwpx"
    write_text_hwpx(output, ["Body A"])

    gate = roundtrip_text_gate("Body A\nBody B", output)

    assert gate["status"] == "FAIL"
    assert "HWPX_TEXT_MISSING_SOURCE_LINES" in gate["errors"]
    assert gate["missing_line_samples"] == ["Body B"]


def test_read_hwpx_section_text_joins_split_runs_within_paragraph(tmp_path: Path) -> None:
    output = tmp_path / "split.hwpx"
    with ZipFile(output, "w") as zf:
        zf.writestr("mimetype", "application/vnd.hancom.hwpml")
        zf.writestr(
            "Contents/section0.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<hs:sec xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph" xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section">
  <hp:p><hp:run charPrIDRef="1"><hp:t>Bo</hp:t></hp:run><hp:run charPrIDRef="2"><hp:t>dy A</hp:t></hp:run></hp:p>
</hs:sec>""",
        )

    gate = roundtrip_text_gate("Body A", output)

    assert gate["status"] == "PASS"


def test_convert_hwp_to_hwpx_reports_extraction_failure(tmp_path: Path) -> None:
    input_path = tmp_path / "bad.hwp"
    output_path = tmp_path / "bad.hwpx"
    input_path.write_bytes(b"bad")

    report = convert_hwp_to_hwpx(
        input_path,
        output_path,
        extractor=lambda _path: {"ok": False, "error": "INPUT_NOT_HWP", "text": ""},
    )

    assert report["status"] == "FAIL"
    assert report["error"] == "INPUT_NOT_HWP"
    assert not output_path.exists()


def test_convert_hwp_to_hwpx_blocks_when_roundtrip_text_fails(monkeypatch, tmp_path: Path) -> None:
    input_path = tmp_path / "source.hwp"
    output_path = tmp_path / "source.hwpx"
    input_path.write_bytes(b"fake fixture; extractor is injected")

    def extractor(_path: Path) -> dict:
        return {
            "ok": True,
            "text": "Body A",
            "sections": [{"name": "BodyText/Section0", "text": "Body A"}],
            "feature_inventory": {"section_count": 1, "bindata_count": 0, "risk_record_tags": {}},
        }

    monkeypatch.setattr(
        "hwp_to_hwpx_standalone.roundtrip_text_gate",
        lambda *_args, **_kwargs: {
            "status": "FAIL",
            "errors": ["HWPX_TEXT_MISSING_SOURCE_LINES"],
            "warnings": [],
        },
    )

    report = convert_hwp_to_hwpx(input_path, output_path, extractor=extractor)

    assert report["status"] == "FAIL"
    assert "roundtrip_text" in report["conversion_gate"]["failed_checks"]
    assert not output_path.exists()


def test_convert_hwp_to_hwpx_does_not_overwrite_existing_output_on_quality_failure(tmp_path: Path) -> None:
    input_path = tmp_path / "source.hwp"
    output_path = tmp_path / "source.hwpx"
    input_path.write_bytes(b"fake fixture; extractor is injected")
    write_text_hwpx(output_path, ["old stable output"])

    def extractor(_path: Path) -> dict:
        return {
            "ok": True,
            "text": "new body",
            "sections": [{"name": "BodyText/Section0", "text": "new body"}],
        }

    report = convert_hwp_to_hwpx(
        input_path,
        output_path,
        extractor=extractor,
        expected_texts=["missing required text"],
    )

    assert report["status"] == "FAIL"
    assert package_contains(output_path, ["old stable output", "new body"]) == {
        "old stable output": True,
        "new body": False,
    }
    assert not list(tmp_path.glob("*.tmp"))


def test_convert_hwp_to_hwpx_renames_existing_output_when_requested(tmp_path: Path) -> None:
    input_path = tmp_path / "source.hwp"
    output_path = tmp_path / "source.hwpx"
    input_path.write_bytes(b"fake fixture; extractor is injected")
    write_text_hwpx(output_path, ["old stable output"])

    def extractor(_path: Path) -> dict:
        return {
            "ok": True,
            "text": "new body",
            "sections": [{"name": "BodyText/Section0", "text": "new body"}],
        }

    report = convert_hwp_to_hwpx(input_path, output_path, extractor=extractor, existing_policy="rename")

    assert report["status"] == "PASS"
    assert report["output"].endswith("source_1.hwpx")
    assert package_contains(output_path, ["old stable output", "new body"]) == {
        "old stable output": True,
        "new body": False,
    }
    assert package_contains(Path(report["output"]), ["new body"]) == {"new body": True}


def test_convert_batch_counts_skipped_outputs(monkeypatch, tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    output_dir.mkdir()
    first = input_dir / "a.hwp"
    second = input_dir / "b.hwp"
    first.write_bytes(b"fake-a")
    second.write_bytes(b"fake-b")
    write_text_hwpx(output_dir / "a.hwpx", ["already converted"])

    def fake_convert(input_path, output_path, **kwargs):
        if Path(output_path).exists() and kwargs["existing_policy"] == "skip":
            return {"status": "SKIP", "input": str(input_path), "output": str(output_path)}
        write_text_hwpx(output_path, [input_path.stem])
        return {"status": "PASS", "input": str(input_path), "output": str(output_path)}

    monkeypatch.setattr("hwp_to_hwpx_standalone.convert_hwp_to_hwpx", fake_convert)

    report = convert_batch(input_dir, output_dir, existing_policy="skip")

    assert report["status"] == "PASS"
    assert report["target_count"] == 2
    assert report["ok_count"] == 1
    assert report["skipped_count"] == 1
    assert report["fail_count"] == 0


def test_build_batch_plan_reports_actions_without_writing_outputs(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    output_dir.mkdir()
    source = input_dir / "a.hwp"
    source.write_bytes(b"a")
    write_text_hwpx(output_dir / "a.hwpx", ["existing"])

    plan = build_batch_plan(input_dir, output_dir, existing_policy="skip")

    assert plan["mode"] == "batch_plan"
    assert plan["target_count"] == 1
    assert plan["action_counts"] == {"SKIP": 1}
    assert plan["items"][0]["error"] == "OUTPUT_EXISTS_SKIPPED"
    assert (output_dir / "a.hwpx").exists()


def test_convert_batch_records_exception_and_continues(monkeypatch, tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    first = input_dir / "a.hwp"
    second = input_dir / "b.hwp"
    first.write_bytes(b"fake-a")
    second.write_bytes(b"fake-b")

    def fake_convert(input_path, output_path, **_kwargs):
        if Path(input_path).name == "a.hwp":
            raise RuntimeError("boom")
        write_text_hwpx(output_path, [input_path.stem])
        return {"status": "PASS", "input": str(input_path), "output": str(output_path)}

    monkeypatch.setattr("hwp_to_hwpx_standalone.convert_hwp_to_hwpx", fake_convert)

    report = convert_batch(input_dir, output_dir)

    assert report["status"] == "FAIL"
    assert report["target_count"] == 2
    assert report["ok_count"] == 1
    assert report["fail_count"] == 1
    assert report["results"][0]["error"] == "UNHANDLED_CONVERSION_EXCEPTION"
    assert report["results"][1]["status"] == "PASS"


def test_convert_batch_includes_job_metadata(monkeypatch, tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    (input_dir / "a.hwp").write_bytes(b"a")

    def fake_target(target, output, **_kwargs):
        write_text_hwpx(output, [target.stem])
        return {"status": "PASS", "input": str(target), "output": str(output)}

    monkeypatch.setattr("hwp_to_hwpx_standalone.convert_batch_target", fake_target)

    report = convert_batch(input_dir, output_dir, job_id="job-1")

    assert report["job_id"] == "job-1"
    assert report["started_at"]
    assert report["finished_at"]
    assert isinstance(report["duration_sec"], float)


def test_convert_batch_fail_fast_stops_after_first_failure(monkeypatch, tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    (input_dir / "a.hwp").write_bytes(b"fake-a")
    (input_dir / "b.hwp").write_bytes(b"fake-b")

    def fake_convert(_input_path, _output_path, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("hwp_to_hwpx_standalone.convert_hwp_to_hwpx", fake_convert)

    report = convert_batch(input_dir, output_dir, fail_fast=True)

    assert report["status"] == "FAIL"
    assert report["target_count"] == 2
    assert len(report["results"]) == 1
    assert report["fail_fast"] is True


def test_write_report_csv_writes_conversion_summary(tmp_path: Path) -> None:
    report = {
        "results": [
            {
                "status": "PASS",
                "input": "a.hwp",
                "output": "a.hwpx",
                "paragraph_count": 3,
                "text_quality": {"status": "PASS", "missing_expected_texts": []},
                "roundtrip_text": {"status": "PASS", "exact_normalized_match": True, "missing_line_count": 0},
                "table_reconstruction": {"status": "PASS", "table_count": 1},
                "fidelity_gate": {"status": "PASS", "policy": "text", "risk_count": 0},
                "validation": {"zip_ok": True, "xml_ok": True},
                "input_info": {"size": 10, "sha256": "in"},
                "output_info": {"size": 20, "sha256": "out"},
            }
        ]
    }
    csv_path = tmp_path / "report.csv"

    write_report_csv(csv_path, report)
    rows = batch_csv_rows(report)

    text = csv_path.read_text(encoding="utf-8-sig")
    assert rows[0]["status"] == "PASS"
    assert "gate_status" in text
    assert "roundtrip_status" in text
    assert "table_reconstruction_status" in text
    assert "table_grid_status" in text
    assert "fidelity_status" in text
    assert "input_sha256" in text
    assert "a.hwpx" in text


def test_fidelity_gate_warns_on_unsupported_records() -> None:
    gate = fidelity_gate(
        {
            "sections": [{"text": "body"}],
            "feature_inventory": {
                "bindata_count": 1,
                "bindata_streams": ["BinData/BIN0001.png"],
                "risk_record_tags": {"77": {"name": "TABLE", "count": 1}},
            },
        },
        policy="audit",
    )

    assert gate["status"] == "WARN"
    assert gate["risk_count"] == 2
    assert gate["full_fidelity"] is False


def test_strict_fidelity_policy_blocks_lossy_conversion(tmp_path: Path) -> None:
    input_path = tmp_path / "source.hwp"
    output_path = tmp_path / "source.hwpx"
    input_path.write_bytes(b"fake fixture; extractor is injected")

    def extractor(_path: Path) -> dict:
        return {
            "ok": True,
            "text": "Body A",
            "sections": [{"name": "BodyText/Section0", "text": "Body A"}],
            "feature_inventory": {
                "bindata_count": 0,
                "risk_record_tags": {"77": {"name": "TABLE", "count": 1}},
            },
        }

    report = convert_hwp_to_hwpx(input_path, output_path, extractor=extractor, fidelity_policy="strict")

    assert report["status"] == "FAIL"
    assert report["fidelity_gate"]["status"] == "FAIL"
    assert "fidelity_policy" in report["conversion_gate"]["failed_checks"]
    assert not output_path.exists()


def test_write_audit_log_appends_gate_summary(tmp_path: Path) -> None:
    audit_path = tmp_path / "logs" / "audit.jsonl"
    report = {
        "status": "PASS",
        "mode": "text_only_rebuild",
        "input": "a.hwp",
        "output": "a.hwpx",
        "conversion_gate": {"status": "PASS", "failed_checks": []},
    }

    write_audit_log(audit_path, report, event="unit_test")

    rows = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["event"] == "unit_test"
    assert rows[0]["conversion_gate"]["status"] == "PASS"


def test_forensic_audit_includes_digest_and_gate_details(tmp_path: Path) -> None:
    audit_path = tmp_path / "audit.jsonl"
    report = {
        "status": "PASS",
        "mode": "text_only_rebuild",
        "input": "a.hwp",
        "output": "a.hwpx",
        "input_info": {"exists": True, "sha256": "in"},
        "output_info": {"exists": True, "sha256": "out"},
        "text_quality": {"status": "PASS"},
        "fidelity_gate": {"status": "PASS", "risk_count": 0},
        "conversion_gate": {"status": "PASS", "failed_checks": []},
    }

    write_audit_log(audit_path, report, event="forensic_test", audit_level="forensic")

    row = json.loads(audit_path.read_text(encoding="utf-8").splitlines()[0])
    assert row["audit_level"] == "forensic"
    assert row["report_sha256"] == build_audit_record(report, event="forensic_test", audit_level="forensic")["report_sha256"]
    assert row["result"]["input_info"]["sha256"] == "in"
    assert row["result"]["fidelity_gate"]["status"] == "PASS"


def test_forensic_item_audit_writes_one_row_per_batch_item(tmp_path: Path) -> None:
    audit_path = tmp_path / "audit.jsonl"
    report = {
        "status": "PASS",
        "mode": "batch_text_only_rebuild",
        "job_id": "job-1",
        "results": [
            {"status": "PASS", "input": "a.hwp", "output": "a.hwpx", "conversion_gate": {"status": "PASS"}},
            {"status": "SKIP", "input": "b.hwp", "output": "b.hwpx", "conversion_gate": {"status": "PASS"}},
        ],
    }

    write_forensic_item_audit(audit_path, report, audit_level="forensic")

    rows = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
    assert [row["event"] for row in rows] == ["conversion_item", "conversion_item"]
    assert rows[0]["job_id"] == "job-1"
    assert rows[1]["item_index"] == 1


def test_conversion_writes_configured_log_file(tmp_path: Path) -> None:
    input_path = tmp_path / "source.hwp"
    output_path = tmp_path / "source.hwpx"
    log_path = tmp_path / "logs" / "hwp2hwpx.log"
    input_path.write_bytes(b"fake fixture; extractor is injected")
    configure_logging(log_path)

    def extractor(_path: Path) -> dict:
        return {
            "ok": True,
            "text": "Body A",
            "sections": [{"name": "BodyText/Section0", "text": "Body A"}],
        }

    report = convert_hwp_to_hwpx(input_path, output_path, extractor=extractor)

    assert report["status"] == "PASS"
    text = log_path.read_text(encoding="utf-8")
    assert "file_start" in text


def test_quality_gate_fails_when_expected_text_is_missing() -> None:
    quality = text_quality_gate("\uac74\ucd95\ubc95 \uc2dc\ud589\uaddc\uce59", ["permit"])

    assert quality["status"] == "FAIL"
    assert "EXPECTED_TEXT_MISSING" in quality["errors"]


def test_quality_gate_warns_on_common_mojibake_marker() -> None:
    quality = text_quality_gate("嫄댁텞踰 踰덊샇")

    assert quality["status"] == "PASS"
    assert "MOJIBAKE_MARKER_FOUND" in quality["warnings"]
    assert quality["mojibake_marker_hits"]


def test_convert_batch_preserves_relative_paths(monkeypatch, tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    nested = input_dir / "nested"
    nested.mkdir(parents=True)
    first = input_dir / "a.hwp"
    second = nested / "b.hwp"
    first.write_bytes(b"fake-a")
    second.write_bytes(b"fake-b")

    def fake_convert(input_path, output_path, **_kwargs):
        write_text_hwpx(output_path, [input_path.stem])
        return {
            "status": "PASS",
            "input": str(input_path),
            "output": str(output_path),
            "paragraph_count": 1,
            "section_count": 1,
        }

    monkeypatch.setattr("hwp_to_hwpx_standalone.convert_hwp_to_hwpx", fake_convert)

    report = convert_batch(input_dir, output_dir)

    assert report["status"] == "PASS"
    assert report["target_count"] == 2
    assert (output_dir / "a.hwpx").exists()
    assert (output_dir / "nested" / "b.hwpx").exists()


def test_convert_batch_supports_parallel_workers(monkeypatch, tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    for name in ("a.hwp", "b.hwp", "c.hwp"):
        (input_dir / name).write_bytes(name.encode("ascii"))

    def fake_target(target, output, **_kwargs):
        write_text_hwpx(output, [target.stem])
        return {"status": "PASS", "input": str(target), "output": str(output)}

    monkeypatch.setattr("hwp_to_hwpx_standalone.convert_batch_target", fake_target)

    report = convert_batch(input_dir, output_dir, workers=3)

    assert report["status"] == "PASS"
    assert report["workers"] == 3
    assert report["ok_count"] == 3
    assert [Path(row["input"]).name for row in report["results"]] == ["a.hwp", "b.hwp", "c.hwp"]


def test_convert_batch_cleans_stale_temp_files(monkeypatch, tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    output_dir.mkdir()
    (input_dir / "a.hwp").write_bytes(b"a")
    stale = output_dir / "old.hwpx.tmp"
    stale.write_bytes(b"tmp")

    def fake_target(target, output, **_kwargs):
        write_text_hwpx(output, [target.stem])
        return {"status": "PASS", "input": str(target), "output": str(output)}

    monkeypatch.setattr("hwp_to_hwpx_standalone.convert_batch_target", fake_target)

    report = convert_batch(input_dir, output_dir)

    assert report["status"] == "PASS"
    assert report["temp_cleanup"]["removed"] == 1
    assert not stale.exists()


def test_convert_batch_fail_fast_uses_single_worker_semantics(monkeypatch, tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    (input_dir / "a.hwp").write_bytes(b"a")
    (input_dir / "b.hwp").write_bytes(b"b")

    def fake_target(target, output, **_kwargs):
        return {"status": "FAIL", "input": str(target), "output": str(output), "error": "boom"}

    monkeypatch.setattr("hwp_to_hwpx_standalone.convert_batch_target", fake_target)

    report = convert_batch(input_dir, output_dir, workers=4, fail_fast=True)

    assert report["workers"] == 4
    assert report["fail_fast"] is True
    assert len(report["results"]) == 1


def test_watch_batch_detects_and_reports_new_hwp_files(monkeypatch, tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    (input_dir / "a.hwp").write_bytes(b"a")

    def fake_target(target, output, **_kwargs):
        write_text_hwpx(output, [target.stem])
        return {
            "status": "PASS",
            "input": str(target),
            "output": str(output),
            "conversion_gate": {"status": "PASS", "failed_checks": []},
        }

    monkeypatch.setattr("hwp_to_hwpx_standalone.convert_batch_target", fake_target)

    report = watch_batch(input_dir, output_dir, interval_sec=0.1, max_cycles=1)

    assert report["status"] == "PASS"
    assert report["mode"] == "watch_text_only_rebuild"
    assert report["cycle_count"] == 1
    assert report["detected_count"] == 1
    assert report["conversion_gate"]["status"] == "PASS"
    assert report["events"][0]["detected_count"] == 1
    assert report["results"][0]["detected_at"]
    assert (output_dir / "a.hwpx").exists()


def test_write_report_md_writes_realtime_summary(tmp_path: Path) -> None:
    report = {
        "status": "PASS",
        "mode": "watch_text_only_rebuild",
        "job_id": "watch-1",
        "input_dir": "input",
        "output_dir": "output",
        "cycle_count": 1,
        "detected_count": 1,
        "ok_count": 1,
        "skipped_count": 0,
        "fail_count": 0,
        "conversion_gate": {"status": "PASS", "failed_checks": []},
        "results": [
            {
                "status": "PASS",
                "input": "a.hwp",
                "output": "a.hwpx",
                "conversion_gate": {"status": "PASS", "failed_checks": []},
            }
        ],
    }
    path = tmp_path / "watch.md"

    write_report_md(path, report)

    text = path.read_text(encoding="utf-8")
    assert "Realtime Detection" in text
    assert "Detected: 1" in text
    assert "a.hwp" in build_markdown_report(report)
