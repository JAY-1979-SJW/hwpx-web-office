-- HWPX Recognition Corpus DB Schema v001
-- SQLite 기반 corpus DB 초기화 스크립트

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ── 핵심 테이블 ──────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS hwpx_documents (
    document_id          TEXT PRIMARY KEY,
    source_path          TEXT NOT NULL,
    source_kind          TEXT NOT NULL DEFAULT 'unknown',
    file_size            INTEGER,
    sha256               TEXT,
    inventory_status     TEXT NOT NULL DEFAULT 'FOUND',
    first_seen_at        TEXT NOT NULL DEFAULT (datetime('now')),
    last_checked_at      TEXT
);

CREATE TABLE IF NOT EXISTS document_classifications (
    classification_id    TEXT PRIMARY KEY,
    document_id          TEXT NOT NULL REFERENCES hwpx_documents(document_id),
    document_type        TEXT NOT NULL DEFAULT 'unknown',
    confidence           REAL,
    classified_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS label_occurrences (
    occurrence_id        TEXT PRIMARY KEY,
    document_id          TEXT NOT NULL REFERENCES hwpx_documents(document_id),
    raw_label            TEXT NOT NULL,
    normalized_label     TEXT NOT NULL,
    semantic_type        TEXT NOT NULL DEFAULT 'UNKNOWN',
    table_id             TEXT,
    row_index            INTEGER,
    col_index            INTEGER,
    confidence           REAL,
    source               TEXT,
    detected_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS human_label_decisions (
    decision_id          TEXT PRIMARY KEY,
    normalized_label     TEXT NOT NULL,
    semantic_type        TEXT NOT NULL,
    decision_status      TEXT NOT NULL DEFAULT 'HELD',
    decided_by           TEXT,
    decided_at           TEXT NOT NULL DEFAULT (datetime('now')),
    notes                TEXT
);

CREATE TABLE IF NOT EXISTS label_promotion_candidates (
    candidate_id         TEXT PRIMARY KEY,
    normalized_label     TEXT NOT NULL,
    semantic_type        TEXT NOT NULL,
    occurrence_count     INTEGER NOT NULL DEFAULT 0,
    promotion_status     TEXT NOT NULL DEFAULT 'PENDING',
    evidence_doc_ids     TEXT,
    created_at           TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at           TEXT
);

CREATE TABLE IF NOT EXISTS label_dictionary_versions (
    version_id           TEXT PRIMARY KEY,
    version_tag          TEXT NOT NULL,
    entry_count          INTEGER NOT NULL DEFAULT 0,
    published_at         TEXT NOT NULL DEFAULT (datetime('now')),
    notes                TEXT
);

CREATE TABLE IF NOT EXISTS label_dictionary_entries (
    entry_id             TEXT PRIMARY KEY,
    version_id           TEXT NOT NULL REFERENCES label_dictionary_versions(version_id),
    normalized_label     TEXT NOT NULL,
    semantic_type        TEXT NOT NULL,
    added_at             TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS accuracy_audits (
    audit_id             TEXT PRIMARY KEY,
    document_id          TEXT REFERENCES hwpx_documents(document_id),
    task_name            TEXT,
    verdict              TEXT NOT NULL DEFAULT 'FAIL',
    details              TEXT,
    audited_at           TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ── 뷰 ───────────────────────────────────────────────────────────────────────

CREATE VIEW IF NOT EXISTS labels_by_frequency AS
SELECT
    normalized_label,
    semantic_type,
    COUNT(*) AS occurrence_count
FROM label_occurrences
GROUP BY normalized_label, semantic_type
ORDER BY occurrence_count DESC;

CREATE VIEW IF NOT EXISTS pending_promotion_candidates AS
SELECT *
FROM label_promotion_candidates
WHERE promotion_status = 'PENDING';

CREATE VIEW IF NOT EXISTS classification_disagreements AS
SELECT
    h1.normalized_label,
    h1.semantic_type AS type_a,
    h2.semantic_type AS type_b,
    h1.decision_status AS status_a,
    h2.decision_status AS status_b
FROM human_label_decisions h1
JOIN human_label_decisions h2
    ON h1.normalized_label = h2.normalized_label
    AND h1.semantic_type < h2.semantic_type
    AND h1.decision_status = 'APPROVED'
    AND h2.decision_status = 'APPROVED';

CREATE VIEW IF NOT EXISTS dictionary_version_summary AS
SELECT
    v.version_tag,
    v.entry_count,
    v.published_at,
    COUNT(e.entry_id) AS actual_entry_count
FROM label_dictionary_versions v
LEFT JOIN label_dictionary_entries e ON e.version_id = v.version_id
GROUP BY v.version_id;
