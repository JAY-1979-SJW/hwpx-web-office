"""HWPX-RECOGNITION-LABEL-PROMOTION-CANDIDATE-REVIEW-BATCH-01 tests."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.hwpx.recognition_corpus import corpus_schema as cs
from scripts.hwpx.recognition_corpus import label_promotion_review_batch as rb


# ── fixture helpers ────────────────────────────────────────────────────

def _open():
    return cs.open_corpus_db(":memory:")


def _add_doc(conn, did):
    conn.execute(
        "INSERT INTO hwpx_documents "
        "(document_id, source_path, source_kind, file_size, mtime,"
        " detected_type, inventory_status, sha256, first_seen_at) "
        "VALUES (?, '/x', 'collected', 1, 1.0, 'hwpx', 'FOUND', ?, 'now')",
        (did, did.ljust(64, "0")))


def _add_occ(conn, did, label, neighbor=""):
    conn.execute(
        "INSERT INTO label_occurrences "
        "(document_id, label_text, normalized_label, neighbor_text,"
        " right_neighbor_empty, audited_at) VALUES (?, ?, ?, ?, 1, 'now')",
        (did, label, label, neighbor))


def _add_cand(conn, label, semantic, occ, docs, score, status="PENDING"):
    conn.execute(
        "INSERT INTO label_promotion_candidates "
        "(normalized_label, proposed_semantic, occurrence_count,"
        " document_count, evidence_score, status, evidence_json) "
        "VALUES (?, ?, ?, ?, ?, ?, '{}')",
        (label, semantic, occ, docs, score, status))


def _add_human(conn, label, semantic, status, by="r1"):
    conn.execute(
        "INSERT INTO human_label_decisions "
        "(normalized_label, semantic_type, decision_status, decided_by,"
        " decided_at) VALUES (?, ?, ?, ?, 'now')",
        (label, semantic, status, by))


def _seed_high(conn):
    """large, clean candidate."""
    _add_cand(conn, "공사명", "PROJECT_NAME", 2000, 800, 0.9)
    for i in range(10):
        did = f"doc{i:04d}"
        _add_doc(conn, did)
        _add_occ(conn, did, "공사명", neighbor=f"공사명 예시 {i}")


def _seed_unknown(conn):
    _add_cand(conn, "미상라벨", "UNKNOWN", 1000, 200, 0.8)
    _add_doc(conn, "dU")
    _add_occ(conn, "dU", "미상라벨")


def _seed_conflict(conn):
    _add_cand(conn, "주소", "ADDRESS", 800, 400, 0.7)
    _add_doc(conn, "dC")
    _add_occ(conn, "dC", "주소")
    _add_human(conn, "주소", "ADDRESS", "APPROVED")
    _add_human(conn, "주소", "COMPANY_NAME", "APPROVED", by="r2")


def _seed_low(conn):
    _add_cand(conn, "희소라벨", "PHONE", 5, 2, 0.4)
    _add_doc(conn, "dL")
    _add_occ(conn, "dL", "희소라벨")


# ── T01: batch build smoke ──────────────────────────────────────────────

def test_t01_batch_build_smoke():
    conn = _open()
    _seed_high(conn); conn.commit()
    b = rb.build_promotion_review_batch(conn)
    assert b["candidateCount"] == 1
    assert b["reviewableCount"] >= 1


def test_t02_ranking_descending():
    conn = _open()
    _add_cand(conn, "공사명", "PROJECT_NAME", 2000, 800, 0.9)
    _add_cand(conn, "전화번호", "PHONE", 30, 10, 0.5)
    _add_cand(conn, "주소", "ADDRESS", 800, 400, 0.7)
    conn.commit()
    b = rb.build_promotion_review_batch(conn)
    labels = [b["buckets"]["HIGH_PRIORITY_REVIEW"][i]["normalizedLabel"]
                 for i in range(min(2,
                          len(b["buckets"]["HIGH_PRIORITY_REVIEW"])))]
    # 공사명이 주소보다 먼저
    all_review = (b["buckets"]["HIGH_PRIORITY_REVIEW"]
                       + b["buckets"]["MEDIUM_PRIORITY_REVIEW"]
                       + b["buckets"]["LOW_PRIORITY_REVIEW"])
    order = [c["normalizedLabel"] for c in all_review]
    assert order.index("공사명") < order.index("주소")


def test_t03_high_priority_bucket():
    conn = _open()
    _seed_high(conn); conn.commit()
    b = rb.build_promotion_review_batch(conn)
    assert len(b["buckets"]["HIGH_PRIORITY_REVIEW"]) == 1


def test_t04_medium_priority_bucket():
    conn = _open()
    _add_cand(conn, "성명", "FREE_TEXT", 50, 10, 0.5)
    _add_doc(conn, "dM"); _add_occ(conn, "dM", "성명")
    conn.commit()
    b = rb.build_promotion_review_batch(conn)
    assert len(b["buckets"]["MEDIUM_PRIORITY_REVIEW"]) == 1


def test_t05_low_priority_bucket():
    conn = _open()
    _add_cand(conn, "기타라벨", "FREE_TEXT", 10, 3, 0.45)
    _add_doc(conn, "dLp"); _add_occ(conn, "dLp", "기타라벨")
    conn.commit()
    b = rb.build_promotion_review_batch(conn)
    assert len(b["buckets"]["LOW_PRIORITY_REVIEW"]) == 1


def test_t06_unknown_semantic_blocked():
    conn = _open()
    _seed_unknown(conn); conn.commit()
    b = rb.build_promotion_review_batch(conn)
    assert len(b["buckets"]["BLOCKED_UNKNOWN_SEMANTIC"]) == 1
    assert b["unknownSemanticCount"] == 1


def test_t07_conflict_bucket():
    conn = _open()
    _seed_conflict(conn); conn.commit()
    b = rb.build_promotion_review_batch(conn)
    assert len(b["buckets"]["BLOCKED_CONFLICT"]) == 1


def test_t08_disagreement_only_bucket():
    conn = _open()
    _add_cand(conn, "라벨D", "PROJECT_NAME", 100, 10, 0.7)
    _add_doc(conn, "dD"); _add_occ(conn, "dD", "라벨D")
    conn.commit()
    b = rb.build_promotion_review_batch(
        conn, tainted_disagreement={"dD"})
    assert len(b["buckets"]["BLOCKED_DISAGREEMENT_ONLY"]) == 1


def test_t09_ambiguous_only_bucket():
    conn = _open()
    _add_cand(conn, "라벨A", "PROJECT_NAME", 100, 10, 0.7)
    _add_doc(conn, "dA"); _add_occ(conn, "dA", "라벨A")
    conn.commit()
    b = rb.build_promotion_review_batch(
        conn, tainted_ambiguous={"dA"})
    assert len(b["buckets"]["BLOCKED_AMBIGUOUS_ONLY"]) == 1


def test_t10_mixed_clean_and_tainted_reviewable():
    conn = _open()
    _add_cand(conn, "라벨M", "PROJECT_NAME", 500, 50, 0.8)
    for i in range(5):
        did = f"dm{i}"; _add_doc(conn, did); _add_occ(conn, did, "라벨M")
    conn.commit()
    b = rb.build_promotion_review_batch(
        conn, tainted_ambiguous={"dm0"})
    # 일부만 tainted → 차단 안 됨, HIGH로 들어가야 함
    assert len(b["buckets"]["BLOCKED_AMBIGUOUS_ONLY"]) == 0
    assert len(b["buckets"]["HIGH_PRIORITY_REVIEW"]) == 1


def test_t11_multi_meaning_flag():
    conn = _open()
    _add_cand(conn, "성명", "FREE_TEXT", 500, 100, 0.7)
    _add_doc(conn, "dg"); _add_occ(conn, "dg", "성명")
    conn.commit()
    b = rb.build_promotion_review_batch(conn)
    cand = b["topReviewCandidates"][0]
    assert "MULTI_MEANING_LABEL" in cand["riskFlags"]
    assert cand["recommendedDecision"] == "REVIEW_REQUIRED"


def test_t12_example_labels_limit():
    conn = _open()
    _add_cand(conn, "X", "PROJECT_NAME", 500, 100, 0.7)
    for i in range(20):
        did = f"dx{i}"; _add_doc(conn, did)
        _add_occ(conn, did, "X")
    conn.commit()
    b = rb.build_promotion_review_batch(conn)
    c = b["topReviewCandidates"][0]
    assert len(c["exampleLabels"]) <= rb.EXAMPLE_LABEL_LIMIT


def test_t13_example_documents_limit():
    conn = _open()
    _add_cand(conn, "X", "PROJECT_NAME", 500, 100, 0.7)
    for i in range(20):
        did = f"dx{i}"; _add_doc(conn, did)
        _add_occ(conn, did, "X")
    conn.commit()
    b = rb.build_promotion_review_batch(conn)
    c = b["topReviewCandidates"][0]
    assert len(c["exampleDocuments"]) <= rb.EXAMPLE_DOCUMENT_LIMIT


def test_t14_top_contexts_generated():
    conn = _open()
    _add_cand(conn, "공사명", "PROJECT_NAME", 500, 100, 0.7)
    for i in range(5):
        did = f"dc{i}"; _add_doc(conn, did)
        _add_occ(conn, did, "공사명",
                    neighbor=f"공사명 주변문맥 예시 {i}")
    conn.commit()
    b = rb.build_promotion_review_batch(conn)
    c = b["topReviewCandidates"][0]
    assert len(c["topContexts"]) >= 1


def test_t15_review_candidate_required_fields():
    conn = _open()
    _seed_high(conn); conn.commit()
    b = rb.build_promotion_review_batch(conn)
    c = b["topReviewCandidates"][0]
    for k in ("candidateId", "normalizedLabel", "proposedSemantic",
                 "occurrenceCount", "documentCount", "evidenceScore",
                 "exampleLabels", "exampleDocuments", "documentTypes",
                 "subTypes", "topContexts", "riskFlags",
                 "recommendedDecision", "reason"):
        assert k in c, k


def test_t16_review_batch_required_fields():
    conn = _open()
    _seed_high(conn); conn.commit()
    b = rb.build_promotion_review_batch(conn)
    for k in ("schemaVersion", "engineVersion", "requestId",
                 "sourceCorpusSha", "generatedAt", "candidateCount",
                 "reviewableCount", "blockedCount", "conflictCount",
                 "unknownSemanticCount", "disagreementOnlyCount",
                 "ambiguousOnlyCount", "buckets",
                 "topReviewCandidates", "warnings"):
        assert k in b, k


def test_t17_markdown_generated():
    conn = _open()
    _seed_high(conn); conn.commit()
    b = rb.build_promotion_review_batch(conn)
    md = rb.build_review_markdown(b)
    assert "| candidateId | normalizedLabel" in md
    assert "공사명" in md


def test_t18_approval_input_valid():
    approval = {
        "schemaVersion": rb.APPROVAL_INPUT_SCHEMA_VERSION,
        "approvedBy": "reviewer1",
        "decidedAt": "2026-05-18",
        "decisions": [{"candidateId": "cand-00000",
                          "normalizedLabel": "공사명",
                          "proposedSemantic": "PROJECT_NAME",
                          "decision": "APPROVE",
                          "reason": "high frequency clean"}],
    }
    v = rb.validate_human_approval_batch_input(approval)
    assert v["ok"] is True


def test_t19_empty_approver_invalid():
    a = {"schemaVersion": rb.APPROVAL_INPUT_SCHEMA_VERSION,
            "approvedBy": "", "decidedAt": "now", "decisions": []}
    v = rb.validate_human_approval_batch_input(a)
    assert v["ok"] is False
    assert any(e["code"] == "EMPTY_APPROVED_BY" for e in v["errors"])


def test_t20_invalid_decision():
    a = {"schemaVersion": rb.APPROVAL_INPUT_SCHEMA_VERSION,
            "approvedBy": "r", "decidedAt": "n",
            "decisions": [{"candidateId": "c", "normalizedLabel": "x",
                              "proposedSemantic": "PROJECT_NAME",
                              "decision": "ACCEPT"}]}
    v = rb.validate_human_approval_batch_input(a)
    assert any(e["code"] == "INVALID_DECISION" for e in v["errors"])


def test_t21_approve_unknown_blocked():
    a = {"schemaVersion": rb.APPROVAL_INPUT_SCHEMA_VERSION,
            "approvedBy": "r", "decidedAt": "n",
            "decisions": [{"candidateId": "c", "normalizedLabel": "x",
                              "proposedSemantic": "UNKNOWN",
                              "decision": "APPROVE"}]}
    v = rb.validate_human_approval_batch_input(a)
    assert any(e["code"] == "APPROVE_UNKNOWN_SEMANTIC" for e in v["errors"])


def test_t22_label_id_mismatch():
    conn = _open()
    _seed_high(conn); conn.commit()
    b = rb.build_promotion_review_batch(conn)
    cid = b["buckets"]["HIGH_PRIORITY_REVIEW"][0]["candidateId"]
    a = {"schemaVersion": rb.APPROVAL_INPUT_SCHEMA_VERSION,
            "approvedBy": "r", "decidedAt": "n",
            "decisions": [{"candidateId": cid,
                              "normalizedLabel": "엉뚱한라벨",
                              "proposedSemantic": "PROJECT_NAME",
                              "decision": "APPROVE"}]}
    v = rb.validate_human_approval_batch_input(a, review_batch=b)
    assert any(e["code"] == "LABEL_ID_MISMATCH" for e in v["errors"])


def test_t23_approve_conflict_blocked():
    conn = _open()
    _seed_conflict(conn); conn.commit()
    b = rb.build_promotion_review_batch(conn)
    cid = b["buckets"]["BLOCKED_CONFLICT"][0]["candidateId"]
    a = {"schemaVersion": rb.APPROVAL_INPUT_SCHEMA_VERSION,
            "approvedBy": "r", "decidedAt": "n",
            "decisions": [{"candidateId": cid,
                              "normalizedLabel": "주소",
                              "proposedSemantic": "ADDRESS",
                              "decision": "APPROVE"}]}
    v = rb.validate_human_approval_batch_input(a, review_batch=b)
    assert any(e["code"] == "APPROVE_CONFLICT" for e in v["errors"])


def test_t24_approve_disagreement_only_blocked():
    conn = _open()
    _add_cand(conn, "라벨D", "PROJECT_NAME", 100, 10, 0.7)
    _add_doc(conn, "dD"); _add_occ(conn, "dD", "라벨D")
    conn.commit()
    b = rb.build_promotion_review_batch(
        conn, tainted_disagreement={"dD"})
    cid = b["buckets"]["BLOCKED_DISAGREEMENT_ONLY"][0]["candidateId"]
    a = {"schemaVersion": rb.APPROVAL_INPUT_SCHEMA_VERSION,
            "approvedBy": "r", "decidedAt": "n",
            "decisions": [{"candidateId": cid,
                              "normalizedLabel": "라벨D",
                              "proposedSemantic": "PROJECT_NAME",
                              "decision": "APPROVE"}]}
    v = rb.validate_human_approval_batch_input(a, review_batch=b)
    assert any(e["code"] == "APPROVE_DISAGREEMENT_ONLY"
                  for e in v["errors"])


def test_t25_approve_ambiguous_only_blocked():
    conn = _open()
    _add_cand(conn, "라벨A", "PROJECT_NAME", 100, 10, 0.7)
    _add_doc(conn, "dA"); _add_occ(conn, "dA", "라벨A")
    conn.commit()
    b = rb.build_promotion_review_batch(
        conn, tainted_ambiguous={"dA"})
    cid = b["buckets"]["BLOCKED_AMBIGUOUS_ONLY"][0]["candidateId"]
    a = {"schemaVersion": rb.APPROVAL_INPUT_SCHEMA_VERSION,
            "approvedBy": "r", "decidedAt": "n",
            "decisions": [{"candidateId": cid,
                              "normalizedLabel": "라벨A",
                              "proposedSemantic": "PROJECT_NAME",
                              "decision": "APPROVE"}]}
    v = rb.validate_human_approval_batch_input(a, review_batch=b)
    assert any(e["code"] == "APPROVE_AMBIGUOUS_ONLY"
                  for e in v["errors"])


def test_t26_no_human_decision_insert():
    """audit helper로 actual code usage 검사 (literal forbidden 리스트 제외)."""
    r = rb.audit_review_batch_safety()
    assert r["ok"] is True
    assert all("human_label_decisions" not in v
                  for v in r["violations"])


def test_t27_no_dictionary_version_creation():
    r = rb.audit_review_batch_safety()
    assert all("label_dictionary_versions" not in v
                  for v in r["violations"])
    assert all("label_dictionary_entries" not in v
                  for v in r["violations"])


def test_t28_no_production_dict_modification():
    src = (PROJECT_ROOT
            / "scripts/hwpx/recognition_corpus/"
              "label_promotion_review_batch.py"
           ).read_text(encoding="utf-8")
    for n in ("fill_review_contract", "_LABEL_TO_SEMANTIC"):
        assert n not in src


def test_t29_no_writer():
    r = rb.audit_review_batch_safety()
    assert all("execute_writer" not in v for v in r["violations"])


def test_t30_no_output_hwpx():
    r = rb.audit_review_batch_safety()
    assert all("ZipFile" not in v for v in r["violations"])


def test_t31_no_ai_no_ocr():
    r = rb.audit_review_batch_safety()
    for v in r["violations"]:
        assert "anthropic" not in v
        assert "openai" not in v
        assert "pytesseract" not in v


def test_t32_no_secret():
    src = (PROJECT_ROOT
            / "scripts/hwpx/recognition_corpus/"
              "label_promotion_review_batch.py"
           ).read_text(encoding="utf-8")
    for n in ("sk-", "Bearer ", "DATABASE_URL="):
        assert n not in src


def test_t33_gitignore_exports_reports():
    gi = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "data/recognition_corpus/exports/" in gi
    assert "reports/" in gi or "/reports/" in gi


def test_t34_audit_safety_helper():
    r = rb.audit_review_batch_safety()
    assert r["ok"] is True, r["violations"]
