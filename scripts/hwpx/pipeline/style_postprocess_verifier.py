"""HWPX-CELL-STYLE-POSTPROCESS-01 — style 적용 결과 검증기.

Parser V2로 재파싱한 결과에서 셀 스타일 값을 검증한다.
원본 파일은 수정하지 않는다.
"""
from __future__ import annotations

from typing import Any


def _find_cell(tables, table_index: int, visual_row: int, visual_col: int) -> Any | None:
    for t in tables:
        if t.tableIndex != table_index:
            continue
        for c in t.cells:
            if c.visualRow == visual_row and c.visualCol == visual_col:
                return c
    return None


def verify_cell_fill_color(
    tables: list,
    table_index: int,
    visual_row: int,
    visual_col: int,
    expected_color: str,
) -> dict:
    """대상 셀의 fillColor가 기대값과 일치하는지 검증."""
    cell = _find_cell(tables, table_index, visual_row, visual_col)
    if cell is None:
        return {"status": "CELL_NOT_FOUND", "table_index": table_index,
                "visual_row": visual_row, "visual_col": visual_col}
    norm_expected = expected_color.upper().lstrip("#")
    norm_expected = f"#{norm_expected}" if not norm_expected.startswith("#") else norm_expected
    actual = (cell.fillColor or "").upper()
    match = actual == norm_expected
    return {
        "status": "PASS" if match else "MISMATCH",
        "expected": norm_expected,
        "actual": actual,
        "table_index": table_index,
        "visual_row": visual_row,
        "visual_col": visual_col,
        "borderFillIDRef": cell.borderFillIDRef,
    }


def verify_cell_font_height(
    tables: list,
    table_index: int,
    visual_row: int,
    visual_col: int,
    *,
    expected_max: int | None = None,
    expected_min: int | None = None,
) -> dict:
    """셀의 fontHeight 범위 검증 (shrink_to_fit 확인)."""
    cell = _find_cell(tables, table_index, visual_row, visual_col)
    if cell is None:
        return {"status": "CELL_NOT_FOUND", "table_index": table_index}
    fh = cell.fontHeight
    if fh is None:
        return {"status": "FONT_HEIGHT_NONE", "table_index": table_index,
                "visual_row": visual_row, "visual_col": visual_col}
    ok = True
    if expected_max is not None and fh > expected_max:
        ok = False
    if expected_min is not None and fh < expected_min:
        ok = False
    return {
        "status": "PASS" if ok else "MISMATCH",
        "fontHeight": fh,
        "expected_max": expected_max,
        "expected_min": expected_min,
        "visual_row": visual_row,
        "visual_col": visual_col,
    }


def verify_cell_alignment(
    tables: list,
    table_index: int,
    visual_row: int,
    visual_col: int,
    *,
    expected_vertical: str | None = None,
    expected_horizontal: str | None = None,
) -> dict:
    """셀의 verticalAlign / horizontalAlign 검증."""
    cell = _find_cell(tables, table_index, visual_row, visual_col)
    if cell is None:
        return {"status": "CELL_NOT_FOUND", "table_index": table_index}
    v_ok = True
    h_ok = True
    actual_v = (cell.verticalAlign or "").upper()
    actual_h = (cell.horizontalAlign or "").upper()
    if expected_vertical and actual_v != expected_vertical.upper():
        v_ok = False
    if expected_horizontal and actual_h != expected_horizontal.upper():
        h_ok = False
    return {
        "status": "PASS" if (v_ok and h_ok) else "MISMATCH",
        "actual_vertical": actual_v,
        "expected_vertical": expected_vertical,
        "actual_horizontal": actual_h,
        "expected_horizontal": expected_horizontal,
        "visual_row": visual_row,
        "visual_col": visual_col,
    }


def verify_no_dangling_style_refs(styles) -> dict:
    """StyleInfo의 danglingRefs가 비어있는지 검증."""
    dangling = list(getattr(styles, "danglingRefs", []) or [])
    return {
        "status": "PASS" if not dangling else "DANGLING_REFS_FOUND",
        "danglingRefs": dangling,
        "count": len(dangling),
    }


def compare_style_before_after(
    before_tables: list,
    after_tables: list,
    table_index: int,
    changed_cells: list[tuple[int, int]],
    unchanged_cells: list[tuple[int, int]] | None = None,
) -> dict:
    """편집 전후 스타일 비교.

    changed_cells: (visual_row, visual_col) 쌍 목록 — 변경 기대
    unchanged_cells: (visual_row, visual_col) 쌍 목록 — 보존 기대
    """
    results: list[dict] = []
    for vr, vc in changed_cells:
        before = _find_cell(before_tables, table_index, vr, vc)
        after = _find_cell(after_tables, table_index, vr, vc)
        changed = (
            before is not None and after is not None
            and before.borderFillIDRef != after.borderFillIDRef
        )
        results.append({
            "visual_row": vr, "visual_col": vc,
            "expected_change": True,
            "changed": changed,
            "before_borderFillIDRef": before.borderFillIDRef if before else None,
            "after_borderFillIDRef": after.borderFillIDRef if after else None,
        })
    for vr, vc in (unchanged_cells or []):
        before = _find_cell(before_tables, table_index, vr, vc)
        after = _find_cell(after_tables, table_index, vr, vc)
        preserved = (
            before is not None and after is not None
            and before.borderFillIDRef == after.borderFillIDRef
        )
        results.append({
            "visual_row": vr, "visual_col": vc,
            "expected_change": False,
            "preserved": preserved,
            "before_borderFillIDRef": before.borderFillIDRef if before else None,
            "after_borderFillIDRef": after.borderFillIDRef if after else None,
        })
    all_ok = all(
        r.get("changed", r.get("preserved", False))
        for r in results
    )
    return {
        "status": "PASS" if all_ok else "MISMATCH",
        "results": results,
    }
