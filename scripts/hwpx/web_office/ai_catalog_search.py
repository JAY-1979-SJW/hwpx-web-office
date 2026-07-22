"""AI 의미 검색 — 자연어 질의를 Claude CLI로 서식 검색어로 해석 후 카탈로그 매칭.

CLAUDE.md §9: Claude Code CLI 최하위 모델(Haiku)만.

흐름:
    "공사 시작할 때 내는 서류" (자연어)
    → claude CLI: 관련 한국 정부 서식 검색 키워드 3~6개 추출
    → 각 키워드로 카탈로그 키워드 검색
    → formId 기준 병합·중복제거 → 순위 반환.

임베딩 인프라 없이 동작(§9 준수). 매 질의 1회 AI 호출 → '폴백/프리미엄' 검색으로 사용.
"""
from __future__ import annotations

import json
import subprocess
from typing import Any

CLAUDE_MODEL = "haiku"
DEFAULT_TIMEOUT_SEC = 60


def semantic_search(query: str, *, limit: int = 20,
                    timeout_sec: int = DEFAULT_TIMEOUT_SEC) -> dict[str, Any]:
    """자연어 질의 → AI 키워드 해석 → 카탈로그 검색."""
    from .catalog_search import search, catalog_ready
    if not catalog_ready():
        return {"ok": False, "error": "CATALOG_NOT_READY", "results": []}
    q = (query or "").strip()
    if not q:
        return {"ok": True, "keywords": [], "results": []}

    keywords = _ai_keywords(q, timeout_sec=timeout_sec)
    if keywords.get("error"):
        return {"ok": False, "error": keywords["error"], "results": []}
    kws = keywords["keywords"]

    # 각 키워드 검색 → formId 병합(키워드 매칭 수로 순위)
    hits: dict[int, dict] = {}
    score: dict[int, int] = {}
    for kw in kws:
        for r in (search(kw, limit=limit).get("results") or []):
            fid = r["formId"]
            hits[fid] = r
            score[fid] = score.get(fid, 0) + 1
    ranked = sorted(hits.values(), key=lambda r: -score[r["formId"]])[:limit]
    for r in ranked:
        r["matchedKeywords"] = score[r["formId"]]
    return {"ok": True, "query": q, "keywords": kws,
            "provider": "claude_cli_haiku", "results": ranked}


def _ai_keywords(query: str, *, timeout_sec: int) -> dict[str, Any]:
    prompt = (
        "사용자가 찾는 한국 정부/공공 서식(HWPX)을 카탈로그에서 검색하기 위한 "
        "핵심 검색어를 뽑아주세요.\n"
        "규칙:\n"
        "- 반드시 JSON 배열만 출력(설명·코드펜스 금지).\n"
        "- 서식명에 실제로 등장할 법한 한국어 명사/키워드 3~6개.\n"
        "- 예: 착공, 감리보고서, 사용승인, 소방시설 등.\n"
        f'사용자 질의: "{query}"'
    )
    try:
        proc = subprocess.run(
            ["claude", "-p", "--model", CLAUDE_MODEL, prompt],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout_sec, check=False)
    except subprocess.TimeoutExpired:
        return {"keywords": [], "error": "AI_TIMEOUT"}
    except FileNotFoundError:
        return {"keywords": [], "error": "CLAUDE_CLI_NOT_FOUND"}
    if proc.returncode != 0:
        return {"keywords": [], "error": f"CLAUDE_CLI_EXIT_{proc.returncode}"}
    kws = _parse_json_array(proc.stdout)
    # 문자열만, 정리
    out = []
    for k in kws:
        if isinstance(k, str) and k.strip() and k.strip() not in out:
            out.append(k.strip())
    return {"keywords": out[:6]}


def _parse_json_array(stdout: str) -> list:
    try:
        t = (stdout or "").strip()
        if "```json" in t:
            t = t.split("```json", 1)[1].split("```", 1)[0]
        elif t.startswith("```"):
            t = t.split("```", 1)[1].split("```", 1)[0]
        i, j = t.find("["), t.rfind("]")
        if i >= 0 and j > i:
            t = t[i:j + 1]
        data = json.loads(t)
        return data if isinstance(data, list) else []
    except Exception:
        return []
