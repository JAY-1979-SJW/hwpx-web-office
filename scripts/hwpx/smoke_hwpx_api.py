#!/usr/bin/env python3
"""
HWPX API Smoke Test Script

감사 목적:
- 모든 샘플 파일을 /parse-hwpx에 POST
- HTTP status, response 검증
- API 계약 검증 (14개 키)
- 품질 지표 수집 (fullText length, blocks count 등)
- 민감정보 마스킹
"""

import os
import sys
import json
import time
import hashlib
import requests
from pathlib import Path
from datetime import datetime
from urllib.parse import urljoin

def mask_pii(text, max_length=300):
    """Mask sensitive Korean text in preview"""
    if not text:
        return ""

    if len(text) > max_length:
        text = text[:max_length] + "..."

    return text

def validate_contract_response(response_json):
    """Validate API response keys against contract v1.0"""
    required_keys = [
        "schemaVersion",
        "engineVersion",
        "requestId",
        "inputFileName",
        "inputFileType",
        "parsedAt",
        "fullText",
        "paragraphs",
        "blocks",
        "tables",
        "warningCount",
        "errorCount",
        "warnings",
        "errors",
        "ok",
    ]

    missing_keys = [key for key in required_keys if key not in response_json]
    present_keys = [key for key in required_keys if key in response_json]

    return present_keys, missing_keys

def analyze_text_quality(fulltext):
    """Analyze text quality metrics"""
    metrics = {
        "length": len(fulltext),
        "empty": len(fulltext) == 0,
        "korean_chars": sum(1 for c in fulltext if ord(c) >= 0xAC00 and ord(c) <= 0xD7A3),
        "ascii_chars": sum(1 for c in fulltext if ord(c) < 128),
        "digits": sum(1 for c in fulltext if c.isdigit()),
        "broken_chars": fulltext.count('�'),
        "xml_residue": len([1 for s in ['<hp:', '<hs:', '<hc:'] if s in fulltext]),
        "control_chars": sum(1 for c in fulltext if ord(c) < 32 and c not in '\n\r\t'),
    }

    return metrics

def smoke_hwpx_api(base_url, inventory_path, out_dir, max_preview_chars=300, include_fixtures=False):
    """Main smoke test function"""

    print(f"[smoke_hwpx_api] Starting API smoke test...", file=sys.stderr)
    print(f"[smoke_hwpx_api] Base URL: {base_url}", file=sys.stderr)
    print(f"[smoke_hwpx_api] Inventory: {inventory_path}", file=sys.stderr)

    # Load inventory
    with open(inventory_path, "r", encoding="utf-8") as f:
        inventory = json.load(f)

    # Filter samples
    samples = inventory["inventory"]
    if not include_fixtures:
        samples = [s for s in samples if not s["isFixture"]]

    print(f"[smoke_hwpx_api] Processing {len(samples)} samples...", file=sys.stderr)

    # Create output directory
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = f"{out_dir}/evidence/{run_id}"
    os.makedirs(run_dir, exist_ok=True)
    os.makedirs(f"{out_dir}/logs", exist_ok=True)

    # Test health first
    try:
        health = requests.get(f"{base_url}/health", timeout=3)
        print(f"[smoke_hwpx_api] Health check: {health.status_code}", file=sys.stderr)
    except Exception as e:
        print(f"[smoke_hwpx_api] ERROR: Health check failed: {e}", file=sys.stderr)
        return None

    # Smoke test each sample
    batch_results = []
    passed = 0
    failed = 0

    for sample in samples:
        filename = sample["filename"]
        filepath = sample["path"]

        if not Path(filepath).exists():
            print(f"[SKIP] {filename} (file not found)", file=sys.stderr)
            continue

        print(f"[POST] {filename[:50]:<50} ", end="", file=sys.stderr)

        try:
            # Read file
            with open(filepath, "rb") as f:
                file_content = f.read()

            # POST to /parse-hwpx
            start_time = time.time()
            response = requests.post(
                f"{base_url}/parse-hwpx",
                data=file_content,
                headers={"Content-Type": "application/octet-stream"},
                timeout=10,
            )
            elapsed_ms = (time.time() - start_time) * 1000

            result = {
                "filename": filename,
                "filepath": filepath,
                "sha256": sample["sha256"],
                "http_status": response.status_code,
                "elapsed_ms": round(elapsed_ms, 2),
                "response_size_bytes": len(response.text),
            }

            # Parse response
            try:
                resp_json = response.json()
                result["ok"] = resp_json.get("ok", False)
                result["errorCount"] = resp_json.get("errorCount", -1)
                result["warningCount"] = resp_json.get("warningCount", -1)
                result["errors"] = resp_json.get("errors", [])
                result["warnings"] = resp_json.get("warnings", [])

                # Contract validation
                present_keys, missing_keys = validate_contract_response(resp_json)
                result["contract_keys_present"] = len(present_keys)
                result["contract_keys_total"] = 14
                result["missing_keys"] = missing_keys

                # Extract quality metrics
                fulltext = resp_json.get("fullText", "")
                paragraphs = resp_json.get("paragraphs", [])
                blocks = resp_json.get("blocks", [])
                tables = resp_json.get("tables", [])

                result["fulltext_length"] = len(fulltext)
                result["fulltext_empty"] = len(fulltext) == 0
                result["fulltext_preview"] = mask_pii(fulltext, max_preview_chars)
                result["paragraphs_count"] = len(paragraphs)
                result["blocks_count"] = len(blocks)
                result["tables_count"] = len(tables)

                # Text quality
                text_quality = analyze_text_quality(fulltext)
                result["text_quality"] = text_quality

                # Determine pass/fail
                is_pass = (
                    response.status_code == 200
                    and result["ok"]
                    and result["errorCount"] == 0
                    and len(fulltext) > 0
                    and resp_json.get("schemaVersion") == "1.0"
                    and resp_json.get("engineVersion") == "1.0.0"
                    and text_quality["broken_chars"] == 0
                    and text_quality["xml_residue"] == 0
                )

                result["is_pass"] = is_pass

                if is_pass:
                    print(f"✅ PASS ({elapsed_ms:.0f}ms)", file=sys.stderr)
                    passed += 1
                else:
                    print(f"❌ FAIL", file=sys.stderr)
                    failed += 1
                    if missing_keys:
                        print(f"   Missing keys: {missing_keys}", file=sys.stderr)
                    if text_quality["broken_chars"] > 0:
                        print(f"   Broken chars: {text_quality['broken_chars']}", file=sys.stderr)

            except Exception as e:
                print(f"❌ JSON ERROR: {e}", file=sys.stderr)
                result["error"] = str(e)
                result["is_pass"] = False
                failed += 1

        except Exception as e:
            print(f"❌ REQUEST ERROR: {e}", file=sys.stderr)
            result = {
                "filename": filename,
                "filepath": filepath,
                "error": str(e),
                "is_pass": False,
            }
            failed += 1

        batch_results.append(result)

        # Save individual summary
        safe_name = filename.replace("/", "_").replace("\\", "_")
        summary_path = f"{run_dir}/{safe_name}.summary.json"
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

    # Generate batch summary
    batch_summary = {
        "run_id": run_id,
        "run_time": datetime.now().isoformat(),
        "base_url": base_url,
        "total_samples": len(batch_results),
        "passed": passed,
        "failed": failed,
        "pass_rate": f"{100*passed/len(batch_results):.1f}%" if batch_results else "0%",
        "results": batch_results,
    }

    # Save batch summary
    batch_json = f"{run_dir}/batch_summary.json"
    with open(batch_json, "w", encoding="utf-8") as f:
        json.dump(batch_summary, f, indent=2, ensure_ascii=False)

    # Save latest
    latest_batch = f"{out_dir}/evidence/latest_batch_summary.json"
    with open(latest_batch, "w", encoding="utf-8") as f:
        json.dump(batch_summary, f, indent=2, ensure_ascii=False)

    print(f"\n[smoke_hwpx_api] Summary:", file=sys.stderr)
    print(f"  Total: {len(batch_results)}", file=sys.stderr)
    print(f"  Passed: {passed}", file=sys.stderr)
    print(f"  Failed: {failed}", file=sys.stderr)
    print(f"  Pass rate: {batch_summary['pass_rate']}", file=sys.stderr)
    print(f"  Batch summary: {batch_json}", file=sys.stderr)

    # Determine judgment
    if passed == len(batch_results) and failed == 0:
        judgment = "CONTRACT_PASS"
    elif failed == 0 and passed > 0:
        judgment = "PASS_WITH_WARNINGS"
    else:
        judgment = "FAIL_SOME_SAMPLES"

    print(f"  Judgment: {judgment}", file=sys.stderr)

    return batch_summary, judgment

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="HWPX API Smoke Test")
    parser.add_argument("--base-url", default="http://127.0.0.1:8080", help="Base URL")
    parser.add_argument(
        "--inventory",
        default="docs/reports/hwpx_audit/inventories/hwpx_sample_inventory_latest.json",
        help="Inventory JSON path",
    )
    parser.add_argument("--out-dir", default="docs/reports/hwpx_audit", help="Output directory")
    parser.add_argument("--max-preview-chars", type=int, default=300, help="Max preview length")
    parser.add_argument("--include-fixtures", action="store_true", help="Include fixtures")

    args = parser.parse_args()

    if not Path(args.inventory).exists():
        print(f"ERROR: Inventory not found: {args.inventory}", file=sys.stderr)
        sys.exit(1)

    batch_summary, judgment = smoke_hwpx_api(
        args.base_url, args.inventory, args.out_dir, args.max_preview_chars, args.include_fixtures
    )

    # Print batch summary to stdout
    print(json.dumps(batch_summary, indent=2, ensure_ascii=False))
