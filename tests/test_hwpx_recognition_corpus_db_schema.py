"""HWPX-RECOGNITION-CORPUS-DB-SCHEMA-CONTRACT-01 — schema tests.

in-memory SQLite 기반. 실제 corpus.sqlite3 또는 9,377건 ingest 없음.
writer 미호출, output HWPX 미생성, 원본 무수정, secret 미출력.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))


@pytest.fixture
def conn():
    from hwpx.recognition_corpus import corpus_schema as cs
    c = sqlite3.connect(":memory:")
    c.execute("PRAGMA foreign_keys = ON")
    cs.init_db(c)
    yield c
    c.close()


@pytest.fixture
def cs_mod():
    from hwpx.recognition_corpus import corpus_schema as m
    return m


# T01: init_db ───────────────────────────────────────────────────────────────

def test_t01_init_db_succeeds(conn):
    assert conn is not None
    tables = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    assert len(tables) >= 8


# T02: 8개 required tables ─────────────────────────────────────────────────

def test_t02_required_tables_exist(conn, cs_mod):
    tables = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    for t in cs_mod.REQUIRED_TABLES:
        assert t in tables, f"missing table: {t}"


# T03: required columns ───────────────────────────────────────────────────

_EXPECTED_COLUMNS: dict[str, set[str]] = {
    "hwpx_documents": {
        "document_id", "source_path", "source_kind", "file_size",
        "mtime", "detected_type", "inventory_status", "sha256",
        "first_seen_at", "last_audited_at", "notes",
    },
    "document_classifications": {
        "classification_id", "document_id", "classifier_version",
        "document_type", "confidence", "evidence_json", "classified_at",
    },
    "label_occurrences": {
        "occurrence_id", "document_id", "section_index", "table_id",
        "cell_key", "paragraph_key", "label_text", "normalized_label",
        "neighbor_text", "right_neighbor_empty", "row_index",
        "cell_index", "occurrence_context_json", "audited_at",
    },
    "human_label_decisions": {
        "decision_id", "normalized_label", "semantic_type",
        "decision_status", "decided_by", "reason", "decided_at",
    },
    "label_promotion_candidates": {
        "candidate_id", "normalized_label", "proposed_semantic",
        "occurrence_count", "document_count", "evidence_score",
        "status", "conflict_count", "evidence_json",
        "approved_at", "promotion_version",
    },
    "label_dictionary_versions": {
        "version", "built_at", "entry_count",
        "source_corpus_sha", "approved_by", "notes",
    },
    "label_dictionary_entries": {
        "version", "normalized_label", "semantic_type",
        "source_evidence_json",
    },
    "accuracy_audits": {
        "audit_id", "dictionary_version", "classifier_version",
        "audit_at", "sample_size", "precision", "recall", "f1", "notes",
    },
}


@pytest.mark.parametrize("table,expected_cols", list(_EXPECTED_COLUMNS.items()))
def test_t03_required_columns(conn, table, expected_cols):
    actual = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    missing = expected_cols - actual
    assert not missing, f"{table} missing columns: {missing}"


# T04: foreign key enforcement ────────────────────────────────────────────

def test_t04_foreign_keys_enabled(conn):
    fk = conn.execute("PRAGMA foreign_keys").fetchone()
    assert fk[0] == 1


def test_t04b_foreign_key_violation_blocks_classification(conn):
    """존재하지 않는 document_id로 분류 INSERT 시 차단."""
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO document_classifications "
            "(document_id, classifier_version, document_type, confidence, classified_at) "
            "VALUES ('nonexistent', 'v1', 'fillable_form', 0.5, 'now')"
        )


# T05: document_id duplicate 차단 ─────────────────────────────────────────

def _insert_doc(conn, doc_id="doc1", sha=None):
    conn.execute(
        "INSERT INTO hwpx_documents "
        "(document_id, source_path, source_kind, file_size, mtime, "
        " detected_type, inventory_status, sha256, first_seen_at) "
        "VALUES (?, ?, 'repo_sample', 100, 0.0, 'hwpx', 'FOUND', ?, '2026-05-18')",
        (doc_id, f"path/{doc_id}.hwpx", sha or doc_id),
    )


def test_t05_document_id_duplicate_blocked(conn):
    _insert_doc(conn, "doc1")
    with pytest.raises(sqlite3.IntegrityError):
        _insert_doc(conn, "doc1")


# T06: UNIQUE(document_id, classifier_version) ────────────────────────────

def test_t06_classification_unique(conn):
    _insert_doc(conn, "d1")
    conn.execute(
        "INSERT INTO document_classifications "
        "(document_id, classifier_version, document_type, confidence, classified_at) "
        "VALUES ('d1', 'v1', 'fillable_form', 0.9, 'now')"
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO document_classifications "
            "(document_id, classifier_version, document_type, confidence, classified_at) "
            "VALUES ('d1', 'v1', 'reference_table', 0.8, 'now')"
        )
    # 다른 classifier_version은 OK
    conn.execute(
        "INSERT INTO document_classifications "
        "(document_id, classifier_version, document_type, confidence, classified_at) "
        "VALUES ('d1', 'v2', 'reference_table', 0.8, 'now')"
    )


# T07: confidence 범위 ───────────────────────────────────────────────────

def test_t07_confidence_out_of_range_blocked(conn):
    _insert_doc(conn, "d1")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO document_classifications "
            "(document_id, classifier_version, document_type, confidence, classified_at) "
            "VALUES ('d1', 'v1', 'fillable_form', 1.5, 'now')"
        )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO document_classifications "
            "(document_id, classifier_version, document_type, confidence, classified_at) "
            "VALUES ('d1', 'v1', 'fillable_form', -0.1, 'now')"
        )


# T08: allowed document_type ─────────────────────────────────────────────

def test_t08_document_type_check_blocks_invalid(conn):
    _insert_doc(conn, "d1")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO document_classifications "
            "(document_id, classifier_version, document_type, confidence, classified_at) "
            "VALUES ('d1', 'v1', 'unknown_invalid_type', 0.5, 'now')"
        )


# T09: normalized_label 인덱스 ────────────────────────────────────────────

def test_t09_label_occurrence_norm_index(conn):
    idx = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index'"
    )}
    assert "idx_label_occurrences_norm" in idx


# T10: human_label_decisions allowed semantic ────────────────────────────

def test_t10_human_decision_semantic_allowed(conn, cs_mod):
    conn.execute(
        "INSERT INTO human_label_decisions "
        "(normalized_label, semantic_type, decision_status, decided_by, decided_at) "
        "VALUES ('공사명', 'PROJECT_NAME', 'APPROVED', 'alice', 'now')"
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO human_label_decisions "
            "(normalized_label, semantic_type, decision_status, decided_by, decided_at) "
            "VALUES ('공사명', 'NOT_A_SEMANTIC', 'APPROVED', 'alice', 'now')"
        )


# T11: decision_status allowed ───────────────────────────────────────────

def test_t11_decision_status_allowed(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO human_label_decisions "
            "(normalized_label, semantic_type, decision_status, decided_by, decided_at) "
            "VALUES ('공사명', 'PROJECT_NAME', 'MAYBE', 'alice', 'now')"
        )


# T12: promotion candidate status allowed ─────────────────────────────────

def test_t12_promotion_status_allowed(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO label_promotion_candidates "
            "(normalized_label, proposed_semantic, occurrence_count, "
            " document_count, evidence_score, status) "
            "VALUES ('공사명', 'PROJECT_NAME', 5, 5, 0.8, 'NOT_A_STATUS')"
        )


# T13: UNKNOWN dictionary entry 차단 ─────────────────────────────────────

def test_t13_unknown_dictionary_entry_blocked(conn, cs_mod):
    conn.execute(
        "INSERT INTO label_dictionary_versions "
        "(version, built_at, entry_count, source_corpus_sha, approved_by) "
        "VALUES ('v1', 'now', 0, 'sha:1', 'alice')"
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO label_dictionary_entries "
            "(version, normalized_label, semantic_type) "
            "VALUES ('v1', '공사명', 'UNKNOWN')"
        )
    assert not cs_mod.is_dictionary_allowed_semantic("UNKNOWN")


# T14: human approval 없는 promotion 차단 helper ─────────────────────────

def test_t14_promotion_blocked_without_human_approval(conn, cs_mod):
    allowed, reason = cs_mod.can_promote_to_dictionary(
        conn, "신규라벨", "PROJECT_NAME"
    )
    assert allowed is False
    assert reason == "BLOCKED_NO_HUMAN_APPROVAL"


def test_t14b_promotion_allowed_with_human_approval(conn, cs_mod):
    conn.execute(
        "INSERT INTO human_label_decisions "
        "(normalized_label, semantic_type, decision_status, decided_by, decided_at) "
        "VALUES ('공사명', 'PROJECT_NAME', 'APPROVED', 'alice', 'now')"
    )
    allowed, reason = cs_mod.can_promote_to_dictionary(
        conn, "공사명", "PROJECT_NAME"
    )
    assert allowed is True
    assert reason == "OK"


# T15: conflicting semantic decisions 감지 ────────────────────────────────

def test_t15_conflicting_semantics_detected(conn, cs_mod):
    conn.execute(
        "INSERT INTO human_label_decisions "
        "(normalized_label, semantic_type, decision_status, decided_by, decided_at) "
        "VALUES ('이름', 'PROJECT_NAME', 'APPROVED', 'alice', 'now')"
    )
    conn.execute(
        "INSERT INTO human_label_decisions "
        "(normalized_label, semantic_type, decision_status, decided_by, decided_at) "
        "VALUES ('이름', 'COMPANY_NAME', 'APPROVED', 'bob', 'now')"
    )
    conflicts = cs_mod.detect_semantic_conflicts(conn, "이름")
    assert len(conflicts) == 2
    allowed, reason = cs_mod.can_promote_to_dictionary(
        conn, "이름", "PROJECT_NAME"
    )
    assert allowed is False
    assert reason == "BLOCKED_CONFLICT"


# T16: dictionary version + entries insert ──────────────────────────────

def test_t16_dictionary_version_and_entries(conn):
    conn.execute(
        "INSERT INTO label_dictionary_versions "
        "(version, built_at, entry_count, source_corpus_sha, approved_by) "
        "VALUES ('v1', 'now', 2, 'sha:1', 'alice')"
    )
    conn.execute(
        "INSERT INTO label_dictionary_entries "
        "(version, normalized_label, semantic_type) "
        "VALUES ('v1', '공사명', 'PROJECT_NAME')"
    )
    conn.execute(
        "INSERT INTO label_dictionary_entries "
        "(version, normalized_label, semantic_type) "
        "VALUES ('v1', '계약금액', 'CONTRACT_AMOUNT')"
    )
    count = conn.execute(
        "SELECT COUNT(*) FROM label_dictionary_entries WHERE version='v1'"
    ).fetchone()[0]
    assert count == 2


# T17: accuracy precision/recall/f1 범위 ────────────────────────────────

def test_t17_accuracy_metric_range(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO accuracy_audits "
            "(dictionary_version, audit_at, sample_size, precision) "
            "VALUES ('v1', 'now', 100, 1.5)"
        )


# T18: labels_by_frequency view ─────────────────────────────────────────

def test_t18_labels_by_frequency_view(conn):
    _insert_doc(conn, "d1")
    _insert_doc(conn, "d2")
    for _ in range(3):
        conn.execute(
            "INSERT INTO label_occurrences "
            "(document_id, label_text, normalized_label, "
            " right_neighbor_empty, audited_at) "
            "VALUES ('d1', '공사명', '공사명', 1, 'now')"
        )
    conn.execute(
        "INSERT INTO label_occurrences "
        "(document_id, label_text, normalized_label, "
        " right_neighbor_empty, audited_at) "
        "VALUES ('d2', '공사명', '공사명', 1, 'now')"
    )
    rows = list(conn.execute("SELECT * FROM labels_by_frequency"))
    assert rows
    assert rows[0][0] == "공사명"
    assert rows[0][1] == 4
    assert rows[0][2] == 2   # 2 distinct documents


# T19: pending_promotion_candidates view ────────────────────────────────

def test_t19_pending_promotion_view(conn):
    conn.execute(
        "INSERT INTO label_promotion_candidates "
        "(normalized_label, proposed_semantic, occurrence_count, "
        " document_count, evidence_score, status) "
        "VALUES ('공사명', 'PROJECT_NAME', 10, 5, 0.9, 'PENDING')"
    )
    conn.execute(
        "INSERT INTO label_promotion_candidates "
        "(normalized_label, proposed_semantic, occurrence_count, "
        " document_count, evidence_score, status) "
        "VALUES ('xxx', 'PROJECT_NAME', 1, 1, 0.2, 'REJECTED')"
    )
    rows = list(conn.execute("SELECT * FROM pending_promotion_candidates"))
    assert len(rows) == 1


# T20: classification_disagreements view ────────────────────────────────

def test_t20_classification_disagreements(conn):
    _insert_doc(conn, "d1")
    conn.execute(
        "INSERT INTO document_classifications "
        "(document_id, classifier_version, document_type, confidence, classified_at) "
        "VALUES ('d1', 'filename_v1', 'fillable_form', 0.7, 'now')"
    )
    conn.execute(
        "INSERT INTO document_classifications "
        "(document_id, classifier_version, document_type, confidence, classified_at) "
        "VALUES ('d1', 'content_v1', 'reference_table', 0.6, 'now')"
    )
    rows = list(conn.execute("SELECT * FROM classification_disagreements"))
    assert len(rows) == 1


# T21: schema init idempotent ───────────────────────────────────────────

def test_t21_init_idempotent(conn, cs_mod):
    cs_mod.init_db(conn)
    cs_mod.init_db(conn)  # 두 번 호출해도 crash 없음
    findings = cs_mod.validate_schema(conn)
    assert findings["ok"] is True


# T22: migration checksum ────────────────────────────────────────────────

def test_t22_migration_checksum(cs_mod):
    info = cs_mod.migration_checksum()
    assert info["schemaVersion"] == "001"
    assert info["migrationFile"] == "001_init.sql"
    assert len(info["sha256"]) == 64
    assert info["byteSize"] > 0


# T23: gitignore for corpus ─────────────────────────────────────────────

def test_t23_gitignore_blocks_corpus_files(cs_mod):
    r = cs_mod.audit_gitignore_for_corpus()
    assert r["ok"] is True, r


# T24: production module DB import 금지 ────────────────────────────────

def test_t24_production_isolation(cs_mod):
    r = cs_mod.audit_production_isolation()
    assert r["ok"] is True, f"production violations: {r['violations']}"
    assert len(r["filesChecked"]) >= 4


# T25: no secret / DB URL ─────────────────────────────────────────────

def test_t25_no_secret_in_schema_file():
    p = (PROJECT_ROOT
          / "data/recognition_corpus/schema/001_init.sql").read_text(
        encoding="utf-8"
    )
    for forbidden in ("sk-", "Bearer ", "DATABASE_URL=", "ANTHROPIC_API_KEY",
                          "OPENAI_API_KEY"):
        assert forbidden not in p
    src = (PROJECT_ROOT
            / "scripts/hwpx/recognition_corpus/corpus_schema.py").read_text(
        encoding="utf-8"
    )
    for forbidden in ("sk-", "Bearer ", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        assert forbidden not in src


# T26: writer 미호출 ─────────────────────────────────────────────────────

def test_t26_writer_not_invoked_during_schema(monkeypatch):
    from hwpx.pipeline import generic_edit_plan_writer_executor_live_sandbox as live
    call_log: list = []
    monkeypatch.setattr(live, "execute_writer_call_plan_live_sandbox",
                          lambda *a, **k: call_log.append("live"))
    # schema 모듈 import + init 자체로 writer가 호출되지 않음
    import importlib
    import hwpx.recognition_corpus.corpus_schema as cs
    importlib.reload(cs)
    c = sqlite3.connect(":memory:")
    cs.init_db(c)
    cs.validate_schema(c)
    c.close()
    assert call_log == []


# T27: output HWPX 미생성 ──────────────────────────────────────────────

def test_t27_no_output_hwpx(tmp_path, cs_mod):
    before = sorted(p.name for p in tmp_path.iterdir())
    db = tmp_path / "corpus.sqlite3"
    conn = cs_mod.open_corpus_db(db)
    conn.close()
    after = sorted(p.name for p in tmp_path.iterdir())
    # corpus.sqlite3 외 .hwpx 없음
    assert all(not n.endswith(".hwpx") for n in after)


# T28-T30: 기존 회귀 모듈 import 가능성 smoke ─────────────────────────────

def test_t28_collected_audit_imports_clean():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "audit_collected_hwpx_inventory",
        PROJECT_ROOT / "scripts/ops/audit_collected_hwpx_inventory.py",
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    assert callable(m.build_inventory)


def test_t29_full_coverage_audit_imports_clean():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "audit_hwpx_recognition_full_coverage",
        PROJECT_ROOT / "scripts/ops/audit_hwpx_recognition_full_coverage.py",
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    assert callable(m.run_audit)


def test_t30_live_pipeline_imports_clean():
    from hwpx.fill_review import fill_review_live_pipeline
    assert callable(fill_review_live_pipeline.run_fill_review_live_pipeline_sandbox)
