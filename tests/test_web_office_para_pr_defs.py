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
    assert {"paraPrId", "tabPrIDRef", "align", "lineSpacing", "margin"} <= set(sample)
    assert any(item.get("align") for item in doc.styles.paraPrDefs.values())
    assert any(item.get("lineSpacing") for item in doc.styles.paraPrDefs.values())
    assert any(item.get("margin") for item in doc.styles.paraPrDefs.values())


def test_render_payload_exposes_para_pr_defs_read_only():
    doc = import_hwpx_as_ro_view(FIXTURE)
    payload = build_render_payload(doc)

    para_defs = payload["styles"]["paraPrDefs"]
    assert para_defs == doc.styles.paraPrDefs
    assert payload["editable"] is False
    assert all(block["editable"] is False for block in payload["blocks"])
