"""
HWPX-FORM-FIELD-MAPPING-01

form_field_mapper.py — 파서 추출값 ↔ 서식 필드 카탈로그 매핑 엔진.

입력:
    ParseResult          (upload_document_parser.py 결과)
    FormCatalogEntry     (form_field_catalog.py 카탈로그)

출력:
    MappingResult        AUTO_FILL_READY / NEEDS_REVIEW / MISSING_REQUIRED 분류

규칙:
    AUTO_FILL_READY   : confidence >= 0.80, 단일 후보, 형식검증 통과
    NEEDS_REVIEW      : 0.60 <= confidence < 0.80, 복수 후보, 형식검증 약함
    MISSING_REQUIRED  : 필수 필드에 후보 없음 또는 confidence < 0.60

제약:
    - 파일 쓰기 함수 미참조
    - AI API / OCR 미참조
    - PII 원문 report 저장 안 함
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# ── 상태 상수 ─────────────────────────────────────────────────────────────────
STATUS_AUTO = "AUTO_FILL_READY"
STATUS_REVIEW = "NEEDS_REVIEW"
STATUS_MISS = "MISSING_REQUIRED"

MAPPING_VERSION = "v1"

# ── 신뢰도 임계값 ─────────────────────────────────────────────────────────────
CONF_AUTO = 0.80  # 이상: AUTO_FILL_READY
CONF_REVIEW = 0.60  # 이상: NEEDS_REVIEW

# ── 형식 검증 패턴 ────────────────────────────────────────────────────────────
_DATE_RE = re.compile(r"\d{4}[-./년]\s*\d{1,2}[-./월]|\d{4}\.\d{2}\.\d{2}")
_AMOUNT_RE = re.compile(r"\d[\d,]+\s*원|\d+\s*[백천만억]")
_REG_NO_RE = re.compile(r"\d{3}-\d{2}-\d{5}|\d{4}-\d{4}|\d{6}-\d{7}")
_PHONE_RE = re.compile(r"\d{2,3}-\d{3,4}-\d{4}")
# PII 마스킹 (report 저장 시)
_PII_MASK_RE = re.compile(r"\d{6}-\d{7}|\d{3}-\d{2}-\d{5}")

# ── 날짜 관련 fieldKey ────────────────────────────────────────────────────────
_DATE_FIELDS = frozenset({
    "startDate",
    "endDate",
    "completionDate",
    "inspectionDate",
    "reportDate",
    "contractDate",
    "durationDays",
})
_AMOUNT_FIELDS = frozenset({"amount", "unitPrice", "totalAmount"})
_REG_FIELDS = frozenset({"registrationNumber", "licenseNumber", "receiptNumber"})

# 공문서 메타 필드 (본문 필드로 자동 매칭 금지)
_META_KEYS = frozenset({"stamp", "approval", "receipt", "notification", "docNumber"})

# sourceEvidenceHint 키워드와 소스 유형 유사도 테이블
_EVIDENCE_MATCH: dict[str, list[str]] = {
    "사업자등록증": ["사업자", "등록증", "법인"],
    "공사계약서": ["계약서", "도급"],
    "착공신고서": ["착공", "착공신고"],
    "완공신고서": ["완공", "준공"],
    "감리계약서": ["감리", "감리계약"],
    "건축허가서": ["허가", "건축허가"],
    "설계도면": ["설계", "도면"],
    "시험성적서": ["시험", "성적서"],
}


# ── 데이터 클래스 ─────────────────────────────────────────────────────────────


@dataclass
class ValidationResult:
    passed: bool
    fieldType: str
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"passed": self.passed, "fieldType": self.fieldType, "reason": self.reason}


@dataclass
class MappedField:
    fieldKey: str
    label: str  # 카탈로그 primaryLabel
    value: str  # 추출된 값 (PII 마스킹 처리)
    status: str  # AUTO_FILL_READY / NEEDS_REVIEW / MISSING_REQUIRED
    confidence: float
    matchReason: str  # direct_key / alias_match / label_match
    sourceLabel: str  # 파서의 sourceLabel
    evidenceHint: str  # 카탈로그 sourceEvidenceHint
    validation: ValidationResult
    candidateCount: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "fieldKey": self.fieldKey,
            "label": self.label,
            "value": _mask_pii(self.value),
            "status": self.status,
            "confidence": round(self.confidence, 3),
            "matchReason": self.matchReason,
            "sourceLabel": self.sourceLabel,
            "evidenceHint": self.evidenceHint,
            "validation": self.validation.to_dict(),
            "candidateCount": self.candidateCount,
        }


@dataclass
class MissingField:
    fieldKey: str
    label: str
    required: bool
    evidenceHint: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "fieldKey": self.fieldKey,
            "label": self.label,
            "required": self.required,
            "evidenceHint": self.evidenceHint,
        }


@dataclass
class MappingResult:
    formId: str
    formName: str
    mappingVersion: str = MAPPING_VERSION
    mappedFields: list[MappedField] = field(default_factory=list)
    reviewFields: list[MappedField] = field(default_factory=list)
    missingFields: list[MissingField] = field(default_factory=list)

    @property
    def summary(self) -> dict[str, int]:
        req_total = sum(1 for f in self.missingFields if f.required)
        req_total += sum(
            1 for f in self.mappedFields if True
        )  # all mapped fields had required status
        return {
            "requiredTotal": len(self.missingFields)
            + len(self.mappedFields)
            + len(self.reviewFields),
            "autoFillReady": len(self.mappedFields),
            "needsReview": len(self.reviewFields),
            "missingRequired": sum(1 for f in self.missingFields if f.required),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "formId": self.formId,
            "formName": self.formName,
            "mappingVersion": self.mappingVersion,
            "summary": self.summary,
            "mappedFields": [f.to_dict() for f in self.mappedFields],
            "reviewFields": [f.to_dict() for f in self.reviewFields],
            "missingFields": [f.to_dict() for f in self.missingFields],
        }


# ── 헬퍼 ─────────────────────────────────────────────────────────────────────


def _mask_pii(value: str) -> str:
    return _PII_MASK_RE.sub("[MASKED]", value)


def _validate_field(fieldKey: str, value: str) -> ValidationResult:
    """fieldKey 유형에 맞는 형식 검증."""
    if fieldKey in _DATE_FIELDS:
        passed = bool(_DATE_RE.search(value))
        return ValidationResult(passed, "date", "" if passed else "date_pattern_not_found")
    if fieldKey in _AMOUNT_FIELDS:
        passed = bool(_AMOUNT_RE.search(value))
        return ValidationResult(passed, "amount", "" if passed else "amount_pattern_not_found")
    if fieldKey in _REG_FIELDS:
        passed = bool(_REG_NO_RE.search(value) or len(value) >= 4)
        return ValidationResult(passed, "registrationNumber", "" if passed else "reg_pattern_weak")
    return ValidationResult(True, "text")


def _evidence_bonus(hint: str, source_label: str) -> float:
    """sourceEvidenceHint 키워드가 source_label에 포함될 때 보너스."""
    if not hint or not source_label:
        return 0.0
    src_lower = source_label.lower()
    for keyword, variants in _EVIDENCE_MATCH.items():
        if keyword in hint:
            for v in variants:
                if v in src_lower:
                    return 0.05
    return 0.0


def _norm_label(s: str) -> str:
    return s.strip().lower().replace(" ", "").replace("_", "")


# ── 매핑 엔진 ─────────────────────────────────────────────────────────────────


def _resolve_field_candidates(cf: dict, extracted_by_key: dict[str, list], parse_result):
    sem = cf.get("semanticField", "")
    label = cf.get("primaryLabel", "")
    aliases = [_norm_label(item) for item in cf.get("labels", [])]
    if not sem:
        # semanticField 미매핑 필드: 라벨 직접 매칭 시도
        candidates = _find_by_label(label, aliases, parse_result)
    else:
        # 1. fieldKey 직접 매칭
        direct = extracted_by_key.get(sem, [])
        # 2. alias 라벨 매칭 (파서 sourceLabel이 카탈로그 label과 일치)
        alias_matches = _find_by_alias(aliases, parse_result, sem)
        candidates = _merge_candidates(direct, alias_matches)
    return sem, label, aliases, candidates


def _classify_matched_field(best, sem: str, aliases: list[str], hint: str, n_candidates: int):
    """매칭 이유·confidence·형식검증 결과를 계산한다."""
    if sem and best.fieldKey == sem:
        match_reason = "direct_key"
    elif _norm_label(best.sourceLabel) in aliases:
        match_reason = "alias_match"
    else:
        match_reason = "label_match"

    conf = best.confidence
    conf += _evidence_bonus(hint, best.sourceLabel)
    if n_candidates > 1:
        conf -= 0.10  # 복수 후보 감점

    vr = _validate_field(sem or "", best.value)
    if not vr.passed and sem in (_DATE_FIELDS | _AMOUNT_FIELDS):
        conf -= 0.10

    conf = max(0.0, min(1.0, conf))
    return match_reason, conf, vr


def map_fields(
    parse_result,  # ParseResult from upload_document_parser
    catalog_entry: dict,  # FormCatalogEntry.to_dict() 결과
) -> MappingResult:
    """
    파서 결과와 카탈로그를 매핑하여 분류 결과 반환.

    Args:
        parse_result: upload_document_parser.ParseResult
        catalog_entry: form_field_catalog.FormCatalogEntry.to_dict() dict
    """
    form_id = catalog_entry.get("formId", "unknown")
    form_name = catalog_entry.get("formName", "")
    result = MappingResult(formId=form_id, formName=form_name)

    # 공문서 메타 필드 자동 매칭 방지: CLS_META 필드 제외
    from hwpx.recognition_corpus.label_taxonomy import CLS_META, classify_label

    def _is_meta(label: str) -> bool:
        return classify_label(label).classification == CLS_META

    # 파서 추출값: fieldKey → list of ExtractedField
    extracted_by_key: dict[str, list] = {}
    for ef in parse_result.extractedFields if hasattr(parse_result, "extractedFields") else []:
        if ef.fieldKey in _META_KEYS:
            continue
        extracted_by_key.setdefault(ef.fieldKey, []).append(ef)

    # 카탈로그 필드 순회
    catalog_fields = catalog_entry.get("fields", [])
    for cf in catalog_fields:
        req = cf.get("required", False)
        hint = cf.get("sourceEvidenceHint", "")
        sem, label, aliases, candidates = _resolve_field_candidates(
            cf, extracted_by_key, parse_result
        )

        if not candidates:
            result.missingFields.append(
                MissingField(
                    fieldKey=sem or label,
                    label=label,
                    required=req,
                    evidenceHint=hint,
                )
            )
            continue

        # 최고 신뢰도 후보 선택
        best = max(candidates, key=lambda e: e.confidence)
        n_candidates = len(set(_mask_pii(e.value) for e in candidates))

        # 공문서 메타 라벨은 본문 필드로 자동 매칭 금지
        if _is_meta(best.sourceLabel):
            result.missingFields.append(
                MissingField(
                    fieldKey=sem or label,
                    label=label,
                    required=req,
                    evidenceHint=hint,
                )
            )
            continue

        match_reason, conf, vr = _classify_matched_field(best, sem, aliases, hint, n_candidates)

        mf = MappedField(
            fieldKey=sem or label,
            label=label,
            value=best.value,
            status="",
            confidence=conf,
            matchReason=match_reason,
            sourceLabel=best.sourceLabel,
            evidenceHint=hint,
            validation=vr,
            candidateCount=n_candidates,
        )

        # 분류
        if conf >= CONF_AUTO and n_candidates == 1 and vr.passed:
            mf.status = STATUS_AUTO
            result.mappedFields.append(mf)
        elif conf >= CONF_REVIEW:
            mf.status = STATUS_REVIEW
            result.reviewFields.append(mf)
        else:
            mf.status = STATUS_MISS
            result.missingFields.append(
                MissingField(
                    fieldKey=sem or label,
                    label=label,
                    required=req,
                    evidenceHint=hint,
                )
            )

    return result


def _find_by_alias(
    aliases: list[str],
    parse_result,
    target_sem: str,
) -> list:
    """파서 결과에서 sourceLabel이 aliases와 일치하는 ExtractedField 반환."""
    matched = []
    for ef in parse_result.extractedFields if hasattr(parse_result, "extractedFields") else []:
        norm = _norm_label(ef.sourceLabel)
        if norm in aliases and ef.fieldKey != target_sem:
            matched.append(ef)
    return matched


def _find_by_label(label: str, aliases: list[str], parse_result) -> list:
    """semanticField 없는 필드에 대해 sourceLabel 기반 매칭."""
    norm_label = _norm_label(label)
    matched = []
    for ef in parse_result.extractedFields if hasattr(parse_result, "extractedFields") else []:
        if _norm_label(ef.sourceLabel) == norm_label or _norm_label(ef.sourceLabel) in aliases:
            matched.append(ef)
    return matched


def _merge_candidates(direct: list, alias: list) -> list:
    """직접 매칭 + 별칭 매칭 합산, 중복 value 제거."""
    seen_vals: set[str] = set()
    merged = []
    for ef in direct + alias:
        v = _mask_pii(ef.value)
        if v not in seen_vals:
            seen_vals.add(v)
            merged.append(ef)
    return merged


# ── 배치 매핑 ─────────────────────────────────────────────────────────────────


def map_from_paths(
    hwpx_path,  # Path: 업로드된 HWPX
    catalog_jsonl,  # Path: form_field_catalog.jsonl
    form_name: str = "",
) -> MappingResult:
    """
    편의 함수: HWPX 경로와 카탈로그 경로를 받아 매핑 결과 반환.

    form_name이 비어 있으면 파일명에서 추론.
    """
    from pathlib import Path

    from hwpx.pipeline.upload_document_parser import parse_hwpx
    from hwpx.recognition_corpus.form_field_catalog import load_catalog_entry
    from hwpx.recognition_corpus.form_type_classifier import classify_form_type

    p = Path(hwpx_path)
    parse_result = parse_hwpx(p)

    ft = classify_form_type(p)
    target_name = form_name or ft.formName

    # 2026-09-29: 줄단위 스캔을 form_field_catalog.load_catalog_entry() 로
    # 옮겼다(재사용 가능하게 — editor_api_route.call_catalog_fill 도 같은
    # 함수를 쓴다). 동작은 동일(같은 완전일치 스캔).
    catalog_entry = load_catalog_entry(target_name, Path(catalog_jsonl))

    if catalog_entry is None:
        # 카탈로그 미매칭: 빈 결과
        return MappingResult(
            formId="unknown",
            formName=target_name,
        )

    return map_fields(parse_result, catalog_entry)
