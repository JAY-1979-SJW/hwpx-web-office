"""Common helpers for small HWP -> HWPX diagnostic scripts."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


THIS_DIR = Path(__file__).resolve().parent
HWPX_DIR = THIS_DIR.parent
SCRIPTS_DIR = HWPX_DIR.parent
REPO_ROOT = SCRIPTS_DIR.parent
for candidate in (HWPX_DIR, SCRIPTS_DIR, REPO_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))


HWP_SIGNATURE = bytes.fromhex("d0cf11e0a1b11ae1")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def status_from_errors(errors: list[str], warnings: list[str] | None = None) -> str:
    if errors:
        return "FAIL"
    if warnings:
        return "WARN"
    return "PASS"


def write_report(path: Path | None, report: dict[str, Any]) -> None:
    if not path:
        return
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def print_report(report: dict[str, Any]) -> None:
    print(json.dumps(report, ensure_ascii=False, indent=2))


def exit_code(report: dict[str, Any]) -> int:
    return 0 if report.get("status") in {"PASS", "WARN"} else 1


def read_prefix(path: Path, size: int = 8) -> bytes:
    with Path(path).open("rb") as fh:
        return fh.read(size)

