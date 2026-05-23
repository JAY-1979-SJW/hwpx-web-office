"""Install repo-local git hooks for commit and prepush guards."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

HOOKS_DIR = ROOT / ".githooks"
REPORT_DIR = ROOT / "data" / "reports" / "hwpx_repo_guard_hooks"

PASS_VERDICT = "PASS_HWPX_REPO_GUARD_HOOKS_INSTALLED"
FAIL_VERDICT = "FAIL_HWPX_REPO_GUARD_HOOKS_INSTALLED"

PRE_COMMIT_SCRIPT = """#!/usr/bin/env sh
python scripts/ops/run_hwpx_repo_commit_guard.py --temp-only
"""

PRE_PUSH_SCRIPT = """#!/usr/bin/env sh
python scripts/ops/run_hwpx_repo_prepush_guard.py --temp-only
"""


def install_repo_guard_hooks(report_dir: Path = REPORT_DIR, configure_git: bool = False) -> dict[str, Any]:
    HOOKS_DIR.mkdir(parents=True, exist_ok=True)
    pre_commit = HOOKS_DIR / "pre-commit"
    pre_push = HOOKS_DIR / "pre-push"
    pre_commit.write_text(PRE_COMMIT_SCRIPT, encoding="utf-8", newline="\n")
    pre_push.write_text(PRE_PUSH_SCRIPT, encoding="utf-8", newline="\n")
    configured = False
    hooks_path = None
    if configure_git:
        subprocess.run(["git", "config", "core.hooksPath", ".githooks"], cwd=str(ROOT), check=True, timeout=30)
        configured = True
        hooks_path = ".githooks"
    payload = {
        "schemaVersion": "hwpx_repo_guard_hooks_installation_v1",
        "verdict": PASS_VERDICT,
        "summary": {
            "hooksInstalled": 2,
            "gitConfigUpdated": configured,
        },
        "hooks": {
            "preCommit": ".githooks/pre-commit",
            "prePush": ".githooks/pre-push",
            "coreHooksPath": hooks_path,
        },
        "security": {
            "piiLeak": 0,
            "rawPathLeak": 0,
            "rawFilenameLeak": 0,
        },
        "warnings": [
            "WARN_GIT_HOOKS_LOCAL_REPO_ONLY",
            "WARN_PREPUSH_GUARD_RUNS_FAIL_FAST_SMOKE",
        ],
    }
    _write_reports(report_dir, payload)
    return payload


def _no_leak(text: str) -> bool:
    return not (
        "C:\\" in text
        or "/Users/" in text
        or ".hwpx" in text
    )


def _safe_write(path: Path, payload: Any) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if not _no_leak(text):
        raise ValueError(f"unsafe hook installation payload: {path.name}")
    path.write_text(text, encoding="utf-8")


def _write_reports(report_dir: Path, payload: dict[str, Any]) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    _safe_write(report_dir / "repo_guard_hooks_installation_summary.json", payload)
    lines = [
        "# HWPX Repo Guard Hooks",
        "",
        f"- verdict: {payload['verdict']}",
        f"- hooks installed: {payload['summary']['hooksInstalled']}",
        f"- git config updated: {payload['summary']['gitConfigUpdated']}",
        f"- pre-commit: {payload['hooks']['preCommit']}",
        f"- pre-push: {payload['hooks']['prePush']}",
    ]
    text = "\n".join(lines) + "\n"
    if not _no_leak(text):
        raise ValueError("unsafe hook installation markdown")
    (report_dir / "repo_guard_hooks_installation_summary.md").write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", default=str(REPORT_DIR))
    parser.add_argument("--configure-git", action="store_true")
    args = parser.parse_args()
    payload = install_repo_guard_hooks(report_dir=Path(args.report_dir), configure_git=args.configure_git)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["verdict"] == PASS_VERDICT else 1


if __name__ == "__main__":
    raise SystemExit(main())
