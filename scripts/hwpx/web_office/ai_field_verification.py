"""문서별 2차 독립 검증 — 1차 판정을 '다른 눈'으로 다시 본다.

기준서: docs/design/hwpx_ai_doc_interpretation_fill_standard.md
운영규칙: CLAUDE.md §4.6 (두 신호 합의)
지시(2026-08-01, 대표님): "문서별로 하나씩 AI 검증이 필요한데"

왜 확신도 문턱을 버리는가
--------------------------
1차 해석의 `confidence` 는 **모델의 자기 신고**다. 실측에서 이게 무너졌다:

    Sonnet 판정: '해한AI엔지니어링' → "시공사(회사명) 기재"  (정확)
    Sonnet 확신도: 0.60  → 문턱 0.7 에 걸려 탈락

의미는 정확히 읽고도 겸손하게 매긴 숫자 때문에 칸이 죽었다. 전체로는
작성자 판정 11,736칸 중 3,066칸(26%)이 확신도 미달로 탈락했다.
문턱을 낮추면 이번엔 오탐이 늘어난다 — 숫자를 조정하는 것으로는 못 푼다.

무엇으로 바꾸는가
-----------------
**같은 문서를 다른 관점으로 한 번 더 판정하고, 두 판정이 일치할 때만
반영한다.** 1차 판정을 검증자에게 **보여주지 않는다** — 보여주면 그 답에
끌려가(anchoring) 독립성이 사라져 검증이 형식만 남는다.

    1차(ai_field_interpretation): "각 칸이 무엇을 적는 칸이고 누가 적는가"
    2차(이 모듈):                 "이 문서를 제출하는 사람이 채워야 할
                                   칸의 목록을 만들어라"

같은 사실을 서로 다른 각도에서 묻고, 일치 여부는 **프로그램이** 대조한다.
모델에게 "동의하십니까"를 묻지 않는다 — 그건 대개 동의로 기운다.
"""
from __future__ import annotations

import json
import os
import subprocess
from typing import Any, Callable

from .ai_doc_interpret import RunnerError
from .ai_form_fill import _parse_json_array

CLAUDE_MODEL = os.environ.get("HWPX_AI_VERIFY_MODEL", "sonnet")
DEFAULT_TIMEOUT_SEC = 300

Runner = Callable[[str], str]


def _cli_runner_factory(timeout_sec: int) -> Runner:
    def _run(prompt: str) -> str:
        try:
            proc = subprocess.run(
                ["claude", "-p", "--model", CLAUDE_MODEL, prompt],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=timeout_sec, check=False)
        except subprocess.TimeoutExpired as exc:
            raise RunnerError("AI_TIMEOUT") from exc
        except FileNotFoundError as exc:
            raise RunnerError("CLAUDE_CLI_NOT_FOUND") from exc
        if proc.returncode != 0:
            raise RunnerError(f"CLAUDE_CLI_EXIT_{proc.returncode}",
                              (proc.stderr or "")[:300])
        return proc.stdout or ""
    return _run


def build_verification_prompt(fields: list[dict]) -> str:
    """2차 프롬프트 — 1차 판정을 싣지 않는다(앵커링 차단).

    질문 각도를 바꾼다: 1차는 '이 칸은 누가 적는가'(칸 중심),
    2차는 '제출자가 채워야 할 칸은 무엇인가'(사람 중심).
    """
    title = ""
    lines = []
    for f in fields:
        ctx = f.get("context") or {}
        title = title or (ctx.get("title") or "")
        lines.append({"key": f["key"], "label": f.get("label") or "",
                      "left": ctx.get("left") or "",
                      "up": ctx.get("up") or ""})
    return (
        "당신은 한국 문서 실무자입니다. 아래 문서를 **작성해서 제출하는 "
        "쪽**(신청인·시공사·보고자 등 이 문서를 만들어 내는 당사자)의 "
        "입장에서, 제출 전에 **내가 직접 채워야 하는 칸**이 무엇인지 "
        "목록을 만드세요.\n"
        "판단 기준:\n"
        "- 내가 채운다 → fills=\"self\". 예: 공사명·위치·시공사명·작업자·"
        "수량·희망일자·신청 사유·내 서명란.\n"
        "- 받는 쪽이 채운다 → fills=\"other\". 예: 접수번호·접수일·처리"
        "기간·검토 결과·합격/불합격 판정·담당자 확인란·발급일·발급자 "
        "직인.\n"
        "- 사람이 값을 적는 칸이 아니다 → fills=\"none\". 예: 용지 규격, "
        "법령·서식번호 표시, 안내문(※ …합니다), 구역 제목, 점검 항목의 "
        "질문 문구 자체, 첨부서류 목록, 자르는선.\n"
        "규칙:\n"
        "- 반드시 JSON 배열만 출력. 다른 설명·코드펜스 금지.\n"
        '- 각 항목: {"key":"칸 key 그대로","fills":"self|other|none"}\n'
        "- 모든 칸에 대해 하나씩 판정하세요. 빠뜨리지 마세요.\n"
        f"문서 제목: {title}\n"
        f"칸 목록: {json.dumps(lines, ensure_ascii=False)}"
    )


def parse_verification(raw: list[dict], fields: list[dict]) -> dict[str, str]:
    """{key: 'self'|'other'|'none'} — 스키마에 없는 key 는 버린다."""
    known = {f["key"] for f in fields}
    out: dict[str, str] = {}
    for r in raw:
        key = str(r.get("key", "")).strip()
        val = str(r.get("fills", "") or "").strip().lower()
        if key in known and key not in out and val in ("self", "other", "none"):
            out[key] = val
    return out


def agreement(interpretations: list[dict],
              verdicts: dict[str, str]) -> dict[str, Any]:
    """1차 해석 × 2차 판정 → 칸별 합의 결과.

    `authorAgreed` 가 반영 대상이다 — 두 판정이 **독립적으로** 작성자
    (self)라고 본 칸. 확신도는 보지 않는다.
    """
    author_agreed: list[str] = []
    disagreed: list[dict] = []
    unverified: list[str] = []
    not_input_agreed: list[str] = []
    other_agreed: list[str] = []

    def _first_label(i: dict) -> str:
        """1차 판정을 2차 어휘(self/other/none)로 옮긴다."""
        if not i.get("isInput", True):
            return "none"
        fb = i.get("filledBy")
        return {"작성자": "self", "상대방": "other"}.get(fb, "")

    for i in interpretations:
        key = i.get("key")
        v = verdicts.get(key)
        if v is None:
            unverified.append(key)
            continue
        first = _first_label(i)
        if first == "" or first != v:
            # 1차가 판정을 못 했거나(빈 filledBy) 둘이 갈렸다 — 반영 안 함
            disagreed.append({"key": key, "label": (i.get("label") or "")[:30],
                              "first": first or "(미판정)", "second": v})
            continue
        if v == "self":
            author_agreed.append(key)
        elif v == "none":
            not_input_agreed.append(key)
        else:
            other_agreed.append(key)
    matched = len(author_agreed) + len(not_input_agreed) + len(other_agreed)
    return {
        "authorAgreed": author_agreed,
        "notInputAgreed": not_input_agreed,
        # 상대방 일치도 '두 판정이 같다'는 사실이므로 일치율에 넣는다.
        # 넣지 않으면 완전 일치 문서가 0.41 로 보여 지표가 사람을 속인다
        # (실사례: 1차 상대방10/작성자7 · 2차 other10/self7 = 완전 일치).
        "otherAgreed": other_agreed,
        "disagreed": disagreed,
        "unverified": unverified,
        "agreementRate": round(matched / max(1, len(interpretations)), 3),
    }


def verify_fields(
    fields: list[dict], interpretations: list[dict], *,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC, runner: Runner | None = None,
) -> dict[str, Any]:
    """문서 1건 2차 검증. 반환에 authorAgreed(반영 대상)를 담는다."""
    if not fields:
        return {"ok": True, "verdicts": {}, "agreement": agreement([], {})}
    prompt = build_verification_prompt(fields)
    run = runner or _cli_runner_factory(timeout_sec)
    try:
        stdout = run(prompt)
    except RunnerError as exc:
        return {"ok": False, "error": exc.code, "detail": exc.detail,
                "verdicts": {}}
    verdicts = parse_verification(_parse_json_array(stdout), fields)
    return {"ok": True, "provider": f"claude_cli_{CLAUDE_MODEL}",
            "verdicts": verdicts,
            "agreement": agreement(interpretations, verdicts)}
