"""
Audit script: HWP-HWPX-LOCAL-FULL-INVENTORY-AND-PROFILE-01.

HWP/HWPX 전수 조사 및 HWPX profiler 결과의 무결성,
read-only 원칙, 원본 수정 없음을 정적 감사한다.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
INV_DIR = PROJECT_ROOT / "reports" / "hwp_hwpx_full_inventory_dl"
PROFILE_DIR = PROJECT_ROOT / "reports" / "hwpx_full_corpus_profile"
INVENTORY_SCRIPT = PROJECT_ROOT / "scripts" / "local" / "local_document_corpus_inventory.py"
PROFILER_SCRIPT = PROJECT_ROOT / "scripts" / "local" / "hwpx_corpus_profiler.py"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.exists() else ""


def audit() -> dict:
    checks: list[dict] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"name": name, "status": "PASS" if ok else "FAIL", "detail": detail})

    # 1. HWP/HWPX inventory 산출물 존재
    for fname in ["document_inventory.jsonl", "document_inventory.csv",
                  "hwp_candidates.jsonl", "hwpx_candidates.jsonl",
                  "hwp_conversion_plan.csv", "engine_candidate_summary.json", "summary.md"]:
        p = INV_DIR / fname
        check(f"inventory output: {fname}", p.exists(), str(p))

    # 2. HWP 후보 목록 존재 (hwp_candidates.jsonl 비어있지 않음)
    hwp_p = INV_DIR / "hwp_candidates.jsonl"
    hwp_count = 0
    if hwp_p.exists():
        lines = [l for l in hwp_p.read_text(encoding="utf-8").splitlines() if l.strip()]
        hwp_count = len(lines)
    check("HWP candidates non-empty", hwp_count > 0, f"count={hwp_count}")

    # 3. HWPX 후보 목록 존재
    hwpx_p = INV_DIR / "hwpx_candidates.jsonl"
    hwpx_count = 0
    if hwpx_p.exists():
        lines = [l for l in hwpx_p.read_text(encoding="utf-8").splitlines() if l.strip()]
        hwpx_count = len(lines)
    check("HWPX candidates non-empty", hwpx_count > 0, f"count={hwpx_count}")

    # 4. hwp_conversion_plan 존재 및 비어있지 않음
    conv_p = INV_DIR / "hwp_conversion_plan.csv"
    check("hwp_conversion_plan non-empty",
          conv_p.exists() and conv_p.stat().st_size > 50, str(conv_p))

    # 5. HWPX profiler 산출물 존재
    for fname in ["inventory.jsonl", "table_catalog.jsonl", "header_dictionary.csv",
                  "parse_failures.jsonl", "fixture_candidates.json", "summary.md"]:
        p = PROFILE_DIR / fname
        check(f"profiler output: {fname}", p.exists(), str(p))

    # 6. table_catalog 비어있지 않음
    tc_p = PROFILE_DIR / "table_catalog.jsonl"
    tc_count = 0
    if tc_p.exists():
        tc_count = len([l for l in tc_p.read_text(encoding="utf-8").splitlines() if l.strip()])
    check("table_catalog non-empty", tc_count > 0, f"count={tc_count}")

    # 7. header_dictionary 비어있지 않음
    hd_p = PROFILE_DIR / "header_dictionary.csv"
    check("header_dictionary non-empty",
          hd_p.exists() and hd_p.stat().st_size > 50, str(hd_p))

    # 8. parse_failures 존재 (내용 여부 무관, 파일만 있으면 됨)
    pf_p = PROFILE_DIR / "parse_failures.jsonl"
    check("parse_failures file present", pf_p.exists(), str(pf_p))

    # 9. HWP 변환 미실행 — profiler 스크립트에 변환 API 없음
    profiler_src = _read(PROFILER_SCRIPT)
    # 실제 함수 호출 패턴만 검사 (주석/docstring 내 언급은 허용)
    forbidden_calls = ["write_package", "apply_edit_plan", "repair_for_server"]
    for fn in forbidden_calls:
        found = bool(re.search(rf"\b{re.escape(fn)}\s*\(", profiler_src))
        check(f"profiler: no conversion call: {fn}", not found, str(PROFILER_SCRIPT))
    for fn in ["Convert-HwpToHwpx", "HwpToHwpx", "com.haehan"]:
        found = bool(re.search(re.escape(fn), profiler_src))
        check(f"profiler: no conversion call: {fn}", not found, str(PROFILER_SCRIPT))

    # 10. inventory 스크립트에 원본 수정 없음
    inv_src = _read(INVENTORY_SCRIPT)
    for pat in [r"\bshutil\.move\b", r"\bshutil\.copy\b", r"\bos\.rename\b"]:
        found = bool(re.search(pat, inv_src))
        check(f"inventory: no modify op: {pat}", not found, str(INVENTORY_SCRIPT))

    # 11. fixture upgrade candidates 생성 확인
    fuc_p = PROFILE_DIR / "hwpx_fixture_upgrade_candidates.json"
    check("fixture_upgrade_candidates.json present", fuc_p.exists(), str(fuc_p))
    if fuc_p.exists():
        try:
            data = json.loads(fuc_p.read_text(encoding="utf-8"))
            check("fixture_upgrade_candidates non-empty", len(data) > 0, f"count={len(data)}")
        except Exception as e:
            check("fixture_upgrade_candidates valid JSON", False, str(e))

    # 12. hwp_conversion_smoke_candidates.json 존재
    sc_p = INV_DIR / "hwp_conversion_smoke_candidates.json"
    check("hwp_conversion_smoke_candidates.json present", sc_p.exists(), str(sc_p))
    if sc_p.exists():
        try:
            data = json.loads(sc_p.read_text(encoding="utf-8"))
            check("smoke candidates count >= 5", len(data) >= 5, f"count={len(data)}")
        except Exception as e:
            check("smoke candidates valid JSON", False, str(e))

    # 13. 원본 수정 없음 원칙 명시 (inventory 스크립트에 read-only 관련 주석/docstring)
    check("inventory: read-only principle stated",
          "read-only" in inv_src.lower() or "원본" in inv_src or "수정 금지" in inv_src,
          str(INVENTORY_SCRIPT))

    # 14. reports 커밋 제외 원칙 — .gitignore 또는 미추적 확인
    gitignore = PROJECT_ROOT / ".gitignore"
    gi_text = _read(gitignore)
    check("reports/ in .gitignore or convention",
          "reports/" in gi_text or "reports/*" in gi_text,
          str(gitignore))

    failed = [c for c in checks if c["status"] != "PASS"]
    return {
        "status": "PASS" if not failed else "FAIL",
        "checks": checks,
        "pass_count": len(checks) - len(failed),
        "fail_count": len(failed),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = audit()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"[hwp_hwpx_full_inventory_profile audit] {report['status']} "
              f"pass={report['pass_count']} fail={report['fail_count']}")
        for c in report["checks"]:
            mark = "OK" if c["status"] == "PASS" else "FAIL"
            print(f"  [{mark}] {c['name']}")
            if c["status"] != "PASS" and c["detail"]:
                print(f"        detail: {c['detail']}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
