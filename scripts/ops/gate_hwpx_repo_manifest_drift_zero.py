"""Fail if repo manifest drift reintroduces stable-path or promotion candidates."""

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

REPORT_DIR = ROOT / "data" / "reports" / "hwpx_repo_manifest_drift_zero_gate"

PASS_VERDICT = "PASS_HWPX_REPO_MANIFEST_DRIFT_ZERO_GATE"
FAIL_VERDICT = "FAIL_HWPX_REPO_MANIFEST_DRIFT_ZERO_GATE"

FAIL_STABLE_PATH_MAPPING_DETECTED = "FAIL_STABLE_PATH_MAPPING_DETECTED"
FAIL_MANIFEST_PROMOTION_CANDIDATE_DETECTED = "FAIL_MANIFEST_PROMOTION_CANDIDATE_DETECTED"
FAIL_CLASSIFICATION_CONTRACT = "FAIL_CLASSIFICATION_CONTRACT"
FAIL_PROMOTION_BUILDER = "FAIL_PROMOTION_BUILDER"


def evaluate_manifest_drift_zero_gate(
    contract_payload: dict[str, Any] | None = None,
    promotion_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    contract = contract_payload or contract_gate.run_repo_classification_contract_gate()
    promotion = promotion_payload or promotion_builder.build_manifest_promotion_candidates()
    failures: list[str] = []
    if contract.get("verdict") != contract_gate.PASS_VERDICT:
        failures.append(FAIL_CLASSIFICATION_CONTRACT)
    if promotion.get("verdict") != promotion_builder.PASS_VERDICT:
        failures.append(FAIL_PROMOTION_BUILDER)
    if contract.get("summary", {}).get("stablePathMappedFiles", 0) != 0:
        failures.append(FAIL_STABLE_PATH_MAPPING_DETECTED)
    if promotion.get("summary", {}).get("manifestPromotionCandidates", 0) != 0:
        failures.append(FAIL_MANIFEST_PROMOTION_CANDIDATE_DETECTED)
    return {
        "schemaVersion": "hwpx_repo_manifest_drift_zero_gate_v1",
        "verdict": PASS_VERDICT if not failures else FAIL_VERDICT,
        "summary": {
            "stablePathMappedFiles": contract.get("summary", {}).get("stablePathMappedFiles", 0),
            "manifestPromotionCandidates": promotion.get("summary", {}).get("manifestPromotionCandidates", 0),
            "modulesAffected": promotion.get("summary", {}).get("modulesAffected", 0),
            "sourceCandidates": promotion.get("summary", {}).get("sourceCandidates", 0),
            "testCandidates": promotion.get("summary", {}).get("testCandidates", 0),
            "auditCandidates": promotion.get("summary", {}).get("auditCandidates", 0),
        },
        "contractVerdict": contract.get("verdict"),
        "promotionVerdict": promotion.get("verdict"),
        "failures": failures,
        "security": {
            "piiLeak": 0,
            "rawPathLeak": 0,
            "rawFilenameLeak": 0,
        },
        "warnings": [
            "WARN_MANIFEST_DRIFT_ZERO_ENFORCED",
            "WARN_FAIL_FAST_ZERO_TOLERANCE",
        ],
    }


def run_manifest_drift_zero_gate(
    report_dir: Path = REPORT_DIR,
    contract_payload: dict[str, Any] | None = None,
    promotion_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = evaluate_manifest_drift_zero_gate(
        contract_payload=contract_payload,
        promotion_payload=promotion_payload,
    )
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
        raise ValueError(f"{contract_gate.new_gate.FAIL_UNSAFE_REPORT}: {path.name}")
    path.write_text(text, encoding="utf-8")


def _write_reports(report_dir: Path, payload: dict[str, Any]) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    _safe_write(report_dir / "manifest_drift_zero_summary.json", payload)
    lines = [
        "# HWPX Repo Manifest Drift Zero Gate",
        "",
        f"- verdict: {payload['verdict']}",
        f"- contract verdict: {payload['contractVerdict']}",
        f"- promotion verdict: {payload['promotionVerdict']}",
        f"- stable path mapped files: {payload['summary']['stablePathMappedFiles']}",
        f"- manifest promotion candidates: {payload['summary']['manifestPromotionCandidates']}",
        f"- modules affected: {payload['summary']['modulesAffected']}",
        f"- security: pii={payload['security']['piiLeak']} rawPath={payload['security']['rawPathLeak']} rawFilename={payload['security']['rawFilenameLeak']}",
        "",
        "## Contract",
        "- stable path mapping count must stay at zero",
        "- manifest promotion candidates must stay at zero",
        "- any drift reintroduction is a fail-fast blocking condition",
    ]
    text = "\n".join(lines) + "\n"
    if not _no_leak(text):
        raise ValueError(contract_gate.new_gate.FAIL_UNSAFE_REPORT)
    (report_dir / "manifest_drift_zero_summary.md").write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", default=str(REPORT_DIR))
    args = parser.parse_args()
    payload = run_manifest_drift_zero_gate(report_dir=Path(args.report_dir))
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["verdict"] == PASS_VERDICT else 1


if __name__ == "__main__":
    raise SystemExit(main())
