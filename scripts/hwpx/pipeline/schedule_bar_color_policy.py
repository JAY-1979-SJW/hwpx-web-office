"""HWPX-SCHEDULE-STATUS-COLOR-POLICY-01

공정표 막대 상태별 색상 정책 모음.
apply_edit_plan / fill_schedule_bars 호출 없음 — 색상값 조회만 수행.

상태 코드:
    PLANNED       예정 (착공 전, 계획선)
    IN_PROGRESS   진행 중
    DONE          완료
    DELAYED       지연
    REVIEW        충돌 검토 중 (REVIEW_REQUIRED)
    BLOCKED       실행 불가 (FAIL / invalid coords)
    TEMPLATE      빈 템플릿 슬롯 (덮어쓰기 허용)
    UNKNOWN       상태 미확인

색상값: 6자리 HEX, # 없음 (XML faceColor 직접 사용 형식).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar


# ── 정책 테이블 (근거: 건설공사 감리 기준 색상 통례 + 엔진 내부 일관성) ───────

@dataclass(frozen=True)
class BarColorEntry:
    status: str
    hex: str         # 6자리 HEX, # 없음
    label: str       # 표시 이름 (한글)
    description: str
    autoAllowed: bool  # AUTO_PLAN_ALLOWED 경로에서 사용 가능 여부


_POLICY_TABLE: list[BarColorEntry] = [
    BarColorEntry(
        status="PLANNED",
        hex="D9EAF7",
        label="예정",
        description="착공 전 계획 막대. 연한 파랑.",
        autoAllowed=True,
    ),
    BarColorEntry(
        status="IN_PROGRESS",
        hex="FFF2CC",
        label="진행",
        description="현재 시공 중인 공종. 노란 계열.",
        autoAllowed=True,
    ),
    BarColorEntry(
        status="DONE",
        hex="92D050",
        label="완료",
        description="시공 완료 공종. 녹색 계열 (기본값).",
        autoAllowed=True,
    ),
    BarColorEntry(
        status="DELAYED",
        hex="F4CCCC",
        label="지연",
        description="공정 지연 발생 공종. 분홍/연한 빨강.",
        autoAllowed=False,  # 지연 처리는 사람 검토 필요
    ),
    BarColorEntry(
        status="REVIEW",
        hex="FFE599",
        label="충돌검토",
        description="REVIEW_REQUIRED 상태 표시용. 진한 노랑.",
        autoAllowed=False,
    ),
    BarColorEntry(
        status="BLOCKED",
        hex="EA9999",
        label="차단",
        description="실행 불가(FAIL/invalid). 연한 빨강.",
        autoAllowed=False,
    ),
    BarColorEntry(
        status="TEMPLATE",
        hex="D9D9D9",
        label="템플릿",
        description="빈 템플릿 슬롯. 회색. 덮어쓰기 허용.",
        autoAllowed=True,
    ),
    BarColorEntry(
        status="UNKNOWN",
        hex="CCCCCC",
        label="미확인",
        description="상태 미확인. 회색.",
        autoAllowed=False,
    ),
]

# ── 조회 인터페이스 ─────────────────────────────────────────────────────────────

_BY_STATUS: dict[str, BarColorEntry] = {e.status: e for e in _POLICY_TABLE}
_BY_HEX: dict[str, BarColorEntry] = {e.hex.upper(): e for e in _POLICY_TABLE}

# conflict → status 매핑 (schedule_bar_plan_generator와 동기화)
_CONFLICT_TO_STATUS: dict[str, str] = {
    "no_conflict":                      "DONE",
    "replaces_existing_empty_template": "DONE",
    "overlaps_existing_bar":            "REVIEW",
    "extends_existing_bar":             "REVIEW",
    "unknown":                          "REVIEW",
    "outside_axis_range":               "BLOCKED",
}

# action → status 매핑
_ACTION_TO_STATUS: dict[str, str] = {
    "AUTO_PLAN_ALLOWED": "DONE",
    "REVIEW_REQUIRED":   "REVIEW",
    "FAIL":              "BLOCKED",
}


def get_color(status: str) -> str:
    """상태 코드로 HEX 색상 반환. 미정의 상태는 UNKNOWN 색상 반환."""
    entry = _BY_STATUS.get(status.upper())
    return entry.hex if entry else _BY_STATUS["UNKNOWN"].hex


def get_entry(status: str) -> BarColorEntry | None:
    """상태 코드로 BarColorEntry 반환."""
    return _BY_STATUS.get(status.upper())


def get_status_from_conflict(conflict: str) -> str:
    """conflict 타입 문자열로 상태 코드 반환."""
    return _CONFLICT_TO_STATUS.get(conflict, "UNKNOWN")


def get_color_from_conflict(conflict: str) -> str:
    """conflict 타입 문자열로 HEX 색상 반환."""
    return get_color(get_status_from_conflict(conflict))


def get_status_from_action(action: str) -> str:
    """bar plan action 문자열로 상태 코드 반환."""
    return _ACTION_TO_STATUS.get(action, "UNKNOWN")


def get_color_from_action(action: str) -> str:
    """bar plan action 문자열로 HEX 색상 반환."""
    return get_color(get_status_from_action(action))


def resolve_bar_color(
    *,
    explicit_color: str | None = None,
    status: str | None = None,
    conflict: str | None = None,
    action: str | None = None,
) -> str:
    """우선순위에 따라 막대 색상을 결정한다.

    우선순위:
    1. explicit_color (사용자 명시값)
    2. status 코드
    3. conflict 타입
    4. action 타입
    5. 기본값 DONE(92D050)
    """
    if explicit_color and len(explicit_color) == 6:
        return explicit_color.upper()
    if status:
        return get_color(status)
    if conflict:
        return get_color_from_conflict(conflict)
    if action:
        return get_color_from_action(action)
    return get_color("DONE")


def is_auto_allowed_color(hex_color: str) -> bool:
    """해당 색상이 AUTO_PLAN_ALLOWED 경로에서 허용되는지 확인."""
    entry = _BY_HEX.get(hex_color.upper().lstrip("#"))
    return entry.autoAllowed if entry else False


def all_statuses() -> list[str]:
    """전체 상태 코드 목록 반환."""
    return [e.status for e in _POLICY_TABLE]


def to_policy_dict() -> dict:
    """전체 정책 테이블을 직렬화 가능한 dict로 반환."""
    return {
        "version": "1.0",
        "statuses": [
            {
                "status": e.status,
                "hex": e.hex,
                "label": e.label,
                "description": e.description,
                "autoAllowed": e.autoAllowed,
            }
            for e in _POLICY_TABLE
        ],
        "conflictMapping": _CONFLICT_TO_STATUS,
        "actionMapping": _ACTION_TO_STATUS,
    }
