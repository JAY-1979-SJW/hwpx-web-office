#!/usr/bin/env python3
"""Read-only P10/P11 audit: API meta contract consistency across handlers."""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTTP_DIR = Path("src/main/java/com/haehan/engine/http")
CONTRACT_DIR = Path("src/main/java/com/haehan/engine/contract")
USECASE_DIR = Path("src/main/java/com/haehan/engine/usecase")

HANDLER_FILES = [
    "HwpxEditorApiHandler.java",
    "ParseHwpxHandler.java",
    "HwpxUploadHandler.java",
    "ConvertHwpToHwpxHandler.java",
    "HealthHandler.java",
    "InspectionGenerateHandler.java",
]

# P11: JSON API endpoints that must have additive schemaVersion/engineVersion/requestId
P11_JSON_HANDLERS = [
    "ParseHwpxHandler.java",
    "ParseWorkbookHandler.java",
    "ParseWorkbookRawHandler.java",
    "ParseWorkbookSemanticHandler.java",
    "AnalyzeWorkbookStructureHandler.java",
    "ParseWorkbookAggregateHandler.java",
]

RAW_PATH_PATTERNS = [
    "archive.reportPath().toString()",
    "archive.outputPath().toString()",
    ".toAbsolutePath().toString()",
    "System.getProperty(\"user.home\")",
]

META_FIELDS = ["schemaVersion", "engineVersion", "requestId"]
ARTIFACT_HEADERS = ["X-Hwpx-Editor-Artifact-Id", "X-Request-Id", "X-Engine-Version"]
GUARD_HEADERS = ["X-Hwpx-Editor-Saved-Path", "X-Hwpx-Editor-Saved-Report-Path"]
ERROR_KEYS = ['"error"', '"message"']


@dataclass
class Finding:
    severity: str
    rule: str
    file: str
    detail: str


def read(path: Path) -> str:
    p = ROOT / path
    return p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""


def audit_handler(name: str, text: str) -> list[Finding]:
    findings: list[Finding] = []
    if not text:
        findings.append(Finding("WARN", "handler_not_found", name, f"{name} not found"))
        return findings

    # raw path direct exposure check: only flag if directly in set() call, not in guarded ternary
    handler_is_guarded = "isRawPathGuarded()" in text or "guardedReportRef" in text
    for pattern in RAW_PATH_PATTERNS:
        if pattern in text:
            lines = text.split("\n")
            for i, line in enumerate(lines):
                if pattern not in line:
                    continue
                # Check if this line is the direct argument to set()
                combined = " ".join(lines[max(0, i-1):i+2])
                if 'set("X-' in combined or "set('X-" in combined:
                    # False positive if surrounded by ternary guard
                    if "isRawPathGuarded()" in combined or "guardedReportRef" in combined or handler_is_guarded:
                        continue
                    findings.append(Finding(
                        "WARN", "raw_path_in_response_header", name,
                        f"Possible raw path in response header near: {line.strip()[:80]}"
                    ))
                    break

    # guard header check: if handler sets guard headers, check if guarded
    for gh in GUARD_HEADERS:
        if f'"{gh}"' in text or f"'{gh}'" in text:
            if "isRawPathGuarded()" not in text and "guardedReportRef" not in text and "guardedArtifactRef" not in text:
                findings.append(Finding(
                    "WARN", "guard_header_without_guard_logic", name,
                    f"Handler sets {gh} but no guard logic found"
                ))

    return findings


def audit() -> dict:
    findings: list[Finding] = []

    # Check ApiResponseMeta helper exists
    meta_helper = ROOT / CONTRACT_DIR / "ApiResponseMeta.java"
    meta_helper_exists = meta_helper.exists()
    meta_helper_text = meta_helper.read_text(encoding="utf-8") if meta_helper_exists else ""
    meta_has_schema_version = "SCHEMA_VERSION" in meta_helper_text
    meta_has_engine_version = "ENGINE_VERSION" in meta_helper_text
    meta_has_request_id = "newRequestId" in meta_helper_text
    meta_has_guarded_report = "guardedReportRef" in meta_helper_text

    if not meta_helper_exists:
        findings.append(Finding("FAIL", "api_response_meta_missing", "ApiResponseMeta.java", "ApiResponseMeta helper not found"))

    # Per-handler audit
    handler_results: dict = {}
    for hname in HANDLER_FILES:
        text = read(HTTP_DIR / hname)
        hfinds = audit_handler(hname, text)
        findings.extend(hfinds)
        handler_results[hname] = {
            "found": bool(text),
            "has_schema_version": any(f in text for f in META_FIELDS[:1]),
            "has_engine_version": any(f in text for f in META_FIELDS[1:2]),
            "has_request_id": "requestId" in text or "X-Request-Id" in text,
            "has_artifact_id_header": any(h in text for h in ARTIFACT_HEADERS),
            "sets_guard_headers": any(gh in text for gh in GUARD_HEADERS),
            "uses_guard_logic": "isRawPathGuarded()" in text or "guardedReportRef" in text,
            "raw_path_findings": len([f for f in hfinds if "raw_path" in f.rule]),
        }

    # HwpxEditorApiHandler specific checks
    editor_text = read(HTTP_DIR / "HwpxEditorApiHandler.java")
    editor_report_path_guarded = "guardedReportRef" in editor_text
    editor_saved_path_guarded = "isRawPathGuarded()" in editor_text
    editor_artifact_id_present = "X-Hwpx-Editor-Artifact-Id" in editor_text
    editor_uses_api_meta = "ApiResponseMeta" in editor_text

    if not editor_report_path_guarded:
        findings.append(Finding("FAIL", "editor_report_path_not_guarded", "HwpxEditorApiHandler.java",
                                "X-Hwpx-Editor-Saved-Report-Path is not guarded via guardedReportRef"))
    if not editor_saved_path_guarded:
        findings.append(Finding("FAIL", "editor_saved_path_not_guarded", "HwpxEditorApiHandler.java",
                                "X-Hwpx-Editor-Saved-Path is not guarded via isRawPathGuarded()"))
    if not editor_artifact_id_present:
        findings.append(Finding("FAIL", "editor_artifact_id_missing", "HwpxEditorApiHandler.java",
                                "X-Hwpx-Editor-Artifact-Id header not found"))

    # P11: JSON API meta additive apply check
    p11_handler_results: dict = {}
    for hname in P11_JSON_HANDLERS:
        text = read(HTTP_DIR / hname)
        has_schema = "schemaVersion" in text or (hname == "ParseHwpxHandler.java" and "DocumentParseResponse" in text)
        has_engine = "engineVersion" in text or (hname == "ParseHwpxHandler.java" and "DocumentParseResponse" in text)
        has_request = "requestId" in text or "X-Request-Id" in text
        p11_handler_results[hname] = {
            "found": bool(text),
            "has_schema_version": has_schema,
            "has_engine_version": has_engine,
            "has_request_id": has_request,
        }
        if not text:
            findings.append(Finding("WARN", "p11_handler_not_found", hname, f"{hname} not found"))
        elif not (has_schema and has_engine and has_request):
            missing = [f for f, v in [("schemaVersion", has_schema), ("engineVersion", has_engine), ("requestId", has_request)] if not v]
            findings.append(Finding("WARN", "p11_meta_incomplete", hname, f"Missing meta fields: {missing}"))

    # Policy document check
    policy_md = ROOT / "docs" / "architecture" / "api_meta_contract_policy_20260515.md"
    policy_json = ROOT / "docs" / "architecture" / "api_meta_contract_policy_20260515.json"
    policy_md_exists = policy_md.exists()
    policy_json_exists = policy_json.exists()

    if not policy_md_exists:
        findings.append(Finding("WARN", "policy_doc_missing", "api_meta_contract_policy_20260515.md", "Policy markdown not found"))
    if not policy_json_exists:
        findings.append(Finding("WARN", "policy_json_missing", "api_meta_contract_policy_20260515.json", "Policy JSON not found"))

    severities = {f.severity for f in findings}
    status = "FAIL" if "FAIL" in severities else ("WARN" if "WARN" in severities else "PASS")

    return {
        "audit": "api_meta_contract",
        "phase": "P11",
        "status": status,
        "api_response_meta_helper": {
            "exists": meta_helper_exists,
            "has_schema_version": meta_has_schema_version,
            "has_engine_version": meta_has_engine_version,
            "has_request_id_factory": meta_has_request_id,
            "has_guarded_report_ref": meta_has_guarded_report,
        },
        "editor_api_guard_status": {
            "saved_path_guarded": editor_saved_path_guarded,
            "report_path_guarded": editor_report_path_guarded,
            "artifact_id_present": editor_artifact_id_present,
            "uses_api_response_meta": editor_uses_api_meta,
        },
        "handler_meta_status": handler_results,
        "p11_json_api_meta_status": p11_handler_results,
        "policy_docs": {
            "markdown": policy_md_exists,
            "json": policy_json_exists,
        },
        "finding_count": len(findings),
        "findings": [asdict(f) for f in findings],
        "policy": {
            "no_endpoint_path_change": True,
            "no_api_response_key_change": True,
            "additive_meta_only": True,
            "raw_path_headers_forbidden": True,
            "push_forbidden": True,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", dest="json_path")
    args = parser.parse_args()
    result = audit()
    print(f"api_meta_contract_status={result['status']}")
    print(f"finding_count={result['finding_count']}")
    for item in result["findings"][:20]:
        print(f"  {item['severity']} [{item['file']}] {item['rule']}: {item['detail'][:80]}")
    if args.json_path:
        Path(args.json_path).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
