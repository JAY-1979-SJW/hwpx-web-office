"""SQL 조인 목차(③단계) 감리.

고정하는 것:
  · 아무것도 재계산하지 않는다 — 4개 스테이징 테이블을 그대로 조인만 한다
  · 문서 1건의 단계 판정이 있는 테이블 조합에 따라 정확히 갈린다
  · scope 필터가 source_path 부분일치로 걸린다
  · 목차 산출물(JSONL+MD)이 전 건수를 담는다(누락 없음)
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

PR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PR))
sys.path.insert(0, str(PR / "scripts/hwpx"))

import scripts.hwpx.web_office.build_pipeline_index as P  # noqa: E402


def _make_catalog(tmp_path: Path) -> Path:
    db = tmp_path / "catalog.sqlite"
    con = sqlite3.connect(db)
    con.execute("""CREATE TABLE forms(
        form_id INTEGER PRIMARY KEY, clean_name TEXT, name TEXT,
        source_path TEXT, doc_type TEXT, form_kind TEXT,
        input_schema TEXT, input_count INT, applicant_count INT,
        office_count INT)""")
    con.execute("""CREATE TABLE schema_address_verification(
        form_id INTEGER PRIMARY KEY, verdict TEXT, ok_cells INT, fail_cells INT)""")
    con.execute("""CREATE TABLE ai_field_interpretation(
        form_id INTEGER PRIMARY KEY, status TEXT, author_count INT,
        not_input_count INT, semantic_count INT)""")
    con.execute("""CREATE TABLE ai_field_verification(
        form_id INTEGER PRIMARY KEY, status TEXT, agreement_rate REAL,
        disagreed_count INT)""")

    rows = [
        # form_id, name, source, schema?, addr, ai1, ai2
        (1, "미착수서식", "a/x.hwpx", None, None, None, None),
        (2, "파싱만됨", "b/x.hwpx", "[]", None, None, None),
        (3, "좌표검증PASS", "onedrive_hwpx/c.hwpx", "[]", "PASS", None, None),
        (4, "좌표검증FAIL", "onedrive_hwpx/d.hwpx", "[]", "FAIL", None, None),
        (5, "AI1차까지", "onedrive_hwpx/e.hwpx", "[]", "PASS", "OK", None),
        (6, "AI2차까지", "onedrive_hwpx/f.hwpx", "[]", "PASS", "OK", "OK"),
    ]
    for fid, nm, sp, schema, addr, ai1, ai2 in rows:
        con.execute(
            "INSERT INTO forms VALUES(?,?,?,?,?,?,?,?,?,?)",
            (fid, nm, nm, sp, "신청신고", "민원신청", schema,
             3 if schema else None, 1 if schema else None,
             2 if schema else None))
        if addr:
            con.execute(
                "INSERT INTO schema_address_verification VALUES(?,?,?,?)",
                (fid, addr, 3 if addr == "PASS" else 1,
                 0 if addr == "PASS" else 2))
        if ai1:
            con.execute(
                "INSERT INTO ai_field_interpretation VALUES(?,?,?,?,?)",
                (fid, ai1, 2, 1, 1))
        if ai2:
            con.execute(
                "INSERT INTO ai_field_verification VALUES(?,?,?,?)",
                (fid, ai2, 0.9, 0))
    con.commit()
    con.close()
    return db


def test_stage_classification_follows_furthest_completed_stage(
        tmp_path, monkeypatch):
    monkeypatch.setattr(P, "CATALOG", _make_catalog(tmp_path))
    rows = {r["form_id"]: r for r in P.query_index()}
    assert rows[1]["stage"] == P.STAGE_NONE
    assert rows[2]["stage"] == P.STAGE_PARSED
    assert rows[3]["stage"] == P.STAGE_ADDR_OK
    assert rows[4]["stage"] == P.STAGE_ADDR_FAIL
    assert rows[5]["stage"] == P.STAGE_AI1
    assert rows[6]["stage"] == P.STAGE_AI2


def test_scope_filters_by_source_path_substring(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "CATALOG", _make_catalog(tmp_path))
    rows = P.query_index(scope="onedrive_hwpx")
    assert {r["form_id"] for r in rows} == {3, 4, 5, 6}


def test_no_scope_returns_everything(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "CATALOG", _make_catalog(tmp_path))
    rows = P.query_index()
    assert len(rows) == 6


def test_write_index_covers_all_rows_and_is_valid_jsonl(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "CATALOG", _make_catalog(tmp_path))
    rows = P.query_index()
    jsonl_path, md_path = P.write_index(rows, out_dir=tmp_path / "out")
    lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 6
    parsed = [json.loads(l) for l in lines]
    assert {p["form_id"] for p in parsed} == {1, 2, 3, 4, 5, 6}
    md = md_path.read_text(encoding="utf-8")
    assert "전체 6건" in md
    for fid in range(1, 7):
        assert f"#{fid}" in md
