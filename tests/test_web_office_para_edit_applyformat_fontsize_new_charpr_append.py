"""WEB-OFFICE-PARA-EDIT-APPLYFORMAT-FONTSIZE-NEW-CHARPR-APPEND-01.

CLAUDE.md §4.1 조건부 허용 — 폰트 크기 변경용 신규 charPr append-only
생성. 기존 "매칭되는 charPr 로 스왑"(existing_charpr 계열 테스트)이
못 다루는 경우: 원하는 크기의 charPr 가 문서에 아예 없을 때.
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
    append_char_pr_for_size, find_matching_char_pr)

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
def test_append_creates_sequential_id_without_touching_existing():
    before = _header_bytes()
    before_prs = _char_prs(before)
    assert before_prs, "fixture 에 charPr 가 있어야 테스트 의미 있음"

    source_id = sorted(before_prs, key=lambda i: int(i))[0]
    after, new_id = append_char_pr_for_size(before, source_id, 18.0)
    after_prs = _char_prs(after)

    max_before = max(int(i) for i in before_prs)
    assert new_id == str(max_before + 1), "신규 id 는 기존 최대값+1"
    assert new_id not in before_prs, "신규 id 는 이전엔 없었음"

    # append-only — 기존 charPr 는 XML 속성 단위로 완전 동일해야 함
    for cid, elem in before_prs.items():
        assert cid in after_prs
        assert after_prs[cid].attrib == elem.attrib, (
            f"기존 charPr {cid} 가 변형됨(append-only 위반)")


@pytest.mark.skipif(not FIXTURE.is_file(), reason="fixture missing")
def test_new_char_pr_height_changed_other_attrs_inherited():
    before = _header_bytes()
    before_prs = _char_prs(before)
    source_id = sorted(before_prs, key=lambda i: int(i))[0]
    source_elem = before_prs[source_id]

    after, new_id = append_char_pr_for_size(before, source_id, 18.0)
    after_prs = _char_prs(after)
    new_elem = after_prs[new_id]

    assert new_elem.get("height") == "1800", "18.0pt → HWPUNIT 1800"
    # height/id 외 속성은 원본 그대로 상속(폰트 종류 등 무변경)
    for key, val in source_elem.attrib.items():
        if key in ("id", "height"):
            continue
        assert new_elem.get(key) == val, f"속성 {key} 가 원본과 달라짐"

    # 자식 요소(fontRef 등)도 그대로 복제됐는지 개수로 확인
    assert len(list(new_elem)) == len(list(source_elem))


@pytest.mark.skipif(not FIXTURE.is_file(), reason="fixture missing")
def test_unknown_source_id_raises():
    before = _header_bytes()
    with pytest.raises(ValueError):
        append_char_pr_for_size(before, "__not_a_real_id__", 12.0)


def test_find_matching_char_pr_returns_none_when_absent():
    defs = {
        "1": {"fontFace": "함초롬바탕", "fontName": "함초롬바탕",
                    "bold": False, "italic": False, "fontSizePt": 10},
    }
    assert find_matching_char_pr(defs, "1", 18.0) is None


def test_find_matching_char_pr_returns_match_when_present():
    defs = {
        "1": {"fontFace": "함초롬바탕", "fontName": "함초롬바탕",
                    "bold": False, "italic": False, "fontSizePt": 10},
        "2": {"fontFace": "함초롬바탕", "fontName": "함초롬바탕",
                    "bold": False, "italic": False, "fontSizePt": 18},
    }
    assert find_matching_char_pr(defs, "1", 18.0) == "2"
