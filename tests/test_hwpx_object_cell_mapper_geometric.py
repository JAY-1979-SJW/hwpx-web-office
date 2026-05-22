"""HWPX-RECOGNITION-OBJECT-CELL-GEOMETRIC-MAPPING-01 테스트.

좌표 기반 추론 candidate read-only 검증.
writer 호출 0, output 0, 원본 무수정.
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
GANTT_BASIC = PROJECT_ROOT / "tests/fixtures/hwpx/gantt/fx_gantt_like_basic.hwpx"


@pytest.fixture(scope="module")
def mapper():
    from hwpx.parser import object_cell_mapper as m
    return m


def _section_with(body: str) -> bytes:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<hp:sec xmlns:hp="{NS_HP}">
  {body}
</hp:sec>""".encode()


# ── 합성 시나리오 ─────────────────────────────────────────────────────────────

def _cell(text: str, x: int, y: int, w: int, h: int,
            col_span: int = 1, row_span: int = 1) -> str:
    span = (f'<hp:cellSpan colSpan="{col_span}" rowSpan="{row_span}"/>'
            if col_span > 1 or row_span > 1 else "")
    return (f'<hp:tc x="{x}" y="{y}" width="{w}" height="{h}">{span}'
            f'<hp:p><hp:run><hp:t>{text}</hp:t></hp:run></hp:p></hp:tc>')


def _row(*cells: str) -> str:
    return "<hp:tr>" + "".join(cells) + "</hp:tr>"


def _obj(tag: str, oid: str, x: int, y: int, w: int, h: int) -> str:
    return (f'<hp:{tag} id="{oid}">'
            f'<hp:offset x="{x}" y="{y}"/>'
            f'<hp:curSz width="{w}" height="{h}"/>'
            f'</hp:{tag}>')


# ── T01: XML ancestry 매핑은 회귀로 유지 ─────────────────────────────────────

def test_xml_ancestry_mapping_unaffected_by_geometric_layer(mapper):
    """XML descendant 매핑은 confidence=1.0 / reason=DESCENDANT_OF_TC 유지."""
    section = _section_with("""
      <hp:tbl id="t0">
        <hp:tr><hp:tc><hp:p><hp:run>
            <hp:pic id="100"><hp:offset x="0" y="0"/>
              <hp:curSz width="10" height="10"/></hp:pic>
        </hp:run></hp:p></hp:tc></hp:tr>
      </hp:tbl>
    """)
    r = mapper.map_objects_to_cells_with_geometry_from_section_xmls(
        [section], document_hash="sha")
    assert r.mappedObjectCount == 1
    m = r.mappings[0]
    assert m.confidence == 1.0
    assert m.reason == "DESCENDANT_OF_TC"
    # 이미 셀 내부 매핑된 객체는 geometric candidate에 포함되지 않는다
    assert all(g.objectKey != m.objectKey for g in r.geometricCandidates)


# ── T02: OUT_OF_CELL + 좌표 없음 → NO_GEOMETRY ───────────────────────────────

def test_out_of_cell_without_geometry_is_no_geometry(mapper):
    section = _section_with("""
      <hp:p><hp:run>
          <hp:pic id="500"/>
      </hp:run></hp:p>
      <hp:tbl id="t0">
        <hp:tr>%s</hp:tr>
      </hp:tbl>
    """ % _cell("A", 0, 0, 100, 50))
    r = mapper.map_objects_to_cells_with_geometry_from_section_xmls(
        [section], document_hash="sha")
    assert r.unmappedObjectCount == 1
    assert r.geometricCandidateCount == 1
    g = r.geometricCandidates[0]
    assert g.reason == "NO_GEOMETRY"
    assert g.confidence == 0.0
    assert g.candidateCellKey is None
    assert r.noGeometryObjectCount == 1


# ── T03: OUT_OF_CELL + 중심점이 셀 bbox 내부 → CENTER_INSIDE_CELL ────────────

def test_center_inside_cell_candidate(mapper):
    section = _section_with(
        # 객체 (offset=110,60, size=20x20 → 중심 120,70)
        _obj("pic", "600", 110, 60, 20, 20) +
        # 표: 한 셀 (0..200 x 0..100) — 객체 중심이 셀 내부
        f'<hp:tbl id="t0"><hp:tr>{_cell("A", 0, 0, 200, 100)}</hp:tr></hp:tbl>'
    )
    r = mapper.map_objects_to_cells_with_geometry_from_section_xmls(
        [section], document_hash="sha")
    assert r.unmappedObjectCount == 1
    assert r.geometricCandidateCount >= 1
    g = r.geometricCandidates[0]
    assert g.reason == "CENTER_INSIDE_CELL"
    assert 0.0 < g.confidence <= 0.8
    assert g.candidateCellKey == "t_s0_000:r0:c0"
    assert g.overlapRatio is not None and g.overlapRatio > 0
    assert g.ambiguous is False


# ── T04: BBOX overlap, 중심점은 셀 외부 → BBOX_OVERLAP, 순위 ─────────────────

def test_bbox_overlap_candidate_ranking(mapper):
    # 객체: x=80..160, y=0..50 (중심 120,25)
    # 셀1: 0..100 → overlap x=80..100 (20*50=1000)
    # 셀2: 100..200 → overlap x=100..160 (60*50=3000), 중심 x=120 in cell2
    # 중심이 셀2 내부면 CENTER_INSIDE_CELL. 중심이 어디에도 안 들어가는 경우를 위해
    # 객체를 두 셀에 걸치되 중심을 셀 사이 경계 위에 두지 않고, 셀과 객체의 위치를
    # 조정하여 중심이 어느 셀에도 안 들어가게 한다.
    # 예: 셀 둘 다 y=100..200, 객체 y=0..50 → 객체 중심 y=25, 셀 y=100..200이므로
    # 어느 셀도 중심을 포함하지 않음. overlap도 0 → NEAREST_CELL이 된다.
    # 따라서 overlap 시나리오는 셀과 객체가 같은 y범위에 걸치게 한다.
    # 셀1 y=0..50, 셀2 y=0..50, 객체 y=0..50, 객체 x중심을 두 셀 모두의 경계 바깥에 두기 위해
    # 객체 가운데가 정확히 셀 경계 위(x=100)면 두 셀 모두 _center_inside는 True (≤ 비교).
    # → 두 cell 모두 inside hit로 보고 ambiguous로 가는 케이스.
    # 별도 BBOX_OVERLAP 테스트: 중심이 셀 외부이지만 일부 영역 overlap만 발생하는 케이스
    # 셀 1: 0..100 x 0..50, 셀 2: 200..300 x 0..50
    # 객체: x=80..220, y=0..50 (중심 150,25 — 두 셀 사이 갭 위치)
    section = _section_with(
        _obj("pic", "700", 80, 0, 140, 50) +
        f'<hp:tbl id="t0"><hp:tr>'
        f'{_cell("A", 0, 0, 100, 50)}'
        f'{_cell("B", 200, 0, 100, 50)}'
        f'</hp:tr></hp:tbl>'
    )
    r = mapper.map_objects_to_cells_with_geometry_from_section_xmls(
        [section], document_hash="sha")
    # 중심 (150, 25)는 두 셀 모두 외부 (셀1 x=0..100, 셀2 x=200..300)
    # 따라서 BBOX_OVERLAP 후보 2건
    reasons = {g.reason for g in r.geometricCandidates}
    assert "BBOX_OVERLAP" in reasons
    overlap_entries = [g for g in r.geometricCandidates if g.reason == "BBOX_OVERLAP"]
    assert len(overlap_entries) >= 2
    # confidence 모두 0.8 이하
    for g in overlap_entries:
        assert 0.0 < g.confidence <= 0.8
    # 두 셀 overlap 면적이 동일 (각각 1000) → ambiguous=true
    assert any(g.ambiguous for g in overlap_entries)


# ── T05: NEAREST_CELL (overlap 없고 가까운 셀) ───────────────────────────────

def test_nearest_cell_candidate_low_confidence(mapper):
    # 셀 0..50 x 0..50, 객체 x=200..220, y=200..220 (멀리 떨어짐)
    section = _section_with(
        _obj("pic", "800", 200, 200, 20, 20) +
        f'<hp:tbl id="t0"><hp:tr>{_cell("A", 0, 0, 50, 50)}</hp:tr></hp:tbl>'
    )
    r = mapper.map_objects_to_cells_with_geometry_from_section_xmls(
        [section], document_hash="sha")
    cands = r.geometricCandidates
    assert len(cands) == 1
    g = cands[0]
    assert g.reason == "NEAREST_CELL"
    assert g.confidence <= 0.6
    assert g.candidateCellKey == "t_s0_000:r0:c0"
    assert g.overlapRatio == 0.0
    assert g.centerDistance is not None and g.centerDistance > 0
    assert g.ambiguous is False


# ── T06: ambiguous (두 셀 동일 점수) ─────────────────────────────────────────

def test_ambiguous_candidate_does_not_promote(mapper):
    # 객체 중심이 셀1과 셀2 둘 다 포함되는 정확한 경계
    # 두 셀: 0..100 x 0..50, 100..200 x 0..50, 객체 x=50..150 y=0..50 (중심 100,25)
    section = _section_with(
        _obj("pic", "900", 50, 0, 100, 50) +
        f'<hp:tbl id="t0"><hp:tr>'
        f'{_cell("A", 0, 0, 100, 50)}'
        f'{_cell("B", 100, 0, 100, 50)}'
        f'</hp:tr></hp:tbl>'
    )
    r = mapper.map_objects_to_cells_with_geometry_from_section_xmls(
        [section], document_hash="sha")
    cands = r.geometricCandidates
    # 중심점 (100,25)이 두 셀 경계 (x<=100, x>=100) 모두에 inside True (포함 비교)
    assert len(cands) >= 2
    assert all(c.reason == "CENTER_INSIDE_CELL" for c in cands)
    assert any(c.ambiguous for c in cands)
    assert r.ambiguousCandidateCount >= 1
    # 단일 확정 mapping으로 승격되지 않는다 — mappings[]는 그대로 OUT_OF_CELL 1건
    out_count = sum(1 for m in r.mappings if m.reason == "OUT_OF_CELL")
    assert out_count == 1


# ── T07: rowSpan/colSpan geometry ────────────────────────────────────────────

def test_merged_cell_geometry_preserved(mapper):
    # rowSpan=2 colSpan=2 셀, bbox 0..200 x 0..100
    section = _section_with(
        _obj("pic", "1000", 50, 30, 20, 20) +  # 중심 (60,40) — 셀 내부
        f'<hp:tbl id="t0"><hp:tr>'
        f'{_cell("Merged", 0, 0, 200, 100, col_span=2, row_span=2)}'
        f'</hp:tr></hp:tbl>'
    )
    r = mapper.map_objects_to_cells_with_geometry_from_section_xmls(
        [section], document_hash="sha")
    # 매핑 자체는 OUT_OF_CELL (객체가 셀 ancestor가 아님)
    # geometric candidate는 CENTER_INSIDE_CELL로 위 셀에 매핑돼야 함
    cands = r.geometricCandidates
    assert len(cands) >= 1
    g = cands[0]
    assert g.reason == "CENTER_INSIDE_CELL"
    assert g.candidateCellKey == "t_s0_000:r0:c0"


# ── T08: coordinateUnit 필드 ─────────────────────────────────────────────────

def test_coordinate_unit_populated_when_geometry_present(mapper):
    section = _section_with(
        _obj("pic", "100", 0, 0, 10, 10) +
        f'<hp:tbl id="t0"><hp:tr>{_cell("A", 0, 0, 50, 50)}</hp:tr></hp:tbl>'
    )
    r = mapper.map_objects_to_cells_with_geometry_from_section_xmls(
        [section], document_hash="sha")
    assert r.coordinateUnit == "HWPX_UNIT"


def test_coordinate_unit_unknown_when_no_geometry(mapper):
    section = _section_with("""
      <hp:p><hp:run><hp:pic id="x"/></hp:run></hp:p>
    """)
    r = mapper.map_objects_to_cells_with_geometry_from_section_xmls(
        [section], document_hash="sha")
    assert r.coordinateUnit == "UNKNOWN"


# ── T09: schema 안정성 ──────────────────────────────────────────────────────

_REQUIRED_TOP_KEYS = (
    "documentHash", "sourcePath", "tableCount", "cellCount",
    "objectCount", "mappedObjectCount", "unmappedObjectCount", "mappings",
    "geometricCandidates", "geometricCandidateCount",
    "geometricMappedCandidateCount", "ambiguousCandidateCount",
    "noGeometryObjectCount", "coordinateUnit",
)

_REQUIRED_CAND_KEYS = (
    "objectKey", "objectType", "candidateCellKey",
    "tableIndex", "rowIndex", "cellIndex", "cellText",
    "overlapRatio", "centerDistance", "confidence", "reason", "ambiguous",
)


def test_top_level_schema_keys(mapper):
    section = _section_with(
        _obj("pic", "1", 10, 10, 5, 5) +
        f'<hp:tbl id="t"><hp:tr>{_cell("A", 0, 0, 50, 50)}</hp:tr></hp:tbl>'
    )
    d = mapper.map_objects_to_cells_with_geometry_from_section_xmls(
        [section], document_hash="sha").to_dict()
    for k in _REQUIRED_TOP_KEYS:
        assert k in d, f"missing top-level key: {k}"


def test_candidate_entry_schema_keys(mapper):
    section = _section_with(
        _obj("pic", "1", 10, 10, 5, 5) +
        f'<hp:tbl id="t"><hp:tr>{_cell("A", 0, 0, 50, 50)}</hp:tr></hp:tbl>'
    )
    r = mapper.map_objects_to_cells_with_geometry_from_section_xmls(
        [section], document_hash="sha")
    entry = r.geometricCandidates[0].to_dict()
    for k in _REQUIRED_CAND_KEYS:
        assert k in entry, f"missing candidate key: {k}"


# ── T10: duplicate candidate 방지 ───────────────────────────────────────────

def test_no_duplicate_candidate_pairs(mapper):
    # 동일 객체에 대해 같은 cellKey가 2회 이상 나오지 않는다
    section = _section_with(
        _obj("pic", "1", 50, 0, 100, 50) +
        f'<hp:tbl id="t0"><hp:tr>'
        f'{_cell("A", 0, 0, 100, 50)}'
        f'{_cell("B", 100, 0, 100, 50)}'
        f'</hp:tr></hp:tbl>'
    )
    r = mapper.map_objects_to_cells_with_geometry_from_section_xmls(
        [section], document_hash="sha")
    pairs = [(g.objectKey, g.candidateCellKey) for g in r.geometricCandidates]
    assert len(pairs) == len(set(pairs)), f"duplicate pairs: {pairs}"


# ── T11: 원본 SHA-256 / mtime 무변경 ────────────────────────────────────────

@pytest.mark.parametrize("fx", [METADATA_FORM, GANTT_BASIC])
def test_source_not_modified(mapper, fx):
    sha_before = hashlib.sha256(fx.read_bytes()).hexdigest()
    mtime_before = fx.stat().st_mtime
    mapper.map_objects_to_cells_with_geometry(fx)
    assert hashlib.sha256(fx.read_bytes()).hexdigest() == sha_before
    assert fx.stat().st_mtime == mtime_before


# ── T12: writer 미호출 ──────────────────────────────────────────────────────

def test_writer_not_invoked(mapper, monkeypatch):
    from hwpx.pipeline import generic_edit_plan_writer_executor_live_sandbox as live
    call_log: list = []
    monkeypatch.setattr(live, "execute_writer_call_plan_live_sandbox",
                          lambda *a, **k: call_log.append("live"))
    mapper.map_objects_to_cells_with_geometry(METADATA_FORM)
    assert call_log == []


# ── T13: output 미생성 ──────────────────────────────────────────────────────

def test_no_output_files_created(mapper, tmp_path):
    before = sorted(p.name for p in tmp_path.iterdir())
    mapper.map_objects_to_cells_with_geometry(METADATA_FORM)
    after = sorted(p.name for p in tmp_path.iterdir())
    assert before == after


# ── T14: 실제 fixture 회귀 ──────────────────────────────────────────────────

def test_real_gantt_container_geometric_candidate_path(mapper):
    """gantt_basic container: 객체에 bbox는 있으나 셀에는 bbox가 없으므로 NO_CELL_GEOMETRY."""
    r = mapper.map_objects_to_cells_with_geometry(GANTT_BASIC)
    # XML ancestry는 OUT_OF_CELL 그대로
    assert r.unmappedObjectCount >= 1
    # 셀 bbox가 전혀 없으므로 모든 geometric candidate는 NO_*
    for g in r.geometricCandidates:
        assert g.confidence == 0.0
        assert g.reason in ("NO_GEOMETRY", "NO_CELL_GEOMETRY")


def test_real_metadata_form_has_no_geometric_candidates(mapper):
    """metadata_form은 객체가 없으므로 geometricCandidates도 비어 있다."""
    r = mapper.map_objects_to_cells_with_geometry(METADATA_FORM)
    assert r.objectCount == 0
    assert r.geometricCandidateCount == 0
    assert r.geometricCandidates == []


# ── T15: confidence < 1.0 (XML 외 경로) ────────────────────────────────────

def test_all_geometric_confidences_below_one(mapper):
    """geometric candidate는 절대 confidence=1.0을 갖지 않는다 (ancestry 매핑은 제외)."""
    section = _section_with(
        _obj("pic", "1", 10, 10, 5, 5) +
        f'<hp:tbl id="t"><hp:tr>{_cell("A", 0, 0, 50, 50)}</hp:tr></hp:tbl>'
    )
    r = mapper.map_objects_to_cells_with_geometry_from_section_xmls(
        [section], document_hash="sha")
    assert r.geometricCandidateCount >= 1
    for g in r.geometricCandidates:
        assert g.confidence < 1.0
