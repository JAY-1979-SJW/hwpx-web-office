"""HWPX-GENERIC-FORMAT-RECOGNITION-AUDIT-01 메타 감사 스크립트.

12개 항목을 검사한다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AUDIT_DIR = PROJECT_ROOT / "reports" / "hwpx_generic_format_recognition_audit"

results: list[tuple[str, str, str]] = []


def check(cid: str, desc: str, passed: bool, detail: str = "") -> None:
    status = "PASS" if passed else f"FAIL {detail}".strip()
    results.append((cid, desc, status))


cov_path = AUDIT_DIR / "coverage_matrix.json"
cov_md_path = AUDIT_DIR / "coverage_matrix.md"
backlog_path = AUDIT_DIR / "missing_feature_backlog.md"
risk_path = AUDIT_DIR / "edit_safety_risk.md"
audit_script = PROJECT_ROOT / "scripts" / "local" / "hwpx_generic_format_recognition_audit.py"

cov_data: dict = {}
if cov_path.exists():
    try:
        cov_data = json.loads(cov_path.read_text(encoding="utf-8"))
    except Exception:
        pass

# ── C01: 감사 스크립트 존재 ──────────────────────────────────────────────────
check("C01", "감사 스크립트 존재",
      audit_script.exists())

# ── C02: coverage_matrix.json 생성 ───────────────────────────────────────────
check("C02", "coverage_matrix.json 생성",
      cov_path.exists() and bool(cov_data))

# ── C03: coverage_matrix.md 생성 ────────────────────────────────────────────
check("C03", "coverage_matrix.md 생성",
      cov_md_path.exists() and len(cov_md_path.read_text(encoding="utf-8")) > 100)

# ── C04: missing_feature_backlog.md 생성 ────────────────────────────────────
check("C04", "missing_feature_backlog.md 생성",
      backlog_path.exists())

# ── C05: edit_safety_risk.md 생성 ───────────────────────────────────────────
check("C05", "edit_safety_risk.md 생성",
      risk_path.exists())

# ── C06: 6건 이상 문서 감사 ──────────────────────────────────────────────────
total = cov_data.get("totalDocuments", 0)
check("C06", "6건 이상 문서 감사",
      total >= 6, f"total={total}")

# ── C07: 원본 수정 없음 ──────────────────────────────────────────────────────
check("C07", "모든 원본 수정 없음",
      cov_data.get("allOriginalUnmodified") == True)

# ── C08: 편집 기능/writer 수정 코드 없음 ─────────────────────────────────────
import re
audit_src = audit_script.read_text(encoding="utf-8") if audit_script.exists() else ""
forbidden = []
for pat in (r"\bapply_edit_plan\s*\(", r"\bwrite_package\s*\(",
            r"\bfill_schedule_bars\s*\(", r"\brepair_for_server\s*\("):
    if re.search(pat, audit_src):
        forbidden.append(pat)
check("C08", "편집/writer 호출 없음",
      len(forbidden) == 0, f"forbidden: {forbidden}")

# ── C09: 인식 결함이 1건 이상 식별됨 (감사 효용 검증) ───────────────────────
backlog_src = backlog_path.read_text(encoding="utf-8") if backlog_path.exists() else ""
has_findings = ("HALIGN" in backlog_src or "FILLCOLOR" in backlog_src
                or "CHAR_STYLE" in backlog_src or "FONTFACE" in backlog_src)
check("C09", "인식 결함 식별됨 (감사 효용)",
      has_findings, f"no findings detected in backlog")

# ── C10: BLOCKER_EDIT_UNSAFE 미발견 (현재 단계 안전) ────────────────────────
blocker = cov_data.get("blockerEditUnsafe", -1)
check("C10", "BLOCKER_EDIT_UNSAFE 0건",
      blocker == 0, f"blocker={blocker}")

# ── C11: reports 산출물 경로 정확 ────────────────────────────────────────────
check("C11", "reports/hwpx_generic_format_recognition_audit/ 경로 사용",
      AUDIT_DIR.exists())

# ── C12: 개인정보/원문명 직접 노출 없음 (docTag만 사용) ─────────────────────
cov_md = cov_md_path.read_text(encoding="utf-8") if cov_md_path.exists() else ""
raw_names = ["감리결과보고서", "gamri_result", "03458", "03459", "03461"]
exposed = [n for n in raw_names if n in cov_md]
check("C12", "원문명 직접 노출 없음",
      len(exposed) == 0, f"exposed: {exposed}")

# ── 결과 출력 ─────────────────────────────────────────────────────────────────
pass_count = sum(1 for _, _, s in results if s == "PASS")
fail_count = len(results) - pass_count

print(f"\n{'='*64}")
print("HWPX-GENERIC-FORMAT-RECOGNITION-AUDIT-01 메타 감사 결과")
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
