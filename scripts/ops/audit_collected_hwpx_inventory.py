"""COLLECTED-HWPX-FULL-INVENTORY-AND-RECOGNITION-AUDIT-01 (Phase A: Inventory)

실제 수집된 전체 HWPX 자료 inventory.
원본 파일 무수정 / DB 접근 없음 / secret 출력 없음.
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
import zipfile
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

OUTPUT_DIR = PROJECT_ROOT / "reports" / "collected_hwpx_inventory_audit"

# 수집본 후보 경로
COLLECTED_DIRS = (
    "deliverables",
    "storage",
    "uploads",
    "downloads",
    "collected",
    "collected_documents",
    "notice_documents",
    "public/uploads",
    "public/downloads",
    "var",
    "tmp/downloads",
)
# repo sample 경로
REPO_SAMPLE_DIRS = (
    "tests/fixtures",
    "tests/data",
    "fixtures",
    "samples",
    "docs",
)
EXCLUDE_PREFIXES = (
    "reports/", "tmp/", ".tmp/", "build/", "dist/",
    "node_modules/", "__pycache__/",
)


def _scan_dir(d: str, source_kind: str) -> list[Path]:
    root = PROJECT_ROOT / d
    if not root.exists():
        return []
    files = []
    for p in root.rglob("*.hwpx"):
        rel = p.relative_to(PROJECT_ROOT).as_posix()
        if any(rel.startswith(pre) for pre in EXCLUDE_PREFIXES):
            continue
        files.append(p)
    return files


def _hwpx_zip_ok(path: Path) -> bool:
    try:
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            return any(n.endswith("header.xml") for n in names)
    except Exception:
        return False


def build_inventory(skip_hash: bool = False) -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    items: list[dict] = []
    discovered_paths: list[dict] = []
    started = time.time()

    for d in COLLECTED_DIRS:
        root = PROJECT_ROOT / d
        discovered_paths.append({"path": d, "exists": root.exists(),
                                    "sourceKind": "collected"})
    for d in REPO_SAMPLE_DIRS:
        root = PROJECT_ROOT / d
        discovered_paths.append({"path": d, "exists": root.exists(),
                                    "sourceKind": "repo_sample"})

    file_id_counter = 0
    sha_to_ids: dict[str, list[str]] = defaultdict(list)

    def _process(p: Path, source_kind: str):
        nonlocal file_id_counter
        rel = p.relative_to(PROJECT_ROOT).as_posix()
        if any(rel.startswith(pre) for pre in EXCLUDE_PREFIXES):
            return
        file_id_counter += 1
        fid = f"hwpx_{file_id_counter:06d}"
        try:
            stat = p.stat()
        except Exception as exc:
            items.append({
                "fileId": fid, "sourceKind": source_kind, "sourcePath": rel,
                "originalFileName": p.name, "extension": p.suffix.lstrip("."),
                "detectedType": "hwpx", "fileSize": -1, "sha256": "",
                "mtime": -1, "exists": False, "readable": False,
                "zeroByte": False, "duplicateGroupId": None,
                "parseCandidate": False,
                "inventoryStatus": f"stat_error:{exc}",
                "notes": str(exc),
            })
            return
        size = stat.st_size
        zero = size == 0
        if skip_hash or zero:
            sha = ""
        else:
            try:
                h = hashlib.sha256()
                with open(p, "rb") as f:
                    for chunk in iter(lambda: f.read(65536), b""):
                        h.update(chunk)
                sha = h.hexdigest()
            except Exception as exc:
                sha = ""
                items.append({
                    "fileId": fid, "sourceKind": source_kind, "sourcePath": rel,
                    "originalFileName": p.name, "extension": p.suffix.lstrip("."),
                    "detectedType": "hwpx", "fileSize": size, "sha256": "",
                    "mtime": stat.st_mtime, "exists": True, "readable": False,
                    "zeroByte": zero, "duplicateGroupId": None,
                    "parseCandidate": False,
                    "inventoryStatus": f"read_error:{exc}",
                    "notes": str(exc),
                })
                return
        zip_ok = (not zero) and _hwpx_zip_ok(p)
        if sha:
            sha_to_ids[sha].append(fid)
        items.append({
            "fileId": fid, "sourceKind": source_kind, "sourcePath": rel,
            "originalFileName": p.name, "extension": p.suffix.lstrip("."),
            "detectedType": "hwpx" if zip_ok else "non_hwpx_zip",
            "fileSize": size, "sha256": sha, "mtime": stat.st_mtime,
            "exists": True, "readable": True, "zeroByte": zero,
            "duplicateGroupId": None,    # 채워질 예정
            "parseCandidate": zip_ok,
            "inventoryStatus": "ok" if zip_ok else "zip_open_failed",
            "notes": "",
        })

    for d in COLLECTED_DIRS:
        for p in _scan_dir(d, "collected"):
            _process(p, "collected")
    for d in REPO_SAMPLE_DIRS:
        for p in _scan_dir(d, "repo_sample"):
            _process(p, "repo_sample")

    # duplicate group id 채우기
    dup_group_seq = 0
    sha_to_group: dict[str, str] = {}
    for sha, ids in sha_to_ids.items():
        if len(ids) >= 2:
            dup_group_seq += 1
            sha_to_group[sha] = f"dup_{dup_group_seq:05d}"
    for item in items:
        sha = item.get("sha256")
        if sha and sha in sha_to_group:
            item["duplicateGroupId"] = sha_to_group[sha]

    elapsed = time.time() - started

    # 집계
    total = len(items)
    existing = sum(1 for i in items if i["exists"])
    missing = sum(1 for i in items if not i["exists"])
    zero = sum(1 for i in items if i["zeroByte"])
    unread = sum(1 for i in items if not i["readable"])
    parse_cands = sum(1 for i in items if i["parseCandidate"])
    unique_sha = len(sha_to_ids)
    dup_total = sum(len(ids) for ids in sha_to_ids.values() if len(ids) >= 2)
    dup_groups = sum(1 for ids in sha_to_ids.values() if len(ids) >= 2)
    collected_count = sum(1 for i in items if i["sourceKind"] == "collected")
    repo_sample_count = sum(1 for i in items if i["sourceKind"] == "repo_sample")

    summary = {
        "elapsedSeconds": round(elapsed, 2),
        "totalHwpxRecords": total,
        "totalHwpxFiles": total,
        "existingHwpxFiles": existing,
        "missingHwpxFiles": missing,
        "zeroByteHwpxFiles": zero,
        "unreadableHwpxFiles": unread,
        "duplicateHwpxFiles": dup_total,
        "duplicateGroupCount": dup_groups,
        "uniqueHwpxFiles": unique_sha,
        "parseCandidateCount": parse_cands,
        "collectedSourceCount": collected_count,
        "repoSampleSourceCount": repo_sample_count,
        "dbStatus": "DB_SKIPPED — local audit phase",
        "discoveredPaths": discovered_paths,
    }

    (OUTPUT_DIR / "inventory.json").write_text(
        json.dumps({"summary": summary, "items": items},
                       ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    md_lines = [
        "# COLLECTED-HWPX-FULL-INVENTORY-AND-RECOGNITION-AUDIT-01 — Inventory",
        "",
        "## Summary",
        f"- total: {total}",
        f"- existing: {existing} / missing: {missing}",
        f"- zeroByte: {zero} / unreadable: {unread}",
        f"- duplicateFiles: {dup_total} (in {dup_groups} groups)",
        f"- uniqueSha256: {unique_sha}",
        f"- parseCandidate: {parse_cands}",
        f"- collected source: {collected_count} / repo_sample: {repo_sample_count}",
        f"- dbStatus: DB_SKIPPED",
        f"- elapsed: {elapsed:.1f}s",
        "",
        "## Discovered paths",
        "",
        "| path | exists | sourceKind |",
        "|---|---|---|",
    ]
    for dp in discovered_paths:
        md_lines.append(f"| {dp['path']} | {dp['exists']} | {dp['sourceKind']} |")
    md_lines.append("")
    md_lines.append("## Source kind breakdown")
    md_lines.append(f"- collected: {collected_count}")
    md_lines.append(f"- repo_sample: {repo_sample_count}")
    (OUTPUT_DIR / "inventory.md").write_text("\n".join(md_lines), encoding="utf-8")

    return summary


if __name__ == "__main__":
    print("[COLLECTED-HWPX-FULL-INVENTORY-AND-RECOGNITION-AUDIT-01 — Phase A]")
    s = build_inventory()
    print(json.dumps(s, ensure_ascii=False, indent=2))
