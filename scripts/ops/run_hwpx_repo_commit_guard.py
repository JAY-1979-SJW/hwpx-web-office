"""Run repo classification guards suitable for a pre-commit hook."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.ops import build_hwpx_repo_manifest_promotion_candidates as promotion_builder  # noqa: E402
from scripts.ops import gate_hwpx_repo_classification_contract as contract_gate  # noqa: E402
from scripts.ops import gate_hwpx_repo_manifest_drift_zero as drift_zero_gate  # noqa: E402
from scripts.ops import gate_hwpx_repo_new_file_classification as new_file_gate  # noqa: E402

REPORT_DIR = ROOT / "data" / "reports" / "hwpx_repo_commit_guard"

PASS_VERDICT = "PASS_HWPX_REPO_COMMIT_GUARD"
FAIL_VERDICT = "FAIL_HWPX_REPO_COMMIT_GUARD"


def evaluate_commit_guard(
    new_file_payload: dict[str, Any],
    contract_payload: dict[str, Any],
    promotion_payload: dict[str, Any],
    drift_payload: dict[str, Any],
) -> dict[str, Any]:
    failures: list[str] = []
    if new_file_payload.get("verdict") != new_file_gate.PASS_VERDICT:
        failures.append("FAIL_NEW_FILE_CLASSIFICATION")
    if contract_payload.get("verdict") != contract_gate.PASS_VERDICT:
        failures.append("FAIL_REPO_CLASSIFICATION_CONTRACT")
    if promotion_payload.get("verdict") != promotion_builder.PASS_VERDICT:
        failures.append("FAIL_MANIFEST_PROMOTION_CANDIDATES")
    if drift_payload.get("verdict") != drift_zero_gate.PASS_VERDICT:
        failures.append("FAIL_MANIFEST_DRIFT_ZERO")
    return {
        "schemaVersion": "hwpx_repo_commit_guard_v1",
        "verdict": PASS_VERDICT if not failures else FAIL_VERDICT,
        "summary": {
            "newFiles": new_file_payload.get("summary", {}).get("newFiles", 0),
            "stablePathMappedFiles": contract_payload.get("summary", {}).get("stablePathMappedFiles", 0),
            "manifestPromotionCandidates": promotion_payload.get("summary", {}).get("manifestPromotionCandidates", 0),
        },
        "newFileVerdict": new_file_payload.get("verdict"),
        "contractVerdict": contract_payload.get("verdict"),
        "promotionVerdict": promotion_payload.get("verdict"),
        "driftVerdict": drift_payload.get("verdict"),
        "failures": failures,
        "security": {
            "piiLeak": 0,
            "rawPathLeak": 0,
            "rawFilenameLeak": 0,
        },
    }


def run_commit_guard(report_dir: Path | None = REPORT_DIR, temp_only: bool = False) -> dict[str, Any]:
    if temp_only:
        return _run_core(None)
    target = report_dir or REPORT_DIR
    target.mkdir(parents=True, exist_ok=True)
    return _run_core(target)


def _run_core(report_dir: Path | None) -> dict[str, Any]:
    if report_dir is None:
        detected = new_file_gate.detect_new_files()
        new_files = detected["stagedAdded"] + [
            path for path in detected["untracked"]
            if path not in detected["stagedAdded"]
        ]
        new_file_payload = new_file_gate.evaluate_new_files(new_files)
        contract_payload = contract_gate.evaluate_repo_classification_contract(
            new_files=[],
        )
        promotion_payload = promotion_builder.evaluate_manifest_promotion_candidates(
            contract_payload=contract_payload,
        )
        drift_payload = drift_zero_gate.evaluate_manifest_drift_zero_gate(
            contract_payload=contract_payload,
            promotion_payload=promotion_payload,
        )
    else:
        new_file_payload = new_file_gate.run_new_file_classification_gate(
            report_dir=report_dir / "new_file_classification",
        )
        contract_payload = contract_gate.run_repo_classification_contract_gate(
            report_dir=report_dir / "repo_classification_contract",
            new_files=[],
        )
        promotion_payload = promotion_builder.build_manifest_promotion_candidates(
            report_dir=report_dir / "manifest_promotion",
            contract_payload=contract_payload,
        )
        drift_payload = drift_zero_gate.run_manifest_drift_zero_gate(
            report_dir=report_dir / "manifest_drift_zero",
            contract_payload=contract_payload,
            promotion_payload=promotion_payload,
        )
    payload = evaluate_commit_guard(new_file_payload, contract_payload, promotion_payload, drift_payload)
    if report_dir is not None and (report_dir == REPORT_DIR or report_dir.is_relative_to(ROOT)):
        _write_reports(report_dir, payload)
    return payload


def _no_leak(text: str) -> bool:
    return not (
        contract_gate.inventory.ABS_PATH_RE.search(text)
        or contract_gate.inventory.RAW_FILENAME_RE.search(text)
        or contract_gate.inventory.PII_RE.search(text)
    )


def _safe_write(path: Path, payload: Any) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if not _no_leak(text):
        raise ValueError(f"{new_file_gate.FAIL_UNSAFE_REPORT}: {path.name}")
    path.write_text(text, encoding="utf-8")


def _write_reports(report_dir: Path, payload: dict[str, Any]) -> None:
    _safe_write(report_dir / "commit_guard_summary.json", payload)
    lines = [
        "# HWPX Repo Commit Guard",
        "",
        f"- verdict: {payload['verdict']}",
        f"- new files: {payload['summary']['newFiles']}",
        f"- stable path mapped files: {payload['summary']['stablePathMappedFiles']}",
        f"- manifest promotion candidates: {payload['summary']['manifestPromotionCandidates']}",
    ]
    text = "\n".join(lines) + "\n"
    if not _no_leak(text):
        raise ValueError(new_file_gate.FAIL_UNSAFE_REPORT)
    (report_dir / "commit_guard_summary.md").write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", default=str(REPORT_DIR))
    parser.add_argument("--temp-only", action="store_true")
    args = parser.parse_args()
    payload = run_commit_guard(report_dir=Path(args.report_dir), temp_only=args.temp_only)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["verdict"] == PASS_VERDICT else 1


if __name__ == "__main__":
    raise SystemExit(main())
