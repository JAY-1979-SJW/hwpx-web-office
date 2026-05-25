"""Contract tests for Web Office app structure drift audit."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.ops import audit_web_office_app_structure_drift as audit_mod  # noqa: E402


def test_app_structure_drift_audit_passes() -> None:
    payload = audit_mod.audit()
    assert payload["verdict"] == audit_mod.PASS_VERDICT, payload["findings"]
    assert payload["summary"]["failures"] == 0


def test_required_endpoints_are_locked() -> None:
    payload = audit_mod.audit()
    assert payload["implementedEndpoints"] == sorted(audit_mod.REQUIRED_ENDPOINTS)


def test_required_paths_exist_and_are_documented() -> None:
    doc_text = audit_mod.APP_STRUCTURE_DOC.read_text(encoding="utf-8")
    for rel_path in audit_mod.REQUIRED_PATHS:
        assert (ROOT / rel_path).is_file(), rel_path
        assert rel_path in doc_text, rel_path


def test_public_security_contract_is_locked() -> None:
    api_source = audit_mod.API_ROUTE.read_text(encoding="utf-8")
    assert 'MODE = "SANDBOX_ONLY"' in api_source
    assert '"sourceMutationAllowed": False' in api_source
    assert 'safe.pop("outputPath", None)' in api_source
