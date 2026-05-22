"""HWPX-AUTO-FILL-MASTER-ORCHESTRATION-01 — operations audit (준공검사)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))


def run_audit() -> dict:
    from scripts.hwpx.master_orchestration import auto_fill_master as mo

    findings: list[dict] = []

    def add(check: str, ok: bool, detail: object = "") -> None:
        findings.append({"check": check,
                            "status": "PASS" if ok else "FAIL",
                            "ok": bool(ok), "detail": detail})

    mod = (PROJECT_ROOT
             / "scripts/hwpx/master_orchestration/auto_fill_master.py")
    add("module_exists", mod.is_file(), str(mod.relative_to(PROJECT_ROOT)))
    add("contract_name_locked",
          mo.CONTRACT_NAME == "HWPX-AUTO-FILL-MASTER-ORCHESTRATION-01",
          mo.CONTRACT_NAME)
    snap = mo.dump_contract_snapshot()
    add("4_stages_locked", len(snap["stages"]) == 4, snap)

    # 최소 가동 (callable 없음)
    res = mo.run_auto_fill_master(source_hwpx_ref="doc-audit")
    add("minimal_run_safe",
          res["pipelineStatus"] == "READY_FOR_REVIEW"
            and any(w["code"] == "RECOGNITION_FN_NOT_INJECTED"
                      for w in res["warnings"]),
          "ok")

    # 전체 callable 주입 흐름
    def rec(ref): return {"documentId": ref,
                              "labelOccurrences": [
                                  {"normalizedLabel": "공사명",
                                      "cellKey": "t0:r0:c1"}]}
    def slot(r): return [{"label": "공사명"}]
    def ext(s, labels): return [
        {"label": "공사명", "value": "v", "evidenceType": "pdf",
            "sourceRef": "r", "confidence": 0.95}]
    def ai(r, slots, exts): return [
        {"proposalId": "p1", "label": "공사명",
            "value": "v", "confidence": 0.9}]
    full = mo.run_auto_fill_master(
        source_hwpx_ref="d2",
        source_documents=[{"sourceId": "s1", "sourceType": "pdf"}],
        recognition_fn=rec, slot_detect_fn=slot,
        extractor_registry={"pdf": ext}, ai_proposal_fn=ai)
    add("full_chain_run",
          full["aiProposalSummary"]["acceptedReadyForReview"] >= 1,
          {"stages": [s["stage"] for s in full["stages"]]})

    # 배관 통합 — D동 적재 가능 확인
    import sqlite3
    from scripts.hwpx.recognition_corpus import (
        corpus_schema as cs,
        audit_learning_log_contract as al,
    )
    from scripts.hwpx.orchestration import fill_review_log_recorder as orc
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    cs.init_db(conn)
    al.init_audit_learning_log_schema(conn)
    rec_res = orc.record_pipeline_result(conn, full)
    add("master_to_d_dong_pipeline",
          rec_res["sessionStatus"] == "READY_FOR_DECISION",
          {"sessionStatus": rec_res["sessionStatus"]})
    conn.close()

    # 격리
    iso = mo.audit_master_isolation()
    add("production_import_isolation", iso["ok"], iso)

    # 금지물
    src = mod.read_text(encoding="utf-8")
    bad_writer = ("GenericEditPlanWriter", "writer_executor",
                    "writer_adapter")
    add("no_writer_in_module",
          not any(n in src for n in bad_writer),
          {"checked": bad_writer})
    bad_ai = ("anthropic.Anthropic", "openai.OpenAI", "tesseract",
                "requests.post(", "urllib.request.urlopen(")
    add("no_ai_ocr_call_in_module",
          not any(n in src for n in bad_ai),
          {"checked": bad_ai})
    bad_secret = ("DATABASE_URL", "password=", "haehan-ai.pem")
    add("no_secret_in_module",
          not any(n in src for n in bad_secret),
          {"checked": bad_secret})
    forbidden_fr_import = ("from scripts.hwpx.fill_review",
                                "import fill_review_contract",
                                "import fill_review_live_pipeline")
    add("no_production_import",
          not any(n in src for n in forbidden_fr_import),
          {"checked": forbidden_fr_import})

    # 인접 동 호환
    try:
        from scripts.hwpx.api_contract import editor_command_contract
        from scripts.hwpx.ai_proposal import ai_proposal_contract
        from scripts.hwpx.source_extractor import source_extractor_contract
        from scripts.hwpx.recognition_corpus import (
            xml_deep_structure_analyzer, audit_learning_log_contract,
        )
        _ = (editor_command_contract, ai_proposal_contract,
                source_extractor_contract,
                xml_deep_structure_analyzer, audit_learning_log_contract)
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
        "auditName": "HWPX-AUTO-FILL-MASTER-ORCHESTRATION-01",
        "contractVersion": mo.CONTRACT_VERSION,
        "summary": summary,
        "findings": findings,
    }


def main() -> int:
    report = run_audit()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["summary"]["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
