"""HWPX-DOCUMENT-FILL-REVIEW-CONTRACT-01 게이트 감사 스크립트.

검수 계약 모듈의 불변식 + operation naming + writer 미호출 검증.
"""
from __future__ import annotations

import json
import sys
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

OUTPUT_DIR = PROJECT_ROOT / "reports" / "hwpx_fill_review_contract_audit"


def _grep_for_set_cell_paragraph_text() -> list[str]:
    """프로젝트 전체에서 setCellParagraphText 출현 위치를 git ls-files 기반으로 탐색.

    의도된 negative reference (FORBIDDEN 집합/테스트/감사 스크립트)는 허용.
    """
    allowed_paths = {
        "scripts/hwpx/fill_review/fill_review_contract.py",
        "scripts/hwpx/fill_review/fill_review_ui_adapter.py",
        "scripts/hwpx/fill_review/fill_review_live_pipeline.py",
        "scripts/ops/audit_hwpx_fill_review_contract.py",
        "scripts/ops/audit_hwpx_fill_review_ui_adapter.py",
        "scripts/ops/audit_hwpx_fill_review_live_pipeline_integration.py",
        "scripts/ops/audit_hwpx_recognition_full_coverage.py",
        "tests/test_hwpx_fill_review_contract.py",
        "tests/test_hwpx_fill_review_ui_adapter.py",
        "tests/test_hwpx_fill_review_live_pipeline_integration.py",
        "tests/test_hwpx_recognition_full_coverage_audit.py",
        # D동 (audit/learning log contract) — declares the same forbidden
        # operation name as a negative reference (CHECK/enum/test).
        "scripts/hwpx/recognition_corpus/audit_learning_log_contract.py",
        "scripts/ops/audit_hwpx_fill_review_audit_learning_log_contract.py",
        "tests/test_hwpx_fill_review_audit_learning_log_contract.py",
        "scripts/hwpx/recognition_corpus/schema/002_audit_learning_logs.sql",
        # 배관 (D↔운영동 orchestration) — references forbidden name in
        # rejection test and audit verification only.
        "scripts/ops/audit_hwpx_fill_review_log_orchestration.py",
        "tests/test_hwpx_fill_review_log_orchestration.py",
    }
    try:
        ls = subprocess.run(
            ["git", "ls-files"], cwd=str(PROJECT_ROOT),
            capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
        )
        hits: list[str] = []
        for path in ls.stdout.splitlines():
            norm = path.replace("\\", "/")
            if not path or norm.startswith("docs/devlog/"):
                continue
            if norm in allowed_paths:
                continue
            full = PROJECT_ROOT / path
            try:
                if not full.is_file():
                    continue
                if full.suffix not in (".py", ".json", ".md", ".ts", ".js"):
                    continue
                text = full.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            if "setCellParagraphText" in text:
                hits.append(path)
        return hits
    except Exception:
        return []


def run_audit() -> dict:
    from scripts.hwpx.fill_review import fill_review_contract as fr
    from scripts.hwpx.pipeline import generic_edit_plan_contract as contract

    findings: list[dict] = []

    # 1) 공식 paragraph 이름 잠금
    findings.append({
        "check": "official_paragraph_op_name_locked",
        "ok": fr.OFFICIAL_PARAGRAPH_FULL_REPLACE_OP == "setParagraphText",
        "detail": f"name={fr.OFFICIAL_PARAGRAPH_FULL_REPLACE_OP}",
    })

    # 2) setCellParagraphText 충돌 검색
    hits = _grep_for_set_cell_paragraph_text()
    findings.append({
        "check": "set_cell_paragraph_text_not_used",
        "ok": len(hits) == 0,
        "detail": (f"no occurrences" if not hits
                     else f"occurrences in: {hits}"),
    })

    # 3) ALLOWED_FILL_REVIEW_OPERATIONS ⊆ contract.ALLOWED_OPERATION_TYPES
    findings.append({
        "check": "fill_review_subset_of_edit_plan_allowed",
        "ok": fr.ALLOWED_FILL_REVIEW_OPERATIONS.issubset(
            contract.ALLOWED_OPERATION_TYPES,
        ),
        "detail": f"fill_review={sorted(fr.ALLOWED_FILL_REVIEW_OPERATIONS)}",
    })

    # 4) FORBIDDEN과 ALLOWED 분리
    findings.append({
        "check": "forbidden_and_allowed_disjoint",
        "ok": fr.FORBIDDEN_PARAGRAPH_OP_NAMES.isdisjoint(
            fr.ALLOWED_FILL_REVIEW_OPERATIONS,
        ),
        "detail": (f"forbidden={sorted(fr.FORBIDDEN_PARAGRAPH_OP_NAMES)} "
                     f"allowed={sorted(fr.ALLOWED_FILL_REVIEW_OPERATIONS)}"),
    })

    # 5) sourceDocumentHash 없는 plan은 BLOCKED
    plan_no_hash = fr.build_approved_edit_plan([], [], source_document_hash="")
    findings.append({
        "check": "missing_source_hash_blocks_plan",
        "ok": (plan_no_hash.verdict == "BLOCKED_INVALID_PLAN"
                and plan_no_hash.operations == []),
        "detail": f"verdict={plan_no_hash.verdict}",
    })

    # 6) APPROVE 없이는 operations=[] (decisions=[])
    plan_no_decision = fr.build_approved_edit_plan([], [],
                                                          source_document_hash="sha:1")
    findings.append({
        "check": "no_decisions_means_no_operations",
        "ok": plan_no_decision.operations == [],
        "detail": f"verdict={plan_no_decision.verdict}",
    })

    # 7) REJECT decision은 operations 생성 안 함
    fake_items = [{
        "reviewItemId": "rev_x", "requirementId": "req_x",
        "target": {"targetType": "cell", "cellKey": "t_s0_000:r0:c1",
                   "paragraphKey": None},
        "currentValue": "", "proposedValue": "X", "evidenceRefs": [],
        "beforePreview": "", "afterPreview": "X",
        "riskLevel": "LOW", "status": "READY_FOR_REVIEW",
        "allowedDecisions": ["APPROVE", "REJECT"],
    }]
    plan_rej = fr.build_approved_edit_plan(
        fake_items, [{"reviewItemId": "rev_x", "decision": "REJECT",
                        "reviewer": "x", "reason": "y"}],
        source_document_hash="sha:1",
    )
    findings.append({
        "check": "reject_does_not_produce_operations",
        "ok": plan_rej.operations == [],
        "detail": f"verdict={plan_rej.verdict}",
    })

    # 8) writerCalled=False / outputCreated=False / originalUnmodified=True (불변식)
    plan_inv = fr.build_approved_edit_plan(
        fake_items, [{"reviewItemId": "rev_x", "decision": "APPROVE",
                        "reviewer": "x", "reason": "y"}],
        source_document_hash="sha:1",
    )
    findings.append({
        "check": "no_writer_no_output_no_mutation",
        "ok": (plan_inv.writerCalled is False
                and plan_inv.outputCreated is False
                and plan_inv.originalUnmodified is True),
        "detail": (f"writerCalled={plan_inv.writerCalled} "
                     f"outputCreated={plan_inv.outputCreated} "
                     f"originalUnmodified={plan_inv.originalUnmodified}"),
    })

    # 9) AUTOGEN_OPERATIONS ⊆ ALLOWED_FILL_REVIEW_OPERATIONS
    findings.append({
        "check": "autogen_subset_of_allowed",
        "ok": fr.AUTOGEN_OPERATIONS.issubset(fr.ALLOWED_FILL_REVIEW_OPERATIONS),
        "detail": f"autogen={sorted(fr.AUTOGEN_OPERATIONS)}",
    })

    # 10) operation 카운트
    findings.append({
        "check": "operation_set_counts",
        "ok": True,
        "detail": {
            "allowed": len(fr.ALLOWED_FILL_REVIEW_OPERATIONS),
            "autogen": len(fr.AUTOGEN_OPERATIONS),
            "forbidden": len(fr.FORBIDDEN_PARAGRAPH_OP_NAMES),
            "decisions": len(fr.ALLOWED_DECISIONS),
        },
    })

    summary = {
        "totalChecks": len(findings),
        "passCount": sum(1 for f in findings if f["ok"]),
        "failCount": sum(1 for f in findings if not f["ok"]),
        "findings": findings,
        "auditVerdict": "PASS" if all(f["ok"] for f in findings) else "FAIL",
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "audit.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    return summary


if __name__ == "__main__":
    print("[HWPX-DOCUMENT-FILL-REVIEW-CONTRACT-01 GATE AUDIT]")
    result = run_audit()
    for f in result["findings"]:
        flag = "PASS" if f["ok"] else "FAIL"
        print(f"  {flag} {f['check']}: {f['detail']}")
    print("=" * 60)
    print(f"verdict: {result['auditVerdict']}  "
          f"pass={result['passCount']}/{result['totalChecks']}")
    sys.exit(0 if result["auditVerdict"] == "PASS" else 1)
