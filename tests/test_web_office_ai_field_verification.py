"""2차 독립 검증 감리 (§4.6 두 신호).

고정하는 것:
  · 검증 프롬프트에 1차 판정이 실리지 않는다(앵커링 차단)
  · 일치 대조는 프로그램이 한다 — 모델에게 "동의하십니까"를 묻지 않는다
  · 두 판정이 일치한 칸만 반영 대상(authorAgreed)
  · 검증이 있으면 확신도 문턱은 쓰이지 않는다 — 낮은 확신도도 통과,
    높은 확신도도 2차가 뒤집으면 탈락
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

PR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PR))
sys.path.insert(0, str(PR / "scripts/hwpx"))

from scripts.hwpx.web_office.ai_field_interpretation import (  # noqa: E402
    should_promote_to_user)
from scripts.hwpx.web_office.ai_field_verification import (  # noqa: E402
    agreement, build_verification_prompt, parse_verification, verify_fields)


def _fields():
    return [
        {"key": "k1", "label": "검측부위",
         "context": {"title": "검측요청서", "left": "위치및공종", "up": ""}},
        {"key": "k2", "label": "검측결과",
         "context": {"title": "검측요청서", "left": "", "up": ""}},
        {"key": "k3", "label": "210mm×297mm(백상지 80g/m2)",
         "context": {"title": "검측요청서", "left": "", "up": ""}},
    ]


def _interp(filled=("작성자", "상대방", None), conf=(0.55, 0.9, 0.9)):
    out = []
    for n, (k, f, c) in enumerate(zip(("k1", "k2", "k3"), filled, conf)):
        out.append({"key": k, "label": _fields()[n]["label"],
                    "isInput": f is not None, "filledBy": f or "",
                    "confidence": c, "ruleRole": "office"})
    return out


# ── 앵커링 차단 ─────────────────────────────────────────────────

def test_prompt_hides_first_pass_judgment():
    p = build_verification_prompt(_fields())
    assert "검측부위" in p and "검측요청서" in p       # 문서 정보는 준다
    # 1차 판정 어휘는 절대 실리지 않는다
    for leaked in ("작성자", "상대방", "filledBy", "confidence", "isInput"):
        assert leaked not in p, leaked
    # 각도가 다른 질문(사람 중심)이어야 한다
    assert "제출하는 쪽" in p and "내가 직접 채워야" in p
    assert '"fills"' in p or "fills=" in p


def test_prompt_never_asks_for_agreement():
    # "동의하십니까"류는 대개 동의로 기운다 — 독립 판정만 요구한다
    p = build_verification_prompt(_fields())
    for bad in ("동의", "맞습니까", "확인해 주", "검토하여 승인"):
        assert bad not in p, bad


# ── 파싱 ────────────────────────────────────────────────────────

def test_parse_drops_unknown_keys_and_bad_values():
    raw = [{"key": "k1", "fills": "self"},
           {"key": "없는키", "fills": "self"},
           {"key": "k2", "fills": "쓰레기값"},
           {"key": "k3", "fills": "NONE"}]          # 대소문자 허용
    v = parse_verification(raw, _fields())
    assert v == {"k1": "self", "k3": "none"}


# ── 일치 대조 ───────────────────────────────────────────────────

def test_agreement_only_counts_independent_match():
    ag = agreement(_interp(), {"k1": "self", "k2": "other", "k3": "none"})
    assert ag["authorAgreed"] == ["k1"]        # 둘 다 작성자
    assert ag["notInputAgreed"] == ["k3"]      # 둘 다 입력칸 아님
    assert ag["disagreed"] == []


def test_agreement_rate_counts_counterparty_match():
    # 실사례: 1차 상대방10/작성자7 · 2차 other10/self7 은 **완전 일치**인데
    # 상대방 일치를 세지 않으면 0.41 로 보여 지표가 사람을 속인다.
    interp = _interp(filled=("작성자", "상대방", None))
    ag = agreement(interp, {"k1": "self", "k2": "other", "k3": "none"})
    assert ag["agreementRate"] == 1.0
    assert ag["otherAgreed"] == ["k2"]


def test_agreement_flags_conflict_and_missing():
    # 1차 작성자 · 2차 상대방 → 불일치(반영 안 함)
    ag = agreement(_interp(), {"k1": "other", "k2": "other"})
    assert ag["authorAgreed"] == []
    assert ag["disagreed"][0]["key"] == "k1"
    assert ag["unverified"] == ["k3"]          # 2차가 판정 안 한 칸


# ── 확신도 문턱 대체 ────────────────────────────────────────────

def _judged(conf: float):
    return {"isInput": True, "filledBy": "작성자", "confidence": conf,
            "ruleRole": "office", "label": "검측부위"}


def test_verification_overrides_low_confidence():
    # 실사례: Sonnet 이 시공사명을 정확히 읽고도 0.60 을 매겨 탈락했다.
    # 2차가 일치하면 확신도와 무관하게 반영한다.
    args = dict(doc_type="기타", form_kind="행정내부", form_applicant_count=0)
    assert should_promote_to_user(_judged(0.60), **args) is False   # 문턱만
    assert should_promote_to_user(_judged(0.60), verified=True, **args) is True


def test_verification_can_reject_high_confidence():
    # 반대 방향도 성립해야 진짜 게이트다
    args = dict(doc_type="기타", form_kind="행정내부", form_applicant_count=0)
    assert should_promote_to_user(_judged(0.99), **args) is True
    assert should_promote_to_user(_judged(0.99), verified=False,
                                  **args) is False


def test_verification_does_not_bypass_protected_zones():
    # 검증이 일치해도 대장·살아있는 서식은 불변
    assert should_promote_to_user(
        _judged(0.9), doc_type="대장기록", form_kind="행정내부",
        form_applicant_count=0, verified=True) is False
    assert should_promote_to_user(
        _judged(0.9), doc_type="기타", form_kind="행정내부",
        form_applicant_count=7, verified=True) is False


# ── runner 주입 ─────────────────────────────────────────────────

def test_verify_fields_with_injected_runner():
    def fake(prompt):
        return json.dumps([{"key": "k1", "fills": "self"},
                           {"key": "k2", "fills": "other"},
                           {"key": "k3", "fills": "none"}])
    out = verify_fields(_fields(), _interp(), runner=fake)
    assert out["ok"] is True
    assert out["agreement"]["authorAgreed"] == ["k1"]


def test_verify_fields_maps_runner_error():
    from scripts.hwpx.web_office.ai_doc_interpret import RunnerError

    def boom(prompt):
        raise RunnerError("AI_TIMEOUT")
    out = verify_fields(_fields(), _interp(), runner=boom)
    assert out["ok"] is False and out["error"] == "AI_TIMEOUT"
