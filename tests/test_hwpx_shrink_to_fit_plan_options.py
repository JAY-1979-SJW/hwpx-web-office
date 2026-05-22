"""
HWPX-EDITOR-SHRINK-TO-FIT-OPTION-PROPAGATION-01 회귀 테스트.

shrink_to_fit / vertical_align 옵션이 set_cells, set_cells_by_label,
set_cells_by_text, set_visual_cells 4개 plan 키에서 모두 동일하게
동작하는지 검증한다.
"""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

import pytest
import xml.etree.ElementTree as ET

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "hwpx"))

from hwpx_edit_tool import apply_edit_plan  # noqa: E402

NS = {
    "hp": "http://www.hancom.co.kr/hwpml/2011/paragraph",
    "hh": "http://www.hancom.co.kr/hwpml/2011/head",
    "hs": "http://www.hancom.co.kr/hwpml/2011/section",
}


@pytest.fixture
def fixture_path() -> Path:
    """굴착공사 협의서 hancom-converted hwpx fixture path."""
    base = Path(r"C:\Users\skyjw\Downloads\hwpx_compare")
    matches = list(base.glob("08_*/*.hwpx"))
    if not matches:
        pytest.skip("fixture HWPX not available")
    return matches[0]


def _ref_ids(path: Path) -> tuple[set[str], set[str], set[str], set[str]]:
    """(defined_charPr, referenced_charPr, defined_paraPr, referenced_paraPr)"""
    with zipfile.ZipFile(path) as zf:
        header = ET.fromstring(zf.read("Contents/header.xml"))
        section = ET.fromstring(zf.read("Contents/section0.xml"))
    defined_char = {cp.attrib.get("id") for cp in header.iter(f"{{{NS['hh']}}}charPr") if cp.attrib.get("id")}
    defined_para = {pp.attrib.get("id") for pp in header.iter(f"{{{NS['hh']}}}paraPr") if pp.attrib.get("id")}
    referenced_char = {run.attrib.get("charPrIDRef") for run in section.iter(f"{{{NS['hp']}}}run") if run.attrib.get("charPrIDRef")}
    referenced_para = {p.attrib.get("paraPrIDRef") for p in section.iter(f"{{{NS['hp']}}}p") if p.attrib.get("paraPrIDRef")}
    return defined_char, referenced_char, defined_para, referenced_para


def _mimetype_compress_type(path: Path) -> int:
    with zipfile.ZipFile(path) as zf:
        return zf.getinfo("mimetype").compress_type


def _charpr_heights(path: Path) -> dict[str, int]:
    with zipfile.ZipFile(path) as zf:
        header = ET.fromstring(zf.read("Contents/header.xml"))
    return {
        cp.attrib["id"]: int(cp.attrib.get("height", "1000") or 1000)
        for cp in header.iter(f"{{{NS['hh']}}}charPr")
        if cp.attrib.get("id")
    }


def _assert_no_dangling(path: Path) -> None:
    defined_c, referenced_c, defined_p, referenced_p = _ref_ids(path)
    assert referenced_c <= defined_c, f"dangling charPrIDRef: {referenced_c - defined_c}"
    assert referenced_p <= defined_p, f"dangling paraPrIDRef: {referenced_p - defined_p}"


# ──────────────────────────────────────────────────────────────────────────────


def test_set_cells_without_shrink_keeps_original_charpr(tmp_path, fixture_path):
    """옵션 없으면 기존 동작 유지 (charPr 신규 정의 없음)."""
    out = tmp_path / "out.hwpx"
    before = _charpr_heights(fixture_path)
    apply_edit_plan(fixture_path, out, {"set_cells": [{"table": 1, "row": 0, "col": 1, "value": "TEST"}]})
    after = _charpr_heights(out)
    assert set(after.keys()) == set(before.keys()), "charPr id set changed without shrink_to_fit"
    _assert_no_dangling(out)


def test_set_cells_with_shrink_to_fit_creates_clone(tmp_path, fixture_path):
    """shrink_to_fit=True이면 새 charPr id가 생성되고 height가 줄어든다."""
    out = tmp_path / "out.hwpx"
    before = _charpr_heights(fixture_path)
    long_value = "한강변 도시가스 배관 정비공사 매우 긴 텍스트입니다 " * 3
    apply_edit_plan(
        fixture_path,
        out,
        {"set_cells": [{"table": 1, "row": 0, "col": 1, "value": long_value, "shrink_to_fit": True}]},
    )
    after = _charpr_heights(out)
    new_ids = set(after.keys()) - set(before.keys())
    assert new_ids, f"no new charPr clone produced (before={set(before)}, after={set(after)})"
    for nid in new_ids:
        assert after[nid] < max(before.values()), f"new charPr height {after[nid]} not reduced"
    _assert_no_dangling(out)


def test_set_cells_by_label_with_shrink_to_fit_creates_clone(tmp_path, fixture_path):
    """set_cells_by_label에서도 shrink_to_fit이 동작한다."""
    out = tmp_path / "out.hwpx"
    before_ids = set(_charpr_heights(fixture_path))
    long_value = "긴긴긴 공사명 텍스트 " * 5
    apply_edit_plan(
        fixture_path,
        out,
        {
            "set_cells_by_label": [
                {
                    "table": 1,
                    "contains": "공 사 명",
                    "value": long_value,
                    "shrink_to_fit": True,
                    "vertical_align": "CENTER",
                }
            ]
        },
    )
    after_ids = set(_charpr_heights(out))
    assert after_ids - before_ids, "set_cells_by_label did not produce charPr clone with shrink_to_fit"
    _assert_no_dangling(out)


def test_set_cells_by_text_with_shrink_to_fit_creates_clone(tmp_path, fixture_path):
    """set_cells_by_text에서도 shrink_to_fit이 동작한다."""
    out = tmp_path / "out.hwpx"
    before_ids = set(_charpr_heights(fixture_path))
    long_value = "교체된 새 긴긴긴 텍스트 " * 5
    apply_edit_plan(
        fixture_path,
        out,
        {
            "set_cells_by_text": [
                {
                    "table": 2,
                    "contains": "고압가스 배관",
                    "value": long_value,
                    "shrink_to_fit": True,
                }
            ]
        },
    )
    after_ids = set(_charpr_heights(out))
    assert after_ids - before_ids, "set_cells_by_text did not produce charPr clone with shrink_to_fit"
    _assert_no_dangling(out)


def test_set_visual_cells_shrink_to_fit_still_works(tmp_path, fixture_path):
    """기존 set_visual_cells shrink_to_fit 동작이 회귀 없이 유지된다."""
    out = tmp_path / "out.hwpx"
    before_ids = set(_charpr_heights(fixture_path))
    long_value = "(주)한국가스공사 매우 긴 시공자명 텍스트 " * 3
    apply_edit_plan(
        fixture_path,
        out,
        {
            "set_visual_cells": [
                {
                    "table": 3,
                    "visual_row": 1,
                    "visual_col": 7,
                    "value": long_value,
                    "shrink_to_fit": True,
                }
            ]
        },
    )
    after_ids = set(_charpr_heights(out))
    assert after_ids - before_ids, "set_visual_cells shrink_to_fit regression"
    _assert_no_dangling(out)


def test_shrink_to_fit_does_not_alter_original_charpr(tmp_path, fixture_path):
    """shrink_to_fit 적용 후 원본 charPr 정의는 그대로 보존된다."""
    out = tmp_path / "out.hwpx"
    before = _charpr_heights(fixture_path)
    apply_edit_plan(
        fixture_path,
        out,
        {"set_cells": [{"table": 1, "row": 0, "col": 1, "value": "긴" * 80, "shrink_to_fit": True}]},
    )
    after = _charpr_heights(out)
    for cid, height in before.items():
        assert after.get(cid) == height, f"original charPr id={cid} mutated: {height} -> {after.get(cid)}"


def test_mimetype_remains_zip_stored_with_shrink(tmp_path, fixture_path):
    """shrink_to_fit 호출 경로에서도 mimetype은 ZIP_STORED 유지."""
    out = tmp_path / "out.hwpx"
    apply_edit_plan(
        fixture_path,
        out,
        {"set_cells": [{"table": 1, "row": 0, "col": 1, "value": "긴 텍스트 " * 30, "shrink_to_fit": True}]},
    )
    assert _mimetype_compress_type(out) == zipfile.ZIP_STORED


def test_no_options_means_no_post_edit_calls(tmp_path, fixture_path):
    """옵션 없을 때 charPr 신규 정의가 생기지 않는다 (기존 동작 보장)."""
    out = tmp_path / "out.hwpx"
    before_ids = set(_charpr_heights(fixture_path))
    apply_edit_plan(
        fixture_path,
        out,
        {
            "set_cells": [{"table": 1, "row": 0, "col": 1, "value": "A"}],
            "set_cells_by_label": [{"table": 1, "contains": "접 수 번 호", "value": "B"}],
            "set_cells_by_text": [{"table": 2, "contains": "고압가스 배관", "value": "C"}],
            "set_visual_cells": [{"table": 3, "visual_row": 1, "visual_col": 7, "value": "D"}],
        },
    )
    after_ids = set(_charpr_heights(out))
    assert after_ids == before_ids, f"charPr ids changed without options: extra={after_ids - before_ids}"
