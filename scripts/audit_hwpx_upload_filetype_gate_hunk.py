#!/usr/bin/env python3
"""Read-only P8E audit for HwpxUploadHandler file type/upload gate hunk readiness."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HANDLER = Path("src/main/java/com/haehan/engine/http/HwpxUploadHandler.java")


@dataclass
class Finding:
    severity: str
    rule: str
    detail: str


def run_git(args: list[str]) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True, stderr=subprocess.DEVNULL)


def read_worktree() -> str:
    return (ROOT / HANDLER).read_text(encoding="utf-8", errors="replace")


def read_head() -> str:
    return run_git(["show", f"HEAD:{HANDLER.as_posix()}"])


def status() -> str:
    out = run_git(["status", "--short", "--", HANDLER.as_posix()]).strip()
    return out[:2] if out else "clean"


def diff_numstat() -> dict[str, int | None]:
    out = run_git(["diff", "--numstat", "--", HANDLER.as_posix()]).strip()
    if not out:
        return {"insertions": 0, "deletions": 0}
    parts = out.split()
    try:
        return {"insertions": int(parts[0]), "deletions": int(parts[1])}
    except (IndexError, ValueError):
        return {"insertions": None, "deletions": None}


def has(pattern: str, text: str) -> bool:
    return re.search(pattern, text, re.IGNORECASE) is not None


def count(pattern: str, text: str) -> int:
    regex = re.compile(pattern, re.IGNORECASE)
    return sum(1 for line in text.splitlines() if regex.search(line))


def audit() -> dict:
    worktree = read_worktree()
    head = read_head()
    findings: list[Finding] = []
    numstat = diff_numstat()
    handler_status = status()
    worktree_lines = worktree.count("\n") + (1 if worktree else 0)
    head_lines = head.count("\n") + (1 if head else 0)

    worktree_signals = {
        "accept_hwpx": has(r"accept=\"[^\"]*\.hwpx", worktree),
        "accept_hwp": has(r"accept=\"[^\"]*\.hwp", worktree),
        "convert_api": has(r"/convert-hwp-to-hwpx", worktree),
        "ascii_safe_filename": has(r"asciiSafeFileName", worktree),
        "file_type_gate_ref": has(r"FileTypeGate", worktree),
        "upload_security_gate_ref": has(r"UploadSecurityGate", worktree),
        "unknown_extension_block": has(r"UNKNOWN_EXTENSION_BLOCKED|unknown extension", worktree),
        "path_traversal_block": has(r"PATH_TRAVERSAL_BLOCKED|path traversal|\.\.", worktree),
    }
    head_signals = {
        "accept_hwpx": has(r"accept=\"[^\"]*\.hwpx", head),
        "accept_hwp": has(r"accept=\"[^\"]*\.hwp", head),
        "convert_api": has(r"/convert-hwp-to-hwpx", head),
        "ascii_safe_filename": has(r"asciiSafeFileName", head),
        "file_type_gate_ref": has(r"FileTypeGate", head),
        "upload_security_gate_ref": has(r"UploadSecurityGate", head),
    }

    dirty_added_upload_flow = (
        worktree_signals["accept_hwp"]
        and worktree_signals["convert_api"]
        and worktree_signals["ascii_safe_filename"]
        and not head_signals["accept_hwp"]
        and not head_signals["convert_api"]
    )
    hunk_split_possible = False

    if handler_status != "clean":
        findings.append(Finding("WARN", "tracked_dirty_handler", "HwpxUploadHandler remains tracked dirty"))
    if dirty_added_upload_flow:
        findings.append(Finding("WARN", "upload_flow_only_in_dirty_body", "P8E upload flow candidates live in uncommitted large dirty body"))
    if (numstat["insertions"] or 0) > 500:
        findings.append(Finding("WARN", "dirty_body_too_large", "handler body diff is too large for safe direct staging"))
    if not worktree_signals["file_type_gate_ref"]:
        findings.append(Finding("WARN", "file_type_gate_not_connected", "FileTypeGate is not directly referenced in worktree handler"))
    if not worktree_signals["upload_security_gate_ref"]:
        findings.append(Finding("WARN", "upload_security_gate_not_connected", "UploadSecurityGate is not directly referenced in worktree handler"))
    if not hunk_split_possible:
        findings.append(Finding("WARN", "p8e_hunk_commit_deferred", "P8E handler hunk is not safely separable from existing dirty body"))

    severities = {finding.severity for finding in findings}
    result_status = "FAIL" if "FAIL" in severities else ("WARN" if "WARN" in severities else "PASS")
    return {
        "audit": "hwpx_upload_filetype_upload_gate_hunk",
        "phase": "P8E",
        "status": result_status,
        "handler": {
            "path": HANDLER.as_posix(),
            "git_status": handler_status,
            "head_lines": head_lines,
            "worktree_lines": worktree_lines,
            "diff_numstat": numstat,
            "handler_body_commit_allowed": False,
        },
        "signals": {
            "head": head_signals,
            "worktree": worktree_signals,
            "worktree_file_input_count": count(r"<input[^>]+type=\"file\"", worktree),
        },
        "hunk_split": {
            "possible": hunk_split_possible,
            "reason": "upload gate candidate flow is part of the large dirty handler body and cannot be staged as a P8E-only hunk safely",
            "commit_handler_body": False,
        },
        "gate_scope": {
            "FileTypeGate": "deferred",
            "UploadSecurityGate": "deferred",
            "ExecutionLocationGate": "excluded",
            "OutputArtifactGate": "excluded",
        },
        "finding_count": len(findings),
        "findings": [asdict(item) for item in findings],
        "policy": {
            "no_endpoint_path_change": True,
            "no_api_response_key_change": True,
            "no_hwp_hancom_execution_added": True,
            "no_handler_body_commit": True,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", dest="json_path")
    args = parser.parse_args()
    result = audit()
    print(f"hwpx_upload_filetype_gate_hunk_status={result['status']}")
    print(f"hunk_split_possible={str(result['hunk_split']['possible']).lower()}")
    print(f"handler_status={result['handler']['git_status']}")
    print(f"finding_count={result['finding_count']}")
    for item in result["findings"][:20]:
        print(f"{item['severity']} {item['rule']}")
    if args.json_path:
        Path(args.json_path).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
