"""Unify repo file classification gates into one contract gate."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.ops import classify_hwpx_repo_inventory as inventory  # noqa: E402
from scripts.ops import gate_hwpx_repo_existing_file_classification as existing_gate  # noqa: E402
from scripts.ops import gate_hwpx_repo_new_file_classification as new_gate  # noqa: E402

REPORT_DIR = ROOT / "data" / "reports" / "hwpx_repo_classification_contract_gate"

PASS_VERDICT = "PASS_HWPX_REPO_CLASSIFICATION_CONTRACT_GATE"
FAIL_VERDICT = "FAIL_HWPX_REPO_CLASSIFICATION_CONTRACT_GATE"


def evaluate_repo_classification_contract(
    tracked_files: list[str] | None = None,
    new_files: list[str] | None = None,
    module_manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    existing_payload = existing_gate.evaluate_existing_files(
        tracked_files or inventory._run_git_ls_files(),
        module_manifest=module_manifest,
    )
    new_payload = new_gate.evaluate_new_files(
        new_files or [],
        module_manifest=module_manifest,
    )
    existing_results = existing_payload["existingFileResults"]
    stable_path_mapped = [
        {
            "safePath": item["safePath"],
            "zone": item["zone"],
            "moduleId": item["moduleId"],
        }
        for item in existing_results
        if item.get("resolutionSource") == "stablePathMapping"
    ]
    manifest_promotion_candidates = sorted(stable_path_mapped, key=lambda item: (item["moduleId"] or "", item["safePath"]))
    failures = sorted(set(existing_payload["failures"]) | set(new_payload["failures"]))
    verdict = PASS_VERDICT if not failures else FAIL_VERDICT
    return {
        "schemaVersion": "hwpx_repo_classification_contract_gate_v1",
        "verdict": verdict,
        "summary": {
            "trackedFiles": existing_payload["summary"]["trackedFiles"],
            "governedExistingFiles": existing_payload["summary"]["governedFiles"],
            "newFiles": new_payload["summary"]["newFiles"],
            "existingFailures": existing_payload["summary"]["failedFiles"],
            "newFailures": new_payload["summary"]["failedFiles"],
            "stablePathMappedFiles": len(stable_path_mapped),
            "manifestPromotionCandidates": len(manifest_promotion_candidates),
        },
        "existingVerdict": existing_payload["verdict"],
        "newVerdict": new_payload["verdict"],
        "existingFileResults": existing_results,
        "newFileResults": new_payload["newFileResults"],
        "stablePathMappedFiles": stable_path_mapped,
        "manifestPromotionCandidates": manifest_promotion_candidates,
        "failures": failures,
        "security": {
            "piiLeak": 0,
            "rawPathLeak": 0,
            "rawFilenameLeak": 0,
        },
        "warnings": [
            "WARN_EXISTING_AND_NEW_CLASSIFICATION_CONTRACT",
            "WARN_STABLE_PATH_MAPPING_REQUIRES_MANIFEST_PROMOTION",
        ],
    }


def run_repo_classification_contract_gate(
    report_dir: Path = REPORT_DIR,
    tracked_files: list[str] | None = None,
    new_files: list[str] | None = None,
    module_manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = evaluate_repo_classification_contract(
        tracked_files=tracked_files,
        new_files=new_files,
        module_manifest=module_manifest,
    )
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
        raise ValueError(f"{new_gate.FAIL_UNSAFE_REPORT}: {path.name}")
    path.write_text(text, encoding="utf-8")


def _write_reports(report_dir: Path, payload: dict[str, Any]) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    _safe_write(report_dir / "repo_classification_contract_summary.json", payload)
    _safe_write(report_dir / "stable_path_mapping_candidates.json", payload["stablePathMappedFiles"])
    _safe_write(report_dir / "manifest_promotion_candidates.json", payload["manifestPromotionCandidates"])
    lines = [
        "# HWPX Repo Classification Contract Gate",
        "",
        f"- verdict: {payload['verdict']}",
        f"- existing verdict: {payload['existingVerdict']}",
        f"- new verdict: {payload['newVerdict']}",
        f"- governed existing files: {payload['summary']['governedExistingFiles']}",
        f"- new files: {payload['summary']['newFiles']}",
        f"- stable path mapped files: {payload['summary']['stablePathMappedFiles']}",
        f"- manifest promotion candidates: {payload['summary']['manifestPromotionCandidates']}",
        f"- security: pii={payload['security']['piiLeak']} rawPath={payload['security']['rawPathLeak']} rawFilename={payload['security']['rawFilenameLeak']}",
        "",
        "## Contract",
        "- existing governed files must stay zone-classified and module-resolved",
        "- new files must be zone-classified before they enter the repo",
        "- stable path mapping is allowed temporarily but should be promoted into module manifest declarations",
    ]
    text = "\n".join(lines) + "\n"
    if not _no_leak(text):
        raise ValueError(new_gate.FAIL_UNSAFE_REPORT)
    (report_dir / "repo_classification_contract_summary.md").write_text(text, encoding="utf-8")


def _load_paths(path: str | None) -> list[str] | None:
    if not path:
        return None
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", default=str(REPORT_DIR))
    parser.add_argument("--tracked-files-json")
    parser.add_argument("--new-files-json")
    args = parser.parse_args()
    payload = run_repo_classification_contract_gate(
        report_dir=Path(args.report_dir),
        tracked_files=_load_paths(args.tracked_files_json),
        new_files=_load_paths(args.new_files_json),
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["verdict"] == PASS_VERDICT else 1


if __name__ == "__main__":
    raise SystemExit(main())
