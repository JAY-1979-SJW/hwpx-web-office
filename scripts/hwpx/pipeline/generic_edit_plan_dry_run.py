"""HWPX-EDIT-PLAN-EXECUTOR-DRY-RUN-01

edit_plan_v1 계약 위에서 동작하는 dry-run 실행기.

이 모듈은 실제 HWPX writer를 호출하지 않는다. 원본 파일을 수정하지 않으며
output HWPX를 생성하지도 않는다. plan과 parser_result만 받아서:
  - validate_edit_plan으로 schema 검증
  - 각 operation의 expectedBefore vs 현재 parser snapshot 비교
  - 예상 변경(expectedChanges) 산출
  - autoExecutable / review / blocked 재분류
하는 모의시공만 수행한다.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from . import generic_edit_plan_contract as contract


# ── 결과 dataclass ────────────────────────────────────────────────────────────

@dataclass
class ExpectedChange:
    operationId: str
    operationType: str
    target: dict
    before: Any = None
    after: Any = None
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "operationId": self.operationId,
            "operationType": self.operationType,
            "target": self.target,
            "before": self.before,
            "after": self.after,
            "note": self.note,
        }


@dataclass
class SafetyFinding:
    code: str
    detail: str
    operationId: str | None = None

    def to_dict(self) -> dict:
        return {"code": self.code, "detail": self.detail,
                "operationId": self.operationId}


@dataclass
class DryRunResult:
    dryRunId: str = ""
    planId: str = ""
    schemaVersion: str = contract.SCHEMA_VERSION
    verdict: str = "BLOCKED_INVALID_PLAN"
    autoExecutable: bool = False
    autoAllowedOps: list[str] = field(default_factory=list)
    reviewRequiredOps: list[str] = field(default_factory=list)
    blockedOps: list[str] = field(default_factory=list)
    expectedChanges: list[ExpectedChange] = field(default_factory=list)
    safetyFindings: list[SafetyFinding] = field(default_factory=list)
    sourceDocumentHashMatched: bool | None = None
    originalUnmodified: bool = True
    writerCalled: bool = False
    outputCreated: bool = False

    def to_dict(self) -> dict:
        return {
            "dryRunId": self.dryRunId,
            "planId": self.planId,
            "schemaVersion": self.schemaVersion,
            "verdict": self.verdict,
            "autoExecutable": self.autoExecutable,
            "autoAllowedOps": self.autoAllowedOps,
            "reviewRequiredOps": self.reviewRequiredOps,
            "blockedOps": self.blockedOps,
            "expectedChanges": [c.to_dict() for c in self.expectedChanges],
            "safetyFindings": [f.to_dict() for f in self.safetyFindings],
            "sourceDocumentHashMatched": self.sourceDocumentHashMatched,
            "originalUnmodified": self.originalUnmodified,
            "writerCalled": self.writerCalled,
            "outputCreated": self.outputCreated,
        }


# ── target lookup ─────────────────────────────────────────────────────────────

def _find_cell(parser_result, table_id: str, row: int, col: int):
    """parser_result.tables[*].cells에서 (tableId,row,col) 셀 검색."""
    if parser_result is None:
        return None
    for t in getattr(parser_result, "tables", []) or []:
        if getattr(t, "tableId", "") != table_id:
            continue
        for c in t.cells:
            if c.row == row and c.col == col:
                return c
    return None


def _current_value_for(op_type: str, cell) -> Any:
    if cell is None:
        return None
    mapping = {
        "setCellText": cell.normalizedText or cell.text,
        "setCellHorizontalAlign": cell.horizontalAlign,
        "setCellVerticalAlign": cell.verticalAlign,
        "setCellFillColor": cell.fillColor,
        "setCellTextStyle": {
            "bold": cell.bold, "italic": cell.italic,
            "underline": cell.underline, "textColor": cell.textColor,
        },
        "setParagraphText": (cell.paragraphs[0] if cell.paragraphs else ""),
        "replaceTextRun": cell.normalizedText or cell.text,
    }
    return mapping.get(op_type)


# ── dry-run 본체 ──────────────────────────────────────────────────────────────

def dry_run_edit_plan(plan: dict, parser_result=None,
                       source_document_hash: str | None = None) -> DryRunResult:
    """plan을 dry-run으로 실행. writer 미호출, output 미생성, 원본 무수정.

    parser_result: ParserV2Result (None이면 target lookup 검증 생략)
    source_document_hash: 호출자가 source 파일에서 계산해 넘긴 sha (옵션)
    """
    result = DryRunResult(
        dryRunId=str(uuid.uuid4()),
        planId=(plan.get("planId", "") if isinstance(plan, dict) else ""),
    )

    # 1) 계약 검증 먼저 (스키마/금지/expectedBefore 누락 등)
    val = contract.validate_edit_plan(plan)
    result.autoAllowedOps = list(val.autoAllowedOps)
    result.reviewRequiredOps = list(val.reviewRequiredOps)
    result.blockedOps = list(val.blockedOps)
    for issue in val.issues:
        result.safetyFindings.append(SafetyFinding(
            code=issue.code, detail=issue.detail, operationId=issue.operationId,
        ))

    if val.verdict == "BLOCKED_INVALID_PLAN":
        result.verdict = "BLOCKED_INVALID_PLAN"
        result.autoExecutable = False
        return result

    # 2) sourceDocumentHash 매칭 (caller가 넘긴 경우만)
    if source_document_hash is not None:
        result.sourceDocumentHashMatched = (
            plan.get("sourceDocumentHash") == source_document_hash
        )
        if not result.sourceDocumentHashMatched:
            result.safetyFindings.append(SafetyFinding(
                "SOURCE_HASH_MISMATCH",
                f"plan.sourceDocumentHash={plan.get('sourceDocumentHash')!r} "
                f"!= actual={source_document_hash!r}",
            ))

    # 3) operation별 모의시공
    auto_ops = set(val.autoAllowedOps)
    review_ops = set(val.reviewRequiredOps)
    blocked_ops = set(val.blockedOps)
    demoted_to_review: list[str] = []
    demoted_to_blocked: list[str] = []

    for op in plan.get("operations", []):
        op_id = op.get("operationId", "")
        op_type = op.get("operationType", "")
        target = op.get("target", {}) or {}

        if op_id in blocked_ops:
            continue   # contract 단계에서 이미 blocked

        # target lookup (셀 ops만 검증)
        cell = None
        # replaceTextRun은 셀 좌표(tableId+row+col)일 수도, paragraph 좌표일 수도 있다.
        # tableId가 있으면 셀 ops로 다루고, paragraphKey/paragraphIndex만 있으면 paragraph 좌표로 본다.
        _cell_lookup_ops = {"setCellText", "setCellHorizontalAlign",
                              "setCellVerticalAlign", "setCellFillColor",
                              "setCellTextStyle"}
        if op_type == "replaceTextRun" and target.get("tableId"):
            _cell_lookup_ops = _cell_lookup_ops | {"replaceTextRun"}
        if op_type in _cell_lookup_ops:
            cell = _find_cell(parser_result, target.get("tableId"),
                                target.get("row"), target.get("col"))
            if parser_result is not None and cell is None:
                result.safetyFindings.append(SafetyFinding(
                    "TARGET_CELL_NOT_FOUND",
                    f"tableId={target.get('tableId')!r} "
                    f"row={target.get('row')} col={target.get('col')}",
                    op_id,
                ))
                # auto/review 어디였든 BLOCKED로 강등
                if op_id in auto_ops:
                    auto_ops.discard(op_id); blocked_ops.add(op_id)
                    demoted_to_blocked.append(op_id)
                elif op_id in review_ops:
                    review_ops.discard(op_id); blocked_ops.add(op_id)
                    demoted_to_blocked.append(op_id)
                continue

        # expectedBefore 일치성 검증
        if parser_result is not None and cell is not None:
            current = _current_value_for(op_type, cell)
            expected_before = op.get("expectedBefore")
            if expected_before is not None and current != expected_before:
                result.safetyFindings.append(SafetyFinding(
                    "EXPECTED_BEFORE_MISMATCH",
                    f"expected={expected_before!r} actual={current!r}",
                    op_id,
                ))
                # auto였으면 review로 강등
                if op_id in auto_ops:
                    auto_ops.discard(op_id); review_ops.add(op_id)
                    demoted_to_review.append(op_id)

        # 예상 변경 산출 (auto / review 모두 포함, blocked는 제외)
        if op_id in blocked_ops:
            continue
        before = _current_value_for(op_type, cell) if cell is not None else op.get("expectedBefore")
        after = op.get("value")
        note = ""
        if op_id in review_ops:
            note = "review_required"
        result.expectedChanges.append(ExpectedChange(
            operationId=op_id, operationType=op_type,
            target=target, before=before, after=after, note=note,
        ))

    # 4) 최종 분류
    result.autoAllowedOps = sorted(auto_ops)
    result.reviewRequiredOps = sorted(review_ops)
    result.blockedOps = sorted(blocked_ops)

    if result.blockedOps and not result.autoAllowedOps and not result.reviewRequiredOps:
        result.verdict = "BLOCKED_UNSAFE"
    elif result.blockedOps:
        # 일부 blocked + 일부 살아남음 → 안전 보수적으로 review로 보고
        result.verdict = "REVIEW_REQUIRED"
    elif result.reviewRequiredOps:
        result.verdict = "REVIEW_REQUIRED"
    else:
        result.verdict = "PASS_AUTO_ALLOWED"

    result.autoExecutable = (
        result.verdict == "PASS_AUTO_ALLOWED"
        and len(result.blockedOps) == 0
        and len(result.reviewRequiredOps) == 0
        and (result.sourceDocumentHashMatched is not False)
    )

    # writer 호출 안 함, output 생성 안 함, 원본 무수정 (불변)
    result.writerCalled = False
    result.outputCreated = False
    result.originalUnmodified = True
    return result
