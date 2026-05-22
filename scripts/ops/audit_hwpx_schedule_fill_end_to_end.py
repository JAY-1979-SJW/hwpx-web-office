"""HWPX-SCHEDULE-FILL-END-TO-END-01 감사 스크립트.

11개 항목을 검사한다.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TESTS_DIR = PROJECT_ROOT / "tests"
PIPELINE_DIR = PROJECT_ROOT / "scripts" / "hwpx" / "pipeline"
EDIT_TOOL = PROJECT_ROOT / "scripts" / "hwpx" / "hwpx_edit_tool.py"

results: list[tuple[str, str, str]] = []


def check(cid: str, desc: str, passed: bool, detail: str = "") -> None:
    status = "PASS" if passed else f"FAIL {detail}".strip()
    results.append((cid, desc, status))


test_path = TESTS_DIR / "test_hwpx_schedule_fill_end_to_end.py"
test_src = test_path.read_text(encoding="utf-8") if test_path.exists() else ""
edit_src = EDIT_TOOL.read_text(encoding="utf-8") if EDIT_TOOL.exists() else ""
gate_src = (PIPELINE_DIR / "hancom_safe_gate.py").read_text(encoding="utf-8")

# ── C01: 테스트 파일 존재 ─────────────────────────────────────────────────────
check("C01", "test_hwpx_schedule_fill_end_to_end.py 존재",
      test_path.exists() and len(test_src) > 300)

# ── C02: empty fixture end-to-end 테스트 존재 ─────────────────────────────────
check("C02", "empty fixture end-to-end 테스트 존재",
      "test_apply_edit_plan_creates_output" in test_src)

# ── C03: REVIEW_REQUIRED 실행 금지 테스트 존재 ────────────────────────────────
check("C03", "REVIEW_REQUIRED fixture 실행 금지 테스트 존재",
      "test_basic_fixture_review_required_no_execution" in test_src
      and "test_partial_fixture_review_required_no_execution" in test_src)

# ── C04: output 경로 사용 확인 ────────────────────────────────────────────────
check("C04", "apply_edit_plan output 경로 사용 확인",
      "OUTPUT_FILLED" in test_src or "output" in test_src)

# ── C05: repair_for_server 미사용 ─────────────────────────────────────────────
_repair_pat = re.compile(r"(?<!#)\brepair_for_server\s*\(")
check("C05", "repair_for_server 미사용",
      not _repair_pat.search(test_src))

# ── C06: full_verify 테스트 존재 ─────────────────────────────────────────────
check("C06", "full_verify 테스트 존재",
      "test_full_verify_pass" in test_src)

# ── C07: Parser V2 reparse 검증 존재 ─────────────────────────────────────────
check("C07", "Parser V2 reparse 검증 존재",
      "test_reparse_output_success" in test_src)

# ── C08: fillColor 검증 존재 ──────────────────────────────────────────────────
check("C08", "fillColor 검증 존재",
      "test_target_cells_fill_color" in test_src
      and "verify_cell_fill_color" in test_src)

# ── C09: non-target 보존 검증 존재 ───────────────────────────────────────────
check("C09", "non-target 보존 검증 존재",
      "test_non_target_cells_preserved" in test_src)

# ── C10: 원본 fixture 수정 금지 테스트 존재 ──────────────────────────────────
check("C10", "원본 fixture 수정 금지 테스트 존재",
      "test_fixture_not_modified" in test_src)

# ── C11: SOLID_FILL_PASS pass_statuses 포함 ──────────────────────────────────
check("C11", "SOLID_FILL_PASS pass_statuses 포함",
      "SOLID_FILL_PASS" in edit_src)

# ── 결과 출력 ─────────────────────────────────────────────────────────────────
pass_count = sum(1 for _, _, s in results if s == "PASS")
fail_count = len(results) - pass_count

print(f"\n{'='*64}")
print("HWPX-SCHEDULE-FILL-END-TO-END-01 감사 결과")
print(f"{'='*64}")
for cid, desc, status in results:
    mark = "✓" if status == "PASS" else "✗"
    print(f"  [{mark}] {cid}: {desc}")
    if status != "PASS":
        print(f"        → {status}")

print(f"\n{'='*64}")
print(f"  총 {len(results)}개 검사 | PASS {pass_count} | FAIL {fail_count}")
print(f"  최종 판정: {'PASS' if fail_count == 0 else 'FAIL'}")
print(f"{'='*64}\n")

sys.exit(0 if fail_count == 0 else 1)
