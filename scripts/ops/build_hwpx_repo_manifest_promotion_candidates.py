"""Build manifest promotion candidates from repo classification contract results."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.ops import classify_hwpx_repo_inventory as inventory  # noqa: E402
from scripts.ops import gate_hwpx_repo_classification_contract as contract_gate  # noqa: E402

REPORT_DIR = ROOT / "data" / "reports" / "hwpx_repo_manifest_promotion_candidates"

PASS_VERDICT = "PASS_HWPX_REPO_MANIFEST_PROMOTION_CANDIDATES"
FAIL_VERDICT = "FAIL_HWPX_REPO_MANIFEST_PROMOTION_CANDIDATES"

FAIL_CONTRACT_GATE = "FAIL_CONTRACT_GATE"
FAIL_PROMOTION_TARGET_UNRESOLVED = "FAIL_PROMOTION_TARGET_UNRESOLVED"


def _promotion_target_key(path: str) -> str | None:
    normalized = path.replace("\\", "/")
    if normalized.startswith("tests/"):
        return "testFiles"
    if normalized.startswith("scripts/ops/audit_"):
        return "auditFiles"
    if normalized.startswith(("scripts/", "frontend/", "docs/")):
        return "sourceFiles"
    return None


def _unsafe_path_map(contract_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    mapping: dict[str, dict[str, Any]] = {}
    for item in contract_payload.get("existingFileResults", []):
        mapping[item["safePath"]] = item
    return mapping


def evaluate_manifest_promotion_candidates(
    contract_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    contract = contract_payload or contract_gate.run_repo_classification_contract_gate()
    path_map = _unsafe_path_map(contract)
    candidates: list[dict[str, Any]] = []
    failures: set[str] = set()
    for item in contract.get("manifestPromotionCandidates", []):
        safe_path = item["safePath"]
        existing = path_map.get(safe_path, {})
        target_key = _promotion_target_key(safe_path)
        if not item.get("moduleId") or not target_key:
            failures.add(FAIL_PROMOTION_TARGET_UNRESOLVED)
        candidates.append(
            {
                "safePath": safe_path,
                "zone": item["zone"],
                "moduleId": item.get("moduleId"),
                "targetKey": target_key,
                "category": existing.get("category"),
                "separationPlan": existing.get("separationPlan"),
            }
        )
    key_counts = Counter(item["targetKey"] or "unresolved" for item in candidates)
    module_counts = Counter(item["moduleId"] or "unresolved" for item in candidates)
    if contract.get("verdict") != contract_gate.PASS_VERDICT:
        failures.add(FAIL_CONTRACT_GATE)
    return {
        "schemaVersion": "hwpx_repo_manifest_promotion_candidates_v1",
        "verdict": PASS_VERDICT if not failures else FAIL_VERDICT,
        "contractVerdict": contract.get("verdict"),
        "summary": {
            "trackedFiles": contract.get("summary", {}).get("trackedFiles", 0),
            "stablePathMappedFiles": contract.get("summary", {}).get("stablePathMappedFiles", 0),
            "manifestPromotionCandidates": len(candidates),
            "modulesAffected": len([key for key in module_counts if key != "unresolved"]),
            "sourceCandidates": key_counts.get("sourceFiles", 0),
            "testCandidates": key_counts.get("testFiles", 0),
            "auditCandidates": key_counts.get("auditFiles", 0),
            "unresolvedCandidates": key_counts.get("unresolved", 0),
        },
        "candidates": candidates,
        "moduleBreakdown": dict(sorted(module_counts.items())),
        "failures": sorted(failures),
        "security": {
            "piiLeak": 0,
            "rawPathLeak": 0,
            "rawFilenameLeak": 0,
        },
        "warnings": [
            "WARN_MANUAL_MANIFEST_PROMOTION_REVIEW_REQUIRED",
            "WARN_NO_AUTO_MANIFEST_EDIT",
        ],
    }


def build_manifest_promotion_candidates(
    report_dir: Path = REPORT_DIR,
    contract_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = evaluate_manifest_promotion_candidates(contract_payload=contract_payload)
    _write_reports(report_dir, payload)
    return payload


def _no_leak(text: str) -> bool:
    return not (
        inventory.ABS_PATH_RE.search(text)
        or inventory.RAW_FILENAME_RE.search(text)
        or inventory.PII_RE.search(text)
    )


def _safe_write(path: Path, payload: Any) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if not _no_leak(text):
        raise ValueError(f"{contract_gate.new_gate.FAIL_UNSAFE_REPORT}: {path.name}")
    path.write_text(text, encoding="utf-8")


def _write_reports(report_dir: Path, payload: dict[str, Any]) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    _safe_write(report_dir / "manifest_promotion_candidates_summary.json", payload)
    _safe_write(report_dir / "manifest_promotion_candidates.json", payload["candidates"])
    _safe_write(report_dir / "manifest_promotion_module_breakdown.json", payload["moduleBreakdown"])
    lines = [
        "# HWPX Repo Manifest Promotion Candidates",
        "",
        f"- verdict: {payload['verdict']}",
        f"- contract verdict: {payload['contractVerdict']}",
        f"- stable path mapped files: {payload['summary']['stablePathMappedFiles']}",
        f"- manifest promotion candidates: {payload['summary']['manifestPromotionCandidates']}",
        f"- modules affected: {payload['summary']['modulesAffected']}",
        f"- source/test/audit: {payload['summary']['sourceCandidates']}/{payload['summary']['testCandidates']}/{payload['summary']['auditCandidates']}",
        f"- unresolved candidates: {payload['summary']['unresolvedCandidates']}",
        f"- security: pii={payload['security']['piiLeak']} rawPath={payload['security']['rawPathLeak']} rawFilename={payload['security']['rawFilenameLeak']}",
        "",
        "## Contract",
        "- stable path mapping candidates should be promoted into explicit module manifest entries",
        "- this builder does not edit the manifest automatically",
        "- unresolved candidates must be fixed before promotion work starts",
    ]
    text = "\n".join(lines) + "\n"
    if not _no_leak(text):
        raise ValueError(contract_gate.new_gate.FAIL_UNSAFE_REPORT)
    (report_dir / "manifest_promotion_candidates_summary.md").write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", default=str(REPORT_DIR))
    args = parser.parse_args()
    payload = build_manifest_promotion_candidates(report_dir=Path(args.report_dir))
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["verdict"] == PASS_VERDICT else 1


if __name__ == "__main__":
    raise SystemExit(main())
