"""편집 실행기 — 편집 계획을 파일에 적용한다. 칸 글자 일부만 고치는 항목(text_edits)은 여기서 먼저 처리한다.

hwpx_edit_tool 은 web_office 마감 시험들이 기준 커밋과 같아야 하는 잠긴 파일이라 고치지 않는다.
그래서 text_edits 가 든 set_visual_cells 항목은 편집기에 넘기기 전에 이 모듈이 따로 적용하고,
나머지 계획만 apply_edit_plan 에 맡긴다. text_edits 항목이 없으면 계획을 그대로 넘긴다.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Any

_HWPX_DIR = Path(__file__).resolve().parents[1]
if str(_HWPX_DIR) not in sys.path:
    sys.path.insert(0, str(_HWPX_DIR))

from hwpx_edit_tool import (
    apply_edit_plan,  # type: ignore  # ruff: ignore[module-import-not-at-top-of-file]
)
from hwpx_package import (
    HwpxPackage,  # type: ignore  # ruff: ignore[module-import-not-at-top-of-file]
)
from hwpx_writer_adapter import (
    HwpxEditor,  # type: ignore  # ruff: ignore[module-import-not-at-top-of-file]
)


def split_text_edit_items(plan: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """계획에서 text_edits 가 든 칸 항목을 떼어 낸다. (나머지 계획, 떼어 낸 항목)"""
    items = [item for item in plan.get("set_visual_cells") or [] if item.get("text_edits")]
    if not items:
        return plan, []
    rest = {k: v for k, v in plan.items() if k != "set_visual_cells"}
    kept = [item for item in plan["set_visual_cells"] if not item.get("text_edits")]
    if kept:
        rest["set_visual_cells"] = kept
    return rest, items


def _apply_text_edit_items(package: HwpxPackage, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    editor = HwpxEditor(package)
    return [
        editor.set_table_visual_cell_text(
            int(item.get("table", item.get("table_index", 0))),
            int(item.get("visual_row", item.get("row", -1))),
            int(item.get("visual_col", item.get("col", -1))),
            str(item.get("value", "")),
            bool(item.get("clear_remaining", True)),
            item.get("text_edits") or None,
        )
        for item in items
    ]


def apply_plan(input_path: Path, output_path: Path, plan: dict[str, Any]) -> dict[str, Any]:
    """apply_edit_plan 과 같은 보고서를 돌려준다. text_edits 항목은 먼저 적용하고 보고서의 작업 목록에 앞서 싣는다."""
    input_path = Path(input_path)
    output_path = Path(output_path)
    rest, items = split_text_edit_items(plan)
    if not items:
        return apply_edit_plan(input_path, output_path, plan)

    with tempfile.TemporaryDirectory(prefix="hwpx_text_edit_") as tmp_dir:
        staged = Path(tmp_dir) / input_path.name
        package = HwpxPackage(input_path)
        edit_ops = _apply_text_edit_items(package, items)
        package.write_package(staged)
        report = apply_edit_plan(staged, output_path, rest)
    report["input"] = str(input_path)
    report["operations"] = edit_ops + list(report.get("operations", []))
    report["operation_count"] = len(report["operations"])
    if any("PASS" not in str(op.get("status", "")).upper() for op in edit_ops):
        report["status"] = "FAIL"
    return report
