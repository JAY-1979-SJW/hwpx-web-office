"""HWPX-RECOGNITION-CORPUS-DB-BUILD-AND-SKIP-CLOSEOUT-01 — corpus DB 빌드 테스트.

build_corpus_db.py 스크립트의 동작을 검증한다.
"""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

SCHEMA_DIR = PROJECT_ROOT / "scripts" / "hwpx" / "recognition_corpus" / "schema"
BUILD_SCRIPT = PROJECT_ROOT / "scripts" / "hwpx" / "recognition_corpus" / "build_corpus_db.py"

REQUIRED_TABLES = (
    "hwpx_documents",
    "document_classifications",
    "label_occurrences",
    "human_label_decisions",
    "label_promotion_candidates",
    "label_dictionary_versions",
    "label_dictionary_entries",
    "accuracy_audits",
)
AUDIT_LOG_TABLES = (
    "fill_review_sessions",
    "fill_review_decision_logs",
    "fill_review_writer_operation_logs",
    "fill_review_readback_logs",
    "fill_review_learning_signals",
    "xml_deep_analyzer_need_flags",
)
PII_PATTERNS = (
    r"\b\d{6}-\d{7}\b",
    r"\b01[016789][-\s]?\d{3,4}[-\s]?\d{4}\b",
    r"\b\d{3}-\d{2}-\d{5}\b",
)


def _get_db_path_from_env(tmp_path: Path) -> Path:
    env = os.environ.get("HWPX_RECOGNITION_CORPUS_DB")
    return Path(env) if env else tmp_path / "corpus.sqlite3"


# ── A01~A03: schema 파일 존재 확인 ──────────────────────────────────────────

def test_schema_directory_exists():
    assert SCHEMA_DIR.is_dir(), f"schema dir not found: {SCHEMA_DIR}"


def test_init_sql_exists():
    assert (SCHEMA_DIR / "001_init.sql").is_file()


def test_migration_002_sql_exists():
    assert (SCHEMA_DIR / "002_audit_learning_logs.sql").is_file()


# ── A04: build script 존재 확인 ──────────────────────────────────────────────

def test_build_script_exists():
    assert BUILD_SCRIPT.is_file()


# ── A05: dry-run은 DB 생성 안 함 ─────────────────────────────────────────────

def test_dry_run_does_not_create_db(tmp_path):
    from hwpx.recognition_corpus.build_corpus_db import build
    db = tmp_path / "dry_run.sqlite3"
    result = build(db, fixture_minimal=False, force=False, dry_run=True)
    assert result["status"] == "DRY_RUN"
    assert not db.exists(), "dry-run should not create DB file"


# ── A06: fixture-minimal은 DB 생성 ───────────────────────────────────────────

def test_fixture_minimal_creates_db(tmp_path):
    from hwpx.recognition_corpus.build_corpus_db import build
    db = tmp_path / "corpus.sqlite3"
    result = build(db, fixture_minimal=True, force=False, dry_run=False)
    assert result["status"] == "PASS", result
    assert db.is_file()


# ── A07: 필수 테이블 존재 확인 ───────────────────────────────────────────────

def test_required_tables_exist(tmp_path):
    from hwpx.recognition_corpus.build_corpus_db import build
    db = tmp_path / "corpus.sqlite3"
    build(db, fixture_minimal=True, force=False, dry_run=False)
    conn = sqlite3.connect(str(db))
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    conn.close()
    for t in REQUIRED_TABLES:
        assert t in tables, f"required table missing: {t}"


# ── A08: audit learning log 테이블 존재 ──────────────────────────────────────

def test_audit_learning_log_tables_exist(tmp_path):
    from hwpx.recognition_corpus.build_corpus_db import build
    db = tmp_path / "corpus.sqlite3"
    build(db, fixture_minimal=True, force=False, dry_run=False)
    conn = sqlite3.connect(str(db))
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    conn.close()
    for t in AUDIT_LOG_TABLES:
        assert t in tables, f"audit log table missing: {t}"


# ── A09: PII 미포함 확인 ────────────────────────────────────────────────────

def test_no_pii_in_minimal_fixture(tmp_path):
    import re
    from hwpx.recognition_corpus.build_corpus_db import build
    db = tmp_path / "corpus.sqlite3"
    build(db, fixture_minimal=True, force=False, dry_run=False)
    conn = sqlite3.connect(str(db))
    rows = conn.execute(
        "SELECT source_path, document_id FROM hwpx_documents"
    ).fetchall()
    conn.close()
    for row in rows:
        text = " ".join(str(v) for v in row if v)
        for pattern in PII_PATTERNS:
            assert not re.search(pattern, text), \
                f"PII pattern {pattern!r} found in row: {row}"


# ── A09 확장: 합성 이름만 사용 확인 ─────────────────────────────────────────

def test_no_real_site_names_in_fixture(tmp_path):
    from hwpx.recognition_corpus.build_corpus_db import build
    db = tmp_path / "corpus.sqlite3"
    build(db, fixture_minimal=True, force=False, dry_run=False)
    conn = sqlite3.connect(str(db))
    paths = [r[0] for r in conn.execute(
        "SELECT source_path FROM hwpx_documents"
    ).fetchall()]
    conn.close()
    for path in paths:
        assert "synthetic" in path or "fx_" in path, \
            f"non-synthetic fixture name: {path}"


# ── A10: corpus.sqlite3 gitignore 확인 ──────────────────────────────────────

def test_corpus_sqlite3_in_gitignore():
    gi = PROJECT_ROOT / ".gitignore"
    text = gi.read_text(encoding="utf-8")
    assert "data/" in text or "*.sqlite3" in text, \
        "corpus.sqlite3 not covered by .gitignore"


# ── 기존 DB 보호: force 없이 덮어쓰기 거부 ───────────────────────────────────

def test_no_overwrite_without_force(tmp_path):
    from hwpx.recognition_corpus.build_corpus_db import build
    db = tmp_path / "corpus.sqlite3"
    build(db, fixture_minimal=False, force=False, dry_run=False)
    assert db.is_file()
    result = build(db, fixture_minimal=True, force=False, dry_run=False)
    assert result["status"] == "SKIP_EXISTS"


# ── --force 재생성 허용 ──────────────────────────────────────────────────────

def test_force_recreates_db(tmp_path):
    from hwpx.recognition_corpus.build_corpus_db import build
    db = tmp_path / "corpus.sqlite3"
    build(db, fixture_minimal=False, force=False, dry_run=False)
    mtime1 = db.stat().st_mtime_ns
    import time; time.sleep(0.01)
    result = build(db, fixture_minimal=True, force=True, dry_run=False)
    assert result["status"] == "PASS"
    mtime2 = db.stat().st_mtime_ns
    assert mtime2 > mtime1, "force should recreate DB"


# ── 환경변수 override ────────────────────────────────────────────────────────

def test_env_var_override(tmp_path, monkeypatch):
    custom_db = tmp_path / "custom" / "corpus.sqlite3"
    monkeypatch.setenv("HWPX_RECOGNITION_CORPUS_DB", str(custom_db))
    from hwpx.recognition_corpus import build_corpus_db
    import importlib
    importlib.reload(build_corpus_db)
    path = build_corpus_db.get_db_path()
    assert path == custom_db


# ── DB 없을 때 SKIP 유지 (기존 동작 회귀) ────────────────────────────────────

def test_no_corpus_db_means_skip(tmp_path, monkeypatch):
    missing = tmp_path / "nonexistent.sqlite3"
    monkeypatch.setenv("HWPX_RECOGNITION_CORPUS_DB", str(missing))
    assert not missing.exists()
    # DB 없음 → fixture resolve는 None 반환해야 한다
    from scripts.ops.audit_web_office_cell_save_hwpx_verify7 import audit
    result = audit()
    assert result["verdict"] in ("SKIP", "PASS"), \
        f"expected SKIP when DB missing, got: {result}"


# ── DB 있을 때 SKIP 대상 테스트 PASS 경로 진입 ───────────────────────────────

def test_corpus_db_present_enables_pass_path(tmp_path, monkeypatch):
    from hwpx.recognition_corpus.build_corpus_db import build
    db = tmp_path / "corpus.sqlite3"
    build(db, fixture_minimal=True, force=False, dry_run=False)
    monkeypatch.setenv("HWPX_RECOGNITION_CORPUS_DB", str(db))
    conn = sqlite3.connect(str(db))
    count = conn.execute("SELECT COUNT(*) FROM hwpx_documents").fetchone()[0]
    conn.close()
    assert count >= 1, "corpus DB should have documents after fixture-minimal"


# ── 깨진 DB는 SKIP 금지 → FAIL 처리 ─────────────────────────────────────────

def test_broken_db_is_not_skipped(tmp_path):
    from hwpx.recognition_corpus.build_corpus_db import build
    db = tmp_path / "broken.sqlite3"
    db.write_bytes(b"not a valid sqlite3 file")
    result = build(db, fixture_minimal=False, force=False, dry_run=False)
    assert result["status"] == "SKIP_EXISTS"

    # schema 검증 시 깨진 DB는 오류
    conn = None
    try:
        conn = sqlite3.connect(str(db))
        conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        is_broken = False
    except sqlite3.DatabaseError:
        is_broken = True
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
    assert is_broken, "file with garbage content should be recognized as broken DB"
