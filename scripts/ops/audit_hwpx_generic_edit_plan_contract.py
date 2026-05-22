"""HWPX-GENERIC-EDIT-PLAN-CONTRACT-01 게이트 감사 스크립트.

계약 모듈이 다음 불변식을 만족하는지 검증한다:
1. SCHEMA_VERSION 고정값
2. ALLOWED_OPERATION_TYPES / BLOCKED_OPERATION_TYPES 교차 없음
3. REVIEW_REQUIRED_OPERATION_TYPES ⊆ ALLOWED_OPERATION_TYPES
4. default_safety()는 모든 REQUIRED_SAFETY_FIELDS를 포함
5. validate_edit_plan(empty_plan_skeleton(...))은 OPS_EMPTY만 issue로 가짐
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

OUTPUT_DIR = PROJECT_ROOT / "reports" / "hwpx_generic_edit_plan_contract_audit"


def run_audit() -> dict:
    from scripts.hwpx.pipeline import generic_edit_plan_contract as c

    findings: list[dict] = []

    # 1) SCHEMA_VERSION
    findings.append({
        "check": "schema_version_pinned",
        "ok": c.SCHEMA_VERSION == "edit_plan_v1",
        "detail": f"SCHEMA_VERSION={c.SCHEMA_VERSION}",
    })

    # 2) allow vs blocked 교차 없음
    overlap = c.ALLOWED_OPERATION_TYPES & c.BLOCKED_OPERATION_TYPES
    findings.append({
        "check": "allow_blocked_disjoint",
        "ok": not overlap,
        "detail": f"overlap={sorted(overlap)}",
    })

    # 3) review ⊆ allow
    review_in_allow = c.REVIEW_REQUIRED_OPERATION_TYPES.issubset(c.ALLOWED_OPERATION_TYPES)
    findings.append({
        "check": "review_subset_of_allow",
        "ok": review_in_allow,
        "detail": f"review={sorted(c.REVIEW_REQUIRED_OPERATION_TYPES)}",
    })

    # 4) default_safety
    safety = c.default_safety()
    missing = [k for k in c.REQUIRED_SAFETY_FIELDS if k not in safety]
    findings.append({
        "check": "default_safety_has_required_fields",
        "ok": not missing,
        "detail": f"missing={missing}",
    })

    # 5) empty skeleton 검증
    skel = c.empty_plan_skeleton("p", "sha:1", "manual", "now")
    res = c.validate_edit_plan(skel)
    only_ops_empty = (
        res.verdict == "BLOCKED_INVALID_PLAN"
        and all(i.code in {"OPS_EMPTY"} for i in res.issues)
    )
    findings.append({
        "check": "empty_skeleton_only_blocks_on_ops_empty",
        "ok": only_ops_empty,
        "detail": f"verdict={res.verdict} codes={[i.code for i in res.issues]}",
    })

    # 6) operationType 카운트
    findings.append({
        "check": "operation_type_counts",
        "ok": True,
        "detail": {
            "allowed": len(c.ALLOWED_OPERATION_TYPES),
            "blocked": len(c.BLOCKED_OPERATION_TYPES),
            "review_required": len(c.REVIEW_REQUIRED_OPERATION_TYPES),
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
    print("[HWPX-GENERIC-EDIT-PLAN-CONTRACT-01 GATE AUDIT]")
    result = run_audit()
    for f in result["findings"]:
        flag = "PASS" if f["ok"] else "FAIL"
        print(f"  {flag} {f['check']}: {f['detail']}")
    print("=" * 60)
    print(f"verdict: {result['auditVerdict']}  pass={result['passCount']}/{result['totalChecks']}")
    sys.exit(0 if result["auditVerdict"] == "PASS" else 1)
