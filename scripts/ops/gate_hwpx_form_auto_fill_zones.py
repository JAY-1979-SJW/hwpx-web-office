"""Zone-level release gate for the HWPX form auto-fill flow."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.ops import audit_hwpx_form_auto_fill_modules as module_audit  # noqa: E402

MANIFEST = ROOT / "scripts" / "ops" / "gate_hwpx_form_auto_fill_zones_manifest.json"
REPORT_DIR = ROOT / "data" / "reports" / "hwpx_form_auto_fill_zone_gates"
PASS_VERDICT = "PASS_HWPX_FORM_AUTO_FILL_ZONE_GATES"
FAIL_VERDICT = "FAIL_HWPX_FORM_AUTO_FILL_ZONE_GATES"

ABS_PATH_RE = re.compile(r"(?<![A-Za-z])([A-Za-z]:[\\/][^\s\"']*|/(home|tmp|var|Users)/[^\s\"']*)")
RAW_FILENAME_RE = re.compile(r"\b[^\\/:\s]+\.hwpx\b", re.IGNORECASE)
PII_RE = re.compile(
    r"(\d{6}-\d{7}|\d{3}-\d{2}-\d{5}|\d{2,3}-\d{3,4}-\d{4}|"
    r"\d{2,6}-\d{2,6}-\d{2,6}|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})"
)


def load_manifest(path: Path = MANIFEST) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _no_leak(text: str) -> bool:
    return not (ABS_PATH_RE.search(text) or RAW_FILENAME_RE.search(text) or PII_RE.search(text))


def gate_zone(zone: dict[str, Any], timeout: int) -> dict[str, Any]:
    module_ids = set(zone["modules"])
    module_result = module_audit.run_module_audits(
        report_dir=REPORT_DIR / "module_subruns" / zone["id"],
        module_ids=module_ids,
        timeout=timeout,
    )
    failed_modules = [item["id"] for item in module_result["moduleResults"] if item["status"] != "PASS"]
    security = {
        "piiLeak": sum(item["security"]["piiLeak"] for item in module_result["moduleResults"]),
        "rawPathLeak": sum(item["security"]["rawPathLeak"] for item in module_result["moduleResults"]),
        "rawFilenameLeak": sum(item["security"]["rawFilenameLeak"] for item in module_result["moduleResults"]),
    }
    required_verdict = zone.get("requiredVerdict", module_audit.PASS_VERDICT)
    status = "PASS" if module_result["verdict"] == required_verdict and not failed_modules and not any(security.values()) else "FAIL"
    return {
        "id": zone["id"],
        "title": zone.get("title", zone["id"]),
        "status": status,
        "modules": sorted(module_ids),
        "moduleVerdict": module_result["verdict"],
        "failedModules": failed_modules,
        "security": security,
    }


def run_zone_gates(
    manifest_path: Path = MANIFEST,
    report_dir: Path = REPORT_DIR,
    zone_ids: set[str] | None = None,
    timeout: int = 300,
) -> dict[str, Any]:
    manifest = load_manifest(manifest_path)
    selected = [zone for zone in manifest["zones"] if not zone_ids or zone["id"] in zone_ids]
    zone_results = [gate_zone(zone, timeout) for zone in selected]
    failed = [item for item in zone_results if item["status"] != "PASS"]
    security = {
        "piiLeak": sum(item["security"]["piiLeak"] for item in zone_results),
        "rawPathLeak": sum(item["security"]["rawPathLeak"] for item in zone_results),
        "rawFilenameLeak": sum(item["security"]["rawFilenameLeak"] for item in zone_results),
    }
    payload = {
        "schemaVersion": "hwpx_form_auto_fill_zone_gates_v1",
        "verdict": PASS_VERDICT if not failed and not any(security.values()) else FAIL_VERDICT,
        "summary": {
            "zonesTotal": len(zone_results),
            "zonesPassed": len(zone_results) - len(failed),
            "zonesFailed": len(failed),
        },
        "zoneResults": zone_results,
        "security": security,
        "warnings": manifest.get("warnings", []),
    }
    _write_reports(report_dir, payload)
    return payload


def _write_reports(report_dir: Path, payload: dict[str, Any]) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    _safe_write(report_dir / "zone_gate_summary.json", payload)
    _safe_write(report_dir / "zone_gate_results.json", payload["zoneResults"])
    lines = [
        "# HWPX Form Auto Fill Zone Gates",
        "",
        f"- verdict: {payload['verdict']}",
        f"- zones: {payload['summary']['zonesPassed']}/{payload['summary']['zonesTotal']} passed",
        f"- security: pii={payload['security']['piiLeak']} rawPath={payload['security']['rawPathLeak']} rawFilename={payload['security']['rawFilenameLeak']}",
        "",
        "## Zones",
    ]
    lines.extend(f"- {item['status']} {item['id']} - modules={','.join(item['modules'])}" for item in payload["zoneResults"])
    text = "\n".join(lines) + "\n"
    if not _no_leak(text):
        raise ValueError("unsafe markdown report")
    (report_dir / "zone_gate_summary.md").write_text(text, encoding="utf-8")


def _safe_write(path: Path, payload: Any) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if not _no_leak(text):
        raise ValueError(f"unsafe report payload: {path.name}")
    path.write_text(text, encoding="utf-8")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default=str(MANIFEST), help="Zone gate manifest JSON.")
    parser.add_argument("--report-dir", default=str(REPORT_DIR), help="PII-safe report directory.")
    parser.add_argument("--timeout", type=int, default=300, help="Per-zone module audit timeout in seconds.")
    parser.add_argument("--zone", action="append", help="Run a single zone id. May be repeated.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    payload = run_zone_gates(
        manifest_path=Path(args.manifest),
        report_dir=Path(args.report_dir),
        zone_ids=set(args.zone or []),
        timeout=args.timeout,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["verdict"] == PASS_VERDICT else 1


if __name__ == "__main__":
    raise SystemExit(main())
