#!/usr/bin/env python3
"""Read-only P9D audit: ParseHwpxHandler usecase gate wiring readiness."""

from __future__ import annotations

import argparse
import json
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


@dataclass
class _GateSignals:
    handler_exists: bool
    usecase_exists: bool
    result_exists: bool
    handler_references_usecase: bool
    handler_references_result: bool
    usecase_no_http_import: bool
    handler_uses_gate_directly: bool
    error_key_in_handler: bool
    status_415_in_handler: bool
    status_413_in_handler: bool
    endpoint_preserved: bool
    gate_files_exist: dict[str, bool]


def read(path: Path) -> str:
    p = ROOT / path
    return p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""


def _collect_findings(signals: _GateSignals) -> list[Finding]:
    checks: list[tuple[bool, str, str, str]] = [
        (not signals.handler_exists, "FAIL", "handler_missing", "ParseHwpxHandler.java not found"),
        (
            not signals.usecase_exists,
            "FAIL",
            "usecase_missing",
            "HwpxUploadParseUseCase.java not found",
        ),
        (
            not signals.result_exists,
            "FAIL",
            "result_missing",
            "HwpxUploadParseResult.java not found",
        ),
        (
            not signals.handler_references_usecase,
            "FAIL",
            "handler_not_wired",
            "ParseHwpxHandler does not reference HwpxUploadParseUseCase",
        ),
        (
            not signals.handler_references_result,
            "WARN",
            "handler_result_ref_missing",
            "ParseHwpxHandler does not reference HwpxUploadParseResult",
        ),
        (
            not signals.usecase_no_http_import,
            "FAIL",
            "usecase_imports_http",
            "HwpxUploadParseUseCase imports from http package — layer boundary violated",
        ),
        (
            signals.handler_uses_gate_directly,
            "WARN",
            "handler_gate_direct",
            "ParseHwpxHandler references gate classes directly (should delegate via usecase)",
        ),
        (
            not signals.error_key_in_handler,
            "FAIL",
            "error_key_missing",
            'ParseHwpxHandler does not include "error" key in responses',
        ),
        (
            not signals.status_415_in_handler,
            "WARN",
            "status_415_missing",
            "ParseHwpxHandler does not map to HTTP 415 for unsupported file types",
        ),
        (
            not signals.status_413_in_handler,
            "WARN",
            "status_413_missing",
            "ParseHwpxHandler does not map to HTTP 413 for oversized uploads",
        ),
        (
            not signals.endpoint_preserved,
            "FAIL",
            "endpoint_path_changed",
            "/parse-hwpx endpoint is no longer mapped to ParseHwpxHandler in EngineHttpServer",
        ),
    ]
    findings = [Finding(sev, rule, detail) for triggered, sev, rule, detail in checks if triggered]
    for name, exists in signals.gate_files_exist.items():
        if not exists:
            findings.append(Finding("FAIL", f"gate_file_missing_{name}", f"{name}.java not found"))
    return findings


def audit() -> dict:
    handler_text = read(HANDLER)
    usecase_text = read(USECASE)
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

    findings = _collect_findings(
        _GateSignals(
            handler_exists=handler_exists,
            usecase_exists=usecase_exists,
            result_exists=result_exists,
            handler_references_usecase=handler_references_usecase,
            handler_references_result=handler_references_result,
            usecase_no_http_import=usecase_no_http_import,
            handler_uses_gate_directly=handler_uses_gate_directly,
            error_key_in_handler=error_key_in_handler,
            status_415_in_handler=status_415_in_handler,
            status_413_in_handler=status_413_in_handler,
            endpoint_preserved=endpoint_preserved,
            gate_files_exist=gate_files_exist,
        )
    )

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
        Path(args.json_path).write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
