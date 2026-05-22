"""
HWPX-FORM-HUMAN-APPROVAL-GATE-01

approval_gate.py — 사용자 결정을 받아 writerEligible 승인 목록 생성.

입력:  ReviewPanel (review_panel.py)  +  FieldDecision 목록
출력:  ApprovalResult
         - approvedFields  : writerEligible=True 항목
         - pendingFields   : HOLD / REQUEST_ATTACHMENT 항목
         - writerEnabled   : 항상 False (writer 실행은 다음 공정)

결정 유형:
    CONFIRM_FIELD      — 값 그대로 확정 → writerEligible=True
    EDIT_VALUE         — 사용자 수정값으로 확정 → writerEligible=True
    HOLD               — 보류 → writerEligible=False
    REQUEST_ATTACHMENT — 첨부서류 요청 후 재검토 → writerEligible=False

금지:
    - writer 실행 금지
    - HWPX 수정 금지
    - 자동입력 금지
    - AI/OCR 호출 금지
    - writerEnabled=True 설정 금지 (이 모듈에서)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

GATE_VERSION = "v1"

# 결정 유형 상수
ACTION_CONFIRM    = "CONFIRM_FIELD"
ACTION_EDIT       = "EDIT_VALUE"
ACTION_HOLD       = "HOLD"
ACTION_ATTACHMENT = "REQUEST_ATTACHMENT"

_VALID_ACTIONS = frozenset({ACTION_CONFIRM, ACTION_EDIT, ACTION_HOLD, ACTION_ATTACHMENT})

# PII 마스킹 (editedValue 포함)
_PII_MASK = re.compile(r"\d{6}-\d{7}|\d{3}-\d{2}-\d{5}")


def _mask(value: str) -> str:
    return _PII_MASK.sub("[MASKED]", value)


# ── 데이터 클래스 ─────────────────────────────────────────────────────────────

@dataclass
class FieldDecision:
    """사용자 한 필드에 대한 결정."""
    fieldKey: str
    action: str                    # CONFIRM_FIELD / EDIT_VALUE / HOLD / REQUEST_ATTACHMENT
    editedValue: str = ""          # EDIT_VALUE 시 사용자 입력값
    comment: str = ""              # 선택적 비고

    def __post_init__(self):
        if self.action not in _VALID_ACTIONS:
            raise ValueError(f"Invalid action '{self.action}'. Must be one of {sorted(_VALID_ACTIONS)}")


@dataclass
class ApprovedField:
    """writerEligible=True로 확정된 필드."""
    fieldKey: str
    label: str
    value: str                     # 확정 값 (PII 마스킹)
    originalValue: str             # 패널 원본값 (PII 마스킹)
    action: str                    # CONFIRM_FIELD / EDIT_VALUE
    sourceZone: str                # autoFillReady / needsReview / missingRequired / missingOptional
    confidence: float              # 패널의 confidence (EDIT_VALUE는 1.0)
    writerEligible: bool = True    # 항상 True (이 목록에 들어오는 조건)
    comment: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "fieldKey":      self.fieldKey,
            "label":         self.label,
            "value":         _mask(self.value),
            "originalValue": _mask(self.originalValue),
            "action":        self.action,
            "sourceZone":    self.sourceZone,
            "confidence":    round(self.confidence, 3),
            "writerEligible": self.writerEligible,
            "comment":       self.comment,
        }


@dataclass
class PendingField:
    """HOLD / REQUEST_ATTACHMENT으로 보류된 필드."""
    fieldKey: str
    label: str
    action: str                    # HOLD / REQUEST_ATTACHMENT
    sourceZone: str
    reason: str = ""               # 보류 사유
    writerEligible: bool = False   # 항상 False

    def to_dict(self) -> dict[str, Any]:
        return {
            "fieldKey":      self.fieldKey,
            "label":         self.label,
            "action":        self.action,
            "sourceZone":    self.sourceZone,
            "reason":        self.reason,
            "writerEligible": self.writerEligible,
        }


@dataclass
class ApprovalSummary:
    totalDecisions:      int
    confirmedCount:      int
    editedCount:         int
    holdCount:           int
    attachmentCount:     int
    writerEligibleCount: int
    undecidedCount:      int   # 패널에 있지만 결정 미제출된 필드 수

    def to_dict(self) -> dict[str, Any]:
        return {
            "totalDecisions":      self.totalDecisions,
            "confirmedCount":      self.confirmedCount,
            "editedCount":         self.editedCount,
            "holdCount":           self.holdCount,
            "attachmentCount":     self.attachmentCount,
            "writerEligibleCount": self.writerEligibleCount,
            "undecidedCount":      self.undecidedCount,
        }


@dataclass
class ApprovalResult:
    gateVersion:    str = GATE_VERSION
    formId:         str = ""
    formName:       str = ""
    writerEnabled:  bool = False   # 항상 False — writer는 다음 공정
    approvedFields: list[ApprovedField] = field(default_factory=list)
    pendingFields:  list[PendingField]  = field(default_factory=list)

    @property
    def summary(self) -> ApprovalSummary:
        confirmed   = sum(1 for f in self.approvedFields if f.action == ACTION_CONFIRM)
        edited      = sum(1 for f in self.approvedFields if f.action == ACTION_EDIT)
        hold_cnt    = sum(1 for f in self.pendingFields  if f.action == ACTION_HOLD)
        attach_cnt  = sum(1 for f in self.pendingFields  if f.action == ACTION_ATTACHMENT)
        return ApprovalSummary(
            totalDecisions      = len(self.approvedFields) + len(self.pendingFields),
            confirmedCount      = confirmed,
            editedCount         = edited,
            holdCount           = hold_cnt,
            attachmentCount     = attach_cnt,
            writerEligibleCount = len(self.approvedFields),
            undecidedCount      = 0,  # apply_decisions()에서 별도 계산
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "gateVersion":   self.gateVersion,
            "formId":        self.formId,
            "formName":      self.formName,
            "writerEnabled": self.writerEnabled,   # 항상 False
            "summary":       self.summary.to_dict(),
            "approvedFields": [f.to_dict() for f in self.approvedFields],
            "pendingFields":  [f.to_dict() for f in self.pendingFields],
        }


# ── 패널 필드 조회 헬퍼 ───────────────────────────────────────────────────────

def _collect_panel_fields(panel_dict: dict) -> dict[str, dict]:
    """
    ReviewPanel.to_dict() → fieldKey → {label, value, confidence, zone} 매핑.
    autoFillReady / needsReview 에서 value/confidence 추출.
    missingRequired / missingOptional 은 value="" confidence=0.0.
    """
    index: dict[str, dict] = {}

    for item in panel_dict.get("autoFillReady", []):
        fk = item["fieldKey"]
        index[fk] = {
            "label":      item.get("label", fk),
            "value":      item.get("value", ""),
            "confidence": item.get("confidence", 0.0),
            "zone":       "autoFillReady",
        }

    for item in panel_dict.get("needsReview", []):
        fk = item["fieldKey"]
        cands = item.get("candidates", [])
        val   = cands[0].get("value", "") if cands else ""
        conf  = cands[0].get("confidence", 0.0) if cands else 0.0
        index[fk] = {
            "label":      item.get("label", fk),
            "value":      val,
            "confidence": conf,
            "zone":       "needsReview",
        }

    for item in panel_dict.get("missingRequired", []):
        fk = item["fieldKey"]
        index.setdefault(fk, {
            "label":      item.get("label", fk),
            "value":      "",
            "confidence": 0.0,
            "zone":       "missingRequired",
        })

    for item in panel_dict.get("missingOptional", []):
        fk = item["fieldKey"]
        index.setdefault(fk, {
            "label":      item.get("label", fk),
            "value":      "",
            "confidence": 0.0,
            "zone":       "missingOptional",
        })

    return index


# ── 메인 처리 함수 ────────────────────────────────────────────────────────────

def apply_decisions(
    panel_dict: dict,
    decisions: list[FieldDecision],
) -> ApprovalResult:
    """
    ReviewPanel dict + FieldDecision 목록 → ApprovalResult.

    Args:
        panel_dict: ReviewPanel.to_dict() 결과
        decisions:  사용자가 제출한 FieldDecision 목록

    Returns:
        ApprovalResult (writerEnabled 항상 False)
    """
    result = ApprovalResult(
        formId   = panel_dict.get("formId", ""),
        formName = panel_dict.get("formName", ""),
    )

    panel_fields = _collect_panel_fields(panel_dict)
    decided_keys: set[str] = set()

    for dec in decisions:
        fk = dec.fieldKey
        decided_keys.add(fk)
        info = panel_fields.get(fk, {
            "label": fk, "value": "", "confidence": 0.0, "zone": "unknown",
        })

        if dec.action in (ACTION_CONFIRM, ACTION_EDIT):
            final_value = dec.editedValue if dec.action == ACTION_EDIT else info["value"]
            conf = 1.0 if dec.action == ACTION_EDIT else info["confidence"]
            result.approvedFields.append(ApprovedField(
                fieldKey      = fk,
                label         = info["label"],
                value         = final_value,
                originalValue = info["value"],
                action        = dec.action,
                sourceZone    = info["zone"],
                confidence    = conf,
                comment       = dec.comment,
            ))

        elif dec.action in (ACTION_HOLD, ACTION_ATTACHMENT):
            result.pendingFields.append(PendingField(
                fieldKey  = fk,
                label     = info["label"],
                action    = dec.action,
                sourceZone= info["zone"],
                reason    = dec.comment,
            ))

    # undecidedCount 반영 (summary는 property이므로 post-processing 불가 → to_dict 재정의 없이 wrapping)
    undecided = len(set(panel_fields.keys()) - decided_keys)
    # writerEnabled는 절대 True로 변경하지 않음
    assert result.writerEnabled is False, "INVARIANT VIOLATION: writerEnabled must be False"

    # undecidedCount를 담기 위해 summary를 override하는 대신 to_dict 후처리로 노출
    result._undecided_count = undecided  # type: ignore[attr-defined]

    return result


# ── to_dict undecided 포함 버전 ───────────────────────────────────────────────

def result_to_dict(result: ApprovalResult) -> dict[str, Any]:
    """
    ApprovalResult.to_dict()에 undecidedCount를 추가한 버전.
    """
    d = result.to_dict()
    d["summary"]["undecidedCount"] = getattr(result, "_undecided_count", 0)
    return d


# ── 편의 함수 ─────────────────────────────────────────────────────────────────

def apply_decisions_from_panel(
    panel,   # ReviewPanel 인스턴스
    decisions: list[FieldDecision],
) -> ApprovalResult:
    """ReviewPanel 인스턴스를 직접 받는 편의 함수."""
    return apply_decisions(panel.to_dict(), decisions)
