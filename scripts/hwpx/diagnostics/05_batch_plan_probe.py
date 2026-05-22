#!/usr/bin/env python3
"""Check batch discovery, output collision policy, and dry-run gate."""

from __future__ import annotations

import argparse
from pathlib import Path

from hwp_diag_common import exit_code, print_report, status_from_errors, utc_now, write_report
from hwp_to_hwpx_standalone import EXISTING_POLICIES, build_batch_plan


def check_batch_plan_probe(input_dir: Path, output_dir: Path, pattern: str, existing_policy: str) -> dict:
    input_dir = Path(input_dir).expanduser().resolve()
    output_dir = Path(output_dir).expanduser().resolve()
    plan = build_batch_plan(input_dir, output_dir, pattern=pattern, existing_policy=existing_policy)
    errors: list[str] = []
    warnings: list[str] = []
    if plan.get("conversion_gate", {}).get("status") == "FAIL":
        errors.append("PLAN_GATE_FAILED")
    if int(plan.get("target_count") or 0) == 0:
        warnings.append("NO_HWP_TARGETS")
    if plan.get("action_counts", {}).get("FAIL"):
        warnings.append("OUTPUT_COLLISION_BLOCKERS")
    return {
        "status": status_from_errors(errors, warnings),
        "tool": "05_batch_plan_probe",
        "checked_at": utc_now(),
        "input_dir": str(input_dir),
        "output_dir": str(output_dir),
        "pattern": pattern,
        "existing_policy": existing_policy,
        "plan": plan,
        "errors": errors,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--pattern", default="*.hwp")
    parser.add_argument("--existing-policy", choices=EXISTING_POLICIES, default="fail")
    parser.add_argument("--report-json", type=Path)
    args = parser.parse_args()
    report = check_batch_plan_probe(args.input_dir, args.output_dir, args.pattern, args.existing_policy)
    write_report(args.report_json, report)
    print_report(report)
    return exit_code(report)


if __name__ == "__main__":
    raise SystemExit(main())

