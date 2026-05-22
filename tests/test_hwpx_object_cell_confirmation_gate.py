"""HWPX-RECOGNITION-OBJECT-CELL-GEOMETRIC-CONFIRMATION-GATE-01 테스트.

read-only confirmation gate 검증. writer 호출 0, output 0, 원본 무수정.
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


@pytest.fixture(scope="module")
def gate():
    from hwpx.parser import object_cell_confirmation_gate as g
    return g


def _section_with(body: str) -> bytes:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<hp:sec xmlns:hp="{NS_HP}">
  {body}
</hp:sec>""".encode()


def _cell(text: str, x: int, y: int, w: int, h: int) -> str:
    return (f'<hp:tc x="{x}" y="{y}" width="{w}" height="{h}">'
            f'<hp:p><hp:run><hp:t>{text}</hp:t></hp:run></hp:p></hp:tc>')


def _obj(tag: str, oid: str, x: int, y: int, w: int, h: int) -> str:
    return (f'<hp:{tag} id="{oid}">'
            f'<hp:offset x="{x}" y="{y}"/>'
            f'<hp:curSz width="{w}" height="{h}"/>'
            f'</hp:{tag}>')


def _decision(object_key, candidate_cell_key, decision,
                  reviewer="manual", reason="user confirm"):
    return {
        "objectKey": object_key,
        "candidateCellKey": candidate_cell_key,
        "decision": decision,
        "reviewer": reviewer,
        "reason": reason,
    }


def _build_center_inside_scenario(mapper):
    """객체 중심이 셀 내부 → CENTER_INSIDE_CELL candidate 1건."""
    section = _section_with(
        _obj("pic", "C1", 110, 60, 20, 20) +
        f'<hp:tbl id="t0"><hp:tr>{_cell("A", 0, 0, 200, 100)}</hp:tr></hp:tbl>'
    )
    return mapper.map_objects_to_cells_with_geometry_from_section_xmls(
        [section], document_hash="sha")


def _build_bbox_overlap_scenario(mapper):
    """객체가 두 셀 모두에 BBOX_OVERLAP → ambiguous 후보."""
    section = _section_with(
        _obj("pic", "O1", 80, 0, 140, 50) +
        f'<hp:tbl id="t0"><hp:tr>'
        f'{_cell("A", 0, 0, 100, 50)}'
        f'{_cell("B", 200, 0, 100, 50)}'
        f'</hp:tr></hp:tbl>'
    )
    return mapper.map_objects_to_cells_with_geometry_from_section_xmls(
        [section], document_hash="sha")


def _build_nearest_scenario(mapper):
    """객체가 모든 셀과 overlap=0, NEAREST_CELL 1건."""
    section = _section_with(
        _obj("pic", "N1", 200, 200, 20, 20) +
        f'<hp:tbl id="t0"><hp:tr>{_cell("A", 0, 0, 50, 50)}</hp:tr></hp:tbl>'
    )
    return mapper.map_objects_to_cells_with_geometry_from_section_xmls(
        [section], document_hash="sha")


def _build_no_geometry_scenario(mapper):
    section = _section_with(
        '<hp:p><hp:run><hp:pic id="P1"/></hp:run></hp:p>'
        f'<hp:tbl id="t0"><hp:tr>{_cell("A", 0, 0, 50, 50)}</hp:tr></hp:tbl>'
    )
    return mapper.map_objects_to_cells_with_geometry_from_section_xmls(
        [section], document_hash="sha")


def _build_no_cell_geometry_scenario(mapper):
    """객체에 bbox는 있으나 셀에 bbox가 전혀 없음."""
    section = _section_with(
        _obj("pic", "P2", 10, 10, 5, 5) +
        '<hp:tbl id="t0"><hp:tr><hp:tc><hp:p><hp:run>'
        '<hp:t>A</hp:t></hp:run></hp:p></hp:tc></hp:tr></hp:tbl>'
    )
    return mapper.map_objects_to_cells_with_geometry_from_section_xmls(
        [section], document_hash="sha")


def _build_in_cell_xml_ancestry_scenario(mapper):
    """DESCENDANT_OF_TC + 추가 OUT_OF_CELL 객체로 보호 시나리오."""
    section = _section_with(
        # XML ancestry로 매핑되는 셀 내 객체
        '<hp:tbl id="t0"><hp:tr><hp:tc x="0" y="0" width="200" height="100">'
        '<hp:p><hp:run>'
        '<hp:pic id="IN"><hp:offset x="50" y="40"/><hp:curSz width="10" height="10"/></hp:pic>'
        '</hp:run></hp:p></hp:tc></hp:tr></hp:tbl>'
    )
    return mapper.map_objects_to_cells_with_geometry_from_section_xmls(
        [section], document_hash="sha")


# ── T01: CENTER_INSIDE_CELL + APPROVE → 승격 ─────────────────────────────────

def test_approve_center_inside_cell_promotes(mapper, gate):
    r = _build_center_inside_scenario(mapper)
    cand = r.geometricCandidates[0]
    decisions = [_decision(cand.objectKey, cand.candidateCellKey, "APPROVE")]
    out = gate.apply_geometric_confirmation(r, decisions)
    assert out.confirmedMappingCount == 1
    assert out.blockedConfirmationCount == 0
    # 새 mapping이 추가됨
    promoted = [m for m in out.mappings if m.reason == "CONFIRMED_CENTER_INSIDE_CELL"]
    assert len(promoted) == 1
    p = promoted[0]
    assert p.objectKey == cand.objectKey
    assert p.cellKey == cand.candidateCellKey
    assert p.confidence == cand.confidence
    assert p.confidence < 1.0
    # confirmationResults
    assert any(c.status == "CONFIRMED" and c.promoted
                for c in out.confirmationResults)


# ── T02: BBOX_OVERLAP + APPROVE → 승격 (단, ambiguous=False만) ───────────────

def test_approve_bbox_overlap_non_ambiguous_promotes(mapper, gate):
    # BBOX_OVERLAP에서 한 셀만 더 큰 overlap을 갖도록 시나리오 변경
    # 객체 80..220 x 0..50, 셀1 0..100 x 0..50 (overlap=1000), 셀2 200..400 x 0..50 (overlap=1000)
    # 동일 overlap이면 ambiguous. 다른 overlap을 만들기 위해 셀2 면적을 다르게:
    section = _section_with(
        _obj("pic", "O1", 80, 0, 140, 50) +
        f'<hp:tbl id="t0"><hp:tr>'
        f'{_cell("A", 0, 0, 100, 50)}'   # overlap = (100-80)*50 = 1000
        f'{_cell("B", 210, 0, 100, 50)}'  # overlap = (220-210)*50 = 500
        f'</hp:tr></hp:tbl>'
    )
    r = mapper.map_objects_to_cells_with_geometry_from_section_xmls(
        [section], document_hash="sha")
    # BBOX_OVERLAP candidates 2건, ambiguous=False (점수 차이 >= 0.05)
    overlap_cands = [c for c in r.geometricCandidates if c.reason == "BBOX_OVERLAP"]
    assert len(overlap_cands) == 2
    non_ambiguous = [c for c in overlap_cands if not c.ambiguous]
    assert len(non_ambiguous) >= 1
    # 가장 큰 overlap을 가진 후보를 APPROVE
    top = max(non_ambiguous, key=lambda c: c.overlapRatio or 0)
    out = gate.apply_geometric_confirmation(r, [
        _decision(top.objectKey, top.candidateCellKey, "APPROVE")
    ])
    assert out.confirmedMappingCount == 1
    promoted = [m for m in out.mappings if m.reason == "CONFIRMED_BBOX_OVERLAP"]
    assert len(promoted) == 1
    assert promoted[0].confidence < 1.0


# ── T03: NEAREST_CELL + APPROVE → 승격, confidence ≤ 0.6 ─────────────────────

def test_approve_nearest_cell_promotes_low_confidence(mapper, gate):
    r = _build_nearest_scenario(mapper)
    cand = r.geometricCandidates[0]
    assert cand.reason == "NEAREST_CELL"
    out = gate.apply_geometric_confirmation(r, [
        _decision(cand.objectKey, cand.candidateCellKey, "APPROVE")
    ])
    assert out.confirmedMappingCount == 1
    promoted = [m for m in out.mappings if m.reason == "CONFIRMED_NEAREST_CELL"]
    assert len(promoted) == 1
    assert promoted[0].confidence <= 0.6
    assert promoted[0].confidence < 1.0


# ── T04: ambiguous APPROVE → BLOCKED ─────────────────────────────────────────

def test_approve_ambiguous_is_blocked(mapper, gate):
    r = _build_bbox_overlap_scenario(mapper)
    amb = next(c for c in r.geometricCandidates if c.ambiguous)
    out = gate.apply_geometric_confirmation(r, [
        _decision(amb.objectKey, amb.candidateCellKey, "APPROVE")
    ])
    assert out.confirmedMappingCount == 0
    assert out.blockedConfirmationCount == 1
    res = out.confirmationResults[0]
    assert res.status == "BLOCKED"
    assert res.blockedReason == "AMBIGUOUS_CANDIDATE"
    assert res.promoted is False
    # mappings에 CONFIRMED 항목 없음
    assert not any(m.reason.startswith("CONFIRMED_") for m in out.mappings)


# ── T05: NO_GEOMETRY APPROVE → BLOCKED ──────────────────────────────────────

def test_approve_no_geometry_is_blocked(mapper, gate):
    r = _build_no_geometry_scenario(mapper)
    cand = r.geometricCandidates[0]
    assert cand.reason == "NO_GEOMETRY"
    out = gate.apply_geometric_confirmation(r, [
        _decision(cand.objectKey, cand.candidateCellKey, "APPROVE")
    ])
    assert out.confirmedMappingCount == 0
    res = out.confirmationResults[0]
    assert res.status == "BLOCKED"
    assert res.blockedReason == "NO_GEOMETRY"


# ── T06: NO_CELL_GEOMETRY APPROVE → BLOCKED ─────────────────────────────────

def test_approve_no_cell_geometry_is_blocked(mapper, gate):
    r = _build_no_cell_geometry_scenario(mapper)
    cand = r.geometricCandidates[0]
    assert cand.reason == "NO_CELL_GEOMETRY"
    out = gate.apply_geometric_confirmation(r, [
        _decision(cand.objectKey, cand.candidateCellKey, "APPROVE")
    ])
    assert out.confirmedMappingCount == 0
    res = out.confirmationResults[0]
    assert res.status == "BLOCKED"
    assert res.blockedReason == "NO_CELL_GEOMETRY"


# ── T07: REJECT ─────────────────────────────────────────────────────────────

def test_reject_decision_not_promoted(mapper, gate):
    r = _build_center_inside_scenario(mapper)
    cand = r.geometricCandidates[0]
    out = gate.apply_geometric_confirmation(r, [
        _decision(cand.objectKey, cand.candidateCellKey, "REJECT")
    ])
    assert out.rejectedCandidateCount == 1
    assert out.confirmedMappingCount == 0
    assert not any(m.reason.startswith("CONFIRMED_") for m in out.mappings)
    # 원 candidate는 보존
    assert any(c.objectKey == cand.objectKey for c in out.geometricCandidates)


# ── T08: HOLD ───────────────────────────────────────────────────────────────

def test_hold_decision_not_promoted(mapper, gate):
    r = _build_center_inside_scenario(mapper)
    cand = r.geometricCandidates[0]
    out = gate.apply_geometric_confirmation(r, [
        _decision(cand.objectKey, cand.candidateCellKey, "HOLD")
    ])
    assert out.heldCandidateCount == 1
    assert out.confirmedMappingCount == 0
    assert not any(m.reason.startswith("CONFIRMED_") for m in out.mappings)


# ── T09: candidate not found → BLOCKED ──────────────────────────────────────

def test_unknown_candidate_blocked(mapper, gate):
    r = _build_center_inside_scenario(mapper)
    out = gate.apply_geometric_confirmation(r, [
        _decision("obj:does-not-exist", "t_s0_000:r0:c0", "APPROVE")
    ])
    assert out.confirmedMappingCount == 0
    res = out.confirmationResults[0]
    assert res.status == "BLOCKED"
    assert res.blockedReason == "CANDIDATE_NOT_FOUND"


# ── T10: invalid decision → BLOCKED_INVALID_DECISION ────────────────────────

def test_invalid_decision_value_blocked(mapper, gate):
    r = _build_center_inside_scenario(mapper)
    cand = r.geometricCandidates[0]
    out = gate.apply_geometric_confirmation(r, [
        _decision(cand.objectKey, cand.candidateCellKey, "MAYBE")
    ])
    assert out.confirmedMappingCount == 0
    res = out.confirmationResults[0]
    assert res.status == "BLOCKED"
    assert res.blockedReason == "INVALID_DECISION"


def test_missing_required_field_blocked(mapper, gate):
    r = _build_center_inside_scenario(mapper)
    bad = {"objectKey": "x", "decision": "APPROVE"}  # candidateCellKey 누락
    out = gate.apply_geometric_confirmation(r, [bad])
    assert out.blockedConfirmationCount == 1
    assert out.confirmationResults[0].blockedReason == "INVALID_DECISION"


# ── T11: 동일 objectKey 다중 APPROVE → BLOCKED ──────────────────────────────

def test_duplicate_approvals_for_same_object_blocked(mapper, gate):
    # 한 객체에 후보가 둘인 시나리오 생성: 두 셀 모두에 BBOX_OVERLAP (overlap 다름)
    section = _section_with(
        _obj("pic", "O1", 80, 0, 140, 50) +
        f'<hp:tbl id="t0"><hp:tr>'
        f'{_cell("A", 0, 0, 100, 50)}'
        f'{_cell("B", 210, 0, 100, 50)}'
        f'</hp:tr></hp:tbl>'
    )
    r = mapper.map_objects_to_cells_with_geometry_from_section_xmls(
        [section], document_hash="sha")
    overlap_cands = [c for c in r.geometricCandidates if c.reason == "BBOX_OVERLAP"]
    assert len(overlap_cands) == 2
    decisions = [
        _decision(overlap_cands[0].objectKey, overlap_cands[0].candidateCellKey, "APPROVE"),
        _decision(overlap_cands[1].objectKey, overlap_cands[1].candidateCellKey, "APPROVE"),
    ]
    out = gate.apply_geometric_confirmation(r, decisions)
    assert out.confirmedMappingCount == 0
    assert out.blockedConfirmationCount == 2
    reasons = [c.blockedReason for c in out.confirmationResults]
    assert reasons.count("DUPLICATE_APPROVAL_FOR_OBJECT") == 2


# ── T12: 이미 DESCENDANT_OF_TC인 객체에 geometric APPROVE → BLOCKED ─────────

def test_already_descendant_mapped_object_blocked(mapper, gate):
    r = _build_in_cell_xml_ancestry_scenario(mapper)
    # 이 시나리오에는 OUT_OF_CELL 객체가 없을 수도 있다. 위조 candidate를 추가해서 보호 동작 확인
    from hwpx.parser.object_cell_mapper import GeometricCandidateEntry
    in_cell_obj = next(m for m in r.mappings if m.reason == "DESCENDANT_OF_TC")
    # 같은 objectKey로 가짜 geometric candidate 주입
    fake_cand = GeometricCandidateEntry(
        objectKey=in_cell_obj.objectKey, objectType=in_cell_obj.objectType,
        candidateCellKey="t_s0_000:r0:c0", tableIndex=0, rowIndex=0, cellIndex=0,
        cellText="A", overlapRatio=0.5, centerDistance=0.0,
        confidence=0.7, reason="CENTER_INSIDE_CELL", ambiguous=False,
    )
    r.geometricCandidates.append(fake_cand)
    out = gate.apply_geometric_confirmation(r, [
        _decision(in_cell_obj.objectKey, "t_s0_000:r0:c0", "APPROVE")
    ])
    assert out.confirmedMappingCount == 0
    res = out.confirmationResults[0]
    assert res.status == "BLOCKED"
    assert res.blockedReason == "ALREADY_MAPPED_BY_XML_ANCESTRY"
    # 기존 DESCENDANT_OF_TC mapping은 변경되지 않음
    assert any(m.reason == "DESCENDANT_OF_TC" and m.objectKey == in_cell_obj.objectKey
                for m in out.mappings)


# ── T13: 승격된 mapping entry schema 15키 보존 ───────────────────────────────

_REQUIRED_ENTRY_KEYS = (
    "objectKey", "objectType", "objectRawTag", "sectionIndex",
    "tableIndex", "rowIndex", "cellIndex", "cellKey", "cellText",
    "rowSpan", "colSpan", "binDataRef", "confidence", "reason", "isImageLike",
)


def test_promoted_mapping_entry_schema(mapper, gate):
    r = _build_center_inside_scenario(mapper)
    cand = r.geometricCandidates[0]
    out = gate.apply_geometric_confirmation(r, [
        _decision(cand.objectKey, cand.candidateCellKey, "APPROVE")
    ])
    promoted = next(m for m in out.mappings if m.reason == "CONFIRMED_CENTER_INSIDE_CELL")
    d = promoted.to_dict()
    for k in _REQUIRED_ENTRY_KEYS:
        assert k in d, f"missing key {k} in promoted entry"


# ── T14: confirmationResults entry schema ───────────────────────────────────

_REQUIRED_CONF_KEYS = (
    "objectKey", "candidateCellKey", "decision", "status",
    "reason", "promoted", "blockedReason",
)

_REQUIRED_TOP_KEYS_AFTER_CONFIRM = (
    "confirmationApplied", "confirmationDecisionCount", "confirmedMappingCount",
    "rejectedCandidateCount", "heldCandidateCount", "blockedConfirmationCount",
    "confirmationResults",
)


def test_confirmation_result_schema(mapper, gate):
    r = _build_center_inside_scenario(mapper)
    cand = r.geometricCandidates[0]
    out = gate.apply_geometric_confirmation(r, [
        _decision(cand.objectKey, cand.candidateCellKey, "APPROVE")
    ])
    d = out.to_dict()
    for k in _REQUIRED_TOP_KEYS_AFTER_CONFIRM:
        assert k in d
    entry = d["confirmationResults"][0]
    for k in _REQUIRED_CONF_KEYS:
        assert k in entry


# ── T15: 원본 fixture sha256 / mtime 무변경 ─────────────────────────────────

@pytest.mark.parametrize("fx", [METADATA_FORM, GANTT_BASIC])
def test_source_fixture_unchanged(mapper, gate, fx):
    sha_before = hashlib.sha256(fx.read_bytes()).hexdigest()
    mtime_before = fx.stat().st_mtime
    r = mapper.map_objects_to_cells_with_geometry(fx)
    # 임의 decision 적용 (대부분 BLOCKED될 것)
    decisions = [
        _decision(c.objectKey, c.candidateCellKey, "APPROVE")
        for c in r.geometricCandidates
    ]
    gate.apply_geometric_confirmation(r, decisions)
    assert hashlib.sha256(fx.read_bytes()).hexdigest() == sha_before
    assert fx.stat().st_mtime == mtime_before


# ── T16: writer 미호출 ──────────────────────────────────────────────────────

def test_writer_not_invoked(mapper, gate, monkeypatch):
    from hwpx.pipeline import generic_edit_plan_writer_executor_live_sandbox as live
    call_log: list = []
    monkeypatch.setattr(
        live, "execute_writer_call_plan_live_sandbox",
        lambda *a, **k: call_log.append("live"),
    )
    r = _build_center_inside_scenario(mapper)
    cand = r.geometricCandidates[0]
    gate.apply_geometric_confirmation(r, [
        _decision(cand.objectKey, cand.candidateCellKey, "APPROVE")
    ])
    assert call_log == []


# ── T17: output 파일 미생성 ──────────────────────────────────────────────────

def test_no_output_files_created(mapper, gate, tmp_path):
    before = sorted(p.name for p in tmp_path.iterdir())
    r = _build_center_inside_scenario(mapper)
    cand = r.geometricCandidates[0]
    gate.apply_geometric_confirmation(r, [
        _decision(cand.objectKey, cand.candidateCellKey, "APPROVE")
    ])
    assert sorted(p.name for p in tmp_path.iterdir()) == before


# ── T18: 입력 result는 mutate되지 않는다 ────────────────────────────────────

def test_input_result_is_not_mutated(mapper, gate):
    r = _build_center_inside_scenario(mapper)
    cand = r.geometricCandidates[0]
    original_mappings_len = len(r.mappings)
    original_candidate_count = r.geometricCandidateCount
    gate.apply_geometric_confirmation(r, [
        _decision(cand.objectKey, cand.candidateCellKey, "APPROVE")
    ])
    # 원본 result는 그대로
    assert len(r.mappings) == original_mappings_len
    assert r.geometricCandidateCount == original_candidate_count
    assert r.confirmationApplied is False
    assert r.confirmedMappingCount == 0


# ── T19: confirmed mapping confidence는 1.0이 되면 안 된다 ──────────────────

def test_confirmed_confidence_never_one(mapper, gate):
    r = _build_center_inside_scenario(mapper)
    cand = r.geometricCandidates[0]
    out = gate.apply_geometric_confirmation(r, [
        _decision(cand.objectKey, cand.candidateCellKey, "APPROVE")
    ])
    for m in out.mappings:
        if m.reason.startswith("CONFIRMED_"):
            assert m.confidence < 1.0


# ── T20: DESCENDANT_OF_TC mapping은 게이트 이후에도 보존 ────────────────────

def test_descendant_of_tc_preserved_after_gate(mapper, gate):
    r = _build_in_cell_xml_ancestry_scenario(mapper)
    descendant_count_before = sum(
        1 for m in r.mappings if m.reason == "DESCENDANT_OF_TC"
    )
    assert descendant_count_before >= 1
    out = gate.apply_geometric_confirmation(r, [])
    descendant_count_after = sum(
        1 for m in out.mappings if m.reason == "DESCENDANT_OF_TC"
    )
    assert descendant_count_after == descendant_count_before


# ── T21: 빈 decisions 리스트는 noop (confirmationApplied=True, 0 counts) ────

def test_empty_decisions_is_noop(mapper, gate):
    r = _build_center_inside_scenario(mapper)
    out = gate.apply_geometric_confirmation(r, [])
    assert out.confirmationApplied is True
    assert out.confirmationDecisionCount == 0
    assert out.confirmedMappingCount == 0
    assert out.rejectedCandidateCount == 0
    assert out.heldCandidateCount == 0
    assert out.blockedConfirmationCount == 0
    # mappings는 원래 그대로 (DESCENDANT_OF_TC만 또는 없음)
    assert all(not m.reason.startswith("CONFIRMED_") for m in out.mappings)
