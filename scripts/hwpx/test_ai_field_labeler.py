"""HWPX-AI-FIELD-LABELER-01 감리검사.

규칙 fallback / AI 채택 / 저신뢰 거부 / 안전표 원천제외 / 예외 안전강등 +
form_template_store 통합을 검증한다. 외부 의존 없음.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "pipeline"))

import ai_field_labeler as labeler  # noqa: E402
import form_template_store as store  # noqa: E402

FIXED_NOW = datetime(2026, 7, 22, tzinfo=timezone.utc)


@dataclass
class FakeSlot:
    tableId: str
    fieldGuess: str
    labelText: str
    row: int
    col: int
    confidence: float = 0.0
    slotId: str = ""


@dataclass
class FakeRecognition:
    formType: str = "application_form"
    tableRoles: dict = field(default_factory=dict)
    enhancedSlots: list = field(default_factory=list)
    unsafeTableIds: list = field(default_factory=list)


def _rec_with_unknowns() -> FakeRecognition:
    return FakeRecognition(
        tableRoles={"t1": "basic_info", "t2": "approval_stamp"},
        enhancedSlots=[
            # 규칙이 잡은 필드(고신뢰) — AI 대상 아님
            FakeSlot("t1", "projectName", "공사명", 0, 1, confidence=0.90,
                     slotId="s_known"),
            # 규칙이 못 잡은 필드 — AI 대상
            FakeSlot("t1", "unknown", "사업명칭", 1, 1, confidence=0.0,
                     slotId="s_unknown"),
            # 직인표 슬롯 — AI에 절대 안 보냄
            FakeSlot("t2", "unknown", "직인", 0, 0, confidence=0.0,
                     slotId="s_stamp"),
        ],
        unsafeTableIds=["t2"],
    )


def test_rule_only_when_no_ai() -> None:
    """AI 미주입 — unknown 유지 + 경고."""
    out = labeler.enrich_recognition_with_ai(_rec_with_unknowns(), None)
    assert out.aiLabeledCount == 0
    assert "s_unknown" in out.stillUnknown
    assert any(w["code"] == "AI_LABELER_NOT_INJECTED" for w in out.warnings)
    print("PASS rule_only_when_no_ai")


def test_ai_labels_unknown_slot() -> None:
    """AI가 unknown 슬롯을 고신뢰로 라벨 → 채택 + 출처=ai."""
    def ai_fn(slots):
        return [{"slotId": s["slotId"], "fieldGuess": "siteName",
                 "confidence": 0.88, "reason": "라벨 '사업명칭' → 현장명"}
                for s in slots]
    out = labeler.enrich_recognition_with_ai(_rec_with_unknowns(), ai_fn)
    enriched = {s.slotId: s for s in out.enhancedSlots}
    assert out.aiLabeledCount == 1
    assert enriched["s_unknown"].fieldGuess == "siteName"
    assert enriched["s_unknown"].fieldSource == labeler.SRC_AI
    # 규칙이 잡은 건 그대로(출처 rule)
    assert enriched["s_known"].fieldSource == labeler.SRC_RULE
    print("PASS ai_labels_unknown_slot")


def test_low_confidence_ai_rejected() -> None:
    """AI 답이 임계값 미만 → unknown 유지(사람 셋팅)."""
    def ai_fn(slots):
        return [{"slotId": s["slotId"], "fieldGuess": "siteName",
                 "confidence": 0.55} for s in slots]
    out = labeler.enrich_recognition_with_ai(_rec_with_unknowns(), ai_fn)
    assert out.aiLabeledCount == 0
    assert "s_unknown" in out.stillUnknown
    print("PASS low_confidence_ai_rejected")


def test_unsafe_slots_never_sent_to_ai() -> None:
    """직인표 슬롯은 AI 페이로드에 포함되지 않는다."""
    seen_ids = []
    def ai_fn(slots):
        seen_ids.extend(s["slotId"] for s in slots)
        return []
    labeler.enrich_recognition_with_ai(_rec_with_unknowns(), ai_fn)
    assert "s_stamp" not in seen_ids, "직인표 슬롯이 AI로 샜다"
    assert "s_known" not in seen_ids, "고신뢰 규칙 슬롯이 불필요하게 AI로 갔다"
    assert seen_ids == ["s_unknown"]
    print("PASS unsafe_slots_never_sent_to_ai")


def test_ai_exception_safe_fallback() -> None:
    """AI 호출 예외 → 규칙 결과로 안전 강등."""
    def ai_fn(slots):
        raise RuntimeError("model timeout")
    out = labeler.enrich_recognition_with_ai(_rec_with_unknowns(), ai_fn)
    assert out.aiLabeledCount == 0
    assert any(e["stage"] == "ai_labeling" for e in out.errors)
    assert "s_unknown" in out.stillUnknown
    print("PASS ai_exception_safe_fallback")


def test_integration_enrich_then_template() -> None:
    """통합 — AI 강화 결과가 그대로 템플릿 셋팅으로 흐른다."""
    def ai_fn(slots):
        return [{"slotId": s["slotId"], "fieldGuess": "siteName",
                 "confidence": 0.90, "reason": "AI"} for s in slots]
    enriched = labeler.enrich_recognition_with_ai(_rec_with_unknowns(), ai_fn)

    tpl = store.build_template_from_recognition(
        form_name="착공신고서",
        recognition_result=enriched,   # EnrichedRecognition 그대로 소비
        required_field_keys={"projectName"},
        now=FIXED_NOW,
    )
    keys = {b.fieldKey for b in tpl.bindings}
    # 규칙(projectName) + AI(siteName) 모두 바인딩, 직인표는 제외
    assert keys == {"projectName", "siteName"}, keys
    assert tpl.excludedTableIds == ["t2"]

    plan = store.apply_template(tpl, {
        "projectName": "행복아파트", "siteName": "서울 강남",
    })
    assert plan.status == store.PLAN_READY
    assert len(plan.cellWrites) == 2
    print("PASS integration_enrich_then_template")


def _run_all() -> int:
    tests = [
        test_rule_only_when_no_ai,
        test_ai_labels_unknown_slot,
        test_low_confidence_ai_rejected,
        test_unsafe_slots_never_sent_to_ai,
        test_ai_exception_safe_fallback,
        test_integration_enrich_then_template,
    ]
    failed = 0
    for t in tests:
        try:
            t()
        except AssertionError as exc:
            failed += 1
            print(f"FAIL {t.__name__}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_run_all())
