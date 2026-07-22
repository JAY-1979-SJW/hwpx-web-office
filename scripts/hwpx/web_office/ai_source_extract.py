"""AI 소스 추출 — Claude Code CLI(비전)로 사업자등록증 등 소스 문서에서 값 추출.

CLAUDE.md 준수:
- §9: 외부 모델 키 직접 사용 금지 → Claude Code CLI 최하위 모델(Haiku)만.
- §4: raw 개인정보는 서식 채움에만 사용, 로그·응답에 원문 저장 최소화.

흐름:
    이미지/PDF 경로 → Claude 비전 OCR → 구조화 필드(JSON) 반환.
    추출된 값은 이후 form fill 단계에서 서식 라벨과 매핑된다.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

CLAUDE_MODEL = "haiku"
DEFAULT_TIMEOUT_SEC = 180

# 사업자등록증 표준 필드
BIZ_REG_FIELDS = [
    "등록번호", "상호", "대표자", "사업장주소",
    "개업일", "업태", "종목", "법인등록번호",
]


def extract_source(image_path: str, *, doc_type: str = "사업자등록증",
                   fields: list[str] | None = None,
                   timeout_sec: int = DEFAULT_TIMEOUT_SEC) -> dict[str, Any]:
    """소스 문서 이미지에서 구조화 값을 추출한다.

    Returns:
        {ok, provider, docType, source:{필드:값}, error?}
    """
    p = Path(image_path)
    if not p.is_file():
        return {"ok": False, "provider": "claude_cli_vision",
                "docType": doc_type, "source": {}, "error": "SOURCE_FILE_NOT_FOUND"}

    fields = fields or BIZ_REG_FIELDS
    prompt = _build_prompt(str(p), doc_type, fields)
    try:
        proc = subprocess.run(
            ["claude", "-p", "--model", CLAUDE_MODEL, prompt],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout_sec, check=False,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "provider": "claude_cli_vision", "docType": doc_type,
                "source": {}, "error": "AI_TIMEOUT"}
    except FileNotFoundError:
        return {"ok": False, "provider": "claude_cli_vision", "docType": doc_type,
                "source": {}, "error": "CLAUDE_CLI_NOT_FOUND"}

    if proc.returncode != 0:
        return {"ok": False, "provider": "claude_cli_vision", "docType": doc_type,
                "source": {}, "error": f"CLAUDE_CLI_EXIT_{proc.returncode}",
                "detail": (proc.stderr or "")[:300]}

    data = _parse_json_object(proc.stdout)
    # 요청 필드만, 문자열로 정규화
    source = {}
    for k in fields:
        v = data.get(k)
        if isinstance(v, (str, int, float)) and str(v).strip():
            source[k] = str(v).strip()
    return {"ok": True, "provider": "claude_cli_vision",
            "docType": doc_type, "source": source}


def _build_prompt(image_path: str, doc_type: str, fields: list[str]) -> str:
    tmpl = ",".join(f'"{f}":""' for f in fields)
    return (
        f"이미지 파일을 읽어 {doc_type} 정보를 추출하세요. 파일 경로: {image_path}\n"
        "규칙:\n"
        "- 반드시 JSON 객체 하나만 출력. 다른 설명·머리말·코드펜스 금지.\n"
        f"- 형식: {{{tmpl}}}\n"
        "- 값을 못 읽으면 빈 문자열로 두세요. 추측하지 마세요.\n"
    )


def _parse_json_object(stdout: str) -> dict[str, Any]:
    try:
        text = (stdout or "").strip()
        if "```json" in text:
            text = text.split("```json", 1)[1].split("```", 1)[0]
        elif text.startswith("```"):
            text = text.split("```", 1)[1].split("```", 1)[0]
        i, j = text.find("{"), text.rfind("}")
        if i >= 0 and j > i:
            text = text[i:j + 1]
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def masked_preview(source: dict[str, Any]) -> dict[str, str]:
    """개인정보 마스킹 미리보기 — 로그·응답용(앞 2글자 + 길이)."""
    out = {}
    for k, v in source.items():
        v = str(v)
        out[k] = (v[:2] + "***" + f"({len(v)}자)") if v else "(빈값)"
    return out
