"""Tests for repo guard hook scripts and installer."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.ops.install_hwpx_repo_guard_hooks as hook_installer  # noqa: E402
import scripts.ops.run_hwpx_repo_commit_guard as commit_guard  # noqa: E402
import scripts.ops.run_hwpx_repo_prepush_guard as prepush_guard  # noqa: E402


def test_01_scripts_importable() -> None:
    assert hasattr(commit_guard, "run_commit_guard")
    assert hasattr(prepush_guard, "run_prepush_guard")
    assert hasattr(hook_installer, "install_repo_guard_hooks")


def test_02_commit_guard_evaluate_passes() -> None:
    payload = commit_guard.evaluate_commit_guard(
        {"verdict": "PASS_HWPX_REPO_NEW_FILE_CLASSIFICATION_GATE", "summary": {"newFiles": 0}},
        {"verdict": "PASS_HWPX_REPO_CLASSIFICATION_CONTRACT_GATE", "summary": {"stablePathMappedFiles": 0}},
        {"verdict": "PASS_HWPX_REPO_MANIFEST_PROMOTION_CANDIDATES", "summary": {"manifestPromotionCandidates": 0}},
        {"verdict": "PASS_HWPX_REPO_MANIFEST_DRIFT_ZERO_GATE"},
    )
    assert payload["verdict"] == commit_guard.PASS_VERDICT


def test_03_commit_guard_evaluate_fails() -> None:
    payload = commit_guard.evaluate_commit_guard(
        {"verdict": "FAIL"},
        {"verdict": "PASS_HWPX_REPO_CLASSIFICATION_CONTRACT_GATE", "summary": {"stablePathMappedFiles": 0}},
        {"verdict": "PASS_HWPX_REPO_MANIFEST_PROMOTION_CANDIDATES", "summary": {"manifestPromotionCandidates": 0}},
        {"verdict": "PASS_HWPX_REPO_MANIFEST_DRIFT_ZERO_GATE"},
    )
    assert payload["verdict"] == commit_guard.FAIL_VERDICT
    assert "FAIL_NEW_FILE_CLASSIFICATION" in payload["failures"]


def test_04_prepush_guard_evaluate_passes() -> None:
    payload = prepush_guard.evaluate_prepush_guard(
        {
            "verdict": "PASS_HWPX_FORM_AUTO_FILL_FAIL_FAST_GATE",
            "summary": {"stepsTotal": 1, "stepsFailed": 0},
            "repoManifestDriftZeroVerdict": "PASS_HWPX_REPO_MANIFEST_DRIFT_ZERO_GATE",
        }
    )
    assert payload["verdict"] == prepush_guard.PASS_VERDICT


def test_05_hook_installer_writes_files(tmp_path: Path) -> None:
    original_hooks_dir = hook_installer.HOOKS_DIR
    try:
        hook_installer.HOOKS_DIR = tmp_path / ".githooks"
        result = hook_installer.install_repo_guard_hooks(report_dir=tmp_path, configure_git=False)
        assert result["verdict"] == hook_installer.PASS_VERDICT
        assert (hook_installer.HOOKS_DIR / "pre-commit").is_file()
        assert (hook_installer.HOOKS_DIR / "pre-push").is_file()
    finally:
        hook_installer.HOOKS_DIR = original_hooks_dir


def test_06_hook_scripts_exist_in_repo() -> None:
    assert (ROOT / ".githooks" / "pre-commit").is_file()
    assert (ROOT / ".githooks" / "pre-push").is_file()


def test_07_reports_are_written(tmp_path: Path) -> None:
    original_hooks_dir = hook_installer.HOOKS_DIR
    try:
        hook_installer.HOOKS_DIR = tmp_path / ".githooks"
        hook_installer.install_repo_guard_hooks(report_dir=tmp_path, configure_git=False)
        assert (tmp_path / "repo_guard_hooks_installation_summary.json").is_file()
        assert (tmp_path / "repo_guard_hooks_installation_summary.md").is_file()
    finally:
        hook_installer.HOOKS_DIR = original_hooks_dir


def test_08_reports_have_no_leaks(tmp_path: Path) -> None:
    original_hooks_dir = hook_installer.HOOKS_DIR
    try:
        hook_installer.HOOKS_DIR = tmp_path / ".githooks"
        hook_installer.install_repo_guard_hooks(report_dir=tmp_path, configure_git=False)
        for path in tmp_path.iterdir():
            if path.is_file():
                text = path.read_text(encoding="utf-8")
                assert "C:\\" not in text
                assert "/Users/" not in text
    finally:
        hook_installer.HOOKS_DIR = original_hooks_dir


def test_09_json_report_valid(tmp_path: Path) -> None:
    original_hooks_dir = hook_installer.HOOKS_DIR
    try:
        hook_installer.HOOKS_DIR = tmp_path / ".githooks"
        hook_installer.install_repo_guard_hooks(report_dir=tmp_path, configure_git=False)
        json.loads((tmp_path / "repo_guard_hooks_installation_summary.json").read_text(encoding="utf-8"))
    finally:
        hook_installer.HOOKS_DIR = original_hooks_dir
