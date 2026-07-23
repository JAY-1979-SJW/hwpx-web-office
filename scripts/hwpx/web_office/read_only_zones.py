"""읽기 전용 자산 구역 — 원본 직접 수정(§4.3/§4.4)이 닿으면 안 되는 곳.

배경 (2026-07-24 정책 통일):
    §4.3 은 web_office 편집 저장을 원본 파일 직접 수정으로 전환했다. 그러나
    그 구현(_apply_in_place_if_requested)에는 어떤 원본이든 덮어쓰는 가드가
    없었다. `data/drafts/form_library/` 의 카탈로그 템플릿(38,000+건)은 채움의
    **원천 참조 라이브러리**다. 편집기로 카탈로그 서식을 열어 editInPlace 로
    저장하면 그 템플릿이 사라진다 — 되돌릴 수 없는 데이터 파괴.

    §4.4: 원본 직접 수정은 **사용자 소유 문서에만** 허용한다. 아래 구역은
    읽기 전용이며, 그 위에서의 편집·채움은 항상 새 파일로 산출한다.

이 모듈은 "이 경로가 읽기 전용 자산인가"만 판정한다. 순수 함수라 파일시스템
접근 없이 테스트된다.
"""
from __future__ import annotations

# 읽기 전용 구역 접두(프로젝트 상대, POSIX 슬래시). 하위 전체가 보호된다.
READ_ONLY_PREFIXES: tuple[str, ...] = (
    "data/drafts/form_library/",   # 카탈로그 템플릿 — 채움의 원천 라이브러리
    "data/recognition_corpus/",    # 인식 코퍼스
    "samples/",                    # 샘플 서식
    "tests/fixtures/",             # 테스트 고정 자산
)


def _normalize(rel: str) -> str:
    """프로젝트 상대 경로를 슬래시 기준으로 눕힌다. 선행 ./ 제거.

    lstrip 을 쓰지 않는다 — '.' 을 통째로 깎으면 '.githooks' 같은 경로가
    뭉개진다(gate_hwpx_session_claim 에서 실제로 겪은 함정).
    """
    s = (rel or "").replace("\\", "/").strip()
    while s.startswith("./"):
        s = s[2:]
    return s


def is_read_only(rel: str) -> bool:
    """이 프로젝트 상대 경로가 읽기 전용 자산 구역에 있는가."""
    s = _normalize(rel)
    return any(s.startswith(p) for p in READ_ONLY_PREFIXES)


def zone_of(rel: str) -> str | None:
    """읽기 전용이면 어느 구역인지(접두), 아니면 None."""
    s = _normalize(rel)
    for p in READ_ONLY_PREFIXES:
        if s.startswith(p):
            return p
    return None
