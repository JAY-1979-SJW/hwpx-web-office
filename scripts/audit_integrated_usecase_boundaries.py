#!/usr/bin/env python3
"""Read-only integrated usecase boundary audit."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXCLUDE_PARTS = {".git", ".gradle", "build", "deliverables", "reports", "logs", "__pycache__", "node_modules"}
TEXT_SUFFIXES = {".java", ".py", ".md", ".json", ".yml", ".yaml", ".kt", ".kts"}

EXCEL_RE = re.compile(r"(?i)(excel|xlsx|xlsm|workbook|sheet|openpyxl|poi|RawWorkbook|WorkbookParser)")
STATEMENT_RE = re.compile(r"(?i)(statement|estimate|contract|progress|bill|boq|quantity|price|unit|ContractBill|ProgressBill)")
HWPX_RE = re.compile(r"(?i)(hwpx|hwp|hancom|HwpToHwpx|Hwpx)")
MATERIAL_RE = re.compile(r"(?i)(material|item|alias|canonical|normaliz)")
LOCAL_EXEC_RE = re.compile(r"(?i)(ProcessBuilder|Runtime\.getRuntime|subprocess\.|Start-Process|win32com|pywinauto|uiautomation|Excel\.Application)")
DB_WRITE_RE = re.compile(r"(?i)\b(insert|update|delete|drop|truncate|alter\s+table|create\s+table|initSchema|seed\()\b")
DB_EXEC_RE = re.compile(r"(?i)(executeUpdate|PreparedStatement|Statement|Connection|INSERT\s+INTO|UPDATE\s+\w+|DELETE\s+FROM|CREATE\s+TABLE|ALTER\s+TABLE|DROP\s+TABLE|initSchema|seed\()")
PATH_OUTPUT_RE = re.compile(r"(?i)(download|artifact|outputFileName|localPath|sendResponseHeaders|Content-Disposition)")
META_RE = re.compile(r"(?s)(schemaVersion).{0,400}(engineVersion).{0,400}(requestId)|requestId.{0,400}schemaVersion.{0,400}engineVersion")
GATE_RE = re.compile(r"(?i)(FileTypeGate|UploadSecurityGate|ExecutionLocationGate|DbWriteGate|SecretMaskingGate|OutputValidationGate|LOCAL_WORKER_REQUIRED|USER_PRESENT_REQUIRED|gate|guard|approval)")
RESPONSE_RE = re.compile(r"(?i)(response|send\(|toJson|Map<String, Object>)")


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


def is_http(path: Path) -> bool:
    s = path.as_posix()
    return s.startswith("src/main/java/com/haehan/engine/http/") and s.endswith("Handler.java")


def is_statement_or_material_area(path: Path, text: str) -> bool:
    s = path.as_posix()
    return bool(STATEMENT_RE.search(s) or MATERIAL_RE.search(s) or STATEMENT_RE.search(text[:5000]) or MATERIAL_RE.search(text[:5000]))


def is_integrated_runtime_db_area(path: Path) -> bool:
    s = path.as_posix()
    return s.startswith((
        "src/main/java/com/haehan/engine/workbook/",
        "src/main/java/com/haehan/engine/inspection/",
    )) or any(name in s for name in (
        "NormalizeContractBillHandler.java",
        "BuildProgressBillHandler.java",
        "StandardizeContractBillHandler.java",
        "ParseWorkbook",
        "AnalyzeWorkbookStructureHandler.java",
        "Inspection",
    ))


def audit() -> dict:
    files = repo_files()
    findings: list[Finding] = []
    candidates = {
        "upload": [],
        "analyze": [],
        "domain_model": [],
        "generate": [],
        "validate": [],
        "download_response": [],
        "adapter_boundary_needed": [],
    }

    docs_present = (ROOT / "docs/architecture/integrated_usecase_boundary_20260514.md").exists()
    contract_docs_present = (ROOT / "docs/architecture/integrated_contract_policy_20260514.md").exists()

    for path in files:
        text = read(path)
        s = path.as_posix()
        head = text[:12000]
        excel = bool(EXCEL_RE.search(s) or EXCEL_RE.search(head))
        statement = bool(STATEMENT_RE.search(s) or STATEMENT_RE.search(head))
        hwpx = bool(HWPX_RE.search(s) or HWPX_RE.search(head))
        material = bool(MATERIAL_RE.search(s) or MATERIAL_RE.search(head))

        if is_http(path) and re.search(r"(?i)(multipart|upload|filename|parse|analyze|generate|download)", head):
            candidates["upload"].append(s)
        if excel or statement:
            if s.startswith(("src/main/java/com/haehan/engine/workbook", "scripts/excel")):
                candidates["analyze"].append(s)
        if s.startswith("src/main/java/com/haehan/engine/workbook") and "/model/" in s:
            candidates["domain_model"].append(s)
        if s.startswith("src/main/java/com/haehan/engine/contract/"):
            candidates["domain_model"].append(s)
        if s.startswith(("scripts/hwpx", "src/main/java/com/haehan/engine/inspection", "src/main/java/com/haehan/engine/workbook/export", "src/main/java/com/haehan/engine/workbook/standardize")) and re.search(r"(?i)(render|generate|builder|writer|standardiz|compose|template)", s + "\n" + head):
            candidates["generate"].append(s)
        if re.search(r"(?i)(validate|validation|gate|audit|roundtrip|golden)", s + "\n" + head):
            candidates["validate"].append(s)
        if is_http(path) and PATH_OUTPUT_RE.search(head):
            candidates["download_response"].append(s)

        if is_http(path) and (excel and hwpx or statement and hwpx):
            findings.append(Finding("WARN", "api_handler_mixes_analysis_and_generation_terms", s, "API handler has analysis and HWPX/generation signals; extract usecase/adapter boundary before adding behavior"))
        if s.startswith("scripts/excel") and hwpx:
            findings.append(Finding("WARN", "excel_script_references_hwpx", s, "Excel script references HWP/HWPX; route through generation adapter"))
            candidates["adapter_boundary_needed"].append(s)
        if s.startswith("scripts/hwpx") and excel:
            findings.append(Finding("WARN", "hwpx_script_references_excel", s, "HWPX script references Excel; route through analysis adapter"))
            candidates["adapter_boundary_needed"].append(s)
        if is_statement_or_material_area(path, head) and DB_WRITE_RE.search(head):
            direct_runtime_write = (
                is_integrated_runtime_db_area(path)
                and DB_EXEC_RE.search(head)
                and "/inspection/" not in s
                and not s.startswith("src/test/")
            )
            severity = "FAIL" if direct_runtime_write and "DbWriteGate" not in head else "WARN"
            findings.append(Finding(severity, "statement_material_db_write_keyword", s, "Statement/material area contains DB write/schema keyword; require DbWriteGate before runtime integration"))
        if is_http(path) and hwpx and LOCAL_EXEC_RE.search(head) and not GATE_RE.search(head):
            findings.append(Finding("FAIL", "server_local_worker_without_gate", s, "HTTP handler appears to connect HWP/Hancom/local execution without visible execution gate"))
        if is_http(path) and PATH_OUTPUT_RE.search(head) and not re.search(r"(?i)(normalize|startsWith|resolve|Path|Content-Disposition|filename)", head):
            findings.append(Finding("WARN", "download_path_traversal_unclear", s, "Generated artifact/download path defense is unclear"))
        if is_http(path) and RESPONSE_RE.search(head) and not META_RE.search(head):
            findings.append(Finding("WARN", "api_response_meta_contract_candidate", s, "API response meta contract may be incomplete"))

    if not docs_present:
        findings.append(Finding("WARN", "integrated_usecase_flow_not_documented", "docs/architecture/integrated_usecase_boundary_20260514.md", "Integrated usecase boundary document is missing"))
    if not contract_docs_present:
        findings.append(Finding("WARN", "integrated_contract_policy_not_documented", "docs/architecture/integrated_contract_policy_20260514.md", "Integrated contract policy document is missing"))

    severities = {f.severity for f in findings}
    status = "FAIL" if "FAIL" in severities else ("WARN" if "WARN" in severities else "PASS")

    return {
        "audit": "integrated_usecase_boundaries",
        "status": status,
        "files_scanned": len(files),
        "finding_count": len(findings),
        "findings": [asdict(f) for f in findings[:200]],
        "candidate_counts": {key: len(value) for key, value in candidates.items()},
        "sample_paths": {key: value[:40] for key, value in candidates.items()},
        "policy": {
            "standard_flow": "UploadFile -> FileTypeGate -> Parser/Analyzer -> Domain Model -> Validation -> Generation Request -> Document/Report Engine -> Output Artifact -> Download/API Response",
            "db_write": "requires DbWriteGate",
            "hwp_hancom": "local worker required",
            "api_response_meta": ["schemaVersion", "engineVersion", "requestId"],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", dest="json_path")
    args = parser.parse_args()
    result = audit()
    print(f"integrated_usecase_boundary_status={result['status']}")
    print(f"files_scanned={result['files_scanned']}")
    print(f"finding_count={result['finding_count']}")
    for key, value in result["candidate_counts"].items():
        print(f"{key}_candidate_count={value}")
    for item in result["findings"][:20]:
        print(f"{item['severity']} {item['rule']} {item['path']}")
    if args.json_path:
        Path(args.json_path).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
