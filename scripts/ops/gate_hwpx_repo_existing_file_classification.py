"""Gate tracked governed files so they stay classified by zone and module scope."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.ops import classify_hwpx_repo_inventory as inventory  # noqa: E402
from scripts.ops import gate_hwpx_repo_new_file_classification as new_file_gate  # noqa: E402

REPORT_DIR = ROOT / "data" / "reports" / "hwpx_repo_existing_file_classification"

PASS_VERDICT = "PASS_HWPX_REPO_EXISTING_FILE_CLASSIFICATION_GATE"
FAIL_VERDICT = "FAIL_HWPX_REPO_EXISTING_FILE_CLASSIFICATION_GATE"

FAIL_EXISTING_FILE_MODULE_UNRESOLVED = "FAIL_EXISTING_FILE_MODULE_UNRESOLVED"

GOVERNED_TESTS = (
    "tests/test_hwpx_form_",
    "tests/test_hwpx_form_writer_",
    "tests/test_hwpx_form_autofill_",
    "tests/test_hwpx_review_panel.py",
    "tests/test_hwpx_approval_gate.py",
)


def _governed_scope(path: str) -> bool:
    return (
        path.startswith("app/backend/routes/hwpx_form_")
        or path.startswith("scripts/hwpx/pipeline/")
        or path.startswith("scripts/ops/hwpx_form_")
        or path.startswith("scripts/ops/gate_hwpx_form_")
        or path.startswith("scripts/ops/audit_hwpx_form_")
        or path.startswith("scripts/ops/install_hwpx_form_auto_fill_")
        or path.startswith("frontend/web_office_viewer/form_autofill")
        or path.startswith(GOVERNED_TESTS)
    )


def _declared_module_map(manifest: dict[str, Any]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for module in manifest.get("modules", []):
        module_id = str(module.get("id", ""))
        for key in ("sourceFiles", "testFiles", "auditFiles"):
            for path in module.get(key, []):
                mapping[str(path).replace("\\", "/")] = module_id
    return mapping


def _needs_zone(path: str) -> bool:
    return new_file_gate._needs_zone(path)


def _needs_module_assignment(path: str, category: str, zone: str) -> bool:
    if zone not in new_file_gate.RELEASE_ZONES:
        return False
    if category not in {"ACTIVE_AUTOFILL", "FRONTEND_VIEWER", "AUDIT_GATE", "TEST_ONLY", "TEST_FIXTURE"}:
        return False
    return _governed_scope(path)


def _infer_module_id(path: str, zone: str) -> str | None:
    lower = path.lower()
    if zone == "input_parse":
        if any(
            token in lower
            for token in (
                "field_mapping",
                "field_mapper",
                "field_catalog",
                "index_and_recommend",
                "type_classification",
                "construction_work_design",
                "parser",
                "preflight",
                "upload_document",
            )
        ):
            return "field_mapping"
    if zone == "review_approval":
        if "approval" in lower or "human_approval" in lower:
            return "approval_gate"
        if "review" in lower:
            return "review_panel"
    if zone == "writer_readback":
        if "writer_sandbox" in lower or "write_sandbox" in lower:
            return "writer_sandbox"
        if "readback" in lower:
            return "readback_hardening"
    if zone == "download_export":
        if "final_export" in lower:
            return "final_export_gate"
        if "download_review" in lower:
            return "download_review"
    if zone == "batch_api_browser":
        if any(token in lower for token in ("api_route", "api_batch", "batch_api_route", "module_communication")):
            return "api_batch"
        if any(
            token in lower
            for token in (
                "browser",
                "frontend_contract",
                "ui_connect",
                "real_like",
                "e2e_smoke",
            )
        ):
            return "api_browser_e2e"
    if zone == "closeout_security":
        return "user_flow_closeout"
    return None


def evaluate_existing_files(
    tracked_files: list[str],
    module_manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    manifest = module_manifest or new_file_gate._load_module_manifest()
    declared_map = _declared_module_map(manifest)
    governed = [path.replace("\\", "/") for path in tracked_files if _governed_scope(path.replace("\\", "/"))]
    results: list[dict[str, Any]] = []
    failures: set[str] = set()
    for path in sorted(dict.fromkeys(governed)):
        category, zone, separation_plan = inventory.classify_path(path)
        declared_module = declared_map.get(path)
        resolved_module = declared_module or _infer_module_id(path, zone)
        file_failures: list[str] = []
        if category == "UNKNOWN_REVIEW_REQUIRED":
            file_failures.append(new_file_gate.FAIL_NEW_FILE_UNKNOWN_CLASSIFICATION)
        if _needs_zone(path) and zone == "unassigned":
            file_failures.append(new_file_gate.FAIL_NEW_FILE_UNASSIGNED_ZONE)
        if _needs_module_assignment(path, category, zone) and not resolved_module:
            file_failures.append(FAIL_EXISTING_FILE_MODULE_UNRESOLVED)
        failures.update(file_failures)
        results.append(
            {
                "safePath": inventory.safe_path(path),
                "category": category,
                "zone": zone,
                "separationPlan": separation_plan,
                "moduleDeclared": bool(declared_module),
                "moduleId": resolved_module,
                "status": "PASS" if not file_failures else "FAIL",
                "failures": sorted(set(file_failures)),
            }
        )
    return {
        "schemaVersion": "hwpx_repo_existing_file_classification_gate_v1",
        "verdict": PASS_VERDICT if not failures else FAIL_VERDICT,
        "summary": {
            "trackedFiles": len(tracked_files),
            "governedFiles": len(governed),
            "passedFiles": sum(1 for item in results if item["status"] == "PASS"),
            "failedFiles": sum(1 for item in results if item["status"] != "PASS"),
        },
        "existingFileResults": results,
        "failures": sorted(failures),
        "security": {
            "piiLeak": 0,
            "rawPathLeak": 0,
            "rawFilenameLeak": 0,
        },
        "warnings": [
            "WARN_EXISTING_GOVERNED_SCOPE_ONLY",
            "WARN_LEGACY_QUARANTINE_NOT_FORCED_BY_THIS_GATE",
        ],
    }


def run_existing_file_classification_gate(
    report_dir: Path = REPORT_DIR,
    tracked_files: list[str] | None = None,
    module_manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    files = tracked_files if tracked_files is not None else inventory._run_git_ls_files()
    payload = evaluate_existing_files(files, module_manifest=module_manifest)
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
        raise ValueError(f"{new_file_gate.FAIL_UNSAFE_REPORT}: {path.name}")
    path.write_text(text, encoding="utf-8")


def _write_reports(report_dir: Path, payload: dict[str, Any]) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    _safe_write(report_dir / "existing_file_classification_summary.json", payload)
    _safe_write(report_dir / "existing_file_classification_results.json", payload["existingFileResults"])
    lines = [
        "# HWPX Repo Existing File Classification Gate",
        "",
        f"- verdict: {payload['verdict']}",
        f"- trackedFiles: {payload['summary']['trackedFiles']}",
        f"- governedFiles: {payload['summary']['governedFiles']}",
        f"- passedFiles: {payload['summary']['passedFiles']}",
        f"- failedFiles: {payload['summary']['failedFiles']}",
        f"- security: pii={payload['security']['piiLeak']} rawPath={payload['security']['rawPathLeak']} rawFilename={payload['security']['rawFilenameLeak']}",
        "",
        "## Contract",
        "- existing governed files cannot remain UNKNOWN_REVIEW_REQUIRED",
        "- existing governed code files cannot stay in the unassigned zone",
        "- existing governed release-zone files must resolve to a module owner by declaration or stable path mapping",
    ]
    text = "\n".join(lines) + "\n"
    if not _no_leak(text):
        raise ValueError(new_file_gate.FAIL_UNSAFE_REPORT)
    (report_dir / "existing_file_classification_summary.md").write_text(text, encoding="utf-8")


def _load_paths(path: str | None) -> list[str] | None:
    if not path:
        return None
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", default=str(REPORT_DIR))
    parser.add_argument("--tracked-files-json")
    args = parser.parse_args()
    payload = run_existing_file_classification_gate(
        report_dir=Path(args.report_dir),
        tracked_files=_load_paths(args.tracked_files_json),
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["verdict"] == PASS_VERDICT else 1


if __name__ == "__main__":
    raise SystemExit(main())
