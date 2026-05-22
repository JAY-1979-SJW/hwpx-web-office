"""
Audit script: HWPX-EDITOR-SHRINK-TO-FIT-OPTION-PROPAGATION-01.

shrink_to_fit / vertical_align 옵션이 4개 plan 키 (set_cells, set_cells_by_label,
set_cells_by_text, set_visual_cells)에서 일관되게 처리되는지 정적 감사한다.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EDIT_TOOL = PROJECT_ROOT / "scripts" / "hwpx" / "hwpx_edit_tool.py"
TABLE_OPS = PROJECT_ROOT / "scripts" / "hwpx" / "hwpx_table_ops.py"
TEST_FILE = PROJECT_ROOT / "tests" / "test_hwpx_shrink_to_fit_plan_options.py"
FULL_VERIFY = PROJECT_ROOT / "scripts" / "local" / "hwpx_full_verify.py"
CONTRACT = PROJECT_ROOT / "docs" / "contracts" / "hwpx_editor_api_contract.md"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.exists() else ""


def audit() -> dict:
    edit_src = _read(EDIT_TOOL)
    ops_src = _read(TABLE_OPS)
    test_src = _read(TEST_FILE)
    verify_src = _read(FULL_VERIFY)
    contract_src = _read(CONTRACT)

    checks = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"name": name, "status": "PASS" if ok else "FAIL", "detail": detail})

    # 1. 기반 함수 존재
    check("shrink_table_visual_cell_text_to_fit defined",
          "def shrink_table_visual_cell_text_to_fit" in ops_src,
          str(TABLE_OPS))
    check("estimate_text_fit defined",
          "def estimate_text_fit" in ops_src,
          str(TABLE_OPS))
    check("clone_char_pr_with_height defined",
          "def clone_char_pr_with_height" in ops_src,
          str(TABLE_OPS))

    # 2. 공통 helper 존재
    check("_apply_cell_post_edit_options helper defined",
          "def _apply_cell_post_edit_options" in edit_src,
          str(EDIT_TOOL))
    check("_resolve_visual_coords helper defined",
          "def _resolve_visual_coords" in edit_src,
          str(EDIT_TOOL))

    # 3. 4개 plan 키 처리부에서 helper 호출
    def _block_after(src: str, marker: str, length: int = 1200) -> str:
        idx = src.find(marker)
        return src[idx:idx + length] if idx >= 0 else ""

    set_cells_block = _block_after(edit_src, 'plan.get("set_cells",')
    set_cells_by_text_block = _block_after(edit_src, 'plan.get("set_cells_by_text"')
    set_cells_by_label_block = _block_after(edit_src, 'plan.get("set_cells_by_label"')
    set_visual_cells_block = _block_after(edit_src, 'plan.get("set_visual_cells"')

    check("set_cells uses _apply_cell_post_edit_options",
          "_apply_cell_post_edit_options" in set_cells_block,
          "scripts/hwpx/hwpx_edit_tool.py set_cells block")
    check("set_cells_by_text uses _apply_cell_post_edit_options",
          "_apply_cell_post_edit_options" in set_cells_by_text_block,
          "scripts/hwpx/hwpx_edit_tool.py set_cells_by_text block")
    check("set_cells_by_label uses _apply_cell_post_edit_options",
          "_apply_cell_post_edit_options" in set_cells_by_label_block,
          "scripts/hwpx/hwpx_edit_tool.py set_cells_by_label block")
    check("set_visual_cells uses _apply_cell_post_edit_options",
          "_apply_cell_post_edit_options" in set_visual_cells_block,
          "scripts/hwpx/hwpx_edit_tool.py set_visual_cells block")

    # 4. 옵션이 모두 shrink_to_fit / vertical_align로 처리되는지 (helper 안에)
    helper_block = _block_after(edit_src, "def _apply_cell_post_edit_options", 1500)
    check("helper handles shrink_to_fit option",
          'item.get("shrink_to_fit")' in helper_block,
          "_apply_cell_post_edit_options")
    check("helper handles vertical_align option",
          'item.get("vertical_align")' in helper_block,
          "_apply_cell_post_edit_options")
    check("helper calls shrink_table_visual_cell_text_to_fit",
          "shrink_table_visual_cell_text_to_fit" in helper_block,
          "_apply_cell_post_edit_options")
    check("helper calls set_table_visual_cell_vertical_align",
          "set_table_visual_cell_vertical_align" in helper_block,
          "_apply_cell_post_edit_options")

    # 5. 옵션 미지정 시 helper 미호출 (default False)
    check("helper returns early when no visual coords",
          "visual_row is None or visual_col is None" in helper_block,
          "_apply_cell_post_edit_options")

    # 6. 테스트 존재
    check("regression test file present",
          TEST_FILE.exists(),
          str(TEST_FILE))
    if test_src:
        for fn in (
            "test_set_cells_without_shrink_keeps_original_charpr",
            "test_set_cells_with_shrink_to_fit_creates_clone",
            "test_set_cells_by_label_with_shrink_to_fit_creates_clone",
            "test_set_cells_by_text_with_shrink_to_fit_creates_clone",
            "test_set_visual_cells_shrink_to_fit_still_works",
            "test_shrink_to_fit_does_not_alter_original_charpr",
            "test_mimetype_remains_zip_stored_with_shrink",
            "test_no_options_means_no_post_edit_calls",
        ):
            check(f"test case present: {fn}", f"def {fn}" in test_src, str(TEST_FILE))

    # 7. full verify 스크립트 존재
    check("hwpx_full_verify.py present",
          FULL_VERIFY.exists() and "def verify(" in verify_src,
          str(FULL_VERIFY))

    # 8. API 계약 변경 영향 없음: editor.set_table_cell_text / set_table_visual_cell_text 서명 변경 없음
    adapter_src = _read(PROJECT_ROOT / "scripts/hwpx/hwpx_writer_adapter.py")
    check("editor.set_table_cell_text signature unchanged",
          bool(re.search(r"def set_table_cell_text\b", adapter_src)) and bool(re.search(r"def set_table_visual_cell_text\b", adapter_src)),
          "scripts/hwpx/hwpx_writer_adapter.py")

    # 9. API 계약 문서에 shrink_to_fit 옵션 기재
    check("API contract documents shrink_to_fit",
          "shrink_to_fit" in contract_src,
          str(CONTRACT) if CONTRACT.exists() else "missing")

    # 10. mimetype ZIP_STORED 보존 패치 유지
    pkg_src = _read(PROJECT_ROOT / "scripts/hwpx/hwpx_package.py")
    check("hwpx_package preserves compress_type explicitly",
          "new_info.compress_type = info.compress_type" in pkg_src,
          "scripts/hwpx/hwpx_package.py")

    failed = [c for c in checks if c["status"] != "PASS"]
    return {
        "status": "PASS" if not failed else "FAIL",
        "checks": checks,
        "fail_count": len(failed),
        "pass_count": len(checks) - len(failed),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="emit JSON only")
    args = parser.parse_args()
    report = audit()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"[shrink_to_fit propagation audit] {report['status']} "
              f"pass={report['pass_count']} fail={report['fail_count']}")
        for c in report["checks"]:
            mark = "OK" if c["status"] == "PASS" else "FAIL"
            print(f"  [{mark}] {c['name']}")
            if c["status"] != "PASS" and c["detail"]:
                print(f"        detail: {c['detail']}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
