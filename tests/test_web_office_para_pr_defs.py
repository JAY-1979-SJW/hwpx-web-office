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
        "relSz",
        "bold",
        "underline",
        "underlineDef",
        "strikeout",
        "strikeoutDef",
    } <= set(sample)
    assert any(item.get("fontRef") for item in doc.styles.charPrDefs.values())
    assert any(item.get("ratio") for item in doc.styles.charPrDefs.values())
    assert any(item.get("relSz") for item in doc.styles.charPrDefs.values())
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
    assert {"fontRef", "ratio", "relSz", "underlineDef", "strikeoutDef"} <= set(sample)
    assert payload["editable"] is False


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
