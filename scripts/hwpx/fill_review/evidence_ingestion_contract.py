"""HWPX-FILL-REVIEW-EVIDENCE-INGESTION-CONTRACT-01

사용자 업로드 자료(계약내역서, 사업자등록증, 도장 이미지, OCR 결과, 수기 입력 등)를
FillReviewContract.match_requirements_with_evidence에 바로 넘길 수 있는
EvidenceSource[] 로 변환하는 deterministic 계약.

원칙:
- writer를 호출하지 않는다 / output HWPX를 만들지 않는다.
- 원본 업로드 파일을 수정하지 않는다.
- AI API / OCR / DB / 네트워크를 호출하지 않는다.
- openpyxl 등으로 직접 실파싱하지 않는다.
- 모든 EvidenceSource는 sourceHash를 가진다.
- confidence가 높아도 자동 승인하지 않는다 (UI/검수 게이트 통과 필수).
- 충돌 값은 warnings에 남기고 자동 선택하지 않는다.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field

SCHEMA_VERSION = "evidence_ingestion_v1"
ENGINE_VERSION = "0.1.0"

# 입력 hint에 허용되는 sourceType (출력에도 동일 집합 사용)
ALLOWED_SOURCE_TYPES: frozenset[str] = frozenset({
    "CONTRACT_XLSX",
    "ESTIMATE_XLSX",
    "BUSINESS_LICENSE",
    "SEAL_IMAGE",
    "OCR_RESULT",
    "MANUAL_ENTRY",
    "USER_INPUT",
    "UPLOADED_DOCUMENT",
    "UNKNOWN",
})

# 표준 extracted field 이름
STANDARD_FIELD_NAMES: frozenset[str] = frozenset({
    "projectName",
    "contractAmount",
    "startDate",
    "endDate",
    "companyName",
    "businessRegistrationNumber",
    "representativeName",
    "siteManagerName",
    "address",
    "phone",
    "sealImageRef",
    "attachmentDocumentRef",
    "freeText",
})

# 한국어 → 표준 field 매핑
_FIELD_ALIASES: dict[str, str] = {
    "공사명": "projectName",
    "프로젝트명": "projectName",
    "사업명": "projectName",
    "계약금액": "contractAmount",
    "도급금액": "contractAmount",
    "총공사금액": "contractAmount",
    "착공일": "startDate",
    "시작일": "startDate",
    "준공일": "endDate",
    "완공일": "endDate",
    "종료일": "endDate",
    "회사명": "companyName",
    "상호": "companyName",
    "업체명": "companyName",
    "사업자등록번호": "businessRegistrationNumber",
    "대표자": "representativeName",
    "대표자명": "representativeName",
    "현장소장": "siteManagerName",
    "현장소장명": "siteManagerName",
    "주소": "address",
    "소재지": "address",
    "전화번호": "phone",
    "연락처": "phone",
    "휴대전화": "phone",
}

_AMOUNT_FIELDS: frozenset[str] = frozenset({"contractAmount"})
_DATE_FIELDS: frozenset[str] = frozenset({"startDate", "endDate"})

# 파일명 키워드 → sourceType (우선순위 순)
_FILENAME_KEYWORDS: list[tuple[tuple[str, ...], str]] = [
    (("사업자등록", "business_license", "business-license"), "BUSINESS_LICENSE"),
    (("도장", "직인", "인감", "seal"), "SEAL_IMAGE"),
    (("기성", "estimate", "내역"), "ESTIMATE_XLSX"),
    (("계약", "contract"), "CONTRACT_XLSX"),
    (("ocr",), "OCR_RESULT"),
]

# 확장자 → 후보 sourceType
_EXT_HINT: dict[str, str] = {
    "xlsx": "CONTRACT_XLSX",
    "xls": "CONTRACT_XLSX",
    "pdf": "UPLOADED_DOCUMENT",
    "hwp": "UPLOADED_DOCUMENT",
    "hwpx": "UPLOADED_DOCUMENT",
    "docx": "UPLOADED_DOCUMENT",
    "png": "SEAL_IMAGE",
    "jpg": "SEAL_IMAGE",
    "jpeg": "SEAL_IMAGE",
    "json": "OCR_RESULT",
    "txt": "OCR_RESULT",
}


# ── dataclasses ──────────────────────────────────────────────────────────────


@dataclass
class RejectedInput:
    inputId: str
    sourceName: str
    reason: str
    warningCode: str

    def to_dict(self) -> dict:
        return {
            "inputId": self.inputId,
            "sourceName": self.sourceName,
            "reason": self.reason,
            "warningCode": self.warningCode,
        }


@dataclass
class IngestionWarning:
    code: str
    detail: str
    inputId: str | None = None
    fieldName: str | None = None

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "detail": self.detail,
            "inputId": self.inputId,
            "fieldName": self.fieldName,
        }


@dataclass
class EvidenceIngestionResult:
    schemaVersion: str = SCHEMA_VERSION
    engineVersion: str = ENGINE_VERSION
    requestId: str = ""
    evidenceSources: list[dict] = field(default_factory=list)
    rejectedInputs: list[RejectedInput] = field(default_factory=list)
    warnings: list[IngestionWarning] = field(default_factory=list)
    sourceCount: int = 0
    evidenceCount: int = 0
    rejectedCount: int = 0

    def to_dict(self) -> dict:
        return {
            "schemaVersion": self.schemaVersion,
            "engineVersion": self.engineVersion,
            "requestId": self.requestId,
            "evidenceSources": self.evidenceSources,
            "rejectedInputs": [r.to_dict() for r in self.rejectedInputs],
            "warnings": [w.to_dict() for w in self.warnings],
            "sourceCount": self.sourceCount,
            "evidenceCount": self.evidenceCount,
            "rejectedCount": self.rejectedCount,
        }


# ── helpers ──────────────────────────────────────────────────────────────────


def _detect_source_type(inp: dict) -> tuple[str, list[str]]:
    """(sourceType, warning_codes) 반환. 입력 hint > 파일명 > 확장자."""
    warnings: list[str] = []
    hint = (inp.get("sourceTypeHint") or "").strip().upper()
    if hint in ALLOWED_SOURCE_TYPES and hint != "UNKNOWN":
        return hint, warnings

    name = (inp.get("sourceName") or "").lower()
    for keywords, st in _FILENAME_KEYWORDS:
        if any(k in name for k in keywords):
            return st, warnings

    ext = (inp.get("fileExtension") or "").lower().lstrip(".")
    if not ext and "." in name:
        ext = name.rsplit(".", 1)[-1]
    if ext in _EXT_HINT:
        return _EXT_HINT[ext], warnings

    warnings.append("UNKNOWN_SOURCE_TYPE")
    return "UNKNOWN", warnings


_AMOUNT_DIGITS_RE = re.compile(r"[\d,]+")


def _normalize_amount(value: str) -> tuple[str, dict | None, str | None]:
    """금액 문자열 정규화. return (display, details, warning_code)."""
    if value is None:
        return "", None, None
    raw = str(value).strip()
    if not raw:
        return "", None, None
    # 숫자/콤마 조합 추출
    m = _AMOUNT_DIGITS_RE.search(raw)
    if m is None:
        return raw, {"raw": raw, "display": raw, "numberCandidate": None}, "INVALID_AMOUNT_FORMAT"
    digits = m.group(0).replace(",", "")
    if not digits.isdigit():
        return raw, {"raw": raw, "display": raw, "numberCandidate": None}, "INVALID_AMOUNT_FORMAT"
    number = int(digits)
    return raw, {"raw": raw, "display": raw, "numberCandidate": number}, None


_DATE_PATTERNS = [
    re.compile(r"^(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})$"),
    re.compile(r"^(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일$"),
]


def _normalize_date(value: str) -> tuple[str, dict | None, str | None]:
    """날짜 문자열 정규화 → ISO 8601 (yyyy-mm-dd)."""
    if value is None:
        return "", None, None
    raw = str(value).strip()
    if not raw:
        return "", None, None
    for pat in _DATE_PATTERNS:
        m = pat.match(raw)
        if m is None:
            continue
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not (1 <= mo <= 12 and 1 <= d <= 31):
            continue
        iso = f"{y:04d}-{mo:02d}-{d:02d}"
        return iso, {"raw": raw, "display": iso, "dateCandidate": iso}, None
    return raw, {"raw": raw, "display": raw, "dateCandidate": None}, "INVALID_DATE_FORMAT"


_BRN_RE = re.compile(r"^\d{3}-\d{2}-\d{5}$")


def _validate_business_registration_number(value: str) -> tuple[str, str | None]:
    raw = str(value or "").strip()
    if _BRN_RE.match(raw):
        return raw, None
    return raw, "INVALID_BUSINESS_REGISTRATION_NUMBER"


def _normalize_field_value(field_name: str, value) -> tuple[str, dict | None, str | None]:
    """field별 정규화 dispatch."""
    if field_name in _AMOUNT_FIELDS:
        return _normalize_amount(value)
    if field_name in _DATE_FIELDS:
        return _normalize_date(value)
    if field_name == "businessRegistrationNumber":
        norm, warn = _validate_business_registration_number(value)
        return norm, {"raw": str(value or ""), "display": norm}, warn
    if value is None:
        return "", None, None
    s = str(value).strip()
    return s, ({"raw": s, "display": s} if s else None), None


def _alias_to_standard(field_name: str) -> str:
    """한국어 키를 표준 영어 키로 정규화."""
    if field_name in STANDARD_FIELD_NAMES:
        return field_name
    return _FIELD_ALIASES.get(field_name, field_name)


def _extract_from_text(text: str) -> dict:
    """간단한 'key: value' 라인을 dict로 추출."""
    if not isinstance(text, str) or not text:
        return {}
    out: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        if not key or not val:
            continue
        std = _alias_to_standard(key)
        if std in STANDARD_FIELD_NAMES:
            out.setdefault(std, val)
    return out


def _extract_from_tables(tables) -> dict:
    """table = list[list[(label, value)]] 또는 [[label, value], ...] 형식 모두 수용."""
    if not isinstance(tables, list):
        return {}
    out: dict[str, str] = {}
    for tbl in tables:
        if not isinstance(tbl, list):
            continue
        for row in tbl:
            if not isinstance(row, (list, tuple)) or len(row) < 2:
                continue
            label = (row[0] or "").strip() if isinstance(row[0], str) else ""
            value = (row[1] or "").strip() if isinstance(row[1], str) else ""
            if not label or not value:
                continue
            std = _alias_to_standard(label)
            if std in STANDARD_FIELD_NAMES:
                out.setdefault(std, value)
    return out


def _merge_fields_with_conflict_check(
    target: dict[str, str],
    additions: dict[str, str],
    warnings: list[IngestionWarning],
    input_id: str,
) -> dict:
    """target에 additions를 merge. 같은 key에 다른 value면 FIELD_CONFLICT warning."""
    conflicts: dict[str, list[str]] = {}
    for k, v in additions.items():
        if k in target:
            if target[k] != v:
                conflicts.setdefault(k, [target[k]]).append(v)
            continue
        target[k] = v
    for k, vals in conflicts.items():
        warnings.append(
            IngestionWarning(
                code="FIELD_CONFLICT",
                detail=f"field={k!r} values={vals}",
                inputId=input_id,
                fieldName=k,
            )
        )
    return target


def _confidence_for_source(
    source_type: str, num_fields: int, has_text: bool, has_tables: bool
) -> float:
    """간단 휴리스틱 confidence (자동 승인의 근거가 아님 — 표시 전용)."""
    base = {
        "CONTRACT_XLSX": 0.7,
        "ESTIMATE_XLSX": 0.7,
        "BUSINESS_LICENSE": 0.8,
        "SEAL_IMAGE": 0.6,
        "OCR_RESULT": 0.55,
        "MANUAL_ENTRY": 0.85,
        "USER_INPUT": 0.85,
        "UPLOADED_DOCUMENT": 0.5,
        "UNKNOWN": 0.3,
    }.get(source_type, 0.4)
    if num_fields >= 3:
        base = min(0.95, base + 0.05)
    if not has_text and not has_tables and num_fields == 0:
        base = min(base, 0.3)
    return round(base, 3)


def _reject_reason(inp: dict) -> tuple[str, str] | None:
    """입력 거부 사유 (reason, warningCode) — 없으면 None(유효한 입력)."""
    if not (inp.get("sourceHash") or "").strip():
        return "sourceHash is required", "SOURCE_HASH_REQUIRED"
    is_empty = (
        not (inp.get("extractedFields") or {})
        and not (inp.get("extractedText") or "").strip()
        and not (inp.get("extractedTables") or [])
        and not (inp.get("metadata") or {})
    )
    if is_empty:
        return (
            "no extractedFields / extractedText / extractedTables / metadata",
            "EMPTY_INPUT",
        )
    return None


def _normalize_extracted_fields(
    raw_fields_in: dict, input_id: str
) -> tuple[dict[str, str], dict[str, dict], list[IngestionWarning]]:
    """1) 직접 주어진 extractedFields (한국어 키도 영어 표준 키로 정규화)."""
    normalized: dict[str, str] = {}
    normalized_details: dict[str, dict] = {}
    per_source_warnings: list[IngestionWarning] = []
    for raw_key, raw_value in raw_fields_in.items():
        std_key = _alias_to_standard(raw_key)
        if std_key not in STANDARD_FIELD_NAMES:
            # 비표준 키는 freeText로 모은다 (충돌 가능성 → conflict check)
            if raw_value:
                existing = normalized.get("freeText", "")
                new_text = f"{raw_key}: {raw_value}"
                merged = (existing + "\n" + new_text) if existing else new_text
                normalized["freeText"] = merged
            continue
        display, details, warn_code = _normalize_field_value(std_key, raw_value)
        if not display:
            continue
        if std_key in normalized and normalized[std_key] != display:
            per_source_warnings.append(
                IngestionWarning(
                    code="FIELD_CONFLICT",
                    detail=f"field={std_key!r} values=[{normalized[std_key]!r}, {display!r}]",
                    inputId=input_id,
                    fieldName=std_key,
                )
            )
            continue
        normalized[std_key] = display
        if details:
            normalized_details[std_key] = details
        if warn_code:
            per_source_warnings.append(
                IngestionWarning(
                    code=warn_code,
                    detail=f"field={std_key!r} value={raw_value!r}",
                    inputId=input_id,
                    fieldName=std_key,
                )
            )
    return normalized, normalized_details, per_source_warnings


def _merge_text_and_table_fields(
    inp: dict,
    normalized: dict[str, str],
    normalized_details: dict[str, dict],
    per_source_warnings: list[IngestionWarning],
    input_id: str,
) -> dict[str, str]:
    """2) extractedText / 3) extractedTables 에서 key-value 보강 후 merge."""
    text_extracted = _extract_from_text(inp.get("extractedText") or "")
    tables_extracted = _extract_from_tables(inp.get("extractedTables") or [])

    for source_dict in (text_extracted, tables_extracted):
        normalized_again: dict[str, str] = {}
        for k, v in source_dict.items():
            display, details, warn_code = _normalize_field_value(k, v)
            if not display:
                continue
            normalized_again[k] = display
            if details and k not in normalized_details:
                normalized_details[k] = details
            if warn_code:
                per_source_warnings.append(
                    IngestionWarning(
                        code=warn_code,
                        detail=f"field={k!r} value={v!r}",
                        inputId=input_id,
                        fieldName=k,
                    )
                )
        normalized = _merge_fields_with_conflict_check(
            normalized,
            normalized_again,
            per_source_warnings,
            input_id,
        )
    return normalized


def _build_evidence_source_record(
    inp: dict,
    input_id: str,
    source_name: str,
    source_type: str,
    normalized_fields: tuple[dict[str, str], dict[str, dict]],
    per_source_warnings: list[IngestionWarning],
) -> dict:
    """4) 결과 evidence 레코드 — confidence 계산 + 부족 경고 부가."""
    normalized, normalized_details = normalized_fields
    ev_id = inp.get("evidenceId") or f"ev_{uuid.uuid4().hex[:8]}"
    confidence = _confidence_for_source(
        source_type,
        num_fields=len(normalized),
        has_text=bool(inp.get("extractedText")),
        has_tables=bool(inp.get("extractedTables")),
    )

    if not normalized:
        per_source_warnings.append(
            IngestionWarning(
                code="MISSING_EXTRACTED_FIELDS",
                detail=f"no normalized field extracted from {source_name!r}",
                inputId=input_id,
            )
        )

    if confidence < 0.4:
        per_source_warnings.append(
            IngestionWarning(
                code="LOW_CONFIDENCE_EXTRACTION",
                detail=f"confidence={confidence}",
                inputId=input_id,
            )
        )

    return {
        "evidenceId": ev_id,
        "sourceType": source_type,
        "sourceName": source_name,
        "sourceHash": inp["sourceHash"],
        "extractedFields": normalized,
        "extractedFieldDetails": normalized_details,
        "confidence": confidence,
        "warnings": [w.to_dict() for w in per_source_warnings],
    }


# ── public API ──────────────────────────────────────────────────────────────


def build_evidence_sources(inputs: list[dict]) -> EvidenceIngestionResult:
    """업로드된 자료 입력 목록 → EvidenceIngestionResult."""
    result = EvidenceIngestionResult(requestId=str(uuid.uuid4()))
    result.sourceCount = len(inputs or [])

    for inp in inputs or []:
        if not isinstance(inp, dict):
            result.rejectedInputs.append(
                RejectedInput(
                    inputId="",
                    sourceName="",
                    reason="input is not a dict",
                    warningCode="EMPTY_INPUT",
                )
            )
            continue

        input_id = inp.get("inputId") or str(uuid.uuid4())
        source_name = inp.get("sourceName") or ""

        rejection = _reject_reason(inp)
        if rejection is not None:
            reason, warning_code = rejection
            result.rejectedInputs.append(
                RejectedInput(
                    inputId=input_id,
                    sourceName=source_name,
                    reason=reason,
                    warningCode=warning_code,
                )
            )
            continue

        source_type, type_warnings = _detect_source_type(inp)
        for code in type_warnings:
            result.warnings.append(
                IngestionWarning(
                    code=code,
                    detail=f"sourceName={source_name!r}",
                    inputId=input_id,
                )
            )

        normalized, normalized_details, per_source_warnings = _normalize_extracted_fields(
            inp.get("extractedFields") or {}, input_id
        )
        normalized = _merge_text_and_table_fields(
            inp, normalized, normalized_details, per_source_warnings, input_id
        )

        evidence_source = _build_evidence_source_record(
            inp,
            input_id,
            source_name,
            source_type,
            (normalized, normalized_details),
            per_source_warnings,
        )
        result.evidenceSources.append(evidence_source)
        result.warnings.extend(per_source_warnings)

    result.evidenceCount = len(result.evidenceSources)
    result.rejectedCount = len(result.rejectedInputs)
    return result
