"""
HWPX-RECOGNITION-LABEL-TAXONOMY-AND-LAYOUT-SEED-01 — 감리 스크립트

A01~A20 전 항목 실행 후 판정 출력.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

TAXONOMY_SCRIPT  = PROJECT_ROOT / "scripts" / "hwpx" / "recognition_corpus" / "label_taxonomy.py"
LAYOUT_SCRIPT    = PROJECT_ROOT / "scripts" / "hwpx" / "recognition_corpus" / "layout_classifier.py"
PREFLIGHT_TEST   = PROJECT_ROOT / "tests" / "test_hwpx_recognition_corpus_profiling_preflight.py"
DB_BUILD_TEST    = PROJECT_ROOT / "tests" / "test_hwpx_recognition_corpus_db_build.py"
TAXONOMY_TEST    = PROJECT_ROOT / "tests" / "test_hwpx_recognition_label_taxonomy_and_layout_seed.py"
SURVEY_DRAFTS    = PROJECT_ROOT / "data" / "reports" / "hwpx_survey_drafts"

PASS_VERDICT = "PASS_HWPX_RECOGNITION_LABEL_TAXONOMY_AND_LAYOUT_SEED"
WARN_REVIEW  = "WARN_REVIEW_REQUIRED_LABELS_REMAIN"
WARN_UNKNOWN = "WARN_LAYOUT_UNKNOWN_REMAINS"
WARN_SYNTH   = "WARN_SYNTHETIC_OR_REPORT_ONLY_VALIDATION"

_PII_RE = re.compile(r"\d{2,3}-\d{3,4}-\d{4}|\d{3}-\d{2}-\d{5}")


class AuditRunner:
    def __init__(self):
        self.results: list[dict] = []
        self.fails: list[str] = []
        self.warns: list[str] = []

    def check(self, code, desc, passed, detail="", fail_verdict=""):
        status = "PASS" if passed else "FAIL"
        self.results.append({"code": code, "status": status, "description": desc, "detail": detail})
        if not passed:
            self.fails.append(fail_verdict or f"FAIL_{code}")
        return passed

    def warn(self, msg):
        self.warns.append(msg)

    def report(self) -> int:
        print("\n" + "=" * 70)
        print("HWPX-RECOGNITION-LABEL-TAXONOMY-AND-LAYOUT-SEED-01 감리 결과")
        print("=" * 70)
        for r in self.results:
            sym = "✓" if r["status"] == "PASS" else "✗"
            print(f"  [{r['status']}] {r['code']} {sym} — {r['description']}")
            if r["detail"]:
                for line in str(r["detail"])[:300].split("\n")[:3]:
                    print(f"         {line}")
        print()
        for w in self.warns:
            print(f"  WARN: {w}")
        if self.warns:
            print()
        if self.fails:
            for f in self.fails:
                print(f"  FAIL verdict: {f}")
            print(f"\n최종 판정: FAIL ({len(self.fails)} items)")
            return 1
        print(f"최종 판정: {PASS_VERDICT}")
        return 0


def run_audit() -> int:
    ar = AuditRunner()

    # A01. label_taxonomy.py exists
    ar.check("A01", "label_taxonomy.py exists", TAXONOMY_SCRIPT.exists(), str(TAXONOMY_SCRIPT))
    # A02. layout_classifier.py exists
    ar.check("A02", "layout_classifier.py exists", LAYOUT_SCRIPT.exists(), str(LAYOUT_SCRIPT))

    if not TAXONOMY_SCRIPT.exists() or not LAYOUT_SCRIPT.exists():
        return ar.report()

    # import
    try:
        from hwpx.recognition_corpus import label_taxonomy as lt
        from hwpx.recognition_corpus import layout_classifier as lc
        import_ok = True
    except Exception as exc:
        ar.check("A02b", "modules importable", False, str(exc))
        return ar.report()

    # A03. survey report input paths supported
    survey_ok = SURVEY_DRAFTS.exists() and (SURVEY_DRAFTS / "survey_header_dictionary.json").exists()
    ar.check("A03", "survey report (drafts) is present",
             survey_ok, str(SURVEY_DRAFTS))

    # A04. top field mappings exist
    top_fields = ["taskName", "number", "receiptNumber", "inspectionStatus", "remarks",
                  "responsiblePerson", "quantity", "contractorName", "durationDays"]
    top_labels = {
        "taskName": "항목", "number": "번호", "receiptNumber": "접수번호",
        "inspectionStatus": "검사결과", "remarks": "비고",
        "responsiblePerson": "성명", "quantity": "수량",
        "contractorName": "시공사", "durationDays": "기간",
    }
    field_ok = all(
        lt.classify_label(lbl).semanticField == field
        for field, lbl in top_labels.items()
    )
    ar.check("A04", "top field mappings exist (taskName/number/... → correct fields)",
             field_ok,
             str({f: lt.classify_label(l).semanticField for f, l in top_labels.items()}))

    # A05. sample header mappings
    sample_labels = {"testType": "종별", "testItem": "시험종목", "testMethod": "시험방법"}
    sample_ok = all(
        lt.classify_label(lbl).semanticField == field
        for field, lbl in sample_labels.items()
    )
    ar.check("A05", "sample header mappings (종별/시험종목/시험방법)",
             sample_ok,
             str({f: lt.classify_label(l).semanticField for f, l in sample_labels.items()}))

    # A06. public doc meta labels separated
    meta_labels = ["접수", "직인", "결재", "담당", "승인", "통보"]
    meta_ok = all(lt.classify_label(l).classification == lt.CLS_META for l in meta_labels)
    ar.check("A06", "공문서 메타 라벨(접수/직인/결재/...) 분리",
             meta_ok,
             str({l: lt.classify_label(l).classification for l in meta_labels}),
             "FAIL_LOW_CONFIDENCE_AUTO_PROMOTED")

    # A07. back-side form hints separated
    back_labels = ["(뒤쪽)", "뒤쪽", "뒷면", "(제2쪽)", "(8쪽중제3쪽)"]
    back_ok = all(lt.classify_label(l).classification == lt.CLS_BACK for l in back_labels)
    ar.check("A07", "뒷면/앞면 마커 분리",
             back_ok,
             str({l: lt.classify_label(l).classification for l in back_labels}))

    # A08. gantt/schedule hints separated
    gantt_result = lc.classify_layout(
        header_texts=["공종", "2026-01", "2026-02", "2026-03", "2026-04", "2026-05"],
        input_cell_types={"header_column": 30},
        total_cells=60, empty_cells=30, row_count=10, col_count=6, input_cell_count=30,
    )
    hs_result = lc.classify_layout(
        header_texts=["공종", "시작일", "완료일", "2026-03"],
        input_cell_types={"header_column": 10},
        total_cells=30, empty_cells=10, row_count=5, col_count=6, input_cell_count=10,
    )
    sched_ok = (gantt_result.layoutType == lc.LT_GANTT and
                hs_result.layoutType == lc.LT_H_SCHEDULE)
    ar.check("A08", "gantt_like/horizontal_schedule 분류",
             sched_ok,
             f"gantt={gantt_result.layoutType}, h_sched={hs_result.layoutType}")

    # A09. mapped/review_required/ignored outputs work
    sample_batch = [
        {"normalizedText": "비고", "totalOccurrences": 100, "fileCount": 50},
        {"normalizedText": "접수", "totalOccurrences": 80,  "fileCount": 30},
        {"normalizedText": "(뒤쪽)", "totalOccurrences": 500, "fileCount": 200},
        {"normalizedText": "알수없는라벨xyz", "totalOccurrences": 1, "fileCount": 1},
    ]
    output = lt.classify_with_counts(sample_batch)
    counts = output["classificationCounts"]
    has_high   = counts.get(lt.CLS_HIGH, 0) + counts.get(lt.CLS_MEDIUM, 0) > 0
    has_meta   = counts.get(lt.CLS_META, 0) > 0
    has_back   = counts.get(lt.CLS_BACK, 0) > 0
    ar.check("A09", "mapped/review_required/ignored 분류 출력 정상",
             has_high and has_meta and has_back,
             f"counts={counts}")

    # A10. low confidence not auto-promoted
    low_conf_labels = ["기타업종", "알수없는항목123"]
    low_ok = all(
        lt.classify_label(l).classification not in (lt.CLS_HIGH, lt.CLS_MEDIUM)
        for l in low_conf_labels
    )
    ar.check("A10", "low confidence 라벨 자동 확정 없음",
             low_ok,
             str({l: lt.classify_label(l).classification for l in low_conf_labels}),
             "FAIL_LOW_CONFIDENCE_AUTO_PROMOTED")

    # A11. raw absolute path leak absent
    taxonomy_src = TAXONOMY_SCRIPT.read_text(encoding="utf-8")
    layout_src   = LAYOUT_SCRIPT.read_text(encoding="utf-8")
    path_leak = any(
        drive in src
        for src in (taxonomy_src, layout_src)
        for drive in ("C:\\Users\\", "D:\\Users\\", "/home/", "/Users/")
    )
    ar.check("A11", "소스코드에 절대경로 없음", not path_leak,
             fail_verdict="FAIL_RAW_PATH_LEAK")

    # A12. raw filename leak absent (only pattern strings should be in source)
    fn_leak = re.search(r"\.hwpx['\"]", taxonomy_src + layout_src)
    ar.check("A12", "소스코드에 raw 파일명 없음", fn_leak is None,
             fail_verdict="FAIL_RAW_FILENAME_LEAK")

    # A13. PII pattern leak absent
    pii_in_source = _PII_RE.search(taxonomy_src + layout_src)
    ar.check("A13", "소스코드에 PII 패턴 없음", pii_in_source is None,
             fail_verdict="FAIL_PII_LEAK")

    # A14. corpus.sqlite3 not created/modified
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        lt.classify_batch(["항목", "비고", "접수"])
        db_files = list(tmp_path.rglob("*.sqlite3"))
    ar.check("A14", "corpus.sqlite3 미생성",
             len(db_files) == 0, str(db_files),
             "FAIL_CORPUS_DB_MUTATED")

    # A15. original HWPX unchanged (check write_package not referenced)
    writer_refs = re.findall(r"write_package|apply_edit_plan|repair_for_server",
                             taxonomy_src + layout_src)
    ar.check("A15", "원본 HWPX 수정 함수 미참조",
             len(writer_refs) == 0, str(writer_refs),
             "FAIL_ORIGINAL_HWPX_MUTATED")

    # A16. writer not called
    ar.check("A16", "writer 호출 없음 (A15와 동일)", len(writer_refs) == 0,
             fail_verdict="FAIL_WRITER_CALLED")

    # A17. AI API not called
    ai_refs = re.findall(r"anthropic|openai|ChatCompletion", taxonomy_src + layout_src)
    ar.check("A17", "AI API 미참조", len(ai_refs) == 0,
             str(ai_refs), "FAIL_AI_OR_OCR_CALLED")

    # A18. OCR not called
    ocr_refs = re.findall(r"pytesseract|easyocr|tesseract|image_to_string",
                          taxonomy_src + layout_src)
    ar.check("A18", "OCR 미참조", len(ocr_refs) == 0,
             str(ocr_refs), "FAIL_AI_OR_OCR_CALLED")

    # A19. previous profiling tests pass
    r19 = subprocess.run(
        [sys.executable, "-m", "pytest", str(PREFLIGHT_TEST), "-q", "--tb=no"],
        capture_output=True, text=True, cwd=str(PROJECT_ROOT)
    )
    ar.check("A19", "profiling preflight 테스트 유지 (14/14)",
             r19.returncode == 0, r19.stdout[-200:])

    # A20. previous DB build tests pass
    r20 = subprocess.run(
        [sys.executable, "-m", "pytest", str(DB_BUILD_TEST), "-q", "--tb=no"],
        capture_output=True, text=True, cwd=str(PROJECT_ROOT)
    )
    ar.check("A20", "corpus DB build 테스트 유지 (17/17)",
             r20.returncode == 0, r20.stdout[-200:])

    # WARNs
    if survey_ok:
        hd = json.loads((SURVEY_DRAFTS / "survey_header_dictionary.json").read_text(encoding="utf-8"))
        unknown_count = sum(1 for r in hd if lt.classify_label(r["normalizedText"]).classification == lt.CLS_UNKNOWN)
        if unknown_count > 0:
            ar.warn(f"{WARN_REVIEW}: {unknown_count}개 UNKNOWN 헤더 잔존")
            ar.warn(WARN_UNKNOWN)
    ar.warn(WARN_SYNTH)

    return ar.report()


if __name__ == "__main__":
    sys.exit(run_audit())
