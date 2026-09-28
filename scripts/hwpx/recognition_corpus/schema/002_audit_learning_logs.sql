-- HWPX Recognition Corpus DB Migration 002
-- fill_review audit/learning log 테이블 추가
--
-- 2026-09-28 완성도 감사: audit_learning_log_contract.py 의 실제 INSERT 문
-- (session/decision/writer_operation/readback/learning_signal/xml_backlog)
-- 이 쓰는 컬럼과 이 DDL 이 어긋나 있었다 — HWPX-FILL-REVIEW-AUDIT-AND-
-- LEARNING-LOG-CONTRACT-01 계약 테스트 46개 전부 이 파일 때문에 실패.
-- 원칙은 001과 동일: production INSERT 문에 실제로 쓰이는 컬럼을 모두
-- 추가하고, 참조하는 코드가 없는 구 컬럼은 지우지 않되 NOT NULL 은
-- 새 INSERT 를 막지 않도록 완화한다.

PRAGMA foreign_keys = ON;

-- ── fill_review 세션 ──────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS fill_review_sessions (
    session_id           TEXT PRIMARY KEY,
    document_id          TEXT,
    source_document_hash TEXT,
    document_type        TEXT,
    sub_type             TEXT,
    classifier_version   TEXT,
    dictionary_version    TEXT,
    started_at           TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at         TEXT,
    session_status       TEXT NOT NULL DEFAULT 'REVIEW_STARTED'
                          CHECK (session_status IN (
                              'REVIEW_STARTED', 'READY_FOR_DECISION', 'DECISION_VALIDATED',
                              'WRITER_APPLIED', 'WRITER_BLOCKED', 'READBACK_FAILED',
                              'COMPLETED', 'CANCELLED', 'ERROR'
                          )),
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
    current_value_hash   TEXT,
    proposed_value_hash  TEXT,
    edited_value_hash    TEXT,
    decision             TEXT NOT NULL
                          CHECK (decision IN (
                              'APPROVE', 'REJECT', 'HOLD', 'EDIT_VALUE',
                              'REQUEST_MATERIAL', 'SYSTEM_APPROVE', 'SYSTEM_HOLD'
                          )),
    decision_source      TEXT NOT NULL
                          CHECK (decision_source IN (
                              'USER', 'SYSTEM_POLICY', 'AI_ASSISTED', 'TEST_FIXTURE'
                          )),
    decided_by           TEXT,
    decided_at           TEXT NOT NULL DEFAULT (datetime('now')),
    evidence_refs_json   TEXT,
    reason               TEXT,
    risk_flags_json      TEXT,
    -- 구 초안 컬럼(참조하는 production 코드 없음, 하위호환용으로만 유지)
    proposed_value       TEXT,
    decision_status      TEXT NOT NULL DEFAULT 'HELD',
    confidence           REAL,
    reviewer             TEXT,
    notes                TEXT
);

-- ── 쓰기 오퍼레이션 로그 ──────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS fill_review_writer_operation_logs (
    op_log_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id           TEXT NOT NULL REFERENCES fill_review_sessions(session_id),
    decision_log_id      INTEGER REFERENCES fill_review_decision_logs(log_id),
    operation_type       TEXT NOT NULL
                          CHECK (operation_type IN (
                              'setCellText', 'setParagraphText', 'replaceTextRun',
                              'setCellHorizontalAlign', 'setCellVerticalAlign'
                          )),
    writer_method        TEXT,
    target_type          TEXT,
    target_key           TEXT,
    expected_before_hash TEXT,
    value_hash           TEXT,
    operation_status     TEXT NOT NULL DEFAULT 'CREATED'
                          CHECK (operation_status IN ('CREATED', 'BLOCKED', 'APPLIED', 'SKIPPED')),
    blocked_reason       TEXT,
    created_at           TEXT NOT NULL DEFAULT (datetime('now')),
    -- 구 초안 컬럼(참조하는 production 코드 없음, 하위호환용으로만 유지)
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
    operation_log_id     INTEGER REFERENCES fill_review_writer_operation_logs(op_log_id),
    readback_status      TEXT NOT NULL
                          CHECK (readback_status IN ('MATCHED', 'MISMATCH', 'NOT_RUN', 'BLOCKED')),
    expected_after_hash  TEXT,
    actual_after_hash    TEXT,
    divergence_code      TEXT,
    divergence_summary   TEXT,
    checked_at           TEXT NOT NULL DEFAULT (datetime('now')),
    -- 구 초안 컬럼(참조하는 production 코드 없음, 하위호환용으로만 유지)
    field_name           TEXT,
    expected_value       TEXT,
    actual_value         TEXT,
    match                INTEGER NOT NULL DEFAULT 1
);

-- ── 학습 시그널 ───────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS fill_review_learning_signals (
    signal_id             INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id            TEXT REFERENCES fill_review_sessions(session_id),
    document_id           TEXT,
    document_type         TEXT,
    sub_type              TEXT,
    normalized_label      TEXT,
    semantic_type         TEXT,
    target_type           TEXT,
    target_pattern        TEXT,
    evidence_type         TEXT,
    decision_source       TEXT,
    writer_success        INTEGER NOT NULL DEFAULT 0,
    readback_success      INTEGER NOT NULL DEFAULT 0,
    reusable              INTEGER NOT NULL DEFAULT 0,
    promotion_candidate_id TEXT,
    blocked_reason        TEXT,
    signal_score          REAL,
    created_at            TEXT NOT NULL DEFAULT (datetime('now')),
    -- 구 초안 컬럼(참조하는 production 코드 없음, 하위호환용으로만 유지)
    signal_type           TEXT,
    signal_value          TEXT,
    weight                REAL NOT NULL DEFAULT 1.0
);

-- ── XML 심층 분석 필요 플래그 ─────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS xml_deep_analyzer_need_flags (
    flag_id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id           TEXT REFERENCES fill_review_sessions(session_id),
    document_id          TEXT,
    reason_code          TEXT
                          CHECK (reason_code IS NULL OR reason_code IN (
                              'RUN_BOUNDARY_UNSUPPORTED', 'CHECKBOX_OR_SHAPE_NEEDED',
                              'OBJECT_ANCHOR_NEEDED', 'STYLE_RESOLUTION_NEEDED',
                              'CELL_INTERNAL_PARAGRAPH_NEEDED', 'MERGED_CELL_GEOMETRY_NEEDED',
                              'READBACK_MISMATCH', 'TARGET_AMBIGUOUS',
                              'LABEL_CONTEXT_INSUFFICIENT'
                          )),
    target_key           TEXT,
    normalized_label     TEXT,
    context_json         TEXT,
    severity             TEXT
                          CHECK (severity IS NULL OR severity IN ('LOW', 'MEDIUM', 'HIGH')),
    -- document_id 는 hwpx_documents 를 참조하지 않는다 — fill_review 세션은
    -- 합성/샘플 document_id 로도 돌아가야 해서(계약 테스트가 hwpx_documents
    -- 를 안 채운 채 이 테이블만 씀) FK 로 묶으면 정상 흐름이 막힌다.
    raised_by            TEXT,
    raised_at            TEXT NOT NULL DEFAULT (datetime('now')),
    resolved             INTEGER NOT NULL DEFAULT 0,
    resolved_at          TEXT,
    created_at           TEXT NOT NULL DEFAULT (datetime('now')),
    -- 구 초안 컬럼(참조하는 production 코드 없음, 하위호환용으로만 유지)
    reason               TEXT
);

-- ── 뷰 ───────────────────────────────────────────────────────────────────────

DROP VIEW IF EXISTS reusable_learning_signals;
CREATE VIEW reusable_learning_signals AS
SELECT * FROM fill_review_learning_signals WHERE reusable = 1;

DROP VIEW IF EXISTS failed_writer_patterns;
CREATE VIEW failed_writer_patterns AS
SELECT * FROM fill_review_writer_operation_logs WHERE operation_status = 'BLOCKED';

DROP VIEW IF EXISTS xml_deep_analyzer_backlog;
CREATE VIEW xml_deep_analyzer_backlog AS
SELECT *
FROM xml_deep_analyzer_need_flags
WHERE resolved = 0
ORDER BY CASE severity
    WHEN 'HIGH' THEN 0
    WHEN 'MEDIUM' THEN 1
    WHEN 'LOW' THEN 2
    ELSE 3
END, raised_at;

DROP VIEW IF EXISTS decision_summary_by_label;
CREATE VIEW decision_summary_by_label AS
SELECT normalized_label, COUNT(*) AS decision_count
FROM fill_review_decision_logs
GROUP BY normalized_label;

DROP VIEW IF EXISTS learning_signal_summary_by_doc_type;
CREATE VIEW learning_signal_summary_by_doc_type AS
SELECT document_type,
       COUNT(*) AS signal_count,
       SUM(reusable) AS reusable_count
FROM fill_review_learning_signals
GROUP BY document_type;
