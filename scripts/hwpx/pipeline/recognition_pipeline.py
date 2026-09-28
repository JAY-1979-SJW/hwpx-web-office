"""HWPX Pipeline — recognition_pipeline.

전체 파이프라인 흐름 조립:
parse_before → recognize → plan → edit → parse_after → compare → hancom_verify → final_decision
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import Any

from .pipeline_contract import (
    PipelineResult, RecognitionResult, make_request_id,
)
from .plan_builder import build_edit_plan, build_edit_plan_from_form
from .form_recognizer import recognize_form
from .reparse_verifier import verify as reparse_verify
from .hancom_safe_gate import verify as hancom_verify

_SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
_HWPX_DIR = _SCRIPTS / "hwpx"
for _p in [str(_SCRIPTS), str(_HWPX_DIR)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from hwpx.parser import parse_hwpx_v2  # type: ignore


def _recognize(parser_result) -> RecognitionResult:
    """ParserV2Result에서 inputSlotCandidates를 분석해 RecognitionResult를 생성."""
    rec = RecognitionResult()

    candidates = getattr(parser_result, "inputSlotCandidates", []) or []
    if not candidates:
        rec.reviewRequired = True
        return rec

    # fieldGuess별로 가장 confidence 높은 슬롯 선택
    best: dict[str, Any] = {}
    for slot in candidates:
        fg = getattr(slot, "fieldGuess", "unknown")
        if fg == "unknown":
            continue
        existing = best.get(fg)
        if existing is None or getattr(slot, "confidence", 0) > getattr(existing, "confidence", 0):
            best[fg] = slot

    rec.slotMap = best
    rec.detectedLabels = [getattr(s, "labelText", "") for s in best.values()]

    if best:
        rec.confidence = sum(getattr(s, "confidence", 0) for s in best.values()) / len(best)
    else:
        rec.confidence = 0.0

    rec.reviewRequired = rec.confidence < 0.70
    return rec


def run_pipeline(
    input_path: Path,
    output_path: Path,
    field_values: dict[str, str],
    *,
    request_id: str | None = None,
) -> PipelineResult:
    """전체 파이프라인을 실행하고 PipelineResult를 반환한다."""
    rid = request_id or make_request_id()
    result = PipelineResult(
        requestId=rid,
        inputFile=hashlib.sha256(str(input_path).encode()).hexdigest()[:16],
        outputFile=str(output_path),
    )

    # ── 1. parse_before ─────────────────────────────────────────────────────
    try:
        before = parse_hwpx_v2(input_path)
        result.stages["parse_before"] = "ok"
    except Exception as exc:
        result.errors.append(f"parse_before_failed: {exc}")
        result.stages["parse_before"] = "error"
        result.finalDecision = "FAIL"
        return result

    if getattr(before, "errors", []):
        result.errors.append(f"parser_errors: {[getattr(e,'code',str(e)) for e in before.errors]}")
        result.stages["parse_before"] = "error"
        result.finalDecision = "FAIL"
        return result

    # ── 2. recognize (form_recognizer 우선) ─────────────────────────────────
    form_rec = None
    try:
        form_rec = recognize_form(before)
        result.formType = form_rec.formType
        result.tableRoles = form_rec.tableRoles
        result.inputSlots = form_rec.enhancedSlots
        result.unsafeTargets = form_rec.unsafeTableIds
        result.stages["recognize"] = "review_required" if form_rec.reviewRequired else "ok"
    except Exception as exc:
        result.warnings.append(f"form_recognize_failed: {exc}")
        result.stages["recognize"] = "error"

    try:
        rec = _recognize(before)
        result.recognition = rec
    except Exception as exc:
        result.warnings.append(f"recognize_failed: {exc}")
        rec = RecognitionResult(reviewRequired=True)
        result.recognition = rec

    # ── 3. plan ─────────────────────────────────────────────────────────────
    try:
        if form_rec and form_rec.enhancedSlots:
            plan_result = build_edit_plan_from_form(form_rec, field_values)
        else:
            plan_result = build_edit_plan(rec, field_values)
        result.plan = plan_result
        result.generatedPlans = plan_result.plannedFields
        result.skippedFields = plan_result.skippedFields
        result.reviewRequiredFields = list(plan_result.reviewRequiredReasons.keys())
        result.stages["plan"] = "ok" if plan_result.plannedFields else "partial"
    except Exception as exc:
        result.errors.append(f"plan_failed: {exc}")
        result.stages["plan"] = "error"
        result.finalDecision = "FAIL"
        return result

    if not plan_result.editPlan:
        result.warnings.append("empty_edit_plan: no fields planned")
        result.stages["edit"] = "skipped"
        result.finalDecision = "REVIEW_REQUIRED"
        return result

    # ── 4. edit ─────────────────────────────────────────────────────────────
    try:
        from hwpx_edit_tool import apply_edit_plan  # type: ignore
        edit_report = apply_edit_plan(input_path, output_path, plan_result.editPlan)
        if edit_report.get("errors"):
            result.errors.extend(edit_report["errors"])
            result.stages["edit"] = "error"
            result.finalDecision = "FAIL"
            return result
        result.stages["edit"] = "ok"
    except Exception as exc:
        result.errors.append(f"edit_failed: {exc}")
        result.stages["edit"] = "error"
        result.finalDecision = "FAIL"
        return result

    # ── 5. parse_after ──────────────────────────────────────────────────────
    try:
        after = parse_hwpx_v2(output_path)
        result.stages["parse_after"] = "ok"
    except Exception as exc:
        result.warnings.append(f"parse_after_failed: {exc}")
        result.stages["parse_after"] = "error"
        result.finalDecision = "REVIEW_REQUIRED"
        return result

    # ── 6. compare (reparse verify) ─────────────────────────────────────────
    try:
        vr = reparse_verify(before, after, plan_result)
        result.verification = vr
        result.stages["compare"] = vr.decision
    except Exception as exc:
        result.warnings.append(f"reparse_verify_failed: {exc}")
        result.stages["compare"] = "error"

    # ── 7. hancom_verify ────────────────────────────────────────────────────
    try:
        hv = hancom_verify(output_path)
        result.hancomVerify = hv
        result.stages["hancom_verify"] = hv.verdict
    except Exception as exc:
        result.warnings.append(f"hancom_verify_failed: {exc}")
        result.stages["hancom_verify"] = "error"
        result.hancomVerify.verdict = "error"

    # ── 8. final_decision ───────────────────────────────────────────────────
    hv_verdict = result.hancomVerify.verdict
    cmp_decision = result.verification.decision

    if hv_verdict == "PASS" and cmp_decision == "PASS":
        result.finalDecision = "PASS"
    elif hv_verdict == "FAIL" or cmp_decision == "FAIL":
        result.finalDecision = "FAIL"
    else:
        result.finalDecision = "REVIEW_REQUIRED"

    return result
