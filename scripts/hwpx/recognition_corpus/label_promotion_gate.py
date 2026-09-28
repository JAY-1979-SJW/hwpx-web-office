"""HWPX-RECOGNITION-LABEL-DICTIONARY-PROMOTION-GATE-01.

Gate 3: PENDING 라벨 후보를 사람 승인 + 충돌 검사 + UNKNOWN 차단 +
disagreement/ambiguous 제외 정책 하에 production 사전 후보로 승격.

production fill_review 로직은 이 모듈을 import하지 않는다.
실제 production 사전 파일 자동 수정 금지 — JSON snapshot export만 수행.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from scripts.hwpx.recognition_corpus import corpus_schema as cs

ENGINE_VERSION = "promotion-gate-deterministic-v1"
SCHEMA_VERSION = "promotion_decision_result_v1"
SNAPSHOT_SCHEMA_VERSION = "label_dictionary_snapshot_v1"

EVIDENCE_SCORE_MIN = 0.3


# ── core evaluation ──────────────────────────────────────────────────────


def _human_decisions(conn: sqlite3.Connection, normalized_label: str) -> list[dict]:
    rows = conn.execute(
        "SELECT semantic_type, decision_status, decided_by "
        "  FROM human_label_decisions WHERE normalized_label=?",
        (normalized_label,),
    ).fetchall()
    return [
        {"semantic_type": r[0], "decision_status": r[1], "decided_by": r[2] if len(r) > 2 else None}
        for r in rows
    ]


def _document_ids_for_label(conn: sqlite3.Connection, normalized_label: str) -> set[str]:
    rows = conn.execute(
        "SELECT DISTINCT document_id FROM label_occurrences WHERE normalized_label=?",
        (normalized_label,),
    ).fetchall()
    return {r[0] for r in rows}


@dataclass
class _CandidateContext:
    label: str
    semantic: str
    occ: int
    docs: int
    score: float
    request_id: str


@dataclass
class _PromotionCounts:
    human_approval: int = 0
    conflict: int = 0
    disagreement: int = 0
    ambiguous: int = 0


def evaluate_promotion_candidate(
    conn: sqlite3.Connection,
    candidate: dict,
    *,
    tainted_document_ids: set[str] | None = None,
    request_id: str = "",
) -> dict:
    """단일 후보 평가. candidate dict 필수 키:
    normalized_label, proposed_semantic, occurrence_count,
    document_count, evidence_score.

    tainted_document_ids: disagreement/ambiguous 분류로 인해
    근거가 신뢰 불가한 document_id 집합.
    """
    ctx = _CandidateContext(
        label=candidate["normalized_label"],
        semantic=candidate["proposed_semantic"],
        occ=int(candidate.get("occurrence_count", 0)),
        docs=int(candidate.get("document_count", 0)),
        score=float(candidate.get("evidence_score", 0.0)),
        request_id=request_id,
    )

    warnings: list[str] = []

    # 1) semantic validity
    if not cs.is_allowed_semantic_type(ctx.semantic):
        return _result(
            ctx,
            "BLOCKED_INVALID_SEMANTIC",
            False,
            "INVALID_SEMANTIC_TYPE",
            _PromotionCounts(),
            warnings + ["INVALID_SEMANTIC_TYPE"],
        )
    if ctx.semantic == "UNKNOWN":
        return _result(
            ctx,
            "BLOCKED_UNKNOWN_SEMANTIC",
            False,
            "UNKNOWN_SEMANTIC_FORBIDDEN",
            _PromotionCounts(),
            warnings + ["UNKNOWN_SEMANTIC_FORBIDDEN"],
        )

    decisions = _human_decisions(conn, ctx.label)
    approved = [
        d
        for d in decisions
        if d["decision_status"] == "APPROVED"
        and d["semantic_type"] == ctx.semantic
        and (d.get("decided_by") or "")
    ]
    rejected_same = [
        d
        for d in decisions
        if d["decision_status"] == "REJECTED" and d["semantic_type"] == ctx.semantic
    ]
    other_approved = [
        d
        for d in decisions
        if d["decision_status"] == "APPROVED" and d["semantic_type"] != ctx.semantic
    ]

    # 2) no human approval
    if not approved:
        return _result(
            ctx,
            "BLOCKED_NO_HUMAN_APPROVAL",
            False,
            "NO_HUMAN_APPROVAL",
            _PromotionCounts(conflict=len(other_approved)),
            warnings + ["NO_HUMAN_APPROVAL"],
        )

    # 3) semantic conflict (다른 semantic APPROVED 존재)
    if other_approved:
        return _result(
            ctx,
            "BLOCKED_CONFLICT",
            False,
            "CONFLICTING_SEMANTIC_DECISIONS",
            _PromotionCounts(human_approval=len(approved), conflict=len(other_approved)),
            warnings + ["CONFLICTING_SEMANTIC_DECISIONS"],
        )

    # 4) REJECTED for same semantic → block as conflict (HELD)
    if rejected_same:
        warnings.append("HAS_REJECTED_FOR_SAME_SEMANTIC")
        return _result(
            ctx,
            "BLOCKED_CONFLICT",
            False,
            "CONFLICTING_SEMANTIC_DECISIONS",
            _PromotionCounts(human_approval=len(approved), conflict=len(rejected_same)),
            warnings,
        )

    # 5) disagreement/ambiguous taint — 모든 evidence가 tainted면 block
    disagreement_count = 0
    ambiguous_count = 0
    if tainted_document_ids is not None:
        doc_ids = _document_ids_for_label(conn, ctx.label)
        if doc_ids:
            tainted = doc_ids & tainted_document_ids
            clean = doc_ids - tainted
            disagreement_count = len(tainted)
            if not clean:
                # 전부 tainted
                return _result(
                    ctx,
                    "BLOCKED_DISAGREEMENT_ONLY",
                    False,
                    "DISAGREEMENT_REQUIRES_REVIEW",
                    _PromotionCounts(human_approval=len(approved), disagreement=disagreement_count),
                    warnings + ["DISAGREEMENT_REQUIRES_REVIEW"],
                )

    # 6) low evidence
    if ctx.score < EVIDENCE_SCORE_MIN or ctx.occ < 3 or ctx.docs < 2:
        return _result(
            ctx,
            "BLOCKED_LOW_EVIDENCE",
            False,
            "LOW_EVIDENCE_SCORE",
            _PromotionCounts(
                human_approval=len(approved),
                disagreement=disagreement_count,
                ambiguous=ambiguous_count,
            ),
            warnings + ["LOW_EVIDENCE_SCORE"],
        )

    # ✅ allowed
    return _result(
        ctx,
        "PROMOTION_ALLOWED",
        True,
        None,
        _PromotionCounts(
            human_approval=len(approved),
            disagreement=disagreement_count,
            ambiguous=ambiguous_count,
        ),
        warnings,
    )


def _result(
    ctx: _CandidateContext,
    status: str,
    allowed: bool,
    reason: str | None,
    counts: _PromotionCounts,
    warnings: list[str],
) -> dict:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "engineVersion": ENGINE_VERSION,
        "requestId": ctx.request_id,
        "normalizedLabel": ctx.label,
        "proposedSemantic": ctx.semantic,
        "status": status,
        "allowed": allowed,
        "blockedReason": reason,
        "occurrenceCount": ctx.occ,
        "documentCount": ctx.docs,
        "evidenceScore": ctx.score,
        "humanApprovalCount": counts.human_approval,
        "conflictCount": counts.conflict,
        "disagreementCount": counts.disagreement,
        "ambiguousCount": counts.ambiguous,
        "warnings": warnings,
    }


def evaluate_all_promotion_candidates(
    conn: sqlite3.Connection,
    *,
    statuses: tuple[str, ...] = ("PENDING",),
    tainted_document_ids: set[str] | None = None,
) -> list[dict]:
    placeholders = ",".join("?" * len(statuses))
    rows = conn.execute(
        f"SELECT normalized_label, proposed_semantic, occurrence_count,"
        f"  document_count, evidence_score "
        f"  FROM label_promotion_candidates WHERE status IN ({placeholders})",
        statuses,
    ).fetchall()
    out: list[dict] = []
    for i, r in enumerate(rows):
        cand = {
            "normalized_label": r[0],
            "proposed_semantic": r[1],
            "occurrence_count": r[2],
            "document_count": r[3],
            "evidence_score": r[4],
        }
        out.append(
            evaluate_promotion_candidate(
                conn,
                cand,
                tainted_document_ids=tainted_document_ids,
                request_id=f"batch-{i}",
            )
        )
    return out


def detect_promotion_conflicts(conn: sqlite3.Connection, normalized_label: str) -> list[dict]:
    return cs.detect_semantic_conflicts(conn, normalized_label)


def filter_disagreement_or_ambiguous_candidates(results: Iterable[dict]) -> list[dict]:
    return [
        r for r in results if r["status"] in ("BLOCKED_DISAGREEMENT_ONLY", "BLOCKED_AMBIGUOUS_ONLY")
    ]


# ── dictionary version build ────────────────────────────────────────────


def build_dictionary_version(  # ruff: ignore[too-many-arguments] (여러 파일에서 호출 — 시그니처 변경 보류)
    conn: sqlite3.Connection,
    version: str,
    results: Iterable[dict],
    *,
    approved_by: str,
    source_corpus_sha: str,
    classifier_version: str = "content_classifier_v1",
    built_at: str = "",
) -> dict:
    """PROMOTION_ALLOWED 결과만 entry로 삽입. UNKNOWN은 schema CHECK가 차단."""
    if not approved_by:
        raise ValueError("approved_by must be non-empty")
    allowed = [r for r in results if r.get("allowed")]
    blocked = [r for r in results if not r.get("allowed")]

    built_at = built_at or "build-now"
    conn.execute(
        "INSERT INTO label_dictionary_versions "
        "(version, built_at, entry_count, source_corpus_sha, approved_by) "
        "VALUES (?, ?, ?, ?, ?)",
        (version, built_at, len(allowed), source_corpus_sha, approved_by),
    )
    for r in allowed:
        if r["proposedSemantic"] == "UNKNOWN":
            raise ValueError("UNKNOWN semantic must not appear in entries")
        conn.execute(
            "INSERT INTO label_dictionary_entries "
            "(version, normalized_label, semantic_type) VALUES (?, ?, ?)",
            (version, r["normalizedLabel"], r["proposedSemantic"]),
        )
    conn.commit()

    return {
        "version": version,
        "builtAt": built_at,
        "entryCount": len(allowed),
        "blockedCount": len(blocked),
        "sourceCorpusSha": source_corpus_sha,
        "classifierVersion": classifier_version,
        "approvedBy": approved_by,
    }


# ── snapshot export / validate ───────────────────────────────────────────

ALLOWED_EXPORT_ROOTS_REL = ("data/recognition_corpus/exports",)


def _under_allowed_root(out_path: Path) -> bool:
    p = out_path.resolve()
    s = str(p).replace("\\", "/")
    if "/exports/" in s and "data/recognition_corpus/exports" in s:
        return True
    # tmp directory (pytest tmp_path)
    if "/tmp/" in s.lower() or "\\temp\\" in s.lower():
        return True
    # explicit pytest tmp prefix
    for kw in ("pytest-of-", "/tmp/", "appdata/local/temp"):
        if kw in s.lower():
            return True
    return False


def export_dictionary_snapshot(
    conn: sqlite3.Connection,
    version: str,
    out_path: Path,
    *,
    classifier_version: str = "content_classifier_v1",
    results: Iterable[dict] | None = None,
) -> dict:
    """version에 해당하는 dictionary_entries를 JSON snapshot으로 저장."""
    out_path = Path(out_path)
    if not _under_allowed_root(out_path):
        raise PermissionError(f"export path must be under exports/ or tmp/: {out_path}")
    v = conn.execute(
        "SELECT built_at, entry_count, source_corpus_sha, approved_by "
        "  FROM label_dictionary_versions WHERE version=?",
        (version,),
    ).fetchone()
    if not v:
        raise ValueError(f"unknown dictionary version: {version}")
    rows = conn.execute(
        "SELECT normalized_label, semantic_type "
        "  FROM label_dictionary_entries WHERE version=? "
        "  ORDER BY normalized_label",
        (version,),
    ).fetchall()

    blocked = []
    if results is not None:
        blocked = [
            {
                "normalizedLabel": r["normalizedLabel"],
                "proposedSemantic": r["proposedSemantic"],
                "status": r["status"],
                "blockedReason": r["blockedReason"],
            }
            for r in results
            if not r.get("allowed")
        ]

    snapshot = {
        "schemaVersion": SNAPSHOT_SCHEMA_VERSION,
        "dictionaryVersion": version,
        "builtAt": v[0],
        "sourceCorpusSha": v[2],
        "classifierVersion": classifier_version,
        "entryCount": len(rows),
        "entries": [
            {
                "normalizedLabel": r[0],
                "semanticType": r[1],
                "sourceEvidence": "corpus_v1",
                "approvedBy": v[3],
                "approvedAt": v[0],
                "occurrenceCount": 0,
                "documentCount": 0,
            }
            for r in rows
        ],
        "blockedCandidates": blocked,
        "warnings": [],
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return snapshot


def validate_dictionary_snapshot(snapshot: dict) -> dict:
    must = (
        "schemaVersion",
        "dictionaryVersion",
        "builtAt",
        "sourceCorpusSha",
        "classifierVersion",
        "entryCount",
        "entries",
        "blockedCandidates",
        "warnings",
    )
    missing = [k for k in must if k not in snapshot]
    invalid_unknown = [e for e in snapshot.get("entries", []) if e.get("semanticType") == "UNKNOWN"]
    entry_required = (
        "normalizedLabel",
        "semanticType",
        "sourceEvidence",
        "approvedBy",
        "approvedAt",
        "occurrenceCount",
        "documentCount",
    )
    bad_entries = [
        e for e in snapshot.get("entries", []) if any(k not in e for k in entry_required)
    ]
    count_match = snapshot.get("entryCount", -1) == len(snapshot.get("entries", []))
    ok = not missing and not invalid_unknown and not bad_entries and count_match
    return {
        "ok": ok,
        "missing": missing,
        "invalidUnknownEntries": invalid_unknown,
        "badEntries": bad_entries,
        "entryCountMatches": count_match,
    }


# ── version compare ─────────────────────────────────────────────────────


def compare_dictionary_versions(conn: sqlite3.Connection, version_a: str, version_b: str) -> dict:
    a = dict(
        conn.execute(
            "SELECT normalized_label, semantic_type "
            "  FROM label_dictionary_entries WHERE version=?",
            (version_a,),
        ).fetchall()
    )
    b = dict(
        conn.execute(
            "SELECT normalized_label, semantic_type "
            "  FROM label_dictionary_entries WHERE version=?",
            (version_b,),
        ).fetchall()
    )
    added = sorted(set(b) - set(a))
    removed = sorted(set(a) - set(b))
    changed = sorted({k for k in (set(a) & set(b)) if a[k] != b[k]})
    return {
        "versionA": version_a,
        "versionB": version_b,
        "entryCountA": len(a),
        "entryCountB": len(b),
        "addedLabels": added,
        "removedLabels": removed,
        "semanticChangedLabels": [{"label": k, "from": a[k], "to": b[k]} for k in changed],
    }


# ── production isolation extra ──────────────────────────────────────────

PROD_SNAPSHOT_FORBIDDEN_IMPORTS = (
    "from scripts.hwpx.recognition_corpus",
    "from hwpx.recognition_corpus",
    "label_promotion_gate",
    "open_corpus_db",
    "corpus.sqlite3",
)


def audit_production_snapshot_isolation() -> dict:
    """production fill_review 모듈이 promotion_gate/DB를 import하지 않는지."""
    violations: list[dict] = []
    for p in cs.PRODUCTION_PATHS:
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        for n in PROD_SNAPSHOT_FORBIDDEN_IMPORTS:
            if n in text:
                violations.append({
                    "file": str(p.relative_to(cs.PROJECT_ROOT)).replace("\\", "/"),
                    "forbidden": n,
                })
    return {"ok": not violations, "violations": violations}
