"""HWPX Pipeline — reparse_verifier.

수정 전/후 ParserV2Result를 비교하여 편집 결과를 검증한다.
"""

from __future__ import annotations

import sys
from pathlib import Path

from .pipeline_contract import PlanResult, VerificationResult

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

_FATAL_WARN_CODES = {"XML_DECODE_FAIL", "SECTION_READ_FAIL", "ZIP_OPEN_FAIL"}


def _fatal_warning_code(after) -> str | None:
    for w in getattr(after, "warnings", []):
        code = getattr(w, "code", str(w))
        if code in _FATAL_WARN_CODES:
            return code
    return None


def _normalized_cell_texts(doc, *, labels_only: bool = False) -> set[str]:
    texts: set[str] = set()
    for tbl in getattr(doc, "tables", []):
        for cell in getattr(tbl, "cells", []):
            if labels_only and not getattr(cell, "isLikelyLabel", False):
                continue
            t = getattr(cell, "normalizedText", "") or ""
            if t:
                texts.add(t.strip())
    return texts


def _match_label_items(label_items, after_cells_text: set[str], result: VerificationResult) -> None:
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


def verify(before, after, plan_result: PlanResult) -> VerificationResult:
    """before/after ParserV2Result와 PlanResult를 비교 검증한다."""
    result = VerificationResult()

    # ── after 치명 경고 확인 ────────────────────────────────────────────────
    fatal_code = _fatal_warning_code(after)
    if fatal_code is not None:
        result.warnings.append(f"fatal_warning: {fatal_code}")
        result.decision = "FAIL"
        return result

    # ── after errors 확인 ───────────────────────────────────────────────────
    if getattr(after, "errors", []):
        result.warnings.append(
            f"after_parse_errors: {[getattr(e, 'code', str(e)) for e in after.errors]}"
        )
        result.decision = "FAIL"
        return result

    # ── 입력값 검증 ─────────────────────────────────────────────────────────
    plan = plan_result.editPlan
    label_items = plan.get("set_cells_by_label", [])

    # after cells를 normalizedText로 인덱싱
    after_cells_text = _normalized_cell_texts(after)
    _match_label_items(label_items, after_cells_text, result)

    # ── 라벨 셀 훼손 확인 ──────────────────────────────────────────────────
    before_labels = _normalized_cell_texts(before, labels_only=True)
    after_all_text = _normalized_cell_texts(after)

    damaged_labels = before_labels - after_all_text
    if damaged_labels:
        result.warnings.append(f"label_cells_damaged: {list(damaged_labels)[:5]}")

    # ── 최종 판정 ──────────────────────────────────────────────────────────
    if result.mismatched or result.warnings:
        result.decision = "REVIEW_REQUIRED"
    else:
        result.decision = "PASS"

    return result
