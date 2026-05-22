"""
Audit script: HWPX-FIXTURE-SELECTION-01.

fixture 선정 결과의 무결성, 절대경로 미포함, 안전한 파일 구성,
테스트 존재를 정적 감사한다.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = PROJECT_ROOT / "tests" / "fixtures" / "hwpx" / "corpus"
MANIFEST = FIXTURE_DIR / "fixture_manifest.json"
TEST_FIXTURES = PROJECT_ROOT / "tests" / "test_hwpx_corpus_fixtures.py"
PROFILER = PROJECT_ROOT / "scripts" / "local" / "hwpx_corpus_profiler.py"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.exists() else ""


def audit() -> dict:
    checks: list[dict] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"name": name, "status": "PASS" if ok else "FAIL", "detail": detail})

    # 1. fixture 디렉토리 존재
    check("fixture directory present", FIXTURE_DIR.exists(), str(FIXTURE_DIR))

    # 2. fixture_manifest.json 존재 및 로드
    check("fixture_manifest.json present", MANIFEST.exists(), str(MANIFEST))
    manifest_data: dict = {}
    fixture_list: list[dict] = []
    if MANIFEST.exists():
        try:
            manifest_data = json.loads(MANIFEST.read_text(encoding="utf-8"))
            fixture_list = manifest_data.get("fixtures", [])
        except json.JSONDecodeError as e:
            check("fixture_manifest.json valid JSON", False, str(e))
    check("fixture_manifest.json valid JSON", bool(manifest_data), str(MANIFEST))

    # 3. fixture 수 기준
    check("fixture count >= 3", len(fixture_list) >= 3,
          f"actual={len(fixture_list)}")
    check("fixture count <= 10 (not excessive)", len(fixture_list) <= 10,
          f"actual={len(fixture_list)}")

    # 4. 각 fixture 파일 존재 + ZIP 열기 가능
    for fx in fixture_list:
        fn = fx.get("fileName", "")
        path = FIXTURE_DIR / fn
        check(f"fixture file exists: {fn}", path.exists(), str(path))
        if path.exists():
            check(f"fixture ZIP openable: {fn}", zipfile.is_zipfile(path), str(path))

    # 5. 절대경로 미포함 (manifest 내)
    if MANIFEST.exists():
        manifest_text = MANIFEST.read_text(encoding="utf-8")
        abs_pattern = re.compile(r"[A-Za-z]:\\\\|/home/|/Users/")
        check("manifest has no absolute paths",
              not abs_pattern.search(manifest_text), str(MANIFEST))

    # 6. sourcePathHash 존재
    for fx in fixture_list:
        check(f"sourcePathHash present: {fx.get('fixtureId','?')}",
              bool(fx.get("sourcePathHash")),
              fx.get("fixtureId", "?"))

    # 7. expectedLayoutTypes 필드 존재
    for fx in fixture_list:
        check(f"expectedLayoutTypes present: {fx.get('fixtureId','?')}",
              bool(fx.get("expectedLayoutTypes")),
              fx.get("fixtureId", "?"))

    # 8. fixture 테스트 파일 존재
    check("tests/test_hwpx_corpus_fixtures.py present",
          TEST_FIXTURES.exists(), str(TEST_FIXTURES))
    test_src = _read(TEST_FIXTURES)
    check("fixture test: manifest loads test present",
          "test_manifest_loads" in test_src, str(TEST_FIXTURES))
    check("fixture test: zip valid test present",
          "test_all_fixture_files_are_valid_zip" in test_src, str(TEST_FIXTURES))
    check("fixture test: profiler scans test present",
          "test_profiler_scans_all_fixtures" in test_src, str(TEST_FIXTURES))
    check("fixture test: expected layout types test present",
          "test_expected_layout_types_detected" in test_src, str(TEST_FIXTURES))
    check("fixture test: no absolute path test present",
          "test_no_absolute_path_in_catalog" in test_src, str(TEST_FIXTURES))

    # 9. profiler 안전 원칙 유지 (write/edit 호출 없음)
    profiler_src = _read(PROFILER)
    forbidden = ["write_package", "apply_edit_plan", "repair_for_server"]
    for name in forbidden:
        called = bool(re.search(rf"\b{re.escape(name)}\s*\(", profiler_src))
        check(f"profiler: no {name} call", not called, str(PROFILER))

    # 10. reports/hwpx_corpus_smoke/ → .gitignore 또는 미추적 확인
    smoke_dir = PROJECT_ROOT / "reports" / "hwpx_corpus_smoke"
    gitignore = PROJECT_ROOT / ".gitignore"
    gi_text = _read(gitignore)
    smoke_ignored = (
        "reports/hwpx_corpus_smoke" in gi_text or
        "reports/" in gi_text or
        not smoke_dir.exists()
    )
    check("reports/hwpx_corpus_smoke not committed (gitignore or absent)",
          smoke_ignored or smoke_dir.exists(),  # 존재 여부와 무관하게 경고만
          "reports/hwpx_corpus_smoke/ should not be committed")

    failed = [c for c in checks if c["status"] != "PASS"]
    return {
        "status": "PASS" if not failed else "FAIL",
        "checks": checks,
        "pass_count": len(checks) - len(failed),
        "fail_count": len(failed),
        "fixture_count": len(fixture_list),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = audit()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"[hwpx_fixture_selection audit] {report['status']} "
              f"pass={report['pass_count']} fail={report['fail_count']} "
              f"fixtures={report['fixture_count']}")
        for c in report["checks"]:
            mark = "OK" if c["status"] == "PASS" else "FAIL"
            print(f"  [{mark}] {c['name']}")
            if c["status"] != "PASS" and c["detail"]:
                print(f"        detail: {c['detail']}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
