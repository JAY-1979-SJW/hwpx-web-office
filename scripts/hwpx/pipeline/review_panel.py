"""
HWPX-FORM-MISSING-AND-REVIEW-PANEL-01

review_panel.py — 매핑 결과를 사용자 검토 패널 데이터로 변환.

입력:  MappingResult  (form_field_mapper.py)
출력:  ReviewPanel    — 4구역 분류 + 필요 첨부서류 + 진행 가능 여부

구역:
    AUTO_FILL_READY    자동입력 가능
    NEEDS_REVIEW       사용자 확인 필요
    MISSING_REQUIRED   누락 필수값
    REQUIRED_ATTACHMENT 필요 첨부서류

read-only: 파일 쓰기 함수 미참조.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

PANEL_VERSION = "v1"

_PII_MASK = re.compile(r"\d{6}-\d{7}|\d{3}-\d{2}-\d{5}")


# ── 필요 첨부서류 추론 ────────────────────────────────────────────────────────
# evidenceHint 텍스트에서 문서 유형을 추출한다.
_ATTACHMENT_KEYWORDS: list[str] = [
    "사업자등록증",
    "공사계약서",
    "착공신고서",
    "완공신고서",
    "감리계약서",
    "건축허가서",
    "설계도면",
    "시험성적서",
    "토지대장",
    "건축물대장",
    "면허증",
    "자격증",
    "내역서",
    "준공도서",
    "완공도서",
    "감리보고서",
]


def _extract_attachment_types(hint: str) -> list[str]:
    """evidenceHint 문자열에서 필요 첨부서류 종류 추출."""
    found = []
    for kw in _ATTACHMENT_KEYWORDS:
        if kw in hint:
            found.append(kw)
    return found


def _mask(value: str) -> str:
    return _PII_MASK.sub("[MASKED]", value)


# ── 데이터 클래스 ─────────────────────────────────────────────────────────────


@dataclass
class AutoFillItem:
    fieldKey: str
    label: str
    value: str  # PII 마스킹됨
    confidence: float
    sourceLabel: str
    matchReason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "fieldKey": self.fieldKey,
            "label": self.label,
            "value": _mask(self.value),
            "confidence": round(self.confidence, 3),
            "sourceLabel": self.sourceLabel,
            "matchReason": self.matchReason,
        }


@dataclass
class ReviewItem:
    fieldKey: str
    label: str
    candidates: list[dict]  # [{value, confidence, sourceLabel}]
    reason: str  # low_confidence / multiple_candidates / type_mismatch
    evidenceHint: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "fieldKey": self.fieldKey,
            "label": self.label,
            "candidates": [{**c, "value": _mask(c.get("value", ""))} for c in self.candidates],
            "reason": self.reason,
            "evidenceHint": self.evidenceHint,
        }


@dataclass
class MissingItem:
    fieldKey: str
    label: str
    required: bool
    evidenceHint: str
    suggestedAttachments: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "fieldKey": self.fieldKey,
            "label": self.label,
            "required": self.required,
            "evidenceHint": self.evidenceHint,
            "suggestedAttachments": self.suggestedAttachments,
        }


@dataclass
class AttachmentItem:
    documentType: str
    neededFor: list[str]  # fieldKey 목록
    priority: str  # required / optional

    def to_dict(self) -> dict[str, Any]:
        return {
            "documentType": self.documentType,
            "neededFor": self.neededFor,
            "priority": self.priority,
        }


@dataclass
class PanelSummary:
    autoFillCount: int
    reviewCount: int
    missingRequiredCount: int
    missingOptionalCount: int
    attachmentCount: int
    readyToProceed: bool  # missingRequired == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "autoFillCount": self.autoFillCount,
            "reviewCount": self.reviewCount,
            "missingRequiredCount": self.missingRequiredCount,
            "missingOptionalCount": self.missingOptionalCount,
            "attachmentCount": self.attachmentCount,
            "readyToProceed": self.readyToProceed,
        }


@dataclass
class ReviewPanel:
    panelVersion: str = PANEL_VERSION
    formId: str = ""
    formName: str = ""
    autoFillReady: list[AutoFillItem] = field(default_factory=list)
    needsReview: list[ReviewItem] = field(default_factory=list)
    missingRequired: list[MissingItem] = field(default_factory=list)
    missingOptional: list[MissingItem] = field(default_factory=list)
    requiredAttachments: list[AttachmentItem] = field(default_factory=list)

    @property
    def summary(self) -> PanelSummary:
        return PanelSummary(
            autoFillCount=len(self.autoFillReady),
            reviewCount=len(self.needsReview),
            missingRequiredCount=len(self.missingRequired),
            missingOptionalCount=len(self.missingOptional),
            attachmentCount=len(self.requiredAttachments),
            readyToProceed=len(self.missingRequired) == 0,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "panelVersion": self.panelVersion,
            "formId": self.formId,
            "formName": self.formName,
            "summary": self.summary.to_dict(),
            "autoFillReady": [i.to_dict() for i in self.autoFillReady],
            "needsReview": [i.to_dict() for i in self.needsReview],
            "missingRequired": [i.to_dict() for i in self.missingRequired],
            "missingOptional": [i.to_dict() for i in self.missingOptional],
            "requiredAttachments": [i.to_dict() for i in self.requiredAttachments],
        }


# ── 빌드 함수 ─────────────────────────────────────────────────────────────────


def _build_attachment_map(mapping_result, panel: ReviewPanel) -> dict[str, list[str]]:
    """MISSING 항목 + review 항목의 evidenceHint에서 첨부서류 맵(docType → [fieldKey])을 만든다."""
    attachment_map: dict[str, list[str]] = {}
    for miss in mapping_result.missingFields:
        attachments = _extract_attachment_types(miss.evidenceHint)
        item = MissingItem(
            fieldKey=miss.fieldKey,
            label=miss.label,
            required=miss.required,
            evidenceHint=miss.evidenceHint,
            suggestedAttachments=attachments,
        )
        if miss.required:
            panel.missingRequired.append(item)
        else:
            panel.missingOptional.append(item)
        for doc in attachments:
            attachment_map.setdefault(doc, [])
            if miss.fieldKey not in attachment_map[doc]:
                attachment_map[doc].append(miss.fieldKey)

    # review 항목의 evidenceHint도 첨부서류로 수집
    for rf in mapping_result.reviewFields:
        for doc in _extract_attachment_types(rf.evidenceHint):
            attachment_map.setdefault(doc, [])
            if rf.fieldKey not in attachment_map[doc]:
                attachment_map[doc].append(rf.fieldKey)

    return attachment_map


def build_review_panel(mapping_result) -> ReviewPanel:
    """
    MappingResult → ReviewPanel 변환.

    Args:
        mapping_result: form_field_mapper.MappingResult
    """
    panel = ReviewPanel(
        formId=mapping_result.formId,
        formName=mapping_result.formName,
    )

    # 1. AUTO_FILL_READY
    for mf in mapping_result.mappedFields:
        panel.autoFillReady.append(
            AutoFillItem(
                fieldKey=mf.fieldKey,
                label=mf.label,
                value=mf.value,
                confidence=mf.confidence,
                sourceLabel=mf.sourceLabel,
                matchReason=mf.matchReason,
            )
        )

    # 2. NEEDS_REVIEW
    for rf in mapping_result.reviewFields:
        reason = _review_reason(rf)
        panel.needsReview.append(
            ReviewItem(
                fieldKey=rf.fieldKey,
                label=rf.label,
                candidates=[
                    {
                        "value": rf.value,
                        "confidence": round(rf.confidence, 3),
                        "sourceLabel": rf.sourceLabel,
                    }
                ],
                reason=reason,
                evidenceHint=rf.evidenceHint,
            )
        )

    # 3. MISSING (+ review 항목의 evidenceHint 첨부서류 수집)
    attachment_map = _build_attachment_map(mapping_result, panel)

    # 4. 필요 첨부서류 (required 먼저)
    req_docs = {doc for miss in panel.missingRequired for doc in miss.suggestedAttachments}
    for doc, needed_for in sorted(attachment_map.items()):
        panel.requiredAttachments.append(
            AttachmentItem(
                documentType=doc,
                neededFor=needed_for,
                priority="required" if doc in req_docs else "optional",
            )
        )

    # required 첨부서류 먼저 정렬
    panel.requiredAttachments.sort(key=lambda a: (a.priority != "required", a.documentType))

    return panel


def _review_reason(mapped_field) -> str:
    """NEEDS_REVIEW 이유 결정."""
    if mapped_field.candidateCount > 1:
        return "multiple_candidates"
    if not mapped_field.validation.passed:
        return "type_mismatch"
    return "low_confidence"


# ── 편의 함수 ─────────────────────────────────────────────────────────────────


def build_panel_from_paths(hwpx_path, catalog_jsonl) -> ReviewPanel:
    """HWPX 경로 + 카탈로그로 바로 ReviewPanel 반환."""
    from hwpx.pipeline.form_field_mapper import map_from_paths

    mapping = map_from_paths(hwpx_path, catalog_jsonl)
    return build_review_panel(mapping)
