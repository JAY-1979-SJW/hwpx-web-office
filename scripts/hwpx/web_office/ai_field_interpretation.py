"""문서별 AI 필드 해석 — '이 칸이 무엇을 요구하는가'를 판정한다.

기준서: docs/design/hwpx_ai_doc_interpretation_fill_standard.md
지시(2026-08-01, 대표님): "개별 문서별로 파싱 로직하고 AI 분석하고 뭘
입력할지 최종 캐시로 저장하면 되잖아?"

ai_doc_interpret 과의 역할 분담 — 둘 다 AI 를 부르지만 시점과 산출이 다르다:

    ai_doc_interpret      런타임. 사용자 소스 → 이 칸에 들어갈 **값**.
    ai_field_interpretation  빌드타임. 문서 → 이 칸의 **의미**(캐시 대상).

**값은 캐시하지 않는다.** 값은 사용자마다 다르고 개인정보라 서버에 굳히면
안 된다(§4 개인정보 원칙 · fill-plan 이 프로필을 저장하지 않는 것과 동일).
캐시하는 것은 문서에 종속된 불변 정보다:

    · isInput   진짜 입력칸인가 — 규칙 추출기가 용지규격("210mm×297mm
                (백상지 80g/m2)")·법령표시("■ …시행규칙[별지제12호서식]")·
                안내문("※ [ ]에는 …")까지 신청인칸으로 등록한 오염을 건다.
    · semantic  표준 의미 태그 — 규칙 기반 부여율 35.0% 의 나머지를 메운다.
    · profileKey 표준 프로필의 어느 키가 이 칸에 들어가는가.
    · question  프로필에 없으면 사용자에게 무엇을 물을 것인가.

이 캐시가 있으면 런타임 채움은 AI 호출 없이 즉시 끝난다(현재 서식당 20~40초).

AI 출력은 신뢰하지 않는다 — `validate_interpretation` 이 스키마에 실재하는
paragraphId 인지, semantic 이 아는 어휘인지 기계 대조하고 아니면 버린다.
"""
from __future__ import annotations

import json
import re
import subprocess
from typing import Any, Callable

from .ai_doc_interpret import RunnerError
from .ai_form_fill import _parse_json_array
from .form_fill_planner import _PROMPT

CLAUDE_MODEL = "haiku"          # §9 — 최하위 모델만
DEFAULT_TIMEOUT_SEC = 180

Runner = Callable[[str], str]

# 아는 의미 태그만 인정한다 — plan_fill 이 소비하는 어휘와 같아야 한다.
# 모르는 태그를 캐시에 넣으면 planner 가 조용히 무시해 '해석했는데 안
# 채워지는' 상태가 된다.
ALLOWED_SEMANTIC = set(_PROMPT) | {"buildingName"}

# 사람이 값을 적는 칸이 아닌 것으로 **규칙이** 알아보는 라벨.
# 용지규격·법령표시·안내문·자르는선 등 — 규칙 추출기가 이것들까지
# 신청인칸으로 등록해 둔 오염이다(전수 6,653건).
#
# ※ 접두어만으로 거르면 안 된다 — 전수에서 "※ 건축면적(m2)",
# "※ 연면적(m2)", "※ 12 특수구조건축물유형" 처럼 ※ 가 붙은 **진짜 입력
# 항목**이 다수 확인됐다(관공서 서식에서 ※ 는 '담당자 기재'를 뜻하기도
# 하지만 항목 자체는 실재한다). 안내 **문장**(…합니다/…습니다로 끝나는
# 것)일 때만 오염으로 본다.
POLLUTION_LABEL_RE = re.compile(
    r"(\d+\s*mm\s*[×xX]\s*\d+\s*mm|백상지|중질지"
    r"|■\s|별지\s*제?\s*\d+\s*호\s*서식|시행규칙\s*\[|시행령\s*\["
    r"|^\s*※.*(합니다|습니다)|자르는\s*선|절취선"
    r"|처리\s*기간|구비\s*서류|수수료\s*$)")

# 강등 최소 확신도 — 이 아래면 AI 가 '입력칸 아님'이라 해도 손대지 않는다.
DEMOTE_MIN_CONFIDENCE = 0.7


def should_demote(interp: dict, *,
                  min_confidence: float = DEMOTE_MIN_CONFIDENCE) -> bool:
    """이 칸을 입력칸 목록에서 빼도 되는가 — AI 와 규칙이 **둘 다** 아니라 할 때만.

    파일럿 실측(8서식·77칸, 2026-08-01): AI 단독 판정으로 강등하면 정상
    입력칸의 **14.5%**(69개 중 10개)를 오탐으로 죽였다. 오탐은 사용자가
    그 칸을 영영 못 채우게 만들어 오염이 남는 것보다 해롭다.

    두 신호가 독립적으로 일치할 때만 강등하면 오탐이 구조적으로 0 이
    된다 — 규칙 패턴에 걸리지 않는 정상 라벨은 후보에조차 오르지 못한다.
    같은 파일럿에서 이 조건으로 오염 검출은 7/8(87.5%)을 유지했다.
    """
    if interp.get("isInput", True):
        return False
    if float(interp.get("confidence") or 0.0) < min_confidence:
        return False
    return bool(POLLUTION_LABEL_RE.search(interp.get("label") or ""))


def _cli_runner_factory(timeout_sec: int) -> Runner:
    def _run(prompt: str) -> str:
        try:
            proc = subprocess.run(
                ["claude", "-p", "--model", CLAUDE_MODEL, prompt],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=timeout_sec, check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise RunnerError("AI_TIMEOUT") from exc
        except FileNotFoundError as exc:
            raise RunnerError("CLAUDE_CLI_NOT_FOUND") from exc
        if proc.returncode != 0:
            raise RunnerError(f"CLAUDE_CLI_EXIT_{proc.returncode}",
                              (proc.stderr or "")[:300])
        return proc.stdout or ""
    return _run


def build_interpretation_prompt(fields: list[dict]) -> str:
    """문맥 포함 필드 목록 → 의미 해석 프롬프트. 값은 묻지 않는다."""
    title = ""
    lines = []
    for f in fields:
        ctx = f.get("context") or {}
        title = title or (ctx.get("title") or "")
        lines.append({"key": f["key"], "label": f.get("label") or "",
                      "left": ctx.get("left") or "",
                      "up": ctx.get("up") or ""})
    return (
        "당신은 한국 관공서 HWPX 서식 분석가입니다. 각 칸이 **무엇을 적는 "
        "칸인지** 판정하세요. 값을 지어내지 마세요 — 값은 묻지 않습니다.\n"
        "규칙:\n"
        "- 반드시 JSON 배열만 출력. 다른 설명·코드펜스 금지.\n"
        '- 각 항목: {"key":"칸 key 그대로","isInput":true/false,'
        '"meaning":"무엇을 적는 칸인지 한 줄","semantic":"태그 또는 빈문자열",'
        '"profileKey":"표준 프로필 키 또는 빈문자열",'
        '"question":"사용자에게 물을 문구","confidence":0.0~1.0}\n'
        "- isInput=false 로 판정할 것: 용지 규격(210mm×297mm 등), 법령·서식 "
        "번호 표시(■ …시행규칙 [별지제…호서식]), 안내문(※ …합니다), 구역 "
        "제목, 첨부서류 목록, 자르는선 — 사람이 값을 적는 칸이 아닙니다.\n"
        f"- semantic 은 다음 중 하나이거나 빈 문자열: "
        f"{sorted(ALLOWED_SEMANTIC)}\n"
        "- profileKey 는 신청인의 표준 신상정보에서 오는 값일 때만 채우고"
        "(성명·주소·연락처 등), 서식 고유 항목이면 빈 문자열로 두고 "
        "question 을 잘 적으세요.\n"
        f"서식 제목: {title}\n"
        f"칸 목록: {json.dumps(lines, ensure_ascii=False)}"
    )


def validate_interpretation(
    raw: list[dict], fields: list[dict],
) -> tuple[list[dict], list[dict]]:
    """(통과, 폐기). AI 출력을 스키마에 대조한다.

    · 스키마에 없는 key → INVENTED_KEY (지어낸 칸 주소를 캐시에 못 넣는다)
    · 모르는 semantic → 태그만 비우고 통과(해석 자체는 살린다)
    """
    known = {f["key"]: f for f in fields}
    seen: set[str] = set()
    ok: list[dict] = []
    bad: list[dict] = []
    for r in raw:
        key = str(r.get("key", "")).strip()
        if key not in known or key in seen:
            bad.append({"key": key,
                        "reason": "INVENTED_KEY" if key not in known
                        else "DUPLICATE_KEY"})
            continue
        seen.add(key)
        sem = str(r.get("semantic", "") or "").strip()
        if sem not in ALLOWED_SEMANTIC:
            sem = ""
        try:
            conf = float(r.get("confidence") or 0.0)
        except (TypeError, ValueError):
            conf = 0.0
        ok.append({
            "key": key,
            "label": known[key].get("label") or "",
            "isInput": bool(r.get("isInput", True)),
            "meaning": str(r.get("meaning", "") or "").strip()[:120],
            "semantic": sem,
            "profileKey": str(r.get("profileKey", "") or "").strip()[:40],
            "question": str(r.get("question", "") or "").strip()[:120],
            "confidence": max(0.0, min(1.0, conf)),
        })
    return ok, bad


def interpret_fields(
    fields: list[dict], *, timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    runner: Runner | None = None,
) -> dict[str, Any]:
    """문맥 포함 필드 목록 → 검증된 해석. 캐시에 넣을 산출물."""
    if not fields:
        return {"ok": True, "interpretations": [], "dropped": [],
                "coverage": 0.0}
    prompt = build_interpretation_prompt(fields)
    run = runner or _cli_runner_factory(timeout_sec)
    try:
        stdout = run(prompt)
    except RunnerError as exc:
        return {"ok": False, "error": exc.code, "detail": exc.detail,
                "interpretations": [], "dropped": []}

    ok, bad = validate_interpretation(_parse_json_array(stdout), fields)
    return {
        "ok": True,
        "provider": "claude_cli_haiku",
        "interpretations": ok,
        "dropped": bad,
        # 해석된 비율 — 규칙 기반 semantic 부여율(35.0%)과 견주는 수치
        "coverage": round(len(ok) / len(fields), 3),
        "inputCount": sum(1 for r in ok if r["isInput"]),
        "notInputCount": sum(1 for r in ok if not r["isInput"]),
        "semanticCount": sum(1 for r in ok if r["semantic"]),
    }
