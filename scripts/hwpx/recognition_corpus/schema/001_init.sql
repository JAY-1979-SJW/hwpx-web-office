-- HWPX Recognition Corpus DB Schema v001
-- SQLite 기반 corpus DB 초기화 스크립트
--
-- 2026-09-28 완성도 감사: 이 파일이 tests/test_hwpx_recognition_corpus_db_schema.py
-- ("HWPX-RECOGNITION-CORPUS-DB-SCHEMA-CONTRACT-01")의 계약과 어긋나 있어서
-- 그 테스트가 전부 실패하고 있었다. corpus_schema.py 의 Python 쪽 상수
-- (ALLOWED_* / REQUIRED_TABLES)는 계약과 일치했지만, 이 DDL 만 예전 초안
-- 그대로 방치돼 있었다 — 실제 corpus.sqlite3 를 아직 아무도 만든 적이
-- 없어서(재현 자료 없음) 아무도 눈치채지 못했다.
--
-- 원칙: 기존 컬럼은 지우거나 이름 바꾸지 않고(스크립트/build_corpus_db.py
-- 가 raw_label/col_index 등 구 컬럼명으로 이미 INSERT 하고 있음) 계약이
-- 요구하는 컬럼만 추가한다. 단, label_promotion_candidates/
-- label_dictionary_versions/label_dictionary_entries/accuracy_audits 는
-- 이 컬럼들을 쓰는 production 코드가 하나도 없어서(grep 확인) 계약에
-- 맞춰 구조를 정리했다.

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ── 핵심 테이블 ──────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS hwpx_documents (
    document_id          TEXT PRIMARY KEY,
    source_path          TEXT NOT NULL,
    source_kind          TEXT NOT NULL DEFAULT 'unknown',
    file_size            INTEGER,
    mtime                REAL,
    detected_type        TEXT,
    sha256               TEXT,
    inventory_status     TEXT NOT NULL DEFAULT 'FOUND',
    first_seen_at        TEXT NOT NULL DEFAULT (datetime('now')),
    last_checked_at      TEXT,
    last_audited_at      TEXT,
    notes                TEXT
);

CREATE TABLE IF NOT EXISTS document_classifications (
    classification_id    TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    document_id          TEXT NOT NULL REFERENCES hwpx_documents(document_id),
    classifier_version   TEXT NOT NULL DEFAULT 'unknown',
    document_type        TEXT NOT NULL DEFAULT 'unknown'
                          CHECK (document_type IN (
                              'fillable_form', 'reference_table', 'empty_template',
                              'unknown', 'broken', 'non_hwpx'
                          )),
    confidence            REAL CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    evidence_json         TEXT,
    classified_at         TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (document_id, classifier_version)
);

CREATE TABLE IF NOT EXISTS label_occurrences (
    occurrence_id         TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    document_id           TEXT NOT NULL REFERENCES hwpx_documents(document_id),
    raw_label             TEXT,
    label_text            TEXT,
    normalized_label      TEXT NOT NULL,
    semantic_type         TEXT NOT NULL DEFAULT 'UNKNOWN',
    section_index         INTEGER,
    table_id              TEXT,
    row_index             INTEGER,
    col_index             INTEGER,
    cell_index            INTEGER,
    cell_key              TEXT,
    paragraph_key         TEXT,
    neighbor_text         TEXT,
    right_neighbor_empty  INTEGER,
    occurrence_context_json TEXT,
    confidence            REAL,
    source                TEXT,
    detected_at           TEXT NOT NULL DEFAULT (datetime('now')),
    audited_at            TEXT
);

CREATE TABLE IF NOT EXISTS human_label_decisions (
    decision_id          TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    normalized_label     TEXT NOT NULL,
    semantic_type        TEXT NOT NULL
                          CHECK (semantic_type IN (
                              'PROJECT_NAME', 'CONTRACT_AMOUNT', 'START_DATE', 'END_DATE',
                              'COMPANY_NAME', 'BUSINESS_REGISTRATION_NUMBER',
                              'REPRESENTATIVE_NAME', 'SITE_MANAGER_NAME',
                              'ADDRESS', 'PHONE',
                              'ATTACHMENT_DOCUMENT', 'STAMP_OR_SEAL',
                              'FREE_TEXT', 'CHECKBOX', 'YES_NO',
                              'INSPECTION_ITEM', 'MATERIAL_NAME',
                              'QUANTITY', 'UNKNOWN'
                          )),
    decision_status      TEXT NOT NULL DEFAULT 'HELD'
                          CHECK (decision_status IN ('APPROVED', 'REJECTED', 'HELD')),
    decided_by           TEXT,
    reason               TEXT,
    decided_at           TEXT NOT NULL DEFAULT (datetime('now')),
    notes                TEXT
);

CREATE TABLE IF NOT EXISTS label_promotion_candidates (
    candidate_id         TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    normalized_label     TEXT NOT NULL,
    proposed_semantic    TEXT,
    occurrence_count     INTEGER NOT NULL DEFAULT 0,
    document_count       INTEGER NOT NULL DEFAULT 0,
    evidence_score       REAL,
    status               TEXT NOT NULL DEFAULT 'PENDING'
                          CHECK (status IN (
                              'PENDING', 'APPROVED', 'REJECTED', 'HELD',
                              'BLOCKED_CONFLICT', 'BLOCKED_LOW_EVIDENCE'
                          )),
    conflict_count       INTEGER NOT NULL DEFAULT 0,
    evidence_json        TEXT,
    approved_at          TEXT,
    promotion_version    TEXT,
    -- 구 초안 컬럼(참조하는 production 코드 없음, 하위호환용으로만 유지)
    semantic_type        TEXT,
    promotion_status     TEXT NOT NULL DEFAULT 'PENDING',
    evidence_doc_ids     TEXT,
    created_at           TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at           TEXT
);

CREATE TABLE IF NOT EXISTS label_dictionary_versions (
    version              TEXT PRIMARY KEY,
    built_at             TEXT NOT NULL DEFAULT (datetime('now')),
    entry_count          INTEGER NOT NULL DEFAULT 0,
    source_corpus_sha    TEXT,
    approved_by          TEXT,
    notes                TEXT
);

CREATE TABLE IF NOT EXISTS label_dictionary_entries (
    entry_id              TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    version               TEXT NOT NULL REFERENCES label_dictionary_versions(version),
    normalized_label      TEXT NOT NULL,
    semantic_type         TEXT NOT NULL
                          CHECK (semantic_type IN (
                              'PROJECT_NAME', 'CONTRACT_AMOUNT', 'START_DATE', 'END_DATE',
                              'COMPANY_NAME', 'BUSINESS_REGISTRATION_NUMBER',
                              'REPRESENTATIVE_NAME', 'SITE_MANAGER_NAME',
                              'ADDRESS', 'PHONE',
                              'ATTACHMENT_DOCUMENT', 'STAMP_OR_SEAL',
                              'FREE_TEXT', 'CHECKBOX', 'YES_NO',
                              'INSPECTION_ITEM', 'MATERIAL_NAME', 'QUANTITY'
                              -- UNKNOWN 은 의도적으로 제외 — dictionary 승격 금지 (Gate 3)
                          )),
    source_evidence_json  TEXT,
    added_at              TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS accuracy_audits (
    audit_id             TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    dictionary_version   TEXT,
    classifier_version   TEXT,
    audit_at             TEXT NOT NULL DEFAULT (datetime('now')),
    sample_size          INTEGER,
    precision            REAL CHECK (precision IS NULL OR (precision >= 0 AND precision <= 1)),
    recall               REAL CHECK (recall IS NULL OR (recall >= 0 AND recall <= 1)),
    f1                   REAL CHECK (f1 IS NULL OR (f1 >= 0 AND f1 <= 1)),
    notes                TEXT,
    -- 구 초안 컬럼(참조하는 production 코드 없음, 하위호환용으로만 유지)
    document_id          TEXT REFERENCES hwpx_documents(document_id),
    task_name            TEXT,
    verdict              TEXT NOT NULL DEFAULT 'FAIL',
    details              TEXT,
    audited_at           TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ── 인덱스 ───────────────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_label_occurrences_norm
    ON label_occurrences(normalized_label);

-- ── 뷰 ───────────────────────────────────────────────────────────────────────

DROP VIEW IF EXISTS labels_by_frequency;
CREATE VIEW labels_by_frequency AS
SELECT
    normalized_label,
    COUNT(*) AS occurrence_count,
    COUNT(DISTINCT document_id) AS document_count
FROM label_occurrences
GROUP BY normalized_label
ORDER BY occurrence_count DESC;

DROP VIEW IF EXISTS pending_promotion_candidates;
CREATE VIEW pending_promotion_candidates AS
SELECT *
FROM label_promotion_candidates
WHERE status = 'PENDING';

DROP VIEW IF EXISTS classification_disagreements;
CREATE VIEW classification_disagreements AS
SELECT
    c1.document_id,
    c1.classifier_version AS version_a,
    c2.classifier_version AS version_b,
    c1.document_type      AS type_a,
    c2.document_type      AS type_b
FROM document_classifications c1
JOIN document_classifications c2
    ON c1.document_id = c2.document_id
    AND c1.classifier_version < c2.classifier_version
    AND c1.document_type != c2.document_type;

DROP VIEW IF EXISTS dictionary_version_summary;
CREATE VIEW dictionary_version_summary AS
SELECT
    v.version,
    v.entry_count,
    v.built_at,
    COUNT(e.entry_id) AS actual_entry_count
FROM label_dictionary_versions v
LEFT JOIN label_dictionary_entries e ON e.version = v.version
GROUP BY v.version;
