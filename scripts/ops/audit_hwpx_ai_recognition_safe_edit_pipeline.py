"""HWPX-AI-RECOGNITION-TO-HANCOM-SAFE-EDIT-PIPELINE-01 감사 스크립트.

17개 항목을 검사하여 PASS/FAIL을 출력한다.
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PIPELINE_PKG = PROJECT_ROOT / "scripts" / "hwpx" / "pipeline"
TESTS_DIR = PROJECT_ROOT / "tests"
DOCS_CONTRACT = PROJECT_ROOT / "docs" / "contracts"
DOCS_ARCH = PROJECT_ROOT / "docs" / "architecture"

results: list[tuple[str, str, str]] = []


def check(cid: str, desc: str, passed: bool, detail: str = "") -> None:
    status = "PASS" if passed else f"FAIL {detail}".strip()
    results.append((cid, desc, status))


# ── C01-C06. 파이프라인 패키지 존재 ──────────────────────────────────────────

files = {
    "C01": ("pipeline 패키지 존재",           PIPELINE_PKG / "__init__.py"),
    "C02": ("recognition_pipeline.py 존재",  PIPELINE_PKG / "recognition_pipeline.py"),
    "C03": ("plan_builder.py 존재",           PIPELINE_PKG / "plan_builder.py"),
    "C04": ("reparse_verifier.py 존재",       PIPELINE_PKG / "reparse_verifier.py"),
    "C05": ("hancom_safe_gate.py 존재",       PIPELINE_PKG / "hancom_safe_gate.py"),
    "C06": ("pipeline_contract.py 존재",      PIPELINE_PKG / "pipeline_contract.py"),
}
for cid, (desc, path) in files.items():
    check(cid, desc, path.exists(), f"not found: {path.name}")

# ── C07-C12. 파이프라인 단계 존재 ────────────────────────────────────────────

engine_src = (PIPELINE_PKG / "recognition_pipeline.py").read_text(encoding="utf-8") \
    if (PIPELINE_PKG / "recognition_pipeline.py").exists() else ""
plan_src   = (PIPELINE_PKG / "plan_builder.py").read_text(encoding="utf-8") \
    if (PIPELINE_PKG / "plan_builder.py").exists() else ""
verify_src = (PIPELINE_PKG / "reparse_verifier.py").read_text(encoding="utf-8") \
    if (PIPELINE_PKG / "reparse_verifier.py").exists() else ""
gate_src   = (PIPELINE_PKG / "hancom_safe_gate.py").read_text(encoding="utf-8") \
    if (PIPELINE_PKG / "hancom_safe_gate.py").exists() else ""

check("C07", "parse_before 단계 존재",   "parse_before" in engine_src)
check("C08", "plan 단계 존재",            "build_edit_plan" in engine_src)
check("C09", "edit 단계 존재",            "apply_edit_plan" in engine_src)
check("C10", "parse_after 단계 존재",     "parse_after" in engine_src)
check("C11", "reparse verify 단계 존재", "reparse_verify" in engine_src)
check("C12", "full_verify gate 존재",     "hwpx_full_verify" in gate_src or "_full_verify" in gate_src)

# ── C13. mimetype ZIP_STORED 검증 존재 ────────────────────────────────────────

check("C13", "mimetype ZIP_STORED 검증 존재",
      "ZIP_STORED" in gate_src)

# ── C14-C15. 옵션 테스트 존재 ─────────────────────────────────────────────────

test_file = TESTS_DIR / "test_hwpx_ai_recognition_safe_edit_pipeline.py"
test_src = test_file.read_text(encoding="utf-8") if test_file.exists() else ""

check("C14", "solid_fill 옵션 테스트 존재",   "solid_fill" in test_src)
check("C15", "shrink_to_fit 옵션 테스트 존재", "shrink_to_fit" in test_src)

# ── C16. 원본 수정 금지 테스트 존재 ──────────────────────────────────────────

check("C16", "원본 수정 금지 테스트 존재",
      "original_not_modified" in test_src or "mtime" in test_src)

# ── C17. reports 커밋 제외 원칙 (gitignore 또는 .gitkeep 확인) ────────────────

gitignore = PROJECT_ROOT / ".gitignore"
gitignore_src = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
check("C17", "reports/ 커밋 제외 원칙 존재",
      "reports/" in gitignore_src or "reports" in gitignore_src)

# ── 결과 출력 ─────────────────────────────────────────────────────────────────

pass_count = sum(1 for _, _, s in results if s == "PASS")
fail_count = len(results) - pass_count

print(f"\n{'='*62}")
print("HWPX-AI-RECOGNITION-SAFE-EDIT-PIPELINE-01 감사 결과")
print(f"{'='*62}")
for cid, desc, status in results:
    mark = "✓" if status == "PASS" else "✗"
    print(f"  [{mark}] {cid}: {desc}")
    if status != "PASS":
        print(f"        → {status}")

print(f"\n{'='*62}")
print(f"  총 {len(results)}개 검사 | PASS {pass_count} | FAIL {fail_count}")
verdict = "PASS" if fail_count == 0 else "FAIL"
print(f"  최종 판정: {verdict}")
print(f"{'='*62}\n")

sys.exit(0 if fail_count == 0 else 1)
