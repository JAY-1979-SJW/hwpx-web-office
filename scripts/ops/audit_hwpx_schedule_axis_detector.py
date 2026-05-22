"""HWPX-SCHEDULE-AXIS-DETECTOR-01 감사 스크립트.

12개 항목을 검사한다.
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PARSER_DIR = PROJECT_ROOT / "scripts" / "hwpx" / "parser"
TESTS_DIR = PROJECT_ROOT / "tests"

results: list[tuple[str, str, str]] = []


def check(cid: str, desc: str, passed: bool, detail: str = "") -> None:
    status = "PASS" if passed else f"FAIL {detail}".strip()
    results.append((cid, desc, status))


det_path = PARSER_DIR / "schedule_detector.py"
det_src = det_path.read_text(encoding="utf-8") if det_path.exists() else ""

contract_path = PARSER_DIR / "parser_contract.py"
contract_src = contract_path.read_text(encoding="utf-8") if contract_path.exists() else ""

engine_path = PARSER_DIR / "parser_engine.py"
engine_src = engine_path.read_text(encoding="utf-8") if engine_path.exists() else ""

test_path = TESTS_DIR / "test_hwpx_schedule_axis_detector.py"
test_src = test_path.read_text(encoding="utf-8") if test_path.exists() else ""

# ── C01–C05: 탐지 함수 존재 ───────────────────────────────────────────────────
check("C01", "schedule_detector.py 존재", det_path.exists())
check("C02", "detect_time_axis 존재", "def detect_time_axis" in det_src)
check("C03", "detect_task_rows 존재", "def detect_task_rows" in det_src)
check("C04", "detect_bar_ranges 존재", "def detect_bar_ranges" in det_src)
check("C05", "detect_progress_column 존재", "def detect_progress_column" in det_src)

# ── C06: ScheduleInfo 계약 ────────────────────────────────────────────────────
check("C06", "ScheduleInfo / schedules 계약 존재",
      "class ScheduleInfo" in contract_src and "schedules" in contract_src)

# ── C07: 테스트 파일 존재 ──────────────────────────────────────────────────────
check("C07", "test_hwpx_schedule_axis_detector.py 존재",
      test_path.exists() and len(test_src) > 300)

# ── C08: 원본 수정 금지 원칙 ─────────────────────────────────────────────────
check("C08", "원본 수정 금지 원칙 존재",
      "원본 fixture 수정 없음" in test_src or "not_modified" in test_src)

# ── C09: apply_edit_plan / write_package 미사용 (import 또는 함수 호출 없음)
import re as _re
_call_pat = _re.compile(r'(?<!#)\b(apply_edit_plan|write_package)\s*\(')
check("C09", "apply_edit_plan / write_package 미사용",
      not _call_pat.search(det_src))

# ── C10: parser_engine 통합 존재 ─────────────────────────────────────────────
check("C10", "parser_engine schedule_detector 통합",
      "schedule_detector" in engine_src and "detect_schedule_structure" in engine_src)

# ── C11: reports 커밋 제외 원칙 명시 ─────────────────────────────────────────
check("C11", "reports 커밋 제외 원칙 명시",
      "reports" in det_src)

# ── C12: fill_schedule_bars 호출 없음 ─────────────────────────────────────────
check("C12", "fill_schedule_bars 호출 없음",
      "fill_schedule_bars" not in det_src)

# ── 결과 출력 ─────────────────────────────────────────────────────────────────
pass_count = sum(1 for _, _, s in results if s == "PASS")
fail_count = len(results) - pass_count

print(f"\n{'='*64}")
print("HWPX-SCHEDULE-AXIS-DETECTOR-01 감사 결과")
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
