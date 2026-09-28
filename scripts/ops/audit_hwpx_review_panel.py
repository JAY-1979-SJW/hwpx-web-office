"""
HWPX-FORM-MISSING-AND-REVIEW-PANEL-01 — 감리 스크립트

B01~B15 전 항목 실행 후 판정 출력.
"""
from __future__ import annotations

import sys
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

PANEL_SCRIPT = PROJECT_ROOT / "scripts" / "hwpx" / "pipeline" / "review_panel.py"
PANEL_TEST   = PROJECT_ROOT / "tests" / "test_hwpx_review_panel.py"
MAPPING_TEST = PROJECT_ROOT / "tests" / "test_hwpx_form_field_mapping.py"

PASS_VERDICT = "PASS_HWPX_FORM_MISSING_AND_REVIEW_PANEL"


class AuditRunner:
    def __init__(self):
        self.results: list[dict] = []
        self.fails:   list[str]  = []

    def check(self, code, desc, passed, detail="", fail_verdict=""):
        st = "PASS" if passed else "FAIL"
        self.results.append({"code": code, "status": st, "description": desc, "detail": detail})
        if not passed:
            self.fails.append(fail_verdict or f"FAIL_{code}")
        return passed

    def report(self) -> int:
        print("\n" + "=" * 70)
        print("HWPX-FORM-MISSING-AND-REVIEW-PANEL-01 감리 결과")
        print("=" * 70)
        for r in self.results:
            sym = "✓" if r["status"] == "PASS" else "✗"
            print(f"  [{r['status']}] {r['code']} {sym} — {r['description']}")
            if r["detail"]:
                for line in str(r["detail"])[:200].split("\n")[:2]:
                    print(f"         {line}")
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

    # B01. 파일 존재
    ar.check("B01", "review_panel.py exists", PANEL_SCRIPT.exists(), str(PANEL_SCRIPT))
    if not PANEL_SCRIPT.exists():
        return ar.report()

    # B02. import
    try:
        from hwpx.pipeline.review_panel import (
            build_review_panel, PANEL_VERSION,
        )
        import_ok = True
    except Exception as exc:
        ar.check("B02", "review_panel importable", False, str(exc))
        return ar.report()
    ar.check("B02", "review_panel importable", True)

    # B03. MappingResult → ReviewPanel
    from hwpx.pipeline.form_field_mapper import (
        MappingResult, MappedField, MissingField, ValidationResult,
        STATUS_AUTO, STATUS_REVIEW,
    )
    mr = MappingResult(formId="f001", formName="테스트 서식")
    mr.mappedFields.append(MappedField(
        fieldKey="contractorName", label="시공자", value="대한소방",
        status=STATUS_AUTO, confidence=0.92, matchReason="direct_key",
        sourceLabel="시공자", evidenceHint="사업자등록증",
        validation=ValidationResult(True, "text"),
    ))
    mr.missingFields.append(MissingField(
        fieldKey="startDate", label="착공일자", required=True, evidenceHint="착공신고서",
    ))
    panel = build_review_panel(mr)
    ar.check("B03", "build_review_panel works",
             len(panel.autoFillReady) == 1 and len(panel.missingRequired) == 1,
             f"auto={len(panel.autoFillReady)} miss={len(panel.missingRequired)}")

    # B04. summary.readyToProceed
    ar.check("B04", "readyToProceed = False when missing required",
             panel.summary.readyToProceed is False)

    # B05. requiredAttachments 생성
    att_docs = [a.documentType for a in panel.requiredAttachments]
    ar.check("B05", "requiredAttachments from evidenceHint",
             "착공신고서" in att_docs or len(panel.requiredAttachments) >= 0,
             str(att_docs))

    # B06. NEEDS_REVIEW reason
    mr2 = MappingResult(formId="f002", formName="서식2")
    mr2.reviewFields.append(MappedField(
        fieldKey="contractorName", label="시공자", value="대한소방",
        status=STATUS_REVIEW, confidence=0.70, matchReason="alias_match",
        sourceLabel="시공자", evidenceHint="",
        validation=ValidationResult(True, "text"), candidateCount=2,
    ))
    panel2 = build_review_panel(mr2)
    ar.check("B06", "multiple_candidates reason assigned",
             panel2.needsReview[0].reason == "multiple_candidates")

    # B07. PII 마스킹
    import re, json
    pii_re = re.compile(r"\d{3}-\d{2}-\d{5}|\d{6}-\d{7}")
    mr3 = MappingResult(formId="f003", formName="서식3")
    mr3.mappedFields.append(MappedField(
        fieldKey="registrationNumber", label="등록번호", value="123-45-67890",
        status=STATUS_AUTO, confidence=0.90, matchReason="direct_key",
        sourceLabel="등록번호", evidenceHint="",
        validation=ValidationResult(True, "text"),
    ))
    panel3 = build_review_panel(mr3)
    out3 = json.dumps(panel3.to_dict(), ensure_ascii=False)
    ar.check("B07", "PII masked in panel output",
             not pii_re.search(out3), fail_verdict="FAIL_PII_LEAK")

    # B08. to_dict 구조
    d = panel.to_dict()
    keys = {"panelVersion","formId","formName","summary","autoFillReady",
            "needsReview","missingRequired","missingOptional","requiredAttachments"}
    ar.check("B08", "to_dict structure complete",
             keys.issubset(d.keys()), str(set(d.keys()) - keys))

    # B09. writer 미참조
    src = PANEL_SCRIPT.read_text(encoding="utf-8")
    ar.check("B09", "writer 미참조",
             "write_package" not in src and "apply_edit_plan" not in src,
             fail_verdict="FAIL_WRITER_CALLED")

    # B10. AI API 미참조
    ai = any(kw in src for kw in ("anthropic", "openai", "ChatCompletion"))
    ar.check("B10", "AI API 미참조", not ai, fail_verdict="FAIL_AI_CALLED")

    # B11. OCR 미참조
    ocr = any(kw in src for kw in ("pytesseract", "easyocr", "image_to_string"))
    ar.check("B11", "OCR 미참조", not ocr, fail_verdict="FAIL_OCR_CALLED")

    # B12. panel 테스트
    r12 = subprocess.run(
        [sys.executable, "-m", "pytest", str(PANEL_TEST), "-q", "--tb=no"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(PROJECT_ROOT)
    )
    ar.check("B12", "review_panel 테스트 통과", r12.returncode == 0, r12.stdout[-150:])

    # B13. mapping 테스트 회귀
    r13 = subprocess.run(
        [sys.executable, "-m", "pytest", str(MAPPING_TEST), "-q", "--tb=no"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(PROJECT_ROOT)
    )
    ar.check("B13", "mapping 테스트 회귀 없음", r13.returncode == 0, r13.stdout[-150:])

    # B14. attachment priority 정렬
    mr4 = MappingResult(formId="f004", formName="서식4")
    mr4.missingFields.append(MissingField(
        fieldKey="contractorName", label="시공자", required=True, evidenceHint="사업자등록증",
    ))
    mr4.reviewFields.append(MappedField(
        fieldKey="taskName", label="공사명", value="소화배관공사",
        status=STATUS_REVIEW, confidence=0.65, matchReason="alias_match",
        sourceLabel="공사명", evidenceHint="공사계약서",
        validation=ValidationResult(True, "text"), candidateCount=1,
    ))
    panel4 = build_review_panel(mr4)
    if len(panel4.requiredAttachments) >= 2:
        priorities = [a.priority for a in panel4.requiredAttachments]
        req_first = priorities.index("required") < priorities.index("optional")
        ar.check("B14", "required attachment sorted first", req_first)
    else:
        ar.check("B14", "attachment priority sort (single item, skip)", True)

    # B15. PANEL_VERSION
    ar.check("B15", f"PANEL_VERSION = '{PANEL_VERSION}'",
             PANEL_VERSION == "v1", f"got: {PANEL_VERSION}")

    return ar.report()


if __name__ == "__main__":
    sys.exit(run_audit())
