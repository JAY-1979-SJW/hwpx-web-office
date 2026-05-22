"""HWPX-SCHEDULE-BAR-PLAN-GENERATOR-01 감사 스크립트.

13개 항목을 검사한다.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PIPELINE_DIR = PROJECT_ROOT / "scripts" / "hwpx" / "pipeline"
PARSER_DIR = PROJECT_ROOT / "scripts" / "hwpx" / "parser"
TESTS_DIR = PROJECT_ROOT / "tests"

results: list[tuple[str, str, str]] = []


def check(cid: str, desc: str, passed: bool, detail: str = "") -> None:
    status = "PASS" if passed else f"FAIL {detail}".strip()
    results.append((cid, desc, status))


gen_src = (PIPELINE_DIR / "schedule_bar_plan_generator.py").read_text(encoding="utf-8")
contract_src = (PARSER_DIR / "parser_contract.py").read_text(encoding="utf-8")

test_path = TESTS_DIR / "test_hwpx_schedule_bar_plan_generator.py"
test_src = test_path.read_text(encoding="utf-8") if test_path.exists() else ""

# ── C01–C06: 함수 존재 ────────────────────────────────────────────────────────
check("C01", "decide_bar_plan_action 존재", "def decide_bar_plan_action" in gen_src)
check("C02", "convert_candidate_to_edit_plan_item 존재",
      "def convert_candidate_to_edit_plan_item" in gen_src)
check("C03", "build_fill_schedule_bars_plan 존재",
      "def build_fill_schedule_bars_plan" in gen_src)
check("C04", "build_fill_schedule_bars_plan_from_candidates 존재",
      "def build_fill_schedule_bars_plan_from_candidates" in gen_src)
check("C05", "validate_schedule_bar_plan 존재", "def validate_schedule_bar_plan" in gen_src)
check("C06", "summarize_schedule_bar_plan 존재", "def summarize_schedule_bar_plan" in gen_src)

# ── C07: 계약 클래스 존재 ─────────────────────────────────────────────────────
_required_classes = [
    "ScheduleBarEditPlanItem",
    "ScheduleBarPlanDecision",
    "ScheduleBarEditPlan",
    "ScheduleBarPlanBuildResult",
]
for cls in _required_classes:
    check(f"C07", f"{cls} 계약 존재", f"class {cls}" in contract_src)
# Use first class for C07 (multiple checks aggregated)
results_c07 = [r for r in results if r[0] == "C07"]
if len(results_c07) > 1:
    all_pass = all(r[2] == "PASS" for r in results_c07)
    results[:] = [r for r in results if r[0] != "C07"]
    results.append(("C07", "4개 계약 클래스 존재", "PASS" if all_pass else
                    f"FAIL missing: {[c for c in _required_classes if f'class {c}' not in contract_src]}"))

# ── C08: 테스트 파일 존재 ─────────────────────────────────────────────────────
check("C08", "test_hwpx_schedule_bar_plan_generator.py 존재",
      test_path.exists() and len(test_src) > 300)

# ── C09: apply_edit_plan 호출 없음 ───────────────────────────────────────────
_apply_pat = re.compile(r"(?<!#)\bapply_edit_plan\s*\(")
check("C09", "apply_edit_plan 호출 없음", not _apply_pat.search(gen_src))

# ── C10: fill_schedule_bars 호출 없음 ────────────────────────────────────────
_fill_pat = re.compile(r"(?<!#)\bfill_schedule_bars\s*\(")
check("C10", "fill_schedule_bars 호출 없음", not _fill_pat.search(gen_src))

# ── C11: write_package 호출 없음 ─────────────────────────────────────────────
_write_pat = re.compile(r"(?<!#)\bwrite_package\s*\(")
check("C11", "write_package 호출 없음", not _write_pat.search(gen_src))

# ── C12: 색상 정책 명시 ────────────────────────────────────────────────────────
check("C12", "색상 정책 (_DEFAULT_COLOR/_REVIEW_COLOR) 명시",
      "_DEFAULT_COLOR" in gen_src and "_REVIEW_COLOR" in gen_src)

# ── C13: to_fill_plan_dict 키 포함 (contract 파일 검사) ──────────────────────
_fill_keys = ["task_row", "start_col", "end_col", "color", "shrink_to_fit"]
check("C13", "to_fill_plan_dict 필수 키 포함",
      all(k in contract_src for k in _fill_keys))

# ── 결과 출력 ─────────────────────────────────────────────────────────────────
pass_count = sum(1 for _, _, s in results if s == "PASS")
fail_count = len(results) - pass_count

print(f"\n{'='*64}")
print("HWPX-SCHEDULE-BAR-PLAN-GENERATOR-01 감사 결과")
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
