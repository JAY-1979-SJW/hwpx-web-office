#!/usr/bin/env python3
"""Read-only P9D audit: ParseHwpxHandler usecase gate wiring readiness."""
from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HANDLER = Path("src/main/java/com/haehan/engine/http/ParseHwpxHandler.java")
USECASE = Path("src/main/java/com/haehan/engine/usecase/HwpxUploadParseUseCase.java")
RESULT = Path("src/main/java/com/haehan/engine/usecase/HwpxUploadParseResult.java")
SERVER = Path("src/main/java/com/haehan/engine/http/EngineHttpServer.java")
GATE_FILES = {
    "FileTypeGate": Path("src/main/java/com/haehan/engine/gate/FileTypeGate.java"),
    "UploadSecurityGate": Path("src/main/java/com/haehan/engine/gate/UploadSecurityGate.java"),
}


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
    handler_text = read(HANDLER)
    usecase_text = read(USECASE)
    result_text = read(RESULT)
    server_text = read(SERVER)

    handler_exists = (ROOT / HANDLER).exists()
    usecase_exists = (ROOT / USECASE).exists()
    result_exists = (ROOT / RESULT).exists()

    handler_references_usecase = "HwpxUploadParseUseCase" in handler_text
    handler_references_result = "HwpxUploadParseResult" in handler_text
    usecase_no_http_import = "com.haehan.engine.http" not in usecase_text
    handler_uses_gate_directly = (
        "FileTypeGate" in handler_text or "UploadSecurityGate" in handler_text
    )
    error_key_in_handler = '"error"' in handler_text
    status_415_in_handler = "415" in handler_text
    status_413_in_handler = "413" in handler_text
    endpoint_preserved = "/parse-hwpx" in server_text and "ParseHwpxHandler" in server_text
    gate_files_exist = {name: (ROOT / path).exists() for name, path in GATE_FILES.items()}

    if not handler_exists:
        findings.append(Finding("FAIL", "handler_missing", "ParseHwpxHandler.java not found"))
    if not usecase_exists:
        findings.append(Finding("FAIL", "usecase_missing", "HwpxUploadParseUseCase.java not found"))
    if not result_exists:
        findings.append(Finding("FAIL", "result_missing", "HwpxUploadParseResult.java not found"))
    if not handler_references_usecase:
        findings.append(Finding("FAIL", "handler_not_wired", "ParseHwpxHandler does not reference HwpxUploadParseUseCase"))
    if not handler_references_result:
        findings.append(Finding("WARN", "handler_result_ref_missing", "ParseHwpxHandler does not reference HwpxUploadParseResult"))
    if not usecase_no_http_import:
        findings.append(Finding("FAIL", "usecase_imports_http", "HwpxUploadParseUseCase imports from http package — layer boundary violated"))
    if handler_uses_gate_directly:
        findings.append(Finding("WARN", "handler_gate_direct", "ParseHwpxHandler references gate classes directly (should delegate via usecase)"))
    if not error_key_in_handler:
        findings.append(Finding("FAIL", "error_key_missing", 'ParseHwpxHandler does not include "error" key in responses'))
    if not status_415_in_handler:
        findings.append(Finding("WARN", "status_415_missing", "ParseHwpxHandler does not map to HTTP 415 for unsupported file types"))
    if not status_413_in_handler:
        findings.append(Finding("WARN", "status_413_missing", "ParseHwpxHandler does not map to HTTP 413 for oversized uploads"))
    if not endpoint_preserved:
        findings.append(Finding("FAIL", "endpoint_path_changed", "/parse-hwpx endpoint is no longer mapped to ParseHwpxHandler in EngineHttpServer"))
    for name, exists in gate_files_exist.items():
        if not exists:
            findings.append(Finding("FAIL", f"gate_file_missing_{name}", f"{name}.java not found"))

    severities = {f.severity for f in findings}
    status = "FAIL" if "FAIL" in severities else ("WARN" if "WARN" in severities else "PASS")
    return {
        "audit": "parse_hwpx_handler_usecase_gate",
        "phase": "P9D",
        "status": status,
        "handler": {
            "exists": handler_exists,
            "references_usecase": handler_references_usecase,
            "references_result": handler_references_result,
            "uses_gate_directly": handler_uses_gate_directly,
            "error_key_present": error_key_in_handler,
            "status_415_present": status_415_in_handler,
            "status_413_present": status_413_in_handler,
        },
        "usecase": {
            "exists": usecase_exists,
            "no_http_import": usecase_no_http_import,
        },
        "endpoint": {
            "parse_hwpx_preserved": endpoint_preserved,
        },
        "gate_presence": gate_files_exist,
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
    print(f"parse_hwpx_handler_usecase_gate_status={result['status']}")
    print(f"finding_count={result['finding_count']}")
    for item in result["findings"][:20]:
        print(f"{item['severity']} {item['rule']}")
    if args.json_path:
        Path(args.json_path).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
