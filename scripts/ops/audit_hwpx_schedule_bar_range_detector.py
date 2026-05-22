"""HWPX-SCHEDULE-BAR-RANGE-DETECTOR-01 감사 스크립트.

12개 항목을 검사한다.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PARSER_DIR = PROJECT_ROOT / "scripts" / "hwpx" / "parser"
TESTS_DIR = PROJECT_ROOT / "tests"

results: list[tuple[str, str, str]] = []


def check(cid: str, desc: str, passed: bool, detail: str = "") -> None:
    status = "PASS" if passed else f"FAIL {detail}".strip()
    results.append((cid, desc, status))


det_src = (PARSER_DIR / "schedule_detector.py").read_text(encoding="utf-8")
contract_src = (PARSER_DIR / "parser_contract.py").read_text(encoding="utf-8")

test_path = TESTS_DIR / "test_hwpx_schedule_bar_range_detector.py"
test_src = test_path.read_text(encoding="utf-8") if test_path.exists() else ""

# ── C01–C06: 함수 존재 ────────────────────────────────────────────────────────
check("C01", "normalize_schedule_date 존재", "def normalize_schedule_date" in det_src)
check("C02", "map_date_range_to_columns 존재", "def map_date_range_to_columns" in det_src)
check("C03", "find_task_row 존재", "def find_task_row" in det_src)
check("C04", "build_schedule_bar_plan_candidate 존재",
      "def build_schedule_bar_plan_candidate" in det_src)
check("C05", "detect_bar_conflict 존재", "def detect_bar_conflict" in det_src)
check("C06", "generate_empty_template_bar_candidates 존재",
      "def generate_empty_template_bar_candidates" in det_src)

# ── C07: 계약 존재 ────────────────────────────────────────────────────────────
check("C07", "ScheduleBarPlanCandidate 계약 존재",
      "class ScheduleBarPlanCandidate" in contract_src)

# ── C08: 테스트 파일 존재 ──────────────────────────────────────────────────────
check("C08", "test_hwpx_schedule_bar_range_detector.py 존재",
      test_path.exists() and len(test_src) > 300)

# ── C09: apply_edit_plan / write_package 미사용 ───────────────────────────────
_call_pat = re.compile(r"(?<!#)\b(apply_edit_plan|write_package)\s*\(")
check("C09", "apply_edit_plan / write_package 미사용",
      not _call_pat.search(det_src))

# ── C10: reports 커밋 제외 원칙 명시 ─────────────────────────────────────────
check("C10", "reports 커밋 제외 원칙 명시", "reports" in det_src)

# ── C11: fill_schedule_bars 함수 호출 없음 (언급은 허용, 실제 호출만 금지)
_fill_call_pat = re.compile(r"(?<!#)\bfill_schedule_bars\s*\(")
check("C11", "fill_schedule_bars 함수 호출 없음", not _fill_call_pat.search(det_src))

# ── C12: 원본 수정 금지 원칙 ─────────────────────────────────────────────────
check("C12", "원본 수정 금지 원칙 명시",
      "원본 fixture 수정 없음" in det_src or "not_modified" in test_src)

# ── 결과 출력 ─────────────────────────────────────────────────────────────────
pass_count = sum(1 for _, _, s in results if s == "PASS")
fail_count = len(results) - pass_count

print(f"\n{'='*64}")
print("HWPX-SCHEDULE-BAR-RANGE-DETECTOR-01 감사 결과")
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
