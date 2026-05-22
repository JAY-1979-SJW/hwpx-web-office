"""HWPX-RECOGNITION-LABEL-DICTIONARY-PROMOTION-GATE-01 tests."""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.hwpx.recognition_corpus import corpus_schema as cs
from scripts.hwpx.recognition_corpus import label_promotion_gate as pg


# ── helpers ──────────────────────────────────────────────────────────────

def _open():
    return cs.open_corpus_db(":memory:")


def _add_human(conn, label, semantic, status, by="reviewer1"):
    conn.execute(
        "INSERT INTO human_label_decisions "
        "(normalized_label, semantic_type, decision_status, decided_by,"
        " decided_at) VALUES (?, ?, ?, ?, 'now')",
        (label, semantic, status, by),
    )
    conn.commit()


def _add_doc(conn, doc_id):
    conn.execute(
        "INSERT INTO hwpx_documents "
        "(document_id, source_path, source_kind, file_size, mtime,"
        " detected_type, inventory_status, sha256, first_seen_at) "
        "VALUES (?, '/x', 'collected', 1, 1.0, 'hwpx', 'FOUND', ?, 'now')",
        (doc_id, doc_id.ljust(64, "0")),
    )


def _add_occ(conn, doc_id, label):
    conn.execute(
        "INSERT INTO label_occurrences "
        "(document_id, label_text, normalized_label, right_neighbor_empty,"
        " audited_at) VALUES (?, ?, ?, 1, 'now')",
        (doc_id, label, label),
    )


def _candidate(label="공사명", semantic="PROJECT_NAME",
                  occ=10, docs=5, score=0.9):
    return {"normalized_label": label, "proposed_semantic": semantic,
              "occurrence_count": occ, "document_count": docs,
              "evidence_score": score}


# ── T01: no human approval → block ───────────────────────────────────────

def test_t01_no_human_approval_blocks():
    conn = _open()
    r = pg.evaluate_promotion_candidate(conn, _candidate())
    assert r["status"] == "BLOCKED_NO_HUMAN_APPROVAL"
    assert r["allowed"] is False
    assert r["blockedReason"] == "NO_HUMAN_APPROVAL"


def test_t02_human_approval_allows():
    conn = _open()
    _add_human(conn, "공사명", "PROJECT_NAME", "APPROVED")
    r = pg.evaluate_promotion_candidate(conn, _candidate())
    assert r["status"] == "PROMOTION_ALLOWED"
    assert r["allowed"] is True
    assert r["humanApprovalCount"] == 1


def test_t03_unknown_semantic_blocked():
    conn = _open()
    r = pg.evaluate_promotion_candidate(
        conn, _candidate(semantic="UNKNOWN"))
    assert r["status"] == "BLOCKED_UNKNOWN_SEMANTIC"
    assert r["blockedReason"] == "UNKNOWN_SEMANTIC_FORBIDDEN"


def test_t04_semantic_conflict_blocked():
    conn = _open()
    _add_human(conn, "공사명", "PROJECT_NAME", "APPROVED")
    _add_human(conn, "공사명", "COMPANY_NAME", "APPROVED", by="reviewer2")
    r = pg.evaluate_promotion_candidate(conn, _candidate())
    assert r["status"] == "BLOCKED_CONFLICT"
    assert r["conflictCount"] >= 1


def test_t05_rejected_only_blocks():
    conn = _open()
    _add_human(conn, "공사명", "PROJECT_NAME", "REJECTED")
    r = pg.evaluate_promotion_candidate(conn, _candidate())
    assert r["allowed"] is False
    assert r["status"] == "BLOCKED_NO_HUMAN_APPROVAL"


def test_t06_held_only_blocks():
    conn = _open()
    _add_human(conn, "공사명", "PROJECT_NAME", "HELD")
    r = pg.evaluate_promotion_candidate(conn, _candidate())
    assert r["allowed"] is False


def test_t07_approved_plus_rejected_held():
    conn = _open()
    _add_human(conn, "공사명", "PROJECT_NAME", "APPROVED")
    _add_human(conn, "공사명", "PROJECT_NAME", "REJECTED", by="r2")
    r = pg.evaluate_promotion_candidate(conn, _candidate())
    assert r["allowed"] is False
    assert "HAS_REJECTED_FOR_SAME_SEMANTIC" in r["warnings"]


def test_t08_disagreement_only_blocks():
    conn = _open()
    _add_human(conn, "공사명", "PROJECT_NAME", "APPROVED")
    _add_doc(conn, "doc-bad")
    _add_occ(conn, "doc-bad", "공사명")
    conn.commit()
    r = pg.evaluate_promotion_candidate(
        conn, _candidate(),
        tainted_document_ids={"doc-bad"})
    assert r["status"] == "BLOCKED_DISAGREEMENT_ONLY"
    assert r["blockedReason"] == "DISAGREEMENT_REQUIRES_REVIEW"


def test_t09_ambiguous_only_blocks_via_taint():
    # disagreement과 동일한 taint 메커니즘이 ambiguous에도 적용됨
    conn = _open()
    _add_human(conn, "공사명", "PROJECT_NAME", "APPROVED")
    _add_doc(conn, "doc-amb")
    _add_occ(conn, "doc-amb", "공사명")
    conn.commit()
    r = pg.evaluate_promotion_candidate(
        conn, _candidate(),
        tainted_document_ids={"doc-amb"})
    assert r["allowed"] is False
    assert r["disagreementCount"] >= 1


def test_t10_mixed_clean_and_tainted_allows():
    conn = _open()
    _add_human(conn, "공사명", "PROJECT_NAME", "APPROVED")
    _add_doc(conn, "doc-bad"); _add_occ(conn, "doc-bad", "공사명")
    _add_doc(conn, "doc-ok"); _add_occ(conn, "doc-ok", "공사명")
    conn.commit()
    r = pg.evaluate_promotion_candidate(
        conn, _candidate(),
        tainted_document_ids={"doc-bad"})
    assert r["allowed"] is True
    assert r["disagreementCount"] == 1


def test_t11_low_evidence_blocked():
    conn = _open()
    _add_human(conn, "공사명", "PROJECT_NAME", "APPROVED")
    r = pg.evaluate_promotion_candidate(
        conn, _candidate(occ=1, docs=1, score=0.05))
    assert r["status"] == "BLOCKED_LOW_EVIDENCE"
    assert r["blockedReason"] == "LOW_EVIDENCE_SCORE"


def test_t12_required_fields():
    conn = _open()
    r = pg.evaluate_promotion_candidate(conn, _candidate())
    for k in ("schemaVersion", "engineVersion", "requestId",
                 "normalizedLabel", "proposedSemantic", "status",
                 "allowed", "blockedReason", "occurrenceCount",
                 "documentCount", "evidenceScore", "humanApprovalCount",
                 "conflictCount", "disagreementCount", "ambiguousCount",
                 "warnings"):
        assert k in r, k


def test_t13_build_dictionary_version_success():
    conn = _open()
    _add_human(conn, "공사명", "PROJECT_NAME", "APPROVED")
    r = [pg.evaluate_promotion_candidate(conn, _candidate())]
    info = pg.build_dictionary_version(
        conn, "v_test", r, approved_by="reviewer1",
        source_corpus_sha="sha:test")
    assert info["entryCount"] == 1


def test_t14_entries_contain_only_allowed():
    conn = _open()
    _add_human(conn, "공사명", "PROJECT_NAME", "APPROVED")
    rs = [
        pg.evaluate_promotion_candidate(conn, _candidate()),
        pg.evaluate_promotion_candidate(
            conn, _candidate(label="x", semantic="UNKNOWN")),
    ]
    pg.build_dictionary_version(
        conn, "v_only_allowed", rs,
        approved_by="r", source_corpus_sha="s")
    n = conn.execute(
        "SELECT COUNT(*) FROM label_dictionary_entries "
        "WHERE version='v_only_allowed'").fetchone()[0]
    assert n == 1


def test_t15_unknown_blocked_in_dictionary_check():
    conn = _open()
    # SQL CHECK가 직접 차단
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO label_dictionary_versions "
            "(version, built_at, entry_count, source_corpus_sha, approved_by)"
            " VALUES ('v0', 'now', 1, 'sha', 'r')")
        conn.execute(
            "INSERT INTO label_dictionary_entries "
            "(version, normalized_label, semantic_type) "
            "VALUES ('v0', 'x', 'UNKNOWN')")
    conn.rollback()


def test_t16_entry_count_consistency():
    conn = _open()
    _add_human(conn, "공사명", "PROJECT_NAME", "APPROVED")
    _add_human(conn, "주소", "ADDRESS", "APPROVED", by="r2")
    rs = [
        pg.evaluate_promotion_candidate(conn, _candidate()),
        pg.evaluate_promotion_candidate(
            conn, _candidate(label="주소", semantic="ADDRESS")),
    ]
    info = pg.build_dictionary_version(
        conn, "v16", rs, approved_by="r", source_corpus_sha="s")
    actual = conn.execute(
        "SELECT COUNT(*) FROM label_dictionary_entries WHERE version='v16'"
    ).fetchone()[0]
    assert info["entryCount"] == actual


def test_t17_snapshot_schema(tmp_path):
    conn = _open()
    _add_human(conn, "공사명", "PROJECT_NAME", "APPROVED")
    r = [pg.evaluate_promotion_candidate(conn, _candidate())]
    pg.build_dictionary_version(conn, "v17", r,
                                       approved_by="r",
                                       source_corpus_sha="s")
    snap = pg.export_dictionary_snapshot(
        conn, "v17", tmp_path / "snap.json", results=r)
    for k in ("schemaVersion", "dictionaryVersion", "builtAt",
                 "sourceCorpusSha", "classifierVersion", "entryCount",
                 "entries", "blockedCandidates", "warnings"):
        assert k in snap


def test_t18_snapshot_export_path_guard(tmp_path):
    conn = _open()
    _add_human(conn, "공사명", "PROJECT_NAME", "APPROVED")
    r = [pg.evaluate_promotion_candidate(conn, _candidate())]
    pg.build_dictionary_version(conn, "v18", r,
                                       approved_by="r",
                                       source_corpus_sha="s")
    # tmp_path는 허용
    pg.export_dictionary_snapshot(conn, "v18",
                                       tmp_path / "snap.json", results=r)
    # 외부 임의 경로는 차단
    with pytest.raises(PermissionError):
        pg.export_dictionary_snapshot(
            conn, "v18",
            PROJECT_ROOT / "scripts/hwpx/snap.json", results=r)


def test_t19_snapshot_validate(tmp_path):
    conn = _open()
    _add_human(conn, "공사명", "PROJECT_NAME", "APPROVED")
    r = [pg.evaluate_promotion_candidate(conn, _candidate())]
    pg.build_dictionary_version(conn, "v19", r,
                                       approved_by="r",
                                       source_corpus_sha="s")
    snap = pg.export_dictionary_snapshot(conn, "v19",
                                                tmp_path / "snap.json",
                                                results=r)
    v = pg.validate_dictionary_snapshot(snap)
    assert v["ok"] is True


def test_t20_compare_versions():
    conn = _open()
    _add_human(conn, "공사명", "PROJECT_NAME", "APPROVED")
    _add_human(conn, "주소", "ADDRESS", "APPROVED", by="r2")
    ra = [pg.evaluate_promotion_candidate(conn, _candidate())]
    pg.build_dictionary_version(conn, "vA", ra,
                                       approved_by="r",
                                       source_corpus_sha="s")
    rb = ra + [pg.evaluate_promotion_candidate(
        conn, _candidate(label="주소", semantic="ADDRESS"))]
    pg.build_dictionary_version(conn, "vB", rb,
                                       approved_by="r",
                                       source_corpus_sha="s")
    d = pg.compare_dictionary_versions(conn, "vA", "vB")
    assert "주소" in d["addedLabels"]
    assert d["entryCountB"] == 2


def test_t21_changed_and_removed():
    conn = _open()
    _add_human(conn, "공사명", "PROJECT_NAME", "APPROVED")
    _add_human(conn, "주소", "ADDRESS", "APPROVED", by="r2")
    rA = [pg.evaluate_promotion_candidate(conn, _candidate()),
            pg.evaluate_promotion_candidate(
                conn, _candidate(label="주소", semantic="ADDRESS"))]
    pg.build_dictionary_version(conn, "vR1", rA,
                                       approved_by="r",
                                       source_corpus_sha="s")
    # vR2: drop "주소", change 공사명 semantic (가상 시나리오)
    conn.execute(
        "INSERT INTO label_dictionary_versions "
        "(version, built_at, entry_count, source_corpus_sha, approved_by) "
        "VALUES ('vR2','now',1,'s','r')")
    conn.execute(
        "INSERT INTO label_dictionary_entries "
        "(version, normalized_label, semantic_type) "
        "VALUES ('vR2','공사명','COMPANY_NAME')")
    conn.commit()
    d = pg.compare_dictionary_versions(conn, "vR1", "vR2")
    assert "주소" in d["removedLabels"]
    assert any(x["label"] == "공사명" for x in d["semanticChangedLabels"])


def test_t22_production_isolation_for_promotion_gate():
    r = pg.audit_production_snapshot_isolation()
    assert r["ok"] is True, r["violations"]


def test_t23_fill_review_no_corpus_import():
    iso = cs.audit_production_isolation()
    assert iso["ok"] is True


def test_t24_no_writer_in_module():
    src = (PROJECT_ROOT
            / "scripts/hwpx/recognition_corpus/label_promotion_gate.py"
           ).read_text(encoding="utf-8")
    assert "execute_writer_call_plan_live_sandbox" not in src


def test_t25_no_output_hwpx_creation():
    src = (PROJECT_ROOT
            / "scripts/hwpx/recognition_corpus/label_promotion_gate.py"
           ).read_text(encoding="utf-8")
    assert "ZipFile" not in src


def test_t26_no_ai_no_ocr():
    src = (PROJECT_ROOT
            / "scripts/hwpx/recognition_corpus/label_promotion_gate.py"
           ).read_text(encoding="utf-8")
    for n in ("import anthropic", "import openai",
                 "anthropic.Anthropic", "pytesseract"):
        assert n not in src


def test_t27_no_secret():
    src = (PROJECT_ROOT
            / "scripts/hwpx/recognition_corpus/label_promotion_gate.py"
           ).read_text(encoding="utf-8")
    for n in ("sk-", "Bearer ", "DATABASE_URL="):
        assert n not in src


def test_t28_gitignore_export_and_corpus():
    gi = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "data/recognition_corpus/exports/" in gi
    assert "data/recognition_corpus/*.sqlite3" in gi


def test_t29_filter_helper_groups_review_required():
    rs = [
        {"status": "PROMOTION_ALLOWED"},
        {"status": "BLOCKED_DISAGREEMENT_ONLY"},
        {"status": "BLOCKED_AMBIGUOUS_ONLY"},
        {"status": "BLOCKED_NO_HUMAN_APPROVAL"},
    ]
    f = pg.filter_disagreement_or_ambiguous_candidates(rs)
    assert len(f) == 2


def test_t30_invalid_semantic_blocked():
    conn = _open()
    r = pg.evaluate_promotion_candidate(
        conn, _candidate(semantic="NOT_A_THING"))
    assert r["status"] == "BLOCKED_INVALID_SEMANTIC"


def test_t31_build_rejects_empty_approver():
    conn = _open()
    with pytest.raises(ValueError):
        pg.build_dictionary_version(conn, "vbad", [],
                                           approved_by="",
                                           source_corpus_sha="s")


def test_t32_evaluate_all_runs_against_db():
    conn = _open()
    conn.execute(
        "INSERT INTO label_promotion_candidates "
        "(normalized_label, proposed_semantic, occurrence_count,"
        " document_count, evidence_score, status, evidence_json) "
        "VALUES ('공사명','PROJECT_NAME',10,5,0.9,'PENDING','{}')")
    _add_human(conn, "공사명", "PROJECT_NAME", "APPROVED")
    rs = pg.evaluate_all_promotion_candidates(conn)
    assert len(rs) == 1 and rs[0]["allowed"] is True


def test_t33_snapshot_count_mismatch_invalid():
    bad = {"schemaVersion": "label_dictionary_snapshot_v1",
              "dictionaryVersion": "v", "builtAt": "n",
              "sourceCorpusSha": "s", "classifierVersion": "c",
              "entryCount": 2, "entries": [], "blockedCandidates": [],
              "warnings": []}
    v = pg.validate_dictionary_snapshot(bad)
    assert v["ok"] is False
    assert v["entryCountMatches"] is False
