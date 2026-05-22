-- HWPX Recognition Corpus DB Migration 002
-- fill_review audit/learning log 테이블 추가

PRAGMA foreign_keys = ON;

-- ── fill_review 세션 ──────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS fill_review_sessions (
    session_id           TEXT PRIMARY KEY,
    document_id          TEXT,
    source_document_hash TEXT,
    document_type        TEXT,
    sub_type             TEXT,
    classifier_version   TEXT,
    dictionary_version   TEXT,
    started_at           TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at         TEXT,
    session_status       TEXT NOT NULL DEFAULT 'REVIEW_STARTED',
    created_by           TEXT,
    notes                TEXT
);

-- ── 검토 결정 로그 ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS fill_review_decision_logs (
    log_id               INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id           TEXT NOT NULL REFERENCES fill_review_sessions(session_id),
    review_item_id       TEXT,
    requirement_id       TEXT,
    normalized_label     TEXT,
    semantic_type        TEXT,
    target_type          TEXT,
    target_key           TEXT,
    proposed_value       TEXT,
    decision_status      TEXT NOT NULL DEFAULT 'HELD',
    confidence           REAL,
    reviewer             TEXT,
    decided_at           TEXT NOT NULL DEFAULT (datetime('now')),
    notes                TEXT
);

-- ── 쓰기 오퍼레이션 로그 ──────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS fill_review_writer_operation_logs (
    op_log_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id           TEXT NOT NULL REFERENCES fill_review_sessions(session_id),
    operation_type       TEXT NOT NULL,
    target_table_id      TEXT,
    target_row           INTEGER,
    target_col           INTEGER,
    value_before         TEXT,
    value_after          TEXT,
    verdict              TEXT NOT NULL DEFAULT 'PASS',
    executed_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ── readback 로그 ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS fill_review_readback_logs (
    readback_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id           TEXT NOT NULL REFERENCES fill_review_sessions(session_id),
    field_name           TEXT,
    expected_value       TEXT,
    actual_value         TEXT,
    match                INTEGER NOT NULL DEFAULT 1,
    checked_at           TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ── 학습 시그널 ───────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS fill_review_learning_signals (
    signal_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id           TEXT REFERENCES fill_review_sessions(session_id),
    normalized_label     TEXT,
    semantic_type        TEXT,
    signal_type          TEXT NOT NULL,
    signal_value         TEXT,
    weight               REAL NOT NULL DEFAULT 1.0,
    created_at           TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ── XML 심층 분석 필요 플래그 ─────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS xml_deep_analyzer_need_flags (
    flag_id              INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id          TEXT REFERENCES hwpx_documents(document_id),
    reason               TEXT NOT NULL,
    raised_by            TEXT,
    raised_at            TEXT NOT NULL DEFAULT (datetime('now')),
    resolved             INTEGER NOT NULL DEFAULT 0,
    resolved_at          TEXT
);
