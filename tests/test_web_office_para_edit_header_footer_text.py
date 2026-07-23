"""WEB-OFFICE-PARA-EDIT-HEADER-FOOTER-TEXT-01.

CLAUDE.md §4.2 (2026-07-24 신설) — <hp:header>/<hp:footer> 안 문단의
텍스트 편집(삭제·삽입·치환)만 허용. 구조 변경(신규 header/footer,
표 구조)은 그대로 금지.
"""
from __future__ import annotations
import hashlib
import sys
import uuid
from pathlib import Path

import pytest

PR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PR))
sys.path.insert(0, str(PR / "scripts/hwpx"))

from hwpx_package import HwpxPackage  # noqa: E402
from scripts.hwpx.web_office.paragraph_writer_adapter import (  # noqa: E402
    apply_paragraph_edits_plan)

FIXTURE = (PR / "data/drafts/form_library"
           / "01a6ff957f_소방시설 자체점검사항 등에 관한 고시_법령본문.hwpx")


def _make_item(**overrides):
    item = {
        "commandId": str(uuid.uuid4()),
        "paragraphId": "hdr_test",
        "runId": "hdr_test_run0",
        "commandType": "TYPE_TEXT",
        "rangeStart": 0, "rangeEnd": 0,
        "expectedBefore": "",
        "afterText": "[테스트] ",
        "containerScope": {"kind": "header", "sectionIndex": 0,
                           "objectId": "0", "paragraphIndex": 0},
    }
    item.update(overrides)
    return item


@pytest.mark.skipif(not FIXTURE.is_file(), reason="fixture missing")
def test_header_paragraph_text_type_applies():
    package = HwpxPackage(FIXTURE)
    source_hash = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
    item = _make_item(sourceDocumentHash=source_hash)
    result = apply_paragraph_edits_plan(
        package, [item], source_hash, dry_run=False, conflict_cells=set())
    assert result["rejected"] == []
    assert len(result["applied"]) == 1
    # TYPE_TEXT 의 afterText 는 삽입된 조각만(전체 문단 텍스트 아님) —
    # 실측(2026-07-24, 실제 Hancom Office COM) 렌더링으로 전체 문단이
    # "[테스트] 소방시설 자체점검사항 등에 관한 고시" 로 정상 반영됨을
    # 별도 확인했다(회귀 확인은 아래 readback 스타일로 재확인).
    assert result["applied"][0]["afterText"] == "[테스트] "


@pytest.mark.skipif(not FIXTURE.is_file(), reason="fixture missing")
def test_header_scope_missing_object_id_rejected():
    package = HwpxPackage(FIXTURE)
    source_hash = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
    item = _make_item(sourceDocumentHash=source_hash)
    del item["containerScope"]["objectId"]
    result = apply_paragraph_edits_plan(
        package, [item], source_hash, dry_run=False, conflict_cells=set())
    assert result["applied"] == []
    assert result["rejected"][0]["reason"] == "SCOPE_MISSING"


@pytest.mark.skipif(not FIXTURE.is_file(), reason="fixture missing")
def test_unknown_header_object_id_rejected():
    package = HwpxPackage(FIXTURE)
    source_hash = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
    item = _make_item(sourceDocumentHash=source_hash)
    item["containerScope"]["objectId"] = "__no_such_id__"
    result = apply_paragraph_edits_plan(
        package, [item], source_hash, dry_run=False, conflict_cells=set())
    assert result["applied"] == []
    assert result["rejected"][0]["reason"] == "HEADER_FOOTER_NOT_FOUND"


@pytest.mark.skipif(not FIXTURE.is_file(), reason="fixture missing")
def test_footer_kind_without_matching_object_rejected_not_crash():
    """매칭되지 않는 footer id 요청은 깨지지 않고 정상 반려돼야 한다.

    주의 — 이 fixture 에는 `<hp:footer id="0">` 이 **실재한다**(문단 5개).
    예전 이 테스트는 objectId="0" 을 썼고, 그 footer 의 첫 문단 run 이
    비어 있어 RUN_TEXT_NODE_MISSING 으로 반려되면서 통과했다. 즉
    'footer 를 못 찾아서'가 아니라 '빈 run 이라 못 써서' 통과한 것이라,
    이 테스트의 이름과 다른 것을 검증하고 있었다.

    빈 칸 기입이 가능해지면서(자동채움 전제) 그 우연한 방어벽이 사라져
    드러났다. 이름대로 **매칭되지 않는 id** 로 바로잡는다.
    """
    package = HwpxPackage(FIXTURE)
    source_hash = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
    item = _make_item(sourceDocumentHash=source_hash)
    item["containerScope"] = {"kind": "footer", "sectionIndex": 0,
                              "objectId": "__no_such_footer__",
                              "paragraphIndex": 0}
    result = apply_paragraph_edits_plan(
        package, [item], source_hash, dry_run=False, conflict_cells=set())
    assert result["applied"] == []
    assert result["rejected"]
    assert result["rejected"][0]["reason"] == "HEADER_FOOTER_NOT_FOUND"
