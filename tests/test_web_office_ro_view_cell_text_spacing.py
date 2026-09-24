"""WEB-OFFICE-RO-VIEW-CELL-TEXT-SPACING 회귀 테스트 (서비스 수준, 개정 1).

기준서: docs/specs/2026-09-24_hwpx_33to02_merge_phase1_spec.md ### 개정 1.

셀 띄어쓰기 교정은 importer(ro_view_importer.py, HEAD 로 원복 — closeout
스위트가 봉인한 파일)가 아니라 service.py 의 `_cell_display_text(cell)` 에서만
한다. importer 의 cell['text'](normalizedText)는 field_roles 판정의 계약이라
바꾸지 않는다.

- a. 공백 보존: form_57.hwpx 를 서비스 파이프라인(_build_payload_from_upload +
  _render_body_html)에 태운 HTML `<td>` 내용(html.unescape) 중 15자+ 연속
  한글이 0건이어야 한다.
- b. 인위적 위반: `_cell_display_text` 를 `cell['text']` 그대로 반환하도록
  monkeypatch 하면(=교정 전 동작 흉내) 같은 측정에서 1건 이상 나와야 한다
  (교정이 실제 차이를 만든다는 증거).
- c. 폴백 단위 테스트: `_cell_display_text` 자체의 문단/텍스트 폴백 규칙.
"""
from __future__ import annotations
import html as _html
import re
import sys
from pathlib import Path

PR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PR))
sys.path.insert(0, str(PR / "scripts/hwpx"))

from scripts.hwpx.web_office import service as svc  # noqa: E402

FORM_57 = PR / "tests/fixtures/form_57.hwpx"

HANGUL_RUN_15 = re.compile(r"[가-힣]{15,}")


def _td_contents(body_html: str) -> list[str]:
    return re.findall(r"<td[^>]*>(.*?)</td>", body_html, re.S)


def _render_form_57() -> str:
    data = FORM_57.read_bytes()
    payload = svc._build_payload_from_upload(data)
    return svc._render_body_html(payload)


def test_form_57_rendered_td_has_no_long_hangul_run_spacing_preserved():
    body = _render_form_57()
    tds = _td_contents(body)
    assert tds, "표 셀(<td>)이 렌더되지 않음"
    violations = [t for t in tds if HANGUL_RUN_15.search(_html.unescape(t))]
    assert violations == []


def test_form_57_pre_fix_behavior_would_fail_spacing_check(monkeypatch):
    """교정 전 동작(cell['text']=normalizedText 그대로 표시)을 흉내내면
    같은 측정에서 15자+ 연속 한글이 1건 이상 나와야 한다 — 교정이 실제로
    차이를 만든다는 증거.
    """
    monkeypatch.setattr(svc, "_cell_display_text", lambda cell: cell.get("text") or "")
    body = _render_form_57()
    tds = _td_contents(body)
    violations = [t for t in tds if HANGUL_RUN_15.search(_html.unescape(t))]
    assert len(violations) >= 1, (
        "인위적 위반(교정 전 동작 흉내)에서도 위반이 0건 — "
        "교정이 실제 차이를 만든다는 증거를 만들지 못함(멈추고 보고 대상)"
    )


def test_cell_display_text_falls_back_to_text_when_no_paragraphs():
    assert svc._cell_display_text({"text": "가나", "paragraphs": []}) == "가나"


def test_cell_display_text_falls_back_to_text_when_paragraphs_empty_text():
    assert svc._cell_display_text(
        {"text": "가나", "paragraphs": [{"text": ""}]}
    ) == "가나"


def test_cell_display_text_joins_non_empty_paragraphs_with_newline():
    assert svc._cell_display_text(
        {"text": "x", "paragraphs": [{"text": "a b"}, {"text": "c"}]}
    ) == "a b\nc"
