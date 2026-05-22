"""HWPX-INPUT-SLOT-DETECTOR-01 감사 스크립트.

15개 항목을 검사한다.
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
HWPX_DIR = PROJECT_ROOT / "scripts" / "hwpx"
PARSER_DIR = HWPX_DIR / "parser"
PIPELINE_DIR = HWPX_DIR / "pipeline"
TESTS_DIR = PROJECT_ROOT / "tests"

results: list[tuple[str, str, str]] = []


def check(cid: str, desc: str, passed: bool, detail: str = "") -> None:
    status = "PASS" if passed else f"FAIL {detail}".strip()
    results.append((cid, desc, status))


det_path = PARSER_DIR / "input_slot_detector.py"
det_src = det_path.read_text(encoding="utf-8") if det_path.exists() else ""

fr_path = PIPELINE_DIR / "form_recognizer.py"
fr_src = fr_path.read_text(encoding="utf-8") if fr_path.exists() else ""

pb_path = PIPELINE_DIR / "plan_builder.py"
pb_src = pb_path.read_text(encoding="utf-8") if pb_path.exists() else ""

test_path = TESTS_DIR / "test_hwpx_input_slot_detector.py"
test_src = test_path.read_text(encoding="utf-8") if test_path.exists() else ""

# ── C01–C08: 탐지 함수 존재 ────────────────────────────────────────────────
check("C01", "detect_label_right_slots 존재", "def detect_label_right_slots" in det_src)
check("C02", "detect_label_below_slots 존재", "def detect_label_below_slots" in det_src)
check("C03", "detect_label_value_pair_slots 존재", "def detect_label_value_pair_slots" in det_src)
check("C04", "detect_merged_input_cells 존재", "def detect_merged_input_cells" in det_src)
check("C05", "detect_blank_after_known_header_slots 존재", "def detect_blank_after_known_header_slots" in det_src)
check("C06", "detect_metadata_form_slots 존재", "def detect_metadata_form_slots" in det_src)
check("C07", "detect_data_table_append_slots 존재", "def detect_data_table_append_slots" in det_src)
check("C08", "detect_status_cells 존재", "def detect_status_cells" in det_src)

# ── C09: unsafe table filter ───────────────────────────────────────────────
check("C09", "unsafe table filter 존재", "def filter_unsafe_slots" in det_src)

# ── C10: confidence scoring ────────────────────────────────────────────────
check("C10", "confidence scoring (score_slot) 존재", "def score_slot" in det_src)

# ── C11: autoEditAllowed 정책 ─────────────────────────────────────────────
check("C11", "autoEditAllowed 정책 존재",
      "_AUTO_EDIT_THRESHOLD" in det_src and "autoEditAllowed" in det_src)

# ── C12: duplicate field review 정책 ──────────────────────────────────────
check("C12", "duplicate field review 정책 존재",
      "duplicate" in pb_src and "review" in pb_src.lower())

# ── C13: 테스트 파일 존재 ─────────────────────────────────────────────────
check("C13", "tests/test_hwpx_input_slot_detector.py 존재",
      test_path.exists() and len(test_src) > 500)

# ── C14: plan_builder slot 기반 set_visual_cells 생성 ─────────────────────
check("C14", "plan_builder set_visual_cells 생성",
      "set_visual_cells" in pb_src)

# ── C15: page/stamp 제외 테스트 존재 ─────────────────────────────────────
check("C15", "page/stamp table 제외 테스트 존재",
      "page_marker" in test_src and "stamp" in test_src)

# ── 결과 출력 ─────────────────────────────────────────────────────────────
pass_count = sum(1 for _, _, s in results if s == "PASS")
fail_count = len(results) - pass_count

print(f"\n{'='*64}")
print("HWPX-INPUT-SLOT-DETECTOR-01 감사 결과")
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
