"""HWPX-XML-DEEP-STRUCTURE-ANALYZER-CONTRACT-01 — operations audit (준공검사).

B동(XML 정밀진단동) 시공 결과 검증. PASS/WARN/FAIL 보고.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))


def run_audit() -> dict:
    from scripts.hwpx.recognition_corpus import (
        xml_deep_structure_analyzer as an,
    )

    findings: list[dict] = []

    def add(check: str, ok: bool, detail: object = "",
              level: str = "FAIL") -> None:
        findings.append({
            "check": check,
            "status": "PASS" if ok else level,
            "ok": bool(ok),
            "detail": detail,
        })

    # 1. 모듈 존재
    mod = (PROJECT_ROOT
             / "scripts/hwpx/recognition_corpus/xml_deep_structure_analyzer.py")
    add("analyzer_module_exists", mod.is_file(),
          str(mod.relative_to(PROJECT_ROOT)))

    # 2. contract name
    add("contract_name_locked",
          an.CONTRACT_NAME == "HWPX-XML-DEEP-STRUCTURE-ANALYZER-CONTRACT-01",
          an.CONTRACT_NAME)

    # 3. 9 analyzer 모두 존재
    missing = [n for n in an.REQUIRED_ANALYZER_NAMES if not hasattr(an, n)]
    add("9_analyzers_present", not missing,
          {"missing": missing, "required": list(an.REQUIRED_ANALYZER_NAMES)})

    # 4. reason_code 9개
    add("reason_code_set_9", len(an.ALLOWED_REASON_CODE) == 9,
          {"count": len(an.ALLOWED_REASON_CODE)})

    # 5. severity 3개
    add("severity_set_3", an.ALLOWED_SEVERITY == frozenset(
        {"LOW", "MEDIUM", "HIGH"}), {"set": sorted(an.ALLOWED_SEVERITY)})

    # 6. 진단 sanity — 9 reason_code 모두 발생 가능한지 확인
    flags = an.diagnose_session(
        paragraph_xml_list=[
            {"xml": ("<p xmlns='hp'>"
                          "<run charPrIDRef='1'><t>a </t></run>"
                          "<run charPrIDRef='2'><t>b </t></run>"
                          "<run charPrIDRef='3'><t>c</t></run></p>"),
                "target_key": "tk", "normalized_label": "공사명"},
        ],
        cell_xml_list=[
            {"xml": "<tc xmlns='hp'></tc>", "target_key": "tk2"},
            {"xml": ("<tbl xmlns='hp'>"
                          "<tc rowSpan='2' colSpan='2'><p/></tc>"
                          "<tc rowSpan='1' colSpan='1' hidden='1'><p/></tc>"
                          "</tbl>"),
                "target_key": "tk3"},
        ],
        element_xml_list=[
            {"xml": "<p xmlns='hp'><ctrlCheck/></p>", "target_key": "tk4"},
            {"xml": "<p xmlns='hp'><pic/><equation/></p>",
                "target_key": "tk5"},
        ],
        readback_checks=[
            {"expected_hash": "a", "actual_hash": "b"},
        ],
        ambiguity_checks=[
            {"candidate_targets": ["x", "y", "z"],
                "normalized_label": "주소"},
        ],
        label_checks=[
            {"normalized_label": None, "neighbor_text": None},
        ],
    )
    codes = sorted({f["reason_code"] for f in flags})
    expected_codes = {
        "RUN_BOUNDARY_UNSUPPORTED", "STYLE_RESOLUTION_NEEDED",
        "CELL_INTERNAL_PARAGRAPH_NEEDED",
        "MERGED_CELL_GEOMETRY_NEEDED",
        "CHECKBOX_OR_SHAPE_NEEDED", "OBJECT_ANCHOR_NEEDED",
        "READBACK_MISMATCH", "TARGET_AMBIGUOUS",
        "LABEL_CONTEXT_INSUFFICIENT",
    }
    missing_codes = sorted(expected_codes - set(codes))
    add("all_9_reason_codes_reachable", not missing_codes,
          {"missing": missing_codes, "detected": codes})

    # 7. D동 schema 호환 (backlog record 변환)
    recs = an.to_backlog_records(flags, session_id=None,
                                       document_id="d-audit",
                                       created_at="2026-05-18T00:00:00Z")
    required_keys = {"document_id", "reason_code", "severity", "created_at"}
    add("backlog_record_schema_match",
          all(required_keys.issubset(r.keys()) for r in recs),
          {"sampleKeys": sorted(recs[0].keys()) if recs else []})

    # 8. D동 audit_learning_log_contract와 enum 일치
    try:
        from scripts.hwpx.recognition_corpus import (
            audit_learning_log_contract as al,
        )
        same_reason = an.ALLOWED_REASON_CODE == al.ALLOWED_REASON_CODE
        same_severity = an.ALLOWED_SEVERITY == al.ALLOWED_SEVERITY
        add("d_dong_enum_compat", same_reason and same_severity,
              {"sameReason": same_reason, "sameSeverity": same_severity})
    except Exception as e:  # pragma: no cover
        add("d_dong_enum_compat", False, str(e))

    # 9. 방화구획
    iso = an.audit_analyzer_isolation()
    add("production_import_isolation", iso["ok"], iso)

    # 10. 모듈 내 금지물 (writer/AI/OCR/secret)
    src = mod.read_text(encoding="utf-8")
    bad_writer = ("GenericEditPlanWriter", "writer_executor",
                    "writer_adapter")
    add("no_writer_in_module",
          not any(n in src for n in bad_writer), {"checked": bad_writer})
    bad_ai = ("anthropic", "openai", "tesseract", "ANTHROPIC_API_KEY")
    add("no_ai_ocr_in_module",
          not any(n.lower() in src.lower() for n in bad_ai),
          {"checked": bad_ai})
    bad_secret = ("DATABASE_URL", "password=", "haehan-ai.pem")
    add("no_secret_in_module",
          not any(n in src for n in bad_secret),
          {"checked": bad_secret})

    # 11. 직전 공정 회귀 가능성 (모듈 import 확인)
    try:
        from scripts.hwpx.recognition_corpus import (
            corpus_schema, label_promotion_review_batch,
            label_promotion_gate, content_classifier,
            audit_learning_log_contract,
        )
        _ = (corpus_schema, label_promotion_review_batch,
                label_promotion_gate, content_classifier,
                audit_learning_log_contract)
        add("prior_corpus_modules_loadable", True, "ok")
    except Exception as e:  # pragma: no cover
        add("prior_corpus_modules_loadable", False, str(e))

    fails = [f for f in findings if f["status"] == "FAIL"]
    warns = [f for f in findings if f["status"] == "WARN"]
    summary = {
        "verdict": "PASS" if not fails else "FAIL",
        "total": len(findings),
        "pass": sum(1 for f in findings if f["status"] == "PASS"),
        "warn": len(warns),
        "fail": len(fails),
    }
    return {
        "auditName": "HWPX-XML-DEEP-STRUCTURE-ANALYZER-CONTRACT-01",
        "analyzerVersion": an.ANALYZER_VERSION,
        "summary": summary,
        "findings": findings,
    }


def main() -> int:
    report = run_audit()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["summary"]["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
