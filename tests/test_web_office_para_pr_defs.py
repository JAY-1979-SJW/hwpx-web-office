from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.hwpx.web_office.ro_view_importer import import_hwpx_as_ro_view  # noqa: E402
from scripts.hwpx.web_office.render_payload import build_render_payload  # noqa: E402


FIXTURE = PROJECT_ROOT / "tests" / "fixtures" / "hwpx" / "corpus" / "fx_metadata_form.hwpx"


def test_para_pr_defs_extract_paragraph_layout_fields():
    doc = import_hwpx_as_ro_view(FIXTURE)

    assert doc.styles.paraPrDefs
    sample = next(iter(doc.styles.paraPrDefs.values()))
    assert {
        "paraPrId",
        "tabPrIDRef",
        "align",
        "autoSpacing",
        "breakSetting",
        "lineSpacing",
        "margin",
        "tabPr",
        "tabItems",
    } <= set(sample)
    assert any(item.get("align") for item in doc.styles.paraPrDefs.values())
    assert any(item.get("autoSpacing") for item in doc.styles.paraPrDefs.values())
    assert any(item.get("breakSetting") for item in doc.styles.paraPrDefs.values())
    assert any(item.get("lineSpacing") for item in doc.styles.paraPrDefs.values())
    assert any(item.get("margin") for item in doc.styles.paraPrDefs.values())
    assert any(item.get("tabPr") for item in doc.styles.paraPrDefs.values())


def test_para_pr_defs_extract_auto_spacing():
    doc = import_hwpx_as_ro_view(FIXTURE)

    auto_spacing = [
        item["autoSpacing"]
        for item in doc.styles.paraPrDefs.values()
        if item.get("autoSpacing")
    ]
    assert auto_spacing
    sample = auto_spacing[0]
    assert {"eAsianEng", "eAsianNum"} <= set(sample)


def test_para_pr_defs_extract_break_setting():
    doc = import_hwpx_as_ro_view(FIXTURE)

    break_settings = [
        item["breakSetting"]
        for item in doc.styles.paraPrDefs.values()
        if item.get("breakSetting")
    ]
    assert break_settings
    sample = break_settings[0]
    assert {
        "breakLatinWord",
        "breakNonLatinWord",
        "widowOrphan",
        "keepWithNext",
        "keepLines",
        "pageBreakBefore",
        "lineWrap",
    } <= set(sample)


def test_para_pr_defs_resolve_tab_items():
    doc = import_hwpx_as_ro_view(
        PROJECT_ROOT
        / "tests"
        / "fixtures"
        / "hwpx"
        / "corpus"
        / "fx_many_tables_page_marker.hwpx"
    )

    tabbed = [
        item for item in doc.styles.paraPrDefs.values()
        if item.get("tabItems")
    ]
    assert tabbed
    first = tabbed[0]
    assert first["tabPr"]["tabPrId"] == first["tabPrIDRef"]
    assert first["tabItemCount"] == len(first["tabItems"])
    assert {"pos", "type", "leader"} <= set(first["tabItems"][0])
    assert first["tabItemCount"] == 4
    assert all(item.get("unit") == "HWPUNIT" for item in first["tabItems"])


def test_render_payload_exposes_para_pr_defs_read_only():
    doc = import_hwpx_as_ro_view(FIXTURE)
    payload = build_render_payload(doc)

    para_defs = payload["styles"]["paraPrDefs"]
    assert para_defs == doc.styles.paraPrDefs
    assert payload["editable"] is False
    assert all(block["editable"] is False for block in payload["blocks"])


def test_char_pr_defs_extract_text_style_fields():
    doc = import_hwpx_as_ro_view(FIXTURE)

    assert doc.styles.charPrDefs
    sample = next(iter(doc.styles.charPrDefs.values()))
    assert {
        "fontRef",
        "ratio",
        "spacing",
        "relSz",
        "offset",
        "bold",
        "underline",
        "underlineDef",
        "strikeout",
        "strikeoutDef",
        "shadow",
    } <= set(sample)
    assert any(item.get("fontRef") for item in doc.styles.charPrDefs.values())
    assert any(item.get("ratio") for item in doc.styles.charPrDefs.values())
    assert any(item.get("relSz") for item in doc.styles.charPrDefs.values())
    assert any(item.get("spacing") for item in doc.styles.charPrDefs.values())
    assert any(item.get("shadow") for item in doc.styles.charPrDefs.values())
    assert any("type" in item.get("underlineDef", {})
               for item in doc.styles.charPrDefs.values())
    assert any("shape" in item.get("strikeoutDef", {})
               for item in doc.styles.charPrDefs.values())


def test_render_payload_exposes_char_pr_defs_read_only():
    doc = import_hwpx_as_ro_view(FIXTURE)
    payload = build_render_payload(doc)

    char_defs = payload["styles"]["charPrDefs"]
    assert set(char_defs) == set(doc.styles.charPrDefs)
    sample = next(iter(char_defs.values()))
    assert {
        "fontRef", "ratio", "spacing", "relSz", "offset",
        "underlineDef", "strikeoutDef", "shadow",
    } <= set(sample)
    assert payload["editable"] is False


def test_font_face_defs_extract_type_info():
    doc = import_hwpx_as_ro_view(FIXTURE)
    payload = build_render_payload(doc)

    assert doc.styles.fontFaceDefs
    assert any(
        font.get("typeInfo")
        for fonts_by_id in doc.styles.fontFaceDefs.values()
        for font in fonts_by_id.values()
    )
    assert payload["styles"]["fontFaceDefs"] == doc.styles.fontFaceDefs


def test_style_defs_extract_style_catalog_refs():
    doc = import_hwpx_as_ro_view(FIXTURE)
    payload = build_render_payload(doc)

    assert doc.styles.styleDefs
    assert doc.styles.styleCount == len(doc.styles.styleDefs)
    sample = next(iter(doc.styles.styleDefs.values()))
    assert {
        "styleId",
        "type",
        "name",
        "engName",
        "paraPrIDRef",
        "charPrIDRef",
        "nextStyleIDRef",
        "langID",
        "lockForm",
        "rawAttrs",
    } <= set(sample)
    assert any(item.get("type") == "PARA" for item in doc.styles.styleDefs.values())
    assert any(item.get("paraPrIDRef") for item in doc.styles.styleDefs.values())
    assert any(item.get("charPrIDRef") for item in doc.styles.styleDefs.values())
    assert payload["styles"]["styleDefs"] == doc.styles.styleDefs


def test_table_and_cell_margin_fields_are_extracted():
    doc = import_hwpx_as_ro_view(FIXTURE)

    assert doc.tables
    assert doc.cells
    assert any(t.inMargin for t in doc.tables)
    assert any(t.outMargin for t in doc.tables)
    assert any(c.cellMargin for c in doc.cells)
    table = next(t for t in doc.tables if t.inMargin and t.outMargin)
    cell = next(c for c in doc.cells if c.cellMargin)
    assert {"left", "right", "top", "bottom"} <= set(table.inMargin)
    assert {"left", "right", "top", "bottom"} <= set(table.outMargin)
    assert {"left", "right", "top", "bottom"} <= set(cell.cellMargin)


def test_render_payload_exposes_table_and_cell_margins_read_only():
    doc = import_hwpx_as_ro_view(FIXTURE)
    payload = build_render_payload(doc)

    tables = payload["tables"]
    assert any(t.get("inMargin") for t in tables)
    assert any(t.get("outMargin") for t in tables)
    assert any(
        cell.get("cellMargin")
        for table in tables
        for cell in table.get("cells", [])
    )
    assert payload["editable"] is False


def test_section_page_layout_fields_are_extracted():
    doc = import_hwpx_as_ro_view(FIXTURE)
    payload = build_render_payload(doc)

    section = doc.sections[0]
    assert section.secPr
    assert section.pagePr
    assert section.grid
    assert section.lineNumberShape
    assert section.pageBorderFills
    assert {"width", "height", "landscape"} <= set(section.pagePr)
    assert any(item.get("offset") for item in section.pageBorderFills)

    page = payload["pages"][0]
    assert page["pagePr"] == section.pagePr
    assert page["pageBorderFills"] == section.pageBorderFills


def test_table_size_field_is_extracted():
    doc = import_hwpx_as_ro_view(FIXTURE)
    payload = build_render_payload(doc)

    assert any(t.tableSize for t in doc.tables)
    table = next(t for t in doc.tables if t.tableSize)
    assert {"width", "height"} <= set(table.tableSize)
    payload_table = next(t for t in payload["tables"] if t["tableId"] == table.tableId)
    assert payload_table["tableSize"] == table.tableSize
