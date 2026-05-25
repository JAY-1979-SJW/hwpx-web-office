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

    assert payload["verdict"] == PASS_VERDICT
    assert payload["statusValue"] == STATUS_VALUE
    assert payload["fullCompatibilityClaimed"] is False
    assert payload["serverFinalReferenceRequired"] is True
    assert payload["corpus"]["hwpxFileCount"] >= 3
    assert payload["corpus"]["manifestFound"] is True
    assert payload["coverageSummary"]["unsupportedWithWarningCount"] >= 1
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
    assert "Unsupported Element Families" in md_path.read_text(encoding="utf-8")


def test_read_remediation_audit_does_not_mutate_fixtures(tmp_path):
    payload = run_audit(report_dir=tmp_path)

    assert payload["failures"] == []
    for result in payload["fixtures"]:
        assert result["sourceUnchanged"] is True
        assert result["verdict"] == "PASS"
