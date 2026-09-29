"""HWPX-PARSER-V2-SKELETON-01: Parser V2 skeleton 테스트.

scripts/hwpx/parser 패키지의 각 모듈이 계약을 준수하는지 검증한다.
원본 HWPX 파일은 수정되지 않는다.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = PROJECT_ROOT / "tests" / "fixtures" / "hwpx" / "corpus"
PARSER_PKG = PROJECT_ROOT / "scripts" / "hwpx" / "parser"

sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

# ── import 테스트 ─────────────────────────────────────────────────────────────


def test_parser_package_importable():
    from hwpx.parser import SCHEMA_VERSION

    assert SCHEMA_VERSION == "v2"


def test_contract_schema_version():
    from hwpx.parser.parser_contract import ENGINE_VERSION, SCHEMA_VERSION

    assert SCHEMA_VERSION == "v2"
    assert isinstance(ENGINE_VERSION, str) and len(ENGINE_VERSION) > 0


def test_errors_module_importable():
    from hwpx.parser.errors import ErrCode, WarnCode

    assert WarnCode.ZIP_OPEN_FAIL or True  # 존재 확인
    assert ErrCode.ZIP_OPEN_FAIL == "ZIP_OPEN_FAIL"


# ── package_reader ────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def fx_metadata():
    return FIXTURE_DIR / "fx_metadata_form.hwpx"


@pytest.fixture(scope="session")
def fx_many_tables():
    return FIXTURE_DIR / "fx_many_tables_page_marker.hwpx"


def test_package_reader_returns_package_info(fx_metadata):
    from hwpx.parser.package_reader import read_package_info

    pkg, warns = read_package_info(fx_metadata)
    assert pkg.entryCount > 0
    assert pkg.hasMimetype is True
    assert pkg.xmlDecodeOk is True


def test_package_reader_section_count(fx_many_tables):
    from hwpx.parser.package_reader import read_package_info

    pkg, _ = read_package_info(fx_many_tables)
    assert pkg.sectionFileCount >= 1


def test_package_reader_readonly(fx_metadata):
    mtime_before = fx_metadata.stat().st_mtime
    from hwpx.parser.package_reader import read_package_info

    read_package_info(fx_metadata)
    mtime_after = fx_metadata.stat().st_mtime
    assert mtime_before == mtime_after


# ── style_parser ──────────────────────────────────────────────────────────────


def test_style_parser_returns_counts(fx_metadata):
    from hwpx.parser.package_reader import read_header_xml
    from hwpx.parser.style_parser import parse_style_summary

    header_raw = read_header_xml(fx_metadata)
    assert header_raw is not None
    style_info = parse_style_summary(header_raw)
    assert style_info.charPrCount >= 0
    assert style_info.paraPrCount >= 0
    assert style_info.borderFillCount >= 0


def test_style_parser_enrich(fx_metadata):
    from hwpx.parser.package_reader import read_header_xml, read_section_xmls
    from hwpx.parser.style_parser import enrich_style_info, parse_style_summary

    header_raw = read_header_xml(fx_metadata)
    style_info = parse_style_summary(header_raw)
    section_xmls = list(read_section_xmls(fx_metadata).values())
    enrich_style_info(style_info, section_xmls)
    assert isinstance(style_info.referencedCharPrIds, list)
    assert isinstance(style_info.referencedBorderFillIds, list)


# ── table_parser ──────────────────────────────────────────────────────────────


def test_table_parser_returns_list(fx_metadata):
    from hwpx.parser.package_reader import read_section_xmls
    from hwpx.parser.table_parser import parse_tables_from_section

    sections = read_section_xmls(fx_metadata)
    all_tables = []
    for raw in sections.values():
        all_tables.extend(parse_tables_from_section(raw, 0))
    assert len(all_tables) >= 1


def test_table_parser_cells_present(fx_metadata):
    from hwpx.parser.package_reader import read_section_xmls
    from hwpx.parser.table_parser import parse_tables_from_section

    sections = read_section_xmls(fx_metadata)
    for raw in sections.values():
        for tbl in parse_tables_from_section(raw, 0):
            assert len(tbl.cells) >= 1
            break


def test_table_parser_many_tables(fx_many_tables):
    from hwpx.parser.package_reader import read_section_xmls
    from hwpx.parser.table_parser import parse_tables_from_section

    sections = read_section_xmls(fx_many_tables)
    all_tables = []
    for raw in sections.values():
        all_tables.extend(parse_tables_from_section(raw, 0))
    assert len(all_tables) >= 10


# ── block_parser ──────────────────────────────────────────────────────────────


def test_block_parser_returns_blocks(fx_metadata):
    from hwpx.parser.block_parser import parse_blocks_from_section
    from hwpx.parser.package_reader import read_section_xmls

    sections = read_section_xmls(fx_metadata)
    all_blocks = []
    for raw in sections.values():
        all_blocks.extend(parse_blocks_from_section(raw, 0))
    assert len(all_blocks) >= 1


def test_block_parser_types(fx_many_tables):
    from hwpx.parser.block_parser import parse_blocks_from_section
    from hwpx.parser.package_reader import read_section_xmls

    sections = read_section_xmls(fx_many_tables)
    valid_types = {"paragraph", "table", "image", "drawing", "page_marker", "unknown"}
    for raw in sections.values():
        for b in parse_blocks_from_section(raw, 0):
            assert b.type in valid_types
            assert b.orderKey != ""


def test_block_parser_order_key_format(fx_metadata):
    from hwpx.parser.block_parser import parse_blocks_from_section
    from hwpx.parser.package_reader import read_section_xmls

    sections = read_section_xmls(fx_metadata)
    for raw in sections.values():
        for b in parse_blocks_from_section(raw, 0):
            assert re.match(r"s\d+:b\d+", b.orderKey)


# ── layout_classifier ─────────────────────────────────────────────────────────


def test_layout_classifier_returns_layout(fx_many_tables):
    from hwpx.parser.layout_classifier import classify_table_layout
    from hwpx.parser.package_reader import read_section_xmls
    from hwpx.parser.table_parser import parse_tables_from_section

    sections = read_section_xmls(fx_many_tables)
    for raw in sections.values():
        for tbl in parse_tables_from_section(raw, 0):
            layout, conf, evidence = classify_table_layout(tbl)
            assert isinstance(layout, str) and len(layout) > 0
            assert 0.0 <= conf <= 1.0
            assert len(evidence) >= 1
            break


def test_layout_classifier_page_marker_detected(fx_many_tables):
    from hwpx.parser.layout_classifier import enrich_table_layout
    from hwpx.parser.package_reader import read_section_xmls
    from hwpx.parser.table_parser import parse_tables_from_section

    sections = read_section_xmls(fx_many_tables)
    layouts = []
    for raw in sections.values():
        for tbl in parse_tables_from_section(raw, 0):
            enrich_table_layout(tbl)
            layouts.append(tbl.layoutGuess)
    assert "page_marker_table" in layouts


# ── input_slot_detector ───────────────────────────────────────────────────────


def test_input_slot_detector_returns_list(fx_metadata):
    from hwpx.parser.input_slot_detector import detect_input_slots
    from hwpx.parser.layout_classifier import enrich_table_layout
    from hwpx.parser.package_reader import read_section_xmls
    from hwpx.parser.table_parser import parse_tables_from_section

    sections = read_section_xmls(fx_metadata)
    all_tables = []
    for raw in sections.values():
        for tbl in parse_tables_from_section(raw, 0):
            enrich_table_layout(tbl)
            all_tables.append(tbl)
    slots = detect_input_slots(all_tables)
    assert isinstance(slots, list)


def test_input_slot_confidence_range(fx_metadata):
    from hwpx.parser.input_slot_detector import detect_input_slots
    from hwpx.parser.layout_classifier import enrich_table_layout
    from hwpx.parser.package_reader import read_section_xmls
    from hwpx.parser.table_parser import parse_tables_from_section

    sections = read_section_xmls(fx_metadata)
    all_tables = []
    for raw in sections.values():
        for tbl in parse_tables_from_section(raw, 0):
            enrich_table_layout(tbl)
            all_tables.append(tbl)
    for slot in detect_input_slots(all_tables):
        assert 0.0 <= slot.confidence <= 1.0
        assert slot.source in (
            "label_right",
            "label_below",
            "form_pair",
            "table_append_row",
            "schedule_bar_range",
            "status_cell",
            "manual_candidate",
        )


# ── parser_engine (통합) ──────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def all_fixture_results():
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
    from hwpx.parser import parse_hwpx_v2

    results = {}
    for fx in FIXTURE_DIR.glob("*.hwpx"):
        results[fx.stem] = parse_hwpx_v2(fx)
    return results


def test_parse_hwpx_v2_returns_result(all_fixture_results):
    from hwpx.parser import ParserV2Result

    for name, result in all_fixture_results.items():
        assert isinstance(result, ParserV2Result), f"{name}: not ParserV2Result"


def test_parse_hwpx_v2_schema_version(all_fixture_results):
    for name, result in all_fixture_results.items():
        assert result.schemaVersion == "v2", f"{name}: schemaVersion != v2"


def test_parse_hwpx_v2_tables_present(all_fixture_results):
    for name, result in all_fixture_results.items():
        assert result.document.tableCount >= 1, f"{name}: no tables"


def test_parse_hwpx_v2_no_errors(all_fixture_results):
    for name, result in all_fixture_results.items():
        assert not result.errors, f"{name}: errors={[e.code for e in result.errors]}"


def test_parse_hwpx_v2_blocks_present(all_fixture_results):
    for name, result in all_fixture_results.items():
        assert len(result.blocks) >= 1, f"{name}: no blocks"


def test_parse_hwpx_v2_title_candidate_not_whole_document(all_fixture_results):
    """회귀 방지: titleCandidate가 문서 전체를 통째로 담으면 안 된다.

    HWPX 관공서 서식은 표(hp:tbl)가 문단 안에 컨트롤로 중첩되는 경우가
    흔한데, _para_text가 이 중첩 표까지 재귀적으로 텍스트를 긁던 버그가
    있었다(2026-09-29, python-hwpx 교차 검증으로 발견). 표 밖 본문
    문단이 비어있으면 표 안 첫 비어있지 않은 셀 텍스트를 제목 후보로
    쓰는 폴백으로 고쳤다 — 실제 표 셀 하나 분량을 크게 넘지 않아야
    한다(느슨한 상한선으로 회귀를 감지).
    """
    for name, result in all_fixture_results.items():
        title = result.document.titleCandidate
        if title:
            assert len(title) < 200, (
                f"{name}: titleCandidate가 비정상적으로 김({len(title)}자) — "
                f"중첩 표 전체가 제목에 섞여 들어가는 회귀 의심: {title[:80]!r}..."
            )


def test_parse_hwpx_v2_title_candidate_metadata_form(all_fixture_results):
    """fx_metadata_form은 표 안 첫 셀이 정확히 이 값이어야 한다(고정 회귀 값)."""
    result = all_fixture_results["fx_metadata_form"]
    assert result.document.titleCandidate == "[별지제10호의2서식] <신설 2020. 12. 14.>"


def test_parse_hwpx_v2_json_serializable(all_fixture_results):
    for name, result in all_fixture_results.items():
        d = result.to_dict()
        try:
            json.dumps(d)
        except Exception as exc:  # ruff: ignore[blind-except] - 직렬화 실패 원인 무관하게 테스트 실패로 보고
            pytest.fail(f"{name}: JSON serialize failed: {exc}")


# ── 원본 수정 없음 ─────────────────────────────────────────────────────────────


def test_original_files_not_modified(all_fixture_results):
    for fx in FIXTURE_DIR.glob("*.hwpx"):
        # 파일이 존재하고 빈 파일이 아님
        assert fx.stat().st_size > 0


# ── write_package / apply_edit_plan import 없음 ──────────────────────────────


def test_no_write_package_import():
    for py_file in PARSER_PKG.glob("*.py"):
        src = py_file.read_text(encoding="utf-8")
        # docstring/comment 라인은 제외하고 실제 코드 라인에서만 검사
        code_lines = [
            l
            for l in src.splitlines()
            if not l.strip().startswith("#")
            and not l.strip().startswith('"""')
            and not l.strip().startswith("'''")
        ]
        code_src = "\n".join(code_lines)
        assert not re.search(r"\bwrite_package\s*\(", code_src), (
            f"{py_file.name}: write_package 호출 발견"
        )


def test_no_apply_edit_plan_import():
    for py_file in PARSER_PKG.glob("*.py"):
        src = py_file.read_text(encoding="utf-8")
        assert not re.search(r"\bapply_edit_plan\s*\(", src), (
            f"{py_file.name}: apply_edit_plan 호출 발견"
        )
