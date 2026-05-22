"""HWPX Pipeline — reparse_verifier.

수정 전/후 ParserV2Result를 비교하여 편집 결과를 검증한다.
"""
from __future__ import annotations

import sys
from pathlib import Path

from .pipeline_contract import PlanResult, VerificationResult

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

_FATAL_WARN_CODES = {"XML_DECODE_FAIL", "SECTION_READ_FAIL", "ZIP_OPEN_FAIL"}


def verify(before, after, plan_result: PlanResult) -> VerificationResult:
    """before/after ParserV2Result와 PlanResult를 비교 검증한다."""
    result = VerificationResult()

    # ── after 치명 경고 확인 ────────────────────────────────────────────────
    for w in getattr(after, "warnings", []):
        code = getattr(w, "code", str(w))
        if code in _FATAL_WARN_CODES:
            result.warnings.append(f"fatal_warning: {code}")
            result.decision = "FAIL"
            return result

    # ── after errors 확인 ───────────────────────────────────────────────────
    if getattr(after, "errors", []):
        result.warnings.append(f"after_parse_errors: {[getattr(e,'code',str(e)) for e in after.errors]}")
        result.decision = "FAIL"
        return result

    # ── 입력값 검증 ─────────────────────────────────────────────────────────
    plan = plan_result.editPlan
    label_items = plan.get("set_cells_by_label", [])

    # after cells를 normalizedText로 인덱싱
    after_cells_text: set[str] = set()
    for tbl in getattr(after, "tables", []):
        for cell in getattr(tbl, "cells", []):
            t = getattr(cell, "normalizedText", "") or ""
            if t:
                after_cells_text.add(t.strip())

    for item in label_items:
        value = item.get("value", "").strip()
        label = item.get("contains", "")
        result.expectedFields[label] = value

        if value in after_cells_text:
            result.matched.append(label)
            result.actualFields[label] = value
        else:
            result.mismatched.append(label)
            result.actualFields[label] = ""

    # ── 라벨 셀 훼손 확인 ──────────────────────────────────────────────────
    before_labels: set[str] = set()
    for tbl in getattr(before, "tables", []):
        for cell in getattr(tbl, "cells", []):
            if getattr(cell, "isLikelyLabel", False):
                t = getattr(cell, "normalizedText", "") or ""
                if t:
                    before_labels.add(t.strip())

    after_all_text: set[str] = set()
    for tbl in getattr(after, "tables", []):
        for cell in getattr(tbl, "cells", []):
            t = getattr(cell, "normalizedText", "") or ""
            if t:
                after_all_text.add(t.strip())

    damaged_labels = before_labels - after_all_text
    if damaged_labels:
        result.warnings.append(f"label_cells_damaged: {list(damaged_labels)[:5]}")

    # ── 최종 판정 ──────────────────────────────────────────────────────────
    if result.mismatched:
        result.decision = "REVIEW_REQUIRED"
    elif result.warnings:
        result.decision = "REVIEW_REQUIRED"
    else:
        result.decision = "PASS"

    return result
