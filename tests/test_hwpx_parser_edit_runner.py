"""edit_runner — text_edits 항목은 잠긴 편집기(hwpx_edit_tool)를 거치지 않고 먼저 적용된다."""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "hwpx"))

from hwpx.pipeline.edit_runner import apply_plan, split_text_edit_items

NS_HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"


def _cell(col: int, paragraphs: list[str]) -> str:
    paras = "".join(f"<hp:p><hp:run><hp:t>{p}</hp:t></hp:run></hp:p>" for p in paragraphs)
    return (
        f'<hp:tc><hp:subList>{paras}</hp:subList>'
        f'<hp:cellAddr colAddr="{col}" rowAddr="0"/><hp:cellSpan colSpan="1" rowSpan="1"/></hp:tc>'
    )


def _write(path: Path) -> Path:
    section = (
        f'<?xml version="1.0" encoding="UTF-8"?><hp:sec xmlns:hp="{NS_HP}"><hp:tbl rowCnt="1" colCnt="2">'
        f'<hp:tr>{_cell(0, ["성명"])}{_cell(1, ["원 공사명:", "서명 또는 인"])}</hp:tr></hp:tbl></hp:sec>'
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("Contents/section0.xml", section.encode("utf-8"))
    return path


def _texts(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("Contents/section0.xml"))
    return [t.text or "" for t in root.iter(f"{{{NS_HP}}}t")]


def _ops_pass(report: dict) -> bool:
    # 합성 패키지는 머리글 파일이 없어 패키지 검증은 늘 FAIL 이다 — 편집 작업 자체의 결과만 본다
    return all("PASS" in str(op.get("status", "")).upper() for op in report["operations"])


def test_split_separates_only_text_edit_items():
    edit_item = {"table": 0, "visual_row": 0, "visual_col": 1, "value": "x", "text_edits": [{"kind": "after"}]}
    plain = {"table": 0, "visual_row": 0, "visual_col": 0, "value": "y"}
    rest, items = split_text_edit_items({"set_visual_cells": [plain, edit_item], "set_cells": [1]})
    assert items == [edit_item]
    assert rest["set_visual_cells"] == [plain] and rest["set_cells"] == [1]


def test_split_leaves_plan_alone_without_text_edits():
    plan = {"set_visual_cells": [{"table": 0, "visual_row": 0, "visual_col": 0, "value": "y"}]}
    rest, items = split_text_edit_items(plan)
    assert items == [] and rest is plan


def test_text_edit_item_changes_only_its_paragraph(tmp_path):
    src = _write(tmp_path / "src.hwpx")
    plan = {
        "set_visual_cells": [
            {
                "table": 0,
                "visual_row": 0,
                "visual_col": 1,
                "value": "원 공사명: OO공사",
                "text_edits": [{"kind": "after", "anchor": "원 공사명:", "value": "OO공사"}],
            }
        ]
    }
    report = apply_plan(src, tmp_path / "out.hwpx", plan)
    assert _ops_pass(report), report["operations"]
    assert report["input"] == str(src)
    assert report["operation_count"] == len(report["operations"]) >= 1
    assert _texts(tmp_path / "out.hwpx") == ["성명", "원 공사명: OO공사", "서명 또는 인"]


def test_mixed_plan_applies_both_kinds(tmp_path):
    src = _write(tmp_path / "src.hwpx")
    plan = {
        "set_visual_cells": [
            {"table": 0, "visual_row": 0, "visual_col": 0, "value": "홍길동"},
            {
                "table": 0,
                "visual_row": 0,
                "visual_col": 1,
                "value": "원 공사명: OO공사",
                "text_edits": [{"kind": "after", "anchor": "원 공사명:", "value": "OO공사"}],
            },
        ]
    }
    report = apply_plan(src, tmp_path / "out.hwpx", plan)
    assert _ops_pass(report), report["operations"]
    assert _texts(tmp_path / "out.hwpx") == ["홍길동", "원 공사명: OO공사", "서명 또는 인"]


def test_missing_anchor_fails_the_report(tmp_path):
    src = _write(tmp_path / "src.hwpx")
    plan = {
        "set_visual_cells": [
            {
                "table": 0,
                "visual_row": 0,
                "visual_col": 1,
                "value": "x",
                "text_edits": [{"kind": "after", "anchor": "없는라벨:", "value": "x"}],
            }
        ]
    }
    report = apply_plan(src, tmp_path / "out.hwpx", plan)
    assert report["status"] == "FAIL"
    assert not _ops_pass(report)
