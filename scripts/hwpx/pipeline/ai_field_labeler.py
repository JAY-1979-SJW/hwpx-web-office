"""HWPX-AI-FIELD-LABELER-01.

AI 셋팅 조수 — 규칙 인식이 못 잡은 입력칸만 AI로 라벨링하는 하이브리드 계층.

문제(기존):
- `form_recognizer`는 하드코딩 키워드 사전(`_KNOWN_FIELD_HINTS`)으로만 필드를
  판단한다. 사전에 없는 라벨은 `fieldGuess="unknown"`으로 흘려버려, 낯선 서식을
  올리면 셋팅이 비어 버린다.

해결(본 모듈, 하이브리드):
  ① 규칙 1차 스캔 결과(공짜·즉시)를 받는다.
  ② `unknown` / 저신뢰 슬롯만 골라 AI 라벨러(callable)에게 "이 칸 뭐야?"를 묻는다.
  ③ AI 답이 임계값 이상일 때만 채택하고, 출처(fieldSource)를 남긴다.
  ④ 강화된 인식 결과를 반환 → 사람 확인 → `form_template_store`에 저장.

경제성:
- AI는 규칙이 놓친 칸에만 호출된다(전체 아님).
- 셋팅은 일회성 — AI 셋팅 비용이 이후 수백 번 채움에 분산된다.

안전(CLAUDE.md 어댑터 패턴 계승):
- `ai_labeler_fn` 미주입/env 미설정 → 규칙 결과 그대로(AI 없이도 안전 동작).
- 직인/결재/법령 등 unsafe 표 슬롯은 **AI에게 보내지도 않는다** — 규칙이 unsafe로
  판정한 것을 AI가 안전으로 뒤집을 수 없다.
- AI 답이 채택 임계값 미만이면 `unknown`으로 남겨 사람이 셋팅하게 한다.
- raw 개인정보 미참조 — 라벨 텍스트·좌표만.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Callable

CONTRACT_NAME = "HWPX-AI-FIELD-LABELER-01"
CONTRACT_VERSION = "v1"

# adapter_contract.ENV_FLAG_HAIKU 미러 — 단일 출처 유지(값 동일).
ENV_FLAG_HAIKU = "ENABLE_LIVE_HAIKU"

# AI 라벨 채택 임계값: 이 미만이면 unknown 유지(사람이 셋팅).
CONF_ACCEPT_AI = 0.70
# 규칙 신뢰도가 이 미만이면 AI 보강 대상에 포함.
CONF_RULE_CEILING = 0.60

# 출처(provenance)
SRC_RULE = "rule"
SRC_AI = "ai"

# ai_labeler_fn 시그니처:
#   fn(unknown_slots: list[dict]) -> list[dict]
#   in  slot dict : {slotId, labelText, tableId, row, col}
#   out label dict: {slotId, fieldGuess, confidence, reason}
AiFieldLabelerCallable = Callable[[list[dict]], list[dict]]


def ai_enabled() -> bool:
    """ENABLE_LIVE_HAIKU env 게이트 상태."""
    return os.environ.get(ENV_FLAG_HAIKU, "").strip().lower() in ("1", "true", "yes", "on")


# ── 강화 슬롯 / 결과 ─────────────────────────────────────────────────

@dataclass
class LabeledSlot:
    slotId: str
    tableId: str
    fieldGuess: str
    labelText: str
    row: int
    col: int
    visualRow: int = 0
    visualCol: int = 0
    rowSpan: int = 1
    colSpan: int = 1
    confidence: float = 0.0
    fieldSource: str = SRC_RULE     # rule | ai
    aiReason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "slotId": self.slotId,
            "tableId": self.tableId,
            "fieldGuess": self.fieldGuess,
            "labelText": self.labelText,
            "row": self.row,
            "col": self.col,
            "visualRow": self.visualRow,
            "visualCol": self.visualCol,
            "rowSpan": self.rowSpan,
            "colSpan": self.colSpan,
            "confidence": round(self.confidence, 3),
            "fieldSource": self.fieldSource,
            "aiReason": self.aiReason,
        }


@dataclass
class EnrichedRecognition:
    """`form_template_store.build_template_from_recognition`가 그대로 소비 가능한 형태."""
    formType: str = "unknown_form"
    tableRoles: dict[str, str] = field(default_factory=dict)
    enhancedSlots: list[LabeledSlot] = field(default_factory=list)
    unsafeTableIds: list[str] = field(default_factory=list)
    aiLabeledCount: int = 0
    stillUnknown: list[str] = field(default_factory=list)
    warnings: list[dict] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contractName": CONTRACT_NAME,
            "formType": self.formType,
            "tableRoles": self.tableRoles,
            "enhancedSlots": [s.to_dict() for s in self.enhancedSlots],
            "unsafeTableIds": list(self.unsafeTableIds),
            "summary": {
                "totalSlots": len(self.enhancedSlots),
                "aiLabeled": self.aiLabeledCount,
                "stillUnknown": len(self.stillUnknown),
            },
            "stillUnknown": list(self.stillUnknown),
            "warnings": self.warnings,
            "errors": self.errors,
        }


# ── 헬퍼: 인식 결과 → 정규화 슬롯 ────────────────────────────────────

def _read(obj, name, default=None):
    return (obj.get(name, default) if isinstance(obj, dict)
            else getattr(obj, name, default))


def _normalize_slots(recognition_result) -> list[LabeledSlot]:
    slots_raw = _read(recognition_result, "enhancedSlots", []) or []
    out: list[LabeledSlot] = []
    for i, s in enumerate(slots_raw):
        tid = _read(s, "tableId", "") or ""
        row = int(_read(s, "row", 0) or 0)
        col = int(_read(s, "col", 0) or 0)
        slot_id = _read(s, "slotId", "") or f"slot_{tid}_r{row}c{col}_{i}"
        out.append(LabeledSlot(
            slotId=slot_id,
            tableId=tid,
            fieldGuess=_read(s, "fieldGuess", "unknown") or "unknown",
            labelText=_read(s, "labelText", "") or "",
            row=row, col=col,
            visualRow=int(_read(s, "visualRow", 0) or 0),
            visualCol=int(_read(s, "visualCol", 0) or 0),
            rowSpan=int(_read(s, "rowSpan", 1) or 1),
            colSpan=int(_read(s, "colSpan", 1) or 1),
            confidence=float(_read(s, "confidence", 0.0) or 0.0),
            fieldSource=SRC_RULE,
        ))
    return out


def _needs_ai(slot: LabeledSlot) -> bool:
    return slot.fieldGuess in ("", "unknown") or slot.confidence < CONF_RULE_CEILING


# ── 메인: 하이브리드 강화 ────────────────────────────────────────────

def enrich_recognition_with_ai(
    recognition_result,
    ai_labeler_fn: AiFieldLabelerCallable | None = None,
    *,
    accept_threshold: float = CONF_ACCEPT_AI,
) -> EnrichedRecognition:
    """규칙 인식 결과를 AI로 보강한다(unknown/저신뢰 슬롯만).

    Args:
        recognition_result: form_recognizer.FormRecognitionResult (또는 동형 dict).
        ai_labeler_fn: 주입 시 unknown 슬롯을 라벨링. None이면 규칙 결과 그대로.
        accept_threshold: AI 라벨 채택 최소 confidence.
    """
    form_type = _read(recognition_result, "formType", "unknown_form") or "unknown_form"
    table_roles = _read(recognition_result, "tableRoles", {}) or {}
    unsafe = list(_read(recognition_result, "unsafeTableIds", []) or [])
    unsafe_set = set(unsafe)

    slots = _normalize_slots(recognition_result)
    enriched = EnrichedRecognition(
        formType=form_type, tableRoles=dict(table_roles),
        enhancedSlots=slots, unsafeTableIds=unsafe)

    # unsafe 표 슬롯은 AI 보강 대상에서 원천 제외(규칙 판정 존중)
    targets = [s for s in slots if s.tableId not in unsafe_set and _needs_ai(s)]

    if not targets:
        enriched.stillUnknown = [s.slotId for s in slots
                                 if s.fieldGuess in ("", "unknown")
                                 and s.tableId not in unsafe_set]
        return enriched

    if ai_labeler_fn is None:
        enriched.warnings.append({
            "code": "AI_LABELER_NOT_INJECTED",
            "detail": ("규칙이 못 잡은 슬롯이 있으나 AI 라벨러 미주입. "
                       "규칙 결과 그대로 반환(사람 셋팅 필요)."),
            "unknownCount": len(targets),
        })
        enriched.stillUnknown = [s.slotId for s in targets]
        return enriched

    payload = [{
        "slotId": s.slotId, "labelText": s.labelText,
        "tableId": s.tableId, "row": s.row, "col": s.col,
    } for s in targets]

    try:
        labels = ai_labeler_fn(payload) or []
    except Exception as exc:  # noqa: BLE001 — AI 실패는 규칙 결과로 안전 강등
        enriched.errors.append({"stage": "ai_labeling", "error": str(exc)[:200]})
        enriched.stillUnknown = [s.slotId for s in targets]
        return enriched

    label_by_id: dict[str, dict] = {}
    for lab in labels:
        sid = lab.get("slotId") if isinstance(lab, dict) else None
        if sid:
            label_by_id[sid] = lab

    slot_by_id = {s.slotId: s for s in slots}
    ai_count = 0
    for s in targets:
        lab = label_by_id.get(s.slotId)
        if not lab:
            continue
        fg = lab.get("fieldGuess") or ""
        conf = float(lab.get("confidence") or 0.0)
        if fg in ("", "unknown") or conf < accept_threshold:
            continue  # 저신뢰/무응답 → unknown 유지(사람 셋팅)
        target = slot_by_id[s.slotId]
        target.fieldGuess = fg
        target.confidence = conf
        target.fieldSource = SRC_AI
        target.aiReason = str(lab.get("reason", ""))[:200]
        ai_count += 1

    enriched.aiLabeledCount = ai_count
    enriched.stillUnknown = [s.slotId for s in slots
                             if s.fieldGuess in ("", "unknown")
                             and s.tableId not in unsafe_set]
    return enriched


# ── 규칙 전용 fallback (env unset 시 배관이 호출) ────────────────────

def placeholder_ai_labeler(unknown_slots: list[dict]) -> list[dict]:
    """env unset — 라벨 0건 반환(안전). 모든 슬롯 unknown 유지."""
    return []


# ── snapshot ─────────────────────────────────────────────────────────

def dump_contract_snapshot() -> dict[str, Any]:
    return {
        "contractName": CONTRACT_NAME,
        "contractVersion": CONTRACT_VERSION,
        "envFlag": ENV_FLAG_HAIKU,
        "aiEnabled": ai_enabled(),
        "acceptThreshold": CONF_ACCEPT_AI,
        "ruleCeiling": CONF_RULE_CEILING,
        "provenance": [SRC_RULE, SRC_AI],
    }
