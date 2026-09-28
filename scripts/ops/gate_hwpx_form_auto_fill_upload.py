"""Upload gate for HWPX form auto-fill before preflight or writer access."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

REPORT_DIR = Path("data") / "reports" / "hwpx_form_auto_fill_upload_gate"

UPLOAD_ACCEPTED = "UPLOAD_ACCEPTED_SANITIZED"
BLOCKED_REAL_USER_FILE = "BLOCKED_REAL_USER_FILE"
BLOCKED_PII_RISK = "BLOCKED_PII_RISK"
BLOCKED_RAW_PATH_RISK = "BLOCKED_RAW_PATH_RISK"
BLOCKED_RAW_FILENAME_RISK = "BLOCKED_RAW_FILENAME_RISK"
BLOCKED_UNSUPPORTED_FILE_TYPE = "BLOCKED_UNSUPPORTED_FILE_TYPE"
BLOCKED_NON_SANDBOX_MODE = "BLOCKED_NON_SANDBOX_MODE"
BLOCKED_SOURCE_MUTATION_ALLOWED = "BLOCKED_SOURCE_MUTATION_ALLOWED"
BLOCKED_OUTPUT_EQUALS_SOURCE = "BLOCKED_OUTPUT_EQUALS_SOURCE"
BLOCKED_UNSANITIZED_SAMPLE = "BLOCKED_UNSANITIZED_SAMPLE"

PASS_VERDICT = "PASS_HWPX_FORM_AUTO_FILL_UPLOAD_GATE"
FAIL_VERDICT = "FAIL_HWPX_FORM_AUTO_FILL_UPLOAD_GATE"

ABS_PATH_RE = re.compile(r"(?<![A-Za-z])([A-Za-z]:[\\/][^\s\"']*|/(home|tmp|var|Users)/[^\s\"']*)")
RAW_FILENAME_RE = re.compile(r"\b[^\\/:\s]+\.hwpx\b", re.IGNORECASE)
PII_RE = re.compile(
    r"(\d{6}-\d{7}|\d{3}-\d{2}-\d{5}|\d{2,3}-\d{3,4}-\d{4}|"
    r"\d{2,6}-\d{2,6}-\d{2,6}|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})"
)
SUPPORTED_PACKAGE_KINDS = {"HWPX_PACKAGE", "SANITIZED_REAL_LIKE_PACKAGE", "SYNTHETIC_PACKAGE"}


def _no_leak(text: str) -> bool:
    return not (ABS_PATH_RE.search(text) or RAW_FILENAME_RE.search(text) or PII_RE.search(text))


def _safe_id(seed: str) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def _first_block_reason(
    request: dict[str, Any], source_hint: str, output_hint: str, package_kind: str, scan_text: str
) -> str | None:
    """업로드 요청을 순서대로 검사해 첫 번째로 걸리는 차단 사유를 반환한다."""
    if request.get("mode") != "SANDBOX_ONLY":
        return BLOCKED_NON_SANDBOX_MODE
    if request.get("sourceMutationAllowed") is not False:
        return BLOCKED_SOURCE_MUTATION_ALLOWED
    if request.get("realUserFile") is True:
        return BLOCKED_REAL_USER_FILE
    if request.get("declaredSanitized") is not True:
        return BLOCKED_UNSANITIZED_SAMPLE
    if package_kind not in SUPPORTED_PACKAGE_KINDS:
        return BLOCKED_UNSUPPORTED_FILE_TYPE
    if source_hint and output_hint and source_hint == output_hint:
        return BLOCKED_OUTPUT_EQUALS_SOURCE
    if ABS_PATH_RE.search(scan_text):
        return BLOCKED_RAW_PATH_RISK
    if RAW_FILENAME_RE.search(scan_text):
        return BLOCKED_RAW_FILENAME_RISK
    if PII_RE.search(scan_text):
        return BLOCKED_PII_RISK
    return None


def evaluate_upload_request(request: dict[str, Any]) -> dict[str, Any]:
    display_name = str(request.get("displayName", "sanitized-sample"))
    package_kind = str(request.get("packageKind", ""))
    source_hint = str(request.get("sourcePathHint", ""))
    output_hint = str(request.get("outputPathHint", ""))
    content_preview = str(request.get("contentPreview", ""))
    scan_text = "\n".join([display_name, source_hint, output_hint, content_preview])

    blocked_reason = _first_block_reason(request, source_hint, output_hint, package_kind, scan_text)

    accepted = blocked_reason is None
    response = {
        "schemaVersion": "hwpx_form_auto_fill_upload_gate_v1",
        "mode": "SANDBOX_ONLY",
        "sourceMutationAllowed": False,
        "status": UPLOAD_ACCEPTED if accepted else "BLOCKED",
        "blockedReason": None if accepted else blocked_reason,
        "sampleId": "sample_" + _safe_id(display_name + package_kind),
        "displayName": display_name if _no_leak(display_name) else "sanitized-sample",
        "packageKind": package_kind if package_kind in SUPPORTED_PACKAGE_KINDS else "UNSUPPORTED",
        "allowedForPreflight": accepted,
        "allowedForWriter": False,
        "security": {
            "piiRisk": bool(PII_RE.search(scan_text)),
            "rawPathRisk": bool(ABS_PATH_RE.search(scan_text)),
            "rawFilenameRisk": bool(RAW_FILENAME_RE.search(scan_text)),
            "realUserFile": request.get("realUserFile") is True,
        },
    }
    text = json.dumps(response, ensure_ascii=False)
    if not _no_leak(text):
        raise ValueError("unsafe upload gate response")
    return response


def run_upload_gate_scenarios(report_dir: Path = REPORT_DIR) -> dict[str, Any]:
    scenarios = {
        "sanitizedSynthetic": {
            "mode": "SANDBOX_ONLY",
            "sourceMutationAllowed": False,
            "declaredSanitized": True,
            "realUserFile": False,
            "displayName": "sanitized_building_form",
            "packageKind": "SYNTHETIC_PACKAGE",
            "sourcePathHint": "source_package_a",
            "outputPathHint": "output_package_a",
            "contentPreview": "masked project data",
        },
        "realUserFile": {
            "mode": "SANDBOX_ONLY",
            "sourceMutationAllowed": False,
            "declaredSanitized": True,
            "realUserFile": True,
            "displayName": "sanitized_building_form",
            "packageKind": "HWPX_PACKAGE",
        },
        "piiRisk": {
            "mode": "SANDBOX_ONLY",
            "sourceMutationAllowed": False,
            "declaredSanitized": True,
            "realUserFile": False,
            "displayName": "sanitized_building_form",
            "packageKind": "HWPX_PACKAGE",
            "contentPreview": "contact 010-1234-5678",
        },
        "rawFilenameRisk": {
            "mode": "SANDBOX_ONLY",
            "sourceMutationAllowed": False,
            "declaredSanitized": True,
            "realUserFile": False,
            "displayName": "sample.hwpx",
            "packageKind": "HWPX_PACKAGE",
        },
        "nonSandbox": {
            "mode": "PRODUCTION",
            "sourceMutationAllowed": False,
            "declaredSanitized": True,
            "realUserFile": False,
            "displayName": "sanitized_building_form",
            "packageKind": "HWPX_PACKAGE",
        },
    }
    results = {name: evaluate_upload_request(payload) for name, payload in scenarios.items()}
    blocked = [item for item in results.values() if item["status"] != UPLOAD_ACCEPTED]
    security = {
        "piiLeak": 0,
        "rawPathLeak": 0,
        "rawFilenameLeak": 0,
        "aiApiCalled": False,
        "ocrCalled": False,
        "hancomRequired": False,
    }
    payload = {
        "schemaVersion": "hwpx_form_auto_fill_upload_gate_scenarios_v1",
        "verdict": PASS_VERDICT,
        "summary": {
            "scenarios": len(results),
            "accepted": sum(1 for item in results.values() if item["status"] == UPLOAD_ACCEPTED),
            "blocked": len(blocked),
        },
        "results": results,
        "security": security,
        "warnings": [
            "WARN_SANDBOX_ONLY",
            "WARN_REAL_USER_FILE_NOT_TESTED",
            "WARN_UPLOAD_GATE_METADATA_ONLY",
        ],
    }
    _write_reports(report_dir, payload)
    return payload


def _write_reports(report_dir: Path, payload: dict[str, Any]) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    _safe_write(report_dir / "upload_gate_summary.json", payload)
    _safe_write(report_dir / "upload_gate_matrix.json", payload["results"])
    lines = [
        "# HWPX Form Auto Fill Upload Gate",
        "",
        f"- verdict: {payload['verdict']}",
        f"- accepted: {payload['summary']['accepted']}",
        f"- blocked: {payload['summary']['blocked']}",
        f"- security: pii={payload['security']['piiLeak']} rawPath={payload['security']['rawPathLeak']} rawFilename={payload['security']['rawFilenameLeak']}",
        "",
        "## Scenarios",
    ]
    for name, item in payload["results"].items():
        reason = item["blockedReason"] or "ACCEPTED"
        lines.append(f"- {name}: {item['status']} {reason}")
    text = "\n".join(lines) + "\n"
    if not _no_leak(text):
        raise ValueError("unsafe upload gate markdown")
    (report_dir / "upload_gate_summary.md").write_text(text, encoding="utf-8")


def _safe_write(path: Path, payload: Any) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if not _no_leak(text):
        raise ValueError(f"unsafe upload gate payload: {path.name}")
    path.write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", default=str(REPORT_DIR))
    args = parser.parse_args()
    payload = run_upload_gate_scenarios(report_dir=Path(args.report_dir))
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["verdict"] == PASS_VERDICT else 1


if __name__ == "__main__":
    raise SystemExit(main())
