from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.ops.audit_web_office_hwpx_read_remediation import (  # noqa: E402
    PASS_VERDICT,
    STATUS_VALUE,
    run_audit,
)


def test_read_remediation_audit_reports_current_scope(tmp_path):
    payload = run_audit(report_dir=tmp_path)
    category_summary = payload["coverageSummary"]["unsupportedCategorySummary"]

    assert payload["verdict"] == PASS_VERDICT
    assert payload["statusValue"] == STATUS_VALUE
    assert payload["fullCompatibilityClaimed"] is False
    assert payload["serverFinalReferenceRequired"] is True
    assert payload["corpus"]["hwpxFileCount"] >= 3
    assert payload["corpus"]["manifestFound"] is True
    assert payload["coverageSummary"]["unsupportedWithWarningCount"] >= 1
    assert category_summary["categoryCount"] >= 5
    assert "paragraph_layout" not in category_summary["categories"]
    assert "text_style" in category_summary["categories"]
    assert "page_layout" in category_summary["categories"]
    assert "unknown_review_required" not in category_summary["categories"]
    assert payload["requiredWording"] == (
        "Basic HWPX read is verified; full compatibility and UI fidelity remain open."
    )


def test_read_remediation_audit_writes_machine_and_human_reports(tmp_path):
    payload = run_audit(report_dir=tmp_path)

    json_path = tmp_path / "reading_remediation_report.json"
    md_path = tmp_path / "reading_remediation_summary.md"

    assert json_path.is_file()
    assert md_path.is_file()
    written = json.loads(json_path.read_text(encoding="utf-8"))
    assert written["verdict"] == payload["verdict"]
    md_text = md_path.read_text(encoding="utf-8")
    assert "Unsupported Element Families" in md_text
    assert "Unsupported Category Summary" in md_text
    assert "text_style" in md_text


def test_read_remediation_audit_attaches_category_to_unsupported_elements(tmp_path):
    payload = run_audit(report_dir=tmp_path)

    for result in payload["fixtures"]:
        classifications = result["packageInventory"]["elementClassifications"]
        unsupported = [
            item
            for item in classifications.values()
            if item["classification"] == "unsupported_with_warning"
        ]
        assert unsupported
        assert all(item["unsupportedCategory"] for item in unsupported)
        assert all(
            item["unsupportedCategory"] != "unknown_review_required"
            for item in unsupported
        )


def test_read_remediation_audit_does_not_mutate_fixtures(tmp_path):
    payload = run_audit(report_dir=tmp_path)

    assert payload["failures"] == []
    for result in payload["fixtures"]:
        assert result["sourceUnchanged"] is True
        assert result["verdict"] == "PASS"
