"""HWPX-RECOGNITION-CONTENT-CLASSIFIER-CONTRACT-01.

내용 기반 documentType 분류기 — deterministic rule-based.

production 로직(fill_review_contract / live pipeline)은 이 모듈을 import하지 않는다.
AI API / OCR / writer 호출 없음. 운영 corpus DB write는 기본 비활성화.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from typing import Any

CLASSIFIER_VERSION = "content_classifier_v1"
ENGINE_VERSION = "rule-deterministic-v1"
SCHEMA_VERSION = "content_classification_result_v1"

# document_classifications.document_type CHECK 제약 (대분류 6종)
ALLOWED_DOCUMENT_TYPES: tuple[str, ...] = (
    "fillable_form",
    "reference_table",
    "empty_template",
    "unknown",
    "broken",
    "non_hwpx",
)
# evidence_json.subType 에 들어가는 세부 유형
ALLOWED_SUB_TYPES: tuple[str, ...] = (
    "application_form",
    "inspection_form",
    "checklist_form",
    "plan_form",
    "certification_form",
    "contract_form",
    "generic_fillable",
    "generic_reference",
    "gantt_template",
    "blank_template",
    "none",
)

# rule keyword sets
APPLICATION_LABELS = frozenset({
    "신청인",
    "신청서",
    "신청",
    "접수번호",
    "접수일자",
    "접수일",
    "대표자",
    "주소",
    "전화번호",
    "상호",
    "성명",
    "생년월일",
    "등록번호",
    "신고인",
    "신고",
    "사업자등록번호",
})
INSPECTION_KEYWORDS = ("점검", "검사", "확인", "적합", "부적합", "양호", "불량")
CHECKLIST_KEYWORDS = ("체크리스트", "checklist", "여부", "확인사항")
PLAN_KEYWORDS = ("계획서", "관리계획", "품질관리계획", "시공계획", "안전관리계획")
CONTRACT_KEYWORDS = ("계약", "계약금액", "공사명", "착공", "준공", "발주자", "시공자", "수급인")
CERTIFICATION_KEYWORDS = ("인증서", "확인증", "증명서", "수료증", "자격증")
REFERENCE_KEYWORDS = ("기준", "요령", "단위량", "보유기준", "작성기준", "산출기준", "별표")
QUESTION_REGEX = re.compile(r"(인가\?|입니까\?|합니까\?|있습니까\?|여부\b)")


# ── filename heuristic ───────────────────────────────────────────────────


def classify_by_filename(rel_path: str) -> str:
    p = rel_path.replace("\\", "/")
    if "[별지" in p:
        return "fillable_form"
    if "[별표" in p:
        return "reference_table"
    if "/gantt/" in p or "gantt" in p.rsplit("/", 1)[-1].lower():
        return "empty_template"
    if "/corpus/" in p and p.endswith(".hwpx"):
        return "fillable_form"
    return "unknown"


# ── feature extraction ──────────────────────────────────────────────────


def _iter_cells(parser_result) -> Iterable[Any]:
    for t in getattr(parser_result, "tables", []) or []:
        for c in getattr(t, "cells", []) or []:
            yield c


def _iter_paragraphs(parser_result) -> Iterable[Any]:
    for p in getattr(parser_result, "paragraphs", []) or []:
        yield p


def extract_content_features(parser_result, rel_path: str = "") -> dict:
    """parser_engine 결과 또는 fixture dict-like 객체에서 feature 추출."""
    tables = getattr(parser_result, "tables", []) or []
    paragraphs = list(_iter_paragraphs(parser_result))
    cells = list(_iter_cells(parser_result))

    cell_count = len(cells)
    table_count = len(tables)

    # cell index by (table, row, col) for right-neighbor check
    by_pos: dict[tuple, Any] = {}
    for c in cells:
        tid = getattr(c, "tableId", None) or ""
        by_pos[tid, getattr(c, "row", -1), getattr(c, "col", -1)] = c

    label_texts: list[str] = []
    right_empty = 0
    label_value_pairs = 0
    for c in cells:
        txt = (getattr(c, "normalizedText", "") or "").strip()
        if not txt or len(txt) > 25:
            continue
        tid = getattr(c, "tableId", None) or ""
        right = by_pos.get((tid, getattr(c, "row", -1), getattr(c, "col", -1) + 1))
        right_txt = getattr(right, "normalizedText", "") if right is not None else None
        if right is not None and (right_txt or "").strip() == "":
            right_empty += 1
            label_texts.append(txt)
        if right is not None and right_txt and len(right_txt) <= 30:
            label_value_pairs += 1

    para_texts = [
        (getattr(p, "normalizedText", "") or getattr(p, "text", "") or "") for p in paragraphs
    ]
    para_joined = " ".join(para_texts)
    question_count = len(QUESTION_REGEX.findall(para_joined))
    empty_para_ratio = sum(1 for t in para_texts if not t.strip()) / max(len(para_texts), 1)

    application_hits = sum(1 for l in label_texts if l in APPLICATION_LABELS)
    inspection_hits = sum(1 for kw in INSPECTION_KEYWORDS if kw in para_joined)
    checklist_hits = sum(1 for kw in CHECKLIST_KEYWORDS if kw in para_joined)
    plan_hits = sum(1 for kw in PLAN_KEYWORDS if kw in para_joined)
    contract_hits = sum(1 for kw in CONTRACT_KEYWORDS if kw in para_joined)
    cert_hits = sum(1 for kw in CERTIFICATION_KEYWORDS if kw in para_joined)
    reference_hits = sum(1 for kw in REFERENCE_KEYWORDS if kw in para_joined)

    unique_labels = len(set(label_texts))
    blank_ratio = right_empty / max(cell_count, 1)

    return {
        "filenamePath": rel_path,
        "tableCount": table_count,
        "cellCount": cell_count,
        "paragraphCount": len(paragraphs),
        "labelOccurrenceCount": len(label_texts),
        "uniqueLabelCount": unique_labels,
        "rightNeighborEmptyCount": right_empty,
        "labelValuePairCandidateCount": label_value_pairs,
        "blankNeighborRatio": round(blank_ratio, 4),
        "questionSentenceCount": question_count,
        "emptyParagraphRatio": round(empty_para_ratio, 4),
        "applicationLabelHits": application_hits,
        "inspectionKeywordHits": inspection_hits,
        "checklistKeywordHits": checklist_hits,
        "planKeywordHits": plan_hits,
        "contractKeywordHits": contract_hits,
        "certificationKeywordHits": cert_hits,
        "referenceKeywordHits": reference_hits,
        "knownSemanticLabelCount": application_hits,
        "unknownLabelCount": max(unique_labels - application_hits, 0),
        "labelSamples": label_texts[:20],
    }


# ── classification ──────────────────────────────────────────────────────


def _score_types(f: dict) -> dict[str, float]:
    """대분류 score 산출 (0~1+ 범위, 정규화 전)."""
    fillable = (
        0.6 * min(f["rightNeighborEmptyCount"] / 8, 1.0)
        + 0.3 * min(f["labelValuePairCandidateCount"] / 10, 1.0)
        + 0.4 * min(f["applicationLabelHits"] / 3, 1.0)
    )
    reference = (
        0.5 * min(f["referenceKeywordHits"] / 3, 1.0)
        + 0.3 * (1.0 if f["blankNeighborRatio"] < 0.05 and f["labelOccurrenceCount"] >= 3 else 0.0)
        + 0.2 * min(f["cellCount"] / 200, 1.0)
    )
    if f["labelOccurrenceCount"] < 3 and f["referenceKeywordHits"] == 0:
        reference *= 0.3
    empty = 0.0
    if f["cellCount"] <= 3 and f["paragraphCount"] <= 3:
        empty = 0.9
    elif f["labelOccurrenceCount"] == 0 and f["emptyParagraphRatio"] > 0.6:
        empty = 0.7
    # gantt 경로 우선
    if "/gantt/" in (f.get("filenamePath", "") or ""):
        empty = max(empty, 0.85)
    return {
        "fillable_form": round(fillable, 4),
        "reference_table": round(reference, 4),
        "empty_template": round(empty, 4),
    }


def _classify_subtype(f: dict, main_type: str) -> str:
    if main_type == "empty_template":
        if "/gantt/" in (f.get("filenamePath", "") or ""):
            return "gantt_template"
        return "blank_template"
    if main_type == "reference_table":
        return "generic_reference"
    if main_type == "fillable_form":
        scores = {
            "checklist_form": (f["checklistKeywordHits"] * 2 + f["questionSentenceCount"]),
            "inspection_form": f["inspectionKeywordHits"],
            "plan_form": f["planKeywordHits"] * 2,
            "contract_form": f["contractKeywordHits"] * 2,
            "certification_form": f["certificationKeywordHits"] * 2,
            "application_form": f["applicationLabelHits"],
        }
        best = max(scores.items(), key=lambda x: x[1])
        if best[1] <= 0:
            return "generic_fillable"
        return best[0]
    return "none"


def _classify_type_and_warnings(
    top: str,
    top_score: float,
    second_score: float,
    features: dict,
    filename_type: str | None,
) -> tuple[str, float, list[str], bool, bool]:
    warnings: list[str] = []

    if top_score < 0.15:
        content_type = "unknown"
        confidence = 0.2
        warnings.append("UNKNOWN_DOCUMENT_TYPE")
        warnings.append("INSUFFICIENT_LABELS")
    else:
        content_type = top
        confidence = min(top_score, 1.0)

    if confidence < 0.4 and content_type != "unknown":
        warnings.append("LOW_CONFIDENCE_CLASSIFICATION")
    if features["labelOccurrenceCount"] < 3:
        warnings.append("INSUFFICIENT_LABELS")
    if features["paragraphCount"] == 0 and features["cellCount"] <= 3:
        warnings.append("EMPTY_OR_SPARSE_TEXT")

    ambiguous = (top_score - second_score) < 0.10 and top_score > 0.15
    if ambiguous:
        warnings.append("AMBIGUOUS_DOCUMENT_TYPE")
        warnings.append("NEEDS_HUMAN_REVIEW")

    disagreement = (
        filename_type in ("fillable_form", "reference_table", "empty_template")
        and filename_type != content_type
    )
    if disagreement:
        warnings.append("FILENAME_CONTENT_DISAGREEMENT")
        warnings.append("NEEDS_HUMAN_REVIEW")

    return content_type, confidence, warnings, ambiguous, disagreement


def _compute_evidence_signals(
    features: dict, content_type: str
) -> tuple[list[str], list[str], list[str]]:
    positive_signals: list[str] = []
    negative_signals: list[str] = []
    matched_rules: list[str] = []
    if content_type == "fillable_form":
        matched_rules.append("rule:right_neighbor_empty>=threshold")
        if features["applicationLabelHits"] > 0:
            positive_signals.append(f"applicationLabelHits={features['applicationLabelHits']}")
    if content_type == "reference_table":
        matched_rules.append("rule:reference_keywords_dominant")
    if content_type == "empty_template":
        matched_rules.append("rule:sparse_cells_and_paragraphs")
    if features["blankNeighborRatio"] < 0.02 and content_type == "fillable_form":
        negative_signals.append("low_blank_neighbor_ratio")
    return matched_rules, positive_signals, negative_signals


def classify_document_content(
    features: dict, filename_type: str | None = None, document_id: str = ""
) -> dict:
    """feature dict → ContentClassificationResult."""
    if filename_type is None:
        filename_type = classify_by_filename(features.get("filenamePath", ""))

    scores = _score_types(features)
    ranked = sorted(scores.items(), key=lambda x: -x[1])
    top, top_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0.0

    content_type, confidence, warnings, ambiguous, disagreement = _classify_type_and_warnings(
        top, top_score, second_score, features, filename_type
    )

    sub_type = _classify_subtype(features, content_type)

    feature_summary = {
        "tableCount": features["tableCount"],
        "cellCount": features["cellCount"],
        "labelOccurrenceCount": features["labelOccurrenceCount"],
        "uniqueLabelCount": features["uniqueLabelCount"],
        "rightNeighborEmptyCount": features["rightNeighborEmptyCount"],
        "labelValuePairCandidateCount": features["labelValuePairCandidateCount"],
        "questionSentenceCount": features["questionSentenceCount"],
        "knownSemanticLabelCount": features["knownSemanticLabelCount"],
        "unknownLabelCount": features["unknownLabelCount"],
    }

    matched_rules, positive_signals, negative_signals = _compute_evidence_signals(
        features, content_type
    )

    return {
        "schemaVersion": SCHEMA_VERSION,
        "engineVersion": ENGINE_VERSION,
        "classifierVersion": CLASSIFIER_VERSION,
        "documentId": document_id,
        "filenamePatternType": filename_type,
        "contentType": content_type,
        "subType": sub_type,
        "confidence": round(float(confidence), 4),
        "scores": scores,
        "evidence": {
            "matchedRules": matched_rules,
            "positiveSignals": positive_signals,
            "negativeSignals": negative_signals,
            "labelExamples": features.get("labelSamples", [])[:10],
            "topLabels": features.get("labelSamples", [])[:5],
            "reason": f"top={content_type} score={confidence}",
        },
        "featureSummary": feature_summary,
        "disagreement": disagreement,
        "ambiguous": ambiguous,
        "warnings": warnings,
    }


# ── helpers ─────────────────────────────────────────────────────────────


def compare_filename_and_content_classification(filename_type: str, content_type: str) -> bool:
    """disagreement 판단. filename이 unknown이면 disagreement False."""
    if filename_type == "unknown":
        return False
    return filename_type != content_type


def build_document_classification_record(result: dict, classified_at: str) -> dict:
    """document_classifications INSERT용 dict."""
    if result["contentType"] not in ALLOWED_DOCUMENT_TYPES:
        raise ValueError(f"contentType {result['contentType']!r} not in ALLOWED_DOCUMENT_TYPES")
    evidence = {
        "subType": result["subType"],
        "scores": result["scores"],
        "evidence": result["evidence"],
        "featureSummary": result["featureSummary"],
        "disagreement": result["disagreement"],
        "ambiguous": result["ambiguous"],
        "warnings": result["warnings"],
        "filenamePatternType": result["filenamePatternType"],
        "engineVersion": result["engineVersion"],
        "schemaVersion": result["schemaVersion"],
    }
    return {
        "document_id": result["documentId"],
        "classifier_version": result["classifierVersion"],
        "document_type": result["contentType"],
        "confidence": result["confidence"],
        "evidence_json": json.dumps(evidence, ensure_ascii=False),
        "classified_at": classified_at,
    }


def summarize_classification_disagreements(results: Iterable[dict]) -> dict:
    """filename vs content 불일치 통계."""
    total = 0
    disagreements = 0
    ambiguous = 0
    needs_review = 0
    by_pair: dict[str, int] = {}
    for r in results:
        total += 1
        if r.get("disagreement"):
            disagreements += 1
            key = f"{r['filenamePatternType']}->{r['contentType']}"
            by_pair[key] = by_pair.get(key, 0) + 1
        if r.get("ambiguous"):
            ambiguous += 1
        if "NEEDS_HUMAN_REVIEW" in r.get("warnings", []):
            needs_review += 1
    return {
        "total": total,
        "disagreementCount": disagreements,
        "ambiguousCount": ambiguous,
        "needsHumanReviewCount": needs_review,
        "byPair": by_pair,
    }
