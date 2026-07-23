"""빈 입력칸에 글자를 쓸 수 있는가 — 자동채움의 전제 조건.

배경:
    서식의 빈 입력칸은 run 은 있는데 그 안에 텍스트 노드가 없다.

        <hp:run charPrIDRef="11"/>                          ← 빈 칸
        <hp:run charPrIDRef="10"><hp:t>성명</hp:t></hp:run>   ← 채운 칸

    writer 는 넣을 자리를 못 찾아 RUN_TEXT_NODE_MISSING 으로 거부했다.
    **자동채움이 노리는 칸은 정의상 전부 빈 칸이므로, 채울 수 있는 칸이
    하나도 없었다.** 기존 문단 편집 시험이 통과해온 것은 이미 글자가 있는
    칸을 고치는 경우였기 때문에 이 구멍이 드러나지 않았다.

    (2026-07-24 전기사용신청서 종단 시험에서 발견)

수리:
    빈 run 에 <hp:t> 를 만들어 넣는다. **삽입에 한해서만** 만든다 —
    교체·삭제이거나 run 에 다른 자식(hp:ctrl 등)이 있으면 종전대로 거부해
    안전한 쪽으로 실패한다. charPrIDRef 는 run 의 것을 그대로 쓰므로
    CLAUDE.md §4 "신규 charPr 생성 금지" 에 저촉되지 않는다.
"""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

PR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PR))
sys.path.insert(0, str(PR / "scripts/hwpx"))

from scripts.hwpx.hwpx_paragraph_ops import (  # noqa: E402
    STATUS_OK, STATUS_RUN_TEXT_NODE_MISSING,
    apply_text_range_edit, paragraph_runs, run_text,
)

NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"
Q = "{%s}" % NS


def _para(run_xml: str) -> ET.Element:
    return ET.fromstring(
        f'<hp:p xmlns:hp="{NS}" paraPrIDRef="137">{run_xml}</hp:p>')


# ── 빈 칸에 쓰기 ────────────────────────────────────────────────

def test_insert_into_empty_run_creates_text_node():
    """자식이 없는 run 에 삽입하면 <hp:t> 가 생기고 글자가 들어간다."""
    p = _para('<hp:run charPrIDRef="11"/>')
    run = paragraph_runs(p)[0]
    assert run.find(f"{Q}t") is None, "전제: 텍스트 노드가 없다"

    r = apply_text_range_edit(p, run, 0, 0, "홍길동", expected_before="")

    assert r["status"] == STATUS_OK, r
    assert run_text(run) == "홍길동"
    assert run.find(f"{Q}t") is not None, "<hp:t> 가 만들어져야 한다"


def test_created_text_node_keeps_char_pr():
    """charPrIDRef 는 run 의 것을 그대로 — 신규 charPr 을 만들지 않는다."""
    p = _para('<hp:run charPrIDRef="11"/>')
    run = paragraph_runs(p)[0]
    r = apply_text_range_edit(p, run, 0, 0, "값", expected_before="")
    assert r["status"] == STATUS_OK
    assert run.attrib.get("charPrIDRef") == "11"
    assert r["charPrIDRef"] == "11"


def test_created_text_node_uses_same_namespace():
    """만든 노드가 hp 네임스페이스여야 한컴이 읽는다."""
    p = _para('<hp:run charPrIDRef="11"/>')
    run = paragraph_runs(p)[0]
    apply_text_range_edit(p, run, 0, 0, "값", expected_before="")
    t = list(run)[0]
    assert t.tag == f"{Q}t", t.tag


def test_written_text_survives_serialization():
    """직렬화 후에도 남아야 한다(저장은 XML 을 다시 쓰는 일이다)."""
    p = _para('<hp:run charPrIDRef="11"/>')
    run = paragraph_runs(p)[0]
    apply_text_range_edit(p, run, 0, 0, "가나다", expected_before="")
    xml = ET.tostring(p, encoding="unicode")
    assert "가나다" in xml
    again = ET.fromstring(xml)
    assert run_text(paragraph_runs(again)[0]) == "가나다"


# ── 안전한 쪽으로 실패해야 하는 경우 ────────────────────────────

def test_non_empty_run_with_other_children_still_rejected():
    """hp:ctrl 등이 섞인 run 은 건드리지 않는다 — 종전대로 거부."""
    p = _para('<hp:run charPrIDRef="11"><hp:ctrl/></hp:run>')
    run = paragraph_runs(p)[0]
    r = apply_text_range_edit(p, run, 0, 0, "값", expected_before="")
    assert r["status"] == STATUS_RUN_TEXT_NODE_MISSING, r


def test_non_insert_range_on_empty_run_rejected():
    """교체·삭제는 지울 글자가 있어야 한다 — 빈 run 에서는 거부."""
    p = _para('<hp:run charPrIDRef="11"/>')
    run = paragraph_runs(p)[0]
    r = apply_text_range_edit(p, run, 0, 3, "값", expected_before="기존")
    assert r["status"] == STATUS_RUN_TEXT_NODE_MISSING, r


def test_nonzero_caret_on_empty_run_rejected():
    """빈 run 의 offset 5 는 존재하지 않는 자리다."""
    p = _para('<hp:run charPrIDRef="11"/>')
    run = paragraph_runs(p)[0]
    r = apply_text_range_edit(p, run, 5, 5, "값", expected_before="")
    assert r["status"] == STATUS_RUN_TEXT_NODE_MISSING, r


def test_expected_before_mismatch_on_empty_run_rejected():
    """빈 칸인데 기존 글자를 기대했다면 전제가 틀린 것 — 거부."""
    p = _para('<hp:run charPrIDRef="11"/>')
    run = paragraph_runs(p)[0]
    r = apply_text_range_edit(p, run, 0, 0, "값", expected_before="있던글자")
    assert r["status"] == STATUS_RUN_TEXT_NODE_MISSING, r


# ── 기존 동작 불변 ──────────────────────────────────────────────

def test_existing_text_edit_unchanged():
    """글자가 있는 run 의 편집은 종전 그대로."""
    p = _para('<hp:run charPrIDRef="10"><hp:t>전기사용자</hp:t></hp:run>')
    run = paragraph_runs(p)[0]
    r = apply_text_range_edit(p, run, 0, 2, "수도", expected_before="전기")
    assert r["status"] == STATUS_OK, r
    assert run_text(run) == "수도사용자"


def test_no_duplicate_text_node_created():
    """이미 <hp:t> 가 있으면 새로 만들지 않는다."""
    p = _para('<hp:run charPrIDRef="10"><hp:t>가</hp:t></hp:run>')
    run = paragraph_runs(p)[0]
    apply_text_range_edit(p, run, 0, 0, "나", expected_before="")
    assert len([e for e in run if e.tag == f"{Q}t"]) == 1
    assert run_text(run) == "나가"
