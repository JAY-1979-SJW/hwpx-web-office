#!/usr/bin/env python3
"""
HWPX Security Defense Test

감사 목적:
- Invalid ZIP 거부 확인
- Non-HWPX ZIP 거부 확인
- Empty file 거부 확인
- 안전한 에러 처리 확인 (500 발생 방지)
"""

import os
import sys
import json
import zipfile
import tempfile
import requests
from pathlib import Path
from datetime import datetime

__test__ = False

def create_invalid_zip():
    """Create invalid ZIP file (not valid ZIP format)"""
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as f:
        f.write(b"This is not a valid ZIP file content")
        return f.name

def create_non_hwpx_zip():
    """Create valid ZIP but without HWPX structure"""
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as f:
        temp_path = f.name

    with zipfile.ZipFile(temp_path, "w") as zf:
        zf.writestr("readme.txt", "This is a normal ZIP file")
        zf.writestr("data.json", '{"key": "value"}')

    return temp_path

def create_empty_hwpx():
    """Create empty HWPX file (0 bytes)"""
    with tempfile.NamedTemporaryFile(suffix=".hwpx", delete=False) as f:
        return f.name

def run_security_smoke(base_url, out_dir):
    """Main security test function"""

    print(f"[test_hwpx_security] Starting security tests...", file=sys.stderr)
    print(f"[test_hwpx_security] Base URL: {base_url}", file=sys.stderr)

    # Create test files
    print(f"[test_hwpx_security] Creating test files...", file=sys.stderr)

    invalid_zip_path = create_invalid_zip()
    non_hwpx_zip_path = create_non_hwpx_zip()
    empty_hwpx_path = create_empty_hwpx()

    print(f"  Invalid ZIP: {invalid_zip_path}", file=sys.stderr)
    print(f"  Non-HWPX ZIP: {non_hwpx_zip_path}", file=sys.stderr)
    print(f"  Empty HWPX: {empty_hwpx_path}", file=sys.stderr)

    test_cases = [
        {
            "name": "Invalid ZIP (not ZIP format)",
            "filepath": invalid_zip_path,
            "expected_ok": False,
            "expect_error": True,
        },
        {
            "name": "Non-HWPX ZIP (valid ZIP, no HWPX structure)",
            "filepath": non_hwpx_zip_path,
            "expected_ok": False,
            "expect_error": True,
        },
        {
            "name": "Empty HWPX file",
            "filepath": empty_hwpx_path,
            "expected_ok": False,
            "expect_error": True,
        },
    ]

    os.makedirs(out_dir, exist_ok=True)

    results = []

    for test_case in test_cases:
        print(f"[TEST] {test_case['name']:<40} ", end="", file=sys.stderr)

        test_name = test_case["name"]
        filepath = test_case["filepath"]
        expected_ok = test_case["expected_ok"]

        try:
            with open(filepath, "rb") as f:
                file_content = f.read()

            response = requests.post(
                f"{base_url}/parse-hwpx",
                data=file_content,
                headers={"Content-Type": "application/octet-stream"},
                timeout=10,
            )

            result = {
                "test_name": test_name,
                "http_status": response.status_code,
                "response_size": len(response.text),
            }

            try:
                resp_json = response.json()
                result["ok"] = resp_json.get("ok", None)
                result["errorCount"] = resp_json.get("errorCount", -1)
                result["errors"] = resp_json.get("errors", [])

                # Check: ok should be False
                if not resp_json.get("ok", True):
                    result["ok_check"] = "PASS"
                    print(f"✅ PASS (ok=false)", file=sys.stderr)
                else:
                    result["ok_check"] = "FAIL"
                    print(f"❌ FAIL (ok should be false)", file=sys.stderr)

                # Check: should have errors
                if resp_json.get("errorCount", 0) > 0:
                    result["error_check"] = "PASS"
                else:
                    result["error_check"] = "WARN"
                    print(f"   Warning: No errors reported", file=sys.stderr)

                # Check: HTTP status
                if 200 <= response.status_code < 300:
                    result["http_check"] = "PASS"
                elif 400 <= response.status_code < 500:
                    result["http_check"] = "PASS"
                else:
                    result["http_check"] = "FAIL"
                    print(f"   ERROR: HTTP {response.status_code}", file=sys.stderr)

                result["is_pass"] = (
                    result.get("ok_check") == "PASS"
                    and result.get("http_check") == "PASS"
                )

            except Exception as e:
                print(f"❌ JSON ERROR: {e}", file=sys.stderr)
                result["error"] = str(e)
                result["is_pass"] = False

        except Exception as e:
            print(f"❌ REQUEST ERROR: {e}", file=sys.stderr)
            result = {
                "test_name": test_name,
                "error": str(e),
                "is_pass": False,
            }

        results.append(result)

    # Cleanup
    print(f"[test_hwpx_security] Cleaning up temp files...", file=sys.stderr)
    for path in [invalid_zip_path, non_hwpx_zip_path, empty_hwpx_path]:
        try:
            os.remove(path)
        except:
            pass

    # Generate summary
    summary = {
        "test_time": datetime.now().isoformat(),
        "base_url": base_url,
        "total_tests": len(results),
        "passed": sum(1 for r in results if r.get("is_pass", False)),
        "failed": sum(1 for r in results if not r.get("is_pass", False)),
        "results": results,
    }

    summary["pass_rate"] = f"{100*summary['passed']/len(results):.1f}%" if results else "0%"

    # Determine judgment
    if summary["failed"] == 0:
        summary["judgment"] = "SECURITY_PASS"
    else:
        summary["judgment"] = "SECURITY_FAIL"

    # Save summary
    json_path = f"{out_dir}/negative_smoke_summary.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    # Generate Markdown report
    md_path = f"{out_dir}/negative_smoke_summary.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# HWPX Security Defense Test\n\n")
        f.write(f"**Test Time**: {summary['test_time']}\n\n")
        f.write(f"## Summary\n\n")
        f.write(f"| 항목 | 결과 |\n")
        f.write(f"|-----|------|\n")
        f.write(f"| Total Tests | {summary['total_tests']} |\n")
        f.write(f"| Passed | {summary['passed']} |\n")
        f.write(f"| Failed | {summary['failed']} |\n")
        f.write(f"| Pass Rate | {summary['pass_rate']} |\n")
        f.write(f"| Judgment | {summary['judgment']} |\n\n")

        f.write(f"## Test Results\n\n")
        for result in results:
            status = "✅" if result.get("is_pass", False) else "❌"
            f.write(f"{status} {result['test_name']}\n")
            if result.get("ok_check"):
                f.write(f"  - ok_check: {result['ok_check']}\n")
            if result.get("error_check"):
                f.write(f"  - error_check: {result['error_check']}\n")
            if result.get("http_check"):
                f.write(f"  - http_check: {result['http_check']}\n")
            if result.get("errors"):
                f.write(f"  - errors: {result['errors']}\n")

    print(f"\n[test_hwpx_security] Summary:", file=sys.stderr)
    print(f"  Total: {summary['total_tests']}", file=sys.stderr)
    print(f"  Passed: {summary['passed']}", file=sys.stderr)
    print(f"  Failed: {summary['failed']}", file=sys.stderr)
    print(f"  Pass rate: {summary['pass_rate']}", file=sys.stderr)
    print(f"  Judgment: {summary['judgment']}", file=sys.stderr)
    print(f"  JSON: {json_path}", file=sys.stderr)
    print(f"  MD: {md_path}", file=sys.stderr)

    return summary

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="HWPX Security Defense Test")
    parser.add_argument("--base-url", default="http://127.0.0.1:8080", help="Base URL")
    parser.add_argument("--out-dir", default="docs/reports/hwpx_audit/evidence", help="Output directory")

    args = parser.parse_args()

    summary = run_security_smoke(args.base_url, args.out_dir)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
