"""HWPX-RECOGNITION-CORPUS-DB-SCHEMA-CONTRACT-01 — schema gate audit."""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

OUTPUT_DIR = PROJECT_ROOT / "reports" / "hwpx_recognition_corpus_schema_audit"


def run_audit() -> dict:
    from scripts.hwpx.recognition_corpus import corpus_schema as cs

    findings: list[dict] = []

    # 1) schema SQL 존재
    sql_path = cs.INIT_SQL_PATH
    findings.append({
        "check": "schema_sql_present",
        "ok": sql_path.is_file(),
        "detail": str(sql_path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
    })

    # 2~4) in-memory DB로 schema 검증
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        cs.init_db(conn)
        v = cs.validate_schema(conn)
        findings.append({
            "check": "required_tables_present",
            "ok": not v["missing_tables"],
            "detail": f"missing={v['missing_tables']}",
        })
        findings.append({
            "check": "required_views_present",
            "ok": not v["missing_views"],
            "detail": f"missing={v['missing_views']}",
        })
        findings.append({
            "check": "foreign_keys_enforced",
            "ok": v["foreign_keys_enabled"],
            "detail": f"fk={v['foreign_keys_enabled']}",
        })

        # 5) enum validators 동작
        findings.append({
            "check": "enum_validators_reject_invalid",
            "ok": (not cs.is_allowed_semantic_type("NOT_A_TYPE")
                    and cs.is_allowed_semantic_type("PROJECT_NAME")),
            "detail": "spot check",
        })

        # 6) promotion gate helper — human approval 없으면 BLOCKED
        allowed, reason = cs.can_promote_to_dictionary(
            conn, "신규라벨", "PROJECT_NAME"
        )
        findings.append({
            "check": "promotion_blocked_without_human_approval",
            "ok": (allowed is False
                    and reason == "BLOCKED_NO_HUMAN_APPROVAL"),
            "detail": f"reason={reason}",
        })

        # 7) UNKNOWN 사전 entry 차단
        findings.append({
            "check": "unknown_semantic_blocked_for_dictionary",
            "ok": (not cs.is_dictionary_allowed_semantic("UNKNOWN")
                    and cs.is_dictionary_allowed_semantic("PROJECT_NAME")),
            "detail": "UNKNOWN not in DICTIONARY_ALLOWED_SEMANTICS",
        })

        # 8) dictionary versioning helper — version + entries insert smoke
        try:
            conn.execute(
                "INSERT INTO label_dictionary_versions "
                "(version, built_at, entry_count, source_corpus_sha, approved_by) "
                "VALUES ('audit_v0', 'now', 1, 'sha:audit', 'audit')"
            )
            conn.execute(
                "INSERT INTO label_dictionary_entries "
                "(version, normalized_label, semantic_type) "
                "VALUES ('audit_v0', 'AUDIT_LABEL', 'PROJECT_NAME')"
            )
            findings.append({
                "check": "dictionary_versioning_works",
                "ok": True, "detail": "version+entry insert succeeded",
            })
        except Exception as exc:
            findings.append({
                "check": "dictionary_versioning_works",
                "ok": False, "detail": str(exc),
            })

        # 9) accuracy audit schema
        try:
            conn.execute(
                "INSERT INTO accuracy_audits "
                "(dictionary_version, audit_at, sample_size, precision, recall, f1) "
                "VALUES ('audit_v0', 'now', 100, 0.9, 0.8, 0.85)"
            )
            findings.append({
                "check": "accuracy_audit_schema_works",
                "ok": True, "detail": "insert succeeded",
            })
        except Exception as exc:
            findings.append({
                "check": "accuracy_audit_schema_works",
                "ok": False, "detail": str(exc),
            })
    finally:
        conn.close()

    # 10) production isolation
    iso = cs.audit_production_isolation()
    findings.append({
        "check": "production_modules_do_not_import_corpus_db",
        "ok": iso["ok"],
        "detail": (f"violations={iso['violations']}"
                     if iso["violations"] else "no violations"),
    })

    # 11) gitignore
    gi = cs.audit_gitignore_for_corpus()
    findings.append({
        "check": "gitignore_excludes_corpus_db",
        "ok": gi["ok"],
        "detail": f"missing={gi.get('missing')}",
    })

    # 12) migration checksum
    ck = cs.migration_checksum()
    findings.append({
        "check": "migration_checksum_computable",
        "ok": len(ck["sha256"]) == 64 and ck["byteSize"] > 0,
        "detail": f"sha256={ck['sha256'][:16]} size={ck['byteSize']}",
    })

    summary = {
        "totalChecks": len(findings),
        "passCount": sum(1 for f in findings if f["ok"]),
        "failCount": sum(1 for f in findings if not f["ok"]),
        "findings": findings,
        "auditVerdict": "PASS" if all(f["ok"] for f in findings) else "FAIL",
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "audit.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    return summary


if __name__ == "__main__":
    print("[HWPX-RECOGNITION-CORPUS-DB-SCHEMA-CONTRACT-01 GATE AUDIT]")
    r = run_audit()
    for f in r["findings"]:
        flag = "PASS" if f["ok"] else "FAIL"
        print(f"  {flag} {f['check']}: {f['detail']}")
    print("=" * 60)
    print(f"verdict: {r['auditVerdict']}  pass={r['passCount']}/{r['totalChecks']}")
    sys.exit(0 if r["auditVerdict"] == "PASS" else 1)
