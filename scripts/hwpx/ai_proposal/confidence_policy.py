"""HWPX-AI-AUTO-FILL-PROPOSAL-CONTRACT-01 — confidence policy.

AI proposal의 confidence + target resolution + 충돌 여부를 결합해서
1차 정책 결정. 본 contract V1은 **자동 승인 OFF**가 기본값.

정책 3단계 (V1, 자동 승인 OFF):
- HIGH (>= AUTO_THRESHOLD, target RESOLVED, 충돌 없음) → "READY_FOR_DECISION"
- MEDIUM (>= REVIEW_THRESHOLD) → "READY_FOR_DECISION"
- LOW (< REVIEW_THRESHOLD) → "AUTO_REJECT" + 사유 기록

자동 승인 ON 모드는 별도 contract로 분리 예정 (학습 데이터 누적 후).
"""
from __future__ import annotations

# V1 정책 임계값 (자동 승인 OFF)
AUTO_THRESHOLD = 0.95  # 자동 승인용 (V1에서는 사용 안 함, 호환 위해 정의만)
REVIEW_THRESHOLD = 0.70  # 사람 검토 대상 최소

AUTO_APPROVE_ENABLED = False  # V1 — 무조건 사람 검토


def classify(
    *,
    confidence: float,
    target_status: str,
    has_conflict: bool = False,
) -> dict:
    """단일 proposal에 대한 1차 분류.

    Args:
        confidence: 0.0~1.0
        target_status: "RESOLVED" | "AMBIGUOUS" | "NOT_FOUND"
        has_conflict: A동/B동 진단에서 충돌 발견 시 True

    Returns:
        dict {
          decision: "READY_FOR_DECISION" | "AUTO_REJECT" | "HOLD",
          reason: str,
          tier: "HIGH" | "MEDIUM" | "LOW" | "BLOCKED",
        }
    """
    if not isinstance(confidence, (int, float)):
        return {"decision": "AUTO_REJECT", "tier": "BLOCKED",
                  "reason": "CONFIDENCE_NOT_NUMBER"}
    conf = float(confidence)

    if target_status == "NOT_FOUND":
        return {"decision": "AUTO_REJECT", "tier": "BLOCKED",
                  "reason": "TARGET_NOT_FOUND"}
    if target_status == "AMBIGUOUS":
        return {"decision": "HOLD", "tier": "BLOCKED",
                  "reason": "TARGET_AMBIGUOUS"}
    if has_conflict:
        return {"decision": "HOLD", "tier": "BLOCKED",
                  "reason": "SEMANTIC_OR_LABEL_CONFLICT"}

    if conf < REVIEW_THRESHOLD:
        return {"decision": "AUTO_REJECT", "tier": "LOW",
                  "reason": f"CONFIDENCE_BELOW_THRESHOLD:{REVIEW_THRESHOLD}"}

    if conf >= AUTO_THRESHOLD:
        if AUTO_APPROVE_ENABLED:
            return {"decision": "SYSTEM_APPROVE", "tier": "HIGH",
                      "reason": "HIGH_CONFIDENCE_AUTO_APPROVE"}
        return {"decision": "READY_FOR_DECISION", "tier": "HIGH",
                  "reason": "HIGH_CONFIDENCE_BUT_AUTO_APPROVE_OFF"}

    return {"decision": "READY_FOR_DECISION", "tier": "MEDIUM",
              "reason": "WITHIN_REVIEW_RANGE"}


def classify_batch(items: list[dict]) -> list[dict]:
    """[{confidence, target_status, has_conflict}, ...] → 분류 결과 리스트."""
    return [classify(
        confidence=it.get("confidence", 0.0),
        target_status=it.get("target_status", "NOT_FOUND"),
        has_conflict=bool(it.get("has_conflict", False)),
    ) for it in items or []]
