"""HWPX Pipeline — reparse_verifier.

수정 전/후 ParserV2Result를 비교하여 편집 결과를 검증한다.
"""

from __future__ import annotations

import sys
from pathlib import Path

from .form_recognizer import table_ordinals
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


def _readback_visual_items(visual_items, after, result: VerificationResult) -> None:
    """set_visual_cells 로 쓴 칸을 다시 읽어 값이 그대로 들어갔는지 확인한다.

    표 번호(table)는 편집기 기준 문서 전체 순번이라 table_ordinals 로 되돌려 찾는다.
    """
    tables = getattr(after, "tables", []) or []
    by_ordinal = {ordinal: tid for tid, ordinal in table_ordinals(tables).items()}
    cells_by_id = {
        t.tableId: {(c.visualRow, c.visualCol): c for c in getattr(t, "cells", [])} for t in tables
    }
    for item in visual_items:
        table_no, row, col = item.get("table"), item.get("visual_row"), item.get("visual_col")
        key = f"table{table_no}:r{row}c{col}"
        value = str(item.get("value", "")).strip()
        result.expectedFields[key] = value
        cell = cells_by_id.get(by_ordinal.get(table_no, ""), {}).get((row, col))
        actual = (getattr(cell, "normalizedText", "") or "").strip() if cell else ""
        result.actualFields[key] = actual
        if cell is not None and actual == " ".join(value.split()):
            result.matched.append(key)
        else:
            result.mismatched.append(key)


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

    visual_items = plan.get("set_visual_cells", [])
    _readback_visual_items(visual_items, after, result)

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
    # 쓴 칸을 하나도 다시 읽어 확인하지 못했거나(검증할 게 없음) 값이 다르면 통과가 아니다.
    if not result.matched and not result.mismatched:
        result.warnings.append("nothing_to_verify: no written cell was read back")
        result.decision = "FAIL"
    elif result.mismatched:
        result.decision = "FAIL"
    elif result.warnings:
        result.decision = "REVIEW_REQUIRED"
    else:
        result.decision = "PASS"

    return result
