"""HWPX-FILL-REVIEW-AUDIT-AND-LEARNING-LOG-CONTRACT-01 — operations audit.

PASS / WARN / FAIL 보고. writer 미호출, output HWPX 미생성, AI/OCR 미호출.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))


def run_audit() -> dict:
    from scripts.hwpx.recognition_corpus import corpus_schema as cs
    from scripts.hwpx.recognition_corpus import (
        audit_learning_log_contract as al,
    )

    findings: list[dict] = []

    def add(check: str, ok: bool, detail: object = "",
              level: str = "FAIL") -> None:
        findings.append({
            "check": check,
            "status": "PASS" if ok else level,
            "ok": bool(ok),
            "detail": detail,
        })

    # 1. migration file
    mig = PROJECT_ROOT / "scripts/hwpx/recognition_corpus/schema/002_audit_learning_logs.sql"
    add("002_migration_exists", mig.is_file(), str(mig.relative_to(PROJECT_ROOT)))

    # 2. log contract module
    mod = PROJECT_ROOT / "scripts/hwpx/recognition_corpus/audit_learning_log_contract.py"
    add("log_contract_module_exists", mod.is_file(),
          str(mod.relative_to(PROJECT_ROOT)))

    # in-memory schema
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    cs.init_db(conn)
    al.init_audit_learning_log_schema(conn)

    # 3. tables present
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    missing_t = [t for t in al.REQUIRED_LOG_TABLES if t not in tables]
    add("6_log_tables_present", not missing_t,
          {"missing": missing_t, "required": list(al.REQUIRED_LOG_TABLES)})

    # 4. views present
    views = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='view'")}
    missing_v = [v for v in al.REQUIRED_LOG_VIEWS if v not in views]
    add("5_log_views_present", not missing_v,
          {"missing": missing_v, "required": list(al.REQUIRED_LOG_VIEWS)})

    # 5. setCellParagraphText forbidden via CHECK
    try:
        conn.execute(
            "INSERT INTO fill_review_sessions "
            "(session_id, document_id, source_document_hash,"
            " started_at, session_status) "
            "VALUES ('s_audit','d','h','t','REVIEW_STARTED')"
        )
        try:
            conn.execute(
                "INSERT INTO fill_review_writer_operation_logs ("
                "session_id, operation_type, target_type, target_key,"
                " expected_before_hash, operation_status, created_at"
                ") VALUES ('s_audit','setCellParagraphText','CELL','tk',"
                "'h','CREATED','t')"
            )
            add("setCellParagraphText_forbidden", False, "CHECK did not block")
        except sqlite3.IntegrityError:
            add("setCellParagraphText_forbidden", True, "blocked by CHECK")
        conn.execute("DELETE FROM fill_review_sessions WHERE session_id='s_audit'")
    except Exception as e:  # pragma: no cover
        add("setCellParagraphText_forbidden", False, str(e))

    # 6. sensitive raw value validation
    try:
        al.validate_no_sensitive_raw_values({"phone_text": "010-1234-5678"})
        add("sensitive_value_blocked", False, "phone not blocked")
    except ValueError:
        add("sensitive_value_blocked", True, "phone blocked")

    try:
        al.validate_no_sensitive_raw_values({"proposed_value": "X"})
        add("raw_proposed_value_blocked", False, "raw proposed_value not blocked")
    except ValueError:
        add("raw_proposed_value_blocked", True, "raw proposed_value blocked")

    # 7. reusable signal condition
    sigs = al.build_learning_signal_records([{
        "session_id": "x", "document_id": "d",
        "document_type": None, "sub_type": None,
        "normalized_label": "공사명", "semantic_type": "PROJECT_NAME",
        "target_type": "CELL", "target_pattern": "p",
        "decision": "APPROVE", "decision_source": "USER",
        "writer_status": "APPLIED", "readback_status": "MATCHED",
        "target_key": "tk", "created_at": "t",
    }])
    add("reusable_signal_full_success", sigs[0]["reusable"] == 1,
          {"reusable": sigs[0]["reusable"]})

    sigs2 = al.build_learning_signal_records([{
        "session_id": "x", "document_id": "d",
        "document_type": None, "sub_type": None,
        "normalized_label": "공사명", "semantic_type": "PROJECT_NAME",
        "target_type": "CELL", "target_pattern": "p",
        "decision": "APPROVE", "decision_source": "USER",
        "writer_status": "APPLIED", "readback_status": "MISMATCH",
        "target_key": "tk", "created_at": "t",
    }])
    add("readback_mismatch_blocks_reuse", sigs2[0]["reusable"] == 0,
          {"blocked_reason": sigs2[0]["blocked_reason"]})

    # 8. production isolation
    iso = al.audit_log_contract_isolation()
    add("production_import_isolation", iso["ok"], iso)

    # 9. no writer / output / AI / OCR / secret in module
    src = mod.read_text(encoding="utf-8")
    bad_writer = ("GenericEditPlanWriter", "writer_executor",
                    "writer_adapter")
    add("no_writer_invocation_in_module",
          not any(n in src for n in bad_writer),
          {"checked": bad_writer})
    bad_ai = ("anthropic", "openai", "tesseract",
                "ANTHROPIC_API_KEY")
    add("no_ai_ocr_in_module",
          not any(n in src for n in bad_ai),
          {"checked": bad_ai})
    bad_secret = ("DATABASE_URL", "password=", "haehan-ai.pem")
    add("no_secret_in_module",
          not any(n in src for n in bad_secret),
          {"checked": bad_secret})

    # 10. gitignore
    gi = (PROJECT_ROOT / ".gitignore").read_text(
        encoding="utf-8", errors="ignore")
    add("gitignore_corpus_protected",
          "data/recognition_corpus/*.sqlite3" in gi
          and "data/recognition_corpus/exports/" in gi,
          {"contains_sqlite_rule":
              "data/recognition_corpus/*.sqlite3" in gi,
            "contains_exports_rule":
              "data/recognition_corpus/exports/" in gi})

    # 11. previous corpus contract still loadable
    try:
        from scripts.hwpx.recognition_corpus import (
            label_promotion_review_batch, label_promotion_gate,
            content_classifier, corpus_schema,
        )
        _ = (label_promotion_review_batch, label_promotion_gate,
                content_classifier, corpus_schema)
        add("previous_corpus_modules_loadable", True, "ok")
    except Exception as e:  # pragma: no cover
        add("previous_corpus_modules_loadable", False, str(e))

    # 12. fill_review live pipeline import compat
    try:
        from scripts.hwpx.fill_review import fill_review_live_pipeline  # noqa
        add("fill_review_live_pipeline_compat", True, "ok")
    except Exception as e:  # pragma: no cover
        add("fill_review_live_pipeline_compat", False, str(e))

    fails = [f for f in findings if f["status"] == "FAIL"]
    warns = [f for f in findings if f["status"] == "WARN"]
    summary = {
        "verdict": ("PASS" if not fails else ("WARN" if not fails and warns
                                                    else "FAIL")),
        "total": len(findings),
        "pass": sum(1 for f in findings if f["status"] == "PASS"),
        "warn": len(warns),
        "fail": len(fails),
    }
    return {
        "auditName": "HWPX-FILL-REVIEW-AUDIT-AND-LEARNING-LOG-CONTRACT-01",
        "migration002": al.migration_002_checksum(),
        "summary": summary,
        "findings": findings,
    }


def main() -> int:
    report = run_audit()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["summary"]["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
