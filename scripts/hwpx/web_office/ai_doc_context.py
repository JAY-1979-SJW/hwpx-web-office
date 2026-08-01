"""문서 문맥 추출 — AI 해석에 줄 '칸 주변 정보'를 순수 함수로 만든다.

기준서: docs/design/hwpx_ai_doc_interpretation_fill_standard.md §5

현행 ai_form_fill 은 라벨 문자열만 모델에 보낸다(매핑률 실측 30.7%,
2026-08-01 전수 조사). 사람이 서식을 채울 때는 라벨만 보지 않는다 —
같은 행의 왼쪽 칸, 같은 열의 위 칸, 서식 제목을 함께 본다. 그 문맥을
여기서 만든다.

이 모듈은 AI 를 모른다 — documentModel 과 입력 스키마만 받아 dict 를
낸다. 전부 순수 함수라 CLI 없이 시험된다.
"""
from __future__ import annotations

import re
from typing import Any

# cell_t_s{섹션}_{표:03d}_r{행}_c{열} — coordinate_layout._cell_id 와 동일
_CID_RE = re.compile(r"^cell_t_s(\d+)_(\d+)_r(\d+)_c(\d+)$")
# par_t_s{섹션}_{표:03d}_r{행}_c{열}_p{문단} — form_direct_fill 과 동일
_PID_RE = re.compile(r"^par_t_s(\d+)_(\d+)_r(\d+)_c(\d+)_p(\d+)$")

# 문맥 텍스트 한 조각의 길이 상한 — 셀에 안내문 전체가 들어있는 경우
# 프롬프트가 문서 전문으로 부풀지 않게 자른다.
_MAX_CONTEXT_CHARS = 60


def cell_text_index(doc_model: dict) -> dict[tuple[int, int, int, int], str]:
    """documentModel.cells → {(섹션, 표, 행, 열): 셀 텍스트}."""
    idx: dict[tuple[int, int, int, int], str] = {}
    for c in doc_model.get("cells") or []:
        m = _CID_RE.match(c.get("cellId") or "")
        if not m:
            continue
        key = tuple(int(g) for g in m.groups())
        idx[key] = (c.get("text") or "").strip()
    return idx


def document_title(doc_model: dict, *, fallback: str = "") -> str:
    """서식 제목 — 표 밖 첫 비어있지 않은 문단. 없으면 fallback(cleanName)."""
    for p in doc_model.get("paragraphs") or []:
        scope = p.get("containerScope") or {}
        if scope.get("kind") == "cell":
            continue
        text = "".join(r.get("text") or "" for r in p.get("runs") or []).strip()
        if text:
            return text[:_MAX_CONTEXT_CHARS]
    return fallback


def _clip(text: str) -> str:
    text = (text or "").strip()
    return text[:_MAX_CONTEXT_CHARS]


def _nearest_left(idx: dict, sec: int, tbl: int, row: int, col: int) -> str:
    for c in range(col - 1, -1, -1):
        t = idx.get((sec, tbl, row, c), "")
        if t:
            return _clip(t)
    return ""


def _nearest_up(idx: dict, sec: int, tbl: int, row: int, col: int) -> str:
    for r in range(row - 1, -1, -1):
        t = idx.get((sec, tbl, r, col), "")
        if t:
            return _clip(t)
    return ""


def context_for_input(inp: dict, idx: dict) -> dict[str, str]:
    """입력칸 1개의 문맥 — 왼쪽 라벨·위 머리글. 좌표는 paragraphId 에서."""
    m = _PID_RE.match(inp.get("paragraphId") or "")
    if not m:
        return {"left": "", "up": ""}
    sec, tbl, row, col, _ = (int(g) for g in m.groups())
    return {
        "left": _nearest_left(idx, sec, tbl, row, col),
        "up": _nearest_up(idx, sec, tbl, row, col),
    }


def build_context_fields(
    schema_inputs: list[dict], doc_model: dict, *, title: str = "",
) -> list[dict[str, Any]]:
    """신청인 입력칸 목록 → AI 해석 입력(문맥 포함 필드 목록).

    key 는 paragraphId — 라벨 중복(같은 라벨이 여러 칸)에도 칸을 정확히
    가리키게 한다. 현행 ai_form_fill 의 라벨 기준 재매핑은 중복 라벨을
    첫 칸에만 잇는 약점이 있었다.
    """
    idx = cell_text_index(doc_model)
    doc_title = document_title(doc_model, fallback=title)
    out: list[dict[str, Any]] = []
    for inp in schema_inputs:
        if inp.get("role") != "applicant":
            continue
        pid = inp.get("paragraphId") or ""
        if not pid:
            continue
        ctx = context_for_input(inp, idx)
        out.append({
            "key": pid,
            "label": _clip(inp.get("label") or ""),
            "subject": inp.get("subject") or "self",
            "sensitive": bool(inp.get("sensitive")),
            "inputType": inp.get("inputType") or "text",
            "semantic": inp.get("semantic") or "",
            "context": {"title": doc_title, **ctx},
        })
    return out
