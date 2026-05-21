#!/usr/bin/env python3
"""Read-only P10B audit: module structure and new code rule compliance."""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
JAVA_SRC = ROOT / "src" / "main" / "java" / "com" / "haehan" / "engine"
JAVA_TEST = ROOT / "src" / "test" / "java" / "com" / "haehan" / "engine"

# Packages that must NOT import com.haehan.engine.http.*
NO_ENGINE_HTTP_IMPORT = ["usecase", "gate", "parser", "workbook", "inspection", "clients", "approval", "ops", "contract"]

# Gate-specific: must not contain side-effect patterns
GATE_SIDE_EFFECT_PATTERNS = [
    r"Files\.(write|copy|move|createDir)",
    r"new ProcessBuilder",
    r"Runtime\.getRuntime\(\)",
    r"Files\.createFile",
]

# Packages that must not appear in usecase imports
USECASE_FORBIDDEN_IMPORTS = [
    "com.haehan.engine.http",
    "com.sun.net.httpserver",
    "com.haehan.engine.hwp",
    "com.haehan.engine.inspection",
]

# Raw path patterns that should not appear directly in response header set() calls
RAW_PATH_RESPONSE_PATTERNS = [
    r'getResponseHeaders\(\)\.set\(.*\.toString\(\)\s*\)',
    r'getResponseHeaders\(\)\.set\(.*getAbsolutePath\(\)\s*\)',
]

# Policy docs
POLICY_FILES = [
    "docs/architecture/module_structure_rules_20260515.md",
    "docs/architecture/new_code_authoring_rules_20260515.md",
    "docs/architecture/module_rule_registry_20260515.json",
    "docs/architecture/code_templates_20260515.md",
    "docs/architecture/audit_gate_matrix_20260515.md",
]


@dataclass
class Finding:
    severity: str
    rule: str
    file: str
    detail: str


def java_files(pkg: str) -> list[Path]:
    d = JAVA_SRC / pkg
    if not d.exists():
        return []
    return list(d.rglob("*.java"))


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""


def audit_no_engine_http_import(pkg: str, findings: list[Finding]) -> dict:
    files = java_files(pkg)
    violations: list[str] = []
    for f in files:
        text = read(f)
        if "import com.haehan.engine.http." in text:
            violations.append(f.name)
            findings.append(Finding(
                "FAIL", "forbidden_engine_http_import", f"{pkg}/{f.name}",
                f"{f.name} imports com.haehan.engine.http (forbidden in {pkg})"
            ))
    return {"package": pkg, "files_checked": len(files), "violations": violations}


def audit_gate_no_side_effects(findings: list[Finding]) -> dict:
    files = java_files("gate")
    violations: list[str] = []
    for f in files:
        if f.name == "GateResult.java":
            continue
        text = read(f)
        for pattern in GATE_SIDE_EFFECT_PATTERNS:
            if re.search(pattern, text):
                violations.append(f"{f.name}: {pattern}")
                findings.append(Finding(
                    "FAIL", "gate_side_effect", f"gate/{f.name}",
                    f"Gate has side effect pattern: {pattern}"
                ))
    return {"files_checked": len(files), "violations": violations}


def audit_usecase_forbidden_imports(findings: list[Finding]) -> dict:
    files = java_files("usecase")
    violations: list[str] = []
    for f in files:
        text = read(f)
        for forbidden in USECASE_FORBIDDEN_IMPORTS:
            if f"import {forbidden}" in text:
                violations.append(f"{f.name}: {forbidden}")
                findings.append(Finding(
                    "FAIL", "usecase_forbidden_import", f"usecase/{f.name}",
                    f"{f.name} imports forbidden package: {forbidden}"
                ))
    return {"files_checked": len(files), "violations": violations}


def audit_raw_path_in_response(findings: list[Finding]) -> dict:
    """Checks for raw path directly in response header set() calls (not in guarded ternary)."""
    handler_dir = JAVA_SRC / "http"
    violations: list[str] = []
    if not handler_dir.exists():
        return {"files_checked": 0, "violations": []}
    files = list(handler_dir.glob("*.java"))
    for f in files:
        text = read(f)
        # Skip files that use isRawPathGuarded (properly guarded)
        if "isRawPathGuarded()" in text or "guardedReportRef" in text or "guardedArtifactRef" in text:
            continue
        for pattern in RAW_PATH_RESPONSE_PATTERNS:
            if re.search(pattern, text):
                violations.append(f"{f.name}: {pattern}")
                findings.append(Finding(
                    "WARN", "raw_path_in_response_header", f"http/{f.name}",
                    f"Possible raw path in response header: {pattern}"
                ))
    return {"files_checked": len(files), "violations": violations}


def audit_policy_docs(findings: list[Finding]) -> dict:
    present: list[str] = []
    missing: list[str] = []
    for path_str in POLICY_FILES:
        p = ROOT / path_str
        if p.exists():
            present.append(path_str)
        else:
            missing.append(path_str)
            findings.append(Finding("FAIL", "policy_doc_missing", path_str, f"Policy document not found: {path_str}"))
    return {"present": present, "missing": missing}


def audit_contract_no_engine_imports(findings: list[Finding]) -> dict:
    files = java_files("contract")
    violations: list[str] = []
    for f in files:
        text = read(f)
        # contract must not import workbook, inspection, parser, usecase, gate, http
        for forbidden_pkg in ["com.haehan.engine.workbook", "com.haehan.engine.inspection",
                               "com.haehan.engine.parser", "com.haehan.engine.usecase",
                               "com.haehan.engine.http"]:
            if f"import {forbidden_pkg}" in text:
                violations.append(f"{f.name}: {forbidden_pkg}")
                findings.append(Finding(
                    "FAIL", "contract_forbidden_import", f"contract/{f.name}",
                    f"contract/{f.name} imports engine package: {forbidden_pkg}"
                ))
    return {"files_checked": len(files), "violations": violations}


    # Handlers written before P10B — grandfathered, gate/usecase rule applies to NEW handlers only
GRANDFATHERED_HANDLERS = {
    "AnalyzeWorkbookStructureHandler.java", "BuildProgressBillHandler.java",
    "HealthHandler.java", "HwpxProxyHandler.java", "HwpxUploadHandler.java",
    "InspectionGenerateHandler.java", "InspectionSettingsHandler.java",
    "InspectionWorksHandler.java", "InternalHandler.java", "LoggingHandler.java",
    "NormalizeContractBillHandler.java", "ParseWorkbookAggregateHandler.java",
    "ParseWorkbookHandler.java", "ParseWorkbookRawHandler.java",
    "ParseWorkbookSemanticHandler.java", "RenderProgressBillTestHandler.java",
    "StandardizeContractBillHandler.java", "ConvertHwpToHwpxHandler.java",
    "InspectionPageHandler.java",
    "ConvertExcelHandler.java",  # 엑셀 변환 출입구 — CostToProgressConverter 직접 호출
    "HwpxDownloadHandler.java",  # 다운로드 전용 핸들러
}

# P9B+ handlers that DO use gate/usecase (compliant)
COMPLIANT_HANDLERS = {
    "HwpxEditorApiHandler.java", "ParseHwpxHandler.java",
}


def audit_handler_gate_exists(findings: list[Finding]) -> dict:
    """New handlers (post P10B) must reference at least one gate or usecase."""
    handler_dir = JAVA_SRC / "http"
    if not handler_dir.exists():
        return {"skipped": True}
    compliant: list[str] = []
    grandfathered: list[str] = []
    violations: list[str] = []
    for f in handler_dir.glob("*Handler.java"):
        text = read(f)
        has_gate = "Gate." in text or "GateResult" in text
        has_usecase = "UseCase." in text or "UseCase.execute" in text or "UseCase.prepare" in text
        if f.name in GRANDFATHERED_HANDLERS:
            grandfathered.append(f.name)
        elif has_gate or has_usecase:
            compliant.append(f.name)
        elif "HttpExchange" in text:
            # New handler (not in grandfathered list) missing gate/usecase
            violations.append(f.name)
            findings.append(Finding(
                "FAIL", "new_handler_no_gate_or_usecase", f"http/{f.name}",
                f"New handler {f.name} has no gate or usecase reference (P10B rule)"
            ))
    return {"compliant": compliant, "grandfathered": grandfathered, "violations": violations}


def audit() -> dict:
    findings: list[Finding] = []

    # 1. No com.haehan.engine.http import in lower layers
    import_results: dict = {}
    for pkg in NO_ENGINE_HTTP_IMPORT:
        import_results[pkg] = audit_no_engine_http_import(pkg, findings)

    # 2. Gate side effects
    gate_side_effects = audit_gate_no_side_effects(findings)

    # 3. UseCase forbidden imports
    usecase_imports = audit_usecase_forbidden_imports(findings)

    # 4. Contract engine imports
    contract_imports = audit_contract_no_engine_imports(findings)

    # 5. Raw path in response
    raw_path = audit_raw_path_in_response(findings)

    # 6. Policy docs
    policy_docs = audit_policy_docs(findings)

    # 7. Handler gate/usecase check
    handler_gate = audit_handler_gate_exists(findings)

    severities = {f.severity for f in findings}
    status = "FAIL" if "FAIL" in severities else ("WARN" if "WARN" in severities else "PASS")

    return {
        "audit": "new_code_structure_rules",
        "phase": "P10B",
        "status": status,
        "layer_import_violations": import_results,
        "gate_side_effect_check": gate_side_effects,
        "usecase_import_check": usecase_imports,
        "contract_import_check": contract_imports,
        "raw_path_response_check": raw_path,
        "policy_docs_check": policy_docs,
        "handler_gate_usecase_check": handler_gate,
        "finding_count": len(findings),
        "findings": [asdict(f) for f in findings],
        "policy": {
            "no_engine_http_import_in_lower_layers": True,
            "gate_no_side_effects": True,
            "usecase_no_http_import": True,
            "contract_no_engine_imports": True,
            "raw_path_headers_forbidden": True,
            "policy_docs_required": True,
            "push_forbidden": True,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", dest="json_path")
    args = parser.parse_args()
    result = audit()
    print(f"new_code_structure_rules_status={result['status']}")
    print(f"finding_count={result['finding_count']}")
    for item in result["findings"][:30]:
        print(f"  {item['severity']} [{item['file']}] {item['rule']}: {item['detail'][:80]}")
    if args.json_path:
        Path(args.json_path).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
