"""
HWPX-FORM-HUMAN-APPROVAL-GATE-01 — 감리 스크립트

C01~C18 전 항목 실행 후 판정 출력.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

GATE_SCRIPT  = PROJECT_ROOT / "scripts" / "hwpx" / "pipeline" / "approval_gate.py"
GATE_TEST    = PROJECT_ROOT / "tests" / "test_hwpx_approval_gate.py"
PANEL_TEST   = PROJECT_ROOT / "tests" / "test_hwpx_review_panel.py"
MAPPING_TEST = PROJECT_ROOT / "tests" / "test_hwpx_form_field_mapping.py"

PASS_VERDICT = "PASS_HWPX_FORM_HUMAN_APPROVAL_GATE"
_PII_RE = re.compile(r"\d{3}-\d{2}-\d{5}|\d{6}-\d{7}")


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
        print("HWPX-FORM-HUMAN-APPROVAL-GATE-01 감리 결과")
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


def _panel_dict(auto=None, review=None, miss_req=None):
    def _ai(fk, lbl, val, conf):
        return {"fieldKey": fk, "label": lbl, "value": val, "confidence": conf,
                "sourceLabel": lbl, "matchReason": "direct_key"}
    def _ri(fk, lbl, val, conf):
        return {"fieldKey": fk, "label": lbl,
                "candidates": [{"value": val, "confidence": conf, "sourceLabel": lbl}],
                "reason": "low_confidence", "evidenceHint": ""}
    def _mi(fk, lbl):
        return {"fieldKey": fk, "label": lbl, "required": True,
                "evidenceHint": "", "suggestedAttachments": []}
    return {
        "panelVersion": "v1", "formId": "audit_form", "formName": "감리 서식",
        "summary": {},
        "autoFillReady":   [_ai(*x) for x in (auto or [])],
        "needsReview":     [_ri(*x) for x in (review or [])],
        "missingRequired": [_mi(*x) for x in (miss_req or [])],
        "missingOptional": [], "requiredAttachments": [],
    }


def run_audit() -> int:
    ar = AuditRunner()

    # C01. 파일 존재
    ar.check("C01", "approval_gate.py exists", GATE_SCRIPT.exists(), str(GATE_SCRIPT))
    if not GATE_SCRIPT.exists():
        return ar.report()

    # C02. import
    try:
        from hwpx.pipeline.approval_gate import (
            apply_decisions, FieldDecision, ACTION_CONFIRM, ACTION_EDIT, ACTION_HOLD, ACTION_ATTACHMENT,
            result_to_dict,
        )
    except Exception as exc:
        ar.check("C02", "approval_gate importable", False, str(exc))
        return ar.report()
    ar.check("C02", "approval_gate importable", True)

    # C03. CONFIRM_FIELD → writerEligible=True
    panel = _panel_dict(auto=[("contractorName", "시공자", "대한소방", 0.92)])
    r3 = apply_decisions(panel, [FieldDecision("contractorName", ACTION_CONFIRM)])
    af_ok = len(r3.approvedFields) == 1 and r3.approvedFields[0].writerEligible is True
    ar.check("C03", "CONFIRM_FIELD → writerEligible=True", af_ok,
             f"approvedFields={len(r3.approvedFields)}")

    # C04. EDIT_VALUE → value 교체
    r4 = apply_decisions(panel, [FieldDecision("contractorName", ACTION_EDIT,
                                               editedValue="한국소방공사")])
    edit_ok = (len(r4.approvedFields) == 1
               and r4.approvedFields[0].value == "한국소방공사"
               and r4.approvedFields[0].originalValue == "대한소방")
    ar.check("C04", "EDIT_VALUE replaces value", edit_ok,
             f"value={r4.approvedFields[0].value if r4.approvedFields else 'none'}")

    # C05. HOLD → pendingFields
    r5 = apply_decisions(panel, [FieldDecision("contractorName", ACTION_HOLD)])
    ar.check("C05", "HOLD → pendingFields, writerEligible=False",
             len(r5.pendingFields) == 1 and r5.pendingFields[0].writerEligible is False)

    # C06. REQUEST_ATTACHMENT → pendingFields
    panel_miss = _panel_dict(miss_req=[("contractorName", "시공자")])
    r6 = apply_decisions(panel_miss, [FieldDecision("contractorName", ACTION_ATTACHMENT)])
    ar.check("C06", "REQUEST_ATTACHMENT → pendingFields",
             len(r6.pendingFields) == 1 and r6.pendingFields[0].action == ACTION_ATTACHMENT)

    # C07. writerEnabled 항상 False
    r7 = apply_decisions(panel, [FieldDecision("contractorName", ACTION_CONFIRM)])
    we_false = r7.writerEnabled is False and r7.to_dict()["writerEnabled"] is False
    ar.check("C07", "writerEnabled 항상 False", we_false,
             fail_verdict="FAIL_WRITER_ENABLED")

    # C08. NEEDS_REVIEW 항목 CONFIRM_FIELD 가능
    panel_rev = _panel_dict(review=[("contractorName", "시공자", "대한소방", 0.70)])
    r8 = apply_decisions(panel_rev, [FieldDecision("contractorName", ACTION_CONFIRM)])
    ar.check("C08", "NEEDS_REVIEW항목 CONFIRM_FIELD 가능",
             len(r8.approvedFields) == 1 and r8.approvedFields[0].sourceZone == "needsReview")

    # C09. undecidedCount
    panel_two = _panel_dict(auto=[("contractorName", "시공자", "A", 0.90),
                                   ("taskName", "공사명", "B", 0.88)])
    r9 = apply_decisions(panel_two, [FieldDecision("contractorName", ACTION_CONFIRM)])
    d9 = result_to_dict(r9)
    ar.check("C09", "undecidedCount 정확",
             d9["summary"]["undecidedCount"] == 1,
             f"undecided={d9['summary']['undecidedCount']}")

    # C10. PII 마스킹
    panel_pii = _panel_dict(auto=[("registrationNumber", "등록번호", "", 0.0)])
    r10 = apply_decisions(panel_pii, [FieldDecision(
        "registrationNumber", ACTION_EDIT, editedValue="123-45-67890")])
    out10 = json.dumps(r10.to_dict(), ensure_ascii=False)
    ar.check("C10", "PII masked in output",
             not _PII_RE.search(out10), fail_verdict="FAIL_PII_LEAK")

    # C11. 잘못된 action → ValueError
    try:
        FieldDecision("x", "INVALID")
        ar.check("C11", "invalid action raises ValueError", False)
    except ValueError:
        ar.check("C11", "invalid action raises ValueError", True)

    # C12. to_dict 구조
    d12 = r3.to_dict()
    keys = {"gateVersion", "formId", "formName", "writerEnabled",
            "summary", "approvedFields", "pendingFields"}
    ar.check("C12", "to_dict structure complete", keys.issubset(d12.keys()))

    # C13. writer 미참조
    src = GATE_SCRIPT.read_text(encoding="utf-8")
    ar.check("C13", "writer 미참조",
             "write_package" not in src and "apply_edit_plan" not in src,
             fail_verdict="FAIL_WRITER_CALLED")

    # C14. AI API 미참조
    ai = any(kw in src for kw in ("anthropic", "openai", "ChatCompletion"))
    ar.check("C14", "AI API 미참조", not ai, fail_verdict="FAIL_AI_CALLED")

    # C15. OCR 미참조
    ocr = any(kw in src for kw in ("pytesseract", "easyocr", "image_to_string"))
    ar.check("C15", "OCR 미참조", not ocr, fail_verdict="FAIL_OCR_CALLED")

    # C16. gate 테스트
    r16 = subprocess.run(
        [sys.executable, "-m", "pytest", str(GATE_TEST), "-q", "--tb=no"],
        capture_output=True, text=True, cwd=str(PROJECT_ROOT)
    )
    ar.check("C16", "approval_gate 테스트 통과", r16.returncode == 0, r16.stdout[-150:])

    # C17. panel 테스트 회귀
    r17 = subprocess.run(
        [sys.executable, "-m", "pytest", str(PANEL_TEST), "-q", "--tb=no"],
        capture_output=True, text=True, cwd=str(PROJECT_ROOT)
    )
    ar.check("C17", "review_panel 테스트 회귀 없음", r17.returncode == 0, r17.stdout[-150:])

    # C18. mapping 테스트 회귀
    r18 = subprocess.run(
        [sys.executable, "-m", "pytest", str(MAPPING_TEST), "-q", "--tb=no"],
        capture_output=True, text=True, cwd=str(PROJECT_ROOT)
    )
    ar.check("C18", "mapping 테스트 회귀 없음", r18.returncode == 0, r18.stdout[-150:])

    return ar.report()


if __name__ == "__main__":
    sys.exit(run_audit())
