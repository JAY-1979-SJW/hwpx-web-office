#!/usr/bin/env python3
"""Read-only HWPX document engine boundary audit."""
from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXCLUDE_PARTS = {".git", ".gradle", "build", "deliverables", "reports", "logs", "__pycache__", "node_modules"}
TEXT_SUFFIXES = {".java", ".py", ".ps1", ".md"}

HWPX_RE = re.compile(r"(?i)(hwpx|hwp|hancom)")
EXCEL_RE = re.compile(r"(?i)(excel|xlsx|xlsm|workbook|sheet|openpyxl|FormFieldLocator|TemplateNamedRange)")
LOCAL_GUI_RE = re.compile(r"(?i)(local-gui|pywinauto|win32com|uiautomation|desktop)")
SERVER_EXEC_RE = re.compile(r"(?i)(ProcessBuilder|Runtime\.getRuntime|subprocess\.|Start-Process|os\.system)")
GATE_RE = re.compile(r"(?i)(LOCAL_WORKER_REQUIRED|USER_PRESENT_REQUIRED|local worker|execution location|gate|guard|approval)")
PACKAGE_GATE_RE = re.compile(r"(?i)(ZipFile|ZipInputStream|zipfile|manifest|mimetype|validate|validation|xml_ok|zip_ok)")
TEMPLATE_RE = re.compile(r"(?i)(template|placeholder|render|schedule|safety|compose|builder|generate)")


@dataclass
class Finding:
    severity: str
    rule: str
    path: str
    detail: str


def repo_files(suffixes: set[str] | None = None) -> list[Path]:
    out = subprocess.check_output(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT)
    files: list[Path] = []
    for raw in out.split(b"\0"):
        if not raw:
            continue
        rel = Path(raw.decode("utf-8", errors="replace"))
        if any(part in EXCLUDE_PARTS for part in rel.parts):
            continue
        if suffixes is None:
            if rel.suffix.lower() in TEXT_SUFFIXES:
                files.append(rel)
        elif rel.suffix.lower() in suffixes:
            files.append(rel)
    return files


def read(path: Path) -> str:
    try:
        return (ROOT / path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def py_import_graph(files: list[Path]) -> dict[str, set[str]]:
    module_to_file = {".".join(path.with_suffix("").parts).replace("-", "_"): path.as_posix() for path in files}
    graph = {path.as_posix(): set() for path in files}
    for path in files:
        try:
            tree = ast.parse(read(path))
        except SyntaxError:
            continue
        src = path.as_posix()
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                for mod, target in module_to_file.items():
                    if mod == name or mod.endswith("." + name):
                        if target != src:
                            graph[src].add(target)
    return graph


def strongly_connected(graph: dict[str, set[str]]) -> list[list[str]]:
    index = 0
    stack: list[str] = []
    indices: dict[str, int] = {}
    low: dict[str, int] = {}
    on_stack: set[str] = set()
    comps: list[list[str]] = []

    def visit(node: str) -> None:
        nonlocal index
        indices[node] = index
        low[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)
        for target in graph.get(node, set()):
            if target not in indices:
                visit(target)
                low[node] = min(low[node], low[target])
            elif target in on_stack:
                low[node] = min(low[node], indices[target])
        if low[node] == indices[node]:
            comp: list[str] = []
            while True:
                item = stack.pop()
                on_stack.remove(item)
                comp.append(item)
                if item == node:
                    break
            if len(comp) > 1:
                comps.append(sorted(comp))

    for node in graph:
        if node not in indices:
            visit(node)
    return comps


def audit() -> dict:
    findings: list[Finding] = []
    files = repo_files()
    hwpx_files = [p for p in files if p.as_posix().startswith("scripts/hwpx") or HWPX_RE.search(p.as_posix())]

    py_hwpx_files = [p for p in repo_files({".py"}) if p.as_posix().startswith("scripts/hwpx")]
    graph = py_import_graph(py_hwpx_files)
    cycles = strongly_connected(graph)
    if cycles:
        findings.append(Finding("WARN", "hwpx_import_cycles", "scripts/hwpx", f"{len(cycles)} cycle(s) detected"))

    fixture_tests = [p.as_posix() for p in files if p.as_posix().startswith("scripts/hwpx/test_") or "roundtrip" in p.as_posix().lower() or "golden" in p.as_posix().lower()]
    if not fixture_tests:
        findings.append(Finding("WARN", "missing_hwpx_fixture_tests", "scripts/hwpx", "no HWPX fixture/golden/roundtrip test signal found"))

    for path in files:
        text = read(path)
        s = path.as_posix()
        if s.startswith("scripts/hwpx") and EXCEL_RE.search(text):
            findings.append(Finding("WARN", "hwpx_references_excel", s, "HWPX script references Excel/XLSX terms; keep adapter boundary explicit"))
        if s.startswith("scripts/hwpx") and LOCAL_GUI_RE.search(text):
            findings.append(Finding("WARN", "hwpx_references_local_gui", s, "HWPX script references local GUI/desktop automation; local worker boundary required"))
        if s.startswith("src/main/java") and "/http/" in s and HWPX_RE.search(text) and TEMPLATE_RE.search(text):
            findings.append(Finding("WARN", "api_handler_template_generation_signal", s, "API handler contains HWPX template/generation keywords"))
        is_java_hwp_adapter = s.startswith("src/main/java/com/haehan/engine/hwp/")
        is_java_http_handler = s.startswith("src/main/java") and "/http/" in s
        if is_java_hwp_adapter and SERVER_EXEC_RE.search(text):
            findings.append(Finding("WARN", "local_worker_adapter_process_execution", s, "HWP/Hancom bridge process execution must stay behind local worker execution gates"))
        if is_java_http_handler and HWPX_RE.search(text) and SERVER_EXEC_RE.search(text) and not GATE_RE.search(text):
            findings.append(Finding("FAIL", "server_hwp_execution_without_gate", s, "server runtime contains HWP/Hancom process execution without visible gate"))
        if s.startswith("src/main/java") and "/http/" in s and HWPX_RE.search(text) and "upload" in text.lower() and not PACKAGE_GATE_RE.search(text):
            findings.append(Finding("WARN", "hwpx_upload_package_gate_signal_missing", s, "HWPX upload handler lacks visible package validation signal"))

    severities = {f.severity for f in findings}
    status = "FAIL" if "FAIL" in severities else ("WARN" if "WARN" in severities else "PASS")
    return {
        "audit": "hwpx_engine_boundaries",
        "status": status,
        "files_scanned": len(files),
        "hwpx_file_count": len(hwpx_files),
        "cycle_count": len(cycles),
        "cycles": cycles[:20],
        "fixture_test_signal_count": len(fixture_tests),
        "finding_count": len(findings),
        "findings": [asdict(f) for f in findings[:200]],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", dest="json_path")
    args = parser.parse_args()
    result = audit()
    print(f"hwpx_engine_boundary_status={result['status']}")
    print(f"files_scanned={result['files_scanned']}")
    print(f"hwpx_file_count={result['hwpx_file_count']}")
    print(f"cycle_count={result['cycle_count']}")
    print(f"fixture_test_signal_count={result['fixture_test_signal_count']}")
    print(f"finding_count={result['finding_count']}")
    for item in result["findings"][:20]:
        print(f"{item['severity']} {item['rule']} {item['path']}")
    if args.json_path:
        Path(args.json_path).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
