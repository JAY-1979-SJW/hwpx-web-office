"""HWPX-RECOGNITION-LABEL-PROMOTION-CANDIDATE-REVIEW-BATCH-01.

PENDING promotion candidate를 사람 승인용 review batch로 정리.
이번 공정은 human_label_decisions INSERT / dictionary version 생성 /
production 사전 수정을 수행하지 않는다.
"""
from __future__ import annotations

import sqlite3
import uuid
from typing import Iterable

from scripts.hwpx.recognition_corpus import corpus_schema as cs

ENGINE_VERSION = "review-batch-deterministic-v1"
SCHEMA_VERSION = "review_batch_result_v1"
APPROVAL_INPUT_SCHEMA_VERSION = "human_approval_batch_input_v1"

DEFAULT_TOP_N = 300
EXAMPLE_LABEL_LIMIT = 5
EXAMPLE_DOCUMENT_LIMIT = 5
TOP_CONTEXT_LIMIT = 3

# multi-meaning / generic label 후보
MULTI_MEANING_LABELS = frozenset({
    "성명", "이름", "주소", "구분", "내용", "비고", "항목",
    "날짜", "일자", "기간", "수량", "단위", "번호", "구역", "계",
})


# ── ranking & bucketing ──────────────────────────────────────────────────

def _risk_flags(cand: dict, *,
                  is_conflict: bool, is_disagreement_only: bool,
                  is_ambiguous_only: bool) -> list[str]:
    flags: list[str] = []
    sem = cand.get("proposed_semantic") or cand.get("proposedSemantic")
    label = cand.get("normalized_label") or cand.get("normalizedLabel")
    occ = int(cand.get("occurrence_count")
                or cand.get("occurrenceCount") or 0)
    docs = int(cand.get("document_count")
                  or cand.get("documentCount") or 0)
    score = float(cand.get("evidence_score")
                      or cand.get("evidenceScore") or 0.0)
    if sem == "UNKNOWN":
        flags.append("UNKNOWN_SEMANTIC")
    if is_conflict:
        flags.append("CONFLICTING_SEMANTIC")
    if is_disagreement_only:
        flags.append("DISAGREEMENT_EVIDENCE")
    if is_ambiguous_only:
        flags.append("AMBIGUOUS_EVIDENCE")
    if score < 0.3:
        flags.append("LOW_EVIDENCE_SCORE")
    if docs < 3:
        flags.append("LOW_DOCUMENT_COUNT")
    if label in MULTI_MEANING_LABELS:
        flags.append("MULTI_MEANING_LABEL")
        flags.append("GENERIC_LABEL")
    if occ >= 500 and docs >= 50 and not flags:
        flags.append("SAFE_HIGH_FREQUENCY_LABEL")
    return flags


def bucket_promotion_candidate(cand: dict, *,
                                    conflicts: int = 0,
                                    is_disagreement_only: bool = False,
                                    is_ambiguous_only: bool = False) -> str:
    sem = cand.get("proposed_semantic") or cand.get("proposedSemantic")
    if sem == "UNKNOWN":
        return "BLOCKED_UNKNOWN_SEMANTIC"
    if conflicts > 0:
        return "BLOCKED_CONFLICT"
    if is_disagreement_only:
        return "BLOCKED_DISAGREEMENT_ONLY"
    if is_ambiguous_only:
        return "BLOCKED_AMBIGUOUS_ONLY"

    occ = int(cand.get("occurrence_count")
                  or cand.get("occurrenceCount") or 0)
    docs = int(cand.get("document_count")
                  or cand.get("documentCount") or 0)
    score = float(cand.get("evidence_score")
                      or cand.get("evidenceScore") or 0.0)
    if score < 0.3 or occ < 5 or docs < 2:
        return "HELD_LOW_EVIDENCE"
    if occ >= 200 and docs >= 30 and score >= 0.6:
        return "HIGH_PRIORITY_REVIEW"
    if occ >= 20 and docs >= 5 and score >= 0.45:
        return "MEDIUM_PRIORITY_REVIEW"
    return "LOW_PRIORITY_REVIEW"


def _recommend_decision(bucket: str, risk_flags: list[str]) -> str:
    if bucket.startswith("BLOCKED_"):
        return "BLOCKED"
    if "MULTI_MEANING_LABEL" in risk_flags:
        return "REVIEW_REQUIRED"
    if bucket == "HIGH_PRIORITY_REVIEW":
        return "APPROVE_RECOMMENDED"
    if bucket == "MEDIUM_PRIORITY_REVIEW":
        return "REVIEW_REQUIRED"
    if bucket == "LOW_PRIORITY_REVIEW":
        return "HOLD_RECOMMENDED"
    if bucket == "HELD_LOW_EVIDENCE":
        return "HOLD_RECOMMENDED"
    return "REVIEW_REQUIRED"


def rank_promotion_candidates(candidates: Iterable[dict]) -> list[dict]:
    """occurrence × evidenceScore + documents priority desc."""
    def _key(c):
        occ = int(c.get("occurrence_count")
                      or c.get("occurrenceCount") or 0)
        docs = int(c.get("document_count")
                      or c.get("documentCount") or 0)
        score = float(c.get("evidence_score")
                          or c.get("evidenceScore") or 0.0)
        return -(occ * score + docs * 5)
    return sorted(candidates, key=_key)


# ── DB context lookup ───────────────────────────────────────────────────

def _semantic_conflict_count(conn: sqlite3.Connection, label: str,
                                  proposed: str) -> int:
    rows = cs.detect_semantic_conflicts(conn, label)
    return sum(1 for r in rows if r["semantic_type"] != proposed)


def _example_documents(conn, label, limit) -> list[str]:
    rows = conn.execute(
        "SELECT DISTINCT document_id FROM label_occurrences "
        "WHERE normalized_label=? LIMIT ?", (label, limit)).fetchall()
    return [r[0] for r in rows]


def _example_label_texts(conn, label, limit) -> list[str]:
    rows = conn.execute(
        "SELECT DISTINCT label_text FROM label_occurrences "
        "WHERE normalized_label=? LIMIT ?", (label, limit)).fetchall()
    return [r[0] for r in rows]


def _document_types(conn, doc_ids: list[str]) -> dict[str, int]:
    if not doc_ids:
        return {}
    placeholders = ",".join("?" * len(doc_ids))
    rows = conn.execute(
        f"SELECT document_type, COUNT(*) "
        f"  FROM document_classifications WHERE document_id IN "
        f"({placeholders}) GROUP BY document_type", doc_ids).fetchall()
    return {r[0]: r[1] for r in rows}


def _top_contexts(conn, label, limit) -> list[str]:
    rows = conn.execute(
        "SELECT neighbor_text FROM label_occurrences "
        "WHERE normalized_label=? AND neighbor_text IS NOT NULL "
        "AND neighbor_text != '' LIMIT ?", (label, limit)).fetchall()
    return [r[0][:60] for r in rows]


def _build_review_candidate(conn, raw, *,
                                 tainted_disagreement: set[str] | None,
                                 tainted_ambiguous: set[str] | None,
                                 candidate_id: str) -> dict:
    label = raw["normalized_label"]
    proposed = raw["proposed_semantic"]
    conflicts = _semantic_conflict_count(conn, label, proposed)

    doc_ids = _example_documents(conn, label, 50)
    tainted_d = tainted_disagreement or set()
    tainted_a = tainted_ambiguous or set()
    if doc_ids:
        clean = [d for d in doc_ids
                    if d not in tainted_d and d not in tainted_a]
        is_disagreement_only = (
            all(d in tainted_d for d in doc_ids) if doc_ids else False)
        is_ambiguous_only = (
            all(d in tainted_a for d in doc_ids) if doc_ids else False)
    else:
        is_disagreement_only = False
        is_ambiguous_only = False

    bucket = bucket_promotion_candidate(
        raw, conflicts=conflicts,
        is_disagreement_only=is_disagreement_only,
        is_ambiguous_only=is_ambiguous_only)
    flags = _risk_flags(
        raw, is_conflict=conflicts > 0,
        is_disagreement_only=is_disagreement_only,
        is_ambiguous_only=is_ambiguous_only)
    rec = _recommend_decision(bucket, flags)
    reason = f"bucket={bucket} risk={','.join(flags) or 'none'}"

    return {
        "candidateId": candidate_id,
        "normalizedLabel": label,
        "proposedSemantic": proposed,
        "occurrenceCount": int(raw["occurrence_count"]),
        "documentCount": int(raw["document_count"]),
        "evidenceScore": float(raw["evidence_score"]),
        "exampleLabels": _example_label_texts(
            conn, label, EXAMPLE_LABEL_LIMIT),
        "exampleDocuments": doc_ids[:EXAMPLE_DOCUMENT_LIMIT],
        "documentTypes": _document_types(
            conn, doc_ids[:EXAMPLE_DOCUMENT_LIMIT]),
        "subTypes": [],
        "topContexts": _top_contexts(conn, label, TOP_CONTEXT_LIMIT),
        "riskFlags": flags,
        "recommendedDecision": rec,
        "reason": reason,
        "_bucket": bucket,
    }


# ── batch build ─────────────────────────────────────────────────────────

def build_promotion_review_batch(
        conn: sqlite3.Connection,
        *,
        top_n: int = DEFAULT_TOP_N,
        tainted_disagreement: set[str] | None = None,
        tainted_ambiguous: set[str] | None = None,
        source_corpus_sha: str = "",
        request_id: str = "",
) -> dict:
    rows = conn.execute(
        "SELECT normalized_label, proposed_semantic, occurrence_count,"
        " document_count, evidence_score FROM label_promotion_candidates"
        " WHERE status='PENDING'"
    ).fetchall()
    raws = [
        {"normalized_label": r[0], "proposed_semantic": r[1],
            "occurrence_count": r[2], "document_count": r[3],
            "evidence_score": r[4]} for r in rows
    ]
    ranked = rank_promotion_candidates(raws)[:top_n]

    candidates: list[dict] = []
    for i, raw in enumerate(ranked):
        candidates.append(_build_review_candidate(
            conn, raw,
            tainted_disagreement=tainted_disagreement,
            tainted_ambiguous=tainted_ambiguous,
            candidate_id=f"cand-{i:05d}"))

    buckets: dict[str, list[dict]] = {
        "HIGH_PRIORITY_REVIEW": [],
        "MEDIUM_PRIORITY_REVIEW": [],
        "LOW_PRIORITY_REVIEW": [],
        "BLOCKED_UNKNOWN_SEMANTIC": [],
        "BLOCKED_CONFLICT": [],
        "BLOCKED_DISAGREEMENT_ONLY": [],
        "BLOCKED_AMBIGUOUS_ONLY": [],
        "HELD_LOW_EVIDENCE": [],
    }
    for c in candidates:
        b = c["_bucket"]
        buckets.setdefault(b, []).append(c)

    reviewable = (len(buckets["HIGH_PRIORITY_REVIEW"])
                      + len(buckets["MEDIUM_PRIORITY_REVIEW"])
                      + len(buckets["LOW_PRIORITY_REVIEW"]))
    blocked = (len(buckets["BLOCKED_UNKNOWN_SEMANTIC"])
                  + len(buckets["BLOCKED_CONFLICT"])
                  + len(buckets["BLOCKED_DISAGREEMENT_ONLY"])
                  + len(buckets["BLOCKED_AMBIGUOUS_ONLY"]))

    warnings: list[str] = []
    if blocked > reviewable:
        warnings.append("MORE_BLOCKED_THAN_REVIEWABLE")

    return {
        "schemaVersion": SCHEMA_VERSION,
        "engineVersion": ENGINE_VERSION,
        "requestId": request_id or uuid.uuid4().hex[:12],
        "sourceCorpusSha": source_corpus_sha,
        "generatedAt": _utc_iso(),
        "candidateCount": len(candidates),
        "reviewableCount": reviewable,
        "blockedCount": blocked,
        "conflictCount": len(buckets["BLOCKED_CONFLICT"]),
        "unknownSemanticCount": len(buckets["BLOCKED_UNKNOWN_SEMANTIC"]),
        "disagreementOnlyCount": len(buckets["BLOCKED_DISAGREEMENT_ONLY"]),
        "ambiguousOnlyCount": len(buckets["BLOCKED_AMBIGUOUS_ONLY"]),
        "buckets": {k: [{kk: vv for kk, vv in c.items() if kk != "_bucket"}
                              for c in v]
                       for k, v in buckets.items()},
        "topReviewCandidates": [
            {kk: vv for kk, vv in c.items() if kk != "_bucket"}
            for c in (buckets["HIGH_PRIORITY_REVIEW"][:20]
                          + buckets["MEDIUM_PRIORITY_REVIEW"][:20])
        ],
        "warnings": warnings,
    }


def _utc_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ── markdown ─────────────────────────────────────────────────────────────

def build_review_markdown(batch: dict, *, max_rows: int = 100) -> str:
    lines = [
        "# HWPX Label Promotion Review Batch",
        "",
        f"- generated: {batch['generatedAt']}",
        f"- candidates: {batch['candidateCount']}",
        f"- reviewable: {batch['reviewableCount']}",
        f"- blocked: {batch['blockedCount']}",
        f"- unknown semantic: {batch['unknownSemanticCount']}",
        f"- conflict: {batch['conflictCount']}",
        f"- disagreementOnly: {batch['disagreementOnlyCount']}",
        f"- ambiguousOnly: {batch['ambiguousOnlyCount']}",
        "",
        "## Review Table",
        "",
        "| candidateId | normalizedLabel | proposedSemantic | occ "
        "| docs | score | risk | recommended | reviewerDecision "
        "| reviewerComment |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    rows = (batch["buckets"]["HIGH_PRIORITY_REVIEW"]
              + batch["buckets"]["MEDIUM_PRIORITY_REVIEW"]
              + batch["buckets"]["LOW_PRIORITY_REVIEW"])
    for c in rows[:max_rows]:
        risk = ",".join(c["riskFlags"]) or "-"
        lines.append(
            f"| {c['candidateId']} | {c['normalizedLabel']} "
            f"| {c['proposedSemantic']} | {c['occurrenceCount']} "
            f"| {c['documentCount']} | {c['evidenceScore']:.2f} "
            f"| {risk} | {c['recommendedDecision']} |  |  |")
    return "\n".join(lines)


# ── approval input validation ────────────────────────────────────────────

ALLOWED_DECISIONS = ("APPROVE", "REJECT", "HOLD")


def validate_human_approval_batch_input(
        approval: dict,
        *,
        review_batch: dict | None = None,
) -> dict:
    """approval JSON validate. INSERT는 수행하지 않는다."""
    errors: list[dict] = []
    must = ("schemaVersion", "approvedBy", "decidedAt", "decisions")
    for k in must:
        if k not in approval:
            errors.append({"code": "MISSING_FIELD", "field": k})
    if approval.get("schemaVersion") != APPROVAL_INPUT_SCHEMA_VERSION:
        errors.append({"code": "INVALID_SCHEMA_VERSION",
                          "field": "schemaVersion"})
    if not (approval.get("approvedBy") or "").strip():
        errors.append({"code": "EMPTY_APPROVED_BY",
                          "field": "approvedBy"})

    # build lookup if review_batch provided
    label_by_id: dict[str, dict] = {}
    if review_batch is not None:
        for bucket_name, items in review_batch.get("buckets", {}).items():
            for c in items:
                label_by_id[c["candidateId"]] = {**c, "_bucket": bucket_name}

    for i, d in enumerate(approval.get("decisions", []) or []):
        ctx = {"index": i, "candidateId": d.get("candidateId")}
        if d.get("decision") not in ALLOWED_DECISIONS:
            errors.append({"code": "INVALID_DECISION", **ctx})
            continue
        if d.get("decision") == "APPROVE":
            if d.get("proposedSemantic") == "UNKNOWN":
                errors.append({"code": "APPROVE_UNKNOWN_SEMANTIC", **ctx})
            if label_by_id:
                cand = label_by_id.get(d.get("candidateId"))
                if cand is None:
                    errors.append({"code": "UNKNOWN_CANDIDATE_ID", **ctx})
                else:
                    if cand["normalizedLabel"] != d.get("normalizedLabel"):
                        errors.append({"code": "LABEL_ID_MISMATCH", **ctx})
                    bucket = cand.get("_bucket", "")
                    if bucket == "BLOCKED_CONFLICT":
                        errors.append({"code": "APPROVE_CONFLICT", **ctx})
                    if bucket == "BLOCKED_DISAGREEMENT_ONLY":
                        errors.append({"code": "APPROVE_DISAGREEMENT_ONLY",
                                          **ctx})
                    if bucket == "BLOCKED_AMBIGUOUS_ONLY":
                        errors.append({"code": "APPROVE_AMBIGUOUS_ONLY",
                                          **ctx})
                    if bucket == "BLOCKED_UNKNOWN_SEMANTIC":
                        errors.append({"code": "APPROVE_UNKNOWN_SEMANTIC",
                                          **ctx})

    return {"ok": not errors, "errors": errors,
              "decisionCount": len(approval.get("decisions", []) or [])}


def audit_review_batch_safety() -> dict:
    """이 모듈 자체의 정적 안전성 점검 (insert/dictionary build 부재 등)."""
    src = (cs.PROJECT_ROOT
            / "scripts/hwpx/recognition_corpus/"
              "label_promotion_review_batch.py"
           ).read_text(encoding="utf-8")
    _ins = "INSERT" + " INTO "
    forbidden = {
        _ins + "human_label_decisions",
        _ins + "label_dictionary_versions",
        _ins + "label_dictionary_entries",
        "execute_writer_call_plan" + "_live_sandbox",
        "ZipFile(",
        "import " + "anthropic",
        "import " + "openai",
        "pytesseract",
    }
    # 자신의 forbidden 리터럴은 제외하고 실제 코드 라인에서만 검사
    code_lines = [ln for ln in src.splitlines()
                       if not ln.lstrip().startswith(("#", '"', "'"))]
    code = "\n".join(code_lines)
    hits = sorted(n for n in forbidden if n in code)
    return {"ok": not hits, "violations": hits}
