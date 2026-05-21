#!/usr/bin/env python3
"""Build promotion evidence from a user-present Hancom conversion result."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hwpx_package import HwpxValidator


HWP_OLE_SIGNATURE = bytes.fromhex("D0CF11E0A1B11AE1")


def read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError("result JSON must be an object")
    return data


def has_hwp_binary_signature(path: Path) -> bool:
    try:
        return path.read_bytes()[: len(HWP_OLE_SIGNATURE)] == HWP_OLE_SIGNATURE
    except OSError:
        return False


def build_output_validation(output_path: Path) -> dict[str, Any]:
    report = HwpxValidator.validate_hwpx(output_path)
    zip_ok = report.get("zip_ok") is True
    xml_ok = report.get("xml_ok") is True
    status = "PASS" if zip_ok and xml_ok else "FAIL"
    return {
        "status": status,
        "zip_ok": zip_ok,
        "xml_ok": xml_ok,
        "source": "HwpxValidator.validate_hwpx",
        "details": report,
    }


def build_promotion_evidence(
    result: dict[str, Any],
    *,
    execution_approved: bool,
    input_path: str | None = None,
    output_path: str | None = None,
) -> dict[str, Any]:
    resolved_input = str(Path(input_path or str(result.get("input_path") or "")).expanduser()) if (input_path or result.get("input_path")) else ""
    input_valid = has_hwp_binary_signature(Path(resolved_input).expanduser()) if resolved_input else False
    resolved_output = Path(output_path or str(result.get("output_path") or "")).expanduser()
    validation = build_output_validation(resolved_output)
    result_ok = result.get("ok") is True
    result_status = str(result.get("status") or "")
    output_valid = validation["zip_ok"] is True and validation["xml_ok"] is True
    one_file_success = result_ok and result_status == "USER_PRESENT_OUTPUT_VALID" and output_valid and input_valid

    return {
        "provider": "user_present",
        "input_path": resolved_input,
        "output_path": str(resolved_output),
        "one_file_success": one_file_success,
        "execution_approved": execution_approved,
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "output_validation": validation,
        "input_validation": {
            "status": "PASS" if input_valid else "FAIL",
            "hwp_binary_signature_ok": input_valid,
        },
        "source_result": {
            "path": result.get("_path"),
            "provider": result.get("provider"),
            "stage": result.get("stage"),
            "status": result_status,
            "output_exists": result.get("output_exists"),
            "output_size": result.get("output_size"),
            "zip_valid": result.get("zip_valid"),
            "zip_entries": result.get("zip_entries"),
            "zip_error": result.get("zip_error"),
            "started_at": result.get("started_at"),
            "finished_at": result.get("finished_at"),
            "warnings": result.get("warnings", []),
        },
        "notes": "Generated from user_present_result.json. execution_approved must only be true after an approved one-file user-present conversion.",
    }


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def run(args: argparse.Namespace) -> dict[str, Any]:
    result_path = Path(args.result_json).expanduser().resolve()
    result = read_json(result_path)
    result["_path"] = str(result_path)
    evidence = build_promotion_evidence(
        result,
        execution_approved=bool(args.execution_approved),
        input_path=args.input_path,
        output_path=args.output_path,
    )
    evidence_path = Path(args.evidence_json).expanduser().resolve()
    write_json(evidence_path, evidence)
    return {
        "status": "PASS" if evidence["one_file_success"] else "FAIL",
        "evidence_json": str(evidence_path),
        "one_file_success": evidence["one_file_success"],
        "execution_approved": evidence["execution_approved"],
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result-json", required=True, help="Path to user_present_result.json")
    parser.add_argument("--evidence-json", required=True, help="Path to write promotion evidence JSON")
    parser.add_argument("--input-path", help="Override input path recorded in result JSON")
    parser.add_argument("--output-path", help="Override output path recorded in result JSON")
    parser.add_argument(
        "--execution-approved",
        action="store_true",
        help="Mark evidence as approved for promotion after a real one-file user-present run",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        result = run(parse_args(argv))
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"status": "FAIL", "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
