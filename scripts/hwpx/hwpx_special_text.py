"""Text safety helpers for HWPX XML content."""

from __future__ import annotations

from typing import Any
import unicodedata


def is_xml10_char(ch: str) -> bool:
    code = ord(ch)
    return (
        code == 0x09
        or code == 0x0A
        or code == 0x0D
        or 0x20 <= code <= 0xD7FF
        or 0xE000 <= code <= 0xFFFD
        or 0x10000 <= code <= 0x10FFFF
    )


def text_special_char_profile(text: str) -> dict[str, Any]:
    profile: dict[str, Any] = {
        "length": len(text),
        "invalid_xml_char_count": 0,
        "control_char_count": 0,
        "newline_count": 0,
        "tab_count": 0,
        "non_ascii_count": 0,
        "special_chars": [],
    }
    seen: set[str] = set()
    for ch in text:
        code = ord(ch)
        if not is_xml10_char(ch):
            profile["invalid_xml_char_count"] += 1
        if code < 32 and ch not in "\r\n\t":
            profile["control_char_count"] += 1
        if ch in "\r\n":
            profile["newline_count"] += 1
        if ch == "\t":
            profile["tab_count"] += 1
        if code > 127:
            profile["non_ascii_count"] += 1
        category = unicodedata.category(ch)
        if code > 127 and (category.startswith(("S", "P")) or "SIGN" in unicodedata.name(ch, "")):
            if ch not in seen:
                seen.add(ch)
                profile["special_chars"].append(
                    {
                        "char": ch,
                        "codepoint": f"U+{code:04X}",
                        "name": unicodedata.name(ch, "UNKNOWN"),
                        "category": category,
                    }
                )
    profile["ok"] = profile["invalid_xml_char_count"] == 0 and profile["control_char_count"] == 0
    return profile


def sanitize_hwpx_text(value: Any, *, normalize_newlines: bool = True) -> dict[str, Any]:
    original = "" if value is None else str(value)
    text = original
    replacements: list[dict[str, Any]] = []
    if normalize_newlines:
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        if normalized != text:
            replacements.append({"type": "NORMALIZE_NEWLINE", "from": "\\r", "to": "\\n"})
        text = normalized
    cleaned_chars: list[str] = []
    for index, ch in enumerate(text):
        if is_xml10_char(ch) and not (ord(ch) < 32 and ch not in "\n\t"):
            cleaned_chars.append(ch)
            continue
        replacements.append({"type": "REMOVE_INVALID_XML_CHAR", "index": index, "codepoint": f"U+{ord(ch):04X}"})
    sanitized = "".join(cleaned_chars)
    return {
        "original": original,
        "text": sanitized,
        "changed": sanitized != original,
        "replacements": replacements,
        "profile": text_special_char_profile(sanitized),
    }


__all__ = ["is_xml10_char", "sanitize_hwpx_text", "text_special_char_profile"]
