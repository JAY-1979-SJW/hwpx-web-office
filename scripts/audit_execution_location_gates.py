#!/usr/bin/env python3
"""Read-only execution location gate audit."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import dataclass, asdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXCLUDE_PARTS = {".git", ".gradle", "build", "deliverables", "reports", "logs", "__pycache__", "node_modules"}
TEXT_SUFFIXES = {".java", ".py", ".ps1", ".sh", ".js", ".ts"}
LOCAL_EXECUTION = re.compile(r"(?i)(hancom|hwp|hwp\.exe|local-gui|desktop|pywinauto|win32com|autogui|uiautomation)")
DANGEROUS_ACTION = re.compile(r"(?i)(password|otp|certificate|sign|submit|payment|transfer|bid|login)")
BROWSER_AUTOMATION = re.compile(r"(?i)(playwright|selenium|chromedriver|browser|cdp)")
PROCESS_EXEC = re.compile(r"(?i)(ProcessBuilder|Runtime\.getRuntime|subprocess\.|Start-Process|os\.system)")
GATE_WORDS = re.compile(r"(?i)(LOCAL_WORKER_REQUIRED|USER_PRESENT_REQUIRED|execution location|local worker|user present|approval|guard|gate)")


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


def is_server_runtime(path: Path) -> bool:
    s = path.as_posix()
    return s.startswith("src/main/java") or s.startswith("src/main/resources")


def is_server_handler(path: Path) -> bool:
    s = path.as_posix()
    return s.startswith("src/main/java") and "/http/" in s


def audit() -> dict:
    findings: list[Finding] = []
    files = repo_files()
    for path in files:
        text = read(path)
        if is_server_handler(path) and LOCAL_EXECUTION.search(text):
            severity = "WARN"
            detail = "server handler references HWP/Hancom/local execution keywords"
            if PROCESS_EXEC.search(text) and not GATE_WORDS.search(text):
                severity = "FAIL"
                detail = "server handler can invoke process execution without visible location gate"
            findings.append(Finding(severity, "server_handler_local_execution_gate", path.as_posix(), detail))
        if is_server_runtime(path) and BROWSER_AUTOMATION.search(text):
            findings.append(Finding("WARN", "server_runtime_browser_automation_keyword", path.as_posix(), "browser automation keyword in server runtime"))
        if is_server_runtime(path) and DANGEROUS_ACTION.search(text) and not GATE_WORDS.search(text):
            findings.append(Finding("WARN", "server_runtime_user_present_keyword_without_gate", path.as_posix(), "user-present keyword without visible gate marker"))
        if path.as_posix().startswith("scripts/local-gui") and DANGEROUS_ACTION.search(text):
            findings.append(Finding("WARN", "local_gui_user_present_keyword", path.as_posix(), "local GUI contains user-present keyword; keep outside server runtime"))

    severities = {f.severity for f in findings}
    status = "FAIL" if "FAIL" in severities else ("WARN" if "WARN" in severities else "PASS")
    return {
        "audit": "execution_location_gates",
        "status": status,
        "files_scanned": len(files),
        "finding_count": len(findings),
        "findings": [asdict(f) for f in findings[:200]],
        "classes": {
            "SERVER_ALLOWED": ["HWPX XML/ZIP", "Excel/XLSX structure analysis", "JSON validation", "report generation"],
            "LOCAL_WORKER_REQUIRED": ["Hancom/HWP conversion", "GUI conversion", "desktop app control"],
            "USER_PRESENT_REQUIRED": ["password", "OTP", "certificate", "sign", "payment", "transfer", "bid", "external login"],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", dest="json_path")
    args = parser.parse_args()
    result = audit()
    print(f"execution_location_status={result['status']}")
    print(f"files_scanned={result['files_scanned']}")
    print(f"finding_count={result['finding_count']}")
    for item in result["findings"][:20]:
        print(f"{item['severity']} {item['rule']} {item['path']}")
    if args.json_path:
        Path(args.json_path).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
