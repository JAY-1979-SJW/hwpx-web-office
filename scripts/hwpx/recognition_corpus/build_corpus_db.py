"""HWPX-RECOGNITION-CORPUS-DB-BUILD-AND-SKIP-CLOSEOUT-01 — corpus DB 빌드 스크립트.

사용법:
  python scripts/hwpx/recognition_corpus/build_corpus_db.py --fixture-minimal
  python scripts/hwpx/recognition_corpus/build_corpus_db.py --dry-run
  python scripts/hwpx/recognition_corpus/build_corpus_db.py --fixture-minimal --force

환경변수:
  HWPX_RECOGNITION_CORPUS_DB : corpus.sqlite3 경로 override (기본: data/recognition_corpus/corpus.sqlite3)
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_DIR = Path(__file__).resolve().parent / "schema"
INIT_SQL = SCHEMA_DIR / "001_init.sql"
MIGRATION_002_SQL = SCHEMA_DIR / "002_audit_learning_logs.sql"

DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "recognition_corpus" / "corpus.sqlite3"


def get_db_path() -> Path:
    env = os.environ.get("HWPX_RECOGNITION_CORPUS_DB")
    return Path(env) if env else DEFAULT_DB_PATH


def _check_schemas() -> list[str]:
    errors: list[str] = []
    if not SCHEMA_DIR.is_dir():
        errors.append(f"FAIL_CORPUS_DB_SCHEMA_MISSING: schema dir not found: {SCHEMA_DIR}")
    if not INIT_SQL.is_file():
        errors.append(f"FAIL_CORPUS_DB_SCHEMA_MISSING: 001_init.sql not found")
    if not MIGRATION_002_SQL.is_file():
        errors.append(f"FAIL_CORPUS_DB_SCHEMA_MISSING: 002_audit_learning_logs.sql not found")
    return errors


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(INIT_SQL.read_text(encoding="utf-8"))
    conn.executescript(MIGRATION_002_SQL.read_text(encoding="utf-8"))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.commit()


def _insert_minimal_fixture(conn: sqlite3.Connection) -> None:
    now = datetime.now(timezone.utc).isoformat()

    docs = [
        ("doc-synthetic-001", "tests/fixtures/hwpx/corpus/fx_synthetic_metadata_form.hwpx",
         "repo_sample", "FOUND"),
        ("doc-synthetic-002", "tests/fixtures/hwpx/corpus/fx_metadata_form.hwpx",
         "repo_sample", "FOUND"),
        ("doc-synthetic-003", "tests/fixtures/hwpx/corpus/fx_nested_legal_complex.hwpx",
         "repo_sample", "FOUND"),
    ]
    for doc_id, path, kind, status in docs:
        conn.execute(
            "INSERT OR IGNORE INTO hwpx_documents "
            "(document_id, source_path, source_kind, inventory_status, first_seen_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (doc_id, path, kind, status, now),
        )

    classifications = [
        ("cls-001", "doc-synthetic-001", "fillable_form", 0.92),
        ("cls-002", "doc-synthetic-002", "fillable_form", 0.88),
        ("cls-003", "doc-synthetic-003", "fillable_form", 0.85),
    ]
    for cls_id, doc_id, doc_type, conf in classifications:
        conn.execute(
            "INSERT OR IGNORE INTO document_classifications "
            "(classification_id, document_id, document_type, confidence, classified_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (cls_id, doc_id, doc_type, conf, now),
        )

    labels = [
        ("lbl-001", "doc-synthetic-001", "공사명", "공사명", "PROJECT_NAME", "t_s0_000", 0, 0, 0.91, "label_right"),
        ("lbl-002", "doc-synthetic-001", "현장명", "현장명", "PROJECT_NAME", "t_s0_000", 1, 0, 0.85, "label_right"),
        ("lbl-003", "doc-synthetic-002", "계약금액", "계약금액", "CONTRACT_AMOUNT", "t_s0_001", 0, 0, 0.87, "label_right"),
        ("lbl-004", "doc-synthetic-003", "회사명", "회사명", "COMPANY_NAME", "t_s0_002", 0, 0, 0.90, "label_right"),
    ]
    for lbl_id, doc_id, raw, norm, sem, tbl, row, col, conf, src in labels:
        conn.execute(
            "INSERT OR IGNORE INTO label_occurrences "
            "(occurrence_id, document_id, raw_label, normalized_label, semantic_type,"
            " table_id, row_index, col_index, confidence, source, detected_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (lbl_id, doc_id, raw, norm, sem, tbl, row, col, conf, src, now),
        )

    conn.commit()


def build(db_path: Path, *, fixture_minimal: bool, force: bool, dry_run: bool) -> dict:
    errors = _check_schemas()
    if errors:
        return {"status": "FAIL", "errors": errors}

    if dry_run:
        return {
            "status": "DRY_RUN",
            "db_path": str(db_path),
            "would_create": not db_path.exists(),
            "schema_ok": True,
        }

    if db_path.exists() and not force:
        return {
            "status": "SKIP_EXISTS",
            "db_path": str(db_path),
            "message": "DB already exists. Use --force to recreate.",
        }

    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists() and force:
        db_path.unlink()

    conn = sqlite3.connect(str(db_path))
    try:
        init_db(conn)
        if fixture_minimal:
            _insert_minimal_fixture(conn)
        conn.close()
    except Exception as exc:
        conn.close()
        if db_path.exists():
            db_path.unlink()
        return {"status": "FAIL", "errors": [str(exc)]}

    return {
        "status": "PASS",
        "db_path": str(db_path),
        "fixture_minimal": fixture_minimal,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="HWPX corpus DB 초기화 스크립트",
    )
    parser.add_argument("--fixture-minimal", action="store_true",
                        help="최소 합성 fixture 데이터를 삽입한다")
    parser.add_argument("--dry-run", action="store_true",
                        help="실제 DB 생성 없이 사전 검증만 실행한다")
    parser.add_argument("--force", action="store_true",
                        help="기존 DB가 있을 때 강제 재생성한다")
    args = parser.parse_args()

    db_path = get_db_path()
    result = build(
        db_path,
        fixture_minimal=args.fixture_minimal,
        force=args.force,
        dry_run=args.dry_run,
    )

    status = result["status"]
    print(f"[build_corpus_db] {status}")
    for k, v in result.items():
        if k != "status":
            print(f"  {k}: {v}")

    return 0 if status in ("PASS", "DRY_RUN", "SKIP_EXISTS") else 1


if __name__ == "__main__":
    sys.exit(main())
