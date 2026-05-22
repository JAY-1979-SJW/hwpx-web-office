"""HWPX-FILL-REVIEW-AUDIT-AND-LEARNING-LOG-CONTRACT-01.

HWPX 작성 검수 세션의 감사 로그 + 학습 로그 contract.

이 모듈은 production 모듈 (fill_review_contract, live_pipeline, writer,
ui_adapter, evidence_ingestion_contract)에서 import되어서는 안 된다.
로그 저장은 별도 orchestration 계층에서만 수행한다.
"""
from __future__ import annotations

import hashlib
import re
import sqlite3
from pathlib import Path

SCHEMA_VERSION = "002"

REQUIRED_LOG_TABLES: tuple[str, ...] = (
    "fill_review_sessions",
    "fill_review_decision_logs",
    "fill_review_writer_operation_logs",
    "fill_review_readback_logs",
    "fill_review_learning_signals",
    "xml_deep_analyzer_need_flags",
)

REQUIRED_LOG_VIEWS: tuple[str, ...] = (
    "reusable_learning_signals",
    "failed_writer_patterns",
    "xml_deep_analyzer_backlog",
    "decision_summary_by_label",
    "learning_signal_summary_by_doc_type",
)

ALLOWED_SESSION_STATUS: frozenset[str] = frozenset({
    "REVIEW_STARTED", "READY_FOR_DECISION", "DECISION_VALIDATED",
    "WRITER_APPLIED", "WRITER_BLOCKED", "READBACK_FAILED",
    "COMPLETED", "CANCELLED", "ERROR",
})
ALLOWED_DECISION: frozenset[str] = frozenset({
    "APPROVE", "REJECT", "HOLD", "EDIT_VALUE",
    "REQUEST_MATERIAL", "SYSTEM_APPROVE", "SYSTEM_HOLD",
})
ALLOWED_DECISION_SOURCE: frozenset[str] = frozenset({
    "USER", "SYSTEM_POLICY", "AI_ASSISTED", "TEST_FIXTURE",
})
ALLOWED_OPERATION_TYPE: frozenset[str] = frozenset({
    "setCellText", "setParagraphText", "replaceTextRun",
    "setCellHorizontalAlign", "setCellVerticalAlign",
})
FORBIDDEN_OPERATION_TYPE: frozenset[str] = frozenset({
    "setCellParagraphText",
})
ALLOWED_OPERATION_STATUS: frozenset[str] = frozenset({
    "CREATED", "BLOCKED", "APPLIED", "SKIPPED",
})
ALLOWED_READBACK_STATUS: frozenset[str] = frozenset({
    "MATCHED", "MISMATCH", "NOT_RUN", "BLOCKED",
})
ALLOWED_REASON_CODE: frozenset[str] = frozenset({
    "RUN_BOUNDARY_UNSUPPORTED", "CHECKBOX_OR_SHAPE_NEEDED",
    "OBJECT_ANCHOR_NEEDED", "STYLE_RESOLUTION_NEEDED",
    "CELL_INTERNAL_PARAGRAPH_NEEDED", "MERGED_CELL_GEOMETRY_NEEDED",
    "READBACK_MISMATCH", "TARGET_AMBIGUOUS",
    "LABEL_CONTEXT_INSUFFICIENT",
})
ALLOWED_SEVERITY: frozenset[str] = frozenset({"LOW", "MEDIUM", "HIGH"})

REUSABLE_DECISIONS: frozenset[str] = frozenset({
    "APPROVE", "EDIT_VALUE", "SYSTEM_APPROVE",
})

# 개인정보 가능성 패턴 (raw 저장 금지)
_BIZNO_RE = re.compile(r"\b\d{3}-\d{2}-\d{5}\b")
_PHONE_RE = re.compile(r"\b01[016789][-\s]?\d{3,4}[-\s]?\d{4}\b")
_RRN_RE = re.compile(r"\b\d{6}-?\d{7}\b")

SCHEMA_DIR = Path(__file__).resolve().parents[3] / "data/recognition_corpus/schema"
MIGRATION_002_PATH = SCHEMA_DIR / "002_audit_learning_logs.sql"


# ── schema init ─────────────────────────────────────────────────────────────

def init_audit_learning_log_schema(conn: sqlite3.Connection) -> None:
    """Migration 002 적용 — idempotent. 001이 이미 적용되어 있어야 한다."""
    sql = MIGRATION_002_PATH.read_text(encoding="utf-8")
    conn.executescript(sql)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.commit()


def validate_log_schema(conn: sqlite3.Connection) -> dict:
    tables = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    views = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='view'"
    )}
    missing_t = [t for t in REQUIRED_LOG_TABLES if t not in tables]
    missing_v = [v for v in REQUIRED_LOG_VIEWS if v not in views]
    return {
        "missing_tables": missing_t,
        "missing_views": missing_v,
        "ok": not missing_t and not missing_v,
    }


# ── hash / redaction ────────────────────────────────────────────────────────

def hash_value(v: str | None) -> str | None:
    if v is None:
        return None
    return hashlib.sha256(v.encode("utf-8")).hexdigest()


def redact_or_hash_value(v: str | None, *, preview_max: int = 20) -> dict:
    """raw 저장 금지. hash + (선택) redactedPreview 반환.

    preview는 20자 초과 금지. 개인정보 패턴은 preview에서도 마스킹.
    """
    if v is None:
        return {"valueHash": None, "redactedPreview": None}
    h = hash_value(v)
    preview = v[:preview_max]
    preview = _BIZNO_RE.sub("[REDACTED-BIZ]", preview)
    preview = _PHONE_RE.sub("[REDACTED-PHONE]", preview)
    preview = _RRN_RE.sub("[REDACTED-RRN]", preview)
    if len(preview) > preview_max:
        preview = preview[:preview_max]
    return {"valueHash": h, "redactedPreview": preview}


def validate_no_sensitive_raw_values(record: dict) -> None:
    """record 내 raw 값이 sensitive pattern이거나 _value (hash 아님) 키가
    raw로 저장되려 하면 ValueError.
    """
    forbidden_keys = (
        "proposed_value", "edited_value",
        "expected_before", "actual_after",
        "current_value",
    )
    for k in forbidden_keys:
        if k in record:
            raise ValueError(
                f"raw value forbidden: key '{k}' must be hashed "
                f"(use '{k}_hash')"
            )
    for k, v in record.items():
        if not isinstance(v, str):
            continue
        if k.endswith("_hash"):
            continue
        if k in ("redacted_preview", "redactedPreview"):
            if len(v) > 20:
                raise ValueError(
                    f"redactedPreview too long ({len(v)} > 20)"
                )
            continue
        if _BIZNO_RE.search(v) or _PHONE_RE.search(v) or _RRN_RE.search(v):
            raise ValueError(
                f"sensitive value pattern detected in field '{k}'"
            )


# ── builders ────────────────────────────────────────────────────────────────

def build_fill_review_session_log(
    *,
    session_id: str,
    document_id: str,
    source_document_hash: str,
    started_at: str,
    session_status: str = "REVIEW_STARTED",
    document_type: str | None = None,
    sub_type: str | None = None,
    classifier_version: str | None = None,
    dictionary_version: str | None = None,
    completed_at: str | None = None,
    created_by: str | None = None,
    notes: str | None = None,
) -> dict:
    if session_status not in ALLOWED_SESSION_STATUS:
        raise ValueError(f"invalid session_status: {session_status}")
    rec = {
        "session_id": session_id,
        "document_id": document_id,
        "source_document_hash": source_document_hash,
        "document_type": document_type,
        "sub_type": sub_type,
        "classifier_version": classifier_version,
        "dictionary_version": dictionary_version,
        "started_at": started_at,
        "completed_at": completed_at,
        "session_status": session_status,
        "created_by": created_by,
        "notes": notes,
    }
    return rec


def insert_session(conn: sqlite3.Connection, rec: dict) -> None:
    conn.execute(
        "INSERT INTO fill_review_sessions ("
        "session_id, document_id, source_document_hash, document_type,"
        " sub_type, classifier_version, dictionary_version,"
        " started_at, completed_at, session_status, created_by, notes"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (rec["session_id"], rec["document_id"], rec["source_document_hash"],
         rec["document_type"], rec["sub_type"], rec["classifier_version"],
         rec["dictionary_version"], rec["started_at"], rec["completed_at"],
         rec["session_status"], rec["created_by"], rec["notes"]),
    )


def build_decision_log_records(decisions: list[dict]) -> list[dict]:
    out: list[dict] = []
    for d in decisions:
        validate_no_sensitive_raw_values(d)
        if d["decision"] not in ALLOWED_DECISION:
            raise ValueError(f"invalid decision: {d['decision']}")
        if d["decision_source"] not in ALLOWED_DECISION_SOURCE:
            raise ValueError(f"invalid decision_source: {d['decision_source']}")
        out.append(d)
    return out


def insert_decision(conn: sqlite3.Connection, d: dict) -> int:
    cur = conn.execute(
        "INSERT INTO fill_review_decision_logs ("
        "session_id, review_item_id, requirement_id, normalized_label,"
        " semantic_type, target_type, target_key,"
        " current_value_hash, proposed_value_hash, edited_value_hash,"
        " decision, decision_source, decided_by, decided_at,"
        " evidence_refs_json, reason, risk_flags_json"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (d["session_id"], d["review_item_id"], d.get("requirement_id"),
         d.get("normalized_label"), d.get("semantic_type"),
         d.get("target_type"), d.get("target_key"),
         d.get("current_value_hash"), d.get("proposed_value_hash"),
         d.get("edited_value_hash"),
         d["decision"], d["decision_source"],
         d.get("decided_by"), d["decided_at"],
         d.get("evidence_refs_json"), d.get("reason"),
         d.get("risk_flags_json")),
    )
    return cur.lastrowid


def build_writer_operation_log_records(ops: list[dict]) -> list[dict]:
    out: list[dict] = []
    for op in ops:
        validate_no_sensitive_raw_values(op)
        if op["operation_type"] in FORBIDDEN_OPERATION_TYPE:
            raise ValueError(
                f"forbidden operation_type: {op['operation_type']}"
            )
        if op["operation_type"] not in ALLOWED_OPERATION_TYPE:
            raise ValueError(f"invalid operation_type: {op['operation_type']}")
        if op["operation_status"] not in ALLOWED_OPERATION_STATUS:
            raise ValueError(
                f"invalid operation_status: {op['operation_status']}"
            )
        if not op.get("expected_before_hash"):
            raise ValueError("expected_before_hash required")
        out.append(op)
    return out


def insert_writer_operation(conn: sqlite3.Connection, op: dict) -> int:
    cur = conn.execute(
        "INSERT INTO fill_review_writer_operation_logs ("
        "session_id, decision_log_id, operation_type, writer_method,"
        " target_type, target_key, expected_before_hash, value_hash,"
        " operation_status, blocked_reason, created_at"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (op["session_id"], op.get("decision_log_id"),
         op["operation_type"], op.get("writer_method"),
         op["target_type"], op["target_key"],
         op["expected_before_hash"], op.get("value_hash"),
         op["operation_status"], op.get("blocked_reason"),
         op["created_at"]),
    )
    return cur.lastrowid


def build_readback_log_records(reads: list[dict]) -> list[dict]:
    out: list[dict] = []
    for r in reads:
        validate_no_sensitive_raw_values(r)
        if r["readback_status"] not in ALLOWED_READBACK_STATUS:
            raise ValueError(
                f"invalid readback_status: {r['readback_status']}"
            )
        out.append(r)
    return out


def insert_readback(conn: sqlite3.Connection, r: dict) -> int:
    cur = conn.execute(
        "INSERT INTO fill_review_readback_logs ("
        "session_id, operation_log_id, readback_status,"
        " expected_after_hash, actual_after_hash,"
        " divergence_code, divergence_summary, checked_at"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (r["session_id"], r.get("operation_log_id"),
         r["readback_status"], r.get("expected_after_hash"),
         r.get("actual_after_hash"), r.get("divergence_code"),
         r.get("divergence_summary"), r["checked_at"]),
    )
    return cur.lastrowid


# ── learning signal derivation ─────────────────────────────────────────────

def _is_reusable(
    *,
    decision: str,
    decision_source: str,
    writer_status: str,
    readback_status: str,
    semantic_type: str | None,
    target_key: str | None,
    normalized_label: str | None,
    has_conflict: bool,
) -> tuple[bool, str | None]:
    if decision not in REUSABLE_DECISIONS:
        return False, f"DECISION_NOT_REUSABLE:{decision}"
    if writer_status != "APPLIED":
        return False, f"WRITER_NOT_APPLIED:{writer_status}"
    if readback_status != "MATCHED":
        return False, f"READBACK_NOT_MATCHED:{readback_status}"
    if not normalized_label:
        return False, "NO_NORMALIZED_LABEL"
    if not semantic_type or semantic_type == "UNKNOWN":
        return False, "SEMANTIC_UNKNOWN_OR_MISSING"
    if not target_key:
        return False, "NO_TARGET_KEY"
    if has_conflict:
        return False, "SEMANTIC_CONFLICT"
    return True, None


def build_learning_signal_records(signals: list[dict]) -> list[dict]:
    """입력 dict는 session+decision+writer+readback flow를 평탄화한 것.

    필수 키:
      session_id, document_id, document_type, sub_type,
      normalized_label, semantic_type, target_type, target_pattern,
      decision, decision_source,
      writer_status, readback_status,
      target_key,
    선택: evidence_type, promotion_candidate_id, has_conflict, signal_score
    """
    out: list[dict] = []
    for s in signals:
        validate_no_sensitive_raw_values(s)
        reusable, blocked = _is_reusable(
            decision=s["decision"],
            decision_source=s["decision_source"],
            writer_status=s.get("writer_status", "NOT_RUN"),
            readback_status=s.get("readback_status", "NOT_RUN"),
            semantic_type=s.get("semantic_type"),
            target_key=s.get("target_key"),
            normalized_label=s.get("normalized_label"),
            has_conflict=bool(s.get("has_conflict", False)),
        )
        score = float(s.get("signal_score", 0.9 if reusable else 0.1))
        if score < 0.0:
            score = 0.0
        if score > 1.0:
            score = 1.0
        out.append({
            "session_id": s["session_id"],
            "document_id": s["document_id"],
            "document_type": s.get("document_type"),
            "sub_type": s.get("sub_type"),
            "normalized_label": s["normalized_label"],
            "semantic_type": s.get("semantic_type") or "UNKNOWN",
            "target_type": s["target_type"],
            "target_pattern": s["target_pattern"],
            "evidence_type": s.get("evidence_type"),
            "decision_source": s["decision_source"],
            "writer_success": 1 if s.get("writer_status") == "APPLIED" else 0,
            "readback_success": 1 if s.get("readback_status") == "MATCHED" else 0,
            "reusable": 1 if reusable else 0,
            "promotion_candidate_id": s.get("promotion_candidate_id"),
            "blocked_reason": blocked,
            "signal_score": score,
            "created_at": s["created_at"],
        })
    return out


def insert_learning_signal(conn: sqlite3.Connection, r: dict) -> int:
    cur = conn.execute(
        "INSERT INTO fill_review_learning_signals ("
        "session_id, document_id, document_type, sub_type,"
        " normalized_label, semantic_type, target_type, target_pattern,"
        " evidence_type, decision_source, writer_success, readback_success,"
        " reusable, promotion_candidate_id, blocked_reason,"
        " signal_score, created_at"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (r["session_id"], r["document_id"], r["document_type"], r["sub_type"],
         r["normalized_label"], r["semantic_type"], r["target_type"],
         r["target_pattern"], r["evidence_type"], r["decision_source"],
         r["writer_success"], r["readback_success"],
         r["reusable"], r["promotion_candidate_id"], r["blocked_reason"],
         r["signal_score"], r["created_at"]),
    )
    return cur.lastrowid


# ── XML deep analyzer backlog ──────────────────────────────────────────────

def build_xml_deep_analyzer_need_flags(flags: list[dict]) -> list[dict]:
    out: list[dict] = []
    for f in flags:
        if f["reason_code"] not in ALLOWED_REASON_CODE:
            raise ValueError(f"invalid reason_code: {f['reason_code']}")
        if f["severity"] not in ALLOWED_SEVERITY:
            raise ValueError(f"invalid severity: {f['severity']}")
        out.append(f)
    return out


def insert_xml_backlog(conn: sqlite3.Connection, f: dict) -> int:
    cur = conn.execute(
        "INSERT INTO xml_deep_analyzer_need_flags ("
        "session_id, document_id, reason_code, target_key,"
        " normalized_label, context_json, severity, created_at"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (f.get("session_id"), f["document_id"], f["reason_code"],
         f.get("target_key"), f.get("normalized_label"),
         f.get("context_json"), f["severity"], f["created_at"]),
    )
    return cur.lastrowid


# ── summaries ──────────────────────────────────────────────────────────────

def summarize_learning_signals(conn: sqlite3.Connection) -> dict:
    rows = conn.execute(
        "SELECT COUNT(*), SUM(reusable),"
        " AVG(signal_score) FROM fill_review_learning_signals"
    ).fetchone()
    total = rows[0] or 0
    reusable = rows[1] or 0
    avg = rows[2] if rows[2] is not None else 0.0
    return {
        "totalSignals": total,
        "reusableCount": reusable,
        "reusableRatio": (reusable / total) if total else 0.0,
        "avgSignalScore": float(avg),
    }


def summarize_xml_deep_analyzer_backlog(conn: sqlite3.Connection) -> dict:
    rows = conn.execute(
        "SELECT reason_code, severity, COUNT(*) "
        "FROM xml_deep_analyzer_need_flags "
        "GROUP BY reason_code, severity"
    ).fetchall()
    by_reason: dict = {}
    total = 0
    for code, sev, cnt in rows:
        by_reason.setdefault(code, {})[sev] = cnt
        total += cnt
    return {"totalFlags": total, "byReasonCode": by_reason}


# ── production isolation ───────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PRODUCTION_PATHS_FOR_LOG_CONTRACT: tuple[Path, ...] = (
    PROJECT_ROOT / "scripts/hwpx/fill_review/fill_review_contract.py",
    PROJECT_ROOT / "scripts/hwpx/fill_review/fill_review_ui_adapter.py",
    PROJECT_ROOT / "scripts/hwpx/fill_review/fill_review_live_pipeline.py",
    PROJECT_ROOT / "scripts/hwpx/fill_review/evidence_ingestion_contract.py",
)
FORBIDDEN_LOG_IMPORTS: tuple[str, ...] = (
    "audit_learning_log_contract",
    "fill_review_learning_signals",
    "fill_review_decision_logs",
    "xml_deep_analyzer_need_flags",
)


def audit_log_contract_isolation() -> dict:
    violations: list[dict] = []
    checked: list[str] = []
    for path in PRODUCTION_PATHS_FOR_LOG_CONTRACT:
        if not path.is_file():
            continue
        checked.append(str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"))
        text = path.read_text(encoding="utf-8", errors="ignore")
        for needle in FORBIDDEN_LOG_IMPORTS:
            if needle in text:
                violations.append({
                    "file": str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
                    "forbidden": needle,
                })
    return {"violations": violations, "ok": not violations,
              "filesChecked": checked}


def migration_002_checksum() -> dict:
    raw = MIGRATION_002_PATH.read_bytes()
    return {
        "schemaVersion": SCHEMA_VERSION,
        "migrationFile": "002_audit_learning_logs.sql",
        "sha256": hashlib.sha256(raw).hexdigest(),
        "byteSize": len(raw),
    }
