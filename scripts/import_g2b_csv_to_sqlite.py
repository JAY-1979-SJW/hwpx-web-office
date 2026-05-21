"""
import_g2b_csv_to_sqlite.py — CSV → SQLite g2b_price 테이블 로더

기능:
  - g2b_price_full.csv → SQLite standard_price.db 적재
  - PRIMARY KEY(prdct_idnt_no, notice_date) 기준 UPSERT
  - duplicate key count 계산 및 보고
  - dry-run mode (temp SQLite만 사용)
  - collect_log 자동 기록
  - 보안: secret/API 호출 없음

사용:
  python import_g2b_csv_to_sqlite.py \
    --input-csv "<CSV_PATH>" \
    --sqlite-path "data/standard_price.db" \
    --dry-run

옵션:
  --input-csv PATH       CSV 파일 경로 (필수)
  --sqlite-path PATH     SQLite 타겟 (기본: data/standard_price.db)
  --dry-run              temp SQLite 검증 (write 없음)
  --limit N              첫 N행만 로드 (테스트)
  --collect-log          collect_log 기록 (기본: off)
  --report-path PATH     결과 보고서 경로 (선택)
"""

import argparse
import csv
import os
import sqlite3
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Tuple


class CSVToSQLiteImporter:
    """CSV to SQLite importer with UPSERT support."""

    # DDL columns
    COLUMNS = (
        "prdct_clsfc_no", "prdct_nm", "prdct_idnt_no", "unit", "price",
        "delivery_cond", "supply_region", "dept_nm", "officer_nm", "officer_tel",
        "notice_date", "vat_type", "biz_div", "work_type",
    )

    DDL_G2B_PRICE = """
    CREATE TABLE IF NOT EXISTS g2b_price (
        prdct_clsfc_no  TEXT,
        prdct_nm        TEXT,
        prdct_idnt_no   TEXT        NOT NULL,
        unit            TEXT,
        price           REAL,
        delivery_cond   TEXT,
        supply_region   TEXT,
        dept_nm         TEXT,
        officer_nm      TEXT,
        officer_tel     TEXT,
        notice_date     TEXT        NOT NULL,
        vat_type        TEXT,
        biz_div         TEXT,
        work_type       TEXT,
        fetched_at      TEXT        NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now')),
        PRIMARY KEY (prdct_idnt_no, notice_date)
    )
    """

    DDL_COLLECT_LOG = """
    CREATE TABLE IF NOT EXISTS collect_log (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        run_at      TEXT,
        category    TEXT,
        total_api   INTEGER,
        inserted    INTEGER,
        updated     INTEGER,
        status      TEXT,
        note        TEXT
    )
    """

    def __init__(self, csv_path: str, sqlite_path: str, dry_run: bool = True, limit: Optional[int] = None):
        """Initialize importer."""
        self.csv_path = Path(csv_path)
        self.sqlite_path = Path(sqlite_path) if not dry_run else None
        self.dry_run = dry_run
        self.limit = limit

        # Statistics
        self.input_rows = 0
        self.inserted = 0
        self.updated = 0
        self.skipped = 0
        self.unique_keys = set()
        self.duplicate_keys = []
        self.errors = []

        if not self.csv_path.exists():
            raise FileNotFoundError(f"CSV not found: {self.csv_path}")

    def validate_csv_header(self) -> bool:
        """Validate CSV header matches expected columns."""
        try:
            with open(self.csv_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                header = next(reader)

            if len(header) != len(self.COLUMNS):
                self.errors.append(f"Header count mismatch: {len(header)} vs {len(self.COLUMNS)}")
                return False

            if tuple(header) != self.COLUMNS:
                self.errors.append(f"Header mismatch: {header} vs {self.COLUMNS}")
                return False

            return True
        except Exception as e:
            self.errors.append(f"CSV validation error: {e}")
            return False

    def load_csv(self, conn: sqlite3.Connection) -> bool:
        """Load CSV into SQLite with UPSERT."""
        try:
            cur = conn.cursor()

            # Create tables
            cur.execute(self.DDL_G2B_PRICE)
            cur.execute(self.DDL_COLLECT_LOG)
            conn.commit()

            # Read and insert rows
            with open(self.csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)

                for row_num, row in enumerate(reader, start=1):
                    if self.limit and row_num > self.limit:
                        break

                    self.input_rows += 1

                    # Extract key
                    key = (row.get("prdct_idnt_no", "").strip(), row.get("notice_date", "").strip())

                    # Validate key
                    if not key[0] or not key[1]:
                        self.skipped += 1
                        self.errors.append(f"Row {row_num}: missing key (prdct_idnt_no or notice_date)")
                        continue

                    # Check for duplicates
                    if key in self.unique_keys:
                        self.duplicate_keys.append(key)
                    else:
                        self.unique_keys.add(key)

                    # Prepare row for insertion
                    values = tuple(row.get(col, "").strip() or None for col in self.COLUMNS)

                    # REPLACE INTO (SQLite handles UPSERT)
                    placeholders = ",".join(["?"] * len(self.COLUMNS))
                    cols = ",".join(self.COLUMNS)

                    try:
                        cur.execute(f"REPLACE INTO g2b_price ({cols}) VALUES ({placeholders})", values)
                        self.inserted += 1
                    except Exception as e:
                        self.skipped += 1
                        self.errors.append(f"Row {row_num}: insert error: {e}")

            conn.commit()
            return True

        except Exception as e:
            self.errors.append(f"CSV load error: {e}")
            return False

    def record_collect_log(self, conn: sqlite3.Connection, note: str = ""):
        """Record collection in collect_log (for temp SQLite only)."""
        try:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO collect_log (run_at, category, total_api, inserted, updated, status, note)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.now().isoformat(),
                    "CSV_IMPORT",
                    self.input_rows,
                    len(self.unique_keys),  # inserted = unique keys
                    len(self.duplicate_keys),  # updated = duplicates (REPLACE)
                    "PASS" if not self.errors else "WARN",
                    note or f"CSV import: {self.input_rows} input → {len(self.unique_keys)} unique"
                )
            )
            conn.commit()
        except Exception as e:
            self.errors.append(f"collect_log error: {e}")

    def run(self) -> bool:
        """Run importer."""
        # Validate CSV
        if not self.validate_csv_header():
            return False

        # Determine database path
        if self.dry_run:
            db_path = tempfile.NamedTemporaryFile(delete=False, suffix=".db").name
        else:
            db_path = str(self.sqlite_path)

        try:
            # Connect to database
            conn = sqlite3.connect(db_path)

            # Load CSV
            if not self.load_csv(conn):
                return False

            # Record log
            self.record_collect_log(conn, f"dry_run={self.dry_run}")

            # Query final state
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM g2b_price")
            final_rows = cur.fetchone()[0]

            # Cleanup
            conn.close()

            if self.dry_run:
                os.unlink(db_path)

            # Report
            self.print_report(final_rows)
            return True

        except Exception as e:
            self.errors.append(f"Run error: {e}")
            return False

    def print_report(self, final_rows: int):
        """Print import report."""
        print("\n" + "=" * 80)
        print("CSV TO SQLITE IMPORT REPORT")
        print("=" * 80)

        print(f"\n📊 통계")
        print(f"  입력 행: {self.input_rows:,}")
        print(f"  고유 key: {len(self.unique_keys):,}")
        print(f"  중복 key: {len(self.duplicate_keys):,}")
        print(f"  최종 행: {final_rows:,}")

        print(f"\n📋 처리 결과")
        print(f"  Inserted: {self.inserted:,}")
        print(f"  Skipped: {self.skipped:,}")

        if self.duplicate_keys:
            print(f"\n⚠️ 중복 key 샘플 (최대 20건)")
            for i, key in enumerate(self.duplicate_keys[:20]):
                print(f"  {i+1}. {key}")

        if self.errors:
            print(f"\n❌ 에러 ({len(self.errors)}건)")
            for i, err in enumerate(self.errors[:10]):
                print(f"  {i+1}. {err}")

        status = "✅ PASS" if not self.errors and len(self.unique_keys) == final_rows else "⚠️ WARN"
        print(f"\n상태: {status}")
        print("=" * 80)


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="CSV to SQLite g2b_price importer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Temp SQLite dry-run (100 rows)
  python import_g2b_csv_to_sqlite.py --input-csv g2b_price_full.csv --dry-run --limit 100

  # Temp SQLite dry-run (full)
  python import_g2b_csv_to_sqlite.py --input-csv g2b_price_full.csv --dry-run

  # Actual load
  python import_g2b_csv_to_sqlite.py --input-csv g2b_price_full.csv --sqlite-path data/standard_price.db
        """
    )

    parser.add_argument("--input-csv", required=True, help="CSV 파일 경로")
    parser.add_argument("--sqlite-path", default="data/standard_price.db", help="SQLite DB 경로")
    parser.add_argument("--dry-run", action="store_true", help="Temp SQLite에서만 검증")
    parser.add_argument("--limit", type=int, help="첫 N행만 로드 (테스트)")
    parser.add_argument("--collect-log", action="store_true", help="collect_log 기록")
    parser.add_argument("--report-path", help="보고서 저장 경로")

    args = parser.parse_args()

    # Create importer
    importer = CSVToSQLiteImporter(
        csv_path=args.input_csv,
        sqlite_path=args.sqlite_path,
        dry_run=args.dry_run,
        limit=args.limit
    )

    # Run
    success = importer.run()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
