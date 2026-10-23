"""HWPX-GANTT-LIKE-FIXTURE-SELECTION-01 감사 스크립트.

12개 항목을 검사한다.
"""
from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = PROJECT_ROOT / "tests" / "fixtures" / "hwpx" / "gantt"
MANIFEST_PATH = FIXTURE_DIR / "gantt_fixture_manifest.json"
TESTS_DIR = PROJECT_ROOT / "tests"

results: list[tuple[str, str, str]] = []


def check(cid: str, desc: str, passed: bool, detail: str = "") -> None:
    status = "PASS" if passed else f"FAIL {detail}".strip()
    results.append((cid, desc, status))


# ── 매니페스트 ─────────────────────────────────────────────────────────────────
manifest_ok = MANIFEST_PATH.exists()
manifest: dict = {}
if manifest_ok:
    try:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except Exception:
        manifest_ok = False

check("C01", "gantt_fixture_manifest.json 존재", manifest_ok)
check("C02", "매니페스트 schemaVersion == '1'",
      manifest.get("schemaVersion") == "1")
check("C03", "매니페스트 fixtures 3개",
      len(manifest.get("fixtures", [])) == 3)

# ── 픽스처 파일 존재 ───────────────────────────────────────────────────────────
fx_names = [fx["fixtureName"] for fx in manifest.get("fixtures", [])]
fx_paths = [FIXTURE_DIR / n for n in fx_names]
all_exist = all(p.exists() for p in fx_paths)
check("C04", "3개 픽스처 .hwpx 파일 존재", all_exist,
      str([n for n, p in zip(fx_names, fx_paths) if not p.exists()]))

# ── ZIP 유효성 ────────────────────────────────────────────────────────────────
zip_ok_all = True
stored_all = True
for p in fx_paths:
    if not p.exists():
        zip_ok_all = False
        stored_all = False
        continue
    try:
        with zipfile.ZipFile(p) as z:
            names = z.namelist()
            if "mimetype" not in names:
                zip_ok_all = False
            info = z.getinfo("mimetype") if "mimetype" in names else None
            if info and info.compress_type != 0:
                stored_all = False
    except Exception:
        zip_ok_all = False
        stored_all = False

check("C05", "3개 픽스처 ZIP 유효 (mimetype 포함)", zip_ok_all)
check("C06", "mimetype ZIP_STORED (compress_type=0)", stored_all)

# ── 매니페스트 fixtureDecision ─────────────────────────────────────────────────
all_safe = all(
    fx.get("fixtureDecision") == "SAFE_FOR_FIXTURE"
    for fx in manifest.get("fixtures", [])
)
check("C07", "모든 픽스처 fixtureDecision == SAFE_FOR_FIXTURE", all_safe)

# ── 구조 정보 ─────────────────────────────────────────────────────────────────
all_7x6 = all(
    fx.get("rowCount") == 7 and fx.get("colCount") == 6
    for fx in manifest.get("fixtures", [])
)
check("C08", "모든 픽스처 7×6 구조 명시", all_7x6)

expected_header = ["공종", "기간", "5월", "6월", "7월", "진척률"]
all_header = all(
    fx.get("header") == expected_header
    for fx in manifest.get("fixtures", [])
)
check("C09", "모든 픽스처 header ['공종','기간','5월','6월','7월','진척률']", all_header)

# ── barType 다양성 ─────────────────────────────────────────────────────────────
bar_types = {fx.get("barType") for fx in manifest.get("fixtures", [])}
check("C10", "barType 다양성 (최소 2종)", len(bar_types) >= 2,
      f"found: {bar_types}")

# ── 테스트 파일 존재 ───────────────────────────────────────────────────────────
test_path = TESTS_DIR / "test_hwpx_gantt_like_fixtures.py"
test_src = test_path.read_text(encoding="utf-8") if test_path.exists() else ""
check("C11", "test_hwpx_gantt_like_fixtures.py 존재",
      test_path.exists() and len(test_src) > 300)

# ── 테스트 핵심 항목 ───────────────────────────────────────────────────────────
check("C12", "테스트 gantt_table 구조 검증 포함",
      "EXPECTED_HEADER" in test_src and "EXPECTED_TASKS" in test_src)

# ── 선정 보고서 존재 ───────────────────────────────────────────────────────────
report_path = PROJECT_ROOT / "docs" / "reports" / "hwpx_gantt_like_fixture_selection_20260517.md"
report_src = report_path.read_text(encoding="utf-8") if report_path.exists() else ""
check("C13", "선정 보고서 docs/reports/hwpx_gantt_like_fixture_selection_20260517.md 존재",
      report_path.exists() and len(report_src) > 300)

# ── 결과 출력 ─────────────────────────────────────────────────────────────────
pass_count = sum(1 for _, _, s in results if s == "PASS")
fail_count = len(results) - pass_count

print(f"\n{'='*64}")
print("HWPX-GANTT-LIKE-FIXTURE-SELECTION-01 감사 결과")
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
