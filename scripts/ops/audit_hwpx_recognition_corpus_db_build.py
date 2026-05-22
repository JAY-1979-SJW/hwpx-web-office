"""HWPX-RECOGNITION-CORPUS-DB-BUILD-AND-SKIP-CLOSEOUT-01 — 감사 스크립트.

corpus DB 빌드 공정의 정적/동적 감사를 수행한다.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = PROJECT_ROOT / "scripts" / "hwpx" / "recognition_corpus" / "schema"
BUILD_SCRIPT = PROJECT_ROOT / "scripts" / "hwpx" / "recognition_corpus" / "build_corpus_db.py"
GITIGNORE = PROJECT_ROOT / ".gitignore"

REQUIRED_TABLES = (
    "hwpx_documents", "document_classifications", "label_occurrences",
    "human_label_decisions", "label_promotion_candidates",
    "label_dictionary_versions", "label_dictionary_entries", "accuracy_audits",
)
AUDIT_LOG_TABLES = (
    "fill_review_sessions", "fill_review_decision_logs",
    "fill_review_writer_operation_logs", "fill_review_readback_logs",
    "fill_review_learning_signals", "xml_deep_analyzer_need_flags",
)
PII_PATTERNS = (
    r"\b\d{6}-\d{7}\b",
    r"\b01[016789][-\s]?\d{3,4}[-\s]?\d{4}\b",
    r"\b\d{3}-\d{2}-\d{5}\b",
)
FORBIDDEN_SOURCE_PATTERNS = (
    r"hwpx_write_gate", r"apply_edit_plan", r"hwpx_full_verify",
    r"import anthropic", r"openai", r"ocr",
)


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"name": name, "status": "PASS" if ok else "FAIL", "detail": detail}


def audit() -> dict:
    checks: list[dict] = []

    # A01. schema directory
    checks.append(_check("A01_schema_dir_exists", SCHEMA_DIR.is_dir(), str(SCHEMA_DIR)))

    # A02. 001_init.sql
    checks.append(_check("A02_init_sql_exists", (SCHEMA_DIR / "001_init.sql").is_file()))

    # A03. 002_audit_learning_logs.sql
    checks.append(_check("A03_migration_002_exists", (SCHEMA_DIR / "002_audit_learning_logs.sql").is_file()))

    # A04. build script
    checks.append(_check("A04_build_script_exists", BUILD_SCRIPT.is_file(), str(BUILD_SCRIPT)))

    # A05. dry-run does not create DB
    with tempfile.TemporaryDirectory() as td:
        dry_db = Path(td) / "dry.sqlite3"
        env = os.environ.copy()
        env["HWPX_RECOGNITION_CORPUS_DB"] = str(dry_db)
        r = subprocess.run(
            [sys.executable, str(BUILD_SCRIPT), "--dry-run"],
            capture_output=True, text=True, env=env,
        )
        checks.append(_check("A05_dry_run_no_db_created", not dry_db.exists(),
                             f"returncode={r.returncode}"))

    # A06 + A07 + A08 + A09: fixture-minimal creates DB, tables, no PII
    with tempfile.TemporaryDirectory() as td:
        fx_db = Path(td) / "corpus.sqlite3"
        env = os.environ.copy()
        env["HWPX_RECOGNITION_CORPUS_DB"] = str(fx_db)
        r = subprocess.run(
            [sys.executable, str(BUILD_SCRIPT), "--fixture-minimal"],
            capture_output=True, text=True, env=env,
        )
        db_created = fx_db.is_file()
        checks.append(_check("A06_fixture_minimal_creates_db", db_created,
                             f"returncode={r.returncode} stderr={r.stderr[:200]}"))

        if db_created:
            try:
                conn = sqlite3.connect(str(fx_db))
                tables = {row[0] for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )}

                # A07
                missing_core = [t for t in REQUIRED_TABLES if t not in tables]
                checks.append(_check("A07_required_tables_exist",
                                     not missing_core, str(missing_core)))

                # A08
                missing_audit = [t for t in AUDIT_LOG_TABLES if t not in tables]
                checks.append(_check("A08_audit_log_tables_exist",
                                     not missing_audit, str(missing_audit)))

                # A09: PII scan
                pii_found: list[str] = []
                for row in conn.execute("SELECT source_path, document_id FROM hwpx_documents"):
                    text = " ".join(str(v) for v in row if v)
                    for pattern in PII_PATTERNS:
                        if re.search(pattern, text):
                            pii_found.append(f"pattern={pattern} row={row}")
                checks.append(_check("A09_no_pii_in_fixture", not pii_found,
                                     str(pii_found)))
                conn.close()
            except Exception as exc:
                checks.append(_check("A07_required_tables_exist", False, str(exc)))
                checks.append(_check("A08_audit_log_tables_exist", False, str(exc)))
                checks.append(_check("A09_no_pii_in_fixture", False, str(exc)))
        else:
            for name in ("A07_required_tables_exist", "A08_audit_log_tables_exist",
                         "A09_no_pii_in_fixture"):
                checks.append(_check(name, False, "DB not created"))

    # A10. corpus.sqlite3 not staged for git
    try:
        r = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True, text=True, cwd=str(PROJECT_ROOT),
        )
        staged = r.stdout
        sqlite_staged = any("sqlite3" in line or ".db" in line for line in staged.splitlines())
        checks.append(_check("A10_corpus_sqlite3_not_staged", not sqlite_staged,
                             staged[:200] if sqlite_staged else ""))
    except Exception as exc:
        checks.append(_check("A10_corpus_sqlite3_not_staged", False, str(exc)))

    # A11. original HWPX files unchanged
    try:
        r = subprocess.run(
            ["git", "diff", "--name-only"],
            capture_output=True, text=True, cwd=str(PROJECT_ROOT),
        )
        hwpx_changed = [l for l in r.stdout.splitlines() if l.endswith(".hwpx")]
        checks.append(_check("A11_original_hwpx_unchanged", not hwpx_changed,
                             str(hwpx_changed)))
    except Exception as exc:
        checks.append(_check("A11_original_hwpx_unchanged", False, str(exc)))

    # A12. no writer call in build script
    build_src = BUILD_SCRIPT.read_text(encoding="utf-8") if BUILD_SCRIPT.is_file() else ""
    writer_refs = [p for p in ("hwpx_write_gate", "apply_edit_plan", "hwpx_edit_tool")
                   if p in build_src]
    checks.append(_check("A12_no_writer_call", not writer_refs, str(writer_refs)))

    # A13. no AI API call in build script
    ai_refs = [p for p in ("anthropic", "openai", "ChatCompletion")
               if p in build_src]
    checks.append(_check("A13_no_ai_api_call", not ai_refs, str(ai_refs)))

    # A14. no OCR call
    ocr_refs = [p for p in ("ocr", "tesseract", "easyocr")
                if p.lower() in build_src.lower()]
    checks.append(_check("A14_no_ocr_call", not ocr_refs, str(ocr_refs)))

    # A15. tests pass
    try:
        r = subprocess.run(
            [sys.executable, "-m", "pytest",
             "tests/test_hwpx_recognition_corpus_db_build.py",
             "-q", "--tb=no"],
            capture_output=True, text=True, cwd=str(PROJECT_ROOT),
        )
        tests_ok = r.returncode == 0
        checks.append(_check("A15_tests_pass", tests_ok,
                             (r.stdout + r.stderr)[-300:]))
    except Exception as exc:
        checks.append(_check("A15_tests_pass", False, str(exc)))

    # A16. DB 없음 환경에서 SKIP 유지 (동적 확인)
    with tempfile.TemporaryDirectory() as td:
        missing_db = Path(td) / "nonexistent.sqlite3"
        env = os.environ.copy()
        env["HWPX_RECOGNITION_CORPUS_DB"] = str(missing_db)
        r = subprocess.run(
            [sys.executable, "-m", "pytest",
             "tests/test_web_office_cell_save_hwpx_verify7.py::test_audit_script_returns_pass",
             "-v", "--tb=short"],
            capture_output=True, text=True, cwd=str(PROJECT_ROOT), env=env,
        )
        skip_ok = "skipped" in r.stdout.lower() or r.returncode == 0
        checks.append(_check("A16_no_db_means_skip_not_fail", skip_ok,
                             (r.stdout + r.stderr)[-200:]))

    failed = [c for c in checks if c["status"] != "PASS"]
    verdict = "PASS_HWPX_RECOGNITION_CORPUS_DB_BUILD" if not failed else "FAIL"

    # warn 조건
    warns: list[str] = []
    warns.append("WARN_MINIMAL_FIXTURE_ONLY")
    if not any("hancom" in c["name"].lower() for c in checks):
        warns.append("WARN_HANCOM_NOT_INSTALLED_FALLBACK_ONLY")

    return {
        "verdict": verdict,
        "pass_count": len(checks) - len(failed),
        "fail_count": len(failed),
        "warns": warns,
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = audit()

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"[audit_corpus_db_build] {report['verdict']} "
              f"pass={report['pass_count']} fail={report['fail_count']}")
        for c in report["checks"]:
            mark = "OK" if c["status"] == "PASS" else "FAIL"
            line = f"  [{mark}] {c['name']}"
            if c["status"] != "PASS" and c["detail"]:
                line += f"\n        {c['detail']}"
            print(line)
        for w in report["warns"]:
            print(f"  [WARN] {w}")

    return 0 if report["verdict"].startswith("PASS") else 1


if __name__ == "__main__":
    sys.exit(main())
