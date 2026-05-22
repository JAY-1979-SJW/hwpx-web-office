"""HWPX-SCHEDULE-REAL-DOCUMENT-BATCH-SMOKE-01 감사 스크립트.

10개 항목을 검사한다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SMOKE_DIR = PROJECT_ROOT / "reports" / "hwpx_schedule_real_document_batch_smoke"

results: list[tuple[str, str, str]] = []


def check(cid: str, desc: str, passed: bool, detail: str = "") -> None:
    status = "PASS" if passed else f"FAIL {detail}".strip()
    results.append((cid, desc, status))


summary_path = SMOKE_DIR / "summary.md"
batch_json_path = SMOKE_DIR / "batch_summary.json"

summary_src = summary_path.read_text(encoding="utf-8") if summary_path.exists() else ""
batch_data: dict = {}
if batch_json_path.exists():
    try:
        batch_data = json.loads(batch_json_path.read_text(encoding="utf-8"))
    except Exception:
        pass

# ── C01: batch_summary.json 생성 ─────────────────────────────────────────────
check("C01", "batch_summary.json 생성",
      batch_json_path.exists() and bool(batch_data))

# ── C02: summary.md 생성 ──────────────────────────────────────────────────────
check("C02", "summary.md 생성",
      summary_path.exists() and len(summary_src) > 100)

# ── C03: 6건 전체 처리 ───────────────────────────────────────────────────────
total = batch_data.get("totalDocuments", 0)
check("C03", "6건 전체 처리",
      total == 6, f"total={total}")

# ── C04: apply_edit_plan 실행 없음 ───────────────────────────────────────────
check("C04", "apply_edit_plan 실행 없음",
      batch_data.get("applyEditPlanExecuted") == False)

# ── C05: output HWPX 생성 없음 ────────────────────────────────────────────────
check("C05", "output HWPX 생성 없음",
      batch_data.get("outputHwpxCreated") == False)

# ── C06: 원본 수정 없음 ───────────────────────────────────────────────────────
check("C06", "모든 원본 파일 수정 없음",
      batch_data.get("allOriginalUnmodified") == True)

# ── C07: FAIL_UNEXPECTED 없음 ─────────────────────────────────────────────────
fail_count = batch_data.get("failUnexpected", -1)
check("C07", "FAIL_UNEXPECTED 0건",
      fail_count == 0, f"failUnexpected={fail_count}")

# ── C08: 개인정보/원문명 hash 처리 (summary에 원문명 없음) ──────────────────
# 원문명 키워드가 summary에 직접 노출되면 FAIL
raw_names = ["감리결과보고서_공정표", "gamri_result", "03458", "03459", "03461"]
exposed = [n for n in raw_names if n in summary_src]
check("C08", "원문명 직접 노출 없음",
      len(exposed) == 0, f"exposed: {exposed}")

# ── C09: scheduleDetected 수 >= 1 ────────────────────────────────────────────
sched_detected = batch_data.get("scheduleDetected", 0)
check("C09", "공정표 탐지 문서 1건 이상",
      sched_detected >= 1, f"scheduleDetected={sched_detected}")

# ── C10: 배치 스크립트 파일 존재 ──────────────────────────────────────────────
batch_script = PROJECT_ROOT / "scripts" / "local" / "hwpx_schedule_real_document_batch_smoke.py"
check("C10", "hwpx_schedule_real_document_batch_smoke.py 존재",
      batch_script.exists())

# ── 결과 출력 ─────────────────────────────────────────────────────────────────
pass_count = sum(1 for _, _, s in results if s == "PASS")
fail_count_total = len(results) - pass_count

print(f"\n{'='*64}")
print("HWPX-SCHEDULE-REAL-DOCUMENT-BATCH-SMOKE-01 감사 결과")
print(f"{'='*64}")
for cid, desc, status in results:
    mark = "✓" if status == "PASS" else "✗"
    print(f"  [{mark}] {cid}: {desc}")
    if status != "PASS":
        print(f"        → {status}")

print(f"\n{'='*64}")
print(f"  총 {len(results)}개 검사 | PASS {pass_count} | FAIL {fail_count_total}")
print(f"  최종 판정: {'PASS' if fail_count_total == 0 else 'FAIL'}")
print(f"{'='*64}\n")

sys.exit(0 if fail_count_total == 0 else 1)
