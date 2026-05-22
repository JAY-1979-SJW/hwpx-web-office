"""HWPX-RECOGNITION-CORPUS-DB-SCHEMA-CONTRACT-01 — schema bootstrap & helpers.

SQLite 기반 corpus DB의 schema init / validator / promotion gate helper.
production 로직(fill_review_contract / live pipeline 등)은 이 모듈을 import하지 않는다.
"""
from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

SCHEMA_VERSION = "001"

REQUIRED_TABLES: tuple[str, ...] = (
    "hwpx_documents",
    "document_classifications",
    "label_occurrences",
    "human_label_decisions",
    "label_promotion_candidates",
    "label_dictionary_versions",
    "label_dictionary_entries",
    "accuracy_audits",
)

REQUIRED_VIEWS: tuple[str, ...] = (
    "labels_by_frequency",
    "pending_promotion_candidates",
    "classification_disagreements",
    "dictionary_version_summary",
)

ALLOWED_SOURCE_KIND: frozenset[str] = frozenset({
    "collected", "repo_sample", "deliverable", "unknown",
})
ALLOWED_INVENTORY_STATUS: frozenset[str] = frozenset({
    "FOUND", "MISSING", "DUPLICATE", "ZERO_BYTE",
    "UNREADABLE", "NON_HWPX_ZIP", "BROKEN",
})
ALLOWED_DOCUMENT_TYPE: frozenset[str] = frozenset({
    "fillable_form", "reference_table", "empty_template",
    "unknown", "broken", "non_hwpx",
})
ALLOWED_SEMANTIC_TYPES: frozenset[str] = frozenset({
    "PROJECT_NAME", "CONTRACT_AMOUNT", "START_DATE", "END_DATE",
    "COMPANY_NAME", "BUSINESS_REGISTRATION_NUMBER",
    "REPRESENTATIVE_NAME", "SITE_MANAGER_NAME",
    "ADDRESS", "PHONE",
    "ATTACHMENT_DOCUMENT", "STAMP_OR_SEAL",
    "FREE_TEXT", "CHECKBOX", "YES_NO",
    "INSPECTION_ITEM", "MATERIAL_NAME",
    "QUANTITY", "UNKNOWN",
})
# UNKNOWN은 production dictionary로 승격 금지 (Gate 3 잠금)
DICTIONARY_FORBIDDEN_SEMANTICS: frozenset[str] = frozenset({"UNKNOWN"})
DICTIONARY_ALLOWED_SEMANTICS: frozenset[str] = (
    ALLOWED_SEMANTIC_TYPES - DICTIONARY_FORBIDDEN_SEMANTICS
)

ALLOWED_HUMAN_DECISION_STATUS: frozenset[str] = frozenset({
    "APPROVED", "REJECTED", "HELD",
})
ALLOWED_PROMOTION_STATUS: frozenset[str] = frozenset({
    "PENDING", "APPROVED", "REJECTED", "HELD",
    "BLOCKED_CONFLICT", "BLOCKED_LOW_EVIDENCE",
})

SCHEMA_DIR = Path(__file__).resolve().parent / "schema"
INIT_SQL_PATH = SCHEMA_DIR / "001_init.sql"


# ── DB init ──────────────────────────────────────────────────────────────────

def init_db(conn: sqlite3.Connection) -> None:
    """schema 생성 — idempotent."""
    sql = INIT_SQL_PATH.read_text(encoding="utf-8")
    conn.executescript(sql)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.commit()


def open_corpus_db(path: str | Path) -> sqlite3.Connection:
    """파일 또는 :memory: SQLite 연결 후 schema init."""
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA foreign_keys = ON")
    init_db(conn)
    return conn


# ── validation ──────────────────────────────────────────────────────────────

def validate_schema(conn: sqlite3.Connection) -> dict:
    """schema 무결성 검증. return findings dict."""
    findings: dict = {"missing_tables": [], "missing_views": [],
                          "foreign_keys_enabled": False, "ok": False}
    tables = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    views = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='view'"
    )}
    findings["missing_tables"] = [t for t in REQUIRED_TABLES if t not in tables]
    findings["missing_views"] = [v for v in REQUIRED_VIEWS if v not in views]
    fk = conn.execute("PRAGMA foreign_keys").fetchone()
    findings["foreign_keys_enabled"] = bool(fk and fk[0])
    findings["ok"] = (
        not findings["missing_tables"]
        and not findings["missing_views"]
        and findings["foreign_keys_enabled"]
    )
    return findings


def migration_checksum() -> dict:
    """현재 migration SQL의 sha256."""
    raw = INIT_SQL_PATH.read_bytes()
    return {
        "schemaVersion": SCHEMA_VERSION,
        "migrationFile": "001_init.sql",
        "sha256": hashlib.sha256(raw).hexdigest(),
        "byteSize": len(raw),
    }


# ── enum validators ─────────────────────────────────────────────────────────

def is_allowed_source_kind(v: str) -> bool:
    return v in ALLOWED_SOURCE_KIND


def is_allowed_inventory_status(v: str) -> bool:
    return v in ALLOWED_INVENTORY_STATUS


def is_allowed_document_type(v: str) -> bool:
    return v in ALLOWED_DOCUMENT_TYPE


def is_allowed_semantic_type(v: str) -> bool:
    return v in ALLOWED_SEMANTIC_TYPES


def is_dictionary_allowed_semantic(v: str) -> bool:
    """production dictionary entry로 허용되는 semantic 인지.

    UNKNOWN은 사전 entry로 승격 금지.
    """
    return v in DICTIONARY_ALLOWED_SEMANTICS


def is_allowed_human_decision_status(v: str) -> bool:
    return v in ALLOWED_HUMAN_DECISION_STATUS


def is_allowed_promotion_status(v: str) -> bool:
    return v in ALLOWED_PROMOTION_STATUS


# ── promotion gate helpers (Gate 3) ─────────────────────────────────────────

def has_human_approval(conn: sqlite3.Connection, normalized_label: str,
                          semantic_type: str) -> bool:
    """동일 (라벨, semantic)에 APPROVED human_label_decisions 1건 이상."""
    row = conn.execute(
        "SELECT COUNT(*) FROM human_label_decisions "
        "WHERE normalized_label=? AND semantic_type=? AND decision_status='APPROVED'",
        (normalized_label, semantic_type),
    ).fetchone()
    return bool(row and row[0] >= 1)


def detect_semantic_conflicts(conn: sqlite3.Connection,
                                  normalized_label: str) -> list[dict]:
    """동일 normalized_label에 충돌 (다른 semantic) APPROVED 결정 검색."""
    rows = conn.execute(
        "SELECT semantic_type, COUNT(*) FROM human_label_decisions "
        "WHERE normalized_label=? AND decision_status='APPROVED' "
        "GROUP BY semantic_type",
        (normalized_label,),
    ).fetchall()
    return [{"semantic_type": r[0], "approved_count": r[1]} for r in rows]


def can_promote_to_dictionary(conn: sqlite3.Connection,
                                  normalized_label: str,
                                  semantic_type: str) -> tuple[bool, str]:
    """승격 가능 여부 + 사유.

    return (allowed, reason)
    """
    # UNKNOWN 차단
    if not is_dictionary_allowed_semantic(semantic_type):
        return False, "BLOCKED_DICTIONARY_FORBIDDEN_SEMANTIC"
    # 사람 APPROVED 1건 이상
    if not has_human_approval(conn, normalized_label, semantic_type):
        return False, "BLOCKED_NO_HUMAN_APPROVAL"
    # 충돌 검사 — 다른 semantic에 APPROVED가 1건이라도 있으면 BLOCKED
    conflicts = detect_semantic_conflicts(conn, normalized_label)
    other = [c for c in conflicts if c["semantic_type"] != semantic_type]
    if other:
        return False, "BLOCKED_CONFLICT"
    return True, "OK"


# ── production isolation check ──────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PRODUCTION_PATHS: tuple[Path, ...] = (
    PROJECT_ROOT / "scripts/hwpx/fill_review/fill_review_contract.py",
    PROJECT_ROOT / "scripts/hwpx/fill_review/fill_review_ui_adapter.py",
    PROJECT_ROOT / "scripts/hwpx/fill_review/fill_review_live_pipeline.py",
    PROJECT_ROOT / "scripts/hwpx/fill_review/evidence_ingestion_contract.py",
    PROJECT_ROOT / "scripts/hwpx/pipeline/generic_edit_plan_writer_executor_live_sandbox.py",
    PROJECT_ROOT / "scripts/hwpx/pipeline/generic_edit_plan_contract.py",
)
PRODUCTION_FORBIDDEN_IMPORTS: tuple[str, ...] = (
    "from scripts.hwpx.recognition_corpus",
    "from hwpx.recognition_corpus",
    "import sqlite3",
    "corpus.sqlite3",
    "open_corpus_db",
)


def audit_production_isolation() -> dict:
    """production 모듈이 corpus DB / sqlite3를 import하지 않는지 grep."""
    violations: list[dict] = []
    for path in PRODUCTION_PATHS:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for needle in PRODUCTION_FORBIDDEN_IMPORTS:
            if needle in text:
                violations.append({
                    "file": str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
                    "forbidden": needle,
                })
    return {
        "violations": violations,
        "ok": len(violations) == 0,
        "filesChecked": [str(p.relative_to(PROJECT_ROOT)).replace("\\", "/")
                            for p in PRODUCTION_PATHS if p.is_file()],
    }


def audit_gitignore_for_corpus() -> dict:
    """corpus.sqlite3 / exports가 gitignore에 있는지 확인."""
    gi = PROJECT_ROOT / ".gitignore"
    if not gi.is_file():
        return {"ok": False, "reason": "gitignore not found"}
    text = gi.read_text(encoding="utf-8", errors="ignore")
    must_have = (
        "data/recognition_corpus/*.sqlite3",
        "data/recognition_corpus/exports/",
    )
    missing = [p for p in must_have if p not in text]
    return {"ok": len(missing) == 0, "missing": missing}
