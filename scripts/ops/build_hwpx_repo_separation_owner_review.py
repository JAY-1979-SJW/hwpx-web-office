"""Build PII-safe owner review packets for repo separation packages."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.ops import gate_hwpx_repo_separation_execution as execution_gate  # noqa: E402

REPORT_DIR = ROOT / "data" / "reports" / "hwpx_repo_separation_owner_review"

PASS_VERDICT = "PASS_HWPX_REPO_SEPARATION_OWNER_REVIEW_PACKETS"
FAIL_VERDICT = "FAIL_HWPX_REPO_SEPARATION_OWNER_REVIEW_PACKETS"
FAIL_EXECUTION_GATE_NOT_PASS = "FAIL_EXECUTION_GATE_NOT_PASS"
FAIL_OWNER_PACKET_APPROVED_PREMATURELY = "FAIL_OWNER_PACKET_APPROVED_PREMATURELY"
FAIL_UNSAFE_REPORT = "FAIL_UNSAFE_REPORT"

ABS_PATH_RE = execution_gate.ABS_PATH_RE
RAW_FILENAME_RE = execution_gate.RAW_FILENAME_RE
PII_RE = execution_gate.PII_RE


def _review_track(package: dict[str, Any]) -> str:
    phase = package["phase"]
    if phase == "P0_HOLD":
        return "HOLD_OWNER_REVIEW"
    if phase == "P1_GATE_PROTECTED_REFACTOR_PLAN":
        return "GATE_OWNER_REVIEW"
    if phase == "P2_DEPENDENCY_IMPACT_REVIEW":
        return "DEPENDENCY_OWNER_REVIEW"
    if phase == "P3_RETENTION_REVIEW":
        return "RETENTION_OWNER_REVIEW"
    return "CONFIG_OWNER_REVIEW"


def _packet_for_package(package: dict[str, Any]) -> dict[str, Any]:
    return {
        "packetId": f"owner_review_{package['areaId']}",
        "packageId": package["packageId"],
        "areaId": package["areaId"],
        "reviewTrack": _review_track(package),
        "approvalStatus": "PENDING_OWNER_REVIEW",
        "fileCount": package["fileCount"],
        "reviewRequiredFiles": package["reviewRequiredFiles"],
        "operation": package["operation"],
        "movePolicy": package["movePolicy"],
        "dryRunOnly": package["dryRunOnly"],
        "executionAllowed": False,
        "approvedForMove": False,
        "approvedForDelete": False,
        "approvedForArchive": False,
        "requiredChecks": [
            "confirm_package_owner",
            "confirm_import_impact_review",
            "confirm_gate_green",
            "confirm_no_pii_raw_path_raw_filename",
            "confirm_no_file_move_delete_archive_without_explicit_approval",
        ],
        "blockedUntil": [
            "owner_review_completed",
            "gate_regression_passed",
            "execution_plan_committed_separately",
        ],
    }


def build_owner_review_packets(report_dir: Path = REPORT_DIR) -> dict[str, Any]:
    execution_payload = execution_gate.run_execution_gate(report_dir=report_dir / "execution_gate_subrun")
    packets = [_packet_for_package(package) for package in execution_payload["executionMatrix"]]
    premature = [
        packet["packetId"]
        for packet in packets
        if packet["approvedForMove"] or packet["approvedForDelete"] or packet["approvedForArchive"] or packet["executionAllowed"]
    ]
    failures = []
    if execution_payload["verdict"] != execution_gate.PASS_VERDICT:
        failures.append(FAIL_EXECUTION_GATE_NOT_PASS)
    if premature:
        failures.append(FAIL_OWNER_PACKET_APPROVED_PREMATURELY)
    payload = {
        "schemaVersion": "hwpx_repo_separation_owner_review_packets_v1",
        "verdict": PASS_VERDICT if not failures else FAIL_VERDICT,
        "baselineHead": execution_payload["baselineHead"],
        "mode": "OWNER_REVIEW_PENDING",
        "summary": {
            "packets": len(packets),
            "pendingPackets": sum(1 for packet in packets if packet["approvalStatus"] == "PENDING_OWNER_REVIEW"),
            "approvedPackets": 0,
            "executionAllowedPackets": 0,
            "holdPackets": sum(1 for packet in packets if packet["reviewTrack"] == "HOLD_OWNER_REVIEW"),
            "totalFiles": execution_payload["summary"]["totalFiles"],
        },
        "ownerReviewPackets": packets,
        "failures": failures,
        "security": {
            "piiLeak": 0,
            "rawPathLeak": 0,
            "rawFilenameLeak": 0,
            "fileMoveApproved": False,
            "fileDeleteApproved": False,
            "fileArchiveApproved": False,
            "fileMovePerformed": False,
            "fileDeletePerformed": False,
        },
        "warnings": [
            "WARN_OWNER_REVIEW_PENDING",
            "WARN_NO_FILE_MOVE_PERFORMED",
            "WARN_APPROVAL_PACKETS_ONLY",
        ],
    }
    _write_reports(report_dir, payload)
    return payload


def _no_leak(text: str) -> bool:
    return not (ABS_PATH_RE.search(text) or RAW_FILENAME_RE.search(text) or PII_RE.search(text))


def _safe_write(path: Path, payload: Any) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if not _no_leak(text):
        raise ValueError(f"{FAIL_UNSAFE_REPORT}: {path.name}")
    path.write_text(text, encoding="utf-8")


def _write_reports(report_dir: Path, payload: dict[str, Any]) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    _safe_write(report_dir / "owner_review_summary.json", payload)
    _safe_write(report_dir / "owner_review_packets.json", payload["ownerReviewPackets"])
    lines = [
        "# HWPX Repo Separation Owner Review Packets",
        "",
        f"- verdict: {payload['verdict']}",
        f"- baseline: {payload['baselineHead']}",
        f"- mode: {payload['mode']}",
        f"- packets: {payload['summary']['packets']}",
        f"- pending: {payload['summary']['pendingPackets']}",
        f"- approved: {payload['summary']['approvedPackets']}",
        f"- executionAllowed: {payload['summary']['executionAllowedPackets']}",
        f"- security: pii={payload['security']['piiLeak']} rawPath={payload['security']['rawPathLeak']} rawFilename={payload['security']['rawFilenameLeak']}",
        "",
        "## Packets",
    ]
    for packet in payload["ownerReviewPackets"]:
        lines.append(
            f"- {packet['packetId']}: track={packet['reviewTrack']} status={packet['approvalStatus']} files={packet['fileCount']}"
        )
    lines.extend(["", "## Guardrails"])
    lines.append("- this report does not approve move/delete/archive")
    lines.append("- all packages remain pending until explicit owner review")
    lines.append("- execution must remain blocked until a separate approved execution plan")
    text = "\n".join(lines) + "\n"
    if not _no_leak(text):
        raise ValueError(FAIL_UNSAFE_REPORT)
    (report_dir / "owner_review_summary.md").write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", default=str(REPORT_DIR))
    args = parser.parse_args()
    payload = build_owner_review_packets(report_dir=Path(args.report_dir))
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["verdict"] == PASS_VERDICT else 1


if __name__ == "__main__":
    raise SystemExit(main())
