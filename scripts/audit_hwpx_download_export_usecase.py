#!/usr/bin/env python3
"""Read-only P9E/P9F audit: HwpxDownloadExportUseCase boundary readiness and handler wiring."""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
USECASE = Path("src/main/java/com/haehan/engine/usecase/HwpxDownloadExportUseCase.java")
RESULT = Path("src/main/java/com/haehan/engine/usecase/HwpxDownloadExportResult.java")
OUTPUT_ARTIFACT_GATE = Path("src/main/java/com/haehan/engine/gate/OutputArtifactGate.java")
SCRIPTS = Path("src/main/java/com/haehan/engine/http/HwpxUploadPageScripts.java")
EDITOR_HANDLER = Path("src/main/java/com/haehan/engine/http/HwpxEditorApiHandler.java")


@dataclass
class Finding:
    severity: str
    rule: str
    detail: str


def read(path: Path) -> str:
    p = ROOT / path
    return p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""


def audit() -> dict:
    findings: list[Finding] = []

    usecase_exists = (ROOT / USECASE).exists()
    result_exists = (ROOT / RESULT).exists()
    gate_exists = (ROOT / OUTPUT_ARTIFACT_GATE).exists()
    usecase_text = read(USECASE)
    result_text = read(RESULT)
    scripts_text = read(SCRIPTS)
    editor_text = read(EDITOR_HANDLER)

    usecase_no_http_import = "com.haehan.engine.http" not in usecase_text
    usecase_uses_output_gate = "OutputArtifactGate" in usecase_text
    usecase_uses_sanitize = "sanitizeDownloadName" in usecase_text
    usecase_uses_artifact_id = "newArtifactId" in usecase_text

    # JS function names preserved in scripts
    download_blob_present = "function downloadBlob(" in scripts_text
    download_raw_blob_present = "function downloadRawBlob(" in scripts_text
    download_draft_json_present = "function downloadDraftJson(" in scripts_text
    output_artifact_sanitize_present = "function outputArtifactSanitizeName(" in scripts_text
    output_artifact_guard_present = "function outputArtifactRawPathGuard(" in scripts_text

    # Handler wiring status (P9F: wired)
    editor_handler_wired = "HwpxDownloadExportUseCase" in editor_text
    editor_uses_safe_filename = "exportResult.safeFilename()" in editor_text
    editor_uses_artifact_id_header = "X-Hwpx-Editor-Artifact-Id" in editor_text
    editor_raw_path_guarded = "isRawPathGuarded()" in editor_text
    editor_no_direct_sanitize_in_header = editor_handler_wired  # safeFilename() replaces toHwpxFileName(outputName) directly

    if not usecase_exists:
        findings.append(Finding("FAIL", "usecase_missing", "HwpxDownloadExportUseCase.java not found"))
    if not result_exists:
        findings.append(Finding("FAIL", "result_missing", "HwpxDownloadExportResult.java not found"))
    if not gate_exists:
        findings.append(Finding("FAIL", "output_artifact_gate_missing", "OutputArtifactGate.java not found"))
    if usecase_exists and not usecase_no_http_import:
        findings.append(Finding("FAIL", "usecase_imports_http", "HwpxDownloadExportUseCase imports from http package"))
    if usecase_exists and not usecase_uses_output_gate:
        findings.append(Finding("WARN", "usecase_no_output_gate", "HwpxDownloadExportUseCase does not reference OutputArtifactGate"))
    if not download_blob_present:
        findings.append(Finding("WARN", "download_blob_js_missing", "downloadBlob JS function not found in scripts"))
    if not download_raw_blob_present:
        findings.append(Finding("WARN", "download_raw_blob_js_missing", "downloadRawBlob JS function not found in scripts"))
    if not download_draft_json_present:
        findings.append(Finding("WARN", "download_draft_json_js_missing", "downloadDraftJson JS function not found in scripts"))
    if not output_artifact_sanitize_present:
        findings.append(Finding("WARN", "output_artifact_sanitize_js_missing", "outputArtifactSanitizeName JS function not found"))
    if not output_artifact_guard_present:
        findings.append(Finding("WARN", "output_artifact_guard_js_missing", "outputArtifactRawPathGuard JS function not found"))

    # P9F: handler must be wired
    if editor_handler_wired and not editor_uses_safe_filename:
        findings.append(Finding("WARN", "handler_not_using_safe_filename", "Handler wired but not using exportResult.safeFilename()"))
    if editor_handler_wired and not editor_uses_artifact_id_header:
        findings.append(Finding("WARN", "handler_missing_artifact_id_header", "Handler wired but X-Hwpx-Editor-Artifact-Id header not set"))
    if editor_handler_wired and not editor_raw_path_guarded:
        findings.append(Finding("WARN", "handler_no_raw_path_guard", "Handler wired but isRawPathGuarded() not used for archive header"))

    severities = {f.severity for f in findings}
    status = "FAIL" if "FAIL" in severities else ("WARN" if "WARN" in severities else "PASS")
    return {
        "audit": "hwpx_download_export_usecase",
        "phase": "P9F",
        "status": status,
        "usecase": {
            "exists": usecase_exists,
            "no_http_import": usecase_no_http_import,
            "uses_output_artifact_gate": usecase_uses_output_gate,
            "uses_sanitize_download_name": usecase_uses_sanitize,
            "uses_new_artifact_id": usecase_uses_artifact_id,
        },
        "result": {
            "exists": result_exists,
        },
        "js_functions_preserved": {
            "downloadBlob": download_blob_present,
            "downloadRawBlob": download_raw_blob_present,
            "downloadDraftJson": download_draft_json_present,
            "outputArtifactSanitizeName": output_artifact_sanitize_present,
            "outputArtifactRawPathGuard": output_artifact_guard_present,
        },
        "handler_wiring": {
            "editor_handler_wired": editor_handler_wired,
            "uses_safe_filename": editor_uses_safe_filename,
            "uses_artifact_id_header": editor_uses_artifact_id_header,
            "raw_path_guarded": editor_raw_path_guarded,
        },
        "gate_presence": {
            "OutputArtifactGate": gate_exists,
        },
        "finding_count": len(findings),
        "findings": [asdict(f) for f in findings],
        "policy": {
            "no_endpoint_path_change": True,
            "no_api_response_key_change": True,
            "no_gate_logic_change": True,
            "push_forbidden": True,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", dest="json_path")
    args = parser.parse_args()
    result = audit()
    print(f"hwpx_download_export_usecase_status={result['status']}")
    print(f"finding_count={result['finding_count']}")
    for item in result["findings"][:20]:
        print(f"{item['severity']} {item['rule']}")
    if args.json_path:
        Path(args.json_path).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
