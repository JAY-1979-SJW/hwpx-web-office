"""Install persistent zone gates, module audits, and module communication contracts."""

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
from scripts.ops import gate_hwpx_repo_new_file_classification as new_file_gate  # noqa: E402
from scripts.ops import gate_hwpx_form_auto_fill_zones as zone_gate  # noqa: E402

MODULE_MANIFEST = ROOT / "scripts" / "ops" / "audit_hwpx_form_auto_fill_module_manifest.json"
ZONE_MANIFEST = ROOT / "scripts" / "ops" / "gate_hwpx_form_auto_fill_zones_manifest.json"
COMM_MANIFEST = ROOT / "scripts" / "ops" / "hwpx_form_auto_fill_module_communication_manifest.json"
INSTALLATION = ROOT / "scripts" / "ops" / "hwpx_form_auto_fill_persistent_gate_installation.json"
REPORT_DIR = ROOT / "data" / "reports" / "hwpx_form_auto_fill_persistent_gates"

PASS_VERDICT = "PASS_HWPX_FORM_AUTO_FILL_PERSISTENT_GATES_INSTALLED"
FAIL_VERDICT = "FAIL_HWPX_FORM_AUTO_FILL_PERSISTENT_GATES_INSTALLED"

ABS_PATH_RE = re.compile(r"(?<![A-Za-z])([A-Za-z]:[\\/][^\s\"']*|/(home|tmp|var|Users)/[^\s\"']*)")
RAW_FILENAME_RE = re.compile(r"\b[^\\/:\s]+\.hwpx\b", re.IGNORECASE)
PII_RE = re.compile(
    r"(\d{6}-\d{7}|\d{3}-\d{2}-\d{5}|\d{2,3}-\d{3,4}-\d{4}|"
    r"\d{2,6}-\d{2,6}-\d{2,6}|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})"
)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _no_leak(text: str) -> bool:
    return not (ABS_PATH_RE.search(text) or RAW_FILENAME_RE.search(text) or PII_RE.search(text))


def _check(code: str, desc: str, ok: bool, fail_code: str | None = None) -> dict[str, Any]:
    return {
        "code": code,
        "desc": desc,
        "status": "PASS" if ok else "FAIL",
        "failCode": None if ok else fail_code,
    }


def _module_ids(module_manifest: dict[str, Any]) -> set[str]:
    return {module["id"] for module in module_manifest.get("modules", [])}


def _zone_ids(zone_manifest: dict[str, Any]) -> set[str]:
    return {zone["id"] for zone in zone_manifest.get("zones", [])}


def _communication_ids(comm_manifest: dict[str, Any]) -> set[str]:
    return {module["id"] for module in comm_manifest.get("modules", [])}


def validate_manifests(
    module_manifest: dict[str, Any],
    zone_manifest: dict[str, Any],
    comm_manifest: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    module_ids = _module_ids(module_manifest)
    zone_ids = _zone_ids(zone_manifest)
    comm_ids = _communication_ids(comm_manifest)
    zone_modules = {
        module_id
        for zone in zone_manifest.get("zones", [])
        for module_id in zone.get("modules", [])
    }
    known_endpoint_bans = set(comm_manifest["globalContract"]["forbiddenEndpoints"])

    checks = [
        _check("A01", "module audit manifest exists", MODULE_MANIFEST.is_file()),
        _check("A02", "zone gate manifest exists", ZONE_MANIFEST.is_file()),
        _check("A03", "module communication manifest exists", COMM_MANIFEST.is_file()),
        _check("A04", "all audited modules have communication settings", module_ids == comm_ids),
        _check("A05", "all zone modules exist in module audit manifest", zone_modules.issubset(module_ids)),
        _check("A06", "communication zones exist in zone manifest", all(item["zone"] in zone_ids for item in comm_manifest["modules"])),
        _check("A07", "global mode is SANDBOX_ONLY", comm_manifest.get("mode") == "SANDBOX_ONLY", "FAIL_OPERATION_MODE_NOT_SANDBOX"),
        _check(
            "A08",
            "global source mutation is disabled",
            comm_manifest["globalContract"].get("sourceMutationAllowed") is False,
            "FAIL_SOURCE_MUTATION_ALLOWED",
        ),
        _check("A09", "global raw payload is disabled", comm_manifest["globalContract"].get("rawPayloadAllowed") is False),
        _check("A10", "global PII payload is disabled", comm_manifest["globalContract"].get("piiPayloadAllowed") is False),
        _check(
            "A11",
            "production and unsafe endpoints are globally forbidden",
            {"production-write", "source-overwrite", "final-deploy", "ai-api", "ocr-api", "hancom-only"}.issubset(
                known_endpoint_bans
            ),
        ),
        _check("A12", "new file classification gate exists", (ROOT / "scripts" / "ops" / "gate_hwpx_repo_new_file_classification.py").is_file()),
    ]

    link_errors = []
    unsafe_modules = []
    for item in comm_manifest["modules"]:
        inbound_ok = bool(item.get("inboundEvents")) or not item.get("upstream")
        outbound_ok = bool(item.get("outboundEvents")) or not item.get("downstream")
        links_ok = set(item.get("upstream", [])).issubset(module_ids) and set(item.get("downstream", [])).issubset(module_ids)
        if not links_ok:
            link_errors.append(item["id"])
        if not inbound_ok or not outbound_ok:
            link_errors.append(item["id"])
        unsafe = (
            item.get("allowedModes") != ["SANDBOX_ONLY"]
            or item.get("sourceMutationAllowed") is not False
            or item.get("rawPayloadAllowed") is not False
            or item.get("piiPayloadAllowed") is not False
            or bool(set(item.get("allowedEndpoints", [])) & known_endpoint_bans)
        )
        if unsafe:
            unsafe_modules.append(item["id"])

    checks.extend(
        [
            _check("A13", "module links reference known modules", not link_errors),
            _check("A14", "module communication remains sandbox and safe", not unsafe_modules),
        ]
    )

    matrix = {
        "moduleCount": len(module_ids),
        "zoneCount": len(zone_ids),
        "communicationCount": len(comm_ids),
        "moduleIds": sorted(module_ids),
        "zoneIds": sorted(zone_ids),
        "linkErrors": sorted(set(link_errors)),
        "unsafeModules": sorted(set(unsafe_modules)),
        "communications": [
            {
                "id": item["id"],
                "zone": item["zone"],
                "upstream": item.get("upstream", []),
                "downstream": item.get("downstream", []),
                "allowedEndpoints": item.get("allowedEndpoints", []),
                "mode": item.get("allowedModes", []),
                "sourceMutationAllowed": item.get("sourceMutationAllowed"),
                "rawPayloadAllowed": item.get("rawPayloadAllowed"),
                "piiPayloadAllowed": item.get("piiPayloadAllowed"),
            }
            for item in comm_manifest["modules"]
        ],
    }
    return checks, matrix


def install_persistent_gates(report_dir: Path = REPORT_DIR, run_smoke: bool = True) -> dict[str, Any]:
    module_manifest = _load_json(MODULE_MANIFEST)
    zone_manifest = _load_json(ZONE_MANIFEST)
    comm_manifest = _load_json(COMM_MANIFEST)
    checks, matrix = validate_manifests(module_manifest, zone_manifest, comm_manifest)

    smoke_runs: dict[str, Any] = {
        "enabled": run_smoke,
        "moduleAudit": None,
        "newFileGate": None,
        "zoneGate": None,
    }
    if run_smoke:
        module_result = module_audit.run_module_audits(
            report_dir=report_dir / "module_audit_smoke",
            module_ids={"field_mapping"},
            timeout=180,
        )
        new_file_result = new_file_gate.run_new_file_classification_gate(
            report_dir=report_dir / "new_file_gate_smoke",
            new_files=[],
        )
        zone_result = zone_gate.run_zone_gates(
            report_dir=report_dir / "zone_gate_smoke",
            zone_ids={"input_parse"},
            timeout=180,
        )
        smoke_runs["moduleAudit"] = {
            "verdict": module_result["verdict"],
            "summary": module_result["summary"],
        }
        smoke_runs["newFileGate"] = {
            "verdict": new_file_result["verdict"],
            "summary": new_file_result["summary"],
        }
        smoke_runs["zoneGate"] = {
            "verdict": zone_result["verdict"],
            "summary": zone_result["summary"],
        }
        checks.extend(
            [
                _check("A15", "representative module audit runs", module_result["verdict"] == module_audit.PASS_VERDICT),
                _check("A16", "representative new file classification gate runs", new_file_result["verdict"] == new_file_gate.PASS_VERDICT),
                _check("A17", "representative zone gate runs", zone_result["verdict"] == zone_gate.PASS_VERDICT),
            ]
        )

    failed = [item for item in checks if item["status"] != "PASS"]
    fail_codes = sorted({item["failCode"] for item in failed if item.get("failCode")})
    verdict = PASS_VERDICT if not failed else FAIL_VERDICT
    installation = {
        "schemaVersion": "hwpx_form_auto_fill_persistent_gate_installation_v1",
        "installationMode": "REPO_PERSISTENT_MANIFEST",
        "verdict": verdict,
        "mode": "SANDBOX_ONLY",
        "sourceMutationAllowed": False,
        "moduleAuditManifest": "scripts/ops/audit_hwpx_form_auto_fill_module_manifest.json",
        "zoneGateManifest": "scripts/ops/gate_hwpx_form_auto_fill_zones_manifest.json",
        "moduleCommunicationManifest": "scripts/ops/hwpx_form_auto_fill_module_communication_manifest.json",
        "commands": [
            "python scripts/ops/audit_hwpx_form_auto_fill_modules.py",
            "python scripts/ops/gate_hwpx_repo_new_file_classification.py",
            "python scripts/ops/gate_hwpx_form_auto_fill_zones.py",
            "python scripts/ops/install_hwpx_form_auto_fill_persistent_gates.py",
        ],
        "warnings": [
            "WARN_SANDBOX_ONLY",
            "WARN_REAL_USER_FILE_NOT_TESTED",
            "WARN_DEPLOY_NOT_PERFORMED",
            "WARN_REPO_PERSISTENT_GATE_CONFIG_ONLY",
        ],
    }
    payload = {
        "schemaVersion": "hwpx_form_auto_fill_persistent_gates_v1",
        "verdict": verdict,
        "installation": installation,
        "summary": {
            "modules": matrix["moduleCount"],
            "zones": matrix["zoneCount"],
            "communications": matrix["communicationCount"],
            "failedChecks": len(failed),
        },
        "checks": checks,
        "communicationMatrix": matrix,
        "smokeRuns": smoke_runs,
        "security": {
            "piiLeak": 0,
            "rawPathLeak": 0,
            "rawFilenameLeak": 0,
            "aiApiCalled": False,
            "ocrCalled": False,
            "hancomRequired": False,
        },
        "failCodes": fail_codes,
        "warnings": installation["warnings"],
    }
    _write_installation(installation)
    _write_reports(report_dir, payload)
    return payload


def _write_installation(payload: dict[str, Any]) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if not _no_leak(text):
        raise ValueError("unsafe installation payload")
    INSTALLATION.write_text(text, encoding="utf-8")


def _write_reports(report_dir: Path, payload: dict[str, Any]) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    _safe_write(report_dir / "persistent_gate_installation_summary.json", payload)
    _safe_write(report_dir / "module_communication_matrix.json", payload["communicationMatrix"])
    _safe_write(report_dir / "persistent_gate_audit.json", {"verdict": payload["verdict"], "checks": payload["checks"]})
    lines = [
        "# HWPX Form Auto Fill Persistent Gates",
        "",
        f"- verdict: {payload['verdict']}",
        f"- mode: {payload['installation']['mode']}",
        f"- modules: {payload['summary']['modules']}",
        f"- zones: {payload['summary']['zones']}",
        f"- communications: {payload['summary']['communications']}",
        f"- security: pii={payload['security']['piiLeak']} rawPath={payload['security']['rawPathLeak']} rawFilename={payload['security']['rawFilenameLeak']}",
        "",
        "## Commands",
    ]
    for command in payload["installation"]["commands"]:
        lines.append(f"- {command}")
    lines.extend(["", "## Checks"])
    for item in payload["checks"]:
        lines.append(f"- {item['status']} {item['code']} {item['desc']}")
    text = "\n".join(lines) + "\n"
    if not _no_leak(text):
        raise ValueError("unsafe markdown report")
    (report_dir / "persistent_gate_installation_summary.md").write_text(text, encoding="utf-8")


def _safe_write(path: Path, payload: Any) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if not _no_leak(text):
        raise ValueError(f"unsafe report payload: {path.name}")
    path.write_text(text, encoding="utf-8")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", default=str(REPORT_DIR), help="PII-safe report directory.")
    parser.add_argument("--skip-smoke", action="store_true", help="Install and validate manifests without running smoke audits.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    payload = install_persistent_gates(report_dir=Path(args.report_dir), run_smoke=not args.skip_smoke)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["verdict"] == PASS_VERDICT else 1


if __name__ == "__main__":
    raise SystemExit(main())
