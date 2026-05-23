"""Tests for persistent HWPX form auto-fill gates and module communication."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.ops.install_hwpx_form_auto_fill_persistent_gates as installer  # noqa: E402


def test_01_manifests_exist() -> None:
    assert installer.MODULE_MANIFEST.is_file()
    assert installer.ZONE_MANIFEST.is_file()
    assert installer.COMM_MANIFEST.is_file()


def test_02_installer_importable() -> None:
    assert hasattr(installer, "install_persistent_gates")
    assert hasattr(installer, "validate_manifests")


def test_03_communication_manifest_covers_all_modules() -> None:
    module_manifest = json.loads(installer.MODULE_MANIFEST.read_text(encoding="utf-8"))
    comm_manifest = json.loads(installer.COMM_MANIFEST.read_text(encoding="utf-8"))
    assert installer._module_ids(module_manifest) == installer._communication_ids(comm_manifest)


def test_04_communication_zones_are_known() -> None:
    zone_manifest = json.loads(installer.ZONE_MANIFEST.read_text(encoding="utf-8"))
    comm_manifest = json.loads(installer.COMM_MANIFEST.read_text(encoding="utf-8"))
    zone_ids = installer._zone_ids(zone_manifest)
    assert all(item["zone"] in zone_ids for item in comm_manifest["modules"])


def test_05_communication_contract_is_sandbox_only() -> None:
    comm_manifest = json.loads(installer.COMM_MANIFEST.read_text(encoding="utf-8"))
    assert comm_manifest["mode"] == "SANDBOX_ONLY"
    assert comm_manifest["globalContract"]["sourceMutationAllowed"] is False
    assert comm_manifest["globalContract"]["rawPayloadAllowed"] is False
    assert comm_manifest["globalContract"]["piiPayloadAllowed"] is False
    for item in comm_manifest["modules"]:
        assert item["allowedModes"] == ["SANDBOX_ONLY"]
        assert item["sourceMutationAllowed"] is False
        assert item["rawPayloadAllowed"] is False
        assert item["piiPayloadAllowed"] is False


def test_06_unsafe_endpoints_forbidden() -> None:
    comm_manifest = json.loads(installer.COMM_MANIFEST.read_text(encoding="utf-8"))
    forbidden = set(comm_manifest["globalContract"]["forbiddenEndpoints"])
    for token in ["production-write", "source-overwrite", "final-deploy", "ai-api", "ocr-api", "hancom-only"]:
        assert token in forbidden
    for item in comm_manifest["modules"]:
        assert not (set(item.get("allowedEndpoints", [])) & forbidden)


def test_07_validate_manifests_passes() -> None:
    checks, matrix = installer.validate_manifests(
        json.loads(installer.MODULE_MANIFEST.read_text(encoding="utf-8")),
        json.loads(installer.ZONE_MANIFEST.read_text(encoding="utf-8")),
        json.loads(installer.COMM_MANIFEST.read_text(encoding="utf-8")),
    )
    assert all(item["status"] == "PASS" for item in checks)
    assert matrix["moduleCount"] == matrix["communicationCount"]
    assert not matrix["linkErrors"]
    assert not matrix["unsafeModules"]


def test_08_install_persistent_gates_writes_reports(tmp_path: Path) -> None:
    result = installer.install_persistent_gates(report_dir=tmp_path, run_smoke=False)
    assert result["verdict"] == installer.PASS_VERDICT
    assert (tmp_path / "persistent_gate_installation_summary.json").is_file()
    assert (tmp_path / "module_communication_matrix.json").is_file()
    assert (tmp_path / "persistent_gate_audit.json").is_file()
    assert installer.INSTALLATION.is_file()


def test_09_reports_have_no_leaks(tmp_path: Path) -> None:
    installer.install_persistent_gates(report_dir=tmp_path, run_smoke=False)
    for path in tmp_path.iterdir():
        text = path.read_text(encoding="utf-8")
        assert not installer.ABS_PATH_RE.search(text)
        assert not installer.RAW_FILENAME_RE.search(text)
        assert not installer.PII_RE.search(text)


def test_10_representative_smoke_passes(tmp_path: Path) -> None:
    result = installer.install_persistent_gates(report_dir=tmp_path, run_smoke=True)
    assert result["verdict"] == installer.PASS_VERDICT
    assert result["smokeRuns"]["moduleAudit"]["verdict"] == installer.module_audit.PASS_VERDICT
    assert result["smokeRuns"]["zoneGate"]["verdict"] == installer.zone_gate.PASS_VERDICT

