"""칸 글자 일부만 고치는 편집 — 라벨 뒤에 값 끼우기(after), 자리표시 글자 바꾸기(replace).

칸 전체를 새 글자로 덮지 않으므로 칸 안의 다른 줄·서명 문구·표시(fwSpace·tab)가 그대로 남는다.
계획 단계(예상 글자 계산)와 편집기(실제 글자 수정)가 같은 함수를 쓰므로 둘의 결과가 어긋나지 않는다.

edit 모양:
  {"kind": "after",   "anchor": "원 공사명:", "value": "OO공사"}   anchor 글자 바로 뒤(공백 앞)에 ' 값' 을 끼운다
  {"kind": "replace", "pattern": r"\\(\\s*\\)", "value": "(OO)"}  pattern 에 맞는 첫 글자를 value 로 바꾼다
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

AFTER = "after"
REPLACE = "replace"


def _char_pattern(ch: str) -> str:
    """글자 하나와 그 NFKC 꼴('①'↔'1')을 둘 다 받는다 — 계획 단계는 정규화한 글자, 편집기는 원본 글자를 다룬다."""
    folded = unicodedata.normalize("NFKC", ch)
    if folded == ch:
        return re.escape(ch)
    return "(?:" + re.escape(ch) + "|" + re.escape(folded) + ")"


def apply_edit(text: str, edit: dict[str, Any]) -> str | None:
    """text 에 edit 하나를 적용한 글자. 자리를 찾지 못하면 None."""
    value = str(edit.get("value", ""))
    kind = edit.get("kind")
    if kind == AFTER:
        anchor = str(edit.get("anchor", ""))
        if not anchor:
            return None
        # 칸 글자의 공백은 서식마다 다르다('원  공사명:' / '원 공사명:') — anchor 의 공백 개수는 따지지 않는다
        tokens = r"\s*".join(_char_pattern(ch) for ch in anchor if not ch.isspace())
        m = re.search(r"(?P<a>" + tokens + r")(?P<w>\s*)", text)
        if m is None:
            return None
        return text[: m.start()] + m.group("a") + " " + value + m.group("w") + text[m.end() :]
    if kind == REPLACE:
        pattern = str(edit.get("pattern", ""))
        if not pattern:
            return None
        m = re.search(pattern, text)
        if m is None:
            return None
        return text[: m.start()] + value + text[m.end() :]
    return None


def apply_edits(text: str, edits: list[dict[str, Any]]) -> str | None:
    """edit 를 차례로 적용한다. 하나라도 자리를 찾지 못하면 None."""
    for edit in edits:
        edited = apply_edit(text, edit)
        if edited is None:
            return None
        text = edited
    return text
