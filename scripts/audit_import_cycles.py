#!/usr/bin/env python3
"""Read-only Java/Python internal import cycle audit."""
from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXCLUDE_PARTS = {".git", ".gradle", "build", "deliverables", "reports", "logs", "__pycache__", "node_modules"}


def repo_files(suffixes: set[str]) -> list[Path]:
    out = subprocess.check_output(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT)
    files: list[Path] = []
    for raw in out.split(b"\0"):
        if not raw:
            continue
        rel = Path(raw.decode("utf-8", errors="replace"))
        if any(part in EXCLUDE_PARTS for part in rel.parts):
            continue
        if rel.suffix.lower() in suffixes:
            files.append(rel)
    return files


def read(path: Path) -> str:
    try:
        return (ROOT / path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def java_graph(files: list[Path]) -> dict[str, set[str]]:
    class_to_file: dict[str, str] = {}
    packages: dict[str, str] = {}
    for path in files:
        text = read(path)
        pkg = re.search(r"^\s*package\s+([A-Za-z0-9_.]+)\s*;", text, re.MULTILINE)
        if not pkg:
            continue
        package = pkg.group(1)
        fqcn = package + "." + path.stem
        class_to_file[fqcn] = path.as_posix()
        packages[path.as_posix()] = package

    graph = {path.as_posix(): set() for path in files}
    for path in files:
        text = read(path)
        src = path.as_posix()
        for imp in re.findall(r"^\s*import\s+([A-Za-z0-9_.*]+)\s*;", text, re.MULTILINE):
            if not imp.startswith("com.haehan.engine."):
                continue
            if imp.endswith(".*"):
                prefix = imp[:-2] + "."
                for fqcn, target in class_to_file.items():
                    if fqcn.startswith(prefix) and target != src:
                        graph[src].add(target)
            elif imp in class_to_file and class_to_file[imp] != src:
                graph[src].add(class_to_file[imp])
    return graph


def python_graph(files: list[Path]) -> dict[str, set[str]]:
    module_to_file: dict[str, str] = {}
    for path in files:
        if path.name == "__init__.py":
            mod = ".".join(path.with_suffix("").parts)
        else:
            mod = ".".join(path.with_suffix("").parts)
        module_to_file[mod.replace("-", "_")] = path.as_posix()

    graph = {path.as_posix(): set() for path in files}
    for path in files:
        text = read(path)
        try:
            tree = ast.parse(text)
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
                candidates = [m for m in module_to_file if m == name or m.endswith("." + name)]
                for mod in candidates[:5]:
                    target = module_to_file[mod]
                    if target != src:
                        graph[src].add(target)
    return graph


def strongly_connected(graph: dict[str, set[str]]) -> list[list[str]]:
    index = 0
    stack: list[str] = []
    indices: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    on_stack: set[str] = set()
    comps: list[list[str]] = []

    def visit(node: str) -> None:
        nonlocal index
        indices[node] = index
        lowlinks[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)
        for target in graph.get(node, set()):
            if target not in indices:
                visit(target)
                lowlinks[node] = min(lowlinks[node], lowlinks[target])
            elif target in on_stack:
                lowlinks[node] = min(lowlinks[node], indices[target])
        if lowlinks[node] == indices[node]:
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
    java_files = repo_files({".java"})
    py_files = repo_files({".py"})
    graph = java_graph(java_files)
    graph.update(python_graph(py_files))
    cycles = strongly_connected(graph)
    status = "WARN" if cycles else "PASS"
    return {
        "audit": "import_cycles",
        "status": status,
        "java_files": len(java_files),
        "python_files": len(py_files),
        "cycle_count": len(cycles),
        "cycles": cycles[:50],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", dest="json_path")
    args = parser.parse_args()
    result = audit()
    print(f"import_cycle_status={result['status']}")
    print(f"java_files={result['java_files']}")
    print(f"python_files={result['python_files']}")
    print(f"cycle_count={result['cycle_count']}")
    for cycle in result["cycles"][:10]:
        print("CYCLE " + " -> ".join(cycle))
    if args.json_path:
        Path(args.json_path).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
