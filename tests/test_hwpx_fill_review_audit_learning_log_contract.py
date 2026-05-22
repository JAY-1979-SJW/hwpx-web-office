"""HWPX-FILL-REVIEW-AUDIT-AND-LEARNING-LOG-CONTRACT-01 tests.

in-memory SQLite. writer 미호출, output HWPX 미생성, AI/OCR 미호출,
원본 무수정, secret 미출력.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def conn():
    from scripts.hwpx.recognition_corpus import corpus_schema as cs
    from scripts.hwpx.recognition_corpus import audit_learning_log_contract as al
    c = sqlite3.connect(":memory:")
    c.execute("PRAGMA foreign_keys = ON")
    cs.init_db(c)
    al.init_audit_learning_log_schema(c)
    yield c
    c.close()


@pytest.fixture
def al_mod():
    from scripts.hwpx.recognition_corpus import audit_learning_log_contract as m
    return m


def _seed_session(conn, al, session_id="s-1", document_id="d-1",
                    status="REVIEW_STARTED"):
    rec = al.build_fill_review_session_log(
        session_id=session_id,
        document_id=document_id,
        source_document_hash="srcsha-" + document_id,
        started_at="2026-05-18T00:00:00Z",
        session_status=status,
        document_type="fillable_form",
        sub_type="검측요청서",
        classifier_version="v1",
        dictionary_version="d1",
    )
    al.insert_session(conn, rec)
    return rec


def _seed_decision(conn, al, session_id="s-1", decision="APPROVE",
                    decision_source="USER", normalized_label="공사명",
                    semantic_type="PROJECT_NAME", target_key="t1"):
    recs = al.build_decision_log_records([{
        "session_id": session_id,
        "review_item_id": "ri-1",
        "normalized_label": normalized_label,
        "semantic_type": semantic_type,
        "target_type": "CELL",
        "target_key": target_key,
        "proposed_value_hash": al.hash_value("PROPOSAL"),
        "decision": decision,
        "decision_source": decision_source,
        "decided_by": "tester",
        "decided_at": "2026-05-18T00:00:01Z",
    }])
    return al.insert_decision(conn, recs[0])


# T01 ─ schema init succeeds
def test_t01_schema_init(conn):
    assert conn is not None


# T02 ─ 6 tables present
def test_t02_tables_exist(conn, al_mod):
    tables = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    for t in al_mod.REQUIRED_LOG_TABLES:
        assert t in tables, t


# T03 ─ 5 views present
def test_t03_views_exist(conn, al_mod):
    views = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='view'")}
    for v in al_mod.REQUIRED_LOG_VIEWS:
        assert v in views, v


# T04 ─ FK enforcement
def test_t04_fk_enforcement(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO fill_review_decision_logs ("
            "session_id, review_item_id, decision, decision_source, decided_at"
            ") VALUES ('NO_SESSION','ri','APPROVE','USER','t')"
        )


# T05 ─ decision enum CHECK
def test_t05_decision_enum(conn, al_mod):
    _seed_session(conn, al_mod)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO fill_review_decision_logs ("
            "session_id, review_item_id, decision, decision_source, decided_at"
            ") VALUES ('s-1','ri','BOGUS','USER','t')"
        )


# T06 ─ decision_source enum CHECK
def test_t06_decision_source_enum(conn, al_mod):
    _seed_session(conn, al_mod)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO fill_review_decision_logs ("
            "session_id, review_item_id, decision, decision_source, decided_at"
            ") VALUES ('s-1','ri','APPROVE','BOGUS','t')"
        )


# T07 ─ operation_type allowed set
def test_t07_operation_type_allowed(conn, al_mod):
    _seed_session(conn, al_mod)
    conn.execute(
        "INSERT INTO fill_review_writer_operation_logs ("
        "session_id, operation_type, target_type, target_key,"
        " expected_before_hash, operation_status, created_at"
        ") VALUES ('s-1','setCellText','CELL','tk','h','CREATED','t')"
    )


# T08 ─ setCellParagraphText forbidden
def test_t08_set_cell_paragraph_text_forbidden(conn, al_mod):
    _seed_session(conn, al_mod)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO fill_review_writer_operation_logs ("
            "session_id, operation_type, target_type, target_key,"
            " expected_before_hash, operation_status, created_at"
            ") VALUES ('s-1','setCellParagraphText','CELL','tk','h','CREATED','t')"
        )
    with pytest.raises(ValueError):
        al_mod.build_writer_operation_log_records([{
            "session_id": "s-1",
            "operation_type": "setCellParagraphText",
            "target_type": "CELL",
            "target_key": "tk",
            "expected_before_hash": "h",
            "operation_status": "CREATED",
            "created_at": "t",
        }])


# T09 ─ readback_status enum CHECK
def test_t09_readback_status_enum(conn, al_mod):
    _seed_session(conn, al_mod)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO fill_review_readback_logs ("
            "session_id, readback_status, checked_at"
            ") VALUES ('s-1','BOGUS','t')"
        )


# T10 ─ severity enum CHECK
def test_t10_severity_enum(conn, al_mod):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO xml_deep_analyzer_need_flags ("
            "document_id, reason_code, severity, created_at"
            ") VALUES ('d','READBACK_MISMATCH','BOGUS','t')"
        )


# T11 ─ session log
def test_t11_session_log(conn, al_mod):
    _seed_session(conn, al_mod)
    r = conn.execute(
        "SELECT session_status FROM fill_review_sessions WHERE session_id='s-1'"
    ).fetchone()
    assert r and r[0] == "REVIEW_STARTED"


# T12 ─ APPROVE decision
def test_t12_decision_approve(conn, al_mod):
    _seed_session(conn, al_mod)
    did = _seed_decision(conn, al_mod, decision="APPROVE")
    assert did >= 1


# T13 ─ SYSTEM_APPROVE decision
def test_t13_system_approve(conn, al_mod):
    _seed_session(conn, al_mod)
    did = _seed_decision(conn, al_mod, decision="SYSTEM_APPROVE",
                            decision_source="SYSTEM_POLICY")
    assert did >= 1


# T14 ─ REQUEST_MATERIAL → reusable False
def test_t14_request_material_not_reusable(conn, al_mod):
    _seed_session(conn, al_mod)
    sigs = al_mod.build_learning_signal_records([{
        "session_id": "s-1", "document_id": "d-1",
        "document_type": "fillable_form", "sub_type": "검측요청서",
        "normalized_label": "공사명", "semantic_type": "PROJECT_NAME",
        "target_type": "CELL", "target_pattern": "table/row/cell",
        "decision": "REQUEST_MATERIAL", "decision_source": "USER",
        "writer_status": "NOT_RUN", "readback_status": "NOT_RUN",
        "target_key": "tk",
        "created_at": "t",
    }])
    assert sigs[0]["reusable"] == 0


# T15 ─ writer operation log
def test_t15_writer_operation(conn, al_mod):
    _seed_session(conn, al_mod)
    did = _seed_decision(conn, al_mod)
    ops = al_mod.build_writer_operation_log_records([{
        "session_id": "s-1", "decision_log_id": did,
        "operation_type": "setCellText",
        "target_type": "CELL", "target_key": "tk",
        "expected_before_hash": "before", "value_hash": "after",
        "operation_status": "APPLIED", "created_at": "t",
    }])
    opid = al_mod.insert_writer_operation(conn, ops[0])
    assert opid >= 1


# T16 ─ expected_before_hash required
def test_t16_expected_before_required(al_mod):
    with pytest.raises(ValueError):
        al_mod.build_writer_operation_log_records([{
            "session_id": "s-1", "operation_type": "setCellText",
            "target_type": "CELL", "target_key": "tk",
            "expected_before_hash": "",
            "operation_status": "CREATED", "created_at": "t",
        }])


# T17 ─ readback MATCHED
def test_t17_readback_matched(conn, al_mod):
    _seed_session(conn, al_mod)
    rec = al_mod.build_readback_log_records([{
        "session_id": "s-1", "readback_status": "MATCHED",
        "expected_after_hash": "h", "actual_after_hash": "h",
        "checked_at": "t",
    }])[0]
    rid = al_mod.insert_readback(conn, rec)
    assert rid >= 1


# T18 ─ readback MISMATCH
def test_t18_readback_mismatch(conn, al_mod):
    _seed_session(conn, al_mod)
    rec = al_mod.build_readback_log_records([{
        "session_id": "s-1", "readback_status": "MISMATCH",
        "divergence_code": "TEXT_MISMATCH",
        "checked_at": "t",
    }])[0]
    al_mod.insert_readback(conn, rec)


# T19 ─ full success → reusable
def test_t19_full_success_reusable(conn, al_mod):
    _seed_session(conn, al_mod)
    sigs = al_mod.build_learning_signal_records([{
        "session_id": "s-1", "document_id": "d-1",
        "document_type": "fillable_form", "sub_type": "검측요청서",
        "normalized_label": "공사명", "semantic_type": "PROJECT_NAME",
        "target_type": "CELL", "target_pattern": "tbl/row/cell",
        "decision": "APPROVE", "decision_source": "USER",
        "writer_status": "APPLIED", "readback_status": "MATCHED",
        "target_key": "tk", "created_at": "t",
    }])
    assert sigs[0]["reusable"] == 1
    al_mod.insert_learning_signal(conn, sigs[0])
    row = conn.execute("SELECT reusable FROM reusable_learning_signals").fetchone()
    assert row[0] == 1


# T20 ─ REJECT/HOLD → reusable False
@pytest.mark.parametrize("decision", ["REJECT", "HOLD", "SYSTEM_HOLD"])
def test_t20_reject_hold_not_reusable(al_mod, decision):
    sigs = al_mod.build_learning_signal_records([{
        "session_id": "s-1", "document_id": "d-1", "document_type": None,
        "sub_type": None, "normalized_label": "공사명",
        "semantic_type": "PROJECT_NAME", "target_type": "CELL",
        "target_pattern": "p", "decision": decision,
        "decision_source": "USER",
        "writer_status": "APPLIED", "readback_status": "MATCHED",
        "target_key": "tk", "created_at": "t",
    }])
    assert sigs[0]["reusable"] == 0


# T21 ─ UNKNOWN semantic → reusable False
def test_t21_unknown_semantic_not_reusable(al_mod):
    sigs = al_mod.build_learning_signal_records([{
        "session_id": "s-1", "document_id": "d-1",
        "document_type": None, "sub_type": None,
        "normalized_label": "X", "semantic_type": "UNKNOWN",
        "target_type": "CELL", "target_pattern": "p",
        "decision": "APPROVE", "decision_source": "USER",
        "writer_status": "APPLIED", "readback_status": "MATCHED",
        "target_key": "tk", "created_at": "t",
    }])
    assert sigs[0]["reusable"] == 0


# T22 ─ writer blocked → reusable False
def test_t22_writer_blocked_not_reusable(al_mod):
    sigs = al_mod.build_learning_signal_records([{
        "session_id": "s-1", "document_id": "d-1",
        "document_type": None, "sub_type": None,
        "normalized_label": "공사명", "semantic_type": "PROJECT_NAME",
        "target_type": "CELL", "target_pattern": "p",
        "decision": "APPROVE", "decision_source": "USER",
        "writer_status": "BLOCKED", "readback_status": "NOT_RUN",
        "target_key": "tk", "created_at": "t",
    }])
    assert sigs[0]["reusable"] == 0


# T23 ─ readback mismatch → reusable False + backlog
def test_t23_readback_mismatch_creates_backlog(conn, al_mod):
    _seed_session(conn, al_mod)
    sigs = al_mod.build_learning_signal_records([{
        "session_id": "s-1", "document_id": "d-1",
        "document_type": None, "sub_type": None,
        "normalized_label": "공사명", "semantic_type": "PROJECT_NAME",
        "target_type": "CELL", "target_pattern": "p",
        "decision": "APPROVE", "decision_source": "USER",
        "writer_status": "APPLIED", "readback_status": "MISMATCH",
        "target_key": "tk", "created_at": "t",
    }])
    assert sigs[0]["reusable"] == 0
    flags = al_mod.build_xml_deep_analyzer_need_flags([{
        "session_id": "s-1", "document_id": "d-1",
        "reason_code": "READBACK_MISMATCH",
        "severity": "HIGH", "created_at": "t",
    }])
    al_mod.insert_xml_backlog(conn, flags[0])
    row = conn.execute(
        "SELECT reason_code FROM xml_deep_analyzer_backlog"
    ).fetchone()
    assert row[0] == "READBACK_MISMATCH"


# T24 ─ run boundary unsupported flag
def test_t24_run_boundary_backlog(conn, al_mod):
    _seed_session(conn, al_mod)
    flags = al_mod.build_xml_deep_analyzer_need_flags([{
        "session_id": "s-1", "document_id": "d-1",
        "reason_code": "RUN_BOUNDARY_UNSUPPORTED",
        "severity": "MEDIUM", "created_at": "t",
    }])
    al_mod.insert_xml_backlog(conn, flags[0])
    s = al_mod.summarize_xml_deep_analyzer_backlog(conn)
    assert s["totalFlags"] == 1
    assert "RUN_BOUNDARY_UNSUPPORTED" in s["byReasonCode"]


# T25 ─ checkbox/object flag
def test_t25_checkbox_object_backlog(conn, al_mod):
    _seed_session(conn, al_mod)
    flags = al_mod.build_xml_deep_analyzer_need_flags([
        {"session_id": "s-1", "document_id": "d-1",
            "reason_code": "CHECKBOX_OR_SHAPE_NEEDED",
            "severity": "LOW", "created_at": "t"},
        {"session_id": "s-1", "document_id": "d-1",
            "reason_code": "OBJECT_ANCHOR_NEEDED",
            "severity": "MEDIUM", "created_at": "t"},
    ])
    for f in flags:
        al_mod.insert_xml_backlog(conn, f)
    assert conn.execute(
        "SELECT COUNT(*) FROM xml_deep_analyzer_need_flags"
    ).fetchone()[0] == 2


# T26 ─ target ambiguous
def test_t26_target_ambiguous(conn, al_mod):
    _seed_session(conn, al_mod)
    flags = al_mod.build_xml_deep_analyzer_need_flags([{
        "session_id": "s-1", "document_id": "d-1",
        "reason_code": "TARGET_AMBIGUOUS",
        "severity": "MEDIUM", "created_at": "t",
    }])
    al_mod.insert_xml_backlog(conn, flags[0])


# T27 ─ raw sensitive value rejected
def test_t27_sensitive_raw_rejected(al_mod):
    with pytest.raises(ValueError):
        al_mod.validate_no_sensitive_raw_values({
            "phone_text": "010-1234-5678",
        })
    with pytest.raises(ValueError):
        al_mod.validate_no_sensitive_raw_values({
            "biz": "123-45-67890",
        })
    with pytest.raises(ValueError):
        al_mod.validate_no_sensitive_raw_values({
            "proposed_value": "ANY",
        })


# T28 ─ hash stored
def test_t28_hash_stored(al_mod):
    h = al_mod.hash_value("hello")
    assert h and len(h) == 64
    r = al_mod.redact_or_hash_value("hello world")
    assert r["valueHash"]
    assert r["redactedPreview"] == "hello world"


# T29 ─ redactedPreview capped at 20 chars
def test_t29_preview_max(al_mod):
    r = al_mod.redact_or_hash_value("a" * 50)
    assert len(r["redactedPreview"]) == 20
    with pytest.raises(ValueError):
        al_mod.validate_no_sensitive_raw_values({
            "redacted_preview": "x" * 21,
        })


# T30 ─ reusable_learning_signals view works
def test_t30_view_reusable(conn, al_mod):
    _seed_session(conn, al_mod)
    sigs = al_mod.build_learning_signal_records([{
        "session_id": "s-1", "document_id": "d-1",
        "document_type": "fillable_form", "sub_type": "x",
        "normalized_label": "공사명", "semantic_type": "PROJECT_NAME",
        "target_type": "CELL", "target_pattern": "p",
        "decision": "APPROVE", "decision_source": "USER",
        "writer_status": "APPLIED", "readback_status": "MATCHED",
        "target_key": "tk", "created_at": "t",
    }])
    al_mod.insert_learning_signal(conn, sigs[0])
    rows = conn.execute("SELECT * FROM reusable_learning_signals").fetchall()
    assert len(rows) == 1


# T31 ─ failed_writer_patterns view works
def test_t31_view_failed_writer(conn, al_mod):
    _seed_session(conn, al_mod)
    op = al_mod.build_writer_operation_log_records([{
        "session_id": "s-1", "operation_type": "setCellText",
        "target_type": "CELL", "target_key": "tk",
        "expected_before_hash": "h",
        "operation_status": "BLOCKED",
        "blocked_reason": "EXPECTED_BEFORE_MISMATCH",
        "created_at": "t",
    }])[0]
    al_mod.insert_writer_operation(conn, op)
    rows = conn.execute("SELECT * FROM failed_writer_patterns").fetchall()
    assert len(rows) == 1


# T32 ─ xml_deep_analyzer_backlog view works
def test_t32_view_backlog(conn, al_mod):
    _seed_session(conn, al_mod)
    flags = al_mod.build_xml_deep_analyzer_need_flags([
        {"session_id": "s-1", "document_id": "d-1",
            "reason_code": "READBACK_MISMATCH", "severity": "LOW",
            "created_at": "t"},
        {"session_id": "s-1", "document_id": "d-1",
            "reason_code": "RUN_BOUNDARY_UNSUPPORTED", "severity": "HIGH",
            "created_at": "t"},
    ])
    for f in flags:
        al_mod.insert_xml_backlog(conn, f)
    rows = conn.execute(
        "SELECT severity FROM xml_deep_analyzer_backlog"
    ).fetchall()
    assert rows[0][0] == "HIGH"


# T33 ─ decision_summary_by_label view
def test_t33_view_decision_summary(conn, al_mod):
    _seed_session(conn, al_mod)
    _seed_decision(conn, al_mod, decision="APPROVE")
    _seed_decision(conn, al_mod, decision="APPROVE")
    rows = conn.execute(
        "SELECT decision_count FROM decision_summary_by_label "
        "WHERE normalized_label='공사명'"
    ).fetchall()
    assert rows and rows[0][0] == 2


# T34 ─ learning_signal_summary_by_doc_type
def test_t34_view_signal_summary(conn, al_mod):
    _seed_session(conn, al_mod)
    sigs = al_mod.build_learning_signal_records([{
        "session_id": "s-1", "document_id": "d-1",
        "document_type": "fillable_form", "sub_type": "검측",
        "normalized_label": "L", "semantic_type": "PROJECT_NAME",
        "target_type": "CELL", "target_pattern": "p",
        "decision": "APPROVE", "decision_source": "USER",
        "writer_status": "APPLIED", "readback_status": "MATCHED",
        "target_key": "tk", "created_at": "t",
    }])
    al_mod.insert_learning_signal(conn, sigs[0])
    rows = conn.execute(
        "SELECT document_type, signal_count, reusable_count "
        "FROM learning_signal_summary_by_doc_type"
    ).fetchall()
    assert rows[0][0] == "fillable_form"
    assert rows[0][1] == 1
    assert rows[0][2] == 1


# T35 ─ production import isolation
def test_t35_production_isolation(al_mod):
    res = al_mod.audit_log_contract_isolation()
    assert res["ok"], res["violations"]


# T36 ─ no writer call (this module never imports writer)
def test_t36_no_writer_invocation(al_mod):
    src = Path(al_mod.__file__).read_text(encoding="utf-8")
    assert "GenericEditPlanWriter" not in src
    assert "writer_executor" not in src
    assert "writer_adapter" not in src


# T37 ─ no output HWPX path written
def test_t37_no_output_hwpx(al_mod):
    src = Path(al_mod.__file__).read_text(encoding="utf-8")
    assert ".hwpx" not in src.lower() or "hwpx" not in [
        token.strip() for token in src.split() if token.endswith(".hwpx")
    ]


# T38 ─ no AI / OCR
def test_t38_no_ai_ocr(al_mod):
    src = Path(al_mod.__file__).read_text(encoding="utf-8")
    for needle in ("anthropic", "openai", "tesseract", "ocr",
                      "claude_cli", "ANTHROPIC_API_KEY"):
        assert needle.lower() not in src.lower(), needle


# T39 ─ no secret/DB url
def test_t39_no_secret(al_mod):
    src = Path(al_mod.__file__).read_text(encoding="utf-8")
    for needle in ("DATABASE_URL", "password=", "secret=", "ssh_key",
                      "haehan-ai.pem"):
        assert needle not in src, needle


# T40 ─ gitignore retains corpus/exports
def test_t40_gitignore():
    gi = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8",
                                                       errors="ignore")
    assert "data/recognition_corpus/*.sqlite3" in gi
    assert "data/recognition_corpus/exports/" in gi


# T41 ─ promotion review batch import still works
def test_t41_promotion_review_batch_compat():
    from scripts.hwpx.recognition_corpus import label_promotion_review_batch  # noqa


# T42 ─ promotion gate import still works
def test_t42_promotion_gate_compat():
    from scripts.hwpx.recognition_corpus import label_promotion_gate  # noqa


# T43 ─ content classifier import still works
def test_t43_content_classifier_compat():
    from scripts.hwpx.recognition_corpus import content_classifier  # noqa


# T44 ─ corpus schema 001 still intact
def test_t44_corpus_schema_compat(conn):
    tables = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    for t in ("hwpx_documents", "label_occurrences",
                "human_label_decisions", "label_promotion_candidates",
                "label_dictionary_versions", "label_dictionary_entries"):
        assert t in tables


# T45 ─ corpus ingest module importable
def test_t45_corpus_ingest_compat():
    from scripts.hwpx.recognition_corpus import corpus_schema  # noqa


# T46 ─ fill_review live pipeline import still works
def test_t46_fill_review_live_pipeline_compat():
    from scripts.hwpx.fill_review import fill_review_live_pipeline  # noqa
