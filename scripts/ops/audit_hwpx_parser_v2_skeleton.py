"""HWPX-PARSER-V2-SKELETON-01 감사 스크립트.

18개 항목을 검사하여 PASS/FAIL을 출력한다.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PARSER_PKG = PROJECT_ROOT / "scripts" / "hwpx" / "parser"
WRITER_FILES = [
    PROJECT_ROOT / "scripts" / "hwpx" / "hwpx_edit_tool.py",
]

results: list[tuple[str, str, str]] = []  # (id, description, status)


def check(check_id: str, description: str, passed: bool, detail: str = "") -> None:
    status = "PASS" if passed else f"FAIL {detail}".strip()
    results.append((check_id, description, status))


# ── 1-10. 파일 존재 ────────────────────────────────────────────────────────────

files = {
    "C01": ("__init__.py",        PARSER_PKG / "__init__.py"),
    "C02": ("parser_contract.py", PARSER_PKG / "parser_contract.py"),
    "C03": ("package_reader.py",  PARSER_PKG / "package_reader.py"),
    "C04": ("block_parser.py",    PARSER_PKG / "block_parser.py"),
    "C05": ("table_parser.py",    PARSER_PKG / "table_parser.py"),
    "C06": ("style_parser.py",    PARSER_PKG / "style_parser.py"),
    "C07": ("layout_classifier.py", PARSER_PKG / "layout_classifier.py"),
    "C08": ("input_slot_detector.py", PARSER_PKG / "input_slot_detector.py"),
    "C09": ("parser_engine.py",   PARSER_PKG / "parser_engine.py"),
    "C10": ("errors.py",          PARSER_PKG / "errors.py"),
}

for cid, (fname, fpath) in files.items():
    check(cid, f"{fname} 존재", fpath.exists(), f"not found: {fpath}")

# ── C11. parse_hwpx_v2 함수 존재 ──────────────────────────────────────────────

engine_src = (PARSER_PKG / "parser_engine.py").read_text(encoding="utf-8")
check("C11", "parse_hwpx_v2 함수 존재",
      "def parse_hwpx_v2" in engine_src)

# ── C12. schemaVersion v2 존재 ────────────────────────────────────────────────

contract_src = (PARSER_PKG / "parser_contract.py").read_text(encoding="utf-8")
check("C12", 'schemaVersion "v2" 존재',
      'SCHEMA_VERSION = "v2"' in contract_src)

# ── C13. blocks/tables/cells/inputSlotCandidates 필드 존재 ────────────────────

required_fields = ["blocks", "tables", "cells", "inputSlotCandidates"]
missing_fields = [f for f in required_fields if f not in contract_src]
check("C13", "blocks/tables/cells/inputSlotCandidates 필드 존재",
      len(missing_fields) == 0, f"missing: {missing_fields}")

# ── C14. write_package import 없음 ────────────────────────────────────────────

write_pkg_found = []
for py_file in PARSER_PKG.glob("*.py"):
    src = py_file.read_text(encoding="utf-8")
    if re.search(r"\bwrite_package\s*\(", src):
        write_pkg_found.append(py_file.name)
check("C14", "write_package 호출 없음",
      len(write_pkg_found) == 0, f"found in: {write_pkg_found}")

# ── C15. apply_edit_plan import 없음 ──────────────────────────────────────────

aep_found = []
for py_file in PARSER_PKG.glob("*.py"):
    src = py_file.read_text(encoding="utf-8")
    if re.search(r"\bapply_edit_plan\s*\(", src):
        aep_found.append(py_file.name)
check("C15", "apply_edit_plan 호출 없음",
      len(aep_found) == 0, f"found in: {aep_found}")

# ── C16. repair_for_server 사용 없음 ──────────────────────────────────────────

rfs_found = []
for py_file in PARSER_PKG.glob("*.py"):
    src = py_file.read_text(encoding="utf-8")
    if re.search(r"\brepair_for_server\s*\(", src):
        rfs_found.append(py_file.name)
check("C16", "repair_for_server 사용 없음",
      len(rfs_found) == 0, f"found in: {rfs_found}")

# ── C17. 기존 writer/editor 파일 미수정 ──────────────────────────────────────

import subprocess
modified_writers = []
for wf in WRITER_FILES:
    if not wf.exists():
        continue
    r = subprocess.run(
        ["git", "diff", "--name-only", str(wf)],
        capture_output=True, text=True, cwd=str(PROJECT_ROOT)
    )
    if wf.name in r.stdout:
        modified_writers.append(wf.name)
check("C17", "기존 writer/editor 파일 미수정",
      len(modified_writers) == 0, f"modified: {modified_writers}")

# ── C18. tests/test_hwpx_parser_v2_skeleton.py 존재 ─────────────────────────

test_file = PROJECT_ROOT / "tests" / "test_hwpx_parser_v2_skeleton.py"
check("C18", "test_hwpx_parser_v2_skeleton.py 존재", test_file.exists())

# ── 결과 출력 ─────────────────────────────────────────────────────────────────

pass_count = sum(1 for _, _, s in results if s == "PASS")
fail_count = len(results) - pass_count

print(f"\n{'='*60}")
print(f"HWPX-PARSER-V2-SKELETON-01 감사 결과")
print(f"{'='*60}")
for cid, desc, status in results:
    mark = "✓" if status == "PASS" else "✗"
    print(f"  [{mark}] {cid}: {desc}")
    if status != "PASS":
        print(f"        → {status}")

print(f"\n{'='*60}")
print(f"  총 {len(results)}개 검사 | PASS {pass_count} | FAIL {fail_count}")
verdict = "PASS" if fail_count == 0 else "FAIL"
print(f"  최종 판정: {verdict}")
print(f"{'='*60}\n")

sys.exit(0 if fail_count == 0 else 1)
