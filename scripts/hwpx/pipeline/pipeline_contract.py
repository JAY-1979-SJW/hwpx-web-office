"""HWPX AI Recognition Safe Edit Pipeline — 계약 dataclass."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any


PIPELINE_SCHEMA_VERSION = "v1"


def make_request_id() -> str:
    return uuid.uuid4().hex[:16]


@dataclass
class RecognitionResult:
    detectedLabels: list[str] = field(default_factory=list)
    slotMap: dict[str, Any] = field(default_factory=dict)
    documentType: str = "unknown"
    confidence: float = 0.0
    reviewRequired: bool = False

    def to_dict(self) -> dict:
        return {
            "detectedLabels": self.detectedLabels,
            "slotMap": {k: (v.slotId if hasattr(v, "slotId") else str(v))
                        for k, v in self.slotMap.items()},
            "documentType": self.documentType,
            "confidence": self.confidence,
            "reviewRequired": self.reviewRequired,
        }


@dataclass
class PlanResult:
    editPlan: dict[str, Any] = field(default_factory=dict)
    plannedFields: list[str] = field(default_factory=list)
    skippedFields: list[str] = field(default_factory=list)
    reviewRequiredReasons: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "editPlan": self.editPlan,
            "plannedFields": self.plannedFields,
            "skippedFields": self.skippedFields,
            "reviewRequiredReasons": self.reviewRequiredReasons,
        }


@dataclass
class VerificationResult:
    expectedFields: dict[str, str] = field(default_factory=dict)
    actualFields: dict[str, str] = field(default_factory=dict)
    matched: list[str] = field(default_factory=list)
    mismatched: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    decision: str = "PASS"

    def to_dict(self) -> dict:
        return {
            "expectedFields": self.expectedFields,
            "actualFields": self.actualFields,
            "matched": self.matched,
            "mismatched": self.mismatched,
            "warnings": self.warnings,
            "decision": self.decision,
        }


@dataclass
class HancomVerifyResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    info: dict[str, Any] = field(default_factory=dict)
    verdict: str = "PASS"

    def to_dict(self) -> dict:
        return {
            "errors": self.errors,
            "warnings": self.warnings,
            "info": self.info,
            "verdict": self.verdict,
        }


@dataclass
class PipelineResult:
    schemaVersion: str = PIPELINE_SCHEMA_VERSION
    requestId: str = field(default_factory=make_request_id)
    inputFile: str = ""
    outputFile: str = ""
    stages: dict[str, str] = field(default_factory=dict)
    finalDecision: str = "FAIL"
    recognition: RecognitionResult = field(default_factory=RecognitionResult)
    plan: PlanResult = field(default_factory=PlanResult)
    verification: VerificationResult = field(default_factory=VerificationResult)
    hancomVerify: HancomVerifyResult = field(default_factory=HancomVerifyResult)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    # 범용 서식 인지 확장 필드
    formType: str = "unknown_form"
    tableRoles: dict[str, str] = field(default_factory=dict)
    inputSlots: list[Any] = field(default_factory=list)
    generatedPlans: list[str] = field(default_factory=list)
    skippedFields: list[str] = field(default_factory=list)
    reviewRequiredFields: list[str] = field(default_factory=list)
    unsafeTargets: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "schemaVersion": self.schemaVersion,
            "requestId": self.requestId,
            "inputFile": self.inputFile,
            "outputFile": self.outputFile,
            "stages": self.stages,
            "finalDecision": self.finalDecision,
            "formType": self.formType,
            "tableRoles": self.tableRoles,
            "inputSlots": [s.to_dict() if hasattr(s, "to_dict") else s for s in self.inputSlots],
            "generatedPlans": self.generatedPlans,
            "skippedFields": self.skippedFields,
            "reviewRequiredFields": self.reviewRequiredFields,
            "unsafeTargets": self.unsafeTargets,
            "recognition": self.recognition.to_dict(),
            "plan": self.plan.to_dict(),
            "verification": self.verification.to_dict(),
            "hancomVerify": self.hancomVerify.to_dict(),
            "warnings": self.warnings,
            "errors": self.errors,
        }
