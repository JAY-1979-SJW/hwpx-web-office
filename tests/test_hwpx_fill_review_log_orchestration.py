"""HWPX-FILL-REVIEW-LOG-ORCHESTRATION-01 — 감리검사.

in-memory SQLite. deterministic pipeline_result fixture 기반.
writer 미호출, output 미생성, AI/OCR 미호출, secret 미출력.
운영동(production)에서 본 모듈 import 금지 유지.
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
    from scripts.hwpx.recognition_corpus import (
        corpus_schema as cs,
        audit_learning_log_contract as al,
    )
    c = sqlite3.connect(":memory:")
    c.execute("PRAGMA foreign_keys = ON")
    cs.init_db(c)
    al.init_audit_learning_log_schema(c)
    yield c
    c.close()


@pytest.fixture
def orc():
    from scripts.hwpx.orchestration import fill_review_log_recorder as m
    return m


def _base_pipeline_result(status="READY_FOR_REVIEW"):
    return {
        "schemaVersion": "1.0",
        "engineVersion": "0.6.2",
        "requestId": "req-1",
        "documentId": "doc-1",
        "sourceDocumentHash": "srchash-1",
        "pipelineStatus": status,
        "recognitionResult": {"documentType": "fillable_form",
                                "subType": "검측요청서"},
        "fillReview": {
            "reviewItems": [
                {"reviewItemId": "ri-1", "label": "공사명",
                    "semanticType": "PROJECT_NAME",
                    "evidenceRefs": ["ev-1"]},
            ],
        },
        "warnings": [],
        "errors": [],
    }


def _approve_decision():
    return {
        "decisions": [{
            "reviewItemId": "ri-1",
            "label": "공사명",
            "semanticType": "PROJECT_NAME",
            "target": {"targetType": "cell", "cellKey": "t0:r0:c1"},
            "currentValue": "",
            "proposedValue": "○○건축공사",
            "decision": "APPROVE",
            "decisionSource": "USER",
            "decidedBy": "rep",
        }],
    }


def _writer_op_applied():
    return [{
        "op": "setCellText",
        "reviewItemId": "ri-1",
        "target": {"targetType": "cell", "cellKey": "t0:r0:c1"},
        "expectedBeforeHash": "before-hash",
        "value": "○○건축공사",
    }]


# ── T01 sanity ─────────────────────────────────────────────────────────────

def test_t01_contract_name(orc):
    assert orc.CONTRACT_NAME == "HWPX-FILL-REVIEW-LOG-ORCHESTRATION-01"


def test_t02_record_minimal_review_ready(conn, orc):
    res = orc.record_pipeline_result(conn, _base_pipeline_result())
    assert res["sessionStatus"] == "READY_FOR_DECISION"
    assert res["counts"]["decisions"] == 0
    row = conn.execute(
        "SELECT session_status FROM fill_review_sessions"
    ).fetchone()
    assert row[0] == "READY_FOR_DECISION"


def test_t03_session_status_completed(conn, orc):
    res = orc.record_pipeline_result(
        conn, _base_pipeline_result(status="COMPLETED"))
    assert res["sessionStatus"] == "COMPLETED"


def test_t04_session_status_error_when_errors(conn, orc):
    pr = _base_pipeline_result()
    pr["errors"] = [{"code": "X"}]
    res = orc.record_pipeline_result(conn, pr)
    assert res["sessionStatus"] == "ERROR"


# ── T10 decision 기록 ──────────────────────────────────────────────────────

def test_t10_approve_decision_recorded(conn, orc):
    res = orc.record_pipeline_result(
        conn, _base_pipeline_result(),
        decision_payload=_approve_decision())
    assert res["counts"]["decisions"] == 1
    row = conn.execute(
        "SELECT decision, normalized_label FROM fill_review_decision_logs"
    ).fetchone()
    assert row[0] == "APPROVE"
    assert row[1] == "공사명"


def test_t11_proposed_value_hashed_not_raw(conn, orc):
    res = orc.record_pipeline_result(
        conn, _base_pipeline_result(),
        decision_payload=_approve_decision())
    row = conn.execute(
        "SELECT proposed_value_hash FROM fill_review_decision_logs"
    ).fetchone()
    h = row[0]
    assert h and len(h) == 64
    assert "○○건축공사" not in h


def test_t12_unknown_decision_skipped(conn, orc):
    dp = _approve_decision()
    dp["decisions"][0]["decision"] = "BOGUS"
    res = orc.record_pipeline_result(
        conn, _base_pipeline_result(), decision_payload=dp)
    assert res["counts"]["decisions"] == 0


# ── T20 writer operation ──────────────────────────────────────────────────

def test_t20_writer_op_applied(conn, orc):
    pr = _base_pipeline_result(status="WRITER_APPLIED")
    pr["approvedEditPlan"] = {"operations": _writer_op_applied()}
    pr["writerResult"] = {"operationResults": [{"status": "APPLIED"}]}
    res = orc.record_pipeline_result(
        conn, pr, decision_payload=_approve_decision())
    assert res["counts"]["writerOps"] == 1
    row = conn.execute(
        "SELECT operation_type, operation_status "
        "FROM fill_review_writer_operation_logs"
    ).fetchone()
    assert row[0] == "setCellText"
    assert row[1] == "APPLIED"


def test_t21_writer_op_blocked(conn, orc):
    pr = _base_pipeline_result(status="WRITER_BLOCKED")
    pr["approvedEditPlan"] = {"operations": _writer_op_applied()}
    pr["writerResult"] = {"operationResults": [
        {"status": "BLOCKED", "blockedReason": "EXPECTED_BEFORE_MISMATCH"}]}
    res = orc.record_pipeline_result(
        conn, pr, decision_payload=_approve_decision())
    row = conn.execute(
        "SELECT operation_status, blocked_reason "
        "FROM fill_review_writer_operation_logs"
    ).fetchone()
    assert row[0] == "BLOCKED"
    assert row[1] == "EXPECTED_BEFORE_MISMATCH"


def test_t22_forbidden_op_type_rejected(conn, orc):
    pr = _base_pipeline_result(status="WRITER_APPLIED")
    pr["approvedEditPlan"] = {"operations": [{
        "op": "setCellParagraphText",
        "reviewItemId": "ri-1",
        "target": {"cellKey": "x"},
        "expectedBeforeHash": "h",
    }]}
    pr["writerResult"] = {"operationResults": [{"status": "APPLIED"}]}
    with pytest.raises(ValueError):
        orc.record_pipeline_result(
            conn, pr, decision_payload=_approve_decision())


# ── T30 readback ──────────────────────────────────────────────────────────

def test_t30_readback_matched(conn, orc):
    pr = _base_pipeline_result(status="COMPLETED")
    pr["approvedEditPlan"] = {"operations": _writer_op_applied()}
    pr["writerResult"] = {"operationResults": [{"status": "APPLIED"}]}
    pr["readback"] = {"operationResults": [
        {"status": "MATCHED", "expectedAfterHash": "h", "actualAfterHash": "h"}]}
    res = orc.record_pipeline_result(
        conn, pr, decision_payload=_approve_decision())
    assert res["counts"]["readbacks"] == 1
    row = conn.execute(
        "SELECT readback_status FROM fill_review_readback_logs"
    ).fetchone()
    assert row[0] == "MATCHED"


def test_t31_readback_mismatch_creates_xml_backlog(conn, orc):
    pr = _base_pipeline_result(status="READBACK_FAILED")
    pr["approvedEditPlan"] = {"operations": _writer_op_applied()}
    pr["writerResult"] = {"operationResults": [{"status": "APPLIED"}]}
    pr["readback"] = {"operationResults": [
        {"status": "MISMATCH", "divergenceCode": "TEXT_MISMATCH",
            "targetKey": "t0:r0:c1", "normalizedLabel": "공사명"}]}
    res = orc.record_pipeline_result(
        conn, pr, decision_payload=_approve_decision())
    assert res["counts"]["xmlBacklogFlags"] >= 1
    row = conn.execute(
        "SELECT reason_code, severity FROM xml_deep_analyzer_need_flags"
    ).fetchone()
    assert row[0] == "READBACK_MISMATCH"
    assert row[1] == "HIGH"


# ── T40 learning signals ──────────────────────────────────────────────────

def test_t40_full_success_creates_reusable_signal(conn, orc):
    pr = _base_pipeline_result(status="COMPLETED")
    pr["approvedEditPlan"] = {"operations": _writer_op_applied()}
    pr["writerResult"] = {"operationResults": [{"status": "APPLIED"}]}
    pr["readback"] = {"operationResults": [{"status": "MATCHED"}]}
    res = orc.record_pipeline_result(
        conn, pr, decision_payload=_approve_decision())
    assert res["counts"]["learningSignals"] == 1
    row = conn.execute(
        "SELECT reusable, blocked_reason FROM fill_review_learning_signals"
    ).fetchone()
    assert row[0] == 1
    assert row[1] is None


def test_t41_readback_mismatch_signal_not_reusable(conn, orc):
    pr = _base_pipeline_result(status="READBACK_FAILED")
    pr["approvedEditPlan"] = {"operations": _writer_op_applied()}
    pr["writerResult"] = {"operationResults": [{"status": "APPLIED"}]}
    pr["readback"] = {"operationResults": [{"status": "MISMATCH"}]}
    res = orc.record_pipeline_result(
        conn, pr, decision_payload=_approve_decision())
    row = conn.execute(
        "SELECT reusable FROM fill_review_learning_signals"
    ).fetchone()
    assert row[0] == 0


# ── T50 XML backlog from warnings ─────────────────────────────────────────

def test_t50_warning_run_boundary_creates_flag(conn, orc):
    pr = _base_pipeline_result()
    pr["warnings"] = [{
        "code": "RUN_BOUNDARY_UNSUPPORTED",
        "targetKey": "tk1",
        "normalizedLabel": "공사명",
    }]
    res = orc.record_pipeline_result(conn, pr)
    assert res["counts"]["xmlBacklogFlags"] == 1
    row = conn.execute(
        "SELECT reason_code FROM xml_deep_analyzer_need_flags"
    ).fetchone()
    assert row[0] == "RUN_BOUNDARY_UNSUPPORTED"


def test_t51_unknown_warning_ignored(conn, orc):
    pr = _base_pipeline_result()
    pr["warnings"] = [{"code": "SOMETHING_ELSE"}]
    res = orc.record_pipeline_result(conn, pr)
    assert res["counts"]["xmlBacklogFlags"] == 0


# ── T60 격리 ──────────────────────────────────────────────────────────────

def test_t60_production_isolation(orc):
    res = orc.audit_orchestration_isolation()
    assert res["ok"], res["violations"]


def test_t61_module_does_not_import_production(orc):
    src = Path(orc.__file__).read_text(encoding="utf-8")
    # orchestration은 D동만 import해야 함. fill_review production import 금지.
    for forbidden in (
        "from scripts.hwpx.fill_review",
        "import fill_review_contract",
        "import fill_review_ui_adapter",
        "import fill_review_live_pipeline",
        "import evidence_ingestion_contract",
    ):
        assert forbidden not in src, forbidden


def test_t62_no_writer_in_module(orc):
    src = Path(orc.__file__).read_text(encoding="utf-8")
    for needle in ("GenericEditPlanWriter", "writer_executor",
                      "writer_adapter"):
        assert needle not in src


def test_t63_no_ai_ocr_in_module(orc):
    src = Path(orc.__file__).read_text(encoding="utf-8").lower()
    for needle in ("anthropic", "openai", "tesseract", "anthropic_api_key"):
        assert needle not in src


def test_t64_no_secret_in_module(orc):
    src = Path(orc.__file__).read_text(encoding="utf-8")
    for needle in ("DATABASE_URL", "password=", "haehan-ai.pem"):
        assert needle not in src


# ── T70 D동 schema 검증 ───────────────────────────────────────────────────

def test_t70_all_inserts_under_d_dong_fk(conn, orc):
    pr = _base_pipeline_result(status="COMPLETED")
    pr["approvedEditPlan"] = {"operations": _writer_op_applied()}
    pr["writerResult"] = {"operationResults": [{"status": "APPLIED"}]}
    pr["readback"] = {"operationResults": [{"status": "MATCHED"}]}
    res = orc.record_pipeline_result(
        conn, pr, decision_payload=_approve_decision())
    # FK enforcement: 모든 자식 row가 session 참조하는지
    for table in ("fill_review_decision_logs",
                    "fill_review_writer_operation_logs",
                    "fill_review_readback_logs",
                    "fill_review_learning_signals"):
        rows = conn.execute(
            f"SELECT session_id FROM {table}").fetchall()
        for r in rows:
            assert r[0] == res["sessionId"]


def test_t71_idempotent_multiple_records(conn, orc):
    pr = _base_pipeline_result()
    r1 = orc.record_pipeline_result(conn, pr)
    pr2 = _base_pipeline_result()
    pr2["requestId"] = "req-2"
    r2 = orc.record_pipeline_result(conn, pr2)
    assert r1["sessionId"] != r2["sessionId"]
    count = conn.execute(
        "SELECT COUNT(*) FROM fill_review_sessions").fetchone()[0]
    assert count == 2


# ── T80 D동 view 통합 확인 ────────────────────────────────────────────────

def test_t80_reusable_signal_visible_in_view(conn, orc):
    pr = _base_pipeline_result(status="COMPLETED")
    pr["approvedEditPlan"] = {"operations": _writer_op_applied()}
    pr["writerResult"] = {"operationResults": [{"status": "APPLIED"}]}
    pr["readback"] = {"operationResults": [{"status": "MATCHED"}]}
    orc.record_pipeline_result(
        conn, pr, decision_payload=_approve_decision())
    rows = conn.execute("SELECT * FROM reusable_learning_signals").fetchall()
    assert len(rows) == 1


def test_t81_xml_backlog_view_works(conn, orc):
    pr = _base_pipeline_result()
    pr["warnings"] = [{"code": "TARGET_AMBIGUOUS"}]
    orc.record_pipeline_result(conn, pr)
    rows = conn.execute("SELECT reason_code FROM xml_deep_analyzer_backlog").fetchall()
    assert any(r[0] == "TARGET_AMBIGUOUS" for r in rows)


# ════════════════════════════════════════════════════════════════════════════
# v1.1 — file-DB 옵션 + 운영 corpus 보호 (R2 차단 게이트)
# ════════════════════════════════════════════════════════════════════════════


def test_v1_1_in_memory_default(orc):
    """db_path=None → in-memory connection."""
    conn = orc.open_logging_connection(None)
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name='fill_review_sessions'").fetchall()
        assert rows
    finally:
        conn.close()


def test_v1_1_file_db_allowed(orc, tmp_path):
    """sandbox path는 허용."""
    db_path = tmp_path / "sandbox.sqlite3"
    conn = orc.open_logging_connection(db_path)
    try:
        assert db_path.exists()
    finally:
        conn.close()


def test_v1_1_protected_corpus_path_rejected(orc):
    """data/recognition_corpus/*.sqlite3 직접 쓰기 차단."""
    with pytest.raises(orc.ProtectedDbPathRejected):
        orc.open_logging_connection(
            "data/recognition_corpus/corpus.sqlite3")


def test_v1_1_protected_path_windows_separator(orc):
    """Windows backslash 경로도 차단."""
    with pytest.raises(orc.ProtectedDbPathRejected):
        orc.open_logging_connection(
            r"data\recognition_corpus\corpus.sqlite3")


def test_v1_1_non_protected_subdir_allowed(orc, tmp_path):
    """recognition_corpus 외 경로는 통과."""
    db_path = tmp_path / "drafts" / "log.sqlite3"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = orc.open_logging_connection(db_path)
    try:
        assert db_path.exists()
    finally:
        conn.close()


def test_v1_1_file_db_persists_record(orc, tmp_path):
    """file DB에 기록 → 재오픈 시 row 유지."""
    db_path = tmp_path / "persist.sqlite3"
    conn = orc.open_logging_connection(db_path)
    pr = {
        "schemaVersion": "1.0", "engineVersion": "0.6.2",
        "requestId": "req-persist-1", "documentId": "d-1",
        "sourceDocumentHash": "h",
        "pipelineStatus": "READY_FOR_REVIEW",
        "fillReview": {"reviewItems": []},
        "warnings": [], "errors": [],
    }
    orc.record_pipeline_result(conn, pr)
    conn.close()

    # 재오픈 확인
    import sqlite3 as sq
    conn2 = sq.connect(str(db_path))
    rows = conn2.execute(
        "SELECT document_id FROM fill_review_sessions").fetchall()
    conn2.close()
    assert rows and rows[0][0] == "d-1"


def test_v1_1_version_bumped(orc):
    assert orc.ORCHESTRATION_VERSION == "v1.1"
