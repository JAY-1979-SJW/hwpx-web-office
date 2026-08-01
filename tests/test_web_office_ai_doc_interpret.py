"""AI 문서 해석·검증·드라이 런 감리.

기준서: docs/design/hwpx_ai_doc_interpretation_fill_standard.md
고정하는 것:
  · 문맥 추출이 왼쪽 칸/위 머리글/서식 제목을 제대로 찾는다 (순수)
  · AI 경계는 runner 주입으로 CLI 없이 시험된다
  · 비창조 검증 — 소스에 없는 값은 기계적으로 폐기된다
  · 주소 검증 — form_direct_fill 과 같은 규칙으로 실파일 대조
  · 드라이 런은 기입하지 않고, 게이트가 §4.5 를 강제한다
"""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

PR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PR))
sys.path.insert(0, str(PR / "scripts/hwpx"))

from scripts.hwpx.web_office.ai_doc_context import (  # noqa: E402
    build_context_fields, cell_text_index, context_for_input, document_title)
from scripts.hwpx.web_office.ai_doc_interpret import (  # noqa: E402
    RunnerError, build_interpretation_prompt, propose_with_context)
from scripts.hwpx.web_office.ai_fill_validate import (  # noqa: E402
    apply_address_results, gate_verdict, validate_non_source,
    value_from_source, verify_addresses)

HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"


# ── 합성 documentModel ──────────────────────────────────────────

def _doc_model():
    return {
        "cells": [
            {"cellId": "cell_t_s0_000_r0_c0", "text": "성명"},
            {"cellId": "cell_t_s0_000_r0_c1", "text": ""},       # 입력칸
            {"cellId": "cell_t_s0_000_r1_c0", "text": "연락처"},
            {"cellId": "cell_t_s0_000_r1_c1", "text": ""},       # 입력칸
            {"cellId": "cell_t_s0_001_r0_c0", "text": "신고인"},
            {"cellId": "cell_t_s0_001_r1_c0", "text": ""},       # 위 머리글형
        ],
        "paragraphs": [
            {"paragraphId": "par_b0_p0", "containerScope": {"kind": "block"},
             "runs": [{"text": "폐수배출시설 설치허가 신청서"}]},
            {"paragraphId": "par_t_s0_000_r0_c0_p0",
             "containerScope": {"kind": "cell"},
             "runs": [{"text": "성명"}]},
        ],
    }


def _inputs():
    return [
        {"label": "성명", "role": "applicant", "inputType": "text",
         "semantic": "name", "subject": "self", "sensitive": False,
         "paragraphId": "par_t_s0_000_r0_c1_p0",
         "tableIndex": 0, "row": 0, "col": 1},
        {"label": "연락처", "role": "applicant", "inputType": "text",
         "semantic": "phone", "subject": "self", "sensitive": False,
         "paragraphId": "par_t_s0_000_r1_c1_p0",
         "tableIndex": 0, "row": 1, "col": 1},
        {"label": "", "role": "applicant", "inputType": "text",
         "semantic": "", "subject": "self", "sensitive": False,
         "paragraphId": "par_t_s0_001_r1_c0_p0",
         "tableIndex": 1, "row": 1, "col": 0},
        {"label": "확인", "role": "office", "inputType": "text",
         "semantic": "", "subject": "self", "sensitive": False,
         "paragraphId": "par_t_s0_000_r9_c9_p0",
         "tableIndex": 0, "row": 9, "col": 9},
    ]


# ── 문맥 추출 (순수) ────────────────────────────────────────────

def test_cell_text_index_and_title():
    idx = cell_text_index(_doc_model())
    assert idx[(0, 0, 0, 0)] == "성명"
    assert idx[(0, 1, 0, 0)] == "신고인"
    assert document_title(_doc_model()) == "폐수배출시설 설치허가 신청서"


def test_context_left_and_up():
    idx = cell_text_index(_doc_model())
    left = context_for_input(
        {"paragraphId": "par_t_s0_000_r1_c1_p0"}, idx)
    assert left["left"] == "연락처"
    up = context_for_input(
        {"paragraphId": "par_t_s0_001_r1_c0_p0"}, idx)
    assert up["up"] == "신고인"


def test_build_context_fields_applicant_only_key_is_pid():
    fields = build_context_fields(_inputs(), _doc_model(), title="대체제목")
    keys = [f["key"] for f in fields]
    assert keys == ["par_t_s0_000_r0_c1_p0", "par_t_s0_000_r1_c1_p0",
                    "par_t_s0_001_r1_c0_p0"]          # office 제외
    assert all(f["context"]["title"] == "폐수배출시설 설치허가 신청서"
               for f in fields)


# ── AI 경계 (runner 주입) ───────────────────────────────────────

def _fields():
    return build_context_fields(_inputs(), _doc_model())


SOURCE = {"성명": "홍길동", "전화번호": "010-1234-5678"}


def test_prompt_contains_context_and_rules():
    p = build_interpretation_prompt(_fields(), SOURCE)
    assert "par_t_s0_000_r1_c1_p0" in p          # key
    assert "연락처" in p                          # left 문맥
    assert "신고인" in p                          # up 문맥
    assert "폐수배출시설" in p                     # 제목
    assert "JSON 배열만" in p and "sourceField" in p
    assert "지어내는 것은 금지" in p


def test_propose_maps_by_key_not_label():
    def fake_runner(prompt):
        return ('[{"key":"par_t_s0_000_r1_c1_p0","value":"010-1234-5678",'
                '"sourceField":"전화번호","confidence":0.9},'
                '{"key":"par_unknown","value":"x","sourceField":"성명",'
                '"confidence":0.5}]')
    res = propose_with_context(_fields(), SOURCE, runner=fake_runner)
    assert res["ok"] is True and res["mode"] == "doc_context"
    assert [p["key"] for p in res["proposals"]] == ["par_t_s0_000_r1_c1_p0"]
    assert res["proposals"][0]["sourceField"] == "전화번호"


def test_propose_holds_third_party_and_flags_sensitive():
    fields = _fields()
    fields[0]["subject"] = "thirdParty"
    fields[0]["label"] = "법정대리인성명"
    fields[1]["sensitive"] = True

    def fake_runner(prompt):
        assert "법정대리인성명" not in prompt      # 라벨조차 안 보낸다
        return ('[{"key":"par_t_s0_000_r1_c1_p0","value":"010-1234-5678",'
                '"sourceField":"전화번호","confidence":0.9}]')
    res = propose_with_context(fields, SOURCE, runner=fake_runner)
    assert [h["label"] for h in res["heldForThirdParty"]] == ["법정대리인성명"]
    assert res["proposals"][0]["requiresConfirmation"] is True


def test_propose_requires_source_and_maps_runner_error():
    res = propose_with_context(_fields(), {}, runner=lambda p: "[]")
    assert res["ok"] is False and res["error"] == "SOURCE_DATA_MISSING"

    def boom(prompt):
        raise RunnerError("AI_TIMEOUT")
    res = propose_with_context(_fields(), SOURCE, runner=boom)
    assert res["ok"] is False and res["error"] == "AI_TIMEOUT"


# ── 비창조 검증 ─────────────────────────────────────────────────

def test_value_from_source_normalizes():
    src = {"전화번호": "010-1234-5678", "주소": "서울특별시 중구 세종대로 110"}
    assert value_from_source("01012345678", src) == "전화번호"
    assert value_from_source("서울특별시 중구", src) == "주소"
    assert value_from_source("지어낸값", src) is None


def test_validate_non_source_rejects_fabrication():
    props = [
        {"key": "a", "value": "홍길동", "sourceField": "성명"},
        {"key": "b", "value": "그럴듯한 지어낸 값", "sourceField": "성명"},
    ]
    ok, bad = validate_non_source(props, {"성명": "홍길동"})
    assert [p["key"] for p in ok] == ["a"]
    assert ok[0]["sourceFieldVerified"] == "성명"
    assert bad[0]["reason"] == "NON_SOURCE_VALUE"


def test_gate_fails_only_when_bad_slips_into_accepted():
    ok = [{"key": "a", "sourceFieldVerified": "성명"}]
    bad = [{"key": "b", "reason": "NON_SOURCE_VALUE"}]
    assert gate_verdict(ok, bad, [])["pass"] is True       # 걸러졌으면 PASS
    leaked = ok + [{"key": "c"}]                            # 미검증이 통과분에
    assert gate_verdict(leaked, [], [])["pass"] is False


# ── 주소 검증 (실파일, form_direct_fill 규칙) ───────────────────

def _write_fixture(path: Path) -> None:
    sec = (
        f'<hp:sec xmlns:hp="{HP}"><hp:tbl>'
        '<hp:tr><hp:tc><hp:p paraPrIDRef="1">'
        '<hp:run charPrIDRef="1"><hp:t>성명</hp:t></hp:run></hp:p></hp:tc>'
        '<hp:tc><hp:p paraPrIDRef="1">'
        '<hp:run charPrIDRef="1"><hp:t/></hp:run></hp:p></hp:tc></hp:tr>'
        "</hp:tbl></hp:sec>"
    )
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mimetype", "application/hwp+zip")
        z.writestr("Contents/section0.xml", sec)


def test_verify_addresses_against_real_file(tmp_path):
    _write_fixture(tmp_path / "f.hwpx")
    fails = verify_addresses(
        "f.hwpx",
        ["par_t_s0_000_r0_c1_p0",       # 실재
         "par_t_s0_000_r5_c0_p0",       # 행 없음
         "par_t_s0_007_r0_c0_p0",       # 표 없음
         "garbage"],
        project_root=tmp_path)
    assert "par_t_s0_000_r0_c1_p0" not in fails
    assert fails["par_t_s0_000_r5_c0_p0"] == "ROW_NOT_FOUND"
    assert fails["par_t_s0_007_r0_c0_p0"] == "TABLE_NOT_FOUND"
    assert fails["garbage"] == "PID_UNPARSEABLE"


def test_apply_address_results_moves_to_rejected():
    ok, bad = apply_address_results(
        [{"key": "p1"}, {"key": "p2"}], {"p2": "ROW_NOT_FOUND"})
    assert [p["key"] for p in ok] == ["p1"]
    assert bad[0]["reason"] == "ADDRESS_UNRESOLVED"


# ── 드라이 런 (기입 없음 · 게이트) ──────────────────────────────

def test_dry_run_never_writes_and_gates(tmp_path, monkeypatch):
    import scripts.hwpx.web_office.ai_fill_dry_run as dr

    fixture = tmp_path / "f.hwpx"
    _write_fixture(fixture)
    sha0 = fixture.read_bytes()

    doc_model = _doc_model()
    fake_env = {"data": {"verdict": "PASS", "documentModel": doc_model,
                         "renderPayload": {}}}
    monkeypatch.setattr(
        "scripts.hwpx.web_office.editor_api_route.call_hwpx_load",
        lambda req, project_root: fake_env)
    monkeypatch.setattr(
        "scripts.hwpx.web_office.form_input_schema.build_input_schema",
        lambda dm, rp, name="", field_count=None: {
            "inputs": [
                {"label": "성명", "role": "applicant", "inputType": "text",
                 "semantic": "name", "subject": "self", "sensitive": False,
                 "paragraphId": "par_t_s0_000_r0_c1_p0",
                 "tableIndex": 0, "row": 0, "col": 1},
                {"label": "연락처", "role": "applicant", "inputType": "text",
                 "semantic": "phone", "subject": "self", "sensitive": False,
                 "paragraphId": "par_t_s0_000_r5_c0_p0",   # 실파일에 없음
                 "tableIndex": 0, "row": 5, "col": 0},
            ],
            "cleanName": "시험서식", "formKind": "민원신청"})

    def fake_runner(prompt):
        return ('[{"key":"par_t_s0_000_r0_c1_p0","value":"홍길동",'
                '"sourceField":"성명","confidence":0.9},'
                '{"key":"par_t_s0_000_r5_c0_p0","value":"010-1234-5678",'
                '"sourceField":"전화번호","confidence":0.8}]')

    report = dr.run_dry_run("f.hwpx", {"성명": "홍길동",
                                       "전화번호": "010-1234-5678"},
                            project_root=tmp_path, runner=fake_runner)
    assert report["dryRun"] is True
    assert fixture.read_bytes() == sha0                 # 기입 없음
    assert [p["key"] for p in report["proposals"]] == \
        ["par_t_s0_000_r0_c1_p0"]
    assert report["rejected"][0]["reason"] == "ADDRESS_UNRESOLVED"
    assert report["verdict"] == "PASS"                  # 걸러냈으므로 PASS
    assert report["gate"]["acceptedCount"] == 1
