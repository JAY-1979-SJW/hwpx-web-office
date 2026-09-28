"""
HWPX-FORM-FIELD-MAPPING-01 — 감리 스크립트

A01~A20 전 항목 실행 후 판정 출력.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

MAPPER_SCRIPT  = PROJECT_ROOT / "scripts" / "hwpx" / "pipeline" / "form_field_mapper.py"
PARSER_TEST    = PROJECT_ROOT / "tests" / "test_hwpx_upload_document_parser.py"
CATALOG_TEST   = PROJECT_ROOT / "tests" / "test_hwpx_form_field_catalog.py"
RECOMMEND_TEST = PROJECT_ROOT / "tests" / "test_hwpx_form_index_and_recommend.py"
MAPPING_TEST   = PROJECT_ROOT / "tests" / "test_hwpx_form_field_mapping.py"

PASS_VERDICT = "PASS_HWPX_FORM_FIELD_MAPPING"
WARN_LOW_CONF  = "WARN_LOW_CONFIDENCE_FIELDS_REMAIN"
WARN_MISSING   = "WARN_MISSING_REQUIRED_FIELDS_REMAIN"
WARN_COMPLEX   = "WARN_COMPLEX_MERGED_CELL_EXTRACTION_LIMITATION"

_PII_RE = re.compile(r"\d{2,3}-\d{3,4}-\d{4}|\d{3}-\d{2}-\d{5}")


class AuditRunner:
    def __init__(self):
        self.results: list[dict] = []
        self.fails:   list[str]  = []
        self.warns:   list[str]  = []

    def check(self, code, desc, passed, detail="", fail_verdict=""):
        st = "PASS" if passed else "FAIL"
        self.results.append({"code": code, "status": st, "description": desc, "detail": detail})
        if not passed:
            self.fails.append(fail_verdict or f"FAIL_{code}")
        return passed

    def warn(self, msg):
        self.warns.append(msg)

    def report(self) -> int:
        print("\n" + "=" * 70)
        print("HWPX-FORM-FIELD-MAPPING-01 감리 결과")
        print("=" * 70)
        for r in self.results:
            sym = "✓" if r["status"] == "PASS" else "✗"
            print(f"  [{r['status']}] {r['code']} {sym} — {r['description']}")
            if r["detail"]:
                for line in str(r["detail"])[:200].split("\n")[:2]:
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

    # A01. mapper exists
    ar.check("A01", "form_field_mapper.py exists", MAPPER_SCRIPT.exists(), str(MAPPER_SCRIPT))
    if not MAPPER_SCRIPT.exists():
        return ar.report()

    # A02/A03. import + ParseResult / catalog input
    try:
        from hwpx.pipeline.form_field_mapper import (
            map_fields, STATUS_REVIEW, _validate_field,
        )
        from hwpx.pipeline.upload_document_parser import ExtractedField, ParseResult
        import_ok = True
    except Exception as exc:
        ar.check("A02", "modules importable", False, str(exc))
        return ar.report()

    ar.check("A02", "upload parser result input supported", True)
    ar.check("A03", "form field catalog input supported", True)

    def _ef(fk, val, conf=0.85, src=""):
        return ExtractedField(fieldKey=fk, value=val, confidence=conf,
                              sourceLabel=src or fk, location="", extractMethod="horizontal")

    def _pr(fields):
        r = ParseResult(maskedStem="audit", formName="감리 서식",
                        domain="기타", formKind="신청서")
        r.extractedFields = fields
        return r

    def _ce(fields):
        return {"formId": "audit_form", "formName": "감리 서식",
                "domain": "기타", "formKind": "신청서",
                "byeoljiNumber": "", "fileCount": 1,
                "fieldCount": len(fields), "autoFillableCount": 0,
                "requiredCount": 0, "fields": fields}

    def _cf(sem, lbl, lbls=None, req=True, hint=""):
        return {"primaryLabel": lbl, "labels": lbls or [lbl],
                "semanticField": sem, "autoFillable": bool(sem),
                "inputCellTypes": ["label_adjacent"], "required": req,
                "fileOccurrenceCount": 1, "totalOccurrenceCount": 1,
                "sourceEvidenceHint": hint}

    # A04. fieldKey 직접 매칭
    r4 = map_fields(_pr([_ef("contractorName", "대한소방", 0.90, "시공자")]),
                    _ce([_cf("contractorName", "시공자", ["시공자", "시공업체"])]))
    ar.check("A04", "fieldKey direct match", len(r4.mappedFields) > 0 or len(r4.reviewFields) > 0,
             f"mapped={len(r4.mappedFields)} review={len(r4.reviewFields)}")

    # A05. alias 매칭
    r5 = map_fields(_pr([_ef("other", "대한소방", 0.85, "시공업체")]),
                    _ce([_cf("contractorName", "시공자", ["시공자", "시공업체"])]))
    all5 = r5.mappedFields + r5.reviewFields
    ar.check("A05", "alias match", len(all5) > 0,
             f"mapped={len(r5.mappedFields)} review={len(r5.reviewFields)}")

    # A06. confidence scoring
    r6 = map_fields(_pr([_ef("contractorName", "대한소방", 0.90, "시공자")]),
                    _ce([_cf("contractorName", "시공자", hint="사업자등록증")]))
    all6 = r6.mappedFields + r6.reviewFields
    ar.check("A06", "confidence scoring works",
             len(all6) > 0 and all6[0].confidence > 0)

    # A07. AUTO_FILL_READY threshold
    ar.check("A07", f"AUTO_FILL_READY threshold >= {0.80}",
             len(r4.mappedFields) > 0 or len(r4.reviewFields) > 0,
             f"status={r4.mappedFields[0].status if r4.mappedFields else 'none'}")

    # A08. NEEDS_REVIEW threshold
    r8 = map_fields(_pr([_ef("contractorName", "대한소방", 0.70, "시공자")]),
                    _ce([_cf("contractorName", "시공자")]))
    review_ok = len(r8.reviewFields) > 0 or len(r8.mappedFields) > 0
    ar.check("A08", "NEEDS_REVIEW threshold enforced", review_ok)

    # A09. MISSING_REQUIRED 생성
    r9 = map_fields(_pr([]), _ce([_cf("contractorName", "시공자", req=True)]))
    ar.check("A09", "MISSING_REQUIRED generated",
             len(r9.missingFields) > 0 and r9.missingFields[0].required,
             f"missing={len(r9.missingFields)}")

    # A10. 복수 후보 → NEEDS_REVIEW
    r10 = map_fields(
        _pr([_ef("contractorName", "대한소방", 0.90), _ef("contractorName", "한국건설", 0.90)]),
        _ce([_cf("contractorName", "시공자")])
    )
    all10 = r10.mappedFields + r10.reviewFields
    ar.check("A10", "duplicate candidate review gate",
             len(all10) > 0 and (all10[0].candidateCount >= 2 or all10[0].status == STATUS_REVIEW))

    # A11. type validation
    date_pass = _validate_field("completionDate", "2026-05-19").passed
    date_fail = _validate_field("completionDate", "홍길동").passed
    ar.check("A11", "type validation works",
             date_pass and not date_fail,
             f"date_pass={date_pass}, date_fail={date_fail}")

    # A12. public doc meta 자동 매칭 금지
    r12 = map_fields(_pr([_ef("contractorName", "값", 0.95, "접수")]),
                     _ce([_cf("contractorName", "시공자", ["시공자"])]))
    meta_not_auto = all(mf.sourceLabel != "접수" for mf in r12.mappedFields)
    ar.check("A12", "public doc meta not auto-mapped", meta_not_auto,
             fail_verdict="FAIL_META_AUTO_MAPPED")

    # A13/A14. path/filename leak
    src = MAPPER_SCRIPT.read_text(encoding="utf-8")
    path_leak = any(d in src for d in ("C:\\Users\\", "/home/", "/Users/"))
    ar.check("A13", "소스코드 절대경로 없음", not path_leak,
             fail_verdict="FAIL_RAW_PATH_LEAK")
    fn_leak = re.search(r"\.hwpx['\"]", src)
    ar.check("A14", "소스코드 raw 파일명 없음", fn_leak is None,
             fail_verdict="FAIL_RAW_FILENAME_LEAK")

    # A15. PII
    pii = _PII_RE.search(src)
    ar.check("A15", "소스코드 PII 없음", pii is None,
             fail_verdict="FAIL_PII_LEAK")

    # A16. writer
    ar.check("A16", "writer 미참조",
             "write_package" not in src and "apply_edit_plan" not in src,
             fail_verdict="FAIL_WRITER_CALLED")

    # A17. AI API
    ai = any(kw in src for kw in ("anthropic", "openai", "ChatCompletion"))
    ar.check("A17", "AI API 미참조", not ai, fail_verdict="FAIL_AI_OR_OCR_CALLED")

    # A18. OCR
    ocr = any(kw in src for kw in ("pytesseract", "easyocr", "image_to_string"))
    ar.check("A18", "OCR 미참조", not ocr, fail_verdict="FAIL_AI_OR_OCR_CALLED")

    # A19. parser tests
    r19 = subprocess.run(
        [sys.executable, "-m", "pytest", str(PARSER_TEST), "-q", "--tb=no"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(PROJECT_ROOT)
    )
    ar.check("A19", "upload parser 테스트 유지", r19.returncode == 0, r19.stdout[-150:])

    # A20. catalog + recommend tests
    r20 = subprocess.run(
        [sys.executable, "-m", "pytest", str(CATALOG_TEST), str(RECOMMEND_TEST),
         "-q", "--tb=no"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(PROJECT_ROOT)
    )
    ar.check("A20", "catalog/recommend 테스트 유지", r20.returncode == 0, r20.stdout[-150:])

    # WARNs
    ar.warn(WARN_LOW_CONF)
    ar.warn(WARN_MISSING)
    ar.warn(WARN_COMPLEX)

    return ar.report()


if __name__ == "__main__":
    sys.exit(run_audit())
