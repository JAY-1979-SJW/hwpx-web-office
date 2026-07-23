"""WEB-OFFICE-PARA-EDIT-APPLYFORMAT-ALL-PROPERTIES-NEW-CHARPR-APPEND-01.

CLAUDE.md §4.1 확장(2026-07-24) — 폰트 크기뿐 아니라 글꼴 종류·색상·
굵게/기울임/밑줄까지 append-only 신규 charPr 로 지원한다.
"""
from __future__ import annotations
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest

PR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PR))
sys.path.insert(0, str(PR / "scripts/hwpx"))

from scripts.hwpx.web_office.charpr_append import (  # noqa: E402
    append_char_pr_with_overrides, find_matching_char_pr)

FIXTURE = PR / "tests/fixtures/hwpx/corpus/fx_metadata_form.hwpx"


def _ln(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _header_bytes() -> bytes:
    with zipfile.ZipFile(FIXTURE) as z:
        return z.read("Contents/header.xml")


def _char_prs(header_bytes: bytes) -> dict[str, ET.Element]:
    root = ET.fromstring(header_bytes)
    return {e.get("id"): e for e in root.iter() if _ln(e.tag) == "charPr"}


@pytest.mark.skipif(not FIXTURE.is_file(), reason="fixture missing")
def test_bold_italic_underline_toggle_append_only():
    before = _header_bytes()
    before_prs = _char_prs(before)
    source_id = sorted(before_prs, key=lambda i: int(i))[0]

    after, new_id = append_char_pr_with_overrides(
        before, source_id, {"bold": True, "italic": True, "underline": True})
    after_prs = _char_prs(after)
    new_elem = after_prs[new_id]

    assert any(_ln(c.tag) == "bold" for c in new_elem)
    assert any(_ln(c.tag) == "italic" for c in new_elem)
    assert any(_ln(c.tag) == "underline" for c in new_elem)

    # append-only — 기존 항목 불변
    for cid, elem in before_prs.items():
        assert after_prs[cid].attrib == elem.attrib


@pytest.mark.skipif(not FIXTURE.is_file(), reason="fixture missing")
def test_bold_off_removes_child_on_copy_only():
    before = _header_bytes()
    before_prs = _char_prs(before)
    # bold 가 걸린 charPr 찾기(없으면 skip)
    bold_id = next((cid for cid, e in before_prs.items()
                     if any(_ln(c.tag) == "bold" for c in e)), None)
    if bold_id is None:
        pytest.skip("fixture 에 bold charPr 없음")
    after, new_id = append_char_pr_with_overrides(
        before, bold_id, {"bold": False})
    after_prs = _char_prs(after)
    assert not any(_ln(c.tag) == "bold" for c in after_prs[new_id])
    # 원본 bold charPr 는 그대로
    assert any(_ln(c.tag) == "bold" for c in after_prs[bold_id])


@pytest.mark.skipif(not FIXTURE.is_file(), reason="fixture missing")
def test_text_color_override():
    before = _header_bytes()
    before_prs = _char_prs(before)
    source_id = sorted(before_prs, key=lambda i: int(i))[0]
    after, new_id = append_char_pr_with_overrides(
        before, source_id, {"textColor": "#FF0000"})
    after_prs = _char_prs(after)
    assert after_prs[new_id].get("textColor") == "#FF0000"


@pytest.mark.skipif(not FIXTURE.is_file(), reason="fixture missing")
def test_font_face_id_applied_to_all_language_slots():
    before = _header_bytes()
    before_prs = _char_prs(before)
    source_id = sorted(before_prs, key=lambda i: int(i))[0]
    after, new_id = append_char_pr_with_overrides(
        before, source_id, {"fontFaceId": "3"})
    after_prs = _char_prs(after)
    fr = next(c for c in after_prs[new_id] if _ln(c.tag) == "fontRef")
    for slot in ("hangul", "latin", "hanja", "japanese", "other", "symbol",
                 "user"):
        assert fr.get(slot) == "3"


def test_unknown_override_key_raises():
    with pytest.raises(ValueError):
        append_char_pr_with_overrides(
            _header_bytes() if FIXTURE.is_file() else b"<hh:head/>",
            "1", {"notARealKey": 1})


def test_find_matching_char_pr_multi_property():
    defs = {
        "1": {"fontRef": {"hangul": "1"}, "fontSizePt": 10,
                    "textColor": "", "bold": False, "italic": False,
                    "underline": False},
        "2": {"fontRef": {"hangul": "1"}, "fontSizePt": 10,
                    "textColor": "", "bold": True, "italic": False,
                    "underline": False},
    }
    # bold=True 만 다르고 나머지 같은 후보를 찾아야 함
    assert find_matching_char_pr(defs, "1", {"bold": True}) == "2"
    # 없는 조합은 None
    assert find_matching_char_pr(defs, "1", {"italic": True}) is None
