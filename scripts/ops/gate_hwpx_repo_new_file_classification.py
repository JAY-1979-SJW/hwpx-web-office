"""Gate new files so they must be classified into repo zones and module scope."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.ops import classify_hwpx_repo_inventory as inventory  # noqa: E402
from scripts.ops import plan_hwpx_repo_detailed_separation as separation  # noqa: E402

REPORT_DIR = ROOT / "data" / "reports" / "hwpx_repo_new_file_classification"
MODULE_MANIFEST = ROOT / "scripts" / "ops" / "audit_hwpx_form_auto_fill_module_manifest.json"

PASS_VERDICT = "PASS_HWPX_REPO_NEW_FILE_CLASSIFICATION_GATE"
FAIL_VERDICT = "FAIL_HWPX_REPO_NEW_FILE_CLASSIFICATION_GATE"

FAIL_NEW_FILE_UNKNOWN_CLASSIFICATION = "FAIL_NEW_FILE_UNKNOWN_CLASSIFICATION"
FAIL_NEW_FILE_UNASSIGNED_ZONE = "FAIL_NEW_FILE_UNASSIGNED_ZONE"
FAIL_NEW_FILE_MODULE_MANIFEST_REQUIRED = "FAIL_NEW_FILE_MODULE_MANIFEST_REQUIRED"
FAIL_NEW_FILE_REPORT_UNCLASSIFIED = "FAIL_NEW_FILE_REPORT_UNCLASSIFIED"
FAIL_UNSAFE_REPORT = "FAIL_UNSAFE_REPORT"

RELEASE_ZONES = separation.RELEASE_ZONES
CODE_SUFFIXES = {".py", ".mjs", ".js", ".ts", ".tsx", ".html", ".json", ".md"}
IGNORE_PREFIXES = (
    "docs/devlog/",
    "reports/",
)


def _load_module_manifest(path: Path = MODULE_MANIFEST) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _declared_paths(manifest: dict[str, Any]) -> set[str]:
    paths: set[str] = set()
    for module in manifest.get("modules", []):
        for key in ("sourceFiles", "testFiles", "auditFiles"):
            paths.update(item.replace("\\", "/") for item in module.get(key, []))
    return paths


def _run_lines(command: list[str]) -> list[str]:
    result = subprocess.run(
        command,
        cwd=str(ROOT),
        capture_output=True,
        text=True, encoding="utf-8", errors="replace",
        timeout=60,
        check=True,
    )
    return [line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()]


def detect_new_files() -> dict[str, list[str]]:
    staged = _run_lines(["git", "diff", "--cached", "--name-only", "--diff-filter=A"])
    untracked = _run_lines(["git", "ls-files", "--others", "--exclude-standard"])
    return {"stagedAdded": staged, "untracked": untracked}


def _ignored(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in IGNORE_PREFIXES)


def _needs_zone(path: str) -> bool:
    suffix = Path(path).suffix.lower()
    if suffix not in CODE_SUFFIXES:
        return False
    return path.startswith(("scripts/", "frontend/", "tests/", "docs/", "data/reports/"))


def _needs_module_manifest(path: str, category: str, zone: str) -> bool:
    if zone not in RELEASE_ZONES:
        return False
    if category not in {"ACTIVE_AUTOFILL", "FRONTEND_VIEWER", "TEST_ONLY", "TEST_FIXTURE"}:
        return False
    if path.startswith("scripts/hwpx/pipeline/"):
        return True
    if path.startswith("frontend/web_office_viewer/form_autofill"):
        return True
    if path.startswith("tests/test_hwpx_form_") or path.startswith("tests/test_hwpx_form_writer_"):
        return True
    if path in {"tests/test_hwpx_review_panel.py", "tests/test_hwpx_approval_gate.py"}:
        return True
    return False


def evaluate_new_files(
    new_files: list[str],
    module_manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    manifest = module_manifest or _load_module_manifest()
    declared = _declared_paths(manifest)
    ignored = [path for path in new_files if _ignored(path)]
    candidates = [path for path in new_files if path not in ignored]
    results = []
    failures: set[str] = set()
    for path in sorted(dict.fromkeys(candidates)):
        category, zone, separation_plan = inventory.classify_path(path)
        file_failures: list[str] = []
        if category == "UNKNOWN_REVIEW_REQUIRED":
            file_failures.append(FAIL_NEW_FILE_UNKNOWN_CLASSIFICATION)
        if _needs_zone(path) and zone == "unassigned":
            file_failures.append(FAIL_NEW_FILE_UNASSIGNED_ZONE)
        if path.startswith("data/reports/") and category != "REPORT_DOC":
            file_failures.append(FAIL_NEW_FILE_REPORT_UNCLASSIFIED)
        if _needs_module_manifest(path, category, zone) and path not in declared:
            file_failures.append(FAIL_NEW_FILE_MODULE_MANIFEST_REQUIRED)
        failures.update(file_failures)
        results.append(
            {
                "safePath": inventory.safe_path(path),
                "category": category,
                "zone": zone,
                "separationPlan": separation_plan,
                "moduleDeclared": path in declared,
                "status": "PASS" if not file_failures else "FAIL",
                "failures": sorted(set(file_failures)),
            }
        )
    return {
        "schemaVersion": "hwpx_repo_new_file_classification_gate_v1",
        "verdict": PASS_VERDICT if not failures else FAIL_VERDICT,
        "summary": {
            "newFiles": len(candidates),
            "ignoredFiles": len(ignored),
            "passedFiles": sum(1 for item in results if item["status"] == "PASS"),
            "failedFiles": sum(1 for item in results if item["status"] != "PASS"),
        },
        "newFileResults": results,
        "ignoredSafePaths": [inventory.safe_path(path) for path in ignored],
        "failures": sorted(failures),
        "security": {
            "piiLeak": 0,
            "rawPathLeak": 0,
            "rawFilenameLeak": 0,
        },
        "warnings": [
            "WARN_NEW_FILES_MUST_BE_CLASSIFIED",
            "WARN_DEVLOG_AND_REPORTS_HOLD_IGNORED",
        ],
    }


def run_new_file_classification_gate(
    report_dir: Path = REPORT_DIR,
    new_files: list[str] | None = None,
    module_manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if new_files is None:
        detected = detect_new_files()
        ordered = detected["stagedAdded"] + [path for path in detected["untracked"] if path not in detected["stagedAdded"]]
    else:
        ordered = [path.replace("\\", "/") for path in new_files]
    payload = evaluate_new_files(ordered, module_manifest=module_manifest)
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
        raise ValueError(f"{FAIL_UNSAFE_REPORT}: {path.name}")
    path.write_text(text, encoding="utf-8")


def _write_reports(report_dir: Path, payload: dict[str, Any]) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    _safe_write(report_dir / "new_file_classification_summary.json", payload)
    _safe_write(report_dir / "new_file_classification_results.json", payload["newFileResults"])
    lines = [
        "# HWPX Repo New File Classification Gate",
        "",
        f"- verdict: {payload['verdict']}",
        f"- newFiles: {payload['summary']['newFiles']}",
        f"- ignoredFiles: {payload['summary']['ignoredFiles']}",
        f"- passedFiles: {payload['summary']['passedFiles']}",
        f"- failedFiles: {payload['summary']['failedFiles']}",
        f"- security: pii={payload['security']['piiLeak']} rawPath={payload['security']['rawPathLeak']} rawFilename={payload['security']['rawFilenameLeak']}",
        "",
        "## Contract",
        "- new files cannot remain UNKNOWN_REVIEW_REQUIRED",
        "- code-bearing new files cannot stay in the unassigned zone",
        "- new runtime/frontend/test files in release zones must be declared in the module manifest",
    ]
    text = "\n".join(lines) + "\n"
    if not _no_leak(text):
        raise ValueError(FAIL_UNSAFE_REPORT)
    (report_dir / "new_file_classification_summary.md").write_text(text, encoding="utf-8")


def _load_paths(path: str | None) -> list[str] | None:
    if not path:
        return None
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", default=str(REPORT_DIR))
    parser.add_argument("--new-files-json")
    args = parser.parse_args()
    payload = run_new_file_classification_gate(
        report_dir=Path(args.report_dir),
        new_files=_load_paths(args.new_files_json),
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["verdict"] == PASS_VERDICT else 1


if __name__ == "__main__":
    raise SystemExit(main())
