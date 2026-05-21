#!/usr/bin/env python3
"""Read-only P13A audit: HWPX editor architecture gate — module boundary, schema, operating rules."""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTTP_DIR = ROOT / "src/main/java/com/haehan/engine/http"
USECASE_DIR = ROOT / "src/main/java/com/haehan/engine/usecase"
GATE_DIR = ROOT / "src/main/java/com/haehan/engine/gate"
CONTRACT_DIR = ROOT / "src/main/java/com/haehan/engine/contract"
ARTIFACT_DIR = ROOT / "src/main/java/com/haehan/engine/artifact"
ARCH_DIR = ROOT / "docs/architecture"
REPORTS_DIR = ROOT / "docs/reports"

REQUIRED_ARCH_DOCS = [
    "hwpx_browser_editor_app_structure_20260515.md",
    "hwpx_browser_editor_module_boundary_rules_20260515.md",
    "hwpx_editor_api_schema_map_20260515.md",
    "hwpx_editor_command_schema_contract_20260515.md",
    "hwpx_editor_operating_rules_20260515.md",
]

P13A_GATE_FILES = [
    "audit_hwpx_editor_architecture_gate.py",
    "test_hwpx_editor_architecture_gate.py",
]

GATE_SIDE_EFFECT_KEYWORDS = [
    "Files.write", "ProcessBuilder", "Runtime.exec", "HttpClient", "Connection"
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

    # 1. Required architecture docs
    arch_docs: dict[str, bool] = {}
    for doc in REQUIRED_ARCH_DOCS:
        exists = (ARCH_DIR / doc).exists()
        arch_docs[doc] = exists
        if not exists:
            findings.append(Finding("FAIL", "arch_doc_missing", doc,
                                    f"Required P13A architecture doc not found: {doc}"))

    # 2. P13A gate files exist
    gate_file_status: dict[str, bool] = {}
    for f in P13A_GATE_FILES:
        exists = (ROOT / ("scripts" if "audit_" in f else "tests") / f).exists()
        gate_file_status[f] = exists
        if not exists:
            findings.append(Finding("FAIL", "gate_file_missing", f,
                                    f"P13A gate file not found: {f}"))

    # 3. Operating rules doc referenced audit gate
    op_rules_text = read(ARCH_DIR / "hwpx_editor_operating_rules_20260515.md")
    op_rules_has_gate = "audit_hwpx_editor_architecture_gate" in op_rules_text
    if not op_rules_has_gate:
        findings.append(Finding("WARN", "operating_rules_no_gate_ref",
                                "hwpx_editor_operating_rules_20260515.md",
                                "audit gate not referenced in operating rules"))

    # RULE-01: UI has buildEditorCommand
    scripts_text = read(HTTP_DIR / "HwpxUploadPageScripts.java")
    rule01_build_cmd = "buildEditorCommand" in scripts_text
    rule01_dispatch_cmd = "dispatchEditorCommand" in scripts_text
    if not rule01_build_cmd:
        findings.append(Finding("FAIL", "rule01_build_editor_command_missing",
                                "HwpxUploadPageScripts.java", "RULE-01: buildEditorCommand not found"))
    if not rule01_dispatch_cmd:
        findings.append(Finding("FAIL", "rule01_dispatch_editor_command_missing",
                                "HwpxUploadPageScripts.java", "RULE-01: dispatchEditorCommand not found"))

    # RULE-02: command dispatch area has no BinData/Contents (SCRIPT_5 region)
    s5_start = scripts_text.find("buildEditorCommand")
    script5_text = scripts_text[s5_start:] if s5_start >= 0 else ""
    rule02_no_xml_zip = "BinData/" not in script5_text and "Contents/" not in script5_text
    if not rule02_no_xml_zip:
        findings.append(Finding("FAIL", "rule02_xml_zip_in_command_dispatch",
                                "HwpxUploadPageScripts.java",
                                "RULE-02: BinData/ or Contents/ found in command dispatch section"))

    # RULE-03: view has no raw filesystem path
    view_text = read(HTTP_DIR / "HwpxUploadPageView.java")
    styles_text = read(HTTP_DIR / "HwpxUploadPageStyles.java")
    rule03_raw_paths = ["/home/", "C:\\\\", "/var/", "/tmp/"]
    rule03_no_raw_in_view = not any(p in view_text for p in rule03_raw_paths)
    rule03_no_raw_in_styles_html = not any(p in styles_text for p in rule03_raw_paths)
    if not rule03_no_raw_in_view:
        findings.append(Finding("FAIL", "rule03_raw_path_in_view",
                                "HwpxUploadPageView.java",
                                "RULE-03: raw filesystem path found in view"))
    if not rule03_no_raw_in_styles_html:
        findings.append(Finding("FAIL", "rule03_raw_path_in_styles",
                                "HwpxUploadPageStyles.java",
                                "RULE-03: raw filesystem path found in styles/HTML"))

    # RULE-04: artifactId guard in handler
    handler_text = read(HTTP_DIR / "HwpxEditorApiHandler.java")
    rule04_guarded = "guardedArtifactRef" in handler_text or "guardedReportRef" in handler_text or "isRawPathGuarded" in handler_text
    if not rule04_guarded:
        findings.append(Finding("WARN", "rule04_no_artifact_path_guard",
                                "HwpxEditorApiHandler.java",
                                "RULE-04: artifactId guard pattern not found in handler"))

    # RULE-05: Handler uses UseCase for command dispatch
    rule05_uses_usecase = "HwpxEditorCommandUseCase" in handler_text
    rule05_uses_command = "HwpxEditorCommand" in handler_text
    if not rule05_uses_usecase:
        findings.append(Finding("FAIL", "rule05_handler_not_wired_to_usecase",
                                "HwpxEditorApiHandler.java",
                                "RULE-05: HwpxEditorCommandUseCase not referenced in handler"))
    if not rule05_uses_command:
        findings.append(Finding("FAIL", "rule05_handler_not_wired_to_command",
                                "HwpxEditorApiHandler.java",
                                "RULE-05: HwpxEditorCommand not referenced in handler"))

    # RULE-06: UseCase has no http import
    usecase_text = read(USECASE_DIR / "HwpxEditorCommandUseCase.java")
    rule06_no_http = (
        "com.haehan.engine.http" not in usecase_text and
        "com.sun.net.httpserver" not in usecase_text
    )
    if not rule06_no_http:
        findings.append(Finding("FAIL", "rule06_usecase_imports_http",
                                "HwpxEditorCommandUseCase.java",
                                "RULE-06: UseCase must not import http package"))

    # RULE-07: Gate has no side effects
    gate_text = read(GATE_DIR / "HwpxEditorValidationGate.java")
    rule07_no_side_effects = not any(kw in gate_text for kw in GATE_SIDE_EFFECT_KEYWORDS)
    if not rule07_no_side_effects:
        bad = [kw for kw in GATE_SIDE_EFFECT_KEYWORDS if kw in gate_text]
        findings.append(Finding("FAIL", "rule07_gate_has_side_effects",
                                "HwpxEditorValidationGate.java",
                                f"RULE-07: gate must not have side effects: {bad}"))

    # RULE-07: Gate checks forbidden keys and raw paths
    rule07_forbidden_keys = "FORBIDDEN_KEYS" in gate_text or "secret" in gate_text.lower()
    rule07_raw_path = "isRawPath" in gate_text or "rawPath" in gate_text.lower()
    if not rule07_forbidden_keys:
        findings.append(Finding("WARN", "rule07_gate_no_forbidden_key_check",
                                "HwpxEditorValidationGate.java",
                                "RULE-07: gate should check forbidden security-sensitive keys"))
    if not rule07_raw_path:
        findings.append(Finding("WARN", "rule07_gate_no_raw_path_check",
                                "HwpxEditorValidationGate.java",
                                "RULE-07: gate should check raw filesystem paths"))

    # RULE-08: dryRun default true in scripts
    rule08_dry_run_default = "dryRun !== false" in scripts_text or "dryRun: true" in scripts_text
    if not rule08_dry_run_default:
        findings.append(Finding("WARN", "rule08_dry_run_default_not_confirmed",
                                "HwpxUploadPageScripts.java",
                                "RULE-08: dryRun default true pattern not confirmed"))

    # RULE-09: No actual apply in P13 command dispatch (APPLY_DEFERRED present)
    result_text = read(USECASE_DIR / "HwpxEditorCommandResult.java")
    rule09_apply_deferred = "APPLY_DEFERRED" in result_text or "applyDeferred" in result_text
    if not rule09_apply_deferred:
        findings.append(Finding("FAIL", "rule09_apply_deferred_missing",
                                "HwpxEditorCommandResult.java",
                                "RULE-09: APPLY_DEFERRED status not found — P13 apply boundary unclear"))

    # RULE-10: Endpoint paths not changed
    server_text = read(HTTP_DIR / "EngineHttpServer.java")
    rule10_editor_endpoint = "/api/hwpx/editor" in server_text
    rule10_upload_endpoint = "/hwpx-editor" in server_text or "/hwpx-upload" in server_text or "hwpx" in server_text.lower()
    if not rule10_editor_endpoint:
        findings.append(Finding("FAIL", "rule10_editor_endpoint_missing",
                                "EngineHttpServer.java",
                                "RULE-10: /api/hwpx/editor not registered"))
    if not rule10_upload_endpoint:
        findings.append(Finding("WARN", "rule10_upload_endpoint_missing",
                                "EngineHttpServer.java",
                                "RULE-10: hwpx upload page endpoint not found"))

    # RULE-11: meta contract present in handler (schemaVersion/engineVersion)
    rule11_schema_version = "schemaVersion" in handler_text
    rule11_engine_version = "engineVersion" in handler_text or "ApiResponseMeta" in handler_text
    if not rule11_schema_version:
        findings.append(Finding("WARN", "rule11_schema_version_missing_in_handler",
                                "HwpxEditorApiHandler.java",
                                "RULE-11: schemaVersion not found in handler"))
    if not rule11_engine_version:
        findings.append(Finding("WARN", "rule11_engine_version_missing_in_handler",
                                "HwpxEditorApiHandler.java",
                                "RULE-11: engineVersion/ApiResponseMeta not found in handler"))

    # RULE-12: Secret keys checked in gate
    rule12_secret_check = "FORBIDDEN_KEYS" in gate_text
    if not rule12_secret_check:
        findings.append(Finding("WARN", "rule12_no_forbidden_keys_constant",
                                "HwpxEditorValidationGate.java",
                                "RULE-12: FORBIDDEN_KEYS constant not found in gate"))

    # RULE-14: Gate and test exist
    rule14_gate_exists = (ROOT / "scripts" / "audit_hwpx_editor_architecture_gate.py").exists()
    rule14_test_exists = (ROOT / "tests" / "test_hwpx_editor_architecture_gate.py").exists()
    if not rule14_gate_exists:
        findings.append(Finding("FAIL", "rule14_gate_script_missing",
                                "scripts/audit_hwpx_editor_architecture_gate.py",
                                "RULE-14: architecture gate script not found"))
    if not rule14_test_exists:
        findings.append(Finding("FAIL", "rule14_gate_test_missing",
                                "tests/test_hwpx_editor_architecture_gate.py",
                                "RULE-14: architecture gate test not found"))

    # RULE-15: File size check
    scripts_lines = len(scripts_text.splitlines())
    rule15_scripts_size_ok = scripts_lines < 3000
    if not rule15_scripts_size_ok:
        findings.append(Finding("WARN", "rule15_scripts_too_large",
                                "HwpxUploadPageScripts.java",
                                f"RULE-15: scripts file has {scripts_lines} lines — consider splitting"))

    # RULE-16: Operating rules doc has gate reference
    rule16_gate_ref = op_rules_has_gate
    if not rule16_gate_ref:
        findings.append(Finding("WARN", "rule16_operating_rules_no_gate",
                                "hwpx_editor_operating_rules_20260515.md",
                                "RULE-16: operating rules must reference audit gate"))

    # Command model in contract package (not http)
    cmd_model_text = read(CONTRACT_DIR / "HwpxEditorCommand.java")
    cmd_model_in_contract = "package com.haehan.engine.contract" in cmd_model_text
    cmd_model_no_http = "com.haehan.engine.http" not in cmd_model_text
    cmd_model_no_httpserver = "com.sun.net.httpserver" not in cmd_model_text
    cmd_model_no_file = "import java.nio.file" not in cmd_model_text
    if not cmd_model_in_contract:
        findings.append(Finding("FAIL", "cmd_model_wrong_package",
                                "HwpxEditorCommand.java",
                                "command model must be in contract package"))
    if not cmd_model_no_http:
        findings.append(Finding("FAIL", "cmd_model_imports_http",
                                "HwpxEditorCommand.java",
                                "command model must not import http package"))

    # P13B checks
    scripts_text2 = read(HTTP_DIR / "HwpxUploadPageScripts.java")
    styles_text2 = read(HTTP_DIR / "HwpxUploadPageStyles.java")
    s5_start2 = scripts_text2.find("buildEditorCommand")
    script5_text2 = scripts_text2[s5_start2:] if s5_start2 >= 0 else ""

    p13b_validate_doc = "validateEditorDocument" in scripts_text2
    if not p13b_validate_doc:
        findings.append(Finding("FAIL", "COMMAND_UI_VALIDATE_DOCUMENT_PRESENT",
                                "HwpxUploadPageScripts.java",
                                "P13B: validateEditorDocument function not found"))

    p13b_replace_text = "dryRunReplaceText" in scripts_text2 and "submitDryRunReplaceText" in scripts_text2
    if not p13b_replace_text:
        findings.append(Finding("FAIL", "COMMAND_UI_REPLACE_TEXT_PRESENT",
                                "HwpxUploadPageScripts.java",
                                "P13B: dryRunReplaceText or submitDryRunReplaceText not found"))

    p13b_update_cell = "dryRunUpdateTableCell" in scripts_text2 and "submitDryRunUpdateTableCell" in scripts_text2
    if not p13b_update_cell:
        findings.append(Finding("FAIL", "COMMAND_UI_UPDATE_TABLE_CELL_PRESENT",
                                "HwpxUploadPageScripts.java",
                                "P13B: dryRunUpdateTableCell or submitDryRunUpdateTableCell not found"))

    p13b_dry_run_only = "dryRun: false" not in script5_text2 and '"dryRun":false' not in script5_text2
    if not p13b_dry_run_only:
        findings.append(Finding("FAIL", "COMMAND_UI_DRY_RUN_ONLY",
                                "HwpxUploadPageScripts.java",
                                "P13B: dryRun=false found in command dispatch — P13B must be dryRun only"))

    p13b_no_apply_btn = "applyEditorCommand" not in scripts_text2 and "dryRun=false" not in scripts_text2
    if not p13b_no_apply_btn:
        findings.append(Finding("WARN", "COMMAND_UI_NO_APPLY_BUTTON_ACTIVE_PATH",
                                "HwpxUploadPageScripts.java",
                                "P13B: actual apply path found in scripts"))

    raw_path_ids = ["filePath", "internalPath", "serverPath", "rawPath"]
    p13b_no_raw_input = not any(f'id="{r}"' in styles_text2 or f"id='{r}'" in styles_text2
                                for r in raw_path_ids)
    if not p13b_no_raw_input:
        findings.append(Finding("FAIL", "COMMAND_UI_NO_RAW_PATH_INPUT",
                                "HwpxUploadPageStyles.java",
                                "P13B: raw path input field found in UI HTML"))

    xml_zip_in_s5 = any(kw in script5_text2 for kw in ["BinData/", "Contents/", ".xml", ".rels"])
    p13b_no_xml_zip = not xml_zip_in_s5
    if not p13b_no_xml_zip:
        findings.append(Finding("FAIL", "COMMAND_UI_NO_XML_ZIP_DIRECT_MUTATION",
                                "HwpxUploadPageScripts.java",
                                "P13B: XML/ZIP direct access found in command dispatch area"))

    p13b_session_required = "sessionArtifactId" in script5_text2
    if not p13b_session_required:
        findings.append(Finding("FAIL", "COMMAND_UI_SESSION_REQUIRED",
                                "HwpxUploadPageScripts.java",
                                "P13B: sessionArtifactId guard not found in command dispatch"))

    p13b_result_fields = (
        "requestId" in scripts_text2 and
        "warningCount" in scripts_text2 or "warnings.length" in scripts_text2 and
        "timestamp" in scripts_text2
    )
    if not p13b_result_fields:
        findings.append(Finding("WARN", "COMMAND_RESULT_PANEL_STATUS_FIELDS",
                                "HwpxUploadPageScripts.java",
                                "P13B: commandResultPanel missing requestId/warningCount/timestamp"))

    p13b_dup_guard = "state.commandRunning" in scripts_text2
    if not p13b_dup_guard:
        findings.append(Finding("FAIL", "COMMAND_DUPLICATE_SUBMIT_GUARD",
                                "HwpxUploadPageScripts.java",
                                "P13B: state.commandRunning duplicate-submit guard not found"))

    # P14A checks
    parse_resp_text = read(CONTRACT_DIR / "DocumentParseResponse.java")
    proxy_text = read(HTTP_DIR / "HwpxProxyHandler.java")
    handler_text2 = read(HTTP_DIR / "HwpxEditorApiHandler.java")
    artifact_registry_text = read(ARTIFACT_DIR / "ArtifactRegistry.java")
    artifact_id_gen_text = read(ARTIFACT_DIR / "ArtifactIdGenerator.java")

    p14a_artifact_in_parse_resp = "artifactId" in parse_resp_text
    if not p14a_artifact_in_parse_resp:
        findings.append(Finding("FAIL", "SERVER_ARTIFACT_ID_PARSE_RESPONSE_PRESENT",
                                "DocumentParseResponse.java",
                                "P14A: artifactId field not found in DocumentParseResponse"))

    p14a_non_empty_id = "UUID.randomUUID" in artifact_id_gen_text or "randomUUID" in artifact_id_gen_text
    if not p14a_non_empty_id:
        findings.append(Finding("FAIL", "SERVER_ARTIFACT_ID_NON_EMPTY",
                                "ArtifactIdGenerator.java",
                                "P14A: ArtifactIdGenerator must use UUID.randomUUID"))

    raw_leak_patterns = ["/home/", "/tmp/", "/var/", "C:\\\\", "tempFile.toString", "getAbsolutePath"]
    p14a_no_raw_path_leak = not any(p in proxy_text for p in raw_leak_patterns)
    if not p14a_no_raw_path_leak:
        bad = [p for p in raw_leak_patterns if p in proxy_text]
        findings.append(Finding("FAIL", "SERVER_ARTIFACT_ID_NO_RAW_PATH_LEAK",
                                "HwpxProxyHandler.java",
                                f"P14A: raw path found in proxy response: {bad}"))

    p14a_command_uses_server_id = "state.artifactId" in scripts_text2
    if not p14a_command_uses_server_id:
        findings.append(Finding("FAIL", "COMMAND_PAYLOAD_USES_SERVER_ARTIFACT_ID",
                                "HwpxUploadPageScripts.java",
                                "P14A: buildEditorCommand must use state.artifactId (server id)"))

    p14a_session_not_source = "artifactId: state.sessionArtifactId" not in scripts_text2
    if not p14a_session_not_source:
        findings.append(Finding("FAIL", "SESSION_ARTIFACT_ID_NOT_SOURCE_OF_TRUTH",
                                "HwpxUploadPageScripts.java",
                                "P14A: sessionArtifactId must not be used as artifactId in buildEditorCommand"))

    p14a_command_blocks_no_id = "state.artifactId" in scripts_text2 and (
        "artifactId" in scripts_text2
    )
    if not p14a_command_blocks_no_id:
        findings.append(Finding("FAIL", "COMMAND_BLOCKS_WITHOUT_ARTIFACT_ID",
                                "HwpxUploadPageScripts.java",
                                "P14A: command dispatch must guard state.artifactId"))

    p14a_unknown_id_rejected = "UNKNOWN_ARTIFACT_ID" in handler_text2
    if not p14a_unknown_id_rejected:
        findings.append(Finding("FAIL", "UNKNOWN_ARTIFACT_ID_REJECTED",
                                "HwpxEditorApiHandler.java",
                                "P14A: handler must reject unknown artifactId with UNKNOWN_ARTIFACT_ID"))

    p14a_dry_run_still = "dryRun: false" not in scripts_text2 and '"dryRun":false' not in scripts_text2
    if not p14a_dry_run_still:
        findings.append(Finding("FAIL", "DRY_RUN_ONLY_STILL_ENFORCED",
                                "HwpxUploadPageScripts.java",
                                "P14A: dryRun=false found in command dispatch"))

    p14a_no_apply_engine = "ApplyEngine" not in handler_text2 or "ApplyEngine" not in read(USECASE_DIR / "HwpxEditorCommandUseCase.java")
    if not p14a_no_apply_engine:
        findings.append(Finding("WARN", "NO_APPLY_ENGINE_CONNECTION_IN_P14A",
                                "HwpxEditorApiHandler.java",
                                "P14A: ApplyEngine connection found — apply deferred to P14C"))

    p14a_no_python_bridge_in_dispatch = "PythonScriptBridge" not in read(USECASE_DIR / "HwpxEditorCommandUseCase.java")
    if not p14a_no_python_bridge_in_dispatch:
        findings.append(Finding("WARN", "NO_PYTHON_SCRIPT_BRIDGE_CONNECTION_IN_P14A",
                                "HwpxEditorCommandUseCase.java",
                                "P14A: PythonScriptBridge connection found in usecase — not expected in P14A"))

    p14a_no_xml_zip_browser = not any(kw in scripts_text2[scripts_text2.find("buildEditorCommand"):]
                                      for kw in ["BinData/", "Contents/", ".xml", ".rels"])
    if not p14a_no_xml_zip_browser:
        findings.append(Finding("FAIL", "NO_XML_ZIP_BROWSER_MUTATION",
                                "HwpxUploadPageScripts.java",
                                "P14A: XML/ZIP direct access in command dispatch area"))

    existing_keys = ["schemaVersion", "engineVersion", "requestId", "inputFileName", "paragraphs"]
    p14a_existing_keys_ok = all(k in parse_resp_text for k in existing_keys)
    if not p14a_existing_keys_ok:
        missing_k = [k for k in existing_keys if k not in parse_resp_text]
        findings.append(Finding("FAIL", "EXISTING_RESPONSE_KEYS_PRESERVED",
                                "DocumentParseResponse.java",
                                f"P14A: existing response keys missing: {missing_k}"))

    p14a_readiness = (
        p14a_artifact_in_parse_resp and p14a_non_empty_id and
        p14a_no_raw_path_leak and p14a_command_uses_server_id and
        p14a_session_not_source and p14a_unknown_id_rejected and
        p14a_dry_run_still and p14a_no_xml_zip_browser and p14a_existing_keys_ok
    )

    # ── P14B-1 gates ──────────────────────────────────────────────────────────
    handler_text3 = read(HTTP_DIR / "HwpxEditorApiHandler.java")
    gate_text3 = read(GATE_DIR / "HwpxEditorValidationGate.java")
    op_rules_text3 = read(ARCH_DIR / "hwpx_editor_operating_rules_20260515.md")
    parse_handler_text = read(HTTP_DIR / "ParseHwpxHandler.java")
    upload_usecase_text = read(USECASE_DIR / "HwpxUploadParseUseCase.java")

    # VALIDATE_DOCUMENT_REQUIRES_SERVER_ARTIFACT_ID
    # Gate no longer has validateDocument exception; handler has uniform check
    p14b1_validate_doc_requires_id = (
        '"validateDocument"' not in gate_text3 or
        "validateDocument" not in gate_text3.split("MISSING_ARTIFACT_ID")[0]
    ) and "validateDocument" not in handler_text3.split("MISSING_ARTIFACT_ID")[0]
    # Simpler: check that validateDocument exception was removed
    p14b1_validate_doc_requires_id = (
        'requiresArtifact = !"validateDocument"' not in handler_text3 and
        'if (!"validateDocument".equals(type))' not in gate_text3
    )
    if not p14b1_validate_doc_requires_id:
        findings.append(Finding("FAIL", "VALIDATE_DOCUMENT_REQUIRES_SERVER_ARTIFACT_ID",
                                "HwpxEditorApiHandler.java",
                                "P14B-1: validateDocument exception for artifactId still present"))

    # VALIDATE_DOCUMENT_REJECTS_UNKNOWN_ARTIFACT_ID
    p14b1_validate_doc_rejects_unknown = "UNKNOWN_ARTIFACT_ID" in handler_text3
    if not p14b1_validate_doc_rejects_unknown:
        findings.append(Finding("FAIL", "VALIDATE_DOCUMENT_REJECTS_UNKNOWN_ARTIFACT_ID",
                                "HwpxEditorApiHandler.java",
                                "P14B-1: UNKNOWN_ARTIFACT_ID rejection not found in handler"))

    # SESSION_ARTIFACT_ID_NOT_ACCEPTED_AS_ARTIFACT_ID
    p14b1_session_not_accepted = "sessionArtifactId" not in handler_text3 or (
        "correlation" in op_rules_text3.lower() or "correlation" in handler_text3.lower()
    )
    # Also check UI doesn't send sessionArtifactId as artifactId
    scripts_text3 = read(HTTP_DIR / "HwpxUploadPageScripts.java")
    p14b1_session_not_accepted = "artifactId: state.sessionArtifactId" not in scripts_text3
    if not p14b1_session_not_accepted:
        findings.append(Finding("FAIL", "SESSION_ARTIFACT_ID_NOT_ACCEPTED_AS_ARTIFACT_ID",
                                "HwpxUploadPageScripts.java",
                                "P14B-1: UI still sends sessionArtifactId as artifactId"))

    # COMMAND_RESPONSE_ECHOES_ARTIFACT_ID
    p14b1_response_echoes_id = (
        'resp.addProperty("artifactId", command.artifactId)' in handler_text3 or
        'resp.addProperty("artifactId"' in handler_text3
    )
    if not p14b1_response_echoes_id:
        findings.append(Finding("FAIL", "COMMAND_RESPONSE_ECHOES_ARTIFACT_ID",
                                "HwpxEditorApiHandler.java",
                                "P14B-1: command response does not echo artifactId from request"))

    # COMMAND_RESPONSE_NO_RAW_PATH_LEAK
    # Already checked in p14a_no_raw_path_leak; verify still holds
    p14b1_no_raw_path_leak = p14a_no_raw_path_leak
    if not p14b1_no_raw_path_leak:
        findings.append(Finding("FAIL", "COMMAND_RESPONSE_NO_RAW_PATH_LEAK",
                                "HwpxProxyHandler.java",
                                "P14B-1: raw path leak detected in proxy handler"))

    # PARSE_HWPX_ARTIFACT_POLICY_DOCUMENTED
    p14b1_parse_hwpx_policy_doc = (
        "ParseHwpxHandler" in op_rules_text3 or
        "parse-hwpx" in op_rules_text3 or
        "RULE-20" in op_rules_text3
    )
    if not p14b1_parse_hwpx_policy_doc:
        findings.append(Finding("FAIL", "PARSE_HWPX_ARTIFACT_POLICY_DOCUMENTED",
                                "hwpx_editor_operating_rules_20260515.md",
                                "P14B-1: /parse-hwpx artifact policy not documented in operating rules"))

    # IN_MEMORY_REGISTRY_LIMITATION_DOCUMENTED
    p14b1_inmemory_doc = (
        "in-memory" in op_rules_text3.lower() or
        "ConcurrentHashMap" in op_rules_text3 or
        "RULE-21" in op_rules_text3
    )
    if not p14b1_inmemory_doc:
        findings.append(Finding("FAIL", "IN_MEMORY_REGISTRY_LIMITATION_DOCUMENTED",
                                "hwpx_editor_operating_rules_20260515.md",
                                "P14B-1: ArtifactRegistry in-memory limitation not documented"))

    # PERSISTENT_REGISTRY_NOT_IMPLEMENTED_IN_P14B1
    artifact_registry_text = read(ARTIFACT_DIR / "ArtifactRegistry.java")
    p14b1_no_persistent = (
        "javax.persistence" not in artifact_registry_text and
        "java.sql" not in artifact_registry_text and
        "JdbcTemplate" not in artifact_registry_text and
        "EntityManager" not in artifact_registry_text
    )
    if not p14b1_no_persistent:
        findings.append(Finding("FAIL", "PERSISTENT_REGISTRY_NOT_IMPLEMENTED_IN_P14B1",
                                "ArtifactRegistry.java",
                                "P14B-1: persistent storage found in ArtifactRegistry (forbidden in P14B-1)"))

    # DRY_RUN_ONLY_STILL_ENFORCED
    p14b1_dry_run_only = p14a_dry_run_still
    if not p14b1_dry_run_only:
        findings.append(Finding("FAIL", "DRY_RUN_ONLY_STILL_ENFORCED",
                                "HwpxUploadPageScripts.java",
                                "P14B-1: dryRun=false found in UI command dispatch"))

    # NO_APPLY_ENGINE_CONNECTION_IN_P14B1
    usecase_text3 = read(USECASE_DIR / "HwpxEditorCommandUseCase.java")
    p14b1_no_apply_engine = "ApplyEngine" not in handler_text3 or (
        "ApplyEngine" in usecase_text3  # defined in usecase but not wired in handler
        and "ApplyEngine" not in handler_text3
    )
    p14b1_no_apply_engine = "ApplyEngine" not in handler_text3
    if not p14b1_no_apply_engine:
        findings.append(Finding("FAIL", "NO_APPLY_ENGINE_CONNECTION_IN_P14B1",
                                "HwpxEditorApiHandler.java",
                                "P14B-1: ApplyEngine wired in handler (forbidden in P14B-1)"))

    # NO_PYTHON_SCRIPT_BRIDGE_CONNECTION_IN_P14B1 (in command dispatch path only)
    p14b1_no_python_bridge = p14a_no_python_bridge_in_dispatch
    if not p14b1_no_python_bridge:
        findings.append(Finding("FAIL", "NO_PYTHON_SCRIPT_BRIDGE_CONNECTION_IN_P14B1",
                                "HwpxEditorCommandUseCase.java",
                                "P14B-1: PythonScriptBridge found in command usecase"))

    # EXISTING_P14A_GATES_STILL_PASS (summary check)
    p14b1_p14a_still_pass = p14a_readiness
    if not p14b1_p14a_still_pass:
        findings.append(Finding("WARN", "EXISTING_P14A_GATES_STILL_PASS",
                                "audit_hwpx_editor_architecture_gate.py",
                                "P14B-1: some P14A gates are no longer passing"))

    p14b1_readiness = (
        p14b1_validate_doc_requires_id and
        p14b1_validate_doc_rejects_unknown and
        p14b1_session_not_accepted and
        p14b1_response_echoes_id and
        p14b1_no_raw_path_leak and
        p14b1_parse_hwpx_policy_doc and
        p14b1_inmemory_doc and
        p14b1_no_persistent and
        p14b1_dry_run_only and
        p14b1_no_apply_engine and
        p14b1_no_python_bridge
    )

    # P13 readiness
    p13_readiness = (
        rule01_build_cmd and rule01_dispatch_cmd and
        rule05_uses_usecase and rule06_no_http and
        rule07_no_side_effects and rule09_apply_deferred and
        rule10_editor_endpoint and cmd_model_in_contract
    )

    p13b_readiness = (
        p13b_validate_doc and p13b_replace_text and p13b_update_cell and
        p13b_dry_run_only and p13b_no_xml_zip and p13b_session_required and p13b_dup_guard
    )

    severities = {f.severity for f in findings}
    status = "FAIL" if "FAIL" in severities else ("WARN" if "WARN" in severities else "PASS")

    return {
        "audit": "hwpx_editor_architecture_gate",
        "phase": "P14A",
        "status": status,
        "arch_docs": arch_docs,
        "gate_files": gate_file_status,
        "rules": {
            "rule01_ui_command_dispatch": rule01_build_cmd and rule01_dispatch_cmd,
            "rule02_no_xml_zip_in_command_dispatch": rule02_no_xml_zip,
            "rule03_no_raw_path_in_view": rule03_no_raw_in_view and rule03_no_raw_in_styles_html,
            "rule04_artifact_path_guard": rule04_guarded,
            "rule05_handler_uses_usecase": rule05_uses_usecase and rule05_uses_command,
            "rule06_usecase_no_http_import": rule06_no_http,
            "rule07_gate_no_side_effects": rule07_no_side_effects,
            "rule07_gate_checks_security": rule07_forbidden_keys and rule07_raw_path,
            "rule08_dry_run_default_true": rule08_dry_run_default,
            "rule09_apply_deferred_present": rule09_apply_deferred,
            "rule10_endpoints_stable": rule10_editor_endpoint,
            "rule11_meta_contract_in_handler": rule11_schema_version and rule11_engine_version,
            "rule12_secret_key_check": rule12_secret_check,
            "rule14_gate_and_test_exist": rule14_gate_exists and rule14_test_exists,
            "rule15_scripts_size_ok": rule15_scripts_size_ok,
            "rule16_operating_rules_gated": rule16_gate_ref,
            "cmd_model_boundary_ok": cmd_model_in_contract and cmd_model_no_http,
            "p13b_validate_document_present": p13b_validate_doc,
            "p13b_replace_text_present": p13b_replace_text,
            "p13b_update_table_cell_present": p13b_update_cell,
            "p13b_dry_run_only": p13b_dry_run_only,
            "p13b_no_apply_button_active_path": p13b_no_apply_btn,
            "p13b_no_raw_path_input": p13b_no_raw_input,
            "p13b_no_xml_zip_direct_mutation": p13b_no_xml_zip,
            "p13b_session_required": p13b_session_required,
            "p13b_result_panel_fields": p13b_result_fields,
            "p13b_duplicate_submit_guard": p13b_dup_guard,
            "p14a_artifact_in_parse_response": p14a_artifact_in_parse_resp,
            "p14a_non_empty_artifact_id": p14a_non_empty_id,
            "p14a_no_raw_path_leak": p14a_no_raw_path_leak,
            "p14a_command_uses_server_artifact_id": p14a_command_uses_server_id,
            "p14a_session_id_not_source_of_truth": p14a_session_not_source,
            "p14a_command_blocks_without_artifact_id": p14a_command_blocks_no_id,
            "p14a_unknown_artifact_id_rejected": p14a_unknown_id_rejected,
            "p14a_dry_run_only_enforced": p14a_dry_run_still,
            "p14a_no_apply_engine_connection": p14a_no_apply_engine,
            "p14a_no_python_bridge_in_dispatch": p14a_no_python_bridge_in_dispatch,
            "p14a_no_xml_zip_browser_mutation": p14a_no_xml_zip_browser,
            "p14a_existing_response_keys_preserved": p14a_existing_keys_ok,
        },
        "p13_readiness": p13_readiness,
        "p13b_readiness": p13b_readiness,
        "p14a_readiness": p14a_readiness,
        "p14b1_readiness": p14b1_readiness,
        "finding_count": len(findings),
        "findings": [asdict(f) for f in findings],
        "policy": {
            "no_endpoint_path_change": True,
            "no_api_response_key_change": True,
            "no_browser_xml_zip_direct": True,
            "no_raw_path_in_ui": True,
            "no_actual_apply_in_p13": True,
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
    print(f"hwpx_editor_architecture_gate_status={result['status']}")
    print(f"p13_readiness={result['p13_readiness']}")
    print(f"p14a_readiness={result.get('p14a_readiness', False)}")
    print(f"p14b1_readiness={result.get('p14b1_readiness', False)}")
    print(f"finding_count={result['finding_count']}")
    for item in result["findings"][:25]:
        print(f"  {item['severity']} [{item['file']}] {item['rule']}: {item['detail'][:80]}")
    if args.json_path:
        Path(args.json_path).write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
