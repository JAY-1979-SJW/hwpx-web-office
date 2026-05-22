"""HWPX-UNIVERSAL-FORM-RECOGNITION-AND-FILL-TEST-01 감사 스크립트.

12개 항목을 검사한다.
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PIPELINE_PKG = PROJECT_ROOT / "scripts" / "hwpx" / "pipeline"
TESTS_DIR = PROJECT_ROOT / "tests"

results: list[tuple[str, str, str]] = []


def check(cid: str, desc: str, passed: bool, detail: str = "") -> None:
    status = "PASS" if passed else f"FAIL {detail}".strip()
    results.append((cid, desc, status))


# ── C01. form_recognizer.py 존재 ──────────────────────────────────────────────

fr_path = PIPELINE_PKG / "form_recognizer.py"
check("C01", "form_recognizer.py 존재", fr_path.exists())
fr_src = fr_path.read_text(encoding="utf-8") if fr_path.exists() else ""

# ── C02. recognize_form 함수 존재 ─────────────────────────────────────────────

check("C02", "recognize_form 함수 존재", "def recognize_form" in fr_src)

# ── C03. classify_table_roles 함수 존재 ───────────────────────────────────────

check("C03", "classify_table_roles 함수 존재", "def classify_table_roles" in fr_src)

# ── C04. input slot 확장 규칙 존재 ────────────────────────────────────────────

required_rules = ["label_right", "label_below", "label_value_pair", "merged_input_cell"]
missing = [r for r in required_rules if r not in fr_src]
check("C04", "input slot 확장 규칙 (4종) 존재", len(missing) == 0, f"missing: {missing}")

# ── C05-C11. 테스트 파일 확인 ─────────────────────────────────────────────────

test_file = TESTS_DIR / "test_hwpx_universal_form_recognition_fill.py"
test_src = test_file.read_text(encoding="utf-8") if test_file.exists() else ""

check("C05", "label_right 테스트 존재",       "label_right" in test_src)
check("C06", "label_value_pair 테스트 존재",  "label_value_pair" in test_src)
check("C07", "unsafe table 제외 테스트 존재", "stamp_table_not_in_slots" in test_src or "unsafe" in test_src)
check("C08", "plan_builder slot 기반 plan 생성 테스트 존재",
      "build_edit_plan_from_form" in test_src)
check("C09", "reparse verify 테스트 존재",    "reparse_verify" in test_src or "verification" in test_src)
check("C10", "full_verify 테스트 존재",       "full_verify" in test_src or "hancomVerify" in test_src)
check("C11", "원본 수정 금지 테스트 존재",    "not_modified" in test_src or "mtime" in test_src)

# ── C12. reports 커밋 제외 원칙 ───────────────────────────────────────────────

gitignore = PROJECT_ROOT / ".gitignore"
gi_src = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
check("C12", "reports/ 커밋 제외 원칙 존재", "reports/" in gi_src or "reports" in gi_src)

# ── 결과 출력 ─────────────────────────────────────────────────────────────────

pass_count = sum(1 for _, _, s in results if s == "PASS")
fail_count = len(results) - pass_count

print(f"\n{'='*64}")
print("HWPX-UNIVERSAL-FORM-RECOGNITION-FILL-01 감사 결과")
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
