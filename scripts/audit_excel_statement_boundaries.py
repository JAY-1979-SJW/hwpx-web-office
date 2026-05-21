#!/usr/bin/env python3
"""Read-only Excel/XLSX and statement engine boundary audit."""
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

EXCEL_RE = re.compile(r"(?i)(excel|xlsx|xlsm|workbook|sheet|namedrange|named_range|formfieldlocator|templatenamedrange|inspection)")
STATEMENT_RE = re.compile(r"(?i)(statement|boq|estimate|contract|progress|progressbill|bill|quantity|price|unit|내역|기성|계약)")
MATERIAL_RE = re.compile(r"(?i)(material|item|alias|canonical|normaliz|품목|자재)")
OPENPYXL_RE = re.compile(r"(?i)\bopenpyxl\b")
DB_WRITE_RE = re.compile(r"(?i)\b(insert|update|delete|drop|truncate|alter\s+table|create\s+table)\b")
LOCAL_EXCEL_RE = re.compile(r"(?i)(win32com|pywin32|comtypes|excel\.application|xlwings|desktop excel|local excel)")
SERVER_RUNTIME_RE = re.compile(r"src/main/java/.+")
HW_SIGNALS_RE = re.compile(r"(?i)(hwpx|hwp|hancom)")


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


def is_excel_area(path: Path, text: str) -> bool:
    s = path.as_posix()
    return (
        s.startswith("src/main/java/com/haehan/engine/inspection")
        or s.startswith("scripts/excel")
        or bool(EXCEL_RE.search(s))
        or bool(EXCEL_RE.search(text[:4000]))
    )


def is_statement_area(path: Path, text: str) -> bool:
    s = path.as_posix()
    return bool(STATEMENT_RE.search(s)) or bool(STATEMENT_RE.search(text[:4000]))


def is_runtime(path: Path) -> bool:
    return bool(SERVER_RUNTIME_RE.match(path.as_posix()))


def audit() -> dict:
    findings: list[Finding] = []
    files = repo_files()
    excel_files: list[str] = []
    statement_files: list[str] = []
    material_files: list[str] = []

    for path in files:
        text = read(path)
        s = path.as_posix()
        excel = is_excel_area(path, text)
        statement = is_statement_area(path, text)
        material = bool(MATERIAL_RE.search(s)) or bool(MATERIAL_RE.search(text[:4000]))

        if excel:
            excel_files.append(s)
        if statement:
            statement_files.append(s)
        if material:
            material_files.append(s)

        if excel and statement and s.startswith("scripts/excel") and "analyze_statement" not in s.lower():
            findings.append(Finding("WARN", "excel_script_mixes_statement_terms", s, "Excel utility appears to contain statement/business terms"))
        if excel and MATERIAL_RE.search(text) and s.startswith("src/main/java/com/haehan/engine/inspection"):
            findings.append(Finding("WARN", "excel_runtime_contains_material_terms", s, "Excel inspection runtime contains material normalization terms"))
        if statement and LOCAL_EXCEL_RE.search(text) and is_runtime(path):
            findings.append(Finding("FAIL", "server_statement_uses_desktop_excel", s, "server runtime statement path references desktop Excel automation"))
        if is_runtime(path) and OPENPYXL_RE.search(text):
            findings.append(Finding("FAIL", "server_runtime_openpyxl", s, "server runtime references openpyxl"))
        elif OPENPYXL_RE.search(text) and s.startswith("scripts/excel"):
            findings.append(Finding("WARN", "python_excel_openpyxl_present", s, "Python Excel script references openpyxl; keep offline/local only"))
        if (excel or statement) and DB_WRITE_RE.search(text) and s.startswith(("scripts/excel", "src/main/java")):
            findings.append(Finding("WARN", "excel_statement_db_write_keyword", s, "Excel/statement area contains DB write/schema keyword; verify read-only boundary"))
        if excel and s.startswith("scripts/excel") and HW_SIGNALS_RE.search(text):
            findings.append(Finding("WARN", "excel_script_references_hwp_hwpx", s, "Excel script references HWP/HWPX; boundary review needed"))

    severities = {f.severity for f in findings}
    status = "FAIL" if "FAIL" in severities else ("WARN" if "WARN" in severities else "PASS")
    return {
        "audit": "excel_statement_boundaries",
        "status": status,
        "files_scanned": len(files),
        "excel_file_count": len(excel_files),
        "statement_file_count": len(statement_files),
        "material_file_count": len(material_files),
        "finding_count": len(findings),
        "findings": [asdict(f) for f in findings[:200]],
        "policy": {
            "primary_runtime_excel_parser": "Java Apache POI",
            "openpyxl_real_parsing_reintroduction": "forbidden_in_P2",
            "desktop_excel_automation": "local_worker_only",
            "db_write": "forbidden_without_approval_gate",
        },
        "sample_paths": {
            "excel": excel_files[:30],
            "statement": statement_files[:30],
            "material": material_files[:30],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", dest="json_path")
    args = parser.parse_args()
    result = audit()
    print(f"excel_statement_boundary_status={result['status']}")
    print(f"files_scanned={result['files_scanned']}")
    print(f"excel_file_count={result['excel_file_count']}")
    print(f"statement_file_count={result['statement_file_count']}")
    print(f"material_file_count={result['material_file_count']}")
    print(f"finding_count={result['finding_count']}")
    for item in result["findings"][:20]:
        print(f"{item['severity']} {item['rule']} {item['path']}")
    if args.json_path:
        Path(args.json_path).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
