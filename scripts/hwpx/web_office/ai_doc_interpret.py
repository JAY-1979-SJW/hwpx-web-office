"""AI 문서 해석 — 문맥 포함 필드를 모델에 주고 칸별 제안값을 받는다.

기준서: docs/design/hwpx_ai_doc_interpretation_fill_standard.md §5

이 모듈만 AI 경계를 만진다. CLI 실행은 runner 함수로 격리한다 —
기본 runner 는 Claude Code CLI(Haiku, §9), 시험은 가짜 runner 를
주입해 CLI 없이 전 경로를 검증한다.

ai_form_fill 과의 차이:
  · 라벨만 → 라벨 + 문맥(서식 제목·왼쪽 칸·위 머리글)
  · 라벨 기준 재매핑(중복 라벨 첫 칸만) → key(paragraphId) 기준 정확 매핑
  · 응답에 sourceField(어느 소스 값에서 왔는지) 요구 — 검증기의 비창조
    검사(§3 원칙 1)가 근거를 기계 대조할 수 있게 한다.
"""
from __future__ import annotations

import json
import subprocess
from typing import Any, Callable

from .ai_form_fill import _parse_json_array, partition_by_subject

CLAUDE_MODEL = "haiku"       # §9 — 최하위 모델만
DEFAULT_TIMEOUT_SEC = 120

Runner = Callable[[str], str]


class RunnerError(Exception):
    """runner 실패 — code 는 ai_form_fill 과 같은 어휘를 쓴다."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(code)
        self.code = code
        self.detail = detail


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


def build_interpretation_prompt(fields: list[dict], source: dict) -> str:
    """문맥 포함 해석 프롬프트. 필드는 key 로 식별한다."""
    lines = []
    for f in fields:
        ctx = f.get("context") or {}
        lines.append({
            "key": f["key"],
            "label": f.get("label") or "",
            "left": ctx.get("left") or "",
            "up": ctx.get("up") or "",
        })
    title = ""
    for f in fields:
        title = (f.get("context") or {}).get("title") or ""
        if title:
            break
    return (
        "당신은 한국 관공서 HWPX 서식 자동입력 도우미입니다. 서식의 각 "
        "입력칸에 대해, 칸의 라벨과 문맥(왼쪽 칸 left, 위 머리글 up)을 "
        "보고 '소스 데이터'의 어느 값이 들어가야 하는지 판단하세요.\n"
        "규칙:\n"
        "- 반드시 JSON 배열만 출력. 다른 설명·코드펜스 금지.\n"
        '- 각 항목: {"key":"입력칸 key 그대로","value":"소스에서 온 실제 값",'
        '"sourceField":"값을 가져온 소스 데이터의 키","confidence":0.0~1.0}\n'
        "- 소스 데이터에 대응 값이 없는 칸은 결과에서 제외하세요. 값을 "
        "지어내는 것은 금지입니다(허위 기재).\n"
        "- 라벨이 안내문·법령 표시·구역 제목이면(입력칸이 아니면) 제외하세요.\n"
        "- 칸 의미와 소스 키가 명확히 일치할 때만 confidence 를 높게.\n"
        f"서식 제목: {title}\n"
        f"소스 데이터: {json.dumps(source, ensure_ascii=False)}\n"
        f"입력칸 목록: {json.dumps(lines, ensure_ascii=False)}"
    )


def propose_with_context(
    fields: list[dict], source_data: dict, *,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    runner: Runner | None = None,
) -> dict[str, Any]:
    """문맥 포함 AI 해석. 반환 형태는 ai_form_fill.propose_values 와 호환.

    fields: ai_doc_context.build_context_fields() 산출물.
    """
    own_fields, third_fields = partition_by_subject(fields)
    held = [{"key": f.get("key"),
             "label": str(f.get("label", "")).strip(),
             "reason": "THIRD_PARTY_FIELD"}
            for f in third_fields if str(f.get("label", "")).strip()]
    if not own_fields:
        return {"ok": True, "provider": "claude_cli_haiku",
                "mode": "doc_context", "proposals": [],
                "heldForThirdParty": held}
    if not source_data:
        # 소스 없이 해석하면 '지어내기'만 남는다 — 비창조 원칙상 거부.
        return {"ok": False, "provider": "claude_cli_haiku",
                "mode": "doc_context", "proposals": [],
                "heldForThirdParty": held, "error": "SOURCE_DATA_MISSING"}

    prompt = build_interpretation_prompt(own_fields, source_data)
    run = runner or _cli_runner_factory(timeout_sec)
    try:
        stdout = run(prompt)
    except RunnerError as exc:
        return {"ok": False, "provider": "claude_cli_haiku",
                "mode": "doc_context", "proposals": [],
                "heldForThirdParty": held,
                "error": exc.code, "detail": exc.detail}

    by_key: dict[str, dict] = {}
    for r in _parse_json_array(stdout):
        k = str(r.get("key", "")).strip()
        if k and k not in by_key:
            by_key[k] = r

    proposals: list[dict] = []
    for f in own_fields:               # 제3자 칸은 애초에 여기 없다
        r = by_key.get(f["key"])
        if not r:
            continue
        val = str(r.get("value", "")).strip()
        if not val:
            continue
        try:
            conf = float(r.get("confidence") or 0.0)
        except (TypeError, ValueError):
            conf = 0.0
        sensitive = bool(f.get("sensitive")) or f.get("inputType") == "secret"
        proposals.append({
            "key": f["key"],
            "label": str(f.get("label", "")).strip(),
            "value": val,
            "sourceField": str(r.get("sourceField", "")).strip(),
            "confidence": max(0.0, min(1.0, conf)),
            "subject": "self",
            "requiresConfirmation": sensitive,
        })
    return {"ok": True, "provider": "claude_cli_haiku",
            "mode": "doc_context", "proposals": proposals,
            "heldForThirdParty": held}
