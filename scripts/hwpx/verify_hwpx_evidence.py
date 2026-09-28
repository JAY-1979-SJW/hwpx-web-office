#!/usr/bin/env python3
"""
HWPX Evidence Verification Script

감사 목적:
- inventory, batch summary, 개별 sample summary 교차 검증
- 27개 샘플 파일 존재 확인
- SHA256 일관성 확인
- 파싱 결과 완전성 확인
- 최종 PASS/WARN/FAIL 판정
"""

import sys
import json
from pathlib import Path
from datetime import datetime

def verify_evidence(inventory_path, batch_summary_path, sample_dir):
    """Main verification function"""

    print("[verify_hwpx_evidence] Starting evidence verification...", file=sys.stderr)
    print(f"[verify_hwpx_evidence] Inventory: {inventory_path}", file=sys.stderr)
    print(f"[verify_hwpx_evidence] Batch summary: {batch_summary_path}", file=sys.stderr)
    print(f"[verify_hwpx_evidence] Sample dir: {sample_dir}", file=sys.stderr)

    # Load inventory
    with Path(inventory_path).open("r", encoding="utf-8") as f:
        inventory = json.load(f)

    real_samples = [s for s in inventory["inventory"] if not s["isFixture"]]
    inventory_count = len(real_samples)

    print(f"[verify_hwpx_evidence] Inventory real samples: {inventory_count}", file=sys.stderr)

    # Load batch summary
    with Path(batch_summary_path).open("r", encoding="utf-8") as f:
        batch_summary = json.load(f)

    batch_count = len(batch_summary["results"])
    batch_passed = sum(1 for r in batch_summary["results"] if r.get("is_pass", False))

    print(f"[verify_hwpx_evidence] Batch results: {batch_count} ({batch_passed} passed)", file=sys.stderr)

    # Cross-validation
    validation_result = {
        "verificationTime": datetime.now().isoformat(),
        "inventoryCount": inventory_count,
        "batchCount": batch_count,
        "batchPassed": batch_passed,
        "checks": {},
        "warnings": [],
        "failures": [],
        "judgment": "PASS",
    }

    # Check 1: Count match
    if inventory_count == batch_count:
        validation_result["checks"]["count_match"] = "PASS"
    else:
        validation_result["checks"]["count_match"] = "FAIL"
        validation_result["failures"].append(f"Count mismatch: inventory={inventory_count}, batch={batch_count}")
        validation_result["judgment"] = "FAIL"

    # Check 2: All samples parsed
    if batch_passed == batch_count:
        validation_result["checks"]["all_parsed"] = "PASS"
    else:
        validation_result["checks"]["all_parsed"] = "FAIL"
        validation_result["failures"].append(f"Parse failures: {batch_count - batch_passed}/{batch_count}")
        validation_result["judgment"] = "FAIL"

    # Check 3: SHA256 consistency
    inventory_hashes = {s["filename"]: s["sha256"] for s in real_samples}
    batch_files = {r["filename"]: r.get("sha256") for r in batch_summary["results"]}

    hash_mismatches = []
    for filename, batch_hash in batch_files.items():
        inv_hash = inventory_hashes.get(filename)
        if inv_hash and batch_hash != inv_hash:
            hash_mismatches.append(filename)

    if not hash_mismatches:
        validation_result["checks"]["sha256_consistency"] = "PASS"
    else:
        validation_result["checks"]["sha256_consistency"] = "WARN"
        validation_result["warnings"].append(f"SHA256 mismatches: {hash_mismatches}")

    # Check 4: No errors
    all_errors = []
    for result in batch_summary["results"]:
        if result.get("errorCount", 0) > 0:
            all_errors.extend(result.get("errors", []))

    if not all_errors:
        validation_result["checks"]["no_errors"] = "PASS"
    else:
        validation_result["checks"]["no_errors"] = "FAIL"
        validation_result["failures"].append(f"Parse errors found: {all_errors}")
        validation_result["judgment"] = "FAIL"

    # Check 5: No broken chars
    total_broken_chars = sum(
        r.get("text_quality", {}).get("broken_chars", 0) for r in batch_summary["results"]
    )

    if total_broken_chars == 0:
        validation_result["checks"]["no_broken_chars"] = "PASS"
    else:
        validation_result["checks"]["no_broken_chars"] = "WARN"
        validation_result["warnings"].append(f"Broken chars found: {total_broken_chars}")

    # Check 6: No XML residue
    total_xml_residue = sum(
        r.get("text_quality", {}).get("xml_residue", 0) for r in batch_summary["results"]
    )

    if total_xml_residue == 0:
        validation_result["checks"]["no_xml_residue"] = "PASS"
    else:
        validation_result["checks"]["no_xml_residue"] = "WARN"
        validation_result["warnings"].append(f"XML residue found: {total_xml_residue}")

    # Check 7: Contract compliance
    contract_violations = []
    for result in batch_summary["results"]:
        missing = result.get("missing_keys", [])
        if missing:
            contract_violations.append(f"{result['filename']}: missing {missing}")

    if not contract_violations:
        validation_result["checks"]["contract_compliance"] = "PASS"
    else:
        validation_result["checks"]["contract_compliance"] = "WARN"
        validation_result["warnings"].append(f"Contract violations: {contract_violations}")

    # Check 8: Tables (expected to be 0)
    total_tables = sum(r.get("tables_count", 0) for r in batch_summary["results"])

    if total_tables == 0:
        validation_result["checks"]["table_count"] = "TABLE_NOT_VERIFIED_WARN"
        validation_result["warnings"].append("No table samples (text-based forms only)")
    else:
        validation_result["checks"]["table_count"] = f"TABLES_FOUND({total_tables})"

    # Check 9: Sample files exist
    missing_sample_files = []
    for sample in real_samples:
        if not Path(sample["path"]).exists():
            missing_sample_files.append(sample["filename"])

    if not missing_sample_files:
        validation_result["checks"]["sample_files_exist"] = "PASS"
    else:
        validation_result["checks"]["sample_files_exist"] = "FAIL"
        validation_result["failures"].append(f"Missing sample files: {missing_sample_files}")
        validation_result["judgment"] = "FAIL"

    # Check 10: Individual summary files exist
    missing_summaries = []
    for result in batch_summary["results"]:
        safe_name = result["filename"].replace("/", "_").replace("\\", "_")
        summary_path = f"{sample_dir}/{safe_name}.summary.json"
        if not Path(summary_path).exists():
            missing_summaries.append(summary_path)

    if not missing_summaries:
        validation_result["checks"]["individual_summaries"] = "PASS"
    else:
        validation_result["checks"]["individual_summaries"] = "WARN"
        validation_result["warnings"].append(f"Missing individual summaries: {len(missing_summaries)}")

    # Final judgment
    if validation_result["judgment"] == "PASS":
        if validation_result["warnings"]:
            validation_result["judgment"] = "PASS_WITH_WARNINGS"
        else:
            validation_result["judgment"] = "EVIDENCE_COMPLETE_PASS"

    print("\n[verify_hwpx_evidence] Checks:", file=sys.stderr)
    for check_name, check_result in validation_result["checks"].items():
        print(f"  {check_name}: {check_result}", file=sys.stderr)

    print(f"\n[verify_hwpx_evidence] Judgment: {validation_result['judgment']}", file=sys.stderr)

    if validation_result["warnings"]:
        print("[verify_hwpx_evidence] Warnings:", file=sys.stderr)
        for warning in validation_result["warnings"]:
            print(f"  - {warning}", file=sys.stderr)

    if validation_result["failures"]:
        print("[verify_hwpx_evidence] Failures:", file=sys.stderr)
        for failure in validation_result["failures"]:
            print(f"  - {failure}", file=sys.stderr)

    return validation_result

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="HWPX Evidence Verification")
    parser.add_argument(
        "--inventory",
        default="docs/reports/hwpx_audit/inventories/hwpx_sample_inventory_latest.json",
        help="Inventory JSON path",
    )
    parser.add_argument(
        "--batch-summary",
        default="docs/reports/hwpx_audit/evidence/latest_batch_summary.json",
        help="Batch summary JSON path",
    )
    parser.add_argument(
        "--sample-dir",
        default="docs/reports/hwpx_audit/evidence",
        help="Sample directory (for finding individual summaries)",
    )
    parser.add_argument("--out-dir", default="docs/reports/hwpx_audit/summaries", help="Output directory")

    args = parser.parse_args()

    if not Path(args.inventory).exists():
        print(f"ERROR: Inventory not found: {args.inventory}", file=sys.stderr)
        sys.exit(1)

    if not Path(args.batch_summary).exists():
        print(f"ERROR: Batch summary not found: {args.batch_summary}", file=sys.stderr)
        sys.exit(1)

    verification_result = verify_evidence(args.inventory, args.batch_summary, args.sample_dir)

    # Save results
    Path(args.out_dir).mkdir(exist_ok=True, parents=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = f"{args.out_dir}/hwpx_evidence_verification_{timestamp}.json"
    with Path(json_path).open("w", encoding="utf-8") as f:
        json.dump(verification_result, f, indent=2, ensure_ascii=False)

    # Save latest
    latest_json = f"{args.out_dir}/hwpx_evidence_verification_latest.json"
    with Path(latest_json).open("w", encoding="utf-8") as f:
        json.dump(verification_result, f, indent=2, ensure_ascii=False)

    # Generate Markdown report
    md_path = f"{args.out_dir}/hwpx_evidence_verification_{timestamp}.md"
    with Path(md_path).open("w", encoding="utf-8") as f:
        f.write("# HWPX Evidence Verification Report\n\n")
        f.write(f"**Verification Time**: {verification_result['verificationTime']}\n\n")
        f.write("## Summary\n\n")
        f.write("| 항목 | 값 |\n")
        f.write("|-----|-----|\n")
        f.write(f"| Inventory Real Samples | {verification_result['inventoryCount']} |\n")
        f.write(f"| Batch Results | {verification_result['batchCount']} |\n")
        f.write(f"| Batch Passed | {verification_result['batchPassed']} |\n")
        f.write(f"| Judgment | {verification_result['judgment']} |\n\n")

        f.write("## Checks\n\n")
        for check_name, check_result in verification_result["checks"].items():
            f.write(f"- {check_name}: {check_result}\n")

        if verification_result["warnings"]:
            f.write("\n## Warnings\n\n")
            for warning in verification_result["warnings"]:
                f.write(f"- {warning}\n")

        if verification_result["failures"]:
            f.write("\n## Failures\n\n")
            for failure in verification_result["failures"]:
                f.write(f"- {failure}\n")

    # Save latest MD
    latest_md = f"{args.out_dir}/hwpx_evidence_verification_latest.md"
    with Path(latest_md).open("w", encoding="utf-8") as f:
        with Path(md_path).open("r", encoding="utf-8") as src:
            f.write(src.read())

    print(json.dumps(verification_result, indent=2, ensure_ascii=False))
