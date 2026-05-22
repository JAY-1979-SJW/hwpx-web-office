"""HWPX-AI-AUTO-FILL-PROPOSAL-CONTRACT-01 — operations audit (준공검사)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))


def run_audit() -> dict:
    from scripts.hwpx.ai_proposal import (
        ai_proposal_contract as apc,
        target_resolver as tr,
        confidence_policy as cp,
        review_item_builder as rib,
    )

    findings: list[dict] = []

    def add(check: str, ok: bool, detail: object = "") -> None:
        findings.append({"check": check,
                            "status": "PASS" if ok else "FAIL",
                            "ok": bool(ok), "detail": detail})

    # 1. 모듈 존재
    mods = {
        "ai_proposal_contract": PROJECT_ROOT / "scripts/hwpx/ai_proposal/ai_proposal_contract.py",
        "target_resolver": PROJECT_ROOT / "scripts/hwpx/ai_proposal/target_resolver.py",
        "confidence_policy": PROJECT_ROOT / "scripts/hwpx/ai_proposal/confidence_policy.py",
        "review_item_builder": PROJECT_ROOT / "scripts/hwpx/ai_proposal/review_item_builder.py",
    }
    for name, p in mods.items():
        add(f"module_exists:{name}", p.is_file(),
              str(p.relative_to(PROJECT_ROOT)))

    # 2. contract name + version
    add("contract_name_locked",
          apc.CONTRACT_NAME == "HWPX-AI-AUTO-FILL-PROPOSAL-CONTRACT-01",
          apc.CONTRACT_NAME)

    # 3. 자동 승인 OFF
    add("auto_approve_off_by_default", cp.AUTO_APPROVE_ENABLED is False,
          {"AUTO_APPROVE_ENABLED": cp.AUTO_APPROVE_ENABLED})

    # 4. envelope sanity
    valid = {"proposalId": "p1", "label": "공사명",
                "value": "○○건축공사", "confidence": 0.9}
    add("valid_envelope_accepted",
          apc.validate_proposal_envelope(valid) == [],
          {"input": valid})

    # 5. forbidden field
    bad = dict(valid); bad["apiKey"] = "sk-..."
    errs = apc.validate_proposal_envelope(bad)
    add("forbidden_field_blocked",
          any(e.startswith("FORBIDDEN_FIELD:apiKey") for e in errs),
          {"errors": errs})

    # 6. confidence policy
    high = cp.classify(confidence=0.99, target_status="RESOLVED")
    add("high_conf_still_review_when_auto_off",
          high["decision"] == "READY_FOR_DECISION",
          {"result": high})
    low = cp.classify(confidence=0.3, target_status="RESOLVED")
    add("low_conf_auto_rejected",
          low["decision"] == "AUTO_REJECT", {"result": low})
    nf = cp.classify(confidence=0.99, target_status="NOT_FOUND")
    add("target_not_found_rejected",
          nf["decision"] == "AUTO_REJECT", {"result": nf})

    # 7. target resolver
    rec = {"labelOccurrences": [
        {"normalizedLabel": "공사명", "cellKey": "t0:r0:c1"}]}
    resolved = tr.resolve_target({"label": "공사명"}, rec)
    add("target_single_resolved",
          resolved["status"] == "RESOLVED", {"result": resolved})

    # 8. builder end-to-end
    res = rib.build_review_items_from_proposals(
        [{"proposalId": "p1", "label": "공사명",
            "value": "○○건축", "confidence": 0.9}], rec)
    add("builder_end_to_end",
          res["summary"]["acceptedReadyForReview"] == 1,
          res["summary"])

    # 9. PII redaction in output
    res2 = rib.build_review_items_from_proposals(
        [{"proposalId": "p1", "label": "공사명",
            "value": "010-1234-5678", "confidence": 0.9}], rec)
    item = res2["reviewItems"][0]
    add("pii_redacted_in_output",
          item["containsSensitive"] is True
            and "010-1234-5678" not in json.dumps(item, ensure_ascii=False),
          {"item": {k: item[k] for k in
                      ("redactedPreview", "containsSensitive")}})

    # 10. 격리
    iso = apc.audit_ai_proposal_isolation()
    add("production_import_isolation", iso["ok"], iso)

    # 11. 모듈 내 금지물
    for name, p in mods.items():
        src = p.read_text(encoding="utf-8")
        bad_writer = ("GenericEditPlanWriter", "writer_executor",
                        "writer_adapter")
        add(f"no_writer:{name}",
              not any(n in src for n in bad_writer),
              {"checked": bad_writer})

    # 12. AI/OCR 미호출 (코드 패턴 기준)
    forbidden_calls = ("anthropic.Anthropic", "openai.OpenAI",
                          "import anthropic", "import openai",
                          "tesseract", "requests.post(",
                          "urllib.request.urlopen(")
    for name, p in mods.items():
        src = p.read_text(encoding="utf-8")
        add(f"no_ai_call:{name}",
              not any(n in src for n in forbidden_calls),
              {"checked": forbidden_calls})

    # 13. secret
    bad_secret = ("DATABASE_URL", "password=", "haehan-ai.pem")
    for name, p in mods.items():
        src = p.read_text(encoding="utf-8")
        add(f"no_secret:{name}",
              not any(n in src for n in bad_secret),
              {"checked": bad_secret})

    # 14. 인접 동 호환성
    try:
        from scripts.hwpx.recognition_corpus import (
            xml_deep_structure_analyzer, audit_learning_log_contract,
        )
        from scripts.hwpx.api_contract import editor_command_contract
        from scripts.hwpx.orchestration import fill_review_log_recorder
        _ = (xml_deep_structure_analyzer, audit_learning_log_contract,
                editor_command_contract, fill_review_log_recorder)
        add("adjacent_dong_compat", True, "B+D+API+배관 loadable")
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
        "auditName": "HWPX-AI-AUTO-FILL-PROPOSAL-CONTRACT-01",
        "contractVersion": apc.CONTRACT_VERSION,
        "summary": summary,
        "findings": findings,
    }


def main() -> int:
    report = run_audit()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["summary"]["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
