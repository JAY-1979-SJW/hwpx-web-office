from __future__ import annotations

import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from hwpx_edit_tool import (
    apply_edit_plan,
    batch_apply,
    create_hwpx_document,
    inspect_hwpx,
    validate_create_plan,
    validate_edit_plan,
    write_batch_html,
    write_inspection_html,
)
from hwpx_package import HwpxPackage, HwpxValidator, package_contains
from hwpx_table_ops import get_table_cell_matrix


def write_edit_sample(path: Path) -> None:
    section = """<?xml version="1.0" encoding="UTF-8"?>
<hp:sec xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">
  <hp:p><hp:run><hp:t>{{PROJECT}}</hp:t></hp:run></hp:p>
  <hp:tbl>
    <hp:tr>
      <hp:tc><hp:p><hp:run><hp:t>label</hp:t></hp:run></hp:p><hp:cellAddr rowAddr="0" colAddr="0" /><hp:cellSpan rowSpan="1" colSpan="1" /></hp:tc>
      <hp:tc><hp:p><hp:run><hp:t>old</hp:t></hp:run></hp:p><hp:cellAddr rowAddr="0" colAddr="1" /><hp:cellSpan rowSpan="1" colSpan="1" /></hp:tc>
    </hp:tr>
    <hp:tr>
      <hp:tc><hp:p><hp:run><hp:t>merged</hp:t></hp:run></hp:p><hp:cellAddr rowAddr="3" colAddr="4" /><hp:cellSpan rowSpan="1" colSpan="2" /></hp:tc>
      <hp:tc><hp:p><hp:run><hp:linesegarray /></hp:run></hp:p><hp:cellAddr rowAddr="3" colAddr="6" /><hp:cellSpan rowSpan="1" colSpan="1" /></hp:tc>
    </hp:tr>
  </hp:tbl>
</hp:sec>
"""
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", "application/hwp+zip")
        zf.writestr(
            "version.xml",
            '<hv:HCFVersion xmlns:hv="http://www.hancom.co.kr/hwpml/2011/version" Version="5.0.0.0" />',
        )
        zf.writestr(
            "Contents/content.hpf",
            """<?xml version="1.0" encoding="UTF-8"?>
<opf:package xmlns:opf="http://www.idpf.org/2007/opf" version="3.0">
  <opf:manifest>
    <opf:item id="section0" href="Contents/section0.xml" media-type="application/xml" />
    <opf:item id="settings" href="settings.xml" media-type="application/xml" />
  </opf:manifest>
  <opf:spine><opf:itemref idref="section0" /></opf:spine>
</opf:package>
""",
        )
        zf.writestr(
            "META-INF/container.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<ocf:container xmlns:ocf="urn:oasis:names:tc:opendocument:xmlns:container">
  <ocf:rootfiles><ocf:rootfile full-path="Contents/content.hpf" media-type="application/hwpml-package+xml" /></ocf:rootfiles>
</ocf:container>
""",
        )
        zf.writestr("META-INF/manifest.xml", '<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0" />')
        zf.writestr("settings.xml", "<settings />")
        zf.writestr("Contents/section0.xml", section)


def test_inspect_hwpx_builds_editable_map(tmp_path: Path) -> None:
    path = tmp_path / "sample.hwpx"
    html_path = tmp_path / "inspect.html"
    write_edit_sample(path)

    report = inspect_hwpx(path)
    write_inspection_html(report, html_path)

    assert report["gate"]["status"] == "PASS"
    assert report["entries"]["section_count"] == 1
    assert report["placeholders"]["tokens"]["PROJECT"] == 1
    assert report["tables"][0]["cell_count"] == 4
    assert report["tables"][0]["cells"][2]["visual_row"] == 3
    assert html_path.exists()


def test_apply_edit_plan_updates_placeholders_and_visual_cells(tmp_path: Path) -> None:
    source = tmp_path / "sample.hwpx"
    output = tmp_path / "updated.hwpx"
    write_edit_sample(source)
    plan = {
        "replace_placeholders": {"PROJECT": "Fire Safety Review"},
        "set_visual_cells": [{"table": 0, "visual_row": 3, "visual_col": 6, "value": "created"}],
        "set_cells": [{"table": 0, "row": 0, "col": 1, "value": "changed"}],
    }

    report = apply_edit_plan(source, output, plan)
    matrix = get_table_cell_matrix(HwpxPackage(output), 0)

    assert report["status"] == "PASS"
    assert package_contains(output, ["Fire Safety Review"])["Fire Safety Review"]
    assert matrix["rows"][0]["cells"][1]["text"] == "changed"
    assert matrix["rows"][1]["cells"][1]["text"] == "created"


def test_apply_edit_plan_supports_text_and_label_based_cell_edits(tmp_path: Path) -> None:
    source = tmp_path / "sample.hwpx"
    output = tmp_path / "updated.hwpx"
    write_edit_sample(source)
    plan = {
        "replace_text": [{"old": "{{PROJECT}}", "new": "Direct Text"}],
        "set_cells_by_label": [{"label": "label", "value": "by-label"}],
        "set_cells_by_text": [{"exact": "merged", "value": "by-search"}],
    }

    report = apply_edit_plan(source, output, plan)
    matrix = get_table_cell_matrix(HwpxPackage(output), 0)

    assert report["status"] == "PASS"
    assert package_contains(output, ["Direct Text"])["Direct Text"]
    assert matrix["rows"][0]["cells"][1]["text"] == "by-label"
    assert matrix["rows"][1]["cells"][0]["text"] == "by-search"


def test_apply_edit_plan_dry_run_does_not_write_output(tmp_path: Path) -> None:
    source = tmp_path / "sample.hwpx"
    output = tmp_path / "dryrun.hwpx"
    write_edit_sample(source)

    report = apply_edit_plan(source, output, {"set_cells_by_label": [{"label": "label", "value": "preview"}]}, dry_run=True)

    assert report["status"] == "PASS"
    assert report["dry_run"] is True
    assert report["output"] is None
    assert not output.exists()
    assert report["inspection"]["tables"][0]["cells"][1]["text"] == "preview"


def test_apply_edit_plan_dry_run_inserts_generated_jpeg_picture(tmp_path: Path) -> None:
    source = tmp_path / "sample.hwpx"
    output = tmp_path / "dryrun_picture.hwpx"
    photo = tmp_path / "phone.jpeg"
    write_edit_sample(source)
    photo.write_bytes(b"\xff\xd8\xff\xd9")

    report = apply_edit_plan(
        source,
        output,
        {
            "insert_generated_pictures": [
                {"path": str(photo), "entry": "BinData/photo_001.jpg", "width": 12000, "height": 9000}
            ]
        },
        dry_run=True,
    )

    assert report["status"] == "PASS"
    assert report["dry_run"] is True
    assert report["output"] is None
    assert not output.exists()
    assert report["operations"][0]["status"] == "GENERATED_PNG_PICTURE_INSERT_PASS"
    assert any(image["entry_name"] == "BinData/photo_001.jpg" for image in report["inspection"]["media"]["images"])


def test_hwpx_validation_reports_package_consistency_errors(tmp_path: Path) -> None:
    source = tmp_path / "broken.hwpx"
    with zipfile.ZipFile(source, "w") as zf:
        zf.writestr("mimetype", "application/hwp+zip")
        zf.writestr("Contents/section0.xml", "<sec />")

    validation = HwpxValidator.validate_hwpx(source)

    assert validation["zip_ok"] is True
    assert validation["xml_ok"] is True
    assert validation["package_consistency"]["status"] == "FAIL"
    assert any(error["code"] == "REQUIRED_ENTRY_MISSING" for error in validation["package_consistency"]["errors"])


def test_apply_edit_plan_reports_before_after_diff(tmp_path: Path) -> None:
    source = tmp_path / "sample.hwpx"
    output = tmp_path / "updated.hwpx"
    write_edit_sample(source)

    report = apply_edit_plan(source, output, {"set_cells_by_label": [{"label": "label", "value": "diff-value"}]})

    assert report["status"] == "PASS"
    assert report["diff"]["cell_change_count"] == 1
    assert report["diff"]["cell_changes"][0]["before"] == "old"
    assert report["diff"]["cell_changes"][0]["after"] == "diff-value"


def test_validate_edit_plan_rejects_missing_selector() -> None:
    report = validate_edit_plan({"set_cells_by_text": [{"value": "x"}]})

    assert report["status"] == "FAIL"
    assert report["errors"][0]["path"] == "set_cells_by_text[0]"


def test_batch_apply_edits_folder_and_writes_html(tmp_path: Path) -> None:
    input_dir = tmp_path / "in"
    output_dir = tmp_path / "out"
    html_path = tmp_path / "batch.html"
    input_dir.mkdir()
    write_edit_sample(input_dir / "a.hwpx")
    write_edit_sample(input_dir / "b.hwpx")

    report = batch_apply(input_dir, output_dir, {"set_cells_by_label": [{"label": "label", "value": "batch-value"}]})
    write_batch_html(report, html_path)

    assert report["status"] == "PASS"
    assert report["target_count"] == 2
    assert report["pass_count"] == 2
    assert (output_dir / "a.hwpx").exists()
    assert (output_dir / "b.hwpx").exists()
    assert html_path.exists()
    matrix = get_table_cell_matrix(HwpxPackage(output_dir / "a.hwpx"), 0)
    assert matrix["rows"][0]["cells"][1]["text"] == "batch-value"


def test_create_hwpx_document_builds_new_paragraph_and_table_document(tmp_path: Path) -> None:
    output = tmp_path / "created.hwpx"
    plan = {
        "metadata": {"title": "Created from editor"},
        "sections": [
            {
                "blocks": [
                    {"type": "paragraph", "text": "신규 문서"},
                    {"type": "table", "rows": [["항목", "값"], ["공사명", "테스트"]]},
                ]
            }
        ],
    }

    report = create_hwpx_document(output, plan, base_dir=tmp_path)
    matrix = get_table_cell_matrix(HwpxPackage(output), 0)

    assert report["status"] == "PASS"
    assert report["summary"]["sections"] == 1
    assert report["summary"]["tables"] == 1
    assert matrix["rows"][1]["cells"][1]["text"] == "테스트"


def test_create_hwpx_document_accepts_editor_generated_tables(tmp_path: Path) -> None:
    output = tmp_path / "created_from_editor.hwpx"
    plan = {
        "metadata": {"title": "Browser editor"},
        "paragraphs": ["Browser editor document", "Body"],
        "append_generated_tables": [{"rows": [["Item", "Value"], ["A", "100"]]}],
    }

    report = create_hwpx_document(output, plan, base_dir=tmp_path)
    matrix = get_table_cell_matrix(HwpxPackage(output), 0)

    assert report["status"] == "PASS"
    assert report["summary"]["tables"] == 1
    assert package_contains(output, ["Browser editor document"])["Browser editor document"]
    assert matrix["rows"][1]["cells"][1]["text"] == "100"


def test_validate_create_plan_rejects_empty_plan() -> None:
    report = validate_create_plan({})

    assert report["status"] == "FAIL"
    assert report["errors"][0]["path"] == "paragraphs"
