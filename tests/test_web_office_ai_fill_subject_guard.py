"""AI 채움 제3자 보호 감리.

실제 사고(2026-07-24 종단 시험): /ai-fill 이 신청인 이름을
'법정대리인성명' 칸에 넣으라고 제안했다. 규칙 경로(/fill-plan)는
subject=thirdParty 로 걸렀는데 AI 경로만 안 봤다.

관공서 제출물에 허위 대리인을 기재하는 것은 단순 오류가 아니라 문서
위조에 가깝다(§4 원칙 3). 이 경계를 고정한다.

모델 호출(claude CLI)은 하지 않는다 — 순수 분할·필터 로직만 검증한다.
"""
from __future__ import annotations

import sys
from pathlib import Path

PR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PR))

from scripts.hwpx.web_office.ai_form_fill import (  # noqa: E402
    _effective_subject, partition_by_subject, propose_values)


# ── 라벨 기반 제3자 판정 ────────────────────────────────────────

def test_third_party_labels_detected():
    for lab in ("법정대리인성명", "대리인", "양수인", "양도인",
                "피신청인", "세무대리인"):
        assert _effective_subject({"label": lab}) == "thirdParty", lab


def test_self_labels_pass():
    for lab in ("성명", "주소", "전화번호", "생년월일", "사업장주소"):
        assert _effective_subject({"label": lab}) == "self", lab


def test_client_claim_cannot_downgrade_third_party():
    """클라이언트가 self 라고 우겨도 라벨이 제3자면 제3자다(§4 원칙 4)."""
    f = {"label": "법정대리인성명", "subject": "self"}
    assert _effective_subject(f) == "thirdParty"


def test_client_claim_can_only_escalate():
    """반대로 클라이언트가 thirdParty 라 하면 존중한다(안전한 쪽)."""
    f = {"label": "성명", "subject": "thirdParty"}
    assert _effective_subject(f) == "thirdParty"


# ── 분할 ────────────────────────────────────────────────────────

def test_partition_separates_third_party():
    fields = [{"label": "성명"}, {"label": "법정대리인성명"},
              {"label": "주소"}, {"label": "대리인"}]
    own, third = partition_by_subject(fields)
    assert [f["label"] for f in own] == ["성명", "주소"]
    assert [f["label"] for f in third] == ["법정대리인성명", "대리인"]


# ── propose_values 가 제3자 칸을 AI 로 보내지 않는다 ─────────────

def _no_cli(*a, **k):
    raise AssertionError("제3자만 있으면 claude CLI 를 불러선 안 된다")


def test_only_third_party_never_calls_model(monkeypatch):
    import scripts.hwpx.web_office.ai_form_fill as M
    monkeypatch.setattr(M.subprocess, "run", _no_cli)
    out = propose_values([{"key": "k1", "label": "법정대리인성명"},
                          {"key": "k2", "label": "양수인"}])
    assert out["ok"] is True
    assert out["proposals"] == []
    held = {h["label"] for h in out["heldForThirdParty"]}
    assert held == {"법정대리인성명", "양수인"}
    assert all(h["reason"] == "THIRD_PARTY_FIELD"
               for h in out["heldForThirdParty"])


def test_model_never_sees_third_party_labels(monkeypatch):
    """모델에 보내는 프롬프트에 제3자 라벨이 들어가면 안 된다."""
    import scripts.hwpx.web_office.ai_form_fill as M
    captured = {}

    class _Proc:
        returncode = 0
        stdout = '[{"label":"성명","value":"홍길동","confidence":0.9}]'
        stderr = ""

    def fake_run(cmd, **kw):
        captured["prompt"] = cmd[-1]
        return _Proc()

    monkeypatch.setattr(M.subprocess, "run", fake_run)
    out = propose_values(
        [{"key": "a", "label": "성명"},
         {"key": "b", "label": "법정대리인성명"}],
        source_data={"성명": "홍길동"})

    assert "법정대리인성명" not in captured["prompt"], "제3자 라벨이 모델에 노출됨"
    assert "성명" in captured["prompt"]
    # 제안은 신청인 칸에만
    assert [p["label"] for p in out["proposals"]] == ["성명"]
    assert out["proposals"][0]["subject"] == "self"
    # 제3자 칸은 held 로
    assert [h["label"] for h in out["heldForThirdParty"]] == ["법정대리인성명"]


def test_applicant_name_never_maps_to_legal_rep(monkeypatch):
    """핵심 회귀 — 신청인 이름이 법정대리인 칸 제안으로 나오지 않는다."""
    import scripts.hwpx.web_office.ai_form_fill as M

    class _Proc:
        returncode = 0
        # 모델이 설령 제3자 라벨에 값을 매핑해 보내도(악의/오류)…
        stdout = ('[{"label":"성명","value":"홍길동","confidence":0.9},'
                  '{"label":"법정대리인성명","value":"홍길동","confidence":0.9}]')
        stderr = ""

    monkeypatch.setattr(M.subprocess, "run", lambda *a, **k: _Proc())
    out = propose_values(
        [{"key": "a", "label": "성명"},
         {"key": "b", "label": "법정대리인성명"}],
        source_data={"성명": "홍길동"})
    labels = [p["label"] for p in out["proposals"]]
    assert "법정대리인성명" not in labels, (
        "…그래도 제3자 칸 제안은 결과에 없어야 한다")


# ── 민감칸은 확인 요구 ──────────────────────────────────────────

def test_sensitive_field_requires_confirmation(monkeypatch):
    import scripts.hwpx.web_office.ai_form_fill as M

    class _Proc:
        returncode = 0
        stdout = ('[{"label":"주민등록번호","value":"000000-0000000",'
                  '"confidence":0.9}]')
        stderr = ""

    monkeypatch.setattr(M.subprocess, "run", lambda *a, **k: _Proc())
    out = propose_values(
        [{"key": "a", "label": "주민등록번호", "sensitive": True}],
        source_data={"주민등록번호": "000000-0000000"})
    assert out["proposals"][0]["requiresConfirmation"] is True


def test_ordinary_field_no_confirmation(monkeypatch):
    import scripts.hwpx.web_office.ai_form_fill as M

    class _Proc:
        returncode = 0
        stdout = '[{"label":"주소","value":"서울시","confidence":0.9}]'
        stderr = ""

    monkeypatch.setattr(M.subprocess, "run", lambda *a, **k: _Proc())
    out = propose_values([{"key": "a", "label": "주소"}],
                         source_data={"주소": "서울시"})
    assert out["proposals"][0]["requiresConfirmation"] is False
