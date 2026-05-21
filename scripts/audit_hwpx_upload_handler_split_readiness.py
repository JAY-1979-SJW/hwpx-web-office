#!/usr/bin/env python3
"""Read-only P9B audit for HwpxUploadHandler view split and gate connection readiness."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HANDLER = Path("src/main/java/com/haehan/engine/http/HwpxUploadHandler.java")
VIEW = Path("src/main/java/com/haehan/engine/http/HwpxUploadPageView.java")
GATE_POLICY = Path("src/main/java/com/haehan/engine/http/HwpxUploadPageGatePolicy.java")
STYLES = Path("src/main/java/com/haehan/engine/http/HwpxUploadPageStyles.java")
SCRIPTS = Path("src/main/java/com/haehan/engine/http/HwpxUploadPageScripts.java")
USECASE = Path("src/main/java/com/haehan/engine/usecase/HwpxUploadParseUseCase.java")
USECASE_RESULT = Path("src/main/java/com/haehan/engine/usecase/HwpxUploadParseResult.java")
SERVER = Path("src/main/java/com/haehan/engine/http/EngineHttpServer.java")
GATES = {
    "FileTypeGate": Path("src/main/java/com/haehan/engine/gate/FileTypeGate.java"),
    "UploadSecurityGate": Path("src/main/java/com/haehan/engine/gate/UploadSecurityGate.java"),
    "ExecutionLocationGate": Path("src/main/java/com/haehan/engine/gate/ExecutionLocationGate.java"),
    "OutputArtifactGate": Path("src/main/java/com/haehan/engine/gate/OutputArtifactGate.java"),
}

PATTERNS = {
    "file_input": re.compile(r"<input[^>]+type=\"file\"", re.IGNORECASE),
    "hwpx_accept": re.compile(r"accept=\"[^\"]*\\.hwpx", re.IGNORECASE),
    "hwp_accept": re.compile(r"accept=\"[^\"]*\\.hwp", re.IGNORECASE),
    "parse_api": re.compile(r"/api/hwpx/parse"),
    "editor_api": re.compile(r"/api/hwpx/editor"),
    "convert_api": re.compile(r"/convert-hwp-to-hwpx"),
    "download": re.compile(r"\bdownload(?:Blob|RawBlob|DraftJson|LiveReport|InspectionReport|DryRunReport)?\b|a\.download"),
    "object_url": re.compile(r"URL\.createObjectURL"),
    "filename_header": re.compile(r"X-Filename"),
    "conversion_gate": re.compile(r"X-Conversion-Gate"),
    "sanitize": re.compile(r"sanitize|asciiSafeFileName|replace\(\ /\[\^|replace\(/"),
    "raw_path": re.compile(r"(?i)(savedPath|localPath|outputFilePath|getAbsolutePath|X-Hwpx-Editor-Saved-Path)"),
    "file_type_gate_ref": re.compile(r"FileTypeGate"),
    "upload_security_gate_ref": re.compile(r"UploadSecurityGate"),
    "execution_location_gate_ref": re.compile(r"ExecutionLocationGate"),
    "output_artifact_gate_ref": re.compile(r"OutputArtifactGate"),
}

RISK_PATTERNS = {
    "direct_process_execution": re.compile(r"\b(ProcessBuilder|Runtime\.getRuntime\(\)\.exec|\.exec\()"),
    "external_browser_execution": re.compile(r"\b(Desktop\.getDesktop\(\)\.browse|Playwright|Selenium|ChromeDriver|GeckoDriver)\b", re.IGNORECASE),
    "db_write": re.compile(r"\b(DriverManager|getConnection|executeUpdate|INSERT\s+INTO|UPDATE\s+\w+|DELETE\s+FROM|DROP\s+TABLE|TRUNCATE)\b", re.IGNORECASE),
    "secret_literal": re.compile(
        r"(?i)(sk-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9_]{20,}|xox[baprs]-[A-Za-z0-9-]{20,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{20,})"
    ),
    "api_error_key": re.compile(r'"\{\\"error\\"|\{"error"'),
    "handler_endpoint_comment": re.compile(r"GET\s+/(hwpx-editor|hwpx-upload)"),
}


@dataclass
class Finding:
    severity: str
    rule: str
    detail: str


def run_git(args: list[str]) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True, stderr=subprocess.DEVNULL)


def read_handler() -> str:
    return (ROOT / HANDLER).read_text(encoding="utf-8", errors="replace")


def read_view() -> str:
    p = ROOT / VIEW
    return p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""


def read_helpers() -> str:
    parts = []
    for helper_path in (GATE_POLICY, STYLES, SCRIPTS):
        p = ROOT / helper_path
        if p.exists():
            parts.append(p.read_text(encoding="utf-8", errors="replace"))
    return "".join(parts)


def read_head_handler() -> str:
    try:
        return subprocess.check_output(
            ["git", "show", f"HEAD:{HANDLER.as_posix()}"],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        return ""


def git_status() -> str:
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


def line_numbers(text: str, pattern: re.Pattern[str], limit: int = 30) -> list[int]:
    lines: list[int] = []
    for index, line in enumerate(text.splitlines(), start=1):
        if pattern.search(line):
            lines.append(index)
            if len(lines) >= limit:
                break
    return lines


def count_pattern(text: str, pattern: re.Pattern[str]) -> int:
    return sum(1 for line in text.splitlines() if pattern.search(line))


def _p9c_usecase_section() -> dict:
    usecase_exists = (ROOT / USECASE).exists()
    result_exists = (ROOT / USECASE_RESULT).exists()
    usecase_text = (ROOT / USECASE).read_text(encoding="utf-8", errors="replace") if usecase_exists else ""
    result_text = (ROOT / USECASE_RESULT).read_text(encoding="utf-8", errors="replace") if result_exists else ""
    combined = usecase_text + result_text
    no_http_import = "com.haehan.engine.http" not in combined
    no_view_import = "HwpxUpload" not in combined.replace("HwpxUploadParseUseCase", "").replace("HwpxUploadParseResult", "")
    handler_wired = "HwpxUploadParseUseCase" in (
        (ROOT / Path("src/main/java/com/haehan/engine/http/ParseHwpxHandler.java")).read_text(encoding="utf-8", errors="replace")
        if (ROOT / Path("src/main/java/com/haehan/engine/http/ParseHwpxHandler.java")).exists() else ""
    )
    return {
        "usecase_exists": usecase_exists,
        "result_exists": result_exists,
        "usecase_path": USECASE.as_posix(),
        "result_path": USECASE_RESULT.as_posix(),
        "no_http_import": no_http_import,
        "no_view_import": no_view_import,
        "handler_wired_p9d_deferred": not handler_wired,
        "uses_file_type_gate": "FileTypeGate" in usecase_text,
        "uses_upload_security_gate": "UploadSecurityGate" in usecase_text,
    }


def audit() -> dict:
    text = read_handler()
    view_text = read_view()
    helper_text = read_helpers()
    # After P9B split, gate refs live in GatePolicy helper; use combined text for gate/pattern checks
    combined_text = text + view_text + helper_text
    head_text = read_head_handler()
    server_text = (ROOT / SERVER).read_text(encoding="utf-8", errors="replace") if (ROOT / SERVER).exists() else ""
    findings: list[Finding] = []
    status = git_status()
    lines = text.count("\n") + (1 if text else 0)
    view_lines = view_text.count("\n") + (1 if view_text else 0)
    numstat = diff_numstat()
    gate_presence = {name: (ROOT / path).exists() for name, path in GATES.items()}
    pattern_counts = {name: count_pattern(combined_text, pattern) for name, pattern in PATTERNS.items()}
    pattern_lines = {name: line_numbers(combined_text, pattern) for name, pattern in PATTERNS.items()}
    risk_counts = {name: count_pattern(combined_text, pattern) for name, pattern in RISK_PATTERNS.items()}
    risk_lines = {name: line_numbers(combined_text, pattern) for name, pattern in RISK_PATTERNS.items()}
    head_endpoints = sorted(set(RISK_PATTERNS["handler_endpoint_comment"].findall(head_text)))
    worktree_endpoints = sorted(set(RISK_PATTERNS["handler_endpoint_comment"].findall(combined_text)))
    allowed_aliases = {"hwpx-editor", "hwpx-upload"}
    server_registry_aliases = sorted(
        alias for alias in allowed_aliases if f'createContext("/{alias}"' in server_text
    )
    handler_endpoint_contract_unchanged = (
        set(worktree_endpoints).issubset(allowed_aliases)
        and "hwpx-upload" in worktree_endpoints
        and set(server_registry_aliases) == allowed_aliases
    )
    api_error_key_preserved = bool(RISK_PATTERNS["api_error_key"].search(head_text)) and bool(RISK_PATTERNS["api_error_key"].search(combined_text))

    view_exists = (ROOT / VIEW).exists()
    if status != "clean":
        findings.append(Finding("WARN", "tracked_dirty_large_handler", "HwpxUploadHandler has pre-existing tracked dirty content"))
    if not view_exists and lines >= 500:
        findings.append(Finding("WARN", "large_handler", f"HwpxUploadHandler has {lines} lines and remains split candidate"))
    elif view_exists and lines >= 200:
        findings.append(Finding("WARN", "handler_still_large_after_split", f"HwpxUploadHandler has {lines} lines even after view split"))
    if not view_exists and ((numstat["insertions"] or 0) > 500 or (numstat["deletions"] or 0) > 100):
        findings.append(Finding("WARN", "dirty_hunk_too_large_for_direct_commit", "Large hunk with no view split; P8D must not commit handler body"))
    if (pattern_counts["hwp_accept"] > 0 or pattern_counts["convert_api"] > 0) and pattern_counts["execution_location_gate_ref"] == 0:
        findings.append(Finding("WARN", "hwp_conversion_ui_flow", "HWP upload/conversion UI flow should route through FileTypeGate and ExecutionLocationGate"))
    if pattern_counts["file_type_gate_ref"] == 0:
        findings.append(Finding("WARN", "file_type_gate_not_connected", "FileTypeGate is not directly referenced"))
    if pattern_counts["upload_security_gate_ref"] == 0:
        findings.append(Finding("WARN", "upload_security_gate_not_connected", "UploadSecurityGate is not directly referenced"))
    if pattern_counts["execution_location_gate_ref"] == 0:
        findings.append(Finding("WARN", "execution_location_gate_not_connected", "ExecutionLocationGate is not directly referenced"))
    if pattern_counts["output_artifact_gate_ref"] == 0:
        findings.append(Finding("WARN", "output_artifact_gate_not_connected", "OutputArtifactGate is not directly referenced"))
    raw_path_guarded = "outputArtifactRawPathGuard" in combined_text
    if pattern_counts["raw_path"] > 0 and not raw_path_guarded:
        findings.append(Finding("WARN", "raw_path_candidate_unguarded", "raw path or saved path response candidate exists without OutputArtifactGate guard"))
    elif pattern_counts["raw_path"] > 0 and raw_path_guarded:
        findings.append(Finding("WARN", "raw_path_candidate_guarded", "raw path candidate exists but is guarded by outputArtifactRawPathGuard"))
    if not handler_endpoint_contract_unchanged:
        findings.append(Finding("FAIL", "handler_endpoint_contract_changed", "Handler endpoint comment contract changed or is unclear"))
    if not api_error_key_preserved:
        findings.append(Finding("FAIL", "api_error_key_not_preserved", "Existing method-not-allowed error key is not clearly preserved"))
    if risk_counts["direct_process_execution"] > 0:
        findings.append(Finding("FAIL", "direct_process_execution_candidate", "Server-side process execution candidate exists in handler"))
    if risk_counts["external_browser_execution"] > 0:
        findings.append(Finding("FAIL", "external_browser_execution_candidate", "External browser automation candidate exists in handler"))
    if risk_counts["db_write"] > 0:
        findings.append(Finding("FAIL", "db_write_candidate", "DB write or DB connection candidate exists in handler"))
    if risk_counts["secret_literal"] > 0:
        findings.append(Finding("FAIL", "known_secret_literal_candidate", "Known secret prefix literal candidate exists in handler"))

    split_plan = {
        "baseline_body_commit": False,
        "reason": "tracked dirty is too large; P8D is audit-only for handler body",
        "recommended_next_hunks": [
            {
                "name": "file_type_upload_gate",
                "candidate_lines": sorted(set(pattern_lines["file_input"] + pattern_lines["hwpx_accept"] + pattern_lines["hwp_accept"]))[:20],
                "gates": ["FileTypeGate", "UploadSecurityGate"],
            },
            {
                "name": "hwp_conversion_execution_gate",
                "candidate_lines": sorted(set(pattern_lines["convert_api"] + pattern_lines["conversion_gate"]))[:20],
                "gates": ["ExecutionLocationGate"],
            },
            {
                "name": "download_output_artifact_gate",
                "candidate_lines": sorted(set(pattern_lines["download"] + pattern_lines["object_url"]))[:20],
                "gates": ["OutputArtifactGate"],
            },
        ],
    }

    severities = {finding.severity for finding in findings}
    result_status = "FAIL" if "FAIL" in severities else ("WARN" if "WARN" in severities else "PASS")
    baseline_decision = "BASELINE_UNSAFE" if result_status == "FAIL" else ("BASELINE_WARN" if result_status == "WARN" else "BASELINE_SAFE")
    baseline_commit_allowed = baseline_decision in {"BASELINE_SAFE", "BASELINE_WARN"}
    return {
        "audit": "hwpx_upload_handler_split_readiness",
        "phase": "P9C",
        "status": result_status,
        "handler": {
            "path": HANDLER.as_posix(),
            "git_status": status,
            "lines": lines,
            "diff_numstat": numstat,
            "commit_body_in_p8d": False,
            "commit_body_allowed_in_p8f": baseline_commit_allowed,
        },
        "p9a_split": {
            "view_file_exists": view_exists,
            "view_path": VIEW.as_posix(),
            "view_lines": view_lines,
            "handler_lines_after_split": lines,
            "handler_slim": lines < 100,
            "view_has_gate_refs": all(
                gate in (view_text + helper_text)
                for gate in ["FileTypeGate", "UploadSecurityGate", "ExecutionLocationGate", "OutputArtifactGate"]
            ),
        },
        "p9b_split": {
            "gate_policy_exists": (ROOT / GATE_POLICY).exists(),
            "styles_exists": (ROOT / STYLES).exists(),
            "scripts_exists": (ROOT / SCRIPTS).exists(),
            "gate_policy_path": GATE_POLICY.as_posix(),
            "styles_path": STYLES.as_posix(),
            "scripts_path": SCRIPTS.as_posix(),
            "gate_policy_lines": helper_text.count("\n") + (1 if helper_text else 0),
            "view_slim": view_lines < 50,
            "gate_policy_has_all_gate_refs": all(
                gate in helper_text
                for gate in ["FileTypeGate", "UploadSecurityGate", "ExecutionLocationGate", "OutputArtifactGate"]
            ),
        },
        "p9c_usecase": _p9c_usecase_section(),
        "baseline": {
            "decision": baseline_decision,
            "commit_allowed": baseline_commit_allowed,
            "reason": (
                "No FAIL-level secret, direct execution, DB write, endpoint contract, or API key risk was detected"
                if baseline_commit_allowed
                else "FAIL-level baseline risk was detected"
            ),
            "remaining_warn_rules": [finding.rule for finding in findings if finding.severity == "WARN"],
        },
        "p8g_gate_connection": {
            "file_type_gate_connected": pattern_counts["file_type_gate_ref"] > 0,
            "upload_security_gate_connected": pattern_counts["upload_security_gate_ref"] > 0,
            "hwpx_allowed_candidate": pattern_counts["file_type_gate_ref"] > 0 and pattern_counts["parse_api"] > 0,
            "hwp_local_worker_required_candidate": pattern_counts["file_type_gate_ref"] > 0 and pattern_counts["convert_api"] > 0,
            "path_traversal_block_candidate": pattern_counts["upload_security_gate_ref"] > 0,
        },
        "p8h_gate_connection": {
            "execution_location_gate_connected": pattern_counts["execution_location_gate_ref"] > 0,
            "local_worker_required_present": "LOCAL_WORKER_REQUIRED" in combined_text,
            "hwp_conversion_flow_has_gate": pattern_counts["execution_location_gate_ref"] > 0 and pattern_counts["convert_api"] > 0,
            "no_direct_server_execution": risk_counts["direct_process_execution"] == 0,
            "no_external_browser": risk_counts["external_browser_execution"] == 0,
        },
        "p8i_gate_connection": {
            "output_artifact_gate_connected": pattern_counts["output_artifact_gate_ref"] > 0,
            "raw_path_guard_present": raw_path_guarded,
            "download_artifact_gate_policy": pattern_counts["output_artifact_gate_ref"] > 0 and pattern_counts["download"] > 0,
            "sanitize_download_name_present": "outputArtifactSanitizeName" in combined_text,
            "raw_path_candidates_exist": pattern_counts["raw_path"] > 0,
        },
        "contract_checks": {
            "handler_endpoint_contract_unchanged": handler_endpoint_contract_unchanged,
            "head_endpoint_aliases": head_endpoints,
            "worktree_endpoint_aliases": worktree_endpoints,
            "server_registry_aliases": server_registry_aliases,
            "api_error_key_preserved": api_error_key_preserved,
        },
        "gate_presence": gate_presence,
        "pattern_counts": pattern_counts,
        "pattern_lines": pattern_lines,
        "risk_counts": risk_counts,
        "risk_lines": risk_lines,
        "split_plan": split_plan,
        "finding_count": len(findings),
        "findings": [asdict(item) for item in findings],
        "policy": {
            "no_handler_body_commit": True,
            "p8f_handler_body_commit_allowed_after_tests": baseline_commit_allowed,
            "no_endpoint_path_change": True,
            "no_api_response_key_change": True,
            "no_hwp_hancom_execution_added": True,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", dest="json_path")
    args = parser.parse_args()
    result = audit()
    print(f"hwpx_upload_handler_split_readiness_status={result['status']}")
    print(f"baseline_decision={result['baseline']['decision']}")
    print(f"baseline_commit_allowed={result['baseline']['commit_allowed']}")
    print(f"handler_status={result['handler']['git_status']}")
    print(f"handler_lines={result['handler']['lines']}")
    print(f"finding_count={result['finding_count']}")
    for item in result["findings"][:20]:
        print(f"{item['severity']} {item['rule']}")
    if args.json_path:
        Path(args.json_path).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
