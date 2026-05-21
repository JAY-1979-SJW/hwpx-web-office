#!/usr/bin/env python3
"""Audit UTF decoding and mojibake risk in HWPX XML and text files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from hwpx_package import audit_hwpx_encoding, audit_text_bytes


def audit_file(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    audit = audit_text_bytes(raw)
    return {
        "path": str(path),
        "exists": True,
        "size": len(raw),
        **audit,
        "status": "PASS" if audit["decode_ok"] and audit["quality"]["ok"] else "FAIL",
    }


def audit_path(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "exists": False, "status": "FAIL", "error": "FILE_NOT_FOUND"}
    if path.suffix.lower() == ".hwpx":
        result = audit_hwpx_encoding(path)
        result["type"] = "hwpx"
        return result
    result = audit_file(path)
    result["type"] = "text"
    return result


def run(paths: list[Path]) -> dict[str, Any]:
    results = [audit_path(path) for path in paths]
    failed = [item for item in results if item.get("status") != "PASS"]
    return {
        "status": "PASS" if not failed else "FAIL",
        "checked": len(results),
        "failed": len(failed),
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--report-json", type=Path)
    args = parser.parse_args()

    report = run(args.paths)
    if args.report_json:
        args.report_json.parent.mkdir(parents=True, exist_ok=True)
        args.report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
