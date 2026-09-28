#!/usr/bin/env python3
"""Read-only P11A/P12/P13 audit: HWPX browser editor product focus structure check."""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    # Windows 콘솔 기본 코드페이지(cp949)에서 findings 안의 '—' 등을
    # 못 찍어서 UnicodeEncodeError 로 죽는 것 방지.
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
HTTP_DIR = ROOT / "src/main/java/com/haehan/engine/http"
USECASE_DIR = ROOT / "src/main/java/com/haehan/engine/usecase"
GATE_DIR = ROOT / "src/main/java/com/haehan/engine/gate"
ARCH_DIR = ROOT / "docs/architecture"

REQUIRED_ARCH_DOCS = [
    "hwpx_browser_editor_product_scope_20260515.md",
    "hwpx_browser_editor_product_scope_20260515.json",
    "hwpx_editor_command_contract_20260515.md",
    "hwpx_editor_command_contract_20260515.json",
    "hwpx_editor_state_model_20260515.md",
    "hwpx_editor_state_model_20260515.json",
    "hwpx_editor_usecase_plan_20260515.md",
    "hwpx_editor_usecase_plan_20260515.json",
]

EXISTING_EDITOR_HANDLERS = [
    "HwpxEditorApiHandler.java",
    "HwpxUploadHandler.java",
    "ParseHwpxHandler.java",
]

EXISTING_USECASES = [
    "HwpxUploadParseUseCase.java",
    "HwpxDownloadExportUseCase.java",
]

# P12: new components
P12_USECASES = [
    "HwpxEditorCommandUseCase.java",
    "HwpxEditorCommandResult.java",
]

P12_GATES = [
    "HwpxEditorValidationGate.java",
    "HwpxEditorValidationResult.java",
]

CONTRACT_DIR = ROOT / "src/main/java/com/haehan/engine/contract"

P12_CONTRACTS = [
    "HwpxEditorCommand.java",
]

SUPPORTED_COMMAND_TYPES = [
    "replaceText", "replacePlaceholder", "updateParagraph",
    "updateTableCell", "addTableRow", "deleteTableRow", "validateDocument",
]

EXISTING_GATES = [
    "FileTypeGate.java",
    "UploadSecurityGate.java",
    "OutputArtifactGate.java",
    "ExecutionLocationGate.java",
]

FORBIDDEN_PATTERNS_IN_HANDLER = [
    "Runtime.exec(",
    "ProcessBuilder",
    "hancom.exe",
    "HncCtrl",
]

BROWSER_BOUNDARY_VIOLATIONS = [
    "hwpx_edit_tool",
    "hwpx_server_ops",
]


@dataclass
class Finding:
    severity: str
    rule: str
    file: str
    detail: str


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def audit() -> dict:
    findings: list[Finding] = []

    # 1. Architecture docs check
    arch_doc_status: dict[str, bool] = {}
    for doc in REQUIRED_ARCH_DOCS:
        exists = (ARCH_DIR / doc).exists()
        arch_doc_status[doc] = exists
        if not exists:
            findings.append(Finding("FAIL", "arch_doc_missing", doc, f"Required P11A architecture doc not found: {doc}"))

    # 2. Existing editor handlers present
    handler_status: dict[str, bool] = {}
    for h in EXISTING_EDITOR_HANDLERS:
        p = HTTP_DIR / h
        handler_status[h] = p.exists()
        if not p.exists():
            findings.append(Finding("FAIL", "editor_handler_missing", h, f"Editor handler not found: {h}"))

    # 3. Existing usecases present
    usecase_status: dict[str, bool] = {}
    for u in EXISTING_USECASES:
        p = USECASE_DIR / u
        usecase_status[u] = p.exists()
        if not p.exists():
            findings.append(Finding("FAIL", "usecase_missing", u, f"Required usecase not found: {u}"))

    # 4. Existing gates present
    gate_status: dict[str, bool] = {}
    for g in EXISTING_GATES:
        p = GATE_DIR / g
        gate_status[g] = p.exists()
        if not p.exists():
            findings.append(Finding("FAIL", "gate_missing", g, f"Required gate not found: {g}"))

    # 5. HwpxEditorApiHandler: check no forbidden patterns (Hancom auto-run guard)
    editor_handler_text = read(HTTP_DIR / "HwpxEditorApiHandler.java")
    for pat in FORBIDDEN_PATTERNS_IN_HANDLER:
        if pat in editor_handler_text:
            findings.append(Finding("FAIL", "forbidden_pattern_in_handler", "HwpxEditorApiHandler.java",
                                    f"Forbidden pattern '{pat}' found — Hancom/runtime exec forbidden"))

    # 6. EngineHttpServer: check editor endpoint registered
    engine_server_text = read(HTTP_DIR / "EngineHttpServer.java")
    editor_endpoint_registered = "/api/hwpx/editor" in engine_server_text
    upload_endpoint_registered = "/hwpx-editor" in engine_server_text or "/hwpx-upload" in engine_server_text
    if not editor_endpoint_registered:
        findings.append(Finding("FAIL", "editor_endpoint_not_registered", "EngineHttpServer.java",
                                "/api/hwpx/editor not registered"))
    if not upload_endpoint_registered:
        findings.append(Finding("WARN", "upload_page_not_registered", "EngineHttpServer.java",
                                "/hwpx-editor or /hwpx-upload not registered"))

    # 7. ExecutionLocationGate: check USER_PRESENT_REQUIRED blocks authentication
    exec_gate_text = read(GATE_DIR / "ExecutionLocationGate.java")
    exec_gate_blocks_auth = "USER_PRESENT_REQUIRED" in exec_gate_text
    exec_gate_allows_hwpx = "SERVER_ALLOWED" in exec_gate_text
    if not exec_gate_blocks_auth:
        findings.append(Finding("WARN", "exec_gate_no_user_present_block", "ExecutionLocationGate.java",
                                "USER_PRESENT_REQUIRED not found — authentication boundary may not be enforced"))
    if not exec_gate_allows_hwpx:
        findings.append(Finding("WARN", "exec_gate_no_server_allowed", "ExecutionLocationGate.java",
                                "SERVER_ALLOWED not found — HWPX server execution may not be classified"))

    # 8. FileTypeGate: HWPX allowed, HWP is warn (not server-allowed)
    filetype_gate_text = read(GATE_DIR / "FileTypeGate.java")
    hwpx_allowed = ".hwpx" in filetype_gate_text and (
        "GateResult.pass(" in filetype_gate_text or "PASS" in filetype_gate_text or
        "SERVER_ALLOWED" in filetype_gate_text
    )
    hwp_not_pass = ".hwp" in filetype_gate_text and (
        "WARN" in filetype_gate_text or "FAIL" in filetype_gate_text or
        "LOCAL_WORKER_REQUIRED" in filetype_gate_text
    )
    if not hwpx_allowed:
        findings.append(Finding("WARN", "filetype_gate_hwpx_not_explicitly_allowed", "FileTypeGate.java",
                                ".hwpx PASS not found"))
    if not hwp_not_pass:
        findings.append(Finding("WARN", "filetype_gate_hwp_may_be_allowed", "FileTypeGate.java",
                                ".hwp may not be gated correctly"))

    # P12: new usecase, gate, contract files
    p12_usecase_status: dict[str, bool] = {}
    for u in P12_USECASES:
        exists = (USECASE_DIR / u).exists()
        p12_usecase_status[u] = exists
        if not exists:
            findings.append(Finding("FAIL", "p12_usecase_missing", u, f"P12 usecase not found: {u}"))

    p12_gate_status: dict[str, bool] = {}
    for g in P12_GATES:
        exists = (GATE_DIR / g).exists()
        p12_gate_status[g] = exists
        if not exists:
            findings.append(Finding("FAIL", "p12_gate_missing", g, f"P12 gate not found: {g}"))

    p12_contract_status: dict[str, bool] = {}
    for c in P12_CONTRACTS:
        exists = (CONTRACT_DIR / c).exists()
        p12_contract_status[c] = exists
        if not exists:
            findings.append(Finding("FAIL", "p12_contract_missing", c, f"P12 contract not found: {c}"))

    # HwpxEditorCommandUseCase: must not import http package
    usecase_cmd_text = read(USECASE_DIR / "HwpxEditorCommandUseCase.java")
    usecase_imports_http = "com.haehan.engine.http" in usecase_cmd_text or "com.sun.net.httpserver" in usecase_cmd_text
    if usecase_imports_http:
        findings.append(Finding("FAIL", "usecase_imports_http",
                                "HwpxEditorCommandUseCase.java",
                                "usecase must not import http package"))

    # HwpxEditorValidationGate: must have no side effects
    gate_text = read(GATE_DIR / "HwpxEditorValidationGate.java")
    gate_side_effect_keywords = ["Files.write", "ProcessBuilder", "Runtime.exec", "HttpClient", "Connection"]
    for kw in gate_side_effect_keywords:
        if kw in gate_text:
            findings.append(Finding("FAIL", "gate_has_side_effect",
                                    "HwpxEditorValidationGate.java",
                                    f"gate must not have side effects, found: {kw}"))

    # HwpxEditorValidationGate: must check raw paths and forbidden keys
    gate_checks_raw_path = "isRawPath" in gate_text or "rawPath" in gate_text.lower() or "../" in gate_text
    gate_checks_forbidden_keys = "FORBIDDEN_KEYS" in gate_text or "secret" in gate_text.lower()
    if not gate_checks_raw_path:
        findings.append(Finding("WARN", "gate_no_raw_path_check",
                                "HwpxEditorValidationGate.java",
                                "gate should check for raw filesystem paths"))
    if not gate_checks_forbidden_keys:
        findings.append(Finding("WARN", "gate_no_forbidden_key_check",
                                "HwpxEditorValidationGate.java",
                                "gate should check for forbidden security-sensitive keys"))

    # Command types: all 7 supported types documented in gate
    gate_command_coverage: dict[str, bool] = {}
    for ctype in SUPPORTED_COMMAND_TYPES:
        gate_command_coverage[ctype] = ctype in gate_text
        if ctype not in gate_text:
            findings.append(Finding("WARN", "gate_missing_command_type",
                                    "HwpxEditorValidationGate.java",
                                    f"command type '{ctype}' not found in gate"))

    # HwpxEditorCommand: must be in contract package, not http
    cmd_text = read(CONTRACT_DIR / "HwpxEditorCommand.java")
    cmd_in_contract = "package com.haehan.engine.contract" in cmd_text
    if not cmd_in_contract and cmd_text:
        findings.append(Finding("FAIL", "command_not_in_contract_package",
                                "HwpxEditorCommand.java",
                                "HwpxEditorCommand must be in contract package"))

    # 9. Product scope JSON: validate key fields exist
    scope_json_path = ARCH_DIR / "hwpx_browser_editor_product_scope_20260515.json"
    if scope_json_path.exists():
        try:
            scope = json.loads(scope_json_path.read_text(encoding="utf-8"))
            if not scope.get("core_principle", {}).get("browser_direct_hwpx_access") is False:
                findings.append(Finding("WARN", "scope_json_missing_browser_access_false",
                                        "hwpx_browser_editor_product_scope_20260515.json",
                                        "browser_direct_hwpx_access must be false"))
            if not scope.get("core_principle", {}).get("hancom_auto_run") is False:
                findings.append(Finding("WARN", "scope_json_missing_hancom_auto_run_false",
                                        "hwpx_browser_editor_product_scope_20260515.json",
                                        "hancom_auto_run must be false"))
        except Exception as e:
            findings.append(Finding("WARN", "scope_json_parse_error",
                                    "hwpx_browser_editor_product_scope_20260515.json", str(e)))

    # 10. Usecase plan JSON: validate implementation order exists
    plan_json_path = ARCH_DIR / "hwpx_editor_usecase_plan_20260515.json"
    if plan_json_path.exists():
        try:
            plan = json.loads(plan_json_path.read_text(encoding="utf-8"))
            phases = [item["phase"] for item in plan.get("implementation_order", [])]
            for required_phase in ["P12", "P13", "P14"]:
                if required_phase not in phases:
                    findings.append(Finding("WARN", "usecase_plan_missing_phase",
                                            "hwpx_editor_usecase_plan_20260515.json",
                                            f"Phase {required_phase} not in implementation_order"))
        except Exception as e:
            findings.append(Finding("WARN", "usecase_plan_json_parse_error",
                                    "hwpx_editor_usecase_plan_20260515.json", str(e)))

    # P13: command dispatch checks
    scripts_text = read(HTTP_DIR / "HwpxUploadPageScripts.java")
    api_handler_text = read(HTTP_DIR / "HwpxEditorApiHandler.java")

    p13_build_editor_command = "buildEditorCommand" in scripts_text
    p13_dispatch_editor_command = "dispatchEditorCommand" in scripts_text
    p13_render_editor_command_result = "renderEditorCommandResult" in scripts_text
    p13_validate_editor_document = "validateEditorDocument" in scripts_text
    p13_dry_run_replace_text = "dryRunReplaceText" in scripts_text
    p13_dry_run_update_table_cell = "dryRunUpdateTableCell" in scripts_text
    p13_command_result_panel = "commandResultPanel" in scripts_text
    p13_handler_uses_usecase = "HwpxEditorCommandUseCase" in api_handler_text
    p13_handler_uses_command = "HwpxEditorCommand" in api_handler_text
    # Only check command dispatch section (SCRIPT_5) for XML/ZIP access — existing photo code excluded
    _s5_start = scripts_text.find("buildEditorCommand")
    _script5_text = scripts_text[_s5_start:] if _s5_start >= 0 else ""
    p13_no_xml_zip_in_scripts = "BinData/" not in _script5_text and "Contents/" not in _script5_text
    p13_no_raw_path_dispatch = (
        "raw_path" not in scripts_text.lower() or "rawPathGuard" in scripts_text
    )
    p13_no_secret_dispatch = not any(
        kw in scripts_text.lower() for kw in ["password:", "token:", "secret:", "cookie:"]
        if kw not in "outputArtifactRawPathGuard"
    )
    p13_dry_run_default = "dryRun: true" in scripts_text or "dryRun !== false" in scripts_text

    if not p13_build_editor_command:
        findings.append(Finding("FAIL", "p13_build_editor_command_missing",
                                "HwpxUploadPageScripts.java", "buildEditorCommand not found"))
    if not p13_dispatch_editor_command:
        findings.append(Finding("FAIL", "p13_dispatch_editor_command_missing",
                                "HwpxUploadPageScripts.java", "dispatchEditorCommand not found"))
    if not p13_render_editor_command_result:
        findings.append(Finding("FAIL", "p13_render_editor_command_result_missing",
                                "HwpxUploadPageScripts.java", "renderEditorCommandResult not found"))
    if not p13_validate_editor_document:
        findings.append(Finding("FAIL", "p13_validate_editor_document_missing",
                                "HwpxUploadPageScripts.java", "validateEditorDocument not found"))
    if not p13_dry_run_replace_text:
        findings.append(Finding("WARN", "p13_dry_run_replace_text_missing",
                                "HwpxUploadPageScripts.java", "dryRunReplaceText not found"))
    if not p13_dry_run_update_table_cell:
        findings.append(Finding("WARN", "p13_dry_run_update_table_cell_missing",
                                "HwpxUploadPageScripts.java", "dryRunUpdateTableCell not found"))
    if not p13_command_result_panel:
        findings.append(Finding("WARN", "p13_command_result_panel_missing",
                                "HwpxUploadPageScripts.java", "commandResultPanel not found"))
    if not p13_handler_uses_usecase:
        findings.append(Finding("FAIL", "p13_handler_not_wired_to_usecase",
                                "HwpxEditorApiHandler.java", "HwpxEditorCommandUseCase not referenced"))
    if not p13_handler_uses_command:
        findings.append(Finding("FAIL", "p13_handler_not_wired_to_command",
                                "HwpxEditorApiHandler.java", "HwpxEditorCommand not referenced"))
    if not p13_no_xml_zip_in_scripts:
        findings.append(Finding("FAIL", "p13_xml_zip_in_scripts",
                                "HwpxUploadPageScripts.java", "BinData/ or Contents/ found in browser scripts"))
    if not p13_dry_run_default:
        findings.append(Finding("WARN", "p13_dry_run_not_default",
                                "HwpxUploadPageScripts.java", "dryRun default true not confirmed in command dispatch"))

    severities = {f.severity for f in findings}
    status = "FAIL" if "FAIL" in severities else ("WARN" if "WARN" in severities else "PASS")

    return {
        "audit": "hwpx_browser_editor_structure",
        "phase": "P13",
        "status": status,
        "arch_docs": arch_doc_status,
        "editor_handlers": handler_status,
        "usecases": usecase_status,
        "gates": gate_status,
        "editor_endpoint_registered": editor_endpoint_registered,
        "upload_page_registered": upload_endpoint_registered,
        "exec_gate": {
            "user_present_required_enforced": exec_gate_blocks_auth,
            "server_allowed_for_hwpx": exec_gate_allows_hwpx,
        },
        "filetype_gate": {
            "hwpx_allowed": hwpx_allowed,
            "hwp_not_server_pass": hwp_not_pass,
        },
        "p12": {
            "usecases": p12_usecase_status,
            "gates": p12_gate_status,
            "contracts": p12_contract_status,
            "usecase_no_http_import": not usecase_imports_http,
            "gate_no_side_effects": not any(kw in gate_text for kw in gate_side_effect_keywords),
            "gate_raw_path_check": gate_checks_raw_path,
            "gate_forbidden_key_check": gate_checks_forbidden_keys,
            "command_type_coverage": gate_command_coverage,
            "command_in_contract_package": cmd_in_contract,
        },
        "p13": {
            "build_editor_command": p13_build_editor_command,
            "dispatch_editor_command": p13_dispatch_editor_command,
            "render_editor_command_result": p13_render_editor_command_result,
            "validate_editor_document": p13_validate_editor_document,
            "dry_run_replace_text": p13_dry_run_replace_text,
            "dry_run_update_table_cell": p13_dry_run_update_table_cell,
            "command_result_panel": p13_command_result_panel,
            "handler_wired_to_usecase": p13_handler_uses_usecase,
            "handler_wired_to_command": p13_handler_uses_command,
            "no_xml_zip_in_scripts": p13_no_xml_zip_in_scripts,
            "dry_run_default_true": p13_dry_run_default,
        },
        "finding_count": len(findings),
        "findings": [asdict(f) for f in findings],
        "policy": {
            "no_endpoint_path_change": True,
            "no_existing_gate_change": True,
            "no_browser_hwpx_direct_access": True,
            "no_hancom_auto_run": True,
            "push_forbidden": True,
            "db_write_forbidden": True,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", dest="json_path")
    args = parser.parse_args()
    result = audit()
    print(f"hwpx_browser_editor_structure_status={result['status']}")
    print(f"finding_count={result['finding_count']}")
    for item in result["findings"][:20]:
        print(f"  {item['severity']} [{item['file']}] {item['rule']}: {item['detail'][:80]}")
    if args.json_path:
        Path(args.json_path).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
