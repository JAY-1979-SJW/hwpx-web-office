"""HWPX-SCHEDULE-STATUS-COLOR-POLICY-01 감사 스크립트.

12개 항목을 검사한다.
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PIPELINE_DIR = PROJECT_ROOT / "scripts" / "hwpx" / "pipeline"
TESTS_DIR = PROJECT_ROOT / "tests"

results: list[tuple[str, str, str]] = []


def check(cid: str, desc: str, passed: bool, detail: str = "") -> None:
    status = "PASS" if passed else f"FAIL {detail}".strip()
    results.append((cid, desc, status))


policy_path = PIPELINE_DIR / "schedule_bar_color_policy.py"
generator_path = PIPELINE_DIR / "schedule_bar_plan_generator.py"
test_path = TESTS_DIR / "test_hwpx_schedule_bar_color_policy.py"

policy_src = policy_path.read_text(encoding="utf-8") if policy_path.exists() else ""
generator_src = generator_path.read_text(encoding="utf-8") if generator_path.exists() else ""
test_src = test_path.read_text(encoding="utf-8") if test_path.exists() else ""

# ── C01: 정책 파일 존재 ──────────────────────────────────────────────────────
check("C01", "schedule_bar_color_policy.py 존재",
      policy_path.exists() and len(policy_src) > 300)

# ── C02: 테스트 파일 존재 ────────────────────────────────────────────────────
check("C02", "test_hwpx_schedule_bar_color_policy.py 존재",
      test_path.exists() and len(test_src) > 300)

# ── C03: 8개 상태 코드 정의 ──────────────────────────────────────────────────
required_statuses = ["PLANNED", "IN_PROGRESS", "DONE", "DELAYED", "REVIEW", "BLOCKED", "TEMPLATE", "UNKNOWN"]
missing = [s for s in required_statuses if f'status="{s}"' not in policy_src]
check("C03", "8개 상태 코드 정의",
      len(missing) == 0, f"missing: {missing}")

# ── C04: 핵심 함수 존재 ──────────────────────────────────────────────────────
required_fns = ["get_color", "get_entry", "get_status_from_conflict",
                "get_color_from_conflict", "get_status_from_action",
                "get_color_from_action", "resolve_bar_color",
                "is_auto_allowed_color", "all_statuses", "to_policy_dict"]
missing_fns = [f for f in required_fns if f"def {f}(" not in policy_src]
check("C04", "핵심 함수 10개 존재",
      len(missing_fns) == 0, f"missing: {missing_fns}")

# ── C05: DONE 색상 = 92D050 ──────────────────────────────────────────────────
check("C05", "DONE 색상 = 92D050",
      '"92D050"' in policy_src)

# ── C06: conflict → status 매핑 존재 ────────────────────────────────────────
check("C06", "conflict → status 매핑 존재",
      "_CONFLICT_TO_STATUS" in policy_src
      and '"no_conflict"' in policy_src
      and '"overlaps_existing_bar"' in policy_src)

# ── C07: action → status 매핑 존재 ──────────────────────────────────────────
check("C07", "action → status 매핑 존재",
      "_ACTION_TO_STATUS" in policy_src
      and "AUTO_PLAN_ALLOWED" in policy_src
      and "REVIEW_REQUIRED" in policy_src)

# ── C08: plan_generator가 color_policy import ────────────────────────────────
check("C08", "schedule_bar_plan_generator가 color_policy import",
      "schedule_bar_color_policy" in generator_src
      and "resolve_bar_color" in generator_src)

# ── C09: plan_generator에 임시 색상 상수 없음 ────────────────────────────────
old_consts = ["_DEFAULT_COLOR", "_REVIEW_COLOR", "_CONFLICT_COLOR", "_STATE_COLORS"]
remaining = [c for c in old_consts if c in generator_src]
check("C09", "plan_generator 임시 색상 상수 제거",
      len(remaining) == 0, f"remaining: {remaining}")

# ── C10: autoAllowed 정책 구분 (DELAYED/REVIEW/BLOCKED=False) ────────────────
check("C10", "DELAYED/REVIEW/BLOCKED autoAllowed=False 정의",
      "autoAllowed=False" in policy_src)

# ── C11: to_policy_dict 직렬화 함수 존재 ────────────────────────────────────
check("C11", "to_policy_dict 직렬화 함수 존재",
      "def to_policy_dict(" in policy_src
      and "conflictMapping" in policy_src
      and "actionMapping" in policy_src)

# ── C12: 24개 테스트 항목 포함 ───────────────────────────────────────────────
required_tests = [
    "test_color_policy_importable",
    "test_all_statuses_count",
    "test_done_color",
    "test_conflict_to_status",
    "test_action_to_status",
    "test_resolve_explicit_color_priority",
    "test_resolve_default_fallback",
    "test_auto_allowed_colors",
    "test_policy_dict_json_serializable",
    "test_plan_generator_uses_color_policy",
    "test_no_hardcoded_color_constants_in_generator",
    "test_plan_generator_still_decides_action",
]
missing_tests = [t for t in required_tests if t not in test_src]
check("C12", "핵심 테스트 항목 포함",
      len(missing_tests) == 0, f"missing: {missing_tests}")

# ── 결과 출력 ─────────────────────────────────────────────────────────────────
pass_count = sum(1 for _, _, s in results if s == "PASS")
fail_count = len(results) - pass_count

print(f"\n{'='*64}")
print("HWPX-SCHEDULE-STATUS-COLOR-POLICY-01 감사 결과")
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
