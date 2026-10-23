"""HWPX-FILL-REVIEW-LOG-ORCHESTRATION-01 — operations audit (준공검사).

D동 ↔ 운영동 배관 안전성, 격리, D동 schema 호환 검증.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))


def _check_module_source_boundaries(mod: Path, add) -> None:
    """orchestration 모듈 소스에 production/AI/OCR/secret 참조가 없는지 확인한다."""
    src = mod.read_text(encoding="utf-8")
    fr_imports = (
        "from scripts.hwpx.fill_review",
        "import fill_review_contract",
        "import fill_review_ui_adapter",
        "import fill_review_live_pipeline",
        "import evidence_ingestion_contract",
    )
    add(
        "orchestration_does_not_import_production",
        not any(n in src for n in fr_imports),
        {"checked": fr_imports},
    )

    add(
        "no_writer_in_module",
        not any(n in src for n in ("GenericEditPlanWriter", "writer_executor", "writer_adapter")),
        "ok",
    )
    add(
        "no_ai_ocr_in_module",
        not any(
            n.lower() in src.lower()
            for n in ("anthropic", "openai", "tesseract", "ANTHROPIC_API_KEY")
        ),
        "ok",
    )
    add(
        "no_secret_in_module",
        not any(n in src for n in ("DATABASE_URL", "password=", "haehan-ai.pem")),
        "ok",
    )


def run_audit() -> dict:
    from scripts.hwpx.orchestration import fill_review_log_recorder as orc
    from scripts.hwpx.recognition_corpus import (
        audit_learning_log_contract as al,
    )
    from scripts.hwpx.recognition_corpus import (
        corpus_schema as cs,
    )

    findings: list[dict] = []

    def add(check: str, ok: bool, detail: object = "") -> None:
        findings.append({
            "check": check,
            "status": "PASS" if ok else "FAIL",
            "ok": bool(ok),
            "detail": detail,
        })

    # 1. 배관 모듈 존재
    mod = PROJECT_ROOT / "scripts/hwpx/orchestration/fill_review_log_recorder.py"
    add("orchestration_module_exists", mod.is_file(), str(mod.relative_to(PROJECT_ROOT)))

    add(
        "contract_name_locked",
        orc.CONTRACT_NAME == "HWPX-FILL-REVIEW-LOG-ORCHESTRATION-01",
        orc.CONTRACT_NAME,
    )

    # 2. in-memory 환경에서 한 번 가동
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    cs.init_db(conn)
    al.init_audit_learning_log_schema(conn)

    pr = {
        "schemaVersion": "1.0",
        "engineVersion": "0.6.2",
        "requestId": "req-audit",
        "documentId": "d-audit",
        "sourceDocumentHash": "h",
        "pipelineStatus": "COMPLETED",
        "recognitionResult": {"documentType": "fillable_form", "subType": "검측요청서"},
        "fillReview": {
            "reviewItems": [
                {
                    "reviewItemId": "ri-1",
                    "label": "공사명",
                    "semanticType": "PROJECT_NAME",
                    "evidenceRefs": ["ev-1"],
                }
            ]
        },
        "approvedEditPlan": {
            "operations": [
                {
                    "op": "setCellText",
                    "reviewItemId": "ri-1",
                    "target": {"targetType": "cell", "cellKey": "t0:r0:c1"},
                    "expectedBeforeHash": "before-hash",
                    "value": "○○건축공사",
                }
            ]
        },
        "writerResult": {"operationResults": [{"status": "APPLIED"}]},
        "readback": {"operationResults": [{"status": "MATCHED"}]},
        "warnings": [],
        "errors": [],
    }
    dp = {
        "decisions": [
            {
                "reviewItemId": "ri-1",
                "label": "공사명",
                "semanticType": "PROJECT_NAME",
                "target": {"targetType": "cell", "cellKey": "t0:r0:c1"},
                "proposedValue": "○○건축공사",
                "decision": "APPROVE",
                "decisionSource": "USER",
                "decidedBy": "rep",
            }
        ]
    }
    res = orc.record_pipeline_result(conn, pr, decision_payload=dp)
    add(
        "session_recorded",
        res["sessionStatus"] == "COMPLETED"
        and res["counts"]["decisions"] == 1
        and res["counts"]["writerOps"] == 1
        and res["counts"]["readbacks"] == 1
        and res["counts"]["learningSignals"] == 1,
        res,
    )

    # 3. raw 개인정보가 hash로만 저장됐는지 확인
    row = conn.execute("SELECT proposed_value_hash FROM fill_review_decision_logs").fetchone()
    add(
        "proposed_value_hashed",
        bool(row and row[0] and len(row[0]) == 64),
        {"hashSample": row[0][:16] + "..." if row and row[0] else None},
    )

    # 4. setCellParagraphText 거부 확인 (별도 in-memory 인스턴스)
    conn2 = sqlite3.connect(":memory:")
    conn2.execute("PRAGMA foreign_keys = ON")
    cs.init_db(conn2)
    al.init_audit_learning_log_schema(conn2)
    pr_bad = dict(pr)
    pr_bad["requestId"] = "req-audit-bad"
    pr_bad["approvedEditPlan"] = {
        "operations": [
            {
                "op": "setCellParagraphText",
                "reviewItemId": "ri-1",
                "target": {"cellKey": "x"},
                "expectedBeforeHash": "h",
            }
        ]
    }
    blocked = False
    try:
        orc.record_pipeline_result(conn2, pr_bad, decision_payload=dp)
    except ValueError:
        blocked = True
    conn2.close()
    add("forbidden_op_blocked", blocked, {"blocked": blocked})

    # 5. 격리 검증 (production이 본 모듈을 import 안 하는지)
    iso = orc.audit_orchestration_isolation()
    add("production_import_isolation", iso["ok"], iso)

    # 6~7. orchestration 모듈 소스 경계 검사(production/writer/AI/OCR/secret 미포함)
    _check_module_source_boundaries(mod, add)

    # 8. D동 schema view 호환
    rows = conn.execute("SELECT COUNT(*) FROM reusable_learning_signals").fetchone()[0]
    add("d_dong_views_compat", rows >= 1, {"reusableSignalCount": rows})

    # 9. 인접 동 import 호환성
    try:
        from scripts.hwpx.api_contract import editor_command_contract
        from scripts.hwpx.recognition_corpus import (
            audit_learning_log_contract,
            xml_deep_structure_analyzer,
        )

        _ = (xml_deep_structure_analyzer, audit_learning_log_contract, editor_command_contract)
        add("adjacent_dong_compat", True, "B+D+API-contract loadable")
    except Exception as e:  # ruff: ignore[blind-except] — import 실패 사유 다양, 감사결과로 보고
        add("adjacent_dong_compat", False, str(e))

    fails = [f for f in findings if f["status"] == "FAIL"]
    summary = {
        "verdict": "PASS" if not fails else "FAIL",
        "total": len(findings),
        "pass": sum(1 for f in findings if f["status"] == "PASS"),
        "fail": len(fails),
    }
    return {
        "auditName": "HWPX-FILL-REVIEW-LOG-ORCHESTRATION-01",
        "orchestrationVersion": orc.ORCHESTRATION_VERSION,
        "summary": summary,
        "findings": findings,
    }


def main() -> int:
    report = run_audit()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["summary"]["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
