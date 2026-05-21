#!/usr/bin/env python3
"""Read-only multi-domain layer boundary audit."""
from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
from dataclasses import dataclass, asdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXCLUDE_PARTS = {".git", ".gradle", "build", "deliverables", "reports", "logs", "__pycache__", "node_modules"}
TEXT_SUFFIXES = {".java", ".py", ".kt", ".kts", ".js", ".ts"}


@dataclass
class Finding:
    severity: str
    rule: str
    path: str
    detail: str


def repo_files() -> list[Path]:
    out = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
    )
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


def read_text(path: Path) -> str:
    try:
        return (ROOT / path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def classify_layer(path: Path) -> str:
    s = path.as_posix().lower()
    if s.startswith("src/main/java") and "/http/" in s:
        return "interface"
    if s.startswith("scripts/local-gui"):
        return "interface_local_gui"
    if s.startswith("src/test") or s.startswith("tests") or "/test_" in s or s.endswith("test.java"):
        return "test_quality"
    if s.startswith("scripts/ops") or s.startswith("scripts/hooks"):
        return "ops_quality"
    if s.startswith("scripts/hwp-worker"):
        return "adapter_local_worker"
    if s.startswith("scripts/hwpx") or s.startswith("scripts/excel"):
        return "engine"
    if s.startswith("src/main/java") and ("/parser/" in s or "/inspection/" in s or "/hwp/" in s):
        return "engine"
    if s.startswith("src/main/java") and "/contract/" in s:
        return "domain_core"
    if s.startswith("src/main/java"):
        return "application"
    if s.startswith("scripts"):
        return "adapter_or_script"
    return "other"


def extract_imports(path: Path, text: str) -> list[str]:
    if path.suffix == ".java":
        return re.findall(r"^\s*import\s+([A-Za-z0-9_.*]+)\s*;", text, flags=re.MULTILINE)
    if path.suffix == ".py":
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return []
        names: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                names.append(node.module)
        return names
    return re.findall(r"\b(?:import|require)\s*(?:\(?[\"'])([^\"']+)", text)


def import_target_layer(name: str) -> str | None:
    lowered = name.lower()
    if "com.haehan.engine.http" in lowered:
        return "interface"
    if ".test" in lowered or lowered.endswith("test"):
        return "test_quality"
    if "scripts.local-gui" in lowered or "local_gui" in lowered:
        return "interface_local_gui"
    if "com.haehan.engine.contract" in lowered:
        return "domain_core"
    if "com.haehan.engine.parser" in lowered or "com.haehan.engine.inspection" in lowered:
        return "engine"
    return None


def audit() -> dict:
    findings: list[Finding] = []
    files = repo_files()
    for path in files:
        layer = classify_layer(path)
        text = read_text(path)
        imports = extract_imports(path, text)
        imported_layers = {target for name in imports if (target := import_target_layer(name))}

        if layer == "domain_core" and {"interface", "interface_local_gui"} & imported_layers:
            findings.append(Finding("FAIL", "domain_must_not_import_interface", path.as_posix(), "domain/core imports interface layer"))
        if layer == "engine" and {"interface", "interface_local_gui"} & imported_layers:
            findings.append(Finding("WARN", "engine_should_not_import_interface", path.as_posix(), "engine imports interface/local GUI layer"))
        if layer.startswith("application") and "test_quality" in imported_layers:
            findings.append(Finding("FAIL", "runtime_must_not_import_tests", path.as_posix(), "runtime imports test-only code"))
        if path.as_posix().startswith("src/main/java") and re.search(r"(?i)(hancom|hwp|desktop|local-gui)", text):
            if re.search(r"(?i)(ProcessBuilder|Runtime\.getRuntime|Desktop\.getDesktop)", text):
                findings.append(Finding("WARN", "server_runtime_local_execution_keyword", path.as_posix(), "server runtime contains local execution keyword"))
        if layer == "engine" and "scripts/local-gui" in text:
            findings.append(Finding("WARN", "engine_references_local_gui_path", path.as_posix(), "engine references local GUI path"))

    severities = {f.severity for f in findings}
    status = "FAIL" if "FAIL" in severities else ("WARN" if "WARN" in severities else "PASS")
    return {
        "audit": "layer_boundaries",
        "status": status,
        "files_scanned": len(files),
        "finding_count": len(findings),
        "findings": [asdict(f) for f in findings[:200]],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", dest="json_path")
    args = parser.parse_args()
    result = audit()
    print(f"layer_boundary_status={result['status']}")
    print(f"files_scanned={result['files_scanned']}")
    print(f"finding_count={result['finding_count']}")
    for item in result["findings"][:20]:
        print(f"{item['severity']} {item['rule']} {item['path']}")
    if args.json_path:
        Path(args.json_path).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
