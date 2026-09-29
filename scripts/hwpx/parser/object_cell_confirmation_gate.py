"""HWPX-RECOGNITION-OBJECT-CELL-GEOMETRIC-CONFIRMATION-GATE-01

geometricCandidates[]에 대한 사람 승인/반려/보류 결정을 적용하는 게이트.

핵심 보호:
- XML ancestry confidence=1.0 매핑(DESCENDANT_OF_TC)은 절대 덮어쓰지 않는다.
- ambiguous=True 후보는 APPROVE가 들어와도 자동 승격 금지.
- NO_GEOMETRY / NO_CELL_GEOMETRY 후보는 APPROVE되어도 승격 금지.
- 동일 objectKey에 대한 중복 APPROVE는 모두 차단.
- 승격된 mapping의 confidence는 원 candidate의 confidence를 넘지 않으며 1.0이 되지 않는다.

이 모듈은 writer를 호출하지 않으며 output HWPX 파일을 만들지 않는다. 입력 result
객체는 mutate되지 않고 deepcopy된 결과가 반환된다.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass

from .object_cell_mapper import (
    ObjectCellMappingEntry,
    ObjectCellMappingResult,
)

ALLOWED_DECISIONS: frozenset[str] = frozenset({"APPROVE", "REJECT", "HOLD"})

# candidate reason → 승격 시 사용할 mapping reason
_CONFIRMED_REASON_BY_CANDIDATE: dict[str, str] = {
    "CENTER_INSIDE_CELL": "CONFIRMED_CENTER_INSIDE_CELL",
    "BBOX_OVERLAP": "CONFIRMED_BBOX_OVERLAP",
    "NEAREST_CELL": "CONFIRMED_NEAREST_CELL",
}

# 절대 승격 금지 reason
_UNPROMOTABLE_REASONS: frozenset[str] = frozenset({
    "NO_GEOMETRY",
    "NO_CELL_GEOMETRY",
})


@dataclass
class ConfirmationResultEntry:
    objectKey: str
    candidateCellKey: str | None
    decision: str
    status: str  # CONFIRMED / REJECTED / HELD / BLOCKED
    reason: str  # 원 candidate reason 또는 사유 문자열
    promoted: bool
    blockedReason: str | None = None

    def to_dict(self) -> dict:
        return {
            "objectKey": self.objectKey,
            "candidateCellKey": self.candidateCellKey,
            "decision": self.decision,
            "status": self.status,
            "reason": self.reason,
            "promoted": self.promoted,
            "blockedReason": self.blockedReason,
        }


def _decision_dict_valid(d) -> bool:
    if not isinstance(d, dict):
        return False
    # candidateCellKey는 None일 수 있다 (NO_GEOMETRY/NO_CELL_GEOMETRY 후보용)
    if "candidateCellKey" not in d:
        return False
    if d.get("objectKey") is None or d.get("decision") is None:
        return False
    return True


def _find_candidate(
    result: ObjectCellMappingResult, object_key: str, candidate_cell_key
) -> object | None:
    for cand in result.geometricCandidates:
        if cand.objectKey == object_key and cand.candidateCellKey == candidate_cell_key:
            return cand
    return None


def _already_descendant_mapped(result: ObjectCellMappingResult, object_key: str) -> bool:
    for m in result.mappings:
        if m.objectKey == object_key and m.reason == "DESCENDANT_OF_TC":
            return True
    return False


def _check_approve_guards(
    cand: object,
    object_key: str,
    out: ObjectCellMappingResult,
    duplicate_approve_object_keys: set[str],
    new_promoted_objects: set[str],
) -> str | None:
    """APPROVE 승격 전 가드 체인. 차단 사유 문자열을 반환하거나(차단), None(승격 가능)."""
    if object_key in duplicate_approve_object_keys:
        return "DUPLICATE_APPROVAL_FOR_OBJECT"
    if _already_descendant_mapped(out, object_key):
        return "ALREADY_MAPPED_BY_XML_ANCESTRY"
    if getattr(cand, "ambiguous", False):
        return "AMBIGUOUS_CANDIDATE"
    if cand.reason in _UNPROMOTABLE_REASONS:
        return cand.reason
    if cand.confidence >= 1.0:
        return "CONFIDENCE_NOT_BELOW_ONE"
    if object_key in new_promoted_objects:
        return "DUPLICATE_APPROVAL_FOR_OBJECT"
    if _CONFIRMED_REASON_BY_CANDIDATE.get(cand.reason) is None:
        return "UNKNOWN_CANDIDATE_REASON"
    return None


def _promote_candidate(out: ObjectCellMappingResult, object_key: str, cand: object) -> None:
    confirmed_reason = _CONFIRMED_REASON_BY_CANDIDATE[cand.reason]
    base_entry = next((m for m in out.mappings if m.objectKey == object_key), None)
    section_index = base_entry.sectionIndex if base_entry else 0
    object_type = cand.objectType or (base_entry.objectType if base_entry else "unknown")
    object_raw_tag = base_entry.objectRawTag if base_entry else ""
    bin_data_ref = base_entry.binDataRef if base_entry else None
    is_image_like = base_entry.isImageLike if base_entry else False

    promoted_entry = ObjectCellMappingEntry(
        objectKey=object_key,
        objectType=object_type,
        objectRawTag=object_raw_tag,
        sectionIndex=section_index,
        tableIndex=cand.tableIndex,
        rowIndex=cand.rowIndex,
        cellIndex=cand.cellIndex,
        cellKey=cand.candidateCellKey,
        cellText=cand.cellText,
        rowSpan=None,
        colSpan=None,
        binDataRef=bin_data_ref,
        confidence=min(cand.confidence, 0.999),
        reason=confirmed_reason,
        isImageLike=is_image_like,
    )
    out.mappings.append(promoted_entry)


def _process_one_decision(
    d: object,
    out: ObjectCellMappingResult,
    duplicate_approve_object_keys: set[str],
    new_promoted_objects: set[str],
) -> str:
    """반환값: 'confirmed' / 'rejected' / 'held' / 'blocked' (카운터 증가용)."""
    if not _decision_dict_valid(d):
        out.confirmationResults.append(
            ConfirmationResultEntry(
                objectKey=(d.get("objectKey") if isinstance(d, dict) else "") or "",
                candidateCellKey=(d.get("candidateCellKey") if isinstance(d, dict) else None),
                decision=(d.get("decision") if isinstance(d, dict) else "") or "",
                status="BLOCKED",
                reason="invalid_shape",
                promoted=False,
                blockedReason="INVALID_DECISION",
            )
        )
        return "blocked"

    object_key = d["objectKey"]
    cand_cell_key = d.get("candidateCellKey")
    decision_val = d["decision"]

    if decision_val not in ALLOWED_DECISIONS:
        out.confirmationResults.append(
            ConfirmationResultEntry(
                objectKey=object_key,
                candidateCellKey=cand_cell_key,
                decision=decision_val,
                status="BLOCKED",
                reason="invalid_decision_value",
                promoted=False,
                blockedReason="INVALID_DECISION",
            )
        )
        return "blocked"

    cand = _find_candidate(out, object_key, cand_cell_key)
    if cand is None:
        out.confirmationResults.append(
            ConfirmationResultEntry(
                objectKey=object_key,
                candidateCellKey=cand_cell_key,
                decision=decision_val,
                status="BLOCKED",
                reason="candidate_not_found",
                promoted=False,
                blockedReason="CANDIDATE_NOT_FOUND",
            )
        )
        return "blocked"

    if decision_val == "REJECT":
        out.confirmationResults.append(
            ConfirmationResultEntry(
                objectKey=object_key,
                candidateCellKey=cand_cell_key,
                decision="REJECT",
                status="REJECTED",
                reason=cand.reason,
                promoted=False,
                blockedReason=None,
            )
        )
        return "rejected"

    if decision_val == "HOLD":
        out.confirmationResults.append(
            ConfirmationResultEntry(
                objectKey=object_key,
                candidateCellKey=cand_cell_key,
                decision="HOLD",
                status="HELD",
                reason=cand.reason,
                promoted=False,
                blockedReason=None,
            )
        )
        return "held"

    # APPROVE 처리
    blocked_reason = _check_approve_guards(
        cand, object_key, out, duplicate_approve_object_keys, new_promoted_objects
    )
    if blocked_reason is not None:
        out.confirmationResults.append(
            ConfirmationResultEntry(
                objectKey=object_key,
                candidateCellKey=cand_cell_key,
                decision="APPROVE",
                status="BLOCKED",
                reason=cand.reason,
                promoted=False,
                blockedReason=blocked_reason,
            )
        )
        return "blocked"

    _promote_candidate(out, object_key, cand)
    new_promoted_objects.add(object_key)
    out.confirmationResults.append(
        ConfirmationResultEntry(
            objectKey=object_key,
            candidateCellKey=cand_cell_key,
            decision="APPROVE",
            status="CONFIRMED",
            reason=cand.reason,
            promoted=True,
            blockedReason=None,
        )
    )
    return "confirmed"


def apply_geometric_confirmation(
    result: ObjectCellMappingResult, decisions: list[dict]
) -> ObjectCellMappingResult:
    """geometric candidate에 사람 결정을 적용.

    원본 result는 mutate되지 않는다. deepcopy된 새 result를 반환.
    """
    out = copy.deepcopy(result)
    decisions = decisions or []
    out.confirmationApplied = True
    out.confirmationDecisionCount = len(decisions)

    # 1) APPROVE 결정의 objectKey 카운트 (중복 차단용)
    approve_counts: dict[str, int] = {}
    for d in decisions:
        if isinstance(d, dict) and d.get("decision") == "APPROVE":
            ok = d.get("objectKey")
            if ok is not None:
                approve_counts[ok] = approve_counts.get(ok, 0) + 1
    duplicate_approve_object_keys: set[str] = {k for k, v in approve_counts.items() if v >= 2}

    new_promoted_objects: set[str] = set()  # 같은 객체가 여러 후보 승격 시도되는 것을 방지

    outcomes = {"confirmed": 0, "rejected": 0, "held": 0, "blocked": 0}
    for d in decisions:
        outcome = _process_one_decision(d, out, duplicate_approve_object_keys, new_promoted_objects)
        outcomes[outcome] += 1

    out.confirmedMappingCount = outcomes["confirmed"]
    out.rejectedCandidateCount = outcomes["rejected"]
    out.heldCandidateCount = outcomes["held"]
    out.blockedConfirmationCount = outcomes["blocked"]
    # mappedObjectCount는 mappings[] 변화에 맞춰 재계산 (DESCENDANT + CONFIRMED 모두 포함)
    out.mappedObjectCount = sum(1 for m in out.mappings if m.cellKey is not None)
    return out
