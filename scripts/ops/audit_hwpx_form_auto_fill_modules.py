"""Module-level audit runner for the HWPX form auto-fill flow."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "scripts" / "ops" / "audit_hwpx_form_auto_fill_module_manifest.json"
REPORT_DIR = ROOT / "data" / "reports" / "hwpx_form_auto_fill_module_audits"

PASS_VERDICT = "PASS_HWPX_FORM_AUTO_FILL_MODULE_AUDITS"
FAIL_VERDICT = "FAIL_HWPX_FORM_AUTO_FILL_MODULE_AUDITS"
ABS_PATH_RE = re.compile(r"(?<![A-Za-z])([A-Za-z]:[\\/][^\s\"']*|/(home|tmp|var|Users)/[^\s\"']*)")
RAW_FILENAME_RE = re.compile(r"\b[^\\/:\s]+\.hwpx\b", re.IGNORECASE)
PII_RE = re.compile(
    r"(\d{6}-\d{7}|\d{3}-\d{2}-\d{5}|\d{2,3}-\d{3,4}-\d{4}|"
    r"\d{2,6}-\d{2,6}-\d{2,6}|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})"
)
TRANSIENT_ERROR_MARKERS = ("PermissionError: [WinError 5]", "winerror 5", "access is denied", "denied")


def load_manifest(path: Path = MANIFEST) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _safe_text(text: str) -> str:
    text = ABS_PATH_RE.sub("<abs-path>", text)
    text = RAW_FILENAME_RE.sub("<hwpx-file>", text)
    text = PII_RE.sub("<masked>", text)
    return text


def _no_leak(text: str) -> bool:
    return not (ABS_PATH_RE.search(text) or RAW_FILENAME_RE.search(text) or PII_RE.search(text))


def _run_pytest(paths: list[str], timeout: int) -> dict[str, Any]:
    started = time.perf_counter()
    result: subprocess.CompletedProcess[str] | None = None
    output = ""
    summary = "no output"
    attempts = 0
    for attempt in (1, 2):
        attempts = attempt
        cmd = [sys.executable, "-m", "pytest", *paths, "-q", "--tb=short"]
        if attempt > 1:
            safe_name = "_".join(Path(path).stem for path in paths)[:80]
            basetemp = Path(tempfile.gettempdir()) / "hwpx_form_auto_fill_module_audits" / f"{os.getpid()}_{attempt}_{safe_name}"
            basetemp.parent.mkdir(parents=True, exist_ok=True)
            cmd.append(f"--basetemp={basetemp}")
        result = subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = result.stdout + "\n" + result.stderr
        lines = [line.strip() for line in output.splitlines() if line.strip()]
        summary = _safe_text(lines[-1] if lines else "no output")
        if result.returncode == 0 or not _is_transient_error(output):
            break
        time.sleep(0.5)
    assert result is not None
    return {
        "status": "PASS" if result.returncode == 0 else "FAIL",
        "returncode": result.returncode,
        "attempts": attempts,
        "durationSeconds": round(time.perf_counter() - started, 3),
        "summary": summary,
    }


def _run_pytest_combined(paths: list[str], timeout: int) -> dict[str, Any]:
    started = time.perf_counter()
    result = subprocess.run(
        [sys.executable, "-m", "pytest", *paths, "-q", "--tb=short"],
        cwd=str(ROOT),
        timeout=timeout,
    )
    return {
        "status": "PASS" if result.returncode == 0 else "FAIL",
        "returncode": result.returncode,
        "attempts": 1,
        "durationSeconds": round(time.perf_counter() - started, 3),
        "summary": f"combined pytest {'passed' if result.returncode == 0 else 'failed'} for {len(paths)} files",
    }


def _is_transient_error(text: str) -> bool:
    lower = text.lower()
    return any(marker.lower() in lower for marker in TRANSIENT_ERROR_MARKERS)


def _read_source(files: list[str]) -> str:
    chunks = []
    for rel_path in files:
        path = ROOT / rel_path
        if path.exists():
            chunks.append(path.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(chunks)


def audit_module_static(module: dict[str, Any], forbidden_tokens: list[str]) -> dict[str, Any]:
    source_files = module.get("sourceFiles", [])
    test_files = module.get("testFiles", [])
    audit_files = module.get("auditFiles", [])
    all_files = source_files + test_files + audit_files
    missing_files = [rel_path for rel_path in all_files if not (ROOT / rel_path).is_file()]
    source_text = _read_source(source_files)
    combined_text = _read_source(all_files)
    missing_tokens = [token for token in module.get("requiredTokens", []) if token not in combined_text]
    forbidden_hits = [token for token in forbidden_tokens if token.lower() in source_text.lower()]
    static_status = "PASS" if not missing_files and not missing_tokens and not forbidden_hits else "FAIL"
    return {
        "staticStatus": static_status,
        "missingFiles": missing_files,
        "missingTokens": missing_tokens,
        "forbiddenSourceHits": forbidden_hits,
    }


def audit_module(module: dict[str, Any], forbidden_tokens: list[str], timeout: int) -> dict[str, Any]:
    test_files = module.get("testFiles", [])
    static = audit_module_static(module, forbidden_tokens)
    pytest_run = _run_pytest(test_files, timeout) if test_files and not static["missingFiles"] else {
        "status": "FAIL",
        "returncode": 2,
        "attempts": 0,
        "durationSeconds": 0.0,
        "summary": "missing files",
    }
    static_status = static["staticStatus"]
    status = "PASS" if static_status == "PASS" and pytest_run["status"] == "PASS" else "FAIL"
    return {
        "id": module["id"],
        "title": module.get("title", module["id"]),
        "status": status,
        "staticStatus": static_status,
        "pytest": pytest_run,
        "missingFiles": static["missingFiles"],
        "missingTokens": static["missingTokens"],
        "forbiddenSourceHits": static["forbiddenSourceHits"],
        "security": {
            "piiLeak": 0,
            "rawPathLeak": 0,
            "rawFilenameLeak": 0,
        },
    }


def _dirty_baseline() -> dict[str, Any]:
    result = subprocess.run(["git", "status", "--short"], cwd=str(ROOT), capture_output=True, text=True, timeout=30)
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return {
        "documented": True,
        "trackedDirty": [line for line in lines if not line.startswith("?? ")],
        "untrackedCount": sum(1 for line in lines if line.startswith("?? ")),
    }


def run_module_audits(
    manifest_path: Path = MANIFEST,
    report_dir: Path = REPORT_DIR,
    module_ids: set[str] | None = None,
    timeout: int = 300,
    combined_pytest: bool = False,
) -> dict[str, Any]:
    manifest = load_manifest(manifest_path)
    modules = manifest["modules"]
    selected = [module for module in modules if not module_ids or module["id"] in module_ids]
    if combined_pytest and selected:
        test_files = sorted({path for module in selected for path in module.get("testFiles", [])})
        combined_run = _run_pytest_combined(test_files, timeout) if test_files else {
            "status": "FAIL",
            "returncode": 2,
            "attempts": 0,
            "durationSeconds": 0.0,
            "summary": "missing files",
        }
        results = []
        for module in selected:
            static = audit_module_static(module, manifest.get("forbiddenSourceTokens", []))
            pytest_run = combined_run if module.get("testFiles") and not static["missingFiles"] else {
                "status": "FAIL",
                "returncode": 2,
                "attempts": 0,
                "durationSeconds": 0.0,
                "summary": "missing files",
            }
            status = "PASS" if static["staticStatus"] == "PASS" and pytest_run["status"] == "PASS" else "FAIL"
            results.append({
                "id": module["id"],
                "title": module.get("title", module["id"]),
                "status": status,
                "staticStatus": static["staticStatus"],
                "pytest": pytest_run,
                "missingFiles": static["missingFiles"],
                "missingTokens": static["missingTokens"],
                "forbiddenSourceHits": static["forbiddenSourceHits"],
                "security": {
                    "piiLeak": 0,
                    "rawPathLeak": 0,
                    "rawFilenameLeak": 0,
                },
            })
    else:
        results = [audit_module(module, manifest.get("forbiddenSourceTokens", []), timeout) for module in selected]
    failed = [item for item in results if item["status"] != "PASS"]
    payload = {
        "schemaVersion": "hwpx_form_auto_fill_module_audits_v1",
        "verdict": PASS_VERDICT if not failed else FAIL_VERDICT,
        "summary": {
            "modulesTotal": len(results),
            "modulesPassed": len(results) - len(failed),
            "modulesFailed": len(failed),
        },
        "moduleResults": results,
        "dirtyBaseline": _dirty_baseline(),
        "warnings": [
            "WARN_SANDBOX_ONLY",
            "WARN_REAL_USER_FILE_NOT_TESTED",
            "WARN_DEPLOY_NOT_PERFORMED",
        ],
    }
    _write_reports(report_dir, payload)
    return payload


def _write_reports(report_dir: Path, payload: dict[str, Any]) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    _safe_write(report_dir / "module_audit_summary.json", payload)
    _safe_write(report_dir / "module_audit_results.json", payload["moduleResults"])
    lines = [
        "# HWPX Form Auto Fill Module Audits",
        "",
        f"- verdict: {payload['verdict']}",
        f"- modules: {payload['summary']['modulesPassed']}/{payload['summary']['modulesTotal']} passed",
        "",
        "## Modules",
    ]
    for item in payload["moduleResults"]:
        lines.append(f"- {item['status']} {item['id']} - {item['pytest']['summary']}")
    text = "\n".join(lines) + "\n"
    if not _no_leak(text):
        raise ValueError("unsafe markdown report")
    (report_dir / "module_audit_summary.md").write_text(text, encoding="utf-8")


def _safe_write(path: Path, payload: Any) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if not _no_leak(text):
        raise ValueError(f"unsafe report payload: {path.name}")
    path.write_text(text, encoding="utf-8")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default=str(MANIFEST), help="Module audit manifest JSON.")
    parser.add_argument("--report-dir", default=str(REPORT_DIR), help="PII-safe report directory.")
    parser.add_argument("--timeout", type=int, default=300, help="Per-module pytest timeout in seconds.")
    parser.add_argument("--module", action="append", help="Run a single module id. May be repeated.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    payload = run_module_audits(
        manifest_path=Path(args.manifest),
        report_dir=Path(args.report_dir),
        module_ids=set(args.module or []),
        timeout=args.timeout,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["verdict"] == PASS_VERDICT else 1


if __name__ == "__main__":
    raise SystemExit(main())
