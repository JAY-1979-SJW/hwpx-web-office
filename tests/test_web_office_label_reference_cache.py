"""라벨 기준서(레퍼런스 캐시) 감리.

고정하는 것:
  · (라벨, docType) 키 정규화 — 공백만 지우고 의미는 안 바꾼다
  · 백필은 새 AI 호출 없이 기존 verdicts+interpretations 만으로 채운다
  · 같은 (라벨,docType) 가 문서마다 다르게 나오면 consistent=0 —
    자동 적용 대상에서 빠진다(실사례: 소방공사감리원)
  · lookup 은 consistent=1 인 것만 돌려준다
  · 값(개인정보)은 저장되지 않는다
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

PR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PR))
sys.path.insert(0, str(PR / "scripts/hwpx"))

import scripts.hwpx.web_office.label_reference_cache as L  # noqa: E402


# ── 키 정규화 ───────────────────────────────────────────────────

def test_cache_key_normalizes_whitespace_only():
    assert L.cache_key(" 접수 번호 ", "신청신고") == L.cache_key("접수번호", "신청신고")
    assert L.cache_key("접수번호", "신청신고") != L.cache_key("접수번호", "대장기록")


def test_cache_key_does_not_merge_different_labels():
    assert L.cache_key("성명", "신청신고") != L.cache_key("성명(대표자)", "신청신고")


# ── 백필(새 AI 호출 없음) ────────────────────────────────────────

def _make_catalog(tmp_path: Path) -> Path:
    db = tmp_path / "catalog.sqlite"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE forms(form_id INTEGER PRIMARY KEY, doc_type TEXT)")
    con.execute("""CREATE TABLE ai_field_interpretation(
        form_id INTEGER PRIMARY KEY, interpretations TEXT)""")
    con.execute("""CREATE TABLE ai_field_verification(
        form_id INTEGER PRIMARY KEY, status TEXT, verdicts TEXT)""")

    def _seed(fid, doc_type, interp, verdicts):
        con.execute("INSERT INTO forms VALUES(?,?)", (fid, doc_type))
        con.execute("INSERT INTO ai_field_interpretation VALUES(?,?)",
                    (fid, json.dumps(interp, ensure_ascii=False)))
        con.execute("INSERT INTO ai_field_verification VALUES(?,?,?)",
                    (fid, "OK", json.dumps(verdicts, ensure_ascii=False)))

    # 문서 1,2: '접수번호'(신청신고) 가 두 문서에서 일관되게 other 일치
    interp1 = [{"key": "k1", "label": "접수번호", "isInput": True,
               "filledBy": "상대방", "semantic": "", "profileKey": "",
               "question": ""}]
    _seed(1, "신청신고", interp1, {"k1": "other"})
    _seed(2, "신청신고", interp1, {"k1": "other"})

    # 문서 3,4: '소방공사감리원'(보고통지) 이 문서마다 다르게 일치 — 비일관
    interp3 = [{"key": "k3", "label": "소방공사감리원", "isInput": True,
               "filledBy": "작성자", "semantic": "", "profileKey": "",
               "question": "감리원 성명을 입력하세요"}]
    _seed(3, "보고통지", interp3, {"k3": "self"})
    interp4 = [{"key": "k4", "label": "소방공사감리원", "isInput": True,
               "filledBy": "상대방", "semantic": "", "profileKey": "",
               "question": ""}]
    _seed(4, "보고통지", interp4, {"k4": "other"})

    # 문서 5: 불일치(1차 self, 2차 other) — 기준서에 안 들어가야 함
    interp5 = [{"key": "k5", "label": "미확정라벨", "isInput": True,
               "filledBy": "작성자", "semantic": "", "profileKey": "",
               "question": ""}]
    _seed(5, "신청신고", interp5, {"k5": "other"})

    con.commit()
    con.close()
    return db


def test_backfill_reuses_existing_verification_without_new_ai_calls(
        tmp_path, monkeypatch):
    monkeypatch.setattr(L, "CATALOG", _make_catalog(tmp_path))
    result = L.backfill_from_verified(project_root=tmp_path)
    assert result["formsScanned"] == 5


def test_backfill_marks_consistent_when_agreement_repeats(tmp_path, monkeypatch):
    monkeypatch.setattr(L, "CATALOG", _make_catalog(tmp_path))
    L.backfill_from_verified(project_root=tmp_path)
    con = sqlite3.connect(tmp_path / "catalog.sqlite")
    row = con.execute(
        f"SELECT verdict, sample_count, consistent FROM {L.TABLE}"
        f" WHERE cache_key=?", (L.cache_key("접수번호", "신청신고"),)).fetchone()
    con.close()
    assert row == ("other", 2, 1)


def test_backfill_marks_inconsistent_when_same_label_disagrees_across_docs(
        tmp_path, monkeypatch):
    # 실사례 재현: 소방공사감리원이 문서마다 다르게 판정됨 — 자동 적용 금지
    monkeypatch.setattr(L, "CATALOG", _make_catalog(tmp_path))
    L.backfill_from_verified(project_root=tmp_path)
    con = sqlite3.connect(tmp_path / "catalog.sqlite")
    row = con.execute(
        f"SELECT sample_count, conflict_count, consistent FROM {L.TABLE}"
        f" WHERE cache_key=?",
        (L.cache_key("소방공사감리원", "보고통지"),)).fetchone()
    con.close()
    assert row == (2, 1, 0)


def test_backfill_excludes_disagreed_fields_entirely(tmp_path, monkeypatch):
    monkeypatch.setattr(L, "CATALOG", _make_catalog(tmp_path))
    L.backfill_from_verified(project_root=tmp_path)
    con = sqlite3.connect(tmp_path / "catalog.sqlite")
    row = con.execute(
        f"SELECT COUNT(*) FROM {L.TABLE} WHERE cache_key=?",
        (L.cache_key("미확정라벨", "신청신고"),)).fetchone()
    con.close()
    assert row[0] == 0


def test_backfill_stores_no_values(tmp_path, monkeypatch):
    monkeypatch.setattr(L, "CATALOG", _make_catalog(tmp_path))
    L.backfill_from_verified(project_root=tmp_path)
    con = sqlite3.connect(tmp_path / "catalog.sqlite")
    cols = [r[1] for r in con.execute(f"PRAGMA table_info({L.TABLE})")]
    con.close()
    assert "value" not in cols


# ── lookup ──────────────────────────────────────────────────────

def test_lookup_returns_only_consistent_entries(tmp_path, monkeypatch):
    monkeypatch.setattr(L, "CATALOG", _make_catalog(tmp_path))
    L.backfill_from_verified(project_root=tmp_path)
    con = sqlite3.connect(tmp_path / "catalog.sqlite")
    hit = L.lookup(con, "접수번호", "신청신고")
    miss = L.lookup(con, "소방공사감리원", "보고통지")   # 비일관 — None 이어야
    con.close()
    assert hit is not None and hit["verdict"] == "other"
    assert miss is None


def test_lookup_unknown_label_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(L, "CATALOG", _make_catalog(tmp_path))
    L.backfill_from_verified(project_root=tmp_path)
    con = sqlite3.connect(tmp_path / "catalog.sqlite")
    miss = L.lookup(con, "본적없는라벨", "신청신고")
    con.close()
    assert miss is None
