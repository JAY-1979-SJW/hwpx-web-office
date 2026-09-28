"""Haiku CLI proposal adapter (env-gated).

CLAUDE.md §9 준수:
- 외부 모델 키 직접 사용 금지
- Claude Code CLI 최하위 모델(Haiku)만 허용

본 어댑터는 `ENABLE_LIVE_HAIKU=1` 환경 변수가 설정될 때만 활성화된다.
미활성 시 `placeholder_ai_proposal()` fallback으로 동작 (자재창고 안전).

내부 구현 메모:
- subprocess.run(["claude", "-p", prompt]) 형태 wrapper
- 실 호출은 production 배포에서만, test 환경은 env unset
- AI는 candidate 제안만 — 자동 승인은 호출자(자동 채움 설계실)에서 OFF
"""
from __future__ import annotations

import json
import subprocess

from . import adapter_contract as ac


def make_proposal(recognition_result: dict,
                       input_slots: list[dict],
                       extracted_values: list[dict]) -> list[dict]:
    """Haiku CLI를 호출하여 AI proposal 리스트를 받는다.

    env unset 시 AdapterDisabled 발생 — 호출자(마스터)가 fallback 사용.
    """
    ac.require_flag(ac.ENV_FLAG_HAIKU)

    prompt = _build_prompt(recognition_result, input_slots, extracted_values)
    # subprocess 호출 — 실 가동 시 활성화. test에서는 env unset이므로 도달 안 함.
    proc = subprocess.run(
        ["claude", "-p", prompt],
        capture_output=True, text=True, check=False, timeout=120,
    )
    if proc.returncode != 0:
        return []
    return _parse_response(proc.stdout)


def _build_prompt(rec: dict, slots: list[dict],
                       extracted: list[dict]) -> str:
    """프롬프트 구성 — raw 개인정보 포함 금지.

    실 호출 시: 추출값은 redactedPreview만 사용, hash는 동봉하지 않음.
    """
    summary = {
        "documentType": rec.get("documentType"),
        "subType": rec.get("subType"),
        "labelCount": len(rec.get("labelOccurrences") or []),
        "slotCount": len(slots),
        "extractedCount": len(extracted),
    }
    return (
        "다음 HWPX 서식에 입력할 후보 값을 JSON 배열로 반환하세요. "
        "각 항목은 {proposalId, label, value, confidence} 키를 포함합니다.\n"
        f"summary: {json.dumps(summary, ensure_ascii=False)}"
    )


def _parse_response(stdout: str) -> list[dict]:
    """모델 출력에서 JSON 배열 추출. 실패 시 빈 리스트."""
    try:
        # 모델이 ```json``` 블록 둘러쌌을 가능성 처리
        text = stdout.strip()
        if "```json" in text:
            text = text.split("```json", 1)[1].split("```", 1)[0]
        elif text.startswith("```"):
            text = text.split("```", 1)[1].split("```", 1)[0]
        data = json.loads(text)
        if isinstance(data, list):
            return [d for d in data if isinstance(d, dict)]
        return []
    except Exception:
        return []
