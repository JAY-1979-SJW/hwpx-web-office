"""
Audit script: HWPX-CORPUS-PROFILER-LOCAL-INVENTORY-01 (+ HEADER-NORMALIZER-IMPROVE-01).

profiler가 read-only 원칙을 지키는지, 모든 출력 로직이 존재하는지,
헤더 정규화 보강이 적용됐는지, 테스트가 갖춰져 있는지를 정적 감사한다.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROFILER = PROJECT_ROOT / "scripts" / "local" / "hwpx_corpus_profiler.py"
TEST = PROJECT_ROOT / "tests" / "test_hwpx_corpus_profiler.py"
TEST_NORMALIZER = PROJECT_ROOT / "tests" / "test_hwpx_header_normalizer.py"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.exists() else ""


def audit() -> dict:
    src = _read(PROFILER)
    test_src = _read(TEST)
    checks: list[dict] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"name": name, "status": "PASS" if ok else "FAIL", "detail": detail})

    # 1. profiler 존재
    check("hwpx_corpus_profiler.py present", PROFILER.exists(), str(PROFILER))

    # 2~5. 금지 호출 없음 — 호출 패턴(`name(`)만 검사, docstring/주석의 단순 언급은 허용
    forbidden = ["write_package", "apply_edit_plan", "repair_for_server", "repair_hwpx_spine"]
    for name in forbidden:
        # name( 또는 name (  형태의 호출만 차단
        called = bool(re.search(rf"\b{re.escape(name)}\s*\(", src))
        check(f"no {name} call in profiler", not called, "scripts/local/hwpx_corpus_profiler.py")

    # 6. read-only 원칙 — ZipFile를 'w'/'a' 모드로 여는 호출이 없어야 함
    write_mode_pattern = re.search(r'zipfile\.ZipFile\([^)]*,\s*["\'][wa]["\']', src)
    check("no zipfile write/append open on input", write_mode_pattern is None,
          "scripts/local/hwpx_corpus_profiler.py")

    # 7~13. 출력 로직 함수 존재
    output_markers = [
        ("inventory.csv", '"inventory.csv"'),
        ("inventory.jsonl", '"inventory.jsonl"'),
        ("package_summary.jsonl", '"package_summary.jsonl"'),
        ("parse_summary.jsonl", '"parse_summary.jsonl"'),
        ("table_catalog.jsonl", '"table_catalog.jsonl"'),
        ("header_dictionary.csv", '"header_dictionary.csv"'),
        ("schedule_candidates.jsonl", '"schedule_candidates.jsonl"'),
        ("parse_failures.jsonl", '"parse_failures.jsonl"'),
        ("fixture_candidates.json", '"fixture_candidates.json"'),
        ("summary.md", '"summary.md"'),
    ]
    for label, needle in output_markers:
        check(f"writes {label}", needle in src, "scripts/local/hwpx_corpus_profiler.py")

    # 14. inspect_package / detect_schedule / select_fixture_candidates 정의 존재
    for fn in ("def inspect_package", "def discover_hwpx", "def detect_schedule_candidate",
               "def select_fixture_candidates", "def classify_table_layout", "def guess_field"):
        check(f"function defined: {fn[4:]}", fn in src, "scripts/local/hwpx_corpus_profiler.py")

    # 15. CLI 옵션 존재
    for opt in ("--root", "--out", "--max-files", "--anonymize-paths", "--fail-fast",
                "--include-hidden", "--copy-fixtures"):
        check(f"CLI option: {opt}", opt in src, "scripts/local/hwpx_corpus_profiler.py")

    # 16. profiler 테스트 존재
    check("regression test file present", TEST.exists(), str(TEST))
    for fn in ("test_empty_root_scan_produces_reports",
               "test_single_valid_hwpx_scan",
               "test_broken_zip_handled",
               "test_broken_mimetype_recorded_as_warning",
               "test_table_catalog_generated",
               "test_header_dictionary_generated",
               "test_schedule_candidate_detected",
               "test_scan_continues_after_failure",
               "test_anonymize_paths_removes_relative_paths",
               "test_jsonl_csv_outputs_are_well_formed"):
        check(f"test case present: {fn}", f"def {fn}" in test_src, str(TEST))

    # 17. copy_fixtures 비활성 (안내 메시지만)
    check("copy_fixtures explicitly disabled at this stage",
          "copy-fixtures requested but disabled" in src or "copy_fixtures requested but disabled" in src,
          "scripts/local/hwpx_corpus_profiler.py")

    # 18~22. 헤더 정규화 보강 (HEADER-NORMALIZER-IMPROVE-01)
    check("normalizer: korean inter-char space removal present",
          r"가-힣" in src and "normalize_header" in src,
          "scripts/local/hwpx_corpus_profiler.py")
    check("FIELD_HINTS: receiptNumber present",
          '"receiptNumber"' in src,
          "scripts/local/hwpx_corpus_profiler.py")
    check("FIELD_HINTS: gasName present",
          '"gasName"' in src,
          "scripts/local/hwpx_corpus_profiler.py")
    check("FIELD_HINTS: nominalDiameter present",
          '"nominalDiameter"' in src,
          "scripts/local/hwpx_corpus_profiler.py")
    check("FIELD_HINTS: remarks present",
          '"remarks"' in src,
          "scripts/local/hwpx_corpus_profiler.py")

    # 23. 정규화 테스트 파일 존재
    norm_test_src = _read(TEST_NORMALIZER)
    check("normalizer test file present", TEST_NORMALIZER.exists(), str(TEST_NORMALIZER))
    check("normalizer test: roundtrip_spaced_korean_to_field present",
          "test_roundtrip_spaced_korean_to_field" in norm_test_src,
          str(TEST_NORMALIZER))
    check("normalizer test: receiptNumber roundtrip present",
          "receiptNumber" in norm_test_src,
          str(TEST_NORMALIZER))

    # 24~33. Full Table Parser / Layout Classifier (FULL-TABLE-PARSER-IMPROVE-01)
    TEST_CLASSIFIER = PROJECT_ROOT / "tests" / "test_hwpx_table_layout_classifier.py"
    cls_test_src = _read(TEST_CLASSIFIER)
    check("table layout classifier test file present",
          TEST_CLASSIFIER.exists(), str(TEST_CLASSIFIER))
    new_categories = [
        "page_marker_table", "stamp_or_approval_table", "metadata_table",
        "legal_complex_table", "nested_container_table", "layout_noise",
    ]
    for cat in new_categories:
        check(f"new layout category present: {cat}", f'"{cat}"' in src,
              "scripts/local/hwpx_corpus_profiler.py")
    check("classificationEvidence output present",
          '"classificationEvidence"' in src,
          "scripts/local/hwpx_corpus_profiler.py")
    check("labelValuePairScore field present",
          '"labelValuePairScore"' in src,
          "scripts/local/hwpx_corpus_profiler.py")
    check("approvalStampScore field present",
          '"approvalStampScore"' in src,
          "scripts/local/hwpx_corpus_profiler.py")
    check("pageMarkerScore field present",
          '"pageMarkerScore"' in src,
          "scripts/local/hwpx_corpus_profiler.py")
    check("nestedTableCount field present",
          '"nestedTableCount"' in src,
          "scripts/local/hwpx_corpus_profiler.py")
    check("_compute_table_scores helper present",
          "def _compute_table_scores" in src,
          "scripts/local/hwpx_corpus_profiler.py")
    check("classifier test: page_marker_table test present",
          "test_page_marker_table_detected" in cls_test_src,
          str(TEST_CLASSIFIER))
    check("classifier test: stamp_or_approval_table test present",
          "test_stamp_or_approval_table" in cls_test_src,
          str(TEST_CLASSIFIER))
    check("classifier test: metadata_table test present",
          "test_metadata_table_detected" in cls_test_src,
          str(TEST_CLASSIFIER))

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
        print(f"[hwpx_corpus_profiler audit] {report['status']} "
              f"pass={report['pass_count']} fail={report['fail_count']}")
        for c in report["checks"]:
            mark = "OK" if c["status"] == "PASS" else "FAIL"
            print(f"  [{mark}] {c['name']}")
            if c["status"] != "PASS" and c["detail"]:
                print(f"        detail: {c['detail']}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
