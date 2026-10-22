"""요청 121 — 칸 종류 판정(cell_kind)과 다시 읽기 판정(reparse_verifier)의 규칙 시험."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
for _p in (_ROOT / "scripts", _ROOT / "scripts" / "hwpx"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from hwpx.parser.cell_kind import cell_kind, is_value_like
from hwpx.pipeline.pipeline_contract import PlanResult
from hwpx.pipeline.reparse_verifier import verify


def test_long_label_ending_with_sign_marker_is_sign():
    assert cell_kind("성능위주설계를한소방기술사성명 (서명또는인) (서명또는인)") == "sign"
    assert cell_kind("수급인 (서명또는인) 귀하") == "sign"


def test_plain_label_is_not_sign_or_notice():
    assert cell_kind("성명") == ""
    assert cell_kind("공사명") == ""


def test_notice_and_page_and_office():
    assert cell_kind("처리절차") == "notice"
    assert cell_kind("(앞 쪽)") == "page"
    assert cell_kind("접수번호") == "office"


def test_value_like_text_is_not_a_label():
    assert is_value_like("100%")
    assert is_value_like("2026-10-23")
    assert not is_value_like("공사명")


class _Doc:
    def __init__(self) -> None:
        self.tables: list = []
        self.warnings: list = []
        self.errors: list = []


def test_nothing_read_back_is_fail_not_pass():
    """쓴 칸을 하나도 다시 읽어 확인하지 못했으면 PASS 가 아니라 FAIL (거짓 통과 방지)."""
    result = verify(_Doc(), _Doc(), PlanResult(editPlan={}))
    assert result.decision == "FAIL"
    assert any("nothing_to_verify" in w for w in result.warnings)
