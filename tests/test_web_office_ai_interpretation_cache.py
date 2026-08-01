"""AI 필드 해석 캐시 감리.

고정하는 것:
  · 해석 프롬프트가 오염(용지규격·법령표시·안내문) 제외 규칙을 담는다
  · AI 가 지어낸 칸 주소(key)는 캐시에 못 들어간다
  · 모르는 semantic 은 태그만 비우고 해석은 살린다
  · promote 는 게이트 미달이면 거부하고, 통과 시 오염을 noise 로 낮추고
    빈 semantic 만 채운다(기존 태그 불변)
  · 캐시에 **값**은 저장되지 않는다(개인정보 §4)
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

PR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PR))
sys.path.insert(0, str(PR / "scripts/hwpx"))

from scripts.hwpx.web_office import build_ai_interpretation_cache as B  # noqa: E402
from scripts.hwpx.web_office.ai_field_interpretation import (  # noqa: E402
    ALLOWED_SEMANTIC, build_interpretation_prompt, interpret_fields,
    should_demote, validate_interpretation)


def _fields():
    return [
        {"key": "par_t_s0_000_r0_c1_p0", "label": "성명",
         "context": {"title": "설치허가 신청서", "left": "성명", "up": ""}},
        {"key": "par_t_s0_000_r1_c0_p0",
         "label": "210mm×297mm(백상지 80g/m2)",
         "context": {"title": "설치허가 신청서", "left": "", "up": ""}},
    ]


# ── 프롬프트 ────────────────────────────────────────────────────

def test_prompt_carries_pollution_rules_and_vocabulary():
    p = build_interpretation_prompt(_fields())
    assert "210mm×297mm" in p                # 오염 예시가 규칙에 있다
    assert "별지" in p and "※" in p
    assert "값을 지어내지 마세요" in p
    assert "residentNo" in p                  # 허용 어휘 노출
    assert "설치허가 신청서" in p             # 문서 제목 문맥


# ── 검증 ────────────────────────────────────────────────────────

def test_validate_rejects_invented_and_duplicate_keys():
    raw = [
        {"key": "par_t_s0_000_r0_c1_p0", "isInput": True, "semantic": "name"},
        {"key": "par_지어낸_주소", "isInput": True, "semantic": "name"},
        {"key": "par_t_s0_000_r0_c1_p0", "isInput": True},      # 중복
    ]
    ok, bad = validate_interpretation(raw, _fields())
    assert [r["key"] for r in ok] == ["par_t_s0_000_r0_c1_p0"]
    assert {r["reason"] for r in bad} == {"INVENTED_KEY", "DUPLICATE_KEY"}


def test_validate_blanks_unknown_semantic_but_keeps_row():
    raw = [{"key": "par_t_s0_000_r0_c1_p0", "isInput": True,
            "semantic": "존재하지않는태그", "meaning": "신청인 성명"}]
    ok, _ = validate_interpretation(raw, _fields())
    assert ok[0]["semantic"] == ""
    assert ok[0]["meaning"] == "신청인 성명"       # 해석은 살린다


def test_allowed_semantic_matches_planner_vocabulary():
    # planner 가 모르는 태그를 캐시에 넣으면 조용히 무시된다
    from scripts.hwpx.web_office.form_fill_planner import _PROMPT
    assert set(_PROMPT).issubset(ALLOWED_SEMANTIC)


# ── 해석 (runner 주입) ──────────────────────────────────────────

def test_interpret_fields_counts_and_never_returns_values():
    def fake_runner(prompt):
        return json.dumps([
            {"key": "par_t_s0_000_r0_c1_p0", "isInput": True,
             "semantic": "name", "meaning": "신청인 성명",
             "profileKey": "성명", "question": "성명을 알려주세요",
             "confidence": 0.95},
            {"key": "par_t_s0_000_r1_c0_p0", "isInput": False,
             "semantic": "", "meaning": "용지 규격 표기",
             "confidence": 0.9},
        ], ensure_ascii=False)
    out = interpret_fields(_fields(), runner=fake_runner)
    assert out["ok"] is True
    assert out["inputCount"] == 1 and out["notInputCount"] == 1
    assert out["semanticCount"] == 1 and out["coverage"] == 1.0
    # 캐시 산출물에 '값' 필드는 존재하지 않는다 (§4 개인정보)
    for r in out["interpretations"]:
        assert "value" not in r


def test_interpret_fields_maps_runner_error():
    from scripts.hwpx.web_office.ai_doc_interpret import RunnerError

    def boom(prompt):
        raise RunnerError("AI_TIMEOUT")
    out = interpret_fields(_fields(), runner=boom)
    assert out["ok"] is False and out["error"] == "AI_TIMEOUT"


# ── 강등 안전장치 (AI 단독 판정 금지) ──────────────────────────

def test_demote_requires_both_ai_and_rule_agreement():
    # AI 가 '입력칸 아님'이라 해도 라벨이 정상이면 살린다 — 파일럿에서
    # AI 단독 판정이 정상칸의 15.8% 를 죽였다.
    assert should_demote({"isInput": False, "confidence": 0.99,
                          "label": "사건과의관계"}) is False
    # 두 신호가 일치할 때만 강등
    assert should_demote({"isInput": False, "confidence": 0.9,
                          "label": "210mm×297mm(백상지 80g/m2)"}) is True


def test_demote_refuses_low_confidence_and_input_cells():
    poll = "■ 수산자원관리법시행규칙[별지제17호서식]"
    assert should_demote({"isInput": False, "confidence": 0.3,
                          "label": poll}) is False       # 확신 부족
    assert should_demote({"isInput": True, "confidence": 0.99,
                          "label": poll}) is False       # AI 가 입력칸이라 함


def test_pollution_patterns_cover_observed_real_labels():
    # 전수 조사에서 실제로 신청인칸으로 등록돼 있던 라벨들
    for label in ("210mm×297mm(백상지 80g/m2)",
                  "■ 소방시설설치및관리에관한법률시행규칙 [별지제12호서식]",
                  "※ [ ]에는해당되는곳에 √표를합니다.",
                  "(자르는선)"):
        assert should_demote({"isInput": False, "confidence": 0.9,
                              "label": label}) is True, label
    # 반대로 정상 입력 라벨은 절대 후보에 못 오른다.
    # ※ 로 시작하는 뒤 3개는 실제 서식의 진짜 입력 항목이다 — ※ 접두어
    # 만으로 거르면 이것들이 죽는다(전수에서 확인된 실사례).
    for label in ("성명", "사업장소재지", "착공일년월일", "심판번호",
                  "가축분뇨배출량(m3/일)",
                  "※ 건축면적(m2)", "※ 연면적(m2)",
                  "※ 12 특수구조건축물유형"):
        assert should_demote({"isInput": False, "confidence": 0.99,
                              "label": label}) is False, label


# ── promote (임시 카탈로그) ─────────────────────────────────────

def _temp_catalog(tmp_path: Path, staged_status="OK") -> Path:
    db = tmp_path / "catalog.sqlite"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE forms(form_id INTEGER PRIMARY KEY,"
                " input_schema TEXT, input_count INT, applicant_count INT,"
                " office_count INT, doc_type TEXT, form_kind TEXT)")
    schema = [
        {"label": "성명", "role": "applicant", "semantic": "",
         "paragraphId": "p1"},
        {"label": "주소", "role": "applicant", "semantic": "address",
         "paragraphId": "p2"},
        {"label": "210mm×297mm(백상지 80g/m2)", "role": "applicant",
         "semantic": "", "paragraphId": "p3"},
    ]
    con.execute("INSERT INTO forms VALUES(1,?,3,3,0,'신청신고','민원신청')",
                (json.dumps(schema, ensure_ascii=False),))
    con.execute(B.DDL)
    interp = [
        {"key": "p1", "isInput": True, "semantic": "name",
         "meaning": "신청인 성명", "profileKey": "성명",
         "question": "성명을 알려주세요", "confidence": 0.95},
        {"key": "p2", "isInput": True, "semantic": "orgName",
         "meaning": "주소", "profileKey": "", "question": "",
         "confidence": 0.5},
        {"key": "p3", "isInput": False, "semantic": "",
         "meaning": "용지 규격", "profileKey": "", "question": "",
         "confidence": 0.9},
    ]
    con.execute(
        f"INSERT INTO {B.STAGING}(form_id, status, interpretations)"
        f" VALUES(1,?,?)",
        (staged_status, json.dumps(interp, ensure_ascii=False)))
    con.commit()
    con.close()
    return db


def test_promote_demotes_pollution_and_fills_blank_semantic(
        tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(B, "CATALOG", _temp_catalog(tmp_path))
    B.promote()
    con = sqlite3.connect(tmp_path / "catalog.sqlite")
    raw, ic, ac = con.execute(
        "SELECT input_schema, input_count, applicant_count"
        " FROM forms WHERE form_id=1").fetchone()
    con.close()
    by_pid = {f["paragraphId"]: f for f in json.loads(raw)}
    assert by_pid["p3"]["role"] == "noise"        # 오염 강등
    assert by_pid["p1"]["semantic"] == "name"     # 빈 태그 채움
    assert by_pid["p2"]["semantic"] == "address"  # 기존 태그 불변
    assert by_pid["p1"]["aiQuestion"] == "성명을 알려주세요"
    assert ic == 2 and ac == 2                    # 집계 재계산
    assert "PROMOTED" in capsys.readouterr().out


def _dead_form_catalog(tmp_path: Path, doc_type="기타",
                       form_kind="행정내부") -> Path:
    """검측요청서 형상 — 전 칸 office(신청인칸 0)."""
    db = tmp_path / "catalog.sqlite"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE forms(form_id INTEGER PRIMARY KEY,"
                " input_schema TEXT, input_count INT, applicant_count INT,"
                " office_count INT, doc_type TEXT, form_kind TEXT)")
    schema = [
        {"label": "검측부위", "role": "office", "semantic": "",
         "paragraphId": "p1"},
        {"label": "검측결과", "role": "office", "semantic": "",
         "paragraphId": "p2"},
    ]
    con.execute("INSERT INTO forms VALUES(1,?,2,0,2,?,?)",
                (json.dumps(schema, ensure_ascii=False), doc_type, form_kind))
    con.execute(B.DDL)
    interp = [
        # 시공사가 적는 칸 → 되살린다
        {"key": "p1", "isInput": True, "filledBy": "작성자", "semantic": "",
         "ruleRole": "office", "label": "검측부위", "meaning": "검측 부위",
         "question": "검측부위를 알려주세요", "confidence": 0.9},
        # 감리자가 적는 칸 → 그대로 관계자
        {"key": "p2", "isInput": True, "filledBy": "상대방", "semantic": "",
         "ruleRole": "office", "label": "검측결과", "meaning": "검측 결과",
         "question": "", "confidence": 0.9},
    ]
    con.execute(
        f"INSERT INTO {B.STAGING}(form_id, status, interpretations)"
        f" VALUES(1,'OK',?)",
        (json.dumps(interp, ensure_ascii=False),))
    con.commit()
    con.close()
    return db


def _roles_after_promote(tmp_path: Path) -> dict:
    con = sqlite3.connect(tmp_path / "catalog.sqlite")
    raw, app = con.execute(
        "SELECT input_schema, applicant_count FROM forms"
        " WHERE form_id=1").fetchone()
    con.close()
    return {"roles": {f["paragraphId"]: f["role"] for f in json.loads(raw)},
            "applicantCount": app}


def test_promote_revives_dead_business_document(tmp_path, monkeypatch, capsys):
    # 검측요청서: 시공사 칸만 되살아나고 감리자 칸은 그대로 관계자
    monkeypatch.setattr(B, "CATALOG", _dead_form_catalog(tmp_path))
    B.promote()
    after = _roles_after_promote(tmp_path)
    assert after["roles"]["p1"] == "applicant"
    assert after["roles"]["p2"] == "office"
    assert after["applicantCount"] == 1
    assert "역할교정" in capsys.readouterr().out


def test_promote_never_revives_protected_ledger(tmp_path, monkeypatch):
    # 대장기록은 안전규칙상 전 칸 관계자가 정답 — AI 가 뭐라 하든 불변
    monkeypatch.setattr(B, "CATALOG",
                        _dead_form_catalog(tmp_path, doc_type="대장기록"))
    B.promote()
    after = _roles_after_promote(tmp_path)
    assert after["roles"] == {"p1": "office", "p2": "office"}
    assert after["applicantCount"] == 0


def test_promote_refuses_when_ok_ratio_below_gate(
        tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(B, "CATALOG",
                        _temp_catalog(tmp_path, staged_status="AI_FAILED"))
    B.promote()  # noqa: F841 — 아래에서 카탈로그 무변경을 확인한다
    out = capsys.readouterr().out
    assert "REJECTED" in out
    con = sqlite3.connect(tmp_path / "catalog.sqlite")
    raw = con.execute(
        "SELECT input_schema FROM forms WHERE form_id=1").fetchone()[0]
    con.close()
    # 거부됐으면 카탈로그는 그대로다
    assert all(f["role"] == "applicant" for f in json.loads(raw))
