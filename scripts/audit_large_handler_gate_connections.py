#!/usr/bin/env python3
"""Read-only audit for large handler gate skeleton connections."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXCLUDE_PARTS = {".git", ".gradle", "build", "deliverables", "reports", "logs", "__pycache__", "node_modules"}
TEXT_SUFFIXES = {".java", ".py", ".md", ".json", ".yml", ".yaml", ".kt", ".kts"}

GATE_FILES = [
    "src/main/java/com/haehan/engine/gate/GateResult.java",
    "src/main/java/com/haehan/engine/gate/FileTypeGate.java",
    "src/main/java/com/haehan/engine/gate/UploadSecurityGate.java",
    "src/main/java/com/haehan/engine/gate/ExecutionLocationGate.java",
    "src/main/java/com/haehan/engine/gate/OutputArtifactGate.java",
]

GATE_TEST_FILES = [
    "src/test/java/com/haehan/engine/gate/FileTypeGateTest.java",
    "src/test/java/com/haehan/engine/gate/UploadSecurityGateTest.java",
    "src/test/java/com/haehan/engine/gate/ExecutionLocationGateTest.java",
    "src/test/java/com/haehan/engine/gate/OutputArtifactGateTest.java",
]

LARGE_HANDLER_NAMES = [
    "HwpxUploadHandler.java",
    "InspectionPageHandler.java",
    "ConvertHwpToHwpxHandler.java",
]

PROCESS_RE = re.compile(r"(?i)(ProcessBuilder|Runtime\.getRuntime|subprocess\.|Start-Process)")
HWP_RE = re.compile(r"(?i)(\\.hwp|HwpToHwpx|Hancom|hwp-to-hwpx|convert-hwp)")
LOCAL_GATE_RE = re.compile(r"(?i)(ExecutionLocationGate|LOCAL_WORKER_REQUIRED|WORKER_TOKEN_REQUIRED|isWorkerTokenAccepted|X-Conversion-Gate|local worker)")
FILE_GATE_RE = re.compile(r"(?i)(FileTypeGate|UploadSecurityGate|safeOutputName|sanitize|filename\\.contains|\\.hwpx|\\.hwp)")
OUTPUT_GATE_RE = re.compile(r"(?i)(OutputArtifactGate|artifactId|Content-Disposition|download|X-Hwpx-Editor-Saved-Path|outputFilePath|getAbsolutePath)")
META_RE = re.compile(r"(?s)(schemaVersion).{0,500}(engineVersion).{0,500}(requestId)|requestId.{0,500}schemaVersion.{0,500}engineVersion")


@dataclass
class Finding:
    severity: str
    rule: str
    path: str
    detail: str


def repo_files() -> list[Path]:
    out = subprocess.check_output(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT)
    files: list[Path] = []
    for raw in out.split(b"\0"):
        if not raw:
            continue
        rel = Path(raw.decode("utf-8", errors="replace"))
        if any(part in EXCLUDE_PARTS for part in rel.parts):
            continue
        if rel.suffix.lower() in TEXT_SUFFIXES:
            files.append(rel)
    return files


def read(path: Path) -> str:
    try:
        return (ROOT / path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def line_count(path: Path) -> int:
    text = read(path)
    return text.count("\n") + (1 if text else 0)


def audit() -> dict:
    files = repo_files()
    findings: list[Finding] = []
    gate_presence = {path: (ROOT / path).exists() for path in GATE_FILES}
    gate_test_presence = {path: (ROOT / path).exists() for path in GATE_TEST_FILES}
    handler_status: list[dict] = []

    for path, exists in gate_presence.items():
        if not exists:
            findings.append(Finding("FAIL", "gate_skeleton_missing", path, "required P6 gate skeleton file is missing"))
    for path, exists in gate_test_presence.items():
        if not exists:
            findings.append(Finding("WARN", "gate_test_missing", path, "gate skeleton test is missing"))

    for path in files:
        s = path.as_posix()
        if not any(s.endswith(name) for name in LARGE_HANDLER_NAMES):
            continue
        text = read(path)
        lines = line_count(path)
        has_file_gate = bool(FILE_GATE_RE.search(text))
        has_execution_gate = bool(LOCAL_GATE_RE.search(text))
        has_output_gate = bool(OUTPUT_GATE_RE.search(text))
        has_meta = bool(META_RE.search(text))
        has_hwp_signal = bool(HWP_RE.search(text))
        has_process_signal = bool(PROCESS_RE.search(text))

        handler_status.append({
            "path": s,
            "lines": lines,
            "has_file_gate_signal": has_file_gate,
            "has_execution_gate_signal": has_execution_gate,
            "has_output_gate_signal": has_output_gate,
            "has_api_meta_signal": has_meta,
            "has_hwp_signal": has_hwp_signal,
            "has_process_signal": has_process_signal,
        })

        if lines >= 500:
            findings.append(Finding("WARN", "large_handler_candidate", s, f"handler has {lines} lines; split remains required"))
        if s.endswith("ConvertHwpToHwpxHandler.java") and not has_execution_gate:
            findings.append(Finding("WARN", "convert_handler_execution_gate_not_connected", s, "Convert handler should call ExecutionLocationGate in P7"))
        if s.endswith("HwpxUploadHandler.java") and not has_file_gate:
            findings.append(Finding("WARN", "hwpx_upload_file_gate_not_connected", s, "HWPX upload page/handler should call FileTypeGate and UploadSecurityGate in P7"))
        if has_hwp_signal and has_process_signal and not has_execution_gate:
            findings.append(Finding("FAIL", "hwp_process_without_execution_gate", s, "HWP/Hancom process execution lacks visible local worker gate"))
        if has_output_gate and not re.search(r"(?i)(OutputArtifactGate|artifactId)", text):
            findings.append(Finding("WARN", "raw_path_or_download_policy_candidate", s, "download/output path should move to OutputArtifactGate/artifact id policy"))
        if not has_meta:
            findings.append(Finding("WARN", "api_meta_contract_candidate", s, "handler lacks visible schemaVersion/engineVersion/requestId meta contract"))

    severities = {finding.severity for finding in findings}
    status = "FAIL" if "FAIL" in severities else ("WARN" if "WARN" in severities else "PASS")
    return {
        "audit": "large_handler_gate_connections",
        "status": status,
        "files_scanned": len(files),
        "gate_presence": gate_presence,
        "gate_test_presence": gate_test_presence,
        "handler_status": handler_status,
        "finding_count": len(findings),
        "findings": [asdict(item) for item in findings[:200]],
        "policy": {
            "p6_scope": "gate skeleton and minimal connection audit",
            "handler_dirty_guard": "do not commit pre-existing large handler dirty changes",
            "hwp_hancom": "LOCAL_WORKER_REQUIRED",
            "raw_path_response": "WARN until artifact id wrapper is connected",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", dest="json_path")
    args = parser.parse_args()
    result = audit()
    print(f"large_handler_gate_connection_status={result['status']}")
    print(f"files_scanned={result['files_scanned']}")
    print(f"handler_count={len(result['handler_status'])}")
    print(f"finding_count={result['finding_count']}")
    for item in result["findings"][:20]:
        print(f"{item['severity']} {item['rule']} {item['path']}")
    if args.json_path:
        Path(args.json_path).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
