"""HWPX-SOURCE-EXTRACTOR-CONTRACT-01.

자재창고 통합 라우터 — PDF / Excel / HWP / 텍스트 / 이미지(OCR) 등
외부 소스 자료에서 라벨별 값을 추출해서 evidence_ingestion 표준 형식으로 출력.

본 모듈은 **신규 파싱 로직을 작성하지 않는다.** 각 파서(KPRC, PDF batch,
Excel, OCR 등)는 외부 callable로 주입한다.

방화구획:
- production 운영동에서 본 모듈 import 금지
- 외부 모델 / OCR / writer / output HWPX / secret 미참조
- raw 개인정보 저장 금지 (evidence 표준 형식이 해시·정규화 처리)
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

CONTRACT_NAME = "HWPX-SOURCE-EXTRACTOR-CONTRACT-01"
CONTRACT_VERSION = "v1"

ALLOWED_SOURCE_TYPES: frozenset[str] = frozenset({
    "pdf", "excel", "hwp", "hwpx", "text", "csv",
    "json", "image", "kprc", "url",
})

# 추출기 callable signature:
# fn(source: dict, target_labels: list[str]) -> list[dict]
# 반환 dict 표준:
# {
#   "label": str,              # normalized label
#   "value": str,              # raw value (downstream에서 hash 처리)
#   "evidenceType": str,       # "pdf_text" / "excel_cell" / "hwp_field" / ...
#   "sourceRef": str,          # 어느 소스에서 왔는지 (file:line, sheet:cell 등)
#   "confidence": float,       # 0.0~1.0
# }

ExtractorCallable = Callable[[dict, list[str]], list[dict]]


class ExtractorRejection(ValueError):
    pass


# ── source descriptor 검증 ─────────────────────────────────────────────────

REQUIRED_SOURCE_FIELDS: tuple[str, ...] = ("sourceId", "sourceType")
FORBIDDEN_SOURCE_FIELDS: tuple[str, ...] = (
    "credential", "token", "password", "secret",
    "apiKey", "sessionCookie",
)


def validate_source_descriptor(s: dict) -> list[str]:
    if not isinstance(s, dict):
        return ["SOURCE_NOT_OBJECT"]
    errs: list[str] = [f"MISSING_FIELD:{k}" for k in REQUIRED_SOURCE_FIELDS if k not in s]
    st = s.get("sourceType")
    if st is not None and st not in ALLOWED_SOURCE_TYPES:
        errs.append(f"UNKNOWN_SOURCE_TYPE:{st}")
    errs.extend(f"FORBIDDEN_FIELD:{forbidden}" for forbidden in FORBIDDEN_SOURCE_FIELDS if forbidden in s)
    return errs


def validate_source_batch(sources: list) -> dict:
    accepted: list[dict] = []
    rejected: list[dict] = []
    seen_ids: set[str] = set()
    for s in sources or []:
        errs = validate_source_descriptor(s)
        sid = s.get("sourceId") if isinstance(s, dict) else None
        if isinstance(sid, str) and sid in seen_ids:
            errs.append("DUPLICATE_SOURCE_ID")
        if errs:
            rejected.append({"sourceId": sid, "errors": errs})
        else:
            seen_ids.add(sid)
            accepted.append(s)
    return {"accepted": accepted, "rejected": rejected,
              "acceptedCount": len(accepted),
              "rejectedCount": len(rejected)}


# ── extracted value 검증 ──────────────────────────────────────────────────

EXTRACTED_REQUIRED: tuple[str, ...] = (
    "label", "value", "evidenceType", "sourceRef", "confidence",
)


def validate_extracted_value(v: dict) -> list[str]:
    if not isinstance(v, dict):
        return ["EXTRACTED_NOT_OBJECT"]
    errs: list[str] = [f"MISSING_FIELD:{k}" for k in EXTRACTED_REQUIRED if k not in v]
    c = v.get("confidence")
    if c is not None:
        if not isinstance(c, (int, float)):
            errs.append("CONFIDENCE_NOT_NUMBER")
        elif not (0.0 <= float(c) <= 1.0):
            errs.append("CONFIDENCE_OUT_OF_RANGE")
    return errs


# ── 정규화 helper ─────────────────────────────────────────────────────────

_NORM_LABEL_RE = re.compile(r"[\s\(\)\[\]\.,:;·\-_/]+")


def normalize_label(label: str) -> str:
    if not label:
        return ""
    return _NORM_LABEL_RE.sub("", label).strip()


# ── 통합 추출기 (라우터) ──────────────────────────────────────────────────

def extract_values_from_sources(
    sources: list[dict],
    target_labels: list[str],
    *,
    extractor_registry: dict[str, ExtractorCallable] | None = None,
) -> dict:
    """여러 소스 자료에서 target_labels에 매칭되는 값을 모두 추출.

    Args:
        sources: source descriptor 리스트 ({sourceId, sourceType, ...})
        target_labels: 찾고자 하는 normalized 라벨 리스트
        extractor_registry: sourceType → ExtractorCallable 매핑.
            None이면 추출 0건 + 모든 source가 NO_EXTRACTOR 사유로 skip.
            production에서는 KPRC/PDF/Excel 파서를 주입.

    Returns:
        {
          extractedValues: list[dict],
          rejectedSources: list,
          skippedSources: list[{sourceId, reason}],
          summary: {sourceCount, extractedCount, byEvidenceType}
        }
    """
    registry = extractor_registry or {}
    norm_targets = [normalize_label(t) for t in (target_labels or []) if t]
    norm_set = set(norm_targets)

    src_result = validate_source_batch(sources)
    accepted_sources = src_result["accepted"]
    extracted: list[dict] = []
    skipped: list[dict] = []
    by_evidence: dict[str, int] = {}

    for s in accepted_sources:
        st = s["sourceType"]
        fn = registry.get(st)
        if fn is None:
            skipped.append({"sourceId": s["sourceId"],
                              "reason": f"NO_EXTRACTOR:{st}"})
            continue
        try:
            raw = fn(s, list(norm_targets))
        except Exception as e:
            skipped.append({"sourceId": s["sourceId"],
                              "reason": f"EXTRACTOR_ERROR:{e!s}"[:200]})
            continue
        if not isinstance(raw, list):
            skipped.append({"sourceId": s["sourceId"],
                              "reason": "EXTRACTOR_RETURN_NOT_LIST"})
            continue
        for v in raw:
            errs = validate_extracted_value(v)
            if errs:
                continue
            v_norm = dict(v)
            v_norm["label"] = normalize_label(v.get("label") or "")
            if norm_set and v_norm["label"] not in norm_set:
                continue  # 요청된 라벨만 통과
            v_norm["sourceId"] = s["sourceId"]
            extracted.append(v_norm)
            et = v_norm.get("evidenceType") or "unknown"
            by_evidence[et] = by_evidence.get(et, 0) + 1

    return {
        "extractedValues": extracted,
        "rejectedSources": src_result["rejected"],
        "skippedSources": skipped,
        "summary": {
            "sourceCount": len(sources or []),
            "acceptedSourceCount": len(accepted_sources),
            "extractedCount": len(extracted),
            "byEvidenceType": by_evidence,
            "targetLabelCount": len(norm_targets),
        },
    }


# ── evidence_ingestion 호환 형식으로 변환 ─────────────────────────────────

def to_evidence_inputs(extracted_values: list[dict]) -> list[dict]:
    """extract_values_from_sources() 결과를 evidence_ingestion_contract
    표준 입력 형식으로 변환.

    표준 입력은 운영동 evidence_ingestion이 받을 수 있는 dict 리스트.
    """
    out: list[dict] = [{
            "evidenceId": f"src-{v.get('sourceId')}-{v.get('label')}",
            "sourceType": v.get("evidenceType"),
            "sourceRef": v.get("sourceRef"),
            "label": v.get("label"),
            "value": v.get("value"),
            "confidence": v.get("confidence"),
        } for v in extracted_values or []]
    return out


def dump_contract_snapshot() -> dict:
    return {
        "contractName": CONTRACT_NAME,
        "contractVersion": CONTRACT_VERSION,
        "allowedSourceTypes": sorted(ALLOWED_SOURCE_TYPES),
        "extractedRequiredFields": list(EXTRACTED_REQUIRED),
        "forbiddenSourceFields": list(FORBIDDEN_SOURCE_FIELDS),
    }


# ── production isolation ───────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PRODUCTION_PATHS_FOR_SOURCE_EXTRACTOR: tuple[Path, ...] = (
    PROJECT_ROOT / "scripts/hwpx/fill_review/fill_review_contract.py",
    PROJECT_ROOT / "scripts/hwpx/fill_review/fill_review_ui_adapter.py",
    PROJECT_ROOT / "scripts/hwpx/fill_review/fill_review_live_pipeline.py",
    PROJECT_ROOT / "scripts/hwpx/fill_review/evidence_ingestion_contract.py",
)
FORBIDDEN_SOURCE_EXTRACTOR_IMPORTS: tuple[str, ...] = (
    "source_extractor_contract",
    "extract_values_from_sources",
)


def audit_source_extractor_isolation() -> dict:
    violations: list[dict] = []
    checked: list[str] = []
    for path in PRODUCTION_PATHS_FOR_SOURCE_EXTRACTOR:
        if not path.is_file():
            continue
        checked.append(str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"))
        text = path.read_text(encoding="utf-8", errors="ignore")
        violations.extend({
                    "file": str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
                    "forbidden": needle,
                } for needle in FORBIDDEN_SOURCE_EXTRACTOR_IMPORTS if needle in text)
    return {"violations": violations, "ok": not violations,
              "filesChecked": checked}
