"""HWPX-RECOGNITION-OBJECT-IN-CELL-MAPPING-01 테스트.

read-only 매핑 검증. writer 호출 없음, output 생성 없음, 원본 무수정.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

NS_HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"

METADATA_FORM = PROJECT_ROOT / "tests/fixtures/hwpx/corpus/fx_metadata_form.hwpx"
NESTED_LEGAL = PROJECT_ROOT / "tests/fixtures/hwpx/corpus/fx_nested_legal_complex.hwpx"
STAMP_APPROVAL = PROJECT_ROOT / "tests/fixtures/hwpx/corpus/fx_stamp_approval_legal.hwpx"
GANTT_BASIC = PROJECT_ROOT / "tests/fixtures/hwpx/gantt/fx_gantt_like_basic.hwpx"


@pytest.fixture(scope="module")
def mapper():
    from hwpx.parser import object_cell_mapper as m
    return m


# ── 합성 XML ----------------------------------------------------------------

def _section_with(table_and_objects_xml: str) -> bytes:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<hp:sec xmlns:hp="{NS_HP}">
  {table_and_objects_xml}
</hp:sec>""".encode()


_EMPTY_SECTION = _section_with("")

_TABLE_ONLY = _section_with("""
  <hp:tbl id="t0">
    <hp:tr><hp:tc><hp:p><hp:run><hp:t>A</hp:t></hp:run></hp:p></hp:tc>
            <hp:tc><hp:p><hp:run><hp:t>B</hp:t></hp:run></hp:p></hp:tc></hp:tr>
    <hp:tr><hp:tc><hp:p><hp:run><hp:t>C</hp:t></hp:run></hp:p></hp:tc>
            <hp:tc><hp:p><hp:run><hp:t>D</hp:t></hp:run></hp:p></hp:tc></hp:tr>
  </hp:tbl>
""")

_ONE_OBJ_IN_CELL = _section_with("""
  <hp:tbl id="t0">
    <hp:tr><hp:tc><hp:p><hp:run><hp:t>Label</hp:t></hp:run></hp:p></hp:tc>
            <hp:tc><hp:p><hp:run>
                <hp:pic id="100">
                  <hp:offset x="10" y="20"/>
                  <hp:curSz width="300" height="400"/>
                </hp:pic>
            </hp:run></hp:p></hp:tc></hp:tr>
  </hp:tbl>
""")

_MULTI_OBJS_SAME_CELL = _section_with("""
  <hp:tbl id="t0">
    <hp:tr><hp:tc><hp:p><hp:run>
                <hp:rect id="200"><hp:curSz width="50" height="50"/></hp:rect>
                <hp:line id="201"><hp:curSz width="100" height="2"/></hp:line>
                <hp:ellipse id="202"><hp:curSz width="20" height="20"/></hp:ellipse>
            </hp:run></hp:p></hp:tc></hp:tr>
  </hp:tbl>
""")

_OBJS_IN_DIFFERENT_CELLS = _section_with("""
  <hp:tbl id="t0">
    <hp:tr>
      <hp:tc><hp:p><hp:run>
          <hp:pic id="300"><hp:curSz width="10" height="10"/></hp:pic>
      </hp:run></hp:p></hp:tc>
      <hp:tc><hp:p><hp:run>
          <hp:rect id="301"><hp:curSz width="20" height="20"/></hp:rect>
      </hp:run></hp:p></hp:tc>
    </hp:tr>
    <hp:tr>
      <hp:tc><hp:p><hp:run>
          <hp:line id="302"><hp:curSz width="30" height="2"/></hp:line>
      </hp:run></hp:p></hp:tc>
      <hp:tc><hp:p><hp:run><hp:t>plain</hp:t></hp:run></hp:p></hp:tc>
    </hp:tr>
  </hp:tbl>
""")

_OBJ_OUTSIDE_CELL = _section_with("""
  <hp:p><hp:run>
      <hp:pic id="500"><hp:curSz width="100" height="100"/></hp:pic>
  </hp:run></hp:p>
  <hp:tbl id="t0">
    <hp:tr><hp:tc><hp:p><hp:run><hp:t>X</hp:t></hp:run></hp:p></hp:tc></hp:tr>
  </hp:tbl>
""")

_SPAN_CELL = _section_with("""
  <hp:tbl id="t0">
    <hp:tr>
      <hp:tc>
          <hp:cellSpan colSpan="2" rowSpan="2"/>
          <hp:p><hp:run>
              <hp:pic id="700"><hp:curSz width="50" height="50"/></hp:pic>
          </hp:run></hp:p>
      </hp:tc>
    </hp:tr>
  </hp:tbl>
""")


# ── T01: 객체 없는 문서 (synthetic empty) ────────────────────────────────────

def test_no_objects_no_tables_returns_zero(mapper):
    r = mapper._map_from_section_xmls([_EMPTY_SECTION], document_hash="sha:empty")
    assert r.tableCount == 0
    assert r.cellCount == 0
    assert r.objectCount == 0
    assert r.mappedObjectCount == 0
    assert r.unmappedObjectCount == 0
    assert r.mappings == []


def test_no_objects_in_fixture_returns_zero(mapper):
    r = mapper.map_objects_to_cells(METADATA_FORM)
    assert r.objectCount == 0
    assert r.mappedObjectCount == 0
    assert r.unmappedObjectCount == 0
    assert r.mappings == []
    assert r.tableCount >= 1
    assert r.cellCount >= 1


# ── T02: 표만 있고 객체 없음 ─────────────────────────────────────────────────

def test_table_only_no_objects(mapper):
    r = mapper._map_from_section_xmls([_TABLE_ONLY], document_hash="sha:tab")
    assert r.tableCount == 1
    assert r.cellCount == 4
    assert r.objectCount == 0
    assert r.mappings == []


# ── T03: 셀 내부 객체 1개 매핑 ───────────────────────────────────────────────

def test_single_in_cell_object_maps_with_confidence_1(mapper):
    r = mapper._map_from_section_xmls([_ONE_OBJ_IN_CELL], document_hash="sha:one")
    assert r.objectCount == 1
    assert r.mappedObjectCount == 1
    assert r.unmappedObjectCount == 0
    m = r.mappings[0]
    assert m.objectType == "picture"
    assert m.confidence == 1.0
    assert m.reason == "DESCENDANT_OF_TC"
    assert m.tableIndex == 0
    assert m.rowIndex == 0
    assert m.cellIndex == 1
    assert m.cellKey == "t_s0_000:r0:c1"
    assert m.isImageLike is True


# ── T04: 한 셀 안에 여러 객체 ────────────────────────────────────────────────

def test_multiple_objects_same_cell_all_mapped_with_unique_keys(mapper):
    r = mapper._map_from_section_xmls([_MULTI_OBJS_SAME_CELL],
                                            document_hash="sha:multi")
    assert r.mappedObjectCount == 3
    cell_keys = {m.cellKey for m in r.mappings}
    assert cell_keys == {"t_s0_000:r0:c0"}
    obj_keys = [m.objectKey for m in r.mappings]
    assert len(obj_keys) == len(set(obj_keys)), "objectKey 중복"
    types = sorted(m.objectType for m in r.mappings)
    assert types == ["ellipse", "line", "rect"]


# ── T05: 여러 셀에 객체 분산 ─────────────────────────────────────────────────

def test_objects_in_different_cells(mapper):
    r = mapper._map_from_section_xmls([_OBJS_IN_DIFFERENT_CELLS],
                                            document_hash="sha:diff")
    assert r.mappedObjectCount == 3
    cell_to_type = {m.cellKey: m.objectType for m in r.mappings}
    assert cell_to_type["t_s0_000:r0:c0"] == "picture"
    assert cell_to_type["t_s0_000:r0:c1"] == "rect"
    assert cell_to_type["t_s0_000:r1:c0"] == "line"


# ── T06: 셀 외부 객체 ────────────────────────────────────────────────────────

def test_object_outside_any_cell_is_unmapped(mapper):
    r = mapper._map_from_section_xmls([_OBJ_OUTSIDE_CELL],
                                            document_hash="sha:out")
    assert r.unmappedObjectCount == 1
    assert r.mappedObjectCount == 0
    m = r.mappings[0]
    assert m.cellKey is None
    assert m.tableIndex is None
    assert m.confidence == 0.0
    assert m.reason == "OUT_OF_CELL"
    assert m.objectType == "picture"


def test_real_gantt_container_is_unmapped(mapper):
    """실제 gantt fixture: container가 페이지(섹션) 레벨에 있으므로 OUT_OF_CELL."""
    r = mapper.map_objects_to_cells(GANTT_BASIC)
    assert r.objectCount >= 1
    assert all(m.confidence in (0.0, 1.0) for m in r.mappings)
    # 적어도 1개는 OUT_OF_CELL이어야 한다 (gantt 컨테이너)
    assert any(m.reason == "OUT_OF_CELL" and m.confidence == 0.0
                for m in r.mappings)


# ── T07: rowSpan/colSpan 셀 ──────────────────────────────────────────────────

def test_rowspan_colspan_preserved(mapper):
    r = mapper._map_from_section_xmls([_SPAN_CELL], document_hash="sha:span")
    assert r.mappedObjectCount == 1
    m = r.mappings[0]
    assert m.rowSpan == 2
    assert m.colSpan == 2
    assert m.cellKey == "t_s0_000:r0:c0"


# ── T08: 객체 타입 분류 ──────────────────────────────────────────────────────

@pytest.mark.parametrize("tag,expected_type,expected_image_like", [
    ("pic", "picture", True),
    ("container", "container", True),
    ("rect", "rect", False),
    ("line", "line", False),
    ("ellipse", "ellipse", False),
    ("arc", "arc", False),
    ("curve", "curve", False),
    ("polygon", "polygon", False),
])
def test_object_type_classification(mapper, tag, expected_type, expected_image_like):
    section = _section_with(f"""
      <hp:tbl id="t0">
        <hp:tr><hp:tc><hp:p><hp:run>
            <hp:{tag} id="9"><hp:curSz width="10" height="10"/></hp:{tag}>
        </hp:run></hp:p></hp:tc></hp:tr>
      </hp:tbl>
    """)
    r = mapper._map_from_section_xmls([section], document_hash="sha:type")
    assert r.objectCount == 1
    m = r.mappings[0]
    assert m.objectType == expected_type
    assert m.objectRawTag == tag
    assert m.isImageLike is expected_image_like


# ── T09: 원본 SHA-256 / mtime 무변경 ────────────────────────────────────────

@pytest.mark.parametrize("fx", [METADATA_FORM, NESTED_LEGAL,
                                    STAMP_APPROVAL, GANTT_BASIC])
def test_source_file_not_modified(mapper, fx):
    sha_before = hashlib.sha256(fx.read_bytes()).hexdigest()
    mtime_before = fx.stat().st_mtime
    mapper.map_objects_to_cells(fx)
    assert hashlib.sha256(fx.read_bytes()).hexdigest() == sha_before
    assert fx.stat().st_mtime == mtime_before


def test_document_hash_equals_source_sha256(mapper):
    sha = hashlib.sha256(METADATA_FORM.read_bytes()).hexdigest()
    r = mapper.map_objects_to_cells(METADATA_FORM)
    assert r.documentHash == sha


# ── T10: writer 미호출 — recognition은 writer 모듈을 import하거나 호출하지 않음 ─

def test_writer_modules_not_invoked_during_mapping(mapper, monkeypatch):
    """live executor 호출 함수가 monkeypatch로 감시되어도 호출되지 않아야 한다."""
    from hwpx.pipeline import generic_edit_plan_writer_executor_live_sandbox as live
    call_log: list[str] = []
    monkeypatch.setattr(
        live, "execute_writer_call_plan_live_sandbox",
        lambda *a, **kw: call_log.append("live") or None,
    )
    mapper.map_objects_to_cells(METADATA_FORM)
    assert call_log == []


def test_no_output_files_created(mapper, tmp_path):
    before = sorted(p.name for p in tmp_path.iterdir())
    mapper.map_objects_to_cells(METADATA_FORM)
    after = sorted(p.name for p in tmp_path.iterdir())
    assert before == after


# ── T11: schema 필수 필드 ────────────────────────────────────────────────────

_REQUIRED_RESULT_KEYS = (
    "documentHash", "sourcePath", "tableCount", "cellCount",
    "objectCount", "mappedObjectCount", "unmappedObjectCount", "mappings",
)

_REQUIRED_ENTRY_KEYS = (
    "objectKey", "objectType", "objectRawTag", "sectionIndex",
    "tableIndex", "rowIndex", "cellIndex", "cellKey", "cellText",
    "rowSpan", "colSpan", "binDataRef", "confidence", "reason", "isImageLike",
)


def test_result_to_dict_has_required_keys(mapper):
    r = mapper.map_objects_to_cells(METADATA_FORM).to_dict()
    for k in _REQUIRED_RESULT_KEYS:
        assert k in r, f"missing top-level key: {k}"


def test_entry_to_dict_has_required_keys(mapper):
    r = mapper._map_from_section_xmls([_ONE_OBJ_IN_CELL], document_hash="sha")
    entry = r.mappings[0].to_dict()
    for k in _REQUIRED_ENTRY_KEYS:
        assert k in entry, f"missing entry key: {k}"


# ── T12: duplicate mapping 방지 ──────────────────────────────────────────────

def test_no_duplicate_object_keys(mapper):
    for fx in (METADATA_FORM, NESTED_LEGAL, STAMP_APPROVAL, GANTT_BASIC):
        r = mapper.map_objects_to_cells(fx)
        keys = [m.objectKey for m in r.mappings]
        assert len(keys) == len(set(keys)), f"duplicate keys in {fx.name}: {keys}"


def test_synthetic_duplicate_ids_resolved_uniquely(mapper):
    """같은 id 값을 가진 객체가 둘 있어도 objectKey는 고유해야 한다."""
    section = _section_with("""
      <hp:tbl id="t0">
        <hp:tr><hp:tc><hp:p><hp:run>
            <hp:rect id="9"><hp:curSz width="10" height="10"/></hp:rect>
            <hp:rect id="9"><hp:curSz width="20" height="20"/></hp:rect>
        </hp:run></hp:p></hp:tc></hp:tr>
      </hp:tbl>
    """)
    r = mapper._map_from_section_xmls([section], document_hash="sha")
    keys = [m.objectKey for m in r.mappings]
    assert len(keys) == 2
    assert len(set(keys)) == 2, f"duplicate keys: {keys}"
