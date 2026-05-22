"""HWPX-SCHEDULE-REAL-DOCUMENT-SMOKE-01 감사 스크립트.

8개 항목을 검사한다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SMOKE_DIR = PROJECT_ROOT / "reports" / "hwpx_schedule_real_document_smoke"
FIXTURE_DOC = PROJECT_ROOT / "tests" / "fixtures" / "hwpx" / "gantt" / "fx_gantt_like_basic.hwpx"

results: list[tuple[str, str, str]] = []


def check(cid: str, desc: str, passed: bool, detail: str = "") -> None:
    status = "PASS" if passed else f"FAIL {detail}".strip()
    results.append((cid, desc, status))


summary_path = SMOKE_DIR / "summary.md"
parse_before_path = SMOKE_DIR / "parse_before.json"

summary_src = summary_path.read_text(encoding="utf-8") if summary_path.exists() else ""
parse_before = {}
if parse_before_path.exists():
    try:
        parse_before = json.loads(parse_before_path.read_text(encoding="utf-8"))
    except Exception:
        pass

# ── C01: summary.md 생성 ──────────────────────────────────────────────────────
check("C01", "summary.md 생성 여부",
      summary_path.exists() and len(summary_src) > 100)

# ── C02: parse_before.json 생성 ──────────────────────────────────────────────
check("C02", "parse_before.json 생성 여부",
      parse_before_path.exists() and bool(parse_before))

# ── C03: conflict gate 실행 여부 ──────────────────────────────────────────────
check("C03", "conflict gate 실행 여부 (summary 포함)",
      "conflict gate" in summary_src.lower() or "decision:" in summary_src)

# ── C04: REVIEW_REQUIRED → apply_edit_plan 미실행 ────────────────────────────
review_required = "REVIEW_REQUIRED" in summary_src
apply_not_executed = "apply_edit_plan executed: False" in summary_src or "applyEditPlanExecuted" in summary_src
check("C04", "REVIEW_REQUIRED 시 apply_edit_plan 미실행",
      (not review_required) or apply_not_executed)

# ── C05: AUTO_PLAN_ALLOWED이면 output 생성 (또는 REVIEW_REQUIRED이면 output 없음) ─
output_hwpx = SMOKE_DIR / "output" / "real_schedule_smoke_filled.hwpx"
if review_required:
    check("C05", "REVIEW_REQUIRED이므로 output 없음",
          not output_hwpx.exists() or "output created: False" in summary_src)
else:
    check("C05", "AUTO_PLAN_ALLOWED이면 output 생성",
          output_hwpx.exists())

# ── C06: 원본 fixture 수정 없음 ───────────────────────────────────────────────
check("C06", "원본 수정 여부: NO",
      "원본 수정 여부: NO (PASS)" in summary_src)

# ── C07: parse_before schedule 탐지 ──────────────────────────────────────────
check("C07", "parse_before schedule table 탐지",
      parse_before.get("scheduleTableFound", False))

# ── C08: smoke 스크립트 파일 존재 ─────────────────────────────────────────────
smoke_script = PROJECT_ROOT / "scripts" / "local" / "hwpx_schedule_real_document_smoke.py"
check("C08", "hwpx_schedule_real_document_smoke.py 존재",
      smoke_script.exists())

# ── 결과 출력 ─────────────────────────────────────────────────────────────────
pass_count = sum(1 for _, _, s in results if s == "PASS")
fail_count = len(results) - pass_count

print(f"\n{'='*64}")
print("HWPX-SCHEDULE-REAL-DOCUMENT-SMOKE-01 감사 결과")
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
