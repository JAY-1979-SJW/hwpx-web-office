"""HWPX-SOURCE-EXTRACTOR-CONTRACT-01 — operations audit (준공검사)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))


def run_audit() -> dict:
    from scripts.hwpx.source_extractor import source_extractor_contract as se

    findings: list[dict] = []

    def add(check: str, ok: bool, detail: object = "") -> None:
        findings.append({"check": check,
                            "status": "PASS" if ok else "FAIL",
                            "ok": bool(ok), "detail": detail})

    mod = (PROJECT_ROOT
             / "scripts/hwpx/source_extractor/source_extractor_contract.py")
    add("module_exists", mod.is_file(), str(mod.relative_to(PROJECT_ROOT)))
    add("contract_name_locked",
          se.CONTRACT_NAME == "HWPX-SOURCE-EXTRACTOR-CONTRACT-01",
          se.CONTRACT_NAME)
    add("10_source_types", len(se.ALLOWED_SOURCE_TYPES) == 10,
          {"types": sorted(se.ALLOWED_SOURCE_TYPES)})

    # envelope
    add("valid_source_accepted",
          se.validate_source_descriptor(
              {"sourceId": "s1", "sourceType": "pdf"}) == [],
          "ok")
    add("missing_field_blocked",
          "MISSING_FIELD:sourceId" in se.validate_source_descriptor({}),
          "ok")
    add("forbidden_field_blocked",
          any("FORBIDDEN_FIELD" in e for e in
                se.validate_source_descriptor(
                    {"sourceId": "s", "sourceType": "pdf",
                        "apiKey": "x"})),
          "ok")

    # 라우터 sanity — no extractor → all skipped
    res = se.extract_values_from_sources(
        [{"sourceId": "s1", "sourceType": "pdf"}], ["공사명"])
    add("no_extractor_safely_skipped",
          res["summary"]["extractedCount"] == 0
            and len(res["skippedSources"]) == 1,
          res["summary"])

    # 라우터 sanity — fake extractor
    def fake(s, labels):
        return [{"label": "공사명", "value": "v",
                    "evidenceType": "pdf_text", "sourceRef": "r",
                    "confidence": 0.9}]
    res2 = se.extract_values_from_sources(
        [{"sourceId": "s1", "sourceType": "pdf"}], ["공사명"],
        extractor_registry={"pdf": fake})
    add("extractor_routed_successfully",
          res2["summary"]["extractedCount"] == 1, res2["summary"])

    # exception handling
    def kaboom(s, labels):
        raise RuntimeError("x")
    res3 = se.extract_values_from_sources(
        [{"sourceId": "s1", "sourceType": "pdf"}], ["x"],
        extractor_registry={"pdf": kaboom})
    add("extractor_exception_isolated",
          res3["summary"]["extractedCount"] == 0
            and "EXTRACTOR_ERROR" in res3["skippedSources"][0]["reason"],
          "ok")

    # to_evidence_inputs
    converted = se.to_evidence_inputs([{
        "label": "공사명", "value": "x", "evidenceType": "pdf_text",
        "sourceRef": "r", "confidence": 0.9, "sourceId": "s1",
    }])
    add("evidence_input_conversion",
          converted and converted[0]["label"] == "공사명",
          "ok")

    # 격리
    iso = se.audit_source_extractor_isolation()
    add("production_import_isolation", iso["ok"], iso)

    # 금지물
    src = mod.read_text(encoding="utf-8")
    bad_ai = ("anthropic.Anthropic", "openai.OpenAI", "tesseract",
                "requests.post(", "urllib.request.urlopen(")
    add("no_ai_ocr_call_in_module",
          not any(n in src for n in bad_ai), {"checked": bad_ai})
    bad_writer = ("GenericEditPlanWriter", "writer_executor")
    add("no_writer_in_module",
          not any(n in src for n in bad_writer), {"checked": bad_writer})
    bad_secret = ("DATABASE_URL", "password=", "haehan-ai.pem")
    add("no_secret_in_module",
          not any(n in src for n in bad_secret), {"checked": bad_secret})

    # 인접 동
    try:
        from scripts.hwpx.api_contract import editor_command_contract
        from scripts.hwpx.ai_proposal import ai_proposal_contract
        from scripts.hwpx.recognition_corpus import (
            xml_deep_structure_analyzer, audit_learning_log_contract,
        )
        from scripts.hwpx.orchestration import fill_review_log_recorder
        _ = (editor_command_contract, ai_proposal_contract,
                xml_deep_structure_analyzer, audit_learning_log_contract,
                fill_review_log_recorder)
        add("adjacent_dong_compat", True, "ok")
    except Exception as e:
        add("adjacent_dong_compat", False, str(e))

    fails = [f for f in findings if f["status"] == "FAIL"]
    summary = {
        "verdict": "PASS" if not fails else "FAIL",
        "total": len(findings),
        "pass": sum(1 for f in findings if f["status"] == "PASS"),
        "fail": len(fails),
    }
    return {
        "auditName": "HWPX-SOURCE-EXTRACTOR-CONTRACT-01",
        "contractVersion": se.CONTRACT_VERSION,
        "summary": summary,
        "findings": findings,
    }


def main() -> int:
    report = run_audit()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["summary"]["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
