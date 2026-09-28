#!/usr/bin/env python3
"""
HWPX Sample Inventory Audit Script

감사 목적:
- 모든 .hwpx 파일 자동 검색
- SHA256 해시 계산
- 파일 메타데이터 수집
- fixture/real sample 분류
- 중복 감지
"""

import sys
import json
import hashlib
import argparse
from pathlib import Path
from datetime import datetime

def calculate_sha256(filepath, chunk_size=65536):
    """Calculate SHA256 hash of file"""
    sha256_hash = hashlib.sha256()
    try:
        with Path(filepath).open("rb") as f:
            for chunk in iter(lambda: f.read(chunk_size), b""):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()
    except Exception as e:  # noqa: BLE001 -- 이 단계만 기록 후 계속
        return f"ERROR: {str(e)}"

def is_fixture(filepath, filename):
    """Determine if file is a test fixture"""
    fixture_patterns = [
        "smoke-test",
        "test",
        "fixture",
        "p1f-validate",
        "p1g-validate",
    ]

    filepath_lower = str(filepath).lower()
    filename_lower = filename.lower()

    # src/test/resources 하위면 fixture
    if "src/test/resources" in filepath_lower:
        return True

    # 파일명에 패턴 있으면 fixture
    for pattern in fixture_patterns:
        if pattern in filename_lower:
            return True

    return False

def estimate_category(filename):
    """Estimate sample category from filename"""
    filename_lower = filename.lower()

    if "별지" in filename or "form" in filename_lower:
        return "form"
    elif "별표" in filename or "standard" in filename_lower:
        return "standard"
    else:
        return "unknown"

def find_all_hwpx_files(sample_root):
    """Find all .hwpx files in sample root"""
    hwpx_files = []
    search_dirs = [
        Path(sample_root) / "samples",
        Path(sample_root) / "samples/hwpx-real",
        Path(sample_root) / "docs/samples",
        Path(sample_root) / "src/test/resources",
        Path("samples"),
    ]

    visited = set()

    for search_dir in search_dirs:
        if not search_dir.exists():
            continue

        try:
            for hwpx_file in search_dir.glob("**/*.hwpx"):
                # Normalize path
                abs_path = hwpx_file.resolve()
                if abs_path in visited:
                    continue
                visited.add(abs_path)
                hwpx_files.append(hwpx_file)
        except Exception as e:  # noqa: BLE001 -- 이 단계만 기록 후 계속
            print(f"Warning: Error scanning {search_dir}: {e}", file=sys.stderr)

    return sorted(hwpx_files)

def audit_hwpx_samples(sample_root=".", output_dir="docs/reports/hwpx_audit"):
    """Main audit function"""

    print("[audit_hwpx_samples] Starting inventory audit...", file=sys.stderr)
    print(f"[audit_hwpx_samples] Sample root: {sample_root}", file=sys.stderr)

    # Find all HWPX files
    hwpx_files = find_all_hwpx_files(sample_root)
    print(f"[audit_hwpx_samples] Found {len(hwpx_files)} HWPX files", file=sys.stderr)

    # Create output directory
    Path(f"{output_dir}/inventories").mkdir(exist_ok=True, parents=True)
    Path(f"{output_dir}/logs").mkdir(exist_ok=True, parents=True)

    # Collect metadata
    inventory = []
    hash_groups = {}
    filename_groups = {}

    for idx, hwpx_file in enumerate(hwpx_files, 1):
        filename = hwpx_file.name
        filepath = str(hwpx_file)
        try:
            relative_path = str(hwpx_file.relative_to(Path.cwd()))
        except ValueError:
            # If file is not relative to cwd, try from parent
            cwd = Path.cwd()
            abs_file = hwpx_file.resolve()
            abs_cwd = cwd.resolve()
            try:
                relative_path = str(abs_file.relative_to(abs_cwd))
            except ValueError:
                relative_path = filepath

        # File stats
        stat = hwpx_file.stat()
        size_bytes = stat.st_size
        mtime = datetime.fromtimestamp(stat.st_mtime).isoformat()

        # Calculate SHA256
        sha256 = calculate_sha256(filepath)

        # Classify
        is_fixture_bool = is_fixture(filepath, filename)
        category = estimate_category(filename)

        item = {
            "index": idx,
            "filename": filename,
            "path": filepath,
            "relativePath": relative_path,
            "sizeBytes": size_bytes,
            "sha256": sha256,
            "modifiedTime": mtime,
            "isFixture": is_fixture_bool,
            "sampleCategory": category,
        }

        inventory.append(item)

        # Track hashes for duplicate detection
        if sha256 != "ERROR" and not is_fixture_bool:
            if sha256 not in hash_groups:
                hash_groups[sha256] = []
            hash_groups[sha256].append(filename)

        # Track filenames
        if filename not in filename_groups:
            filename_groups[filename] = []
        filename_groups[filename].append(filepath)

        print(f"[{idx:2d}/27] {filename[:60]:<60} {size_bytes:>10} bytes", file=sys.stderr)

    # Generate report
    audit_time = datetime.now().isoformat()

    real_samples = [item for item in inventory if not item["isFixture"]]
    fixtures = [item for item in inventory if item["isFixture"]]

    report = {
        "auditTime": audit_time,
        "totalFiles": len(inventory),
        "realSamples": len(real_samples),
        "fixtures": len(fixtures),
        "inventory": inventory,
        "duplicateHashes": {k: v for k, v in hash_groups.items() if len(v) > 1},
        "sameFilenames": {k: v for k, v in filename_groups.items() if len(v) > 1},
    }

    # Save JSON
    json_path = f"{output_dir}/inventories/hwpx_sample_inventory_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with Path(json_path).open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    # Save latest symlink equivalent
    latest_json = f"{output_dir}/inventories/hwpx_sample_inventory_latest.json"
    with Path(latest_json).open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    # Generate Markdown report
    md_path = f"{output_dir}/inventories/hwpx_sample_inventory_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    with Path(md_path).open("w", encoding="utf-8") as f:
        f.write("# HWPX Sample Inventory\n\n")
        f.write(f"**Audit Time**: {audit_time}\n\n")
        f.write("## Summary\n\n")
        f.write("| 구분 | 개수 |\n")
        f.write("|------|------|\n")
        f.write(f"| Total | {report['totalFiles']} |\n")
        f.write(f"| Real Samples | {report['realSamples']} |\n")
        f.write(f"| Fixtures | {report['fixtures']} |\n\n")

        f.write("## Inventory\n\n")
        f.write("| # | Filename | Size (B) | Category | Fixture |\n")
        f.write("|---|----------|----------|----------|----------|\n")
        for item in inventory:
            is_fixture_mark = "✅" if item["isFixture"] else "❌"
            f.write(f"| {item['index']:2d} | {item['filename'][:50]} | {item['sizeBytes']:>10} | {item['sampleCategory']:<10} | {is_fixture_mark} |\n")

        f.write("\n## SHA256 Hashes\n\n")
        for item in real_samples:
            f.write(f"- `{item['sha256']}`  {item['filename']}\n")

    # Save latest MD
    latest_md = f"{output_dir}/inventories/hwpx_sample_inventory_latest.md"
    with Path(latest_md).open("w", encoding="utf-8") as f:
        with Path(md_path).open("r", encoding="utf-8") as src:
            f.write(src.read())

    print("\n[audit_hwpx_samples] Results:", file=sys.stderr)
    print(f"  Real samples: {report['realSamples']}", file=sys.stderr)
    print(f"  Fixtures: {report['fixtures']}", file=sys.stderr)
    print(f"  JSON: {latest_json}", file=sys.stderr)
    print(f"  MD: {latest_md}", file=sys.stderr)

    # Determine judgment
    if report['realSamples'] >= 1:
        judgment = "PASS"
    else:
        judgment = "WARN_REAL_SAMPLE_NOT_FOUND"

    if any(item.get("sha256", "").startswith("ERROR") for item in real_samples):
        judgment = "FAIL_SHA256_MISSING"

    print(f"  Judgment: {judgment}", file=sys.stderr)

    return report, judgment

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="HWPX Sample Inventory Audit")
    parser.add_argument("--sample-root", default=".", help="Sample root directory")
    parser.add_argument("--out-dir", default="docs/reports/hwpx_audit", help="Output directory")

    args = parser.parse_args()

    report, judgment = audit_hwpx_samples(args.sample_root, args.out_dir)

    # Print final JSON to stdout
    print(json.dumps(report, indent=2, ensure_ascii=False))
