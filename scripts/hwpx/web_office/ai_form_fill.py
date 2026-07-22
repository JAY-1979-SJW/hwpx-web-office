"""AI 서식 자동채움 — Claude Code CLI(Haiku)로 입력칸 값 제안.

CLAUDE.md 준수:
- §9: 외부 모델 키 직접 사용 금지 → Claude Code CLI 최하위 모델(Haiku)만.
- §7: AI inject(claude CLI) 경로를 통해서만 자동채움 실행.

흐름:
    입력칸 라벨 목록 → 프롬프트 → `claude -p --model haiku` →
    JSON 배열 파싱 → 라벨 기준 재매핑 → {key,label,value,confidence} 반환.

안전:
- raw 개인정보 미참조 — 라벨 텍스트만 모델에 전달.
- 모델 출력은 '제안'일 뿐 — 자동 승인 없음(사람이 검토·확정).
"""
from __future__ import annotations

import json
import subprocess
from typing import Any

CLAUDE_MODEL = "haiku"   # §9 — 최하위 모델만
DEFAULT_TIMEOUT_SEC = 120


def propose_values(fields: list[dict], *, source_data: dict | None = None,
                   timeout_sec: int = DEFAULT_TIMEOUT_SEC) -> dict[str, Any]:
    """입력칸 라벨에 대한 AI 제안 값을 반환.

    Args:
        fields: [{key, label}, ...] — 채울 빈 입력칸(키 + 라벨).
        source_data: {필드:값} — 있으면 이 실제 소스 값을 서식 라벨에 매핑(예시 아님).

    Returns:
        {ok, provider, mode, proposals:[{key,label,value,confidence}], error?}
    """
    labels = []
    seen = set()
    for f in fields:
        lab = str(f.get("label", "")).strip()
        if lab and lab not in seen:
            seen.add(lab)
            labels.append(lab)

    mode = "source_mapping" if source_data else "example"
    if not labels:
        return {"ok": True, "provider": "claude_cli_haiku", "mode": mode, "proposals": []}

    prompt = (_build_source_prompt(labels, source_data) if source_data
              else _build_prompt(labels))
    try:
        proc = subprocess.run(
            ["claude", "-p", "--model", CLAUDE_MODEL, prompt],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout_sec, check=False,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "provider": "claude_cli_haiku", "proposals": [], "error": "AI_TIMEOUT"}
    except FileNotFoundError:
        return {"ok": False, "provider": "claude_cli_haiku", "proposals": [], "error": "CLAUDE_CLI_NOT_FOUND"}

    if proc.returncode != 0:
        return {"ok": False, "provider": "claude_cli_haiku", "proposals": [],
                "error": f"CLAUDE_CLI_EXIT_{proc.returncode}",
                "detail": (proc.stderr or "")[:300]}

    raw = _parse_json_array(proc.stdout)
    by_label: dict[str, dict] = {}
    for r in raw:
        lab = str(r.get("label", "")).strip()
        if lab and lab not in by_label:
            by_label[lab] = r

    proposals: list[dict] = []
    for f in fields:
        lab = str(f.get("label", "")).strip()
        r = by_label.get(lab)
        if not r:
            continue
        val = str(r.get("value", "")).strip()
        if not val:
            continue
        try:
            conf = float(r.get("confidence") or 0.0)
        except (TypeError, ValueError):
            conf = 0.0
        proposals.append({
            "key": f.get("key"),
            "label": lab,
            "value": val,
            "confidence": max(0.0, min(1.0, conf)),
        })

    return {"ok": True, "provider": "claude_cli_haiku", "mode": mode, "proposals": proposals}


def _build_source_prompt(labels: list[str], source: dict) -> str:
    """소스 데이터(실제 값)를 서식 라벨에 매핑하는 프롬프트."""
    return (
        "당신은 한국 관공서 HWPX 서식 자동입력 도우미입니다. "
        "아래 '소스 데이터'(실제 사업자등록증 등에서 추출한 값)를 서식의 입력칸 라벨에 "
        "매핑하세요.\n"
        "규칙:\n"
        "- 반드시 JSON 배열만 출력. 다른 설명·코드펜스 금지.\n"
        '- 각 항목: {"label":"서식 라벨 그대로","value":"소스에서 온 실제 값","confidence":0.0~1.0}\n'
        "- 소스 데이터에 대응 값이 없는 라벨은 결과에서 제외하세요(추측 금지).\n"
        "- 라벨 의미와 소스 필드가 명확히 일치할 때만 매핑하고 confidence를 높게.\n"
        f"소스 데이터: {json.dumps(source, ensure_ascii=False)}\n"
        f"서식 입력칸 라벨: {json.dumps(labels, ensure_ascii=False)}"
    )


def _build_prompt(labels: list[str]) -> str:
    return (
        "당신은 한국 관공서 HWPX 서식 자동입력 도우미입니다. "
        "아래 입력칸 라벨 각각에 들어갈 현실적인 예시 값을 제안하세요.\n"
        "규칙:\n"
        "- 반드시 JSON 배열만 출력하세요. 다른 설명·머리말·코드펜스 금지.\n"
        '- 각 항목 형식: {"label":"입력받은 라벨 그대로","value":"제안값","confidence":0.0~1.0}\n'
        "- 라벨이 값을 넣을 항목이 아니면(안내문 등) 그 라벨은 제외하세요.\n"
        "- 확실하지 않으면 confidence를 낮게 매기세요.\n"
        f"라벨 목록: {json.dumps(labels, ensure_ascii=False)}"
    )


def _parse_json_array(stdout: str) -> list[dict]:
    """모델 출력에서 JSON 배열 추출. 코드펜스·앞뒤 텍스트 방어."""
    try:
        text = (stdout or "").strip()
        if "```json" in text:
            text = text.split("```json", 1)[1].split("```", 1)[0]
        elif text.startswith("```"):
            text = text.split("```", 1)[1].split("```", 1)[0]
        i, j = text.find("["), text.rfind("]")
        if i >= 0 and j > i:
            text = text[i:j + 1]
        data = json.loads(text)
        return [d for d in data if isinstance(d, dict)] if isinstance(data, list) else []
    except Exception:
        return []
