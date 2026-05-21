#!/usr/bin/env python3
"""Read-only P7 audit for handler-to-gate runtime connection readiness."""
from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

HANDLERS = {
    "convert": Path("src/main/java/com/haehan/engine/http/ConvertHwpToHwpxHandler.java"),
    "hwpx_upload": Path("src/main/java/com/haehan/engine/http/HwpxUploadHandler.java"),
    "inspection": Path("src/main/java/com/haehan/engine/http/InspectionPageHandler.java"),
}

GATE_FILES = {
    "file_type": Path("src/main/java/com/haehan/engine/gate/FileTypeGate.java"),
    "upload_security": Path("src/main/java/com/haehan/engine/gate/UploadSecurityGate.java"),
    "execution_location": Path("src/main/java/com/haehan/engine/gate/ExecutionLocationGate.java"),
    "output_artifact": Path("src/main/java/com/haehan/engine/gate/OutputArtifactGate.java"),
    "gate_result": Path("src/main/java/com/haehan/engine/gate/GateResult.java"),
}

EXPECTED_ENDPOINTS = {
    "/convert-hwp-to-hwpx": "ConvertHwpToHwpxHandler",
    "/hwpx-editor": "HwpxUploadHandler",
    "/hwpx-upload": "HwpxUploadHandler",
    "/inspection": "InspectionPageHandler",
}


@dataclass
class Finding:
    severity: str
    rule: str
    path: str
    detail: str


def run_git(args: list[str]) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True, stderr=subprocess.DEVNULL)


def git_status(path: Path) -> str:
    out = run_git(["status", "--short", "--", path.as_posix()]).strip()
    return out[:2] if out else "clean"


def is_tracked(path: Path) -> bool:
    try:
        subprocess.check_output(["git", "ls-files", "--error-unmatch", path.as_posix()], cwd=ROOT, stderr=subprocess.DEVNULL)
        return True
    except subprocess.CalledProcessError:
        return False


def read(path: Path) -> str:
    try:
        return (ROOT / path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def line_count(text: str) -> int:
    return text.count("\n") + (1 if text else 0)


def diff_numstat(path: Path) -> dict[str, int | None]:
    try:
        out = run_git(["diff", "--numstat", "--", path.as_posix()]).strip()
    except subprocess.CalledProcessError:
        return {"insertions": None, "deletions": None}
    if not out:
        return {"insertions": 0, "deletions": 0}
    parts = out.split()
    try:
        return {"insertions": int(parts[0]), "deletions": int(parts[1])}
    except (IndexError, ValueError):
        return {"insertions": None, "deletions": None}


VIEW_COMPANION: dict[str, Path] = {
    "hwpx_upload": Path("src/main/java/com/haehan/engine/http/HwpxUploadPageView.java"),
}

# After P9B, gate refs moved from HwpxUploadPageView into HwpxUploadPageGatePolicy;
# LOCAL_WORKER_REQUIRED string literal lives in HwpxUploadPageScripts.java
P9B_COMPANIONS: dict[str, list[Path]] = {
    "hwpx_upload": [
        Path("src/main/java/com/haehan/engine/http/HwpxUploadPageGatePolicy.java"),
        Path("src/main/java/com/haehan/engine/http/HwpxUploadPageScripts.java"),
    ],
}


def handler_record(name: str, path: Path) -> dict:
    text = read(path)
    # After P9A view split, gate refs may live in a companion view file
    view_path = VIEW_COMPANION.get(name)
    view_text = read(view_path) if view_path and (ROOT / view_path).exists() else ""
    extra_texts = "".join(
        read(p) for p in P9B_COMPANIONS.get(name, []) if (ROOT / p).exists()
    )
    combined = text + view_text + extra_texts
    status = git_status(path)
    tracked = is_tracked(path)
    return {
        "name": name,
        "path": path.as_posix(),
        "view_path": view_path.as_posix() if view_path else None,
        "exists": (ROOT / path).exists(),
        "tracked": tracked,
        "git_status": status,
        "lines": line_count(text),
        "diff_numstat": diff_numstat(path) if tracked else None,
        "references": {
            "FileTypeGate": "FileTypeGate" in combined,
            "UploadSecurityGate": "UploadSecurityGate" in combined,
            "ExecutionLocationGate": "ExecutionLocationGate" in combined,
            "OutputArtifactGate": "OutputArtifactGate" in combined,
            "LOCAL_WORKER_REQUIRED": "LOCAL_WORKER_REQUIRED" in combined,
            "X_Conversion_Gate_header": "X-Conversion-Gate" in combined,
        },
    }


def endpoint_status() -> dict[str, bool]:
    server_text = read(Path("src/main/java/com/haehan/engine/http/EngineHttpServer.java"))
    return {
        endpoint: (endpoint in server_text and handler in server_text)
        for endpoint, handler in EXPECTED_ENDPOINTS.items()
    }


def audit() -> dict:
    findings: list[Finding] = []
    gate_presence = {name: (ROOT / path).exists() for name, path in GATE_FILES.items()}
    handlers = {name: handler_record(name, path) for name, path in HANDLERS.items()}
    endpoints = endpoint_status()

    for name, exists in gate_presence.items():
        if not exists:
            findings.append(Finding("FAIL", "gate_skeleton_missing", GATE_FILES[name].as_posix(), "required gate skeleton file is missing"))

    convert = handlers["convert"]
    if convert["git_status"] == "??":
        findings.append(Finding("WARN", "convert_handler_untracked_connection_deferred", convert["path"], "handler is untracked; committing P7 hunk would include the whole pre-existing file"))
    if not convert["references"]["ExecutionLocationGate"]:
        findings.append(Finding("WARN", "convert_handler_execution_gate_reference_missing", convert["path"], "ExecutionLocationGate is not directly referenced yet"))
    if convert["references"]["X_Conversion_Gate_header"] or convert["references"]["LOCAL_WORKER_REQUIRED"]:
        findings.append(Finding("WARN", "convert_handler_has_preexisting_gate_signals", convert["path"], "pre-existing conversion gate signals exist but should be normalized through ExecutionLocationGate"))

    hwpx = handlers["hwpx_upload"]
    if hwpx["git_status"].strip() and hwpx["git_status"] != "clean":
        findings.append(Finding("WARN", "hwpx_upload_tracked_dirty_connection_deferred", hwpx["path"], "handler already has tracked dirty content; gate hunk is not safely separable"))
    if not (hwpx["references"]["FileTypeGate"] and hwpx["references"]["UploadSecurityGate"]):
        findings.append(Finding("WARN", "hwpx_upload_file_upload_gate_reference_missing", hwpx["path"], "FileTypeGate/UploadSecurityGate are not directly referenced yet"))
    if not hwpx["references"]["ExecutionLocationGate"]:
        findings.append(Finding("WARN", "hwpx_upload_execution_location_gate_reference_missing", hwpx["path"], "ExecutionLocationGate is not directly referenced in HwpxUploadHandler"))

    inspection = handlers["inspection"]
    if inspection["lines"] >= 500:
        findings.append(Finding("WARN", "inspection_large_handler_deferred", inspection["path"], "large inspection page handler remains P8 candidate"))
    if not inspection["references"]["OutputArtifactGate"]:
        findings.append(Finding("WARN", "inspection_output_gate_reference_missing", inspection["path"], "OutputArtifactGate is not directly referenced yet"))

    for endpoint, ok in endpoints.items():
        if not ok:
            findings.append(Finding("FAIL", "expected_endpoint_missing", "src/main/java/com/haehan/engine/http/EngineHttpServer.java", f"expected endpoint mapping is not visible: {endpoint}"))

    hwpx_gate_connected = (
        hwpx["references"]["FileTypeGate"]
        and hwpx["references"]["UploadSecurityGate"]
        and hwpx["references"]["ExecutionLocationGate"]
    )
    handler_commit_eligible = {
        "convert": False,
        "hwpx_upload": hwpx_gate_connected,
        "inspection": False,
        "reason": "P7/P8 handler gate hunks are safely separable only when all required gates are connected in the handler",
    }

    severities = {item.severity for item in findings}
    status = "FAIL" if "FAIL" in severities else ("WARN" if "WARN" in severities else "PASS")
    return {
        "audit": "handler_gate_runtime_connections",
        "phase": "P7",
        "status": status,
        "gate_presence": gate_presence,
        "handlers": handlers,
        "expected_endpoint_mappings_visible": endpoints,
        "handler_commit_eligible": handler_commit_eligible,
        "finding_count": len(findings),
        "findings": [asdict(item) for item in findings],
        "policy": {
            "no_endpoint_path_change": True,
            "no_api_response_key_change": True,
            "no_external_execution": True,
            "no_db_write": True,
            "push_forbidden": True,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", dest="json_path")
    args = parser.parse_args()
    result = audit()
    print(f"handler_gate_runtime_connection_status={result['status']}")
    print(f"finding_count={result['finding_count']}")
    for name, record in result["handlers"].items():
        print(f"handler={name} status={record['git_status']} lines={record['lines']}")
    for item in result["findings"][:20]:
        print(f"{item['severity']} {item['rule']} {item['path']}")
    if args.json_path:
        Path(args.json_path).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
