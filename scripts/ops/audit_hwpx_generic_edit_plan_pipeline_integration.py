"""HWPX-EDIT-PLAN-PIPELINE-INTEGRATION-AUDIT-01 게이트 감사 스크립트.

5단계 파이프라인 7개 시나리오를 끝까지 실행하여 stage별 verdict /
invariant 보존 여부를 종합 보고한다. writer는 호출되지 않으며 output 파일도
만들어지지 않는다.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

METADATA_FORM = PROJECT_ROOT / "tests/fixtures/hwpx/corpus/fx_metadata_form.hwpx"
OUTPUT_DIR = PROJECT_ROOT / "reports" / "hwpx_generic_edit_plan_pipeline_integration_audit"


def _stages():
    from scripts.hwpx.pipeline import (
        generic_edit_plan_contract as c,
        generic_edit_plan_dry_run as d,
        generic_edit_plan_review_gate as g,
        generic_edit_plan_writer_adapter as a,
        generic_edit_plan_writer_executor_noop as e,
    )
    return c, d, g, a, e


def _parse():
    from scripts.hwpx.parser import parse_hwpx_v2
    return parse_hwpx_v2(METADATA_FORM)


def _first_text_cell(parsed):
    for t in parsed.tables:
        for c in t.cells:
            if c.normalizedText:
                return t.tableId, c
    return None, None


def _ops_text(t_id, cell, op_id="op-text",
                expected=None, value="NEW"):
    return {
        "operationId": op_id, "operationType": "setCellText",
        "target": {"tableId": t_id, "row": cell.row, "col": cell.col},
        "value": value, "preserveStyle": True,
        "expectedBefore": expected if expected is not None
                            else (cell.normalizedText or cell.text),
        "riskLevel": "low", "requiresReview": False, "reason": "audit",
    }


def _ops_fill(t_id, cell, op_id="op-fill"):
    return {
        "operationId": op_id, "operationType": "setCellFillColor",
        "target": {"tableId": t_id, "row": cell.row, "col": cell.col},
        "value": "#FFFF00", "preserveStyle": True,
        "expectedBefore": cell.fillColor,
        "riskLevel": "low", "requiresReview": False, "reason": "audit",
    }


def _ops_move():
    return {
        "operationId": "op-move", "operationType": "moveObject",
        "target": {"objectId": "obj-x"}, "value": None,
        "preserveStyle": True, "expectedBefore": None,
        "riskLevel": "high", "requiresReview": True, "reason": "audit",
    }


def _decision(plan_id, op_id, decision, reviewer="alice"):
    return {
        "decisionId": f"d-{op_id}", "planId": plan_id,
        "operationId": op_id, "reviewer": reviewer,
        "decision": decision, "reason": "audit",
        "decidedAt": "2026-05-18T12:00:00Z",
    }


def _run_pipeline(c, d, g, a, e, plan, decisions, parsed):
    dr = d.dry_run_edit_plan(plan, parsed)
    gate = g.apply_review_decisions(dr, decisions)
    wcp = a.build_writer_call_plan(plan, dr, gate)
    exe = e.execute_writer_call_plan_noop(wcp)
    return dr, gate, wcp, exe


def _scenario_summary(name, plan, decisions, dr, gate, wcp, exe,
                          expected_writer_calls):
    invariants = (
        wcp.writerCalled is False and exe.writerCalled is False
        and wcp.outputCreated is False and exe.outputCreated is False
        and wcp.originalUnmodified and exe.originalUnmodified
    )
    return {
        "scenario": name,
        "planId": plan["planId"],
        "operations": [op["operationId"] for op in plan["operations"]],
        "dryRunVerdict": dr.verdict,
        "gateVerdict": gate.gateVerdict,
        "adapterVerdict": wcp.verdict,
        "adapterReadyForWriter": wcp.readyForWriter,
        "executorVerdict": exe.verdict,
        "executorReady": exe.readyForExecution,
        "writerCalls": len(wcp.writerCalls),
        "simulatedCalls": len(exe.simulatedCalls),
        "expectedWriterCalls": expected_writer_calls,
        "writerCallsAsExpected": len(wcp.writerCalls) == expected_writer_calls,
        "invariantsHeld": invariants,
    }


def run_audit() -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    c, d, g, a, e = _stages()
    parsed = _parse()
    t_id, cell = _first_text_cell(parsed)

    sha_before = hashlib.sha256(METADATA_FORM.read_bytes()).hexdigest()
    mtime_before = METADATA_FORM.stat().st_mtime

    scenarios = []

    # 1) AUTO
    plan1 = c.empty_plan_skeleton("plan-auto", "sha256:abc", "ai", "now")
    plan1["operations"] = [_ops_text(t_id, cell)]
    dr, gate, wcp, exe = _run_pipeline(c, d, g, a, e, plan1, [], parsed)
    scenarios.append(_scenario_summary("AUTO_setCellText", plan1, [],
                                            dr, gate, wcp, exe, 1))

    # 2) REVIEW approve
    plan2 = c.empty_plan_skeleton("plan-rv-ok", "sha256:abc", "ai", "now")
    plan2["operations"] = [_ops_fill(t_id, cell)]
    dr, gate, wcp, exe = _run_pipeline(c, d, g, a, e, plan2,
                                            [_decision(plan2["planId"], "op-fill", "APPROVE")],
                                            parsed)
    scenarios.append(_scenario_summary("REVIEW_approve_setCellFillColor", plan2, [],
                                            dr, gate, wcp, exe, 1))

    # 3) REVIEW reject
    plan3 = c.empty_plan_skeleton("plan-rv-rej", "sha256:abc", "ai", "now")
    plan3["operations"] = [_ops_fill(t_id, cell)]
    dr, gate, wcp, exe = _run_pipeline(c, d, g, a, e, plan3,
                                            [_decision(plan3["planId"], "op-fill", "REJECT")],
                                            parsed)
    scenarios.append(_scenario_summary("REVIEW_reject_setCellFillColor", plan3, [],
                                            dr, gate, wcp, exe, 0))

    # 4) REVIEW hold
    plan4 = c.empty_plan_skeleton("plan-rv-hold", "sha256:abc", "ai", "now")
    plan4["operations"] = [_ops_fill(t_id, cell)]
    dr, gate, wcp, exe = _run_pipeline(c, d, g, a, e, plan4,
                                            [_decision(plan4["planId"], "op-fill", "HOLD")],
                                            parsed)
    scenarios.append(_scenario_summary("REVIEW_hold_setCellFillColor", plan4, [],
                                            dr, gate, wcp, exe, 0))

    # 5) BLOCKED
    plan5 = c.empty_plan_skeleton("plan-blk", "sha256:abc", "ai", "now")
    plan5["operations"] = [_ops_move()]
    dr, gate, wcp, exe = _run_pipeline(c, d, g, a, e, plan5, [], parsed)
    scenarios.append(_scenario_summary("BLOCKED_moveObject", plan5, [],
                                            dr, gate, wcp, exe, 0))

    # 6) expectedBefore mismatch (no review decision → PENDING)
    plan6 = c.empty_plan_skeleton("plan-mis", "sha256:abc", "ai", "now")
    plan6["operations"] = [_ops_text(t_id, cell, op_id="op-mis",
                                          expected="WRONG_PREVIOUS_VALUE")]
    dr, gate, wcp, exe = _run_pipeline(c, d, g, a, e, plan6, [], parsed)
    scenarios.append(_scenario_summary("EXPECTED_BEFORE_MISMATCH", plan6, [],
                                            dr, gate, wcp, exe, 0))

    # 7) sourceDocumentHash missing
    plan7 = c.empty_plan_skeleton("plan-nohash", "", "ai", "now")
    plan7["operations"] = [_ops_text(t_id, cell)]
    dr, gate, wcp, exe = _run_pipeline(c, d, g, a, e, plan7, [], parsed)
    scenarios.append(_scenario_summary("SOURCE_HASH_MISSING", plan7, [],
                                            dr, gate, wcp, exe, 0))

    sha_after = hashlib.sha256(METADATA_FORM.read_bytes()).hexdigest()
    mtime_after = METADATA_FORM.stat().st_mtime
    source_unmodified = (sha_before == sha_after and mtime_before == mtime_after)

    all_invariants = all(s["invariantsHeld"] for s in scenarios)
    all_expected = all(s["writerCallsAsExpected"] for s in scenarios)
    verdict = "PASS" if (all_invariants and all_expected and source_unmodified) else "FAIL"

    summary = {
        "verdict": verdict,
        "scenarioCount": len(scenarios),
        "allInvariantsHeld": all_invariants,
        "allWriterCallsAsExpected": all_expected,
        "sourceUnmodified": source_unmodified,
        "scenarios": scenarios,
    }
    (OUTPUT_DIR / "integration_matrix.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    return summary


if __name__ == "__main__":
    print("[HWPX-EDIT-PLAN-PIPELINE-INTEGRATION-AUDIT-01]")
    result = run_audit()
    for s in result["scenarios"]:
        print(f"  {s['scenario']}: "
              f"dr={s['dryRunVerdict']} gate={s['gateVerdict']} "
              f"adapter={s['adapterVerdict']} exe={s['executorVerdict']} "
              f"calls={s['writerCalls']}/{s['expectedWriterCalls']} "
              f"inv={s['invariantsHeld']}")
    print("=" * 60)
    print(f"verdict: {result['verdict']}  "
          f"invariants={result['allInvariantsHeld']} "
          f"expected={result['allWriterCallsAsExpected']} "
          f"sourceUnmod={result['sourceUnmodified']}")
    sys.exit(0 if result["verdict"] == "PASS" else 1)
