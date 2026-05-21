#!/usr/bin/env python3
"""Read-only upload/file gate audit."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import dataclass, asdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXCLUDE_PARTS = {".git", ".gradle", "build", "deliverables", "reports", "logs", "__pycache__", "node_modules"}
TEXT_SUFFIXES = {".java", ".py", ".js", ".ts"}
UPLOAD_RE = re.compile(r"(?i)(upload|multipart|fileupload|download|parse|convert)")
EXT_RE = re.compile(r"(?i)(\.hwpx|\.xlsx|\.xlsm|\.csv|\.hwp)")
SIZE_RE = re.compile(r"(?i)(max.*size|size.*limit|content-length|DRAFT_FILE_LIMIT|MAX_.*BYTES|fileSize)")
PATH_GUARD_RE = re.compile(r"(?i)(normalize|canonical|resolve|path traversal|\\.\\.|sanitize|safe)")
ZIP_RE = re.compile(r"(?i)(ZipInputStream|ZipFile|zipfile|PK\\x03\\x04|mimetype)")
LOCAL_WORKER_RE = re.compile(r"(?i)(LOCAL_WORKER_REQUIRED|local worker|hancom|hwp-worker|execution location|gate|guard)")


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


def is_upload_surface(path: Path, text: str) -> bool:
    s = path.as_posix().lower()
    if s.startswith("src/main/java"):
        return "/http/" in s or s.endswith("handler.java") or "upload" in s or "convert" in s
    if s.startswith("scripts/"):
        return "upload" in s or "convert" in s or "hwp_to" in s or "download" in s
    return bool(UPLOAD_RE.search(text))


def audit() -> dict:
    findings: list[Finding] = []
    files = repo_files()
    upload_files = 0
    for path in files:
        text = read(path)
        if not is_upload_surface(path, text):
            continue
        upload_files += 1
        has_ext = bool(EXT_RE.search(text))
        has_size = bool(SIZE_RE.search(text))
        has_path_guard = bool(PATH_GUARD_RE.search(text))
        mentions_hwp = ".hwp" in text.lower()
        mentions_hwpx = ".hwpx" in text.lower()

        if not has_ext and path.as_posix().startswith("src/main/java"):
            findings.append(Finding("WARN", "missing_extension_allowlist_signal", path.as_posix(), "upload-like Java surface lacks visible extension allowlist"))
        if not has_size and path.as_posix().startswith("src/main/java") and "upload" in text.lower():
            findings.append(Finding("WARN", "missing_file_size_signal", path.as_posix(), "upload-like Java surface lacks visible size limit"))
        if not has_path_guard and path.as_posix().startswith("src/main/java") and "upload" in text.lower():
            findings.append(Finding("WARN", "missing_path_traversal_signal", path.as_posix(), "upload-like Java surface lacks visible path guard"))
        is_http = "/http/" in path.as_posix().lower()
        if mentions_hwp and not mentions_hwpx and is_http and not LOCAL_WORKER_RE.search(text):
            findings.append(Finding("FAIL", "hwp_server_direct_processing_without_gate", path.as_posix(), ".hwp appears in server upload surface without local worker gate marker"))
        elif mentions_hwp and is_http and not LOCAL_WORKER_RE.search(text):
            findings.append(Finding("WARN", "hwp_server_surface_requires_gate_review", path.as_posix(), ".hwp appears in server surface; local worker gate must be explicit"))
        if mentions_hwpx and not ZIP_RE.search(text) and "parse" in text.lower() and path.as_posix().startswith("src/main/java"):
            findings.append(Finding("WARN", "hwpx_parse_without_zip_signal", path.as_posix(), "HWPX parse surface lacks visible ZIP/package validation signal"))

    severities = {f.severity for f in findings}
    status = "FAIL" if "FAIL" in severities else ("WARN" if "WARN" in severities else "PASS")
    return {
        "audit": "upload_file_gates",
        "status": status,
        "files_scanned": len(files),
        "upload_surface_count": upload_files,
        "finding_count": len(findings),
        "findings": [asdict(f) for f in findings[:200]],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", dest="json_path")
    args = parser.parse_args()
    result = audit()
    print(f"upload_file_gate_status={result['status']}")
    print(f"files_scanned={result['files_scanned']}")
    print(f"upload_surface_count={result['upload_surface_count']}")
    print(f"finding_count={result['finding_count']}")
    for item in result["findings"][:20]:
        print(f"{item['severity']} {item['rule']} {item['path']}")
    if args.json_path:
        Path(args.json_path).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
