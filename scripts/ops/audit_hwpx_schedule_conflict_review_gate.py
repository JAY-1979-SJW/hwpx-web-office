"""HWPX-SCHEDULE-CONFLICT-REVIEW-GATE-01 감사 스크립트.

12개 항목을 검사한다.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TESTS_DIR = PROJECT_ROOT / "tests"
PIPELINE_DIR = PROJECT_ROOT / "scripts" / "hwpx" / "pipeline"
CONTRACT_FILE = PROJECT_ROOT / "scripts" / "hwpx" / "parser" / "parser_contract.py"

results: list[tuple[str, str, str]] = []


def check(cid: str, desc: str, passed: bool, detail: str = "") -> None:
    status = "PASS" if passed else f"FAIL {detail}".strip()
    results.append((cid, desc, status))


test_path = TESTS_DIR / "test_hwpx_schedule_conflict_review_gate.py"
gate_path = PIPELINE_DIR / "conflict_review_gate.py"

test_src = test_path.read_text(encoding="utf-8") if test_path.exists() else ""
gate_src = gate_path.read_text(encoding="utf-8") if gate_path.exists() else ""
contract_src = CONTRACT_FILE.read_text(encoding="utf-8") if CONTRACT_FILE.exists() else ""

# ── C01: 게이트 파일 존재 ──────────────────────────────────────────────────────
check("C01", "conflict_review_gate.py 존재",
      gate_path.exists() and len(gate_src) > 300)

# ── C02: 테스트 파일 존재 ──────────────────────────────────────────────────────
check("C02", "test_hwpx_schedule_conflict_review_gate.py 존재",
      test_path.exists() and len(test_src) > 300)

# ── C03: build_review_list 함수 존재 ─────────────────────────────────────────
check("C03", "build_review_list 함수 존재",
      "def build_review_list(" in gate_src)

# ── C04: apply_review_decisions 함수 존재 ────────────────────────────────────
check("C04", "apply_review_decisions 함수 존재",
      "def apply_review_decisions(" in gate_src)

# ── C05: gate_all_approved / gate_all_rejected 존재 ──────────────────────────
check("C05", "gate_all_approved / gate_all_rejected 존재",
      "def gate_all_approved(" in gate_src and "def gate_all_rejected(" in gate_src)

# ── C06: validate_gate_output / summarize_gate_output 존재 ───────────────────
check("C06", "validate_gate_output / summarize_gate_output 존재",
      "def validate_gate_output(" in gate_src and "def summarize_gate_output(" in gate_src)

# ── C07: apply_edit_plan 호출 없음 ────────────────────────────────────────────
_apply_pat = re.compile(r"(?<!#)\bapply_edit_plan\s*\(")
check("C07", "apply_edit_plan 호출 없음",
      not _apply_pat.search(gate_src))

# ── C08: fill_schedule_bars 실행 없음 ─────────────────────────────────────────
_fill_pat = re.compile(r"(?<!#)\bfill_schedule_bars\s*\(")
check("C08", "fill_schedule_bars 실행 없음 (call)",
      not _fill_pat.search(gate_src))

# ── C09: contract에 ScheduleBarReviewItem / ScheduleBarReviewDecision 존재 ───
check("C09", "ScheduleBarReviewItem / ScheduleBarReviewDecision 존재",
      "class ScheduleBarReviewItem" in contract_src
      and "class ScheduleBarReviewDecision" in contract_src)

# ── C10: contract에 ScheduleBarReviewList / ScheduleBarGateOutput 존재 ────────
check("C10", "ScheduleBarReviewList / ScheduleBarGateOutput 존재",
      "class ScheduleBarReviewList" in contract_src
      and "class ScheduleBarGateOutput" in contract_src)

# ── C11: ScheduleBarGateOutput.to_fill_plan_dict 존재 ────────────────────────
check("C11", "ScheduleBarGateOutput.to_fill_plan_dict 존재",
      "to_fill_plan_dict" in contract_src)

# ── C12: 16개 테스트 항목 포함 ────────────────────────────────────────────────
required_tests = [
    "test_conflict_review_gate_importable",
    "test_review_required_items_separated",
    "test_auto_allowed_items_in_auto_list",
    "test_invalid_coords_in_failed_items",
    "test_approved_decision_moves_to_approved",
    "test_rejected_decision_moves_to_rejected",
    "test_deferred_decision_moves_to_deferred",
    "test_no_decision_moves_to_pending",
    "test_auto_items_always_in_approved",
    "test_gate_all_approved",
    "test_gate_all_rejected",
    "test_to_fill_plan_dict_approved_only",
    "test_gate_output_json_serializable",
    "test_validate_gate_output_pass",
    "test_basic_fixture_produces_review_list",
    "test_no_apply_or_fill_calls_in_gate",
]
missing = [t for t in required_tests if t not in test_src]
check("C12", "16개 테스트 항목 포함",
      len(missing) == 0, f"missing: {missing}")

# ── 결과 출력 ─────────────────────────────────────────────────────────────────
pass_count = sum(1 for _, _, s in results if s == "PASS")
fail_count = len(results) - pass_count

print(f"\n{'='*64}")
print("HWPX-SCHEDULE-CONFLICT-REVIEW-GATE-01 감사 결과")
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
