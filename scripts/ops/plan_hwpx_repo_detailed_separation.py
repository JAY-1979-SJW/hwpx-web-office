"""Detailed separation plan that links repo inventory to gates and module audits."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.ops import classify_hwpx_repo_inventory as inventory  # noqa: E402

MODULE_MANIFEST = ROOT / "scripts" / "ops" / "audit_hwpx_form_auto_fill_module_manifest.json"
ZONE_MANIFEST = ROOT / "scripts" / "ops" / "gate_hwpx_form_auto_fill_zones_manifest.json"
COMM_MANIFEST = ROOT / "scripts" / "ops" / "hwpx_form_auto_fill_module_communication_manifest.json"
REPORT_DIR = ROOT / "data" / "reports" / "hwpx_repo_detailed_separation_plan"

PASS_VERDICT = "PASS_HWPX_REPO_DETAILED_SEPARATION_PLAN"
FAIL_VERDICT = "FAIL_HWPX_REPO_DETAILED_SEPARATION_PLAN"

ABS_PATH_RE = inventory.ABS_PATH_RE
RAW_FILENAME_RE = inventory.RAW_FILENAME_RE
PII_RE = inventory.PII_RE

AREA_RULES = [
    {
        "id": "runtime_autofill_line",
        "title": "SANDBOX_ONLY autofill runtime",
        "categories": {"ACTIVE_AUTOFILL"},
        "action": "protect_with_module_audit_and_zone_gate",
        "gatePolicy": "required_for_release_zones",
        "movePolicy": "no_move_until_gate_green",
    },
    {
        "id": "hwpx_core_library",
        "title": "HWPX core parser and document utilities",
        "categories": {"ACTIVE_HWPX_CORE"},
        "action": "keep_as_shared_core_with_import_review",
        "gatePolicy": "source_dependency_review_required",
        "movePolicy": "no_move_until_import_impact_review",
    },
    {
        "id": "frontend_viewer_shell",
        "title": "Browser viewer and UI shell",
        "categories": {"FRONTEND_VIEWER"},
        "action": "protect_browser_contracts",
        "gatePolicy": "browser_regression_required",
        "movePolicy": "no_move_until_route_contract_review",
    },
    {
        "id": "audit_gate_layer",
        "title": "Audits, gates, installers, dashboards",
        "categories": {"AUDIT_GATE"},
        "action": "keep_as_release_gate_layer",
        "gatePolicy": "self_audit_required",
        "movePolicy": "no_move_until_gate_bootstrap_review",
    },
    {
        "id": "test_support_layer",
        "title": "Tests and fixtures",
        "categories": {"TEST_ONLY", "TEST_FIXTURE"},
        "action": "keep_with_target_module_mapping",
        "gatePolicy": "pytest_required",
        "movePolicy": "no_move_until_test_owner_review",
    },
    {
        "id": "docs_reports_layer",
        "title": "PII-safe reports and closeout docs",
        "categories": {"REPORT_DOC"},
        "action": "keep_pii_safe_artifacts",
        "gatePolicy": "leak_scan_required",
        "movePolicy": "no_move_until_report_retention_review",
    },
    {
        "id": "legacy_experiment_quarantine",
        "title": "Legacy and experimental scripts",
        "categories": {"LEGACY_EXPERIMENT"},
        "action": "quarantine_before_any_archive_or_split",
        "gatePolicy": "manual_review_required",
        "movePolicy": "no_move_no_delete_without_owner_approval",
    },
    {
        "id": "config_root_layer",
        "title": "Root configuration and build metadata",
        "categories": {"CONFIG_BUILD"},
        "action": "keep_as_root_configuration",
        "gatePolicy": "config_change_review_required",
        "movePolicy": "no_move_without_build_review",
    },
    {
        "id": "manual_review_hold",
        "title": "Unknown files requiring manual review",
        "categories": {"UNKNOWN_REVIEW_REQUIRED"},
        "action": "hold_until_classified",
        "gatePolicy": "manual_review_required",
        "movePolicy": "no_move_no_delete_without_owner_approval",
    },
]

RELEASE_ZONES = {
    "input_parse",
    "review_approval",
    "writer_readback",
    "download_export",
    "batch_api_browser",
    "closeout_security",
}

FORBIDDEN_ENDPOINTS = {
    "production-write",
    "source-overwrite",
    "final-deploy",
    "ai-api",
    "ocr-api",
    "hancom-only",
}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _area_for_category(category: str) -> dict[str, Any]:
    for rule in AREA_RULES:
        if category in rule["categories"]:
            return rule
    return AREA_RULES[-1]


def _summarize_area(rule: dict[str, Any], files: list[dict[str, Any]]) -> dict[str, Any]:
    zones = Counter(item["zone"] for item in files)
    safety = Counter(item["safetyClass"] for item in files)
    risks: Counter[str] = Counter()
    for item in files:
        risks.update(item.get("riskTags", []))
    review_required = sum(1 for item in files if item["safetyClass"] in {"HIGH_REVIEW", "REVIEW_REQUIRED"})
    return {
        "id": rule["id"],
        "title": rule["title"],
        "fileCount": len(files),
        "categories": sorted(rule["categories"]),
        "zones": dict(sorted(zones.items())),
        "safetyClasses": dict(sorted(safety.items())),
        "riskTags": dict(sorted(risks.items())),
        "reviewRequiredFiles": review_required,
        "action": rule["action"],
        "gatePolicy": rule["gatePolicy"],
        "movePolicy": rule["movePolicy"],
        "sampleSafePaths": [item["safePath"] for item in files[:20]],
    }


def _build_area_matrix(files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_area: dict[str, list[dict[str, Any]]] = defaultdict(list)
    rules_by_id = {rule["id"]: rule for rule in AREA_RULES}
    for item in files:
        rule = _area_for_category(item["category"])
        by_area[rule["id"]].append(item)
    return [_summarize_area(rules_by_id[rule["id"]], by_area.get(rule["id"], [])) for rule in AREA_RULES]


def _build_module_gate_matrix(
    module_manifest: dict[str, Any],
    zone_manifest: dict[str, Any],
    comm_manifest: dict[str, Any],
) -> dict[str, Any]:
    module_ids = {module["id"] for module in module_manifest.get("modules", [])}
    comm_by_id = {module["id"]: module for module in comm_manifest.get("modules", [])}
    zone_by_id = {zone["id"]: zone for zone in zone_manifest.get("zones", [])}
    zone_module_ids = {module_id for zone in zone_manifest.get("zones", []) for module_id in zone.get("modules", [])}
    module_rows = []
    unsafe_modules = []
    link_errors = []
    for module in module_manifest.get("modules", []):
        module_id = module["id"]
        comm = comm_by_id.get(module_id, {})
        zone_id = comm.get("zone")
        links_known = set(comm.get("upstream", [])).issubset(module_ids) and set(comm.get("downstream", [])).issubset(module_ids)
        safe_contract = (
            comm.get("allowedModes") == ["SANDBOX_ONLY"]
            and comm.get("sourceMutationAllowed") is False
            and comm.get("rawPayloadAllowed") is False
            and comm.get("piiPayloadAllowed") is False
            and not (set(comm.get("allowedEndpoints", [])) & FORBIDDEN_ENDPOINTS)
        )
        if not links_known:
            link_errors.append(module_id)
        if not safe_contract:
            unsafe_modules.append(module_id)
        module_rows.append(
            {
                "moduleId": module_id,
                "zone": zone_id,
                "sourceCount": len(module.get("sourceFiles", [])),
                "testCount": len(module.get("testFiles", [])),
                "auditCount": len(module.get("auditFiles", [])),
                "hasCommunication": module_id in comm_by_id,
                "hasZoneGate": module_id in zone_module_ids,
                "linksKnown": links_known,
                "safeContract": safe_contract,
                "allowedEndpoints": sorted(comm.get("allowedEndpoints", [])),
            }
        )
    return {
        "moduleCount": len(module_ids),
        "communicationCount": len(comm_by_id),
        "zoneCount": len(zone_by_id),
        "releaseZones": sorted(RELEASE_ZONES),
        "zoneGateIds": sorted(zone_by_id),
        "allModulesHaveCommunication": module_ids == set(comm_by_id),
        "allZoneModulesKnown": zone_module_ids.issubset(module_ids),
        "allReleaseZonesGated": RELEASE_ZONES.issubset(set(zone_by_id)),
        "unsafeModules": sorted(unsafe_modules),
        "linkErrors": sorted(link_errors),
        "modules": module_rows,
    }


def _build_zone_separation_matrix(files: list[dict[str, Any]], gate_matrix: dict[str, Any]) -> list[dict[str, Any]]:
    zone_counts = Counter(item["zone"] for item in files)
    gated = set(gate_matrix["zoneGateIds"])
    rows = []
    for zone, count in sorted(zone_counts.items()):
        rows.append(
            {
                "zone": zone,
                "fileCount": count,
                "releaseGate": zone in gated,
                "gateMode": "module_audit_and_zone_gate" if zone in gated else "inventory_review_only",
                "splitReadiness": "GATED" if zone in gated else "HOLD_FOR_REVIEW",
            }
        )
    return rows


def plan_detailed_separation(report_dir: Path = REPORT_DIR) -> dict[str, Any]:
    inventory_payload = inventory.classify_repo(report_dir=report_dir / "inventory_subrun")
    module_manifest = _load_json(MODULE_MANIFEST)
    zone_manifest = _load_json(ZONE_MANIFEST)
    comm_manifest = _load_json(COMM_MANIFEST)
    files = inventory_payload["files"]
    area_matrix = _build_area_matrix(files)
    gate_matrix = _build_module_gate_matrix(module_manifest, zone_manifest, comm_manifest)
    zone_matrix = _build_zone_separation_matrix(files, gate_matrix)
    failed = [
        not gate_matrix["allModulesHaveCommunication"],
        not gate_matrix["allZoneModulesKnown"],
        not gate_matrix["allReleaseZonesGated"],
        bool(gate_matrix["unsafeModules"]),
        bool(gate_matrix["linkErrors"]),
        inventory_payload["verdict"] != inventory.PASS_VERDICT,
    ]
    payload = {
        "schemaVersion": "hwpx_repo_detailed_separation_plan_v1",
        "verdict": FAIL_VERDICT if any(failed) else PASS_VERDICT,
        "baselineHead": inventory_payload["baselineHead"],
        "scope": "tracked_files_only_classification_no_move",
        "summary": {
            "totalFiles": inventory_payload["summary"]["totalFiles"],
            "areas": len(area_matrix),
            "zones": len(zone_matrix),
            "modules": gate_matrix["moduleCount"],
            "releaseZonesGated": sum(1 for item in zone_matrix if item["releaseGate"]),
            "holdZones": sum(1 for item in zone_matrix if not item["releaseGate"]),
            "legacyExperimentFiles": inventory_payload["summary"]["legacyExperimentFiles"],
            "unknownReviewRequiredFiles": inventory_payload["summary"]["unknownReviewRequiredFiles"],
        },
        "areaMatrix": area_matrix,
        "zoneSeparationMatrix": zone_matrix,
        "gateModuleLinkMatrix": gate_matrix,
        "security": {
            "piiLeak": 0,
            "rawPathLeak": 0,
            "rawFilenameLeak": 0,
            "aiApiAllowed": False,
            "ocrAllowed": False,
            "hancomRequired": False,
            "sourceMutationAllowed": False,
            "productionWriteAllowed": False,
        },
        "warnings": [
            "WARN_CLASSIFICATION_ONLY_NO_FILE_MOVE",
            "WARN_LEGACY_EXPERIMENT_QUARANTINE_REQUIRED",
            "WARN_UNKNOWN_REVIEW_REQUIRED_HOLD",
            "WARN_TRACKED_FILES_ONLY",
        ],
    }
    _write_reports(report_dir, payload)
    return payload


def _no_leak(text: str) -> bool:
    return not (ABS_PATH_RE.search(text) or RAW_FILENAME_RE.search(text) or PII_RE.search(text))


def _safe_write(path: Path, payload: Any) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if not _no_leak(text):
        raise ValueError(f"unsafe detailed separation payload: {path.name}")
    path.write_text(text, encoding="utf-8")


def _write_reports(report_dir: Path, payload: dict[str, Any]) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    _safe_write(report_dir / "detailed_separation_plan.json", payload)
    _safe_write(report_dir / "detailed_separation_matrix.json", payload["areaMatrix"])
    _safe_write(report_dir / "zone_separation_matrix.json", payload["zoneSeparationMatrix"])
    _safe_write(report_dir / "gate_module_link_matrix.json", payload["gateModuleLinkMatrix"])
    lines = [
        "# HWPX Repo Detailed Separation Plan",
        "",
        f"- verdict: {payload['verdict']}",
        f"- baseline: {payload['baselineHead']}",
        f"- scope: {payload['scope']}",
        f"- total files: {payload['summary']['totalFiles']}",
        f"- modules linked: {payload['gateModuleLinkMatrix']['moduleCount']}",
        f"- release zones gated: {payload['summary']['releaseZonesGated']}",
        f"- hold zones: {payload['summary']['holdZones']}",
        f"- security: pii={payload['security']['piiLeak']} rawPath={payload['security']['rawPathLeak']} rawFilename={payload['security']['rawFilenameLeak']}",
        "",
        "## Areas",
    ]
    for area in payload["areaMatrix"]:
        lines.append(
            f"- {area['id']}: files={area['fileCount']} action={area['action']} move={area['movePolicy']}"
        )
    lines.extend(["", "## Zone Gates"])
    for zone in payload["zoneSeparationMatrix"]:
        lines.append(
            f"- {zone['zone']}: files={zone['fileCount']} gate={zone['releaseGate']} readiness={zone['splitReadiness']}"
        )
    lines.extend(["", "## Next Work"])
    lines.append("- no file move/delete before owner review")
    lines.append("- wire detailed modules only after zone gate remains green")
    lines.append("- keep legacy and unknown files in hold until classified")
    text = "\n".join(lines) + "\n"
    if not _no_leak(text):
        raise ValueError("unsafe detailed separation markdown")
    (report_dir / "detailed_separation_summary.md").write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", default=str(REPORT_DIR))
    args = parser.parse_args()
    payload = plan_detailed_separation(report_dir=Path(args.report_dir))
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["verdict"] == PASS_VERDICT else 1


if __name__ == "__main__":
    raise SystemExit(main())
