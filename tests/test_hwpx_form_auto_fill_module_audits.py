"""Tests for HWPX form auto-fill module audit runner."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.ops.audit_hwpx_form_auto_fill_modules as module_audit  # noqa: E402


def test_01_manifest_exists() -> None:
    assert module_audit.MANIFEST.is_file()


def test_02_manifest_has_expected_modules() -> None:
    manifest = module_audit.load_manifest()
    module_ids = {module["id"] for module in manifest["modules"]}
    for expected in [
        "field_mapping",
        "review_panel",
        "approval_gate",
        "writer_sandbox",
        "readback_hardening",
        "download_review",
        "final_export_gate",
        "api_batch",
        "api_browser_e2e",
        "user_flow_closeout",
    ]:
        assert expected in module_ids


def test_03_manifest_paths_exist() -> None:
    manifest = module_audit.load_manifest()
    for module in manifest["modules"]:
        for key in ["sourceFiles", "testFiles", "auditFiles"]:
            for rel_path in module.get(key, []):
                assert (ROOT / rel_path).is_file(), rel_path


def test_04_runner_importable() -> None:
    assert hasattr(module_audit, "run_module_audits")
    assert hasattr(module_audit, "audit_module")


def test_05_single_module_audit_passes(tmp_path: Path) -> None:
    result = module_audit.run_module_audits(report_dir=tmp_path, module_ids={"field_mapping"}, timeout=120)
    assert result["verdict"] == module_audit.PASS_VERDICT
    assert result["summary"]["modulesTotal"] == 1
    assert result["moduleResults"][0]["id"] == "field_mapping"


def test_06_report_files_written(tmp_path: Path) -> None:
    module_audit.run_module_audits(report_dir=tmp_path, module_ids={"review_panel"}, timeout=120)
    assert (tmp_path / "module_audit_summary.json").is_file()
    assert (tmp_path / "module_audit_results.json").is_file()
    assert (tmp_path / "module_audit_summary.md").is_file()


def test_07_report_has_no_leak_patterns(tmp_path: Path) -> None:
    module_audit.run_module_audits(report_dir=tmp_path, module_ids={"approval_gate"}, timeout=120)
    text = (tmp_path / "module_audit_summary.json").read_text(encoding="utf-8")
    assert not module_audit.ABS_PATH_RE.search(text)
    assert not module_audit.RAW_FILENAME_RE.search(text)
    assert not module_audit.PII_RE.search(text)


def test_08_manifest_is_valid_json() -> None:
    json.loads(module_audit.MANIFEST.read_text(encoding="utf-8"))


def test_09_windows_pytest_cleanup_permission_is_nonblocking() -> None:
    output = (
        ".................................... [100%]\n"
        "86 passed, 22 warnings, 22 errors in 23.86s\n"
        "PermissionError: [WinError 5] access is denied"
    )
    assert module_audit._is_pytest_cleanup_permission_only(output)


def test_10_pytest_timeout_is_structured_failure(monkeypatch) -> None:
    def timeout_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=kwargs.get("args", "pytest"), timeout=1)

    monkeypatch.setattr(module_audit.subprocess, "run", timeout_run)
    result = module_audit._run_pytest(["tests/test_hwpx_approval_gate.py"], timeout=1)

    assert result["status"] == "FAIL"
    assert result["returncode"] == -9
    assert "timed out" in result["summary"]


def test_11_combined_pytest_timeout_is_structured_failure(monkeypatch) -> None:
    def timeout_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=kwargs.get("args", "pytest"), timeout=1)

    monkeypatch.setattr(module_audit.subprocess, "run", timeout_run)
    result = module_audit._run_pytest_combined(
        ["tests/test_hwpx_approval_gate.py"],
        timeout=1,
    )

    assert result["status"] == "FAIL"
    assert result["returncode"] == -9
    assert "timed out" in result["summary"]
