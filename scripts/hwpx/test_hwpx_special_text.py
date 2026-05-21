from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from hwpx_special_text import sanitize_hwpx_text, text_special_char_profile


def test_sanitize_hwpx_text_preserves_common_korean_symbols() -> None:
    text = "면적 1,000㎡ ※ 확인 ① ② & < >"

    result = sanitize_hwpx_text(text)

    assert result["text"] == text
    assert result["changed"] is False
    assert result["profile"]["invalid_xml_char_count"] == 0
    assert any(item["char"] == "㎡" for item in result["profile"]["special_chars"])


def test_sanitize_hwpx_text_removes_invalid_xml_control_chars() -> None:
    result = sanitize_hwpx_text("A\x00B\x08C")

    assert result["text"] == "ABC"
    assert result["changed"] is True
    assert len(result["replacements"]) == 2


def test_special_char_profile_reports_newlines_tabs_and_non_ascii() -> None:
    profile = text_special_char_profile("가\t나\n다")

    assert profile["tab_count"] == 1
    assert profile["newline_count"] == 1
    assert profile["non_ascii_count"] == 3
